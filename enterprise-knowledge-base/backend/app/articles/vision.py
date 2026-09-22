"""可插拔视觉分析模块 — 将现场照片转换为文字描述

- 设计为抽象接口 + OpenAI 兼容实现，方便后续切换提供商。
- API key 未配置时自动降级为占位描述，不影响文章生成流程。
- 逐张处理、即时释放内存。
"""

import base64
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.minio_client import get_minio_client


# ============================================================
# 抽象接口
# ============================================================

class VisionProvider(ABC):
    """视觉模型抽象接口"""

    @abstractmethod
    async def analyze(self, image_base64: str, prompt: str) -> str: ...


# ============================================================
# OpenAI 兼容实现（覆盖 SiliconFlow / OpenAI / 任何兼容端点）
# ============================================================

class OpenAICompatibleVisionProvider(VisionProvider):
    """支持所有 OpenAI 兼容 API 的多模态视觉模型"""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def analyze(self, image_base64: str, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


# ============================================================
# 工厂函数
# ============================================================

def get_vision_provider() -> VisionProvider | None:
    """根据配置返回视觉提供商实例；未配置 key 时返回 None"""
    if not settings.vision_model_api_key:
        logger.warning("vision_api_key_not_configured")
        return None
    return OpenAICompatibleVisionProvider(
        base_url=settings.vision_model_base_url,
        api_key=settings.vision_model_api_key,
        model=settings.vision_model_name,
    )


# ============================================================
# 主入口
# ============================================================

_PHOTO_PROMPT = """你是一位建筑防潮防水专家。请如实描述这张照片中确实可见的内容，用于撰写专业 GEO 文章。严格遵守：

1. 只描述画面中明确可见的材料、设备、工具、施工工艺、现场环境（地下室/外墙/地面等）；
2. 看不到或无法确定的内容一律不写，必要时写"无法确认"，严禁推测、脑补、编造设备型号或工艺名称；
3. 不要评价照片质量，不要过度解读；
4. 用中文、客观、简洁地分条描述，每条不超过 20 字。"""


async def analyze_photos(
    photo_object_names: list[str],
    topic: str,
) -> str:
    """批量分析照片，返回汇总的描述文本。

    逐张下载 → base64 → 视觉模型分析 → 即时释放内存。
    视觉模型不可用时返回占位描述。
    """
    provider = get_vision_provider()
    if provider is None:
        desc = (
            f"文章主题「{topic}」配有 {len(photo_object_names)} 张现场照片，编号为："
            + "、".join(f"照片{i + 1}" for i in range(len(photo_object_names)))
            + "。"
            f"请在正文中为每张照片插入 [IMAGE: 照片N: 配图建议: xxx] 标记"
            f"（如施工现场、设备细节、环境场景等），N 必须来自上方编号，每张照片至少使用一次。"
            f"示例：[IMAGE: 照片1: 配图建议: 电渗透设备安装现场全貌]"
        )
        logger.info("vision_skipped", photo_count=len(photo_object_names), reason="no_api_key")
        return desc

    minio_client = get_minio_client()
    descriptions: list[str] = []
    prompt = _PHOTO_PROMPT + f"\n\n文章主题：{topic}"

    for i, name in enumerate(photo_object_names):
        try:
            # 1. 从 MinIO 下载
            response = minio_client.get_object("knowledge-docs", name)
            data = response.read()
            response.close()
            response.release_conn()

            # 2. base64 编码
            img_b64 = base64.b64encode(data).decode()

            # 3. 立即释放原始字节
            del data

            # 4. 调用视觉模型
            desc = await provider.analyze(img_b64, prompt)
            descriptions.append(f"【照片 {i + 1}：{name.rsplit('/', 1)[-1]}】\n{desc}")

            # 5. 释放 base64 字符串
            del img_b64

            logger.info("vision_photo_analyzed", object_name=name)

        except Exception as exc:
            logger.warning("vision_photo_failed", object_name=name, error=str(exc))
            descriptions.append(f"【照片 {i + 1}：{name}】\n（图片分析失败：{exc}）")

    # 如果所有照片分析都失败了（如 API key 过期），提供兜底指引
    if all("（图片分析失败" in d for d in descriptions):
        recovery = (
            f"视觉分析暂时不可用，但文章配合 {len(photo_object_names)} 张现场照片展示，编号为："
            + "、".join(f"照片{i + 1}" for i in range(len(photo_object_names)))
            + "。"
            f"请在正文合适位置插入 `[IMAGE: 照片N: 配图建议: xxx]` 标记来描述每张照片适合展示的内容"
            f"（如施工现场全貌、设备安装细节、防水处理前后对比等），N 必须来自上方编号，每张照片至少使用一次。"
            f"例如：[IMAGE: 照片1: 配图建议: 电渗透设备安装完成后的地下室全貌]"
        )
        descriptions.append(recovery)

    return "\n\n---\n\n".join(descriptions)

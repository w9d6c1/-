"""发布集成 — 微信公众号 API + Wechatsync CLI + 文件导出

三层发布能力：
1. 微信公众号草稿 API (direct_api)
2. Wechatsync CLI 多平台发布 (wechatsync)
3. DOCX / HTML / Markdown 文件导出 (export)

参照: app/core/minio_client.py (自包含工具模块模式)
"""

import asyncio
import base64
import json
import re
import tempfile
import time
from io import BytesIO
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import logger

# ============================================================
# 平台注册表
# ============================================================

PLATFORMS: dict[str, dict] = {
    "toutiao":       {"name": "头条号",    "method": "wechatsync"},
    "baijia":        {"name": "百家号",    "method": "wechatsync"},
    "zhihu":         {"name": "知乎",      "method": "wechatsync"},
    "wangyi":        {"name": "网易号",    "method": "wechatsync"},
    "csdn":          {"name": "CSDN",      "method": "wechatsync"},
    "jianshu":       {"name": "简书",      "method": "wechatsync"},
    "weibo":         {"name": "微博",      "method": "wechatsync"},
    "xiaohongshu":   {"name": "小红书",    "method": "wechatsync"},
    "yidianhao":     {"name": "一点号",    "method": "wechatsync"},
    "douyin_tuwen":  {"name": "抖音图文",  "method": "wechatsync"},
}

# wechatsync 扩展内部平台 key 映射（扩展侧 ID 与本系统不一致的平台）
_WECHATSYNC_PLATFORM_MAP = {
    "baijia": "baidu",
    "wangyi": "netease",
    "yidianhao": "yidian",
    "douyin_tuwen": "douyin",
}


def list_platforms() -> list[dict]:
    """列出所有可用平台及发布方式"""
    result = []
    for pid, info in PLATFORMS.items():
        result.append({
            "platform": pid,
            "name": info["name"],
            "method": info["method"],
            "available": True,  # TODO: 检测 wechatsync CLI 可用性
        })
    return result


# ============================================================
# 微信公众号草稿 API
# ============================================================

_WECHAT_TOKEN_CACHE: dict[str, dict] = {}


async def publish_to_wechat_mp(
    title: str,
    content_md: str,
    appid: str = "",
    appsecret: str = "",
    image_placement: list[dict] | None = None,
) -> dict:
    """发布文章到微信公众号草稿箱

    优先使用传入的 appid/appsecret，否则回退到 settings 中的全局配置。
    配图以 base64 内嵌进 HTML，无需外部图片地址。
    """
    _appid = appid or settings.wechat_mp_appid
    _secret = appsecret or settings.wechat_mp_appsecret

    if not _appid or not _secret:
        return {"success": False, "url": None, "error": "微信公众号 appid/appsecret 未配置"}

    # 为每个账号独立缓存 token（按 appid 分 key）
    cache_key = f"token:{_appid}"
    now = time.time()
    cache = _WECHAT_TOKEN_CACHE.get(cache_key, {"token": "", "expires_at": 0})
    if cache["token"] and now < cache["expires_at"] - 300:
        token = cache["token"]
    else:
        _url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": _appid,
            "secret": _secret,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(_url, params=params)
                data = resp.json()
                if "access_token" in data:
                    token = data["access_token"]
                    _WECHAT_TOKEN_CACHE[cache_key] = {"token": token, "expires_at": now + data.get("expires_in", 7200)}
                else:
                    return {"success": False, "url": None, "error": f"获取微信 access_token 失败: {data}"}
        except Exception as exc:
            return {"success": False, "url": None, "error": str(exc)}

    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    # 将 Markdown 转为简单 HTML（微信接受富文本）；配图标记已解析为 base64 内嵌
    prepared = prepare_publish_content(title, content_md, image_placement)
    html_content = prepared["html"]

    payload = {
        "articles": [{
            "title": title,
            "content": html_content,
            "need_open_comment": 0,
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if "media_id" in data:
                logger.info("wechat_publish_success", title=title)
                return {"success": True, "url": None, "media_id": data["media_id"]}
            else:
                err = data.get("errmsg", str(data))
                logger.warning("wechat_publish_failed", error=err)
                return {"success": False, "url": None, "error": err}
    except Exception as exc:
        return {"success": False, "url": None, "error": str(exc)}


def _md_to_wechat_html(md_content: str) -> str:
    """简易 Markdown → 微信兼容 HTML（粗体、标题、段落）"""
    # 微信草稿接受基本的 HTML 标签
    import re
    html = md_content
    html = re.sub(r"^### (.+)", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\n\n", "</p><p>", html)
    html = f"<section><p>{html}</p></section>"
    return html


# ============================================================
# Wechatsync CLI
# ============================================================

async def publish_via_wechatsync(
    title: str,
    content_md: str,
    platform: str,
    credentials: dict | None = None,
    image_placement: list[dict] | None = None,
) -> dict:
    """通过 Wechatsync CLI 发布文章到指定平台草稿箱

    若提供 credentials，将写入临时配置文件供 CLI 使用。
    配图以公开 URL 形式写入 Markdown，由 CLI 下载后上传到平台。
    """
    prepared = prepare_publish_content(title, content_md, image_placement)
    publish_md = prepared["markdown"]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    ) as f:
        f.write(f"# {title}\n\n{publish_md}")
        tmp_path = f.name

    env = None
    if credentials:
        import os
        env = {}
        for key, val in credentials.items():
            env[f"WECHATSYNC_{key.upper()}"] = str(val) if val else ""

    try:
        proc = await asyncio.create_subprocess_exec(
            settings.wechatsync_cli_path,
            "sync",
            str(tmp_path),
            "--platforms", platform,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **env} if env else None,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info("wechatsync_publish_success", platform=platform)
            return {"success": True, "url": None, "output": stdout.decode()}
        else:
            err = stderr.decode() or f"exit code {proc.returncode}"
            logger.warning("wechatsync_publish_failed", platform=platform, error=err)
            return {"success": False, "url": None, "error": err}
    except FileNotFoundError:
        return {"success": False, "url": None, "error": f"wechatsync CLI 未安装 ({settings.wechatsync_cli_path})"}
    except Exception as exc:
        return {"success": False, "url": None, "error": str(exc) or repr(exc)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def publish_via_bridge(
    title: str,
    content_md: str,
    platform: str,
    account_group: str,
    token: str,
    image_placement: list[dict] | None = None,
) -> dict:
    """通过本机发布桥接器(3010)发布文章到指定平台

    桥接器按账号组路由到对应端口，连接 Chrome 扩展，使用浏览器已登录身份发布到草稿箱。
    同时携带 Markdown（公开 URL 图片）与 HTML（base64 内嵌图片），兼容各平台扩展对两种格式的接受度。
    """
    ext_platform = _WECHATSYNC_PLATFORM_MAP.get(platform, platform)
    prepared = prepare_publish_content(title, content_md, image_placement)
    # 始终发送 base64 HTML，避免 Chrome 扩展因外部 URL 不可达而无法下载图片
    payload_content = prepared["html"]
    try:
        # CLI 等待 Chrome 扩展重连最长 240s + 同步耗时，需大于桥接器 spawn 超时(480s)
        async with httpx.AsyncClient(timeout=510.0) as client:
            resp = await client.post(
                f"{settings.publisher_bridge_url}/api/publish",
                json={
                    "title": title,
                    "markdown": prepared["markdown"],
                    "content": payload_content,
                    "platform": ext_platform,
                    "group": account_group,
                    "token": token,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info("bridge_publish_success", platform=platform, group=account_group)
                return data
            return {"success": False, "url": None, "error": f"桥接器返回 {resp.status_code}"}
    except httpx.ConnectError:
        logger.warning("bridge_unreachable", group=account_group)
        return {"success": False, "url": None, "error": "桥接器未启动(3010不可达)"}
    except httpx.TimeoutException as exc:
        logger.error("bridge_publish_timeout", error=repr(exc))
        return {"success": False, "url": None, "error": f"桥接器响应超时: {repr(exc)}"}
    except Exception as exc:
        logger.error("bridge_publish_error", error=repr(exc))
        return {"success": False, "url": None, "error": str(exc) or repr(exc)}


# ============================================================
# 照片解析 — 下载 MinIO 图片供导出内嵌
# ============================================================

_PHOTO_BUCKET = "knowledge-docs"
# 兼容新格式 [IMAGE: 照片N: 配图建议: xxx] 与旧格式 [IMAGE: 配图建议: xxx]
_IMAGE_MARKER_RE = re.compile(
    r"\[IMAGE:\s*(?:照片\s*(\d+)\s*[:：])?\s*配图建议[:：]\s*(.+?)\]",
    re.IGNORECASE,
)


def _download_photo(object_name: str) -> bytes | None:
    """从 MinIO 同步下载单张照片，返回字节；失败返回 None"""
    try:
        from app.core.minio_client import get_minio_client
        client = get_minio_client()
        response = client.get_object(_PHOTO_BUCKET, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except Exception as exc:
        logger.warning("photo_download_failed", object_name=object_name, error=str(exc))
        return None


def _compress_image(data: bytes, max_width: int = 1200, quality: int = 80) -> bytes:
    """压缩图片：限制最大宽度 + JPEG 质量压缩，减少 base64 payload 体积。

    原图 2MB JPEG → 压缩后通常 200-400KB，base64 编码后体积减少约 70-80%。
    """
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(data))
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("image_compress_failed", error=str(exc))
        return data


def _resolve_markers_to_photos(
    content: str,
    image_placement: list[dict],
    download: bool = True,
) -> list[dict]:
    """提取正文中的 [IMAGE: 配图建议: xxx] 标记，匹配 placement 并下载照片。

    返回列表: [{marker, caption, object_name, photo_bytes, photo_base64}, ...]
    """
    results: list[dict] = []
    for i, match in enumerate(_IMAGE_MARKER_RE.finditer(content)):
        caption = match.group(2).strip()
        full_marker = match.group(0)
        # 位置优先：image_placement 由 generator 按标记顺序提取，保证一一对应；
        # caption 匹配仅作为 placement 耗尽时的兜底（避免重复 caption 全部错配第一张）。
        placement = (
            image_placement[i]
            if i < len(image_placement)
            else next(
                (p for p in image_placement if p.get("caption", "").strip().lower() == caption.lower()),
                None,
            )
        )

        obj_name = placement.get("object_name") if placement else None
        photo_bytes = _download_photo(obj_name) if (download and obj_name) else None
        if photo_bytes:
            photo_bytes = _compress_image(photo_bytes)
        photo_b64 = base64.b64encode(photo_bytes).decode() if photo_bytes else None

        results.append({
            "marker": full_marker,
            "caption": caption,
            "object_name": obj_name,
            "photo_bytes": photo_bytes,
            "photo_base64": photo_b64,
        })
    return results


def _photo_mime(object_name: str) -> str:
    """根据对象名扩展名返回 MIME 类型（默认 jpeg）"""
    lower = (object_name or "").lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".bmp"):
        return "image/bmp"
    return "image/jpeg"


def prepare_publish_content(
    title: str,
    content: str,
    image_placement: list[dict] | None = None,
) -> dict[str, str]:
    """发布前解析 [IMAGE] 标记，生成带真实图片的两份正文。

    返回:
    - markdown: 标记 → ![配图建议](公开URL)，供支持 Markdown 图片的平台扩展下载上传
    - html:     标记 → <img src="data:base64"> 内嵌并转为 HTML，
                供富文本平台（微信直连）与不依赖外网下载的扩展使用
    - has_photos: 是否解析出照片
    """
    md_content = content
    html_content = content

    photos = _resolve_markers_to_photos(content, image_placement or [], download=True)
    if photos:
        api_base = (settings.publish_public_base_url or "").rstrip("/") or _get_api_base_url()
        for photo in photos:
            caption = photo["caption"]
            obj_name = photo["object_name"]

            if obj_name:
                url = f"{api_base}/api/public/images/{obj_name}"
                md_content = md_content.replace(photo["marker"], f"![{caption}]({url})")
            else:
                md_content = md_content.replace(photo["marker"], f"> 📷 {caption}")

            if photo["photo_base64"]:
                mime = _photo_mime(obj_name)
                img_tag = (
                    f'<img src="data:{mime};base64,{photo["photo_base64"]}" '
                    f'alt="{caption}" style="max-width:100%" />'
                )
                html_content = html_content.replace(photo["marker"], img_tag)
            else:
                html_content = html_content.replace(
                    photo["marker"], f"<p>📷 {caption}</p>"
                )

    return {
        "markdown": md_content,
        "html": _md_to_wechat_html(html_content),
        "has_photos": bool(photos),
    }


# ============================================================
# 文件导出
# ============================================================

def _get_api_base_url() -> str:
    """获取 API 基础 URL，用于 MD 导出中的图片引用"""
    host = getattr(settings, "app_public_host", None) or "localhost"
    scheme = "https" if getattr(settings, "app_https", False) else "http"
    port = getattr(settings, "app_public_port", None)
    if port and port not in (80, 443):
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def export_markdown(title: str, content: str, image_placement: list[dict] | None = None) -> bytes:
    """导出为 Markdown 文件，将 [IMAGE] 标记替换为 ![](photo_url)"""
    md_content = content
    if image_placement:
        photos = _resolve_markers_to_photos(content, image_placement, download=False)
        api_base = _get_api_base_url()
        for photo in photos:
            if photo["object_name"]:
                url = f"{api_base}/api/admin/articles/photos/{photo['object_name']}"
                md_content = md_content.replace(photo["marker"], f"![{photo['caption']}]({url})")
            else:
                md_content = md_content.replace(photo["marker"], f"> 📷 {photo['caption']}")
    md = f"# {title}\n\n{md_content}\n"
    return md.encode("utf-8")


def export_html(title: str, content_md: str, image_placement: list[dict] | None = None) -> bytes:
    """导出为完整 HTML 文档，照片以 base64 内嵌，离线可完整呈现"""
    html_content = content_md

    # 替换 [IMAGE] 标记为 base64 内嵌图片
    if image_placement:
        photos = _resolve_markers_to_photos(content_md, image_placement, download=True)
        for photo in photos:
            if photo["photo_base64"]:
                img_tag = (
                    f'<figure style="margin:1.5em 0">'
                    f'<img src="data:image/jpeg;base64,{photo["photo_base64"]}" '
                    f'style="max-width:100%;border-radius:8px;display:block" '
                    f'alt="{photo["caption"]}" />'
                    f'<figcaption style="text-align:center;color:#888;font-size:0.9em;margin-top:0.5em">'
                    f'{photo["caption"]}</figcaption>'
                    f'</figure>'
                )
                html_content = html_content.replace(photo["marker"], img_tag)
            else:
                html_content = html_content.replace(
                    photo["marker"],
                    f'<p style="color:#888;font-style:italic;padding:1em;background:#f5f5f5;border-radius:8px">&#x1F4F7; 配图建议：{photo["caption"]}</p>',
                )

    html_body = _md_to_wechat_html(html_content)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 720px; margin: 0 auto; padding: 2em 1em; line-height: 1.8; color: #333; }}
  h1 {{ font-size: 1.6em; text-align: center; }}
  h2 {{ font-size: 1.3em; margin-top: 1.5em; }}
  h3 {{ font-size: 1.1em; }}
  p {{ margin: 0.8em 0; }}
  strong {{ color: #1a1a1a; }}
  section {{ margin-top: 1em; }}
</style>
</head>
<body>
<h1>{title}</h1>
{html_body}
</body>
</html>"""
    return html.encode("utf-8")


def export_docx(title: str, content_md: str, image_placement: list[dict] | None = None) -> bytes:
    """导出为 DOCX 文件，照片通过 MinIO 下载后内嵌到文档中"""
    try:
        from docx import Document
        from docx.shared import Cm, Inches, Pt, RGBColor

        doc = Document()
        for section in doc.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(2.5)
            section.right_margin = Cm(2.5)

        heading = doc.add_heading(title, level=0)
        heading.alignment = 1

        # 解析正文中的 [IMAGE] 标记
        photo_map: dict[str, bytes] = {}
        if image_placement:
            photos = _resolve_markers_to_photos(content_md, image_placement, download=True)
            for photo in photos:
                if photo["photo_bytes"]:
                    photo_map[photo["marker"]] = photo["photo_bytes"]

        for block in content_md.split("\n\n"):
            block = block.strip()
            if not block:
                continue

            # 检查是否为照片标记
            if block in photo_map:
                try:
                    img_stream = BytesIO(photo_map[block])
                    p = doc.add_paragraph()
                    p.alignment = 1
                    run = p.add_run()
                    run.add_picture(img_stream, width=Inches(4.5))
                    # 图片说明
                    caption = _IMAGE_MARKER_RE.match(block)
                    if caption:
                        cap_p = doc.add_paragraph(caption.group(2).strip())
                        cap_p.alignment = 1
                        for r in cap_p.runs:
                            r.font.size = Pt(9)
                            r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
                except Exception as exc:
                    logger.warning("docx_photo_embed_failed", error=str(exc))
                    cap = _IMAGE_MARKER_RE.match(block)
                    cap_text = cap.group(2).strip() if cap else block
                    p = doc.add_paragraph(f"[图片: {cap_text}]")
                    for r in p.runs:
                        r.font.size = Pt(10)
                continue

            # 检查行内 IMAGE 标记 — 支持同一段落内多个标记
            has_inline = _IMAGE_MARKER_RE.search(block)
            if has_inline:
                # 找到 block 中所有 marker 的位置
                markers_in_block: list[tuple[int, int, str, bytes]] = []
                for marker, img_bytes in photo_map.items():
                    start = 0
                    while True:
                        pos = block.find(marker, start)
                        if pos == -1:
                            break
                        markers_in_block.append((pos, pos + len(marker), marker, img_bytes))
                        start = pos + 1
                markers_in_block.sort(key=lambda x: x[0])

                if not markers_in_block:
                    p = doc.add_paragraph(block)
                    for r in p.runs:
                        r.font.size = Pt(11)
                    continue

                cursor = 0
                for m_start, m_end, m_text, m_bytes in markers_in_block:
                    if cursor < m_start:
                        before = block[cursor:m_start].strip()
                        if before:
                            p = doc.add_paragraph(before)
                            for r in p.runs:
                                r.font.size = Pt(11)
                    try:
                        img_stream = BytesIO(m_bytes)
                        ip = doc.add_paragraph()
                        ip.alignment = 1
                        ir = ip.add_run()
                        ir.add_picture(img_stream, width=Inches(4.5))
                    except Exception as exc:
                        logger.warning("docx_inline_photo_failed", error=str(exc))
                    caption_match = _IMAGE_MARKER_RE.match(m_text)
                    if caption_match:
                        cap_p = doc.add_paragraph(caption_match.group(1).strip())
                        cap_p.alignment = 1
                        for r in cap_p.runs:
                            r.font.size = Pt(9)
                            r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
                    cursor = m_end
                if cursor < len(block):
                    after = block[cursor:].strip()
                    if after:
                        p = doc.add_paragraph(after)
                        for r in p.runs:
                            r.font.size = Pt(11)
                continue

            # 处理标题
            if block.startswith("### "):
                doc.add_heading(block[4:], level=3)
            elif block.startswith("## "):
                doc.add_heading(block[3:], level=2)
            elif block.startswith("# "):
                doc.add_heading(block[2:], level=1)
            else:
                p = doc.add_paragraph(block)
                for r in p.runs:
                    r.font.size = Pt(11)
                    r.font.name = "宋体"

        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()
    except ImportError:
        raise RuntimeError("python-docx 未安装，无法导出 DOCX")

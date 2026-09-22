"""OCR 服务 — RapidOCR(onnxruntime, CPU) 懒加载封装

供 text_parser 对扫描版 PDF 页面做文字识别兜底。引擎进程内单例，
首次调用时加载 det/cls/rec 模型（镜像内已随包提供或从 ocr_model_dir 读取）。
"""

from __future__ import annotations

import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine = None
_engine_lock = None


def _get_engine():
    """返回进程级单例 RapidOCR 引擎（首次调用导入并加载模型）。

    当 ocr_model_dir 下存在 rapidocr_cfg.yaml 时使用其中配置（通常指向
    mobile 模型以提升 CPU 速度），否则用包内置默认模型。
    """
    global _engine, _engine_lock
    if _engine is not None:
        return _engine
    if _engine_lock is None:
        import threading

        _engine_lock = threading.Lock()
    with _engine_lock:
        if _engine is not None:
            return _engine
        from rapidocr_onnxruntime import RapidOCR

        cfg = os.path.join(settings.ocr_model_dir, "rapidocr_cfg.yaml")
        if os.path.exists(cfg):
            _engine = RapidOCR(config_path=cfg)
        else:
            _engine = RapidOCR()
        logger.info("rapidocr_engine_ready")
    return _engine


def _normalize_result(result) -> str:
    """兼容多种 RapidOCR 返回形态：list[(box,text,score)...] / dict{txts:...} / 对象。"""
    if result is None:
        return ""
    if isinstance(result, tuple) and len(result) >= 1:
        result = result[0]
    if isinstance(result, dict):
        txts = result.get("txts")
        if txts is not None:
            return "\n".join(str(t) for t in txts)
        boxes = result.get("boxes")
        if isinstance(boxes, list):
            return "\n".join(str(b[1]) if isinstance(b, (list, tuple)) and len(b) > 1 else str(b) for b in boxes)
        return ""
    # 对象带 .txts 属性（新版 RapidOCR 返回 RapidOCROutput）
    txts = getattr(result, "txts", None)
    if txts is not None:
        return "\n".join(str(t) for t in txts)
    if isinstance(result, (list, tuple)):
        lines = []
        for item in result:
            if isinstance(item, (list, tuple)):
                if len(item) >= 2 and isinstance(item[1], str):
                    lines.append(item[1])
                elif item:
                    lines.append(str(item[0]))
            else:
                lines.append(str(item))
        return "\n".join(lines)
    return str(result)


def ocr_image(image) -> str:
    """识别单张图像（numpy BGR/RGB 或 PIL Image / 文件字节均可）为多行文本。

    失败时返回空字符串并记录日志，绝不向上抛出导致整书解析中断。
    """
    try:
        engine = _get_engine()
        result = engine(image)
        text = _normalize_result(result)
        return text
    except Exception:  # noqa: BLE001 - OCR 失败降级为空文本
        logger.warning("ocr_page_failed", exc_info=True)
        return ""

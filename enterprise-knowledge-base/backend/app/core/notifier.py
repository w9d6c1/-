"""Webhook 通知模块 — 企微 / 钉钉 / 自定义

通过环境变量 WEBHOOK_URL 配置通知地址。
支持高危安全事件、系统告警等推送。
"""

import json
import httpx

from app.core.config import settings
from app.core.logging import logger


async def send_notification(
    title: str,
    content: str,
    severity: str = "medium",
) -> bool:
    webhook_url = settings.webhook_url
    if not webhook_url:
        logger.debug("webhook_not_configured", title=title)
        return False

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": (
                f"## [{severity.upper()}] {title}\n\n"
                f"{content}\n\n"
                f"> 来自: {settings.app_name} v{settings.app_version}"
            ),
        },
    }

    # 钉钉格式兼容
    if "dingtalk" in webhook_url:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### [{severity.upper()}] {title}\n\n{content}\n\n---\n{settings.app_name}",
            },
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                logger.info("webhook_sent", title=title, severity=severity)
                return True
            logger.warning("webhook_failed", status=resp.status_code, body=resp.text[:200])
            return False
    except Exception:
        logger.warning("webhook_error", title=title, exc_info=True)
        return False


async def notify_security_event(
    event_type: str,
    detail: str,
    severity: str = "high",
) -> None:
    await send_notification(
        title=f"安全事件: {event_type}",
        content=detail,
        severity=severity,
    )

"""企业微信 API 客户端 — access_token 缓存 + 主动发送应用消息"""

import time

import httpx

from app.agents.cache import get_cache
from app.core.config import settings
from app.core.logging import logger

_QYAPI_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
_TOKEN_CACHE_KEY = "channel:wecom:access_token"


async def get_access_token(force_refresh: bool = False) -> str | None:
    """获取企微 access_token,优先读 Redis 缓存(有效期 2 小时,提前 5 分钟刷新)。"""
    cache = get_cache()

    if not force_refresh:
        try:
            cached = await cache.get(_TOKEN_CACHE_KEY)
            if cached and cached.get("token") and cached.get("expire_at", 0) > time.time():
                return str(cached["token"])
        except Exception:
            logger.warning("wecom_token_cache_get_failed", exc_info=True)

    if not settings.wecom_corp_id or not settings.wecom_secret:
        logger.warning("wecom_credentials_missing")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_QYAPI_BASE}/gettoken",
                params={"corpid": settings.wecom_corp_id, "corpsecret": settings.wecom_secret},
            )
            data = resp.json()
    except Exception:
        logger.warning("wecom_gettoken_request_failed", exc_info=True)
        return None

    if data.get("errcode") != 0:
        logger.warning("wecom_gettoken_error", errcode=data.get("errcode"), errmsg=data.get("errmsg"))
        return None

    token = data["access_token"]
    expires_in = int(data.get("expires_in", 7200))
    expire_at = time.time() + expires_in - 300
    try:
        await cache.set(_TOKEN_CACHE_KEY, {"token": token, "expire_at": expire_at}, ttl=expires_in - 300)
    except Exception:
        logger.warning("wecom_token_cache_set_failed", exc_info=True)
    return token


async def _post_message(token: str, payload: dict) -> dict:
    """发送一次消息请求,返回企微响应 dict(异常时返回 errcode=-1)。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_QYAPI_BASE}/message/send",
                params={"access_token": token},
                json=payload,
            )
            return resp.json()
    except Exception:
        logger.warning("wecom_send_request_failed", exc_info=True)
        return {"errcode": -1, "errmsg": "request_failed"}


async def send_text_message(to_user: str, content: str) -> bool:
    """通过应用主动发送文本消息给指定用户。"""
    token = await get_access_token()
    if not token:
        return False

    payload = {
        "touser": to_user,
        "msgtype": "text",
        "agentid": settings.wecom_agent_id,
        "text": {"content": content},
    }

    data = await _post_message(token, payload)
    if data.get("errcode") == 0:
        logger.info("wecom_message_sent", to_user=to_user)
        return True

    # token 失效则刷新重试一次
    if data.get("errcode") in (40014, 42001):
        token = await get_access_token(force_refresh=True)
        if token:
            data = await _post_message(token, payload)
            if data.get("errcode") == 0:
                logger.info("wecom_message_sent", to_user=to_user, retried=True)
                return True

    logger.warning("wecom_send_error", to_user=to_user, errcode=data.get("errcode"), errmsg=data.get("errmsg"))
    return False


async def download_media(media_id: str) -> bytes | None:
    """下载企微临时素材（语音/图片等），返回原始字节。

    语音消息素材有效期为 3 天。企微返回错误时响应体为 JSON 而非二进制。
    """
    token = await get_access_token()
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_QYAPI_BASE}/media/get",
                params={"access_token": token, "media_id": media_id},
            )
    except Exception:
        logger.warning("wecom_media_download_exception", media_id=media_id, exc_info=True)
        return None

    if resp.status_code != 200:
        logger.warning("wecom_media_download_failed", media_id=media_id, status=resp.status_code)
        return None

    content = resp.content
    content_type = resp.headers.get("content-type", "")
    # 出错时企微返回 JSON（而非二进制音频）
    if content_type.startswith("application/json") or content.startswith(b"{"):
        try:
            data = resp.json()
            logger.warning(
                "wecom_media_download_error",
                media_id=media_id,
                errcode=data.get("errcode"),
                errmsg=data.get("errmsg"),
            )
        except Exception:
            pass
        return None

    if not content:
        return None
    return content

"""企业微信回调路由 — URL 验证(GET) + 消息接收(POST)"""

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from app.channels.wecom.crypto import (
    WXBizMsgCrypt,
    WeComCryptoError,
    parse_encrypt_from_xml,
    parse_message_xml,
)
from app.channels.wecom.service import handle_message
from app.core.config import settings
from app.core.logging import logger

router = APIRouter(prefix="/wecom", tags=["channel-wecom"])


def _get_crypt() -> WXBizMsgCrypt | None:
    if not (settings.wecom_token and settings.wecom_aes_key and settings.wecom_corp_id):
        return None
    try:
        return WXBizMsgCrypt(
            token=settings.wecom_token,
            encoding_aes_key=settings.wecom_aes_key,
            corp_id=settings.wecom_corp_id,
        )
    except WeComCryptoError:
        logger.warning("wecom_crypt_init_failed", exc_info=True)
        return None


@router.get("/callback")
async def verify_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """企微回调 URL 验证:校验签名并返回解密后的 echostr。"""
    crypt = _get_crypt()
    if crypt is None:
        return Response(content="wecom not configured", status_code=503)
    try:
        decrypted = crypt.decrypt_message(msg_signature, timestamp, nonce, echostr)
    except WeComCryptoError:
        logger.warning("wecom_verify_failed", exc_info=True)
        return Response(content="verify failed", status_code=403)
    return Response(content=decrypted, media_type="text/plain")


@router.post("/callback")
async def receive_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """接收企微消息:验签解密 → 后台异步处理 → 立即返回空串。"""
    crypt = _get_crypt()
    if crypt is None:
        return Response(content="", status_code=503)

    body = (await request.body()).decode("utf-8")
    try:
        encrypt = parse_encrypt_from_xml(body)
        plaintext = crypt.decrypt_message(msg_signature, timestamp, nonce, encrypt)
        msg = parse_message_xml(plaintext)
    except WeComCryptoError:
        logger.warning("wecom_message_decrypt_failed", exc_info=True)
        return Response(content="", status_code=403)

    # 后台异步生成并主动回推,被动响应立即返回空串(企微 5s 超时约束)
    background_tasks.add_task(handle_message, msg)
    return Response(content="", media_type="text/plain")

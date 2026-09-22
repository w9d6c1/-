"""腾讯云语音识别 — 一句话识别 (SentenceRecognition)

企微语音消息下载后为 AMR/speex 等格式，经腾讯云 ASR 转成文字。
使用标准库 hmac/hashlib 实现 TC3-HMAC-SHA256 签名，零新增 pip 依赖。
未配置 SecretId/SecretKey 时返回 None，由调用方优雅降级。
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.logging import logger

_ASR_HOST = "asr.tencentcloudapi.com"
_ASR_SERVICE = "asr"
_ASR_VERSION = "2019-06-14"
_ASR_ACTION = "SentenceRecognition"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def build_authorization(
    secret_id: str,
    secret_key: str,
    payload: str,
    timestamp: int,
    host: str = _ASR_HOST,
    service: str = _ASR_SERVICE,
) -> str:
    """构造 TC3-HMAC-SHA256 签名 Authorization 头。"""
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    algorithm = "TC3-HMAC-SHA256"

    # 1. 拼接规范请求串
    http_request_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    ct = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{ct}\nhost:{host}\n"
    signed_headers = "content-type;host"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
    )

    # 2. 拼接待签名字符串
    credential_scope = f"{date}/{service}/tc3_request"
    hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

    # 3. 计算签名
    secret_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _sign(secret_date, service)
    secret_signing = _sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # 4. 拼接 Authorization
    return (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


async def transcribe(audio_bytes: bytes, voice_format: str = "amr", usr_key: str = "") -> str | None:
    """将语音字节流转成文字；未配置凭证或失败时返回 None。"""
    if not audio_bytes:
        return None
    if not settings.tencent_secret_id or not settings.tencent_secret_key:
        logger.warning("asr_not_configured")
        return None

    data_b64 = base64.b64encode(audio_bytes).decode("ascii")
    payload = {
        "ProjectId": 0,
        "SubServiceType": 2,  # 一句话识别
        "EngSerViceType": settings.asr_engine_type,
        "SourceType": 1,  # 音频数据以 base64 放在请求体
        "VoiceFormat": (voice_format or "amr").lower(),
        "UsrAudioKey": usr_key or str(int(time.time() * 1000)),
        "Data": data_b64,
        "DataLen": len(audio_bytes),
    }
    body = json.dumps(payload)
    timestamp = int(time.time())
    authorization = build_authorization(
        settings.tencent_secret_id,
        settings.tencent_secret_key,
        body,
        timestamp,
    )

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": _ASR_HOST,
        "X-TC-Action": _ASR_ACTION,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": _ASR_VERSION,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(f"https://{_ASR_HOST}/", headers=headers, content=body)
            data = resp.json()
    except Exception:
        logger.warning("asr_request_failed", exc_info=True)
        return None

    result = data.get("Response", {}) if isinstance(data, dict) else {}
    if result.get("Error"):
        logger.warning(
            "asr_error",
            code=result["Error"].get("Code"),
            message=result["Error"].get("Message"),
        )
        return None

    text = (result.get("Result") or "").strip()
    return text or None

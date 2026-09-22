"""平台账号凭证加密/解密模块

使用 Fernet (AES-128-CBC + HMAC-SHA256) 对称加密。
密钥从 settings.jwt_secret_key 派生（SHA256 → base64 → 32 字节 Fernet key）。
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _derive_key() -> bytes:
    """从 JWT_SECRET_KEY 派生 Fernet 加密密钥"""
    raw = settings.jwt_secret_key.encode("utf-8")
    key_bytes = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(key_bytes)


_fernet = Fernet(_derive_key())


def encrypt_credentials(plaintext: str) -> str:
    """加密凭证明文，返回 base64 密文字符串"""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credentials(ciphertext: str) -> str:
    """解密密文，返回原始凭证明文"""
    return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

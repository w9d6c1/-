"""企业微信消息加解密 — WXBizMsgCrypt

实现企微回调消息的签名校验与 AES-CBC 加解密。
参考企业微信官方加解密方案:
- 签名: sha1(sorted(token, timestamp, nonce, encrypt))
- 加密: AES-256-CBC, PKCS7 padding, key = base64decode(EncodingAESKey + "=")
- 明文结构: random(16) + msg_len(4, 网络字节序) + msg + receiveid
"""

import base64
import hashlib
import socket
import struct
import time
from secrets import token_bytes

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

try:
    # 优先使用 defusedxml 防御 XXE / 实体炸弹(外部不可信输入)
    from defusedxml.ElementTree import fromstring as _xml_fromstring
except ImportError:  # pragma: no cover - 回退到标准库
    from xml.etree.ElementTree import fromstring as _xml_fromstring


class WeComCryptoError(Exception):
    """加解密/校验异常"""


def _pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    if pad_len == 0:
        pad_len = block_size
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise WeComCryptoError("empty plaintext")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 32:
        raise WeComCryptoError("invalid padding")
    return data[:-pad_len]


class WXBizMsgCrypt:
    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        if len(encoding_aes_key) != 43:
            raise WeComCryptoError("EncodingAESKey must be 43 chars")
        self.token = token
        self.corp_id = corp_id
        self.aes_key = base64.b64decode(encoding_aes_key + "=")
        if len(self.aes_key) != 32:
            raise WeComCryptoError("decoded AES key must be 32 bytes")

    # ── 签名 ──
    def compute_signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        params = sorted([self.token, timestamp, nonce, encrypt])
        raw = "".join(params).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        expected = self.compute_signature(timestamp, nonce, encrypt)
        # 恒定时间比较
        if len(expected) != len(signature):
            return False
        result = 0
        for a, b in zip(expected, signature):
            result |= ord(a) ^ ord(b)
        return result == 0

    # ── 解密 ──
    def decrypt(self, encrypt_b64: str) -> str:
        cipher_data = base64.b64decode(encrypt_b64)
        decryptor = Cipher(
            algorithms.AES(self.aes_key), modes.CBC(self.aes_key[:16])
        ).decryptor()
        plaintext = decryptor.update(cipher_data) + decryptor.finalize()
        plaintext = _pkcs7_unpad(plaintext)

        # random(16) + msg_len(4) + msg + receiveid
        content = plaintext[16:]
        msg_len = socket.ntohl(struct.unpack("I", content[:4])[0])
        msg = content[4 : 4 + msg_len]
        receiveid = content[4 + msg_len :]

        if receiveid.decode("utf-8") != self.corp_id:
            raise WeComCryptoError("corp_id mismatch")
        return msg.decode("utf-8")

    def decrypt_message(
        self, msg_signature: str, timestamp: str, nonce: str, encrypt_b64: str
    ) -> str:
        if not self.verify_signature(msg_signature, timestamp, nonce, encrypt_b64):
            raise WeComCryptoError("signature verification failed")
        return self.decrypt(encrypt_b64)

    # ── 加密 ──
    def encrypt(self, plaintext: str) -> str:
        text = plaintext.encode("utf-8")
        random16 = token_bytes(16)
        msg_len = struct.pack("I", socket.htonl(len(text)))
        raw = random16 + msg_len + text + self.corp_id.encode("utf-8")
        raw = _pkcs7_pad(raw)

        encryptor = Cipher(
            algorithms.AES(self.aes_key), modes.CBC(self.aes_key[:16])
        ).encryptor()
        cipher_data = encryptor.update(raw) + encryptor.finalize()
        return base64.b64encode(cipher_data).decode("utf-8")

    def encrypt_message(self, reply_msg: str, nonce: str, timestamp: str | None = None) -> str:
        ts = timestamp or str(int(time.time()))
        encrypt = self.encrypt(reply_msg)
        signature = self.compute_signature(ts, nonce, encrypt)
        return (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
            f"<TimeStamp>{ts}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )


def parse_encrypt_from_xml(body: str) -> str:
    """从企微回调 XML body 中提取 Encrypt 字段"""
    try:
        root = _xml_fromstring(body)
        node = root.find("Encrypt")
        if node is None or node.text is None:
            raise WeComCryptoError("no Encrypt in body")
        return node.text
    except WeComCryptoError:
        raise
    except Exception as e:  # ParseError 或 defusedxml 拦截的恶意实体
        raise WeComCryptoError(f"invalid xml body: {e}") from e


def parse_message_xml(plaintext_xml: str) -> dict[str, str]:
    """解析解密后的消息 XML 为字典"""
    try:
        root = _xml_fromstring(plaintext_xml)
    except Exception as e:  # ParseError 或 defusedxml 拦截的恶意实体
        raise WeComCryptoError(f"invalid message xml: {e}") from e
    return {child.tag: (child.text or "") for child in root}

"""企业微信消息加解密测试 — WXBizMsgCrypt"""

import pytest

from app.channels.wecom.crypto import (
    WXBizMsgCrypt,
    WeComCryptoError,
    parse_encrypt_from_xml,
    parse_message_xml,
)

# 测试用固定凭证(43 字符 AESKey)
TOKEN = "QDG6eK1CT3d5aVdh"
AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"  # 43 chars
CORP_ID = "wx5823bf96d3bd56c7"


def _make_crypt(corp_id: str = CORP_ID) -> WXBizMsgCrypt:
    return WXBizMsgCrypt(token=TOKEN, encoding_aes_key=AES_KEY, corp_id=corp_id)


class TestWXBizMsgCryptInit:
    def test_invalid_aes_key_length(self):
        with pytest.raises(WeComCryptoError):
            WXBizMsgCrypt(token=TOKEN, encoding_aes_key="tooshort", corp_id=CORP_ID)

    def test_valid_init(self):
        crypt = _make_crypt()
        assert len(crypt.aes_key) == 32


class TestSignature:
    def test_signature_deterministic(self):
        crypt = _make_crypt()
        sig1 = crypt.compute_signature("1409659813", "1372623149", "ENCRYPTED")
        sig2 = crypt.compute_signature("1409659813", "1372623149", "ENCRYPTED")
        assert sig1 == sig2
        assert len(sig1) == 40  # sha1 hex

    def test_verify_signature_ok(self):
        crypt = _make_crypt()
        sig = crypt.compute_signature("ts", "nonce", "enc")
        assert crypt.verify_signature(sig, "ts", "nonce", "enc") is True

    def test_verify_signature_fail(self):
        crypt = _make_crypt()
        assert crypt.verify_signature("bad", "ts", "nonce", "enc") is False


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_plaintext(self):
        crypt = _make_crypt()
        original = "<xml><Content>你好，世界</Content></xml>"
        encrypted = crypt.encrypt(original)
        decrypted = crypt.decrypt(encrypted)
        assert decrypted == original

    def test_roundtrip_message_envelope(self):
        crypt = _make_crypt()
        reply = "<xml><Content>回答内容</Content></xml>"
        envelope = crypt.encrypt_message(reply, nonce="nonce123", timestamp="1409659813")
        # 从密文信封中取出 Encrypt 再解密
        encrypt = parse_encrypt_from_xml(envelope)
        decrypted = crypt.decrypt(encrypt)
        assert decrypted == reply

    def test_decrypt_message_verifies_signature(self):
        crypt = _make_crypt()
        plaintext = "<xml><Content>测试</Content></xml>"
        encrypt = crypt.encrypt(plaintext)
        sig = crypt.compute_signature("ts", "nonce", encrypt)
        result = crypt.decrypt_message(sig, "ts", "nonce", encrypt)
        assert result == plaintext

    def test_decrypt_message_bad_signature(self):
        crypt = _make_crypt()
        encrypt = crypt.encrypt("<xml></xml>")
        with pytest.raises(WeComCryptoError):
            crypt.decrypt_message("wrongsig", "ts", "nonce", encrypt)

    def test_corp_id_mismatch(self):
        crypt_a = _make_crypt(corp_id=CORP_ID)
        crypt_b = _make_crypt(corp_id="different_corp")
        encrypt = crypt_a.encrypt("<xml></xml>")
        with pytest.raises(WeComCryptoError):
            crypt_b.decrypt(encrypt)


class TestXmlParsing:
    def test_parse_encrypt_from_xml(self):
        body = "<xml><Encrypt><![CDATA[ABC123]]></Encrypt><ToUserName><![CDATA[x]]></ToUserName></xml>"
        assert parse_encrypt_from_xml(body) == "ABC123"

    def test_parse_encrypt_missing(self):
        with pytest.raises(WeComCryptoError):
            parse_encrypt_from_xml("<xml><Other>x</Other></xml>")

    def test_parse_encrypt_invalid_xml(self):
        with pytest.raises(WeComCryptoError):
            parse_encrypt_from_xml("not xml at all <<<")

    def test_parse_message_xml(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user001]]></FromUserName>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[请问年假怎么请]]></Content>"
            "<MsgId>1234567890</MsgId>"
            "</xml>"
        )
        msg = parse_message_xml(xml)
        assert msg["FromUserName"] == "user001"
        assert msg["MsgType"] == "text"
        assert msg["Content"] == "请问年假怎么请"
        assert msg["MsgId"] == "1234567890"

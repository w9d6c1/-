"""集成测试 — 企业微信回调 API (URL 验证 GET + 消息接收 POST)"""

import base64
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.wecom.crypto import WXBizMsgCrypt
from app.core.config import settings

# 43 字符 EncodingAESKey（32 字节 base64 去尾 '='）
TOKEN = "wecom-test-token"
AES_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode().rstrip("=")
CORP_ID = "corp-test-001"


def _configured_crypt() -> WXBizMsgCrypt:
    return WXBizMsgCrypt(token=TOKEN, encoding_aes_key=AES_KEY, corp_id=CORP_ID)


@pytest.fixture(autouse=True)
def _wecom_settings(monkeypatch):
    monkeypatch.setattr(settings, "wecom_token", "")
    monkeypatch.setattr(settings, "wecom_aes_key", "")
    monkeypatch.setattr(settings, "wecom_corp_id", "")
    yield


class TestWeComVerifyUrl:
    async def test_unconfigured_returns_503(self, client):
        resp = await client.get(
            "/api/channels/wecom/callback",
            params={"msg_signature": "x", "timestamp": "1", "nonce": "n", "echostr": "y"},
        )
        assert resp.status_code == 503

    async def test_valid_signature_decrypts_echostr(self, client, monkeypatch):
        monkeypatch.setattr(settings, "wecom_token", TOKEN)
        monkeypatch.setattr(settings, "wecom_aes_key", AES_KEY)
        monkeypatch.setattr(settings, "wecom_corp_id", CORP_ID)

        crypt = _configured_crypt()
        ts = str(int(time.time()))
        nonce = "nonce-123"
        echostr = crypt.encrypt("hello_echostr")
        sig = crypt.compute_signature(ts, nonce, echostr)

        resp = await client.get(
            "/api/channels/wecom/callback",
            params={
                "msg_signature": sig,
                "timestamp": ts,
                "nonce": nonce,
                "echostr": echostr,
            },
        )
        assert resp.status_code == 200
        assert resp.text == "hello_echostr"

    async def test_bad_signature_returns_403(self, client, monkeypatch):
        monkeypatch.setattr(settings, "wecom_token", TOKEN)
        monkeypatch.setattr(settings, "wecom_aes_key", AES_KEY)
        monkeypatch.setattr(settings, "wecom_corp_id", CORP_ID)

        crypt = _configured_crypt()
        ts = str(int(time.time()))
        echostr = crypt.encrypt("secret")

        resp = await client.get(
            "/api/channels/wecom/callback",
            params={
                "msg_signature": "deadbeef" * 5,
                "timestamp": ts,
                "nonce": "n",
                "echostr": echostr,
            },
        )
        assert resp.status_code == 403


class TestWeComReceiveMessage:
    def _build_request(self, crypt: WXBizMsgCrypt, message_xml: str, nonce: str = "nonce-1") -> tuple[str, dict]:
        ts = str(int(time.time()))
        encrypt = crypt.encrypt(message_xml)
        sig = crypt.compute_signature(ts, nonce, encrypt)
        body = (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{sig}]]></MsgSignature>"
            f"<TimeStamp>{ts}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )
        return body, {"msg_signature": sig, "timestamp": ts, "nonce": nonce}

    MESSAGE_XML = (
        "<xml><ToUserName>corp-test-001</ToUserName>"
        "<FromUserName>user01</FromUserName>"
        "<CreateTime>1234567890</CreateTime>"
        "<MsgType>text</MsgType><Content>你好</Content><MsgId>1</MsgId></xml>"
    )

    async def test_unconfigured_returns_503(self, client):
        resp = await client.post(
            "/api/channels/wecom/callback",
            params={"msg_signature": "x", "timestamp": "1", "nonce": "n"},
            content="<xml/>",
        )
        assert resp.status_code == 503

    async def test_valid_message_returns_empty_and_handles_background(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(settings, "wecom_token", TOKEN)
        monkeypatch.setattr(settings, "wecom_aes_key", AES_KEY)
        monkeypatch.setattr(settings, "wecom_corp_id", CORP_ID)

        crypt = _configured_crypt()
        body, params = self._build_request(crypt, self.MESSAGE_XML)

        handle_mock = AsyncMock()
        with patch("app.channels.wecom.router.handle_message", handle_mock):
            resp = await client.post(
                "/api/channels/wecom/callback",
                params=params,
                content=body,
            )
        assert resp.status_code == 200
        assert resp.text == ""
        assert handle_mock.await_count == 1

    async def test_invalid_signature_returns_403(self, client, monkeypatch):
        monkeypatch.setattr(settings, "wecom_token", TOKEN)
        monkeypatch.setattr(settings, "wecom_aes_key", AES_KEY)
        monkeypatch.setattr(settings, "wecom_corp_id", CORP_ID)

        crypt = _configured_crypt()
        body, params = self._build_request(crypt, self.MESSAGE_XML)

        resp = await client.post(
            "/api/channels/wecom/callback",
            params={**params, "msg_signature": "bad-signature-value"},
            content=body,
        )
        assert resp.status_code == 403

    async def test_malformed_xml_returns_403(self, client, monkeypatch):
        monkeypatch.setattr(settings, "wecom_token", TOKEN)
        monkeypatch.setattr(settings, "wecom_aes_key", AES_KEY)
        monkeypatch.setattr(settings, "wecom_corp_id", CORP_ID)

        # 环境的 rich 日志器无法渲染 ExpatError 链, 打桩避免其崩溃 (与业务断言无关)
        with patch("app.channels.wecom.router.logger.warning"):
            resp = await client.post(
                "/api/channels/wecom/callback",
                params={"msg_signature": "x", "timestamp": "1", "nonce": "n"},
                content="not xml at all",
            )
        assert resp.status_code == 403

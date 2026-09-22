"""腾讯云语音识别 (asr) 单元测试 — TC3 签名 + 转写 + 降级"""

import pytest


class TestBuildAuthorization:
    def test_deterministic_and_valid(self):
        from app.channels.wecom.asr import build_authorization

        a1 = build_authorization("AKID", "SECRET", '{"x":1}', 1700000000)
        a2 = build_authorization("AKID", "SECRET", '{"x":1}', 1700000000)
        assert a1 == a2
        assert a1.startswith("TC3-HMAC-SHA256 Credential=AKID/")
        assert "SignedHeaders=content-type;host" in a1
        sig = a1.rsplit("Signature=", 1)[1]
        assert len(sig) == 64

    def test_changes_with_payload(self):
        from app.channels.wecom.asr import build_authorization

        a1 = build_authorization("AKID", "SECRET", '{"x":1}', 1700000000)
        a2 = build_authorization("AKID", "SECRET", '{"x":2}', 1700000000)
        assert a1 != a2

    def test_changes_with_secret(self):
        from app.channels.wecom.asr import build_authorization

        a1 = build_authorization("AKID", "SECRET1", '{"x":1}', 1700000000)
        a2 = build_authorization("AKID", "SECRET2", '{"x":1}', 1700000000)
        assert a1 != a2


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_empty_audio_returns_none(self):
        from app.channels.wecom import asr

        assert await asr.transcribe(b"") is None

    @pytest.mark.asyncio
    async def test_unconfigured_returns_none(self, monkeypatch):
        from app.channels.wecom import asr

        monkeypatch.setattr(asr.settings, "tencent_secret_id", "")
        monkeypatch.setattr(asr.settings, "tencent_secret_key", "")
        assert await asr.transcribe(b"fake-audio") is None

    @pytest.mark.asyncio
    async def test_success_returns_text(self, monkeypatch):
        from app.channels.wecom import asr

        monkeypatch.setattr(asr.settings, "tencent_secret_id", "AKIDtest")
        monkeypatch.setattr(asr.settings, "tencent_secret_key", "secretkey")

        class FakeResponse:
            def json(self):
                return {"Response": {"Result": "公司年假政策", "RequestId": "req-1"}}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return FakeResponse()

        monkeypatch.setattr(asr.httpx, "AsyncClient", FakeClient)
        result = await asr.transcribe(b"fake-audio", voice_format="amr", usr_key="m1")
        assert result == "公司年假政策"

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, monkeypatch):
        from app.channels.wecom import asr

        monkeypatch.setattr(asr.settings, "tencent_secret_id", "AKIDtest")
        monkeypatch.setattr(asr.settings, "tencent_secret_key", "secretkey")

        class FakeResponse:
            def json(self):
                return {"Response": {"Error": {"Code": "InvalidParameter", "Message": "bad"}}}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return FakeResponse()

        monkeypatch.setattr(asr.httpx, "AsyncClient", FakeClient)
        assert await asr.transcribe(b"fake-audio") is None

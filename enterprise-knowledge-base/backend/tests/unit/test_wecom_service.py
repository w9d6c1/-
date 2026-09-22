"""企业微信渠道服务与客户端测试"""

from unittest.mock import AsyncMock, patch

import pytest


class TestServiceDedup:
    @pytest.mark.asyncio
    async def test_empty_msg_id_not_duplicate(self):
        from app.channels.wecom import service

        assert await service.is_duplicate("") is False

    @pytest.mark.asyncio
    async def test_first_seen_not_duplicate(self):
        from app.channels.wecom import service

        mock_client = AsyncMock()
        mock_client.set.return_value = True  # SET NX 成功 = 首次
        mock_cache = AsyncMock()
        mock_cache._ensure_client.return_value = mock_client
        with patch.object(service, "get_cache", return_value=mock_cache):
            assert await service.is_duplicate("msg1") is False
            mock_client.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_seen_is_duplicate(self):
        from app.channels.wecom import service

        mock_client = AsyncMock()
        mock_client.set.return_value = None  # SET NX 失败 = 已存在
        mock_cache = AsyncMock()
        mock_cache._ensure_client.return_value = mock_client
        with patch.object(service, "get_cache", return_value=mock_cache):
            assert await service.is_duplicate("msg1") is True


class TestGetOrCreateThread:
    @pytest.mark.asyncio
    async def test_reuse_existing_thread(self):
        from app.channels.wecom import service

        mock_cache = AsyncMock()
        mock_cache.get.return_value = {"thread_id": "existing-tid"}
        with patch.object(service, "get_cache", return_value=mock_cache):
            tid = await service._get_or_create_thread("user1")
            assert tid == "existing-tid"
            mock_cache.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_new_thread(self):
        from app.channels.wecom import service

        mock_cache = AsyncMock()
        mock_cache.get.return_value = None
        with patch.object(service, "get_cache", return_value=mock_cache):
            tid = await service._get_or_create_thread("user1")
            assert tid
            mock_cache.set.assert_awaited_once()


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_skips_duplicate(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=True)), \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message({"MsgType": "text", "FromUserName": "u1", "MsgId": "1", "Content": "hi"})
            proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_text_replies_hint(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "send_text_message", AsyncMock(return_value=True)) as send, \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message({"MsgType": "image", "FromUserName": "u1", "MsgId": "2"})
            send.assert_awaited_once()
            proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_user_returns_early(self):
        from app.channels.wecom import service

        with patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message({"MsgType": "text", "FromUserName": "", "Content": "hi"})
            proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_content_no_reply(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message({"MsgType": "text", "FromUserName": "u1", "MsgId": "3", "Content": "   "})
            proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_text_triggers_process(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message({"MsgType": "text", "FromUserName": "u1", "MsgId": "4", "Content": "年假政策"})
            proc.assert_awaited_once_with("u1", "年假政策")

    @pytest.mark.asyncio
    async def test_voice_message_transcribes_and_replies(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "download_media", AsyncMock(return_value=b"audio")), \
             patch.object(service.asr, "transcribe", AsyncMock(return_value="公司年假政策")), \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message(
                {"MsgType": "voice", "FromUserName": "u1", "MsgId": "10", "MediaId": "m1", "Format": "amr"}
            )
            proc.assert_awaited_once_with("u1", "公司年假政策")

    @pytest.mark.asyncio
    async def test_voice_download_failure_sends_fallback(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "download_media", AsyncMock(return_value=None)), \
             patch.object(service, "send_text_message", AsyncMock(return_value=True)) as send, \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message(
                {"MsgType": "voice", "FromUserName": "u1", "MsgId": "11", "MediaId": "m1", "Format": "amr"}
            )
            send.assert_awaited_once()
            proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_voice_transcribe_none_sends_fallback(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "download_media", AsyncMock(return_value=b"audio")), \
             patch.object(service.asr, "transcribe", AsyncMock(return_value=None)), \
             patch.object(service, "send_text_message", AsyncMock(return_value=True)) as send, \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message(
                {"MsgType": "voice", "FromUserName": "u1", "MsgId": "12", "MediaId": "m1", "Format": "amr"}
            )
            send.assert_awaited_once()
            proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_voice_missing_media_id_sends_fallback(self):
        from app.channels.wecom import service

        with patch.object(service, "is_duplicate", AsyncMock(return_value=False)), \
             patch.object(service, "send_text_message", AsyncMock(return_value=True)) as send, \
             patch.object(service, "process_and_reply", AsyncMock()) as proc:
            await service.handle_message({"MsgType": "voice", "FromUserName": "u1", "MsgId": "13", "MediaId": ""})
            send.assert_awaited_once()
            proc.assert_not_awaited()


class TestProcessAndReply:
    @pytest.mark.asyncio
    async def test_sends_ack_before_answer(self):
        """启用确认消息时，先推 ack 再推最终答案"""
        from app.channels.wecom import service

        with patch.object(service.settings, "wecom_send_ack", True), \
             patch.object(service, "send_text_message", AsyncMock(return_value=True)) as send, \
             patch.object(service, "generate_answer", AsyncMock(return_value="最终答案")) as gen:
            await service.process_and_reply("u1", "年假政策")

        gen.assert_awaited_once_with("u1", "年假政策")
        assert send.await_count == 2
        first_call = send.await_args_list[0]
        assert first_call[0][1] == service.settings.wecom_ack_reply

    @pytest.mark.asyncio
    async def test_no_ack_when_disabled(self):
        """关闭确认消息时，只推最终答案一次"""
        from app.channels.wecom import service

        with patch.object(service.settings, "wecom_send_ack", False), \
             patch.object(service, "send_text_message", AsyncMock(return_value=True)) as send, \
             patch.object(service, "generate_answer", AsyncMock(return_value="答案")):
            await service.process_and_reply("u1", "年假政策")

        send.assert_awaited_once_with("u1", "答案")


class TestClientSend:
    @pytest.mark.asyncio
    async def test_send_no_token_returns_false(self):
        from app.channels.wecom import client

        with patch.object(client, "get_access_token", AsyncMock(return_value=None)):
            assert await client.send_text_message("u1", "hi") is False

    @pytest.mark.asyncio
    async def test_send_success(self):
        from app.channels.wecom import client

        with patch.object(client, "get_access_token", AsyncMock(return_value="tok")), \
             patch.object(client, "_post_message", AsyncMock(return_value={"errcode": 0})):
            assert await client.send_text_message("u1", "hi") is True

    @pytest.mark.asyncio
    async def test_send_token_expired_then_retry_success(self):
        from app.channels.wecom import client

        post = AsyncMock(side_effect=[{"errcode": 42001}, {"errcode": 0}])
        with patch.object(client, "get_access_token", AsyncMock(side_effect=["tok1", "tok2"])), \
             patch.object(client, "_post_message", post):
            assert await client.send_text_message("u1", "hi") is True
            assert post.await_count == 2

    @pytest.mark.asyncio
    async def test_send_hard_error_returns_false(self):
        from app.channels.wecom import client

        with patch.object(client, "get_access_token", AsyncMock(return_value="tok")), \
             patch.object(client, "_post_message", AsyncMock(return_value={"errcode": 81013})):
            assert await client.send_text_message("u1", "hi") is False


class TestXXEProtection:
    def test_entity_expansion_blocked(self):
        from app.channels.wecom.crypto import WeComCryptoError, parse_message_xml

        # 典型 XXE / 实体炸弹,defusedxml 应拦截
        payload = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE lolz [<!ENTITY lol "lollol">]>'
            "<xml><Content>&lol;</Content></xml>"
        )
        with pytest.raises(WeComCryptoError):
            parse_message_xml(payload)

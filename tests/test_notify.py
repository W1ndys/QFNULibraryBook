"""
测试 py/notify/notify.py — 消息推送模块
"""
import json
import logging
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from notify.notify import send_message, _dingtalk, _send_bark, _send_anpush


# ========== send_message 分发测试 ==========

class TestSendMessageDispatch:
    """send_message 根据 push_method 分发到正确后端"""

    @patch("notify.notify.asyncio.run")
    def test_dispatch_tg(self, mock_run, sample_config):
        """push_method='TG' 调用 Telegram"""
        sample_config.push_method = "TG"
        send_message(sample_config, "test msg", "title")
        mock_run.assert_called_once()

    @patch("notify.notify._dingtalk")
    def test_dispatch_dd(self, mock_dd, sample_config):
        """push_method='DD' 调用钉钉"""
        sample_config.push_method = "DD"
        send_message(sample_config, "test msg", "title")
        mock_dd.assert_called_once()

    @patch("notify.notify._send_bark")
    def test_dispatch_bark(self, mock_bark, sample_config):
        """push_method='BARK' 调用 Bark"""
        sample_config.push_method = "BARK"
        send_message(sample_config, "test msg", "title")
        mock_bark.assert_called_once()

    @patch("notify.notify._send_anpush")
    def test_dispatch_anpush(self, mock_anpush, sample_config):
        """push_method='ANPUSH' 调用 AnPush"""
        sample_config.push_method = "ANPUSH"
        send_message(sample_config, "test msg", "title")
        mock_anpush.assert_called_once()

    def test_unknown_method_warns(self, sample_config, caplog):
        """未知推送方式记录 warning"""
        sample_config.push_method = "UNKNOWN"
        with caplog.at_level(logging.WARNING):
            send_message(sample_config, "msg", "title")
        assert "未知的推送方式" in caplog.text

    def test_empty_method_noop(self, sample_config):
        """空字符串不崩溃"""
        sample_config.push_method = ""
        send_message(sample_config, "msg", "title")  # 不应抛异常


# ========== 钉钉推送 ==========

class TestDingtalk:
    """_dingtalk 函数测试"""

    @patch("notify.notify.requests.post")
    def test_hmac_signature(self, mock_post):
        """带 secret 时 URL 包含 timestamp 和 sign"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        _dingtalk("title", "content", "fake_token", "fake_secret")
        call_url = mock_post.call_args[0][0]
        assert "timestamp=" in call_url
        assert "sign=" in call_url

    @patch("notify.notify.requests.post")
    def test_payload_format(self, mock_post):
        """JSON body 含 msgtype: text"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        _dingtalk("title", "content", "token", "secret")
        call_kwargs = mock_post.call_args[1]
        payload = json.loads(call_kwargs["data"])
        assert payload["msgtype"] == "text"
        assert "title" in payload["text"]["content"]

    @patch("notify.notify.requests.post")
    def test_no_secret_skips_signature(self, mock_post):
        """无 secret 时 URL 不含签名"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        _dingtalk("title", "content", "token", dd_bot_secret=None)
        call_url = mock_post.call_args[0][0]
        assert "timestamp=" not in call_url
        assert "sign=" not in call_url


# ========== Bark 推送 ==========

class TestBark:
    """_send_bark 函数测试"""

    @patch("notify.notify.requests.get")
    def test_url_construction(self, mock_get):
        """GET URL 格式正确"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_get.return_value = mock_response

        config = MagicMock()
        config.bark_url = "https://example.com/bark/"
        config.bark_extra = "?sound=bird"

        _send_bark(config, "msg content", "title")
        call_url = mock_get.call_args[0][0]
        assert "title" in call_url
        assert "msg content" in call_url
        assert "?sound=bird" in call_url

    @patch("notify.notify.requests.get")
    def test_request_exception_no_crash(self, mock_get):
        """请求异常不崩溃"""
        import requests as req
        mock_get.side_effect = req.exceptions.RequestException("network error")

        config = MagicMock()
        config.bark_url = "https://example.com/bark/"
        config.bark_extra = ""

        result = _send_bark(config, "msg", "title")
        assert result is None


# ========== AnPush 推送 ==========

class TestAnPush:
    """_send_anpush 函数测试"""

    @patch("notify.notify.requests.post")
    def test_payload_format(self, mock_post):
        """POST 数据含 title, content, channel"""
        config = MagicMock()
        config.anpush_token = "token123"
        config.anpush_channel = "ch1"

        _send_anpush(config, "content", "title")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["data"]["title"] == "title"
        assert call_kwargs["data"]["content"] == "content"
        assert call_kwargs["data"]["channel"] == "ch1"


# ========== Telegram 推送 ==========

class TestTelegram:
    """Telegram 推送测试"""

    @patch("notify.notify.Bot")
    def test_calls_bot_send_message(self, mock_bot_cls, sample_config):
        """Bot.send_message 被正确调用"""
        import asyncio

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_cls.return_value = mock_bot

        sample_config.push_method = "TG"
        send_message(sample_config, "test msg", "title")
        mock_bot.send_message.assert_called_once()

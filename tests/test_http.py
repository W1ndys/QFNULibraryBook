"""
测试 py/api/http.py — 带重试的 HTTP 请求工具
"""
from unittest.mock import patch, MagicMock

import pytest
import requests

from api.http import post_with_retry, RequestFailed


class TestRequestFailed:
    """自定义异常"""

    def test_is_exception(self):
        """RequestFailed 是 Exception 子类"""
        assert issubclass(RequestFailed, Exception)

    def test_can_be_raised(self):
        """可以正常抛出和捕获"""
        with pytest.raises(RequestFailed):
            raise RequestFailed("test error")


class TestPostWithRetry:
    """post_with_retry 函数测试"""

    @patch("api.http.requests.post")
    def test_success_first_try(self, mock_post):
        """首次成功返回 JSON"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 1, "msg": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = post_with_retry("http://test.com", {"key": "val"}, {})
        assert result == {"code": 1, "msg": "ok"}
        assert mock_post.call_count == 1

    @patch("api.http.requests.post")
    def test_retries_on_timeout(self, mock_post):
        """全部超时后抛出 RequestFailed"""
        mock_post.side_effect = requests.exceptions.Timeout("timeout")

        with pytest.raises(RequestFailed):
            post_with_retry("http://test.com", {}, {}, max_retries=3)
        assert mock_post.call_count == 3

    @patch("api.http.requests.post")
    def test_retries_on_http_error(self, mock_post):
        """HTTP 错误触发重试"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
        mock_post.return_value = mock_response

        with pytest.raises(RequestFailed):
            post_with_retry("http://test.com", {}, {}, max_retries=2)
        assert mock_post.call_count == 2

    @patch("api.http.requests.post")
    def test_retries_on_json_decode_error(self, mock_post):
        """JSON 解析失败触发重试"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_response

        with pytest.raises(RequestFailed):
            post_with_retry("http://test.com", {}, {}, max_retries=2)
        assert mock_post.call_count == 2

    @patch("api.http.requests.post")
    def test_sends_json_data(self, mock_post):
        """验证 data 通过 json 参数发送"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 1}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        data = {"key": "value"}
        post_with_retry("http://test.com", data, {"h": "v"})
        mock_post.assert_called_once_with(
            "http://test.com", json=data, headers={"h": "v"}, timeout=15
        )

    @patch("api.http.requests.post")
    def test_custom_max_retries(self, mock_post):
        """自定义重试次数"""
        mock_post.side_effect = requests.exceptions.Timeout("timeout")

        with pytest.raises(RequestFailed):
            post_with_retry("http://test.com", {}, {}, max_retries=5)
        assert mock_post.call_count == 5

    @patch("api.http.requests.post")
    def test_custom_timeout(self, mock_post):
        """自定义超时时间传递"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 1}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        post_with_retry("http://test.com", {}, {}, timeout=30)
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["timeout"] == 30

    @patch("api.http.requests.post")
    def test_success_after_failures(self, mock_post):
        """前几次失败，后续成功"""
        success_response = MagicMock()
        success_response.json.return_value = {"code": 1, "msg": "ok"}
        success_response.raise_for_status.return_value = None

        mock_post.side_effect = [
            requests.exceptions.Timeout("timeout"),
            requests.exceptions.Timeout("timeout"),
            success_response,
        ]

        result = post_with_retry("http://test.com", {}, {}, max_retries=5)
        assert result == {"code": 1, "msg": "ok"}
        assert mock_post.call_count == 3

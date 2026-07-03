"""
测试 py/auth/token.py — Token 管理器
"""
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import pytest

from auth.token import TokenManager, AuthenticationError, TOKEN_EXPIRY


class TestAuthenticationError:
    """异常类"""

    def test_is_exception(self):
        assert issubclass(AuthenticationError, Exception)


class TestTokenManager:
    """TokenManager 测试"""

    @patch("auth.token._login_with_retry")
    def test_get_token_calls_login(self, mock_login):
        """首次调用触发 qfnu_login"""
        mock_login.return_value = ("张三", "abc123")
        mgr = TokenManager("20240001", "pass")
        result = mgr.get_token()
        mock_login.assert_called_once_with("20240001", "pass", max_retries=3)

    @patch("auth.token._login_with_retry")
    def test_returns_bearer_prefix(self, mock_login):
        """返回值以 bearer 开头"""
        mock_login.return_value = ("张三", "abc123")
        mgr = TokenManager("20240001", "pass")
        result = mgr.get_token()
        assert result.startswith("bearer")
        assert result == "bearerabc123"

    @patch("auth.token._login_with_retry")
    def test_caches_within_expiry(self, mock_login):
        """1.5h 内重复调用只登录一次（手动设置 _timestamp 模拟）"""
        mock_login.return_value = ("张三", "abc123")
        mgr = TokenManager("20240001", "pass")
        # 首次调用
        mgr.get_token()
        assert mock_login.call_count == 1
        # 手动设置 timestamp 为 1 小时前（未过期）
        mgr._timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        mgr.get_token()
        assert mock_login.call_count == 1  # 仍只调用 1 次

    @patch("auth.token._login_with_retry")
    def test_refreshes_after_expiry(self, mock_login):
        """超过 1.5h 后重新登录"""
        mock_login.return_value = ("张三", "abc123")
        mgr = TokenManager("20240001", "pass")
        mgr.get_token()
        assert mock_login.call_count == 1
        # 手动设置 timestamp 为 2 小时前（已过期）
        mgr._timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
        mgr.get_token()
        assert mock_login.call_count == 2  # 重新登录

    def test_raises_on_empty_username(self):
        """空用户名抛出 AuthenticationError"""
        mgr = TokenManager("", "pass")
        with pytest.raises(AuthenticationError):
            mgr.get_token()

    def test_raises_on_empty_password(self):
        """空密码抛出 AuthenticationError"""
        mgr = TokenManager("user", "")
        with pytest.raises(AuthenticationError):
            mgr.get_token()

    @patch("auth.token._login_with_retry")
    def test_raises_on_login_failure(self, mock_login):
        """登录失败返回 None 时抛出 AuthenticationError"""
        mock_login.return_value = (None, None)
        mgr = TokenManager("user", "pass")
        with pytest.raises(AuthenticationError):
            mgr.get_token()

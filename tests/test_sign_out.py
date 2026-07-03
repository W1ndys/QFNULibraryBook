"""
测试 py/sign_out.py — 签退脚本
"""
from unittest.mock import patch, MagicMock

import pytest

from sign_out import go_home
from auth.token import AuthenticationError
from api.http import RequestFailed
from api.exceptions import SignOutFailed


class TestGoHome:
    """go_home 函数测试"""

    @patch("sign_out.send_message")
    @patch("sign_out.post_with_retry")
    @patch("sign_out.get_member_seat")
    def test_success(
        self, mock_member, mock_retry, mock_send,
        sample_config, fake_token_mgr
    ):
        """签退成功"""
        mock_member.return_value = {
            "data": {
                "data": [{"id": "5001", "statusName": "使用中"}]
            }
        }
        mock_retry.return_value = {"msg": "完全离开操作成功"}

        result = go_home(sample_config, fake_token_mgr)
        assert result is True  # 签退成功返回 True
        mock_send.assert_called_once()
        assert "签退成功" in mock_send.call_args[0][1]

    @patch("sign_out.send_message")
    @patch("sign_out.get_member_seat")
    def test_no_active_seat(self, mock_member, mock_send, sample_config, fake_token_mgr):
        """无正在使用的座位"""
        mock_member.return_value = {
            "data": {
                "data": [{"id": "5001", "statusName": "已取消"}]
            }
        }
        result = go_home(sample_config, fake_token_mgr)
        assert result is False  # 无座位返回 False，不再抛出 SystemExit

    @patch("sign_out.get_member_seat")
    def test_member_seat_none(self, mock_member, sample_config, fake_token_mgr):
        """get_member_seat 返回 None"""
        mock_member.return_value = None
        result = go_home(sample_config, fake_token_mgr)
        assert result is False  # 返回 False，不再抛出 SystemExit

    @patch("sign_out.send_message")
    def test_auth_error(self, mock_send, sample_config):
        """认证失败"""
        mock_mgr = MagicMock()
        mock_mgr.get_token.side_effect = AuthenticationError("认证失败")
        with pytest.raises(SignOutFailed):
            go_home(sample_config, mock_mgr)
        mock_send.assert_called_once()

    @patch("sign_out.send_message")
    @patch("sign_out.post_with_retry")
    @patch("sign_out.get_member_seat")
    def test_request_failed(
        self, mock_member, mock_retry, mock_send, sample_config, fake_token_mgr
    ):
        """签退请求失败"""
        mock_member.return_value = {
            "data": {
                "data": [{"id": "5001", "statusName": "使用中"}]
            }
        }
        mock_retry.side_effect = RequestFailed("failed")
        with pytest.raises(SignOutFailed):
            go_home(sample_config, fake_token_mgr)

    @patch("sign_out.get_member_seat")
    def test_already_signed_out(self, mock_member, sample_config, fake_token_mgr):
        """已签退（非 '完全离开操作成功'）"""
        mock_member.return_value = {
            "data": {
                "data": [{"id": "5001", "statusName": "使用中"}]
            }
        }
        with patch("sign_out.post_with_retry") as mock_retry:
            mock_retry.return_value = {"msg": "其他状态"}
            # 不应抛出异常
            result = go_home(sample_config, fake_token_mgr)
            assert result is None  # 已签退返回 None
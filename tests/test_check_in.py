"""
测试 py/check_in.py — 签到脚本
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from check_in import lib_rsv
from auth.token import AuthenticationError
from api.exceptions import CheckInFailed


class TestLibRsv:
    """lib_rsv 函数测试"""

    @patch("check_in.send_message")
    @patch("check_in.requests.session")
    def test_success(self, mock_session_cls, mock_send, sample_config, fake_token_mgr):
        """签到成功"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.text = json.dumps({"msg": "签到成功"})
        mock_session.post.return_value = mock_response

        lib_rsv(sample_config, fake_token_mgr)
        # 验证 send_message 被调用且含 "签到成功"
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "签到成功" in call_args[1]

    @patch("check_in.send_message")
    @patch("check_in.requests.session")
    def test_already_checked_in(self, mock_session_cls, mock_send, sample_config, fake_token_mgr):
        """重复签到"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.text = json.dumps({"msg": "使用中,不用重复签到！"})
        mock_session.post.return_value = mock_response

        lib_rsv(sample_config, fake_token_mgr)
        call_args = mock_send.call_args[0]
        assert "已签到" in call_args[1]

    @patch("check_in.send_message")
    @patch("check_in.requests.session")
    def test_not_effective(self, mock_session_cls, mock_send, sample_config, fake_token_mgr):
        """预约未生效"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.text = json.dumps({"msg": "对不起，您的预约未生效"})
        mock_session.post.return_value = mock_response

        lib_rsv(sample_config, fake_token_mgr)
        call_args = mock_send.call_args[0]
        assert "未生效" in call_args[1]

    @patch("check_in.send_message")
    @patch("check_in.requests.session")
    def test_failure(self, mock_session_cls, mock_send, sample_config, fake_token_mgr):
        """未知消息 → 签到失败"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.text = json.dumps({"msg": "未知错误"})
        mock_session.post.return_value = mock_response

        lib_rsv(sample_config, fake_token_mgr)
        call_args = mock_send.call_args[0]
        assert "签到失败" in call_args[1]

    def test_auth_error_exits(self, sample_config):
        """认证失败 → CheckInFailed"""
        mock_mgr = MagicMock()
        mock_mgr.get_token.side_effect = AuthenticationError("认证失败")
        with pytest.raises(CheckInFailed):
            lib_rsv(sample_config, mock_mgr)

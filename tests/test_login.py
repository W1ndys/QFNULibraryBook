"""
测试 py/auth/login.py — 登录模块（滑块验证码 + CAS 登录）
"""
from unittest.mock import patch, MagicMock

import pytest
import numpy as np

from auth.login import (
    _generate_human_tracks,
    _detect_gap,
    _get_salt_and_execution,
    _check_need_captcha,
)


# ========== 鼠标轨迹生成 ==========

class TestGenerateHumanTracks:
    """_generate_human_tracks 测试"""

    def test_returns_list_of_dicts(self):
        """返回 list[dict]，每个含 a, b, c"""
        tracks = _generate_human_tracks(100)
        assert isinstance(tracks, list)
        assert len(tracks) > 0
        for t in tracks:
            assert "a" in t
            assert "b" in t
            assert "c" in t

    def test_starts_at_zero(self):
        """首个点原点"""
        tracks = _generate_human_tracks(100)
        assert tracks[0] == {"a": 0, "b": 0, "c": 0}

    def test_ends_near_distance(self):
        """最后一点的 a 接近目标距离"""
        distance = 150.0
        tracks = _generate_human_tracks(distance)
        assert abs(tracks[-1]["a"] - distance) <= 0.5

    def test_monotonic_x(self):
        """a 值非递减"""
        tracks = _generate_human_tracks(200)
        for i in range(1, len(tracks)):
            assert tracks[i]["a"] >= tracks[i - 1]["a"]

    def test_small_distance(self):
        """小距离也能正常生成"""
        tracks = _generate_human_tracks(5)
        assert len(tracks) > 0
        assert abs(tracks[-1]["a"] - 5.0) <= 0.5


# ========== 缺口检测 ==========

class TestDetectGap:
    """_detect_gap 测试"""

    def test_scales_to_280(self):
        """验证 280/bg_width 缩放因子"""
        bg = np.zeros((160, 400, 3), dtype=np.uint8)
        slider = np.zeros((160, 60, 3), dtype=np.uint8)

        with patch("auth.login._detect_gap_opencv") as mock_detect:
            mock_detect.return_value = (100, 0.95)
            result = _detect_gap(bg, slider)

        # 100 * (280 / 400) = 70
        assert abs(result - 70.0) < 0.01


# ========== HTML 参数提取 ==========

class TestGetSaltAndExecution:
    """_get_salt_and_execution 测试"""

    def test_parses_html(self):
        """HTML 含隐藏字段正确提取"""
        html = '''
        <input type="hidden" id="pwdEncryptSalt" value="testSalt123">
        <input type="hidden" name="execution" value="exec456">
        '''
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = html
        mock_session.get.return_value = mock_response

        salt, execution = _get_salt_and_execution(mock_session, {})
        assert salt == "testSalt123"
        assert execution == "exec456"

    def test_missing_fields(self):
        """HTML 缺少字段返回 (None, None)"""
        html = "<html><body>No hidden inputs</body></html>"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = html
        mock_session.get.return_value = mock_response

        salt, execution = _get_salt_and_execution(mock_session, {})
        assert salt is None
        assert execution is None


# ========== 验证码检查 ==========

class TestCheckNeedCaptcha:
    """_check_need_captcha 测试"""

    def test_returns_true(self):
        """响应含 'true' 返回 truthy"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "true"
        mock_session.get.return_value = mock_response

        result = _check_need_captcha(mock_session, {}, "user")
        assert result is True

    def test_returns_false(self):
        """响应为 'false' 返回 falsy"""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "false"
        mock_session.get.return_value = mock_response

        result = _check_need_captcha(mock_session, {}, "user")
        assert result is False

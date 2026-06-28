"""
测试 py/get_info.py — 日期/教室/座位查询函数
"""
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import pytest

from get_info import get_date, get_build_id, get_segment, get_member_seat, get_seat_info
from api.http import RequestFailed


# ========== get_date ==========

class TestGetDate:
    """日期解析函数"""

    def test_get_date_today(self):
        """today 返回今天日期字符串"""
        fixed = datetime(2026, 6, 28, 12, 0, 0)
        with patch("get_info.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            result = get_date("today")
        assert result == "2026-06-28"

    def test_get_date_tomorrow(self):
        """tomorrow 返回明天日期字符串"""
        fixed = datetime(2026, 6, 28, 12, 0, 0)
        with patch("get_info.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            result = get_date("tomorrow")
        assert result == "2026-06-29"

    def test_get_date_invalid_exits(self):
        """非法参数调用 sys.exit()"""
        with pytest.raises(SystemExit):
            get_date("invalid_date")


# ========== get_build_id ==========

class TestGetBuildId:
    """教室名称查询"""

    def test_get_build_id_valid(self):
        """有效教室名称返回正确 ID"""
        assert get_build_id("综合楼-801自习室") == 16

    def test_get_build_id_alias(self):
        """别名教室返回正确 ID"""
        assert get_build_id("东校区图书馆-三层自习室") == 22

    def test_get_build_id_unknown(self):
        """不存在的教室返回 None"""
        assert get_build_id("不存在的教室") is None

    def test_get_build_id_sample_ids(self):
        """更多教室 ID 验证"""
        assert get_build_id("西校区图书馆-二层自习室") == 45
        assert get_build_id("行政楼-四层东区自习室") == 13
        assert get_build_id("电视台楼-二层自习室") == 12


# ========== get_segment ==========

class TestGetSegment:
    """时间段查询"""

    @patch("get_info.post_with_retry")
    def test_get_segment_success(self, mock_retry):
        """匹配日期返回 segment ID"""
        mock_retry.return_value = {
            "data": [
                {
                    "day": "2026-06-28",
                    "times": [{"id": 999, "name": "08:00-22:00"}],
                },
                {
                    "day": "2026-06-29",
                    "times": [{"id": 1000, "name": "08:00-22:00"}],
                },
            ]
        }
        result = get_segment(16, "2026-06-28")
        assert result == 999

    @patch("get_info.post_with_retry")
    def test_get_segment_no_match(self, mock_retry):
        """无匹配日期返回 None"""
        mock_retry.return_value = {
            "data": [
                {"day": "2026-07-01", "times": [{"id": 999}]},
            ]
        }
        result = get_segment(16, "2026-06-28")
        assert result is None

    @patch("get_info.post_with_retry")
    def test_get_segment_request_failed(self, mock_retry):
        """RequestFailed 触发 sys.exit()"""
        mock_retry.side_effect = RequestFailed("failed")
        with pytest.raises(SystemExit):
            get_segment(16, "2026-06-28")


# ========== get_member_seat ==========

class TestGetMemberSeat:
    """用户座位查询"""

    @patch("get_info.post_with_retry")
    def test_get_member_seat_success(self, mock_retry):
        """正常返回座位数据"""
        expected = {"code": 1, "data": {"data": [{"id": "1"}]}}
        mock_retry.return_value = expected
        result = get_member_seat("bearer fake_token")
        assert result == expected

    @patch("get_info.post_with_retry")
    def test_get_member_seat_request_failed(self, mock_retry):
        """RequestFailed 返回 None"""
        mock_retry.side_effect = RequestFailed("failed")
        result = get_member_seat("bearer fake_token")
        assert result is None

    @patch("get_info.post_with_retry")
    def test_get_member_seat_key_error(self, mock_retry):
        """KeyError 返回 None"""
        mock_retry.side_effect = KeyError("missing key")
        result = get_member_seat("bearer fake_token")
        assert result is None


# ========== get_seat_info ==========

class TestGetSeatInfo:
    """座位信息查询"""

    @patch("get_info.post_with_retry")
    def test_get_seat_info_filters_free(self, mock_retry):
        """只返回空闲座位"""
        mock_retry.return_value = {
            "data": [
                {"id": "100", "no": "001", "status_name": "空闲"},
                {"id": "101", "no": "002", "status_name": "已预约"},
                {"id": "102", "no": "003", "status_name": "空闲"},
                {"id": "103", "no": "004", "status_name": "使用中"},
            ]
        }
        result = get_seat_info(16, 999, "2026-06-28")
        assert len(result) == 2
        assert all(s.get("id") for s in result)  # 返回的字典含 id 和 no

    @patch("get_info.post_with_retry")
    def test_get_seat_info_returns_id_no(self, mock_retry):
        """返回字典仅含 id 和 no"""
        mock_retry.return_value = {
            "data": [
                {"id": "100", "no": "001", "status_name": "空闲", "extra": "data"},
            ]
        }
        result = get_seat_info(16, 999, "2026-06-28")
        assert len(result) == 1
        assert set(result[0].keys()) == {"id", "no"}

    @patch("get_info.post_with_retry")
    def test_get_seat_info_empty_data(self, mock_retry):
        """空数据返回空列表"""
        mock_retry.return_value = {"data": []}
        result = get_seat_info(16, 999, "2026-06-28")
        assert result == []

    @patch("get_info.post_with_retry")
    def test_get_seat_info_all_occupied(self, mock_retry):
        """全部非空闲时返回空列表"""
        mock_retry.return_value = {
            "data": [
                {"id": "100", "no": "001", "status_name": "已预约"},
                {"id": "101", "no": "002", "status_name": "使用中"},
            ]
        }
        result = get_seat_info(16, 999, "2026-06-28")
        assert result == []

"""
测试 src/get_seat_info_ForAdmin.py — 管理员工具
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from get_seat_info_ForAdmin import get_seat_info, get_info_and_select_seat
from api.http import RequestFailed


class TestGetSeatInfo:
    """get_seat_info 函数测试"""

    @patch("get_seat_info_ForAdmin.post_with_retry")
    def test_returns_free_seats(self, mock_retry):
        """只返回空闲座位"""
        mock_retry.return_value = {
            "data": [
                {"id": "100", "no": "001", "status_name": "空闲"},
                {"id": "101", "no": "002", "status_name": "已预约"},
                {"id": "102", "no": "003", "status_name": "空闲"},
            ]
        }
        result = get_seat_info(16, 999, "2026-06-28")
        assert len(result) == 2
        assert result[0]["id"] == "100"
        assert result[1]["id"] == "102"

    @patch("get_seat_info_ForAdmin.post_with_retry")
    def test_saves_file(self, mock_retry, tmp_path):
        """save_file 非空时写入 JSON 文件"""
        response_data = {"data": [{"id": "100", "no": "001", "status_name": "空闲"}]}
        mock_retry.return_value = response_data

        save_path = str(tmp_path / "output.json")
        result = get_seat_info(16, 999, "2026-06-28", save_file=save_path)

        # 验证文件已写入
        with open(save_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == response_data

    @patch("get_seat_info_ForAdmin.post_with_retry")
    def test_no_save(self, mock_retry):
        """save_file=None 不写文件"""
        mock_retry.return_value = {"data": [{"id": "100", "no": "001", "status_name": "空闲"}]}
        result = get_seat_info(16, 999, "2026-06-28")
        assert result is not None

    @patch("get_seat_info_ForAdmin.post_with_retry")
    def test_request_failed_returns_none(self, mock_retry):
        """RequestFailed 返回 None"""
        mock_retry.side_effect = RequestFailed("failed")
        result = get_seat_info(16, 999, "2026-06-28")
        assert result is None


class TestGetInfoAndSelectSeat:
    """get_info_and_select_seat 测试"""

    @patch("get_seat_info_ForAdmin.get_seat_info")
    @patch("get_seat_info_ForAdmin.get_segment")
    @patch("get_seat_info_ForAdmin.get_build_id")
    @patch("get_seat_info_ForAdmin.get_date")
    def test_all_classrooms(self, mock_date, mock_build, mock_seg, mock_seat_info):
        """遍历所有教室"""
        mock_date.return_value = "2026-06-28"
        mock_build.return_value = 16
        mock_seg.return_value = 999
        mock_seat_info.return_value = [{"id": "100", "no": "001"}]

        config = MagicMock()
        config.date = "tomorrow"
        config.classrooms_name = ["综合楼-801自习室", "综合楼-803自习室"]

        get_info_and_select_seat(config)
        assert mock_seat_info.call_count == 2

    @patch("get_seat_info_ForAdmin.get_build_id")
    @patch("get_seat_info_ForAdmin.get_date")
    def test_unknown_classroom_skip(self, mock_date, mock_build):
        """未知教室跳过"""
        mock_date.return_value = "2026-06-28"
        mock_build.return_value = None

        config = MagicMock()
        config.date = "tomorrow"
        config.classrooms_name = ["不存在的教室"]

        get_info_and_select_seat(config)  # 不应崩溃

"""
测试 py/get_seat.py — 座位预约主逻辑
"""
from unittest.mock import patch, MagicMock

import pytest

from get_seat import (
    random_get_seat,
    check_reservation_status,
    check_book_seat,
    post_to_get_seat,
    select_seat,
    run_seat_reservation,
)
from api.exceptions import ReservationFailed
from classrooms import EXCLUDE_ID
from config.config import AppConfig
from api.http import RequestFailed


# ========== random_get_seat ==========

class TestRandomGetSeat:
    """随机选座"""

    def test_returns_id(self):
        """从列表随机返回一个 id"""
        data = [{"id": "100"}, {"id": "200"}, {"id": "300"}]
        result = random_get_seat(data)
        assert result in ["100", "200", "300"]

    def test_single_item(self):
        """单个座位返回该 id"""
        data = [{"id": "42"}]
        assert random_get_seat(data) == "42"

    def test_empty_raises(self):
        """空列表抛出 IndexError"""
        with pytest.raises(IndexError):
            random_get_seat([])


# ========== check_reservation_status ==========

class TestCheckReservationStatus:
    """预约状态检测"""

    def test_success(self, sample_config, fake_token_mgr):
        """预约成功"""
        with patch("get_seat.check_book_seat") as mock_check:
            mock_check.return_value = True
            result = check_reservation_status(
                {"msg": "预约成功"}, sample_config, fake_token_mgr, []
            )
        assert result is True

    def test_duplicate(self, sample_config, fake_token_mgr):
        """重复预约"""
        with patch("get_seat.check_book_seat") as mock_check:
            mock_check.return_value = True
            result = check_reservation_status(
                {"msg": "当前用户在该时段已存在座位预约，不可重复预约"},
                sample_config, fake_token_mgr, [],
            )
        assert result is True

    def test_not_open(self, sample_config, fake_token_mgr):
        """未到预约时间"""
        result = check_reservation_status(
            {"msg": "开放预约时间19:20"}, sample_config, fake_token_mgr, []
        )
        assert result is False

    def test_not_logged_in(self, sample_config, fake_token_mgr):
        """未登录触发 token 刷新"""
        result = check_reservation_status(
            {"msg": "您尚未登录"}, sample_config, fake_token_mgr, []
        )
        fake_token_mgr.get_token.assert_called()
        assert result is False

    def test_cancel_success_exits(self, sample_config, fake_token_mgr):
        """取消成功返回 True（不再退出）"""
        result = check_reservation_status(
            {"msg": "取消成功"}, sample_config, fake_token_mgr, []
        )
        assert result is True

    def test_unknown_msg(self, sample_config, fake_token_mgr):
        """未知消息返回 True"""
        result = check_reservation_status(
            {"msg": "未知状态"}, sample_config, fake_token_mgr, []
        )
        assert result is True

    def test_invalid_input_exits(self, sample_config, fake_token_mgr):
        """非 dict 输入触发 ReservationFailed"""
        with pytest.raises(ReservationFailed):
            check_reservation_status(
                "not a dict", sample_config, fake_token_mgr, []
            )


# ========== check_book_seat ==========

class TestCheckBookSeat:
    """检查已预约座位"""

    @patch("get_seat.get_member_seat")
    def test_found_reservation(self, mock_member, sample_config, fake_token_mgr):
        """已预约成功"""
        mock_member.return_value = {
            "data": {
                "data": [{"statusName": "预约成功", "name": "001", "nameMerge": "综合楼-801 001"}]
            }
        }
        messages = []
        result = check_book_seat(sample_config, fake_token_mgr, messages, "bearer token")
        assert result is True

    @patch("get_seat.get_member_seat")
    def test_no_reservation(self, mock_member, sample_config, fake_token_mgr):
        """无预约"""
        mock_member.return_value = {
            "data": {
                "data": [{"statusName": "已取消", "name": "001", "nameMerge": "test"}]
            }
        }
        result = check_book_seat(sample_config, fake_token_mgr, [], "bearer token")
        assert result is False

    @patch("get_seat.get_member_seat")
    def test_not_logged_in_refreshes(self, mock_member, sample_config, fake_token_mgr):
        """未登录时刷新 token"""
        mock_member.return_value = {"msg": "您尚未登录"}
        check_book_seat(sample_config, fake_token_mgr, [], "bearer token")
        fake_token_mgr.get_token.assert_called()

    @patch("get_seat.get_member_seat")
    def test_member_none(self, mock_member, sample_config, fake_token_mgr):
        """返回 None 不崩溃"""
        mock_member.return_value = None
        result = check_book_seat(sample_config, fake_token_mgr, [], "bearer token")
        assert result is False


# ========== select_seat ==========

class TestSelectSeat:
    """选座主逻辑"""

    @patch("get_seat.post_to_get_seat")
    @patch("get_seat.get_seat_info")
    def test_mode3_random(self, mock_seat_info, mock_post, sample_config, fake_token_mgr):
        """模式 3：随机选择后 sys.exit（retries 满）"""
        sample_config.mode = "3"
        mock_seat_info.return_value = [
            {"id": "100", "no": "001"},
            {"id": "101", "no": "002"},
        ]
        mock_post.return_value = None
        # select_seat 循环 100 次后抛 ReservationFailed
        with patch("get_seat.send_message"):
            with pytest.raises(ReservationFailed):
                select_seat(16, 999, "2026-06-28", sample_config, fake_token_mgr, [])
        # post_to_get_seat 被调用了
        assert mock_post.call_count >= 1

    @patch("get_seat.post_to_get_seat")
    @patch("get_seat.get_seat_info")
    def test_mode2_excludes(self, mock_seat_info, mock_post, sample_config, fake_token_mgr):
        """模式 2：排除 EXCLUDE_ID 中的座位"""
        sample_config.mode = "2"
        # 第一个座位在 EXCLUDE_ID 中，第二个不在
        excluded_id = list(EXCLUDE_ID)[0]
        mock_seat_info.return_value = [
            {"id": excluded_id, "no": "001"},
            {"id": "99999", "no": "002"},
        ]
        mock_post.return_value = None
        # 循环结束后 sys.exit
        with patch("get_seat.send_message"):
            with pytest.raises(ReservationFailed):
                select_seat(16, 999, "2026-06-28", sample_config, fake_token_mgr, [])
        # 每次调用 post_to_get_seat 时选中的都是 99999（非排除的）
        for call in mock_post.call_args_list:
            assert call[0][0] == "99999"

    @patch("get_seat.post_to_get_seat")
    @patch("get_seat.get_seat_info")
    def test_mode1_filters_range(self, mock_seat_info, mock_post, sample_config, fake_token_mgr):
        """模式 1：范围过滤"""
        sample_config.mode = "1"
        sample_config.seat_id = [[100, 102]]
        mock_seat_info.return_value = [
            {"id": "100", "no": "001"},
            {"id": "101", "no": "002"},
            {"id": "200", "no": "100"},  # 超出范围
        ]
        mock_post.return_value = None
        with patch("get_seat.send_message"):
            with pytest.raises(ReservationFailed):
                select_seat(16, 999, "2026-06-28", sample_config, fake_token_mgr, [])
        # 每次选中的座位 ID 都在 100-102 范围内
        for call in mock_post.call_args_list:
            assert call[0][0] in ["100", "101"]

    @patch("get_seat.get_seat_info")
    def test_mode4_wrong_build_skips(self, mock_seat_info, sample_config, fake_token_mgr):
        """模式 4 + build_id != 22 → 循环 100 次后退出"""
        sample_config.mode = "4"
        mock_seat_info.return_value = [{"id": "100", "no": "228"}]
        with patch("get_seat.send_message"):
            with pytest.raises(ReservationFailed):
                select_seat(16, 999, "2026-06-28", sample_config, fake_token_mgr, [])

    @patch("get_seat.post_to_get_seat")
    @patch("get_seat.get_seat_info")
    def test_mode4_target_found(self, mock_seat_info, mock_post, sample_config, fake_token_mgr):
        """模式 4 + 座位 228 可用，选中后继续循环"""
        sample_config.mode = "4"
        mock_seat_info.return_value = [
            {"id": "5001", "no": "228"},
            {"id": "5002", "no": "229"},
        ]
        mock_post.return_value = None
        with patch("get_seat.send_message"):
            with pytest.raises(ReservationFailed):
                select_seat(22, 999, "2026-06-28", sample_config, fake_token_mgr, [])
        # 每次都选中 228 号座位
        for call in mock_post.call_args_list:
            assert call[0][0] == "5001"

    @patch("get_seat.get_seat_info")
    def test_unknown_mode_breaks(self, mock_seat_info, sample_config, fake_token_mgr):
        """非法模式 → break"""
        sample_config.mode = "99"
        mock_seat_info.return_value = [{"id": "100", "no": "001"}]
        select_seat(16, 999, "2026-06-28", sample_config, fake_token_mgr, [])
        # 只调用一次就 break
        assert mock_seat_info.call_count == 1

    @patch("get_seat.get_seat_info")
    def test_empty_data_breaks(self, mock_seat_info, sample_config, fake_token_mgr):
        """空座位列表 → break"""
        sample_config.mode = "3"
        mock_seat_info.return_value = []
        messages = []
        select_seat(16, 999, "2026-06-28", sample_config, fake_token_mgr, messages)
        assert mock_seat_info.call_count == 1
        assert any("获取座位信息失败" in m for m in messages)


# ========== run_seat_reservation ==========

class TestRunSeatReservation:
    """预约主流程"""

    @patch("get_seat.send_message")
    @patch("get_seat.select_seat")
    @patch("get_seat.get_segment")
    @patch("get_seat.get_build_id")
    @patch("get_seat.get_date")
    def test_full_flow(
        self, mock_date, mock_build, mock_seg, mock_select, mock_send,
        sample_config, fake_token_mgr
    ):
        """遍历所有教室"""
        mock_date.return_value = "2026-06-28"
        mock_build.return_value = 16
        mock_seg.return_value = 999
        sample_config.classrooms_name = ["综合楼-801自习室", "综合楼-803自习室"]

        run_seat_reservation(sample_config, fake_token_mgr)
        assert mock_select.call_count == 2

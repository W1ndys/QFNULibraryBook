"""
测试 py/api/constants.py — API URL 和请求头常量
"""
from api.constants import (
    LIB_BASE_URL,
    URL_GET_SEAT,
    URL_CLASSROOM_DETAIL_INFO,
    URL_CLASSROOM_SEAT,
    URL_CHECK_IN,
    URL_CHECK_OUT,
    URL_CANCEL_SEAT,
    URL_CHECK_STATUS,
    DEFAULT_HEADERS,
)


class TestBaseUrl:
    """基础 URL"""

    def test_base_url_format(self):
        """LIB_BASE_URL 以 http:// 开头"""
        assert LIB_BASE_URL.startswith("http://")

    def test_base_url_no_trailing_slash(self):
        """LIB_BASE_URL 无尾部斜杠"""
        assert not LIB_BASE_URL.endswith("/")


class TestUrls:
    """API URL 常量"""

    def test_all_urls_start_with_base(self):
        """所有 URL_* 常量以 LIB_BASE_URL 开头"""
        all_urls = [
            URL_GET_SEAT,
            URL_CLASSROOM_DETAIL_INFO,
            URL_CLASSROOM_SEAT,
            URL_CHECK_IN,
            URL_CHECK_OUT,
            URL_CANCEL_SEAT,
            URL_CHECK_STATUS,
        ]
        for url in all_urls:
            assert url.startswith(LIB_BASE_URL), f"{url} 未以 {LIB_BASE_URL} 开头"

    def test_url_get_seat_path(self):
        """预约 URL 路径正确"""
        assert "/api/Seat/confirm" in URL_GET_SEAT

    def test_url_check_in_path(self):
        """签到 URL 路径正确"""
        assert "/api/Seat/touch_qr_books" in URL_CHECK_IN

    def test_url_check_out_path(self):
        """签退 URL 路径正确"""
        assert "/api/Space/checkout" in URL_CHECK_OUT


class TestDefaultHeaders:
    """默认请求头"""

    def test_has_required_keys(self):
        """包含必要请求头字段"""
        required = ["Content-Type", "User-Agent", "Origin", "Referer"]
        for key in required:
            assert key in DEFAULT_HEADERS, f"缺少 {key}"

    def test_content_type_is_json(self):
        """Content-Type 为 application/json"""
        assert DEFAULT_HEADERS["Content-Type"] == "application/json"

    def test_origin_matches_base(self):
        """Origin 等于 LIB_BASE_URL"""
        assert DEFAULT_HEADERS["Origin"] == LIB_BASE_URL

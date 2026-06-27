"""
API URL 常量和默认请求头
"""

# 图书馆预约系统 API 基础 URL
LIB_BASE_URL = "http://libyy.qfnu.edu.cn"

# 座位相关
URL_GET_SEAT = f"{LIB_BASE_URL}/api/Seat/confirm"
URL_CLASSROOM_DETAIL_INFO = f"{LIB_BASE_URL}/api/Seat/date"
URL_CLASSROOM_SEAT = f"{LIB_BASE_URL}/api/Seat/seat"
URL_CHECK_IN = f"{LIB_BASE_URL}/api/Seat/touch_qr_books"

# 签退相关
URL_CHECK_OUT = f"{LIB_BASE_URL}/api/Space/checkout"
URL_CANCEL_SEAT = f"{LIB_BASE_URL}/api/Space/cancel"

# 用户状态
URL_CHECK_STATUS = f"{LIB_BASE_URL}/api/Member/seat"

# 默认请求头
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
    "lang": "zh",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    ),
    "Origin": LIB_BASE_URL,
    "Referer": f"{LIB_BASE_URL}/h5/index.html",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5",
}

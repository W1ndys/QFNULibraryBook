"""
自定义异常类 — 多用户并发场景下的异常隔离

提供以下异常类型:
  - RequestFailed: HTTP 请求在最大重试次数后失败
  - AuthenticationError: 用户认证失败
  - ReservationFailed: 座位预约失败
  - CheckInFailed: 签到失败
  - SignOutFailed: 签退失败
"""


class RequestFailed(Exception):
    """POST 请求在最大重试次数后仍然失败"""
    pass


class AuthenticationError(Exception):
    """用户认证失败（用户名/密码错误或网络故障）"""
    pass


class ReservationFailed(Exception):
    """座位预约失败"""
    pass


class CheckInFailed(Exception):
    """签到失败"""
    pass


class SignOutFailed(Exception):
    """签退失败"""
    pass
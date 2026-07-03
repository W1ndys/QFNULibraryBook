"""
Token 管理器 — 封装 Bearer Token 获取和缓存
支持多线程安全（threading.Lock 双重检查锁）
"""
import datetime
import logging
import threading

from auth.login import _login_with_retry

logger = logging.getLogger(__name__)

# Token 有效期
TOKEN_EXPIRY = datetime.timedelta(hours=1, minutes=30)

# 登录最大重试次数
_MAX_LOGIN_RETRIES = 3


class AuthenticationError(Exception):
    """登录认证失败"""
    pass


class TokenManager:
    """
    Bearer Token 管理器，自动处理获取和过期缓存。

    线程安全：使用 threading.Lock + 双重检查锁定模式（Double-checked locking）。

    使用方式:
        token_mgr = TokenManager(username, password)
        auth_token = token_mgr.get_token()  # 返回 "bearer" + token
    """

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._token: str = ""
        self._timestamp: datetime.datetime = None
        self._lock = threading.Lock()

    def _is_expired(self) -> bool:
        """检查 Token 是否已过期（兼容 naive 和 aware datetime）"""
        if self._timestamp is None:
            return True
        # 兼容：如果存储的是 naive datetime，视为 UTC
        ts = self._timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - ts) > TOKEN_EXPIRY

    def get_token(self) -> str:
        """
        获取有效的 Bearer Token（带 "bearer" 前缀）。
        如果 Token 已过期或未获取，自动重新登录。

        线程安全：双重检查锁定，避免多个线程同时刷新 Token。

        异常:
            AuthenticationError: 登录失败
        """
        if not self._username or not self._password:
            raise AuthenticationError("未找到用户名或密码")

        # 无锁快速路径：Token 有效时直接返回
        if self._token and not self._is_expired():
            logger.info("使用现有授权码")
            return self._token

        # 锁保护下的刷新路径
        with self._lock:
            # 双重检查：避免获取锁期间已被其他线程刷新
            if self._token and not self._is_expired():
                logger.info("使用现有授权码（锁后检查）")
                return self._token

            logger.info("Token 已过期或未获取，重新登录...")
            name, token = _login_with_retry(self._username, self._password,
                                            max_retries=_MAX_LOGIN_RETRIES)
            if token is None:
                raise AuthenticationError("获取 token 失败，账号密码错误或者网络错误。")
            self._token = "bearer" + str(token)
            self._timestamp = datetime.datetime.now(datetime.timezone.utc)
            logger.info(f"成功获取授权码，姓名: {name}")

        return self._token
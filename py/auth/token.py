"""
Token 管理器 — 封装 Bearer Token 获取和缓存
"""
import datetime
import logging

from auth.login import qfnu_login

logger = logging.getLogger(__name__)

# Token 有效期
TOKEN_EXPIRY = datetime.timedelta(hours=1, minutes=30)


class AuthenticationError(Exception):
    """登录认证失败"""
    pass


class TokenManager:
    """
    Bearer Token 管理器，自动处理获取和过期缓存。

    使用方式:
        token_mgr = TokenManager(username, password)
        auth_token = token_mgr.get_token()  # 返回 "bearer" + token
    """

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._token: str = ""
        self._timestamp: datetime.datetime = None

    def get_token(self) -> str:
        """
        获取有效的 Bearer Token（带 "bearer" 前缀）。
        如果 Token 已过期或未获取，自动重新登录。

        异常:
            AuthenticationError: 登录失败
        """
        if not self._username or not self._password:
            raise AuthenticationError("未找到用户名或密码")

        if (
            self._timestamp is None
            or (datetime.datetime.now() - self._timestamp) > TOKEN_EXPIRY
        ):
            logger.info("Token 已过期或未获取，重新登录...")
            name, token = qfnu_login(self._username, self._password)
            if token is None:
                raise AuthenticationError("获取 token 失败，账号密码错误或者网络错误。")
            self._token = "bearer" + str(token)
            self._timestamp = datetime.datetime.now()
            logger.info(f"成功获取授权码，姓名: {name}")
        else:
            logger.info("使用现有授权码")

        return self._token

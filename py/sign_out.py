"""
图书馆签退脚本
用法: python sign_out.py [-c configs/studentA.yml]
"""
import argparse
import logging

from config.config import AppConfig
from auth.token import TokenManager, AuthenticationError
from notify.notify import send_message
from api.constants import URL_CHECK_OUT, DEFAULT_HEADERS
from api.http import post_with_retry, RequestFailed
from api.exceptions import SignOutFailed
from get_info import get_member_seat

logger = logging.getLogger(__name__)


def go_home(config: AppConfig, token_mgr: TokenManager):
    """签退主逻辑"""
    try:
        auth_token = token_mgr.get_token()
        res = get_member_seat(auth_token)

        if res is not None:
            seat_id = None
            for item in res["data"]["data"]:
                if item["statusName"] == "使用中":
                    seat_id = item["id"]
                    break

            if seat_id is not None:
                post_data = {"id": seat_id, "authorization": auth_token}
                request_headers = {
                    **DEFAULT_HEADERS,
                    "Authorization": auth_token,
                }
                try:
                    res = post_with_retry(URL_CHECK_OUT, post_data, request_headers, max_retries=10, retry_delay=1, timeout=15)
                except RequestFailed:
                    logger.error("签退请求失败，超过最大重试次数")
                    send_message(config, "\n超过最大重试次数,请求失败。", "图书馆签退通知")
                    raise SignOutFailed("超过最大重试次数,请求失败。")

                if "msg" in res:
                    status = res["msg"]
                    logger.info("签退状态：" + status)
                    if status == "完全离开操作成功":
                        send_message(config, "签退成功", "图书馆签退通知")
                        return True
                    else:
                        logger.info("已经签退")
            else:
                logger.error("没有找到正在使用的座位，今天你可能没有预约座位")
                send_message(config, "\n没有找到正在使用的座位，今天你可能没有预约座位", "图书馆签退通知")
                return False
        else:
            logger.error("获取数据失败，请检查登录状态")
            return False

    except AuthenticationError as e:
        logger.error(str(e))
        send_message(config, f"\n{e}", "图书馆签退通知")
        raise SignOutFailed(str(e)) from e
    except KeyError:
        logger.error("返回数据与规则不符，大概率是没有登录")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="图书馆签退脚本")
    parser.add_argument("-c", "--config", help="指定配置文件路径，默认为 configs/template.yml")
    args = parser.parse_args()

    try:
        config = AppConfig.from_yaml(args.config)
        token_mgr = TokenManager(config.username, config.password)
        go_home(config, token_mgr)
    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")

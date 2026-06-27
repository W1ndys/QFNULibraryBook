"""
图书馆签到脚本
用法: python check_in.py [-c config_studentA.yml]
"""
import argparse
import json
import logging
import sys

import requests

from config.config import AppConfig
from auth.token import TokenManager, AuthenticationError
from notify.notify import send_message
from api.constants import URL_CHECK_IN
from crypto.aes import encrypt_seat_data

logger = logging.getLogger(__name__)


def lib_rsv(config: AppConfig, token_mgr: TokenManager):
    """签到主逻辑"""
    try:
        bearer_token = token_mgr.get_token()
    except AuthenticationError as e:
        logger.error(str(e))
        sys.exit()

    sub_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/117.0.5938.63 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "authorization": bearer_token,
    }
    sub_data = {
        "aesjson": encrypt_seat_data('{"method":"checkin"}'),
        "authorization": bearer_token,
    }

    session = requests.session()
    res = session.post(
        url=URL_CHECK_IN,
        headers=sub_headers,
        data=json.dumps(sub_data),
    )
    res = json.loads(res.text)
    print(res)

    title = f"图书馆签到通知 - 学号: {config.username}"
    if res["msg"] == "签到成功":
        logger.info("签到成功")
        send_message(config, config.username + "签到成功！", title)
    elif res["msg"] == "使用中,不用重复签到！":
        logger.info("已签到")
        send_message(config, config.username + "已签到！", title)
    elif res["msg"] == "对不起，您的预约未生效":
        logger.warning("预约未生效")
        send_message(config, config.username + "对不起，您的预约未生效！", title)
    else:
        logger.error("签到失败")
        send_message(config, config.username + "签到失败！", title)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="图书馆签到脚本")
    parser.add_argument("-c", "--config", help="指定配置文件路径，默认为 config.yml")
    args = parser.parse_args()

    try:
        config = AppConfig.from_yaml(args.config)
        token_mgr = TokenManager(config.username, config.password)
        lib_rsv(config, token_mgr)
    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")

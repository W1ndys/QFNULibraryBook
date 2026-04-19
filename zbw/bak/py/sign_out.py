import asyncio
import datetime
import logging
import os
import random
import sys
import time

import requests
import yaml
from telegram import Bot

from get_bearer_token import get_bearer_token
from get_info import (
    get_member_seat,
)

import json
import base64
import hmac
import hashlib
import urllib.parse


# 配置日志
logger = logging.getLogger("httpx")
logger.setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

URL_GET_SEAT = "http://libyy.qfnu.edu.cn/api/Seat/confirm"
URL_CHECK_OUT = "http://libyy.qfnu.edu.cn/api/Space/checkout"
URL_CANCEL_SEAT = "http://libyy.qfnu.edu.cn/api/Space/cancel"

# 配置文件
CHANNEL_ID = ""
TELEGRAM_BOT_TOKEN = ""
USERNAME = ""
PASSWORD = ""
GITHUB = ""
BARK_URL = ""
BARK_EXTRA = ""
ANPUSH_TOKEN = ""
ANPUSH_CHANNEL = ""
DD_BOT_SECRET = ""
DD_BOT_TOKEN = ""
PUSH_METHOD = ""


# 读取YAML配置文件并设置全局变量
def read_config_from_yaml():
    global CHANNEL_ID, TELEGRAM_BOT_TOKEN, CLASSROOMS_NAME, SEAT_ID, DATE, USERNAME, PASSWORD, GITHUB, BARK_EXTRA, BARK_URL, ANPUSH_TOKEN, ANPUSH_CHANNEL, PUSH_METHOD, DD_BOT_TOKEN, DD_BOT_SECRET
    current_dir = os.path.dirname(
        os.path.abspath(__file__)
    )  # 获取当前文件所在的目录的绝对路径
    config_file_path = os.path.join(
        current_dir, "config.yml"
    )  # 将文件名与目录路径拼接起来
    with open(
        config_file_path, "r", encoding="utf-8"
    ) as yaml_file:  # 指定为UTF-8格式打开文件
        config = yaml.safe_load(yaml_file)
        CHANNEL_ID = config.get("CHANNEL_ID", "")
        TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN", "")
        CLASSROOMS_NAME = config.get(
            "CLASSROOMS_NAME", []
        )  # 将 CLASSROOMS_NAME 读取为列表
        SEAT_ID = config.get("SEAT_ID", [])  # 将 SEAT_ID 读取为列表
        DATE = config.get("DATE", "")
        USERNAME = config.get("USERNAME", "")
        PASSWORD = config.get("PASSWORD", "")
        GITHUB = config.get("GITHUB", "")
        BARK_URL = config.get("BARK_URL", "")
        BARK_EXTRA = config.get("BARK_EXTRA", "")
        ANPUSH_TOKEN = config.get("ANPUSH_TOKEN", "")
        ANPUSH_CHANNEL = config.get("ANPUSH_CHANNEL", "")
        DD_BOT_TOKEN = config.get("DD_BOT_TOKEN", "")
        DD_BOT_SECRET = config.get("DD_BOT_SECRET", "")
        PUSH_METHOD = config.get("PUSH_METHOD", "")


# 在代码的顶部定义全局变量
MESSAGE = ""
AUTH_TOKEN = ""
TOKEN_TIMESTAMP = None
TOKEN_EXPIRY_DELTA = datetime.timedelta(hours=1, minutes=30)


# 打印变量
def print_variables():
    variables = {
        "CHANNEL_ID": CHANNEL_ID,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "CLASSROOMS_NAME": CLASSROOMS_NAME,
        "SEAT_ID": SEAT_ID,
        "USERNAME": USERNAME,
        "PASSWORD": PASSWORD,
        "GITHUB": GITHUB,
        "BARK_URL": BARK_URL,
        "BARK_EXTRA": BARK_EXTRA,
        "ANPUSH_TOKEN": ANPUSH_TOKEN,
        "ANPUSH_CHANNEL": ANPUSH_CHANNEL,
        "PUSH_METHOD": PUSH_METHOD,
    }
    for var_name, var_value in variables.items():
        logger.info(f"{var_name}: {var_value} - {type(var_value)}")


# post 请求
def send_post_request_and_save_response(url, data, headers):
    global MESSAGE
    retries = 0
    while retries < 20:
        try:
            response = requests.post(url, json=data, headers=headers, timeout=120)
            response.raise_for_status()
            response_data = response.json()
            return response_data
        except requests.exceptions.Timeout:
            logger.error("请求超时，正在重试...")
            retries += 1
        except Exception as e:
            logger.error(f"request请求异常: {str(e)}")
            retries += 1
    logger.error("超过最大重试次数,请求失败。")
    MESSAGE += "\n超过最大重试次数,请求失败。"
    send_message()
    sys.exit()


def send_message():
    if PUSH_METHOD == "TG":
        asyncio.run(send_message_telegram())
    if PUSH_METHOD == "ANPUSH":
        send_message_anpush()
    if PUSH_METHOD == "BARK":
        send_message_bark()
    if PUSH_METHOD == "DD":
        dingtalk("图书馆签退通知", MESSAGE, DD_BOT_TOKEN, DD_BOT_SECRET)


# 推送到钉钉
def dingtalk(text, desp, DD_BOT_TOKEN, DD_BOT_SECRET=None):
    url = f"https://oapi.dingtalk.com/robot/send?access_token={DD_BOT_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {"msgtype": "text", "text": {"content": f"{text}\n{desp}"}}
    if DD_BOT_TOKEN and DD_BOT_SECRET:
        timestamp = str(round(time.time() * 1000))
        secret_enc = DD_BOT_SECRET.encode("utf-8")
        string_to_sign = f"{timestamp}\n{DD_BOT_SECRET}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(
            secret_enc, string_to_sign_enc, digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(
            base64.b64encode(hmac_code).decode("utf-8").strip()
        )
        url = f"{url}&timestamp={timestamp}&sign={sign}"

    response = requests.post(url, headers=headers, data=json.dumps(payload))

    try:
        data = response.json()
        if response.status_code == 200 and data.get("errcode") == 0:
            logger.info("钉钉发送通知消息成功🎉")
        else:
            logger.error(f"钉钉发送通知消息失败😞\n{data.get('errmsg')}")
    except Exception as e:
        logger.error(f"钉钉发送通知消息失败😞\n{e}")

    return response.json()


# 推送到 Bark
def send_message_bark():
    try:
        response = requests.get(BARK_URL + MESSAGE + BARK_EXTRA)
        # 检查响应状态码是否为200
        if response.status_code == 200:
            logger.info("成功推送消息到 Bark")
            # 返回响应内容
            return response.text
        else:
            logger.error(f"推送到 Bark 的 GET请求失败，状态码：{response.status_code}")
            return None
    except requests.exceptions.RequestException:
        logger.info("GET请求异常, 你的 BARK 链接不正确")
        return None


def send_message_anpush():
    url = "https://api.anpush.com/push/" + ANPUSH_TOKEN
    payload = {"title": "预约通知", "content": MESSAGE, "channel": ANPUSH_CHANNEL}

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    requests.post(url, headers=headers, data=payload)
    # logger.info(response.text)


async def send_message_telegram():
    try:
        # 使用 API 令牌初始化您的机器人
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        # logger.info(f"要发送的消息为： {MESSAGE}\n")
        await bot.send_message(chat_id=CHANNEL_ID, text=MESSAGE)
        logger.info("成功推送消息到 Telegram")
    except Exception as e:
        logger.info(
            f"发送消息到 Telegram 失败, 可能是没有设置此通知方式，也可能是没有连接到 Telegram"
        )
        return e


def get_auth_token():
    global TOKEN_TIMESTAMP, AUTH_TOKEN
    try:
        # 如果未从配置文件中读取到用户名或密码，则抛出异常
        if not USERNAME or not PASSWORD:
            raise ValueError("未找到用户名或密码")

        # 检查 Token 是否过期
        if (
            TOKEN_TIMESTAMP is None
            or (datetime.datetime.now() - TOKEN_TIMESTAMP) > TOKEN_EXPIRY_DELTA
        ):
            # Token 过期或尚未获取，重新获取
            name, token = get_bearer_token(USERNAME, PASSWORD)
            logger.info(f"成功获取授权码")
            AUTH_TOKEN = "bearer" + str(token)
            # 更新 Token 的时间戳
            TOKEN_TIMESTAMP = datetime.datetime.now()
        else:
            logger.info("使用现有授权码")
    except Exception as e:
        logger.error(f"获取授权码时发生异常: {str(e)}")
        sys.exit()


def go_home():
    global MESSAGE
    try:
        get_auth_token()
        res = get_member_seat(AUTH_TOKEN)
        # logger.info(res)
        if res is not None:
            seat_id = None  # 初始化为None
            for item in res["data"]["data"]:
                if item["statusName"] == "使用中":
                    seat_id = item["id"]  # 找到使用中的座位
                    # logger.info("test")
                    # logger.info(seat_id)
                    break  # 找到座位后退出循环

            if seat_id is not None:  # 确保 seat_id 不为空
                post_data = {"id": seat_id, "authorization": AUTH_TOKEN}
                request_headers = {
                    "Content-Type": "application/json",
                    "Connection": "keep-alive",
                    "Accept": "application/json, text/plain, */*",
                    "lang": "zh",
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
                    "like Gecko)"
                    "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
                    "Origin": "http://libyy.qfnu.edu.cn",
                    "Referer": "http://libyy.qfnu.edu.cn/h5/index.html",
                    "Accept-Encoding": "gzip, deflate",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5",
                    "Authorization": AUTH_TOKEN,
                }
                res = send_post_request_and_save_response(
                    URL_CHECK_OUT, post_data, request_headers
                )
                if "msg" in res:
                    status = res["msg"]
                    logger.info("签退状态：" + status)
                    if status == "完全离开操作成功":
                        MESSAGE += "\n签退成功"
                        send_message()
                        sys.exit()
                    else:
                        logger.info("已经签退")
            else:
                logger.error("没有找到正在使用的座位，今天你可能没有预约座位")
                MESSAGE += "\n没有找到正在使用的座位，今天你可能没有预约座位"
                send_message()
                sys.exit()
        else:
            logger.error("获取数据失败，请检查登录状态")
            sys.exit()

    except KeyError:
        logger.error("返回数据与规则不符，大概率是没有登录")


if __name__ == "__main__":
    try:
        read_config_from_yaml()
        go_home()
    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")

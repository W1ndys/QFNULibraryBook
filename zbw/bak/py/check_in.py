import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timedelta

import requests
import yaml
from telegram import Bot

import json
import base64
import hmac
import hashlib
import urllib.parse

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


session = requests.session()

from get_bearer_token import get_bearer_token


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
MODE = ""
CLASSROOMS_NAME = ""
SEAT_ID = ""
DATE = ""
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
    global CHANNEL_ID, TELEGRAM_BOT_TOKEN, CLASSROOMS_NAME, MODE, SEAT_ID, DATE, USERNAME, PASSWORD, GITHUB, BARK_EXTRA, BARK_URL, ANPUSH_TOKEN, ANPUSH_CHANNEL, PUSH_METHOD, DD_BOT_TOKEN, DD_BOT_SECRET
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
        MODE = config.get("MODE", "")
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
TOKEN_EXPIRY_DELTA = timedelta(hours=1, minutes=30)


# 打印变量
# 好像是师哥测试数据的函数，暂时保留
def print_variables():
    variables = {
        "CHANNEL_ID": CHANNEL_ID,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "MODE": MODE,
        "CLASSROOMS_NAME": CLASSROOMS_NAME,
        "SEAT_ID": SEAT_ID,
        "USERNAME": USERNAME,
        "PASSWORD": PASSWORD,
        "GITHUB": GITHUB,
        "BARK_URL": BARK_URL,
        "BARK_EXTRA": BARK_EXTRA,
        "ANPUSH_TOKEN": ANPUSH_TOKEN,
        "ANPUSH_CHANNEL": ANPUSH_CHANNEL,
        "DD_BOT_TOKEN": DD_BOT_TOKEN,
        "DD_BOT_SECRET": DD_BOT_SECRET,
        "PUSH_METHOD": PUSH_METHOD,
    }
    for var_name, var_value in variables.items():
        logger.info(f"{var_name}: {var_value} - {type(var_value)}")


def send_message():
    if PUSH_METHOD == "TG":
        asyncio.run(send_message_telegram())
    if PUSH_METHOD == "ANPUSH":
        send_message_anpush()
    if PUSH_METHOD == "BARK":
        send_message_bark()
    if PUSH_METHOD == "DD":
        dingtalk("图书馆签到通知", MESSAGE, DD_BOT_TOKEN, DD_BOT_SECRET)


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


# 推送到 AnPush
def send_message_anpush():
    url = "https://api.anpush.com/push/" + ANPUSH_TOKEN
    payload = {"title": "预约通知", "content": MESSAGE, "channel": ANPUSH_CHANNEL}

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    requests.post(url, headers=headers, data=payload)
    # logger.info(response.text)


# 推送到 Telegram
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


# 获取授权码
def get_auth_token():
    global TOKEN_TIMESTAMP, AUTH_TOKEN
    try:
        # 如果未从配置文件中读取到用户名或密码，则抛出异常
        if not USERNAME or not PASSWORD:
            raise ValueError("未找到用户名或密码")

        # 检查 Token 是否过期
        if (
            TOKEN_TIMESTAMP is None
            or (datetime.now() - TOKEN_TIMESTAMP) > TOKEN_EXPIRY_DELTA
        ):
            # Token 过期或尚未获取，重新获取
            name, token = get_bearer_token(USERNAME, PASSWORD)
            logger.info("成功获取授权码")
            AUTH_TOKEN = "bearer" + str(token)
            # 更新 Token 的时间戳
            TOKEN_TIMESTAMP = datetime.now()
        else:
            logger.info("使用现有授权码")
    except Exception as e:
        logger.error(f"获取授权码时发生异常: {str(e)}")
        sys.exit()


# AES加密
def aes_encrypt():
    json_data = '{"method":"checkin"}'
    aes_key = datetime.now().strftime("%Y%m%d")
    aes_key = aes_key + aes_key[::-1]
    aes_iv = "ZZWBKJ_ZHIHUAWEI"
    cipher = Cipher(
        algorithms.AES(aes_key.encode("utf-8")),
        modes.CBC(aes_iv.encode("utf-8")),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(json_data.encode("utf-8")) + padder.finalize()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode()


# 签到请求函数
def lib_rsv(bearer_token, user_name):
    global MESSAGE
    sub_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
                        Chrome/117.0.5938.63 Safari/537.36",
        "Content-Type": "application/json",
        "authorization": bearer_token,
    }
    sub_data = {"aesjson": aes_encrypt(), "authorization": bearer_token}
    res = session.post(
        url="http://libyy.qfnu.edu.cn/api/Seat/touch_qr_books",
        headers=sub_headers,
        data=json.dumps(sub_data),
    )
    res = json.loads(res.text)
    print(res)
    if res["msg"] == "签到成功":
        # requests.get(url="" + user_name + "签到成功")
        logger.info("签到成功")
        MESSAGE = user_name + "签到成功！"
        send_message()
    elif res["msg"] == "使用中,不用重复签到！":
        # requests.get(url="" + user_name + "已签到")
        logger.info("已签到")
        MESSAGE = user_name + "已签到！"
        send_message()
    elif res["msg"] == "对不起，您的预约未生效":
        logger.warning("预约未生效")
        MESSAGE = user_name + "对不起，您的预约未生效！"
        send_message()
    else:
        # requests.get(url="" + user_name + "签到失败")
        logger.error("签到失败")
        MESSAGE = user_name + "签到失败！"
        send_message()


if __name__ == "__main__":
    try:
        read_config_from_yaml()
        get_auth_token()
        lib_rsv(AUTH_TOKEN, USERNAME)

    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")

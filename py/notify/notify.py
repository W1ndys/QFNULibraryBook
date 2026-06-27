"""
统一消息推送模块
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse

import requests
from telegram import Bot

logger = logging.getLogger(__name__)


def send_message(config, message: str, title: str):
    """
    统一消息推送入口。

    参数:
        config: AppConfig 配置实例
        message: 推送消息内容
        title: 推送标题（所有后端统一使用）
    """
    method = config.push_method
    if method == "TG":
        asyncio.run(_send_telegram(config, message))
    elif method == "ANPUSH":
        _send_anpush(config, message, title)
    elif method == "BARK":
        _send_bark(config, message, title)
    elif method == "DD":
        _dingtalk(title, message, config.dd_bot_token, config.dd_bot_secret)
    elif method:
        logger.warning(f"未知的推送方式: {method}")


def _dingtalk(text, desp, dd_bot_token, dd_bot_secret=None):
    """推送到钉钉"""
    url = f"https://oapi.dingtalk.com/robot/send?access_token={dd_bot_token}"
    headers = {"Content-Type": "application/json"}
    payload = {"msgtype": "text", "text": {"content": f"{text}\n{desp}"}}

    if dd_bot_token and dd_bot_secret:
        timestamp = str(round(time.time() * 1000))
        secret_enc = dd_bot_secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{dd_bot_secret}"
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


def _send_bark(config, message, title):
    """推送到 Bark"""
    try:
        # Bark 推送格式: URL + 标题 + "/" + 消息 + 额外参数
        url = f"{config.bark_url}{title}/{message}{config.bark_extra}"
        response = requests.get(url)
        if response.status_code == 200:
            logger.info("成功推送消息到 Bark")
            return response.text
        else:
            logger.error(f"推送到 Bark 失败，状态码：{response.status_code}")
            return None
    except requests.exceptions.RequestException:
        logger.info("GET 请求异常, 你的 BARK 链接不正确")
        return None


def _send_anpush(config, message, title):
    """推送到 AnPush"""
    url = f"https://api.anpush.com/push/{config.anpush_token}"
    payload = {"title": title, "content": message, "channel": config.anpush_channel}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    requests.post(url, headers=headers, data=payload)


async def _send_telegram(config, message):
    """推送到 Telegram"""
    try:
        bot = Bot(token=config.telegram_bot_token)
        await bot.send_message(chat_id=config.channel_id, text=message)
        logger.info("成功推送消息到 Telegram")
    except Exception as e:
        logger.info(
            f"发送消息到 Telegram 失败, 可能是没有设置此通知方式，也可能是没有连接到 Telegram: {e}"
        )

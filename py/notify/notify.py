"""
统一消息推送模块
"""
import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger(__name__)

# tenacity 重试配置：仅对网络/超时异常重试，不重试业务错误
_notify_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    reraise=True,
    retry=retry_if_exception_type(
        (requests.exceptions.RequestException, ConnectionError, TimeoutError)
    ),
)


def _check_push_config(config) -> bool:
    """检查推送配置是否完整（根据 push_method 校验对应渠道的必填字段）"""
    method = config.push_method
    if method == "TG":
        return bool(config.telegram_bot_token and config.channel_id)
    elif method == "DD":
        return bool(config.dd_bot_token)
    elif method == "BARK":
        return bool(config.bark_url)
    elif method == "ANPUSH":
        return bool(config.anpush_token)
    return False


def send_message(config, message: str, title: str) -> bool:
    """
    统一消息推送入口。

    参数:
        config: AppConfig 配置实例
        message: 推送消息内容
        title: 推送标题（所有后端统一使用）

    返回:
        True 表示发送成功（或配置为空），False 表示发送失败
    """
    method = config.push_method
    if not method:
        return False

    # 校验推送方式是否有效
    known_methods = ("TG", "DD", "BARK", "ANPUSH")
    if method not in known_methods:
        logger.warning(f"未知的推送方式: {method}")
        return False

    # 校验配置完整性
    if not _check_push_config(config):
        logger.warning(f"推送方式 {method} 配置不完整，跳过推送")
        return False

    # 分发推送（内层 _send_* 已含 tenacity 重试，外层兜底捕获未预期的异常）
    try:
        if method == "TG":
            return _send_telegram(config, message)
        elif method == "ANPUSH":
            return _send_anpush(config, message, title)
        elif method == "BARK":
            return _send_bark(config, message, title)
        elif method == "DD":
            return _dingtalk(title, message, config.dd_bot_token, config.dd_bot_secret)
        else:
            logger.warning(f"未知的推送方式: {method}")
            return False
    except Exception as e:
        logger.error(f"推送失败（{method}）: {e}")
        return False


@_notify_retry
def _dingtalk(text, desp, dd_bot_token, dd_bot_secret=None) -> bool:
    """推送到钉钉（HMAC-SHA256 签名），成功返回 True"""
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

    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)

    try:
        data = response.json()
        if response.status_code == 200 and data.get("errcode") == 0:
            logger.info("钉钉发送通知消息成功🎉")
            return True
        else:
            logger.error(f"钉钉发送通知消息失败😞\n{data.get('errmsg')}")
            return False
    except Exception as e:
        logger.error(f"钉钉发送通知消息失败😞\n{e}")
        return False


@_notify_retry
def _send_bark(config, message, title) -> bool:
    """推送到 Bark，成功返回 True"""
    url = f"{config.bark_url}{title}/{message}{config.bark_extra}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        logger.info("成功推送消息到 Bark")
        return True
    else:
        logger.error(f"推送到 Bark 失败，状态码：{response.status_code}")
        return False


@_notify_retry
def _send_anpush(config, message, title) -> bool:
    """推送到 AnPush，成功返回 True"""
    url = f"https://api.anpush.com/push/{config.anpush_token}"
    payload = {"title": title, "content": message, "channel": config.anpush_channel}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, headers=headers, data=payload, timeout=10)

    if response.status_code == 200:
        logger.info("成功推送消息到 AnPush")
        return True
    else:
        logger.error(f"推送到 AnPush 失败，状态码：{response.status_code}")
        return False


@_notify_retry
def _send_telegram(config, message) -> bool:
    """
    推送到 Telegram（基于 HTTP API，无需 python-telegram-bot）。
    使用 requests.post() 直接调用 Bot API，避免 asyncio.run() 的嵌套事件循环风险。
    """
    try:
        url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
        payload = {"chat_id": config.channel_id, "text": message}
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("成功推送消息到 Telegram")
            return True
        else:
            logger.error(f"推送到 Telegram 失败，状态码：{response.status_code}")
            return False
    except Exception as e:
        logger.error(f"发送消息到 Telegram 失败: {e}")
        return False
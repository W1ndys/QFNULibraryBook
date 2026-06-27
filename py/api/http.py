"""
统一 HTTP 请求工具
"""
import logging
import time

import requests

logger = logging.getLogger(__name__)


class RequestFailed(Exception):
    """POST 请求在最大重试次数后仍然失败"""
    pass


def post_with_retry(url, data, headers, max_retries=100, retry_delay=0, timeout=120):
    """
    带重试的 POST 请求。

    参数:
        url: 请求 URL
        data: JSON 请求体（字典）
        headers: 请求头
        max_retries: 最大重试次数
        retry_delay: 重试间隔秒数
        timeout: 请求超时秒数

    返回:
        解析后的 JSON 响应（字典）

    异常:
        RequestFailed: 超过最大重试次数
    """
    retries = 0
    while retries < max_retries:
        try:
            response = requests.post(url, json=data, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error("请求超时，正在重试...")
            retries += 1
            if retry_delay > 0:
                time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"请求异常: {e}")
            retries += 1
            if retry_delay > 0:
                time.sleep(retry_delay)

    raise RequestFailed(f"超过最大重试次数 ({max_retries})，请求失败: {url}")

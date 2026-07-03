"""
统一 HTTP 请求工具（带重试）
"""
import logging
import random
import time

import requests

from api.exceptions import RequestFailed

logger = logging.getLogger(__name__)


def post_with_retry(url, data, headers, max_retries=10, retry_delay=1,
                    timeout=15, total_timeout=120, session=None):
    """
    带重试的 POST 请求。

    参数:
        url: 请求 URL
        data: JSON 请求体（字典）
        headers: 请求头
        max_retries: 最大重试次数（默认 10）
        retry_delay: 重试基础间隔秒数（默认 1s，会加上 0~0.5s 的随机抖动）
        timeout: 单次请求超时秒数（默认 15s）
        total_timeout: 整个重试过程的总超时秒数（默认 120s，到达后放弃）
        session: 可选的 requests.Session 实例，用于连接复用

    返回:
        解析后的 JSON 响应（字典）

    异常:
        RequestFailed: 超过最大重试次数或总超时
    """
    start_time = time.time()

    for retries in range(max_retries):
        # 检查总超时
        elapsed = time.time() - start_time
        if total_timeout > 0 and elapsed >= total_timeout:
            raise RequestFailed(
                f"总超时 {total_timeout}s (已用时 {elapsed:.1f}s)，放弃请求: {url}"
            )

        try:
            http = session.post if session else requests.post
            response = http(url, json=data, headers=headers, timeout=timeout)

            # raise_for_status 将 4xx/5xx 转为 HTTPError
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"请求超时 ({timeout}s)，正在重试 ({retries+1}/{max_retries})...")
        except requests.exceptions.HTTPError as e:
            # 4xx 客户端错误：快速失败，不重试
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise RequestFailed(
                    f"HTTP {e.response.status_code} (4xx)，请求被拒绝: {url}"
                ) from e
            # 5xx 服务端错误或无响应体：继续重试
            status = e.response.status_code if e.response is not None else "N/A"
            logger.error(f"HTTP 错误 ({status})，正在重试 ({retries+1}/{max_retries})...")
        except RequestFailed:
            # 已确认的失败，直接抛出
            raise
        except Exception as e:
            logger.error(f"请求异常 ({retries+1}/{max_retries}): {e}")

        # 随机抖动：避免多线程同时重试撞车
        jitter = random.uniform(0, 0.5)
        time.sleep(retry_delay + jitter)

    raise RequestFailed(f"超过最大重试次数 ({max_retries})，请求失败: {url}")
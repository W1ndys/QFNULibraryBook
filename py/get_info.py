"""
座位查询工具模块
提供日期解析、教室段查询、座位信息获取、用户座位查询等功能。
"""
import logging
import sys
from datetime import datetime, timedelta

import requests

from classrooms import classroom_id_mapping
from api.constants import (
    URL_CLASSROOM_DETAIL_INFO,
    URL_CLASSROOM_SEAT,
    URL_CHECK_STATUS,
    DEFAULT_HEADERS,
)
from api.http import post_with_retry, RequestFailed
from crypto.aes import encrypt_seat_data, decrypt_seat_data

logger = logging.getLogger(__name__)


def get_date(date):
    """获取预约日期字符串（YYYY-MM-DD 格式）"""
    try:
        if date == "today":
            nowday = datetime.now().date()
        elif date == "tomorrow":
            nowday = datetime.now().date() + timedelta(days=1)
        else:
            logger.error(f"未知的参数: {date}")
            sys.exit()

        if nowday:
            return nowday.strftime("%Y-%m-%d")
        else:
            logger.error("日期获取失败")
            sys.exit()
    except Exception as e:
        logger.error(f"获取日期异常: {e}")
        sys.exit()


def get_build_id(classname):
    """根据教室名称获取系统 ID"""
    logger.info(f"教室名称: {classname}")
    build_id = classroom_id_mapping.get(classname)
    return build_id


def get_segment(build_id, nowday):
    """获取指定教室和日期的时间段 ID"""
    try:
        post_data = {"build_id": build_id}
        res = post_with_retry(
            URL_CLASSROOM_DETAIL_INFO, post_data, DEFAULT_HEADERS,
            max_retries=10, retry_delay=1, timeout=15
        )
        segment = None
        for item in res["data"]:
            if item["day"] == nowday:
                segment = item["times"][0]["id"]
                break
        return segment
    except RequestFailed:
        logger.error("获取segment失败，超过最大重试次数")
        sys.exit()
    except Exception as e:
        logger.error(f"获取segment时出错: {e}")
        sys.exit()


def get_member_seat(auth):
    """查询当前用户的座位信息"""
    try:
        post_data = {"page": 1, "limit": 3, "authorization": auth}
        request_headers = {**DEFAULT_HEADERS, "Authorization": auth}
        res = post_with_retry(
            URL_CHECK_STATUS, post_data, request_headers,
            max_retries=10, retry_delay=1, timeout=15
        )
        return res
    except RequestFailed:
        logger.error("获取用户座位信息失败")
        return None
    except KeyError:
        logger.error("数据获取失败, Token 失效，重新获取")
        return None


def get_seat_info(build_id, segment, nowday):
    """获取指定教室的空闲座位列表"""
    post_data = {
        "area": build_id,
        "segment": segment,
        "day": nowday,
        "startTime": "08:00",
        "endTime": "22:00",
    }
    res = post_with_retry(
        URL_CLASSROOM_SEAT, post_data, DEFAULT_HEADERS,
        max_retries=10, retry_delay=1, timeout=15
    )
    free_seats = []
    for seat in res["data"]:
        if seat["status_name"] == "空闲":
            free_seats.append({"id": seat["id"], "no": seat["no"]})
    return free_seats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("get_info 模块加载成功")

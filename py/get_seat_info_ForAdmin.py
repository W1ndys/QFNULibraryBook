"""
管理员工具：抓取教室座位信息并保存为 JSON 文件
用法: python get_seat_info_ForAdmin.py [-c configs/template.yml]
"""
import argparse
import json
import logging
import sys

import requests

from config.config import AppConfig
from classrooms import classroom_id_mapping
from api.constants import (
    URL_CLASSROOM_DETAIL_INFO,
    URL_CLASSROOM_SEAT,
    DEFAULT_HEADERS,
)
from api.http import post_with_retry, RequestFailed
from get_info import get_date, get_build_id, get_segment

logger = logging.getLogger(__name__)


def get_seat_info(build_id, segment, nowday, save_file=None):
    """获取座位信息，可选保存为 JSON 文件"""
    try:
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

        # 保存为 JSON 文件
        if save_file:
            with open(save_file, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=4)
            logger.info(f"座位信息已保存到 {save_file}")

        free_seats = []
        for seat in res["data"]:
            if seat["status_name"] == "空闲":
                free_seats.append({"id": seat["id"], "no": seat["no"]})

        return free_seats

    except requests.exceptions.Timeout:
        logger.warning("请求超时")
    except RequestFailed:
        logger.error("获取座位信息失败，超过最大重试次数")
    except Exception as e:
        logger.error(f"获取座位信息异常: {e}")

    return None


def get_info_and_select_seat(config: AppConfig):
    """抓取座位信息主函数"""
    try:
        nowday = get_date(config.date)
        logger.info(f"预约日期: {nowday}")

        for classroom_name in config.classrooms_name:
            build_id = get_build_id(classroom_name)
            if build_id is None:
                logger.error(f"未找到教室: {classroom_name}")
                continue

            logger.info(f"正在获取 {classroom_name} (ID: {build_id}) 的座位信息...")
            segment = get_segment(build_id, nowday)
            if segment is None:
                logger.error(f"未获取到 {classroom_name} 的时间段")
                continue

            logger.info(f"时间段 ID: {segment}")

            # 保存为 JSON 文件（文件名使用教室名称）
            save_file = f"{classroom_name}.json"
            data = get_seat_info(build_id, segment, nowday, save_file=save_file)

            if data:
                logger.info(f"{classroom_name}: {len(data)} 个空闲座位")
            else:
                logger.warning(f"{classroom_name}: 获取座位信息失败")

    except KeyboardInterrupt:
        logger.info("主动退出程序")
    except Exception as e:
        logger.error(f"执行异常: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="管理员工具：抓取教室座位信息")
    parser.add_argument("-c", "--config", help="指定配置文件路径，默认为 configs/template.yml")
    parser.add_argument("--classrooms", nargs="+", help="指定教室名称列表，覆盖配置文件")
    parser.add_argument("--date", choices=["today", "tomorrow"], help="指定日期，覆盖配置文件")
    args = parser.parse_args()

    config = AppConfig.from_yaml(args.config)

    # 命令行参数覆盖配置文件
    if args.classrooms:
        config.classrooms_name = args.classrooms
    if args.date:
        config.date = args.date

    # 默认值
    if not config.classrooms_name:
        config.classrooms_name = ["西校区图书馆-二层自习室"]
    if not config.date:
        config.date = "tomorrow"

    logger.info(f"教室列表: {config.classrooms_name}")
    logger.info(f"预约日期: {config.date}")

    get_info_and_select_seat(config)

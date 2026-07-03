"""
图书馆座位预约脚本
用法: python get_seat.py [-c configs/studentA.yml]
"""
import argparse
import logging
import random

from config.config import AppConfig
from auth.token import TokenManager, AuthenticationError
from notify.notify import send_message
from api.constants import URL_GET_SEAT, DEFAULT_HEADERS
from api.http import post_with_retry, RequestFailed
from api.exceptions import ReservationFailed
from crypto.aes import encrypt_seat_data
from classrooms import classroom_id_mapping, EXCLUDE_ID
from get_info import get_date, get_seat_info, get_segment, get_build_id, get_member_seat

logger = logging.getLogger(__name__)


def check_book_seat(config, token_mgr, messages, auth_token):
    """检查是否存在已预约的座位，返回 True 表示已有座位"""
    try:
        res = get_member_seat(auth_token)
        if res is not None and "msg" in res and res["msg"] == "您尚未登录":
            auth_token = token_mgr.get_token()
        if res is not None and "data" in res:
            for entry in res["data"]["data"]:
                if entry["statusName"] == "预约成功":
                    seat_id = entry["name"]
                    name = entry["nameMerge"]
                    logger.info(f"预约成功：你当前的座位是 {name} {seat_id}")
                    messages.append(f"\n预约成功：你当前的座位是 {name} {seat_id}\n")
                    return True
                elif entry["statusName"] == "使用中" and config.date == "today":
                    logger.info("存在正在使用的座位")
                    return True
    except KeyError:
        logger.error("获取个人座位出现错误")
    return False


def check_reservation_status(seat_result, config, token_mgr, messages):
    """
    状态检测函数。
    返回: True 表示已完成（成功/失败），False 表示需继续尝试
    """
    if isinstance(seat_result, dict) and "msg" in seat_result:
        status = seat_result["msg"]
        if status is not None:
            if status == "当前用户在该时段已存在座位预约，不可重复预约":
                logger.info("重复预约, 请检查选择的时间段或是否已经预约成功")
                check_book_seat(config, token_mgr, messages, token_mgr.get_token())
                return True
            elif status == "预约成功":
                logger.info("预约成功")
                check_book_seat(config, token_mgr, messages, token_mgr.get_token())
                return True
            elif status == "开放预约时间19:20":
                logger.info("未到预约时间")
            elif status == "您尚未登录":
                logger.info("没有登录，将重新尝试获取 token")
                token_mgr.get_token()
            elif status == "该空间当前状态不可预约":
                logger.info("此位置已被预约或位置不可用")
            elif status == "取消成功":
                logger.info("取消成功")
                return True
            else:
                logger.info(f"未知状态信息: {status}")
                return True
        else:
            logger.info(seat_result)
    else:
        logger.error("未能获取有效的座位预约状态，token已失效，请不要在脚本执行过程中手动登录")
        messages.append("\n未能获取有效的座位预约状态，token已失效")
        title = f"脚本执行通知 - 学号: {config.username}"
        send_message(config, "\n".join(messages), title)
        raise ReservationFailed("Token已失效，预约失败")
    return False


def post_to_get_seat(select_id, segment, config, token_mgr, messages):
    """发送预约请求"""
    auth_token = token_mgr.get_token()
    origin_data = '{{"seat_id":"{}","segment":"{}"}}'.format(select_id, segment)
    aes_data = encrypt_seat_data(str(origin_data))

    post_data = {"aesjson": aes_data}
    request_headers = {**DEFAULT_HEADERS, "Authorization": auth_token}

    try:
        seat_result = post_with_retry(URL_GET_SEAT, post_data, request_headers,
                                     max_retries=10, retry_delay=1, timeout=15)
    except RequestFailed:
        messages.append("\n超过最大重试次数,请求失败。")
        title = f"脚本执行通知 - 学号: {config.username}"
        send_message(config, "\n".join(messages), title)
        raise ReservationFailed("超过最大重试次数,请求失败。")

    return check_reservation_status(seat_result, config, token_mgr, messages)


def random_get_seat(data):
    """从座位列表中随机选一个"""
    random_dict = random.choice(data)
    return random_dict["id"]


def select_seat(build_id, segment, nowday, config, token_mgr, messages):
    """选座主逻辑"""
    flag = False
    retries = 0

    while not flag and retries < 100:
        logger.info(f"开始第 {retries + 1} 次尝试获取座位")
        retries += 1

        data = get_seat_info(build_id, segment, nowday)

        if not data:
            logger.warning("获取座位信息失败，可能是时间段内不存在或该区域暂不可用")
            # 反向查找教室名称
            classname = build_id
            for key, value in classroom_id_mapping.items():
                if value == build_id:
                    classname = key
                    break
            messages.append(f"\n[{classname}]: 获取座位信息失败")
            break

        if config.mode == "1":
            # 模式 1: 指定范围内有插座的位置
            seat_id_range = []
            for ran in config.seat_id:
                seat_id_range.extend(list(map(str, list(range(ran[0], ran[1] + 1)))))
            new_data = [d for d in data if (d["id"] not in EXCLUDE_ID) and (d["id"] in seat_id_range)]
            if new_data:
                select_id = random_get_seat(new_data)
                logger.info(f"随机选择的座位为: {select_id}")
                if post_to_get_seat(select_id, segment, config, token_mgr, messages):
                    flag = True
            continue

        elif config.mode == "2":
            # 模式 2: 有插座的位置
            new_data = [d for d in data if d["id"] not in EXCLUDE_ID]
            if new_data:
                select_id = random_get_seat(new_data)
                logger.info(f"随机选择的座位为: {select_id}")
                if post_to_get_seat(select_id, segment, config, token_mgr, messages):
                    flag = True
            continue

        elif config.mode == "3":
            # 模式 3: 随机选择
            select_id = random_get_seat(data)
            logger.info(f"随机选择的座位为: {select_id}")
            if post_to_get_seat(select_id, segment, config, token_mgr, messages):
                flag = True
            continue

        elif config.mode == "4":
            # 模式 4: 东校区图书馆三层自习室指定座位优先
            if build_id != 22:
                logger.info("模式4只适用于东校区图书馆三层自习室，跳过当前教室")
                continue

            if data:
                logger.info(f"调试: 实际返回的前5个座位: {data[:5]}")

            # 从配置文件 SEAT_ID 读取目标座位号，第一个为优先选择
            target_seats_raw = config.seat_id
            target_seats_flat = []
            for item in target_seats_raw:
                if isinstance(item, list):
                    target_seats_flat.extend(item)
                else:
                    target_seats_flat.append(item)
            target_seats = [str(s) for s in target_seats_flat]
            priority_seats = target_seats[:1] if target_seats else []

            available_target_seats = []
            for seat in data:
                seat_no = seat["no"].lstrip("0") or "0"
                if seat_no in target_seats:
                    available_target_seats.append(seat)

            logger.info(
                f"调试: 可用座位数量: {len(data)}, 符合条件的座位数量: {len(available_target_seats)}"
            )
            if available_target_seats:
                logger.info(
                    f"调试: 符合条件的座位: {[(s['id'], s['no']) for s in available_target_seats]}"
                )

            if available_target_seats:
                priority_available = [
                    s for s in available_target_seats
                    if (s["no"].lstrip("0") or "0") in priority_seats
                ]
                if priority_available:
                    selected_seat = random.choice(priority_available)
                    select_id = selected_seat["id"]
                    logger.info(f"优先选择的座位为: {selected_seat['no']} (系统ID: {select_id})")
                else:
                    selected_seat = random.choice(available_target_seats)
                    select_id = selected_seat["id"]
                    logger.info(f"从指定座位中选择的座位为: {selected_seat['no']} (系统ID: {select_id})")
                if post_to_get_seat(select_id, segment, config, token_mgr, messages):
                    flag = True
            else:
                logger.info("指定座位列表中无可用座位，立即重试")
            continue

        else:
            logger.error(f"未知的模式: {config.mode}")
            break

    if retries >= 100:
        logger.error("超过最大重试次数,无法获取座位")
        messages.append("\n超过最大重试次数,无法获取座位")
        title = f"脚本执行通知 - 学号: {config.username}"
        send_message(config, "\n".join(messages), title)
        raise ReservationFailed("超过最大重试次数,无法获取座位")


def run_seat_reservation(config: AppConfig, token_mgr: TokenManager):
    """预约主函数"""
    messages = []
    try:
        new_date = get_date(config.date)
        auth_token = token_mgr.get_token()

        for classroom_name in config.classrooms_name:
            build_id = get_build_id(classroom_name)
            segment = get_segment(build_id, new_date)
            select_seat(build_id, segment, new_date, config, token_mgr, messages)

        # 推送最终结果
        if messages:
            title = f"脚本执行通知 - 学号: {config.username}"
            send_message(config, "\n".join(messages), title)

    except AuthenticationError as e:
        logger.error(str(e))
        messages.append(f"\n{e}")
        title = f"脚本执行通知 - 学号: {config.username}"
        send_message(config, "\n".join(messages), title)
        raise ReservationFailed(f"登录认证失败: {e}") from e
    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="图书馆座位预约脚本")
    parser.add_argument("-c", "--config", help="指定配置文件路径，默认为 configs/template.yml")
    args = parser.parse_args()

    try:
        config = AppConfig.from_yaml(args.config)
        token_mgr = TokenManager(config.username, config.password)
        run_seat_reservation(config, token_mgr)
    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")

"""
19:20 预约窗口敏感性测试脚本
============================
在 19:19:00 启动，持续测量到 19:25:00，记录 API 响应变化。
用法: python scripts/time_window_test.py -c configs/studentA.yml
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

import requests

# 添加 src/ 目录到路径，使脚本可从 scripts/ 目录独立运行
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config.config import AppConfig
from auth.token import TokenManager, AuthenticationError
from api.constants import (
    URL_CLASSROOM_DETAIL_INFO,
    URL_CLASSROOM_SEAT,
    URL_CHECK_STATUS,
    DEFAULT_HEADERS,
)
from api.http import post_with_retry
from crypto.aes import encrypt_seat_data
from classrooms import classroom_id_mapping

logger = logging.getLogger(__name__)


def timestamp_ms():
    """当前时间戳（毫秒精度）"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def test_segment(build_id, target_date):
    """测试获取时间段"""
    start = time.perf_counter()
    try:
        post_data = {"build_id": build_id}
        r = requests.post(
            URL_CLASSROOM_DETAIL_INFO, json=post_data, headers=DEFAULT_HEADERS, timeout=10
        )
        elapsed = time.perf_counter() - start
        data = r.json()

        segment = None
        for item in data.get("data", []):
            if item["day"] == target_date:
                segment = item["times"][0]["id"]
                break

        return {
            "elapsed_s": round(elapsed, 3),
            "status": r.status_code,
            "segment_found": segment is not None,
            "segment_id": segment,
            "available_dates": [item["day"] for item in data.get("data", [])],
        }
    except Exception as e:
        return {"elapsed_s": round(time.perf_counter() - start, 3), "error": str(e)}


def test_seat_list(build_id, segment, target_date):
    """测试获取座位列表"""
    start = time.perf_counter()
    try:
        post_data = {
            "area": build_id,
            "segment": segment,
            "day": target_date,
            "startTime": "08:00",
            "endTime": "22:00",
        }
        r = requests.post(
            URL_CLASSROOM_SEAT, json=post_data, headers=DEFAULT_HEADERS, timeout=10
        )
        elapsed = time.perf_counter() - start
        data = r.json()
        seats = data.get("data", [])
        free = sum(1 for s in seats if s.get("status_name") == "空闲")
        return {
            "elapsed_s": round(elapsed, 3),
            "status": r.status_code,
            "total_seats": len(seats),
            "free_seats": free,
        }
    except Exception as e:
        return {"elapsed_s": round(time.perf_counter() - start, 3), "error": str(e)}


def test_confirm_probe(auth_token, segment):
    """
    用无效座位 ID 测试 /api/Seat/confirm 的响应行为。
    注意：此请求可能被服务端记录，仅在时间窗口测试中使用。
    """
    start = time.perf_counter()
    try:
        # 使用一个明显不存在的座位 ID
        origin_data = '{{"seat_id":"9999999","segment":"{}"}}'.format(segment)
        aes_data = encrypt_seat_data(str(origin_data))
        post_data = {"aesjson": aes_data}
        request_headers = {**DEFAULT_HEADERS, "Authorization": auth_token}

        r = requests.post(
            URL_CLASSROOM_SEAT.replace("/Seat/seat", "/Seat/confirm"),
            json=post_data, headers=request_headers, timeout=10
        )
        elapsed = time.perf_counter() - start
        return {
            "elapsed_s": round(elapsed, 3),
            "status": r.status_code,
            "body": r.text[:200],
        }
    except Exception as e:
        return {"elapsed_s": round(time.perf_counter() - start, 3), "error": str(e)}


def run_time_window_test(config_file):
    """持续测试 19:20 前后的 API 响应变化"""
    config = AppConfig.from_yaml(config_file)
    results = []
    target_date = (datetime.now().date() + __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

    classroom_name = config.classrooms_name[0] if config.classrooms_name else "东校区图书馆-三楼自修区"
    build_id = classroom_id_mapping.get(classroom_name, 22)

    print(f"\n{'='*60}")
    print(f"  19:20 预约窗口敏感性测试")
    print(f"  教室: {classroom_name} (ID={build_id})")
    print(f"  目标日期: {target_date}")
    print(f"  测试内容: segment 查询 + 座位查询 + confirm 探测")
    print(f"{'='*60}")
    print(f"\n💡 提示: 请在 19:19:00 左右启动此脚本")
    print(f"   脚本将自动持续运行到 19:25:00\n")

    # 预热 token（19:19 前）
    print("[预热] 获取 Token...")
    token_mgr = TokenManager(config.username, config.password)
    try:
        auth_token = token_mgr.get_token()
        print(f"[预热] Token 获取成功\n")
    except AuthenticationError as e:
        print(f"[预热] ❌ Token 获取失败: {e}")
        return

    round_num = 0
    start_time = time.time()

    # 运行 6 分钟（约 19:19 ~ 19:25）
    while time.time() - start_time < 360:
        round_num += 1
        now = datetime.now()
        now_str = now.strftime("%H:%M:%S")

        print(f"\n--- 第 {round_num} 轮 [{now_str}] ---")

        round_result = {
            "round": round_num,
            "time": now_str,
            "timestamp": now.timestamp(),
        }

        # 测试 1: segment 查询
        seg = test_segment(build_id, target_date)
        round_result["segment"] = seg
        seg_status = f"✅ segment={seg['segment_id']}" if seg.get("segment_found") else "❌ 未找到"
        print(f"  segment: {seg_status} ({seg['elapsed_s']*1000:.0f}ms)")

        # 测试 2: 如果有 segment，测试座位列表
        if seg.get("segment_id"):
            seats = test_seat_list(build_id, seg["segment_id"], target_date)
            round_result["seats"] = seats
            print(f"  座位: 空闲={seats.get('free_seats', '?')}/{seats.get('total_seats', '?')} ({seats['elapsed_s']*1000:.0f}ms)")

            # 测试 3: confirm 探测（仅在 19:20 后执行，避免提前触发）
            if now.hour >= 19 and now.minute >= 20:
                confirm = test_confirm_probe(auth_token, seg["segment_id"])
                round_result["confirm"] = confirm
                body_preview = confirm.get("body", confirm.get("error", ""))[:80]
                print(f"  confirm: HTTP {confirm.get('status', '?')} ({confirm['elapsed_s']*1000:.0f}ms)")
                print(f"    响应: {body_preview}")

        results.append(round_result)

        # 间隔：19:19:50 到 19:20:10 期间每 2 秒一次，其余每 10 秒
        if now.hour == 19 and now.minute == 19 and now.second >= 50:
            time.sleep(2)
        elif now.hour == 19 and now.minute == 20 and now.second <= 10:
            time.sleep(2)
        else:
            time.sleep(10)

    # 保存结果
    output_file = "time_window_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  测试完成！共 {round_num} 轮")
    print(f"  结果已保存到: {output_file}")
    print(f"{'='*60}\n")

    # 快速汇总
    seg_found_rounds = [r for r in results if r.get("segment", {}).get("segment_found")]
    if seg_found_rounds:
        first_found = seg_found_rounds[0]
        print(f"📊 首次获取到 segment 的时间: {first_found['time']} (第 {first_found['round']} 轮)")
        seg_times = [r["segment"]["elapsed_s"] for r in results if "elapsed_s" in r.get("segment", {})]
        if seg_times:
            print(f"📊 segment 查询平均耗时: {sum(seg_times)/len(seg_times)*1000:.0f}ms")
    else:
        print("📊 整个测试期间均未获取到 segment")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="19:20 预约窗口敏感性测试")
    parser.add_argument("-c", "--config", help="配置文件路径", required=True)
    args = parser.parse_args()

    run_time_window_test(args.config)

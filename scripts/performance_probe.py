"""
图书馆预约系统 API 性能探测脚本
================================
只读探测，不触发真实预约。使用 TokenManager 认证。
用法: python scripts/performance_probe.py -c configs/studentA.yml [-n 10]
"""
import argparse
import json
import logging
import statistics
import os
import sys
import time
from datetime import datetime

import requests

# 添加 src/ 目录到路径，使脚本可从 scripts/ 目录独立运行
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config.config import AppConfig
from auth.token import TokenManager, AuthenticationError
from auth.login import qfnu_login
from api.constants import (
    URL_CLASSROOM_DETAIL_INFO,
    URL_CLASSROOM_SEAT,
    URL_CHECK_STATUS,
    LIB_BASE_URL,
    DEFAULT_HEADERS,
)
from api.http import post_with_retry
from crypto.aes import encrypt_seat_data
from classrooms import classroom_id_mapping

logger = logging.getLogger(__name__)

# ==================== 测量工具 ====================

def measure(func, *args, n=10, label="", **kwargs):
    """执行函数 n 次，返回耗时统计"""
    times = []
    errors = []
    for i in range(n):
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        except Exception as e:
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            errors.append(str(e))
        # 请求间隔 3s 避免触发风控
        if i < n - 1:
            time.sleep(3)

    if not times:
        return {"label": label, "error": "全部失败"}

    stats = {
        "label": label,
        "samples": len(times),
        "avg_ms": round(statistics.mean(times) * 1000, 1),
        "p50_ms": round(statistics.median(times) * 1000, 1),
        "min_ms": round(min(times) * 1000, 1),
        "max_ms": round(max(times) * 1000, 1),
    }
    if len(times) >= 2:
        stats["p95_ms"] = round(sorted(times)[int(len(times) * 0.95)] * 1000, 1)
        stats["stdev_ms"] = round(statistics.stdev(times) * 1000, 1)
    if errors:
        stats["errors"] = len(errors)
        stats["error_samples"] = errors[:3]
    return stats


# ==================== 探测函数 ====================

def probe_login_full(config):
    """测量完整登录流程（IDS CAS + CAPTCHA + Token）"""
    start = time.perf_counter()
    name, token = qfnu_login(config.username, config.password)
    elapsed = time.perf_counter() - start
    return {
        "label": "登录全链路（IDS CAS + CAPTCHA）",
        "elapsed_s": round(elapsed, 2),
        "success": token is not None,
        "name": name,
    }


def probe_token_cache(token_mgr):
    """测量 Token 缓存命中耗时"""
    start = time.perf_counter()
    token = token_mgr.get_token()
    elapsed = time.perf_counter() - start
    return round(elapsed * 1000, 2)


def probe_segment(build_id, nowday):
    """测量 /api/Seat/date 响应时间（单次）"""
    post_data = {"build_id": build_id}
    start = time.perf_counter()
    res = post_with_retry(
        URL_CLASSROOM_DETAIL_INFO, post_data, DEFAULT_HEADERS,
        max_retries=3, retry_delay=1, timeout=10
    )
    elapsed = time.perf_counter() - start
    # 解析 segment
    segment = None
    for item in res.get("data", []):
        if item["day"] == nowday:
            segment = item["times"][0]["id"]
            break
    return {"elapsed_s": round(elapsed, 3), "segment": segment, "found_date": segment is not None}


def probe_seat_list(build_id, segment, nowday, with_sleep=False):
    """测量 /api/Seat/seat 响应时间"""
    post_data = {
        "area": build_id,
        "segment": segment,
        "day": nowday,
        "startTime": "08:00",
        "endTime": "22:00",
    }
    start = time.perf_counter()
    res = post_with_retry(
        URL_CLASSROOM_SEAT, post_data, DEFAULT_HEADERS,
        max_retries=3, retry_delay=1, timeout=10
    )
    elapsed = time.perf_counter() - start

    free_count = sum(1 for s in res.get("data", []) if s.get("status_name") == "空闲")
    total_count = len(res.get("data", []))

    if with_sleep:
        time.sleep(1)  # 模拟原代码中的 sleep

    return {
        "elapsed_s": round(elapsed, 3),
        "total_seats": total_count,
        "free_seats": free_count,
    }


def probe_member_seat(auth_token):
    """测量 /api/Member/seat 响应时间（单次）"""
    post_data = {"page": 1, "limit": 3, "authorization": auth_token}
    request_headers = {**DEFAULT_HEADERS, "Authorization": auth_token}
    start = time.perf_counter()
    try:
        res = post_with_retry(
            URL_CHECK_STATUS, post_data, request_headers,
            max_retries=3, retry_delay=1, timeout=10
        )
        elapsed = time.perf_counter() - start
        return {"elapsed_s": round(elapsed, 3), "status": "ok", "data_keys": list(res.keys()) if isinstance(res, dict) else None}
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"elapsed_s": round(elapsed, 3), "status": "error", "error": str(e)}


def probe_aes_encrypt():
    """测量 AES 加密耗时"""
    test_data = '{"seat_id":"7500","segment":"123"}'
    times = []
    for _ in range(100):
        start = time.perf_counter()
        encrypt_seat_data(test_data)
        times.append(time.perf_counter() - start)
    return {
        "label": "AES 加密 (100 次平均)",
        "avg_us": round(statistics.mean(times) * 1_000_000, 1),
        "p50_us": round(statistics.median(times) * 1_000_000, 1),
        "max_us": round(max(times) * 1_000_000, 1),
    }


def probe_tcp_latency():
    """测量到服务器的 TCP 握手延迟"""
    times = []
    for _ in range(5):
        try:
            start = time.perf_counter()
            r = requests.get(LIB_BASE_URL, timeout=10)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        except Exception:
            pass
        time.sleep(1)
    if times:
        return {
            "label": "TCP + HTTP 基础延迟",
            "avg_ms": round(statistics.mean(times) * 1000, 1),
            "min_ms": round(min(times) * 1000, 1),
            "max_ms": round(max(times) * 1000, 1),
        }
    return {"label": "TCP + HTTP 基础延迟", "error": "全部失败"}


def probe_http_status_distribution(auth_token, n=5):
    """探测 /api/Member/seat 的 HTTP 状态码分布"""
    post_data = {"page": 1, "limit": 3, "authorization": auth_token}
    request_headers = {**DEFAULT_HEADERS, "Authorization": auth_token}
    status_codes = {}
    for i in range(n):
        try:
            r = requests.post(
                URL_CHECK_STATUS, json=post_data, headers=request_headers, timeout=10
            )
            code = r.status_code
            status_codes[code] = status_codes.get(code, 0) + 1
        except requests.exceptions.Timeout:
            status_codes["timeout"] = status_codes.get("timeout", 0) + 1
        except Exception as e:
            status_codes[f"error:{type(e).__name__}"] = status_codes.get(f"error:{type(e).__name__}", 0) + 1
        time.sleep(3)
    return status_codes


# ==================== 主流程 ====================

def run_probe(config_file, n_samples=10):
    """执行完整性能探测"""
    results = {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results["probe_time"] = timestamp
    results["n_samples"] = n_samples

    config = AppConfig.from_yaml(config_file)
    print(f"\n{'='*60}")
    print(f"  图书馆预约系统 API 性能探测")
    print(f"  时间: {timestamp}")
    print(f"  每项测量 {n_samples} 次（间隔 3s）")
    print(f"{'='*60}\n")

    # ---- 1. AES 加密开销（无需网络） ----
    print("[1/7] 测量 AES 加密开销...")
    results["aes_encrypt"] = probe_aes_encrypt()
    print(f"  平均: {results['aes_encrypt']['avg_us']}μs\n")

    # ---- 2. TCP 基础延迟 ----
    print("[2/7] 测量 TCP + HTTP 基础延迟...")
    results["tcp_latency"] = probe_tcp_latency()
    if "avg_ms" in results["tcp_latency"]:
        print(f"  平均: {results['tcp_latency']['avg_ms']}ms\n")
    else:
        print(f"  失败\n")

    # ---- 3. 登录全链路 ----
    print("[3/7] 测量登录全链路（仅 1 次，含 CAPTCHA）...")
    results["login"] = probe_login_full(config)
    print(f"  耗时: {results['login']['elapsed_s']}s, 成功: {results['login']['success']}\n")

    if not results["login"]["success"]:
        print("  ❌ 登录失败，无法继续测量。请检查账号密码。")
        return results

    # ---- 4. Token 缓存命中 ----
    print("[4/7] 测量 Token 缓存命中...")
    token_mgr = TokenManager(config.username, config.password)
    # 预热
    token_mgr.get_token()
    cache_times = []
    for _ in range(n_samples):
        cache_times.append(probe_token_cache(token_mgr))
        time.sleep(0.5)
    results["token_cache_ms"] = {
        "avg_ms": round(statistics.mean(cache_times), 2),
        "max_ms": round(max(cache_times), 2),
    }
    print(f"  平均: {results['token_cache_ms']['avg_ms']}ms\n")

    # ---- 5. API 端点测量 ----
    auth_token = token_mgr.get_token()

    # 获取 segment
    classroom_name = config.classrooms_name[0] if config.classrooms_name else "东校区图书馆-三楼自修区"
    build_id = classroom_id_mapping.get(classroom_name, 22)
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"[5/7] 测量时间段查询 /api/Seat/date (教室: {classroom_name})...")
    seg_results = []
    for i in range(min(n_samples, 5)):
        seg_results.append(probe_segment(build_id, today))
        time.sleep(3)
    results["segment"] = seg_results
    seg_times = [r["elapsed_s"] for r in seg_results]
    print(f"  平均: {round(statistics.mean(seg_times)*1000, 1)}ms\n")

    # 获取一个有效的 segment 用于后续测量
    valid_segment = None
    for r in seg_results:
        if r["segment"]:
            valid_segment = r["segment"]
            break

    if valid_segment:
        print(f"[6/7] 测量座位查询 /api/Seat/seat (segment={valid_segment})...")
        seat_results = []
        for i in range(min(n_samples, 5)):
            seat_results.append(probe_seat_list(build_id, valid_segment, today))
            time.sleep(3)
        results["seat_list"] = seat_results
        seat_times = [r["elapsed_s"] for r in seat_results]
        free_counts = [r["free_seats"] for r in seat_results]
        print(f"  平均: {round(statistics.mean(seat_times)*1000, 1)}ms, 空闲座位: {free_counts}\n")
    else:
        print(f"[6/7] 跳过座位查询（未获取到有效 segment）\n")
        results["seat_list"] = "skipped - no valid segment"

    print(f"[7/7] 测量用户状态查询 /api/Member/seat + HTTP 状态码分布...")
    member_results = []
    for i in range(min(n_samples, 5)):
        member_results.append(probe_member_seat(auth_token))
        time.sleep(3)
    results["member_seat"] = member_results
    member_times = [r["elapsed_s"] for r in member_results]
    print(f"  平均: {round(statistics.mean(member_times)*1000, 1)}ms\n")

    # HTTP 状态码分布
    results["status_codes"] = probe_http_status_distribution(auth_token, n=5)
    print(f"  HTTP 状态码分布: {results['status_codes']}\n")

    # ---- 汇总 ----
    print(f"\n{'='*60}")
    print("  探测完成！结果已保存到 performance_results.json")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="图书馆预约系统 API 性能探测")
    parser.add_argument("-c", "--config", help="配置文件路径", required=True)
    parser.add_argument("-n", "--samples", type=int, default=10, help="每项测量次数（默认 10）")
    parser.add_argument("-o", "--output", default="performance_results.json", help="输出文件路径")
    args = parser.parse_args()

    results = run_probe(args.config, args.samples)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"结果已保存到: {args.output}")

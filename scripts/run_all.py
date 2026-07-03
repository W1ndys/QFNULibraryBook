"""
多用户并发入口 — 同时为多个用户执行预约/签到/签退。

用法:
  python run_all.py seat --users configs/users.yml      # 多用户并发抢座
  python run_all.py checkin --users configs/users.yml   # 多用户签到
  python run_all.py signout --users configs/users.yml   # 多用户签退

  python run_all.py seat -u configs/users.yml --notify-mode aggregated  # 聚合通知

支持 KeyboardInterrupt 优雅关闭。
"""
import argparse
import concurrent.futures
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

import yaml

# 添加 py/ 目录到路径，使脚本可从 scripts/ 目录独立运行
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from config.config import AppConfig
from auth.token import TokenManager
from notify.notify import send_message

logger = logging.getLogger(__name__)


@dataclass
class UserEntry:
    """用户配置条目"""
    config: str
    name: str = ""


class UsersConfig:
    """多用户配置文件加载器"""

    def __init__(self, config_path: str):
        self.users: List[UserEntry] = []
        self._load(config_path)

    def _load(self, config_path: str):
        """加载 users.yml，检查格式"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"多用户配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict) or "users" not in raw:
            raise ValueError(
                f"users.yml 格式错误：缺少 'users' 键，请检查文件格式\n"
                f"正确格式：\n"
                f"  users:\n"
                f"    - config: studentA.yml\n"
                f"      name: \"可选别名\""
            )

        user_list = raw["users"]
        if not isinstance(user_list, list) or len(user_list) == 0:
            raise ValueError("users.yml 中 'users' 列表为空")

        base_dir = os.path.dirname(os.path.abspath(config_path))
        for entry in user_list:
            if "config" not in entry:
                raise ValueError(
                    f"users.yml 条目缺少 'config' 字段: {entry}"
                )
            config_rel_path = entry["config"]
            config_abs = (os.path.join(base_dir, config_rel_path)
                          if not os.path.isabs(config_rel_path)
                          else config_rel_path)
            self.users.append(UserEntry(
                config=config_abs,
                name=entry.get("name", ""),
            ))


def load_user_configs(entry: UserEntry) -> Optional[AppConfig]:
    """加载单个用户的配置，失败时返回 None"""
    try:
        cfg = AppConfig.from_yaml(entry.config)
        # 配置自检
        if not cfg.username or not cfg.password:
            logger.warning(f"[{entry.name or entry.config}] 用户名或密码为空，跳过")
            return None
        logger.info(f"[{cfg.username}] 加载配置成功")
        return cfg
    except Exception as e:
        logger.error(f"[{entry.name or entry.config}] 配置加载失败: {e}")
        return None


def run_action_for_user(cfg: AppConfig, action: str) -> bool:
    """
    为单个用户执行指定操作。

    返回:
        True 表示成功，False 表示失败

    异常不会传播到调用方（已在内部捕获）
    """
    user_label = f"[{cfg.username}]"
    try:
        token_mgr = TokenManager(cfg.username, cfg.password)

        if action == "seat":
            from get_seat import run_seat_reservation
            run_seat_reservation(cfg, token_mgr)
        elif action == "checkin":
            from check_in import lib_rsv
            lib_rsv(cfg, token_mgr)
        elif action == "signout":
            from sign_out import go_home
            go_home(cfg, token_mgr)
        else:
            logger.error(f"{user_label} 未知操作: {action}")
            return False

        logger.info(f"{user_label} {action} 完成")
        return True

    except Exception as e:
        logger.error(f"{user_label} {action} 失败: {e}")
        return False


def send_summary_notification(results: list, action: str, start_time: float):
    """发送聚合通知"""
    elapsed = time.time() - start_time
    success_count = sum(1 for r in results if r["success"])
    total = len(results)
    usernames_success = [r["user"] for r in results if r["success"]]
    usernames_failed = [r["user"] for r in results if not r["success"]]

    summary = (
        f"📋 {action} 执行报告\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"✅ 成功: {success_count}/{total}\n"
        f"⏱ 耗时: {elapsed:.1f}s\n"
    )
    if usernames_success:
        summary += f"👍 用户: {', '.join(usernames_success)}\n"
    if usernames_failed:
        summary += f"❌ 失败: {', '.join(usernames_failed)}\n"

    logger.info(f"\n{summary}")


def run_concurrent(configs: List[AppConfig], action: str,
                   max_workers: int = 8, notify_mode: str = "each"):
    """
    用线程池并发执行指定操作。

    参数:
        configs: 用户配置列表
        action: 操作类型 (seat/checkin/signout)
        max_workers: 最大并发线程数
        notify_mode: 'each' 每个用户单独通知 / 'aggregated' 仅聚合通知
    """
    n_users = len(configs)
    max_workers = min(max_workers, n_users)
    results = []
    start_time = time.time()

    logger.info(f"开始并发 {action}，{n_users} 个用户，{max_workers} 个线程")

    executor = None
    try:
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="User"
        )

        future_to_cfg = {}
        for cfg in configs:
            future = executor.submit(run_action_for_user, cfg, action)
            future_to_cfg[future] = cfg

        for future in concurrent.futures.as_completed(future_to_cfg):
            cfg = future_to_cfg[future]
            user_label = cfg.username
            try:
                success = future.result()
                results.append({
                    "user": user_label,
                    "success": success,
                })
                status = "✅" if success else "❌"
                logger.info(f"{status} [{user_label}] {action} {'成功' if success else '失败'}")
            except Exception as e:
                results.append({
                    "user": user_label,
                    "success": False,
                })
                logger.error(f"❌ [{user_label}] {action} 异常: {e}")

    except KeyboardInterrupt:
        logger.warning("⚠️ 用户中断，正在停止所有线程...")
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
        return results

    # 通知
    if notify_mode == "aggregated":
        # 只需一条聚合通知给第一个用户的配置（使用其通知渠道）
        if configs:
            send_summary_notification(results, action, start_time)
            send_message(configs[0], send_summary_notification(
                results, action, start_time), f"{action} 执行报告")
    # 'each' 模式：每个用户的 lib_rsv/go_home 内部已独立发送通知

    elapsed = time.time() - start_time
    success_count = sum(1 for r in results if r["success"])

    logger.info(
        f"📊 汇总: {success_count}/{len(results)} 成功, "
        f"耗时 {elapsed:.1f}s"
    )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="多用户并发预约/签到/签退"
    )
    parser.add_argument(
        "action",
        choices=["seat", "checkin", "signout"],
        help="操作类型"
    )
    parser.add_argument(
        "-u", "--users",
        default="configs/users.yml",
        help="多用户配置文件路径（默认: configs/users.yml）"
    )
    parser.add_argument(
        "-w", "--max-workers",
        type=int, default=8,
        help="最大并发线程数（默认: 8）"
    )
    parser.add_argument(
        "--notify-mode",
        choices=["each", "aggregated"],
        default="each",
        help="通知模式: each=每个用户单独推送, aggregated=仅聚合通知"
    )

    args = parser.parse_args()

    # 日志格式（含线程名）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        users_cfg = UsersConfig(args.users)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    # 加载所有用户配置，跳过无效配置
    configs = []
    for entry in users_cfg.users:
        cfg = load_user_configs(entry)
        if cfg is not None:
            configs.append(cfg)

    if not configs:
        print("❌ 没有可用的用户配置，退出", file=sys.stderr)
        sys.exit(1)

    if len(configs) < len(users_cfg.users):
        print(f"⚠️  加载了 {len(configs)}/{len(users_cfg.users)} 个用户配置")

    print(f"🔨 开始 {args.action}，共 {len(configs)} 个用户...")
    run_concurrent(
        configs,
        args.action,
        max_workers=args.max_workers,
        notify_mode=args.notify_mode,
    )


if __name__ == "__main__":
    main()
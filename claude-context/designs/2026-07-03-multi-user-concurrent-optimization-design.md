# 多用户并发 + 速度优化 设计文档

> 2026-07-03 | 基于项目现状分析

## 1. 目标

1. **多用户并发抢座** — 多个账号同时发起预约，互不阻塞
2. **单用户速度优化** — 最小化登录/预约链路上的非必要延迟
3. **稳定性提升** — 修复资源泄漏、线程安全、Session 管理等问题

## 2. 架构

### 2.1 整体结构

```
新增:
  py/run_all.py                 # 多用户并发入口
  py/config/users.yml           # 多用户配置（列出子配置文件路径）

修改:
  py/auth/token.py              # 线程安全
  py/auth/login.py              # Session 管理 + 速度优化
  py/get_seat.py                # 提取纯函数 run_seat_reservation()
  py/check_in.py                # 多用户签到支持
  py/sign_out.py                # 多用户签退支持
  py/api/http.py                # 重试策略优化
```

### 2.2 多用户并发模型

```
users.yml
├─ config_studentA.yml  ──→ 线程1: 登录 → 获取座位信息 → 预约
├─ config_studentB.yml  ──→ 线程2: 登录 → 获取座位信息 → 预约
└─ config_studentC.yml  ──→ 线程N: ...

所有线程同时启动，各自拥有独立的:
  - TokenManager（含 Lock）
  - requests.Session
  - 通知实例

主线程等待全部完成，聚合结果。
```

**为什么用 `threading` 而非 `multiprocessing`：**
- 瓶颈是网络 I/O，不是 CPU
- 线程共享进程内存，配置/常量不需要复制
- 更轻量，启动快

### 2.3 TokenManager 线程安全

```python
import threading

class TokenManager:
    def __init__(self, username, password):
        self._lock = threading.Lock()
        ...

    def get_token(self) -> str:
        with self._lock:
            # 双重检查：获取锁后再次检查是否过期
            if self._token and not self._is_expired():
                return self._token
            # 登录...
            self._token = "bearer" + token
            self._timestamp = datetime.now(timezone.utc)
            return self._token
```

### 2.4 Session 管理

```python
# 当前：qfnu_login 创建 session 但不关闭
# 改进：context manager
def qfnu_login(username, password):
    with requests.session() as session:
        return _get_bearer_token(session, username, password)

# _login_with_retry 也相应包装
def _login_with_retry(username, password, max_retries=3):
    for attempt in range(max_retries):
        try:
            name, token = qfnu_login(username, password)
            ...
```

## 3. 速度优化细节

### 3.1 减少登录链路上的 sleep

| 位置 | 当前 | 改为 | 理由 |
|------|------|------|------|
| `_do_solve_slider_captcha` 轮间 | `time.sleep(0.2)` | **0.05s** | 轮间延迟只需服务器感知到足够时间差即可 |
| `_get_salt_and_execution` 重试 | `time.sleep(0.5)` | **仅在失败时 sleep 0.3s** | 首次成功不应延误 |
| `_login_with_retry` 退避 | 1s, 2s, 4s | **0.5s, 1s, 2s** | 抢座场景时效性强，适度缩短 |

### 3.2 减少预约循环中的重复请求

当前 `select_seat` 中每次循环都 `get_seat_info` + `post_to_get_seat`。如果座位信息 API 可以在一次请求中获取所有教室的座位，可以缓存。

但当前代码已经是对每个教室单独轮询，结构合理。主要优化点是：
- `post_to_get_seat` 中 `token_mgr.get_token()` 使用缓存的 token（已实现 ✓）

## 4. 稳定性改进

### 4.1 HTTP 重试策略（`py/api/http.py`）

| 问题 | 改进 |
|------|------|
| 4xx 状态码也重试 | 区分处理：4xx 不重试，5xx/网络错误才重试 |
| 固定 1s 间隔 | 加上随机抖动（`time.sleep(retry_delay + random.uniform(0, 0.5))`） |
| 无总超时 | 添加 `total_timeout` 参数，避免无限重试 |

### 4.2 配置自检

在 `run_all.py` 启动时检查所有用户配置：
- 用户名/密码非空
- 推送配置至少有一个渠道完整
- 教室列表非空、日期格式正确

任何一个配置有问题，在启动时立即报错，不等到登录时才失败。

## 5. 新增文件

### 5.1 `py/run_all.py` — 多用户并发入口

```python
"""
多用户并发预约/签到/签退入口。
用法:
  python run_all.py seat -c users.yml        # 多用户并发抢座
  python run_all.py checkin -c users.yml     # 多用户签到
  python run_all.py signout -c users.yml     # 多用户签退
"""
import argparse
import concurrent.futures
import logging
import sys

from config.config import AppConfig
from get_seat import run_seat_reservation
from check_in import lib_rsv
from sign_out import go_home
from auth.token import TokenManager
from notify.notify import send_message

logger = logging.getLogger(__name__)


def load_users(users_config_path: str) -> list[AppConfig]:
    """从 users.yml 加载所有用户配置"""
    import yaml, os
    base_dir = os.path.dirname(users_config_path)
    with open(users_config_path) as f:
        data = yaml.safe_load(f)
    configs = []
    for entry in data["users"]:
        config_path = entry["config"]
        if not os.path.isabs(config_path):
            config_path = os.path.join(base_dir, config_path)
        configs.append(AppConfig.from_yaml(config_path))
    return configs


def run_concurrent(configs: list[AppConfig], action: str):
    """用线程池并发执行指定操作"""
    results = []
    max_workers = min(len(configs), 8)  # 最多 8 个并发线程

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for cfg in configs:
            token_mgr = TokenManager(cfg.username, cfg.password)
            if action == "seat":
                future = executor.submit(run_seat_reservation, cfg, token_mgr)
            elif action == "checkin":
                future = executor.submit(lib_rsv, cfg, token_mgr)
            elif action == "signout":
                future = executor.submit(go_home, cfg, token_mgr)
            futures[future] = cfg

        for future in concurrent.futures.as_completed(futures):
            cfg = futures[future]
            try:
                future.result()
                results.append((cfg.username, True, None))
            except Exception as e:
                results.append((cfg.username, False, str(e)))

    # 聚合通知
    success = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    summary = f"执行完成: 成功 {len(success)}/{len(results)}"
    if failed:
        summary += f"\n失败: {', '.join(r[0] for r in failed)}"
    logger.info(summary)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多用户并发预约/签到/签退")
    parser.add_argument("action", choices=["seat", "checkin", "signout"])
    parser.add_argument("-c", "--config", default="users.yml", help="多用户配置文件")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    configs = load_users(args.config)
    print(f"加载了 {len(configs)} 个用户配置，开始并发 {args.action}...")
    run_concurrent(configs, args.action)
```

### 5.2 `py/config/users.yml` — 多用户配置模板

```yaml
# 多用户配置文件
# 列出每个用户的子配置文件路径（相对于本文件的相对路径，或绝对路径）

users:
  - config: config_studentA.yml
    name: "学生 A"       # 可选：仅用于日志标识
  - config: config_studentB.yml
    name: "学生 B"
```

## 6. 改动清单

### 新建文件
| 文件 | 说明 |
|------|------|
| `py/run_all.py` | 多用户并发入口 |
| `py/config/users.yml` | 多用户配置模板 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `py/auth/token.py` | 添加 `threading.Lock`，双重检查锁 |
| `py/auth/login.py` | `time.sleep(0.2→0.05)`、`_login_with_retry` 退避缩短 |
| `py/api/http.py` | 4xx 不重试、添加抖动、区分异常类型 |

### 不修改的文件
- `py/get_seat.py` — 现有逻辑不变，被 `run_all.py` 直接调用
- `py/check_in.py` — 同上
- `py/sign_out.py` — 同上

## 7. 成功标准

1. **多用户并发** — 3 个用户同时运行，总耗时 ≈ 最慢的单个用户耗时（而非三者之和）
2. **速度提升** — 单次登录耗时减少 1-2 秒
3. **稳定性** — `pytest tests/` 全部通过，无新增异常
4. **向后兼容** — 单用户模式（`python get_seat.py -c ...`）仍然正常工作

## 8. 风险与回退

| 风险 | 缓解 |
|------|------|
| 多线程并发可能触发 IDS 限流 | ThreadPool 默认最多 8 个线程，可通过 `max_workers` 调整 |
| `time.sleep` 缩减可能导致滑块验证失败 | 保持 `_do_solve_slider_captcha` 外层 5 轮不变（5*0.05 = 0.25s，仍有足够时差） |
| TokenManager 锁竞争 | 仅在 token 过期时持有锁，耗时 <5s，影响可忽略 |

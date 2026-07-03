# 多用户并发 + 速度优化 设计文档 V2

> 2026-07-03 | 基于 V1 审核意见修订 | 审核结论：修改后批准

## 1. 目标

1. **多用户并发抢座** — 多个账号同时发起预约，互不阻塞
2. **单用户速度优化** — 最小化登录/预约链路上的非必要延迟（正常路径节省 ~0.6s）
3. **稳定性提升** — 修复资源泄漏、线程安全、Session 管理、sys.exit() 进程级崩溃等问题

## 2. 架构

### 2.1 整体结构

```
新增:
  py/run_all.py                 # 多用户并发入口
  py/config/users.yml           # 多用户配置模板

修改:
  py/auth/token.py              # +threading.Lock, 统一 UTC 时区
  py/auth/login.py              # sleep 缩短 + Session context manager
  py/get_seat.py                # sys.exit() → 自定义异常；提取 run_seat_reservation()
  py/check_in.py                # sys.exit() → 自定义异常；lib_rsv() 返回状态
  py/sign_out.py                # sys.exit() → 自定义异常；go_home() 返回状态
  py/api/http.py                # 4xx 不重试、加抖动、支持 session 参数
  py/api/constants.py           # 统一 User-Agent 和 Authorization header
```

### 2.2 多用户并发模型

```
users.yml → 线程1: 登录 → 获取座位信息 → 预约
           → 线程2: 登录 → 获取座位信息 → 预约
           → 线程N: ...

所有线程同时启动，各自拥有独立的:
  - TokenManager（含 threading.Lock）
  - requests.Session（context manager 自动关闭）
  - per-thread 的 Session 池用于 REST API 调用

主线程等待全部完成，聚合结果并推送通知。
```

**并发方案：threading**（非 multiprocessing）
- 瓶颈是网络 I/O，不是 CPU
- 线程共享进程内存，配置/常量不需要复制
- 更轻量，启动快

**线程安全保证：**
- 每个 worker 线程拥有独立的 `TokenManager` 实例
- `TokenManager.get_token()` 内部使用 `threading.Lock` 双重检查锁
- 每个线程持有自己的 `requests.Session`
- `sys.exit()` 已替换为异常，一个线程失败不会杀死其他线程

### 2.3 TokenManager 线程安全

```python
import threading
from datetime import datetime, timezone

class TokenManager:
    def __init__(self, username: str, password: str):
        self._lock = threading.Lock()
        self._username = username
        self._password = password
        self._token: str = ""
        self._timestamp: datetime = None  # ✅ 统一 UTC

    def get_token(self) -> str:
        if not self._username or not self._password:
            raise AuthenticationError("未找到用户名或密码")

        # 无锁快速路径
        if self._token and not self._is_expired():
            return self._token

        # 锁保护下的刷新路径
        with self._lock:
            # 双重检查：避免获取锁期间已被其他线程刷新
            if self._token and not self._is_expired():
                return self._token

            logger.info("Token 已过期或未获取，重新登录...")
            name, token = _login_with_retry(self._username, self._password,
                                            max_retries=_MAX_LOGIN_RETRIES)
            if token is None:
                raise AuthenticationError("获取 token 失败")
            self._token = "bearer" + str(token)
            self._timestamp = datetime.now(timezone.utc)
            logger.info(f"成功获取授权码，姓名: {name}")
            return self._token

    def _is_expired(self) -> bool:
        if self._timestamp is None:
            return True
        return (datetime.now(timezone.utc) - self._timestamp) > TOKEN_EXPIRY
```

**为什么统一 UTC：**
- `datetime.now(timezone.utc)` 避免夏令时切换问题
- `TOKEN_EXPIRY = timedelta(hours=1, minutes=30)` 是固定时长差，时区不影响差值
- 与早期版本兼容：早期使用本地时间，改造后统一 UTC

### 2.4 Session 管理

```python
def qfnu_login(username, password):
    """✅ 使用 context manager，自动关闭 session"""
    with requests.session() as session:
        return _get_bearer_token(session, username, password)
```

**REST API 调用（post_with_retry）：**
- 新增可选的 `session` 参数，允许调用方传入 per-thread session
- 不传时保持向后兼容（内部创建单次连接）
- 建议调用方（如 `get_seat.py`）为每个线程创建自己的 session 池

### 2.5 sys.exit() 替换（关键修复）

三个入口文件中的 `sys.exit()` 均替换为自定义异常：

```python
# 新增异常类（放在各模块或 api/exceptions.py）
class ReservationFailed(Exception):
    """预约失败"""
    pass

class CheckInFailed(Exception):
    """签到失败"""
    pass

class SignOutFailed(Exception):
    """签退失败"""
    pass
```

**替换规则（以 get_seat.py 为例）：**
```python
# 改前:
sys.exit()

# 改后:
raise ReservationFailed("超过最大重试次数，无法获取座位")
```

**向后兼容：**
- `if __name__ == "__main__"` 块中的 `sys.exit()` 保留
- 异常在 `run_all.py` 的 `future.result()` 处由 `run_concurrent()` 统一捕获
- 单用户模式下（直接运行 `python get_seat.py ...`），未被捕获的异常按正常 Python 异常传播

## 3. 速度优化细节

### 3.1 减少登录链路上的 sleep

| 位置 | 当前 | 改为 | 理由 | 节省 |
|------|------|------|------|------|
| `_do_solve_slider_captcha` 轮间 | `time.sleep(0.2)` | **0.1s** | 保留足够时差避免风控 | 4×0.1=0.4s |
| `_get_salt_and_execution` 重试 | `time.sleep(0.5)` | **仅失败时 sleep 0.3s** | 首次成功不应延误 | ~0.2s |
| `_login_with_retry` 退避 | 1s, 2s, 4s | **0.5s, 1s, 2s** | 抢座场景时效性强 | ~3.5s(仅重试时) |

**正常路径预期收益：~0.6s**（仅多用户并发时收益叠加，但单用户感知提升有限）

### 3.2 预约循环优化

主要优化点已在：
- `post_to_get_seat` 中 `token_mgr.get_token()` 使用缓存的 token（✅ 已实现）

## 4. 稳定性改进

### 4.1 HTTP 重试策略 (`py/api/http.py`)

| 问题 | 改进 |
|------|------|
| 4xx 状态码也重试 | 区分处理：4xx 直接抛出 `RequestFailed`，不重试；5xx/网络错误才重试 |
| 固定 1s 间隔 | 加随机抖动：`time.sleep(retry_delay + random.uniform(0, 0.5))` |
| 无 session 支持 | 新增可选 `session` 参数，调用方可传入 per-thread Session |
| 无调用级总超时 | 新增 `total_timeout` 参数：累计超时后放弃，而非强制中断当前请求 |

```python
def post_with_retry(url, data, headers, max_retries=10, retry_delay=1,
                    timeout=15, total_timeout=120, session=None):
    """带重试的 POST 请求（支持 4xx 快速失败、抖动、session 复用、总超时）"""
    start_time = time.time()
    for retries in range(max_retries):
        try:
            if time.time() - start_time > total_timeout:
                raise RequestFailed(f"总超时 {total_timeout}s，放弃请求: {url}")

            http = session.post if session else requests.post
            response = http(url, json=data, headers=headers, timeout=timeout)

            # 4xx 快速失败，不重试
            if 400 <= response.status_code < 500:
                raise RequestFailed(f"HTTP {response.status_code}: 请求被拒绝")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error("请求超时，正在重试...")
        except Exception as e:
            logger.error(f"请求异常: {e}")

        delay = retry_delay + random.uniform(0, 0.5)
        time.sleep(delay)

    raise RequestFailed(f"超过最大重试次数 ({max_retries})，请求失败: {url}")
```

### 4.2 配置自检

`run_all.py` 启动时检查所有用户配置：
- 用户名/密码非空
- 推送配置至少有一个渠道完整
- 教室列表非空、日期格式正确
- `users.yml` 格式校验（缺少 `users` 键时给出清晰提示）

任何一个配置有问题，在启动时立即报错，不等到登录时才失败。

### 4.3 Worker 异常隔离

- 每个用户的 worker 线程异常不会传播到其他线程
- `future.result()` 仅在当前线程失败时抛出异常
- `run_concurrent()` 在 `as_completed` 循环中为每个 future 包裹 try/except

### 4.4 统一 Authorization Header

- `check_in.py` 中 `"authorization"` → `"Authorization"`
- 所有文件统一为 `"Authorization"`（HTTP 标准大写）

### 4.5 KeyboardInterrupt 处理

```python
def run_concurrent(configs, action):
    executor = None
    try:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        # ... 提交任务 ...
    except KeyboardInterrupt:
        logger.warning("用户中断，正在停止所有线程...")
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
    return results
```

### 4.6 日志配置

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s: %(message)s",
)
```

## 5. 新增文件

### 5.1 `py/run_all.py` — 多用户并发入口

```python
"""
多用户并发预约/签到/签退入口。
用法:
  python run_all.py seat -c users.yml        # 多用户并发抢座
  python run_all.py checkin -c users.yml     # 多用户签到
  python run_all.py signout -c users.yml     # 多用户签退
  python run_all.py seat -c users.yml --notify-mode aggregated  # 聚合通知

支持 KeyboardInterrupt graceful shutdown。
"""
```

**关键行为：**
- ThreadPoolExecutor 默认 `max_workers=min(n_users, 8)`
- `--notify-mode`：`each`（默认，每个用户单独推）/ `aggregated`（仅一条聚合通知）
- 聚合通知包含成功/失败统计

### 5.2 `py/config/users.yml` — 多用户配置模板

```yaml
# 多用户配置文件
# 列出每个用户的子配置文件路径（相对于本文件的相对路径，或绝对路径）
# name 字段可选，仅用于日志标识；未设置时使用配置中的 USERNAME

users:
  - config: config_studentA.yml
    name: "张柏维"       # 可选
  - config: config_studentB.yml
    name: "郑欣悦"       # 可选
```

### 5.3 `py/api/exceptions.py` — 自定义异常类（可选拆分）

```python
class RequestFailed(Exception): pass      # 已有，位置不变
class AuthenticationError(Exception): pass # 已有，位置不变
class ReservationFailed(Exception): pass   # 新增
class CheckInFailed(Exception): pass       # 新增
class SignOutFailed(Exception): pass       # 新增
```

## 6. 改动清单

### 新建文件
| 文件 | 说明 |
|------|------|
| `py/run_all.py` | 多用户并发入口 |
| `py/config/users.yml` | 多用户配置模板 |
| `tests/test_run_all.py` | 并发逻辑单元测试 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `py/auth/token.py` | +`threading.Lock`；`datetime.now()` → UTC；新增 `_is_expired()` 方法 |
| `py/auth/login.py` | sleep 缩短(0.2→0.1/0.3)；`qfnu_login` 用 `with session`；重试退避缩短 |
| `py/api/http.py` | 4xx不重试、+抖动、+`session`参数、+`total_timeout`参数 |
| `py/api/constants.py` | 统一 `"authorization"` → `"Authorization"` |
| `py/get_seat.py` | `sys.exit()` → `raise ReservationFailed`；`run_seat_reservation()` 保留为纯函数 |
| `py/check_in.py` | `sys.exit()` → `raise CheckInFailed`；`"authorization"` → `"Authorization"` |
| `py/sign_out.py` | `sys.exit()` → `raise SignOutFailed`；`lib_rsv`/`go_home` 返回状态 |
| `py/api/exceptions.py` | 新增 `ReservationFailed`、`CheckInFailed`、`SignOutFailed` |

### 不修改的文件
| 文件 | 理由 |
|------|------|
| `py/config/config.py` | 配置加载逻辑不变 |
| `py/crypto/aes.py` | 加密逻辑不受影响 |
| `py/classrooms.py` | 教室映射不变 |
| `py/get_info.py` | 座位查询工具不变 |
| `py/notify/notify.py` | 通知模块已在上次改动中优化完毕 |

## 7. 成功标准

1. **多用户并发** — 3 个用户同时运行，总耗时 ≈ 最慢的单个用户耗时（而非三者之和）
2. **速度提升** — 正常路径下登录耗时减少 ~0.6s；极端慢路径下减少 ~4s
3. **稳定性** — `pytest tests/` 全部通过（含新增的 `test_run_all.py`）
4. **异常隔离** — 一个用户失败不会影响其他用户
5. **向后兼容** — 单用户模式（`python get_seat.py -c ...`）仍然正常工作

## 8. 风险与回退

| 风险 | 缓解 |
|------|------|
| 🔴 sys.exit() 被 new 代码重新引入 | 代码审查时重点检查，所有 exit 必须走异常 |
| 🟡 多线程并发触发 IDS 限流 | max_workers 默认 8，可通过 --max-workers 调整 |
| 🟡 sleep 缩减(0.2→0.1)导致滑块验证失败 | 保持 5 轮不变 + 0.1s 是 0.2s 的 50%，时差仍充裕 |
| 🟡 timezone.utc 与已有缓存 token 兼容 | TokenManager._timestamp=None 时强制刷新，仅首次受影响 |
| ⚪ 线程日志交错 | 日志格式 +threadName 字段，可追溯每个线程 |

### 回退命令
```bash
git checkout master -- py/run_all.py py/config/users.yml tests/test_run_all.py \
    py/auth/token.py py/auth/login.py py/api/http.py py/api/constants.py \
    py/get_seat.py py/check_in.py py/sign_out.py py/api/exceptions.py
```
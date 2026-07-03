# 通知发送 & 登录可靠性改进规范 V2

> 基于 V1 审核意见修订，审核结论：修改后批准

## 1. 目的

提升项目两个核心子系统的可靠性：
1. **通知发送**（`py/notify/notify.py`）— 确保推送失败时有重试机制，各渠道健壮性统一
2. **登录成功率**（`py/auth/login.py` + `py/auth/token.py`）— 确保单账号登录成功率 > 99%（含网络波动、验证码识别失败、服务器暂时错误等异常）

## 2. 边界

- ❌ 不涉及座位预约/签到/签退的业务逻辑
- ❌ 不涉及 YAML 配置文件的新增字段
- ✅ 仅改动以下文件和目录：
  - `py/notify/notify.py`
  - `py/auth/login.py`
  - `py/auth/token.py`
  - `tests/test_notify.py`
  - `requirements.txt`

## 3. 技术方案

### 3.1 通知发送改进

| 问题 | 改进方案 |
|------|---------|
| 各渠道无任何重试 | 使用 `tenacity` 装饰器，`max_attempts=3`，`wait_fixed(1)` |
| `_send_anpush` 忽略响应 | 增加响应状态码校验，非 2xx 抛出异常触发重试 |
| TG 使用 `asyncio.run()` 可能引起嵌套事件循环冲突 | 改用 `requests.post()` 调用 Telegram Bot API，移除 `python-telegram-bot` 依赖 |
| 所有通知请求无超时控制 | 通知信道统一添加 `timeout=10` |
| 发送失败调用方无感知 | `send_message` 增加 `-> bool` 返回值（当前仅预留，不修改调用方） |
| 配置不完整的渠道静默失败 | 增加配置完整性前置校验，不完整则 warning 并跳过 |

**配置完整性定义：**
- TG：`push_method="TG"` 且 `telegram_bot_token` 和 `channel_id` 均非空
- DD：`push_method="DD"` 且 `dd_bot_token` 非空（`dd_bot_secret` 可选）
- BARK：`push_method="BARK"` 且 `bark_url` 非空
- ANPUSH：`push_method="ANPUSH"` 且 `anpush_token` 非空

**tenacity 装饰器配置：**
```python
_notify_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(
        (requests.exceptions.RequestException, ConnectionError, TimeoutError)
    ),
)
```

### 3.2 登录成功率改进

| 问题 | 改进方案 |
|------|---------|
| `qfnu_login` 无任何重试 | 新增 `login_with_retry()` 函数，3 次重试 + 指数退避 (1s, 2s, 4s) |
| `TokenManager.get_token()` 登录失败直接抛异常 | 改为调用 `login_with_retry()`，3 轮均失败才抛 `AuthenticationError` |
| 无请求级超时容错 | 统一使用 `timeout=30`（与当前值一致，**不降低**） |
| 验证码识别偶尔失败 | `_do_solve_slider_captcha` 保持 5 轮不变（改进检测精度而非增加轮数） |
| 无 Session 级重试 | `_get_salt_and_execution()` 增加 3 次重试，间隔 0.5s |

**重试嵌套说明（3 层）：**
```
TokenManager.get_token()           # 第 1 层：发现过期后调用 qfnu_login
  └─ login_with_retry()            # 第 2 层：3 次重试 + 指数退避 1s, 2s, 4s
       └─ qfnu_login()
            └─ _get_bearer_token()
                 └─ _get_ids_token()
                      └─ _get_salt_and_execution()  # 第 3 层：3 次重试 + 0.5s 间隔
```
最坏情况最大请求量：3 × 3 = 9 次 IDS 请求（`_get_salt_and_execution` 的 3 次是快速 GET 重试，不计入完整的登录流程重试计数）

## 4. 具体改动清单

### 文件: `py/notify/notify.py`
```diff
- import asyncio                         # 删除（TG 不再需要）
- from telegram import Bot               # 删除（TG 改用 requests）
+ from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
+ _notify_retry = retry(...)             # 新增装饰器配置
- def send_message(config, message, title):      # 返回值：None
+ def send_message(config, message, title) -> bool:  # 返回值：bool
-  TG 分支: asyncio.run(_send_telegram(...))
+  TG 分支: _send_telegram_requests(...)  # 改用 requests.post()
+ 各入口增加配置完整性校验
- _dingtalk(): requests.post() 无 timeout
+ _dingtalk(): requests.post(timeout=10)
- _send_bark(): requests.get() 无 timeout
+ _send_bark(): requests.get(timeout=10)
- _send_anpush(): 忽略响应
+ _send_anpush(): 校验响应状态码，非 2xx 抛出异常
+ 所有 _send_* 统一返回 bool
```

### 文件: `py/auth/login.py`
```diff
+ def _login_with_retry(session, username, password):
+     """3 次重试 + 指数退避"""
- _do_solve_slider_captcha(): range(5)    # 5 轮
+ _do_solve_slider_captcha(): range(5)    # ★ 保持 5 轮不变
- _get_salt_and_execution(): 单次 GET
+ _get_salt_and_execution(): 3 次重试 + time.sleep(0.5) 间隔
```

### 文件: `py/auth/token.py`
```diff
+ _MAX_LOGIN_RETRIES = 3
  get_token():
-    name, token = qfnu_login(...)
+    name, token = _login_with_retry(session, ...)  # 含 3 次重试 + 指数退避
```

### 文件: `requirements.txt`
```diff
- python-telegram-bot                    # 删除
+ tenacity                               # 新增
```

### 文件: `tests/test_notify.py`
```diff
- @patch("notify.notify.asyncio.run")
- def test_dispatch_tg(self, mock_run, ...): ...
+ @patch("notify.notify.requests.post")
+ def test_dispatch_tg(self, mock_post, ...): ...

- class TestTelegram:
-     @patch("notify.notify.Bot")
-     def test_calls_bot_send_message(self, mock_bot_cls, ...): ...
+ class TestTelegram:
+     @patch("notify.notify.requests.post")
+     def test_send_message_via_requests(self, mock_post, ...): ...
```

### 文件: `py/notify/notify.py` import 清理
```diff
- import asyncio
- from telegram import Bot
```

## 5. 成功标准

1. **通知发送成功率 ≥99%**
   - 测量方法：对新实现的 `_send_*` 函数编写单元测试，mock 网络异常场景，验证 3 次重试逻辑正确工作
   - 持续观察：GitHub Actions 运行 7 天，日志中无通知发送失败的 error 日志
2. **登录成功率 ≥99%**
   - 验证方法：`pytest tests/` 全部通过
   - 持续观察：GitHub Actions 中签到/签退工作流连续 7 天无 `AuthenticationError` 或 "获取 token 失败" 日志
3. **回归验证**
   - `pytest tests/` 全部通过（含 `test_notify.py`、`test_check_in.py`、`test_get_seat.py`、`test_sign_out.py` 等）

## 6. 回退方案

```bash
git checkout master -- py/notify/notify.py py/auth/login.py py/auth/token.py requirements.txt tests/test_notify.py
```
然后手动检查是否有未跟踪的变更残留。

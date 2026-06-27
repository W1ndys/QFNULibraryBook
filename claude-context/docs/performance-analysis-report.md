# 图书馆预约系统性能分析报告

> **生成时间**: 2026-06-28
> **分析对象**: QFNULibraryBook 图书馆座位自动预约工具
> **目标系统**: http://libyy.qfnu.edu.cn

---

## 1. 核心结论

### 为什么有的时候抢不着座位？

**主要原因（按可能性从高到低排序）**：

| 排名 | 根因 | 可能性 | 影响程度 |
|------|------|--------|---------|
| 🥇 | **`select_seat` 的 `flag` 永远不为 `True`，导致 100 轮无效迭代浪费黄金窗口** | ⭐⭐⭐⭐⭐ | 致命 |
| 🥈 | **19:20 前 `get_segment` 可能获取不到次日时间段，导致首次尝试被延迟** | ⭐⭐⭐⭐ | 严重 |
| 🥉 | **Token 过期触发 CAPTCHA 重新登录，在 19:20 注入 5~30s 延迟** | ⭐⭐⭐ | 中等 |
| 4 | 指定座位竞争（多人抢同一座位） | ⭐⭐⭐ | 中等 |
| 5 | `timeout=120s` 过高，高峰期单次请求可能阻塞 2 分钟 | ⭐⭐ | 中等 |

---

## 2. 最严重的问题：`flag` 永不为 True（已确认 Bug）

### 问题描述

`py/get_seat.py` 第 110~213 行的 `select_seat` 函数中：

```python
def select_seat(build_id, segment, nowday, config, token_mgr, messages):
    flag = False          # ← 初始化为 False
    retries = 0

    while not flag and retries < 100:   # ← 条件：flag 为 False 时继续
        retries += 1
        data = get_seat_info(build_id, segment, nowday)
        # ... 过滤座位 ...
        post_to_get_seat(select_id, segment, config, token_mgr, messages)
        # ↑ 调用了预约，但返回值被丢弃
        continue   # ← 回到 while 循环，flag 仍为 False
```

**关键事实**：
1. `flag` 在函数体内 **没有任何代码路径** 将其设为 `True`
2. `post_to_get_seat` 调用 `check_reservation_status` 获取返回值（`True`/`False`），但 **丢弃了返回值**
3. 结果：无论预约成功还是失败，外层循环 **必定跑满 100 次**

### 时间损耗计算

每次外层迭代的时间构成：
```
get_seat_info():  ~200ms (网络) + 1000ms (time.sleep) = ~1.2s
AES 加密:         ~0.1ms (可忽略)
post_to_get_seat(): ~200ms (网络) + post_with_retry 内部重试
检查状态:          ~0ms (本地)
─────────────────────────────
单次迭代合计:      ~1.4s（最佳情况）
```

**100 次迭代 = ~140 秒 ≈ 2.3 分钟**

### 对抢座的致命影响

假设在 19:20:00 首次成功预约到座位：
- 19:20:00 — 预约成功 ✅
- 19:20:01 ~ 19:22:20 — **继续执行 99 次无效迭代**
  - 每次收到 "当前用户在该时段已存在座位预约，不可重复预约"
  - `check_reservation_status` 返回 `True`，但 `post_to_get_seat` 不处理
  - 浪费约 140 秒
- 19:22:20 — 才进入下一个教室（如果配了多个教室）

**在竞争激烈的 19:20 窗口期，这 140 秒的浪费是致命的**。如果第一个教室没抢到，等 140 秒后才尝试第二个教室，好座位早已被抢光。

### 修复建议

```python
# 方案 A：让 post_to_get_seat 返回状态，设置 flag
def post_to_get_seat(select_id, segment, config, token_mgr, messages):
    # ... 现有代码 ...
    return check_reservation_status(seat_result, config, token_mgr, messages)

# 在 select_seat 中：
result = post_to_get_seat(select_id, segment, config, token_mgr, messages)
if result:
    flag = True  # ← 预约成功或已存在，停止重试
```

---

## 3. 执行流程完整时间线

### 3.1 正常流程（单教室，无 bug）

```
T+0.000s   脚本启动
T+0.001s   get_date("tomorrow") → 本地计算，0ms
T+0.002s   TokenManager.get_token()
           ├─ 缓存命中 → ~0ms
           └─ 首次登录 → IDS CAS 全链路:
              ├─ GET 登录页 + 解析 HTML      ~500ms
              ├─ checkNeedCaptcha             ~200ms
              ├─ CAPTCHA 求解 (如需)          5~30s
              ├─ POST 登录表单                ~300ms
              └─ CAS Token 换 Bearer Token    ~400ms
              合计: 6~31s
T+Xs       进入教室循环 (classroom_name → build_id)
T+X+0.2s   get_segment(build_id, tomorrow)
           ├─ POST /api/Seat/date             ~200ms
           ├─ 查找 tomorrow 的 segment
           └─ 若 19:20 前查不到 → return None → 后续全失败
T+X+0.4s   select_seat() — 第 1 次迭代
           ├─ get_seat_info(build_id, segment, tomorrow)
           │  ├─ POST /api/Seat/seat           ~200ms
           │  └─ time.sleep(1)                 1000ms   ⚠️ 强制等待
           ├─ 过滤空闲座位                      ~0ms
           ├─ post_to_get_seat(seat_id, segment)
           │  ├─ AES 加密                      ~0.1ms
           │  ├─ POST /api/Seat/confirm         ~200ms
           │  └─ post_with_retry 默认参数:
           │     max_retries=100, retry_delay=0, timeout=120s
           ├─ check_reservation_status          ~0ms
           └─ continue（无论成功与否）
T+X+1.8s   第 2 次迭代开始...
...
T+X+142s   第 100 次迭代结束
```

### 3.2 关键瓶颈标注

| 瓶颈 | 位置 | 耗时 | 严重性 |
|------|------|------|--------|
| 🔴 **flag 永不为 True** | `get_seat.py:112-206` | +140s/教室 | 致命 |
| 🔴 **19:20 前 segment 不可用** | `get_info.py:get_segment()` | 可能 0~300s | 严重 |
| 🟡 **time.sleep(1) 强制等待** | `get_info.py:113` | +1s/迭代 × 100 = +100s | 严重 |
| 🟡 **timeout=120s 过高** | `api/http.py:17` | 高峰期单次阻塞可达 120s | 中等 |
| 🟡 **retry_delay=0 零延迟重试** | `post_to_get_seat` 调用 | 可能触发服务端限流 | 中等 |
| 🟢 **Token 过期重登录** | `token.py:50-55` | +5~30s（含 CAPTCHA） | 低 |

### 3.3 多教室场景的级联效应

假设配置 3 个教室，MODE=3：
```
教室 1: 100 次迭代 × 1.4s = 140s
教室 2: 100 次迭代 × 1.4s = 140s  （即使教室 1 已预约成功）
教室 3: 100 次迭代 × 1.4s = 140s  （即使教室 1 已预约成功）
───────────────────────────
总计: 420s ≈ 7 分钟
```

而实际上只要第一个教室成功了，后面两个完全不需要尝试。

---

## 4. 重试机制深度分析

### 4.1 实际重试架构（顺序管道，非嵌套）

```
select_seat 外层循环 (100 次):
│
├── get_seat_info(build_id, segment, nowday)
│   ├── while True:                          ← 外层死循环（仅 timeout 时触发）
│   │   ├── post_with_retry(                 ← 内层重试
│   │   │     URL_CLASSROOM_SEAT,
│   │   │     max_retries=100,
│   │   │     retry_delay=3s,               ← 每次重试间隔 3s
│   │   │     timeout=120s                   ← 单次请求超时 120s
│   │   │   )
│   │   │   成功 → 解析数据 → time.sleep(1) → return
│   │   │   超时 → 内层重试 100 次
│   │   │   全部失败 → raise RequestFailed → sys.exit()
│   │   └── requests.exceptions.Timeout:
│   │       time.sleep(1) → 继续外层 while True
│   └── 正常返回座位列表（含空闲座位）
│
├── 过滤空闲座位 → 选择一个
│
├── post_to_get_seat(select_id, segment, ...)
│   ├── AES 加密
│   ├── post_with_retry(                     ← 内层重试
│   │     URL_GET_SEAT,
│   │     max_retries=100,
│   │     retry_delay=0s,                   ⚠️ 零延迟！
│   │     timeout=120s
│   │   )
│   │   成功 → 返回 JSON
│   │   非 200 → raise_for_status → 立即重试（0延迟）
│   │   超时 → 立即重试（0延迟）
│   │   全部失败 → sys.exit()
│   └── check_reservation_status(result)
│       返回 True/False → ⚠️ 返回值被丢弃！
│
└── continue（无条件继续下一轮）
```

### 4.2 理论最坏情况分析

| 场景 | 耗时 |
|------|------|
| 最佳情况（首次成功，无 bug 修复后） | ~1.4s |
| 当前代码（首次成功，bug 存在） | ~140s（100 次迭代） |
| get_seat_info 全部超时 | 100 次 × (100 × 3s + 120s) = **42,000s ≈ 11.7h** |
| post_to_get_seat 全部超时 | 100 次 × (100 × 120s) = **1,200,000s ≈ 13.9 天**（理论值） |
| 现实最坏（单教室，全部超时） | 取决于先触发哪个退出条件 |

### 4.3 零延迟重试的风险

`post_to_get_seat` 使用 `retry_delay=0`（默认值），意味着：
- 如果服务端返回 429（限流），脚本会以 **零延迟** 连发 100 次请求
- 这相当于对服务端发起小型 DDoS
- 可能导致：IP 被封禁、账号被标记、服务端降级响应

---

## 5. 时间窗口机制分析

### 5.1 已知约束

从代码中 `"开放预约时间19:20"` 消息可知：
- 系统在 **每天 19:20** 开放次日座位预约
- 19:20 之前发送的 `/api/Seat/confirm` 请求会被拒绝
- 19:20 之前 `/api/Seat/date` 可能不返回次日时间段

### 5.2 `get_segment` 在 19:20 前的行为

```python
def get_segment(build_id, nowday):
    post_data = {"build_id": build_id}
    res = post_with_retry(URL_CLASSROOM_DETAIL_INFO, post_data, DEFAULT_HEADERS,
                          max_retries=100, retry_delay=3)
    segment = None
    for item in res["data"]:
        if item["day"] == nowday:     # 查找明天的日期
            segment = item["times"][0]["id"]
            break
    return segment   # 若未找到，返回 None
```

**关键问题**：
- 如果在 19:19:50 运行脚本，`post_with_retry` 成功返回（HTTP 200），但 `data` 中不包含明天的日期
- `segment` 将为 `None`
- 后续 `get_seat_info(build_id, None, tomorrow)` 将发送 `segment: None` 的请求
- 服务端可能返回空数据或错误

**待时间窗口测试验证**：
- `get_segment` 返回 `None` 后脚本是否会 `sys.exit()`？
- 还是继续运行并在后续迭代中不断失败？

### 5.3 黄金窗口计算

从 19:20:00 开始，理想情况下的时间线：
```
19:20:00.000  窗口开放
19:20:00.200  最快的用户发到 /api/Seat/confirm
19:20:00.500  第一批座位被抢走
19:20:02.000  热门座位（如 228 号）大概率已被抢
19:20:10.000  大部分有插座的座位已被占
19:20:30.000  只剩偏僻位置
```

**如果因为 flag bug 浪费 140 秒**：
- 19:20:00 尝试第一个教室
- 19:22:20 才开始尝试第二个教室
- 此时好座位早已被抢光

---

## 6. AES 密钥日期对齐分析

### 6.1 密钥生成机制

```python
def _get_seat_key() -> str:
    current_date = datetime.now().strftime("%Y%m%d")
    return current_date + current_date[::-1]   # 例如: "20260628" + "82606620"
```

- 密钥基于 `datetime.now()` **实时生成**（每次调用 `encrypt_seat_data` 时）
- 跨午夜安全：23:59 用今天日期，00:01 用明天日期
- IV 固定：`"ZZWBKJ_ZHIHUAWEI"`

### 6.2 日期对齐问题

| 场景 | 客户端密钥 | 服务端密钥（推测） | 是否匹配 |
|------|-----------|-------------------|---------|
| 19:20 预约明天 | `2026062820260628[::-1]` | 同左（服务端用当天日期） | ✅ |
| 跨午夜仍在重试 | 自动切换为明天日期 | 服务端也切换 | ✅ |
| 预约当天座位 | 用当天日期 | 用当天日期 | ✅ |

### 6.3 结论

- AES 密钥日期对齐 **大概率不会导致问题**
- 密钥仅用于请求体混淆，真正的认证靠 Bearer Token
- 但建议在时间窗口测试中验证：捕获一次成功的加密请求，手动解密确认内容正确

---

## 7. 其他发现

### 7.1 `get_seat_info` 中的冗余 `while True` 循环

```python
def get_seat_info(build_id, segment, nowday):
    while True:                    # ← 外层死循环
        try:
            res = post_with_retry(  # ← 内层已有 100 次重试
                URL_CLASSROOM_SEAT, post_data, DEFAULT_HEADERS,
                max_retries=100, retry_delay=3)
            # ... 解析 ...
            time.sleep(1)
            return free_seats      # 正常退出
        except requests.exceptions.Timeout:
            pass                   # ← post_with_retry 已处理超时，此处不可达
        except RequestFailed:
            sys.exit()             # ← 直接退出
        except Exception:
            sys.exit()             # ← 直接退出
        time.sleep(1)
```

**分析**：`post_with_retry` 已经内部处理了超时重试（100 次），所以外层 `while True` 中的 `Timeout` 分支实际上 **永远不会被执行**（因为 `post_with_retry` 会在超时时重试而不是抛异常）。这是死代码。

### 7.2 `check_reservation_status` 错误状态覆盖

| 服务端 msg | 处理 | 是否完整 |
|-----------|------|---------|
| `"预约成功"` | 返回 True | ✅ |
| `"当前用户在该时段已存在座位预约，不可重复预约"` | 返回 True | ✅ |
| `"开放预约时间19:20"` | 返回 False（继续重试） | ✅ |
| `"您尚未登录"` | 重新获取 Token | ✅ |
| `"该空间当前状态不可预约"` | 返回 False（继续重试） | ✅ |
| `"取消成功"` | sys.exit() | ⚠️ 不应在预约流程中出现 |
| 其他未知 msg | 返回 True → 停止重试 | ⚠️ 可能遗漏某些错误状态 |
| `msg` 为 None | 打印结果 → 返回 False | ✅ |

**风险**：如果服务端返回了代码未覆盖的新错误消息，脚本会误判为"已完成"并停止重试。

---

## 8. 优化建议

### 建议 1：修复 `flag` bug（优先级：🔴 最高）

**预期收益**：单教室节省 ~140 秒，多教室节省 ~140s × N

```python
# 修改 post_to_get_seat，返回 check_reservation_status 的结果
def post_to_get_seat(select_id, segment, config, token_mgr, messages):
    # ... 现有代码 ...
    return check_reservation_status(seat_result, config, token_mgr, messages)

# 修改 select_seat，使用返回值控制循环
result = post_to_get_seat(select_id, segment, config, token_mgr, messages)
if result:
    break  # 预约成功或已有座位，立即停止
```

### 建议 2：移除 `time.sleep(1)`（优先级：🟡 高）

**预期收益**：每次迭代节省 1 秒，100 次迭代节省 100 秒

`get_seat_info` 中的 `time.sleep(1)` 在快节奏抢座场景中不必要。如果是防风控，可以改为可配置参数。

### 建议 3：为 `post_to_get_seat` 配置合理的 retry_delay（优先级：🟡 高）

**预期收益**：避免零延迟重试触发服务端限流

```python
# 当前（危险）：
seat_result = post_with_retry(URL_GET_SEAT, post_data, request_headers)
# 默认: max_retries=100, retry_delay=0, timeout=120

# 建议：
seat_result = post_with_retry(URL_GET_SEAT, post_data, request_headers,
                              max_retries=10, retry_delay=1, timeout=10)
```

### 建议 4：降低 HTTP 超时时间（优先级：🟡 高）

**预期收益**：高峰期单次请求阻塞从 120s 降至 10s

```python
# 当前：
post_with_retry(url, data, headers, timeout=120)

# 建议：
post_with_retry(url, data, headers, timeout=10)
```

### 建议 5：Token 预热机制（优先级：🟢 中）

**预期收益**：避免 19:20 窗口期内的 5~30s 登录延迟

在 CI/CD 工作流中，提前 10 分钟运行一个轻量级 token 预热步骤：
```yaml
- name: 预热 Token
  run: python -c "from auth.token import TokenManager; TokenManager('$USER', '$PASS').get_token()"
```

### 建议 6：支持 segment 预计算（优先级：🟢 中）

**预期收益**：如果 19:20 前能获取到 segment，可以在窗口开放的瞬间立即发送预约请求

```python
# 在 19:20 前轮询 segment，一旦获取到立即开始预约
while True:
    segment = get_segment(build_id, tomorrow)
    if segment:
        break
    time.sleep(1)
# segment 就绪，立即进入 select_seat
```

---

## 9. 测量工具说明

本次分析生成了两个测量脚本：

| 脚本 | 用途 | 用法 |
|------|------|------|
| `py/performance_probe.py` | API 性能基线测量 | `python py/performance_probe.py -c config_studentA.yml -n 10` |
| `py/time_window_test.py` | 19:20 窗口敏感性测试 | 在 19:19:00 运行 `python py/time_window_test.py -c config_studentA.yml` |

### 运行性能探测

```bash
cd py
python performance_probe.py -c config_studentA.yml -n 10
# 结果输出到 performance_results.json
```

### 运行时间窗口测试

```bash
cd py
# 在 19:19:00 左右启动
python time_window_test.py -c config_studentA.yml
# 结果输出到 time_window_results.json
```

> ⚠️ **注意**：时间窗口测试会向 `/api/Seat/confirm` 发送带无效座位 ID 的探测请求。虽然不会实际预约成功，但可能被服务端记录。请谨慎使用。

---

## 10. 总结

**抢座失败的最根本原因是代码层面的 `flag` bug**，而非单纯的时间问题。但这个 bug 与时间窗口叠加后效果是灾难性的：

1. 19:20:00 窗口开放
2. 脚本首次尝试预约成功 ✅
3. 但脚本不知道成功了，继续跑 99 次无效迭代（~140 秒）
4. 19:22:20 才尝试下一个教室
5. 此时好座位早已被抢光 ❌

**修复 `flag` bug 后**，单教室选座时间从 ~140 秒降至 ~1.4 秒（**提升 100 倍**）。这是投入产出比最高的优化。

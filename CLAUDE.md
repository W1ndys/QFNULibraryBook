# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

曲阜师范大学图书馆座位自动预约工具（QFNULibraryBook）。自动化完成自习室座位的预约、签到、签退三阶段流程，目标系统为 `http://libyy.qfnu.edu.cn`。所有日志、注释、配置值均使用中文。

## Commands

```bash
# 安装依赖
pip install -r requirements.txt

# 预约座位（读取 py/config.yml）
python py/get_seat.py

# 签到（支持指定配置文件）
python py/check_in.py -c config_studentA.yml

# 签退
python py/sign_out.py -c config_studentA.yml

# 管理员：抓取座位信息并保存到 json/seat_info/
python py/get_seat_info_ForAdmin.py
```

无测试套件，无 lint 配置。

## Architecture

### 三阶段工作流

1. **预约** (`py/get_seat.py`) — 读取 YAML 配置，遍历配置的自习室，按模式筛选座位，AES 加密后 POST 到 `/api/Seat/confirm`，每个自习室最多重试 100 次
2. **签到** (`py/check_in.py`) — AES 加密 `{"method":"checkin"}`，POST 到 `/api/Seat/touch_qr_books`
3. **签退** (`py/sign_out.py`) — 查询当前"使用中"座位，POST 到 `/api/Space/checkout`

### 认证链

`get_bearer_token.py` → `get_ids_token.py`（IDS 登录，BeautifulSoup 抓取登录页提取 salt/execution 字段）→ `ids_utils/passwd_encrypt.py`（AES-CBC 加密密码）→ CAS token 换取 bearer token。bearer token 有效期 1.5 小时。

### 核心工具模块 (`py/get_info.py`)

包含 `classroom_id_mapping`（18 个自习室名称→ID 映射）、日期/时间段/座位查询函数、以及 AES 加密/解密函数（使用 pycryptodome，密钥由当前日期回文派生）。

### 预约模式（`get_seat.py` 中的 `MODE`）

| 模式 | 说明 |
|------|------|
| 1 | 指定 ID 范围内的有插座座位（排除 `EXCLUDE_ID`） |
| 2 | 有插座座位（任意位置，排除 `EXCLUDE_ID`） |
| 3 | 完全随机选座（最快，成功率最高） |
| 4 | 指定座位优先（如 228 号） |

### 消息推送

所有入口脚本共享 4 种推送方式，由配置文件 `PUSH_METHOD` 字段控制：`TG`（Telegram）、`DD`（钉钉，HMAC-SHA256 签名）、`BARK`、`ANPUSH`。通知函数在各脚本中重复定义。

### CI/CD

GitHub Actions 两个工作流定时执行：
- `check_in.yml` — 每天 00:20 UTC（北京时间 08:20）签到
- `sign_out.yml` — 每天 13:30 UTC（北京时间 21:30）签退

均支持 `workflow_dispatch` 手动触发，遍历 `config_studentA/B/C.yml` 多用户配置。

### 关键 API 端点

均位于 `http://libyy.qfnu.edu.cn/api/`：
- `/Seat/date` — 获取可用时间段
- `/Seat/seat` — 获取座位可用性
- `/Seat/confirm` — 预约（AES 加密请求体）
- `/Seat/touch_qr_books` — 签到（AES 加密请求体）
- `/Member/seat` — 查询当前用户座位
- `/Space/checkout` — 签退

## Key Technical Details

- **AES 加密混合使用两个库**：`get_info.py` 使用 `pycryptodome`（`Crypto`），`check_in.py` 和 `passwd_encrypt.py` 使用 `cryptography`（`cryptography.hazmat`）。修改加密逻辑时注意区分。
- **配置文件**位于 `py/` 目录下，`config.yml` 为模板，`config_student*.yml` 用于 CI 多用户场景。
- **座位数据**：`json/seat_info/` 下的 JSON 文件为静态座位布局快照，由 `get_seat_info_ForAdmin.py` 生成。
- **全局变量**：代码大量使用全局变量管理 token、时间戳等状态。
- **提交规范**：遵循宽松的 conventional commit 风格（`feat:`、`fix:`、`ci:`、`refactor:`、`chore:`、`docs:`）。

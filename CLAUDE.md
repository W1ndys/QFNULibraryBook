# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

曲阜师范大学图书馆座位自动预约工具（QFNULibraryBook）。自动化完成自习室座位的预约、签到、签退三阶段流程，目标系统为 `http://libyy.qfnu.edu.cn`。所有日志、注释、配置值均使用中文。

## Commands

```bash
# 安装依赖
pip install -r requirements.txt

# 预约座位
python src/get_seat.py -c configs/studentA.yml

# 签到
python src/check_in.py -c configs/studentA.yml

# 签退
python src/sign_out.py -c configs/studentA.yml

# 多用户并发
python scripts/run_all.py seat -u configs/users.yml

# 管理员：抓取座位信息
python src/get_seat_info_ForAdmin.py
```

无测试套件，无 lint 配置。

## Architecture

### 目录结构

```yaml
configs/                  # 用户级 YAML 配置文件
  - studentA.yml          # 学生 A 配置
  - studentB.yml          # 学生 B 配置
  - template.yml          # 配置模板
  - users.yml             # 多用户管理配置
scripts/                  # 工具/探测脚本
  - run_all.py            # 多用户并发入口
  - performance_probe.py  # API 性能探测
  - time_window_test.py   # 预约窗口测试
  - performance_results.json
src/
├── auth/               # 登录 + Token 管理
│   ├── login.py        # IDS CAS 登录 + 滑块验证码 + Bearer Token 获取
│   └── token.py        # TokenManager 类（自动缓存和过期管理）
├── config/
│   └── config.py       # AppConfig 数据类（替代全局变量）
├── notify/
│   └── notify.py       # 统一消息推送（TG/DD/Bark/AnPush）
├── crypto/
│   └── aes.py          # 统一 AES 加密（仅 pycryptodome）
├── api/
│   ├── constants.py    # API URL 和默认请求头
│   ├── exceptions.py   # 自定义异常
│   └── http.py         # 带重试的 HTTP 请求工具
├── classrooms.py       # 教室映射 + EXCLUDE_ID
├── get_seat.py         # 入口：预约
├── check_in.py         # 入口：签到
├── sign_out.py         # 入口：签退
├── get_info.py         # 工具：座位查询
└── get_seat_info_ForAdmin.py  # 管理员工具
data/                     # 静态座位布局数据
  └── seat_info/          # 座位快照（JSON）
```

### 三阶段工作流

1. **预约** (`src/get_seat.py`) — 读取 YAML 配置，遍历配置的自习室，按模式筛选座位，AES 加密后 POST 到 `/api/Seat/confirm`，每个自习室最多重试 100 次
2. **签到** (`src/check_in.py`) — AES 加密 `{"method":"checkin"}`，POST 到 `/api/Seat/touch_qr_books`
3. **签退** (`src/sign_out.py`) — 查询当前"使用中"座位，POST 到 `/api/Space/checkout`

### 认证链

`src/auth/login.py` 实现完整的登录流程：正则提取登录页参数 → 滑块验证码破解（OpenCV 边缘检测 + 模板匹配，三阶段搜索）→ AES-CBC 加密密码 → IDS CAS 登录 → CAS Token 换取 Bearer Token。`src/auth/token.py` 的 `TokenManager` 类封装 token 获取和 1.5 小时缓存。

### 核心工具模块 (`src/get_info.py`)

包含日期/时间段/座位查询函数。教室映射（19+1 个别名）在 `src/classrooms.py` 中统一管理，AES 加密在 `src/crypto/aes.py` 中统一管理。

### 预约模式（`get_seat.py` 中的 `MODE`）

| 模式 | 说明 |
|------|------|
| 1 | 指定 ID 范围内的有插座座位（排除 `EXCLUDE_ID`） |
| 2 | 有插座座位（任意位置，排除 `EXCLUDE_ID`） |
| 3 | 完全随机选座（最快，成功率最高） |
| 4 | 指定座位优先（如 228 号） |

### 消息推送

`src/notify/notify.py` 统一实现 4 种推送方式，由配置文件 `PUSH_METHOD` 字段控制：`TG`（Telegram）、`DD`（钉钉，HMAC-SHA256 签名）、`BARK`、`ANPUSH`。调用签名：`send_message(config, message, title)`。

### 关键 API 端点

均位于 `http://libyy.qfnu.edu.cn/api/`，URL 常量定义在 `src/api/constants.py`：
- `/Seat/date` — 获取可用时间段
- `/Seat/seat` — 获取座位可用性
- `/Seat/confirm` — 预约（AES 加密请求体）
- `/Seat/touch_qr_books` — 签到（AES 加密请求体）
- `/Member/seat` — 查询当前用户座位
- `/Space/checkout` — 签退

## Key Technical Details

- **AES 加密统一使用 pycryptodome**：`src/crypto/aes.py` 提供 `encrypt_seat_data()`（日期回文密钥）和 `encrypt_login_data()`（随机前缀 + 随机 IV）。
- **配置管理**：`src/config/config.py` 的 `AppConfig` 数据类替代全局变量，通过 `AppConfig.from_yaml(config_file)` 加载。用户配置文件位于 `configs/` 目录下；Python 配置模块在 `src/config/`。
- **座位数据**：`data/seat_info/` 下的 JSON 文件为静态座位布局快照，由 `get_seat_info_ForAdmin.py` 生成。
- **提交规范**：遵循宽松的 conventional commit 风格（`feat:`、`fix:`、`ci:`、`refactor:`、`chore:`、`docs:`）。

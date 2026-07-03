# QFNULibraryBook

曲阜师范大学图书馆座位自动预约程序

## 项目简介

自动化完成自习室座位的预约、签到、签退三阶段流程，支持多用户、多教室、多推送渠道。目标系统为 `http://libyy.qfnu.edu.cn`。

## 免责声明

本脚本仅供学习使用，使用本脚本预约图书馆座位后，请合理、有效地利用座位时间进行学习，以免占用其他有需求同学的学习资源。

**注意事项：**

1. 使用本脚本预约座位后，请按时前往图书馆学习。不得恶意占用座位或空占资源。
2. 本项目不对因违规使用或不当操作而导致的任何后果承担责任。
3. 请自觉遵守图书馆的相关规定，合理使用学习资源，共同维护良好的学习环境。

本项目为公益性质，任何滥用行为与开发者无关。开发者保留在必要时对项目进行调整或关闭的权利。

## 功能特点

- **多种预约模式**：4 种模式（指定范围+插座、插座优先、完全随机、指定座位）
- **自动签到签退**：支持自动签到和签退
- **滑块验证码破解**：OpenCV 边缘检测 + 三阶段搜索策略
- **多渠道通知**：钉钉、Telegram、Bark、AnPush
- **多用户支持**：通过 `-c` 参数指定不同配置文件
- **CI/CD**：GitHub Actions 定时签到签退

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

编辑 `configs/template.yml`（模板）或创建 `configs/studentX.yml`（多用户），填入：

- `USERNAME` / `PASSWORD`：学号和密码
- `PUSH_METHOD`：通知方式（`TG` / `DD` / `BARK` / `ANPUSH`）
- 对应通知渠道的 token/密钥
- `CLASSROOMS_NAME`：要预约的自习室列表
- `MODE`：选座模式（1-4）
- `DATE`：预约日期（`today` / `tomorrow`）

### 运行

```bash
# 预约座位
python src/get_seat.py -c configs/studentA.yml

# 签到
python src/check_in.py -c configs/studentA.yml

# 签退
python src/sign_out.py -c configs/studentA.yml

# 管理员：抓取座位信息快照
python src/get_seat_info_ForAdmin.py -c configs/template.yml --classrooms "东校区图书馆-三楼自修区"
```

## 预约模式

| 模式 | 说明 |
|:-----|:-----|
| 1 | 指定 ID 范围内的有插座座位（排除无插座座位） |
| 2 | 有插座座位（任意位置） |
| 3 | 完全随机选座（最快，成功率最高） |
| 4 | 指定座位优先（如 228 号） |

## 支持的自习室

| 教室名称 | 位置 |
|:---------|:-----|
| 西校区图书馆-二层/三层/四层自习室 | 西校区图书馆 |
| 西校区图书馆-五层静音自习室 | 西校区图书馆 |
| 西校区东辅楼-二层/三层自习室 | 西校区东辅楼 |
| 东校区图书馆-一楼自修区（朗读空间） | 东校区图书馆 |
| 东校区图书馆-三楼自修区 | 东校区图书馆 |
| 东校区图书馆-四层中文现刊室 | 东校区图书馆 |
| 综合楼-801/803/804/805/806自习室 | 综合楼 |
| 行政楼-四层东区/中区/西区自习室 | 行政楼 |
| 电视台楼-二层自习室 | 电视台楼 |

## 项目结构

```
src/
├── auth/           # 登录认证（滑块验证码 + CAS + Token 管理）
├── config/         # 配置管理（AppConfig 数据类）
├── notify/         # 消息推送（TG/DD/Bark/AnPush）
├── crypto/         # AES 加密（pycryptodome）
├── api/            # HTTP 工具和 URL 常量
├── classrooms.py   # 教室映射和排除座位 ID
├── get_seat.py     # 预约入口
├── check_in.py     # 签到入口
├── sign_out.py     # 签退入口
└── get_info.py     # 座位查询工具
data/seat_info/     # 教室座位布局快照
.github/workflows/  # CI 定时任务
```

CI/CD
-----

此前已通过 GitHub Actions 自动执行签到和签退（已移除），当前可手动运行。

## 贡献者

- [@W1ndys](https://github.com/W1ndys)：二次开发者
- [@sakurasep](https://github.com/sakurasep)：原作者
- [@nakaii-002](https://github.com/nakaii-002)：签到功能贡献者

## 开源许可

CC BY-NC 4.0 — 基于 [上杉九月](https://github.com/sakurasep) 的 [qfnuLibraryBook](https://github.com/sakurasep/qfnuLibraryBook) 二次开发。

# 用户指令记忆

本文件记录了用户的指令、偏好和教导，用于在未来的交互中提供参考。

## 格式

### 用户指令条目
用户指令条目应遵循以下格式：

[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

### 项目知识条目
Agent 在任务执行过程中发现的条目应遵循以下格式：

[项目知识摘要]
- Date: [YYYY-MM-DD]
- Context: Agent 在执行 [具体任务描述] 时发现
- Category: [代码结构|代码模式|代码生成|构建方法|测试方法|依赖关系|环境配置]
- Instructions:
  - [具体的知识点，逐行描述]

## 去重策略
- 添加新条目前，检查是否存在相似或相同的指令
- 若发现重复，跳过新条目或与已有条目合并
- 合并时，更新上下文或日期信息
- 这有助于避免冗余条目，保持记忆文件整洁

## 条目

### 项目整体架构
- Date: 2026-04-18
- Context: Agent 在阅读全部代码整理接口文档时发现
- Category: 代码结构
- Instructions:
  - 项目是曲阜师范大学图书馆座位预约脚本（QFNULibraryBook）
  - 主要代码在 `py/` 目录下，`v3.1/` 是优化版本，`old_py/` 是旧版本
  - 登录流程分两阶段：先通过 IDS 统一认证获取 CAS ticket，再用 ticket 换取图书馆 Bearer Token
  - 预约数据通过 AES-CBC 加密传输，密钥基于当前日期生成（YYYYMMDD + 回文），IV 固定为 `ZZWBKJ_ZHIHUAWEI`
  - 三种预约模式：模式1（排除无插座位随机选）、模式2（指定座位范围）、模式3（全随机）
  - 图书馆预约系统基础 URL：`http://libyy.qfnu.edu.cn`
  - IDS 认证系统基础 URL：`http://ids.qfnu.edu.cn`

### 构建与运行方式
- Date: 2026-04-18
- Context: Agent 在阅读 README 和配置文件时发现
- Category: 构建方法
- Instructions:
  - Python 3.10+ 运行环境
  - 依赖安装：`pip install -r requirements.txt`
  - 配置文件：`py/config.yml`，需填写 USERNAME 和 PASSWORD
  - 支持 Telegram / Bark / Anpush / 钉钉 四种消息推送渠道
  - 支持 GitHub Actions 运行，通过 GITHUB 字段控制时区偏移

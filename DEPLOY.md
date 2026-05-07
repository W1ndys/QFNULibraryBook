# 曲阜师范大学图书馆预约程序 Docker 部署指南

## 前提条件

- 安装 Docker 和 Docker Compose
- 有一个有效的图书馆账号和密码

## 配置步骤

### 1. 配置文件设置

打开 `py/config.yml` 文件，根据注释修改以下配置项：

```yaml
# 通知渠道选择,分别代表Telegram、Bark、Anpush、钉钉
PUSH_METHOD: "DD"  # 选择通知方式，可选值：TG、ANPUSH、BARK、DD

# Telegram 相关（如果选择TG通知）
CHANNEL_ID: ""  # Telegram 频道 ID
TELEGRAM_BOT_TOKEN: ""  # Telegram Bot Token

# Bark 相关（如果选择BARK通知）
BARK_URL: ""  # Bark 推送地址
BARK_EXTRA: ""  # Bark 额外参数

# Anpush 相关（如果选择ANPUSH通知）
ANPUSH_TOKEN: ""  # Anpush Token
ANPUSH_CHANNEL: ""  # Anpush 推送频道

# 钉钉相关（如果选择DD通知）
DD_BOT_TOKEN: ""  # 钉钉机器人 Token
DD_BOT_SECRET: ""  # 钉钉机器人密钥

# 账号授权相关
USERNAME: ""  # 图书馆账号
PASSWORD: ""  # 图书馆密码

# 是否是 Github Action
GITHUB: false

# 座位ID范围
SEAT_ID:
  - 7292
  - 7315

# 自习室名称
CLASSROOMS_NAME:
  - 西校区图书馆-三层自习室
```

### 2. 构建和运行

#### 方法一：使用 docker-compose 构建运行

在项目根目录下执行以下命令：

```bash
# 构建并运行容器
docker-compose up --build

# 或者在后台运行
docker-compose up --build -d
```

#### 方法二：使用已导出的镜像

如果已经有导出的镜像文件 `qfnu-library-book.tar`，可以使用以下命令加载并运行：

```bash
# 加载镜像
docker load -i qfnu-library-book.tar

# 运行容器
docker-compose up -d
```

### 3. 运行不同的脚本

默认情况下，容器会运行 `get_seat_tomorrow_mode_1.py` 脚本。如果要运行其他脚本，可以使用以下命令：

```bash
# 运行签到脚本
docker-compose run --rm qfnu-library-book check_in.py

# 运行签退脚本
docker-compose run --rm qfnu-library-book sign_out.py

# 运行预约模式2脚本
docker-compose run --rm qfnu-library-book get_seat_tomorrow_mode_2.py

# 运行预约模式3脚本
docker-compose run --rm qfnu-library-book get_seat_tomorrow_mode_3.py
```

### 4. 查看容器状态

```bash
# 查看容器运行状态
docker-compose ps

# 查看容器日志
docker-compose logs qfnu-library-book

# 停止容器
docker-compose down
```

## 故障排除

### 1. 构建失败

如果构建失败，可能是网络问题导致依赖安装失败。请检查网络连接并重试。

### 2. 运行失败

如果运行失败，请检查以下几点：

- 配置文件是否正确填写
- 图书馆账号和密码是否正确
- 网络连接是否正常

### 3. 常见错误

- **获取 token 失败**：请检查账号密码是否正确，网络是否正常
- **未到预约时间**：脚本会在预约时间（19:20）自动启动，请耐心等待
- **重复预约**：系统检测到已经有预约，会自动停止

## 注意事项

1. 本脚本仅供学习使用，请勿恶意占用座位资源
2. 使用签到功能时请务必在合理的时间段内执行
3. 请自觉遵守图书馆的相关规定，合理使用学习资源
4. 容器运行时会自动挂载配置文件，修改配置后需要重启容器

## 版本说明

本部署方案基于项目的 `py` 目录中的脚本，适用于预约明天的座位。如果需要使用其他版本的功能，请参考项目的其他目录。
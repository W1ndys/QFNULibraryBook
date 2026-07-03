# QFNU 图书馆座位管理 Web 应用

曲阜师范大学图书馆座位签到/签退 Web 工具。

## 快速开始

```bash
# 1. 安装项目根目录依赖（滑块验证码等）
cd ..
pip install -r requirements.txt

# 2. 安装 Web 额外依赖
cd web
pip install -r requirements.txt

# 3. 启动服务
python app.py
```

浏览器打开 `http://localhost:5000`。

## 功能

- 学号/密码登录（复用 CAS 认证 + 滑块验证码自动破解）
- 一键签到
- 一键签退
- 服务端会话管理

## 技术栈

- Flask + Flask-Session
- 现有 `py/` 模块（`auth/login.py`, `check_in.py`, `sign_out.py`）

## 页面

### 登录页
- 仿 CAS 统一身份认证风格，蓝色主题
- 输入学号/工号和密码即可登录
- 底部保留账号激活、忘记密码链接

### 控制面板
- 签到按钮（绿色）
- 签退按钮（橙色）
- 操作结果实时反馈

## 注意

- 每次签到/签退都会触发完整登录流程（~2-5s 滑块破解），请耐心等待
- 密码存储在服务端 session 中，仅限个人使用

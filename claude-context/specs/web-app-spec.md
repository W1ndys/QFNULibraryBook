# QFNU Library Seat Manager — Web 应用规格

**修订**: v3（二审修订）

## 1. 目的

在项目根目录下新建 `web/` 子文件夹，创建曲阜师范大学图书馆座位管理 Web 应用。用户通过浏览器输入学号密码登录后，可一键签到、签退。

## 2. 边界

| 范围 | 说明 |
|------|------|
| **包含** | `web/` 目录下所有文件：Flask 后端 + 前端页面 + README |
| **包含** | 基于现有 `src/` 代码的 Python import（不修改 `src/`） |
| **不包含** | 修改 `src/` 下任何文件 |
| **不包含** | 预约（抢座）功能 |
| **不包含** | 用户注册、数据库、持久化存储 |
| **不包含** | 生产级部署（WSGI 服务器配置留作后续） |

## 3. 技术方案

### 3.1 架构

```
Browser (HTML/CSS/JS)
    │  POST /api/login    (学号+密码)
    │  POST /api/checkin  (签到)
    │  POST /api/signout  (签退)
    ▼
Flask (web/app.py)
    ├── sys.path.insert(0, os.path.join(__file__, '..', 'src'))  # 绝对路径
    │   from auth.login import qfnu_login
    │   from auth.token import TokenManager
    │   from config.config import AppConfig
    ▼
src/（现有代码，不动）
```

**运行方式**：`cd web && python app.py`（结果以 `cd web && python app.py` 为准，不保证从其他 CWD 运行）

### 3.2 Flask 后端

#### 初始化配置

```python
import os, sys, logging
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from flask import Flask, session, request, jsonify, render_template
from flask_session import Session
from auth.login import qfnu_login
from auth.token import TokenManager
from config.config import AppConfig
from check_in import lib_rsv
from sign_out import go_home
from api.exceptions import CheckInFailed, SignOutFailed

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
```

#### 会话管理

- 使用 **Flask-Session**（`SESSION_TYPE='filesystem'`），session 数据存服务端磁盘，cookie 只存 session ID
- 登录成功后 session 存 `username` + `password`（明文密码存服务端，仅适用于本地/可信环境）
- `TokenManager` 含 `threading.Lock` 不能 pickle → 不能存 session，改为每次请求重建
- 每次 API 请求从 session 读凭证重建 `TokenManager` + `AppConfig`

```python
def get_auth_context():
    """从 session 重建凭证上下文（每次请求调用）"""
    u = session.get('username')
    p = session.get('password')
    if not u or not p:
        return None, None
    return AppConfig(username=u, password=p, push_method=''), TokenManager(u, p)
```

> ⚠️ 每次重建 TokenManager 意味着每次签到/签退都会触发完整登录（含滑块破解约 2-5s）。
> Token 有 1.5h 有效期但当前不缓存，未来可优化为 session 中缓存 token 字符串避免重复登录。

#### API 路由

| 路由 | 方法 | 请求体 | 成功响应 | 错误响应 | 说明 |
|------|------|--------|----------|----------|------|
| `/` | GET | — | HTML | — | 根据 session 返回登录页或面板 |
| `/api/login` | POST | `{"username":"","password":""}` | `{"success":true,"name":""}` | `{"success":false,"error":"","error_code":"LOGIN_FAILED"}` 401 | `qfnu_login()`。**2-5s 滑块破解**，前端设 ≥15s 超时 |
| `/api/checkin` | POST | — | `{"success":true,"message":"签到成功"}` | `{"success":false,"error":"...","error_code":"CHECKIN_FAILED"}` 502 | `lib_rsv()` 返回 None 不报错即成功 |
| `/api/signout` | POST | — | `{"success":true,"message":"签退成功"}` | `{"success":false,"error":"...","error_code":"SIGNOUT_FAILED"}` 502 | `go_home()` 返回 True 成功，False/None 算失败 |
| `/api/status` | GET | — | `{"logged_in":true,"username":""}` | `{"logged_in":false}` 200 | 检查 session |
| `/api/logout` | POST | — | `{"success":true}` | — | 清 session |

**CSRF 防护**：前端 AJAX POST 带 header `X-Requested-With: XMLHttpRequest`，后端检查，无此 header 的 POST 返回 403。

**错误处理**：Flask 路由层统一 catch `(CheckInFailed, SignOutFailed, requests.RequestException, json.JSONDecodeError, Exception)`，全部返回统一格式 `{"success":false,"error":"","error_code":"INTERNAL_ERROR"}` HTTP 500。

### 3.3 前端页面

#### 登录页
- 复刻 CAS 样式，**移除**验证码区域、二维码、微信/QQ 登录
- 保留账号激活、忘记密码链接（指向原 CAS 页面）
- 表单：学号 + 密码 + 登录按钮
- 登录失败红色提示，点击加载态

#### 控制面板
- 欢迎（姓名）+ 签到按钮 + 签退按钮 + 登出按钮
- 成功绿色 / 失败红色
- 页脚：`抢课联系 fastjackcost880@gmail.com`

#### 美化
- 用 `premium-frontend-ui` skill

### 3.4 文件结构

```
web/
├── app.py                  # Flask 后端
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── logo.png
├── requirements.txt         # Flask>=3.0 Flask-Session>=0.8
└── README.md
```

### 3.5 依赖

```
Flask>=3.0,<4.0
Flask-Session>=0.8,<1.0
```
及现有 `requirements.txt` 中的依赖（opencv, numpy, requests, pycryptodome, yaml, tenacity）。

### 3.6 已知限制与安全说明

| 事项 | 说明 |
|------|------|
| 滑块验证码 | 每次登录 2-5s 自动破解，签到/签退会重新登录（不缓存 token） |
| 密码存储 | session 存明文密码，服务端 filesystem 存储，仅限本地/可信环境 |
| 单线程 | Flask dev server 单线程，登录时阻塞其他请求 |
| 调试图片 | `login.py` 向 `src/debug_captcha/` 写调试 PNG（已清理过该目录） |
| 无多用户隔离 | 单 Flask 实例仅适合单人使用 |

## 4. 成功标准

- [ ] `cd web && pip install -r requirements.txt && python app.py` 启动
- [ ] 浏览器 `http://localhost:5000` 显示 CAS 风格登录页
- [ ] 输入学号密码可登录，显示控制面板
- [ ] 签到按钮调用 `lib_rsv()` 并显示结果
- [ ] 签退按钮调用 `go_home()` 并显示结果
- [ ] 登录失败显示错误提示
- [ ] 页脚显示联系邮箱
- [ ] `README.md` 含完整说明
- [ ] `src/` 无文件被修改
- [ ] 无 `X-Requested-With` 的 POST 被拒

## 5. 实施步骤

1. `clone-website` skill 抓 CAS 页面
2. 创建 `web/{templates/,static/}`
3. 写 `app.py`（含以上所有 API）
4. 写前端 HTML/CSS/JS
5. 写 `README.md`
6. 推送 GitHub

## 6. 应急预案

| 异常 | 处理 |
|------|------|
| Flask 无法 import src/ 模块 | 检查 `sys.path` 的 `__file__` 解析 |
| `send_message()` 报错 | `AppConfig(push_method='')` 跳过 |
| TokenManager 不能序列化 | 已改为 session 存明文，每次重建 |
| sync 跨重启失效 | 固定 `FLASK_SECRET_KEY` 环境变量 |
| push GitHub 失败 | `git remote -v` 检查 |
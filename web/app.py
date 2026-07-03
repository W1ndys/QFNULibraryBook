"""
QFNU 图书馆座位管理 Web 应用
===============================
Flask 后端，调用 py/ 下的签到/签退模块。
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from flask import Flask, jsonify, render_template, request, session
from flask_session import Session
import requests

from api.exceptions import CheckInFailed, SignOutFailed
from auth.login import qfnu_login
from auth.token import TokenManager
from config.config import AppConfig
from check_in import lib_rsv
from sign_out import go_home

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _csrf_guard():
    """检查 POST 请求是否来自 AJAX（防 CSRF）"""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify({"success": False, "error": "CSRF 拒绝", "error_code": "CSRF_REJECTED"}), 403
    return None


def get_auth_context():
    """从 session 重建凭证上下文（每次请求调用）"""
    u = session.get("username")
    p = session.get("password")
    if not u or not p:
        return None, None
    cfg = AppConfig(username=u, password=p, push_method="")
    return cfg, TokenManager(u, p)


# ---------- 页面 ----------

@app.route("/")
def index():
    return render_template("index.html")


# ---------- API ----------

@app.route("/api/login", methods=["POST"])
def api_login():
    guard = _csrf_guard()
    if guard:
        return guard

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体为空", "error_code": "BAD_REQUEST"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "学号和密码不能为空", "error_code": "BAD_REQUEST"}), 400

    try:
        name, token = qfnu_login(username, password)
        if not token:
            return jsonify({"success": False, "error": "登录失败，请检查账号密码", "error_code": "LOGIN_FAILED"}), 401

        session["username"] = username
        session["password"] = password
        logger.info(f"用户 {username} ({name}) 登录成功")
        return jsonify({"success": True, "name": name})
    except Exception as e:
        logger.error(f"登录异常: {e}")
        return jsonify({"success": False, "error": f"登录异常: {e}", "error_code": "LOGIN_FAILED"}), 401


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    guard = _csrf_guard()
    if guard:
        return guard

    cfg, token_mgr = get_auth_context()
    if not cfg:
        return jsonify({"success": False, "error": "未登录", "error_code": "UNAUTHORIZED"}), 401

    try:
        lib_rsv(cfg, token_mgr)
        logger.info(f"[{cfg.username}] 签到成功")
        return jsonify({"success": True, "message": "签到成功"})
    except (CheckInFailed, SignOutFailed, requests.RequestException, json.JSONDecodeError) as e:
        logger.error(f"[{cfg.username}] 签到失败: {e}")
        return jsonify({"success": False, "error": f"签到失败: {e}", "error_code": "CHECKIN_FAILED"}), 502
    except Exception as e:
        logger.error(f"[{cfg.username}] 签到异常: {e}")
        return jsonify({"success": False, "error": f"签到异常: {e}", "error_code": "CHECKIN_FAILED"}), 500


@app.route("/api/signout", methods=["POST"])
def api_signout():
    guard = _csrf_guard()
    if guard:
        return guard

    cfg, token_mgr = get_auth_context()
    if not cfg:
        return jsonify({"success": False, "error": "未登录", "error_code": "UNAUTHORIZED"}), 401

    try:
        result = go_home(cfg, token_mgr)
        if result:
            logger.info(f"[{cfg.username}] 签退成功")
            return jsonify({"success": True, "message": "签退成功"})
        else:
            logger.warning(f"[{cfg.username}] 签退失败")
            return jsonify({"success": False, "error": "签退失败：没有正在使用的座位", "error_code": "SIGNOUT_FAILED"}), 502
    except (CheckInFailed, SignOutFailed, requests.RequestException, json.JSONDecodeError) as e:
        logger.error(f"[{cfg.username}] 签退失败: {e}")
        return jsonify({"success": False, "error": f"签退失败: {e}", "error_code": "SIGNOUT_FAILED"}), 502
    except Exception as e:
        logger.error(f"[{cfg.username}] 签退异常: {e}")
        return jsonify({"success": False, "error": f"签退异常: {e}", "error_code": "SIGNOUT_FAILED"}), 500


@app.route("/api/status")
def api_status():
    u = session.get("username")
    if u:
        return jsonify({"logged_in": True, "username": u})
    return jsonify({"logged_in": False})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    guard = _csrf_guard()
    if guard:
        return guard
    session.clear()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

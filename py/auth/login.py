"""
曲阜师范大学图书馆 - 登录模块
================================
基于 qfnu_login.py 适配，提供自动滑块验证码 + CAS 登录 + Bearer Token 获取。

公开 API:
    qfnu_login(username, password) -> (name, token)
"""
import base64
import json
import logging
import random
import os
import re
import time

import cv2
import numpy as np
import requests

from crypto.aes import encrypt_login_data

logger = logging.getLogger(__name__)

# IDS 认证服务器
IDS_URL = "http://ids.qfnu.edu.cn"
LIB_URL = "http://libyy.qfnu.edu.cn"

_service_url = "http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas"
_login_url = f"{IDS_URL}/authserver/login?service={_service_url}"
_referer = _login_url


# ==================== 滑块验证码 ====================

def _detect_gap_opencv(bg, slider):
    """提取滑块图形 + 多策略匹配（边缘、逆像、ROI）定位缺口"""
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    bg_gray = clahe.apply(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY))
    slider_gray = clahe.apply(cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY))

    # 提取滑块实际图形区域（非黑色像素包围盒）
    piece_mask = slider_gray > 15
    cols = np.any(piece_mask, axis=0)
    rows = np.any(piece_mask, axis=1)
    if not np.any(cols) or not np.any(rows):
        return 140, 0
    c_start = np.argmax(cols)
    c_end = len(cols) - np.argmax(cols[::-1])
    r_start = np.argmax(rows)
    r_end = len(rows) - np.argmax(rows[::-1])
    piece = slider_gray[r_start:r_end, c_start:c_end]

    # 多种匹配策略
    candidates = []

    # 策略 1: 逆像匹配（滑块图黑底亮块 → 背景图暗缺口对齐）
    bg_inv = (255 - bg_gray).astype(np.float32)
    piece_inv = (255 - piece).astype(np.float32)
    for method, label in [(cv2.TM_CCOEFF_NORMED, "inv_ccoeff"),
                           (cv2.TM_CCORR_NORMED, "inv_ccorr")]:
        result = cv2.matchTemplate(bg_inv, piece_inv, method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        candidates.append((max_loc[0] + c_start, max_val, label))

    # 策略 2: 裁剪后灰度直接匹配（不逆像）
    bg_f = bg_gray.astype(np.float32)
    piece_f = piece.astype(np.float32)
    for method, label in [(cv2.TM_CCOEFF_NORMED, "gray_ccoeff")]:
        result = cv2.matchTemplate(bg_f, piece_f, method)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        candidates.append((max_loc[0] + c_start, max_val, label))

    # 策略 3: 较宽松边缘（Canny 40-130）匹配
    bg_edge = cv2.Canny(bg_gray, 40, 130)
    piece_edge = cv2.Canny(piece, 40, 130)
    if np.count_nonzero(piece_edge) > 10:
        result = cv2.matchTemplate(bg_edge, piece_edge, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        candidates.append((max_loc[0] + c_start, max_val, "cedge_ccoeff"))

    if not candidates:
        return 140, 0

    # 逆像和逆像相关系数优先，取中位数
    inv_candidates = [c for c in candidates if c[2].startswith("inv_")]
    if inv_candidates:
        xs = sorted([c[0] for c in inv_candidates])
        best_x = xs[len(xs) // 2]
        best_score = max(c[1] for c in inv_candidates)
    else:
        best = max(candidates, key=lambda c: c[1])
        best_x, best_score = best[0], best[1]

    return int(best_x), best_score


def _detect_gap(bg, slider):
    """检测滑块缺口位置，返回缩放到 280px 显示宽度的坐标"""
    opencv_gap, score = _detect_gap_opencv(bg, slider)
    bg_width = bg.shape[1]
    scale = 280 / bg_width
    logger.debug(f"原始x={opencv_gap}, 分数={score:.4f}, 缩放={scale:.4f}")
    return opencv_gap * scale


def _generate_human_tracks(distance):
    """生成模拟人类拖拽的鼠标轨迹"""
    tracks = [{"a": 0, "b": 0, "c": 0}]
    current_x = 0

    # 慢启动阶段
    while current_x < distance * 0.1:
        move = random.uniform(1, 3)
        current_x += move
        tracks.append({
            "a": round(current_x, 1),
            "b": random.randint(-1, 1),
            "c": random.randint(8, 15),
        })

    # 快速移动阶段
    while current_x < distance * 0.5:
        move = random.uniform(3, 8)
        if current_x + move > distance * 0.5:
            move = distance * 0.5 - current_x
        current_x += move
        tracks.append({
            "a": round(current_x, 1),
            "b": random.randint(-1, 1),
            "c": random.randint(10, 20),
        })

    # 减速阶段
    while current_x < distance:
        move = random.uniform(1, 4)
        if current_x + move > distance:
            move = distance - current_x
        current_x += move
        tracks.append({
            "a": round(current_x, 1),
            "b": random.randint(-1, 1),
            "c": random.randint(15, 30),
        })

    # 精确对齐
    if abs(distance - tracks[-1]["a"]) > 0.5:
        tracks.append({
            "a": round(distance, 1),
            "b": random.randint(-1, 1),
            "c": random.randint(5, 15),
        })

    return tracks


def _solve_slider_captcha(session, headers, max_attempts=300):
    """破解滑块验证码：检测引导 + 全域覆盖 + 反向校验"""
    logger.info("获取滑块验证码...")

    try:
        captcha_api = f"{IDS_URL}/authserver/common/openSliderCaptcha.htl"
        r = session.get(captcha_api, headers=headers, timeout=30)

        if r.status_code != 200:
            logger.error(f"获取验证码失败: HTTP {r.status_code}")
            return False

        data = r.json()

        if "bigImage" not in data or "smallImage" not in data:
            logger.error("验证码数据格式错误")
            return False

        small_img_bytes = base64.b64decode(data["smallImage"])
        safe_secure = small_img_bytes[-16:].decode("utf-8")

        bg_array = np.frombuffer(base64.b64decode(data["bigImage"]), dtype=np.uint8)
        bg = cv2.imdecode(bg_array, cv2.IMREAD_COLOR)

        slider_array = np.frombuffer(small_img_bytes, dtype=np.uint8)
        slider = cv2.imdecode(slider_array, cv2.IMREAD_COLOR)

        if bg is None or slider is None:
            logger.error("图片解码失败")
            return False

        # 调试保存
        try:
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "debug_captcha")
            os.makedirs(debug_dir, exist_ok=True)
            ts = int(time.time())
            cv2.imwrite(os.path.join(debug_dir, f"bg_{ts}.png"), bg)
            cv2.imwrite(os.path.join(debug_dir, f"slider_{ts}.png"), slider)
        except Exception:
            pass

        detected_gap = _detect_gap(bg, slider)
        logger.info(f"缺口检测: 显示x={detected_gap:.2f} (bg={bg.shape[1]}x{bg.shape[0]})")

        verify_api = f"{IDS_URL}/authserver/common/verifySliderCaptcha.htl"
        base_gap = int(detected_gap)

        # 快速验证函数
        def _try_gap(gap):
            tracks = _generate_human_tracks(gap)
            verify_data = {"canvasLength": 280, "moveLength": gap, "tracks": tracks}
            encrypted_sign = encrypt_login_data(json.dumps(verify_data), safe_secure)
            r = session.post(
                verify_api,
                data={"sign": encrypted_sign},
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=30,
            )
            return r.json().get("errorCode") == 1

        total_attempts = 0
        tried = set()

        # 搜索策略
        search_phases = [
            ([base_gap], "中心值"),
            (list(range(max(20, base_gap - 15), min(260, base_gap + 15) + 1, 1)), "近邻±15"),
            (list(range(20, 261, 2)), "全域步长2"),
            (list(range(21, 261, 2)), "全域步长2偏移"),
        ]

        for gap_list, phase_name in search_phases:
            for gap in gap_list:
                if gap in tried: continue
                if total_attempts >= max_attempts:
                    logger.warning(f"已达最大尝试次数 {max_attempts}")
                    return False
                tried.add(gap); total_attempts += 1

                if _try_gap(gap):
                    logger.info(f"验证成功! gap={gap}, 阶段={phase_name}, 总尝试={total_attempts}")
                    return True

        logger.error(f"所有验证尝试失败 (共{total_attempts}次)")
        return False

    except Exception as e:
        logger.error(f"验证码异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== IDS 登录 ====================

def _get_salt_and_execution(session, headers):
    """从登录页 HTML 中提取 salt 和 execution 参数（最多 3 次重试，间隔 0.5s）"""
    for attempt in range(3):
        try:
            r = session.get(_login_url, headers=headers, timeout=30)
            html = r.text

            exec_match = re.search(
                r'name="execution"[^>]*value="([^"]*)"', html, re.IGNORECASE
            )
            salt_match = re.search(
                r'id="pwdEncryptSalt"[^>]*value="([^"]*)"', html, re.IGNORECASE
            )

            if exec_match and salt_match:
                return salt_match.group(1), exec_match.group(1)
        except Exception as e:
            logger.warning(f"获取登录页参数失败 (尝试 {attempt+1}/3): {e}")

        if attempt < 2:
            time.sleep(0.3)

    logger.error("无法提取登录参数（execution 或 pwdEncryptSalt）")
    return None, None


def _check_need_captcha(session, headers, username):
    """检查是否需要滑块验证码"""
    url = f"{IDS_URL}/authserver/checkNeedCaptcha.htl"
    r = session.get(url=url, params={"username": username}, headers=headers, timeout=30)
    return "true" in r.text


def _do_solve_slider_captcha(session, headers):
    """执行滑块验证码验证，最多尝试 5 轮"""
    logger.info("开始滑块验证码验证...")

    slider_url = f"{IDS_URL}/authserver/common/toSliderCaptcha.htl"
    session.get(slider_url, headers=headers, timeout=30)

    for attempt in range(5):
        logger.info(f"滑块验证码尝试 {attempt + 1}/5")
        result = _solve_slider_captcha(session, headers)
        if result:
            logger.info("滑块验证码验证成功")
            return True
        if attempt < 4:
            time.sleep(0.1)

    logger.error("滑块验证码验证失败，所有尝试均失败")
    return False


def _get_ids_token(session, username, password):
    """IDS CAS 登录，返回重定向 URL"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/117.0.5938.63 Safari/537.36"
        ),
        "Referer": _referer,
    }

    logger.info(f"开始获取Token，用户名: {username}")

    salt, execution = _get_salt_and_execution(session, headers)
    if not salt:
        return None
    logger.info(f"获取salt成功: {salt[:8]}...")

    logger.info("检查是否需要验证码...")
    need_captcha = _check_need_captcha(session, headers, username)

    if need_captcha:
        logger.info("系统需要滑块验证码，开始验证...")
        success = _do_solve_slider_captcha(session, headers)
        if not success:
            logger.error("滑块验证码验证失败，无法继续登录")
            return None

        salt, execution = _get_salt_and_execution(session, headers)
        logger.info("验证码通过后重新获取execution成功")
    else:
        logger.info("不需要验证码，直接登录")

    enc_passwd = encrypt_login_data(password, salt)

    data = {
        "username": username,
        "password": enc_passwd,
        "captcha": "",
        "_eventId": "submit",
        "cllt": "userNameLogin",
        "dllt": "generalLogin",
        "lt": "",
        "execution": execution,
    }

    login_response = session.post(
        _login_url,
        data=data,
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=False,
        timeout=30,
    )

    if login_response.status_code == 302:
        redirect_url = login_response.headers.get("Location", "")
        if redirect_url:
            logger.info("登录成功，获取到Token")
            return redirect_url

    logger.error(f"登录失败，状态码: {login_response.status_code}")
    return None


# ==================== 获取 Bearer Token ====================

def _get_bearer_token(session, username, password):
    """完整的 Token 获取流程：IDS 登录 → CAS 换取 → 用户信息"""
    ids_token = _get_ids_token(session, username, password)
    if not ids_token:
        logger.error("获取IDS Token失败")
        return None, None

    logger.info("获取IDS Token成功")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/117.0.5938.63 Safari/537.36"
        ),
    }

    logger.info("访问IDS Token链接...")
    session.get(url=ids_token, headers=headers, allow_redirects=False, timeout=30)

    logger.info("获取CAS登录...")
    res = session.get(
        url=f"{LIB_URL}/api/cas/cas",
        headers=headers,
        allow_redirects=False,
        timeout=30,
    )

    if "Location" not in res.headers:
        logger.error("CAS登录失败，未返回Location")
        return None, None

    cas_token = res.headers["Location"][-32:]
    logger.info(f"获取CAS Token成功: {cas_token[:16]}...")

    headers_post = {**headers, "Content-Type": "application/json"}

    logger.info("获取用户信息...")
    res = session.post(
        url=f"{LIB_URL}/api/cas/user",
        headers=headers_post,
        data=json.dumps({"cas": cas_token}),
        timeout=30,
    )

    if res.status_code != 200:
        logger.error(f"获取用户信息失败: HTTP {res.status_code}")
        return None, None

    try:
        parsed_res = json.loads(res.text)
    except json.JSONDecodeError:
        logger.error(f"解析用户信息失败: {res.text[:100]}")
        return None, None

    if "member" not in parsed_res:
        logger.error(f"用户信息格式错误: {parsed_res}")
        return None, None

    name = parsed_res["member"]["name"]
    token = parsed_res["member"]["token"]

    logger.info(f"获取Bearer Token成功，姓名: {name}")
    return name, token


# ==================== 公开 API ====================

def _login_with_retry(username: str, password: str, max_retries: int = 3):
    """
    登录重试包装器，3 次重试 + 指数退避 (0.5s, 1s, 2s)。

    参数:
        username: 学号/工号
        password: 密码
        max_retries: 最大重试次数（默认 3）

    返回:
        (name, token) 元组。失败返回 (None, None)。
    """
    for attempt in range(max_retries):
        try:
            name, token = qfnu_login(username, password)
            if token is not None:
                return name, token
        except Exception as e:
            logger.warning(f"登录异常 (尝试 {attempt+1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            delay = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
            logger.info(f"登录失败，{delay} 秒后重试...")
            time.sleep(delay)

    return None, None


def qfnu_login(username, password):
    """
    曲阜师范大学图书馆登录。

    参数:
        username: 学号/工号
        password: 密码

    返回:
        (name, token) 元组。使用时需拼接 "bearer" + token。
        失败返回 (None, None)。
    """
    with requests.session() as session:
        return _get_bearer_token(session, username, password)

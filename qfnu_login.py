"""
曲阜师范大学图书馆 - 滑块验证码登录脚本
========================================
功能：自动完成滑块验证码验证 + CAS登录 + 获取Bearer Token
依赖：requests, opencv-python-headless, pycryptodome, numpy

使用方法：
    from qfnu_login import qfnu_login
    name, token = qfnu_login("用户名", "密码")
    if token:
        print(f"登录成功，姓名: {name}")
        print(f"Token: bearer{token}")
"""

import base64
import json
import random
import re
import logging
import sys
import time

import cv2
import numpy as np
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("qfnu_login")

AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"

IDS_URL = "http://ids.qfnu.edu.cn"
LIB_URL = "http://libyy.qfnu.edu.cn"


# ==================== 工具函数 ====================

def random_string(length):
    return ''.join(random.choice(AES_CHARS) for _ in range(length))


def encrypt_password(data, key):
    prefix = random_string(64)
    iv = random_string(16)
    plaintext = prefix + data
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    ciphertext = cipher.encrypt(pad(plaintext.encode('utf-8'), AES.block_size))
    return base64.b64encode(ciphertext).decode('utf-8')


def generate_encrypted_password(password, key):
    return encrypt_password(password, key)


# ==================== 滑块验证码 ====================

def detect_gap_opencv(bg, slider):
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    slider_gray = cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY)

    bg_edge = cv2.Canny(bg_gray, 50, 150)
    slider_edge = cv2.Canny(slider_gray, 50, 150)

    best_edge_x = 0
    best_edge_score = -1
    for width in [slider.shape[1], 80, 75, 70, 65, 60]:
        if width > slider_edge.shape[1]:
            continue
        puzzle = slider_edge[:, :width]
        result = cv2.matchTemplate(bg_edge, puzzle, cv2.TM_CCOEFF_NORMED)
        _, max_val, max_loc, _ = cv2.minMaxLoc(result)
        if max_val > best_edge_score:
            best_edge_score = max_val
            best_edge_x = max_loc[0]

    best_gray_x = 0
    best_gray_score = -1
    for width in [slider.shape[1], 80, 75, 70, 65, 60]:
        if width > slider_gray.shape[1]:
            continue
        puzzle = slider_gray[:, :width]
        result = cv2.matchTemplate(bg_gray, puzzle, cv2.TM_CCORR_NORMED)
        _, max_val, max_loc, _ = cv2.minMaxLoc(result)
        if max_val > best_gray_score:
            best_gray_score = max_val
            best_gray_x = max_loc[0]

    if best_edge_score > best_gray_score:
        return best_edge_x, best_edge_score
    else:
        return best_gray_x, best_gray_score


def detect_gap(bg, slider):
    opencv_gap, score = detect_gap_opencv(bg, slider)
    bg_width = bg.shape[1]
    scale = 280 / bg_width
    return opencv_gap * scale


def generate_human_tracks(distance):
    tracks = [{'a': 0, 'b': 0, 'c': 0}]
    current_x = 0

    while current_x < distance * 0.1:
        move = random.uniform(1, 3)
        current_x += move
        tracks.append({'a': round(current_x, 1), 'b': random.randint(-1, 1), 'c': random.randint(8, 15)})

    while current_x < distance * 0.5:
        move = random.uniform(3, 8)
        if current_x + move > distance * 0.5:
            move = distance * 0.5 - current_x
        current_x += move
        tracks.append({'a': round(current_x, 1), 'b': random.randint(-1, 1), 'c': random.randint(10, 20)})

    while current_x < distance:
        move = random.uniform(1, 4)
        if current_x + move > distance:
            move = distance - current_x
        current_x += move
        tracks.append({'a': round(current_x, 1), 'b': random.randint(-1, 1), 'c': random.randint(15, 30)})

    if abs(distance - tracks[-1]['a']) > 0.5:
        tracks.append({'a': round(distance, 1), 'b': random.randint(-1, 1), 'c': random.randint(5, 15)})

    return tracks


def solve_slider_captcha(session, headers, max_attempts=300):
    logger.info("获取滑块验证码...")

    try:
        captcha_api = f'{IDS_URL}/authserver/common/openSliderCaptcha.htl'
        r = session.get(captcha_api, headers=headers, timeout=30)

        if r.status_code != 200:
            logger.error(f"获取验证码失败: HTTP {r.status_code}")
            return False

        data = r.json()

        if 'bigImage' not in data or 'smallImage' not in data:
            logger.error("验证码数据格式错误")
            return False

        small_img_bytes = base64.b64decode(data['smallImage'])
        safe_secure = small_img_bytes[-16:].decode('utf-8')

        bg_array = np.frombuffer(base64.b64decode(data['bigImage']), dtype=np.uint8)
        bg = cv2.imdecode(bg_array, cv2.IMREAD_COLOR)

        slider_array = np.frombuffer(small_img_bytes, dtype=np.uint8)
        slider = cv2.imdecode(slider_array, cv2.IMREAD_COLOR)

        if bg is None or slider is None:
            logger.error("图片解码失败")
            return False

        detected_gap = detect_gap(bg, slider)
        logger.info(f"缺口检测: 显示x={detected_gap:.2f}")

        verify_api = f'{IDS_URL}/authserver/common/verifySliderCaptcha.htl'

        base_gap = int(detected_gap)
        search_phases = [
            ([base_gap], 1, "中心值"),
            (list(range(max(20, base_gap - 15), min(260, base_gap + 15) + 1, 1)), 1, "近邻±15"),
            (list(range(20, 261, 1)), 1, "全域步长1"),
        ]

        total_attempts = 0
        tried_gaps = set()

        for gap_list, step, phase_name in search_phases:
            phase_attempts = 0
            for gap in gap_list:
                if gap in tried_gaps:
                    continue
                if total_attempts >= max_attempts:
                    logger.warning(f"已达最大尝试次数 {max_attempts}")
                    return False

                tried_gaps.add(gap)
                total_attempts += 1
                phase_attempts += 1

                tracks = generate_human_tracks(gap)
                verify_data = {'canvasLength': 280, 'moveLength': gap, 'tracks': tracks}
                encrypted_sign = encrypt_password(json.dumps(verify_data), safe_secure)

                r = session.post(verify_api, data={'sign': encrypted_sign}, headers={
                    **headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                }, timeout=30)

                result = r.json()

                if result.get('errorCode') == 1:
                    logger.info(f"验证成功! gap={gap}, 阶段={phase_name}, 总尝试={total_attempts}")
                    return True

            logger.debug(f"{phase_name}完成: 尝试{phase_attempts}次, 累计{total_attempts}次")

        logger.error(f"所有验证尝试失败 (共{total_attempts}次)")
        return False

    except Exception as e:
        logger.error(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== IDS登录 ====================

_service_url = "http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas"
_login_url = f'{IDS_URL}/authserver/login?service={_service_url}'
_referer = _login_url


def _get_salt_and_execution(session, headers):
    r = session.get(_login_url, headers=headers, timeout=30)
    html = r.text

    exec_match = re.search(r'name="execution"[^>]*value="([^"]*)"', html, re.IGNORECASE)
    salt_match = re.search(r'id="pwdEncryptSalt"[^>]*value="([^"]*)"', html, re.IGNORECASE)

    if not exec_match or not salt_match:
        logger.error("无法提取登录参数")
        return None, None

    salt = salt_match.group(1)
    execution = exec_match.group(1)
    return salt, execution


def _check_need_captcha(session, headers, username):
    url = f'{IDS_URL}/authserver/checkNeedCaptcha.htl'
    data = {'username': username}
    r = session.get(url=url, params=data, headers=headers, timeout=30)
    return "true" in r.text


def _solve_slider_captcha(session, headers):
    logger.info("开始滑块验证码验证...")

    slider_url = f'{IDS_URL}/authserver/common/toSliderCaptcha.htl'
    session.get(slider_url, headers=headers, timeout=30)

    for attempt in range(10):
        logger.info(f"滑块验证码尝试 {attempt + 1}/10")
        result = solve_slider_captcha(session, headers)
        if result:
            logger.info("滑块验证码验证成功")
            return True
        time.sleep(0.3)

    logger.error("滑块验证码验证失败，所有尝试均失败")
    return False


def get_ids_token(session, username, password):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.5938.63 Safari/537.36',
        'Referer': _referer,
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
        success = _solve_slider_captcha(session, headers)
        if not success:
            logger.error("滑块验证码验证失败，无法继续登录")
            return None

        salt, execution = _get_salt_and_execution(session, headers)
        logger.info("验证码通过后重新获取execution成功")
    else:
        logger.info("不需要验证码，直接登录")

    enc_passwd = generate_encrypted_password(password, salt)

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
        headers={
            **headers,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        allow_redirects=False,
        timeout=30
    )

    if login_response.status_code == 302:
        redirect_url = login_response.headers.get('Location', '')
        if redirect_url:
            logger.info("登录成功，获取到Token")
            return redirect_url

    logger.error(f"登录失败，状态码: {login_response.status_code}")
    return None


# ==================== 获取Bearer Token ====================

def get_bearer_token(username, password):
    logger.info("开始获取Bearer Token")

    session = requests.session()

    ids_token = get_ids_token(session, username, password)
    if not ids_token:
        logger.error("获取IDS Token失败")
        return None, None

    logger.info("获取IDS Token成功")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.5938.63 Safari/537.36',
    }

    logger.info("访问IDS Token链接...")
    session.get(url=ids_token, headers=headers, allow_redirects=False, timeout=30)

    logger.info("获取CAS登录...")
    res = session.get(
        url=f'{LIB_URL}/api/cas/cas',
        headers=headers,
        allow_redirects=False,
        timeout=30,
    )

    if "Location" not in res.headers:
        logger.error("CAS登录失败，未返回Location")
        return None, None

    cas_token = res.headers["Location"][-32:]
    logger.info(f"获取CAS Token成功: {cas_token[:16]}...")

    data = {"cas": cas_token}
    headers_post = {
        **headers,
        "Content-Type": "application/json",
    }

    logger.info("获取用户信息...")
    res = session.post(
        url=f'{LIB_URL}/api/cas/user',
        headers=headers_post,
        data=json.dumps(data),
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


# ==================== 主入口 ====================

def qfnu_login(username, password):
    """
    曲阜师范大学图书馆登录

    参数:
        username: 学号/工号
        password: 密码

    返回:
        (name, token) 元组
        - name: 姓名
        - token: Bearer Token（使用时需加 "bearer" 前缀，如 "bearer" + token）
        失败返回 (None, None)
    """
    return get_bearer_token(username, password)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python qfnu_login.py <用户名> <密码>")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]

    name, token = qfnu_login(username, password)
    if token:
        print(f"\n登录成功！")
        print(f"姓名: {name}")
        print(f"Bearer Token: bearer{token[:50]}...")
    else:
        print("\n登录失败")
        sys.exit(1)

"""
滑块验证码处理模块

处理曲阜师范大学 IDS 统一身份认证平台的滑块验证码。
流程：获取图片 → 提取 safeSecure → 检测缺口 → 模拟轨迹 → AES 加密 → 提交验证

逆向自 ids-sliderCaptcha.js + longbow.slidercaptcha.js
"""

import base64
import json
import logging
import random
import time

import cv2
import numpy as np
import requests

from ids_utils.passwd_encrypt import generate_random_string, encrypt_data

# 滑块画布宽度（与 JS 端 sliderCaptcha width 一致）
CANVAS_WIDTH = 280
MAX_RETRIES = 5

logger = logging.getLogger("slider_captcha")


class SliderCaptchaError(Exception):
    """滑块验证码处理失败"""
    pass


def open_slider_captcha(session):
    """
    加载滑块验证码图片

    调用前需先请求 toSliderCaptcha.htl 初始化服务器端状态。
    GET /authserver/common/openSliderCaptcha.htl
    返回: {"big_image": bytes, "small_image": bytes, "safe_secure": str}
    """
    url = "http://ids.qfnu.edu.cn/authserver/common/openSliderCaptcha.htl"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/117.0.5938.63 Safari/537.36",
    }
    try:
        resp = session.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        big_image_b64 = data.get("bigImage", "")
        small_image_b64 = data.get("smallImage", "")
        if not big_image_b64 or not small_image_b64:
            raise SliderCaptchaError("滑块验证码图片数据缺失")

        # 解码图片字节
        big_image_bytes = base64.b64decode(big_image_b64)
        small_image_bytes = base64.b64decode(small_image_b64)

        # 提取 safeSecure: JS 端 atob(smallImage) 后取最后 16 字节作为字符串
        # JS atob 使用 Latin-1 编码（每个字节 → 一个字符）
        small_raw = base64.b64decode(small_image_b64)
        safe_secure = small_raw[-16:].decode("latin-1")
        if len(safe_secure) < 16:
            raise SliderCaptchaError(f"safeSecure 长度不足: {len(safe_secure)}")

        logger.info(f"[+]---滑块验证码图片获取成功")
        return {
            "big_image": big_image_bytes,
            "small_image": small_image_bytes,
            "safe_secure": safe_secure,
        }
    except Exception as e:
        if isinstance(e, SliderCaptchaError):
            raise
        raise SliderCaptchaError(f"获取滑块验证码图片失败: {e}")


def detect_gap_position(big_image_bytes, small_image_bytes):
    """
    检测拼图缺口 x 坐标（画布坐标系 280px）

    使用 alpha 掩码模板匹配：利用小图的透明通道裁剪出拼图块形状，
    然后在大图中匹配对应位置。经实测置信度通常 > 0.85。

    注意：每个验证码只能调用 verify 一次，失败即失效，需刷新图片重试。

    Returns:
        int: 画布坐标系下的缺口 x 偏移量（像素）
    """
    try:
        big_img = cv2.imdecode(
            np.frombuffer(big_image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE
        )
        small_raw = cv2.imdecode(
            np.frombuffer(small_image_bytes, np.uint8), cv2.IMREAD_UNCHANGED
        )

        if big_img is None or small_raw is None:
            raise SliderCaptchaError("图片解码失败")

        original_width = big_img.shape[1]
        scale = CANVAS_WIDTH / original_width

        # 利用 alpha 通道裁剪拼图块
        if small_raw.shape[2] == 4:
            alpha = small_raw[:, :, 3]
            cols = np.where(np.any(alpha > 10, axis=0))[0]
            rows = np.where(np.any(alpha > 10, axis=1))[0]
            if len(cols) == 0 or len(rows) == 0:
                raise SliderCaptchaError("小图无有效内容")
            x1, x2 = cols[0], cols[-1] + 1
            y1, y2 = rows[0], rows[-1] + 1
            small_crop = cv2.cvtColor(
                small_raw[y1:y2, x1:x2, :3], cv2.COLOR_BGR2GRAY
            )
            mask_crop = (alpha[y1:y2, x1:x2] > 10).astype(np.uint8) * 255
        else:
            small_crop = (
                cv2.cvtColor(small_raw, cv2.COLOR_BGR2GRAY)
                if len(small_raw.shape) == 3
                else small_raw
            )
            mask_crop = None

        # 带掩码的模板匹配
        method = cv2.TM_CCOEFF_NORMED
        if mask_crop is not None:
            result = cv2.matchTemplate(big_img, small_crop, method, mask=mask_crop)
        else:
            result = cv2.matchTemplate(big_img, small_crop, method)

        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        move_length = round(max_loc[0] * scale)

        logger.info(
            f"[+]---缺口检测: 原图x={max_loc[0]}, "
            f"画布x={move_length}, 置信度={max_val:.3f}"
        )
        return move_length

    except Exception as e:
        if isinstance(e, SliderCaptchaError):
            raise
        raise SliderCaptchaError(f"缺口位置检测失败: {e}")


def generate_mouse_tracks(distance):
    """
    生成自然的鼠标拖动轨迹

    模拟人类拖动行为：加速 → 匀速 → 微调
    返回: [{"a": x偏移, "b": y偏移, "c": 相对时间戳ms}, ...]
    """
    tracks = []
    current_x = 0
    current_time = 0

    # 三段式轨迹：加速(40%) → 匀速(40%) → 减速微调(20%)
    total_time = random.randint(400, 700)  # 总拖动时间 400~700ms
    phase1_end = distance * 0.4
    phase2_end = distance * 0.8

    # 起始点
    tracks.append({"a": 0, "b": 0, "c": 0})

    while current_x < distance:
        progress = current_x / distance

        if current_x < phase1_end:
            # 加速阶段：步长逐渐增大
            step = random.uniform(2, 6)
        elif current_x < phase2_end:
            # 匀速阶段：稳定步长
            step = random.uniform(4, 8)
        else:
            # 减速微调：步长逐渐减小
            step = random.uniform(1, 3)

        # 时间增量（越到后面间隔越大，模拟减速）
        time_delta = random.randint(10, 30)
        current_time += time_delta

        current_x += step
        # y 轴微小抖动（模拟手抖）
        y_offset = random.randint(-2, 2)

        remaining = distance - current_x
        if remaining <= 0:
            # 最后一步精确到位
            tracks.append({"a": distance, "b": y_offset, "c": current_time})
            break

        tracks.append({
            "a": round(current_x),
            "b": y_offset,
            "c": current_time,
        })

    # 确保最后一个点的 x == distance（与 JS 端验证逻辑一致）
    if tracks[-1]["a"] != distance:
        current_time += random.randint(15, 30)
        tracks.append({"a": distance, "b": 0, "c": current_time})

    # 添加起点（JS 端第一个点是 {a:0, b:0, c:0}）
    if tracks[0]["a"] != 0:
        tracks.insert(0, {"a": 0, "b": 0, "c": 0})

    return tracks


def encrypt_slider_data(canvas_length, move_length, tracks, safe_secure):
    """
    加密滑块验证数据

    与 JS 端 encryptPassword(JSON.stringify(payload), safeSecure) 完全对齐：
    - randomString(64) + JSON 作为明文
    - safe_secure 直接作为 AES 密钥（UTF-8 字节，16字节 = AES-128）
    - randomString(16) 直接作为 IV（UTF-8 字节）
    - AES-128-CBC + PKCS7 填充
    - 输出: base64(ciphertext)，无 Salted__ 前缀
    """
    payload = {
        "canvasLength": canvas_length,
        "moveLength": move_length,
        "tracks": tracks,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))

    # 与 generate_encrypted_password 一致：64 字符随机前缀 + 明文
    random_prefix = generate_random_string(64)
    plaintext = random_prefix + payload_json

    # 16 字符随机 IV
    iv = generate_random_string(16)

    # AES-128-CBC 加密（safe_secure 作为 key，16 字节）
    return encrypt_data(plaintext, safe_secure, iv)


def verify_slider_captcha(session, canvas_length, move_length, tracks, safe_secure):
    """
    向服务端提交滑块验证

    POST /authserver/common/verifySliderCaptcha.htl
    请求体: {sign: encrypted_payload}
    """
    url = "http://ids.qfnu.edu.cn/authserver/common/verifySliderCaptcha.htl"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/117.0.5938.63 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        sign = encrypt_slider_data(canvas_length, move_length, tracks, safe_secure)
        resp = session.post(url, headers=headers, data={"sign": sign})
        resp.raise_for_status()
        result = resp.json()

        success = result.get("errorCode") == 1
        if success:
            logger.info("[+]---滑块验证码验证成功")
        else:
            logger.warning(f"[-]---滑块验证码验证失败: {result}")
        return success
    except Exception as e:
        logger.error(f"[X]---滑块验证码验证请求异常: {e}")
        return False


def solve_slider_captcha(session):
    """
    一站式解决滑块验证码

    关键约束：每个验证码只能验证一次，失败即失效。
    每次尝试：toSliderCaptcha → openSliderCaptcha → 检测 → 单次验证。

    成功返回 True，全部失败抛出 SliderCaptchaError。
    """
    base_url = "http://ids.qfnu.edu.cn/authserver"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/117.0.5938.63 Safari/537.36",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"[+]---滑块验证码第 {attempt}/{MAX_RETRIES} 次尝试")
        try:
            # 初始化服务器端滑块验证码状态
            session.get(f"{base_url}/common/toSliderCaptcha.htl", headers=headers)

            # 获取滑块图片 + safeSecure
            captcha_data = open_slider_captcha(session)

            # 检测缺口位置
            move_length = detect_gap_position(
                captcha_data["big_image"],
                captcha_data["small_image"],
            )

            # 生成拟人轨迹
            tracks = generate_mouse_tracks(move_length)

            # 单次验证（失败则验证码失效，需刷新重试）
            success = verify_slider_captcha(
                session,
                canvas_length=CANVAS_WIDTH,
                move_length=move_length,
                tracks=tracks,
                safe_secure=captcha_data["safe_secure"],
            )

            if success:
                return True

            logger.warning(f"[-]---第 {attempt} 次尝试失败，准备刷新验证码重试...")
            time.sleep(0.5)

        except SliderCaptchaError as e:
            logger.warning(f"[-]---第 {attempt} 次尝试异常: {e}")
            time.sleep(0.5)

    raise SliderCaptchaError(f"滑块验证码 {MAX_RETRIES} 次尝试均失败")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 独立测试：完整滑块验证流程
    test_session = requests.Session()
    test_session.get(
        "http://ids.qfnu.edu.cn/authserver/login"
        "?service=http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas",
        timeout=10,
    )

    try:
        result = solve_slider_captcha(test_session)
        print(f"滑块验证结果: {'成功' if result else '失败'}")
    except SliderCaptchaError as e:
        print(f"滑块验证失败: {e}")

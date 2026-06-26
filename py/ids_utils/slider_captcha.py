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
MAX_RETRIES = 3

logger = logging.getLogger("slider_captcha")


class SliderCaptchaError(Exception):
    """滑块验证码处理失败"""
    pass


def open_slider_captcha(session):
    """
    加载滑块验证码图片

    GET /authserver/common/openSliderCaptcha.htl
    返回: {"big_image": bytes, "small_image": bytes, "safe_secure": str}
    """
    url = "https://ids.qfnu.edu.cn/authserver/common/openSliderCaptcha.htl"
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


def detect_gap_candidates(big_image_bytes, max_candidates=5):
    """
    检测拼图缺口候选 x 坐标列表（画布坐标系 280px）

    使用 Sobel 边缘检测找显著峰对，按双峰最低强度排序。
    返回前 max_candidates 个候选位置（画布坐标）。

    Returns:
        list[int]: 候选画布 x 坐标列表，按置信度降序
    """
    try:
        from scipy.signal import find_peaks
    except ImportError:
        raise SliderCaptchaError("缺少 scipy 依赖，无法检测缺口位置")

    try:
        big_img = cv2.imdecode(
            np.frombuffer(big_image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE
        )
        if big_img is None:
            raise SliderCaptchaError("背景图解码失败")

        original_width = big_img.shape[1]
        scale = CANVAS_WIDTH / original_width

        # Sobel 水平方向边缘检测 → 按列求和
        sobel_x = cv2.Sobel(big_img, cv2.CV_64F, 1, 0, ksize=3)
        col_profile = np.sum(np.abs(sobel_x), axis=0)
        col_smooth = np.convolve(col_profile, np.ones(5) / 5, mode="same")

        # 找显著边缘峰
        peaks, _ = find_peaks(
            col_smooth,
            height=np.mean(col_smooth) * 1.2,
            distance=20,
            prominence=500,
        )

        if len(peaks) < 2:
            raise SliderCaptchaError(f"边缘峰不足: 仅检测到 {len(peaks)} 个")

        # 按"双峰最低强度"排序
        pairs = []
        for i in range(len(peaks)):
            for j in range(i + 1, len(peaks)):
                strength = min(col_smooth[peaks[i]], col_smooth[peaks[j]])
                gap_x = min(peaks[i], peaks[j])
                pairs.append((gap_x, strength))
        pairs.sort(key=lambda p: -p[1])

        # 去重（相近的 x 只保留最强的）
        candidates = []
        for gap_x, _ in pairs:
            canvas_x = round(gap_x * scale)
            if not candidates or abs(canvas_x - candidates[-1]) > 3:
                candidates.append(canvas_x)
            if len(candidates) >= max_candidates:
                break

        logger.info(f"[+]---缺口候选: {candidates}")
        return candidates

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
    url = "https://ids.qfnu.edu.cn/authserver/common/verifySliderCaptcha.htl"
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

    对每张验证码图片尝试多个候选缺口位置（由 Sobel 峰对排序决定），
    总共最多 MAX_RETRIES 次图片刷新。

    成功返回 True，全部失败抛出 SliderCaptchaError。
    """
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"[+]---滑块验证码第 {attempt}/{MAX_RETRIES} 次尝试")
        try:
            # 1. 获取滑块图片 + safeSecure
            captcha_data = open_slider_captcha(session)

            # 2. 检测多个候选缺口位置
            candidates = detect_gap_candidates(captcha_data["big_image"])

            # 3. 逐一尝试每个候选位置
            for i, move_length in enumerate(candidates):
                tracks = generate_mouse_tracks(move_length)
                success = verify_slider_captcha(
                    session,
                    canvas_length=CANVAS_WIDTH,
                    move_length=move_length,
                    tracks=tracks,
                    safe_secure=captcha_data["safe_secure"],
                )
                if success:
                    return True
                logger.info(f"    候选 {i+1}/{len(candidates)} (x={move_length}) 失败")

            logger.warning(f"[-]---第 {attempt} 次尝试所有候选均失败，准备重试...")
            time.sleep(1)

        except SliderCaptchaError as e:
            logger.warning(f"[-]---第 {attempt} 次尝试异常: {e}")
            time.sleep(1)

    raise SliderCaptchaError(f"滑块验证码 {MAX_RETRIES} 次尝试均失败")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 独立测试：获取图片并检测缺口候选位置
    test_session = requests.Session()
    test_session.get(
        "http://ids.qfnu.edu.cn/authserver/login"
        "?service=http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas",
        timeout=10,
    )

    data = open_slider_captcha(test_session)
    candidates = detect_gap_candidates(data["big_image"])
    print(f"候选位置: {candidates}")

    if candidates:
        distance = candidates[0]
        tracks = generate_mouse_tracks(distance)
        print(f"轨迹点数: {len(tracks)}")
        print(f"起点: {tracks[0]}")
        print(f"终点: {tracks[-1]}")
        print(f"终点 x == 目标距离: {tracks[-1]['a'] == distance}")

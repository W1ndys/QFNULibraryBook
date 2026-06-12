import datetime
import json
import logging
import os
import sys
import time
import base64
import hmac
import hashlib
import urllib.parse

import requests
import yaml
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# ============ 日志配置 ============
LOG_PATH = "/workspace/reserve.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("reserve_211")


# ============ 预约配置 ============
CLASSROOM_NAME = "东校区图书馆-三层自习室02"
BUILD_ID = 23
SEAT_ID = 4379  # 座位系统 ID
SEAT_NO = "211"  # 座位号（仅用于日志/通知展示）


# ============ 教室名称 -> build_id 映射（与 get_info.py 保持一致）============
classroom_id_mapping = {
    "西校区图书馆-三层自习室": 38,
    "西校区图书馆-四层自习室": 39,
    "西校区图书馆-五层自习室": 40,
    "东校区图书馆-三层自习室01": 22,
    "东校区图书馆-三层自习室02": 23,
    "综合楼-801自习室": 16,
    "综合楼-803自习室": 17,
    "综合楼-804自习室": 18,
    "综合楼-805自习室": 19,
    "综合楼-806自习室": 20,
    "行政楼-四层东区自习室": 13,
    "行政楼-四层中区自习室": 14,
    "行政楼-四层西区自习室": 15,
    "电视台楼-二层自习室": 12,
}


# ============ 常量 ============
URL_GET_SEAT = "http://libyy.qfnu.edu.cn/api/Seat/confirm"
URL_DATE = "http://libyy.qfnu.edu.cn/api/Seat/date"
URL_CAS_CAS = "http://libyy.qfnu.edu.cn/api/cas/cas"
URL_CAS_USER = "http://libyy.qfnu.edu.cn/api/cas/user"
URL_IDS_LOGIN = "http://ids.qfnu.edu.cn/authserver/login?service=http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas"


# ============ 读取 config.yml ============
def load_config():
    config_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yml"
    )
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============ 等待时间：等待到当天 19:20 ============
def wait_until_1920(github_mode):
    """
    脚本在 19:15 启动后，内部持续轮询等待，直到 19:20 准时开始抢座。
    若系统时间已超过 19:20，则立刻开始。
    """
    while True:
        now = datetime.datetime.now()
        # 如果是 Github Action 环境，UTC 时间加 8 小时
        if github_mode:
            now = now + datetime.timedelta(hours=8)
        target = now.replace(hour=19, minute=20, second=0, microsecond=0)
        diff = (target - now).total_seconds()
        if diff <= 0:
            logger.info("已到达 19:20，开始抢座。")
            break
        # 距离目标时间超过 1 分钟：每 30 秒打一次日志，其他时间短 sleep
        if diff > 60:
            logger.info(f"距离 19:20 还有 {int(diff)} 秒，继续等待...")
            time.sleep(30)
        else:
            # 最后一分钟，进入高频小 sleep 轮询
            logger.info(f"距离 19:20 还有 {diff:.2f} 秒，准备抢座...")
            time.sleep(0.5)


# ============ IDS 登录 & 获取 Bearer Token ============
def _ids_generate_encrypted_password(passwd, salt):
    """等同 ids_utils.passwd_encrypt.generate_encrypted_password"""
    import random as _r

    aes_chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
    key = "".join(_r.choice(aes_chars) for _ in range(64))
    iv = "".join(_r.choice(aes_chars) for _ in range(16))
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.backends import default_backend

    data = (key + passwd).strip().encode("utf-8")
    key_enc = salt.encode("utf-8")
    iv_enc = iv.encode("utf-8")
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key_enc), modes.CBC(iv_enc), backend=backend)
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def get_bearer_token(username, password):
    """
    走 ids.qfnu.edu.cn CAS 登录流程，获取图书馆系统的 bearer token。
    """
    session = requests.Session()
    # 1. 获取 salt & execution
    r = session.get(URL_IDS_LOGIN, timeout=30)
    soup = parse_html(r.text)
    salt = soup["pwdEncryptSalt"]
    execution = soup["execution"]
    logger.info(f"获取 IDS salt / execution 完成")

    # 2. 加密密码
    enc_pwd = _ids_generate_encrypted_password(password, salt)

    # 3. 提交登录
    data = {
        "username": username,
        "password": enc_pwd,
        "captcha": "",
        "_eventId": "submit",
        "cllt": "userNameLogin",
        "dllt": "generalLogin",
        "lt": "",
        "execution": execution,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://libyy.qfnu.edu.cn/",
    }
    r = session.post(URL_IDS_LOGIN, headers=headers, data=data,
                     allow_redirects=False, timeout=30)
    # 跟随重定向
    while r.status_code in (301, 302):
        r = session.get(r.headers["Location"], headers=headers,
                        allow_redirects=False, timeout=30)

    # 4. 拿 CAS token
    r = session.get(URL_CAS_CAS, headers=headers,
                    allow_redirects=False, timeout=30)
    cas_token = r.headers["Location"][-32:]

    # 5. 拿用户 token
    r = session.post(
        URL_CAS_USER,
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps({"cas": cas_token}),
        timeout=30,
    )
    info = r.json()
    name = info.get("member", {}).get("name")
    token = info.get("member", {}).get("token")
    if not token:
        raise RuntimeError(f"获取 bearer token 失败: {info}")
    logger.info(f"登录成功: {name}")
    return name, "bearer" + token


def parse_html(html):
    """最小实现：从 IDS login 页面提取 pwdEncryptSalt / execution"""
    import re

    def get(name):
        m = re.search(
            r'input[^>]*name=["\']' + re.escape(name) + r'["\'][^>]*value=["\']([^"\']*)["\']',
            html,
        )
        if not m:
            m = re.search(
                r'id=["\']' + re.escape(name) + r'["\'][^>]*value=["\']([^"\']*)["\']',
                html,
            )
        return m.group(1) if m else ""

    return {"pwdEncryptSalt": get("pwdEncryptSalt"), "execution": get("execution")}


# ============ 加密（和 get_info.py 一致） ============
def _aes_encrypt_for_seat(text):
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    palindrome = current_date[::-1]
    key = (current_date + palindrome).encode("utf-8")
    iv = b"ZZWBKJ_ZHIHUAWEI"
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct_bytes = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct_bytes).decode("utf-8")


# ============ 获取明天日期和时段 segment ============
def get_tomorrow_date():
    return (datetime.datetime.now().date() + datetime.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def get_segment(build_id, date_str):
    """调用 /api/Seat/date 拿到目标日期下的 segment id"""
    r = requests.post(
        URL_DATE,
        headers={"Content-Type": "application/json"},
        json={"build_id": build_id},
        timeout=30,
    )
    data = r.json()
    for item in data.get("data", []):
        if item.get("day") == date_str:
            seg = item["times"][0]["id"]
            logger.info(f"{date_str} segment = {seg}")
            return seg
    raise RuntimeError(f"未在响应中找到日期 {date_str}: {data}")


# ============ 抢座 ============
def try_reserve_once(auth_token, seat_id, segment):
    origin = '{"seat_id":"%s","segment":"%s"}' % (seat_id, segment)
    encrypted = _aes_encrypt_for_seat(origin)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "http://libyy.qfnu.edu.cn",
        "Referer": "http://libyy.qfnu.edu.cn/h5/index.html",
        "Authorization": auth_token,
    }
    r = requests.post(URL_GET_SEAT, json={"aesjson": encrypted},
                      headers=headers, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text}


def reserve_loop(auth_token, seat_id, segment, max_attempts=20):
    """轮询发起预约请求，直到预约成功或达到重试上限"""
    for i in range(1, max_attempts + 1):
        try:
            resp = try_reserve_once(auth_token, seat_id, segment)
            msg = resp.get("msg") if isinstance(resp, dict) else str(resp)
            logger.info(f"第 {i} 次请求 -> msg={msg}")
            if msg == "预约成功":
                return True, resp
            if msg == "当前用户在该时段已存在座位预约，不可重复预约":
                return True, resp
            if msg == "开放预约时间19:20":
                # 尚未开放，继续重试
                time.sleep(0.3)
                continue
            if msg == "该空间当前状态不可预约":
                # 座位不可用（被别人先抢走了）
                return False, resp
            # 其他未知状态：短暂等待再试
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"第 {i} 次请求异常: {e}")
            time.sleep(0.5)
    return False, None


# ============ 钉钉推送 ============
def send_dingtalk(title, content, token, secret):
    if not token:
        logger.info("未配置 DD_BOT_TOKEN，跳过钉钉推送")
        return
    url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
    headers = {"Content-Type": "application/json"}
    payload = {"msgtype": "text", "text": {"content": f"{title}\n{content}"}}
    if token and secret:
        ts = str(round(time.time() * 1000))
        string_to_sign = f"{ts}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(
            base64.b64encode(hmac_code).decode("utf-8").strip()
        )
        url = f"{url}&timestamp={ts}&sign={sign}"
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        logger.info(f"钉钉推送响应: {r.json()}")
    except Exception as e:
        logger.error(f"钉钉推送失败: {e}")


# ============ 主流程 ============
def main():
    cfg = load_config()
    username = cfg.get("USERNAME")
    password = cfg.get("PASSWORD")
    dd_token = cfg.get("DD_BOT_TOKEN")
    dd_secret = cfg.get("DD_BOT_SECRET")
    github_mode = bool(cfg.get("GITHUB", False))

    logger.info("=" * 50)
    logger.info(f"开始执行：座位 {SEAT_NO} (id={SEAT_ID}) @ {CLASSROOM_NAME}")

    # 1. 等待到 19:20
    wait_until_1920(github_mode)

    # 2. 提前/同时准备 token 和 segment
    try:
        _, auth_token = get_bearer_token(username, password)
    except Exception as e:
        msg = f"获取登录 Token 失败: {e}"
        logger.error(msg)
        send_dingtalk("❌ 座位预约失败", msg, dd_token, dd_secret)
        sys.exit(1)

    try:
        date_str = get_tomorrow_date()
        build_id = classroom_id_mapping.get(CLASSROOM_NAME, BUILD_ID)
        segment = get_segment(build_id, date_str)
    except Exception as e:
        msg = f"获取日期/segment 失败: {e}"
        logger.error(msg)
        send_dingtalk("❌ 座位预约失败", msg, dd_token, dd_secret)
        sys.exit(1)

    # 3. 抢座
    ok, resp = reserve_loop(auth_token, SEAT_ID, segment, max_attempts=20)

    if ok:
        content = (
            f"🎉 {date_str} 座位 {SEAT_NO} (id={SEAT_ID}) @ {CLASSROOM_NAME} 预约成功\n"
            f"系统响应: {json.dumps(resp, ensure_ascii=False)}"
        )
        logger.info("预约成功")
        send_dingtalk("✅ 座位预约成功", content, dd_token, dd_secret)
    else:
        content = (
            f"❌ {date_str} 座位 {SEAT_NO} (id={SEAT_ID}) @ {CLASSROOM_NAME} 预约失败\n"
            f"最后一次响应: {json.dumps(resp, ensure_ascii=False) if resp else '无'}"
        )
        logger.error("预约失败（达到重试上限或座位已不可用）")
        send_dingtalk("❌ 座位预约失败", content, dd_token, dd_secret)
        sys.exit(1)


if __name__ == "__main__":
    main()

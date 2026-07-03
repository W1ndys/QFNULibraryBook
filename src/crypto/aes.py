"""
统一 AES 加密模块 — 仅使用 pycryptodome
"""
import base64
from datetime import datetime

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# 座位 API 固定 IV
_SEAT_IV = "ZZWBKJ_ZHIHUAWEI"


def encrypt_with_key(plaintext: str, key: str, iv: str) -> str:
    """通用 AES-CBC 加密。key/iv 为 UTF-8 字符串，返回 base64 编码的密文。"""
    key_bytes = key.encode("utf-8")
    iv_bytes = iv.encode("utf-8")
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    ciphertext = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ciphertext).decode("utf-8")


def decrypt_with_key(ciphertext_b64: str, key: str, iv: str) -> str:
    """通用 AES-CBC 解密。encrypt_with_key 的逆操作。"""
    key_bytes = key.encode("utf-8")
    iv_bytes = iv.encode("utf-8")
    ciphertext = base64.b64decode(ciphertext_b64)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
    return decrypted.decode("utf-8")


def _get_seat_key() -> str:
    """生成座位 API 加密密钥：YYYYMMDD + 回文"""
    current_date = datetime.now().strftime("%Y%m%d")
    return current_date + current_date[::-1]


def encrypt_seat_data(json_text: str) -> str:
    """加密座位预约/签到请求体。使用日期回文密钥和固定 IV。"""
    return encrypt_with_key(json_text, _get_seat_key(), _SEAT_IV)


def decrypt_seat_data(ciphertext_b64: str) -> str:
    """解密座位预约/签到响应体。encrypt_seat_data 的逆操作。"""
    return decrypt_with_key(ciphertext_b64, _get_seat_key(), _SEAT_IV)


def encrypt_login_data(data: str, key: str) -> str:
    """
    加密登录数据（密码/滑块验证码）。
    在明文前添加 64 字节随机前缀，使用随机 16 字节 IV。
    """
    import random

    chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
    prefix = "".join(random.choice(chars) for _ in range(64))
    iv = "".join(random.choice(chars) for _ in range(16))
    plaintext = prefix + data
    return encrypt_with_key(plaintext, key, iv)

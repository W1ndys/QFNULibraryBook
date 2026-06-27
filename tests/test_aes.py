"""
测试 py/crypto/aes.py — AES 加密模块
"""
import base64
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest

from crypto.aes import (
    encrypt_with_key,
    decrypt_with_key,
    _get_seat_key,
    encrypt_seat_data,
    decrypt_seat_data,
    encrypt_login_data,
)


# ========== 通用加解密 ==========

class TestEncryptDecryptWithKey:
    """encrypt_with_key / decrypt_with_key 往返测试"""

    def test_encrypt_decrypt_roundtrip(self):
        """加解密往返后明文一致"""
        key = "0123456789abcdef"
        iv = "fedcba9876543210"
        plaintext = "Hello, AES-CBC!"
        ciphertext = encrypt_with_key(plaintext, key, iv)
        result = decrypt_with_key(ciphertext, key, iv)
        assert result == plaintext

    def test_encrypt_with_key_known_vector(self):
        """相同 key/iv/明文，输出稳定可回归"""
        key = "0123456789abcdef"
        iv = "fedcba9876543210"
        plaintext = "test data"
        # 连续加密两次，结果一致（无随机成分）
        c1 = encrypt_with_key(plaintext, key, iv)
        c2 = encrypt_with_key(plaintext, key, iv)
        assert c1 == c2

    def test_decrypt_bad_ciphertext(self):
        """垃圾 base64 输入抛出异常"""
        key = "0123456789abcdef"
        iv = "fedcba9876543210"
        with pytest.raises(Exception):
            decrypt_with_key("not-valid-base64!!!", key, iv)

    def test_decrypt_wrong_key(self):
        """密钥不匹配时解密失败"""
        key_a = "0123456789abcdef"
        key_b = "abcdef0123456789"
        iv = "fedcba9876543210"
        ciphertext = encrypt_with_key("secret", key_a, iv)
        with pytest.raises(ValueError):
            decrypt_with_key(ciphertext, key_b, iv)

    def test_roundtrip_unicode(self):
        """中文明文正常加解密"""
        key = "0123456789abcdef"
        iv = "fedcba9876543210"
        plaintext = "曲阜师范大学图书馆"
        ciphertext = encrypt_with_key(plaintext, key, iv)
        assert decrypt_with_key(ciphertext, key, iv) == plaintext

    def test_roundtrip_empty_string(self):
        """空字符串加解密"""
        key = "0123456789abcdef"
        iv = "fedcba9876543210"
        ciphertext = encrypt_with_key("", key, iv)
        assert decrypt_with_key(ciphertext, key, iv) == ""


# ========== 座位 API 密钥生成 ==========

class TestGetSeatKey:
    """_get_seat_key 日期回文密钥测试"""

    def test_get_seat_key_format(self):
        """mock 固定日期，验证回文结构"""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20260628"
        mock_cls = MagicMock()
        mock_cls.now.return_value = mock_now
        with patch("crypto.aes.datetime", mock_cls):
            result = _get_seat_key()
        assert result == "2026062882606202"

    def test_get_seat_key_length(self):
        """始终 16 字符"""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20260628"
        mock_cls = MagicMock()
        mock_cls.now.return_value = mock_now
        with patch("crypto.aes.datetime", mock_cls):
            result = _get_seat_key()
        assert len(result) == 16

    def test_get_seat_key_is_palindrome_structure(self):
        """前 8 位是日期，后 8 位是日期回文"""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20260101"
        mock_cls = MagicMock()
        mock_cls.now.return_value = mock_now
        with patch("crypto.aes.datetime", mock_cls):
            key = _get_seat_key()
        assert key[:8] == "20260101"
        assert key[8:] == "10106202"


# ========== 座位数据加解密 ==========

class TestSeatDataEncryption:
    """encrypt_seat_data / decrypt_seat_data 测试"""

    def test_encrypt_decrypt_seat_data_roundtrip(self):
        """座位数据加解密往返一致"""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20260628"
        mock_cls = MagicMock()
        mock_cls.now.return_value = mock_now
        with patch("crypto.aes.datetime", mock_cls):
            plaintext = '{"seat_id":"100","segment":"999"}'
            ciphertext = encrypt_seat_data(plaintext)
            result = decrypt_seat_data(ciphertext)
        assert result == plaintext

    def test_encrypt_seat_data_uses_fixed_iv(self):
        """验证使用固定 IV 'ZZWBKJ_ZHIHUAWEI'"""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20260628"
        mock_cls = MagicMock()
        mock_cls.now.return_value = mock_now
        with patch("crypto.aes.datetime", mock_cls):
            with patch("crypto.aes.encrypt_with_key") as mock_enc:
                mock_enc.return_value = "fake_cipher"
                encrypt_seat_data('{"test":1}')
                # 检查调用参数中的 IV
                call_args = mock_enc.call_args
                assert call_args[0][2] == "ZZWBKJ_ZHIHUAWEI"


# ========== 登录数据加密 ==========

class TestLoginDataEncryption:
    """encrypt_login_data 测试"""

    def test_encrypt_login_data_non_deterministic(self):
        """同输入两次调用，输出不同（随机前缀+IV）"""
        key = "0123456789abcdef"
        r1 = encrypt_login_data("password123", key)
        r2 = encrypt_login_data("password123", key)
        assert r1 != r2

    def test_encrypt_login_data_valid_base64(self):
        """输出可正常 base64 解码"""
        key = "0123456789abcdef"
        result = encrypt_login_data("test", key)
        # 不应抛出异常
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_encrypt_login_data_chinese_plaintext(self):
        """中文明文正常加密不报错"""
        key = "0123456789abcdef"
        result = encrypt_login_data("测试密码", key)
        decoded = base64.b64decode(result)
        # 64 字节前缀 + 中文数据（至少 16 字节 AES 块）
        assert len(decoded) >= 64 + 16

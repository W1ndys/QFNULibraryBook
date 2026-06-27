"""
公共测试 fixtures — 共享配置、mock 对象和样本数据
"""
import pytest
from unittest.mock import MagicMock

from config.config import AppConfig


@pytest.fixture
def sample_config():
    """填充所有字段的 AppConfig 实例（假值）"""
    return AppConfig(
        push_method="TG",
        channel_id="123456",
        telegram_bot_token="fake:token",
        bark_url="https://example.com/bark/",
        bark_extra="?sound=bird",
        anpush_token="fake_anpush",
        anpush_channel="ch1",
        dd_bot_token="fake_dd_token",
        dd_bot_secret="fake_dd_secret",
        username="20240001",
        password="testpass123",
        mode="2",
        classrooms_name=["综合楼-801自习室"],
        seat_id=[[3796, 3810]],
        date="tomorrow",
        github="",
    )


@pytest.fixture
def minimal_config():
    """仅必填字段的 AppConfig"""
    return AppConfig(username="20240001", password="testpass")


@pytest.fixture
def sample_yaml_config_path(tmp_path):
    """写入临时完整 YAML 配置文件，返回路径"""
    content = (
        "USERNAME: '20240001'\n"
        "PASSWORD: secret\n"
        "MODE: '2'\n"
        "CLASSROOMS_NAME:\n"
        "  - 综合楼-801自习室\n"
        "SEAT_ID:\n"
        "  - [3796, 3810]\n"
        "DATE: tomorrow\n"
        "PUSH_METHOD: TG\n"
        "CHANNEL_ID: '123456'\n"
        "TELEGRAM_BOT_TOKEN: fake:token\n"
        "BARK_URL: https://example.com/bark/\n"
        "BARK_EXTRA: '?sound=bird'\n"
        "ANPUSH_TOKEN: fake_anpush\n"
        "ANPUSH_CHANNEL: ch1\n"
        "DD_BOT_TOKEN: fake_dd_token\n"
        "DD_BOT_SECRET: fake_dd_secret\n"
        "GITHUB: ''\n"
    )
    p = tmp_path / "config.yml"
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def minimal_yaml_config_path(tmp_path):
    """写入临时最简 YAML 配置文件，返回路径"""
    content = (
        "USERNAME: '20240001'\n"
        "PASSWORD: secret\n"
    )
    p = tmp_path / "config_minimal.yml"
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def fake_token_mgr():
    """不调用网络的 MagicMock TokenManager"""
    mgr = MagicMock()
    mgr.get_token.return_value = "bearerFAKE_TOKEN_12345"
    return mgr


@pytest.fixture
def sample_seat_data():
    """模拟 API 座位列表（混合状态）"""
    return [
        {"id": "3796", "no": "001", "status_name": "空闲", "area": "16"},
        {"id": "3797", "no": "002", "status_name": "已预约", "area": "16"},
        {"id": "3798", "no": "003", "status_name": "空闲", "area": "16"},
        {"id": "3799", "no": "004", "status_name": "使用中", "area": "16"},
    ]


@pytest.fixture
def sample_member_seat_response():
    """模拟 /api/Member/seat 响应"""
    return {
        "code": 1,
        "msg": "操作成功",
        "data": {
            "data": [
                {
                    "id": "5001",
                    "name": "001",
                    "nameMerge": "综合楼-801 001",
                    "statusName": "预约成功",
                },
            ]
        },
    }


@pytest.fixture
def sample_seat_api_response():
    """模拟 /api/Seat/seat 完整响应"""
    return {
        "code": 1,
        "msg": "操作成功",
        "data": [
            {
                "id": "3796",
                "no": "001",
                "name": "001",
                "area": "16",
                "category": "12",
                "point_x": "27.1875",
                "point_y": "14.05",
                "width": "1.77",
                "height": "3.19",
                "status": "1",
                "status_name": "空闲",
                "area_name": "综合楼-801自习室",
            },
            {
                "id": "3797",
                "no": "002",
                "name": "002",
                "area": "16",
                "category": "12",
                "point_x": "30.0",
                "point_y": "14.05",
                "width": "1.77",
                "height": "3.19",
                "status": "2",
                "status_name": "已预约",
                "area_name": "综合楼-801自习室",
            },
        ],
    }

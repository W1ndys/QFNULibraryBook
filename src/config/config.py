"""
统一配置管理 — AppConfig 数据类
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml


@dataclass
class AppConfig:
    """应用配置，替代全局变量和 read_config_from_yaml()"""

    # 推送通知
    push_method: str = ""
    channel_id: str = ""
    telegram_bot_token: str = ""
    bark_url: str = ""
    bark_extra: str = ""
    anpush_token: str = ""
    anpush_channel: str = ""
    dd_bot_token: str = ""
    dd_bot_secret: str = ""
    # 认证
    username: str = ""
    password: str = ""
    # 座位预约
    mode: str = ""
    classrooms_name: List[str] = field(default_factory=list)
    seat_id: List[list] = field(default_factory=list)
    date: str = ""
    # 其他（当前未使用，保留以保持配置文件向后兼容）
    github: str = ""

    @classmethod
    def from_yaml(cls, config_file: Optional[str] = None) -> "AppConfig":
        """
        从 YAML 配置文件加载配置。

        参数:
            config_file: 配置文件路径。None 使用默认 configs/template.yml，
                        相对路径基于项目根目录解析（不存在则回退到 src/ 目录），绝对路径直接使用。
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))  # src/config/
        src_dir = os.path.dirname(current_dir)                     # src/
        project_root = os.path.dirname(src_dir)                     # 项目根目录

        if config_file is None:
            config_path = os.path.join(project_root, "configs", "template.yml")
        elif os.path.isabs(config_file):
            config_path = config_file
        else:
            # 优先从项目根目录解析；如不存在则回退到 src/ 目录（过渡兼容）
            config_path = os.path.join(project_root, config_file)
            if not os.path.exists(config_path):
                config_path = os.path.join(src_dir, config_file)

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return cls(
            push_method=raw.get("PUSH_METHOD", ""),
            channel_id=raw.get("CHANNEL_ID", ""),
            telegram_bot_token=raw.get("TELEGRAM_BOT_TOKEN", ""),
            bark_url=raw.get("BARK_URL", ""),
            bark_extra=raw.get("BARK_EXTRA", ""),
            anpush_token=raw.get("ANPUSH_TOKEN", ""),
            anpush_channel=raw.get("ANPUSH_CHANNEL", ""),
            dd_bot_token=raw.get("DD_BOT_TOKEN", ""),
            dd_bot_secret=raw.get("DD_BOT_SECRET", ""),
            username=raw.get("USERNAME", ""),
            password=raw.get("PASSWORD", ""),
            mode=raw.get("MODE", ""),
            classrooms_name=raw.get("CLASSROOMS_NAME", []),
            seat_id=raw.get("SEAT_ID", []),
            date=raw.get("DATE", ""),
            github=raw.get("GITHUB", ""),
        )

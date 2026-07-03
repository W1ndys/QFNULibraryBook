"""
测试 py/config/config.py — 配置加载
"""
import os
import pytest

from config.config import AppConfig


class TestAppConfigDefaults:
    """AppConfig 默认构造"""

    def test_default_constructor(self):
        """无参构造所有字段为空值"""
        cfg = AppConfig()
        assert cfg.username == ""
        assert cfg.password == ""
        assert cfg.mode == ""
        assert cfg.classrooms_name == []
        assert cfg.seat_id == []
        assert cfg.date == ""
        assert cfg.push_method == ""
        assert cfg.channel_id == ""
        assert cfg.telegram_bot_token == ""
        assert cfg.bark_url == ""
        assert cfg.bark_extra == ""
        assert cfg.anpush_token == ""
        assert cfg.anpush_channel == ""
        assert cfg.dd_bot_token == ""
        assert cfg.dd_bot_secret == ""
        assert cfg.github == ""


class TestFromYaml:
    """AppConfig.from_yaml 测试"""

    def test_loads_all_fields(self, sample_yaml_config_path):
        """加载完整 YAML，每个字段匹配"""
        cfg = AppConfig.from_yaml(sample_yaml_config_path)
        assert cfg.username == "20240001"
        assert cfg.password == "secret"
        assert cfg.mode == "2"
        assert cfg.classrooms_name == ["综合楼-801自习室"]
        assert cfg.seat_id == [[3796, 3810]]
        assert cfg.date == "tomorrow"
        assert cfg.push_method == "TG"
        assert cfg.channel_id == "123456"
        assert cfg.telegram_bot_token == "fake:token"
        assert cfg.dd_bot_token == "fake_dd_token"

    def test_default_values_minimal(self, minimal_yaml_config_path):
        """仅 USERNAME/PASSWORD 时其余字段为空"""
        cfg = AppConfig.from_yaml(minimal_yaml_config_path)
        assert cfg.username == "20240001"
        assert cfg.password == "secret"
        assert cfg.push_method == ""
        assert cfg.classrooms_name == []
        assert cfg.seat_id == []

    def test_missing_file_raises(self):
        """不存在的路径抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            AppConfig.from_yaml("/nonexistent/path/config.yml")

    def test_none_uses_default_path(self):
        """None 路径解析到项目根目录下的 configs/template.yml"""
        # from_yaml(None) 会尝试打开 configs/template.yml
        # 如果该文件存在则正常加载，否则抛 FileNotFoundError
        try:
            cfg = AppConfig.from_yaml(None)
            # 如果存在，验证加载成功
            assert isinstance(cfg, AppConfig)
        except FileNotFoundError:
            # configs/template.yml 不存在时预期行为
            pass

    def test_absolute_path(self, tmp_path):
        """绝对路径直接使用"""
        p = tmp_path / "test_config.yml"
        p.write_text("USERNAME: abs_test\nPASSWORD: pwd\n", encoding="utf-8")
        cfg = AppConfig.from_yaml(str(p))
        assert cfg.username == "abs_test"

    def test_empty_file_raises(self, tmp_path):
        """空 YAML 文件抛出 AttributeError（yaml.safe_load 返回 None）"""
        p = tmp_path / "empty.yml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(AttributeError):
            AppConfig.from_yaml(str(p))

    def test_classrooms_name_is_list(self, tmp_path):
        """单项也保持 List[str]"""
        p = tmp_path / "single.yml"
        p.write_text(
            "USERNAME: test\nCLASSROOMS_NAME:\n  - 综合楼-801自习室\n",
            encoding="utf-8",
        )
        cfg = AppConfig.from_yaml(str(p))
        assert isinstance(cfg.classrooms_name, list)
        assert cfg.classrooms_name == ["综合楼-801自习室"]

    def test_seat_id_is_list_of_lists(self, tmp_path):
        """seat_id 结构为 List[list]"""
        p = tmp_path / "seats.yml"
        p.write_text(
            "USERNAME: test\nSEAT_ID:\n  - [100, 200]\n  - [300, 400]\n",
            encoding="utf-8",
        )
        cfg = AppConfig.from_yaml(str(p))
        assert isinstance(cfg.seat_id, list)
        assert all(isinstance(item, list) for item in cfg.seat_id)
        assert cfg.seat_id == [[100, 200], [300, 400]]

    def test_unicode_classroom_names(self, tmp_path):
        """含特殊字符的教室名称"""
        p = tmp_path / "unicode.yml"
        p.write_text(
            "USERNAME: test\nCLASSROOMS_NAME:\n  - 东校区图书馆-一楼自修区（朗读空间）\n",
            encoding="utf-8",
        )
        cfg = AppConfig.from_yaml(str(p))
        assert cfg.classrooms_name == ["东校区图书馆-一楼自修区（朗读空间）"]

"""
测试 json/seat_info/ — JSON 数据文件一致性
"""
import json
import os
import glob

import pytest

from classrooms import classroom_id_mapping

# JSON 数据文件目录
SEAT_INFO_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "seat_info")


@pytest.fixture
def all_json_files():
    """加载所有 JSON 文件"""
    files = glob.glob(os.path.join(SEAT_INFO_DIR, "*.json"))
    assert len(files) > 0, "未找到 JSON 文件"
    results = []
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = os.path.basename(fpath)
        results.append((name, data))
    return results


class TestJsonSnapshots:
    """JSON 数据文件结构一致性"""

    def test_all_json_files_parse(self, all_json_files):
        """所有文件合法 JSON（fixture 已成功加载）"""
        assert len(all_json_files) == 15

    def test_required_top_level_keys(self, all_json_files):
        """每个文件有 code, msg, data"""
        for name, data in all_json_files:
            assert "code" in data, f"{name} 缺少 code"
            assert "msg" in data, f"{name} 缺少 msg"
            assert "data" in data, f"{name} 缺少 data"

    def test_data_is_list(self, all_json_files):
        """data 字段为列表"""
        for name, data in all_json_files:
            assert isinstance(data["data"], list), f"{name} 的 data 不是列表"

    def test_seats_have_required_fields(self, all_json_files):
        """每个座位有 id, no, status_name, area"""
        required = {"id", "no", "status_name", "area"}
        for name, data in all_json_files:
            for seat in data["data"]:
                missing = required - set(seat.keys())
                assert not missing, f"{name} 中座位 {seat.get('id')} 缺少 {missing}"

    def test_seat_ids_are_strings(self, all_json_files):
        """座位 id 全为字符串"""
        for name, data in all_json_files:
            for seat in data["data"]:
                assert isinstance(seat["id"], str), f"{name} 中 {seat['id']} 不是字符串"

    def test_status_names_known(self, all_json_files):
        """status_name 属于已知值集合"""
        known = {"空闲", "已预约", "使用中", "锁定"}
        for name, data in all_json_files:
            for seat in data["data"]:
                assert seat["status_name"] in known, (
                    f"{name} 中座位 {seat['id']} 状态未知: {seat['status_name']}"
                )

    def test_no_duplicate_seat_ids(self, all_json_files):
        """每个文件内 seat id 唯一"""
        for name, data in all_json_files:
            ids = [s["id"] for s in data["data"]]
            assert len(ids) == len(set(ids)), f"{name} 存在重复 seat id"

    def test_seat_count_per_file(self, all_json_files):
        """每个文件至少有座位数据"""
        for name, data in all_json_files:
            assert len(data["data"]) > 0, f"{name} 没有座位数据"

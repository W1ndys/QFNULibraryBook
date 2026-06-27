"""
测试 py/classrooms.py — 教室映射和排除列表
"""
from classrooms import classroom_id_mapping, EXCLUDE_ID


class TestClassroomIdMapping:
    """教室名称到 ID 的映射"""

    def test_mapping_entry_count(self):
        """共 22 个条目（18 主要 + 4 别名）"""
        assert len(classroom_id_mapping) == 22

    def test_primary_classrooms_unique_ids(self):
        """去除别名后，唯一 ID 数量为 18"""
        unique_ids = set(classroom_id_mapping.values())
        assert len(unique_ids) == 18

    def test_alias_resolves_correctly(self):
        """别名映射到正确的 ID"""
        assert classroom_id_mapping["东校区图书馆-三层自习室"] == 22
        assert classroom_id_mapping["东校区图书馆-三层自习室01"] == 22
        assert classroom_id_mapping["东校区图书馆-三层电子阅览室"] == 21
        assert classroom_id_mapping["西校区图书馆-五层自习室"] == 40

    def test_all_values_positive_int(self):
        """所有值为 int 且 > 0"""
        for name, cid in classroom_id_mapping.items():
            assert isinstance(cid, int), f"{name} 的值不是 int"
            assert cid > 0, f"{name} 的值 <= 0"

    def test_primary_classroom_samples(self):
        """几个主要教室的 ID 正确"""
        assert classroom_id_mapping["综合楼-801自习室"] == 16
        assert classroom_id_mapping["西校区图书馆-二层自习室"] == 45
        assert classroom_id_mapping["行政楼-四层东区自习室"] == 13
        assert classroom_id_mapping["电视台楼-二层自习室"] == 12


class TestExcludeId:
    """无插座座位排除集合"""

    def test_exclude_id_count(self):
        """共 104 个排除座位 ID"""
        assert len(EXCLUDE_ID) == 104

    def test_exclude_id_all_strings(self):
        """所有元素为字符串"""
        for sid in EXCLUDE_ID:
            assert isinstance(sid, str), f"{sid} 不是字符串"

    def test_exclude_id_no_mutation(self):
        """集合类型确认"""
        assert isinstance(EXCLUDE_ID, set)

    def test_exclude_id_contains_expected(self):
        """包含已知的无插座座位"""
        assert "7115" in EXCLUDE_ID
        assert "7806" in EXCLUDE_ID
        assert "7887" in EXCLUDE_ID

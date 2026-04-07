"""
基础测试套件
"""

import pytest
import tempfile
from pathlib import Path

from memchinesepalace.compressor import (
    WenjianCompressor, WenjianSpec, WenjianEntry, MemoryType, Importance, Status
)
from memchinesepalace.palace import Palace, Dian, Xuan, Du, Jian, DianType, LangType
from memchinesepalace.knowledge_graph import KnowledgeGraph


# ─────────────────────────────────────────────────────────────────────────────
# 文简压缩测试
# ─────────────────────────────────────────────────────────────────────────────

class TestWenjianCompressor:

    def setup_method(self):
        self.compressor = WenjianCompressor(use_tiktoken=False)

    def test_rule_compress_removes_particles(self):
        text = "我们的团队决定了要使用PostgreSQL数据库"
        result = self.compressor.rule_compress(text)
        assert "的" not in result
        assert "了" not in result
        assert "要" in result or "PostgreSQL" in result

    def test_rule_compress_simplifies_phrases(self):
        result = self.compressor.rule_compress("我们决定使用Clerk")
        assert "议定" in result

    def test_rule_compress_preserves_english(self):
        text = "决定使用 PostgreSQL 而不是 MySQL"
        result = self.compressor.rule_compress(text)
        assert "PostgreSQL" in result
        assert "MySQL" in result

    def test_compression_ratio_calculation(self):
        original = "这是一段较长的测试文本，用于验证压缩比计算是否正确"
        compressed = "测试文本·压缩比验证"
        ratio = self.compressor.compression_ratio(original, compressed)
        assert ratio > 1.0

    def test_wenjian_spec_not_empty(self):
        spec = WenjianSpec.as_prompt()
        assert len(spec) > 100
        assert "文简" in spec
        assert "议" in spec

    def test_short_spec_contains_key_elements(self):
        spec = WenjianSpec.as_short_prompt()
        assert "议" in spec
        assert "事" in spec

    def test_llm_compress_prompt_contains_text(self):
        text = "决定切换到 Clerk"
        prompt = self.compressor.get_llm_compress_prompt(text, MemoryType.YI)
        assert text in prompt
        assert "文简" in prompt
        assert "议" in prompt


class TestWenjianEntry:

    def test_to_wenjian_basic(self):
        entry = WenjianEntry(
            memory_type=MemoryType.YI,
            content="迁身份至Clerk",
            importance=Importance.KEY,
            status=Status.DECIDED,
        )
        result = entry.to_wenjian()
        assert result.startswith("议")
        assert "迁身份至Clerk" in result
        assert "★★★★" in result
        assert "[定]" in result

    def test_from_wenjian_parses_type(self):
        entry = WenjianEntry.from_wenjian("事 26/03/15 完成auth迁移[毕]★★★")
        assert entry.memory_type == MemoryType.SHI

    def test_roundtrip(self):
        original = WenjianEntry(
            memory_type=MemoryType.CE,
            content="荐使用PostgreSQL",
            importance=Importance.HIGH,
        )
        wenjian_text = original.to_wenjian()
        parsed = WenjianEntry.from_wenjian(wenjian_text)
        assert parsed.memory_type == MemoryType.CE
        assert "PostgreSQL" in parsed.content


# ─────────────────────────────────────────────────────────────────────────────
# 宫殿结构测试
# ─────────────────────────────────────────────────────────────────────────────

class TestPalace:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.palace = Palace(Path(self.tmp) / "palace")

    def teardown_method(self):
        self.palace.close()

    def test_upsert_and_get_dian(self):
        dian = Dian(name="test-project", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        retrieved = self.palace.get_dian("test-project")
        assert retrieved is not None
        assert retrieved.name == "test-project"
        assert retrieved.dian_type == DianType.PROJECT

    def test_upsert_and_get_xuan(self):
        dian = Dian(name="test-project", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)

        xuan = Xuan(name="auth", dian_name="test-project")
        self.palace.upsert_xuan(xuan)
        retrieved = self.palace.get_xuan("auth", "test-project")
        assert retrieved is not None
        assert retrieved.name == "auth"

    def test_dian_xuan_relationship(self):
        dian = Dian(name="test-project", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        xuan = Xuan(name="auth", dian_name="test-project")
        self.palace.upsert_xuan(xuan)

        updated_dian = self.palace.get_dian("test-project")
        assert "auth" in updated_dian.xuan_names

    def test_add_and_get_du(self):
        dian = Dian(name="proj", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        xuan = Xuan(name="db", dian_name="proj")
        self.palace.upsert_xuan(xuan)

        du = Du(
            id=Du.generate_id("test content", "test-source"),
            content="决定使用PostgreSQL",
            source="test",
            lang_type=LangType.JUEYI,
            xuan_name="db",
            dian_name="proj",
        )
        du_id = self.palace.add_du(du)
        retrieved = self.palace.get_du(du_id)
        assert retrieved is not None
        assert retrieved.content == "决定使用PostgreSQL"

    def test_upsert_and_search_jian(self):
        dian = Dian(name="proj", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        xuan = Xuan(name="db", dian_name="proj")
        self.palace.upsert_xuan(xuan)

        jian = Jian(
            id="test-jian-1",
            wenjian_text="议 迁身份至Clerk[定]★★★★",
            du_ids=[],
            lang_type=LangType.JUEYI,
            xuan_name="db",
            dian_name="proj",
            importance=Importance.KEY,
        )
        self.palace.upsert_jian(jian)
        results = self.palace.search_jian(dian_name="proj")
        assert len(results) == 1
        assert results[0].id == "test-jian-1"

    def test_stats(self):
        dian = Dian(name="proj", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        stats = self.palace.stats()
        assert stats["殿数"] >= 1

    def test_rebuild_dao(self):
        # 创建两个殿，各有一个同名轩
        for proj in ["proj-a", "proj-b"]:
            dian = Dian(name=proj, dian_type=DianType.PROJECT)
            self.palace.upsert_dian(dian)
            xuan = Xuan(name="auth", dian_name=proj)
            self.palace.upsert_xuan(xuan)

        count = self.palace.rebuild_dao()
        assert count >= 1
        daos = self.palace.find_dao("auth")
        assert len(daos) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 知识图谱测试
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeGraph:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.kg = KnowledgeGraph(Path(self.tmp) / "kg.db")

    def teardown_method(self):
        self.kg.close()

    def test_add_and_query(self):
        self.kg.add_triple("伟明", "负责", "后端")
        triples = self.kg.query_entity("伟明")
        assert len(triples) == 1
        assert triples[0].subject == "伟明"
        assert triples[0].relation == "负责"
        assert triples[0].obj == "后端"

    def test_invalidate(self):
        self.kg.add_triple("伟明", "负责", "后端", valid_from="2023-01-01")
        self.kg.invalidate("伟明", "负责", "后端", ended="2024-01-01")
        triples = self.kg.query_entity("伟明", as_of="2024-06-01")
        active = [t for t in triples if t.is_current]
        assert len(active) == 0

    def test_contradiction_detection(self):
        self.kg.add_triple("项目A", "状态", "进行中")
        conflict = self.kg.check_contradiction("项目A", "状态", "已完成")
        assert conflict is not None
        assert "矛盾" in conflict["message"]

    def test_no_contradiction_same_value(self):
        self.kg.add_triple("项目A", "状态", "进行中")
        conflict = self.kg.check_contradiction("项目A", "状态", "进行中")
        assert conflict is None

    def test_timeline(self):
        self.kg.add_triple("auth迁移", "状态", "计划中", valid_from="2026-01-01")
        self.kg.add_triple("auth迁移", "状态", "进行中", valid_from="2026-01-15")
        self.kg.add_triple("auth迁移", "状态", "已完成", valid_from="2026-02-01")
        timeline = self.kg.timeline("auth迁移")
        assert len(timeline) >= 3

    def test_to_wenjian_summary(self):
        self.kg.add_triple("伟明", "角色", "后端工程师")
        self.kg.add_triple("伟明", "任期", "3年")
        summary = self.kg.to_wenjian_summary("伟明")
        assert "伟明" in summary

    def test_stats(self):
        self.kg.add_triple("A", "rel", "B")
        stats = self.kg.stats()
        assert stats["三元组总数"] >= 1

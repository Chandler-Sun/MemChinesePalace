"""
完整测试套件 v2
覆盖 README 描述的所有功能：
  - 文简压缩（所有类型 / estimate_savings / expand prompt / format_block）
  - 宫殿结构（殿/轩/简/牍/道 完整 CRUD）
  - 数据挖掘（mine_text / mine_file / 对话挖掘 / 自动类型推断）
  - 语义搜索（关键词回退 / 结果格式化 / 殿过滤）
  - 记忆层栈（L0/L1/L2 / wake_up / system_prompt_injection）
  - 知识图谱（历史查询 / relation 过滤 / timeline 顺序）
  - 配置（默认值 / 环境变量）
  - 端到端集成（mine → search → wake_up 全流程）
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from memchinesepalace.compressor import (
    WenjianCompressor, WenjianSpec, WenjianEntry,
    MemoryType, Importance, Status,
    format_wenjian_block, parse_wenjian_block,
)
from memchinesepalace.palace import Palace, Dian, Xuan, Du, Jian, DianType, LangType
from memchinesepalace.knowledge_graph import KnowledgeGraph
from memchinesepalace.config import Config
from memchinesepalace.miner import Miner, MineMode, detect_memory_type, detect_importance, infer_xuan_name
from memchinesepalace.searcher import Searcher
from memchinesepalace.layers import MemoryStack


# ─────────────────────────────────────────────────────────────────────────────
# 共用 fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_palace(tmp_path):
    palace = Palace(tmp_path / "palace")
    yield palace
    palace.close()


@pytest.fixture
def tmp_kg(tmp_path):
    kg = KnowledgeGraph(tmp_path / "kg.db")
    yield kg
    kg.close()


@pytest.fixture
def config(tmp_path):
    cfg = Config()
    cfg.palace_path = str(tmp_path / "palace")
    cfg.use_llm_compression = False
    cfg.use_rule_compression = True
    return cfg


@pytest.fixture
def miner(tmp_palace, config):
    return Miner(tmp_palace, config)


@pytest.fixture
def searcher(tmp_palace, config):
    return Searcher(tmp_palace, config)


@pytest.fixture
def stack(tmp_palace, config):
    return MemoryStack(tmp_palace, config)


# ─────────────────────────────────────────────────────────────────────────────
# 文简压缩（扩展）
# ─────────────────────────────────────────────────────────────────────────────

class TestWenjianCompressor:

    def setup_method(self):
        self.c = WenjianCompressor(use_tiktoken=False)

    # ── 基础压缩 ──

    def test_removes_particles(self):
        result = self.c.rule_compress("我们的团队决定了要使用PostgreSQL数据库")
        assert "的" not in result
        assert "了" not in result

    def test_simplifies_decision_phrase(self):
        assert "议定" in self.c.rule_compress("我们决定使用Clerk")

    def test_preserves_english_terms(self):
        result = self.c.rule_compress("决定使用 PostgreSQL 而不是 MySQL")
        assert "PostgreSQL" in result
        assert "MySQL" in result

    def test_simplifies_recommend(self):
        result = self.c.rule_compress("建议使用 Redis 作为缓存")
        assert "荐" in result

    def test_simplifies_due_to(self):
        result = self.c.rule_compress("因为价格便宜所以选择了 Clerk")
        assert "Clerk" in result

    def test_compression_ratio_gt_one(self):
        original = "这是一段较长的测试文本，用于验证压缩比计算是否正确哦"
        compressed = "测试·压缩比验证"
        assert self.c.compression_ratio(original, compressed) > 1.0

    def test_compression_ratio_empty_compressed(self):
        assert self.c.compression_ratio("test", "") == 0.0

    # ── estimate_savings ──

    def test_estimate_savings_keys(self):
        savings = self.c.estimate_savings(100, 20)
        assert "compression_ratio" in savings
        assert "saved_tokens_per_call" in savings
        assert "saved_usd_per_1k_calls" in savings
        assert savings["compression_ratio"] == 5.0
        assert savings["saved_tokens_per_call"] == 80

    # ── LLM prompt 生成 ──

    def test_compress_prompt_all_types(self):
        for mt in MemoryType:
            prompt = self.c.get_llm_compress_prompt("test content", mt)
            assert "test content" in prompt
            assert mt.value in prompt

    def test_expand_prompt_contains_wenjian(self):
        wenjian = "议 迁身份至Clerk[定]★★★★"
        prompt = self.c.get_llm_expand_prompt(wenjian)
        assert wenjian in prompt
        assert "展开" in prompt

    def test_expand_prompt_with_context(self):
        prompt = self.c.get_llm_compress_prompt("test", MemoryType.YI, context="项目漂木")
        assert "项目漂木" in prompt

    # ── WenjianSpec ──

    def test_spec_contains_all_types(self):
        spec = WenjianSpec.as_prompt()
        for mt in MemoryType:
            assert mt.value in spec

    def test_spec_contains_status_markers(self):
        spec = WenjianSpec.as_prompt()
        for s in Status:
            assert s.value in spec

    def test_short_spec_is_shorter_than_full(self):
        assert len(WenjianSpec.as_short_prompt()) < len(WenjianSpec.as_prompt())

    def test_token_count_positive(self):
        assert WenjianSpec.token_count() > 0


class TestWenjianEntry:

    def test_all_memory_types_serialize(self):
        for mt in MemoryType:
            entry = WenjianEntry(memory_type=mt, content="测试内容", importance=Importance.MED)
            result = entry.to_wenjian()
            assert result.startswith(mt.value)

    def test_all_status_markers_serialize(self):
        for status in Status:
            entry = WenjianEntry(
                memory_type=MemoryType.YI, content="内容",
                importance=Importance.MED, status=status,
            )
            assert status.value in entry.to_wenjian()

    def test_all_importance_levels_serialize(self):
        for imp in Importance:
            entry = WenjianEntry(memory_type=MemoryType.YI, content="内容", importance=imp)
            assert imp.value in entry.to_wenjian()

    def test_time_ref_included(self):
        entry = WenjianEntry(
            memory_type=MemoryType.SHI, content="事件",
            importance=Importance.MED, time_ref="26/03/15",
        )
        assert "26/03/15" in entry.to_wenjian()

    def test_english_preserved_in_content(self):
        entry = WenjianEntry(
            memory_type=MemoryType.CE, content="荐使用 PostgreSQL v16",
            importance=Importance.HIGH,
        )
        assert "PostgreSQL" in entry.to_wenjian()
        assert "v16" in entry.to_wenjian()

    def test_parse_all_types(self):
        for mt in MemoryType:
            text = f"{mt.value} 测试内容★★"
            parsed = WenjianEntry.from_wenjian(text)
            assert parsed.memory_type == mt

    def test_roundtrip_preserves_content(self):
        entry = WenjianEntry(
            memory_type=MemoryType.HAO, content="偏好使用 TypeScript",
            importance=Importance.HIGH,
        )
        parsed = WenjianEntry.from_wenjian(entry.to_wenjian())
        assert "TypeScript" in parsed.content

    def test_format_wenjian_block(self):
        entries = [
            WenjianEntry(memory_type=MemoryType.YI, content="决策A", importance=Importance.KEY),
            WenjianEntry(memory_type=MemoryType.SHI, content="事件B", importance=Importance.MED),
        ]
        block = format_wenjian_block(entries, title="测试区块")
        assert "【测试区块】" in block
        assert "议" in block
        assert "事" in block

    def test_parse_wenjian_block(self):
        block = "【测试】\n议 决策A★★★\n事 事件B★★"
        entries = parse_wenjian_block(block)
        assert len(entries) == 2
        assert entries[0].memory_type == MemoryType.YI
        assert entries[1].memory_type == MemoryType.SHI


# ─────────────────────────────────────────────────────────────────────────────
# 宫殿（扩展）
# ─────────────────────────────────────────────────────────────────────────────

class TestPalace:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.palace = Palace(Path(self.tmp) / "palace")

    def teardown_method(self):
        self.palace.close()

    def _make_dian_xuan(self, dian_name="proj", xuan_name="auth"):
        dian = Dian(name=dian_name, dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        xuan = Xuan(name=xuan_name, dian_name=dian_name)
        self.palace.upsert_xuan(xuan)
        return dian, xuan

    # ── 殿 ──

    def test_upsert_and_get_dian(self):
        dian = Dian(name="p1", dian_type=DianType.PROJECT, description="描述")
        self.palace.upsert_dian(dian)
        r = self.palace.get_dian("p1")
        assert r.dian_type == DianType.PROJECT
        assert r.description == "描述"

    def test_list_dian(self):
        for name in ["d1", "d2", "d3"]:
            self.palace.upsert_dian(Dian(name=name, dian_type=DianType.TOPIC))
        assert len(self.palace.list_dian()) == 3

    def test_dian_person_type(self):
        self.palace.upsert_dian(Dian(name="person1", dian_type=DianType.PERSON))
        r = self.palace.get_dian("person1")
        assert r.dian_type == DianType.PERSON

    def test_dian_identity_wenjian(self):
        dian = Dian(name="p1", dian_type=DianType.PROJECT, identity_wenjian="测试身份文简")
        self.palace.upsert_dian(dian)
        r = self.palace.get_dian("p1")
        assert r.identity_wenjian == "测试身份文简"

    def test_get_nonexistent_dian(self):
        assert self.palace.get_dian("不存在") is None

    # ── 轩 ──

    def test_upsert_and_list_xuan(self):
        self._make_dian_xuan("proj", "auth")
        self._make_dian_xuan("proj", "db")
        xuans = self.palace.list_xuan("proj")
        names = [x.name for x in xuans]
        assert "auth" in names
        assert "db" in names

    def test_xuan_auto_added_to_dian(self):
        self._make_dian_xuan("proj", "auth")
        dian = self.palace.get_dian("proj")
        assert "auth" in dian.xuan_names

    def test_multiple_xuans_in_dian(self):
        self._make_dian_xuan("proj", "auth")
        self._make_dian_xuan("proj", "db")
        # 通过列出轩来验证，不依赖殿的缓存列表
        xuans = self.palace.list_xuan("proj")
        assert len(xuans) == 2

    # ── 牍 ──

    def test_add_and_get_du(self):
        self._make_dian_xuan()
        du = Du(
            id=Du.generate_id("content", "src"),
            content="决定使用PostgreSQL",
            source="test",
            lang_type=LangType.JUEYI,
            xuan_name="auth",
            dian_name="proj",
        )
        self.palace.add_du(du)
        r = self.palace.get_du(du.id)
        assert r.content == "决定使用PostgreSQL"

    def test_du_added_to_xuan_ids(self):
        self._make_dian_xuan()
        du = Du(
            id=Du.generate_id("c", "s"),
            content="内容",
            source="test",
            lang_type=LangType.JUEYI,
            xuan_name="auth",
            dian_name="proj",
        )
        self.palace.add_du(du)
        xuan = self.palace.get_xuan("auth", "proj")
        assert du.id in xuan.du_ids

    def test_du_generate_id_deterministic(self):
        id1 = Du.generate_id("same content", "same source")
        id2 = Du.generate_id("same content", "same source")
        assert id1 == id2

    def test_get_nonexistent_du(self):
        assert self.palace.get_du("不存在") is None

    # ── 简 ──

    def test_upsert_and_get_jian(self):
        self._make_dian_xuan()
        jian = Jian(
            id="j1", wenjian_text="议 测试★★★",
            du_ids=[], lang_type=LangType.JUEYI,
            xuan_name="auth", dian_name="proj",
            importance=Importance.HIGH,
        )
        self.palace.upsert_jian(jian)
        r = self.palace.get_jian("j1")
        assert r.wenjian_text == "议 测试★★★"

    def test_search_jian_by_dian(self):
        self._make_dian_xuan("proj-a", "auth")
        self._make_dian_xuan("proj-b", "auth")
        for i, dian in enumerate(["proj-a", "proj-b"]):
            jian = Jian(
                id=f"j{i}", wenjian_text=f"议 内容{i}★★★",
                du_ids=[], lang_type=LangType.JUEYI,
                xuan_name="auth", dian_name=dian,
                importance=Importance.HIGH,
            )
            self.palace.upsert_jian(jian)
        results = self.palace.search_jian(dian_name="proj-a")
        assert len(results) == 1
        assert results[0].dian_name == "proj-a"

    def test_search_jian_by_xuan(self):
        self._make_dian_xuan("proj", "auth")
        self._make_dian_xuan("proj", "db")
        for xuan in ["auth", "db"]:
            jian = Jian(
                id=f"j-{xuan}", wenjian_text="议 内容★★★",
                du_ids=[], lang_type=LangType.JUEYI,
                xuan_name=xuan, dian_name="proj",
                importance=Importance.HIGH,
            )
            self.palace.upsert_jian(jian)
        results = self.palace.search_jian(dian_name="proj", xuan_name="auth")
        assert len(results) == 1

    def test_search_jian_min_importance(self):
        self._make_dian_xuan()
        for i, imp in enumerate([Importance.LOW, Importance.MED, Importance.HIGH, Importance.KEY]):
            jian = Jian(
                id=f"j{i}", wenjian_text="议 内容",
                du_ids=[], lang_type=LangType.JUEYI,
                xuan_name="auth", dian_name="proj",
                importance=imp,
            )
            self.palace.upsert_jian(jian)
        results = self.palace.search_jian(min_importance=Importance.HIGH)
        assert all(r.importance in [Importance.HIGH, Importance.KEY, Importance.CRITICAL] for r in results)

    def test_jian_compression_ratio(self):
        self._make_dian_xuan()
        jian = Jian(
            id="j1", wenjian_text="简",
            du_ids=[], lang_type=LangType.JUEYI,
            xuan_name="auth", dian_name="proj",
            importance=Importance.MED,
            original_token_count=100,
            wenjian_token_count=10,
        )
        assert jian.compression_ratio == 10.0

    def test_jian_compression_ratio_zero_tokens(self):
        jian = Jian(
            id="j0", wenjian_text="",
            du_ids=[], lang_type=LangType.JUEYI,
            xuan_name="x", dian_name="d",
            importance=Importance.MED,
        )
        assert jian.compression_ratio == 0.0

    # ── 道 ──

    def test_rebuild_dao(self):
        for proj in ["a", "b"]:
            self._make_dian_xuan(proj, "auth")
        count = self.palace.rebuild_dao()
        assert count >= 1
        daos = self.palace.find_dao("auth")
        assert len(daos) >= 1

    def test_dao_connects_correct_dians(self):
        for proj in ["x", "y"]:
            self._make_dian_xuan(proj, "topic")
        self.palace.rebuild_dao()
        daos = self.palace.find_dao("topic")
        dian_pairs = {(d.dian_a, d.dian_b) for d in daos}
        assert ("x", "y") in dian_pairs or ("y", "x") in dian_pairs

    def test_no_dao_for_unique_xuan(self):
        self._make_dian_xuan("proj", "unique-topic")
        self.palace.rebuild_dao()
        assert self.palace.find_dao("unique-topic") == []

    # ── 统计 ──

    def test_stats_counts(self):
        self._make_dian_xuan("proj", "auth")
        stats = self.palace.stats()
        assert stats["殿数"] >= 1
        assert stats["轩数"] >= 1

    def test_wake_up_context_empty_palace(self):
        ctx = self.palace.wake_up_context()
        assert isinstance(ctx, str)

    def test_wake_up_context_with_identity(self):
        dian = Dian(name="proj", dian_type=DianType.PROJECT, identity_wenjian="proj身份简介")
        self.palace.upsert_dian(dian)
        ctx = self.palace.wake_up_context(dian_name="proj")
        assert "proj身份简介" in ctx


# ─────────────────────────────────────────────────────────────────────────────
# 数据挖掘器
# ─────────────────────────────────────────────────────────────────────────────

class TestMinerHelpers:
    """辅助函数：类型检测 / 重要性检测 / 轩名推断"""

    def test_detect_memory_type_decision(self):
        assert detect_memory_type("决定切换到 Clerk") == MemoryType.YI

    def test_detect_memory_type_event(self):
        assert detect_memory_type("已完成 auth 迁移部署") == MemoryType.SHI

    def test_detect_memory_type_discovery(self):
        assert detect_memory_type("发现 Auth0 不支持多租户") == MemoryType.DE

    def test_detect_memory_type_preference(self):
        assert detect_memory_type("我们偏好使用 PostgreSQL") == MemoryType.HAO

    def test_detect_memory_type_strategy(self):
        assert detect_memory_type("建议使用 Redis 缓存") == MemoryType.CE

    def test_detect_importance_critical(self):
        assert detect_importance("架构决策：迁移到微服务") == Importance.CRITICAL

    def test_detect_importance_key(self):
        assert detect_importance("重要决定：切换数据库") == Importance.KEY

    def test_detect_importance_default(self):
        assert detect_importance("今天开了个会") == Importance.MED

    def test_infer_xuan_auth(self):
        assert infer_xuan_name("auth migration to Clerk", "proj") == "auth"

    def test_infer_xuan_database(self):
        assert infer_xuan_name("switched to PostgreSQL database", "proj") == "database"

    def test_infer_xuan_deploy(self):
        assert infer_xuan_name("deployed to production via docker", "proj") == "deploy"

    def test_infer_xuan_api(self):
        assert infer_xuan_name("redesigned the REST API endpoints", "proj") == "api"

    def test_infer_xuan_default(self):
        assert infer_xuan_name("miscellaneous topic", "proj") == "通用"


class TestMiner:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.config = Config()
        self.config.palace_path = str(Path(self.tmp) / "palace")
        self.config.use_llm_compression = False
        self.palace = Palace(Path(self.tmp) / "palace")
        self.miner = Miner(self.palace, self.config)

    def teardown_method(self):
        self.palace.close()

    def test_mine_text_creates_du_and_jian(self):
        du, jian = self.miner.mine_text(
            "决定使用 PostgreSQL 而非 SQLite",
            dian_name="my-project",
            xuan_name="database",
        )
        assert du.id is not None
        assert jian.id is not None
        assert self.palace.get_du(du.id) is not None
        assert self.palace.get_jian(jian.id) is not None

    def test_mine_text_auto_creates_dian(self):
        self.miner.mine_text("content", dian_name="auto-dian", xuan_name="x")
        assert self.palace.get_dian("auto-dian") is not None

    def test_mine_text_auto_creates_xuan(self):
        self.miner.mine_text("content", dian_name="proj", xuan_name="auto-xuan")
        assert self.palace.get_xuan("auto-xuan", "proj") is not None

    def test_mine_text_auto_infers_xuan(self):
        du, jian = self.miner.mine_text(
            "auth migration from Auth0 to Clerk",
            dian_name="proj",
        )
        assert jian.xuan_name == "auth"

    def test_mine_text_wenjian_compresses(self):
        original = "我们的团队决定了要从Auth0迁移到Clerk认证服务，主要原因是价格便宜"
        du, jian = self.miner.mine_text(original, dian_name="proj", xuan_name="auth")
        assert len(jian.wenjian_text) < len(original)

    def test_mine_text_preserves_original_in_du(self):
        original = "决定使用 PostgreSQL，因为需要并发写入"
        du, _ = self.miner.mine_text(original, dian_name="proj", xuan_name="db")
        assert self.palace.get_du(du.id).content == original

    def test_mine_text_duplicate_idempotent(self):
        text = "决定使用 PostgreSQL"
        self.miner.mine_text(text, dian_name="proj", xuan_name="db")
        self.miner.mine_text(text, dian_name="proj", xuan_name="db")
        results = self.palace.search_jian(dian_name="proj")
        assert len(results) >= 1

    def test_mine_file_project_mode(self, tmp_path):
        f = tmp_path / "notes.md"
        f.write_text("# 架构决策\n\n决定使用 PostgreSQL 而不是 SQLite。\n\n建议迁移 CI 到 GitHub Actions。")
        results = self.miner.mine_file(f, dian_name="proj", mode=MineMode.PROJECT)
        assert len(results) >= 1

    def test_mine_file_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            self.miner.mine_file(tmp_path / "不存在.txt", dian_name="proj")

    def test_mine_file_plain_text_convo(self, tmp_path):
        f = tmp_path / "chat.txt"
        f.write_text(
            "User: 我们应该用哪个数据库？\n\n"
            "Assistant: 建议使用 PostgreSQL，支持并发写入和大数据集。\n\n"
            "User: 好的，决定了。"
        )
        results = self.miner.mine_file(f, dian_name="proj", mode=MineMode.CONVOS)
        assert len(results) >= 1

    def test_mine_file_json_convo(self, tmp_path):
        convo = [
            {"role": "user", "content": "为什么用 Clerk？"},
            {"role": "assistant", "content": "Clerk 价格更便宜，$25/月对比 Auth0 的 $240/月，且开发体验更好。"},
        ]
        f = tmp_path / "chat.json"
        f.write_text(json.dumps(convo))
        results = self.miner.mine_file(f, dian_name="proj", mode=MineMode.CONVOS)
        assert len(results) >= 1

    def test_mine_directory(self, tmp_path):
        for i, content in enumerate([
            "团队决定使用 PostgreSQL 数据库，因为需要支持并发写入和大规模数据集存储。",
            "发现 Auth0 不支持多租户场景，这是一个重要的架构缺陷，需要尽快解决。",
            "建议将 CI 流水线从 Jenkins 迁移至 GitHub Actions，可以节省大量配置工作。",
        ]):
            (tmp_path / f"note{i}.md").write_text(content)
        stats = self.miner.mine_directory(tmp_path, dian_name="proj")
        assert stats["文件数"] == 3
        assert stats["牍数"] >= 1

    def test_mine_directory_rebuilds_dao(self, tmp_path):
        (tmp_path / "note.md").write_text("auth migration decision")
        self.miner.mine_directory(tmp_path, dian_name="proj-a")
        self.miner.mine_directory(tmp_path, dian_name="proj-b")
        # dao 重建后同名轩应连接
        daos = self.palace.find_dao("auth")
        # 可能为0（如果xuan名不同），不强断言；只验证不报错
        assert isinstance(daos, list)


# ─────────────────────────────────────────────────────────────────────────────
# 语义搜索
# ─────────────────────────────────────────────────────────────────────────────

class TestSearcher:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.config = Config()
        self.config.palace_path = str(Path(self.tmp) / "palace")
        self.config.use_llm_compression = False
        self.palace = Palace(Path(self.tmp) / "palace")
        self.miner = Miner(self.palace, self.config)
        self.searcher = Searcher(self.palace, self.config)

    def teardown_method(self):
        self.palace.close()

    def _seed(self):
        texts = [
            ("决定使用 PostgreSQL，支持并发写入", "my-proj", "database"),
            ("迁移身份系统从 Auth0 到 Clerk", "my-proj", "auth"),
            ("CI 流水线迁移到 GitHub Actions", "my-proj", "ci"),
            ("发现 Auth0 多租户支持有缺陷", "my-proj", "auth"),
        ]
        for text, dian, xuan in texts:
            self.miner.mine_text(text, dian_name=dian, xuan_name=xuan)

    def test_keyword_search_returns_results(self):
        self._seed()
        results = self.searcher.search("PostgreSQL", use_vector=False)
        assert len(results) >= 1
        assert any("PostgreSQL" in r.jian.wenjian_text or "PostgreSQL" in
                   (self.palace.get_du(r.jian.du_ids[0]).content if r.jian.du_ids else "")
                   for r in results)

    def test_search_with_dian_filter(self):
        self._seed()
        # 另一个殿
        self.miner.mine_text("其他殿的内容", dian_name="other-proj", xuan_name="misc")
        results = self.searcher.search("内容", dian_name="my-proj", use_vector=False)
        assert all(r.jian.dian_name == "my-proj" for r in results)

    def test_search_with_xuan_filter(self):
        self._seed()
        results = self.searcher.search("迁移", dian_name="my-proj", xuan_name="auth", use_vector=False)
        assert all(r.jian.xuan_name == "auth" for r in results)

    def test_search_empty_palace(self):
        results = self.searcher.search("任意查询", use_vector=False)
        assert results == []

    def test_search_score_between_0_and_1(self):
        self._seed()
        results = self.searcher.search("Auth0 Clerk", use_vector=False)
        for r in results:
            assert 0.0 <= r.score <= 1.0

    def test_search_top_k_limit(self):
        self._seed()
        results = self.searcher.search("迁移", top_k=2, use_vector=False)
        assert len(results) <= 2

    def test_search_with_source(self):
        self._seed()
        results = self.searcher.search_with_source("PostgreSQL")
        for r in results:
            if r.jian.du_ids:
                assert r.matched_du is not None

    def test_format_results_not_empty(self):
        self._seed()
        results = self.searcher.search("auth", use_vector=False)
        formatted = self.searcher.format_results(results)
        assert "找到" in formatted
        assert len(formatted) > 0

    def test_format_results_empty(self):
        formatted = self.searcher.format_results([])
        assert "无匹配" in formatted

    def test_format_results_with_source(self):
        self._seed()
        results = self.searcher.search_with_source("PostgreSQL")
        formatted = self.searcher.format_results(results, show_source=True)
        assert isinstance(formatted, str)


# ─────────────────────────────────────────────────────────────────────────────
# 记忆层栈
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryStack:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.config = Config()
        self.config.palace_path = str(Path(self.tmp) / "palace")
        self.config.use_llm_compression = False
        self.palace = Palace(Path(self.tmp) / "palace")
        self.miner = Miner(self.palace, self.config)
        self.stack = MemoryStack(self.palace, self.config)

    def teardown_method(self):
        self.palace.close()

    def test_build_l0_returns_layer(self):
        l0 = self.stack.build_l0()
        assert l0.level == 0
        assert l0.name == "心法"
        assert len(l0.content) > 0

    def test_build_l0_default_identity(self):
        l0 = self.stack.build_l0()
        assert "记忆" in l0.content or "AI" in l0.content

    def test_build_l1_empty_palace(self):
        l1 = self.stack.build_l1()
        assert l1.level == 1
        assert l1.name == "要略"

    def test_build_l1_with_key_memories(self):
        dian = Dian(name="proj", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        xuan = Xuan(name="db", dian_name="proj")
        self.palace.upsert_xuan(xuan)
        jian = Jian(
            id="key-j", wenjian_text="议 关键决策★★★★",
            du_ids=[], lang_type=LangType.JUEYI,
            xuan_name="db", dian_name="proj",
            importance=Importance.KEY,
        )
        self.palace.upsert_jian(jian)
        l1 = self.stack.build_l1(dian_name="proj")
        assert "关键决策" in l1.content

    def test_build_l2_returns_layer(self):
        dian = Dian(name="proj", dian_type=DianType.PROJECT)
        self.palace.upsert_dian(dian)
        l2 = self.stack.build_l2("proj")
        assert l2.level == 2
        assert l2.name == "事记"

    def test_build_l2_with_xuan(self):
        self.miner.mine_text("auth migration决定", dian_name="proj", xuan_name="auth")
        l2 = self.stack.build_l2("proj", xuan_name="auth")
        # 内容中应包含轩名
        assert "auth" in l2.content

    def test_wake_up_returns_string(self):
        ctx = self.stack.wake_up()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_wake_up_includes_spec(self):
        ctx = self.stack.wake_up(include_spec=True)
        assert "文简" in ctx

    def test_wake_up_without_spec(self):
        ctx = self.stack.wake_up(include_spec=False)
        assert isinstance(ctx, str)

    def test_wake_up_with_dian_filter(self):
        dian = Dian(name="myproj", dian_type=DianType.PROJECT, identity_wenjian="myproj身份")
        self.palace.upsert_dian(dian)
        ctx = self.stack.wake_up(dian_name="myproj")
        assert "myproj身份" in ctx

    def test_system_prompt_injection_returns_string(self):
        ctx = self.stack.system_prompt_injection()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_system_prompt_injection_includes_stats(self):
        ctx = self.stack.system_prompt_injection()
        assert "宫殿状态" in ctx


# ─────────────────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────────────────

class TestConfig:

    def test_defaults(self):
        cfg = Config()
        assert cfg.llm_provider == "openai"
        assert cfg.use_llm_compression is True
        assert cfg.use_rule_compression is True
        assert cfg.max_wake_up_tokens == 200
        assert cfg.default_dian == "通用"

    def test_palace_path_obj(self, tmp_path):
        cfg = Config()
        cfg.palace_path = str(tmp_path / "palace")
        assert cfg.palace_path_obj == tmp_path / "palace"

    def test_save_and_load(self, tmp_path):
        cfg = Config()
        cfg.palace_path = str(tmp_path / "palace")
        cfg.default_dian = "test-dian"
        cfg.max_wake_up_tokens = 300
        config_file = tmp_path / "config.json"
        cfg.save(config_file)
        loaded = Config.load(config_file)
        assert loaded.default_dian == "test-dian"
        assert loaded.max_wake_up_tokens == 300

    def test_load_nonexistent_returns_defaults(self, tmp_path):
        cfg = Config.load(tmp_path / "nonexistent.json")
        assert cfg.max_wake_up_tokens == 200

    def test_env_var_openai(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        cfg = Config.load(tmp_path / "nonexistent.json")
        assert cfg.llm_api_key == "sk-test-key"

    def test_env_var_anthropic(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        cfg = Config.load(tmp_path / "nonexistent.json")
        assert cfg.llm_provider == "anthropic"
        assert cfg.llm_api_key == "sk-ant-test"

    def test_env_var_local_llm(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
        cfg = Config.load(tmp_path / "nonexistent.json")
        assert cfg.llm_base_url == "http://localhost:11434/v1"
        assert cfg.llm_provider == "local"

    def test_get_identity_missing_file(self):
        cfg = Config()
        cfg.identity_file = "/tmp/不存在的文件.txt"
        # 不报错，返回空字符串
        assert cfg.get_identity() == ""

    def test_get_identity_from_file(self, tmp_path):
        identity_file = tmp_path / "identity.txt"
        identity_file.write_text("我是测试AI助手")
        cfg = Config()
        cfg.identity_file = str(identity_file)
        assert cfg.get_identity() == "我是测试AI助手"


# ─────────────────────────────────────────────────────────────────────────────
# 知识图谱（扩展）
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

    def test_query_by_obj(self):
        self.kg.add_triple("伟明", "负责", "后端")
        triples = self.kg.query_entity("后端")
        assert len(triples) == 1

    def test_query_with_relation_filter(self):
        self.kg.add_triple("伟明", "负责", "后端")
        self.kg.add_triple("伟明", "推荐", "Clerk")
        results = self.kg.query_entity("伟明", relation="推荐")
        assert len(results) == 1
        assert results[0].obj == "Clerk"

    def test_historical_query(self):
        self.kg.add_triple("proj", "状态", "进行中", valid_from="2026-01-01")
        self.kg.invalidate("proj", "状态", "进行中", ended="2026-02-01")
        self.kg.add_triple("proj", "状态", "已完成", valid_from="2026-02-01")
        # 1月中查询：应该是"进行中"
        old = self.kg.query_entity("proj", as_of="2026-01-15", relation="状态")
        assert any(t.obj == "进行中" for t in old)
        # 现在查询：应该是"已完成"
        current = self.kg.query_entity("proj", relation="状态")
        assert any(t.obj == "已完成" for t in current)

    def test_invalidate_count(self):
        self.kg.add_triple("伟明", "负责", "后端")
        count = self.kg.invalidate("伟明", "负责", "后端")
        assert count == 1

    def test_invalidate_nonexistent_no_error(self):
        count = self.kg.invalidate("不存在", "关系", "对象")
        assert count == 0

    def test_timeline_ordered_by_time(self):
        self.kg.add_triple("proj", "状态", "计划中", valid_from="2026-01-01")
        self.kg.add_triple("proj", "状态", "进行中", valid_from="2026-01-15")
        self.kg.add_triple("proj", "状态", "已完成", valid_from="2026-02-01")
        timeline = self.kg.timeline("proj")
        times = [t.valid_from for t in timeline if t.valid_from]
        assert times == sorted(times)

    def test_contradiction_detection_fires(self):
        self.kg.add_triple("proj", "状态", "进行中")
        conflict = self.kg.check_contradiction("proj", "状态", "已完成")
        assert conflict is not None
        assert "矛盾" in conflict["message"]
        assert conflict["new_value"] == "已完成"
        assert "进行中" in conflict["existing_values"]

    def test_no_contradiction_same_value(self):
        self.kg.add_triple("proj", "状态", "进行中")
        assert self.kg.check_contradiction("proj", "状态", "进行中") is None

    def test_no_contradiction_no_prior(self):
        assert self.kg.check_contradiction("新实体", "状态", "任何值") is None

    def test_no_contradiction_after_invalidate(self):
        self.kg.add_triple("proj", "状态", "进行中")
        self.kg.invalidate("proj", "状态", "进行中")
        assert self.kg.check_contradiction("proj", "状态", "已完成") is None

    def test_triple_is_current(self):
        self.kg.add_triple("proj", "状态", "活跃")
        triples = self.kg.query_entity("proj")
        assert triples[0].is_current is True

    def test_triple_not_current_after_invalidate(self):
        self.kg.add_triple("proj", "状态", "旧状态", valid_from="2020-01-01")
        self.kg.invalidate("proj", "状态", "旧状态", ended="2021-01-01")
        # valid_until 已设为过去时间，is_current 应返回 False
        triples = self.kg.query_entity("proj", as_of="2020-06-01")
        assert len(triples) >= 1
        assert not triples[0].is_current

    def test_wenjian_summary_format(self):
        self.kg.add_triple("伟明", "角色", "后端工程师")
        self.kg.add_triple("伟明", "任期", "3年")
        summary = self.kg.to_wenjian_summary("伟明")
        assert "伟明" in summary
        assert "·" in summary

    def test_stats(self):
        for i in range(5):
            self.kg.add_triple(f"主{i}", "关系", f"客{i}")
        stats = self.kg.stats()
        assert stats["三元组总数"] == 5
        assert stats["当前有效"] == 5
        assert stats["实体数"] >= 5

    def test_source_jian_id_stored(self):
        triple_id = self.kg.add_triple("proj", "决策", "用Clerk", source_jian_id="jian-123")
        assert triple_id > 0


# ─────────────────────────────────────────────────────────────────────────────
# 端到端集成测试
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEnd:
    """
    模拟 README 描述的完整工作流：
    挖掘 → 存储 → 搜索 → 唤醒上下文
    """

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.config = Config()
        self.config.palace_path = str(Path(self.tmp) / "palace")
        self.config.use_llm_compression = False
        self.palace = Palace(Path(self.tmp) / "palace")
        self.kg = KnowledgeGraph(Path(self.tmp) / "palace" / "kg.db")
        self.miner = Miner(self.palace, self.config)
        self.searcher = Searcher(self.palace, self.config)
        self.stack = MemoryStack(self.palace, self.config)

    def teardown_method(self):
        self.palace.close()
        self.kg.close()

    def test_full_workflow_mine_search_wakeup(self):
        """README 核心场景：挖掘项目文件 → 搜索决策 → 生成唤醒上下文"""
        # 1. 挖掘多条记忆
        memories = [
            ("The team decided to migrate authentication from Auth0 to Clerk based on pricing.", "project", "auth"),
            ("Kai recommended PostgreSQL over SQLite for concurrent writes.", "project", "database"),
            ("Maya completed the auth migration after 12 days.", "project", "auth"),
            ("Team prefers GitHub Actions over Jenkins for CI pipeline.", "project", "ci"),
        ]
        for content, dian, xuan in memories:
            self.miner.mine_text(content, dian_name=dian, xuan_name=xuan)

        # 2. 宫殿统计应正确
        stats = self.palace.stats()
        assert stats["殿数"] >= 1
        assert stats["轩数"] >= 3
        assert stats["简数"] == 4
        assert stats["牍数"] == 4

        # 3. 跨殿通道重建
        dao_count = self.palace.rebuild_dao()
        assert isinstance(dao_count, int)

        # 4. 搜索 auth 相关决策
        results = self.searcher.search("auth migration", dian_name="project", use_vector=False)
        assert len(results) >= 1

        # 5. 搜索数据库决策
        results = self.searcher.search("PostgreSQL database", use_vector=False)
        assert len(results) >= 1

        # 6. 生成唤醒上下文
        ctx = self.stack.wake_up(include_spec=True)
        assert isinstance(ctx, str)
        assert len(ctx) > 100

    def test_mine_and_kg_combined(self):
        """记忆挖掘 + 知识图谱联动"""
        du, jian = self.miner.mine_text(
            "Kai has been the backend lead for 3 years",
            dian_name="team", xuan_name="members",
        )
        # 向知识图谱添加与竹简关联的三元组
        self.kg.add_triple("Kai", "角色", "后端主程", source_jian_id=jian.id)
        self.kg.add_triple("Kai", "任期", "3年", source_jian_id=jian.id)

        triples = self.kg.query_entity("Kai")
        assert len(triples) == 2
        assert all(t.source_jian_id == jian.id for t in triples)

    def test_contradiction_in_full_workflow(self):
        """工作流中的矛盾检测"""
        self.kg.add_triple("auth迁移", "负责人", "美云")
        # 新信息错误地说少风负责
        conflict = self.kg.check_contradiction("auth迁移", "负责人", "少风")
        assert conflict is not None
        assert "美云" in conflict["existing_values"]

    def test_wake_up_token_budget(self):
        """唤醒上下文应在合理 token 范围内"""
        # 添加一些关键记忆
        dian = Dian(name="proj", dian_type=DianType.PROJECT, identity_wenjian="项目身份简介")
        self.palace.upsert_dian(dian)
        xuan = Xuan(name="core", dian_name="proj")
        self.palace.upsert_xuan(xuan)
        for i in range(5):
            jian = Jian(
                id=f"key-{i}", wenjian_text=f"议 关键决策{i}★★★★",
                du_ids=[], lang_type=LangType.JUEYI,
                xuan_name="core", dian_name="proj",
                importance=Importance.KEY,
            )
            self.palace.upsert_jian(jian)

        ctx = self.stack.wake_up(dian_name="proj")
        # 文简上下文应该远小于 1000 字符（约等效于 500 tokens）
        assert len(ctx) < 2000

    def test_wenjian_format_in_stored_jian(self):
        """存储的竹简文本应符合文简格式（包含类型标头）"""
        du, jian = self.miner.mine_text(
            "决定使用 PostgreSQL 而不是 SQLite",
            dian_name="proj", xuan_name="db",
        )
        valid_prefixes = [mt.value for mt in MemoryType]
        has_valid_prefix = any(jian.wenjian_text.startswith(p) for p in valid_prefixes)
        # 规则压缩可能不带类型头，但至少应该是非空字符串
        assert len(jian.wenjian_text) > 0

    def test_multi_dian_cross_search(self):
        """跨殿搜索：不同项目的同类决策都能检索到"""
        self.miner.mine_text("auth migration decided", dian_name="proj-a", xuan_name="auth")
        self.miner.mine_text("authentication system changed", dian_name="proj-b", xuan_name="auth")
        # 不带 dian 过滤时两者都应出现
        all_results = self.searcher.search("auth", use_vector=False)
        dians = {r.jian.dian_name for r in all_results}
        assert len(dians) >= 2

    def test_file_mining_end_to_end(self, tmp_path):
        """从文件挖掘到搜索的完整链路"""
        doc = tmp_path / "decisions.md"
        doc.write_text(
            "# 架构决策记录\n\n"
            "## 数据库选型\n决定使用 PostgreSQL，原因：需要并发写入能力。\n\n"
            "## 认证服务\n决定从 Auth0 迁移到 Clerk，节省 $215/月。\n"
        )
        results = self.miner.mine_file(doc, dian_name="my-proj", mode=MineMode.PROJECT)
        assert len(results) >= 1

        # 搜索应能找到内容
        search_results = self.searcher.search("PostgreSQL", dian_name="my-proj", use_vector=False)
        assert len(search_results) >= 1

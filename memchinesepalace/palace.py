"""
宫殿数据结构

借鉴记忆宫殿（Method of Loci）原理，以中国古代宫殿建筑为隐喻：

  宫 (Palace)  — 整个记忆系统
  殿 (Dian)    — 一个人/项目/主题的顶层空间（等同于 MemPalace 的 Wing）
  轩 (Xuan)    — 殿内的具体话题室（等同于 Room）
  简 (Jian)    — 竹简：压缩后的文简摘要（等同于 Closet）
  牍 (Du)      — 木牍：原始完整内容（等同于 Drawer）

廊 (Lang) — 连接同一殿内不同轩的走廊（等同于 Hall）
道 (Dao)  — 跨殿连接的通道（等同于 Tunnel）
"""

from __future__ import annotations

import json
import sqlite3
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Iterator

from .compressor import MemoryType, Importance, Status, WenjianEntry


# ─────────────────────────────────────────────────────────────────────────────
# 廊类型 (Lang / Hall Types)
# ─────────────────────────────────────────────────────────────────────────────

class LangType(Enum):
    """廊类型：记忆的功能分类"""
    JUEYI = "廊·议"   # 决策/事实
    SHIJIAN = "廊·事"  # 事件/里程碑
    FAXIAN = "廊·得"   # 发现/洞见
    PIANAO = "廊·好"   # 偏好/习惯
    CELÜE = "廊·策"    # 建议/策略

    @classmethod
    def from_memory_type(cls, mt: MemoryType) -> "LangType":
        mapping = {
            MemoryType.YI: cls.JUEYI,
            MemoryType.SHI: cls.SHIJIAN,
            MemoryType.DE: cls.FAXIAN,
            MemoryType.HAO: cls.PIANAO,
            MemoryType.CE: cls.CELÜE,
        }
        return mapping[mt]


# ─────────────────────────────────────────────────────────────────────────────
# 牍 (Du) — 原始记录
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Du:
    """木牍：原始逐字记录，永不压缩"""
    id: str
    content: str                      # 原始完整内容
    source: str                       # 来源（文件路径、对话ID等）
    lang_type: LangType
    xuan_name: str                    # 所属轩名
    dian_name: str                    # 所属殿名
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    @classmethod
    def generate_id(cls, content: str, source: str) -> str:
        return hashlib.sha256(f"{source}:{content[:100]}".encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# 简 (Jian) — 文简压缩摘要
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Jian:
    """竹简：文简压缩的摘要，AI快读层"""
    id: str
    wenjian_text: str                 # 文简格式的压缩文本
    du_ids: list[str]                 # 对应的牍ID列表
    lang_type: LangType
    xuan_name: str
    dian_name: str
    importance: Importance = Importance.MED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    original_token_count: int = 0
    wenjian_token_count: int = 0

    @property
    def compression_ratio(self) -> float:
        if self.wenjian_token_count == 0:
            return 0.0
        return self.original_token_count / self.wenjian_token_count

    def to_display(self) -> str:
        return (
            f"[{self.dian_name}/{self.xuan_name}/{self.lang_type.value}]\n"
            f"{self.wenjian_text}\n"
            f"（压缩比 {self.compression_ratio:.1f}x，来自 {len(self.du_ids)} 条记录）"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 轩 (Xuan) — 话题室
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Xuan:
    """轩：殿内的具体话题空间"""
    name: str                         # 轩名，如 "auth-migration"、"数据库选型"
    dian_name: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    jian_ids: list[str] = field(default_factory=list)
    du_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def path(self) -> str:
        return f"{self.dian_name}/{self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# 殿 (Dian) — 顶层空间
# ─────────────────────────────────────────────────────────────────────────────

class DianType(Enum):
    PERSON = "人"      # 一个人
    PROJECT = "项"     # 一个项目
    TOPIC = "题"       # 一个话题/领域
    GENERAL = "通"     # 通用


@dataclass
class Dian:
    """殿：一个人/项目/主题的顶层记忆空间"""
    name: str                         # 殿名，如 "wing_kai"、"wing_driftwood"
    dian_type: DianType
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    xuan_names: list[str] = field(default_factory=list)
    identity_wenjian: str = ""        # 该殿的文简身份摘要（L0层）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_xuan(self, xuan_name: str) -> None:
        if xuan_name not in self.xuan_names:
            self.xuan_names.append(xuan_name)


# ─────────────────────────────────────────────────────────────────────────────
# 道 (Dao) — 跨殿通道
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Dao:
    """道：连接不同殿中同名轩的跨殿通道"""
    xuan_name: str                    # 触发连接的轩名（必须两侧相同）
    dian_a: str
    dian_b: str
    strength: float = 1.0             # 关联强度

    @property
    def key(self) -> str:
        return f"{min(self.dian_a, self.dian_b)}↔{max(self.dian_a, self.dian_b)}:{self.xuan_name}"


# ─────────────────────────────────────────────────────────────────────────────
# 宫 (Palace) — 整个记忆宫殿
# ─────────────────────────────────────────────────────────────────────────────

class Palace:
    """
    记忆宫殿主体
    所有数据持久化于 SQLite，向量检索使用 ChromaDB（可选）
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS dian (
        name TEXT PRIMARY KEY,
        dian_type TEXT NOT NULL,
        description TEXT DEFAULT '',
        keywords TEXT DEFAULT '[]',
        xuan_names TEXT DEFAULT '[]',
        identity_wenjian TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS xuan (
        name TEXT NOT NULL,
        dian_name TEXT NOT NULL,
        description TEXT DEFAULT '',
        keywords TEXT DEFAULT '[]',
        jian_ids TEXT DEFAULT '[]',
        du_ids TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        PRIMARY KEY (name, dian_name)
    );

    CREATE TABLE IF NOT EXISTS jian (
        id TEXT PRIMARY KEY,
        wenjian_text TEXT NOT NULL,
        du_ids TEXT DEFAULT '[]',
        lang_type TEXT NOT NULL,
        xuan_name TEXT NOT NULL,
        dian_name TEXT NOT NULL,
        importance TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        original_token_count INTEGER DEFAULT 0,
        wenjian_token_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS du (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        source TEXT NOT NULL,
        lang_type TEXT NOT NULL,
        xuan_name TEXT NOT NULL,
        dian_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS dao (
        xuan_name TEXT NOT NULL,
        dian_a TEXT NOT NULL,
        dian_b TEXT NOT NULL,
        strength REAL DEFAULT 1.0,
        PRIMARY KEY (xuan_name, dian_a, dian_b)
    );

    CREATE INDEX IF NOT EXISTS idx_jian_dian ON jian(dian_name);
    CREATE INDEX IF NOT EXISTS idx_jian_xuan ON jian(xuan_name);
    CREATE INDEX IF NOT EXISTS idx_du_dian ON du(dian_name);
    CREATE INDEX IF NOT EXISTS idx_du_xuan ON du(xuan_name);
    """

    def __init__(self, palace_path: Path | str):
        self.palace_path = Path(palace_path)
        self.palace_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.palace_path / "palace.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Dian CRUD ──────────────────────────────────────────────────────────

    def upsert_dian(self, dian: Dian) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO dian VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
               dian_type=excluded.dian_type,
               description=excluded.description,
               keywords=excluded.keywords,
               xuan_names=excluded.xuan_names,
               identity_wenjian=excluded.identity_wenjian""",
            (
                dian.name, dian.dian_type.value, dian.description,
                json.dumps(dian.keywords, ensure_ascii=False),
                json.dumps(dian.xuan_names, ensure_ascii=False),
                dian.identity_wenjian, dian.created_at,
            )
        )
        conn.commit()

    def get_dian(self, name: str) -> Optional[Dian]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM dian WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        return Dian(
            name=row["name"],
            dian_type=DianType(row["dian_type"]),
            description=row["description"],
            keywords=json.loads(row["keywords"]),
            xuan_names=json.loads(row["xuan_names"]),
            identity_wenjian=row["identity_wenjian"],
            created_at=row["created_at"],
        )

    def list_dian(self) -> list[Dian]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM dian ORDER BY created_at").fetchall()
        return [self.get_dian(r["name"]) for r in rows]

    # ── Xuan CRUD ──────────────────────────────────────────────────────────

    def upsert_xuan(self, xuan: Xuan) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO xuan VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(name, dian_name) DO UPDATE SET
               description=excluded.description,
               keywords=excluded.keywords,
               jian_ids=excluded.jian_ids,
               du_ids=excluded.du_ids""",
            (
                xuan.name, xuan.dian_name, xuan.description,
                json.dumps(xuan.keywords, ensure_ascii=False),
                json.dumps(xuan.jian_ids, ensure_ascii=False),
                json.dumps(xuan.du_ids, ensure_ascii=False),
                xuan.created_at,
            )
        )
        # 确保殿的xuan_names中包含该轩
        dian = self.get_dian(xuan.dian_name)
        if dian and xuan.name not in dian.xuan_names:
            dian.xuan_names.append(xuan.name)
            self.upsert_dian(dian)
        conn.commit()

    def get_xuan(self, name: str, dian_name: str) -> Optional[Xuan]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM xuan WHERE name=? AND dian_name=?", (name, dian_name)
        ).fetchone()
        if not row:
            return None
        return Xuan(
            name=row["name"],
            dian_name=row["dian_name"],
            description=row["description"],
            keywords=json.loads(row["keywords"]),
            jian_ids=json.loads(row["jian_ids"]),
            du_ids=json.loads(row["du_ids"]),
            created_at=row["created_at"],
        )

    def list_xuan(self, dian_name: str) -> list[Xuan]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT name FROM xuan WHERE dian_name=? ORDER BY name", (dian_name,)
        ).fetchall()
        return [self.get_xuan(r["name"], dian_name) for r in rows]

    # ── Du CRUD ────────────────────────────────────────────────────────────

    def add_du(self, du: Du) -> str:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO du VALUES (?,?,?,?,?,?,?,?)",
            (
                du.id, du.content, du.source, du.lang_type.value,
                du.xuan_name, du.dian_name, du.created_at,
                json.dumps(du.metadata, ensure_ascii=False),
            )
        )
        # 更新轩的du_ids
        xuan = self.get_xuan(du.xuan_name, du.dian_name)
        if xuan and du.id not in xuan.du_ids:
            xuan.du_ids.append(du.id)
            self.upsert_xuan(xuan)
        conn.commit()
        return du.id

    def get_du(self, du_id: str) -> Optional[Du]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM du WHERE id=?", (du_id,)).fetchone()
        if not row:
            return None
        return Du(
            id=row["id"],
            content=row["content"],
            source=row["source"],
            lang_type=LangType(row["lang_type"]),
            xuan_name=row["xuan_name"],
            dian_name=row["dian_name"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]),
        )

    # ── Jian CRUD ──────────────────────────────────────────────────────────

    def upsert_jian(self, jian: Jian) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO jian VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
               wenjian_text=excluded.wenjian_text,
               du_ids=excluded.du_ids,
               importance=excluded.importance,
               updated_at=excluded.updated_at,
               original_token_count=excluded.original_token_count,
               wenjian_token_count=excluded.wenjian_token_count""",
            (
                jian.id, jian.wenjian_text,
                json.dumps(jian.du_ids, ensure_ascii=False),
                jian.lang_type.value, jian.xuan_name, jian.dian_name,
                jian.importance.value, jian.created_at, jian.updated_at,
                jian.original_token_count, jian.wenjian_token_count,
            )
        )
        # 更新轩的jian_ids
        xuan = self.get_xuan(jian.xuan_name, jian.dian_name)
        if xuan and jian.id not in xuan.jian_ids:
            xuan.jian_ids.append(jian.id)
            self.upsert_xuan(xuan)
        conn.commit()

    def get_jian(self, jian_id: str) -> Optional[Jian]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM jian WHERE id=?", (jian_id,)).fetchone()
        if not row:
            return None
        return Jian(
            id=row["id"],
            wenjian_text=row["wenjian_text"],
            du_ids=json.loads(row["du_ids"]),
            lang_type=LangType(row["lang_type"]),
            xuan_name=row["xuan_name"],
            dian_name=row["dian_name"],
            importance=Importance(row["importance"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            original_token_count=row["original_token_count"],
            wenjian_token_count=row["wenjian_token_count"],
        )

    def search_jian(
        self,
        dian_name: Optional[str] = None,
        xuan_name: Optional[str] = None,
        lang_type: Optional[LangType] = None,
        min_importance: Optional[Importance] = None,
    ) -> list[Jian]:
        """按条件筛选竹简"""
        conn = self._get_conn()
        conditions = []
        params: list = []
        if dian_name:
            conditions.append("dian_name=?")
            params.append(dian_name)
        if xuan_name:
            conditions.append("xuan_name=?")
            params.append(xuan_name)
        if lang_type:
            conditions.append("lang_type=?")
            params.append(lang_type.value)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = conn.execute(
            f"SELECT id FROM jian {where} ORDER BY updated_at DESC",
            params
        ).fetchall()

        results = []
        importance_order = [i.value for i in Importance]
        for row in rows:
            jian = self.get_jian(row["id"])
            if jian:
                if min_importance and importance_order.index(jian.importance.value) < importance_order.index(min_importance.value):
                    continue
                results.append(jian)
        return results

    # ── Dao (跨殿通道) ─────────────────────────────────────────────────────

    def find_dao(self, xuan_name: str) -> list[Dao]:
        """查找所有经过指定轩名的跨殿通道"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM dao WHERE xuan_name=?", (xuan_name,)
        ).fetchall()
        return [
            Dao(
                xuan_name=r["xuan_name"],
                dian_a=r["dian_a"],
                dian_b=r["dian_b"],
                strength=r["strength"],
            )
            for r in rows
        ]

    def rebuild_dao(self) -> int:
        """重建所有跨殿通道（基于同名轩自动连接）"""
        conn = self._get_conn()
        conn.execute("DELETE FROM dao")

        # 找出所有跨殿的同名轩
        rows = conn.execute(
            """SELECT name as xuan_name, GROUP_CONCAT(dian_name) as dians
               FROM xuan GROUP BY name HAVING COUNT(*) > 1"""
        ).fetchall()

        count = 0
        for row in rows:
            dians = row["dians"].split(",")
            for i in range(len(dians)):
                for j in range(i + 1, len(dians)):
                    conn.execute(
                        "INSERT OR IGNORE INTO dao VALUES (?,?,?,?)",
                        (row["xuan_name"], dians[i], dians[j], 1.0)
                    )
                    count += 1
        conn.commit()
        return count

    # ── 统计 ────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        conn = self._get_conn()
        return {
            "殿数": conn.execute("SELECT COUNT(*) FROM dian").fetchone()[0],
            "轩数": conn.execute("SELECT COUNT(*) FROM xuan").fetchone()[0],
            "简数": conn.execute("SELECT COUNT(*) FROM jian").fetchone()[0],
            "牍数": conn.execute("SELECT COUNT(*) FROM du").fetchone()[0],
            "道数": conn.execute("SELECT COUNT(*) FROM dao").fetchone()[0],
            "总压缩比": self._avg_compression(),
        }

    def _avg_compression(self) -> str:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT AVG(CAST(original_token_count AS FLOAT)/NULLIF(wenjian_token_count,0)) FROM jian"
        ).fetchone()
        val = row[0]
        return f"{val:.1f}x" if val else "N/A"

    def wake_up_context(self, dian_name: Optional[str] = None, max_tokens: int = 200) -> str:
        """
        生成唤醒上下文（L0+L1层），注入到LLM系统提示
        类似 MemPalace 的 wake-up 命令
        """
        lines = ["【记忆宫殿·唤醒】\n"]

        dians = [self.get_dian(dian_name)] if dian_name else self.list_dian()
        dians = [d for d in dians if d]

        for dian in dians:
            if dian.identity_wenjian:
                lines.append(f"殿·{dian.name}：{dian.identity_wenjian}")

        # 找关键性最高的简
        key_jians = self.search_jian(
            dian_name=dian_name,
            min_importance=Importance.KEY
        )[:10]

        if key_jians:
            lines.append("\n【要事】")
            for jian in key_jians:
                lines.append(jian.wenjian_text)

        return "\n".join(lines)

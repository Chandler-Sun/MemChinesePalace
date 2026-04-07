"""
知识图谱 (Knowledge Graph)

时序实体关系三元组，基于 SQLite。
支持时间窗口查询：某个事实在某时间点是否成立。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Triple:
    """时序知识三元组：主体-关系-客体"""
    subject: str
    relation: str
    obj: str
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    confidence: float = 1.0
    source_jian_id: Optional[str] = None  # 来源竹简ID
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.valid_from is None:
            self.valid_from = datetime.now().isoformat()

    @property
    def is_current(self) -> bool:
        now = datetime.now().isoformat()
        if self.valid_from and self.valid_from > now:
            return False
        if self.valid_until and self.valid_until < now:
            return False
        return True

    def to_wenjian(self) -> str:
        """序列化为文简三元组格式"""
        time_str = ""
        if self.valid_from:
            time_str = f"（{self.valid_from[:10]}起）"
        if self.valid_until:
            time_str += f"（至{self.valid_until[:10]}）"
        return f"{self.subject}·{self.relation}·{self.obj}{time_str}"


class KnowledgeGraph:
    """
    时序知识图谱
    存储实体间的关系，支持时间窗口查询和矛盾检测
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS triple (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        relation TEXT NOT NULL,
        obj TEXT NOT NULL,
        valid_from TEXT,
        valid_until TEXT,
        confidence REAL DEFAULT 1.0,
        source_jian_id TEXT,
        metadata TEXT DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_subject ON triple(subject);
    CREATE INDEX IF NOT EXISTS idx_relation ON triple(relation);
    CREATE INDEX IF NOT EXISTS idx_obj ON triple(obj);
    CREATE INDEX IF NOT EXISTS idx_subj_rel ON triple(subject, relation);
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def add_triple(
        self,
        subject: str,
        relation: str,
        obj: str,
        valid_from: Optional[str] = None,
        confidence: float = 1.0,
        source_jian_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        triple = Triple(
            subject=subject,
            relation=relation,
            obj=obj,
            valid_from=valid_from,
            confidence=confidence,
            source_jian_id=source_jian_id,
            metadata=metadata or {},
        )
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO triple (subject, relation, obj, valid_from, confidence, source_jian_id, metadata) VALUES (?,?,?,?,?,?,?)",
            (
                triple.subject, triple.relation, triple.obj,
                triple.valid_from, triple.confidence,
                triple.source_jian_id,
                json.dumps(triple.metadata, ensure_ascii=False),
            )
        )
        conn.commit()
        return cursor.lastrowid

    def invalidate(
        self,
        subject: str,
        relation: str,
        obj: str,
        ended: Optional[str] = None,
    ) -> int:
        """标记某三元组失效（设置 valid_until）"""
        ended = ended or datetime.now().isoformat()
        conn = self._get_conn()
        result = conn.execute(
            """UPDATE triple SET valid_until=?
               WHERE subject=? AND relation=? AND obj=? AND (valid_until IS NULL OR valid_until > ?)""",
            (ended, subject, relation, obj, ended)
        )
        conn.commit()
        return result.rowcount

    def query_entity(
        self,
        entity: str,
        as_of: Optional[str] = None,
        relation: Optional[str] = None,
    ) -> list[Triple]:
        """查询实体的所有关系"""
        as_of = as_of or datetime.now().isoformat()
        conn = self._get_conn()

        conditions = [
            "(subject=? OR obj=?)",
            "(valid_from IS NULL OR valid_from <= ?)",
            "(valid_until IS NULL OR valid_until > ?)",
        ]
        params: list = [entity, entity, as_of, as_of]

        if relation:
            conditions.append("relation=?")
            params.append(relation)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM triple WHERE {where} ORDER BY valid_from DESC",
            params
        ).fetchall()

        return [self._row_to_triple(r) for r in rows]

    def timeline(self, entity: str) -> list[Triple]:
        """实体的时间线故事"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM triple WHERE subject=? OR obj=? ORDER BY valid_from ASC",
            (entity, entity)
        ).fetchall()
        return [self._row_to_triple(r) for r in rows]

    def check_contradiction(
        self,
        subject: str,
        relation: str,
        new_obj: str,
    ) -> Optional[dict]:
        """
        矛盾检测：检查新事实是否与现有事实冲突
        返回 None 表示无冲突，否则返回冲突信息
        """
        now = datetime.now().isoformat()
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM triple
               WHERE subject=? AND relation=?
               AND (valid_until IS NULL OR valid_until > ?)
               AND obj != ?""",
            (subject, relation, now, new_obj)
        ).fetchall()

        if rows:
            existing = [self._row_to_triple(r) for r in rows]
            return {
                "conflict": True,
                "subject": subject,
                "relation": relation,
                "new_value": new_obj,
                "existing_values": [t.obj for t in existing],
                "message": (
                    f"🔴 矛盾检测：{subject}·{relation} 当前值为 "
                    f"{[t.obj for t in existing]}，新值为 {new_obj}"
                )
            }
        return None

    def stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM triple").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM triple WHERE valid_until IS NULL OR valid_until > ?",
            (datetime.now().isoformat(),)
        ).fetchone()[0]
        entities = conn.execute(
            "SELECT COUNT(DISTINCT subject) FROM triple"
        ).fetchone()[0]
        return {
            "三元组总数": total,
            "当前有效": active,
            "实体数": entities,
        }

    def to_wenjian_summary(self, entity: str, max_triples: int = 10) -> str:
        """将实体的知识图谱序列化为文简格式"""
        triples = self.query_entity(entity)[:max_triples]
        if not triples:
            return f"（{entity}：无记录）"
        lines = [f"【{entity}·知识】"]
        for t in triples:
            lines.append(f"  {t.to_wenjian()}")
        return "\n".join(lines)

    def _row_to_triple(self, row: sqlite3.Row) -> Triple:
        return Triple(
            subject=row["subject"],
            relation=row["relation"],
            obj=row["obj"],
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            confidence=row["confidence"],
            source_jian_id=row["source_jian_id"],
            metadata=json.loads(row["metadata"]),
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

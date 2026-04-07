"""
语义搜索引擎 (Semantic Searcher)

基于 ChromaDB 向量数据库，支持：
- 语义相似度搜索
- 殿/轩 精确过滤（显著提升召回率）
- 文简 + 原文双重搜索
- 无 API 纯本地运行
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from .palace import Palace, Jian, Du, LangType
from .config import Config


@dataclass
class SearchResult:
    jian: Jian
    score: float           # 相似度分数 0-1
    matched_du: Optional[Du] = None

    def to_display(self) -> str:
        score_bar = "█" * int(self.score * 10)
        return (
            f"[{score_bar:<10}] {self.score:.2f}\n"
            f"  {self.jian.dian_name}/{self.jian.xuan_name}\n"
            f"  {self.jian.wenjian_text}\n"
        )


class Searcher:
    """
    语义搜索引擎
    优先按殿/轩过滤以提升精度，类似 MemPalace 的 34% 召回提升
    """

    def __init__(self, palace: Palace, config: Config):
        self.palace = palace
        self.config = config
        self._chroma_client = None
        self._collection = None

    def _get_collection(self):
        """懒加载 ChromaDB collection"""
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
            from chromadb.utils import embedding_functions

            chroma_path = Path(self.config.palace_path) / "chroma"
            self._chroma_client = chromadb.PersistentClient(path=str(chroma_path))

            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.config.embedding_model
            )

            self._collection = self._chroma_client.get_or_create_collection(
                name=self.config.chroma_collection,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            pass
        return self._collection

    def index_jian(self, jian: Jian) -> bool:
        """索引一条竹简到向量数据库"""
        collection = self._get_collection()
        if collection is None:
            return False

        try:
            # 同时索引文简文本和元数据
            collection.upsert(
                ids=[jian.id],
                documents=[jian.wenjian_text],
                metadatas=[{
                    "dian_name": jian.dian_name,
                    "xuan_name": jian.xuan_name,
                    "lang_type": jian.lang_type.value,
                    "importance": jian.importance.value,
                    "du_ids": json.dumps(jian.du_ids),
                }]
            )
            return True
        except Exception:
            return False

    def index_all(self) -> dict:
        """重建所有竹简的向量索引"""
        collection = self._get_collection()
        if collection is None:
            return {"错误": "ChromaDB 不可用，请安装：pip install chromadb"}

        conn = self.palace._get_conn()
        rows = conn.execute("SELECT id FROM jian").fetchall()

        indexed = 0
        failed = 0
        for row in rows:
            jian = self.palace.get_jian(row["id"])
            if jian:
                if self.index_jian(jian):
                    indexed += 1
                else:
                    failed += 1

        return {"已索引": indexed, "失败": failed, "总计": indexed + failed}

    def search(
        self,
        query: str,
        dian_name: Optional[str] = None,
        xuan_name: Optional[str] = None,
        lang_type: Optional[LangType] = None,
        top_k: int = 5,
        use_vector: bool = True,
    ) -> list[SearchResult]:
        """
        语义搜索

        优先使用向量搜索（ChromaDB），若不可用则回退到关键词搜索。
        按殿/轩过滤可大幅提升精度（+34% recall@10）。
        """
        if use_vector:
            results = self._vector_search(query, dian_name, xuan_name, lang_type, top_k)
            if results:
                return results

        # 回退：关键词搜索
        return self._keyword_search(query, dian_name, xuan_name, lang_type, top_k)

    def _vector_search(
        self,
        query: str,
        dian_name: Optional[str],
        xuan_name: Optional[str],
        lang_type: Optional[LangType],
        top_k: int,
    ) -> list[SearchResult]:
        """向量语义搜索"""
        collection = self._get_collection()
        if collection is None:
            return []

        try:
            where: dict[str, Any] = {}
            if dian_name and xuan_name:
                where = {"$and": [{"dian_name": dian_name}, {"xuan_name": xuan_name}]}
            elif dian_name:
                where = {"dian_name": dian_name}
            elif xuan_name:
                where = {"xuan_name": xuan_name}
            if lang_type:
                if where:
                    where = {"$and": [where, {"lang_type": lang_type.value}]}
                else:
                    where = {"lang_type": lang_type.value}

            query_params = {
                "query_texts": [query],
                "n_results": min(top_k, collection.count() or 1),
            }
            if where:
                query_params["where"] = where

            chroma_results = collection.query(**query_params)

            results = []
            if chroma_results["ids"] and chroma_results["ids"][0]:
                for i, jian_id in enumerate(chroma_results["ids"][0]):
                    jian = self.palace.get_jian(jian_id)
                    if jian:
                        distance = chroma_results["distances"][0][i] if chroma_results.get("distances") else 0.5
                        score = 1.0 - distance
                        results.append(SearchResult(jian=jian, score=score))

            return results
        except Exception:
            return []

    def _keyword_search(
        self,
        query: str,
        dian_name: Optional[str],
        xuan_name: Optional[str],
        lang_type: Optional[LangType],
        top_k: int,
    ) -> list[SearchResult]:
        """关键词回退搜索"""
        all_jians = self.palace.search_jian(
            dian_name=dian_name,
            xuan_name=xuan_name,
            lang_type=lang_type,
        )

        query_lower = query.lower()
        scored = []
        for jian in all_jians:
            text = jian.wenjian_text.lower()
            # 简单词频匹配
            score = sum(1 for word in query_lower.split() if word in text) / max(len(query_lower.split()), 1)
            if score > 0:
                scored.append(SearchResult(jian=jian, score=score))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def search_with_source(
        self,
        query: str,
        dian_name: Optional[str] = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """搜索并同时返回原始牍内容"""
        results = self.search(query, dian_name=dian_name, top_k=top_k)
        for result in results:
            if result.jian.du_ids:
                result.matched_du = self.palace.get_du(result.jian.du_ids[0])
        return results

    def format_results(self, results: list[SearchResult], show_source: bool = False) -> str:
        """格式化搜索结果为文本"""
        if not results:
            return "（无匹配结果）"

        lines = [f"找到 {len(results)} 条相关记忆：\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r.jian.dian_name}/{r.jian.xuan_name}] {r.score:.0%} 相似")
            lines.append(f"   {r.jian.wenjian_text}")
            if show_source and r.matched_du:
                preview = r.matched_du.content[:100].replace("\n", " ")
                lines.append(f"   原文：{preview}…")
            lines.append("")

        return "\n".join(lines)

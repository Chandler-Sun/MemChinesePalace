"""
数据挖掘器 (Miner)

从各类数据源中提取记忆，并调用文简压缩后存入宫殿。

支持：
- 项目文件（代码、文档、笔记）
- 对话记录（Claude、ChatGPT、Cursor、Slack导出）
- 通用文本
"""

from __future__ import annotations

import re
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterator
from enum import Enum

from .palace import Palace, Du, Jian, Xuan, Dian, DianType, LangType
from .compressor import WenjianCompressor, MemoryType, Importance
from .config import Config


class MineMode(Enum):
    PROJECT = "project"    # 代码/文档
    CONVOS = "convos"      # 对话记录
    GENERAL = "general"    # 通用文本（自动分类）


# 对话格式检测规则
CONVO_PATTERNS = {
    "claude": [r'"role":\s*"(user|assistant)"', r'"content":\s*"'],
    "chatgpt": [r'"role":\s*"(user|assistant|system)"', r'"message"'],
    "cursor": [r'"text":\s*"', r'"role":\s*"(user|assistant)"'],
    "plain": [r'^(User|Assistant|Human|AI):\s+', r'^---'],
}

# 记忆类型关键词分类
MEMORY_TYPE_KEYWORDS = {
    MemoryType.YI: [
        "决定", "决策", "选择", "采用", "放弃", "改用", "切换",
        "decided", "chose", "switched", "adopted", "deprecated",
        "议定", "定案",
    ],
    MemoryType.SHI: [
        "完成", "发布", "部署", "修复", "发现bug", "上线",
        "completed", "deployed", "released", "fixed", "launched",
        "里程碑",
    ],
    MemoryType.DE: [
        "发现", "意识到", "原来", "注意到", "洞察",
        "discovered", "realized", "found out", "noticed", "insight",
    ],
    MemoryType.HAO: [
        "偏好", "习惯", "喜欢", "不喜欢", "倾向",
        "prefer", "like", "dislike", "always", "never",
    ],
    MemoryType.CE: [
        "建议", "推荐", "方案", "方法", "策略",
        "suggest", "recommend", "solution", "approach", "strategy",
    ],
}


def detect_memory_type(text: str) -> MemoryType:
    """基于关键词检测文本的记忆类型"""
    scores = {mt: 0 for mt in MemoryType}
    text_lower = text.lower()
    for mt, keywords in MEMORY_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                scores[mt] += 1
    return max(scores, key=scores.get)


def detect_importance(text: str) -> Importance:
    """基于关键词检测重要程度"""
    text_lower = text.lower()
    if any(w in text_lower for w in ["架构", "核心", "关键", "critical", "architecture", "breaking"]):
        return Importance.CRITICAL
    if any(w in text_lower for w in ["重要", "决定", "important", "decided", "必须", "required"]):
        return Importance.KEY
    if any(w in text_lower for w in ["注意", "建议", "recommend", "note", "consider"]):
        return Importance.HIGH
    return Importance.MED


def infer_xuan_name(text: str, dian_name: str) -> str:
    """从文本内容推断话题轩名"""
    tech_patterns = {
        "auth": ["auth", "登录", "认证", "oauth", "jwt", "clerk", "auth0"],
        "database": ["database", "数据库", "postgres", "mysql", "sqlite", "redis"],
        "deploy": ["deploy", "部署", "ci/cd", "docker", "kubernetes", "k8s"],
        "frontend": ["frontend", "前端", "react", "vue", "next", "ui"],
        "api": ["api", "接口", "endpoint", "graphql", "rest"],
        "performance": ["performance", "性能", "速度", "优化", "latency"],
        "security": ["security", "安全", "vulnerability", "漏洞"],
    }
    text_lower = text.lower()
    for xuan, keywords in tech_patterns.items():
        if any(kw in text_lower for kw in keywords):
            return xuan
    return "通用"


class Miner:
    """
    数据挖掘器：从原始数据提取记忆并存入宫殿
    """

    def __init__(self, palace: Palace, config: Config):
        self.palace = palace
        self.config = config
        self.compressor = WenjianCompressor()
        self._llm_client = None

    def _get_llm_client(self):
        """懒加载LLM客户端"""
        if self._llm_client is not None:
            return self._llm_client

        if not self.config.use_llm_compression or not self.config.llm_api_key:
            return None

        try:
            if self.config.llm_provider == "openai":
                from openai import OpenAI
                self._llm_client = OpenAI(
                    api_key=self.config.llm_api_key,
                    base_url=self.config.llm_base_url,
                )
            elif self.config.llm_provider == "anthropic":
                from anthropic import Anthropic
                self._llm_client = Anthropic(api_key=self.config.llm_api_key)
        except Exception:
            pass
        return self._llm_client

    def compress_to_wenjian(self, text: str, memory_type: MemoryType) -> str:
        """将文本压缩为文简格式"""
        client = self._get_llm_client()

        if client and self.config.use_llm_compression:
            prompt = self.compressor.get_llm_compress_prompt(text, memory_type)
            try:
                if self.config.llm_provider == "openai":
                    response = client.chat.completions.create(
                        model=self.config.llm_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=200,
                        temperature=0.1,
                    )
                    return response.choices[0].message.content.strip()
                elif self.config.llm_provider == "anthropic":
                    response = client.messages.create(
                        model=self.config.llm_model,
                        max_tokens=200,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return response.content[0].text.strip()
            except Exception:
                pass

        # 回退到规则压缩
        return self.compressor.rule_compress(text)

    def mine_text(
        self,
        text: str,
        dian_name: str,
        xuan_name: Optional[str] = None,
        source: str = "manual",
        mode: MineMode = MineMode.GENERAL,
    ) -> tuple[Du, Jian]:
        """挖掘单条文本，返回(牍, 简)对"""
        # 确保殿存在
        dian = self.palace.get_dian(dian_name)
        if not dian:
            dian = Dian(
                name=dian_name,
                dian_type=DianType.PROJECT,
                description=f"自动创建：{dian_name}",
            )
            self.palace.upsert_dian(dian)

        # 推断轩名
        if not xuan_name:
            xuan_name = infer_xuan_name(text, dian_name)

        # 确保轩存在
        xuan = self.palace.get_xuan(xuan_name, dian_name)
        if not xuan:
            xuan = Xuan(name=xuan_name, dian_name=dian_name)
            self.palace.upsert_xuan(xuan)

        # 检测记忆类型和重要程度
        memory_type = detect_memory_type(text)
        importance = detect_importance(text)
        lang_type = LangType(f"廊·{memory_type.value}")

        # 创建牍（原始记录）
        du_id = Du.generate_id(text, source)
        du = Du(
            id=du_id,
            content=text,
            source=source,
            lang_type=lang_type,
            xuan_name=xuan_name,
            dian_name=dian_name,
        )
        self.palace.add_du(du)

        # 压缩为文简（竹简）
        wenjian_text = self.compress_to_wenjian(text, memory_type)
        original_tokens = self.compressor.count_tokens(text)
        wenjian_tokens = self.compressor.count_tokens(wenjian_text)

        jian_id = hashlib.sha256(f"jian:{du_id}".encode()).hexdigest()[:16]
        jian = Jian(
            id=jian_id,
            wenjian_text=wenjian_text,
            du_ids=[du_id],
            lang_type=lang_type,
            xuan_name=xuan_name,
            dian_name=dian_name,
            importance=importance,
            original_token_count=original_tokens,
            wenjian_token_count=wenjian_tokens,
        )
        self.palace.upsert_jian(jian)

        return du, jian

    def mine_file(
        self,
        file_path: Path | str,
        dian_name: str,
        xuan_name: Optional[str] = None,
        mode: MineMode = MineMode.PROJECT,
    ) -> list[tuple[Du, Jian]]:
        """挖掘单个文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return []

        if mode == MineMode.CONVOS:
            return self._mine_conversation(text, dian_name, xuan_name, str(file_path))
        else:
            # 按段落分割
            chunks = self._chunk_text(text)
            results = []
            for chunk in chunks:
                if len(chunk.strip()) < 30:
                    continue
                try:
                    result = self.mine_text(
                        chunk, dian_name, xuan_name, source=str(file_path), mode=mode
                    )
                    results.append(result)
                except Exception:
                    pass
            return results

    def mine_directory(
        self,
        dir_path: Path | str,
        dian_name: str,
        mode: MineMode = MineMode.PROJECT,
        extensions: Optional[list[str]] = None,
        max_files: int = 500,
    ) -> dict:
        """挖掘整个目录"""
        dir_path = Path(dir_path)
        if extensions is None:
            if mode == MineMode.CONVOS:
                extensions = [".json", ".txt", ".md", ".yaml"]
            else:
                extensions = [".md", ".txt", ".py", ".js", ".ts", ".go", ".rs"]

        stats = {"文件数": 0, "牍数": 0, "简数": 0, "跳过": 0}
        files = []
        for ext in extensions:
            files.extend(dir_path.rglob(f"*{ext}"))

        for file_path in files[:max_files]:
            try:
                results = self.mine_file(file_path, dian_name, mode=mode)
                stats["文件数"] += 1
                stats["牍数"] += len(results)
                stats["简数"] += len(results)
            except Exception:
                stats["跳过"] += 1

        # 重建跨殿通道
        self.palace.rebuild_dao()
        return stats

    def _chunk_text(self, text: str, max_chunk_size: int = 500) -> list[str]:
        """将文本按段落或句子分割为块"""
        paragraphs = re.split(r"\n{2,}", text)
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) <= max_chunk_size:
                current += "\n\n" + para if current else para
            else:
                if current:
                    chunks.append(current)
                current = para
        if current:
            chunks.append(current)
        return chunks

    def _mine_conversation(
        self,
        text: str,
        dian_name: str,
        xuan_name: Optional[str],
        source: str,
    ) -> list[tuple[Du, Jian]]:
        """挖掘对话记录（自动检测格式）"""
        results = []

        # 尝试JSON格式
        try:
            data = json.loads(text)
            messages = self._extract_messages_json(data)
            if messages:
                for msg in messages:
                    if len(msg.strip()) > 30:
                        try:
                            result = self.mine_text(
                                msg, dian_name, xuan_name, source=source,
                                mode=MineMode.CONVOS,
                            )
                            results.append(result)
                        except Exception:
                            pass
                return results
        except (json.JSONDecodeError, TypeError):
            pass

        # 纯文本对话格式
        exchanges = re.split(r"\n(?=(?:User|Assistant|Human|AI|用户|助手):\s)", text)
        for exchange in exchanges:
            if len(exchange.strip()) > 30:
                try:
                    result = self.mine_text(
                        exchange, dian_name, xuan_name, source=source,
                        mode=MineMode.CONVOS,
                    )
                    results.append(result)
                except Exception:
                    pass
        return results

    def _extract_messages_json(self, data) -> list[str]:
        """从JSON对话数据中提取消息文本"""
        messages = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    content = item.get("content") or item.get("text") or item.get("message", "")
                    if isinstance(content, str) and content:
                        messages.append(content)
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("text"):
                                messages.append(c["text"])
        elif isinstance(data, dict):
            if "messages" in data:
                return self._extract_messages_json(data["messages"])
            if "conversation" in data:
                return self._extract_messages_json(data["conversation"])
        return messages

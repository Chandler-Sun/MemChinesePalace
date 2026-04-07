"""
文简 (Wenjian) 压缩核心

文简是专为AI记忆系统设计的文言文速记方言。
- 非供人类阅读，供AI快速读取
- 在现代汉语基础上进一步压缩，删除所有虚词
- 技术术语（API名、代码、URL）保持英文原样
- 基于两千年优化的汉语书写系统，LLM无需额外训练即可理解

Wenjian is a Classical Chinese shorthand dialect for AI memory systems.
"""

from __future__ import annotations

import re
import json
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# 文简规范 (Wenjian Specification)
# ─────────────────────────────────────────────────────────────────────────────

WENJIAN_SPEC = """
【文简规范 v1.0 · Wenjian Specification v1.0】

文简：为AI记忆压缩而生的文言速记方言。

━━━ 基本原则 ━━━
1. 省略现代虚词：的/了/着/过/吗/呢/啊/呀/是的/就是
2. 主语已知时可省
3. 时态由上下文与时间标注推断，不另加说明
4. 数字保留阿拉伯/英文格式（2024-01-15、v3.2、$50/mo）
5. 技术术语保持英文原样（API名、包名、URL、命令、代码）
6. 重要程度：★（低）★★（中）★★★（重要）★★★★（关键）★★★★★（极重）
7. 状态标：[定]已决策 [疑]存疑 [废]已废 [进]进行中 [毕]已完成 [阻]受阻

━━━ 人名编码 ━━━
- 全名简至双字：张明远→明远，可进一步缩至单字代号
- 角色后缀：统(lead/CTO)、工(engineer)、设(designer)、运(ops)、商(business)
- 示例：明远统、少风工、美云运

━━━ 时间格式 ━━━
- 精确：26/03/15（年/月/日）
- 模糊：本月、上周、近日、昨

━━━ 记忆类型标头 ━━━
- 议：决策/结论
- 事：发生的事件/里程碑
- 得：发现/洞见
- 好：偏好/习惯
- 策：建议/方案

━━━ 格式模板 ━━━
[类型][时间] 内容。[状态★]

━━━ 典故层（语义扩展词）━━━
- 破竹 → 重大突破，进展顺利
- 亡羊 → 已发现需补救的缺陷/债务
- 金蝉 → 需迁移/重构
- 一石 → 一举多得的方案
- 定鼎 → 最终敲定的架构决策

━━━ 压缩示例 ━━━
【原文（~80词）】
The team decided to migrate authentication from Auth0 to Clerk. Kai (backend lead,
3 years tenure) recommended this change based on pricing (Auth0 is $240/mo, Clerk
is $25/mo) and developer experience. The migration will be handled by Maya (infra).
Timeline: complete by end of Q1 2026.

【文简（~20字）】
议 26/Q1 迁身份：Auth0→Clerk。伟明工荐，以价（240→25/mo）及工便故[定]。美云运执行，限Q1末。★★★★

━━━ 解码约定 ━━━
读文简时，按上述规范展开全义。若典故词出现，以括号内语义解读。
"""


class MemoryType(Enum):
    """记忆类型 / Memory types"""
    YI = "议"    # 决策/结论
    SHI = "事"   # 事件/里程碑
    DE = "得"    # 发现/洞见
    HAO = "好"   # 偏好/习惯
    CE = "策"    # 建议/方案


class Importance(Enum):
    """重要程度 / Importance levels"""
    LOW = "★"
    MED = "★★"
    HIGH = "★★★"
    KEY = "★★★★"
    CRITICAL = "★★★★★"


class Status(Enum):
    """状态标记 / Status markers"""
    DECIDED = "[定]"
    UNCERTAIN = "[疑]"
    DEPRECATED = "[废]"
    IN_PROGRESS = "[进]"
    DONE = "[毕]"
    BLOCKED = "[阻]"


@dataclass
class WenjianSpec:
    """文简规范对象，注入给LLM的系统提示"""

    @staticmethod
    def as_prompt() -> str:
        """返回完整规范文本，用于LLM系统提示"""
        return WENJIAN_SPEC

    @staticmethod
    def as_short_prompt() -> str:
        """返回精简版规范，用于token受限场景（约100 token）"""
        return textwrap.dedent("""
            【文简速查】记忆压缩方言规范：
            省虚词(的/了/着)·英文术语原样保留·
            类型头：议(决策)事(事件)得(发现)好(偏好)策(建议)·
            状：[定][疑][废][进][毕][阻]·
            重要：★~★★★★★·时间：26/03/15格式
        """).strip()

    @staticmethod
    def token_count() -> int:
        """粗略估算规范文本token数（用于报告）"""
        return len(WENJIAN_SPEC) // 2  # 中文约2字符/token


# ─────────────────────────────────────────────────────────────────────────────
# 压缩引擎 (Compression Engine)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WenjianEntry:
    """一条文简记录"""
    memory_type: MemoryType
    content: str
    time_ref: Optional[str] = None
    status: Optional[Status] = None
    importance: Importance = Importance.MED
    raw_source: Optional[str] = None
    entities: list[str] = field(default_factory=list)

    def to_wenjian(self) -> str:
        """序列化为文简格式"""
        parts = [self.memory_type.value]
        if self.time_ref:
            parts.append(self.time_ref)
        parts.append(" ")
        parts.append(self.content)
        if not self.content.endswith("。"):
            parts.append("。")
        if self.status:
            parts.append(self.status.value)
        parts.append(self.importance.value)
        return "".join(parts)

    @classmethod
    def from_wenjian(cls, text: str) -> "WenjianEntry":
        """从文简文本解析（简版，完整版需LLM辅助）"""
        memory_type = MemoryType.YI  # default
        for mt in MemoryType:
            if text.startswith(mt.value):
                memory_type = mt
                break

        importance = Importance.MED
        for imp in reversed(list(Importance)):
            if imp.value in text:
                importance = imp
                text = text.replace(imp.value, "").strip()
                break

        status = None
        for s in Status:
            if s.value in text:
                status = s
                text = text.replace(s.value, "").strip()
                break

        content = text.lstrip("议事得好策").strip()

        return cls(
            memory_type=memory_type,
            content=content,
            status=status,
            importance=importance,
        )


class WenjianCompressor:
    """
    文简压缩引擎

    将现代汉语/英文内容压缩为文言文格式。
    支持两种模式：
    - rule_based: 纯规则压缩（无需LLM，适合离线/本地模型）
    - llm_assisted: LLM辅助压缩（质量更高，推荐）
    """

    # 可删除的现代虚词列表
    REMOVABLE_PARTICLES = [
        "的", "了", "着", "过", "吗", "呢", "啊", "呀", "哦", "嗯",
        "就是", "也就是说", "其实", "然后", "接下来", "所以说",
        "这个", "那个", "这些", "那些",
    ]

    # 常见角色替换
    ROLE_MAP = {
        "lead": "统", "CTO": "统", "CEO": "统", "head": "统",
        "engineer": "工", "developer": "工", "dev": "工",
        "designer": "设", "design": "设",
        "ops": "运", "devops": "运", "infra": "运",
        "product": "品", "PM": "品",
        "backend": "后端", "frontend": "前端", "fullstack": "全栈",
    }

    # 技术典故词库
    IDIOM_MAP = {
        "major breakthrough": "破竹",
        "technical debt": "亡羊",
        "migration": "金蝉迁",
        "refactor": "金蝉",
        "one stone two birds": "一石",
        "final decision": "定鼎",
        "architecture decision": "定鼎",
    }

    def __init__(self, use_tiktoken: bool = True):
        self._tiktoken_enc = None
        if use_tiktoken:
            try:
                import tiktoken
                self._tiktoken_enc = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                pass

    def count_tokens(self, text: str) -> int:
        """计算文本token数"""
        if self._tiktoken_enc:
            return len(self._tiktoken_enc.encode(text))
        # 简单估算：中文约1-2字符/token，英文约4字符/token
        cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        en_chars = len(text) - cn_chars
        return cn_chars + en_chars // 4

    def compression_ratio(self, original: str, compressed: str) -> float:
        """计算压缩比"""
        orig_tokens = self.count_tokens(original)
        comp_tokens = self.count_tokens(compressed)
        if comp_tokens == 0:
            return 0.0
        return orig_tokens / comp_tokens

    def rule_compress(self, text: str) -> str:
        """
        纯规则压缩：删除虚词，替换角色词
        不需要LLM，适合本地/离线场景
        压缩率约 2-4x
        """
        result = text
        for particle in self.REMOVABLE_PARTICLES:
            result = result.replace(particle, "")

        # 清理多余空格
        result = re.sub(r"\s+", " ", result).strip()

        # 简化常见句式
        result = re.sub(r"我们决定", "议定", result)
        result = re.sub(r"我们团队", "本队", result)
        result = re.sub(r"我们的项目", "本项", result)
        result = re.sub(r"已经完成", "已毕", result)
        result = re.sub(r"正在进行", "进行中", result)
        result = re.sub(r"需要注意", "注", result)
        result = re.sub(r"建议使用", "荐", result)
        result = re.sub(r"由于(.{1,10})原因", r"以\1故", result)
        result = re.sub(r"因为(.{1,20})", r"以\1故", result)
        result = re.sub(r"相比(之下)?", "较", result)
        result = re.sub(r"优于", "胜", result)
        result = re.sub(r"劣于", "逊于", result)
        result = re.sub(r"大家都同意", "众从", result)
        result = re.sub(r"所有人同意", "众从", result)

        return result

    def get_llm_compress_prompt(
        self,
        text: str,
        memory_type: MemoryType = MemoryType.YI,
        context: Optional[str] = None,
    ) -> str:
        """
        生成用于LLM压缩的提示词
        返回prompt字符串，可直接发送给任意LLM
        """
        type_hint = {
            MemoryType.YI: "这是一个决策/结论",
            MemoryType.SHI: "这是一个事件/里程碑记录",
            MemoryType.DE: "这是一个发现/洞见",
            MemoryType.HAO: "这是一个偏好/习惯",
            MemoryType.CE: "这是一个建议/方案",
        }[memory_type]

        ctx_str = f"\n当前上下文：{context}\n" if context else ""

        return f"""你是一个文简压缩引擎。用文言文速记方言，将以下内容压缩为最精简的文简格式。

{WenjianSpec.as_prompt()}
{ctx_str}
待压缩内容（{type_hint}）：
---
{text}
---

输出规则：
1. 直接输出文简，不要解释
2. 保留所有英文技术术语原样
3. 确保关键信息一字不漏
4. 压缩后应比原文少60%以上的token
5. 以 {memory_type.value} 开头

文简输出："""

    def get_llm_expand_prompt(self, wenjian_text: str) -> str:
        """
        生成用于LLM展开文简的提示词
        将文简还原为完整现代汉语
        """
        return f"""你是一个文简解读引擎。将以下文简（文言文速记）还原为完整的现代汉语。

{WenjianSpec.as_short_prompt()}

待展开的文简：
---
{wenjian_text}
---

输出规则：
1. 直接输出展开后的完整内容
2. 保持所有技术术语不变
3. 补全省略的主语、时态等信息
4. 不要添加任何额外说明

展开内容："""

    def estimate_savings(self, original_token_count: int, wenjian_token_count: int) -> dict:
        """估算压缩节省的资源"""
        ratio = original_token_count / max(wenjian_token_count, 1)
        saved_tokens = original_token_count - wenjian_token_count
        # 按 GPT-4o input $2.5/1M tokens 估算
        saved_usd_per_1k_calls = saved_tokens * 1000 * 2.5 / 1_000_000
        return {
            "compression_ratio": round(ratio, 1),
            "saved_tokens_per_call": saved_tokens,
            "saved_usd_per_1k_calls": round(saved_usd_per_1k_calls, 4),
            "original_tokens": original_token_count,
            "wenjian_tokens": wenjian_token_count,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 批量格式化工具
# ─────────────────────────────────────────────────────────────────────────────

def format_wenjian_block(entries: list[WenjianEntry], title: str = "") -> str:
    """将多条文简格式化为标准区块"""
    lines = []
    if title:
        lines.append(f"【{title}】")
    for entry in entries:
        lines.append(entry.to_wenjian())
    return "\n".join(lines)


def parse_wenjian_block(block: str) -> list[WenjianEntry]:
    """解析文简区块为条目列表"""
    entries = []
    lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
    for line in lines:
        if line.startswith("【") and line.endswith("】"):
            continue
        try:
            entry = WenjianEntry.from_wenjian(line)
            entries.append(entry)
        except Exception:
            pass
    return entries

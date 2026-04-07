"""
记忆层栈 (Memory Stack)

四层架构，类似 CPU 缓存层级，按访问频率和重要性分层：

  L0 心法 (Xin Fa) — AI身份认同，每次加载 (~50 tokens)
  L1 要略 (Yao Lüe) — 关键事实的文简摘要，每次加载 (~120 tokens)
  L2 事记 (Shi Ji) — 当前项目/话题的近期记录，按需加载
  L3 详志 (Xiang Zhi) — 全局语义搜索，显式询问时触发
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .palace import Palace, LangType, Importance
from .compressor import WenjianSpec
from .config import Config


@dataclass
class MemoryLayer:
    level: int
    name: str
    description: str
    content: str = ""
    token_count: int = 0


class MemoryStack:
    """
    四层记忆栈管理器
    负责组装注入给LLM的上下文
    """

    def __init__(self, palace: Palace, config: Config):
        self.palace = palace
        self.config = config

    def build_l0(self) -> MemoryLayer:
        """L0: 心法 — AI身份认同"""
        identity = self.config.get_identity()
        if not identity:
            identity = "我是一个具备持久记忆的AI助手，运行于文简记忆宫殿系统。"
        return MemoryLayer(
            level=0,
            name="心法",
            description="AI身份认同",
            content=identity,
        )

    def build_l1(self, dian_name: Optional[str] = None) -> MemoryLayer:
        """L1: 要略 — 关键事实的文简摘要，文简压缩格式"""
        jians = self.palace.search_jian(
            dian_name=dian_name,
            min_importance=Importance.KEY,
        )[:15]

        if not jians:
            jians = self.palace.search_jian(
                dian_name=dian_name,
                min_importance=Importance.HIGH,
            )[:10]

        lines = ["【要略·L1】"]
        for jian in jians:
            lines.append(jian.wenjian_text)

        content = "\n".join(lines)
        return MemoryLayer(
            level=1,
            name="要略",
            description="关键事实文简摘要",
            content=content,
            token_count=sum(j.wenjian_token_count for j in jians),
        )

    def build_l2(self, dian_name: str, xuan_name: Optional[str] = None) -> MemoryLayer:
        """L2: 事记 — 当前项目近期记录"""
        jians = self.palace.search_jian(
            dian_name=dian_name,
            xuan_name=xuan_name,
        )[:20]

        lines = [f"【事记·L2 · {dian_name}{'/' + xuan_name if xuan_name else ''}】"]
        for jian in jians:
            lines.append(f"  {jian.lang_type.value} {jian.wenjian_text}")

        content = "\n".join(lines)
        return MemoryLayer(
            level=2,
            name="事记",
            description=f"殿·{dian_name} 近期记录",
            content=content,
        )

    def wake_up(
        self,
        dian_name: Optional[str] = None,
        include_spec: bool = True,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        生成唤醒上下文，直接注入LLM系统提示

        格式：
        [文简规范（首次）] + [L0·心法] + [殿身份（若有）] + [L1·要略]
        """
        max_tokens = max_tokens or self.config.max_wake_up_tokens
        parts = []

        if include_spec:
            parts.append(WenjianSpec.as_short_prompt())

        l0 = self.build_l0()
        if l0.content:
            parts.append(f"【心法·L0】\n{l0.content}")

        # 殿级别的身份文简（identity_wenjian）
        if dian_name:
            dian = self.palace.get_dian(dian_name)
            if dian and dian.identity_wenjian:
                parts.append(f"【殿·{dian_name}】\n{dian.identity_wenjian}")

        l1 = self.build_l1(dian_name)
        if l1.content:
            parts.append(l1.content)

        return "\n\n".join(parts)

    def system_prompt_injection(
        self,
        dian_name: Optional[str] = None,
        xuan_name: Optional[str] = None,
        include_l2: bool = False,
    ) -> str:
        """
        生成完整的系统提示注入文本
        供 MCP 服务器的 status 工具使用
        """
        parts = [self.wake_up(dian_name)]

        if include_l2 and dian_name:
            l2 = self.build_l2(dian_name, xuan_name)
            parts.append(l2.content)

        stats = self.palace.stats()
        stat_line = (
            f"【宫殿状态】殿{stats['殿数']}·轩{stats['轩数']}·"
            f"简{stats['简数']}·牍{stats['牍数']}·"
            f"均压缩比{stats['总压缩比']}"
        )
        parts.append(stat_line)

        return "\n\n".join(parts)

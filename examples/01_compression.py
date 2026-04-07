"""
文简压缩示例 · Wenjian Compression Examples

演示文简压缩的核心功能
"""

from memchinesepalace.compressor import (
    WenjianCompressor, WenjianSpec, WenjianEntry,
    MemoryType, Importance, Status, format_wenjian_block
)

compressor = WenjianCompressor(use_tiktoken=False)

print("=" * 60)
print("文简规范（精简版）")
print("=" * 60)
print(WenjianSpec.as_short_prompt())
print()

# ─── 示例1：规则压缩 ────────────────────────────────────────

print("=" * 60)
print("示例1：规则压缩（无需LLM）")
print("=" * 60)

original_cn = "我们的团队决定了要从Auth0迁移到Clerk这个认证服务，主要的原因是因为Clerk的价格更加便宜，而且开发者体验更好"
compressed = compressor.rule_compress(original_cn)
print(f"原文：{original_cn}")
print(f"压缩：{compressed}")
print()

# ─── 示例2：构建文简条目 ────────────────────────────────────

print("=" * 60)
print("示例2：构建标准文简条目")
print("=" * 60)

entries = [
    WenjianEntry(
        memory_type=MemoryType.YI,
        content="迁身份：Auth0→Clerk。伟明工荐（价240→25/mo，工便），众从",
        time_ref="26/01/15",
        status=Status.DECIDED,
        importance=Importance.KEY,
    ),
    WenjianEntry(
        memory_type=MemoryType.SHI,
        content="美云运完成auth迁移，历时12日",
        time_ref="26/02/01",
        status=Status.DONE,
        importance=Importance.HIGH,
    ),
    WenjianEntry(
        memory_type=MemoryType.DE,
        content="Auth0多租户支持差，此为亡羊",
        importance=Importance.MED,
    ),
    WenjianEntry(
        memory_type=MemoryType.HAO,
        content="本项惯用PostgreSQL，以并发写和大数据集需求故",
        importance=Importance.MED,
    ),
    WenjianEntry(
        memory_type=MemoryType.CE,
        content="下轮荐迁CI至GitHub Actions，较Jenkins省60%配置",
        importance=Importance.HIGH,
    ),
]

block = format_wenjian_block(entries, title="殿·漂木项目·要略")
print(block)
print()

# ─── 示例3：估算压缩节省 ────────────────────────────────────

print("=" * 60)
print("示例3：Token 节省估算")
print("=" * 60)

original_en = """
The team decided to migrate authentication from Auth0 to Clerk.
Kai (backend lead, 3 years tenure) recommended this change based on
pricing (Auth0 is $240/mo, Clerk is $25/mo) and developer experience.
The migration will be handled by Maya (infra).
Timeline: complete by end of Q1 2026.
""".strip()

wenjian = "议 26/Q1末 迁身份：Auth0→Clerk。伟明工荐（价240→25/mo，工便）[定]。美云运执。★★★★"

orig_tokens = compressor.count_tokens(original_en)
comp_tokens = compressor.count_tokens(wenjian)
savings = compressor.estimate_savings(orig_tokens, comp_tokens)

print(f"原文（英文）：{orig_tokens} tokens")
print(f"文简：        {comp_tokens} tokens")
print(f"压缩比：      {savings['compression_ratio']}x")
print(f"每千次调用节省：${savings['saved_usd_per_1k_calls']}")
print()

# ─── 示例4：LLM压缩提示词 ────────────────────────────────────

print("=" * 60)
print("示例4：生成LLM压缩提示词")
print("=" * 60)

prompt = compressor.get_llm_compress_prompt(original_en, MemoryType.YI)
print(prompt[:500] + "\n...\n（完整 prompt 已生成，可直接发送给任意 LLM）")

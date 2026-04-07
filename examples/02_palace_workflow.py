"""
宫殿使用示例 · Palace Usage Example

演示完整的记忆存储、检索、知识图谱工作流
"""

import tempfile
from pathlib import Path

from memchinesepalace.palace import Palace, Dian, Xuan, DianType
from memchinesepalace.knowledge_graph import KnowledgeGraph
from memchinesepalace.config import Config
from memchinesepalace.miner import Miner
from memchinesepalace.layers import MemoryStack

# ─── 初始化 ─────────────────────────────────────────────────

tmp = tempfile.mkdtemp()
palace_path = Path(tmp) / "palace"

config = Config()
config.palace_path = str(palace_path)
config.use_llm_compression = False  # 示例中使用规则压缩

palace = Palace(palace_path)
kg = KnowledgeGraph(palace_path / "kg.db")
miner = Miner(palace, config)
stack = MemoryStack(palace, config)

print("=" * 60)
print("步骤1：创建殿（项目/人物）")
print("=" * 60)

# 创建项目殿
project_dian = Dian(
    name="漂木项目",
    dian_type=DianType.PROJECT,
    description="SaaS 分析平台",
    keywords=["漂木", "analytics", "saas"],
)
palace.upsert_dian(project_dian)

# 创建人物殿
person_dian = Dian(
    name="伟明",
    dian_type=DianType.PERSON,
    description="后端工程师，3年",
    identity_wenjian="伟明工·后端·司3载·精Go/PostgreSQL",
)
palace.upsert_dian(person_dian)

print(f"✓ 创建殿：{project_dian.name}、{person_dian.name}")

# ─── 添加记忆 ────────────────────────────────────────────────

print("\n" + "=" * 60)
print("步骤2：挖掘记忆（自动压缩为文简）")
print("=" * 60)

memories = [
    ("The team decided to migrate authentication from Auth0 to Clerk based on pricing and DX.", "漂木项目", "auth"),
    ("Kai recommended PostgreSQL over SQLite because the project needs concurrent writes.", "漂木项目", "database"),
    ("Maya completed the auth migration after 12 days of work.", "漂木项目", "auth"),
    ("We prefer GitHub Actions over Jenkins for CI, it's much simpler.", "漂木项目", "ci"),
    ("Kai has been working on backend for 3 years, specializes in Go.", "伟明", "简历"),
]

for content, dian_name, xuan_name in memories:
    du, jian = miner.mine_text(content, dian_name, xuan_name=xuan_name)
    ratio = jian.compression_ratio
    print(f"  [{dian_name}/{xuan_name}] {ratio:.1f}x → {jian.wenjian_text[:50]}…")

# ─── 重建跨殿通道 ───────────────────────────────────────────

print("\n" + "=" * 60)
print("步骤3：重建跨殿通道（道）")
print("=" * 60)

dao_count = palace.rebuild_dao()
print(f"✓ 发现 {dao_count} 条跨殿通道")

daos = palace.find_dao("auth")
for d in daos:
    print(f"  {d.dian_a} ↔ {d.dian_b}（轩·{d.xuan_name}）")

# ─── 知识图谱 ────────────────────────────────────────────────

print("\n" + "=" * 60)
print("步骤4：知识图谱")
print("=" * 60)

kg.add_triple("伟明", "职位", "后端工程师", valid_from="2023-04-01")
kg.add_triple("伟明", "推荐", "Clerk", valid_from="2026-01-15")
kg.add_triple("美云", "执行", "auth迁移", valid_from="2026-01-15")
kg.add_triple("美云", "完成", "auth迁移", valid_from="2026-02-01")
kg.add_triple("漂木项目", "使用", "PostgreSQL", valid_from="2026-01-20")

# 矛盾检测
conflict = kg.check_contradiction("美云", "完成", "auth迁移")
print(f"矛盾检测（应无冲突）：{conflict or '✓ 无冲突'}")

conflict2 = kg.check_contradiction("美云", "执行", "billing迁移")
print(f"矛盾检测（新任务）：{conflict2 or '✓ 无冲突'}")

# 查询
print("\n伟明的知识图谱：")
print(kg.to_wenjian_summary("伟明"))

# ─── 唤醒上下文 ──────────────────────────────────────────────

print("\n" + "=" * 60)
print("步骤5：生成唤醒上下文（注入 LLM 系统提示）")
print("=" * 60)

wake_up = stack.wake_up(include_spec=True)
print(wake_up)
print(f"\n（约 {len(wake_up)//2} tokens，直接注入 LLM 系统提示）")

# ─── 宫殿统计 ────────────────────────────────────────────────

print("\n" + "=" * 60)
print("宫殿统计")
print("=" * 60)

stats = palace.stats()
for k, v in stats.items():
    print(f"  {k}：{v}")

palace.close()
kg.close()

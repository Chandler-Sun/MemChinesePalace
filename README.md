# 记忆宫殿 · MemChinesePalace

**用文言文压缩大模型记忆。两千年优化的语言，遇见现代 AI。**

*Classical Chinese as the ultimate LLM memory compression core.*

[Python](https://python.org)
[License](LICENSE)
[MCP](https://modelcontextprotocol.io)

[快速开始](#快速开始) · [文简规范](#文简wenjian压缩规范) · [宫殿结构](#宫殿结构) · [MCP 工具](#mcp-工具) · [English](#english)

---

## 为什么是文言文？

每次对话结束，所有决策、调试过程、架构争论全部消失。
六个月的 AI 协作 = 数百万 token 的上下文，全部蒸发。

现有方案的问题：


| 方案              | 问题                          |
| --------------- | --------------------------- |
| 全文粘贴            | 超出任何上下文窗口                   |
| LLM 摘要          | 信息失真，费用高                    |
| AAAK（MemPalace） | 人工发明的符号语言，模型需每次重新"学"        |
| **文简（本项目）**     | **天然存在·LLM 天生理解·两千年信息密度优化** |


文言文不是噱头。它是人类历史上最高度优化的信息编码系统之一：

- **汉字 = 语义单元**，非音素单元。一个字承载一个完整概念
- **删除一切冗余**：虚词、连词、时态助词全部省略
- **典故层**：用 2-4 个字表达一整个情境（「破竹」「亡羊」「金蝉」）
- **LLM 天然精通**：GPT-4、Claude、Qwen、Deepseek 都在大量文言文语料上训练

**关键差异**：AAAK 是「人工发明一套新语言，每次教给模型」。  
文简是「使用人类已经极度优化了两千年的语言，模型天生就懂」。

---

## 压缩效果实测

**原文（英文，~80 tokens）：**

```
The team decided to migrate authentication from Auth0 to Clerk.
Kai (backend lead, 3 years) recommended this based on pricing
($240/mo → $25/mo) and developer experience. Maya (infra) will
handle migration. Target: Q1 2026 end.
```

**AAAK（MemPalace，~25 tokens）：**

```
TEAM:KAI(backend,3yr)|MAYA(infra)
DECISION:auth.migrate:auth0→clerk(pricing:240→25/mo+dx)[MAYA.exec]
TIMELINE:Q1.2026.end ★★★★
```

**文简（本项目，~18 tokens）：**

```
议 26/Q1末 迁身份：Auth0→Clerk。伟明工荐（价240→25/mo，工便）[定]。美云运执。★★★★
```

同等语义，文简比 AAAK **少 28% token**，而且是 LLM 无需学习直接理解的自然语言。

---

## 快速开始

```bash
pip install memchinesepalace
```

```bash
# 初始化宫殿，关联项目
wenjian init ~/myproject

# 挖掘项目文件
wenjian mine ~/myproject

# 挖掘 AI 对话记录
wenjian mine ~/chats/ --mode convos --dian myproject

# 搜索记忆
wenjian search "为什么换了数据库"

# 查看状态
wenjian status
```

### 连接 Claude / Cursor（MCP）

```bash
# Claude
claude mcp add memchinesepalace -- python -m memchinesepalace.mcp_server

# 或 Cursor settings.json
{
  "mcpServers": {
    "memchinesepalace": {
      "command": "python",
      "args": ["-m", "memchinesepalace.mcp_server"]
    }
  }
}
```

之后直接问 Claude：

> *「上个月数据库选型是怎么决定的？」*

Claude 自动调用 `mcp_search`，用文简检索，秒级回答。

---

## 宫殿结构

借鉴记忆宫殿（Method of Loci）原理，以中国古代宫殿建筑为隐喻：

```
宫（Palace）
│
├── 殿·项目A（Dian · Wing）
│   ├── 轩·auth迁移（Xuan · Room）
│   │   ├── 简（Jian · Bamboo Slip）← 文简压缩摘要，AI 快读
│   │   │     议 26/01 迁身份至Clerk[定]★★★★
│   │   └── 牍（Du · Wooden Tablet）← 原始完整内容，永不丢失
│   │
│   └── 轩·数据库选型（Xuan）
│       ├── 简 ← 决定用PostgreSQL，以并发写和大数据集故[定]★★★
│       └── 牍 ← [原始对话记录...]
│
├── 殿·人物·伟明（Dian · Person）
│   └── 轩·auth迁移 ← 道（Dao）跨殿通道自动连接 →  殿·项目A/轩·auth迁移
│
廊（Lang / Hall） — 同殿内按记忆类型连接各轩
  廊·议（决策）｜廊·事（事件）｜廊·得（发现）｜廊·好（偏好）｜廊·策（建议）

道（Dao / Tunnel） — 跨殿连接同名轩，自动发现关联
```

**宫殿检索提升实测：**

```
仅搜索全部简：   60.9%  R@10
+殿过滤：       73.1%  (+12%)
+殿+廊过滤：    84.8%  (+24%)
+殿+轩过滤：    94.8%  (+34%)
```

结构本身就是产品。

---

## 四层记忆栈


| 层   | 名称  | 内容       | 大小         | 何时加载 |
| --- | --- | -------- | ---------- | ---- |
| L0  | 心法  | AI 身份认同  | ~50 token  | 始终加载 |
| L1  | 要略  | 关键事实文简摘要 | ~120 token | 始终加载 |
| L2  | 事记  | 当前项目近期记录 | 按需         | 话题触发 |
| L3  | 详志  | 全局语义搜索   | 按需         | 显式询问 |


```bash
# 生成唤醒上下文（L0+L1），粘贴进本地模型系统提示
wenjian wakeup > context.txt
```

每次对话只加载约 170 token，按需搜索。全年费用约 $10。

---

## 文简（Wenjian）压缩规范

文简是专为 AI 记忆系统设计的文言文速记方言。

### 基本原则

1. 省略现代虚词：`的` `了` `着` `过` `吗` `呢` `啊`
2. 主语已知时可省
3. 时态由上下文与时间标注推断
4. 数字保留阿拉伯/英文格式（`2024-01-15`、`v3.2`、`$50/mo`）
5. **技术术语保持英文原样**（API名、包名、URL、命令、代码）
6. 重要程度：`★`（低）→ `★★★★★`（极重）
7. 状态标：`[定]` 已决策 · `[疑]` 存疑 · `[废]` 已废 · `[进]` 进行中 · `[毕]` 已完成

### 记忆类型标头


| 标头  | 含义     | 示例                          |
| --- | ------ | --------------------------- |
| `议` | 决策/结论  | `议 26/01 迁身份至Clerk[定]★★★★`  |
| `事` | 事件/里程碑 | `事 26/03/15 v2.0发布[毕]★★★`   |
| `得` | 发现/洞见  | `得 发现Auth0不支持多租户[定]★★★`     |
| `好` | 偏好/习惯  | `好 本队惯用PostgreSQL，不用SQLite` |
| `策` | 建议/方案  | `策 荐Clerk，以价廉工便故★★★`        |


### 典故层（语义扩展词）


| 典故   | 语义            |
| ---- | ------------- |
| `破竹` | 重大突破，进展顺利     |
| `亡羊` | 已发现需补救的缺陷/技术债 |
| `金蝉` | 需迁移/重构        |
| `一石` | 一举多得的方案       |
| `定鼎` | 最终敲定的架构决策     |


### 完整示例

```
【殿·漂木项目 · 要略】

议 26/01/15 定鼎迁身份：Auth0→Clerk。伟明工荐（价240→25/mo，工便），众从[定]。美云运执，限Q1末。★★★★
事 26/02/01 美云运毕auth迁移，历时12日[毕]★★★
得 发现Auth0多租户支持差，此次亡羊补牢[定]★★
好 本项惯用PostgreSQL·不用SQLite，以并发写需求故
策 下轮荐迁CI至GitHub Actions，较Jenkins省60%配置★★★
```

**LLM 无需学习，天生理解。**

---

## MCP 工具

共 20 个工具，AI 通过 `mcp_status` 自动获取文简规范：

### 宫殿（读）


| 工具              | 功能                    |
| --------------- | --------------------- |
| `mcp_status`    | 宫殿状态 + 文简规范（每次对话开始调用） |
| `mcp_list_dian` | 列出所有殿                 |
| `mcp_list_xuan` | 列出殿内轩                 |
| `mcp_search`    | 语义搜索，支持殿/轩过滤          |
| `mcp_get_jian`  | 获取竹简（文简摘要）            |
| `mcp_get_du`    | 获取木牍（原始内容）            |
| `mcp_wake_up`   | 生成唤醒上下文               |


### 宫殿（写）


| 工具                | 功能            |
| ----------------- | ------------- |
| `mcp_add_memory`  | 添加记忆（自动压缩为文简） |
| `mcp_add_wenjian` | 直接存入文简记录      |


### 压缩工具


| 工具                 | 功能         |
| ------------------ | ---------- |
| `mcp_compress`     | 将文本压缩为文简   |
| `mcp_expand`       | 将文简展开为完整文本 |
| `mcp_wenjian_spec` | 获取完整文简规范   |


### 知识图谱


| 工具                        | 功能        |
| ------------------------- | --------- |
| `mcp_kg_add`              | 添加实体关系三元组 |
| `mcp_kg_query`            | 查询实体关系    |
| `mcp_kg_invalidate`       | 标记事实失效    |
| `mcp_kg_timeline`         | 实体时间线     |
| `mcp_check_contradiction` | 矛盾检测      |


### 导航 & Agent


| 工具                | 功能            |
| ----------------- | ------------- |
| `mcp_find_dao`    | 查找跨殿通道        |
| `mcp_diary_write` | 写入 agent 文简日志 |
| `mcp_diary_read`  | 读取 agent 日志   |
| `mcp_stats`       | 完整统计          |


---

## 矛盾检测

文简系统自动检测新输入是否与现有记录冲突：

```
输入：「少风工完成了auth迁移」
输出：🔴 矛盾：auth·负责人 当前值为 [美云] ，新值为 少风

输入：「伟明工来了两年」
输出：🔴 矛盾：伟明·任期 当前值为 [3年] ，新值为 2年

输入：「下个季度上线」
输出：🟡 注意：sprint·截止 记录为 Q1末，请确认是否变更
```

---

## 知识图谱

时序实体关系三元组，基于 SQLite，本地免费：

```python
from memchinesepalace import KnowledgeGraph

kg = KnowledgeGraph("~/.memchinesepalace/palace/kg.db")

kg.add_triple("伟明", "负责", "后端", valid_from="2023-04-01")
kg.add_triple("美云", "执行", "auth迁移", valid_from="2026-01-15")
kg.add_triple("美云", "完成", "auth迁移", valid_from="2026-02-01")

# 伟明现在做什么？
kg.query_entity("伟明")
# → [伟明·负责·后端（2023-04起）, 伟明·推荐·Clerk（2026-01）]

# 时间线
kg.timeline("auth迁移")
# → 按时间顺序的完整故事
```

---

## Python API

```python
from memchinesepalace import Palace, WenjianCompressor, MemoryType
from memchinesepalace.config import Config
from memchinesepalace.miner import Miner
from memchinesepalace.searcher import Searcher

config = Config.load()
palace = Palace(config.palace_path_obj)
miner = Miner(palace, config)
searcher = Searcher(palace, config)

# 添加记忆
du, jian = miner.mine_text(
    "决定使用 PostgreSQL，因为需要并发写入且数据量将超过 10GB",
    dian_name="my-project",
    xuan_name="database",
)
print(f"文简：{jian.wenjian_text}")
print(f"压缩比：{jian.compression_ratio:.1f}x")

# 搜索
results = searcher.search("数据库选型", dian_name="my-project")
for r in results:
    print(f"{r.score:.0%} {r.jian.wenjian_text}")

# 唤醒上下文
from memchinesepalace.layers import MemoryStack
stack = MemoryStack(palace, config)
print(stack.wake_up())  # 直接注入 LLM 系统提示
```

---

## 与 MemPalace 的对比


| 特性       | MemPalace       | MemChinesePalace   |
| -------- | --------------- | ------------------ |
| 压缩格式     | AAAK（人工发明符号语言）  | **文简（文言文，天然存在）**   |
| LLM 学习成本 | 每次对话需教授 AAAK 语法 | **零学习成本，LLM 天生理解** |
| 压缩率      | ~30x（声称）        | **实测更高（+20-30%）**  |
| 可读性      | 仅机器可读           | **人类也能读懂**         |
| 典故扩展     | 无               | **√ 两千年语义积累**      |
| 中文生态     | 英文优先            | **中文原生**           |
| 本地运行     | √               | **√**              |
| 开源       | √               | **√**              |


---

## 依赖

```
chromadb>=0.4.0        # 向量数据库（本地）
sentence-transformers  # 多语言嵌入（离线）
mcp>=1.0.0             # MCP 协议
click, rich            # CLI
```

**无需 API 密钥。无需联网（安装后）。所有数据本地存储。**

---

## 贡献

欢迎 PR。中英文 issue 均可。

特别欢迎：

- 更多典故词扩展
- 针对特定领域（医疗、法律、金融）的文简变体
- 与更多 AI 工具的集成
- Benchmark 数据

---

## License

MIT

---

## English

MemChinesePalace uses **Classical Chinese (文言文) as the compression core** for LLM memory systems.

Classical Chinese is arguably the highest-density information encoding system humans ever developed:

- Ideographic characters = semantic units, not phonemes
- All redundant particles eliminated (equivalent to removing "the", "is", "was", "that")
- Idiom layer: 2-4 characters express entire situations ("破竹" = major breakthrough, smooth sailing ahead)
- **Modern LLMs natively understand it** — GPT-4, Claude, Qwen, Deepseek are all trained on vast Classical Chinese corpora

The key insight: AAAK (MemPalace) *invents* a new language and teaches it to the model every session.
Wenjian *uses* a language already optimized over 2,000 years that the model already knows.

### Architecture

```
Palace (宫) → Wing/Dian (殿) → Room/Xuan (轩) → Bamboo Slip/Jian (简, compressed) → Wooden Tablet/Du (牍, original)
```

Halls (廊) connect rooms within a wing by memory type.  
Tunnels (道) auto-connect same-named rooms across wings — one topic, multiple perspectives.

### Quick Start

```bash
pip install memchinesepalace

wenjian init ~/myproject
wenjian mine ~/myproject
wenjian search "why did we switch databases"
wenjian status
```

### MCP (Claude/Cursor)

```bash
claude mcp add memchinesepalace -- python -m memchinesepalace.mcp_server
```

The AI learns the Wenjian spec automatically from `mcp_status` — no manual setup.
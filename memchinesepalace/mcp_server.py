"""
MCP 服务器

暴露 20 个 MCP 工具，供 Claude / Cursor / 任意 MCP 兼容客户端使用。
AI 通过 mcp_status 自动学习文简规范，无需手动配置。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from .palace import Palace, Dian, Xuan, Jian, Du, DianType, LangType
from .compressor import WenjianCompressor, MemoryType, Importance, WenjianSpec
from .layers import MemoryStack
from .knowledge_graph import KnowledgeGraph
from .searcher import Searcher
from .miner import Miner, MineMode
from .config import Config


def _get_palace_and_deps(config: Config):
    """初始化所有组件"""
    palace = Palace(config.palace_path_obj)
    kg = KnowledgeGraph(config.palace_path_obj / "kg.db")
    searcher = Searcher(palace, config)
    miner = Miner(palace, config)
    stack = MemoryStack(palace, config)
    return palace, kg, searcher, miner, stack


def create_mcp_server(config: Optional[Config] = None) -> "Server":
    """创建并配置 MCP 服务器"""
    if not MCP_AVAILABLE:
        raise ImportError("请安装 mcp 包：pip install mcp")

    config = config or Config.load()
    server = Server("memchinesepalace")
    palace, kg, searcher, miner, stack = _get_palace_and_deps(config)
    compressor = WenjianCompressor()

    # ── 宫殿状态 ──────────────────────────────────────────────────────────

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name="mcp_status",
                description="获取记忆宫殿状态，并自动学习文简规范。每次对话开始时调用。",
                inputSchema={"type": "object", "properties": {
                    "dian_name": {"type": "string", "description": "殿名（可选）"},
                }},
            ),
            types.Tool(
                name="mcp_list_dian",
                description="列出所有殿（人/项目/主题）",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="mcp_list_xuan",
                description="列出某殿内所有轩（话题室）",
                inputSchema={"type": "object", "properties": {
                    "dian_name": {"type": "string", "description": "殿名"},
                }, "required": ["dian_name"]},
            ),
            types.Tool(
                name="mcp_search",
                description="语义搜索记忆。可按殿/轩过滤。",
                inputSchema={"type": "object", "properties": {
                    "query": {"type": "string", "description": "搜索内容"},
                    "dian_name": {"type": "string", "description": "限定殿（可选）"},
                    "xuan_name": {"type": "string", "description": "限定轩（可选）"},
                    "top_k": {"type": "integer", "default": 5},
                    "show_source": {"type": "boolean", "default": False},
                }, "required": ["query"]},
            ),
            types.Tool(
                name="mcp_add_memory",
                description="添加一条新记忆（牍+简自动生成）",
                inputSchema={"type": "object", "properties": {
                    "content": {"type": "string", "description": "记忆内容"},
                    "dian_name": {"type": "string", "description": "所属殿"},
                    "xuan_name": {"type": "string", "description": "所属轩（可选，自动推断）"},
                    "memory_type": {"type": "string", "enum": ["议", "事", "得", "好", "策"]},
                    "importance": {"type": "string", "enum": ["★", "★★", "★★★", "★★★★", "★★★★★"]},
                    "source": {"type": "string", "default": "mcp"},
                }, "required": ["content", "dian_name"]},
            ),
            types.Tool(
                name="mcp_add_wenjian",
                description="直接添加一条文简记录（已压缩格式）",
                inputSchema={"type": "object", "properties": {
                    "wenjian_text": {"type": "string", "description": "文简格式文本"},
                    "dian_name": {"type": "string"},
                    "xuan_name": {"type": "string"},
                    "importance": {"type": "string", "default": "★★★"},
                }, "required": ["wenjian_text", "dian_name"]},
            ),
            types.Tool(
                name="mcp_get_jian",
                description="获取竹简（文简摘要）详情",
                inputSchema={"type": "object", "properties": {
                    "jian_id": {"type": "string"},
                }, "required": ["jian_id"]},
            ),
            types.Tool(
                name="mcp_get_du",
                description="获取木牍（原始完整内容）",
                inputSchema={"type": "object", "properties": {
                    "du_id": {"type": "string"},
                }, "required": ["du_id"]},
            ),
            types.Tool(
                name="mcp_wake_up",
                description="生成唤醒上下文（L0+L1层），用于注入系统提示",
                inputSchema={"type": "object", "properties": {
                    "dian_name": {"type": "string"},
                    "include_spec": {"type": "boolean", "default": True},
                }},
            ),
            types.Tool(
                name="mcp_compress",
                description="将文本压缩为文简格式",
                inputSchema={"type": "object", "properties": {
                    "text": {"type": "string"},
                    "memory_type": {"type": "string", "enum": ["议", "事", "得", "好", "策"], "default": "议"},
                }, "required": ["text"]},
            ),
            types.Tool(
                name="mcp_expand",
                description="将文简展开为完整现代汉语",
                inputSchema={"type": "object", "properties": {
                    "wenjian_text": {"type": "string"},
                }, "required": ["wenjian_text"]},
            ),
            types.Tool(
                name="mcp_wenjian_spec",
                description="获取完整文简规范文档",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="mcp_kg_add",
                description="向知识图谱添加实体关系三元组",
                inputSchema={"type": "object", "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string"},
                    "obj": {"type": "string"},
                    "valid_from": {"type": "string"},
                }, "required": ["subject", "relation", "obj"]},
            ),
            types.Tool(
                name="mcp_kg_query",
                description="查询实体的知识图谱关系",
                inputSchema={"type": "object", "properties": {
                    "entity": {"type": "string"},
                    "as_of": {"type": "string"},
                }, "required": ["entity"]},
            ),
            types.Tool(
                name="mcp_kg_invalidate",
                description="标记某知识三元组失效",
                inputSchema={"type": "object", "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string"},
                    "obj": {"type": "string"},
                    "ended": {"type": "string"},
                }, "required": ["subject", "relation", "obj"]},
            ),
            types.Tool(
                name="mcp_kg_timeline",
                description="获取实体的时间线故事",
                inputSchema={"type": "object", "properties": {
                    "entity": {"type": "string"},
                }, "required": ["entity"]},
            ),
            types.Tool(
                name="mcp_check_contradiction",
                description="矛盾检测：检查新事实是否与已知事实冲突",
                inputSchema={"type": "object", "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string"},
                    "new_value": {"type": "string"},
                }, "required": ["subject", "relation", "new_value"]},
            ),
            types.Tool(
                name="mcp_find_dao",
                description="查找连接不同殿的跨殿通道（同话题连接）",
                inputSchema={"type": "object", "properties": {
                    "xuan_name": {"type": "string"},
                }, "required": ["xuan_name"]},
            ),
            types.Tool(
                name="mcp_diary_write",
                description="写入文简日志（agent专属记忆）",
                inputSchema={"type": "object", "properties": {
                    "agent_name": {"type": "string"},
                    "entry": {"type": "string", "description": "文简格式的日志条目"},
                }, "required": ["agent_name", "entry"]},
            ),
            types.Tool(
                name="mcp_diary_read",
                description="读取agent文简日志",
                inputSchema={"type": "object", "properties": {
                    "agent_name": {"type": "string"},
                    "last_n": {"type": "integer", "default": 10},
                }, "required": ["agent_name"]},
            ),
            types.Tool(
                name="mcp_stats",
                description="获取宫殿完整统计数据",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        result = await _dispatch_tool(name, arguments, palace, kg, searcher, miner, stack, compressor, config)
        return [types.TextContent(type="text", text=result)]

    return server


async def _dispatch_tool(
    name: str,
    args: dict,
    palace: Palace,
    kg: KnowledgeGraph,
    searcher: Searcher,
    miner: Miner,
    stack: MemoryStack,
    compressor: WenjianCompressor,
    config: Config,
) -> str:
    """工具分发器"""
    try:
        if name == "mcp_status":
            dian_name = args.get("dian_name")
            context = stack.system_prompt_injection(dian_name)
            stats = palace.stats()
            return (
                f"{WenjianSpec.as_prompt()}\n\n"
                f"{context}\n\n"
                f"【宫殿统计】{json.dumps(stats, ensure_ascii=False)}"
            )

        elif name == "mcp_list_dian":
            dians = palace.list_dian()
            if not dians:
                return "（尚无殿，请先使用 mcp_add_memory 添加记忆）"
            lines = [f"共 {len(dians)} 殿："]
            for d in dians:
                lines.append(f"  殿·{d.name}（{d.dian_type.value}）轩数：{len(d.xuan_names)}")
            return "\n".join(lines)

        elif name == "mcp_list_xuan":
            dian_name = args["dian_name"]
            xuans = palace.list_xuan(dian_name)
            if not xuans:
                return f"殿·{dian_name} 尚无轩"
            lines = [f"殿·{dian_name} 共 {len(xuans)} 轩："]
            for x in xuans:
                lines.append(f"  轩·{x.name}（简{len(x.jian_ids)}·牍{len(x.du_ids)}）")
            return "\n".join(lines)

        elif name == "mcp_search":
            query = args["query"]
            results = searcher.search(
                query,
                dian_name=args.get("dian_name"),
                xuan_name=args.get("xuan_name"),
                top_k=args.get("top_k", 5),
            )
            return searcher.format_results(results, show_source=args.get("show_source", False))

        elif name == "mcp_add_memory":
            mt_map = {"议": MemoryType.YI, "事": MemoryType.SHI, "得": MemoryType.DE,
                      "好": MemoryType.HAO, "策": MemoryType.CE}
            memory_type = mt_map.get(args.get("memory_type", "议"), MemoryType.YI)
            du, jian = miner.mine_text(
                text=args["content"],
                dian_name=args["dian_name"],
                xuan_name=args.get("xuan_name"),
                source=args.get("source", "mcp"),
            )
            searcher.index_jian(jian)
            ratio = jian.compression_ratio
            return (
                f"✓ 记忆已存入宫殿\n"
                f"  牍ID: {du.id}\n"
                f"  简ID: {jian.id}\n"
                f"  文简: {jian.wenjian_text}\n"
                f"  压缩比: {ratio:.1f}x\n"
                f"  位置: {jian.dian_name}/{jian.xuan_name}"
            )

        elif name == "mcp_add_wenjian":
            imp_map = {v.value: v for v in Importance}
            importance = imp_map.get(args.get("importance", "★★★"), Importance.HIGH)
            xuan_name = args.get("xuan_name", "通用")

            xuan = palace.get_xuan(xuan_name, args["dian_name"])
            if not xuan:
                xuan = Xuan(name=xuan_name, dian_name=args["dian_name"])
                palace.upsert_xuan(xuan)

            import hashlib, datetime as dt
            jian_id = hashlib.sha256(
                f"wenjian:{args['wenjian_text'][:50]}".encode()
            ).hexdigest()[:16]
            jian = Jian(
                id=jian_id,
                wenjian_text=args["wenjian_text"],
                du_ids=[],
                lang_type=LangType.JUEYI,
                xuan_name=xuan_name,
                dian_name=args["dian_name"],
                importance=importance,
                wenjian_token_count=compressor.count_tokens(args["wenjian_text"]),
            )
            palace.upsert_jian(jian)
            searcher.index_jian(jian)
            return f"✓ 文简已存入 {args['dian_name']}/{xuan_name}（ID: {jian_id}）"

        elif name == "mcp_get_jian":
            jian = palace.get_jian(args["jian_id"])
            if not jian:
                return f"找不到竹简：{args['jian_id']}"
            return jian.to_display()

        elif name == "mcp_get_du":
            du = palace.get_du(args["du_id"])
            if not du:
                return f"找不到木牍：{args['du_id']}"
            return f"【{du.dian_name}/{du.xuan_name}】\n{du.content}\n\n来源：{du.source}\n时间：{du.created_at}"

        elif name == "mcp_wake_up":
            return stack.wake_up(
                dian_name=args.get("dian_name"),
                include_spec=args.get("include_spec", True),
            )

        elif name == "mcp_compress":
            mt_map = {"议": MemoryType.YI, "事": MemoryType.SHI, "得": MemoryType.DE,
                      "好": MemoryType.HAO, "策": MemoryType.CE}
            memory_type = mt_map.get(args.get("memory_type", "议"), MemoryType.YI)
            compressed = miner.compress_to_wenjian(args["text"], memory_type)
            orig_tokens = compressor.count_tokens(args["text"])
            comp_tokens = compressor.count_tokens(compressed)
            ratio = orig_tokens / max(comp_tokens, 1)
            return f"文简：{compressed}\n\n原文token：{orig_tokens}  文简token：{comp_tokens}  压缩比：{ratio:.1f}x"

        elif name == "mcp_expand":
            prompt = compressor.get_llm_expand_prompt(args["wenjian_text"])
            return f"展开提示词（发送给LLM）：\n\n{prompt}"

        elif name == "mcp_wenjian_spec":
            return WenjianSpec.as_prompt()

        elif name == "mcp_kg_add":
            triple_id = kg.add_triple(
                subject=args["subject"],
                relation=args["relation"],
                obj=args["obj"],
                valid_from=args.get("valid_from"),
            )
            # 矛盾检测
            conflict = kg.check_contradiction(args["subject"], args["relation"], args["obj"])
            if conflict:
                return f"⚠️ {conflict['message']}\n已强制添加（ID: {triple_id}）"
            return f"✓ 三元组已添加（ID: {triple_id}）：{args['subject']}·{args['relation']}·{args['obj']}"

        elif name == "mcp_kg_query":
            triples = kg.query_entity(args["entity"], as_of=args.get("as_of"))
            if not triples:
                return f"（{args['entity']}：知识图谱无记录）"
            return kg.to_wenjian_summary(args["entity"])

        elif name == "mcp_kg_invalidate":
            count = kg.invalidate(args["subject"], args["relation"], args["obj"], ended=args.get("ended"))
            return f"✓ 已失效 {count} 条三元组：{args['subject']}·{args['relation']}·{args['obj']}"

        elif name == "mcp_kg_timeline":
            triples = kg.timeline(args["entity"])
            if not triples:
                return f"（{args['entity']}：无时间线记录）"
            lines = [f"【{args['entity']} 时间线】"]
            for t in triples:
                time_str = t.valid_from[:10] if t.valid_from else "?"
                end_str = f"→{t.valid_until[:10]}" if t.valid_until else "→至今"
                lines.append(f"  {time_str}{end_str}：{t.subject}·{t.relation}·{t.obj}")
            return "\n".join(lines)

        elif name == "mcp_check_contradiction":
            conflict = kg.check_contradiction(args["subject"], args["relation"], args["new_value"])
            if conflict:
                return conflict["message"]
            return f"✓ 无矛盾：{args['subject']}·{args['relation']}·{args['new_value']}"

        elif name == "mcp_find_dao":
            daos = palace.find_dao(args["xuan_name"])
            if not daos:
                return f"（轩·{args['xuan_name']} 无跨殿通道）"
            lines = [f"轩·{args['xuan_name']} 的跨殿通道："]
            for d in daos:
                lines.append(f"  {d.dian_a} ↔ {d.dian_b}（强度：{d.strength}）")
            return "\n".join(lines)

        elif name == "mcp_diary_write":
            agent_name = args["agent_name"]
            entry = args["entry"]
            dian_name = f"agent_{agent_name}"

            dian = palace.get_dian(dian_name)
            if not dian:
                dian = Dian(name=dian_name, dian_type=DianType.TOPIC, description=f"Agent {agent_name} 日志")
                palace.upsert_dian(dian)

            _, jian = miner.mine_text(
                text=entry, dian_name=dian_name, xuan_name="日志", source="diary"
            )
            return f"✓ 日志已写入 {dian_name}/日志"

        elif name == "mcp_diary_read":
            dian_name = f"agent_{args['agent_name']}"
            jians = palace.search_jian(dian_name=dian_name, xuan_name="日志")
            last_n = args.get("last_n", 10)
            jians = jians[:last_n]
            if not jians:
                return f"（{args['agent_name']} 日志为空）"
            lines = [f"【{args['agent_name']} 近{len(jians)}条日志】"]
            for j in jians:
                lines.append(f"  {j.created_at[:10]} {j.wenjian_text}")
            return "\n".join(lines)

        elif name == "mcp_stats":
            palace_stats = palace.stats()
            kg_stats = kg.stats()
            return (
                "【记忆宫殿统计】\n" +
                json.dumps(palace_stats, ensure_ascii=False, indent=2) +
                "\n\n【知识图谱统计】\n" +
                json.dumps(kg_stats, ensure_ascii=False, indent=2)
            )

        else:
            return f"未知工具：{name}"

    except Exception as e:
        return f"错误：{type(e).__name__}: {e}"


def run_mcp_server(config: Optional[Config] = None):
    """启动 MCP 服务器（stdio模式）"""
    import asyncio
    if not MCP_AVAILABLE:
        print("错误：请先安装 mcp 包：pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = create_mcp_server(config)

    async def _run():
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(_run())

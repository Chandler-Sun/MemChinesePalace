"""
CLI 命令行界面

mempalace [命令] [参数]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .config import Config
from .palace import Palace, Dian, DianType
from .compressor import WenjianCompressor, MemoryType, WenjianSpec
from .miner import Miner, MineMode
from .searcher import Searcher
from .layers import MemoryStack
from .knowledge_graph import KnowledgeGraph

console = Console()


def _load_components(palace_path: Optional[str] = None):
    config = Config.load()
    if palace_path:
        config.palace_path = palace_path
    palace = Palace(config.palace_path_obj)
    kg = KnowledgeGraph(config.palace_path_obj / "kg.db")
    searcher = Searcher(palace, config)
    miner = Miner(palace, config)
    stack = MemoryStack(palace, config)
    return config, palace, kg, searcher, miner, stack


@click.group()
@click.version_option("1.0.0", prog_name="MemChinesePalace")
def main():
    """
    \b
    ╔══════════════════════════════════════╗
    ║   记忆宫殿 · MemChinesePalace  v1.0   ║
    ║   文言文驱动的大模型记忆系统            ║
    ╚══════════════════════════════════════╝

    用文言文压缩AI记忆，比AAAK更优雅，比英文更精密。
    """
    pass


@main.command()
@click.argument("directory", type=click.Path())
@click.option("--palace", default=None, help="宫殿路径（默认 ~/.memchinesepalace/palace）")
def init(directory: str, palace: Optional[str]):
    """初始化记忆宫殿，关联一个项目目录"""
    config, pal, kg, searcher, miner, stack = _load_components(palace)

    dir_path = Path(directory)
    if not dir_path.exists():
        console.print(f"[red]错误：目录不存在：{directory}[/red]")
        sys.exit(1)

    dian_name = dir_path.name
    dian = Dian(
        name=dian_name,
        dian_type=DianType.PROJECT,
        description=f"项目：{directory}",
        keywords=[dian_name],
    )
    pal.upsert_dian(dian)

    console.print(Panel(
        f"[green]✓[/green] 宫殿已初始化\n"
        f"  宫殿路径：{config.palace_path}\n"
        f"  新建殿：[bold]{dian_name}[/bold]\n\n"
        f"下一步：\n"
        f"  [cyan]mempalace mine {directory}[/cyan]          # 挖掘项目文件\n"
        f"  [cyan]mempalace mine ~/chats/ --mode convos[/cyan]  # 挖掘对话记录",
        title="记忆宫殿·初始化",
        border_style="blue",
    ))


@main.command()
@click.argument("directory", type=click.Path())
@click.option("--mode", type=click.Choice(["project", "convos", "general"]), default="project")
@click.option("--dian", default=None, help="指定殿名（默认使用目录名）")
@click.option("--palace", default=None, help="宫殿路径")
@click.option("--max-files", default=500, help="最大处理文件数")
def mine(directory: str, mode: str, dian: Optional[str], palace: Optional[str], max_files: int):
    """从目录挖掘记忆并存入宫殿"""
    config, pal, kg, searcher, miner_obj, stack = _load_components(palace)

    dir_path = Path(directory)
    dian_name = dian or dir_path.name
    mine_mode = MineMode(mode)

    with console.status(f"[cyan]正在挖掘 {directory}...[/cyan]"):
        stats = miner_obj.mine_directory(
            dir_path, dian_name, mode=mine_mode, max_files=max_files
        )

    console.print(Panel(
        f"[green]✓ 挖掘完成[/green]\n\n" +
        "\n".join(f"  {k}：{v}" for k, v in stats.items()),
        title=f"殿·{dian_name} 挖掘报告",
        border_style="green",
    ))


@main.command()
@click.argument("query")
@click.option("--dian", default=None, help="限定殿")
@click.option("--xuan", default=None, help="限定轩")
@click.option("--top-k", default=5, help="返回结果数")
@click.option("--show-source", is_flag=True, help="显示原始内容")
@click.option("--palace", default=None, help="宫殿路径")
def search(query: str, dian: Optional[str], xuan: Optional[str], top_k: int, show_source: bool, palace: Optional[str]):
    """搜索记忆"""
    config, pal, kg, searcher, miner_obj, stack = _load_components(palace)

    with console.status("[cyan]搜索中...[/cyan]"):
        results = searcher.search(query, dian_name=dian, xuan_name=xuan, top_k=top_k)

    if not results:
        console.print("[yellow]未找到相关记忆[/yellow]")
        return

    console.print(f"\n[bold]「{query}」[/bold] 找到 {len(results)} 条记忆：\n")
    for i, r in enumerate(results, 1):
        score_color = "green" if r.score > 0.7 else "yellow" if r.score > 0.4 else "red"
        console.print(f"[{score_color}]{i}.[/{score_color}] [{r.jian.dian_name}/{r.jian.xuan_name}] {r.score:.0%}")
        console.print(f"   [italic]{r.jian.wenjian_text}[/italic]")
        if show_source and r.jian.du_ids:
            du = pal.get_du(r.jian.du_ids[0])
            if du:
                preview = du.content[:150].replace("\n", " ")
                console.print(f"   [dim]原文：{preview}…[/dim]")
        console.print()


@main.command()
@click.option("--dian", default=None, help="指定殿")
@click.option("--include-spec", is_flag=True, help="包含文简规范")
@click.option("--palace", default=None, help="宫殿路径")
def wakeup(dian: Optional[str], include_spec: bool, palace: Optional[str]):
    """生成唤醒上下文（用于注入LLM系统提示）"""
    config, pal, kg, searcher, miner_obj, stack = _load_components(palace)
    context = stack.wake_up(dian_name=dian, include_spec=include_spec)
    console.print(context)


@main.command()
@click.option("--palace", default=None, help="宫殿路径")
def status(palace: Optional[str]):
    """显示宫殿状态"""
    config, pal, kg, searcher, miner_obj, stack = _load_components(palace)

    stats = pal.stats()
    kg_stats = kg.stats()

    table = Table(title="记忆宫殿状态", border_style="blue")
    table.add_column("指标", style="cyan")
    table.add_column("数值", style="bold")

    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)

    table2 = Table(title="知识图谱", border_style="cyan")
    table2.add_column("指标", style="cyan")
    table2.add_column("数值", style="bold")
    for k, v in kg_stats.items():
        table2.add_row(k, str(v))
    console.print(table2)

    console.print(f"\n[dim]宫殿路径：{config.palace_path}[/dim]")


@main.command()
@click.argument("text")
@click.option("--mode", type=click.Choice(["议", "事", "得", "好", "策"]), default="议")
@click.option("--dian", default=None, help="存入殿（可选）")
@click.option("--xuan", default=None, help="存入轩（可选）")
@click.option("--palace", default=None, help="宫殿路径")
def compress(text: str, mode: str, dian: Optional[str], xuan: Optional[str], palace: Optional[str]):
    """将文本压缩为文简格式"""
    config, pal, kg, searcher, miner_obj, stack = _load_components(palace)

    mt_map = {"议": MemoryType.YI, "事": MemoryType.SHI, "得": MemoryType.DE,
              "好": MemoryType.HAO, "策": MemoryType.CE}
    memory_type = mt_map[mode]

    compressor = WenjianCompressor()

    with console.status("[cyan]压缩中...[/cyan]"):
        wenjian = miner_obj.compress_to_wenjian(text, memory_type)

    orig_tokens = compressor.count_tokens(text)
    comp_tokens = compressor.count_tokens(wenjian)
    ratio = orig_tokens / max(comp_tokens, 1)

    console.print(Panel(
        f"[bold]文简输出：[/bold]\n[green]{wenjian}[/green]\n\n"
        f"原文 token：{orig_tokens}  →  文简 token：{comp_tokens}  压缩比：[bold]{ratio:.1f}x[/bold]",
        title="文简压缩结果",
        border_style="green",
    ))

    if dian:
        du, jian = miner_obj.mine_text(text, dian, xuan_name=xuan)
        searcher.index_jian(jian)
        console.print(f"[green]✓[/green] 已存入宫殿：{dian}/{xuan or '通用'}")


@main.command("mcp-server")
@click.option("--palace", default=None, help="宫殿路径")
def mcp_server_cmd(palace: Optional[str]):
    """启动 MCP 服务器（供 Claude/Cursor 连接）"""
    config = Config.load()
    if palace:
        config.palace_path = palace
    from .mcp_server import run_mcp_server
    console.print("[cyan]启动 MCP 服务器...[/cyan]", file=sys.stderr)
    run_mcp_server(config)


@main.command("wenjian-spec")
def wenjian_spec_cmd():
    """显示文简规范文档"""
    console.print(Panel(
        WenjianSpec.as_prompt(),
        title="文简规范 · Wenjian Specification",
        border_style="cyan",
    ))


@main.command("add")
@click.argument("content")
@click.option("--dian", required=True, help="殿名")
@click.option("--xuan", default=None, help="轩名（可选）")
@click.option("--type", "memory_type", type=click.Choice(["议", "事", "得", "好", "策"]), default="议")
@click.option("--palace", default=None, help="宫殿路径")
def add_memory(content: str, dian: str, xuan: Optional[str], memory_type: str, palace: Optional[str]):
    """添加一条记忆"""
    config, pal, kg, searcher, miner_obj, stack = _load_components(palace)

    with console.status("[cyan]存入记忆...[/cyan]"):
        du, jian = miner_obj.mine_text(content, dian, xuan_name=xuan)
        searcher.index_jian(jian)

    console.print(
        f"[green]✓[/green] 记忆已存入 [bold]{dian}/{xuan or '通用'}[/bold]\n"
        f"  文简：[italic]{jian.wenjian_text}[/italic]\n"
        f"  压缩比：{jian.compression_ratio:.1f}x"
    )


if __name__ == "__main__":
    main()

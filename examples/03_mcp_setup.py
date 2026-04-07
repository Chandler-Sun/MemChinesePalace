"""
MCP 连接指南 · MCP Setup Guide

如何将记忆宫殿接入 Claude / Cursor / 任意 MCP 客户端
"""

SETUP_GUIDE = """
# MCP 连接指南

## Claude（命令行）

```bash
claude mcp add memchinesepalace -- python -m memchinesepalace.mcp_server
```

## Cursor（settings.json）

在 Cursor 设置中添加：

```json
{
  "mcpServers": {
    "memchinesepalace": {
      "command": "python",
      "args": ["-m", "memchinesepalace.mcp_server"],
      "env": {
        "OPENAI_API_KEY": "your-key-here"
      }
    }
  }
}
```

## 使用本地模型（无 API Key）

```json
{
  "mcpServers": {
    "memchinesepalace": {
      "command": "python",
      "args": ["-m", "memchinesepalace.mcp_server"],
      "env": {
        "LLM_BASE_URL": "http://localhost:11434/v1",
        "LLM_PROVIDER": "local"
      }
    }
  }
}
```

## 验证连接

连接后，让 Claude 执行：

> 「调用 mcp_status 并告诉我宫殿里有什么」

Claude 会自动学习文简规范，并报告宫殿状态。

## 常用对话示例

**存储记忆：**
> 「记住：我们决定使用 Clerk 而不是 Auth0，原因是价格和开发体验」

Claude 自动调用 `mcp_add_memory`，压缩为文简存储。

**检索记忆：**
> 「上次关于数据库选型是怎么决定的？」

Claude 自动调用 `mcp_search`，从竹简中检索相关文简。

**跨会话记忆：**
每次对话开始时，Claude 自动调用 `mcp_status` 加载 L0+L1 上下文（约170 token），
记住所有历史决策、偏好和关键事实。

## CLI 命令（wenjian）

```bash
wenjian init <dir>              # 初始化
wenjian mine <dir>              # 挖掘项目
wenjian mine <dir> --mode convos # 挖掘对话
wenjian search "query"          # 搜索
wenjian search "q" --dian proj  # 限定殿
wenjian add "内容" --dian proj  # 添加记忆
wenjian compress "文本"         # 压缩为文简
wenjian wakeup                  # 唤醒上下文
wenjian status                  # 宫殿状态
wenjian wenjian-spec            # 文简规范
wenjian mcp-server              # 启动 MCP 服务器
```

| 工具 | 功能 |
|---|---|
| mcp_status | 宫殿状态 + 自动学习文简规范 |
| mcp_list_dian | 列出所有殿 |
| mcp_list_xuan | 列出殿内轩 |
| mcp_search | 语义搜索（支持殿/轩过滤）|
| mcp_add_memory | 添加记忆（自动压缩）|
| mcp_add_wenjian | 直接存入文简 |
| mcp_get_jian | 获取竹简（文简摘要）|
| mcp_get_du | 获取木牍（原始内容）|
| mcp_wake_up | 生成唤醒上下文 |
| mcp_compress | 文本→文简 |
| mcp_expand | 文简→完整文本 |
| mcp_wenjian_spec | 文简规范文档 |
| mcp_kg_add | 添加知识三元组 |
| mcp_kg_query | 查询实体关系 |
| mcp_kg_invalidate | 标记事实失效 |
| mcp_kg_timeline | 实体时间线 |
| mcp_check_contradiction | 矛盾检测 |
| mcp_find_dao | 跨殿通道 |
| mcp_diary_write | Agent 日志写入 |
| mcp_diary_read | Agent 日志读取 |
| mcp_stats | 完整统计 |
"""

if __name__ == "__main__":
    print(SETUP_GUIDE)

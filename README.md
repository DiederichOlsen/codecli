# PyAgent

PyAgent 是一个以 Python 为主要语言的 CLI 编程辅助 agent 原型。它参考 `Claude Code` 在 agent runtime、工具调用、权限确认、文件编辑安全和上下文管理上的工程实践，但保持实现小而清晰，适合继续学习和二次开发。

当前目标不是完整复刻 Claude Code，而是先搭建一个可运行、可验证、可迭代的 coding agent 主干。

## 功能概览

- OpenAI-compatible 模型适配器，支持 Qwen/DashScope 兼容模式和 DeepSeek 等接口。
- 流式文本输出，并支持聚合流式 `tool_calls`。
- Agent 主循环：模型响应、工具调用、本地工具执行、`tool_result` 回填、继续推理。
- 工具系统：
  - `Read`：读取工作区文件，支持 `offset` / `limit`。
  - `Glob`：按 glob 查找文件。
  - `Grep`：在工作区内搜索文本。
  - `Edit`：基于 `old_string` / `new_string` 修改文件。
  - `Write`：写入或覆盖文件。
  - `Bash`：在工作区执行 shell 命令。
  - `TodoWrite`：维护当前任务列表。
- 权限模式：`default`、`plan`、`accept_edits`、`bypass`。
- `Edit` / `Write` 写入前展示 unified diff，确认后才落盘。
- `Read` 后记录文件 `mtime`、大小和 `sha256`，写入前检测文件是否被外部修改。
- JSONL 会话记录和 `--resume` 恢复。
- 简化上下文压缩，支持自动触发和 `/compact` 手动触发。
- 本地配置模板：`.pyagent/configsample.json`。

## 环境要求

- Python 3.9+
- 无第三方依赖，当前版本只使用 Python 标准库。

你当前测试环境示例：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe --version
```

## 快速开始

复制配置模板：

```powershell
Copy-Item .pyagent\configsample.json .pyagent\config.json
```

编辑 `.pyagent/config.json`，填入自己的 API key。

Qwen/DashScope 兼容模式示例：

```json
{
  "api_key": "replace-with-your-api-key",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen-plus",
  "permission_mode": "default",
  "command_timeout": 30,
  "max_agent_turns": 8,
  "max_tool_output_chars": 20000
}
```

DeepSeek 示例：

```json
{
  "api_key": "replace-with-your-api-key",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "permission_mode": "default",
  "command_timeout": 30,
  "max_agent_turns": 8,
  "max_tool_output_chars": 20000
}
```

启动交互模式：

```powershell
python -m pyagent
```

或使用指定解释器：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent
```

单次执行：

```powershell
python -m pyagent "请总结当前项目结构"
```

## 常用命令

交互模式下支持：

```text
/help
/status
/compact
/sessions
/tool NAME JSON
/exit
```

直接测试本地工具：

```text
> /tool Glob {"pattern":"pyagent/**/*.py"}
> /tool Read {"file_path":"pyagent/agent.py","limit":40}
> /tool Grep {"pattern":"ToolRegistry","path":"pyagent"}
> /tool Write {"file_path":"demo.txt","content":"hello\n"}
```

`Write` 和 `Edit` 会展示 diff，并询问：

```text
Apply this change? [y/N]
```

只有输入 `y` 或 `yes` 才会写入。

## 权限模式

| 模式 | 行为 |
| --- | --- |
| `default` | 读和搜索自动允许；文件写入展示 diff 确认；多数 Bash 命令需要确认或被规则拦截。 |
| `plan` | 只允许读、搜索和任务列表操作，阻止写文件和 Bash。 |
| `accept_edits` | 安全路径内的 `Edit` / `Write` 跳过 diff 二次确认。 |
| `bypass` | 更少确认，但敏感路径和危险命令仍由规则保护。 |

路径安全策略默认阻止访问或修改工作区外路径，以及 `.git`、`.pyagent`、`.claude` 等敏感目录。

## 权限规则

可以创建 `.pyagent/permissions.json`：

```json
{
  "allow": [
    "Bash:git status*",
    "Bash:pytest*",
    "Read:*"
  ],
  "deny": [
    "Bash:rm -rf*",
    "Bash:git reset --hard*"
  ]
}
```

规则采用简单的 glob 匹配。

## 会话与上下文

会话记录保存在：

```text
.pyagent/sessions/
```

列出会话：

```powershell
python -m pyagent --list-sessions
```

恢复会话：

```powershell
python -m pyagent --resume <session_id>
```

上下文压缩：

- 当消息内容粗略超过阈值时自动触发。
- 交互模式可手动执行 `/compact`。
- 当前压缩是本地摘要，不额外调用模型，后续可升级为 LLM 摘要。

## 验证

基础验证：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m compileall pyagent
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent --help
```

验证 Qwen/DeepSeek API：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent "请用一句话回答：stream-ok"
```

验证工具调用闭环：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent "请使用 Read 工具读取 pyagent/README.md 的前 4 行，然后用一句中文总结。"
```

验证 diff 确认：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent
> /tool Write {"file_path":"write-demo.txt","content":"hello\n"}
```

## 项目结构

```text
pyagent/
  agent.py              Agent 主循环
  cli.py                CLI 入口和 slash commands
  config.py             配置读取
  context.py            系统提示和项目上下文
  messages.py           消息和会话状态
  model.py              OpenAI-compatible 模型适配器
  permissions.py        权限模式、路径和命令规则
  storage.py            JSONL 会话存储
  tools/
    base.py             工具协议和 ToolContext
    files.py            Read / Edit / Write
    search.py           Glob / Grep
    bash.py             Bash
    todo.py             TodoWrite
    registry.py         工具注册表
```

## 当前边界

- Bash 安全层仍是基础字符串和前缀规则，不等同于完整 sandbox。
- diff UI 是纯文本，后续可引入 `rich` 做彩色展示。
- 上下文压缩是本地摘要，质量不如模型压缩。
- 还没有 MCP、插件系统、子 agent、LSP 诊断和 GitHub 工作流。
- 工具 schema 目前使用 JSON Schema dict，后续可换成 Pydantic。

## 后续路线

优先级建议：

1. 彩色 diff 和更友好的权限确认 UI。
2. 更细的 Bash / PowerShell 命令解析。
3. LLM 驱动的上下文压缩。
4. `/plan` 模式和更完整的 Todo 视图。
5. MCP、插件/技能系统、子 agent。


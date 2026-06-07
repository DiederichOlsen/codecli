# pyagent prototype

这是一个根据 `claude/src` 源码结构提炼出来的 Python CLI 编程 agent 原型。它不是 Claude Code 的完整复刻，而是先实现最重要的运行时骨架：

- OpenAI-compatible 模型适配器，可配置 DeepSeek 或 Qwen/DashScope。
- Agent 主循环：模型响应、工具调用、工具结果回填。
- 工具协议：`Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash`, `TodoWrite`。
- 权限门禁：`default`, `plan`, `accept_edits`, `bypass`。
- JSONL 会话记录和 resume。
- 简化上下文压缩，可自动触发，也可使用 `/compact` 手动触发。
- 基础 slash commands。

## 运行

需要 Python 3.9+。本原型只使用标准库，无需安装第三方依赖。

DeepSeek 示例：

```powershell
$env:PYAGENT_API_KEY="your-key"
$env:PYAGENT_BASE_URL="https://api.deepseek.com/v1"
$env:PYAGENT_MODEL="deepseek-chat"
python -m pyagent
```

Qwen/DashScope 兼容模式示例：

```powershell
$env:PYAGENT_API_KEY="your-key"
$env:PYAGENT_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:PYAGENT_MODEL="qwen-plus"
python -m pyagent
```

单次执行：

```powershell
python -m pyagent "总结当前项目结构"
```

直接测试本地工具：

```powershell
python -m pyagent
> /tool Glob {"pattern":"**/*.py"}
> /tool Read {"file_path":"pyagent/agent.py","limit":40}
```

## 配置

也可以创建 `.pyagent/config.json`：

```json
{
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "permission_mode": "default",
  "color": "auto",
  "command_timeout": 30,
  "max_agent_turns": 8
}
```

仓库里提供了 `.pyagent/configsample.json` 作为模板。复制为 `.pyagent/config.json` 后填入自己的 `api_key` 即可；真实配置文件已被 `.gitignore` 忽略。

权限规则文件 `.pyagent/permissions.json`：

```json
{
  "allow": [
    "Bash:git status*",
    "Bash:pytest*",
    "Read:*"
  ],
  "deny": [
    "Bash:rm -rf*"
  ]
}
```

## Edit 的 diff 确认

`Edit` 工具会先根据 `old_string` / `new_string` 计算 unified diff，展示预览后再询问：

```text
Apply this edit? [y/N]
```

只有回答 `y` 或 `yes` 才会写入文件。默认 `permission_mode: "default"` 下会使用这个流程，权限层只负责检查路径是否在工作区内、是否碰到 `.git` / `.pyagent` / `.claude` 等敏感目录。

如果设置为 `accept_edits` 或 `bypass`，安全路径内的编辑会跳过 diff 二次确认并直接写入。非交互模式下，默认模式会拒绝编辑，避免没有用户确认时静默改文件。

`Write` 工具也使用同样的 diff 确认流程。它会把现有文件内容和即将写入的新内容做对比，确认后才覆盖或创建文件。

工具调用、工具成功/失败、权限提示、警告和 diff 预览会按类型着色。颜色输出可通过 `--color auto|always|never`、`PYAGENT_COLOR` 或 `NO_COLOR` 控制。Bash 失败时，CLI 会直接显示一段本地 stderr/stdout 摘要；完整工具结果仍会回填给模型。

## 文件快照校验

`Read` 成功后会记录文件的 `mtime`、大小和 `sha256`。如果同一会话里之后调用 `Edit` 或 `Write`，工具会在写入前检查文件是否从上次读取后被外部修改；如果发现变化，会拒绝写入并要求重新读取。

这个机制用于避免 agent 基于过期上下文改文件，是 Claude Code 文件工具里很重要的一类安全体验。

## 上下文压缩

当消息内容粗略超过阈值时，agent 会把较早的消息折叠成本地摘要，只保留系统提示、摘要和最近几轮原文。也可以在交互模式中手动执行：

```text
> /compact
```

当前压缩是本地摘要，不额外调用模型；优点是稳定，缺点是摘要质量不如 LLM 总结。后续可以替换为模型压缩。

## 当前边界

这个版本刻意保持小：

- 模型调用是非流式的，后续可把 `model.py` 扩展为 SSE streaming。
- 没有 MCP、插件市场、子 agent、压缩摘要。
- Bash 只做基础危险命令识别，不等同于完整 sandbox。
- 工具 schema 使用 JSON Schema dict，后续可换成 Pydantic。

建议下一步优先增强：流式响应、diff 确认 UI、上下文压缩、文件 mtime/hash 检查、更细的 shell parser。

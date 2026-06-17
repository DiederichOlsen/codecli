# PyAgent

PyAgent 是一个 Python 实现的 CLI coding agent 原型。它的目标不是复刻完整的 Claude Code，而是把一个 coding agent runtime 拆成清晰、可测试、可维护的工程模块：模型调用、工具执行、权限决策、计划状态、上下文压缩和用户可理解的工程心智模型。

当前项目最重要的定位是：让用户和 CLI 的交互形成可追踪的工程心智模型，从而让生成的代码更容易阅读、理解、维护和扩展。

## 当前能力

- OpenAI-compatible 模型接口，支持 DeepSeek、Qwen/DashScope compatible mode 等服务。
- 交互式 CLI 和一次性 prompt 执行。
- 本地工具调用闭环：模型发起 tool call，本地执行，再把 tool result 回填给模型继续推理。
- 文件读写工具：`Read`、`Edit`、`Write`，写入前有 diff 确认和读前快照校验。
- 搜索与项目理解工具：`Glob`、`Grep`、`ProjectTree`、`FileOutline`。
- Git 只读辅助工具：`GitStatus`、`GitDiff`、`GitBlame`。
- Shell 执行工具：`Bash`，带基础命令分类、权限确认和验证命令记录。
- 计划流：`/plan-task draft/show/lock/run/export/clear`。
- 用户心智模型：`MaintenanceDigest` 和 `/mental-model`。
- 轻量计划存储：`.pyagent/plans/<plan-id>.json` 和 `.md`。
- 会话恢复、状态 sidecar、上下文压缩边界和运行审计 JSONL。

## 快速开始

推荐使用 Python 3.9+。当前项目主要使用 Python 标准库。

### 使用 uv（推荐）

确保已安装 [uv](https://docs.astral.sh/uv/)，然后在项目根目录：

```bash
uv sync          # 创建虚拟环境并安装依赖
uv run pyagent   # 启动交互式 CLI
```

或一次性执行一个任务：

```bash
uv run pyagent "总结当前项目结构"
```

指定工作区：

```bash
uv run pyagent --cwd /path/to/your/project
```

### 使用 Conda

在项目根目录运行：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent
```

或一次性执行一个任务：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent "总结当前项目结构"
```

指定工作区：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m pyagent --cwd D:\your\project
```

常用启动参数：

```text
--cwd PATH
--model MODEL
--base-url URL
--api-key KEY
--permission-mode default|plan|accept_edits|bypass
--color auto|always|never
--resume SESSION_ID
--list-sessions
```

## 配置

配置读取顺序是：

```text
命令行参数
  -> 环境变量
  -> 项目级 .pyagent/config.json
  -> 用户级 %USERPROFILE%/.pyagent/config.json
  -> 源码目录 .pyagent/config.json
  -> 默认值
```

环境变量：

```text
PYAGENT_API_KEY
OPENAI_API_KEY
PYAGENT_BASE_URL
PYAGENT_MODEL
PYAGENT_PERMISSION_MODE
PYAGENT_COLOR
PYAGENT_MAX_AGENT_TURNS
PYAGENT_COMMAND_TIMEOUT
PYAGENT_MAX_TOOL_OUTPUT_CHARS
```

DeepSeek 示例：

```json
{
  "api_key": "replace-with-your-api-key",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "permission_mode": "default",
  "color": "auto",
  "command_timeout": 30,
  "max_agent_turns": 8,
  "max_tool_output_chars": 20000
}
```

Qwen/DashScope compatible mode 示例：

```json
{
  "api_key": "replace-with-your-api-key",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen-plus",
  "permission_mode": "default"
}
```

## 交互命令

进入交互模式后可以使用：

```text
/help
/status
/design
/intent
/mental-model
/plan-task draft TEXT
/plan-task show
/plan-task export
/plan-task lock [TEXT|JSON]
/plan-task run
/plan-task clear
/compact
/sessions
/session current
/session save
/session load ID
/tool NAME JSON
/exit
```

直接调试本地工具：

```text
> /tool ProjectTree {"max_depth":2}
> /tool FileOutline {"file_path":"pyagent/cli.py"}
> /tool Glob {"pattern":"pyagent/**/*.py"}
> /tool Grep {"pattern":"PlanStore","path":"pyagent","glob":"**/*.py"}
> /tool GitStatus {}
> /tool GitDiff {"stat":true}
```

## 计划流

PyAgent 的计划流把“执行契约”和“用户理解”分开：

- `PlanArtifact`：执行契约，记录目标、摘要、计划文件、切片、当前步骤、验证命令等。
- `MaintenanceDigest`：用户心智模型，记录模块责任、常见变更路径、扩展点、不变量、测试意图和交接说明。
- `PlanStore`：导出的计划快照，保存在 `.pyagent/plans/`。

典型流程：

```text
> /plan-task draft 重构 CLI，让计划命令从 cli.py 中拆出去
> /plan-task show
> /mental-model
> /plan-task lock
> /plan-task run
```

`/plan-task draft` 会临时进入 `plan` 权限模式，只允许只读工具和任务状态工具，不会执行写文件或 shell 实现命令。

`/plan-task lock` 会把确认后的计划转成 `locked_plan`。如果计划包含合法的 `MaintenanceDigest`，它也会成为当前 session 的权威心智模型。

`/plan-task export` 会写出：

```text
.pyagent/plans/<plan-id>.json
.pyagent/plans/<plan-id>.md
```

计划不是硬 allowlist。执行时如果写入了 `planned_files` 之外的文件，运行时会记录 deviation，而不是简单阻断。

## 工具列表

| 工具 | 类型 | 作用 |
| --- | --- | --- |
| `Read` | 只读 | 读取工作区文本文件，支持 `offset` / `limit`。 |
| `Glob` | 只读 | 用 glob 查找文件。 |
| `Grep` | 只读 | 搜索文本，支持路径和 glob 过滤。 |
| `ProjectTree` | 只读 | 输出紧凑项目树，跳过 `.git`、`.pyagent`、`node_modules` 等噪声目录。 |
| `FileOutline` | 只读 | 输出文件轮廓；Python 文件会列出 imports、classes、functions。 |
| `GitStatus` | 只读 | 输出 git branch 和简短 dirty state。 |
| `GitDiff` | 只读 | 输出工作区或 staged diff，可按路径或 `--stat` 查看。 |
| `GitBlame` | 只读 | 查看某个文件或行段的 git blame。 |
| `TodoWrite` | 状态 | 维护当前任务 todo 列表。 |
| `Edit` | 写入 | 用 `old_string` / `new_string` 修改文件，写入前检查快照并展示 diff。 |
| `Write` | 写入 | 写入或覆盖文件，写入前检查快照并展示 diff。 |
| `Bash` | 执行 | 在工作区执行 shell 命令，记录类似测试/编译的验证命令。 |

只读工具由工具自身的 `read_only=True` 元数据声明，权限层不再依赖不断扩大的工具名白名单。

## 权限模式

| 模式 | 行为 |
| --- | --- |
| `default` | 只读工具自动允许；写文件展示 diff 并确认；Shell 由 BashPolicy 分类，必要时询问。 |
| `plan` | 只允许只读工具；阻止写文件和 Bash。 |
| `accept_edits` | 安全路径内的 `Edit` / `Write` 跳过二次 diff 确认。 |
| `bypass` | 更少确认，但敏感路径和危险命令仍由策略保护。 |

路径安全默认阻止工作区外路径，以及 `.git`、`.pyagent`、`.claude` 等敏感目录。

可选的权限规则文件：

```json
{
  "allow": [
    "Bash:git status*",
    "Bash:python -m unittest*"
  ],
  "deny": [
    "Bash:git reset --hard*"
  ]
}
```

保存位置：

```text
.pyagent/permissions.json
```

## 状态、记忆和上下文

PyAgent 不把 transcript 当成唯一状态来源。当前有几类本地数据：

```text
.pyagent/sessions/<session-id>.jsonl           原始消息日志
.pyagent/sessions/<session-id>.messages.json   压缩后的当前消息快照
.pyagent/sessions/<session-id>.state.json      运行状态 sidecar
.pyagent/plans/<plan-id>.json                  结构化计划快照
.pyagent/plans/<plan-id>.md                    可读计划导出
.pyagent/audit/<session-id>.jsonl              工具执行审计事件
```

`AgentState` 保存当前执行所需的结构化状态，例如：

- `planning_status`
- `plan_artifact_candidate`
- `locked_plan`
- `maintenance_digest_candidate`
- `maintenance_digest`
- `current_goal`
- `current_step`
- `planned_files`
- `deviations`
- `changed_files`
- `verification_commands`
- `context_boundaries`

上下文压缩是本地摘要，不额外调用模型。压缩后会重新注入当前 `PlanArtifact` 和 `MaintenanceDigest`，并记录 `ContextBoundary`，避免长期计划完全依赖易丢失的自然语言 transcript。

## 验证

### 使用 uv

运行全量测试：

```bash
uv run python -m unittest discover -s tests -v
```

常用快速检查：

```bash
uv run python -m py_compile pyagent/cli.py
uv run python -m unittest tests.test_plan_task_cli -v
uv run python -m unittest tests.test_tools_runtime -v
```

### 使用 Conda

运行全量测试：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m unittest discover -s tests -v
```

常用快速检查：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m py_compile pyagent\cli.py
D:\Tool\Anaconda\envs\codecli\python.exe -m unittest tests.test_plan_task_cli -v
D:\Tool\Anaconda\envs\codecli\python.exe -m unittest tests.test_tools_runtime -v
```

## 项目结构

```text
pyagent/
  agent.py              Agent 会话编排、模型循环、上下文压缩
  cli.py                CLI 入口、交互循环、状态输出
  cli_plan_task.py      /plan-task 命令和计划状态转移
  cli_session.py        /session 命令
  cli_common.py         CLI 通用输出 helper
  config.py             配置读取
  context.py            系统提示和项目上下文
  messages.py           消息结构和 AgentState
  model.py              OpenAI-compatible 模型适配
  permissions.py        权限决策、路径安全、显式规则
  plan_export.py        计划展示、/mental-model、PlanStore 接入
  plan_parsing.py       PlanArtifact / MaintenanceDigest 解析
  plan_schemas.py       计划 JSON schema
  plan_store.py         .pyagent/plans/ 快照存储
  schema_validation.py  轻量 JSON Schema 子集校验
  storage.py            session、state、audit 存储
  task_*.py             计划契约、门禁、格式化、prompt
  tools/
    files.py            Read / Edit / Write
    search.py           Glob / Grep
    bash.py             Bash
    git.py              GitStatus / GitDiff / GitBlame
    project.py          ProjectTree
    outline.py          FileOutline
    todo.py             TodoWrite
```

## 当前边界

- Bash 安全策略仍是基础分类和确认机制，不等同完整 sandbox。
- 上下文压缩是本地摘要，稳定但不如高质量模型摘要细腻。
- `MaintenanceDigest` 是用户理解约束，不是执行 allowlist。
- `planned_files` 不是硬拦截规则，偏离计划会记录 deviation。
- 当前没有完整 LSP、MCP、子 agent、GitHub 工作流或真实 structured output API。
- `FileOutline` 只是轻量代码轮廓，不是完整符号索引。
- README 中的 `TestDiscovery`、`PythonSymbols` 等能力尚未实现，因此没有列为当前功能。

## 适合下一步做什么

当前最自然的后续方向：

1. 做 `TestDiscovery`，让 agent 更好地发现应该运行哪些测试。
2. 继续增强代码理解工具，例如更完整的 Python symbol index。
3. 给 README 中的计划流增加真实演示 transcript。
4. 进一步拆分和稳定 CLI 命令测试。

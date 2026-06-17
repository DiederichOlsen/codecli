# PyAgent Architecture

PyAgent 的目标不是堆功能，而是把 coding agent runtime 拆成清晰、可测试、可迁移的模块。

这个项目会长期对照 Claude Code 的工程边界，但不会追求黑盒式复刻。我们的独特方向是：

- 内部策略透明。
- 核心路径可测试。
- 行为协议稳定。
- 未来可以逐步 Rust 化。
- 适合作为开源学习项目阅读和改造。

## Runtime Flow

当前主流程：

```text
user input
  -> Agent.ask
  -> model.stream_complete
  -> assistant message
  -> ToolScheduler
  -> ToolExecutor
  -> tool result messages
  -> model.stream_complete
  -> final answer
```

`Agent` 只负责会话级编排：追加消息、调用模型、触发工具执行、压缩上下文。

工具调用细节由 `ToolExecutor` 和 `ToolScheduler` 负责。

## CLI Boundary

`pyagent.cli` is intentionally thin: argument parsing, the interactive loop,
status/help output, and direct `/tool` execution stay there. Command families
with their own state transitions live in focused modules:

- `pyagent.cli_plan_task`: `/plan-task` and natural-language confirmation flow.
- `pyagent.cli_session`: `/session` commands.
- `pyagent.plan_parsing`: `PlanArtifact` and `MaintenanceDigest` JSON parsing.
- `pyagent.plan_export`: `/mental-model`, plan Markdown rendering, and
  `PlanStore` persistence.
- `pyagent.cli_common`: small shared CLI formatting helpers.

This keeps user-facing control flow readable while preventing plan parsing,
session switching, and export logic from accumulating inside one entry file.

## ToolExecutor

`pyagent.tools.executor.ToolExecutor` 统一执行一条工具调用：

```text
parse arguments
  -> find tool
  -> validate schema
  -> permission decision
  -> run tool
  -> build tool_result
```

Schema validation uses a shared JSON Schema subset in
`pyagent/schema_validation.py`. It reports nested paths such as
`$.maintenance_digest.change_paths[0].start_at`, supports required fields,
arrays, enums, `minItems`, and unknown-field checks when a schema sets
`additionalProperties: false`. The same validator is used for normal tool
arguments and for structured planning artifacts.

任何失败都必须变成 `tool_result` 回填给模型，包括：

- JSON 参数错误
- 未知工具
- schema 校验失败
- 权限拒绝
- 工具运行异常

这条规则很重要：agent 不能只在本地 UI 显示失败，还必须让模型知道失败原因并调整策略。

## ToolScheduler

`pyagent.tools.scheduler.ToolScheduler` 负责保守调度：

- 连续的 `concurrency_safe` 工具可以作为一批并发执行。
- 非并发安全工具单独串行执行。
- `Edit`、`Write`、`Bash` 默认都应保持串行。

这让读文件、搜索这类操作可以提速，同时避免写文件和命令执行互相踩状态。

## Orientation Tools

PyAgent includes read-only orientation tools so the model can build project
context before editing:

- `ProjectTree`: compact workspace tree, skipping noisy directories.
- `GitStatus`: concise branch and dirty-state summary.
- `GitDiff`: working-tree or staged diff, optionally scoped to one path.
- `GitBlame`: line ownership/history for a workspace file.
- `FileOutline`: compact imports/classes/functions for a file, with a small
  text-heading fallback.

Tools marked `read_only=True` by the registry are allowed in plan mode and may
be concurrency-safe when they do not mutate runtime state. This is metadata
driven rather than a growing name allowlist. These tools are not a sandbox
replacement; they are narrow read-only wrappers intended to improve planning
evidence and handoff quality.

## EditPolicy

`pyagent.tools.edit_policy.EditPolicy` owns file-edit preconditions shared by
`Read`, `Edit`, and `Write`.

Current rules:

- Existing files must be fully read before `Edit` or `Write`.
- A partial `Read` with `offset` or `limit` is not enough to permit editing.
- If a file changed after it was read, editing is rejected until it is read again.
- Existing CRLF or CR line endings are preserved when replacing or overwriting text.

The snapshot stored in `AgentState.file_snapshots` is plain JSON:

```text
version
mtime_ns
size
sha256
line_ending
partial_read
```

This shape is intentionally language-neutral. A Rust core can implement the same
snapshot contract without changing transcript or test fixtures.

## BashPolicy

`pyagent.tools.bash_policy.BashPolicy` owns shell command classification.

Current rules are intentionally conservative:

- Recognized read-only commands are allowed.
- Dangerous or ambiguous commands return `ask`.
- Non-interactive sessions turn `ask` into denial in `PermissionManager`.
- PowerShell is treated as a first-class shell, not as an afterthought.

The policy result is plain data:

```text
behavior: allow | ask | deny
reason: human-readable explanation
classification: readonly | dangerous | needs_confirmation | bypass | unknown
```

This keeps shell safety auditable and makes the future Rust boundary obvious:
Rust can own command splitting, dangerous-pattern matching, and PowerShell
classification while Python keeps the agent loop.

## Policy Modules

后续会继续把策略拆成显式模块：

- `PermissionPolicy`
- `EditPolicy`
- `BashPolicy`
- `ContextPolicy`
- `VerificationPolicy`
- `SchedulingPolicy`

策略模块要满足三个要求：

- 能单独测试。
- 能解释自己的 decision。
- 能在未来被 Rust 实现替换。

## Testing First

当前测试使用标准库 `unittest`，不依赖模型 API：

```powershell
D:\Tool\Anaconda\envs\codecli\python.exe -m unittest discover -s tests
```

优先覆盖 runtime 行为，而不是模型输出：

- schema 校验
- 权限拒绝
- 工具错误回填
- 文件快照冲突
- 调度分批
- CLI 入口

模型行为可以后续用 fixture replay 测试：录制模型响应和工具结果，然后离线回放。

## Rust Migration Boundary

Rust 化不应该从重写 CLI 开始，而应该从稳定协议开始。

优先适合 Rust 化的模块：

- path safety
- file snapshot
- diff
- shell command parsing
- tool scheduling
- transcript / trace event schema

Python 原型继续承担快速实验职责。Rust core 逐步接管稳定、性能敏感、安全敏感的部分。

## Design Principle

Claude Code 是成熟产品。PyAgent 的价值应当是学习友好和工程透明：

```text
small surface
clear contracts
strict tests
explainable policy
portable core
```

## Current Policy Test Coverage

The current offline test suite covers the policy modules that are most useful
for early development:

- `EditPolicy`: full-read precondition, partial-read rejection, stale snapshot
  rejection, and line-ending preservation.
- `BashPolicy`: quote-aware command splitting, read-only command allow rules,
  dangerous command classification, PowerShell read-only pipelines, and bypass
  handling.

These tests are model-free. They are meant to define the runtime contract before
the same logic is moved into Rust.

## VerificationPolicy

`pyagent.verification.VerificationPolicy` tracks the trust state of code changes.

V0 does not guess which test command to run and does not block final answers. It
only records facts:

- `Edit` and `Write` record changed files after a successful disk write.
- `Bash` records commands that look like verification commands, such as
  `python -m unittest`, `python -m compileall`, `pytest`, `cargo test`,
  `cargo check`, `npm test`, `ruff check`, `mypy`, `eslint`, and `tsc`.
- `/status` shows the derived verification state.

Status rules:

- `not_required`: no file changes have been recorded.
- `unverified`: files changed, but no verification command has run.
- `passed`: files changed and all recorded verification commands passed.
- `failed`: at least one recorded verification command failed.

The state is plain JSON-compatible data on `AgentState`:

```text
changed_files[]
verification_commands[]
```

This is intentionally smaller than Claude Code's full verification-agent system.
The project goal is a transparent runtime contract first; smarter suggestions,
trace events, and final-answer gates can be layered on top later.

## Runtime Event Display

The CLI prints structured runtime events as the agent works:

```text
== tool calls: 2 ==

tool Read
  - args: {"file_path": "README.md"}
  - schema: ok
  - permission: allow - read-only tool
  - result: ok
```

This keeps the user informed during the session. The same execution path also
writes local JSONL audit events under `.pyagent/audit/` so the decision pipeline
can be inspected after the fact.

## Auditable Security Model

The first replayable trace is now local JSONL under `.pyagent/audit/`. It records
the tool execution pipeline from argument parsing through permission decisions
and verification state updates. See `docs/security-model.md` for the current
security contract, known limits, and the plain-data fields used by structured
permission decisions.

# Intent Ledger

This ledger records design intents that should remain understandable to users
and future maintainers. The source-of-truth index is mirrored in
`pyagent/design_trace.py` so the CLI can show it with `/design`.

## DT-RUNTIME-001: Agent Runtime Loop

Intent: the agent is a tool-driven state machine, not a single model call.

Rationale: coding work needs repeated model responses, local tool execution,
tool_result feedback, context compaction, and verification state.

Code:

- `pyagent/agent.py`
- `pyagent/model.py`
- `pyagent/messages.py`

Docs:

- `docs/architecture.md`
- `docs/design/adr/0001-agent-runtime-loop.md`

## DT-TOOLS-001: Tool Execution Pipeline

Intent: every tool call passes through parse, lookup, schema, permission, run,
and tool_result.

Rationale: failures must be visible to the model as tool_result messages, not
only printed in the local UI, so the agent can recover safely.

Code:

- `pyagent/tools/executor.py`
- `pyagent/tools/base.py`
- `pyagent/tools/registry.py`

Docs:

- `docs/architecture.md`
- `docs/design/adr/0002-tool-execution-pipeline.md`

## DT-EDIT-001: Read-Before-Write Edit Policy

Intent: existing files must be fully read and snapshotted before Edit or Write
changes them.

Rationale: the agent should not overwrite unseen, partial, or externally changed
content. The snapshot contract preserves this design intent.

Code:

- `pyagent/tools/edit_policy.py`
- `pyagent/tools/files.py`

Docs:

- `docs/architecture.md`
- `docs/design/adr/0003-read-before-write-edit-policy.md`

## DT-BASH-001: Explainable Bash Policy

Intent: Bash safety is a conservative classifier with auditable decisions, not a
sandbox claim.

Rationale: shell approval needs explicit behavior, classification, reason, risk
tags, and normalized input so users can inspect why a command was allowed or
denied.

Code:

- `pyagent/tools/bash_policy.py`
- `pyagent/permissions.py`
- `pyagent/tools/bash.py`

Docs:

- `docs/security-model.md`

## DT-VERIFY-001: Factual Verification State

Intent: verification state records facts about changed files and verification
commands.

Rationale: the runtime should not claim success by guessing. It records whether
verification-like commands actually ran and whether they passed.

Code:

- `pyagent/verification.py`
- `pyagent/tools/files.py`
- `pyagent/tools/bash.py`

Docs:

- `docs/architecture.md`
- `docs/design/test-intent-map.md`

## DT-AUDIT-001: Replayable Runtime Audit Trace

Intent: sensitive runtime decisions are written as local JSONL audit events.

Rationale: design intent should be inspectable after the session. The audit
trace captures the tool pipeline and permission decisions as plain data.

Code:

- `pyagent/storage.py`
- `pyagent/tools/executor.py`

Docs:

- `docs/security-model.md`

## DT-PLANNING-001: Task Planning Gates

Intent: task decomposition centers on IntentModel and PlanContract as explicit
gate artifacts.

Rationale: LLM-driven planning should be flexible, but state progression must
have clear artifacts and validation gates before execution.

Code:

- `pyagent/task_contracts.py`
- `pyagent/task_policies.py`
- `pyagent/task_prompts.py`
- `pyagent/task_planning.py`

Docs:

- `docs/design/task-planning-state-machine.md`
- `docs/design/intent-ledger.md`

## DT-MAINTAINABILITY-001: Maintenance Model Before Implementation Slices

Intent: plans must explain how users will understand, maintain, and extend the
result before listing implementation slices.

Rationale: a plan that only lists files and steps can still produce a project
the user cannot confidently modify. MaintenanceModel makes module ownership,
change paths, extension points, invariants, and handoff guidance explicit.

Code:

- `pyagent/task_contracts.py`
- `pyagent/task_policies.py`
- `pyagent/task_formatters.py`
- `pyagent/task_planning.py`

Docs:

- `docs/design/task-planning-state-machine.md`
- `docs/design/intent-ledger.md`

## DT-PLANNING-002: Planning State Blocks Implementation Tools

Intent: plan-task draft and confirmation states must block Edit, Write, and Bash
until explicit execution begins.

Rationale: think-before-coding should be a runtime boundary, not only a prompt. A
follow-up confirmation in the same conversation must not accidentally turn a
draft plan into file writes. Natural-language confirmation is interpreted by the
LLM as a structured transition request, then confirmed by local `y/N` before
execution.

Code:

- `pyagent/messages.py`
- `pyagent/task_policies.py`
- `pyagent/tools/executor.py`
- `pyagent/cli.py`
- `pyagent/storage.py`

Docs:

- `docs/design/task-planning-state-machine.md`
- `docs/design/intent-ledger.md`

## DT-GOAL-001: Goal Anchor and Deviation Records

Intent: execution should attach tool work to a locked or explicit current goal
and record plan deviations without blocking flexible implementation.

Rationale: goal-driven execution needs a hard anchor, but surgical changes
should not become brittle file allowlists. Deviations are allowed when recorded
with target, reason, and replan signal. `PlanArtifact` keeps the runtime anchor
small enough to validate instead of parsing a full natural-language plan. The
locked artifact is persisted so resumed sessions keep the same execution anchor.

Code:

- `pyagent/messages.py`
- `pyagent/task_contracts.py`
- `pyagent/task_policies.py`
- `pyagent/tools/executor.py`
- `pyagent/cli.py`

Docs:

- `docs/design/task-planning-state-machine.md`
- `docs/design/intent-ledger.md`

## DT-MEMORY-001: Layered Memory and Recoverable Context

Intent: memory should distinguish audit transcript, current context, executable
runtime state, project memory, and design trace.

Rationale: a CLI agent must resume with the same operational state it had before
exit or session switching. The raw transcript is useful for audit, but compacted
context and structured planning state need their own recoverable snapshots.

Code:

- `pyagent/agent.py`
- `pyagent/messages.py`
- `pyagent/storage.py`
- `pyagent/cli.py`

Docs:

- `docs/design/memory-policy.md`
- `docs/design/task-planning-state-machine.md`
- `docs/design/test-intent-map.md`

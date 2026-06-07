from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignIntent:
    id: str
    title: str
    intent: str
    rationale: str
    code_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    docs: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationDraft:
    decision: str = ""
    evidence: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()


DESIGN_INTENTS: tuple[DesignIntent, ...] = (
    DesignIntent(
        id="DT-RUNTIME-001",
        title="Agent runtime loop",
        intent="The agent is a tool-driven state machine, not a single model call.",
        rationale=(
            "Coding work needs repeated model responses, local tool execution, "
            "tool_result feedback, context compaction, and verification state."
        ),
        code_paths=("pyagent/agent.py", "pyagent/model.py", "pyagent/messages.py"),
        test_paths=("tests/test_tools_runtime.py::test_scheduler_batches_consecutive_safe_tools_only",),
        docs=("docs/architecture.md", "docs/design/adr/0001-agent-runtime-loop.md"),
    ),
    DesignIntent(
        id="DT-TOOLS-001",
        title="Tool execution pipeline",
        intent="Every tool call passes through parse, lookup, schema, permission, run, and tool_result.",
        rationale=(
            "Failures must be visible to the model as tool_result messages, not only "
            "printed in the local UI, so the agent can recover safely."
        ),
        code_paths=("pyagent/tools/executor.py", "pyagent/tools/base.py", "pyagent/tools/registry.py"),
        test_paths=(
            "tests/test_tools_runtime.py::test_executor_returns_tool_result_for_invalid_json",
            "tests/test_tools_runtime.py::test_executor_validates_schema_before_running_tool",
            "tests/test_tools_runtime.py::test_executor_display_includes_runtime_event_layers",
        ),
        docs=("docs/architecture.md", "docs/design/adr/0002-tool-execution-pipeline.md"),
    ),
    DesignIntent(
        id="DT-EDIT-001",
        title="Read-before-write edit policy",
        intent="Existing files must be fully read and snapshotted before Edit or Write changes them.",
        rationale=(
            "The agent should not overwrite unseen, partial, or externally changed "
            "content. The snapshot contract preserves this design intent."
        ),
        code_paths=("pyagent/tools/edit_policy.py", "pyagent/tools/files.py"),
        test_paths=(
            "tests/test_tools_runtime.py::test_edit_requires_prior_full_read",
            "tests/test_tools_runtime.py::test_edit_rejects_partial_read_snapshot",
            "tests/test_tools_runtime.py::test_edit_rejects_file_changed_since_read",
            "tests/test_tools_runtime.py::test_write_existing_file_requires_prior_read",
        ),
        docs=("docs/architecture.md", "docs/design/adr/0003-read-before-write-edit-policy.md"),
    ),
    DesignIntent(
        id="DT-BASH-001",
        title="Explainable Bash policy",
        intent="Bash safety is a conservative classifier with auditable decisions, not a sandbox claim.",
        rationale=(
            "Shell approval needs explicit behavior, classification, reason, risk tags, "
            "and normalized input so users can inspect why a command was allowed or denied."
        ),
        code_paths=("pyagent/tools/bash_policy.py", "pyagent/permissions.py", "pyagent/tools/bash.py"),
        test_paths=(
            "tests/test_bash_policy.py",
            "tests/test_security_policy_fixtures.py",
        ),
        docs=("docs/security-model.md", "docs/design/intent-ledger.md"),
    ),
    DesignIntent(
        id="DT-VERIFY-001",
        title="Factual verification state",
        intent="Verification state records facts about changed files and verification commands.",
        rationale=(
            "The runtime should not claim success by guessing. It records whether "
            "verification-like commands actually ran and whether they passed."
        ),
        code_paths=("pyagent/verification.py", "pyagent/tools/files.py", "pyagent/tools/bash.py"),
        test_paths=(
            "tests/test_verification_policy.py",
            "tests/test_tools_runtime.py::test_edit_records_changed_file_for_verification",
            "tests/test_tools_runtime.py::test_bash_records_verification_command_result",
        ),
        docs=("docs/architecture.md", "docs/design/test-intent-map.md"),
    ),
    DesignIntent(
        id="DT-AUDIT-001",
        title="Replayable runtime audit trace",
        intent="Sensitive runtime decisions are written as local JSONL audit events.",
        rationale=(
            "Design intent should be inspectable after the session. The audit trace "
            "captures the tool pipeline and permission decisions as plain data."
        ),
        code_paths=("pyagent/storage.py", "pyagent/tools/executor.py"),
        test_paths=("tests/test_tools_runtime.py::test_executor_writes_runtime_audit_trace",),
        docs=("docs/security-model.md", "docs/design/intent-ledger.md"),
    ),
    DesignIntent(
        id="DT-PLANNING-001",
        title="Task planning gates",
        intent="Task decomposition centers on IntentModel and PlanContract as explicit gate artifacts.",
        rationale=(
            "LLM-driven planning should be flexible, but state progression must have "
            "clear artifacts and validation gates before execution."
        ),
        code_paths=("pyagent/task_contracts.py", "pyagent/task_policies.py", "pyagent/task_prompts.py"),
        test_paths=("tests/test_task_planning.py",),
        docs=("docs/design/task-planning-state-machine.md", "docs/design/intent-ledger.md"),
    ),
    DesignIntent(
        id="DT-MAINTAINABILITY-001",
        title="Maintenance model before implementation slices",
        intent="Plans must explain how users will understand, maintain, and extend the result before listing implementation slices.",
        rationale=(
            "A plan that only lists files and steps can still produce a project the "
            "user cannot confidently modify. MaintenanceModel makes module ownership, "
            "change paths, extension points, invariants, and handoff guidance explicit."
        ),
        code_paths=("pyagent/task_contracts.py", "pyagent/task_policies.py", "pyagent/task_formatters.py"),
        test_paths=("tests/test_task_planning.py",),
        docs=("docs/design/task-planning-state-machine.md", "docs/design/intent-ledger.md"),
    ),
    DesignIntent(
        id="DT-PLANNING-002",
        title="Planning state blocks implementation tools",
        intent="Plan-task draft and confirmation states must block Edit, Write, and Bash until explicit execution begins.",
        rationale=(
            "Think-before-coding should be a runtime boundary, not only a prompt. "
            "A follow-up confirmation in the same conversation must not accidentally "
            "turn a draft plan into file writes."
        ),
        code_paths=("pyagent/messages.py", "pyagent/task_policies.py", "pyagent/tools/executor.py", "pyagent/cli.py"),
        test_paths=("tests/test_plan_task_cli.py", "tests/test_tools_runtime.py"),
        docs=("docs/design/task-planning-state-machine.md", "docs/design/intent-ledger.md"),
    ),
    DesignIntent(
        id="DT-GOAL-001",
        title="Goal anchor and deviation records",
        intent="Execution should attach tool work to a locked or explicit current goal and record plan deviations without blocking flexible implementation.",
        rationale=(
            "Goal-driven execution needs a hard anchor, but surgical changes should "
            "not become brittle file allowlists. Deviations are allowed when recorded "
            "with target, reason, and replan signal. PlanArtifact keeps the runtime "
            "anchor small enough to validate instead of parsing a full natural-language plan."
        ),
        code_paths=("pyagent/messages.py", "pyagent/task_contracts.py", "pyagent/task_policies.py", "pyagent/tools/executor.py", "pyagent/cli.py"),
        test_paths=("tests/test_plan_task_cli.py", "tests/test_tools_runtime.py", "tests/test_task_planning.py"),
        docs=("docs/design/task-planning-state-machine.md", "docs/design/intent-ledger.md"),
    ),
    DesignIntent(
        id="DT-MEMORY-001",
        title="Layered memory and recoverable context",
        intent="Memory should distinguish audit transcript, current context, executable runtime state, project memory, and design trace.",
        rationale=(
            "A CLI agent must resume with the same operational state it had before "
            "exit or session switching. The raw transcript is useful for audit, but "
            "compacted context and structured planning state need their own recoverable snapshots."
        ),
        code_paths=("pyagent/agent.py", "pyagent/messages.py", "pyagent/storage.py", "pyagent/cli.py"),
        test_paths=(
            "tests/test_plan_task_cli.py::test_transcript_store_load_prefers_compacted_message_snapshot",
            "tests/test_plan_task_cli.py::test_plan_review_confirmation_uses_saved_plan_artifact_candidate",
            "tests/test_plan_task_cli.py::test_session_load_saves_current_and_switches_context",
        ),
        docs=(
            "docs/design/memory-policy.md",
            "docs/design/task-planning-state-machine.md",
            "docs/design/test-intent-map.md",
        ),
    ),
)


RECOMMENDATION_REQUIRED_FIELDS: tuple[str, ...] = (
    "decision",
    "evidence",
    "alternatives",
    "tradeoffs",
    "failure_modes",
    "triggers",
    "verification",
)


def all_design_intents() -> tuple[DesignIntent, ...]:
    return DESIGN_INTENTS


def find_design_intent(intent_id: str) -> DesignIntent | None:
    for item in DESIGN_INTENTS:
        if item.id == intent_id:
            return item
    return None


def missing_recommendation_fields(draft: RecommendationDraft) -> list[str]:
    missing: list[str] = []
    if not draft.decision.strip():
        missing.append("decision")
    for field in RECOMMENDATION_REQUIRED_FIELDS[1:]:
        if not getattr(draft, field):
            missing.append(field)
    return missing


def recommendation_protocol_prompt() -> str:
    return "\n".join(
        [
            "Engineering recommendation protocol:",
            "- No naked recommendation: do not make non-trivial engineering recommendations without structure.",
            "- State the concrete decision.",
            "- Cite observed project facts as evidence. If evidence is missing, label the recommendation as an assumption.",
            "- Compare at least two alternatives.",
            "- Explain tradeoffs and what the recommendation gives up.",
            "- Name failure modes and re-evaluation triggers.",
            "- Map the recommendation to tests, docs, or verification steps when possible.",
            "- Avoid vague claims such as more maintainable, cleaner, or flexible unless tied to a concrete maintenance action.",
        ]
    )


def format_design_index() -> str:
    lines = ["Design Trace index"]
    for item in DESIGN_INTENTS:
        lines.extend(
            [
                "",
                f"{item.id}: {item.title}",
                f"  intent: {item.intent}",
                f"  rationale: {item.rationale}",
                "  code:",
                *[f"    - {path}" for path in item.code_paths],
                "  docs:",
                *[f"    - {path}" for path in item.docs],
            ]
        )
    return "\n".join(lines)


def format_test_intent_map() -> str:
    lines = ["Test intent map"]
    for item in DESIGN_INTENTS:
        lines.extend(
            [
                "",
                f"{item.id}: {item.intent}",
                "  tests:",
            ]
        )
        if item.test_paths:
            lines.extend(f"    - {path}" for path in item.test_paths)
        else:
            lines.append("    - none recorded")
    return "\n".join(lines)

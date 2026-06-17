# Test Intent Map

Tests are the strongest executable record of design intent. This map explains
which project decisions each test protects.

## DT-RUNTIME-001: Agent Runtime Loop

Intent: the agent is a tool-driven state machine, not a single model call.

Tests:

- `tests/test_tools_runtime.py::test_scheduler_batches_consecutive_safe_tools_only`

## DT-TOOLS-001: Tool Execution Pipeline

Intent: every tool call passes through parse, lookup, schema, permission, run,
and tool_result.

Tests:

- `tests/test_tools_runtime.py::test_executor_returns_tool_result_for_invalid_json`
- `tests/test_tools_runtime.py::test_executor_validates_schema_before_running_tool`
- `tests/test_tools_runtime.py::test_executor_display_includes_runtime_event_layers`
- `tests/test_tools_runtime.py::test_executor_writes_runtime_audit_trace`

## DT-EDIT-001: Read-Before-Write Edit Policy

Intent: existing files must be fully read and snapshotted before Edit or Write
changes them.

Tests:

- `tests/test_tools_runtime.py::test_edit_requires_prior_full_read`
- `tests/test_tools_runtime.py::test_edit_rejects_partial_read_snapshot`
- `tests/test_tools_runtime.py::test_edit_rejects_file_changed_since_read`
- `tests/test_tools_runtime.py::test_write_existing_file_requires_prior_read`
- `tests/test_tools_runtime.py::test_edit_preserves_crlf_line_endings`
- `tests/test_tools_runtime.py::test_write_preserves_existing_crlf_line_endings`

## DT-BASH-001: Explainable Bash Policy

Intent: Bash safety is a conservative classifier with auditable decisions, not a
sandbox claim.

Tests:

- `tests/test_bash_policy.py`
- `tests/test_security_policy_fixtures.py`

## DT-VERIFY-001: Factual Verification State

Intent: verification state records facts about changed files and verification
commands.

Tests:

- `tests/test_verification_policy.py`
- `tests/test_tools_runtime.py::test_edit_records_changed_file_for_verification`
- `tests/test_tools_runtime.py::test_bash_records_verification_command_result`

## DT-AUDIT-001: Replayable Runtime Audit Trace

Intent: sensitive runtime decisions are written as local JSONL audit events.

Tests:

- `tests/test_tools_runtime.py::test_executor_writes_runtime_audit_trace`

## DT-PLANNING-001: Task Planning Gates

Intent: task decomposition centers on IntentModel and PlanContract as explicit
gate artifacts.

Tests:

- `tests/test_task_planning.py`

## DT-MAINTAINABILITY-001: Maintenance Model Before Implementation Slices

Intent: plans must explain how users will understand, maintain, and extend the
result before listing implementation slices.

Tests:

- `tests/test_task_planning.py::test_valid_maintenance_model_passes_gate`
- `tests/test_task_planning.py::test_plan_contract_requires_maintenance_model`
- `tests/test_task_planning.py::test_maintenance_model_formatter_explains_how_to_change_project`

## DT-PLANNING-002: Planning State Blocks Implementation Tools

Intent: plan-task draft and confirmation states must block Edit, Write, and Bash
until explicit execution begins.

Tests:

- `tests/test_plan_task_cli.py::test_plan_task_draft_runs_agent_in_temporary_plan_mode`
- `tests/test_plan_task_cli.py::test_plan_task_lock_records_execution_anchor`
- `tests/test_plan_task_cli.py::test_plan_task_lock_accepts_json_artifact`
- `tests/test_plan_task_cli.py::test_plan_task_lock_rejects_absolute_planned_file`
- `tests/test_plan_task_cli.py::test_plan_task_run_uses_locked_plan_summary`
- `tests/test_plan_task_cli.py::test_plan_task_run_enters_executing_state`
- `tests/test_plan_task_cli.py::test_plan_review_message_uses_model_transition_decision_to_lock_and_run`
- `tests/test_plan_task_cli.py::test_plan_review_message_can_be_cancelled_after_model_confirmation`
- `tests/test_plan_task_cli.py::test_plan_review_message_without_transition_keeps_review_state`
- `tests/test_plan_task_cli.py::test_session_load_saves_current_and_switches_context`
- `tests/test_plan_task_cli.py::test_session_current_reports_active_context`
- `tests/test_tools_runtime.py::test_executor_blocks_write_when_plan_task_is_not_executing`
- `tests/test_tools_runtime.py::test_executor_allows_write_when_plan_task_is_executing`

## DT-MEMORY-001: Layered Memory and Recoverable Context

Intent: memory should distinguish audit transcript, current context, executable
runtime state, project memory, and design trace.

Tests:

- `tests/test_plan_task_cli.py::test_transcript_store_load_prefers_compacted_message_snapshot`
- `tests/test_plan_task_cli.py::test_plan_review_confirmation_uses_saved_plan_artifact_candidate`
- `tests/test_plan_task_cli.py::test_session_load_saves_current_and_switches_context`

## DT-MAINTENANCE-DIGEST-001: User-Facing Engineering Mental Model

Intent: each reviewed plan should produce a compact, recoverable mental model
for the user.

Tests:

- `tests/test_task_planning.py::test_valid_maintenance_digest_passes_gate`
- `tests/test_task_planning.py::test_maintenance_digest_requires_user_mental_model_fields`
- `tests/test_task_planning.py::test_plan_contract_requires_maintenance_digest_candidate`
- `tests/test_plan_task_cli.py::test_mental_model_displays_current_digest`
- `tests/test_plan_task_cli.py::test_plan_task_lock_accepts_lightweight_execution_contract`

# ADR 0002: Tool Execution Pipeline

Status: accepted

## Context

Local tools are powerful enough to read files, edit files, and run shell
commands. A failed tool call must be handled as part of the agent conversation,
not only as terminal output.

## Decision

Every tool call goes through one explicit pipeline:

```text
parse arguments
  -> lookup tool
  -> validate schema
  -> decide permission
  -> run tool
  -> build tool_result
```

Any failure in the pipeline returns a `tool_result` message to the model.

## Alternatives

- Let each tool parse and validate its own raw model input.
- Raise local exceptions and stop the agent turn.
- Print failures only in the CLI and hide them from the model.

## Consequences

- The model can recover from invalid JSON, schema errors, unknown tools, and
  permission denials.
- The executor becomes a stable boundary for audit events and future Rust
  migration.
- The executor must stay small; unrelated policy should move into dedicated
  policy modules.

## Verification

- `tests/test_tools_runtime.py::test_executor_returns_tool_result_for_invalid_json`
- `tests/test_tools_runtime.py::test_executor_validates_schema_before_running_tool`
- `tests/test_tools_runtime.py::test_executor_display_includes_runtime_event_layers`
- `tests/test_tools_runtime.py::test_executor_writes_runtime_audit_trace`

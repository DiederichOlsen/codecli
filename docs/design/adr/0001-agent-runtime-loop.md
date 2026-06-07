# ADR 0001: Agent Runtime Loop

Status: accepted

## Context

PyAgent needs to support coding tasks that cannot be answered by one model call.
The model may need to inspect files, run tools, receive tool results, revise its
plan, and verify changes.

## Decision

Use an explicit agent loop:

```text
user input
  -> model response
  -> assistant message
  -> tool calls
  -> tool results
  -> next model response
  -> final answer
```

`Agent` owns session-level orchestration. Tool execution, permission decisions,
and scheduling stay behind separate runtime boundaries.

## Alternatives

- Single chat completion per user input.
- A large monolithic engine that owns model calls, permissions, tools, and UI.
- A fully distributed task runner from the start.

## Consequences

- The runtime can recover from tool failures because failures become messages.
- Context compaction and transcript persistence have a clear owner.
- The loop is easy to inspect and test, but long tasks need turn limits and
  careful final-answer behavior.

## Verification

- `tests/test_tools_runtime.py::test_scheduler_batches_consecutive_safe_tools_only`
- `docs/architecture.md`

# Memory Policy

PyAgent uses layered memory instead of one general-purpose memory bucket. Each
layer has a different authority and recovery role.

## Layers

### Project Memory

Source:

- `CLAUDE.md`
- `AGENTS.md`
- `.pyagent/memory.md`

Use: long-lived project instructions and user-authored operating rules.

Prompt role: loaded into the system prompt at session start.

Authority: advisory. It should guide behavior, but runtime gates still decide
whether tools may execute.

### Transcript

Source:

- `.pyagent/sessions/<session-id>.jsonl`

Use: append-only conversation audit log.

Prompt role: used for recovery when no compacted message snapshot exists.

Authority: historical. It records what happened, but it is not the canonical
runtime state.

### Compacted Message Snapshot

Source:

- `.pyagent/sessions/<session-id>.messages.json`

Use: current model context after compaction.

Prompt role: preferred over replaying the full transcript during session load.

Authority: current conversational context. It keeps resume behavior aligned with
the compacted in-memory context.

### Runtime State Snapshot

Source:

- `.pyagent/sessions/<session-id>.state.json`

Use: current executable state.

Stores:

- `planning_status`
- `planning_request`
- `plan_artifact_candidate`
- `locked_plan`
- `current_goal`
- `current_plan_summary`
- `current_step`
- `current_slice_id`
- `planned_files`
- `deviations`
- verification records

Prompt role: selectively injected through task prompts and status displays.

Authority: operational. Tool gates and execution policy use this state.

### Design Trace

Source:

- `docs/design/*`
- `pyagent/design_trace.py`

Use: long-lived engineering intent, ADRs, test intent maps, and maintenance
guidance.

Prompt role: exposed through `/design` and `/intent`, and partly reflected in
the system prompt.

Authority: design rationale. It explains why mechanisms exist and which tests
protect them.

## Rules

- Do not treat transcript text as executable state.
- Prefer structured state for execution anchors.
- Keep compacted context recoverable across `/session load` and `--resume`.
- Keep the raw transcript append-only for auditability.
- Store the latest `PlanArtifactCandidate` in state so confirmation does not
depend on searching old assistant text.
- Use Design Trace for stable engineering intent, not volatile task details.

## Current Tradeoffs

The full `PlanContract` and `MaintenanceModel` are still primarily transcript
artifacts. The runtime persists a lightweight `PlanArtifactCandidate` and locked
`PlanArtifact` with plan identity, revision, source message, confirmation time,
non-goals, constraints, slices, and verification checks. This is enough to
recover the execution contract after compaction without turning the full plan
into session state. A future `PlanStore` can make full plan versions first-class
without overloading session state.

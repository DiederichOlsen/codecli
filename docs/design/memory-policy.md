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

- `state_schema_version`
- `state_revision`
- `compact_epoch`
- `last_source_message_id`
- `context_boundaries`
- `planning_status`
- `planning_request`
- `plan_artifact_candidate`
- `maintenance_digest_candidate`
- `maintenance_digest`
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

### PlanStore Snapshot

Source:

- `.pyagent/plans/<plan-id>.json`
- `.pyagent/plans/<plan-id>.md`

Use: user-visible plan export and lightweight plan version anchor.

Stores:

- plan id and revision;
- session id and saved timestamp;
- locked or candidate `PlanArtifact`;
- current `MaintenanceDigest`, when available;
- Markdown view path.

Prompt role: not automatically replayed into every model call. The runtime
state remains the current execution authority; PlanStore makes the reviewed plan
and mental model easier for users to inspect, diff, and hand off.

Authority: documentary and versioning. It is not a tool permission rule or file
allowlist.

### Context Boundary

Source:

- `AgentState.context_boundaries`
- system messages with `subtype=context_boundary`

Use: records each local compaction as a recoverable boundary.

Stores:

- boundary id and compact epoch;
- pre/post compact message counts;
- preserved recent message ids;
- summary message id;
- active plan id/revision;
- active digest id/revision;
- planning status.

Prompt role: the compacted model context gets a short boundary notice plus the
current `PlanArtifact` and `MaintenanceDigest` re-injected as authoritative
runtime state.

Authority: recovery metadata. It explains what survived compaction; it is not a
tool permission rule or file allowlist.

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

The full `PlanContract` is still primarily a transcript artifact. A full
`MaintenanceModel` may be produced for broad or architectural tasks, but it is no
longer required for every task. The runtime persists a lightweight
`PlanArtifactCandidate` and locked
`PlanArtifact` with plan identity, revision, source message, confirmation time,
non-goals, constraints, slices, and verification checks. This is enough to
recover the execution contract after compaction without turning the full plan
into session state.

The runtime also persists a lightweight `MaintenanceDigestCandidate` and locked
`MaintenanceDigest`. The digest is the current user-facing engineering mental
model for the session: module map, change paths, extension points, invariants,
test intent map, and handoff notes. It is authoritative for understanding and
handoff, not for tool permission or file allowlisting.

The lightweight `PlanStore` now makes exported plan snapshots first-class
without overloading session state. A future iteration can add richer version
history, source-message indexing, or spec-style file trees on top of the same
boundary.

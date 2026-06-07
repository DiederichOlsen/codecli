# Design Trace

Design Trace is PyAgent's lightweight record of why the project is shaped the
way it is. The goal is not to generate more documentation. The goal is to keep
design intent close to code, tests, and user-facing maintenance guidance.

PyAgent treats design intent as a runtime concern:

- recommendations need evidence, alternatives, tradeoffs, and failure modes;
- important design decisions are recorded as ADRs;
- tests are mapped to the design intent they protect;
- the CLI exposes the current trace with `/design` and `/intent`.

## Files

- `intent-ledger.md` records current design intents and their code owners.
- `recommendation-protocol.md` defines what counts as a useful engineering
  recommendation.
- `task-planning-state-machine.md` defines the IntentModel and PlanContract
  gates used before execution.
- `test-intent-map.md` maps tests to the design intent they preserve.
- `adr/` records durable architecture decisions.
- `diagrams/` contains source diagrams that can be rendered by Mermaid.

## Maintenance Rule

When a change introduces a new runtime boundary, policy, or irreversible
architecture choice, add or update one of these:

- a design intent entry;
- an ADR;
- a test-intent mapping;
- a diagram if structure or flow changed.

If the change only edits implementation details behind an existing intent, keep
the docs stable and update tests instead.

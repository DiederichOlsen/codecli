# Task Planning State Machine

PyAgent's task planning model is LLM-driven but runtime-gated. The model may
draft intent and plans, but progression into execution should depend on explicit
artifacts that can be inspected, validated, and revised by the user.

V0 focuses on two gate artifacts and one fallback artifact:

```text
RawTask
  -> IntentModel
  -> PlanOptions if IntentModel is blocked
  -> PlanContract if IntentModel is accepted
  -> MaintenanceModel
  -> LockedPlan
  -> Execution
  -> Handoff
```

`Execution` and `Handoff` are not implemented as first-class state objects yet.
The current work defines the data contracts and gate checks for the two states
that matter most before code changes begin.

## CLI Draft Mode

Interactive sessions support:

```text
/plan-task draft <request>
/plan-task lock [summary-or-json]
/plan-task run
/plan-task clear
/session load <session-id>
```

This command asks the model to draft an `IntentModel` and `PlanContract` for the
request. It temporarily runs the agent in `plan` permission mode, so the model
may inspect files with read/search tools but cannot apply edits.

The command is intentionally not an execution command. Its purpose is to make
the planning artifacts visible enough for human review:

- Does the intent match what the user meant?
- Are non-goals and scope boundaries clear?
- Is the selected approach backed by project evidence?
- Are implementation slices reviewable?
- Do tests or docs protect the design intent?

Draft mode does not execute. `/plan-task lock` records the reviewed plan as a
small `PlanArtifact` execution anchor. `/plan-task run` is the separate command
that enters execution mode after the user has reviewed and optionally locked the
plan.

`/plan-task draft` is now backed by runtime state, not only prompt text. Drafting
sets `AgentState.planning_status` to `drafting` and then `needs_confirmation`.
While the status is `drafting`, `blocked`, `needs_confirmation`, or `locked`, the
tool executor blocks `Edit`, `Write`, and `Bash`. This prevents a normal followup
such as "yes" from accidentally starting implementation in a draft session.

`/plan-task lock` accepts either a short human summary or a compact JSON object
with `goal`, `summary`, `planned_files`, and `current_step`. Slash commands are
kept as explicit/debuggable controls, but they are not the only interaction
path.

In normal conversation, when the planning state is `needs_confirmation`, the
user can respond in natural language. The runtime asks the LLM to interpret that
message in plan-review context. If the LLM judges that the user is confirming
execution, it must output a structured `PlanTransitionDecision`; the local
runtime then asks for a final `y/N` confirmation before locking and running.

This is still not a full natural-language parser. The LLM may propose a
`PlanArtifactCandidate` or transition decision, but the runtime validates and
stores only the small structured artifact.

`/plan-task run` is the explicit transition into `executing`. Only then may the
agent use implementation tools for the confirmed plan. If a locked artifact
exists, run mode uses that artifact instead of the raw user request as the goal
anchor.

When execution starts, PyAgent creates a goal anchor on `AgentState`:

```text
current_goal
current_plan_summary
current_step
current_slice_id
planned_files
deviations[]
locked_plan
```

Implementation tools in `executing` require `current_goal`. If a write targets a
file outside `planned_files`, the runtime records a deviation instead of
blocking it. This keeps implementation flexible while making plan drift visible.

Draft mode has one important branch rule:

- If `IntentModel` is blocked, the model must not draft a full `PlanContract`.
- It should output `PlanOptions` instead: conditional choices with
  `when_to_choose`, `evidence_needed`, `tradeoffs`, and only the first slice.
- A full `PlanContract` is allowed only after the intent gate is acceptable.
- A full `PlanContract` must include `MaintenanceModel` before implementation
  slices.

This prevents the agent from filling in detailed implementation slices while
the core intent, technology choice, or project scope is still unresolved.

## IntentModel

`IntentModel` translates the user's request into an engineering intent.

It must record:

- the raw user request;
- the concrete goal;
- the user value;
- non-goals and scope boundaries;
- domain concepts and workflows;
- constraints and assumptions;
- open questions and blocking questions;
- evidence;
- confidence.

Gate rule: a plan cannot be formed while the intent has low confidence,
unresolved blocking questions, missing scope boundaries, missing assumptions, or
missing evidence.

This prevents the agent from planning a solution before it knows what problem it
is solving.

## PlanContract

`PlanContract` is the agreement the agent intends to execute.

It must record:

- selected approach and rationale;
- project evidence;
- alternatives considered;
- affected and new files;
- design intents, docs, or ADR/RFC updates;
- reviewable implementation slices;
- tests or an explicit no-test rationale;
- compatibility notes;
- rollback plan;
- risks, risk level, and whether user confirmation is required.

Gate rule: a contract is not review-ready if the plan has no implementation
slices, no file scope, no evidence, no tests or no-test rationale, missing docs
for design intent changes, or high risk without user confirmation.

It also cannot pass without a `MaintenanceModel`. File lists and slices explain
how to build the result, but not how the user should understand and maintain it.

## PlanArtifact

`PlanArtifact` is the small runtime form of a reviewed plan. It intentionally
does not duplicate the full `PlanContract`.

It records:

- goal;
- summary;
- plan id, revision, source message id, creation time, and confirmation time;
- non-goals and constraints that should survive context compaction;
- planned files;
- lightweight slices with id, purpose, files, and check;
- optional current slice id;
- current step as free text;
- verification commands or checks.

Gate rule: a locked artifact must have a goal and summary, and planned files
must be workspace-relative paths without parent-directory traversal. This keeps
LLM output useful without letting free-form text become executable state.

`PlanArtifact` is an execution contract, not a hard file allowlist. It gives the
runtime enough identity, source, and boundary information to recover after
compaction or resume. It does not block every out-of-plan edit; those are handled
by deviation records so execution can stay flexible.

The locked artifact is persisted in a session state sidecar:

```text
.pyagent/sessions/<session-id>.state.json
```

The transcript remains the conversation log. The state sidecar stores runtime
state such as `planning_status`, `planning_request`, `locked_plan`,
`current_goal`, `current_slice_id`, `planned_files`, `deviations`, and
verification records. On resume, PyAgent loads both the transcript and this
state snapshot.

Interactive sessions can also switch context without restarting:

```text
/sessions
/session current
/session save
/session load <session-id>
```

`/session load` saves the current session state first, then loads the target
session transcript and state sidecar. This makes context selection explicit and
lets the user manage separate planning/execution threads by session id.

## MaintenanceModel

`MaintenanceModel` explains the project from the future maintainer's point of
view. It must appear before implementation slices so the plan's structure is
driven by maintainability, not merely by implementation order.

It records:

- mental model: the simplest explanation of how the project works;
- module responsibilities: what each core module owns and does not own;
- change scenarios: where to start for common future changes;
- extension points: where new features are meant to attach;
- invariants: rules that should not be broken;
- dependency rules: which modules may depend on which other modules;
- complexity budget: abstractions intentionally not introduced yet;
- test intent map: which checks protect which design intent;
- handoff map: where the user should go to change common behavior.

Gate rule: a plan cannot pass if the maintenance model has no mental model, no
module responsibilities, fewer than three change scenarios, fewer than two
extension points, no invariants, no dependency rules, no test intent map, or no
handoff map.

This shifts `/plan-task draft` from "implementation plan generator" toward
"maintainable project co-design." The user should see not only what files will
exist, but why those boundaries exist and how to modify them later.

## Behavior Principles

The planning and execution flow is meant to turn engineering habits into runtime
infrastructure:

- Think before coding: no implementation tools before the planning state allows
  execution.
- Simplicity first: plans should include a complexity budget and avoid larger
  abstractions until the current goal needs them.
- Surgical changes: execution should operate one slice at a time and avoid
  changes outside the current slice.
- Goal-driven execution: each slice needs an expected change and a check that
  demonstrates progress toward the confirmed goal.

Current runtime enforcement is strongest for the first principle: draft and
locked planning states block write and shell tools.

Goal-driven execution has a hard anchor: executing plan-task runs must have a
`current_goal`, and tool audit events include the current goal and step.

Surgical changes use a soft deviation protocol: out-of-plan writes are allowed
but recorded as deviations. This avoids making slices brittle while preserving a
reviewable trail.

Deviation records include the active plan id, plan revision, and current slice id
when available. These fields are audit anchors, not execution blockers.

Simplicity first is currently enforced through required `complexity_budget`
entries in `MaintenanceModel` and a `ComplexityReview` shape for future checks.
It is intentionally not a hard file-count rule because some simple solutions
still need several files.

## PlanOptions

`PlanOptions` are used when the intent is not stable enough for a contract.

They must not pretend to be a full plan. Each option records:

- name;
- when to choose it;
- evidence still needed;
- tradeoffs;
- first slice only.

This keeps recommendations evidence-driven. For example, a game project should
not default to a specific engine before the user confirms target platform,
workflow preference, and prototype scope.

## User Intervention

The user should be able to revise both artifacts:

- at the IntentModel gate: goal, non-goals, scope, vocabulary, constraints;
- at the PlanContract gate: approach, file structure, slice order, tests, docs,
  and confirmation requirements.

This is the mechanism that makes the resulting project familiar through shared
understanding, not through style imitation.

For execution confirmation, the user should not need to know internal slash
commands. A phrase such as "use this plan and start" is interpreted by the LLM in
review context, then converted into a structured transition request. The local
state machine remains the authority: it validates the artifact, asks `y/N`, and
only then moves from `needs_confirmation` to `locked` and `executing`.

## Current Code

- `pyagent/task_contracts.py`
- `pyagent/task_policies.py`
- `pyagent/task_prompts.py`
- `pyagent/task_formatters.py`
- `pyagent/task_planning.py` compatibility facade
- `pyagent/storage.py`
- `tests/test_task_planning.py`

Future work can add structured plan parsing, current-slice tracking, and
slice-level file allowlists once draft output has been reviewed on real tasks.

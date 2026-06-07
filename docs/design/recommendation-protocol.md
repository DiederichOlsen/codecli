# Recommendation Protocol

PyAgent should not give naked recommendations. A recommendation is naked when it
states a preferred direction without enough project evidence, alternatives,
tradeoffs, and ways to know when the advice has become wrong.

## Required Shape

For non-trivial engineering recommendations, include:

- Decision: the concrete recommendation.
- Evidence: observed facts from the current project.
- Alternatives: at least two plausible options.
- Tradeoffs: what the recommendation gives up.
- Failure modes: when the recommendation can become harmful.
- Re-evaluation triggers: facts that should make the team revisit the decision.
- Verification: tests, docs, or checks that can confirm the choice is working.

If evidence is missing, label the output as an assumption instead of presenting
it as a recommendation.

## Invalid

```text
Use a modular design because it will be more maintainable.
```

This is too vague. It does not say which modules, what project facts justify
them, what alternatives were rejected, or how maintainability will be checked.

## Valid

```text
Decision:
Keep ToolExecutor separate from Agent.

Evidence:
- Agent already owns session-level orchestration.
- ToolExecutor already has tests for invalid JSON, schema failures, permission
  decisions, audit trace, and tool_result construction.
- docs/architecture.md identifies the executor pipeline as a Rust migration
  boundary.

Alternatives:
- Inline tool execution into Agent.
- Split each pipeline stage into separate services.

Tradeoffs:
- The current boundary adds one more object to construct.
- It keeps the central runtime loop smaller and easier to reason about.

Failure modes:
- If executor policy grows unrelated responsibilities, the boundary becomes a
  dumping ground.

Re-evaluation triggers:
- More than one caller needs only part of the pipeline.
- Tool execution needs independent lifecycle or background processing.

Verification:
- tests/test_tools_runtime.py keeps tool failure behavior replayable.
```

## Prompt Rule

The system prompt imports the same protocol through
`pyagent.design_trace.recommendation_protocol_prompt()`. The CLI-facing docs and
the model-facing prompt should stay aligned.

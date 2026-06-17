from __future__ import annotations


def build_plan_task_draft_prompt(raw_request: str) -> str:
    request = raw_request.strip()
    return "\n".join(
        [
            "Draft a task plan. Do not implement the task yet.",
            "",
            "Runtime constraint:",
            "- You may inspect the project with read-only tools.",
            "- Do not call Edit or Write.",
            "- Use Read, Glob, and Grep for inspection.",
            "- Do not call Bash in draft mode.",
            "- If evidence is missing, say what must be inspected instead of guessing.",
            "",
            "User request:",
            request,
            "",
            "Produce these sections in order:",
            "",
            "1. IntentModel draft",
            "- task_id: a short stable id",
            "- raw_request",
            "- task_type",
            "- goal",
            "- user_value",
            "- non_goals",
            "- scope_boundaries",
            "- domain_concepts",
            "- workflows",
            "- constraints",
            "- assumptions",
            "- open_questions",
            "- blocking_questions",
            "- evidence",
            "- confidence: low | medium | high",
            "",
            "2. IntentModel gate",
            "- Say gate: ok only if the goal, scope boundaries, non-goals, assumptions, evidence, "
            "and confidence are strong enough and there are no blocking questions.",
            "- Otherwise say gate: blocked and list the fields that need user input or more inspection.",
            "",
            "3. Planning branch",
            "- If IntentModel gate is blocked, do not draft a full PlanContract.",
            "- If IntentModel gate is blocked, output PlanOptions instead:",
            "  - at least two conditional options",
            "  - when_to_choose",
            "  - evidence_needed",
            "  - tradeoffs",
            "  - first_slice only, not a full implementation breakdown",
            "- If IntentModel gate is ok, output PlanContract draft:",
            "  - selected_approach",
            "  - rationale with project evidence",
            "  - alternatives_considered",
            "  - affected_files",
            "  - new_files",
            "  - design_intents",
            "  - MaintenanceDigestCandidate before implementation_slices:",
            "    - mental_model",
            "    - module_map: module, responsibility",
            "    - change_paths: scenario, start_at, notes",
            "    - extension_points",
            "    - invariants",
            "    - test_intent_map",
            "    - handoff_notes",
            "  - Optional MaintenanceModel for broad or architectural tasks:",
            "    - mental_model",
            "    - module_responsibilities: module, owns, does_not_own, depends_on",
            "    - change_scenarios: scenario, start_at, likely_files, notes",
            "    - extension_points",
            "    - invariants",
            "    - dependency_rules",
            "    - complexity_budget",
            "    - test_intent_map",
            "    - handoff_map",
            "  - implementation_slices, each with id, purpose, files, expected_change, and check",
            "  - tests or no_tests_rationale",
            "  - docs",
            "  - migration_or_compatibility_notes",
            "  - rollback_plan",
            "  - risks",
            "  - risk_level: low | medium | high",
            "  - user_confirmation_required",
            "",
            "4. Plan gate",
            "- If you output PlanOptions, say PlanContract gate: not reached because IntentModel is blocked.",
            "- Say gate: ok only if the plan has evidence, file scope, MaintenanceDigestCandidate, reviewable slices, checks, "
            "tests or a no-test rationale, docs for design-intent changes, rollback notes, and confirmation for high risk.",
            "- Otherwise say gate: blocked and list missing fields.",
            "",
            "5. MaintenanceDigest candidate",
            "- Only if PlanContract gate is ok, output a compact JSON object named MaintenanceDigestCandidate.",
            "- If you produced a full MaintenanceModel, compress it. Otherwise derive the digest directly from inspected project evidence.",
            "- This is for the user, not for tool execution. It should help them understand, maintain, and extend the project.",
            "- Include: mental_model, module_map, change_paths, extension_points, invariants, test_intent_map, handoff_notes.",
            "- module_map items: module, responsibility.",
            "- change_paths items: scenario, start_at, notes.",
            "- test_intent_map items: intent, checks.",
            "- DigestGate is ok only if mental_model is non-empty, module_map has at least one item, change_paths has at least two items, "
            "extension_points has at least one item, invariants has at least one item, and handoff_notes has at least one item.",
            "- If DigestGate is blocked, say PlanArtifactCandidate: not produced.",
            "",
            "6. PlanArtifact candidate",
            "- Only if PlanContract gate is ok, output a compact JSON object named PlanArtifactCandidate.",
            "- Include: goal, summary, planned_files, current_step.",
            "- Embed the digest JSON as maintenance_digest when DigestGate is ok.",
            "- Also include lightweight execution-contract fields when available:",
            "  - non_goals",
            "  - constraints",
            "  - slices: id, purpose, files, check",
            "  - current_slice_id",
            "  - verification",
            "- planned_files must be workspace-relative paths from affected_files and new_files.",
            "- If PlanContract gate is blocked, say PlanArtifactCandidate: not produced.",
            "- Minimal valid shape:",
            "```json",
            (
                '{"goal":"...","summary":"...","planned_files":["pyagent/example.py"],'
                '"current_step":"...","maintenance_digest":{"mental_model":"...",'
                '"module_map":[{"module":"pyagent/example.py","responsibility":"..."}],'
                '"change_paths":[{"scenario":"...","start_at":"pyagent/example.py","notes":"..."},'
                '{"scenario":"...","start_at":"tests/test_example.py","notes":"..."}],'
                '"extension_points":["..."],"invariants":["..."],'
                '"test_intent_map":[{"intent":"...","checks":["..."]}],'
                '"handoff_notes":["..."]}}'
            ),
            "```",
            "",
            "7. Human review questions",
            "- Ask only the questions whose answers would materially change the intent or plan.",
        ]
    )


def build_plan_task_run_prompt(raw_request: str) -> str:
    request = raw_request.strip() or "the locked plan in the current conversation"
    return "\n".join(
        [
            "Execute the current plan in small, goal-driven slices.",
            "",
            "Execution principles:",
            "- Think before coding: restate the current slice goal before changing files.",
            "- Simplicity first: choose the smallest design that satisfies the confirmed plan.",
            "- Surgical changes: only edit files needed for the current slice.",
            "- Goal-driven execution: each tool call should move the confirmed goal or current slice forward.",
            "- If implementation would exceed the locked plan, stop and ask to replan.",
            "- After each slice, run or describe the relevant check before moving on.",
            "",
            "Current request or locked plan:",
            request,
        ]
    )


def build_plan_review_transition_prompt(user_message: str) -> str:
    message = user_message.strip()
    return "\n".join(
        [
            "The current task is in plan review state. Interpret the user's latest message before any implementation.",
            "",
            "Rules:",
            "- Do not implement yet.",
            "- Do not call Edit, Write, or Bash.",
            "- If the user is answering review questions, revising scope, asking questions, or changing requirements, update the plan text only.",
            "- If the user explicitly confirms the reviewed plan and asks to start, output a PlanTransitionDecision JSON object.",
            "- The runtime, not you, will lock the plan and start execution after a y/N confirmation.",
            "",
            "PlanTransitionDecision schema:",
            "```json",
            (
                '{"action":"confirm_execution","artifact":{"goal":"","summary":"","planned_files":[],'
                '"non_goals":[],"constraints":[],"slices":[],"current_slice_id":"","current_step":"",'
                '"verification":[],"maintenance_digest":{"mental_model":"","module_map":[],"change_paths":[],'
                '"extension_points":[],"invariants":[],"test_intent_map":[],"handoff_notes":[]}}}'
            ),
            "```",
            "",
            "If the message is not an execution confirmation, do not output PlanTransitionDecision.",
            "",
            "User message:",
            message,
        ]
    )

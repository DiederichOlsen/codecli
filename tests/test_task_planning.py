from __future__ import annotations

import unittest

from pyagent.task_planning import (
    ComplexityReview,
    DigestChangePath,
    DigestModule,
    DigestTestIntent,
    ImplementationSlice,
    IntentModel,
    ChangeScenario,
    MaintenanceModel,
    MaintenanceDigest,
    ModuleResponsibility,
    PlanArtifact,
    PlanArtifactSlice,
    PlanAlternative,
    PlanContract,
    PlanOption,
    TestIntentMapping,
    build_plan_artifact,
    build_maintenance_digest,
    build_goal_anchor,
    build_plan_review_transition_prompt,
    build_plan_task_draft_prompt,
    build_plan_task_run_prompt,
    format_plan_artifact,
    format_gate_result,
    format_intent_model,
    format_maintenance_model,
    format_maintenance_digest,
    format_plan_contract,
    format_plan_options,
    lock_plan_artifact,
    validate_complexity_review,
    validate_maintenance_model,
    validate_maintenance_digest,
    validate_intent_model,
    validate_plan_artifact,
    validate_plan_contract,
    validate_plan_options,
)


def valid_intent_model(**overrides: object) -> IntentModel:
    data = {
        "task_id": "task-1",
        "raw_request": "Add a task decomposition state machine.",
        "task_type": "feature",
        "goal": "Represent task decomposition as explicit planning artifacts.",
        "user_value": "The user can inspect and maintain the plan before execution.",
        "non_goals": ("Do not implement full automatic execution yet.",),
        "scope_boundaries": ("Planning data lives in pyagent/task_planning.py.",),
        "domain_concepts": ("IntentModel", "PlanContract"),
        "workflows": ("Draft intent, validate gate, draft plan, validate gate.",),
        "constraints": ("Use plain dataclasses and standard library only.",),
        "assumptions": ("The first version is model-free and testable.",),
        "open_questions": (),
        "blocking_questions": (),
        "evidence": ("User prioritized IntentModel and PlanContract.",),
        "confidence": "medium",
    }
    data.update(overrides)
    return IntentModel(**data)


def valid_maintenance_model(**overrides: object) -> MaintenanceModel:
    data = {
        "mental_model": "Input updates entities, entities query world collision, rendering uses camera offsets.",
        "module_responsibilities": (
            ModuleResponsibility(
                module="world/tilemap.py",
                owns=("Tile data", "solid tile lookup", "map rendering"),
                does_not_own=("player combat", "enemy AI"),
                depends_on=("settings.py", "pixel_art.py"),
            ),
            ModuleResponsibility(
                module="sprites/player.py",
                owns=("player movement", "player combat state"),
                does_not_own=("map generation", "HUD rendering"),
                depends_on=("utils/collision.py", "settings.py"),
            ),
        ),
        "change_scenarios": (
            ChangeScenario(
                scenario="Add a new enemy type.",
                start_at="sprites/enemy.py",
                likely_files=("sprites/enemy.py", "pixel_art.py", "world/tilemap.py"),
                notes="Add behavior without changing player input handling.",
            ),
            ChangeScenario(
                scenario="Add a new chest reward.",
                start_at="sprites/chest.py",
                likely_files=("sprites/chest.py", "sprites/hud.py"),
                notes="Keep scoring rules out of tilemap rendering.",
            ),
            ChangeScenario(
                scenario="Change map size.",
                start_at="settings.py",
                likely_files=("settings.py", "world/tilemap.py", "world/camera.py"),
                notes="Camera clamp and tile data must stay consistent.",
            ),
        ),
        "extension_points": (
            "Add new sprite color grids in pixel_art.py.",
            "Add new entity classes under sprites/.",
        ),
        "invariants": (
            "World rendering must not mutate game state.",
            "Camera offset affects drawing, not entity world positions.",
        ),
        "dependency_rules": (
            "sprites may query world collision APIs; world modules must not import player.",
            "HUD reads game state but does not change combat state.",
        ),
        "complexity_budget": (
            "Do not introduce ECS for the first prototype.",
            "Do not add an external asset pipeline until generated sprites become limiting.",
        ),
        "test_intent_map": (
            TestIntentMapping(
                intent="Collision keeps entities out of solid tiles.",
                checks=("unit test utils/collision.py", "manual wall movement check"),
            ),
            TestIntentMapping(
                intent="Camera follows player without changing world positions.",
                checks=("unit test camera clamp", "manual movement check"),
            ),
        ),
        "handoff_map": (
            "To tune gameplay numbers, start in settings.py.",
            "To add enemies, start in sprites/enemy.py and pixel_art.py.",
            "To change map layout, start in world/tilemap.py.",
        ),
    }
    data.update(overrides)
    return MaintenanceModel(**data)


def valid_maintenance_digest(**overrides: object) -> MaintenanceDigest:
    data = {
        "mental_model": "PyAgent is a CLI runtime with explicit planning, tool, and memory policies.",
        "module_map": (
            DigestModule(
                module="pyagent/task_contracts.py",
                responsibility="Defines planning and maintenance data contracts.",
            ),
        ),
        "change_paths": (
            DigestChangePath(
                scenario="Change planning gates.",
                start_at="pyagent/task_policies.py",
                notes="Update validators and matching tests together.",
            ),
            DigestChangePath(
                scenario="Change CLI planning commands.",
                start_at="pyagent/cli.py",
                notes="Keep storage and plan-task tests aligned.",
            ),
        ),
        "extension_points": ("Add new planning artifacts in task_contracts.py.",),
        "invariants": ("Runtime state must stay JSON-compatible.",),
        "test_intent_map": (
            DigestTestIntent(
                intent="Planning artifacts remain recoverable after resume.",
                checks=("tests/test_plan_task_cli.py",),
            ),
        ),
        "handoff_notes": ("Start with /mental-model to understand current module boundaries.",),
    }
    data.update(overrides)
    return MaintenanceDigest(**data)


def valid_plan_contract(**overrides: object) -> PlanContract:
    data = {
        "task_id": "task-1",
        "selected_approach": "Add a small planning policy module.",
        "rationale": "The project already favors plain-data policy modules with tests.",
        "evidence": ("docs/architecture.md calls for explicit policy modules.",),
        "alternatives_considered": (
            PlanAlternative(
                name="Prompt-only",
                summary="Only add planning instructions to the system prompt.",
                tradeoffs=("Fast but not testable.",),
            ),
        ),
        "affected_files": ("pyagent/design_trace.py",),
        "new_files": ("pyagent/task_planning.py", "tests/test_task_planning.py"),
        "design_intents": ("DT-PLANNING-001",),
        "implementation_slices": (
            ImplementationSlice(
                id="slice-1",
                purpose="Add planning data structures and gates.",
                files=("pyagent/task_planning.py",),
                expected_change="Introduce IntentModel and PlanContract validation.",
                check="python -m unittest tests.test_task_planning",
                design_intent_id="DT-PLANNING-001",
            ),
        ),
        "tests": ("tests/test_task_planning.py",),
        "docs": ("docs/design/task-planning-state-machine.md",),
        "no_tests_rationale": "",
        "migration_or_compatibility_notes": ("No transcript format change in V0.",),
        "rollback_plan": "Remove the new module, tests, and design intent entry.",
        "risks": ("The model may still skip the flow until CLI integration exists.",),
        "risk_level": "medium",
        "user_confirmation_required": False,
        "maintenance_model": valid_maintenance_model(),
        "maintenance_digest": valid_maintenance_digest(),
    }
    data.update(overrides)
    return PlanContract(**data)


class TaskPlanningTests(unittest.TestCase):
    def test_valid_intent_model_passes_gate(self) -> None:
        result = validate_intent_model(valid_intent_model())

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())

    def test_intent_model_blocks_low_confidence_and_open_blockers(self) -> None:
        result = validate_intent_model(
            valid_intent_model(
                confidence="low",
                blocking_questions=("Does this require persistent task state?",),
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertFalse(result.ok)
        self.assertIn("confidence", fields)
        self.assertIn("blocking_questions", fields)

    def test_intent_model_requires_scope_non_goals_assumptions_and_evidence(self) -> None:
        result = validate_intent_model(
            valid_intent_model(
                non_goals=(),
                scope_boundaries=(),
                assumptions=(),
                evidence=(),
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertIn("non_goals", fields)
        self.assertIn("scope_boundaries", fields)
        self.assertIn("assumptions", fields)
        self.assertIn("evidence", fields)

    def test_valid_plan_contract_passes_gate(self) -> None:
        result = validate_plan_contract(valid_plan_contract())

        self.assertTrue(result.ok)

    def test_valid_maintenance_model_passes_gate(self) -> None:
        result = validate_maintenance_model(valid_maintenance_model())

        self.assertTrue(result.ok)

    def test_valid_maintenance_digest_passes_gate(self) -> None:
        result = validate_maintenance_digest(valid_maintenance_digest())

        self.assertTrue(result.ok)

    def test_maintenance_digest_requires_user_mental_model_fields(self) -> None:
        result = validate_maintenance_digest(
            valid_maintenance_digest(
                mental_model="",
                module_map=(),
                change_paths=(
                    DigestChangePath(
                        scenario="Change planning gates.",
                        start_at="pyagent/task_policies.py",
                    ),
                ),
                extension_points=(),
                invariants=(),
                handoff_notes=(),
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertIn("mental_model", fields)
        self.assertIn("module_map", fields)
        self.assertIn("change_paths", fields)
        self.assertIn("extension_points", fields)
        self.assertIn("invariants", fields)
        self.assertIn("handoff_notes", fields)

    def test_maintenance_model_requires_handoff_and_change_scenarios(self) -> None:
        result = validate_maintenance_model(
            valid_maintenance_model(
                mental_model="",
                change_scenarios=(),
                extension_points=("Only one extension point.",),
                handoff_map=(),
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertIn("mental_model", fields)
        self.assertIn("change_scenarios", fields)
        self.assertIn("extension_points", fields)
        self.assertIn("handoff_map", fields)

    def test_plan_contract_allows_digest_without_full_maintenance_model(self) -> None:
        result = validate_plan_contract(valid_plan_contract(maintenance_model=None))

        self.assertTrue(result.ok)

    def test_plan_contract_requires_maintenance_digest_candidate(self) -> None:
        result = validate_plan_contract(valid_plan_contract(maintenance_digest=None))

        self.assertFalse(result.ok)
        self.assertIn("maintenance_digest", [issue.field for issue in result.issues])

    def test_plan_contract_requires_tests_or_explicit_no_test_rationale(self) -> None:
        result = validate_plan_contract(valid_plan_contract(tests=(), no_tests_rationale=""))

        self.assertFalse(result.ok)
        self.assertEqual(result.issues[0].field, "tests")

    def test_plan_contract_requires_docs_for_design_intent_changes(self) -> None:
        result = validate_plan_contract(valid_plan_contract(docs=()))

        self.assertFalse(result.ok)
        self.assertEqual(result.issues[0].field, "docs")

    def test_plan_contract_requires_slice_checks(self) -> None:
        result = validate_plan_contract(
            valid_plan_contract(
                implementation_slices=(
                    ImplementationSlice(
                        id="slice-1",
                        purpose="Add module.",
                        files=("pyagent/task_planning.py",),
                        expected_change="Add data structures.",
                        check="",
                    ),
                )
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertIn("implementation_slices[1].check", fields)

    def test_high_risk_plan_requires_user_confirmation(self) -> None:
        result = validate_plan_contract(
            valid_plan_contract(
                risk_level="high",
                user_confirmation_required=False,
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.issues[0].field, "user_confirmation_required")

    def test_formatters_make_gate_artifacts_readable(self) -> None:
        intent_text = format_intent_model(valid_intent_model())
        plan_text = format_plan_contract(valid_plan_contract())
        gate_text = format_gate_result(validate_plan_contract(valid_plan_contract(tests=())))

        self.assertIn("IntentModel", intent_text)
        self.assertIn("scope_boundaries", intent_text)
        self.assertIn("PlanContract", plan_text)
        self.assertIn("alternatives_considered", plan_text)
        self.assertIn("gate: ok", format_gate_result(validate_plan_contract(valid_plan_contract())))
        self.assertIn("gate: blocked", gate_text)

    def test_plan_task_draft_prompt_requires_gate_artifacts_without_execution(self) -> None:
        prompt = build_plan_task_draft_prompt("Add a plan-task draft command.")

        self.assertIn("Do not implement the task yet", prompt)
        self.assertIn("Do not call Edit or Write", prompt)
        self.assertIn("Do not call Bash in draft mode", prompt)
        self.assertIn("IntentModel draft", prompt)
        self.assertIn("If IntentModel gate is blocked, do not draft a full PlanContract", prompt)
        self.assertIn("PlanOptions", prompt)
        self.assertIn("PlanContract gate: not reached", prompt)
        self.assertIn("MaintenanceDigestCandidate before implementation_slices", prompt)
        self.assertIn("Optional MaintenanceModel", prompt)
        self.assertIn("change_scenarios", prompt)
        self.assertIn("MaintenanceDigest candidate", prompt)
        self.assertIn("DigestGate", prompt)
        self.assertIn("PlanArtifactCandidate", prompt)
        self.assertIn("maintenance_digest", prompt)
        self.assertIn("non_goals", prompt)
        self.assertIn("current_slice_id", prompt)
        self.assertIn("verification", prompt)
        self.assertIn("Human review questions", prompt)

    def test_plan_task_run_prompt_includes_four_engineering_principles(self) -> None:
        prompt = build_plan_task_run_prompt("Add a feature")

        self.assertIn("Think before coding", prompt)
        self.assertIn("Simplicity first", prompt)
        self.assertIn("Surgical changes", prompt)
        self.assertIn("Goal-driven execution", prompt)
        self.assertIn("If implementation would exceed the locked plan", prompt)

    def test_plan_review_transition_prompt_asks_model_to_classify_execution_confirmation(self) -> None:
        prompt = build_plan_review_transition_prompt("可以，开始")

        self.assertIn("plan review state", prompt)
        self.assertIn("PlanTransitionDecision", prompt)
        self.assertIn("confirm_execution", prompt)
        self.assertIn("Do not implement yet", prompt)

    def test_goal_anchor_uses_request_as_current_goal(self) -> None:
        anchor = build_goal_anchor("Add a feature")

        self.assertEqual(anchor.goal, "Add a feature")
        self.assertIn("Add a feature", anchor.plan_summary)

    def test_plan_artifact_can_lock_state_anchor(self) -> None:
        state = type(
            "State",
            (),
            {
                "current_goal": "",
                "current_plan_summary": "",
                "current_step": "",
                "planned_files": [],
                "locked_plan": {},
                "planning_status": "needs_confirmation",
            },
        )()
        artifact = build_plan_artifact(
            "Add a feature",
            summary="Add a small tested feature",
            planned_files=("pyagent/cli.py", "tests/test_plan_task_cli.py"),
            non_goals=("Do not build a full PlanStore.",),
            constraints=("Keep current_step free text.",),
            slices=(
                PlanArtifactSlice(
                    id="slice-1",
                    purpose="Persist plan identity.",
                    files=("pyagent/cli.py",),
                    check="python -m unittest tests.test_plan_task_cli",
                ),
            ),
            current_slice_id="slice-1",
            current_step="Update CLI",
            verification=("python -m unittest tests.test_plan_task_cli",),
        )

        result = lock_plan_artifact(state, artifact)

        self.assertTrue(result.ok)
        self.assertEqual(state.planning_status, "locked")
        self.assertEqual(state.current_goal, "Add a feature")
        self.assertEqual(state.current_plan_summary, "Add a small tested feature")
        self.assertEqual(state.planned_files, ["pyagent/cli.py", "tests/test_plan_task_cli.py"])
        self.assertEqual(state.locked_plan["plan_id"], artifact.plan_id)
        self.assertEqual(state.locked_plan["revision"], 1)
        self.assertEqual(state.locked_plan["current_slice_id"], "slice-1")
        self.assertEqual(state.locked_plan["slices"][0]["id"], "slice-1")
        self.assertTrue(state.locked_plan["confirmed_at"])
        formatted = format_plan_artifact(artifact)
        self.assertIn("PlanArtifact", formatted)
        self.assertIn("plan_id", formatted)
        self.assertIn("slice-1", formatted)

    def test_plan_artifact_rejects_unanchored_or_unsafe_paths(self) -> None:
        result = validate_plan_artifact(
            PlanArtifact(
                goal="Add a feature",
                summary="Add a small tested feature",
                planned_files=("C:/tmp/file.py", "../outside.py"),
            )
        )
        messages = [issue.message for issue in result.issues]

        self.assertFalse(result.ok)
        self.assertIn("must be workspace-relative", messages)
        self.assertIn("must not traverse parent directories", messages)

    def test_plan_artifact_rejects_unsafe_slice_files(self) -> None:
        result = validate_plan_artifact(
            build_plan_artifact(
                "Add a feature",
                summary="Add a small tested feature",
                slices=(
                    PlanArtifactSlice(
                        id="slice-1",
                        purpose="Persist plan identity.",
                        files=("../outside.py",),
                        check="python -m unittest tests.test_task_planning",
                    ),
                ),
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertFalse(result.ok)
        self.assertIn("slices[1].files[1]", fields)

    def test_complexity_review_requires_simpler_alternative_and_budget_impact(self) -> None:
        result = validate_complexity_review(
            ComplexityReview(
                new_files_count=2,
                new_abstractions=("Planner",),
                simpler_alternative="",
                complexity_budget_impact="",
                needs_user_confirmation=False,
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertIn("simpler_alternative", fields)
        self.assertIn("complexity_budget_impact", fields)

    def test_maintenance_model_formatter_explains_how_to_change_project(self) -> None:
        text = format_maintenance_model(valid_maintenance_model())

        self.assertIn("MaintenanceModel", text)
        self.assertIn("module_responsibilities", text)
        self.assertIn("change_scenarios", text)
        self.assertIn("handoff_map", text)

    def test_maintenance_digest_formatter_shows_user_mental_model(self) -> None:
        text = format_maintenance_digest(valid_maintenance_digest())

        self.assertIn("MaintenanceDigest", text)
        self.assertIn("mental_model", text)
        self.assertIn("module_map", text)
        self.assertIn("change_paths", text)
        self.assertIn("handoff_notes", text)

    def test_plan_options_require_conditional_evidence_driven_choices(self) -> None:
        options = (
            PlanOption(
                name="Python + Pygame prototype",
                when_to_choose="Choose this when local desktop prototyping is the priority.",
                evidence_needed=("User confirms desktop target.",),
                tradeoffs=("Fast setup, weaker editor tooling than a game engine.",),
                first_slice="Create a minimal window and input loop.",
            ),
            PlanOption(
                name="Godot prototype",
                when_to_choose="Choose this when editor workflow and tilemap tooling matter.",
                evidence_needed=("User is willing to use a game engine.",),
                tradeoffs=("More setup, stronger built-in game tooling.",),
                first_slice="Create a project with one scene and player movement.",
            ),
        )

        result = validate_plan_options(options)
        text = format_plan_options(options)

        self.assertTrue(result.ok)
        self.assertIn("when_to_choose", text)
        self.assertIn("evidence_needed", text)
        self.assertIn("first_slice", text)

    def test_plan_options_gate_blocks_single_default_recommendation(self) -> None:
        result = validate_plan_options(
            (
                PlanOption(
                    name="Python + Pygame",
                    when_to_choose="",
                    evidence_needed=(),
                    tradeoffs=(),
                    first_slice="",
                ),
            )
        )
        fields = [issue.field for issue in result.issues]

        self.assertIn("plan_options", fields)
        self.assertIn("plan_options[1].when_to_choose", fields)
        self.assertIn("plan_options[1].evidence_needed", fields)
        self.assertIn("plan_options[1].tradeoffs", fields)
        self.assertIn("plan_options[1].first_slice", fields)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
PLANNING_STATUSES = {"idle", "drafting", "blocked", "needs_confirmation", "locked", "executing", "completed"}
PLANNING_WRITE_LOCK_STATUSES = {"drafting", "blocked", "needs_confirmation", "locked"}
PLANNING_WRITE_TOOLS = {"Edit", "Write", "Bash"}


@dataclass(frozen=True)
class GateIssue:
    field: str
    message: str


@dataclass(frozen=True)
class GateResult:
    issues: tuple[GateIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class GoalAnchor:
    goal: str
    plan_summary: str
    current_step: str = ""


@dataclass(frozen=True)
class PlanArtifact:
    goal: str
    summary: str
    planned_files: tuple[str, ...] = ()
    current_step: str = ""
    plan_id: str = field(default_factory=lambda: str(uuid4()))
    revision: int = 1
    source_message_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confirmed_at: str = ""
    non_goals: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    slices: tuple["PlanArtifactSlice", ...] = ()
    current_slice_id: str = ""
    verification: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanArtifactSlice:
    id: str
    purpose: str
    files: tuple[str, ...] = ()
    check: str = ""


@dataclass(frozen=True)
class DeviationRecord:
    tool_name: str
    target: str
    reason: str
    goal_aligned: bool
    requires_replan: bool
    plan_id: str = ""
    plan_revision: int = 0
    current_slice_id: str = ""


@dataclass(frozen=True)
class ComplexityReview:
    new_files_count: int
    new_abstractions: tuple[str, ...]
    simpler_alternative: str
    complexity_budget_impact: str
    needs_user_confirmation: bool


@dataclass(frozen=True)
class IntentModel:
    task_id: str
    raw_request: str
    task_type: str
    goal: str
    user_value: str
    non_goals: tuple[str, ...]
    scope_boundaries: tuple[str, ...]
    domain_concepts: tuple[str, ...]
    workflows: tuple[str, ...]
    constraints: tuple[str, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    blocking_questions: tuple[str, ...]
    evidence: tuple[str, ...]
    confidence: str


@dataclass(frozen=True)
class PlanAlternative:
    name: str
    summary: str
    tradeoffs: tuple[str, ...]


@dataclass(frozen=True)
class PlanOption:
    name: str
    when_to_choose: str
    evidence_needed: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    first_slice: str


@dataclass(frozen=True)
class ModuleResponsibility:
    module: str
    owns: tuple[str, ...]
    does_not_own: tuple[str, ...]
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class ChangeScenario:
    scenario: str
    start_at: str
    likely_files: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class TestIntentMapping:
    intent: str
    checks: tuple[str, ...]


@dataclass(frozen=True)
class MaintenanceModel:
    mental_model: str
    module_responsibilities: tuple[ModuleResponsibility, ...]
    change_scenarios: tuple[ChangeScenario, ...]
    extension_points: tuple[str, ...]
    invariants: tuple[str, ...]
    dependency_rules: tuple[str, ...]
    complexity_budget: tuple[str, ...]
    test_intent_map: tuple[TestIntentMapping, ...]
    handoff_map: tuple[str, ...]


@dataclass(frozen=True)
class ImplementationSlice:
    id: str
    purpose: str
    files: tuple[str, ...]
    expected_change: str
    check: str
    design_intent_id: str = ""


@dataclass(frozen=True)
class PlanContract:
    task_id: str
    selected_approach: str
    rationale: str
    evidence: tuple[str, ...]
    alternatives_considered: tuple[PlanAlternative, ...]
    affected_files: tuple[str, ...]
    new_files: tuple[str, ...]
    design_intents: tuple[str, ...]
    implementation_slices: tuple[ImplementationSlice, ...]
    tests: tuple[str, ...]
    docs: tuple[str, ...]
    no_tests_rationale: str
    migration_or_compatibility_notes: tuple[str, ...]
    rollback_plan: str
    risks: tuple[str, ...]
    risk_level: str
    user_confirmation_required: bool
    maintenance_model: MaintenanceModel | None = None

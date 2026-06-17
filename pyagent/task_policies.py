from __future__ import annotations

from datetime import datetime, timezone

from .task_contracts import (
    ComplexityReview,
    DeviationRecord,
    DigestChangePath,
    DigestModule,
    DigestTestIntent,
    GateIssue,
    GateResult,
    GoalAnchor,
    IntentModel,
    MaintenanceDigest,
    MaintenanceModel,
    PlanArtifact,
    PlanArtifactSlice,
    PLANNING_WRITE_LOCK_STATUSES,
    PLANNING_WRITE_TOOLS,
    PlanContract,
    PlanOption,
    VALID_CONFIDENCE,
    VALID_RISK_LEVELS,
)


def planning_status_blocks_tool(status: str, tool_name: str) -> bool:
    return status in PLANNING_WRITE_LOCK_STATUSES and tool_name in PLANNING_WRITE_TOOLS


def planning_status_reason(status: str) -> str:
    if status == "drafting":
        return "plan-task draft is still drafting; implementation tools are blocked"
    if status == "blocked":
        return "plan-task intent is blocked; resolve planning questions before implementation"
    if status == "needs_confirmation":
        return "plan-task draft needs explicit locking or run command before implementation"
    if status == "locked":
        return "plan is locked but not executing; use /plan-task run to start implementation"
    return "planning state blocks implementation tools"


def has_goal_anchor(state: object) -> bool:
    return bool(str(getattr(state, "current_goal", "")).strip())


def build_goal_anchor(raw_request: str, *, plan_summary: str = "", current_step: str = "") -> GoalAnchor:
    goal = raw_request.strip()
    summary = plan_summary.strip() or f"Execute confirmed plan for: {goal}"
    return GoalAnchor(goal=goal, plan_summary=summary, current_step=current_step.strip())


def build_plan_artifact(
    raw_request: str,
    *,
    summary: str = "",
    planned_files: tuple[str, ...] = (),
    current_step: str = "",
    plan_id: str = "",
    revision: int = 1,
    source_message_id: str = "",
    created_at: str = "",
    confirmed_at: str = "",
    non_goals: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
    slices: tuple[PlanArtifactSlice, ...] = (),
    current_slice_id: str = "",
    verification: tuple[str, ...] = (),
) -> PlanArtifact:
    goal = raw_request.strip()
    return PlanArtifact(
        goal=goal,
        summary=summary.strip() or f"Execute confirmed plan for: {goal}",
        planned_files=tuple(path.strip() for path in planned_files if path.strip()),
        current_step=current_step.strip(),
        **({"plan_id": plan_id.strip()} if plan_id.strip() else {}),
        revision=max(1, int(revision or 1)),
        source_message_id=source_message_id.strip(),
        created_at=created_at.strip() or _utc_now(),
        confirmed_at=confirmed_at.strip(),
        non_goals=tuple(item.strip() for item in non_goals if item.strip()),
        constraints=tuple(item.strip() for item in constraints if item.strip()),
        slices=tuple(slices),
        current_slice_id=current_slice_id.strip(),
        verification=tuple(item.strip() for item in verification if item.strip()),
    )


def validate_plan_artifact(artifact: PlanArtifact) -> GateResult:
    issues: list[GateIssue] = []
    _require_text(issues, "goal", artifact.goal)
    _require_text(issues, "summary", artifact.summary)
    _require_text(issues, "plan_id", artifact.plan_id)
    if artifact.revision < 1:
        issues.append(GateIssue("revision", "must be one or greater"))
    for index, path in enumerate(artifact.planned_files, start=1):
        _validate_workspace_path(issues, f"planned_files[{index}]", path)
    for index, item in enumerate(artifact.slices, start=1):
        prefix = f"slices[{index}]"
        _require_text(issues, f"{prefix}.id", item.id)
        _require_text(issues, f"{prefix}.purpose", item.purpose)
        for file_index, path in enumerate(item.files, start=1):
            _validate_workspace_path(issues, f"{prefix}.files[{file_index}]", path)
    return GateResult(tuple(issues))


def lock_plan_artifact(state: object, artifact: PlanArtifact) -> GateResult:
    result = validate_plan_artifact(artifact)
    if not result.ok:
        return result
    state.current_goal = artifact.goal
    state.current_plan_summary = artifact.summary
    state.current_step = artifact.current_step
    if hasattr(state, "current_slice_id"):
        state.current_slice_id = artifact.current_slice_id
    state.planned_files = list(artifact.planned_files)
    confirmed_at = artifact.confirmed_at or _utc_now()
    state.locked_plan = {
        "plan_id": artifact.plan_id,
        "revision": artifact.revision,
        "source_message_id": artifact.source_message_id,
        "created_at": artifact.created_at,
        "confirmed_at": confirmed_at,
        "goal": artifact.goal,
        "summary": artifact.summary,
        "planned_files": list(artifact.planned_files),
        "current_step": artifact.current_step,
        "current_slice_id": artifact.current_slice_id,
        "non_goals": list(artifact.non_goals),
        "constraints": list(artifact.constraints),
        "slices": [
            {
                "id": item.id,
                "purpose": item.purpose,
                "files": list(item.files),
                "check": item.check,
            }
            for item in artifact.slices
        ],
        "verification": list(artifact.verification),
    }
    state.planning_status = "locked"
    return result


def should_record_deviation(state: object, tool_name: str, target: str) -> bool:
    if tool_name not in {"Edit", "Write"}:
        return False
    planned_files = [str(item) for item in getattr(state, "planned_files", [])]
    if not planned_files:
        return False
    normalized_target = target.replace("\\", "/").lower()
    return not any(normalized_target.endswith(path.replace("\\", "/").lower()) for path in planned_files)


def record_deviation(
    state: object,
    *,
    tool_name: str,
    target: str,
    reason: str,
    goal_aligned: bool = True,
    requires_replan: bool = False,
) -> None:
    deviations = getattr(state, "deviations", None)
    if deviations is None:
        return
    record = DeviationRecord(
        tool_name=tool_name,
        target=target,
        reason=reason,
        goal_aligned=goal_aligned,
        requires_replan=requires_replan,
        plan_id=str((getattr(state, "locked_plan", {}) or {}).get("plan_id", "")),
        plan_revision=int((getattr(state, "locked_plan", {}) or {}).get("revision", 0) or 0),
        current_slice_id=str(getattr(state, "current_slice_id", "")),
    )
    deviations.append(
        {
            "tool_name": record.tool_name,
            "target": record.target,
            "reason": record.reason,
            "goal_aligned": record.goal_aligned,
            "requires_replan": record.requires_replan,
            "plan_id": record.plan_id,
            "plan_revision": record.plan_revision,
            "current_slice_id": record.current_slice_id,
        }
    )


def validate_complexity_review(review: ComplexityReview) -> GateResult:
    issues: list[GateIssue] = []
    if review.new_files_count < 0:
        issues.append(GateIssue("new_files_count", "must be zero or greater"))
    _require_text(issues, "simpler_alternative", review.simpler_alternative)
    _require_text(issues, "complexity_budget_impact", review.complexity_budget_impact)
    return GateResult(tuple(issues))


def validate_plan_options(options: tuple[PlanOption, ...]) -> GateResult:
    issues: list[GateIssue] = []
    if len(options) < 2:
        issues.append(GateIssue("plan_options", "at least two conditional options are required"))
    for index, option in enumerate(options, start=1):
        prefix = f"plan_options[{index}]"
        _require_text(issues, f"{prefix}.name", option.name)
        _require_text(issues, f"{prefix}.when_to_choose", option.when_to_choose)
        _require_items(issues, f"{prefix}.evidence_needed", option.evidence_needed)
        _require_items(issues, f"{prefix}.tradeoffs", option.tradeoffs)
        _require_text(issues, f"{prefix}.first_slice", option.first_slice)
    return GateResult(tuple(issues))


def validate_maintenance_model(model: MaintenanceModel) -> GateResult:
    issues: list[GateIssue] = []
    _require_text(issues, "mental_model", model.mental_model)
    _require_items(issues, "module_responsibilities", model.module_responsibilities)
    _require_min_items(issues, "change_scenarios", model.change_scenarios, 3)
    _require_min_items(issues, "extension_points", model.extension_points, 2)
    _require_items(issues, "invariants", model.invariants)
    _require_items(issues, "dependency_rules", model.dependency_rules)
    _require_items(issues, "complexity_budget", model.complexity_budget)
    _require_items(issues, "test_intent_map", model.test_intent_map)
    _require_items(issues, "handoff_map", model.handoff_map)

    for index, item in enumerate(model.module_responsibilities, start=1):
        prefix = f"module_responsibilities[{index}]"
        _require_text(issues, f"{prefix}.module", item.module)
        _require_items(issues, f"{prefix}.owns", item.owns)
        _require_items(issues, f"{prefix}.does_not_own", item.does_not_own)
    for index, item in enumerate(model.change_scenarios, start=1):
        prefix = f"change_scenarios[{index}]"
        _require_text(issues, f"{prefix}.scenario", item.scenario)
        _require_text(issues, f"{prefix}.start_at", item.start_at)
        _require_items(issues, f"{prefix}.likely_files", item.likely_files)
        _require_text(issues, f"{prefix}.notes", item.notes)
    for index, item in enumerate(model.test_intent_map, start=1):
        prefix = f"test_intent_map[{index}]"
        _require_text(issues, f"{prefix}.intent", item.intent)
        _require_items(issues, f"{prefix}.checks", item.checks)
    return GateResult(tuple(issues))


def build_maintenance_digest(
    *,
    mental_model: str,
    module_map: tuple[DigestModule, ...],
    change_paths: tuple[DigestChangePath, ...],
    extension_points: tuple[str, ...],
    invariants: tuple[str, ...],
    handoff_notes: tuple[str, ...],
    test_intent_map: tuple[DigestTestIntent, ...] = (),
    digest_id: str = "",
    revision: int = 1,
    source_plan_id: str = "",
    source_message_id: str = "",
    updated_at: str = "",
) -> MaintenanceDigest:
    return MaintenanceDigest(
        mental_model=mental_model.strip(),
        module_map=tuple(module_map),
        change_paths=tuple(change_paths),
        extension_points=tuple(item.strip() for item in extension_points if item.strip()),
        invariants=tuple(item.strip() for item in invariants if item.strip()),
        handoff_notes=tuple(item.strip() for item in handoff_notes if item.strip()),
        test_intent_map=tuple(test_intent_map),
        **({"digest_id": digest_id.strip()} if digest_id.strip() else {}),
        revision=max(1, int(revision or 1)),
        source_plan_id=source_plan_id.strip(),
        source_message_id=source_message_id.strip(),
        updated_at=updated_at.strip() or _utc_now(),
    )


def validate_maintenance_digest(digest: MaintenanceDigest) -> GateResult:
    issues: list[GateIssue] = []
    _require_text(issues, "mental_model", digest.mental_model)
    _require_items(issues, "module_map", digest.module_map)
    _require_min_items(issues, "change_paths", digest.change_paths, 2)
    _require_items(issues, "extension_points", digest.extension_points)
    _require_items(issues, "invariants", digest.invariants)
    _require_items(issues, "handoff_notes", digest.handoff_notes)
    _require_text(issues, "digest_id", digest.digest_id)
    if digest.revision < 1:
        issues.append(GateIssue("revision", "must be one or greater"))

    for index, item in enumerate(digest.module_map, start=1):
        prefix = f"module_map[{index}]"
        _require_text(issues, f"{prefix}.module", item.module)
        _require_text(issues, f"{prefix}.responsibility", item.responsibility)
    for index, item in enumerate(digest.change_paths, start=1):
        prefix = f"change_paths[{index}]"
        _require_text(issues, f"{prefix}.scenario", item.scenario)
        _require_text(issues, f"{prefix}.start_at", item.start_at)
    for index, item in enumerate(digest.test_intent_map, start=1):
        prefix = f"test_intent_map[{index}]"
        _require_text(issues, f"{prefix}.intent", item.intent)
        _require_items(issues, f"{prefix}.checks", item.checks)
    return GateResult(tuple(issues))


def validate_intent_model(model: IntentModel) -> GateResult:
    issues: list[GateIssue] = []
    _require_text(issues, "task_id", model.task_id)
    _require_text(issues, "raw_request", model.raw_request)
    _require_text(issues, "goal", model.goal)
    _require_text(issues, "user_value", model.user_value)
    _require_items(issues, "non_goals", model.non_goals)
    _require_items(issues, "scope_boundaries", model.scope_boundaries)
    _require_items(issues, "assumptions", model.assumptions)
    _require_items(issues, "evidence", model.evidence)

    if model.confidence not in VALID_CONFIDENCE:
        issues.append(GateIssue("confidence", "confidence must be low, medium, or high"))
    elif model.confidence == "low":
        issues.append(GateIssue("confidence", "low-confidence intent must return to clarification or code inspection"))

    if model.blocking_questions:
        issues.append(
            GateIssue(
                "blocking_questions",
                "blocking questions must be resolved before forming a plan contract",
            )
        )

    return GateResult(tuple(issues))


def validate_plan_contract(contract: PlanContract) -> GateResult:
    issues: list[GateIssue] = []
    _require_text(issues, "task_id", contract.task_id)
    _require_text(issues, "selected_approach", contract.selected_approach)
    _require_text(issues, "rationale", contract.rationale)
    _require_items(issues, "evidence", contract.evidence)
    _require_items(issues, "alternatives_considered", contract.alternatives_considered)

    if not contract.affected_files and not contract.new_files:
        issues.append(GateIssue("files", "plan must list affected_files or new_files"))

    if not contract.implementation_slices:
        issues.append(GateIssue("implementation_slices", "plan must include reviewable implementation slices"))
    for index, item in enumerate(contract.implementation_slices, start=1):
        prefix = f"implementation_slices[{index}]"
        _require_text(issues, f"{prefix}.id", item.id)
        _require_text(issues, f"{prefix}.purpose", item.purpose)
        _require_items(issues, f"{prefix}.files", item.files)
        _require_text(issues, f"{prefix}.expected_change", item.expected_change)
        _require_text(issues, f"{prefix}.check", item.check)

    if not contract.tests and not contract.no_tests_rationale.strip():
        issues.append(GateIssue("tests", "plan must list tests or explain why tests are not needed"))

    if contract.design_intents and not contract.docs:
        issues.append(GateIssue("docs", "plans that change design intent must include docs, ADR, or RFC updates"))

    if contract.maintenance_model is not None:
        for issue in validate_maintenance_model(contract.maintenance_model).issues:
            issues.append(GateIssue(f"maintenance_model.{issue.field}", issue.message))

    if contract.maintenance_digest is None:
        issues.append(GateIssue("maintenance_digest", "plan must include a user-facing MaintenanceDigestCandidate"))
    else:
        for issue in validate_maintenance_digest(contract.maintenance_digest).issues:
            issues.append(GateIssue(f"maintenance_digest.{issue.field}", issue.message))

    _require_text(issues, "rollback_plan", contract.rollback_plan)

    if contract.risk_level not in VALID_RISK_LEVELS:
        issues.append(GateIssue("risk_level", "risk_level must be low, medium, or high"))
    elif contract.risk_level == "high" and not contract.user_confirmation_required:
        issues.append(GateIssue("user_confirmation_required", "high-risk plans require explicit user confirmation"))

    return GateResult(tuple(issues))


def _require_text(issues: list[GateIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(GateIssue(field, "required"))


def _require_items(issues: list[GateIssue], field: str, values: tuple[object, ...]) -> None:
    if not values:
        issues.append(GateIssue(field, "at least one item is required"))


def _require_min_items(issues: list[GateIssue], field: str, values: tuple[object, ...], minimum: int) -> None:
    if len(values) < minimum:
        issues.append(GateIssue(field, f"at least {minimum} items are required"))


def _validate_workspace_path(issues: list[GateIssue], field: str, path: str) -> None:
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        issues.append(GateIssue(field, "must not be blank"))
    if normalized.startswith("/") or ":" in normalized:
        issues.append(GateIssue(field, "must be workspace-relative"))
    if normalized == ".." or normalized.startswith("../") or "/../" in normalized:
        issues.append(GateIssue(field, "must not traverse parent directories"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

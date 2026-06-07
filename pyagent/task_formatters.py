from __future__ import annotations

from .task_contracts import GateResult, IntentModel, MaintenanceModel, PlanArtifact, PlanContract, PlanOption


def format_plan_options(options: tuple[PlanOption, ...]) -> str:
    lines = ["PlanOptions"]
    if not options:
        lines.append("  - none")
        return "\n".join(lines)
    for option in options:
        lines.extend(
            [
                f"  - {option.name}",
                f"    when_to_choose: {option.when_to_choose}",
                "    evidence_needed:",
                *_format_items(option.evidence_needed, indent="      "),
                "    tradeoffs:",
                *_format_items(option.tradeoffs, indent="      "),
                f"    first_slice: {option.first_slice}",
            ]
        )
    return "\n".join(lines)


def format_maintenance_model(model: MaintenanceModel) -> str:
    lines = [
        "MaintenanceModel",
        f"  mental_model: {model.mental_model}",
        "  module_responsibilities:",
    ]
    if model.module_responsibilities:
        for item in model.module_responsibilities:
            lines.append(f"    - {item.module}")
            lines.append("      owns:")
            lines.extend(_format_items(item.owns, indent="        "))
            lines.append("      does_not_own:")
            lines.extend(_format_items(item.does_not_own, indent="        "))
            lines.append("      depends_on:")
            lines.extend(_format_items(item.depends_on, indent="        "))
    else:
        lines.append("    - none")
    lines.append("  change_scenarios:")
    if model.change_scenarios:
        for item in model.change_scenarios:
            lines.append(f"    - {item.scenario}")
            lines.append(f"      start_at: {item.start_at}")
            lines.append("      likely_files:")
            lines.extend(_format_items(item.likely_files, indent="        "))
            lines.append(f"      notes: {item.notes}")
    else:
        lines.append("    - none")
    lines.extend(
        [
            "  extension_points:",
            *_format_items(model.extension_points),
            "  invariants:",
            *_format_items(model.invariants),
            "  dependency_rules:",
            *_format_items(model.dependency_rules),
            "  complexity_budget:",
            *_format_items(model.complexity_budget),
            "  test_intent_map:",
        ]
    )
    if model.test_intent_map:
        for item in model.test_intent_map:
            lines.append(f"    - {item.intent}")
            lines.append("      checks:")
            lines.extend(_format_items(item.checks, indent="        "))
    else:
        lines.append("    - none")
    lines.extend(["  handoff_map:", *_format_items(model.handoff_map)])
    return "\n".join(lines)


def format_gate_result(result: GateResult) -> str:
    if result.ok:
        return "gate: ok"
    lines = ["gate: blocked"]
    for issue in result.issues:
        lines.append(f"  - {issue.field}: {issue.message}")
    return "\n".join(lines)


def format_plan_artifact(artifact: PlanArtifact) -> str:
    lines = [
        "PlanArtifact",
        f"  plan_id: {artifact.plan_id}",
        f"  revision: {artifact.revision}",
        f"  goal: {artifact.goal}",
        f"  summary: {artifact.summary}",
        "  planned_files:",
        *_format_items(artifact.planned_files),
    ]
    if artifact.source_message_id:
        lines.append(f"  source_message_id: {artifact.source_message_id}")
    if artifact.created_at:
        lines.append(f"  created_at: {artifact.created_at}")
    if artifact.confirmed_at:
        lines.append(f"  confirmed_at: {artifact.confirmed_at}")
    if artifact.non_goals:
        lines.extend(["  non_goals:", *_format_items(artifact.non_goals)])
    if artifact.constraints:
        lines.extend(["  constraints:", *_format_items(artifact.constraints)])
    if artifact.slices:
        lines.append("  slices:")
        for item in artifact.slices:
            lines.append(f"    - {item.id}: {item.purpose}")
            if item.files:
                lines.append(f"      files: {', '.join(item.files)}")
            if item.check:
                lines.append(f"      check: {item.check}")
    if artifact.current_slice_id:
        lines.append(f"  current_slice_id: {artifact.current_slice_id}")
    if artifact.current_step:
        lines.append(f"  current_step: {artifact.current_step}")
    if artifact.verification:
        lines.extend(["  verification:", *_format_items(artifact.verification)])
    return "\n".join(lines)


def format_intent_model(model: IntentModel) -> str:
    lines = [
        "IntentModel",
        f"  task_id: {model.task_id}",
        f"  task_type: {model.task_type}",
        f"  confidence: {model.confidence}",
        f"  goal: {model.goal}",
        f"  user_value: {model.user_value}",
        "  non_goals:",
        *_format_items(model.non_goals),
        "  scope_boundaries:",
        *_format_items(model.scope_boundaries),
        "  domain_concepts:",
        *_format_items(model.domain_concepts),
        "  workflows:",
        *_format_items(model.workflows),
        "  constraints:",
        *_format_items(model.constraints),
        "  assumptions:",
        *_format_items(model.assumptions),
        "  open_questions:",
        *_format_items(model.open_questions),
        "  blocking_questions:",
        *_format_items(model.blocking_questions),
        "  evidence:",
        *_format_items(model.evidence),
    ]
    return "\n".join(lines)


def format_plan_contract(contract: PlanContract) -> str:
    lines = [
        "PlanContract",
        f"  task_id: {contract.task_id}",
        f"  risk_level: {contract.risk_level}",
        f"  user_confirmation_required: {contract.user_confirmation_required}",
        f"  selected_approach: {contract.selected_approach}",
        f"  rationale: {contract.rationale}",
        "  evidence:",
        *_format_items(contract.evidence),
        "  alternatives_considered:",
    ]
    if contract.alternatives_considered:
        for item in contract.alternatives_considered:
            lines.append(f"    - {item.name}: {item.summary}")
            for tradeoff in item.tradeoffs:
                lines.append(f"      tradeoff: {tradeoff}")
    else:
        lines.append("    - none")
    lines.extend(
        [
            "  affected_files:",
            *_format_items(contract.affected_files),
            "  new_files:",
            *_format_items(contract.new_files),
            "  design_intents:",
            *_format_items(contract.design_intents),
            "  maintenance_model:",
            "    - present" if contract.maintenance_model else "    - missing",
            "  implementation_slices:",
        ]
    )
    if contract.implementation_slices:
        for item in contract.implementation_slices:
            lines.append(f"    - {item.id}: {item.purpose}")
            lines.append(f"      files: {', '.join(item.files)}")
            lines.append(f"      expected_change: {item.expected_change}")
            lines.append(f"      check: {item.check}")
            if item.design_intent_id:
                lines.append(f"      design_intent_id: {item.design_intent_id}")
    else:
        lines.append("    - none")
    lines.extend(
        [
            "  tests:",
            *_format_items(contract.tests),
            f"  no_tests_rationale: {contract.no_tests_rationale or '(none)'}",
            "  docs:",
            *_format_items(contract.docs),
            "  migration_or_compatibility_notes:",
            *_format_items(contract.migration_or_compatibility_notes),
            f"  rollback_plan: {contract.rollback_plan}",
            "  risks:",
            *_format_items(contract.risks),
        ]
    )
    return "\n".join(lines)


def _format_items(values: tuple[str, ...], *, indent: str = "    ") -> list[str]:
    if not values:
        return [f"{indent}- none"]
    return [f"{indent}- {item}" for item in values]

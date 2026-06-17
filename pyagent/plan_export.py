from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent import Agent
from .config import Config
from .plan_parsing import parse_maintenance_digest, parse_plan_artifact_bundle
from .plan_store import PlanStore
from .task_planning import MaintenanceDigest, PlanArtifact, format_maintenance_digest, format_plan_artifact
from . import ui


def persist_current_plan(agent: Agent, config: Config) -> dict[str, Path] | None:
    if not hasattr(config, "config_dir"):
        return None
    artifact = current_plan_payload(agent)
    if not artifact:
        return None
    digest = agent.state.maintenance_digest or agent.state.maintenance_digest_candidate or None
    text = format_plan_state_markdown(agent)
    return PlanStore(config.config_dir).save(
        session_id=str(agent.state.session_id),
        artifact=artifact,
        maintenance_digest=digest if isinstance(digest, dict) else None,
        markdown=text,
    )


def format_plan_state_markdown(agent: Agent) -> str:
    sections: list[str] = []
    state = agent.state
    title = (
        str(state.locked_plan.get("goal", "")).strip()
        if isinstance(state.locked_plan, dict)
        else ""
    ) or state.current_goal or state.planning_request or "Current Plan"
    if not state.locked_plan and not state.plan_artifact_candidate and not state.maintenance_digest and not state.maintenance_digest_candidate:
        return ""
    sections.extend(
        [
            f"# {title}",
            "",
            f"- planning_status: {state.planning_status}",
            f"- session_id: {state.session_id}",
            f"- compact_epoch: {state.compact_epoch}",
            "",
        ]
    )
    artifact = plan_artifact_from_state(agent)
    if artifact is not None:
        sections.extend(["## PlanArtifact", "", "```text", format_plan_artifact(artifact), "```", ""])
    elif state.locked_plan:
        sections.extend(["## Locked Plan", "", "```json", json.dumps(state.locked_plan, ensure_ascii=False, indent=2), "```", ""])
    elif state.plan_artifact_candidate:
        sections.extend(["## PlanArtifactCandidate", "", "```json", json.dumps(state.plan_artifact_candidate, ensure_ascii=False, indent=2), "```", ""])

    digest = maintenance_digest_from_state(agent)
    if digest is not None:
        sections.extend(["## MaintenanceDigest", "", "```text", format_maintenance_digest(digest), "```", ""])

    if state.context_boundaries:
        boundary = state.context_boundaries[-1]
        sections.extend(
            [
                "## Last ContextBoundary",
                "",
                f"- compact_epoch: {boundary.get('compact_epoch', '(unknown)')}",
                f"- plan_id: {boundary.get('plan_id') or 'none'}",
                f"- digest_id: {boundary.get('digest_id') or 'none'}",
                f"- summary_message_id: {boundary.get('summary_message_id') or 'none'}",
                "",
            ]
        )
    return "\n".join(sections).rstrip()


def print_mental_model(agent: Agent) -> None:
    value = getattr(agent.state, "maintenance_digest", {})
    if not isinstance(value, dict) or not value:
        candidate = getattr(agent.state, "maintenance_digest_candidate", {})
        if isinstance(candidate, dict) and candidate:
            try:
                print(format_maintenance_digest(parse_maintenance_digest(candidate)))
                print(ui.warning("This is a draft MaintenanceDigestCandidate; lock the plan to make it current."))
                return
            except ValueError:
                pass
        print("No MaintenanceDigest is locked for this session yet.")
        return
    try:
        print(format_maintenance_digest(parse_maintenance_digest(value)))
    except ValueError as exc:
        print(ui.error(f"Invalid stored MaintenanceDigest: {exc}"))


def plan_artifact_from_state(agent: Agent) -> PlanArtifact | None:
    payload = agent.state.locked_plan or agent.state.plan_artifact_candidate
    if not isinstance(payload, dict) or not payload:
        return None
    try:
        artifact, _digest = parse_plan_artifact_bundle(
            agent.state.planning_request,
            json.dumps(payload, ensure_ascii=False),
        )
        return artifact
    except ValueError:
        return None


def maintenance_digest_from_state(agent: Agent) -> MaintenanceDigest | None:
    payload = agent.state.maintenance_digest or agent.state.maintenance_digest_candidate
    if not isinstance(payload, dict) or not payload:
        return None
    try:
        return parse_maintenance_digest(payload)
    except ValueError:
        return None


def current_plan_payload(agent: Agent) -> dict[str, Any]:
    for payload in (agent.state.locked_plan, agent.state.plan_artifact_candidate):
        if isinstance(payload, dict) and payload:
            return dict(payload)
    return {}

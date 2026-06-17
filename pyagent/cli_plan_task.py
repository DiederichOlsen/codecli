from __future__ import annotations

import json

from .agent import Agent
from .cli_common import print_missing_api_key
from .config import Config
from .plan_export import format_plan_state_markdown, persist_current_plan
from .plan_parsing import (
    candidate_json_objects,
    extract_plan_transition_decision,
    looks_like_digest_payload,
    maintenance_digest_to_dict,
    parse_maintenance_digest,
    parse_plan_artifact_bundle,
    plan_artifact_to_dict,
)
from .storage import TranscriptStore
from .task_planning import (
    MaintenanceDigest,
    PlanArtifact,
    build_goal_anchor,
    build_plan_artifact,
    build_plan_review_transition_prompt,
    build_plan_task_draft_prompt,
    build_plan_task_run_prompt,
    format_gate_result,
    format_maintenance_digest,
    format_plan_artifact,
    lock_plan_artifact,
    validate_maintenance_digest,
)
from . import ui


def run_plan_task_command(agent: Agent, config: Config, prompt: str) -> None:
    parts = prompt.split(" ", 2)
    if len(parts) < 2:
        print("Usage: /plan-task draft TEXT")
        return
    action = parts[1]
    raw_request = parts[2] if len(parts) > 2 else ""
    if action == "draft":
        run_plan_task_draft(agent, config, raw_request)
        return
    if action == "run":
        run_plan_task_run(agent, config)
        return
    if action == "lock":
        run_plan_task_lock(agent, config, raw_request)
        return
    if action == "show":
        run_plan_task_show(agent)
        return
    if action == "export":
        run_plan_task_export(agent, config)
        return
    if action == "clear":
        clear_plan_task_state(agent)
        print("plan-task state cleared")
        return
    print("Usage: /plan-task draft TEXT | /plan-task show | /plan-task export | /plan-task lock [TEXT|JSON] | /plan-task run | /plan-task clear")


def run_plan_task_draft(agent: Agent, config: Config, raw_request: str) -> None:
    if not raw_request.strip():
        print("Usage: /plan-task draft TEXT")
        return
    if not config.api_key:
        print_missing_api_key(config)
        return

    agent.state.planning_status = "drafting"
    agent.state.planning_request = raw_request.strip()
    previous_config_mode = agent.config.permission_mode
    previous_permission_mode = agent.permissions.mode
    agent.config.permission_mode = "plan"
    agent.permissions.mode = "plan"
    try:
        print(ui.warning("Planning draft mode: read/search only; no implementation will be applied."))
        agent.ask(build_plan_task_draft_prompt(raw_request))
        store_latest_plan_artifact_candidate(agent)
    finally:
        agent.config.permission_mode = previous_config_mode
        agent.permissions.mode = previous_permission_mode
        if agent.state.planning_status == "drafting":
            agent.state.planning_status = "needs_confirmation"


def run_plan_task_lock(agent: Agent, config: Config, raw_artifact: str) -> None:
    if not agent.state.planning_request:
        print("No plan-task draft is active. Use /plan-task draft TEXT first.")
        return
    if agent.state.planning_status not in {"needs_confirmation", "locked"}:
        print(f"Cannot lock plan from status: {agent.state.planning_status}")
        return

    try:
        artifact, digest = parse_plan_artifact_bundle(agent.state.planning_request, raw_artifact)
    except ValueError as exc:
        print(f"Invalid plan artifact: {exc}")
        return

    if not lock_artifact_and_digest(agent, artifact, digest):
        return

    print("plan-task locked")
    print(format_plan_artifact(artifact))
    if digest is not None:
        print(format_maintenance_digest(digest))
    paths = persist_current_plan(agent, config)
    if paths:
        print(f"plan stored: {paths['json']}")
        print(f"plan view: {paths['markdown']}")


def run_plan_task_run(agent: Agent, config: Config) -> None:
    if not config.api_key:
        print_missing_api_key(config)
        return
    if not agent.state.planning_request:
        print("No plan-task draft is active. Use /plan-task draft TEXT first.")
        return
    if agent.state.planning_status not in {"needs_confirmation", "locked", "executing"}:
        print(f"Cannot run plan from status: {agent.state.planning_status}")
        return

    if agent.state.locked_plan:
        anchor = build_goal_anchor(
            str(agent.state.locked_plan.get("goal", agent.state.planning_request)),
            plan_summary=str(agent.state.locked_plan.get("summary", "")),
            current_step=str(agent.state.locked_plan.get("current_step", "")),
        )
    else:
        anchor = build_goal_anchor(agent.state.planning_request)
    agent.state.current_goal = anchor.goal
    agent.state.current_plan_summary = anchor.plan_summary
    agent.state.current_step = anchor.current_step
    agent.state.current_slice_id = str(agent.state.locked_plan.get("current_slice_id", ""))
    agent.state.planning_status = "executing"
    print(ui.warning("Plan execution mode: implementation tools are now allowed for the confirmed plan."))
    agent.ask(build_plan_task_run_prompt(anchor.plan_summary))


def run_plan_task_show(agent: Agent) -> None:
    text = format_plan_state_markdown(agent)
    if not text:
        print("No active plan yet. Use /plan-task draft TEXT first.")
        return
    print(text)


def run_plan_task_export(agent: Agent, config: Config) -> None:
    text = format_plan_state_markdown(agent)
    if not text:
        print("No active plan yet. Use /plan-task draft TEXT first.")
        return
    paths = persist_current_plan(agent, config)
    if not paths:
        print("No structured plan artifact is available to export yet.")
        return
    print(f"plan exported: {paths['markdown']}")
    print(f"plan snapshot: {paths['json']}")


def clear_plan_task_state(agent: Agent) -> None:
    agent.state.planning_status = "idle"
    agent.state.planning_request = ""
    agent.state.current_goal = ""
    agent.state.current_plan_summary = ""
    agent.state.current_step = ""
    agent.state.current_slice_id = ""
    agent.state.planned_files = []
    agent.state.plan_artifact_candidate = {}
    agent.state.maintenance_digest_candidate = {}
    agent.state.maintenance_digest = {}
    agent.state.locked_plan = {}
    agent.state.deviations = []


def handle_plan_review_message(agent: Agent, config: Config, store: TranscriptStore, prompt: str) -> bool:
    if agent.state.planning_status != "needs_confirmation":
        return False
    if not config.api_key:
        print_missing_api_key(config)
        return True

    response_text = agent.ask(build_plan_review_transition_prompt(prompt))
    store_latest_plan_artifact_candidate(agent)
    source_message_id = latest_assistant_message_id(agent)
    should_execute, transition_artifact, transition_digest = extract_plan_transition_decision(
        response_text,
        source_message_id=source_message_id,
    )
    if not should_execute:
        store.save_state(agent.state)
        return True

    state_artifact, state_digest = plan_artifact_candidate_from_state(agent)
    latest_artifact, latest_digest = extract_latest_plan_artifact_bundle(agent)
    artifact = transition_artifact or state_artifact or latest_artifact
    digest = transition_digest or state_digest or latest_digest
    if artifact is None:
        artifact = build_plan_artifact(
            agent.state.planning_request,
            summary=(
                "Confirmed plan from the current conversation. "
                "No structured PlanArtifactCandidate was found, so planned_files is empty."
            ),
            current_step="start execution",
        )

    print("Plan execution confirmation detected by model.")
    print(format_plan_artifact(artifact))
    if digest is not None:
        print(format_maintenance_digest(digest))
    answer = input("Lock this plan and start execution? y/N ").strip().lower()
    if answer not in {"y", "yes"}:
        print("plan-task confirmation cancelled")
        store.save_state(agent.state)
        return True

    if not lock_artifact_and_digest(agent, artifact, digest):
        store.save_state(agent.state)
        return True
    persist_current_plan(agent, config)
    store.save_state(agent.state)
    print("plan-task locked")
    run_plan_task_run(agent, config)
    store.save_state(agent.state)
    return True


def lock_artifact_and_digest(agent: Agent, artifact: PlanArtifact, digest: MaintenanceDigest | None) -> bool:
    if digest is not None:
        digest_result = validate_maintenance_digest(digest)
        if not digest_result.ok:
            print(format_gate_result(digest_result))
            return False
    artifact_result = lock_plan_artifact(agent.state, artifact)
    if not artifact_result.ok:
        print(format_gate_result(artifact_result))
        return False
    if digest is not None:
        agent.state.maintenance_digest = maintenance_digest_to_dict(digest)
        agent.state.maintenance_digest_candidate = {}
    return True


def extract_latest_plan_artifact_bundle(agent: Agent) -> tuple[PlanArtifact | None, MaintenanceDigest | None]:
    for message in reversed(agent.state.messages):
        if message.get("role") != "assistant":
            continue
        content = str(message.get("content", ""))
        if "PlanArtifactCandidate" not in content and "MaintenanceDigestCandidate" not in content:
            continue
        artifact: PlanArtifact | None = None
        digest: MaintenanceDigest | None = None
        for raw_json in candidate_json_objects(content):
            try:
                payload = json.loads(raw_json)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("action") == "confirm_execution":
                payload = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
            if looks_like_digest_payload(payload):
                try:
                    digest = parse_maintenance_digest(payload)
                except ValueError:
                    pass
                continue
            try:
                artifact, embedded_digest = parse_plan_artifact_bundle(
                    agent.state.planning_request,
                    raw_json,
                    source_message_id=str(message.get("id", "")),
                )
                digest = embedded_digest or digest
            except ValueError:
                continue
        if artifact is not None or digest is not None:
            return artifact, digest
    return None, None


def store_latest_plan_artifact_candidate(agent: Agent) -> None:
    artifact, digest = extract_latest_plan_artifact_bundle(agent)
    if artifact is not None:
        agent.state.plan_artifact_candidate = plan_artifact_to_dict(artifact)
    if digest is not None:
        agent.state.maintenance_digest_candidate = maintenance_digest_to_dict(digest)


def plan_artifact_candidate_from_state(agent: Agent) -> tuple[PlanArtifact | None, MaintenanceDigest | None]:
    value = getattr(agent.state, "plan_artifact_candidate", {})
    if not isinstance(value, dict) or not value:
        return None, maintenance_digest_candidate_from_state(agent)
    try:
        artifact, digest = parse_plan_artifact_bundle(
            agent.state.planning_request,
            json.dumps(value, ensure_ascii=False),
        )
        return artifact, digest or maintenance_digest_candidate_from_state(agent)
    except ValueError:
        return None, maintenance_digest_candidate_from_state(agent)


def maintenance_digest_candidate_from_state(agent: Agent) -> MaintenanceDigest | None:
    value = getattr(agent.state, "maintenance_digest_candidate", {})
    if not isinstance(value, dict) or not value:
        return None
    try:
        return parse_maintenance_digest(value)
    except ValueError:
        return None


def latest_assistant_message_id(agent: Agent) -> str:
    for message in reversed(agent.state.messages):
        if message.get("role") == "assistant":
            return str(message.get("id", ""))
    return ""


def next_status_action(state: object) -> str:
    status = str(getattr(state, "planning_status", "idle"))
    if status == "idle":
        return "use /plan-task draft TEXT for substantial changes"
    if status == "drafting":
        return "wait for the draft, then review /plan-task show"
    if status == "needs_confirmation":
        return "review /plan-task show, then /plan-task lock or answer with changes"
    if status == "locked":
        return "use /plan-task run to execute the locked plan"
    if status == "executing":
        return "keep changes aligned with the locked plan; use /mental-model for orientation"
    if status == "completed":
        return "use /plan-task clear before starting a new unrelated task"
    return "inspect /plan-task show"

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional

from .agent import Agent
from .config import Config
from .design_trace import format_design_index, format_test_intent_map
from .storage import TranscriptStore
from .task_planning import (
    PlanArtifact,
    PlanArtifactSlice,
    build_goal_anchor,
    build_plan_artifact,
    build_plan_review_transition_prompt,
    build_plan_task_draft_prompt,
    build_plan_task_run_prompt,
    format_gate_result,
    format_plan_artifact,
    lock_plan_artifact,
)
from .verification import VerificationPolicy
from . import ui


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code inspired Python coding agent prototype.")
    parser.add_argument("prompt", nargs="*", help="Prompt to run once. If omitted, starts interactive mode.")
    parser.add_argument("--cwd", default=".", help="Workspace directory.")
    parser.add_argument("--model", help="Model name, for example deepseek-chat or qwen-plus.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL.")
    parser.add_argument("--api-key", help="API key. Prefer PYAGENT_API_KEY.")
    parser.add_argument("--permission-mode", choices=["default", "plan", "accept_edits", "bypass"], help="Permission mode.")
    parser.add_argument("--color", choices=["auto", "always", "never"], help="Color output mode.")
    parser.add_argument("--resume", help="Resume a session id.")
    parser.add_argument("--list-sessions", action="store_true", help="List saved sessions.")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    config = Config.load(
        cwd,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        permission_mode=args.permission_mode,
        color=args.color,
    )
    ui.configure_color(config.color)
    config.config_dir.mkdir(parents=True, exist_ok=True)

    store = TranscriptStore(config.config_dir)
    if args.list_sessions:
        for item in store.list_sessions():
            print(json.dumps(item, ensure_ascii=False))
        return 0

    state = store.load(args.resume) if args.resume else None
    agent = Agent(config=config, state=state, interactive=True)
    if args.prompt:
        if not config.api_key:
            _print_missing_api_key(config)
            return 2
        agent.ask(" ".join(args.prompt))
        store.save_state(agent.state)
        return 0

    print("pyagent prototype")
    print(f"session: {agent.state.session_id}")
    print("Commands: /help, /status, /design, /intent, /plan-task draft REQUEST, /compact, /sessions, /session load ID, /tool NAME JSON, /exit")
    while True:
        try:
            prompt = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            store.save_state(agent.state)
            print("session state saved")
            return 0
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            store.save_state(agent.state)
            print("session state saved")
            return 0
        if prompt == "/help":
            _print_help()
            continue
        if prompt == "/status":
            print(f"cwd: {config.cwd}")
            print(f"model: {config.model}")
            print(f"base_url: {config.base_url}")
            print(f"permission_mode: {config.permission_mode}")
            print(f"color: {config.color}")
            print("config_files:")
            for path in config.config_files:
                exists = "exists" if path.exists() else "missing"
                print(f"  - {path} ({exists})")
            print(f"messages: {len(agent.state.messages)}")
            print(f"todos: {agent.state.todos}")
            print(f"file_snapshots: {len(agent.state.file_snapshots)}")
            print(f"planning_status: {agent.state.planning_status}")
            if agent.state.planning_request:
                print(f"planning_request: {agent.state.planning_request}")
            if agent.state.current_goal:
                print(f"current_goal: {agent.state.current_goal}")
            if agent.state.current_step:
                print(f"current_step: {agent.state.current_step}")
            if agent.state.current_slice_id:
                print(f"current_slice_id: {agent.state.current_slice_id}")
            if agent.state.plan_artifact_candidate:
                print("plan_artifact_candidate:")
                print(_indent_block(json.dumps(agent.state.plan_artifact_candidate, ensure_ascii=False)))
            if agent.state.locked_plan:
                print("locked_plan:")
                print(_indent_block(json.dumps(agent.state.locked_plan, ensure_ascii=False)))
            if agent.state.planned_files:
                print("planned_files:")
                for path in agent.state.planned_files:
                    print(f"  - {path}")
            if agent.state.deviations:
                print(f"deviations: {len(agent.state.deviations)}")
            print(VerificationPolicy().format_status(agent.state))
            continue
        if prompt == "/design":
            print(format_design_index())
            continue
        if prompt == "/intent":
            print(format_test_intent_map())
            continue
        if prompt.startswith("/plan-task "):
            _run_plan_task_command(agent, config, prompt)
            store.save_state(agent.state)
            continue
        if prompt == "/compact":
            changed = agent.compact_now()
            print("context compacted" if changed else "nothing to compact yet")
            continue
        if prompt == "/sessions":
            for item in store.list_sessions():
                print(json.dumps(item, ensure_ascii=False))
            continue
        if prompt == "/session" or prompt.startswith("/session "):
            _run_session_command(agent, store, prompt)
            continue
        if prompt.startswith("/tool "):
            _run_tool_command(agent, prompt)
            store.save_state(agent.state)
            continue
        if _handle_plan_review_message(agent, config, store, prompt):
            continue
        if not config.api_key:
            _print_missing_api_key(config)
            continue
        agent.ask(prompt)
        store.save_state(agent.state)


def _print_missing_api_key(config: Config) -> None:
    print(ui.error("Missing API key."))
    print(f"cwd: {config.cwd}")
    print("Checked config files:")
    for path in config.config_files:
        exists = "exists" if path.exists() else "missing"
        print(f"  - {path} ({exists})")
    print(ui.warning("Fix one of these:"))
    print("  1. Put api_key in %USERPROFILE%\\.pyagent\\config.json")
    print("  2. Put api_key in the target project's .pyagent\\config.json")
    print("  3. Set PYAGENT_API_KEY")


def _print_help() -> None:
    print(
        """Available commands:
  /status                 Show current session settings.
  /design                 Show the Design Trace index.
  /intent                 Show which tests protect which design intents.
  /plan-task draft TEXT   Draft IntentModel and PlanContract without executing.
  /plan-task lock [TEXT]  Lock the reviewed plan as the execution anchor.
  /plan-task run          Execute the current plan explicitly.
  /plan-task clear        Clear the current planning state.
  /compact                Summarize older context locally.
  /sessions               List saved sessions.
  /session current        Show the active session id.
  /session save           Save the active session state.
  /session load ID        Save current state, then switch to another session.
  /tool NAME JSON         Run a local tool directly, e.g. /tool Glob {"pattern":"**/*.py"}
  /exit                   Exit.

Environment:
  PYAGENT_API_KEY         API key.
  PYAGENT_BASE_URL        OpenAI-compatible base URL.
  PYAGENT_MODEL           Model name.
  PYAGENT_COLOR           auto, always, or never.
  NO_COLOR                Disable ANSI color output when set.

Provider examples:
  DeepSeek base URL: https://api.deepseek.com/v1
  Qwen/DashScope compatible URL: https://dashscope.aliyuncs.com/compatible-mode/v1
"""
    )


def _run_plan_task_command(agent: Agent, config: Config, prompt: str) -> None:
    parts = prompt.split(" ", 2)
    if len(parts) < 2:
        print("Usage: /plan-task draft TEXT")
        return
    action = parts[1]
    raw_request = parts[2] if len(parts) > 2 else ""
    if action == "draft":
        _run_plan_task_draft(agent, config, raw_request)
        return
    if action == "run":
        _run_plan_task_run(agent, config)
        return
    if action == "lock":
        _run_plan_task_lock(agent, raw_request)
        return
    if action == "clear":
        agent.state.planning_status = "idle"
        agent.state.planning_request = ""
        agent.state.current_goal = ""
        agent.state.current_plan_summary = ""
        agent.state.current_step = ""
        agent.state.current_slice_id = ""
        agent.state.planned_files = []
        agent.state.plan_artifact_candidate = {}
        agent.state.locked_plan = {}
        agent.state.deviations = []
        print("plan-task state cleared")
        return
    print("Usage: /plan-task draft TEXT | /plan-task lock [TEXT|JSON] | /plan-task run | /plan-task clear")


def _run_session_command(agent: Agent, store: TranscriptStore, prompt: str) -> None:
    parts = prompt.split()
    if len(parts) == 1 or parts[1] == "current":
        print(f"session: {agent.state.session_id}")
        print(f"messages: {len(agent.state.messages)}")
        print(f"planning_status: {agent.state.planning_status}")
        return
    if parts[1] == "save":
        store.save_state(agent.state)
        print(f"session state saved: {agent.state.session_id}")
        return
    if parts[1] == "load":
        if len(parts) < 3:
            print("Usage: /session load ID")
            return
        previous_session_id = agent.state.session_id
        session_id = parts[2]
        agent.load_session(session_id)
        print(f"session switched: {previous_session_id} -> {agent.state.session_id}")
        print(f"messages: {len(agent.state.messages)}")
        print(f"planning_status: {agent.state.planning_status}")
        return
    print("Usage: /session current | /session save | /session load ID")


def _run_plan_task_draft(agent: Agent, config: Config, raw_request: str) -> None:
    if not raw_request.strip():
        print("Usage: /plan-task draft TEXT")
        return
    if not config.api_key:
        _print_missing_api_key(config)
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
        _store_latest_plan_artifact_candidate(agent)
    finally:
        agent.config.permission_mode = previous_config_mode
        agent.permissions.mode = previous_permission_mode
        if agent.state.planning_status == "drafting":
            agent.state.planning_status = "needs_confirmation"


def _run_plan_task_lock(agent: Agent, raw_artifact: str) -> None:
    if not agent.state.planning_request:
        print("No plan-task draft is active. Use /plan-task draft TEXT first.")
        return
    if agent.state.planning_status not in {"needs_confirmation", "locked"}:
        print(f"Cannot lock plan from status: {agent.state.planning_status}")
        return

    try:
        artifact = _parse_plan_artifact_input(agent.state.planning_request, raw_artifact)
    except ValueError as exc:
        print(f"Invalid plan artifact: {exc}")
        return

    result = lock_plan_artifact(agent.state, artifact)
    if not result.ok:
        print(format_gate_result(result))
        return

    print("plan-task locked")
    print(format_plan_artifact(artifact))


def _run_plan_task_run(agent: Agent, config: Config) -> None:
    if not config.api_key:
        _print_missing_api_key(config)
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


def _handle_plan_review_message(agent: Agent, config: Config, store: TranscriptStore, prompt: str) -> bool:
    if agent.state.planning_status != "needs_confirmation":
        return False
    if not config.api_key:
        _print_missing_api_key(config)
        return True

    response_text = agent.ask(build_plan_review_transition_prompt(prompt))
    _store_latest_plan_artifact_candidate(agent)
    source_message_id = _latest_assistant_message_id(agent)
    should_execute, transition_artifact = _extract_plan_transition_decision(
        response_text,
        source_message_id=source_message_id,
    )
    if not should_execute:
        store.save_state(agent.state)
        return True

    artifact = transition_artifact or _plan_artifact_candidate_from_state(agent) or _extract_latest_plan_artifact_candidate(agent)
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
    answer = input("Lock this plan and start execution? y/N ").strip().lower()
    if answer not in {"y", "yes"}:
        print("plan-task confirmation cancelled")
        store.save_state(agent.state)
        return True

    result = lock_plan_artifact(agent.state, artifact)
    if not result.ok:
        print(format_gate_result(result))
        store.save_state(agent.state)
        return True
    store.save_state(agent.state)
    print("plan-task locked")
    _run_plan_task_run(agent, config)
    store.save_state(agent.state)
    return True


def _extract_latest_plan_artifact_candidate(agent: Agent) -> PlanArtifact | None:
    for message in reversed(agent.state.messages):
        if message.get("role") != "assistant":
            continue
        content = str(message.get("content", ""))
        if "PlanArtifactCandidate" not in content:
            continue
        for raw_json in _candidate_json_objects(content):
            try:
                return _parse_plan_artifact_input(
                    agent.state.planning_request,
                    raw_json,
                    source_message_id=str(message.get("id", "")),
                )
            except ValueError:
                continue
    return None


def _store_latest_plan_artifact_candidate(agent: Agent) -> None:
    artifact = _extract_latest_plan_artifact_candidate(agent)
    if artifact is not None:
        agent.state.plan_artifact_candidate = _plan_artifact_to_dict(artifact)


def _plan_artifact_candidate_from_state(agent: Agent) -> PlanArtifact | None:
    value = getattr(agent.state, "plan_artifact_candidate", {})
    if not isinstance(value, dict) or not value:
        return None
    try:
        return _parse_plan_artifact_input(agent.state.planning_request, json.dumps(value, ensure_ascii=False))
    except ValueError:
        return None


def _plan_artifact_to_dict(artifact: PlanArtifact) -> dict[str, object]:
    return {
        "goal": artifact.goal,
        "summary": artifact.summary,
        "plan_id": artifact.plan_id,
        "revision": artifact.revision,
        "source_message_id": artifact.source_message_id,
        "created_at": artifact.created_at,
        "confirmed_at": artifact.confirmed_at,
        "planned_files": list(artifact.planned_files),
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
        "current_slice_id": artifact.current_slice_id,
        "current_step": artifact.current_step,
        "verification": list(artifact.verification),
    }


def _extract_plan_transition_decision(
    content: str,
    *,
    source_message_id: str = "",
) -> tuple[bool, PlanArtifact | None]:
    if "PlanTransitionDecision" not in content and '"confirm_execution"' not in content:
        return False, None
    for raw_json in _candidate_json_objects(content):
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("action") != "confirm_execution":
            continue
        artifact_payload = payload.get("artifact")
        if isinstance(artifact_payload, dict):
            try:
                return True, _parse_plan_artifact_input(
                    "",
                    json.dumps(artifact_payload, ensure_ascii=False),
                    source_message_id=source_message_id,
                )
            except ValueError:
                continue
        return True, None
    return False, None


def _candidate_json_objects(content: str) -> list[str]:
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if blocks:
        return blocks
    marker = content.find("PlanArtifactCandidate")
    if marker < 0:
        marker = content.find("PlanTransitionDecision")
    if marker < 0:
        return []
    tail = content[marker:]
    start = tail.find("{")
    if start < 0:
        return []
    depth = 0
    for index, char in enumerate(tail[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return [tail[start : index + 1]]
    return []


def _parse_plan_artifact_input(
    planning_request: str,
    raw_artifact: str,
    *,
    source_message_id: str = "",
) -> PlanArtifact:
    text = raw_artifact.strip()
    if not text:
        return build_plan_artifact(planning_request, source_message_id=source_message_id)
    if not text.startswith("{"):
        return build_plan_artifact(planning_request, summary=text, source_message_id=source_message_id)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON artifact must be an object")

    planned_files = _string_list(payload, "planned_files")
    non_goals = _string_list(payload, "non_goals")
    constraints = _string_list(payload, "constraints")
    verification = _string_list(payload, "verification")
    slices = _parse_artifact_slices(payload.get("slices"))

    return build_plan_artifact(
        str(payload.get("goal", planning_request)).strip(),
        summary=str(payload.get("summary", "")).strip(),
        plan_id=str(payload.get("plan_id", "")).strip(),
        revision=_int_value(payload.get("revision"), default=1),
        source_message_id=str(payload.get("source_message_id", "") or source_message_id).strip(),
        created_at=str(payload.get("created_at", "")).strip(),
        confirmed_at=str(payload.get("confirmed_at", "")).strip(),
        planned_files=planned_files,
        non_goals=non_goals,
        constraints=constraints,
        slices=slices,
        current_slice_id=str(payload.get("current_slice_id", "")).strip(),
        current_step=str(payload.get("current_step", "")).strip(),
        verification=verification,
    )


def _string_list(payload: dict[str, object], key: str) -> tuple[str, ...]:
    if key not in payload:
        return ()
    value = payload.get(key, ())
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return tuple(str(item) for item in value)


def _parse_artifact_slices(value: object) -> tuple[PlanArtifactSlice, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("slices must be a list")
    slices: list[PlanArtifactSlice] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"slices[{index}] must be an object")
        files_value = item.get("files", ())
        if files_value is None:
            files = ()
        elif isinstance(files_value, list):
            files = tuple(str(file_item) for file_item in files_value)
        else:
            raise ValueError(f"slices[{index}].files must be a list")
        slices.append(
            PlanArtifactSlice(
                id=str(item.get("id", "")).strip(),
                purpose=str(item.get("purpose", "")).strip(),
                files=files,
                check=str(item.get("check", "")).strip(),
            )
        )
    return tuple(slices)


def _int_value(value: object, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("revision must be an integer") from exc


def _latest_assistant_message_id(agent: Agent) -> str:
    for message in reversed(agent.state.messages):
        if message.get("role") == "assistant":
            return str(message.get("id", ""))
    return ""


def _run_tool_command(agent: Agent, prompt: str) -> None:
    try:
        _, name, raw = prompt.split(" ", 2)
        args = json.loads(raw)
    except ValueError:
        print("Usage: /tool NAME JSON")
        return
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}")
        return
    result = agent.run_local_tool(name, args)
    print(ui.tool_status(name, result.success))
    if not result.success and result.display_summary:
        print(ui.error(_indent_block(result.display_summary)))
    print(result.content)


def _indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())

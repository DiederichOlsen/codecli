from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from . import ui
from .agent import Agent
from .cli_common import indent_block, print_missing_api_key
from .cli_plan_task import handle_plan_review_message, next_status_action, run_plan_task_command
from .cli_session import run_session_command
from .config import Config
from .design_trace import format_design_index, format_test_intent_map
from .plan_export import print_mental_model
from .storage import TranscriptStore
from .verification import VerificationPolicy

# Backward-compatible internal imports for existing tests and local scripts.
_handle_plan_review_message = handle_plan_review_message
_print_mental_model = print_mental_model
_print_missing_api_key = print_missing_api_key
_run_plan_task_command = run_plan_task_command
_run_session_command = run_session_command


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
            print_missing_api_key(config)
            return 2
        agent.ask(" ".join(args.prompt))
        store.save_state(agent.state)
        return 0

    print("pyagent prototype")
    print(f"session: {agent.state.session_id}")
    print("Commands: /help, /status, /design, /intent, /mental-model, /plan-task draft REQUEST, /plan-task show, /compact, /sessions, /session load ID, /tool NAME JSON, /exit")
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
            _print_status(agent, config)
            continue
        if prompt == "/design":
            print(format_design_index())
            continue
        if prompt == "/intent":
            print(format_test_intent_map())
            continue
        if prompt == "/mental-model":
            print_mental_model(agent)
            continue
        if prompt.startswith("/plan-task "):
            run_plan_task_command(agent, config, prompt)
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
            run_session_command(agent, store, prompt)
            continue
        if prompt.startswith("/tool "):
            _run_tool_command(agent, prompt)
            store.save_state(agent.state)
            continue
        if handle_plan_review_message(agent, config, store, prompt):
            continue
        if not config.api_key:
            print_missing_api_key(config)
            continue
        agent.ask(prompt)
        store.save_state(agent.state)


def _print_help() -> None:
    print(
        """Available commands:
  /status                 Show current session settings.
  /design                 Show the Design Trace index.
  /intent                 Show which tests protect which design intents.
  /mental-model           Show the current user-facing MaintenanceDigest.
  /plan-task draft TEXT   Draft IntentModel and PlanContract without executing.
  /plan-task show         Show the current plan and mental model.
  /plan-task export       Export the current plan view to .pyagent/plans/.
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


def _print_status(agent: Agent, config: Config) -> None:
    print(f"cwd: {config.cwd}")
    print(f"model: {config.model}")
    print(f"base_url: {config.base_url}")
    print(f"permission_mode: {config.permission_mode}")
    print(f"color: {config.color}")
    print(f"state_schema_version: {agent.state.state_schema_version}")
    print(f"state_revision: {agent.state.state_revision}")
    print(f"compact_epoch: {agent.state.compact_epoch}")
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
    if agent.state.maintenance_digest:
        digest = agent.state.maintenance_digest
        print(
            "maintenance_digest: "
            f"{digest.get('digest_id', '(unknown)')} "
            f"rev={digest.get('revision', '(unknown)')} "
            f"updated_at={digest.get('updated_at', '(unknown)')}"
        )
    if agent.state.context_boundaries:
        boundary = agent.state.context_boundaries[-1]
        print(
            "last_context_boundary: "
            f"epoch={boundary.get('compact_epoch', '(unknown)')} "
            f"plan={boundary.get('plan_id') or 'none'} "
            f"digest={boundary.get('digest_id') or 'none'}"
        )
    if agent.state.plan_artifact_candidate:
        print("plan_artifact_candidate:")
        print(indent_block(json.dumps(agent.state.plan_artifact_candidate, ensure_ascii=False)))
    if agent.state.maintenance_digest_candidate:
        print("maintenance_digest_candidate:")
        print(indent_block(json.dumps(agent.state.maintenance_digest_candidate, ensure_ascii=False)))
    if agent.state.locked_plan:
        print("locked_plan:")
        print(indent_block(json.dumps(agent.state.locked_plan, ensure_ascii=False)))
    if agent.state.planned_files:
        print("planned_files:")
        for path in agent.state.planned_files:
            print(f"  - {path}")
    if agent.state.deviations:
        print(f"deviations: {len(agent.state.deviations)}")
    print(VerificationPolicy().format_status(agent.state))
    print(f"next: {next_status_action(agent.state)}")


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
        print(ui.error(indent_block(result.display_summary)))
    print(result.content)


if __name__ == "__main__":
    raise SystemExit(main())

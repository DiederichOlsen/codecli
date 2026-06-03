from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .agent import Agent
from .config import Config
from .storage import TranscriptStore


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code inspired Python coding agent prototype.")
    parser.add_argument("prompt", nargs="*", help="Prompt to run once. If omitted, starts interactive mode.")
    parser.add_argument("--cwd", default=".", help="Workspace directory.")
    parser.add_argument("--model", help="Model name, for example deepseek-chat or qwen-plus.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL.")
    parser.add_argument("--api-key", help="API key. Prefer PYAGENT_API_KEY.")
    parser.add_argument("--permission-mode", choices=["default", "plan", "accept_edits", "bypass"], help="Permission mode.")
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
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)

    store = TranscriptStore(config.config_dir)
    if args.list_sessions:
        for item in store.list_sessions():
            print(json.dumps(item, ensure_ascii=False))
        return 0

    state = store.load(args.resume) if args.resume else None
    agent = Agent(config=config, state=state, interactive=True)
    if args.prompt:
        agent.ask(" ".join(args.prompt))
        return 0

    print("pyagent prototype")
    print(f"session: {agent.state.session_id}")
    print("Commands: /help, /status, /compact, /sessions, /tool NAME JSON, /exit")
    while True:
        try:
            prompt = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return 0
        if prompt == "/help":
            _print_help()
            continue
        if prompt == "/status":
            print(f"cwd: {config.cwd}")
            print(f"model: {config.model}")
            print(f"base_url: {config.base_url}")
            print(f"permission_mode: {config.permission_mode}")
            print(f"messages: {len(agent.state.messages)}")
            print(f"todos: {agent.state.todos}")
            print(f"file_snapshots: {len(agent.state.file_snapshots)}")
            continue
        if prompt == "/compact":
            changed = agent.compact_now()
            print("context compacted" if changed else "nothing to compact yet")
            continue
        if prompt == "/sessions":
            for item in store.list_sessions():
                print(json.dumps(item, ensure_ascii=False))
            continue
        if prompt.startswith("/tool "):
            _run_tool_command(agent, prompt)
            continue
        agent.ask(prompt)


def _print_help() -> None:
    print(
        """Available commands:
  /status                 Show current session settings.
  /compact                Summarize older context locally.
  /sessions               List saved sessions.
  /tool NAME JSON         Run a local tool directly, e.g. /tool Glob {"pattern":"**/*.py"}
  /exit                   Exit.

Environment:
  PYAGENT_API_KEY         API key.
  PYAGENT_BASE_URL        OpenAI-compatible base URL.
  PYAGENT_MODEL           Model name.

Provider examples:
  DeepSeek base URL: https://api.deepseek.com/v1
  Qwen/DashScope compatible URL: https://dashscope.aliyuncs.com/compatible-mode/v1
"""
    )


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
    print(result.content)


if __name__ == "__main__":
    raise SystemExit(main())

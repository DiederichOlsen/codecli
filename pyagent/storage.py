from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .messages import AgentState, Message


class TranscriptStore:
    def __init__(self, config_dir: Path) -> None:
        self.root = config_dir / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def messages_path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.messages.json"

    def state_path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.state.json"

    def append(self, session_id: str, message: Message) -> None:
        path = self.path_for(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def load(self, session_id: str) -> AgentState:
        state = AgentState(session_id=session_id)
        if self._load_message_snapshot(state):
            self._load_state_snapshot(state)
            return state
        path = self.path_for(session_id)
        if not path.exists():
            self._load_state_snapshot(state)
            return state
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                state.messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._load_state_snapshot(state)
        return state

    def has_message_snapshot(self, session_id: str) -> bool:
        return self.messages_path_for(session_id).exists()

    def save_messages(self, state: AgentState) -> None:
        snapshot = {
            "messages": state.messages,
        }
        path = self.messages_path_for(state.session_id)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_state(self, state: AgentState) -> None:
        snapshot = {
            "planning_status": state.planning_status,
            "planning_request": state.planning_request,
            "current_goal": state.current_goal,
            "current_plan_summary": state.current_plan_summary,
            "current_step": state.current_step,
            "current_slice_id": state.current_slice_id,
            "planned_files": state.planned_files,
            "plan_artifact_candidate": state.plan_artifact_candidate,
            "locked_plan": state.locked_plan,
            "deviations": state.deviations,
            "todos": state.todos,
            "changed_files": state.changed_files,
            "verification_commands": state.verification_commands,
        }
        path = self.state_path_for(state.session_id)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _load_message_snapshot(self, state: AgentState) -> bool:
        path = self.messages_path_for(state.session_id)
        if not path.exists():
            return False
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if not isinstance(snapshot, dict):
            return False
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return False
        state.messages = [message for message in messages if isinstance(message, dict)]
        return True

    def _load_state_snapshot(self, state: AgentState) -> None:
        path = self.state_path_for(state.session_id)
        if not path.exists():
            return
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(snapshot, dict):
            return
        for field in (
            "planning_status",
            "planning_request",
            "current_goal",
            "current_plan_summary",
            "current_step",
            "current_slice_id",
        ):
            value = snapshot.get(field)
            if isinstance(value, str):
                setattr(state, field, value)
        for field in ("planned_files", "deviations", "todos", "changed_files", "verification_commands"):
            value = snapshot.get(field)
            if isinstance(value, list):
                setattr(state, field, value)
        plan_artifact_candidate = snapshot.get("plan_artifact_candidate")
        if isinstance(plan_artifact_candidate, dict):
            state.plan_artifact_candidate = plan_artifact_candidate
        locked_plan = snapshot.get("locked_plan")
        if isinstance(locked_plan, dict):
            state.locked_plan = locked_plan

    def list_sessions(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted(self.root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            result.append(
                {
                    "session_id": path.stem,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "mtime": path.stat().st_mtime,
                }
            )
        return result


class RuntimeTraceStore:
    """Append-only JSONL audit trace for local runtime events."""

    def __init__(self, config_dir: Path) -> None:
        self.root = config_dir / "audit"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def append(self, session_id: str, event: dict[str, Any]) -> None:
        item = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            **event,
        }
        path = self.path_for(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

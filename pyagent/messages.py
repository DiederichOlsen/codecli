from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4


Message = dict[str, Any]


def new_id() -> str:
    return str(uuid4())


def user_message(content: str) -> Message:
    return {"id": new_id(), "role": "user", "content": content}


def system_message(content: str) -> Message:
    return {"id": new_id(), "role": "system", "content": content}


def assistant_message(content: Optional[str], tool_calls: Optional[list[dict[str, Any]]] = None) -> Message:
    msg: Message = {"id": new_id(), "role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def tool_message(tool_call_id: str, name: str, content: str) -> Message:
    return {
        "id": new_id(),
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": content,
    }


@dataclass
class AgentState:
    messages: list[Message] = field(default_factory=list)
    todos: list[dict[str, str]] = field(default_factory=list)
    file_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    planning_status: str = "idle"
    planning_request: str = ""
    current_goal: str = ""
    current_plan_summary: str = ""
    current_step: str = ""
    current_slice_id: str = ""
    planned_files: list[str] = field(default_factory=list)
    plan_artifact_candidate: dict[str, Any] = field(default_factory=dict)
    locked_plan: dict[str, Any] = field(default_factory=dict)
    deviations: list[dict[str, Any]] = field(default_factory=list)
    # Verification state stays JSON-compatible for transcript replay and Rust migration.
    changed_files: list[dict[str, Any]] = field(default_factory=list)
    verification_commands: list[dict[str, Any]] = field(default_factory=list)
    session_id: str = field(default_factory=new_id)

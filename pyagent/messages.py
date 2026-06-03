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
    # 记录 Read 后的文件版本。Edit/Write 会用它检测“读后被外部修改”的情况。
    file_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    session_id: str = field(default_factory=new_id)

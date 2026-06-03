from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .messages import AgentState, Message


class TranscriptStore:
    def __init__(self, config_dir: Path) -> None:
        self.root = config_dir / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def append(self, session_id: str, message: Message) -> None:
        path = self.path_for(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def load(self, session_id: str) -> AgentState:
        state = AgentState(session_id=session_id)
        path = self.path_for(session_id)
        if not path.exists():
            return state
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                state.messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return state

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

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG_DIR = ".pyagent"


@dataclass
class Config:
    cwd: Path
    config_dir: Path
    api_key: str
    base_url: str
    model: str
    permission_mode: str
    max_agent_turns: int
    command_timeout: int
    max_tool_output_chars: int

    @classmethod
    def load(
        cls,
        cwd: Path,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        permission_mode: Optional[str] = None,
    ) -> "Config":
        config_dir = cwd / DEFAULT_CONFIG_DIR
        file_config = _read_json(config_dir / "config.json")
        env = os.environ
        return cls(
            cwd=cwd,
            config_dir=config_dir,
            api_key=api_key or env.get("PYAGENT_API_KEY") or env.get("OPENAI_API_KEY") or file_config.get("api_key", ""),
            base_url=(
                base_url
                or env.get("PYAGENT_BASE_URL")
                or file_config.get("base_url")
                or "https://api.deepseek.com/v1"
            ).rstrip("/"),
            model=model or env.get("PYAGENT_MODEL") or file_config.get("model") or "deepseek-chat",
            permission_mode=permission_mode or env.get("PYAGENT_PERMISSION_MODE") or file_config.get("permission_mode") or "default",
            max_agent_turns=int(env.get("PYAGENT_MAX_AGENT_TURNS") or file_config.get("max_agent_turns") or 8),
            command_timeout=int(env.get("PYAGENT_COMMAND_TIMEOUT") or file_config.get("command_timeout") or 30),
            max_tool_output_chars=int(
                env.get("PYAGENT_MAX_TOOL_OUTPUT_CHARS")
                or file_config.get("max_tool_output_chars")
                or 20000
            ),
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

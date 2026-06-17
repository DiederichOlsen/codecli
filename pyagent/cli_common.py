from __future__ import annotations

from .config import Config
from . import ui


def print_missing_api_key(config: Config) -> None:
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


def indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())

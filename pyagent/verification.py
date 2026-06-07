from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationSummary:
    status: str
    changed_files: int
    commands: int


class VerificationPolicy:
    """Tracks whether local code changes have been verified.

    The state is stored as JSON-compatible dicts on AgentState so transcripts
    and a future Rust core can share the same contract.
    """

    def record_file_change(self, state: Any, *, path: Path, operation: str) -> None:
        entry = {
            "file_path": str(path),
            "operation": operation,
            "changed": True,
        }
        if entry not in state.changed_files:
            state.changed_files.append(entry)

    def maybe_record_command(
        self,
        state: Any,
        *,
        command: str,
        exit_code: int | str,
        success: bool,
        summary: str,
    ) -> bool:
        if not is_verification_command(command):
            return False
        state.verification_commands.append(
            {
                "command": command,
                "exit_code": exit_code,
                "success": success,
                "summary": summary[:2000],
            }
        )
        return True

    def summarize(self, state: Any) -> VerificationSummary:
        return VerificationSummary(
            status=self.status(state),
            changed_files=len(state.changed_files),
            commands=len(state.verification_commands),
        )

    def status(self, state: Any) -> str:
        if not state.changed_files:
            return "not_required"
        if not state.verification_commands:
            return "unverified"
        if any(not command.get("success") for command in state.verification_commands):
            return "failed"
        return "passed"

    def format_status(self, state: Any) -> str:
        summary = self.summarize(state)
        lines = [
            "verification",
            f"  status: {summary.status}",
            f"  changed_files: {summary.changed_files}",
            f"  verification_commands: {summary.commands}",
        ]
        for item in state.changed_files[-10:]:
            lines.append(f"  - changed: {item['operation']} {item['file_path']}")
        for item in state.verification_commands[-10:]:
            label = "ok" if item.get("success") else "failed"
            lines.append(f"  - {label}: {item.get('command')} (exit_code={item.get('exit_code')})")
        return "\n".join(lines)


def is_verification_command(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip().lower())
    if not normalized:
        return False
    unquoted = normalized.replace('"', "").replace("'", "")
    if _matches_python_module_check(unquoted, "unittest") or _matches_python_module_check(unquoted, "compileall"):
        return True
    prefixes = (
        "pytest",
        "python -m unittest",
        "python.exe -m unittest",
        "python -m compileall",
        "python.exe -m compileall",
        "npm test",
        "npm run test",
        "pnpm test",
        "pnpm run test",
        "yarn test",
        "cargo test",
        "cargo check",
        "go test",
        "mypy",
        "ruff check",
        "eslint",
        "tsc",
    )
    return any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes)


def _matches_python_module_check(command: str, module: str) -> bool:
    pattern = rf"(^|[\\/ ])python(\.exe)? -m {re.escape(module)}($| )"
    return re.search(pattern, command) is not None

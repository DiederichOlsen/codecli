from __future__ import annotations

import locale
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolResult, truncate_output
from ..verification import VerificationPolicy


_VERIFICATION_POLICY = VerificationPolicy()


class BashTool:
    name = "Bash"
    description = "Run a shell command in the current workspace."
    read_only = False
    concurrency_safe = False
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "description": "Optional timeout in seconds."},
        },
        "required": ["command"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        timeout = int(args.get("timeout") or ctx.command_timeout)
        command = str(args["command"])
        env = os.environ.copy()
        # Windows 终端常见默认编码是 gbk/cp936。这里让 Python 子进程优先用 UTF-8，
        # 避免 `print("... ✓")` 这类验证命令因为 stdout 编码失败。
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        python_dir = str(Path(sys.executable).resolve().parent)
        env["PATH"] = python_dir + os.pathsep + env.get("PATH", "")
        try:
            proc = subprocess.run(
                command,
                cwd=str(ctx.cwd),
                shell=True,
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _decode_output(exc.stdout or b"")
            stderr = _decode_output(exc.stderr or b"")
            content = _format_output(
                exit_code="timeout",
                stdout=stdout,
                stderr=stderr or f"Command timed out after {timeout}s.",
            )
            _VERIFICATION_POLICY.maybe_record_command(
                ctx.state,
                command=command,
                exit_code="timeout",
                success=False,
                summary=stderr or stdout or f"Command timed out after {timeout}s.",
            )
            return ToolResult(
                truncate_output(content, ctx.max_output_chars),
                success=False,
                display_summary=_build_failure_summary(stderr or stdout or f"Command timed out after {timeout}s."),
            )
        stdout = _decode_output(proc.stdout)
        stderr = _decode_output(proc.stderr)
        output = [
            f"exit_code: {proc.returncode}",
            "",
            "stdout:",
            stdout,
            "",
            "stderr:",
            stderr,
        ]
        success = proc.returncode == 0
        summary = _build_failure_summary(stderr or stdout)
        if not success and not summary:
            summary = f"Command failed with exit_code: {proc.returncode} and produced no output."
        _VERIFICATION_POLICY.maybe_record_command(
            ctx.state,
            command=command,
            exit_code=proc.returncode,
            success=success,
            summary=summary or stdout,
        )
        return ToolResult(
            truncate_output("\n".join(output), ctx.max_output_chars),
            success=success,
            display_summary="" if success else summary,
        )


def _format_output(*, exit_code: str, stdout: str, stderr: str) -> str:
    return "\n".join(
        [
            f"exit_code: {exit_code}",
            "",
            "stdout:",
            stdout,
            "",
            "stderr:",
            stderr,
        ]
    )


def _decode_output(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _build_failure_summary(text: str, *, max_lines: int = 12, max_chars: int = 2000) -> str:
    text = text.strip()
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    summary = "\n".join(lines[-max_lines:])
    if len(summary) > max_chars:
        summary = summary[-max_chars:]
    return summary

from __future__ import annotations

import subprocess
from typing import Any

from .base import ToolContext, ToolResult, truncate_output


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
        try:
            proc = subprocess.run(
                command,
                cwd=str(ctx.cwd),
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(f"Command timed out after {timeout}s.\n{exc}", success=False)
        output = [
            f"exit_code: {proc.returncode}",
            "",
            "stdout:",
            proc.stdout or "",
            "",
            "stderr:",
            proc.stderr or "",
        ]
        return ToolResult(truncate_output("\n".join(output), ctx.max_output_chars), success=proc.returncode == 0)

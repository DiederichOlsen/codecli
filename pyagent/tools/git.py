from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolResult, truncate_output


class GitStatusTool:
    name = "GitStatus"
    description = "Show concise git status and current branch for the workspace."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        result = _run_git(ctx, ["status", "--short", "--branch"])
        return ToolResult(truncate_output(result, ctx.max_output_chars))


class GitDiffTool:
    name = "GitDiff"
    description = "Show git diff for the workspace, optionally scoped to one path."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional workspace-relative path."},
            "staged": {"type": "boolean", "description": "Show staged diff instead of working tree diff."},
            "stat": {"type": "boolean", "description": "Show --stat summary instead of full diff."},
        },
        "required": [],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = ["diff"]
        if bool(args.get("staged")):
            command.append("--cached")
        if bool(args.get("stat")):
            command.append("--stat")
        path = str(args.get("path") or "").strip()
        if path:
            rel = _safe_relative_path(ctx.cwd, path)
            if rel is None:
                return ToolResult("GitDiff error: path must stay inside workspace.", success=False)
            command.extend(["--", rel])
        result = _run_git(ctx, command)
        return ToolResult(truncate_output(result or "(no diff)", ctx.max_output_chars))


class GitBlameTool:
    name = "GitBlame"
    description = "Show git blame for a workspace file, optionally scoped to a line range."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "line_start": {"type": "integer"},
            "line_end": {"type": "integer"},
        },
        "required": ["file_path"],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rel = _safe_relative_path(ctx.cwd, str(args["file_path"]))
        if rel is None:
            return ToolResult("GitBlame error: file_path must stay inside workspace.", success=False)
        command = ["blame", "--date=short"]
        start = args.get("line_start")
        end = args.get("line_end")
        if start is not None or end is not None:
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                return ToolResult("GitBlame error: line_start and line_end must form a valid positive range.", success=False)
            command.extend(["-L", f"{start},{end}"])
        command.extend(["--", rel])
        result = _run_git(ctx, command)
        return ToolResult(truncate_output(result, ctx.max_output_chars))


def _run_git(ctx: ToolContext, command: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *command],
            cwd=str(ctx.cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=ctx.command_timeout,
        )
    except FileNotFoundError:
        return "git is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return f"git {' '.join(command)} timed out after {ctx.command_timeout}s."
    output = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    if proc.returncode != 0:
        return output or f"git {' '.join(command)} failed with exit_code {proc.returncode}."
    return output


def _safe_relative_path(cwd: Path, path: str) -> str | None:
    try:
        full = (cwd / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        rel = full.relative_to(cwd.resolve())
    except (OSError, ValueError):
        return None
    return rel.as_posix()

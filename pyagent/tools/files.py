from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .. import ui
from .base import ToolContext, ToolResult, truncate_output
from .edit_policy import EditPolicy
from ..verification import VerificationPolicy


_EDIT_POLICY = EditPolicy()
_VERIFICATION_POLICY = VerificationPolicy()


class ReadTool:
    name = "Read"
    description = "Read a text file from the current workspace, optionally by line range."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to read."},
            "offset": {"type": "integer", "description": "1-based line number to start reading from."},
            "limit": {"type": "integer", "description": "Number of lines to read."},
        },
        "required": ["file_path"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(ctx.cwd, args["file_path"])
        if not path.exists():
            return ToolResult(f"Error: file does not exist: {path}", success=False)

        text = _EDIT_POLICY.read_text(path)
        lines = text.splitlines()
        offset = int(args.get("offset") or 1)
        limit = args.get("limit")
        start = max(offset - 1, 0)
        end = start + int(limit) if limit else None
        selected = lines[start:end]

        partial = start > 0 or (end is not None and end < len(lines))
        _EDIT_POLICY.record_read(ctx, path, partial=partial)

        numbered = "\n".join(f"{idx + start + 1:>6} | {line}" for idx, line in enumerate(selected))
        return ToolResult(truncate_output(numbered, ctx.max_output_chars))


class WriteTool:
    name = "Write"
    description = "Write a text file in the current workspace."
    read_only = False
    concurrency_safe = False
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["file_path", "content"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(ctx.cwd, args["file_path"])
        precondition = _EDIT_POLICY.validate_write_precondition(ctx, path)
        if precondition:
            return ToolResult(precondition, success=False)

        before = _EDIT_POLICY.read_text(path) if path.exists() else ""
        after = _EDIT_POLICY.adapt_replacement_to_file(path, str(args["content"]))
        if before == after:
            return ToolResult("Write skipped: file content is already identical.")

        diff = _build_diff(path, before, after)
        if _requires_diff_confirmation(ctx):
            if not ctx.interactive:
                return ToolResult(
                    "Write cancelled: this permission mode requires interactive diff confirmation.",
                    success=False,
                )
            if not _confirm_change("Write preview", path, diff, ctx):
                return ToolResult("Write rejected by user. File was not changed.", success=False)

        _EDIT_POLICY.write_text(path, after)
        _EDIT_POLICY.record_read(ctx, path, partial=False)
        _VERIFICATION_POLICY.record_file_change(ctx.state, path=path, operation="write")
        return ToolResult(truncate_output(f"Wrote {path}\n\n{diff}", ctx.max_output_chars))


class EditTool:
    name = "Edit"
    description = "Edit a file by replacing old_string with new_string."
    read_only = False
    concurrency_safe = False
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(ctx.cwd, args["file_path"])
        old = _EDIT_POLICY.adapt_replacement_to_file(path, str(args["old_string"]))
        new = _EDIT_POLICY.adapt_replacement_to_file(path, str(args["new_string"]))
        replace_all = bool(args.get("replace_all", False))

        if old == new:
            return ToolResult("Error: old_string and new_string are identical.", success=False)

        if not path.exists():
            if old != "":
                return ToolResult(f"Error: file does not exist: {path}", success=False)
            before = ""
        else:
            precondition = _EDIT_POLICY.validate_write_precondition(ctx, path)
            if precondition:
                return ToolResult(precondition, success=False)
            before = _EDIT_POLICY.read_text(path)

        count = before.count(old)
        if old and count == 0:
            return ToolResult("Error: old_string was not found in the file.", success=False)
        if old and count > 1 and not replace_all:
            return ToolResult(
                f"Error: old_string appears {count} times. Set replace_all=true or provide more context.",
                success=False,
            )

        after = before.replace(old, new) if replace_all else before.replace(old, new, 1)
        diff = _build_diff(path, before, after)
        if not diff:
            return ToolResult("Error: edit produced no visible changes.", success=False)

        if _requires_diff_confirmation(ctx):
            if not ctx.interactive:
                return ToolResult(
                    "Edit cancelled: this permission mode requires interactive diff confirmation.",
                    success=False,
                )
            if not _confirm_change("Edit preview", path, diff, ctx):
                return ToolResult("Edit rejected by user. File was not changed.", success=False)

        _EDIT_POLICY.write_text(path, after)
        _EDIT_POLICY.record_read(ctx, path, partial=False)
        _VERIFICATION_POLICY.record_file_change(ctx.state, path=path, operation="edit")
        return ToolResult(truncate_output(f"Edited {path}\n\n{diff}", ctx.max_output_chars))


def _resolve(cwd: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


def _requires_diff_confirmation(ctx: ToolContext) -> bool:
    return ctx.permission_mode not in {"accept_edits", "bypass"}


def _confirm_change(title: str, path: Path, diff: str, ctx: ToolContext) -> bool:
    # The permission layer sees JSON arguments; the user needs the concrete disk diff.
    print(f"\n{title}")
    print(f"File: {path}")
    print("-" * 72)
    print(ui.diff(truncate_output(diff, min(ctx.max_output_chars, 12000))))
    print("-" * 72)
    answer = input("Apply this change? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _build_diff(path: Path, before: str, after: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
            lineterm="",
        )
    )

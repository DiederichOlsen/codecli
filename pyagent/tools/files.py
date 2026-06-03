from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any, Optional

from .base import ToolContext, ToolResult, truncate_output


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
        text = path.read_text(encoding="utf-8", errors="replace")
        _record_snapshot(ctx, path)
        lines = text.splitlines()
        offset = int(args.get("offset") or 1)
        limit = args.get("limit")
        start = max(offset - 1, 0)
        selected = lines[start : start + int(limit)] if limit else lines[start:]
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
        stale = _check_stale_snapshot(ctx, path)
        if stale:
            return ToolResult(stale, success=False)
        before = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        after = str(args["content"])
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after, encoding="utf-8")
        _record_snapshot(ctx, path)
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
        old = str(args["old_string"])
        new = str(args["new_string"])
        replace_all = bool(args.get("replace_all", False))
        if old == new:
            return ToolResult("Error: old_string and new_string are identical.", success=False)
        if not path.exists():
            if old != "":
                return ToolResult(f"Error: file does not exist: {path}", success=False)
            before = ""
        else:
            stale = _check_stale_snapshot(ctx, path)
            if stale:
                return ToolResult(stale, success=False)
            before = path.read_text(encoding="utf-8", errors="replace")
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

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after, encoding="utf-8")
        _record_snapshot(ctx, path)
        return ToolResult(truncate_output(f"Edited {path}\n\n{diff}", ctx.max_output_chars))


def _resolve(cwd: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


def _requires_diff_confirmation(ctx: ToolContext) -> bool:
    return ctx.permission_mode not in {"accept_edits", "bypass"}


def _confirm_change(title: str, path: Path, diff: str, ctx: ToolContext) -> bool:
    """展示真实 diff 并等待用户确认。

    这是刻意放在工具内部完成的：权限层只能看到模型给出的 JSON 参数，
    而用户真正需要确认的是“将要写入磁盘的具体变化”。
    """
    print(f"\n{title}")
    print(f"File: {path}")
    print("-" * 72)
    print(truncate_output(diff, min(ctx.max_output_chars, 12000)))
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


def _record_snapshot(ctx: ToolContext, path: Path) -> None:
    snapshot = _snapshot(path)
    if snapshot is not None:
        ctx.state.file_snapshots[str(path.resolve())] = snapshot


def _check_stale_snapshot(ctx: ToolContext, path: Path) -> Optional[str]:
    """检测文件是否在 Read 之后被外部修改。

    Claude Code 的文件工具会尽量避免“基于旧上下文写文件”。这里用一个
    简化版：如果当前会话读过该文件，就在写入前比较 mtime/size/sha256。
    """
    key = str(path.resolve())
    previous = ctx.state.file_snapshots.get(key)
    if previous is None or not path.exists():
        return None
    current = _snapshot(path)
    if current is None or current == previous:
        return None
    return (
        "Error: file changed since it was last read in this session. "
        "Read the file again before editing or writing it."
    )


def _snapshot(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = path.read_bytes()
        stat = path.stat()
    except OSError:
        return None
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": hashlib.sha256(data).hexdigest(),
    }

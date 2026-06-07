from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from .base import ToolContext


SNAPSHOT_VERSION = 1


class EditPolicy:
    """File-edit safety rules shared by Read/Edit/Write.

    This module is deliberately data-oriented. The snapshot shape is plain JSON
    so the same contract can be reused by a future Rust implementation.
    """

    def record_read(self, ctx: ToolContext, path: Path, *, partial: bool) -> None:
        snapshot = self.snapshot(path)
        if snapshot is None:
            return
        snapshot["partial_read"] = partial
        ctx.state.file_snapshots[str(path.resolve())] = snapshot

    def validate_write_precondition(self, ctx: ToolContext, path: Path) -> Optional[str]:
        if not path.exists():
            return None

        key = str(path.resolve())
        previous = ctx.state.file_snapshots.get(key)
        if previous is None:
            return "Error: file has not been read yet. Read it before editing or overwriting it."
        if previous.get("partial_read"):
            return "Error: file was only partially read. Read the full file before editing or overwriting it."

        current = self.snapshot(path)
        if current is None or not _snapshots_match(previous, current):
            return (
                "Error: file changed since it was last read in this session. "
                "Read the file again before editing or writing it."
            )
        return None

    def read_text(self, path: Path) -> str:
        return path.read_bytes().decode("utf-8", errors="replace")

    def write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def adapt_replacement_to_file(self, path: Path, text: str) -> str:
        if not path.exists():
            return text
        snapshot = self.snapshot(path)
        ending = (snapshot or {}).get("line_ending", "lf")
        return convert_line_endings(text, str(ending))

    def snapshot(self, path: Path) -> Optional[dict[str, Any]]:
        try:
            data = path.read_bytes()
            stat = path.stat()
        except OSError:
            return None
        text_sample = data[:128 * 1024].decode("utf-8", errors="replace")
        return {
            "version": SNAPSHOT_VERSION,
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "line_ending": detect_line_ending(text_sample),
            "partial_read": False,
        }


def detect_line_ending(text: str) -> str:
    crlf = text.count("\r\n")
    if crlf:
        return "crlf"
    if "\r" in text:
        return "cr"
    return "lf"


def convert_line_endings(text: str, line_ending: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if line_ending == "crlf":
        return normalized.replace("\n", "\r\n")
    if line_ending == "cr":
        return normalized.replace("\n", "\r")
    return normalized


def _snapshots_match(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    keys = ("mtime_ns", "size", "sha256")
    return all(previous.get(key) == current.get(key) for key in keys)

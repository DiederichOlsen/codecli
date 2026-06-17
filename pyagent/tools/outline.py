from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolResult, truncate_output


class FileOutlineTool:
    name = "FileOutline"
    description = "Show a compact symbol outline for one workspace file, especially Python modules."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Workspace-relative file path."},
        },
        "required": ["file_path"],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _safe_file(ctx.cwd, str(args["file_path"]))
        if path is None:
            return ToolResult("FileOutline error: file_path must be a file inside workspace.", success=False)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(f"FileOutline error: {exc}", success=False)

        if path.suffix == ".py":
            content = _python_outline(path, text, ctx.cwd)
        else:
            content = _text_outline(path, text, ctx.cwd)
        return ToolResult(truncate_output(content, ctx.max_output_chars))


def _python_outline(path: Path, text: str, cwd: Path) -> str:
    rel = path.relative_to(cwd).as_posix()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return f"file: {rel}\nsyntax_error: line {exc.lineno}: {exc.msg}"

    imports: list[str] = []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(f"import {alias.name}" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.append(f"from {module} import {', '.join(alias.name for alias in node.names)}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(f"class {node.name}:{node.lineno}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    symbols.append(f"  {prefix} {item.name}:{item.lineno}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            symbols.append(f"{prefix} {node.name}:{node.lineno}")

    lines = [f"file: {rel}"]
    if imports:
        lines.append("imports:")
        lines.extend(f"  - {item}" for item in imports)
    if symbols:
        lines.append("symbols:")
        lines.extend(f"  - {item}" for item in symbols)
    if len(lines) == 1:
        lines.append("(no top-level imports, classes, or functions found)")
    return "\n".join(lines)


def _text_outline(path: Path, text: str, cwd: Path) -> str:
    rel = path.relative_to(cwd).as_posix()
    headings = [
        f"{index}: {line.strip()}"
        for index, line in enumerate(text.splitlines(), start=1)
        if line.lstrip().startswith("#")
    ][:40]
    lines = [f"file: {rel}", "type: plain_text"]
    if headings:
        lines.append("headings:")
        lines.extend(f"  - {item}" for item in headings)
    else:
        lines.append("(no outline available for this file type)")
    return "\n".join(lines)


def _safe_file(cwd: Path, path: str) -> Path | None:
    try:
        full = (cwd / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        full.relative_to(cwd.resolve())
    except (OSError, ValueError):
        return None
    if not full.is_file():
        return None
    return full

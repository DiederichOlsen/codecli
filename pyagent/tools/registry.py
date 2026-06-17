from __future__ import annotations

from typing import Optional

from .base import Tool, tool_schema
from .bash import BashTool
from .files import EditTool, ReadTool, WriteTool
from .git import GitBlameTool, GitDiffTool, GitStatusTool
from .outline import FileOutlineTool
from .project import ProjectTreeTool
from .search import GlobTool, GrepTool
from .todo import TodoWriteTool


def default_tools() -> list[Tool]:
    return [
        ReadTool(),
        GlobTool(),
        GrepTool(),
        EditTool(),
        WriteTool(),
        BashTool(),
        TodoWriteTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitBlameTool(),
        ProjectTreeTool(),
        FileOutlineTool(),
    ]


class ToolRegistry:
    def __init__(self, tools: Optional[list[Tool]] = None) -> None:
        self.tools = tools or default_tools()
        self.by_name = {tool.name: tool for tool in self.tools}

    def schemas(self) -> list[dict]:
        return [tool_schema(tool) for tool in self.tools]

    def names(self) -> list[str]:
        return [tool.name for tool in self.tools]

    def read_only_names(self) -> set[str]:
        return {tool.name for tool in self.tools if tool.read_only}

    def get(self, name: str) -> Optional[Tool]:
        return self.by_name.get(name)

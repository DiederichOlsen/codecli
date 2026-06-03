from __future__ import annotations

import fnmatch
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PermissionDecision:
    behavior: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.behavior == "allow"


class PermissionManager:
    def __init__(self, *, cwd: Path, config_dir: Path, mode: str = "default", interactive: bool = True) -> None:
        self.cwd = cwd.resolve()
        self.config_dir = config_dir
        self.mode = mode
        self.interactive = interactive
        self.rules = self._load_rules()

    def decide(self, tool_name: str, args: dict) -> PermissionDecision:
        explicit = self._match_explicit_rule(tool_name, args)
        if explicit:
            return explicit

        if self.mode == "plan":
            if tool_name in {"Read", "Grep", "Glob", "TodoWrite"}:
                return PermissionDecision("allow", "plan mode read-only tool")
            return PermissionDecision("deny", "plan mode blocks write and shell tools")

        if tool_name == "Read":
            path = Path(str(args.get("file_path", "")))
            if not self.path_is_safe(path):
                return self._ask(tool_name, args, "read path is outside workspace or sensitive")
            return PermissionDecision("allow", "read-only tool")

        if tool_name == "Grep":
            if args.get("path"):
                path = Path(str(args.get("path", "")))
                if not self.path_is_safe(path):
                    return self._ask(tool_name, args, "search path is outside workspace or sensitive")
            return PermissionDecision("allow", "read-only tool")

        if tool_name in {"Glob", "TodoWrite"}:
            return PermissionDecision("allow", "read-only tool")

        if tool_name == "Edit":
            path = Path(str(args.get("file_path", "")))
            if not self.path_is_safe(path):
                return self._ask(tool_name, args, "file path is outside workspace or sensitive")
            if self.mode in {"accept_edits", "bypass"}:
                return PermissionDecision("allow", f"{self.mode} mode allows file edits")
            if not self.interactive:
                return PermissionDecision("deny", "file edit requires interactive diff confirmation")
            # 默认模式下不在这里展示 JSON 确认，交给 Edit 工具展示真实 diff 后再确认。
            return PermissionDecision("allow", "Edit tool will show a diff before writing")

        if tool_name == "Write":
            path = Path(str(args.get("file_path", "")))
            if not self.path_is_safe(path):
                return self._ask(tool_name, args, "file path is outside workspace or sensitive")
            if self.mode in {"accept_edits", "bypass"}:
                return PermissionDecision("allow", f"{self.mode} mode allows file writes")
            if not self.interactive:
                return PermissionDecision("deny", "file write requires interactive diff confirmation")
            return PermissionDecision("allow", "Write tool will show a diff before writing")

        if tool_name == "Bash":
            command = str(args.get("command", ""))
            if self._is_dangerous_command(command):
                return self._ask(tool_name, args, "command looks destructive or privileged")
            if self._is_readonly_command(command) or self.mode == "bypass":
                return PermissionDecision("allow", "safe command prefix")
            return self._ask(tool_name, args, "shell command requires confirmation")

        return self._ask(tool_name, args, "unknown tool requires confirmation")

    def path_is_safe(self, path: Path) -> bool:
        try:
            full = (self.cwd / path).resolve() if not path.is_absolute() else path.resolve()
        except OSError:
            return False
        try:
            full.relative_to(self.cwd)
        except ValueError:
            return False
        lower_parts = {part.lower() for part in full.parts}
        if lower_parts.intersection({".git", ".claude", ".pyagent"}):
            return False
        dangerous_files = {
            ".gitconfig",
            ".gitmodules",
            ".bashrc",
            ".bash_profile",
            ".zshrc",
            ".zprofile",
            ".profile",
            ".mcp.json",
        }
        if full.name.lower() in dangerous_files:
            return False
        return True

    def _ask(self, tool_name: str, args: dict, reason: str) -> PermissionDecision:
        if not self.interactive:
            return PermissionDecision("deny", reason)
        print(f"\nPermission required for {tool_name}: {reason}")
        preview = json.dumps(args, ensure_ascii=False, indent=2)
        print(preview[:2000])
        answer = input("Allow once? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            return PermissionDecision("allow", "approved by user")
        return PermissionDecision("deny", "rejected by user")

    def _load_rules(self) -> dict:
        path = self.config_dir / "permissions.json"
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"allow": [], "deny": []}

    def _match_explicit_rule(self, tool_name: str, args: dict) -> Optional[PermissionDecision]:
        target = self._rule_target(tool_name, args)
        for behavior in ("deny", "allow"):
            for pattern in self.rules.get(behavior, []):
                if fnmatch.fnmatch(target, pattern):
                    return PermissionDecision(behavior, f"matched rule {pattern}")
        return None

    def _rule_target(self, tool_name: str, args: dict) -> str:
        if tool_name == "Bash":
            return f"Bash:{args.get('command', '')}"
        if "file_path" in args:
            return f"{tool_name}:{args.get('file_path', '')}"
        return tool_name

    def _is_readonly_command(self, command: str) -> bool:
        first = _first_word(command)
        if not first:
            return False
        readonly = {
            "ls",
            "dir",
            "pwd",
            "cat",
            "type",
            "head",
            "tail",
            "grep",
            "rg",
            "find",
            "git",
            "python",
            "python3",
            "pytest",
        }
        if first not in readonly:
            return False
        lowered = command.lower()
        if first == "git":
            safe_git = ("git status", "git diff", "git log", "git show", "git branch")
            return lowered.strip().startswith(safe_git)
        return not self._is_dangerous_command(command)

    def _is_dangerous_command(self, command: str) -> bool:
        lowered = command.lower()
        dangerous_fragments = [
            "rm -rf",
            "del /",
            "rmdir /s",
            "git reset --hard",
            "git clean",
            "sudo ",
            "doas ",
            "chmod -r",
            "chown -r",
            "| sh",
            "| bash",
            "curl ",
            "wget ",
            ">",
            ">>",
        ]
        return any(fragment in lowered for fragment in dangerous_fragments)


def _first_word(command: str) -> str:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        parts = command.split()
    return (parts[0].lower() if parts else "").strip()

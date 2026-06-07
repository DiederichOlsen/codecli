from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import ui
from .tools.bash_policy import BashPolicy


@dataclass
class PermissionDecision:
    behavior: str
    reason: str = ""
    policy: str = "PermissionManager"
    classification: str = "unknown"
    risk_tags: list[str] = field(default_factory=list)
    normalized_input: str = ""
    matched_rule: str = ""

    @property
    def allowed(self) -> bool:
        return self.behavior == "allow"

    def to_audit_dict(self) -> dict:
        return {
            "behavior": self.behavior,
            "reason": self.reason,
            "policy": self.policy,
            "classification": self.classification,
            "risk_tags": list(self.risk_tags),
            "normalized_input": self.normalized_input,
            "matched_rule": self.matched_rule,
        }


class PermissionManager:
    def __init__(self, *, cwd: Path, config_dir: Path, mode: str = "default", interactive: bool = True) -> None:
        self.cwd = cwd.resolve()
        self.config_dir = config_dir
        self.mode = mode
        self.interactive = interactive
        self.rules = self._load_rules()
        self.bash_policy = BashPolicy()

    def decide(self, tool_name: str, args: dict) -> PermissionDecision:
        explicit = self._match_explicit_rule(tool_name, args)
        if explicit:
            return explicit

        if self.mode == "plan":
            if tool_name in {"Read", "Grep", "Glob", "TodoWrite"}:
                return PermissionDecision(
                    "allow",
                    "plan mode read-only tool",
                    policy="ModePolicy",
                    classification="readonly",
                    risk_tags=["readonly"],
                    normalized_input=self._rule_target(tool_name, args),
                )
            return PermissionDecision(
                "deny",
                "plan mode blocks write and shell tools",
                policy="ModePolicy",
                classification="blocked_by_mode",
                risk_tags=["mode_restriction"],
                normalized_input=self._rule_target(tool_name, args),
            )

        if tool_name == "Read":
            path = Path(str(args.get("file_path", "")))
            if not self.path_is_safe(path):
                return self._ask(tool_name, args, "read path is outside workspace or sensitive")
            return PermissionDecision(
                "allow",
                "read-only tool",
                policy="FilePathPolicy",
                classification="readonly",
                risk_tags=["readonly"],
                normalized_input=self._normalize_path(path),
            )

        if tool_name == "Grep":
            if args.get("path"):
                path = Path(str(args.get("path", "")))
                if not self.path_is_safe(path):
                    return self._ask(tool_name, args, "search path is outside workspace or sensitive")
            return PermissionDecision(
                "allow",
                "read-only tool",
                policy="FilePathPolicy",
                classification="readonly",
                risk_tags=["readonly"],
                normalized_input=self._rule_target(tool_name, args),
            )

        if tool_name in {"Glob", "TodoWrite"}:
            return PermissionDecision(
                "allow",
                "read-only tool",
                policy="ToolPolicy",
                classification="readonly",
                risk_tags=["readonly"],
                normalized_input=self._rule_target(tool_name, args),
            )

        if tool_name == "Edit":
            path = Path(str(args.get("file_path", "")))
            if not self.path_is_safe(path):
                return self._ask(tool_name, args, "file path is outside workspace or sensitive")
            if self.mode in {"accept_edits", "bypass"}:
                return PermissionDecision(
                    "allow",
                    f"{self.mode} mode allows file edits",
                    policy="ModePolicy",
                    classification="file_write",
                    risk_tags=["filesystem_write"],
                    normalized_input=self._normalize_path(path),
                )
            if not self.interactive:
                return PermissionDecision(
                    "deny",
                    "file edit requires interactive diff confirmation",
                    policy="InteractiveApprovalPolicy",
                    classification="requires_user_confirmation",
                    risk_tags=["filesystem_write", "interactive_required"],
                    normalized_input=self._normalize_path(path),
                )
            # 默认模式下不在这里展示 JSON 确认，交给 Edit 工具展示真实 diff 后再确认。
            return PermissionDecision(
                "allow",
                "Edit tool will show a diff before writing",
                policy="InteractiveApprovalPolicy",
                classification="file_write_with_diff",
                risk_tags=["filesystem_write", "diff_confirmation"],
                normalized_input=self._normalize_path(path),
            )

        if tool_name == "Write":
            path = Path(str(args.get("file_path", "")))
            if not self.path_is_safe(path):
                return self._ask(tool_name, args, "file path is outside workspace or sensitive")
            if self.mode in {"accept_edits", "bypass"}:
                return PermissionDecision(
                    "allow",
                    f"{self.mode} mode allows file writes",
                    policy="ModePolicy",
                    classification="file_write",
                    risk_tags=["filesystem_write"],
                    normalized_input=self._normalize_path(path),
                )
            if not self.interactive:
                return PermissionDecision(
                    "deny",
                    "file write requires interactive diff confirmation",
                    policy="InteractiveApprovalPolicy",
                    classification="requires_user_confirmation",
                    risk_tags=["filesystem_write", "interactive_required"],
                    normalized_input=self._normalize_path(path),
                )
            return PermissionDecision(
                "allow",
                "Write tool will show a diff before writing",
                policy="InteractiveApprovalPolicy",
                classification="file_write_with_diff",
                risk_tags=["filesystem_write", "diff_confirmation"],
                normalized_input=self._normalize_path(path),
            )

        if tool_name == "Bash":
            command = str(args.get("command", ""))
            decision = self.bash_policy.decide(command, mode=self.mode)
            if decision.behavior == "allow":
                return PermissionDecision(
                    "allow",
                    decision.reason,
                    policy="BashPolicy",
                    classification=decision.classification,
                    risk_tags=decision.risk_tags,
                    normalized_input=decision.normalized_command,
                )
            if decision.behavior == "deny":
                return PermissionDecision(
                    "deny",
                    decision.reason,
                    policy="BashPolicy",
                    classification=decision.classification,
                    risk_tags=decision.risk_tags,
                    normalized_input=decision.normalized_command,
                )
            return self._ask(tool_name, args, decision.reason)

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
            return PermissionDecision(
                "deny",
                reason,
                policy="InteractiveApprovalPolicy",
                classification="requires_user_confirmation",
                risk_tags=["interactive_required"],
                normalized_input=self._rule_target(tool_name, args),
            )
        print(ui.warning(f"\nPermission required for {tool_name}: {reason}"))
        preview = json.dumps(args, ensure_ascii=False, indent=2)
        print(preview[:2000])
        answer = input("Allow once? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            return PermissionDecision(
                "allow",
                "approved by user",
                policy="InteractiveApprovalPolicy",
                classification="approved_by_user",
                risk_tags=["user_approved"],
                normalized_input=self._rule_target(tool_name, args),
            )
        return PermissionDecision(
            "deny",
            "rejected by user",
            policy="InteractiveApprovalPolicy",
            classification="rejected_by_user",
            risk_tags=["user_rejected"],
            normalized_input=self._rule_target(tool_name, args),
        )

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
                    return PermissionDecision(
                        behavior,
                        f"matched rule {pattern}",
                        policy="ExplicitRulePolicy",
                        classification=f"explicit_{behavior}",
                        risk_tags=["explicit_rule"],
                        normalized_input=target,
                        matched_rule=pattern,
                    )
        return None

    def _rule_target(self, tool_name: str, args: dict) -> str:
        if tool_name == "Bash":
            return f"Bash:{args.get('command', '')}"
        if "file_path" in args:
            return f"{tool_name}:{args.get('file_path', '')}"
        return tool_name

    def _normalize_path(self, path: Path) -> str:
        try:
            full = (self.cwd / path).resolve() if not path.is_absolute() else path.resolve()
        except OSError:
            return str(path)
        return str(full)

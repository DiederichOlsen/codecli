from __future__ import annotations

import shlex
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BashDecision:
    behavior: str
    reason: str
    classification: str
    risk_tags: list[str] = field(default_factory=list)
    normalized_command: str = ""
    segments: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.behavior == "allow"

    def to_audit_dict(self) -> dict:
        return {
            "behavior": self.behavior,
            "reason": self.reason,
            "classification": self.classification,
            "risk_tags": list(self.risk_tags),
            "normalized_command": self.normalized_command,
            "segments": list(self.segments),
            "operators": list(self.operators),
        }


class BashPolicy:
    """Transparent shell permission policy.

    This is not a full shell parser. It is a conservative classifier with a
    plain-data result so the same contract can later move into Rust.
    """

    def decide(self, command: str, *, mode: str = "default") -> BashDecision:
        command = command.strip()
        pieces = split_command(command)
        if not command:
            return BashDecision("ask", "empty shell command", "unknown", ["empty"], command, [], [])

        dangerous = self._dangerous_finding(command, pieces)
        if dangerous:
            reason, risk_tags = dangerous
            return BashDecision("ask", reason, "dangerous", risk_tags, command, pieces.segments, pieces.operators)

        if self._is_readonly_pieces(pieces):
            return BashDecision(
                "allow",
                "recognized read-only shell command",
                "readonly",
                ["readonly"],
                command,
                pieces.segments,
                pieces.operators,
            )

        if mode == "bypass":
            return BashDecision(
                "allow",
                "bypass mode allows non-dangerous shell command",
                "bypass",
                ["bypass"],
                command,
                pieces.segments,
                pieces.operators,
            )

        return BashDecision(
            "ask",
            "shell command requires confirmation",
            "needs_confirmation",
            ["unknown_shell"],
            command,
            pieces.segments,
            pieces.operators,
        )

    def is_readonly(self, command: str) -> bool:
        pieces = split_command(command)
        return self._is_readonly_pieces(pieces)

    def _is_readonly_pieces(self, pieces: CommandPieces) -> bool:
        if not pieces.segments:
            return False
        if any(op in {">", ">>", "<"} for op in pieces.operators):
            return False
        return all(_is_readonly_segment(segment) for segment in pieces.segments)

    def _dangerous_reason(self, command: str) -> str:
        finding = self._dangerous_finding(command, split_command(command))
        return finding[0] if finding else ""

    def _dangerous_finding(self, command: str, pieces: CommandPieces) -> tuple[str, list[str]] | None:
        lowered = command.lower()
        dangerous_fragments = (
            ("rm -rf", "recursive forced removal", ["filesystem_write", "destructive_delete"]),
            ("del /", "destructive Windows delete", ["filesystem_write", "destructive_delete", "windows_shell"]),
            ("rmdir /s", "recursive Windows directory removal", ["filesystem_write", "destructive_delete", "windows_shell"]),
            ("git reset --hard", "hard git reset", ["git_state", "destructive"]),
            ("git clean", "git clean can remove untracked files", ["git_state", "destructive_delete"]),
            ("sudo ", "privileged command", ["privilege_escalation"]),
            ("doas ", "privileged command", ["privilege_escalation"]),
            ("chmod -r", "recursive permission change", ["permission_change", "filesystem_write"]),
            ("chown -r", "recursive ownership change", ["permission_change", "filesystem_write"]),
            ("| sh", "pipes downloaded or generated code into sh", ["generated_code_execution"]),
            ("| bash", "pipes downloaded or generated code into bash", ["generated_code_execution"]),
            ("| iex", "pipes code into PowerShell Invoke-Expression", ["generated_code_execution", "windows_shell"]),
            ("invoke-expression", "PowerShell Invoke-Expression can execute generated code", ["generated_code_execution", "windows_shell"]),
            (" iwr ", "PowerShell web request may download code", ["network", "windows_shell"]),
            (" invoke-webrequest ", "PowerShell web request may download code", ["network", "windows_shell"]),
            ("curl ", "network download command", ["network"]),
            ("wget ", "network download command", ["network"]),
            ("executionpolicy bypass", "PowerShell execution policy bypass", ["policy_bypass", "windows_shell"]),
            ("start-process", "PowerShell process launch may escape the session", ["process_launch", "windows_shell"]),
            ("-verb runas", "PowerShell elevation request", ["privilege_escalation", "windows_shell"]),
            ("remove-item", "PowerShell destructive remove cmdlet", ["filesystem_write", "destructive_delete", "windows_shell"]),
            ("set-content", "PowerShell file overwrite cmdlet", ["filesystem_write", "windows_shell"]),
            ("clear-content", "PowerShell file truncation cmdlet", ["filesystem_write", "destructive", "windows_shell"]),
            ("out-file", "PowerShell file output cmdlet", ["filesystem_write", "windows_shell"]),
            ("register-scheduledtask", "PowerShell persistence mechanism", ["persistence", "windows_shell"]),
            ("new-service", "PowerShell service creation", ["persistence", "windows_shell"]),
            ("set-mppreference", "PowerShell security configuration change", ["security_config", "windows_shell"]),
        )
        padded = f" {lowered} "
        for fragment, reason, risk_tags in dangerous_fragments:
            if fragment in padded:
                return reason, risk_tags
        if any(op in {">", ">>"} for op in pieces.operators):
            return "shell output redirection can overwrite files", ["filesystem_write", "redirection"]
        return None


@dataclass(frozen=True)
class CommandPieces:
    segments: list[str]
    operators: list[str]


def split_command(command: str) -> CommandPieces:
    segments: list[str] = []
    operators: list[str] = []
    current: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        char = command[i]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            i += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            i += 1
            continue
        two = command[i : i + 2]
        if two in {"&&", "||", ">>"}:
            _push_segment(segments, current)
            operators.append(two)
            i += 2
            continue
        if char in {"|", ";", ">", "<"}:
            _push_segment(segments, current)
            operators.append(char)
            i += 1
            continue
        current.append(char)
        i += 1
    _push_segment(segments, current)
    return CommandPieces(segments=segments, operators=operators)


def _push_segment(segments: list[str], current: list[str]) -> None:
    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    current.clear()


def _is_readonly_segment(segment: str) -> bool:
    parts = _split_words(segment)
    if not parts:
        return False
    first = _normalize_command_name(parts[0])

    if first == "git":
        return _starts_with(segment, ("git status", "git diff", "git log", "git show", "git branch"))
    if first in {"ls", "dir", "pwd", "cat", "type", "head", "tail", "grep", "rg", "find"}:
        return True
    if first in {"get-childitem", "gci", "get-content", "select-string", "where-object"}:
        return True
    if first in {"pytest"}:
        return True
    if first in {"python", "python3", "python.exe"}:
        return _is_safe_python_invocation(parts)
    return False


def _is_safe_python_invocation(parts: list[str]) -> bool:
    if len(parts) < 3 or parts[1] != "-m":
        return False
    module = parts[2]
    return module == "compileall" or module == "unittest"


def _starts_with(command: str, prefixes: tuple[str, ...]) -> bool:
    lowered = command.lower().strip()
    return any(lowered == prefix or lowered.startswith(prefix + " ") for prefix in prefixes)


def _split_words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=False)
    except ValueError:
        return segment.split()


def _normalize_command_name(value: str) -> str:
    return value.strip("\"'").lower()

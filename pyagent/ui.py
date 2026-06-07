from __future__ import annotations

import os
import sys


_COLOR_MODE = "auto"
_ANSI_ENABLED = False

_STYLES = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "blue": "\033[34m",
}
_RESET = "\033[0m"


def configure_color(mode: str = "auto") -> None:
    """配置终端颜色策略。

    这个模块刻意保持很薄：业务层只表达输出类型，不直接拼 ANSI。
    后续 Rust 化时，可以把这些语义映射到 anstyle/owo-colors 等终端库。
    """
    global _COLOR_MODE, _ANSI_ENABLED
    env_mode = os.environ.get("PYAGENT_COLOR")
    if env_mode:
        mode = env_mode
    if os.environ.get("NO_COLOR"):
        mode = "never"
    _COLOR_MODE = mode if mode in {"auto", "always", "never"} else "auto"
    _ANSI_ENABLED = _should_enable_ansi(_COLOR_MODE)


def color(text: str, style: str) -> str:
    if not _ANSI_ENABLED:
        return text
    code = _STYLES.get(style)
    if not code:
        return text
    return f"{code}{text}{_RESET}"


def dim(text: str) -> str:
    return color(text, "dim")


def runtime_header(title: str) -> str:
    return color(f"== {title} ==", "blue")


def event_title(kind: str, name: str) -> str:
    return f"{color(kind, 'cyan')} {color(name, 'bold')}"


def event_line(label: str, value: str = "", *, style: str = "") -> str:
    label_text = color(label, style) if style else label
    if value:
        return f"  - {label_text}: {value}"
    return f"  - {label_text}"


def event_block(title: str, lines: list[str]) -> str:
    if not lines:
        return title
    return "\n".join([title, *lines])


def inline_json(text: str, *, limit: int = 500) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 24] + " ... [truncated]"


def tool_call(name: str, args: str) -> str:
    return event_block(
        event_title("tool", name),
        [event_line("args", inline_json(args), style="dim")],
    )


def tool_status(name: str, success: bool) -> str:
    label = "[tool ok]" if success else "[tool error]"
    style = "green" if success else "red"
    return f"{color(label, style)} {name}"


def warning(text: str) -> str:
    return color(text, "yellow")


def error(text: str) -> str:
    return color(text, "red")


def diff(text: str) -> str:
    if not _ANSI_ENABLED:
        return text
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(("---", "+++", "@@")):
            lines.append(color(line, "cyan"))
        elif line.startswith("+"):
            lines.append(color(line, "green"))
        elif line.startswith("-"):
            lines.append(color(line, "red"))
        else:
            lines.append(line)
    return "\n".join(lines)


def _should_enable_ansi(mode: str) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        _enable_windows_ansi()
        return True
    if not sys.stdout.isatty():
        return False
    _enable_windows_ansi()
    return True


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        return

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from .messages import Message


@dataclass
class ModelResponse:
    content: str
    tool_calls: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass
class ModelStreamEvent:
    type: str
    delta: str = ""
    response: Optional[ModelResponse] = None


class OpenAICompatibleModel:
    """Minimal OpenAI-compatible chat completions client.

    Works with providers that expose /chat/completions using OpenAI-compatible
    message and tool schemas, including DeepSeek and DashScope compatible mode.
    """

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: int = 120) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        if not self.api_key:
            raise RuntimeError(
                "Missing API key. Set PYAGENT_API_KEY, OPENAI_API_KEY, or .pyagent/config.json."
            )

        payload = {
            "model": self.model,
            "messages": [_to_api_message(m) for m in messages],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model API HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Model API connection error: {exc}") from exc

        choice = raw.get("choices", [{}])[0]
        msg = choice.get("message", {}) or {}
        return ModelResponse(
            content=msg.get("content") or "",
            tool_calls=msg.get("tool_calls") or [],
            raw=raw,
        )

    def stream_complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Iterator[ModelStreamEvent]:
        """流式调用模型，同时在本地聚合最终 assistant 消息。

        OpenAI-compatible 的 tool call streaming 是增量格式：同一个工具调用的
        name/arguments 可能被拆成多段。这里把增量统一聚合好，Agent 层只需要
        打印 text delta，并在 done 事件中拿到完整 ModelResponse。
        """
        if not self.api_key:
            raise RuntimeError(
                "Missing API key. Set PYAGENT_API_KEY, OPENAI_API_KEY, or .pyagent/config.json."
            )

        payload = {
            "model": self.model,
            "messages": [_to_api_message(m) for m in messages],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "stream": True,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        content_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, Any]] = {}
        raw_chunks: list[dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    raw_chunks.append(chunk)
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text_delta = delta.get("content")
                    if text_delta:
                        content_parts.append(text_delta)
                        yield ModelStreamEvent(type="text", delta=text_delta)
                    for tool_delta in delta.get("tool_calls") or []:
                        _merge_tool_delta(tool_call_parts, tool_delta)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model API HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Model API connection error: {exc}") from exc

        response = ModelResponse(
            content="".join(content_parts),
            tool_calls=_finalize_tool_calls(tool_call_parts),
            raw={"stream_chunks": raw_chunks},
        )
        yield ModelStreamEvent(type="done", response=response)


def _to_api_message(message: Message) -> dict[str, Any]:
    role = message["role"]
    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message["tool_call_id"],
            "name": message.get("name"),
            "content": message.get("content", ""),
        }
    content = message.get("content", "")
    # Per OpenAI spec: assistant messages with tool_calls should have
    # content=null (not "") when there is no text response.
    if role == "assistant" and message.get("tool_calls") and not content:
        content = None
    result = {"role": role, "content": content}
    if role == "assistant" and message.get("tool_calls"):
        result["tool_calls"] = message["tool_calls"]
    return result


def _merge_tool_delta(parts: dict[int, dict[str, Any]], delta: dict[str, Any]) -> None:
    index = int(delta.get("index") or 0)
    current = parts.setdefault(
        index,
        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
    )
    if delta.get("id"):
        current["id"] += str(delta["id"])
    function = delta.get("function") or {}
    if function.get("name"):
        current["function"]["name"] += str(function["name"])
    if function.get("arguments"):
        current["function"]["arguments"] += str(function["arguments"])


def _finalize_tool_calls(parts: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [parts[index] for index in sorted(parts)]

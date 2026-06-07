from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .executor import ToolExecution, ToolExecutor
from .registry import ToolRegistry


class ToolScheduler:
    """Schedules tool calls with conservative concurrency.

    Consecutive concurrency-safe calls run as one batch. Everything else runs
    serially. This mirrors the important safety rule from Claude Code while
    keeping the implementation easy to audit.
    """

    def __init__(self, *, registry: ToolRegistry, executor: ToolExecutor, max_workers: int = 4) -> None:
        self.registry = registry
        self.executor = executor
        self.max_workers = max_workers

    def run(self, calls: list[dict[str, Any]]) -> list[ToolExecution]:
        results: list[ToolExecution] = []
        for safe, batch in self._partition(calls):
            if safe and len(batch) > 1:
                results.extend(self._run_concurrently(batch))
            else:
                for call in batch:
                    results.append(self.executor.execute_call(call))
        return results

    def _partition(self, calls: list[dict[str, Any]]) -> list[tuple[bool, list[dict[str, Any]]]]:
        batches: list[tuple[bool, list[dict[str, Any]]]] = []
        for call in calls:
            safe = self._is_concurrency_safe(call)
            if safe and batches and batches[-1][0]:
                batches[-1][1].append(call)
            else:
                batches.append((safe, [call]))
        return batches

    def _run_concurrently(self, calls: list[dict[str, Any]]) -> list[ToolExecution]:
        workers = max(1, min(self.max_workers, len(calls)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.executor.execute_call, calls))

    def _is_concurrency_safe(self, call: dict[str, Any]) -> bool:
        func = call.get("function") or {}
        tool = self.registry.get(str(func.get("name") or ""))
        return bool(tool and tool.concurrency_safe)

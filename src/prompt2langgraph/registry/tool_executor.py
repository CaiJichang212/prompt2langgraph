"""Tool executor and callable registry for tool-type nodes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from prompt2langgraph.diagnostics.codes import E_SEC_015
from prompt2langgraph.registry.executors import ExecutorError, ExecutorHandler


class ToolCallableRegistry:
    """Registry of trusted Python callables for tool-type nodes."""

    def __init__(self) -> None:
        self._callables: dict[str, ExecutorHandler] = {}

    def register(self, ref: str, callable: ExecutorHandler) -> None:
        self._callables[ref] = callable

    def get(self, ref: str) -> ExecutorHandler:
        if ref not in self._callables:
            raise KeyError(f"tool callable '{ref}' is not registered")
        return self._callables[ref]

    def has(self, ref: str) -> bool:
        return ref in self._callables

    def refs(self) -> list[str]:
        return sorted(self._callables)


class ToolExecutor:
    """Execute tool-type nodes by invoking a registered callable."""

    def __init__(
        self,
        registry: ToolCallableRegistry,
        tool_ref: str,
        *,
        timeout_s: int = 60,
    ) -> None:
        self._registry = registry
        self._tool_ref = tool_ref
        self._timeout_s = timeout_s

    def __call__(self, inputs: dict, params: dict) -> dict:
        if not self._registry.has(self._tool_ref):
            raise ExecutorError(
                E_SEC_015,
                f"tool ref '{self._tool_ref}' is not registered",
            )
        callable = self._registry.get(self._tool_ref)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(callable, inputs, params)
                return future.result(timeout=self._timeout_s)
        except FuturesTimeoutError as exc:
            raise ExecutorError(
                E_SEC_015,
                f"tool '{self._tool_ref}' timed out after {self._timeout_s}s",
                hint=str(exc),
            ) from exc
        except ExecutorError:
            raise
        except Exception as exc:
            raise ExecutorError(
                E_SEC_015,
                f"tool '{self._tool_ref}' execution failed: {exc}",
                hint=str(exc),
            ) from exc

"""Real LLM executor for llm-type nodes."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from prompt2langgraph.diagnostics.codes import E_LLM_001, E_LLM_002, E_LLM_003
from prompt2langgraph.llm.messages import dict_messages_to_langchain
from prompt2langgraph.registry.executors import ExecutorError


class LLMExecutor:
    """Execute llm-type nodes by invoking a real LLM model client."""

    _metadata_key = "_pt2lg_meta"

    def __init__(self, model_client: BaseChatModel) -> None:
        self._client = model_client

    def __call__(self, inputs: dict, params: dict) -> dict:
        try:
            messages = self._build_messages(inputs, params)
            response = self._client.invoke(messages)
            content = response.content
            if isinstance(content, list):
                content = "".join(str(item) for item in content)
            payload: dict[str, Any] = {"answer": str(content) if content is not None else ""}
            token_count = self._extract_token_count(response)
            if token_count is not None:
                payload["_pt2lg_meta"] = {"token_count": token_count}
            return payload
        except ExecutorError:
            raise
        except TimeoutError as exc:
            raise ExecutorError(E_LLM_001, "LLM call timed out", hint=str(exc)) from exc
        except Exception as exc:
            raise ExecutorError(E_LLM_002, f"LLM API error: {exc}", hint=str(exc)) from exc

    @staticmethod
    def _extract_token_count(response: Any) -> int | None:
        usage_metadata = getattr(response, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            token_count = LLMExecutor._extract_int_from_mapping(usage_metadata)
            if token_count is not None:
                return token_count

        metadata = getattr(response, "response_metadata", None)
        if not isinstance(metadata, dict):
            return None

        usage = metadata.get("token_usage")
        if isinstance(usage, dict):
            token_count = LLMExecutor._extract_int_from_mapping(usage)
            if token_count is not None:
                return token_count

        usage = metadata.get("usage_metadata")
        if isinstance(usage, dict):
            token_count = LLMExecutor._extract_int_from_mapping(usage)
            if token_count is not None:
                return token_count

        token_count = LLMExecutor._extract_int_from_mapping(metadata)
        if token_count is not None:
            return token_count
        return None

    @staticmethod
    def _extract_int_from_mapping(mapping: dict[str, Any]) -> int | None:
        for key in ("token_count", "total_tokens", "total"):
            value = mapping.get(key)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    def _build_messages(self, inputs: dict, params: dict) -> list:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []
        system_prompt = params.get("system_prompt")
        if system_prompt:
            messages.append(SystemMessage(content=str(system_prompt)))

        if "messages" in inputs:
            try:
                messages.extend(dict_messages_to_langchain(inputs["messages"]))
            except ValueError as exc:
                raise ExecutorError(
                    E_LLM_003, f"invalid message format: {exc}", hint=str(exc)
                ) from exc
        elif "question" in inputs:
            messages.append(HumanMessage(content=str(inputs["question"])))
        else:
            raise ExecutorError(E_LLM_003, "inputs must contain 'messages' or 'question'")
        return messages

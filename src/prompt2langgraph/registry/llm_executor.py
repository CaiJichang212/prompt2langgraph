"""Real LLM executor for llm-type nodes."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from prompt2langgraph.diagnostics.codes import E_LLM_001, E_LLM_002, E_LLM_003
from prompt2langgraph.llm.messages import dict_messages_to_langchain
from prompt2langgraph.registry.executors import ExecutorError


class LLMExecutor:
    """Execute llm-type nodes by invoking a real LLM model client."""

    def __init__(self, model_client: BaseChatModel) -> None:
        self._client = model_client

    def __call__(self, inputs: dict, params: dict) -> dict:
        try:
            messages = self._build_messages(inputs, params)
            response = self._client.invoke(messages)
            content = response.content
            if isinstance(content, list):
                content = "".join(str(item) for item in content)
            return {"answer": str(content) if content is not None else ""}
        except ExecutorError:
            raise
        except TimeoutError as exc:
            raise ExecutorError(E_LLM_001, "LLM call timed out", hint=str(exc)) from exc
        except Exception as exc:
            raise ExecutorError(E_LLM_002, f"LLM API error: {exc}", hint=str(exc)) from exc

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

"""Tests for LLMExecutor: real LLM executor for llm-type nodes."""
from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from prompt2langgraph.diagnostics.codes import E_LLM_001, E_LLM_002, E_LLM_003
from prompt2langgraph.registry.executors import ExecutorError
from prompt2langgraph.registry.llm_executor import LLMExecutor


# ---------------------------------------------------------------------------
# 1. Normal call returns {"answer": "..."}
# ---------------------------------------------------------------------------
def test_normal_call_returns_answer():
    fake = GenericFakeChatModel(messages=iter(["fake response"]))
    executor = LLMExecutor(fake)
    result = executor({"question": "hello"}, {})
    assert result == {"answer": "fake response"}


# ---------------------------------------------------------------------------
# 2. question is automatically wrapped as HumanMessage
# ---------------------------------------------------------------------------
def test_question_wrapped_as_human_message():
    captured: list = []

    class SpyModel(GenericFakeChatModel):
        def invoke(self, input, config=None, **kwargs):
            captured.extend(input)
            return AIMessage(content="spy")

    fake = SpyModel(messages=iter(["spy"]))
    executor = LLMExecutor(fake)
    executor({"question": "what?"}, {})
    assert len(captured) == 1
    assert isinstance(captured[0], HumanMessage)
    assert captured[0].content == "what?"


# ---------------------------------------------------------------------------
# 3. Missing messages and question raises ExecutorError (E_LLM_003)
# ---------------------------------------------------------------------------
def test_missing_messages_and_question_raises():
    fake = GenericFakeChatModel(messages=iter(["x"]))
    executor = LLMExecutor(fake)
    with pytest.raises(ExecutorError) as exc_info:
        executor({}, {})
    assert exc_info.value.code == E_LLM_003


# ---------------------------------------------------------------------------
# 4. system_prompt prepends SystemMessage
# ---------------------------------------------------------------------------
def test_system_prompt_prepends_system_message():
    captured: list = []

    class SpyModel(GenericFakeChatModel):
        def invoke(self, input, config=None, **kwargs):
            captured.extend(input)
            return AIMessage(content="ok")

    fake = SpyModel(messages=iter(["ok"]))
    executor = LLMExecutor(fake)
    executor({"question": "hi"}, {"system_prompt": "You are helpful."})
    assert len(captured) == 2
    assert isinstance(captured[0], SystemMessage)
    assert captured[0].content == "You are helpful."
    assert isinstance(captured[1], HumanMessage)
    assert captured[1].content == "hi"


# ---------------------------------------------------------------------------
# 5. Timeout raises ExecutorError (E_LLM_001)
# ---------------------------------------------------------------------------
def test_timeout_raises_executor_error():
    class TimeoutModel(GenericFakeChatModel):
        def invoke(self, input, config=None, **kwargs):
            raise TimeoutError("timed out")

    fake = TimeoutModel(messages=iter(["x"]))
    executor = LLMExecutor(fake)
    with pytest.raises(ExecutorError) as exc_info:
        executor({"question": "hello"}, {})
    assert exc_info.value.code == E_LLM_001


# ---------------------------------------------------------------------------
# 6. API error raises ExecutorError (E_LLM_002)
# ---------------------------------------------------------------------------
def test_api_error_raises_executor_error():
    class ErrorModel(GenericFakeChatModel):
        def invoke(self, input, config=None, **kwargs):
            raise RuntimeError("API failure")

    fake = ErrorModel(messages=iter(["x"]))
    executor = LLMExecutor(fake)
    with pytest.raises(ExecutorError) as exc_info:
        executor({"question": "hello"}, {})
    assert exc_info.value.code == E_LLM_002


# ---------------------------------------------------------------------------
# 7. Invalid role raises ExecutorError (E_LLM_003)
# ---------------------------------------------------------------------------
def test_invalid_role_raises_executor_error():
    fake = GenericFakeChatModel(messages=iter(["x"]))
    executor = LLMExecutor(fake)
    with pytest.raises(ExecutorError) as exc_info:
        executor({"messages": [{"role": "alien", "content": "hi"}]}, {})
    assert exc_info.value.code == E_LLM_003


# ---------------------------------------------------------------------------
# 8. Auth error wrapped as ExecutorError (E_LLM_002)
# ---------------------------------------------------------------------------
def test_auth_error_wrapped_as_executor_error():
    class AuthErrorModel(GenericFakeChatModel):
        def invoke(self, input, config=None, **kwargs):
            raise PermissionError("Invalid API key")

    fake = AuthErrorModel(messages=iter(["x"]))
    executor = LLMExecutor(fake)
    with pytest.raises(ExecutorError) as exc_info:
        executor({"question": "hello"}, {})
    assert exc_info.value.code == E_LLM_002


# ---------------------------------------------------------------------------
# 9. ExecutorError.to_diagnostic() returns correct Diagnostic
# ---------------------------------------------------------------------------
def test_executor_error_to_diagnostic():
    err = ExecutorError(E_LLM_003, "bad input", hint="check messages", node_id="n1")
    diag = err.to_diagnostic()
    assert diag.code == E_LLM_003
    assert diag.severity == "error"
    assert diag.message == "bad input"
    assert diag.hint == "check messages"
    assert diag.location is not None
    assert diag.location.node_id == "n1"


# ---------------------------------------------------------------------------
# 10. response.content is list -> joined as str
# ---------------------------------------------------------------------------
def test_list_content_joined_as_str():
    class ListContentModel(GenericFakeChatModel):
        def invoke(self, input, config=None, **kwargs):
            return AIMessage(content=["hello", " ", "world"])

    fake = ListContentModel(messages=iter(["x"]))
    executor = LLMExecutor(fake)
    result = executor({"question": "hi"}, {})
    assert result == {"answer": "hello world"}

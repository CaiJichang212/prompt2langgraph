"""Tests for the llm provider lightweight abstraction module."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr


# ---------------------------------------------------------------------------
# LLMConfig defaults
# ---------------------------------------------------------------------------
def test_llm_config_defaults():
    from prompt2langgraph.llm.config import LLMConfig

    cfg = LLMConfig()
    assert cfg.model == "qwen-plus"
    assert cfg.temperature == 0.0
    assert cfg.request_timeout_s == 60
    assert cfg.base_url is None
    assert cfg.api_key is None
    assert cfg.max_tokens is None


# ---------------------------------------------------------------------------
# api_key is SecretStr, repr hides plaintext
# ---------------------------------------------------------------------------
def test_api_key_is_secret_str():
    from prompt2langgraph.llm.config import LLMConfig

    cfg = LLMConfig(api_key=SecretStr("sk-test-secret"))
    assert isinstance(cfg.api_key, SecretStr)
    r = repr(cfg)
    assert "sk-test-secret" not in r


# ---------------------------------------------------------------------------
# load_llm_config reads from env vars
# ---------------------------------------------------------------------------
@patch.dict(os.environ, {"MODEL": "gpt-4o", "BASE_URL": "https://api.example.com", "API_KEY": "sk-123"})
def test_load_llm_config_from_env():
    from prompt2langgraph.llm.config import load_llm_config

    cfg = load_llm_config()
    assert cfg.model == "gpt-4o"
    assert cfg.base_url == "https://api.example.com"
    assert cfg.api_key is not None
    assert cfg.api_key.get_secret_value() == "sk-123"


# ---------------------------------------------------------------------------
# load_llm_config uses defaults when env vars missing
# ---------------------------------------------------------------------------
@patch.dict(os.environ, {}, clear=True)
@patch("prompt2langgraph.llm.config.load_dotenv")
def test_load_llm_config_defaults_when_missing(mock_dotenv):
    from prompt2langgraph.llm.config import load_llm_config

    cfg = load_llm_config()
    assert cfg.model == "qwen-plus"
    assert cfg.base_url is None
    assert cfg.api_key is None


# ---------------------------------------------------------------------------
# build_llm_client returns ChatOpenAI with correct params
# ---------------------------------------------------------------------------
@patch.dict(os.environ, {"API_KEY": "sk-test"}, clear=True)
@patch("prompt2langgraph.llm.config.load_dotenv")
def test_build_llm_client_returns_chat_openai(mock_dotenv):
    from prompt2langgraph.llm.provider import build_llm_client

    client = build_llm_client()
    from langchain_openai import ChatOpenAI

    assert isinstance(client, ChatOpenAI)
    assert client.model_name == "qwen-plus"
    assert client.temperature == 0.0
    assert client.request_timeout == 60


# ---------------------------------------------------------------------------
# Explicit params override env defaults
# ---------------------------------------------------------------------------
@patch.dict(os.environ, {"MODEL": "gpt-4o", "BASE_URL": "https://env-url", "API_KEY": "sk-env"}, clear=True)
def test_build_llm_client_explicit_override():
    from prompt2langgraph.llm.provider import build_llm_client

    client = build_llm_client(
        model="my-model",
        base_url="https://explicit-url",
        api_key="sk-explicit",
        temperature=0.7,
        timeout_s=120,
    )
    assert client.model_name == "my-model"
    assert client.openai_api_base == "https://explicit-url"
    assert client.temperature == 0.7
    assert client.request_timeout == 120


# ---------------------------------------------------------------------------
# dict_messages_to_langchain: all roles
# ---------------------------------------------------------------------------
def test_dict_messages_to_langchain_all_roles():
    from prompt2langgraph.llm.messages import dict_messages_to_langchain

    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "tool", "content": "tool result", "tool_call_id": "call_1"},
    ]
    result = dict_messages_to_langchain(msgs)
    assert len(result) == 4
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    assert isinstance(result[0], SystemMessage)
    assert result[0].content == "You are helpful."
    assert isinstance(result[1], HumanMessage)
    assert result[1].content == "Hello"
    assert isinstance(result[2], AIMessage)
    assert result[2].content == "Hi there!"
    assert isinstance(result[3], ToolMessage)
    assert result[3].content == "tool result"
    assert result[3].tool_call_id == "call_1"


# ---------------------------------------------------------------------------
# tool role missing tool_call_id raises
# ---------------------------------------------------------------------------
def test_dict_messages_tool_missing_tool_call_id():
    from prompt2langgraph.llm.messages import dict_messages_to_langchain

    with pytest.raises(ValueError, match="tool_call_id"):
        dict_messages_to_langchain([{"role": "tool", "content": "result"}])


# ---------------------------------------------------------------------------
# Unknown role raises
# ---------------------------------------------------------------------------
def test_dict_messages_unknown_role():
    from prompt2langgraph.llm.messages import dict_messages_to_langchain

    with pytest.raises(ValueError, match="unknown message role"):
        dict_messages_to_langchain([{"role": "alien", "content": "hello"}])


# ---------------------------------------------------------------------------
# content must be str
# ---------------------------------------------------------------------------
def test_dict_messages_content_must_be_str():
    from prompt2langgraph.llm.messages import dict_messages_to_langchain

    with pytest.raises(ValueError, match="content must be str"):
        dict_messages_to_langchain([{"role": "user", "content": 123}])

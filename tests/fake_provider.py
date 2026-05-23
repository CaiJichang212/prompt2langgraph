"""Fake LLM provider for testing."""
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel


def fake_chat_model(response_text: str = "fake response") -> BaseChatModel:
    """Create a fake chat model that returns the given response text."""
    return GenericFakeChatModel(messages=iter([response_text]))

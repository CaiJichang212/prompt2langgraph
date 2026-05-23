"""OpenAI-style dict messages to LangChain BaseMessage conversion."""
from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage


def dict_messages_to_langchain(messages: list[dict]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str):
            raise ValueError(f"message content must be str, got {type(content).__name__}")
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if not tool_call_id:
                raise ValueError("tool message requires 'tool_call_id' field")
            result.append(ToolMessage(content=content, tool_call_id=tool_call_id))
        else:
            raise ValueError(f"unknown message role: {role!r}")
    return result

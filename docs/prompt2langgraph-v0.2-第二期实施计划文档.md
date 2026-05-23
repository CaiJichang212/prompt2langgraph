# prompt2langgraph v0.2 第二期实施计划文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v0.2 第一期已实现的 `Prompt → LLM → 简化 JSON plan → WorkflowSpec` 输入闭环基础上，补齐真实 LLM 执行能力和受控 Tool 执行能力，引入策略与安全约束体系，使 Workflow 的 `llm` 和 `tool` 节点从 mock 运行演进为具备真实业务执行潜力的系统。

**Architecture:** 第二期新增顶层 `llm/` 轻量基础模块（提取第一期 `prompting/planner.py` 中的 LLM 客户端构造逻辑为共享依赖），新增 `LLMExecutor` 和 `ToolExecutor` 两种动态 executor，通过 `ExecutorType.LLM` / `ExecutorType.PYTHON_CALLABLE` 分发。`ExecutorType.LLM` 的 ref 格式约定为 `llm.<model_id>`，model_id 必须在 `allowed_models` 白名单中；`ExecutorType.PYTHON_CALLABLE` 的 ref 必须在 `ToolCallableRegistry` 和 `allowed_tool_refs` 白名单中。策略约束在 `validate_workflow()` 阶段即被检查，运行时只做防御性二次校验。所有新增 executor 通过 fake provider 独立测试，不依赖真实网络调用。

**Tech Stack:** Python 3.11, Typer, Pydantic, pytest, `langchain_openai`, `langchain_core.language_models.fake_chat_models.GenericFakeChatModel`, `BaseChatModel`, `SecretStr`, `concurrent.futures.ThreadPoolExecutor`。

---

## 一、实施范围与执行原则

本实施计划严格遵守《[prompt2langgraph-v0.2-第二期开发计划文档](docs/prompt2langgraph-v0.2-%E7%AC%AC%E4%BA%8C%E6%9C%9F%E5%BC%80%E5%8F%91%E8%AE%A1%E5%88%92%E6%96%87%E6%A1%A3.md)》定义的范围，只覆盖以下内容：

- 新增顶层 `llm/` 轻量基础模块，统一 `langchain_openai.ChatOpenAI` 的构造入口；
- 实现真实 LLM Executor，使 `llm` 类型节点在运行时可以调用外部模型，同时保留 `builtin.echo_llm` 作为 mock/fallback；
- 实现 Tool Executor 最小受控模型，使 `tool` 类型节点只能执行预注册、受信任的纯 Python callable；
- 增强策略与安全约束体系，包括 `external_call` 开关、`allowed_models` 模型白名单、`allowed_tool_refs` 工具白名单、`collect_metrics` 运行时调用记录；
- 在验证层和运行层强制检查新增策略约束；
- 补齐集成测试，以 fake provider 和预注册 fake tool 覆盖新增能力的完整链路；
- 同步更新 `README.md`、`CLAUDE.md`、`AGENTS.md`。

不在本期实施计划中的内容：

- 多 provider 适配器模式（不引入 `provider/` 包，不做 model discovery，不做 provider 热切换）；
- subprocess 沙箱、Docker 隔离或网络访问控制；
- `join` edge 执行能力；
- `skill_dir` 到 `WorkflowSpec` 的可执行转换；
- `side_effect` 节点的最小执行闭环（保留现有占位行为）；
- LLM 输出质量评估或多轮规划/反思/自动修复机制；
- Prompt 计划生成阶段的 LLM 能力扩展（第一期行为不变）；
- 在 bundle/lockfile 中写入真实 secret 或 secret 名称。

开发过程必须遵守以下执行原则：

1. 先测试、后实现，优先使用 TDD 推进；
2. 策略先行于执行：任何真实外部调用都必须先经过策略层显式允许；
3. 安全白名单而非黑名单：模型调用采用必填 `allowed_models`，工具调用采用 `allowed_tool_refs`；
4. Executor 可切换、Mock 保留：通过 executor ref 区分 mock 和真实，不修改现有 `echo_llm` 行为；
5. 可测试性内建：所有新增 executor 通过 fake provider 独立测试；
6. 每完成一个任务即运行对应测试，最后执行 `uv run pytest`。

---

## 二、建议改动文件结构

### 2.1 预计新增文件

- `src/prompt2langgraph/llm/__init__.py`
  - LLM 基础模块包入口，导出 `LLMConfig`、`build_llm_client()`。
- `src/prompt2langgraph/llm/config.py`
  - `LLMConfig` Pydantic 模型，从 `.env` 加载 LLM 配置。
- `src/prompt2langgraph/llm/provider.py`
  - `build_llm_client()` 函数，统一构造 `langchain_openai.ChatOpenAI`。
- `src/prompt2langgraph/llm/messages.py`
  - OpenAI-style dict messages 到 LangChain `BaseMessage` 的转换工具。
- `src/prompt2langgraph/registry/llm_executor.py`
  - `LLMExecutor` 类，真实 LLM 节点执行器。
- `src/prompt2langgraph/registry/tool_executor.py`
  - `ToolExecutor` 类与 `ToolCallableRegistry`，受控工具执行器。
- `tests/fake_provider.py`
  - 基于 `GenericFakeChatModel` 的 fake LLM provider。
- `tests/fake_tools.py`
  - 预注册 fake tool callable 集合。
- `tests/test_llm_provider.py`
  - `LLMConfig` 配置加载与 `build_llm_client()` 测试。
- `tests/test_llm_executor.py`
  - `LLMExecutor` 单元测试（使用 fake provider）。
- `tests/test_tool_executor.py`
  - `ToolExecutor` 单元测试（使用 fake tool）。
- `tests/test_security_policy.py`
  - 新增策略约束校验函数测试。
- `tests/test_integration_execution.py`
  - 集成测试：fake provider 下的完整图执行。

### 2.2 预计修改文件

- `src/prompt2langgraph/ir/models.py`
  - `PolicySpec` 新增 `external_call`、`allowed_models`、`collect_metrics`、`allowed_tool_refs` 字段；
  - `SecurityPolicy` 新增 `allowed_tool_refs` 字段；
  - `ExecutorDefinition`（在 `registry/executors.py`）新增 `dynamic` 字段。
- `src/prompt2langgraph/registry/executors.py`
  - `ExecutorDefinition` 新增 `dynamic: bool = False` 字段。
- `src/prompt2langgraph/registry/builtins.py`
  - `builtin_executor_registry()` 中新增 `llm.qwen-plus` 和内置 tool ref 的 schema-only definition。
- `src/prompt2langgraph/compiler/langgraph_py.py`
  - `_node_wrapper()` 签名扩展，新增 `policies`、`model_client`、`tool_registry`、`error_sink` 参数；
  - `invoke_node()` 内部新增 `ExecutorType.LLM` / `PYTHON_CALLABLE` 动态 dispatch 和 `ExecutorError` 捕获逻辑；
  - `compile_workflow_to_graph()` 签名扩展，新增 `policies`、`model_client`、`tool_registry`、`error_sink` 参数。
- `src/prompt2langgraph/validate/security.py`
  - 新增 `check_external_policy()`、`check_model_whitelist()`、`check_tool_refs()` 函数。
- `src/prompt2langgraph/validate/validator.py`
  - `validate_workflow()` 中组合调用新增策略校验函数。
- `src/prompt2langgraph/diagnostics/codes.py`
  - 新增诊断码：`E_LLM_001` ~ `E_LLM_003`、`E_SEC_013` ~ `E_SEC_015`。
- `src/prompt2langgraph/policy/resolver.py`
  - `resolve_policies()` 扩展，纳入 `external_call`、`allowed_models`、`collect_metrics`、`allowed_tool_refs`。
- `src/prompt2langgraph/binding/binder.py`
  - `bind_workflow()` 扩展，反映动态 executor definition 和新增策略字段。
- `src/prompt2langgraph/runtime/events.py`
  - `RunMetrics` 新增 `call_count`、`total_latency_ms` 字段；
  - 新增 `ExternalCallRecord` 模型；
  - `RunResult` 新增 `external_calls: list[ExternalCallRecord]` 字段。
- `src/prompt2langgraph/runtime/runner.py`
  - `run_workflow()` 中对接 `error_sink` 回调、`ExternalCallRecord` 收集和 `RunMetrics` 汇总。
- `src/prompt2langgraph/prompting/planner.py`
  - `build_model_client()` 委托给 `llm.provider.build_llm_client()`；
  - `PromptPlannerConfig` 标记为 deprecated。
- `src/prompt2langgraph/prompting/config.py`
  - 迁移为兼容 wrapper 或删除内部重复配置逻辑。
- `src/prompt2langgraph/prompting/__init__.py`
  - 导出调整，标记 `PromptPlannerConfig` 为 deprecated。
- `src/prompt2langgraph/__init__.py`
  - 暴露第二期新增 public API（如有）。
- `README.md`
  - 更新运行时能力说明（`llm` 真实执行、`tool` 受控执行、策略约束体系）。
- `CLAUDE.md`
  - 更新架构速览、运行时能力和安全边界描述。
- `AGENTS.md`
  - 同步更新能力边界、安全边界和回归要求。

### 2.3 复用现有文件

- `src/prompt2langgraph/ir/normalize.py`
  - 继续作为 workflow 规范化入口，新增 policy 字段需纳入规范化。
- `src/prompt2langgraph/ir/lockfile.py`
  - lockfile 序列化/反序列化，新增 policy 字段需纳入 hash 计算。
- `src/prompt2langgraph/validate/typecheck.py`
  - 继续使用 `ExecutorDefinition.input_schema/output_schema` 做输入输出校验，动态 executor 不破坏现有 typecheck。
- `src/prompt2langgraph/validate/graphcheck.py`
  - 继续作为图结构校验入口。
- `src/prompt2langgraph/runtime/artifacts.py`
  - 编译产物生成与读取，需确保新增 policy 字段正确序列化到 `workflow.ir.json` / `workflow.lock.json`。
- `tests/test_compile_flow.py`
  - 编译产物路径回归，需确保包含 LLM executor 节点的 workflow 编译产物正确。
- `tests/test_cli.py`
  - CLI `run` 命令在新增 executor 下的行为回归。

---

## 三、实施任务拆解

### Task 1：扩展诊断码与 IR 模型

**目标：** 为第二期所有新增能力预分配诊断码，扩展 `PolicySpec`、`SecurityPolicy` 和 `NodeSpec` 模型字段，为 `ExecutorDefinition` 增加 `dynamic` 字段。

**Files:**
- Modify: `src/prompt2langgraph/diagnostics/codes.py`
- Modify: `src/prompt2langgraph/ir/models.py`
- Modify: `src/prompt2langgraph/registry/executors.py`
- Test: `tests/test_ir_schema.py`

- [ ] **Step 1: 写 IR 模型扩展的失败测试**

```python
# tests/test_ir_schema.py 追加

from prompt2langgraph.ir.models import PolicySpec, SecurityPolicy, ExecutorType, ExecutorRef
from prompt2langgraph.registry.executors import ExecutorDefinition


def test_policy_spec_has_external_call_default_false() -> None:
    policy = PolicySpec()
    assert policy.external_call is False


def test_policy_spec_has_allowed_models_default_empty() -> None:
    policy = PolicySpec()
    assert policy.allowed_models == []


def test_policy_spec_has_collect_metrics_default_false() -> None:
    policy = PolicySpec()
    assert policy.collect_metrics is False


def test_policy_spec_has_allowed_tool_refs_default_empty() -> None:
    policy = PolicySpec()
    assert policy.allowed_tool_refs == []


def test_security_policy_has_allowed_tool_refs_default_none() -> None:
    sec = SecurityPolicy()
    assert sec.allowed_tool_refs is None


def test_executor_definition_has_dynamic_default_false() -> None:
    d = ExecutorDefinition(ref="test.ref", type=ExecutorType.BUILTIN)
    assert d.dynamic is False


def test_node_spec_has_timeout_s_default_none() -> None:
    from prompt2langgraph.ir.models import NodeSpec, ExecutorRef

    node = NodeSpec(
        id="n1",
        kind="llm",
        executor=ExecutorRef(ref="builtin.echo_llm", type=ExecutorType.BUILTIN),
    )
    assert node.timeout_s is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_ir_schema.py::test_policy_spec_has_external_call_default_false tests/test_ir_schema.py::test_policy_spec_has_allowed_models_default_empty tests/test_ir_schema.py::test_policy_spec_has_collect_metrics_default_false tests/test_ir_schema.py::test_policy_spec_has_allowed_tool_refs_default_empty tests/test_ir_schema.py::test_security_policy_has_allowed_tool_refs_default_none tests/test_ir_schema.py::test_executor_definition_has_dynamic_default_false tests/test_ir_schema.py::test_node_spec_has_timeout_s_default_none -v`

Expected: FAIL，提示字段不存在。

- [ ] **Step 3: 扩展诊断码**

在 `src/prompt2langgraph/diagnostics/codes.py` 末尾追加：

```python
# LLM executor diagnostics
E_LLM_001 = "E_LLM_001"  # LLM 调用超时
E_LLM_002 = "E_LLM_002"  # LLM API 错误
E_LLM_003 = "E_LLM_003"  # LLM 非法消息格式

# External call security diagnostics
E_SEC_013 = "E_SEC_013"  # external_call 未启用但有 LLM executor 节点
E_SEC_014 = "E_SEC_014"  # 模型不在 allowed_models 白名单
E_SEC_015 = "E_SEC_015"  # tool ref 未授权或未注册
```

- [ ] **Step 4: 扩展 PolicySpec 和 SecurityPolicy 模型**

在 `src/prompt2langgraph/ir/models.py` 中修改 `PolicySpec`：

```python
class PolicySpec(BaseModel):
    external_call: bool = False
    allowed_models: list[str] = Field(default_factory=list)
    collect_metrics: bool = False
    allowed_tool_refs: list[str] = Field(default_factory=list)
    allow_side_effects: bool = False
    default_timeout_s: int = 60
```

修改 `SecurityPolicy`：

```python
class SecurityPolicy(BaseModel):
    requires_approval: bool = False
    idempotency_key: str | None = None
    allowed_tool_refs: list[str] | None = None
```

在 `NodeSpec` 中新增 `timeout_s` 字段：

```python
class NodeSpec(BaseModel):
    # ... 现有字段保持不变 ...
    timeout_s: int | None = None  # 节点级执行超时（秒），None 表示使用 PolicySpec.default_timeout_s
```

- [ ] **Step 5: 扩展 ExecutorDefinition 增加 dynamic 字段**

在 `src/prompt2langgraph/registry/executors.py` 中修改 `ExecutorDefinition`：

```python
@dataclass(frozen=True)
class ExecutorDefinition:
    ref: str
    type: ExecutorType
    input_schema: dict[str, TypeSpec] = field(default_factory=dict)
    output_schema: dict[str, TypeSpec] = field(default_factory=dict)
    secrets: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    handler: ExecutorHandler | None = None
    dynamic: bool = False
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_ir_schema.py -v`

Expected: PASS（新增测试通过，现有测试不受影响）。

- [ ] **Step 7: 提交本任务**

```bash
git add src/prompt2langgraph/diagnostics/codes.py src/prompt2langgraph/ir/models.py src/prompt2langgraph/registry/executors.py tests/test_ir_schema.py
git commit -m "feat: extend IR models with phase-2 policy fields and dynamic executor definition"
```

---

### Task 2：创建 LLM Provider 轻量抽象模块（`llm/` 包）

**目标：** 新增顶层 `llm/` 包，包含 `LLMConfig`、`build_llm_client()` 和消息转换工具，统一 `langchain_openai.ChatOpenAI` 的构造入口。

**Files:**
- Create: `src/prompt2langgraph/llm/__init__.py`
- Create: `src/prompt2langgraph/llm/config.py`
- Create: `src/prompt2langgraph/llm/provider.py`
- Create: `src/prompt2langgraph/llm/messages.py`
- Test: `tests/test_llm_provider.py`

- [ ] **Step 1: 写 LLM Provider 模块测试**

```python
# tests/test_llm_provider.py

import pytest
from pydantic import SecretStr

from prompt2langgraph.llm.config import LLMConfig, load_llm_config
from prompt2langgraph.llm.provider import build_llm_client
from prompt2langgraph.llm.messages import dict_messages_to_langchain


def test_llm_config_defaults() -> None:
    config = LLMConfig()
    assert config.model == "qwen-plus"
    assert config.base_url is None
    assert config.api_key is None
    assert config.temperature == 0.0
    assert config.max_tokens is None
    assert config.request_timeout_s == 60


def test_llm_config_api_key_is_secret_str() -> None:
    config = LLMConfig(api_key=SecretStr("sk-12345"))
    assert "sk-12345" not in repr(config)
    assert config.api_key.get_secret_value() == "sk-12345"


def test_load_llm_config_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "qwen-turbo")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-secret-key")

    config = load_llm_config()

    assert config.model == "qwen-turbo"
    assert config.base_url == "https://env.example.com/v1"
    assert config.api_key.get_secret_value() == "env-secret-key"


def test_load_llm_config_missing_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("MODEL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    config = load_llm_config()

    assert config.model == "qwen-plus"
    assert config.base_url is None
    assert config.api_key is None


def test_build_llm_client_returns_chat_openai(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("BASE_URL", "https://test.example.com/v1")

    client = build_llm_client(model="qwen-plus", temperature=0.2)

    from langchain_openai import ChatOpenAI
    assert isinstance(client, ChatOpenAI)
    assert client.model_name == "qwen-plus"
    assert client.temperature == 0.2


def test_build_llm_client_uses_env_defaults(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "qwen-turbo")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    client = build_llm_client()

    assert client.model_name == "qwen-turbo"


def test_build_llm_client_explicit_params_override_env(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "qwen-turbo")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    client = build_llm_client(
        model="qwen-max",
        base_url="https://custom.example.com/v1",
        api_key="custom-key",
    )

    assert client.model_name == "qwen-max"


def test_dict_messages_to_langchain_user_message() -> None:
    from langchain_core.messages import HumanMessage

    messages = [{"role": "user", "content": "Hello"}]
    result = dict_messages_to_langchain(messages)

    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == "Hello"


def test_dict_messages_to_langchain_system_message() -> None:
    from langchain_core.messages import SystemMessage

    messages = [{"role": "system", "content": "You are helpful."}]
    result = dict_messages_to_langchain(messages)

    assert isinstance(result[0], SystemMessage)


def test_dict_messages_to_langchain_assistant_message() -> None:
    from langchain_core.messages import AIMessage

    messages = [{"role": "assistant", "content": "Hi there!"}]
    result = dict_messages_to_langchain(messages)

    assert isinstance(result[0], AIMessage)


def test_dict_messages_to_langchain_unknown_role_raises() -> None:
    with pytest.raises(ValueError, match="unsupported role"):
        dict_messages_to_langchain([{"role": "function", "content": "result"}])


def test_dict_messages_to_langchain_tool_message() -> None:
    from langchain_core.messages import ToolMessage

    messages = [{"role": "tool", "content": "42", "tool_call_id": "call_abc123"}]
    result = dict_messages_to_langchain(messages)

    assert isinstance(result[0], ToolMessage)
    assert result[0].content == "42"
    assert result[0].tool_call_id == "call_abc123"


def test_dict_messages_to_langchain_tool_message_missing_call_id_raises() -> None:
    with pytest.raises(ValueError, match="tool_call_id"):
        dict_messages_to_langchain([{"role": "tool", "content": "result"}])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_llm_provider.py -v`

Expected: FAIL，提示 `ModuleNotFoundError`。

- [ ] **Step 3: 实现 `llm/config.py`**

```python
"""LLM configuration loading from .env."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr


class LLMConfig(BaseModel):
    """LLM provider configuration loaded from environment.

    WARNING: Do not serialize this configuration object to persistent storage.
    """

    model: str = Field(default="qwen-plus")
    base_url: str | None = None
    api_key: SecretStr | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = None
    request_timeout_s: int = Field(default=60, ge=1)


def load_llm_config() -> LLMConfig:
    load_dotenv()
    api_key = os.getenv("API_KEY")
    return LLMConfig(
        model=os.getenv("MODEL", "qwen-plus"),
        base_url=os.getenv("BASE_URL"),
        api_key=SecretStr(api_key) if api_key else None,
    )
```

- [ ] **Step 4: 实现 `llm/messages.py`**

```python
"""OpenAI-style dict messages to LangChain BaseMessage conversion."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

_ROLE_MAP = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
    # tool role 预留：当前第二期不启用 LANGCHAIN_TOOL executor，
    # 但预留映射以降低后续实现 tool calling 场景的改动成本
    "tool": ToolMessage,
}


def dict_messages_to_langchain(messages: list[dict[str, str]]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        cls = _ROLE_MAP.get(role)
        if cls is None:
            raise ValueError(
                f"unsupported role {role!r}; expected one of {sorted(_ROLE_MAP)}"
            )
        if not isinstance(content, str):
            raise ValueError(f"message content must be a string, got {type(content).__name__}")
        # ToolMessage 需要 tool_call_id 参数
        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            if not tool_call_id:
                raise ValueError("tool role messages require a 'tool_call_id' field")
            result.append(ToolMessage(content=content, tool_call_id=tool_call_id))
        else:
            result.append(cls(content=content))
    return result
```

- [ ] **Step 5: 实现 `llm/provider.py`**

```python
"""LLM client construction for prompt2langgraph."""

from __future__ import annotations

from pydantic import SecretStr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from prompt2langgraph.llm.config import LLMConfig, load_llm_config


def build_llm_client(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout_s: int | None = None,
) -> BaseChatModel:
    """Build a ChatOpenAI client unified for Prompt planning and runtime LLM executor.

    WARNING: Do not serialize the returned client to persistent storage.
    The client contains credentials that must not leak into bundles or lockfiles.
    """
    config: LLMConfig = load_llm_config()
    resolved_api_key = _resolve_api_key(api_key, config.api_key)
    return ChatOpenAI(
        model=model if model is not None else config.model,
        base_url=base_url if base_url is not None else config.base_url,
        api_key=resolved_api_key,
        temperature=temperature if temperature is not None else config.temperature,
        max_tokens=max_tokens if max_tokens is not None else config.max_tokens,
        timeout=timeout_s if timeout_s is not None else config.request_timeout_s,
    )


def _resolve_api_key(explicit: str | None, from_config: SecretStr | None) -> str | None:
    """Resolve API key from explicit parameter or config, treating empty strings as missing."""
    if explicit is not None and explicit.strip():
        return SecretStr(explicit).get_secret_value()
    if from_config is not None:
        value = from_config.get_secret_value()
        if value and value.strip():
            return value
    return None
```

- [ ] **Step 6: 实现 `llm/__init__.py`**

```python
from prompt2langgraph.llm.config import LLMConfig, load_llm_config
from prompt2langgraph.llm.provider import build_llm_client
from prompt2langgraph.llm.messages import dict_messages_to_langchain

__all__ = [
    "LLMConfig",
    "build_llm_client",
    "dict_messages_to_langchain",
    "load_llm_config",
]
```

- [ ] **Step 7: 运行测试确认通过**

Run: `uv run pytest tests/test_llm_provider.py -v`

Expected: PASS

- [ ] **Step 8: 提交本任务**

```bash
git add src/prompt2langgraph/llm/__init__.py src/prompt2langgraph/llm/config.py src/prompt2langgraph/llm/provider.py src/prompt2langgraph/llm/messages.py tests/test_llm_provider.py
git commit -m "feat: add llm provider abstraction module with config and client builder"
```

---

### Task 3：重构 `prompting/planner.py` 委托给 `llm/` 模块

**目标：** 将 `prompting/planner.py` 中的 `build_model_client()` 委托给 `llm.provider.build_llm_client()`，标记 `PromptPlannerConfig` 为 deprecated，保持第一期 Prompt 计划生成行为完全兼容。

**Files:**
- Modify: `src/prompt2langgraph/prompting/planner.py`
- Modify: `src/prompt2langgraph/prompting/config.py`
- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Test: `tests/test_prompt_planner.py`

- [ ] **Step 1: 写重构回归测试**

```python
# tests/test_prompt_planner.py 追加


def test_build_model_client_delegates_to_llm_provider(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "qwen-turbo")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    from prompt2langgraph.prompting.planner import (
        PromptPlanRequest,
        build_model_client,
    )

    request = PromptPlanRequest(
        prompt="test",
        model="qwen-plus",
        base_url="https://custom.example.com/v1",
        api_key="custom-key",
    )
    client = build_model_client(request)

    assert client.model_name == "qwen-plus"


def test_generate_plan_text_still_works_after_refactor() -> None:
    from prompt2langgraph.prompting.planner import (
        PromptPlanRequest,
        generate_plan_text,
    )

    class FakeModel:
        def invoke(self, messages):
            return type("Response", (), {"content": '{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'})()

    request = PromptPlanRequest(prompt="build a simple answer workflow")
    result = generate_plan_text(request, model_client=FakeModel())

    assert result.raw_text.startswith("{")
    assert '"name":"Demo"' in result.raw_text
```

- [ ] **Step 2: 运行测试确认当前行为**

Run: `uv run pytest tests/test_prompt_planner.py::test_generate_plan_text_still_works_after_refactor -v`

Expected: PASS（重构前先确认现有测试通过）。

- [ ] **Step 3: 修改 `prompting/config.py`，标记 deprecated**

```python
"""Prompt planner configuration (deprecated, use llm.config.LLMConfig instead)."""

from __future__ import annotations

import os
import warnings

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr

from prompt2langgraph.llm.config import LLMConfig, load_llm_config as _load_llm_config


class PromptPlannerConfig(BaseModel):
    """DEPRECATED: Use llm.config.LLMConfig instead."""

    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def load_prompt_planner_config() -> PromptPlannerConfig:
    warnings.warn(
        "PromptPlannerConfig is deprecated, use llm.config.LLMConfig instead",
        DeprecationWarning,
        stacklevel=2,
    )
    config = _load_llm_config()
    return PromptPlannerConfig(
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key.get_secret_value() if config.api_key else None,
    )
```

- [ ] **Step 4: 修改 `prompting/planner.py`，`build_model_client()` 委托给 `llm.provider`**

修改 `build_model_client()` 函数：

```python
def build_model_client(request: PromptPlanRequest) -> BaseChatModel:
    from prompt2langgraph.llm.provider import build_llm_client

    return build_llm_client(
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
        temperature=request.temperature,
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_prompt_planner.py -v`

Expected: PASS（所有现有 Prompt 计划生成测试通过）。

- [ ] **Step 6: 提交本任务**

```bash
git add src/prompt2langgraph/prompting/planner.py src/prompt2langgraph/prompting/config.py src/prompt2langgraph/prompting/__init__.py tests/test_prompt_planner.py
git commit -m "refactor: delegate build_model_client to llm.provider, deprecate PromptPlannerConfig"
```

---

### Task 4：实现真实 LLM Executor

**目标：** 新增 `LLMExecutor` 类，使 `llm` 类型节点在运行时可以调用外部模型。通过 `ExecutorType.LLM` 分发，`ref="llm.qwen-plus"` 为真实 executor。

**Files:**
- Create: `src/prompt2langgraph/registry/llm_executor.py`
- Modify: `src/prompt2langgraph/registry/builtins.py`
- Test: `tests/test_llm_executor.py`

- [ ] **Step 1: 写 LLM Executor 测试（使用 fake provider）**

```python
# tests/test_llm_executor.py

import pytest

from prompt2langgraph.registry.llm_executor import LLMExecutor
from prompt2langgraph.registry.executors import ExecutorError


class FakeBaseChatModel:
    """Fake BaseChatModel for testing LLMExecutor."""

    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content="fake response from qwen-plus")


def test_llm_executor_returns_answer_dict() -> None:
    executor = LLMExecutor(model_client=FakeBaseChatModel())
    result = executor({"messages": [{"role": "user", "content": "Hello"}]}, {})

    assert result == {"answer": "fake response from qwen-plus"}


def test_llm_executor_auto_wraps_question_input() -> None:
    executor = LLMExecutor(model_client=FakeBaseChatModel())
    result = executor({"question": "What is AI?"}, {})

    assert result == {"answer": "fake response from qwen-plus"}


def test_llm_executor_missing_messages_raises() -> None:
    executor = LLMExecutor(model_client=FakeBaseChatModel())
    with pytest.raises(ExecutorError, match="E_LLM_003"):
        executor({}, {})


def test_llm_executor_system_prompt_prepends() -> None:
    captured_messages = []

    class CapturingModel:
        def invoke(self, messages):
            captured_messages.extend(messages)
            from langchain_core.messages import AIMessage
            return AIMessage(content="response")

    executor = LLMExecutor(model_client=CapturingModel())
    executor(
        {"messages": [{"role": "user", "content": "Hello"}]},
        {"system_prompt": "You are professional."},
    )

    from langchain_core.messages import SystemMessage
    assert isinstance(captured_messages[0], SystemMessage)
    assert captured_messages[0].content == "You are professional."


def test_llm_executor_handles_network_timeout() -> None:
    class TimeoutModel:
        def invoke(self, messages):
            raise TimeoutError("connection timed out")

    executor = LLMExecutor(model_client=TimeoutModel())
    with pytest.raises(ExecutorError, match="E_LLM_001"):
        executor({"messages": [{"role": "user", "content": "Hello"}]}, {})


def test_llm_executor_handles_api_error() -> None:
    class ErrorModel:
        def invoke(self, messages):
            raise RuntimeError("API returned 500")

    executor = LLMExecutor(model_client=ErrorModel())
    with pytest.raises(ExecutorError, match="E_LLM_002"):
        executor({"messages": [{"role": "user", "content": "Hello"}]}, {})


def test_llm_executor_invalid_message_role_raises() -> None:
    executor = LLMExecutor(model_client=FakeBaseChatModel())
    with pytest.raises(ExecutorError, match="E_LLM_003"):
        executor(
            {"messages": [{"role": "function", "content": "result"}]}, {}
        )


def test_llm_executor_missing_api_key_raises() -> None:
    """当 API_KEY 缺失时，LLM executor 应返回明确诊断而非崩溃。"""
    from prompt2langgraph.llm.provider import build_llm_client

    # 模拟 API_KEY 缺失的场景：build_llm_client() 在无 API_KEY 时
    # 应能构造 client（延迟验证），但调用时 API 会返回认证错误
    # 此测试验证 LLMExecutor 对认证错误的包装
    class AuthErrorModel:
        def invoke(self, messages):
            raise RuntimeError("Authentication error: Invalid API key")

    executor = LLMExecutor(model_client=AuthErrorModel())
    with pytest.raises(ExecutorError, match="E_LLM_002"):
        executor({"messages": [{"role": "user", "content": "Hello"}]}, {})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_llm_executor.py -v`

Expected: FAIL，提示 `ModuleNotFoundError`。

- [ ] **Step 3: 在 `registry/executors.py` 中新增 `ExecutorError`**

```python
# 在 registry/executors.py 末尾追加

from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation


class ExecutorError(RuntimeError):
    """Error raised by executor implementations with structured diagnostic info."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        node_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.node_id = node_id

    def to_diagnostic(self) -> Diagnostic:
        return Diagnostic(
            code=self.code,
            severity="error",
            message=self.message,
            location=DiagnosticLocation(node_id=self.node_id) if self.node_id else None,
            hint=self.hint,
        )
```

- [ ] **Step 4: 实现 `registry/llm_executor.py`**

```python
"""Real LLM executor for llm nodes."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from prompt2langgraph.diagnostics.codes import E_LLM_001, E_LLM_002, E_LLM_003
from prompt2langgraph.llm.messages import dict_messages_to_langchain
from prompt2langgraph.registry.executors import ExecutorError


class LLMExecutor:
    """Executor for llm nodes that calls a real LLM.

    Injects a BaseChatModel via dependency injection; test with fake,
    production with ChatOpenAI from llm.provider.build_llm_client().
    """

    def __init__(self, model_client: BaseChatModel) -> None:
        self._model_client = model_client

    def __call__(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        messages = self._extract_messages(inputs)
        system_prompt = params.get("system_prompt")
        if system_prompt:
            from langchain_core.messages import SystemMessage
            messages.insert(0, SystemMessage(content=system_prompt))
        try:
            response = self._model_client.invoke(messages)
        except TimeoutError as exc:
            raise ExecutorError(
                E_LLM_001,
                "LLM call timed out",
                hint=str(exc),
            ) from exc
        except Exception as exc:
            raise ExecutorError(
                E_LLM_002,
                "LLM API error",
                hint=str(exc),
            ) from exc
        content = response.content
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        return {"answer": str(content)}

    def _extract_messages(self, inputs: dict[str, Any]) -> list:
        if "messages" in inputs:
            raw = inputs["messages"]
            if isinstance(raw, list):
                try:
                    return dict_messages_to_langchain(raw)
                except ValueError as exc:
                    raise ExecutorError(
                        E_LLM_003,
                        f"invalid message format: {exc}",
                    ) from exc
            raise ExecutorError(
                E_LLM_003,
                "messages input must be a list of {role, content} dicts",
            )
        if "question" in inputs:
            from langchain_core.messages import HumanMessage
            return [HumanMessage(content=str(inputs["question"]))]
        raise ExecutorError(
            E_LLM_003,
            "LLM executor requires messages or question input",
        )
```

- [ ] **Step 5: 在 `registry/builtins.py` 中注册 `llm.qwen-plus` schema-only definition**

```python
# 在 builtin_executor_registry() 返回的列表末尾添加

ExecutorDefinition(
    ref="llm.qwen-plus",
    type=ExecutorType.LLM,
    input_schema={"question": STRING},
    output_schema={"answer": STRING},
    dynamic=True,
    handler=None,
),
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_llm_executor.py -v`

Expected: PASS

- [ ] **Step 7: 提交本任务**

```bash
git add src/prompt2langgraph/registry/executors.py src/prompt2langgraph/registry/llm_executor.py src/prompt2langgraph/registry/builtins.py tests/test_llm_executor.py
git commit -m "feat: add real LLM executor with ExecutorType.LLM dispatch"
```

---

### Task 5：实现 Tool Executor 最小受控模型

**目标：** 新增 `ToolExecutor` 类和 `ToolCallableRegistry`，使 `tool` 类型节点只能执行预注册、受信任的纯 Python callable。

**Files:**
- Create: `src/prompt2langgraph/registry/tool_executor.py`
- Modify: `src/prompt2langgraph/registry/builtins.py`
- Test: `tests/test_tool_executor.py`

- [ ] **Step 1: 写 Tool Executor 测试**

```python
# tests/test_tool_executor.py

import time

import pytest

from prompt2langgraph.registry.tool_executor import ToolCallableRegistry, ToolExecutor
from prompt2langgraph.registry.executors import ExecutorError


def echo_tool(inputs: dict, params: dict) -> dict:
    text = inputs.get("text", "")
    return {"result": text}


def fail_tool(inputs: dict, params: dict) -> dict:
    raise RuntimeError("tool intentionally fails")


def slow_tool(inputs: dict, params: dict) -> dict:
    time.sleep(10)
    return {"result": "slow"}


@pytest.fixture
def tool_registry() -> ToolCallableRegistry:
    registry = ToolCallableRegistry()
    registry.register("tool.echo", echo_tool)
    registry.register("tool.fail", fail_tool)
    registry.register("tool.sleep", slow_tool)
    return registry


def test_tool_executor_calls_registered_tool(tool_registry) -> None:
    executor = ToolExecutor(registry=tool_registry, tool_ref="tool.echo")
    result = executor({"text": "hello"}, {})

    assert result == {"result": "hello"}


def test_tool_executor_unknown_ref_raises(tool_registry) -> None:
    executor = ToolExecutor(registry=tool_registry, tool_ref="tool.does_not_exist")
    with pytest.raises(ExecutorError, match="E_SEC_015"):
        executor({"text": "hello"}, {})


def test_tool_executor_propagates_tool_error(tool_registry) -> None:
    executor = ToolExecutor(registry=tool_registry, tool_ref="tool.fail")
    with pytest.raises(ExecutorError):
        executor({}, {})


def test_tool_callable_registry_has_and_get() -> None:
    registry = ToolCallableRegistry()
    registry.register("tool.echo", echo_tool)

    assert registry.has("tool.echo") is True
    assert registry.has("tool.nonexistent") is False
    assert registry.get("tool.echo") == echo_tool

    with pytest.raises(KeyError):
        registry.get("tool.nonexistent")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_tool_executor.py -v`

Expected: FAIL，提示 `ModuleNotFoundError`。

- [ ] **Step 3: 实现 `registry/tool_executor.py`**

```python
"""Tool Executor and callable registry for controlled tool execution."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from typing import Any

from prompt2langgraph.diagnostics.codes import E_SEC_015
from prompt2langgraph.registry.executors import ExecutorError, ExecutorHandler


class ToolCallableRegistry:
    """Registry of trusted, pre-registered Python callables for tool nodes.

    Only callables explicitly registered here can be executed. The registry
    is NOT a sandbox—it does not provide subprocess isolation, Docker
    containment, or network access control.
    """

    def __init__(self) -> None:
        self._callables: dict[str, ExecutorHandler] = {}

    def register(self, ref: str, callable: ExecutorHandler) -> None:
        self._callables[ref] = callable

    def get(self, ref: str) -> ExecutorHandler:
        return self._callables[ref]

    def has(self, ref: str) -> bool:
        return ref in self._callables

    def refs(self) -> list[str]:
        return sorted(self._callables)


class ToolExecutor:
    """Executor for tool nodes using pre-registered Python callables.

    Only callables already registered in the ToolCallableRegistry can be executed.
    Dynamic code import from workflow JSON is NOT supported.
    """

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

    def __call__(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._registry.has(self._tool_ref):
            raise ExecutorError(
                E_SEC_015,
                f'tool ref "{self._tool_ref}" is not registered',
                hint="Register the tool callable in ToolCallableRegistry before execution.",
            )
        callable = self._registry.get(self._tool_ref)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(callable, inputs, params)
                return future.result(timeout=self._timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise ExecutorError(
                E_SEC_015,
                f'tool "{self._tool_ref}" exceeded timeout of {self._timeout_s}s',
                hint="The timeout is a soft limit; the callable may still be running.",
            ) from exc
        except Exception as exc:
            raise ExecutorError(
                E_SEC_015,
                f'tool "{self._tool_ref}" execution failed',
                hint=str(exc),
            ) from exc
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_tool_executor.py -v`

Expected: PASS

- [ ] **Step 5: 提交本任务**

```bash
git add src/prompt2langgraph/registry/tool_executor.py tests/test_tool_executor.py
git commit -m "feat: add ToolExecutor with ToolCallableRegistry for controlled tool execution"
```

---

### Task 6：实现策略校验层

**目标：** 在 `validate/security.py` 中新增 `check_external_policy()`、`check_model_whitelist()`、`check_tool_refs()` 函数，在 `validate/validator.py` 中组合调用。

**Files:**
- Modify: `src/prompt2langgraph/validate/security.py`
- Modify: `src/prompt2langgraph/validate/validator.py`
- Test: `tests/test_security_policy.py`

- [ ] **Step 1: 写策略校验测试**

```python
# tests/test_security_policy.py

from prompt2langgraph.ir.models import (
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    PolicySpec,
    SecurityPolicy,
    WorkflowSpec,
    StateSchema,
)
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.validate.security import (
    check_external_policy,
    check_model_whitelist,
    check_tool_refs,
)
from prompt2langgraph.diagnostics.codes import E_SEC_013, E_SEC_014, E_SEC_015


def _make_workflow(*, nodes=None, policies=None) -> WorkflowSpec:
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test",
        name="test",
        entrypoint="n1",
        state_schema=StateSchema(),
        nodes=nodes or [],
        edges=[],
        policies=policies or PolicySpec(),
    )


def test_check_external_policy_llm_node_without_external_call_reports_error() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="llm",
            executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
        )
    ]
    wf = _make_workflow(nodes=nodes, policies=PolicySpec(external_call=False))
    diags = check_external_policy(wf)

    assert len(diags) == 1
    assert diags[0].code == E_SEC_013


def test_check_external_policy_llm_node_with_external_call_passes() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="llm",
            executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
        )
    ]
    wf = _make_workflow(nodes=nodes, policies=PolicySpec(external_call=True))
    diags = check_external_policy(wf)

    assert len(diags) == 0


def test_check_external_policy_builtin_llm_passes_without_external_call() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="llm",
            executor=ExecutorRef(ref="builtin.echo_llm", type=ExecutorType.BUILTIN),
        )
    ]
    wf = _make_workflow(nodes=nodes, policies=PolicySpec(external_call=False))
    diags = check_external_policy(wf)

    assert len(diags) == 0


def test_check_model_whitelist_missing_model_reports_error() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="llm",
            executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
        )
    ]
    wf = _make_workflow(
        nodes=nodes,
        policies=PolicySpec(external_call=True, allowed_models=[]),
    )
    diags = check_model_whitelist(wf)

    assert len(diags) == 1
    assert diags[0].code == E_SEC_014


def test_check_model_whitelist_matching_model_passes() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="llm",
            executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
        )
    ]
    wf = _make_workflow(
        nodes=nodes,
        policies=PolicySpec(external_call=True, allowed_models=["qwen-plus"]),
    )
    diags = check_model_whitelist(wf)

    assert len(diags) == 0


def test_check_tool_refs_unregistered_ref_reports_error() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="tool",
            executor=ExecutorRef(ref="tool.unregistered", type=ExecutorType.PYTHON_CALLABLE),
        )
    ]
    wf = _make_workflow(nodes=nodes)
    tool_registry = ToolCallableRegistry()

    diags = check_tool_refs(wf, tool_registry)

    assert len(diags) == 1
    assert diags[0].code == E_SEC_015


def test_check_tool_refs_registered_and_allowed_passes() -> None:
    nodes = [
        NodeSpec(
            id="n1",
            kind="tool",
            executor=ExecutorRef(ref="tool.echo", type=ExecutorType.PYTHON_CALLABLE),
        )
    ]
    wf = _make_workflow(
        nodes=nodes,
        policies=PolicySpec(allowed_tool_refs=["tool.echo"]),
    )
    tool_registry = ToolCallableRegistry()
    tool_registry.register("tool.echo", lambda i, p: {"r": i.get("x", "")})

    diags = check_tool_refs(wf, tool_registry)

    assert len(diags) == 0


def test_check_tool_refs_no_whitelist_configured_reports_error() -> None:
    """当全局和节点级均未配置 allowed_tool_refs 时，应报 E_SEC_015 诊断。"""
    nodes = [
        NodeSpec(
            id="n1",
            kind="tool",
            executor=ExecutorRef(ref="tool.echo", type=ExecutorType.PYTHON_CALLABLE),
        )
    ]
    # allowed_tool_refs 使用默认值 []，即空白名单
    wf = _make_workflow(nodes=nodes, policies=PolicySpec(allowed_tool_refs=[]))
    tool_registry = ToolCallableRegistry()
    tool_registry.register("tool.echo", lambda i, p: {"r": i.get("x", "")})

    diags = check_tool_refs(wf, tool_registry)

    assert len(diags) == 1
    assert diags[0].code == E_SEC_015


def test_check_tool_refs_langchain_tool_type_is_skipped() -> None:
    """ExecutorType.LANGCHAIN_TOOL 节点当前不触发 check_tool_refs() 校验。"""
    from prompt2langgraph.ir.models import ExecutorRef

    nodes = [
        NodeSpec(
            id="n1",
            kind="tool",
            executor=ExecutorRef(ref="builtin.some_tool", type=ExecutorType.LANGCHAIN_TOOL),
        )
    ]
    wf = _make_workflow(nodes=nodes, policies=PolicySpec(allowed_tool_refs=[]))
    tool_registry = ToolCallableRegistry()

    # LANGCHAIN_TOOL 类型不受 check_tool_refs() 检查，不产生诊断
    diags = check_tool_refs(wf, tool_registry)
    assert len(diags) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_security_policy.py -v`

Expected: FAIL，提示函数不存在。

- [ ] **Step 3: 扩展 `validate/security.py`**

在现有 `check_security()` 函数后追加：

```python
from prompt2langgraph.diagnostics.codes import E_SEC_013, E_SEC_014, E_SEC_015
from prompt2langgraph.ir.models import ExecutorType, WorkflowSpec
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry


def check_external_policy(workflow: WorkflowSpec) -> list[Diagnostic]:
    """Check that external_call is enabled when any node uses ExecutorType.LLM."""
    diagnostics: list[Diagnostic] = []
    llm_nodes = [
        node for node in workflow.nodes
        if node.executor.type is ExecutorType.LLM
    ]
    if llm_nodes and not workflow.policies.external_call:
        for node in llm_nodes:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_013,
                    severity="error",
                    message=(
                        f'node "{node.id}" uses ExecutorType.LLM but '
                        f'external_call is not enabled in workflow policies'
                    ),
                    location=DiagnosticLocation(node_id=node.id),
                    hint="Set workflow.policies.external_call=True to enable external LLM calls.",
                )
            )
    return diagnostics


def check_model_whitelist(workflow: WorkflowSpec) -> list[Diagnostic]:
    """Check that every ExecutorType.LLM ref's model_id is in allowed_models."""
    diagnostics: list[Diagnostic] = []
    llm_nodes = [
        node for node in workflow.nodes
        if node.executor.type is ExecutorType.LLM
    ]
    if not llm_nodes:
        return diagnostics
    allowed = workflow.policies.allowed_models
    for node in llm_nodes:
        ref = node.executor.ref
        if not ref.startswith("llm."):
            continue
        model_id = ref[len("llm."):]
        if model_id not in allowed:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_014,
                    severity="error",
                    message=(
                        f'node "{node.id}" executor "{ref}" model '
                        f'"{model_id}" is not in allowed_models'
                    ),
                    location=DiagnosticLocation(node_id=node.id),
                    hint=f"Add '{model_id}' to workflow.policies.allowed_models.",
                )
            )
    return diagnostics


def check_tool_refs(
    workflow: WorkflowSpec,
    tool_registry: ToolCallableRegistry,
) -> list[Diagnostic]:
    """Check that all PYTHON_CALLABLE executor refs are registered and allowed.

    LANGCHAIN_TOOL 类型的节点在当前第二期中不受此函数校验
    （LANGCHAIN_TOOL 的执行能力留待后续版本实现）。
    """
    diagnostics: list[Diagnostic] = []
    tool_nodes = [
        node for node in workflow.nodes
        if node.executor.type is ExecutorType.PYTHON_CALLABLE
    ]
    if not tool_nodes:
        return diagnostics
    global_allowed = workflow.policies.allowed_tool_refs
    for node in tool_nodes:
        ref = node.executor.ref
        node_allowed = (
            node.security.allowed_tool_refs
            if node.security is not None
            else None
        )
        effective_allowed = node_allowed if node_allowed is not None else global_allowed
        # effective_allowed 至少为 []（PolicySpec 默认值），不存在 None 情况
        if ref not in effective_allowed:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_015,
                    severity="error",
                    message=(
                        f'node "{node.id}" tool ref "{ref}" is not in '
                        f'allowed_tool_refs'
                    ),
                    location=DiagnosticLocation(node_id=node.id),
                    hint=f"Add '{ref}' to allowed_tool_refs.",
                )
            )
        if not tool_registry.has(ref):
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_015,
                    severity="error",
                    message=(
                        f'node "{node.id}" tool ref "{ref}" is not registered '
                        f'in ToolCallableRegistry'
                    ),
                    location=DiagnosticLocation(node_id=node.id),
                    hint=f"Register '{ref}' in ToolCallableRegistry.",
                )
            )
    return diagnostics
```

- [ ] **Step 4: 更新 `validate/validator.py` 组合调用**

在 `validate_workflow()` 中的 `check_security` 调用后追加：

```python
from prompt2langgraph.validate.security import (
    check_external_policy,
    check_model_whitelist,
    check_tool_refs,
)
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

# 在 validate_workflow() 中，check_security 调用之后：
# ... check_security(spec, node_registry) ...
# diagnostics.extend(check_external_policy(spec))
# diagnostics.extend(check_model_whitelist(spec))
```

需要修改 `validate_workflow()` 签名增加 `tool_registry` 参数：

```python
def validate_workflow(
    workflow: WorkflowSpec | dict[str, Any],
    *,
    nodes: NodeRegistry | None = None,
    executors: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> ValidationReport:
```

并在调用处传入：

```python
    _tool_registry = tool_registry or ToolCallableRegistry()
    # ...
    diagnostics.extend(check_external_policy(spec))
    diagnostics.extend(check_model_whitelist(spec))
    diagnostics.extend(check_tool_refs(spec, _tool_registry))
```

同时修改 `_check_registries()` 函数，增加对 `dynamic=True` executor 的显式放行逻辑：

```python
def _check_registries(
    spec: WorkflowSpec,
    node_registry: NodeRegistry,
    executor_registry: ExecutorRegistry,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for node in spec.nodes:
        # ... 现有 kind 校验逻辑不变 ...

        # executor ref 校验
        if not executor_registry.has(node.executor.ref):
            # dynamic=True 的 schema-only definition 必须预先注册
            diagnostics.append(
                Diagnostic(
                    code=E_VAL_003,
                    severity="error",
                    message=f'node "{node.id}" executor ref "{node.executor.ref}" is not registered',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )
            continue

        definition = executor_registry.get(node.executor.ref)

        # dynamic executor 允许 handler=None，跳过 handler 校验
        if definition.handler is None and not definition.dynamic:
            diagnostics.append(
                Diagnostic(
                    code=E_VAL_003,
                    severity="error",
                    message=(
                        f'node "{node.id}" executor "{node.executor.ref}" has no handler '
                        f'and is not marked as dynamic'
                    ),
                    location=DiagnosticLocation(node_id=node.id),
                    hint="Either provide a handler or set dynamic=True on the executor definition.",
                )
            )
            continue

        # 非 dynamic executor 继续走现有 handler 调用校验逻辑
        # ...
    return diagnostics
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_security_policy.py -v`

Expected: PASS

- [ ] **Step 6: 运行现有 validator 测试确认回归通过**

Run: `uv run pytest tests/test_validator.py -v`

Expected: PASS

- [ ] **Step 7: 提交本任务**

```bash
git add src/prompt2langgraph/validate/security.py src/prompt2langgraph/validate/validator.py tests/test_security_policy.py
git commit -m "feat: add external call and tool ref security validation checks"
```

---

### Task 7：扩展编译器以支持动态 Executor Dispatch

**目标：** 修改 `compiler/langgraph_py.py`，使 `_node_wrapper()` 和 `compile_workflow_to_graph()` 支持 `ExecutorType.LLM` / `PYTHON_CALLABLE` 的动态 dispatch，传入 `policies`、`model_client`、`tool_registry`、`error_sink` 参数。

**Files:**
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Test: `tests/test_langgraph_compiler.py`

- [ ] **Step 1: 写编译器动态 dispatch 测试**

```python
# tests/test_langgraph_compiler.py 追加

from prompt2langgraph.ir.models import (
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    PolicySpec,
    StateSchema,
    WorkflowSpec,
)
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry


class FakeModel:
    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content="fake response")


def test_compile_workflow_with_llm_executor_node() -> None:
    workflow = WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_llm",
        name="TestLLM",
        entrypoint="llm_node",
        state_schema=StateSchema(
            channels={"question": {"type": "string"}},
            input={"question": {"type": "string"}},
            output={"answer": {"type": "string"}},
        ),
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
                inputs={"question": {"state_key": "question"}},
                outputs={"answer": {"state_key": "answer"}},
            )
        ],
        edges=[
            EdgeSpec(id="e1", source="llm_node", target="__end__", kind=EdgeKind.LINEAR)
        ],
        policies=PolicySpec(external_call=True, allowed_models=["qwen-plus"]),
    )

    executors = builtin_executor_registry()
    executors.register(
        ExecutorDefinition(
            ref="llm.qwen-plus",
            type=ExecutorType.LLM,
            input_schema={"question": {"type": "string"}},
            output_schema={"answer": {"type": "string"}},
            dynamic=True,
            handler=None,
        )
    )

    from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph

    graph = compile_workflow_to_graph(
        workflow,
        executors,
        policies=workflow.policies,
        model_client=FakeModel(),
    )

    result = graph.invoke({"question": "What is AI?"})
    assert result["answer"] == "fake response"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_langgraph_compiler.py::test_compile_workflow_with_llm_executor_node -v`

Expected: FAIL，提示函数签名不匹配或执行失败。

- [ ] **Step 3: 修改 `compile_workflow_to_graph()` 签名和调用**

```python
from prompt2langgraph.ir.models import PolicySpec
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.registry.executors import ExecutorError

NodeErrorSink = Callable[[ExecutorError], None]


def compile_workflow_to_graph(
    workflow: WorkflowSpec,
    executors: ExecutorRegistry,
    *,
    event_sink: NodeEventSink | None = None,
    checkpointer: Any | None = None,
    policies: PolicySpec | None = None,
    model_client: Any | None = None,
    tool_registry: ToolCallableRegistry | None = None,
    error_sink: NodeErrorSink | None = None,
    metrics_sink: Callable[[ExternalCallRecord], None] | None = None,
):
    # ... 现有逻辑 ...
    _policies = policies or workflow.policies

    for node in workflow.nodes:
        builder.add_node(
            node.id,
            _node_wrapper(
                node,
                executors,
                event_sink,
                loop_edges_by_source.get(node.id, []),
                workflow.state_schema.reducers,
                fanout_result_keys,
                policies=_policies,
                model_client=model_client,
                tool_registry=tool_registry,
                error_sink=error_sink,
                metrics_sink=metrics_sink,
            ),
        )
```

- [ ] **Step 4: 修改 `_node_wrapper()` 签名和 `invoke_node()` 内部 dispatch**

```python
def _node_wrapper(
    node: NodeSpec,
    executors: ExecutorRegistry,
    event_sink: NodeEventSink | None,
    loop_edges: list[EdgeSpec],
    reducers: dict[str, ReducerName],
    fanout_result_keys: set[str],
    *,
    policies: PolicySpec | None = None,
    model_client: Any | None = None,
    tool_registry: ToolCallableRegistry | None = None,
    error_sink: NodeErrorSink | None = None,
    metrics_sink: Callable[[ExternalCallRecord], None] | None = None,
):
    executor = executors.get(node.executor.ref)

    def invoke_node(state: dict[str, Any]) -> dict[str, Any]:
        if event_sink is not None:
            event_sink("node.started", node.id)
        inputs = {
            input_name: _state_value(state, selector.state_key, node.id)
            for input_name, selector in node.inputs.items()
        }
        try:
            raw_outputs = _invoke_executor(
                node,
                executor,
                inputs,
                policies=policies,
                model_client=model_client,
                tool_registry=tool_registry,
                metrics_sink=metrics_sink,
            )
        except ExecutorError as exc:
            exc.node_id = node.id
            if error_sink is not None:
                error_sink(exc)
            raise
        # ... 现有 output mapping 和 loop counter 逻辑不变 ...
        update = {}
        for output_name, selector in node.outputs.items():
            if output_name not in raw_outputs:
                raise RuntimeError(
                    f'node "{node.id}" executor omitted declared output "{output_name}"'
                )
            output_value = raw_outputs[output_name]
            if (
                selector.state_key in fanout_result_keys
                and reducers.get(selector.state_key) is ReducerName.APPEND
                and not isinstance(output_value, list)
            ):
                output_value = [output_value]
            update[selector.state_key] = output_value
        for edge in loop_edges:
            if edge.loop_guard is None:
                continue
            counter_key = edge.loop_guard.counter_key
            counts = dict(state.get(counter_key, {}))
            counts[edge.id] = int(counts.get(edge.id, 0)) + 1
            update[counter_key] = counts
        if event_sink is not None:
            event_sink("node.finished", node.id)
        return update

    return invoke_node


def _invoke_executor(
    node: NodeSpec,
    executor: ExecutorDefinition,
    inputs: dict[str, Any],
    *,
    policies: PolicySpec | None = None,
    model_client: Any | None = None,
    tool_registry: ToolCallableRegistry | None = None,
    metrics_sink: Callable[[ExternalCallRecord], None] | None = None,
) -> dict[str, Any]:
    """Dispatch executor invocation based on executor type and dynamic flag.

    When ``policies.collect_metrics`` is True and ``metrics_sink`` is provided,
    successful external calls are recorded via ``metrics_sink`` with timing info.
    Failed calls are recorded by the ``error_sink`` in the caller.
    """
    import time

    is_external = (
        (executor.dynamic and executor.type is ExecutorType.LLM)
        or (executor.dynamic and executor.type is ExecutorType.PYTHON_CALLABLE)
    )
    should_record = is_external and policies is not None and policies.collect_metrics and metrics_sink is not None

    if executor.dynamic and executor.type is ExecutorType.LLM:
        if model_client is None:
            raise ExecutorError(
                E_SEC_013,
                f'node "{node.id}" requires model_client but none was provided',
                node_id=node.id,
            )
        from prompt2langgraph.registry.llm_executor import LLMExecutor
        llm = LLMExecutor(model_client=model_client)
        start = time.monotonic()
        result = llm(inputs, node.params)
        if should_record:
            elapsed_ms = (time.monotonic() - start) * 1000
            model_id = node.executor.ref[len("llm."):] if node.executor.ref.startswith("llm.") else None
            metrics_sink(ExternalCallRecord(
                node_id=node.id,
                executor_ref=node.executor.ref,
                model=model_id,
                latency_ms=round(elapsed_ms, 1),
                status="succeeded",
            ))
        return result

    if executor.dynamic and executor.type is ExecutorType.PYTHON_CALLABLE:
        if tool_registry is None:
            raise ExecutorError(
                E_SEC_015,
                f'node "{node.id}" requires tool_registry but none was provided',
                node_id=node.id,
            )
        timeout_s = (
            node.timeout_s
            or (policies.default_timeout_s if policies else 60)
        )
        from prompt2langgraph.registry.tool_executor import ToolExecutor
        tool = ToolExecutor(
            registry=tool_registry,
            tool_ref=node.executor.ref,
            timeout_s=timeout_s,
        )
        start = time.monotonic()
        result = tool(inputs, node.params)
        if should_record:
            elapsed_ms = (time.monotonic() - start) * 1000
            metrics_sink(ExternalCallRecord(
                node_id=node.id,
                executor_ref=node.executor.ref,
                latency_ms=round(elapsed_ms, 1),
                status="succeeded",
            ))
        return result

    # Fall through to existing handler path for BUILTIN etc.
    return executor.invoke(inputs, node.params)
```

> **Note:** `runtime/artifacts.py` 的 `_validate_and_compile_target()` 也调用 `compile_workflow_to_graph()`。
> 扩展签名后，应确保传入 `policies=normalized.policies`，使编译器拥有策略上下文用于验证；
> `model_client` 和 `tool_registry` 保持为 `None`（编译阶段不执行真实外部调用）。

> **预留路径：LangGraph 原生 RetryPolicy 映射**
>
> 当前第二期不实现自动重试，但为后续版本预留以下映射路径：
>
> 当 `NodeSpec.retry.max_attempts > 1` 时，可将 `langgraph.types.RetryPolicy` 传给 `builder.add_node()` 的 `retry_policy=` 参数，让 LangGraph 框架层统一管理重试。
>
> **兼容性注意**：当前 `_invoke_executor()` 中 LLM/Tool 的异常已转为 `ExecutorError(RuntimeError)` 抛出。LangGraph 的 `RetryPolicy` 默认 `retry_on` 使用 `default_retry_on`，该策略会排除 `RuntimeError`（及 `ValueError`、`TypeError` 等编程错误），因此后续启用自动重试时需要自定义 `retry_on` 回调以包含 `ExecutorError`，或将 `ExecutorError` 改为继承非 `RuntimeError` 的异常基类。
>
> 参考文档：[LangGraph Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_langgraph_compiler.py -v`

Expected: PASS

- [ ] **Step 6: 提交本任务**

```bash
git add src/prompt2langgraph/compiler/langgraph_py.py tests/test_langgraph_compiler.py
git commit -m "feat: add dynamic executor dispatch for ExecutorType.LLM and PYTHON_CALLABLE"
```

---

### Task 8：扩展 Runtime Events 与 Runner

**目标：** 扩展 `RunMetrics`、新增 `ExternalCallRecord`，修改 `run_workflow()` 对接 `error_sink` 回调、metrics 收集和 `external_calls` 汇总。

**Files:**
- Modify: `src/prompt2langgraph/runtime/events.py`
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: 写 RunMetrics 和 ExternalCallRecord 测试**

```python
# tests/test_runner.py 追加

from prompt2langgraph.runtime.events import ExternalCallRecord, RunMetrics, RunResult


def test_run_metrics_has_phase2_fields() -> None:
    m = RunMetrics()
    assert m.call_count == 0
    assert m.total_latency_ms is None


def test_external_call_record_fields() -> None:
    record = ExternalCallRecord(
        node_id="n1",
        executor_ref="llm.qwen-plus",
        model="qwen-plus",
        latency_ms=150.5,
        token_count=42,
        status="succeeded",
    )
    assert record.node_id == "n1"
    assert record.model == "qwen-plus"
    assert record.status == "succeeded"


def test_run_result_has_external_calls_default_empty() -> None:
    result = RunResult(
        status="succeeded",
        run_id="run_1",
        thread_id="thread_1",
    )
    assert result.external_calls == []


def test_external_call_record_succeeded_status() -> None:
    """collect_metrics=True 时成功调用应记录 status='succeeded' 的 ExternalCallRecord。"""
    record = ExternalCallRecord(
        node_id="n1",
        executor_ref="llm.qwen-plus",
        model="qwen-plus",
        latency_ms=120.3,
        status="succeeded",
    )
    assert record.status == "succeeded"
    assert record.error_code is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_runner.py -v -k "phase2 or external_call"`

Expected: FAIL，提示字段不存在。

- [ ] **Step 3: 扩展 `runtime/events.py`**

```python
# RunMetrics 新增字段
class RunMetrics(BaseModel):
    duration_ms: float | None = None
    token_count: int | None = None
    retry_count: int = 0
    tool_call_count: int = 0
    call_count: int = 0
    total_latency_ms: float | None = None

# 新增 ExternalCallRecord
class ExternalCallRecord(BaseModel):
    node_id: str
    executor_ref: str
    model: str | None = None
    latency_ms: float | None = None
    token_count: int | None = None
    status: Literal["succeeded", "failed"]
    error_code: str | None = None

# RunResult 新增字段
class RunResult(BaseModel):
    status: Literal["succeeded", "failed", "waiting"]
    run_id: str
    thread_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    events: list[RunEvent] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    interrupt: RunInterrupt | None = None
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    external_calls: list[ExternalCallRecord] = Field(default_factory=list)
```

- [ ] **Step 4: 修改 `runtime/runner.py`**

在 `run_workflow()` 中增加 `model_client`、`tool_registry` 参数，并传递到 `compile_workflow_to_graph()`：

```python
def run_workflow(
    workflow: WorkflowSpec,
    input_payload: dict[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
    thread_id: str | None = None,
    resume_payload: Any = _NO_RESUME,
    state_store_dir: Path | None = None,
    model_client: Any | None = None,
    tool_registry: Any | None = None,
) -> RunResult:
```

在 `compile_workflow_to_graph()` 调用处传入新参数，并增加 `error_sink` 和 `metrics_sink` 回调用于收集 `ExecutorError` 和成功调用的 `ExternalCallRecord`：

```python
    external_calls: list[ExternalCallRecord] = []

    def error_sink(exc: ExecutorError) -> None:
        if exc.node_id is None:
            return
        external_calls.append(
            ExternalCallRecord(
                node_id=exc.node_id,
                executor_ref="unknown",
                status="failed",
                error_code=exc.code,
            )
        )

    def metrics_sink(record: ExternalCallRecord) -> None:
        external_calls.append(record)

    graph = compile_workflow_to_graph(
        workflow,
        executor_registry,
        event_sink=record_node_event,
        checkpointer=checkpointer,
        policies=workflow.policies,
        model_client=model_client,
        tool_registry=tool_registry,
        error_sink=error_sink,
        metrics_sink=metrics_sink,
    )
```

在 `RunResult` 构造时传入 `external_calls`。

- [ ] **Step 4.1: 更新 CLI `run` 命令传递 `model_client` 和 `tool_registry`**

在 `cli.py` 的 `run` 命令中，当 workflow 包含 `ExecutorType.LLM` 或 `ExecutorType.PYTHON_CALLABLE` 节点时，需要构造 `model_client` 和 `tool_registry` 并传入 `run_workflow()`：

```python
# cli.py run 命令中，在调用 run_workflow() 之前：
from prompt2langgraph.llm.provider import build_llm_client
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

model_client = None
tool_registry = None

# 检查 workflow 是否需要外部执行能力
has_llm_nodes = any(
    node.executor.type is ExecutorType.LLM
    for node in spec.nodes
)
has_tool_nodes = any(
    node.executor.type is ExecutorType.PYTHON_CALLABLE
    for node in spec.nodes
)

if has_llm_nodes and spec.policies.external_call:
    model_client = build_llm_client()

if has_tool_nodes:
    tool_registry = ToolCallableRegistry()
    # 内置 tool 可在此注册，或由用户通过配置文件加载

result = run_workflow(
    spec,
    input_payload,
    model_client=model_client,
    tool_registry=tool_registry,
)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_runner.py -v`

Expected: PASS

- [ ] **Step 6: 提交本任务**

```bash
git add src/prompt2langgraph/runtime/events.py src/prompt2langgraph/runtime/runner.py tests/test_runner.py
git commit -m "feat: extend RunMetrics and RunResult for external call tracking"
```

---

### Task 9：补齐集成测试

**目标：** 以 fake provider 和 fake tool 覆盖 LLM executor + tool executor 的完整链路测试。

**Files:**
- Create: `tests/fake_provider.py`
- Create: `tests/fake_tools.py`
- Create: `tests/test_integration_execution.py`

- [ ] **Step 1: 创建 `tests/fake_provider.py`**

```python
"""Fake LLM provider for testing, based on LangChain GenericFakeChatModel."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.language_models.chat_models import BaseChatModel


def fake_chat_model(
    response_text: str = "fake response",
    *,
    usage_metadata: dict | None = None,
) -> BaseChatModel:
    """Create a fake chat model that returns a fixed response.

    Uses LangChain's built-in GenericFakeChatModel for compatibility with
    the BaseChatModel interface.

    Note: GenericFakeChatModel accepts an iterator of messages (str or AIMessage).
    Strings are automatically wrapped in AIMessage by GenericFakeChatModel.
    If usage_metadata is needed, use a custom fake model instead.
    """
    return GenericFakeChatModel(messages=iter([response_text]))
```

- [ ] **Step 2: 创建 `tests/fake_tools.py`**

```python
"""Fake tool callables for integration testing."""

from typing import Any


def fake_tool_echo(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {"output": inputs.get("input", "")}


def fake_tool_upper(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {"output": str(inputs.get("input", "")).upper()}


def fake_tool_fail(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("fake tool failure")


FAKE_TOOLS: dict[str, Any] = {
    "tool.echo": fake_tool_echo,
    "tool.upper": fake_tool_upper,
    "tool.fail": fake_tool_fail,
}
```

- [ ] **Step 3: 创建 `tests/test_integration_execution.py`**

```python
"""Integration tests for LLM and Tool executor with fake providers."""

from prompt2langgraph.ir.models import (
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    PolicySpec,
    StateSchema,
    WorkflowSpec,
)
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from tests.fake_provider import fake_chat_model
from tests.fake_tools import fake_tool_echo, fake_tool_upper, fake_tool_fail


def _make_llm_executor_registry() -> ExecutorRegistry:
    registry = builtin_executor_registry()
    registry.register(
        ExecutorDefinition(
            ref="llm.qwen-plus",
            type=ExecutorType.LLM,
            input_schema={"question": {"type": "string"}},
            output_schema={"answer": {"type": "string"}},
            dynamic=True,
            handler=None,
        )
    )
    return registry


def test_full_execution_llm_node_with_fake_provider() -> None:
    workflow = WorkflowSpec(
        schema_version="0.1",
        workflow_id="integ_llm",
        name="IntegLLM",
        entrypoint="ask",
        state_schema=StateSchema(
            channels={"question": {"type": "string"}, "answer": {"type": "string"}},
            input={"question": {"type": "string"}},
            output={"answer": {"type": "string"}},
        ),
        nodes=[
            NodeSpec(
                id="ask",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
                inputs={"question": {"state_key": "question"}},
                outputs={"answer": {"state_key": "answer"}},
            )
        ],
        edges=[EdgeSpec(id="e1", source="ask", target="__end__", kind=EdgeKind.LINEAR)],
        policies=PolicySpec(external_call=True, allowed_models=["qwen-plus"]),
    )
    graph = compile_workflow_to_graph(
        workflow,
        _make_llm_executor_registry(),
        policies=workflow.policies,
        model_client=fake_chat_model("hello from fake model"),
    )
    result = graph.invoke({"question": "hi"})
    assert result["answer"] == "hello from fake model"


def test_full_execution_mock_and_real_executor_coexist() -> None:
    workflow = WorkflowSpec(
        schema_version="0.1",
        workflow_id="mix_exec",
        name="MixExec",
        entrypoint="transform",
        state_schema=StateSchema(
            channels={
                "question": {"type": "string"},
                "value": {"type": "string"},
                "answer": {"type": "string"},
            },
            input={"question": {"type": "string"}},
            output={"answer": {"type": "string"}},
        ),
        nodes=[
            NodeSpec(
                id="transform",
                kind="transform",
                executor=ExecutorRef(ref="builtin.identity_transform", type=ExecutorType.BUILTIN),
                inputs={"value": {"state_key": "question"}},
                outputs={"value": {"state_key": "value"}},
            ),
            NodeSpec(
                id="ask",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
                inputs={"question": {"state_key": "value"}},
                outputs={"answer": {"state_key": "answer"}},
            ),
        ],
        edges=[
            EdgeSpec(id="e1", source="transform", target="ask", kind=EdgeKind.LINEAR),
            EdgeSpec(id="e2", source="ask", target="__end__", kind=EdgeKind.LINEAR),
        ],
        policies=PolicySpec(external_call=True, allowed_models=["qwen-plus"]),
    )
    graph = compile_workflow_to_graph(
        workflow,
        _make_llm_executor_registry(),
        policies=workflow.policies,
        model_client=fake_chat_model("transformed response"),
    )
    result = graph.invoke({"question": "original"})
    assert result["answer"] == "transformed response"


def test_full_execution_tool_node_with_fake_registry() -> None:
    tool_registry = ToolCallableRegistry()
    tool_registry.register("tool.echo", fake_tool_echo)

    workflow = WorkflowSpec(
        schema_version="0.1",
        workflow_id="integ_tool",
        name="IntegTool",
        entrypoint="t1",
        state_schema=StateSchema(
            channels={"input": {"type": "string"}, "output": {"type": "string"}},
            input={"input": {"type": "string"}},
            output={"output": {"type": "string"}},
        ),
        nodes=[
            NodeSpec(
                id="t1",
                kind="tool",
                executor=ExecutorRef(ref="tool.echo", type=ExecutorType.PYTHON_CALLABLE),
                inputs={"input": {"state_key": "input"}},
                outputs={"output": {"state_key": "output"}},
            )
        ],
        edges=[EdgeSpec(id="e1", source="t1", target="__end__", kind=EdgeKind.LINEAR)],
        policies=PolicySpec(allowed_tool_refs=["tool.echo"]),
    )

    registry = builtin_executor_registry()
    registry.register(
        ExecutorDefinition(
            ref="tool.echo",
            type=ExecutorType.PYTHON_CALLABLE,
            input_schema={"input": {"type": "string"}},
            output_schema={"output": {"type": "string"}},
            dynamic=True,
            handler=None,
        )
    )

    graph = compile_workflow_to_graph(
        workflow,
        registry,
        policies=workflow.policies,
        tool_registry=tool_registry,
    )
    result = graph.invoke({"input": "hello tool"})
    assert result["output"] == "hello tool"
```

- [ ] **Step 4: （已合并到 Step 2，无需重复）**

- [ ] **Step 5: 运行集成测试确认通过**

Run: `uv run pytest tests/test_integration_execution.py -v`

Expected: PASS

- [ ] **Step 6: 提交本任务**

```bash
git add tests/fake_provider.py tests/fake_tools.py tests/test_integration_execution.py
git commit -m "test: add integration tests for llm and tool executor with fake providers"
```

---

### Task 10：更新 Policy Resolver 与 Binding Binder

**目标：** 将新增策略字段纳入 `resolve_policies()`、`bind_workflow()` 和 `normalize_workflow()` 的输出，确保 `workflow.ir.json` / `workflow.lock.json` 正确序列化。

**Files:**
- Modify: `src/prompt2langgraph/policy/resolver.py`
- Modify: `src/prompt2langgraph/binding/binder.py`
- Modify: `src/prompt2langgraph/ir/normalize.py`
- Test: `tests/test_compile_flow.py`

- [ ] **Step 1: 修改 `policy/resolver.py`**

```python
# resolve_policies() 中新增策略摘要

class ResolvedWorkflow(BaseModel):
    workflow: WorkflowSpec
    node_policies: dict[str, dict[str, Any]] = Field(default_factory=dict)
    external_call: bool = False
    allowed_models: list[str] = Field(default_factory=list)
    collect_metrics: bool = False
    allowed_tool_refs: list[str] = Field(default_factory=list)


def resolve_policies(
    workflow: WorkflowSpec,
    *,
    nodes: NodeRegistry | None = None,
    compile_options: dict[str, Any] | None = None,
) -> ResolvedWorkflow:
    # ... 现有逻辑 ...
    return ResolvedWorkflow(
        workflow=workflow,
        node_policies=node_policies,
        external_call=workflow.policies.external_call,
        allowed_models=list(workflow.policies.allowed_models),
        collect_metrics=workflow.policies.collect_metrics,
        allowed_tool_refs=list(workflow.policies.allowed_tool_refs),
    )
```

- [ ] **Step 2: 修改 `binding/binder.py`**

```python
# bind_workflow() 中对 dynamic executor 和 allowed_models/tool_refs 的记录

def bind_workflow(
    workflow: WorkflowSpec,
    *,
    executors: ExecutorRegistry | None = None,
) -> BoundWorkflow:
    registry = executors or builtin_executor_registry()
    bindings: dict[str, dict[str, Any]] = {}
    for node in workflow.nodes:
        executor = registry.get(node.executor.ref)
        bindings[node.id] = {
            "executor": executor.ref,
            "type": executor.type.value,
            "capabilities": list(executor.required_capabilities),
            "dynamic": executor.dynamic,
            "allowed_models": list(workflow.policies.allowed_models),
            "external_call": workflow.policies.external_call,
        }
    return BoundWorkflow(workflow=workflow, executor_bindings=bindings)
```

- [ ] **Step 3: 确认 `ir/normalize.py` 中的 `normalize_workflow()` 正确序列化新增策略字段**

`normalize_workflow()` 需要对 `PolicySpec` 的新增字段（`external_call`、`allowed_models`、`collect_metrics`、`allowed_tool_refs`）和 `NodeSpec` 的新增字段（`timeout_s`）进行规范化处理。确认点：

1. `workflow.ir.json` 中包含补齐后的 policy 默认值（如 `"external_call": false`、`"allowed_models": []`）；
2. `workflow.lock.json` 中包含相同字段，确保 lockfile hash 计算稳定；
3. 旧 workflow JSON（缺少新增字段）经过 `normalize_workflow()` 后，输出包含 Pydantic 默认值补齐的结果；
4. 现有 golden fixtures（`linear_llm/`、`fanout_map_reduce/` 等）的 `workflow.ir.json` 需确认是否需要更新以反映新增的 policy 字段。

> **验证命令**：
> ```bash
> uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
> # 检查 build/linear_llm/workflow.ir.json 中是否包含 external_call、allowed_models 等字段
> ```

- [ ] **Step 4: 运行编译产物回归测试**

Run: `uv run pytest tests/test_compile_flow.py -v`

Expected: PASS（现有测试通过，compile report 可能因新增字段而产生 diff，需要更新 golden fixtures）。

- [ ] **Step 5: 提交本任务**

```bash
git add src/prompt2langgraph/policy/resolver.py src/prompt2langgraph/binding/binder.py src/prompt2langgraph/ir/normalize.py tests/test_compile_flow.py
git commit -m "feat: extend policy resolver, binder, and normalizer with phase-2 policy fields"
```

---

### Task 11：更新文档与全量回归

**目标：** 更新 `README.md`、`CLAUDE.md`、`AGENTS.md`，确保文档与第二期能力一致。执行全量回归测试。

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Test: 全量 `tests/`

- [ ] **Step 1: 更新 README.md**

需要补充的内容：

- `llm` 节点现在可通过 `ExecutorType.LLM`（ref 格式 `llm.<model_id>`）调用真实模型；
- `tool` 节点现在可通过 `ExecutorType.PYTHON_CALLABLE` 执行预注册、受信任的纯 Python callable；
- 真实执行依赖外部 LLM API，需通过 `.env` 配置 `MODEL`、`BASE_URL`、`API_KEY`；
- 新增策略约束体系：`external_call`（默认 `false`）、`allowed_models`（模型白名单）、`allowed_tool_refs`（工具白名单）、`collect_metrics`（运行时调用记录）；
- `.env` 配置现在同时服务于 Prompt 计划生成和运行时 LLM 执行；
- 区分 `plan` 命令使用的 LLM（第一期能力）和运行时 `llm` 节点使用的 LLM（第二期能力）。

新增 CLI 示例：

```bash
# 配置 .env
echo 'MODEL=qwen-plus' > .env
echo 'BASE_URL=https://your-endpoint/v1' >> .env
echo 'API_KEY=your-api-key' >> .env

# 运行包含真实 LLM executor 的 workflow
uv run pt2lg run workflow_with_real_llm.json --input '{"question":"What is AI?"}' --json
```

- [ ] **Step 2: 更新 CLAUDE.md**

需要补充的内容：

- `llm/` 顶层模块作为 LLM 客户端构造的共享入口；
- `registry/llm_executor.py` 和 `registry/tool_executor.py` 是新的动态 executor；
- `ExecutorType.LLM` 和 `ExecutorType.PYTHON_CALLABLE` 通过 `dynamic=True` 的 schema-only definition 注册，运行时动态实例化；
- 策略约束在 `validate_workflow()` 阶段即被检查，新增 `check_external_policy`、`check_model_whitelist`、`check_tool_refs`；
- `model_client` 通过闭包注入，不在 executor 内部自行创建 client。

- [ ] **Step 3: 更新 AGENTS.md**

需要补充的内容：

- runtime `llm` 节点现在具备真实执行能力（需要 `external_call=True` 和 `allowed_models`）；
- runtime `tool` 节点现在具备受控执行能力（需要 `allowed_tool_refs` 和 `ToolCallableRegistry`）；
- 策略默认安全关闭：`external_call=False`，旧 workflow 必须显式启用；
- `.env` 配置同时服务于 Prompt 计划生成和运行时 LLM 执行；
- 新增回归要求：修改 executor dispatch 或策略校验后，需跑 `tests/test_security_policy.py`、`tests/test_integration_execution.py`。

- [ ] **Step 4: 运行全量回归**

```bash
# 运行所有测试
uv run pytest

# 运行 Prompt 相关定向测试（确认重构后行为不变）
uv run pytest tests/test_prompt_planner.py tests/test_prompt_parser.py tests/test_public_api.py tests/test_cli.py -v

# 运行第二期新增测试
uv run pytest tests/test_llm_provider.py tests/test_llm_executor.py tests/test_tool_executor.py tests/test_security_policy.py tests/test_integration_execution.py -v
```

Expected: 全量 PASS

- [ ] **Step 5: 手工 CLI 验收**

```bash
# 确认现有命令不受影响
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --json
```

Expected: 所有命令正常输出。

- [ ] **Step 6: 提交文档修改**

```bash
git add README.md CLAUDE.md AGENTS.md
git commit -m "docs: document phase-2 real execution capabilities and security policies"
```

---

### Task 12：补齐 Edge Case 与回归确认

**目标：** 确保旧 fixture 加载兼容、lockfile hash 一致、异常路径覆盖。

**Files:**
- Test: `tests/test_compile_flow.py`
- Test: `tests/test_validator.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: 写旧 fixture 兼容性测试**

```python
# tests/test_compile_flow.py 追加


def test_old_fixture_loads_with_new_policy_defaults() -> None:
    """旧 workflow JSON（缺少新增 policy 字段）应能正常加载，按 Pydantic 默认值补齐。"""
    from prompt2langgraph.ir.models import WorkflowSpec

    old_workflow = {
        "schema_version": "0.1",
        "workflow_id": "old_test",
        "name": "old_test",
        "entrypoint": "n1",
        "state_schema": {
            "channels": {"question": {"type": "string"}, "answer": {"type": "string"}},
            "input": {"question": {"type": "string"}},
            "output": {"answer": {"type": "string"}},
        },
        "nodes": [
            {
                "id": "n1",
                "kind": "llm",
                "executor": {"ref": "builtin.echo_llm", "type": "builtin"},
            }
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "__end__", "kind": "linear"}],
        # 无 policies 字段
    }
    spec = WorkflowSpec.model_validate(old_workflow)
    assert spec.policies.external_call is False
    assert spec.policies.allowed_models == []
    assert spec.policies.collect_metrics is False


def test_lockfile_hash_consistent_with_new_policies() -> None:
    """lockfile hash 应包含补齐后的 policy 默认值。"""
    from prompt2langgraph.ir.lockfile import sha256_canonical_json
    from prompt2langgraph.ir.models import WorkflowSpec
    from prompt2langgraph.ir.normalize import normalize_workflow

    wf1 = WorkflowSpec(
        schema_version="0.1",
        workflow_id="hash_test",
        name="hash_test",
        entrypoint="n1",
        state_schema=StateSchema(channels={"q": {"type": "string"}, "a": {"type": "string"}}),
        nodes=[
            NodeSpec(
                id="n1",
                kind="llm",
                executor=ExecutorRef(ref="builtin.echo_llm", type=ExecutorType.BUILTIN),
            )
        ],
        edges=[EdgeSpec(id="e1", source="n1", target="__end__", kind=EdgeKind.LINEAR)],
    )
    hash1 = sha256_canonical_json(normalize_workflow(wf1).model_dump(mode="json"))
    hash2 = sha256_canonical_json(normalize_workflow(wf1).model_dump(mode="json"))
    assert hash1 == hash2
```

- [ ] **Step 2: 运行全量回归确认**

Run: `uv run pytest`

Expected: 全量 PASS

- [ ] **Step 3: 提交本任务**

```bash
git add tests/test_compile_flow.py tests/test_validator.py tests/test_runner.py
git commit -m "test: add backwards compatibility and lockfile hash regression tests"
```

---

## 四、执行顺序建议

建议严格按以下顺序推进：

1. **Task 1**：扩展诊断码与 IR 模型（无依赖，先行）；
2. **Task 2**：创建 LLM Provider 轻量抽象模块（无依赖，可并行与 Task 1）；
3. **Task 3**：重构 `prompting/planner.py` 委托给 `llm/` 模块（依赖 Task 2，完成后立即执行，作为 `llm/` 模块的第一个集成验证点）；
4. **Task 4**：实现真实 LLM Executor（依赖 Task 2）；
5. **Task 5**：实现 Tool Executor 最小受控模型（与 Task 4 可并行）；
6. **Task 6**：实现策略校验层（依赖 Task 1 的 IR 模型扩展，与 Task 4/5 可并行）；
7. **Task 7**：扩展编译器以支持动态 Executor Dispatch（依赖 Task 4、5、6）；
8. **Task 8**：扩展 Runtime Events 与 Runner（依赖 Task 7）；
9. **Task 9**：补齐集成测试（依赖 Task 4、5、7）；
10. **Task 10**：更新 Policy Resolver 与 Binding Binder（依赖 Task 1、6）；
11. **Task 11**：更新文档与全量回归（依赖所有前序任务）；
12. **Task 12**：补齐 Edge Case 与回归确认（依赖所有前序任务）。

```
Task 1 (IR + 诊断码) ──┬──→ Task 6 (策略校验) ──→ Task 7 (编译器) ──→ Task 8 (Runner)
                       │                                        │
Task 2 (llm/ 模块) ────┼──→ Task 3 (重构 planner) ← 紧随 Task 2 │
                       │                                        │
                       ├──→ Task 4 (LLM Executor) ──────────────┤
                       │                                        │
                       └──→ Task 5 (Tool Executor) ─────────────┤
                                                                │
                       ←── Task 10 (Resolver + Binder)          │
                                                                ↓
                                                          Task 9 (集成测试)
                                                                │
                                                                ↓
                                                          Task 11 (文档 + 回归)
                                                                │
                                                                ↓
                                                          Task 12 (Edge Case)
```

---

## 五、关键注意事项

1. 不在 bundle/lockfile 中写入真实 secret 或 secret 名称；
2. `builtin.echo_llm` 保留为 mock/fallback，行为和注册路径不变；
3. `ExecutorType.LLM` 的 ref 格式约定为 `llm.<model_id>`，`model_id` 必须在 `allowed_models` 白名单中；
4. `security.py` 新增的函数必须独立可测试，不在函数内部导入 `ToolCallableRegistry` 的默认实例（由调用方注入）；
5. 动态 executor 必须在 `ExecutorRegistry` 中注册 schema-only definition（`dynamic=True, handler=None`），验证阶段保留 ref/type/schema 校验；
6. `_check_registries()` 中允许 `definition.dynamic=True` 且 `handler is None` 的 executor 通过校验；`definition.dynamic=False` 且 `handler=None` 应报 `E_VAL_003` 诊断；
7. `ToolExecutor` 不做 subprocess 沙箱、Docker 隔离或网络访问控制；
8. 不在 CLI 中新增 `prompt run` 之类的二次入口；
9. 不在 `prompt2langgraph.cli` 模块导入阶段急切初始化 `langchain_openai` 客户端；
10. 保持现有 JSON plan / Workflow IR 入口测试全部稳定通过；
11. 文档更新不止 `README.md`，还必须同步 `CLAUDE.md` 和 `AGENTS.md`；
12. 所有新增 executor 通过 fake provider 独立测试，不依赖真实网络调用；
13. CLI `run` 命令需要在运行时根据 workflow 中的节点类型自动构造 `model_client` 和 `tool_registry`，并传入 `run_workflow()`；
14. `collect_metrics=True` 时，成功调用和失败调用均需记录 `ExternalCallRecord`（成功通过 `metrics_sink`，失败通过 `error_sink`）；
15. `check_tool_refs()` 中 `effective_allowed` 为 `None` 或空列表时，按默认安全原则报 `E_SEC_015` 诊断；
16. `GenericFakeChatModel` 接受 `messages=iter([...])` 迭代器参数，其中可传入 `str` 或 `AIMessage` 实例。

---

## 六、完成判定

当以下条件全部满足时，可判定 v0.2 第二期实施完成：

- 顶层 `llm/` 轻量基础模块已就绪，`prompting/planner.py` 的 `build_model_client()` 已委托给 `llm.provider.build_llm_client()`；
- `llm` 节点可通过 `ExecutorType.LLM`（ref 格式 `llm.<model_id>`）调用真实模型，fake provider 下可验证完整调用链路；
- `tool` 节点可通过 `ExecutorType.PYTHON_CALLABLE` 执行受信任、预注册且经 `allowed_tool_refs` 授权的纯 Python callable；
- 真实 executor 和 mock executor 可通过 executor ref 区分（`ref="builtin.echo_llm"` = mock，`ref="llm.qwen-plus"` = real），mock 行为完全兼容；
- 策略约束在 `validate_workflow()` 阶段即被检查：`external_call` 开关、`allowed_models` 白名单、`allowed_tool_refs` 白名单；
- `collect_metrics=True` 时，`RunResult.external_calls` 中可获取成功和失败调用的 `ExternalCallRecord`（成功通过 `metrics_sink`，失败通过 `error_sink`）；
- CLI `run` 命令能根据 workflow 节点类型自动构造 `model_client` 和 `tool_registry`，传入 `run_workflow()`；
- `tests/test_llm_provider.py`、`tests/test_llm_executor.py`、`tests/test_tool_executor.py`、`tests/test_security_policy.py`、`tests/test_integration_execution.py` 全部通过；
- 现有第一期测试基线全部通过（`tests/test_prompt_planner.py`、`tests/test_prompt_parser.py`、`tests/test_public_api.py`、`tests/test_cli.py`）；
- `README.md`、`CLAUDE.md`、`AGENTS.md` 已同步更新，明确区分 `plan` 命令使用的 LLM（第一期）和运行时 `llm` 节点使用的 LLM（第二期）；
- `uv run pytest` 全量通过；
- 未越界实现多 provider 适配、subprocess 沙箱、`join` edge 执行、`side_effect` 闭环等非目标能力。

---

## 附录 A：LangChain / LangGraph 官方文档参考索引

本计划中的设计决策参考了以下 LangChain/LangGraph v1 官方文档。

### LangGraph 核心

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Graph API 概览 | [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api) | Task 7 |
| 使用 Graph API（增量构建） | [Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api) | Task 7 |
| Nodes（节点函数签名） | [Nodes](https://docs.langchain.com/oss/python/langgraph/graph-api#nodes) | Task 7 |
| RetryPolicy 重试策略 | [Add retry policies](https://docs.langchain.com/oss/python/langgraph/use-graph-api#add-retry-policies) | Task 7 |
| Fault tolerance（超时 + 重试） | [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance) | Task 4 |

### LangChain Agent 与 Middleware

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| create_agent 概述 | [Agents](https://docs.langchain.com/oss/python/langchain/agents) | Task 4, 7 |
| Custom middleware（wrap_model_call） | [Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) | Task 6 |
| Middleware hooks 一览 | [Middleware hooks](https://docs.langchain.com/oss/python/releases/langchain-v1#custom-middleware) | Task 6 |

### 模型与工具

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Chat model 集成 | [Chat model integrations](https://docs.langchain.com/oss/python/integrations/chat/index) | Task 2 |
| Base URL 和代理设置 | [Base URL and proxy settings](https://docs.langchain.com/oss/python/langchain/models#base-url-and-proxy-settings) | Task 2 |
| Providers 概览 | [Providers overview](https://docs.langchain.com/oss/python/integrations/providers/overview) | Task 2 |
| Tools（@tool 装饰器） | [Tools](https://docs.langchain.com/oss/python/migrate/langchain-v1#tools) | Task 5 |

### 测试

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Unit testing（GenericFakeChatModel） | [Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing) | Task 9 |
| Integration testing | [Integration testing](https://docs.langchain.com/oss/python/langchain/test/integration-testing) | Task 9 |
| LangGraph 节点测试 | [Testing individual nodes](https://docs.langchain.com/oss/python/langgraph/test#getting-started) | Task 9 |

> **使用说明**：以上链接基于 LangChain/LangGraph v1 官方文档（docs.langchain.com），查询日期为 2026 年 5 月。后续实施时如遇链接失效，可通过 docs.langchain.com 搜索对应主题关键词获取最新页面。
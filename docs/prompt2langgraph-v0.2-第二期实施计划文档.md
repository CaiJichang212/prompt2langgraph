# prompt2langgraph v0.2 第二期实施计划文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v0.2 第一期已实现的 `Prompt -> LLM -> 简化 JSON plan -> WorkflowSpec` 输入闭环基础上，补齐真实 LLM 执行能力和受控 Tool 执行能力，引入策略与安全约束体系，使 Workflow 的 `llm` 和 `tool` 节点从 mock 运行演进为具备真实业务执行潜力的系统。

**Architecture:** 第二期新增顶层 `llm/` 轻量基础模块（提取第一期 `prompting/planner.py` 中的 LLM 客户端构造逻辑为共享依赖），新增 `LLMExecutor` 和 `ToolExecutor` 两种动态 executor，通过 `ExecutorType.LLM` / `ExecutorType.PYTHON_CALLABLE` 分发。`ExecutorType.LLM` 的 ref 格式约定为 `llm.<model_id>`，model_id 必须在 `allowed_models` 白名单中；`ExecutorType.PYTHON_CALLABLE` 的 ref 必须在 `ToolCallableRegistry` 和 `allowed_tool_refs` 白名单中。策略约束在 `validate_workflow()` 阶段即被检查，运行时只做防御性二次校验。所有新增 executor 通过 fake provider 独立测试，不依赖真实网络调用。

**Tech Stack:** Python 3.11, Typer, Pydantic, pytest, `langchain_openai`, `langchain_core.language_models.fake_chat_models.GenericFakeChatModel`, `BaseChatModel`, `SecretStr`, `concurrent.futures.ThreadPoolExecutor`.

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

## 二、改动文件结构

### 2.1 新增文件

| 文件 | 职责 |
|------|------|
| `src/prompt2langgraph/llm/__init__.py` | 包入口，导出 `LLMConfig`、`build_llm_client()`、`dict_messages_to_langchain` |
| `src/prompt2langgraph/llm/config.py` | `LLMConfig` Pydantic 模型 + `load_llm_config()` 从 `.env` 加载 |
| `src/prompt2langgraph/llm/provider.py` | `build_llm_client()` 统一构造 `ChatOpenAI` |
| `src/prompt2langgraph/llm/messages.py` | OpenAI-style dict messages 到 LangChain `BaseMessage` 的转换 |
| `src/prompt2langgraph/registry/llm_executor.py` | `LLMExecutor` 类，真实 LLM 节点执行器 |
| `src/prompt2langgraph/registry/tool_executor.py` | `ToolExecutor` 类 + `ToolCallableRegistry` |
| `tests/fake_provider.py` | 基于 `GenericFakeChatModel` 的 fake LLM provider |
| `tests/fake_tools.py` | 预注册 fake tool callable 集合 |
| `tests/test_llm_provider.py` | `LLMConfig` + `build_llm_client()` + 消息转换测试 |
| `tests/test_llm_executor.py` | `LLMExecutor` 单元测试（fake provider） |
| `tests/test_tool_executor.py` | `ToolExecutor` + `ToolCallableRegistry` 单元测试 |
| `tests/test_security_policy.py` | 新增策略约束校验函数测试 |
| `tests/test_integration_execution.py` | 集成测试：fake provider 下的完整图执行 |

### 2.2 修改文件

| 文件 | 改动要点 |
|------|----------|
| `src/prompt2langgraph/diagnostics/codes.py` | 新增 `E_LLM_001`~`E_LLM_003`、`E_SEC_013`~`E_SEC_015` |
| `src/prompt2langgraph/ir/models.py` | `PolicySpec` 新增 `external_call`、`allowed_models`、`collect_metrics`、`allowed_tool_refs`；`SecurityPolicy` 新增 `allowed_tool_refs` |
| `src/prompt2langgraph/registry/executors.py` | `ExecutorDefinition` 新增 `dynamic: bool = False`；新增 `ExecutorError` 异常类 |
| `src/prompt2langgraph/registry/builtins.py` | 新增 `llm.qwen-plus` 的 schema-only definition（`dynamic=True`） |
| `src/prompt2langgraph/compiler/langgraph_py.py` | `_node_wrapper()` / `compile_workflow_to_graph()` 扩展签名，新增动态 executor dispatch |
| `src/prompt2langgraph/validate/security.py` | 新增 `check_external_policy()`、`check_model_whitelist()`、`check_tool_refs()` |
| `src/prompt2langgraph/validate/validator.py` | `validate_workflow()` 组合调用新增策略校验，签名增加 `tool_registry` 参数 |
| `src/prompt2langgraph/policy/resolver.py` | `ResolvedWorkflow` 新增策略摘要字段；`resolve_policies()` 扩展 |
| `src/prompt2langgraph/binding/binder.py` | `bind_workflow()` 扩展，反映 dynamic executor 和新增策略字段 |
| `src/prompt2langgraph/runtime/events.py` | `RunMetrics` 新增 `call_count`、`total_latency_ms`；新增 `ExternalCallRecord`；`RunResult` 新增 `external_calls` |
| `src/prompt2langgraph/runtime/runner.py` | `run_workflow()` 新增 `model_client`、`tool_registry` 参数，对接 error_sink / metrics_sink |
| `src/prompt2langgraph/prompting/planner.py` | `build_model_client()` 委托给 `llm.provider.build_llm_client()` |
| `src/prompt2langgraph/prompting/config.py` | `PromptPlannerConfig` 标记 deprecated，委托给 `LLMConfig` |
| `src/prompt2langgraph/prompting/__init__.py` | 导出调整，标记 `PromptPlannerConfig` 为 deprecated |
| `src/prompt2langgraph/__init__.py` | 暴露第二期新增 public API（如有） |
| `README.md` / `CLAUDE.md` / `AGENTS.md` | 同步更新 |

### 2.3 复用现有文件（需确认兼容）

| 文件 | 关注点 |
|------|--------|
| `src/prompt2langgraph/ir/normalize.py` | 新增 policy 字段需纳入规范化 |
| `src/prompt2langgraph/ir/lockfile.py` | 新增 policy 字段需纳入 hash 计算 |
| `src/prompt2langgraph/runtime/artifacts.py` | 编译产物需正确序列化新增 policy 字段 |
| `tests/test_compile_flow.py` | 编译产物路径回归 |
| `tests/test_cli.py` | CLI `run` 命令在新增 executor 下的行为回归 |

---

## 三、当前代码库关键接口基线

> 以下为执行者必须了解的当前代码库接口，新增代码必须与此基线兼容。

### 3.1 IR 模型（`ir/models.py`）

- `PolicySpec`：当前仅有 `allow_side_effects: bool = False`、`default_timeout_s: int = 60`
- `SecurityPolicy`：当前仅有 `requires_approval: bool = False`、`idempotency_key: str | None = None`
- `NodeSpec`：已有 `timeout_s: int | None = None`、`security: SecurityPolicy | None = None`
- `ExecutorType`：已有 `LLM = "llm"`、`PYTHON_CALLABLE = "python_callable"` 枚举值

### 3.2 Executor Registry（`registry/executors.py`）

- `ExecutorDefinition`：当前字段 `ref, type, input_schema, output_schema, secrets, required_capabilities, handler`；无 `dynamic` 字段
- `ExecutorRegistry`：`register()`、`get()`、`has()`、`refs()`
- `ExecutorHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]`

### 3.3 诊断码（`diagnostics/codes.py`）

- 当前最大码 `E_REDUCER_012`；新增从 `E_LLM_001` 和 `E_SEC_013` 起编

### 3.4 编译器（`compiler/langgraph_py.py`）

- `compile_workflow_to_graph(workflow, executors, *, event_sink=None, checkpointer=None)`
- `_node_wrapper(node, executors, event_sink, loop_edges, reducers, fanout_result_keys)`
- 当前 `invoke_node()` 直接调用 `executor.invoke(inputs, node.params)`

### 3.5 验证器（`validate/validator.py`）

- `validate_workflow(workflow, *, nodes=None, executors=None) -> ValidationReport`
- `_check_registries()` 中 `handler=None` 的 executor 会通过校验（`invoke()` 返回 `{}`）

### 3.6 Runner（`runtime/runner.py`）

- `run_workflow(workflow, input_payload, *, executors=None, thread_id=None, resume_payload=..., state_store_dir=None) -> RunResult`

### 3.7 Runtime Events（`runtime/events.py`）

- `RunMetrics`：当前字段 `duration_ms, token_count, retry_count, tool_call_count`
- `RunResult`：当前字段 `status, run_id, thread_id, output, events, diagnostics, interrupt, metrics, tool_calls`

### 3.8 Policy Resolver（`policy/resolver.py`）

- `ResolvedWorkflow`：当前字段 `workflow, node_policies`
- `resolve_policies(workflow, *, nodes=None, compile_options=None) -> ResolvedWorkflow`

### 3.9 Binder（`binding/binder.py`）

- `BoundWorkflow`：当前字段 `workflow, executor_bindings`
- `bind_workflow(workflow, *, executors=None) -> BoundWorkflow`
- 当前 `executor_bindings` 每节点记录 `executor, type, capabilities`

---

## 四、实施任务拆解

### Task 1：扩展诊断码与 IR 模型

**目标：** 为第二期所有新增能力预分配诊断码，扩展 `PolicySpec` 和 `SecurityPolicy` 模型字段，为 `ExecutorDefinition` 增加 `dynamic` 字段。

**Files:**
- Modify: `src/prompt2langgraph/diagnostics/codes.py`
- Modify: `src/prompt2langgraph/ir/models.py`
- Modify: `src/prompt2langgraph/registry/executors.py`
- Test: `tests/test_ir_schema.py`

**接口契约：**

`PolicySpec` 新增字段（追加到现有 `allow_side_effects` 和 `default_timeout_s` 之后）：
- `external_call: bool = False` — 是否允许外部调用
- `allowed_models: list[str] = Field(default_factory=list)` — 允许的模型 ID 白名单
- `collect_metrics: bool = False` — 是否收集运行时调用记录
- `allowed_tool_refs: list[str] = Field(default_factory=list)` — 允许的 tool ref 白名单

`SecurityPolicy` 新增字段：
- `allowed_tool_refs: list[str] | None = None` — 节点级 tool ref 白名单（None 表示继承全局）

`ExecutorDefinition` 新增字段：
- `dynamic: bool = False` — 标记为动态 executor（handler=None 合法，运行时注入）

新增诊断码：
- `E_LLM_001` — LLM 调用超时
- `E_LLM_002` — LLM API 错误
- `E_LLM_003` — LLM 非法消息格式
- `E_SEC_013` — external_call 未启用但有 LLM executor 节点
- `E_SEC_014` — 模型不在 allowed_models 白名单
- `E_SEC_015` — tool ref 未授权或未注册

**测试场景：**
- `PolicySpec()` 默认值：`external_call=False`、`allowed_models=[]`、`collect_metrics=False`、`allowed_tool_refs=[]`
- `SecurityPolicy()` 默认值：`allowed_tool_refs=None`
- `ExecutorDefinition(ref="test", type=ExecutorType.BUILTIN)` 默认 `dynamic=False`
- 旧 workflow JSON（缺少新增 policy 字段）经 `WorkflowSpec.model_validate()` 后，Pydantic 默认值补齐

- [ ] **Step 1:** 写失败测试，确认新增字段不存在
- [ ] **Step 2:** 扩展 `diagnostics/codes.py` 新增 6 个诊断码
- [ ] **Step 3:** 扩展 `PolicySpec`、`SecurityPolicy` 新增字段
- [ ] **Step 4:** 扩展 `ExecutorDefinition` 新增 `dynamic` 字段
- [ ] **Step 5:** 运行测试确认通过
- [ ] **Step 6:** 运行 `uv run pytest` 确认无回归
- [ ] **Step 7:** 提交

---

### Task 2：创建 LLM Provider 轻量抽象模块（`llm/` 包）

**目标：** 新增顶层 `llm/` 包，包含 `LLMConfig`、`build_llm_client()` 和消息转换工具，统一 `ChatOpenAI` 的构造入口。

**Files:**
- Create: `src/prompt2langgraph/llm/__init__.py`
- Create: `src/prompt2langgraph/llm/config.py`
- Create: `src/prompt2langgraph/llm/provider.py`
- Create: `src/prompt2langgraph/llm/messages.py`
- Test: `tests/test_llm_provider.py`

**接口契约：**

`LLMConfig(BaseModel)`：
- `model: str = "qwen-plus"`、`base_url: str | None = None`、`api_key: SecretStr | None = None`
- `temperature: float = 0.0`（0.0~2.0）、`max_tokens: int | None = None`、`request_timeout_s: int = 60`
- **安全约束**：`repr()` 不泄露 api_key 明文

`load_llm_config() -> LLMConfig`：
- 从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`（与第一期 `prompting/config.py` 环境变量名一致）
- `API_KEY` 包装为 `SecretStr`

`build_llm_client(model=None, base_url=None, api_key=None, temperature=None, max_tokens=None, timeout_s=None) -> BaseChatModel`：
- 先 `load_llm_config()` 获取默认值，显式参数覆盖默认值
- 返回 `ChatOpenAI` 实例
- **安全约束**：不在返回值中序列化凭证；不在 bundle/lockfile 中写入

`dict_messages_to_langchain(messages: list[dict]) -> list[BaseMessage]`：
- 支持 `role`：`system` -> `SystemMessage`、`user` -> `HumanMessage`、`assistant` -> `AIMessage`、`tool` -> `ToolMessage`
- `tool` 角色要求 `tool_call_id` 字段，缺失抛 `ValueError`
- 未知 role 抛 `ValueError`
- `content` 必须为 `str`

**测试场景：**
- `LLMConfig()` 默认值正确
- `api_key` 为 `SecretStr`，`repr()` 不含明文
- `load_llm_config()` 从环境变量读取
- `load_llm_config()` 环境变量缺失时使用默认值
- `build_llm_client()` 返回 `ChatOpenAI` 实例，参数正确
- 显式参数覆盖环境变量默认值
- 消息转换：user / system / assistant / tool 各角色
- tool 角色缺失 `tool_call_id` 抛异常
- 未知 role 抛异常

- [ ] **Step 1:** 写失败测试
- [ ] **Step 2:** 实现 `llm/config.py`
- [ ] **Step 3:** 实现 `llm/messages.py`
- [ ] **Step 4:** 实现 `llm/provider.py`
- [ ] **Step 5:** 实现 `llm/__init__.py`
- [ ] **Step 6:** 运行测试确认通过
- [ ] **Step 7:** 提交

---

### Task 3：重构 `prompting/planner.py` 委托给 `llm/` 模块

**目标：** 将 `prompting/planner.py` 中的 `build_model_client()` 委托给 `llm.provider.build_llm_client()`，标记 `PromptPlannerConfig` 为 deprecated，保持第一期 Prompt 计划生成行为完全兼容。

**Files:**
- Modify: `src/prompt2langgraph/prompting/planner.py`
- Modify: `src/prompt2langgraph/prompting/config.py`
- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Test: `tests/test_prompt_planner.py`

**接口契约：**

`prompting/config.py` 变更：
- `PromptPlannerConfig` 标记 deprecated（docstring + `warnings.warn(DeprecationWarning)`）
- `load_prompt_planner_config()` 内部委托给 `load_llm_config()`，转换字段

`prompting/planner.py` 变更：
- `build_model_client(request)` 内部委托给 `llm.provider.build_llm_client(model=..., base_url=..., api_key=..., temperature=...)`
- `generate_plan_text()` 和 `plan_prompt_to_workflow_spec()` 签名和行为不变

**测试场景：**
- `build_model_client()` 委托后返回正确的 client
- `generate_plan_text()` 使用 fake model 仍正常工作
- 现有 `tests/test_prompt_planner.py` 全部通过

- [ ] **Step 1:** 写重构回归测试
- [ ] **Step 2:** 确认现有测试通过
- [ ] **Step 3:** 修改 `prompting/config.py` 标记 deprecated
- [ ] **Step 4:** 修改 `prompting/planner.py` 委托 `build_llm_client()`
- [ ] **Step 5:** 运行 `tests/test_prompt_planner.py` 确认通过
- [ ] **Step 6:** 运行 `tests/test_prompt_planner.py`、`tests/test_prompt_parser.py`、`tests/test_public_api.py`、`tests/test_cli.py` 确认无回归
- [ ] **Step 7:** 提交

---

### Task 4：实现真实 LLM Executor

**目标：** 新增 `LLMExecutor` 类，使 `llm` 类型节点在运行时可以调用外部模型。通过 `ExecutorType.LLM` 分发，`ref="llm.qwen-plus"` 为真实 executor。

**Files:**
- Create: `src/prompt2langgraph/registry/llm_executor.py`
- Modify: `src/prompt2langgraph/registry/executors.py`（新增 `ExecutorError`）
- Modify: `src/prompt2langgraph/registry/builtins.py`（注册 `llm.qwen-plus`）
- Test: `tests/test_llm_executor.py`

**接口契约：**

`ExecutorError(RuntimeError)` — 新增异常类（在 `registry/executors.py`）：
- `__init__(code: str, message: str, *, hint: str | None = None, node_id: str | None = None)`
- `to_diagnostic() -> Diagnostic` — 转为结构化诊断
- 用于 LLM/Tool executor 的统一错误包装

`LLMExecutor`：
- `__init__(model_client: BaseChatModel)` — 依赖注入，不自行创建 client
- `__call__(inputs: dict, params: dict) -> dict` — 返回 `{"answer": str}`
- 输入格式：`inputs["messages"]` 为 `list[dict]`（经 `dict_messages_to_langchain` 转换），或 `inputs["question"]` 为 `str`（自动包装为 `HumanMessage`）
- `params["system_prompt"]` 支持（前置 `SystemMessage`）
- 异常映射：`TimeoutError` -> `E_LLM_001`，其他异常 -> `E_LLM_002`，消息格式错误 -> `E_LLM_003`
- `response.content` 为 `list` 时拼接为 `str`

`registry/builtins.py` 变更：
- 在 `builtin_executor_registry()` 返回列表中追加 `llm.qwen-plus` 的 schema-only definition：
  - `ref="llm.qwen-plus"`、`type=ExecutorType.LLM`、`dynamic=True`、`handler=None`
  - `input_schema={"question": STRING}`、`output_schema={"answer": STRING}`

**测试场景：**
- 正常调用返回 `{"answer": "..."}`
- `question` 自动包装为 `HumanMessage`
- `messages` 缺失且无 `question` 抛 `E_LLM_003`
- `system_prompt` 前置 `SystemMessage`
- 超时抛 `E_LLM_001`
- API 错误抛 `E_LLM_002`
- 非法 role 抛 `E_LLM_003`
- 认证错误包装为 `E_LLM_002`

- [ ] **Step 1:** 写失败测试
- [ ] **Step 2:** 在 `registry/executors.py` 新增 `ExecutorError`
- [ ] **Step 3:** 实现 `registry/llm_executor.py`
- [ ] **Step 4:** 在 `registry/builtins.py` 注册 `llm.qwen-plus`
- [ ] **Step 5:** 运行测试确认通过
- [ ] **Step 6:** 提交

---

### Task 5：实现 Tool Executor 最小受控模型

**目标：** 新增 `ToolExecutor` 类和 `ToolCallableRegistry`，使 `tool` 类型节点只能执行预注册、受信任的纯 Python callable。

**Files:**
- Create: `src/prompt2langgraph/registry/tool_executor.py`
- Test: `tests/test_tool_executor.py`

**接口契约：**

`ToolCallableRegistry`：
- `register(ref: str, callable: ExecutorHandler)` — 注册受信任 callable
- `get(ref: str) -> ExecutorHandler` — 未注册抛 `KeyError`
- `has(ref: str) -> bool`
- `refs() -> list[str]` — 返回已注册 ref 排序列表
- **安全约束**：不是沙箱，不做 subprocess 隔离、Docker 或网络控制

`ToolExecutor`：
- `__init__(registry: ToolCallableRegistry, tool_ref: str, *, timeout_s: int = 60)`
- `__call__(inputs: dict, params: dict) -> dict`
- ref 未注册抛 `ExecutorError(E_SEC_015)`
- 使用 `ThreadPoolExecutor(max_workers=1)` 执行，超时抛 `ExecutorError(E_SEC_015)`
- callable 异常包装为 `ExecutorError(E_SEC_015)`

**测试场景：**
- 调用已注册 tool 返回正确结果
- 未注册 ref 抛 `E_SEC_015`
- callable 异常传播为 `ExecutorError`
- `ToolCallableRegistry.has()` / `get()` / `refs()` 行为

- [ ] **Step 1:** 写失败测试
- [ ] **Step 2:** 实现 `registry/tool_executor.py`
- [ ] **Step 3:** 运行测试确认通过
- [ ] **Step 4:** 提交

---

### Task 6：实现策略校验层

**目标：** 在 `validate/security.py` 中新增三个校验函数，在 `validate/validator.py` 中组合调用。

**Files:**
- Modify: `src/prompt2langgraph/validate/security.py`
- Modify: `src/prompt2langgraph/validate/validator.py`
- Test: `tests/test_security_policy.py`

**接口契约：**

`check_external_policy(workflow: WorkflowSpec) -> list[Diagnostic]`：
- 检查：存在 `ExecutorType.LLM` 节点但 `policies.external_call=False` 时，报 `E_SEC_013`
- `ExecutorType.BUILTIN` 的 `llm` 节点不受此约束

`check_model_whitelist(workflow: WorkflowSpec) -> list[Diagnostic]`：
- 检查：`ExecutorType.LLM` 节点的 ref 格式为 `llm.<model_id>`，`model_id` 不在 `allowed_models` 时报 `E_SEC_014`
- ref 不以 `llm.` 开头的跳过

`check_tool_refs(workflow: WorkflowSpec, tool_registry: ToolCallableRegistry) -> list[Diagnostic]`：
- 检查对象：仅 `ExecutorType.PYTHON_CALLABLE` 节点（`LANGCHAIN_TOOL` 跳过）
- 检查 1：ref 不在 `allowed_tool_refs`（全局或节点级）时报 `E_SEC_015`
  - 节点级 `node.security.allowed_tool_refs` 优先，`None` 时继承全局 `policies.allowed_tool_refs`
  - 空列表 `[]` 按默认安全原则报 `E_SEC_015`
- 检查 2：ref 未在 `ToolCallableRegistry` 注册时报 `E_SEC_015`

`validate/validator.py` 变更：
- `validate_workflow()` 签名新增 `tool_registry: ToolCallableRegistry | None = None`
- 在 `check_security()` 调用后追加三个新校验调用
- `_check_registries()` 中：`dynamic=True` 且 `handler=None` 的 executor 放行；`dynamic=False` 且 `handler=None` 报 `E_BIND_006`

**测试场景：**
- LLM 节点 + `external_call=False` -> 报 `E_SEC_013`
- LLM 节点 + `external_call=True` -> 通过
- Builtin LLM 节点 + `external_call=False` -> 通过
- LLM 节点 + `allowed_models=[]` -> 报 `E_SEC_014`
- LLM 节点 + `allowed_models=["qwen-plus"]` -> 通过
- Tool 节点 + 未注册 ref -> 报 `E_SEC_015`
- Tool 节点 + 已注册 + 在白名单 -> 通过
- Tool 节点 + 已注册 + 空白名单 -> 报 `E_SEC_015`
- `LANGCHAIN_TOOL` 节点不受 `check_tool_refs()` 检查

- [ ] **Step 1:** 写失败测试
- [ ] **Step 2:** 扩展 `validate/security.py` 新增三个函数
- [ ] **Step 3:** 更新 `validate/validator.py` 组合调用 + 签名扩展
- [ ] **Step 4:** 运行 `tests/test_security_policy.py` 确认通过
- [ ] **Step 5:** 运行 `tests/test_validator.py` 确认无回归
- [ ] **Step 6:** 提交

---

### Task 7：扩展编译器以支持动态 Executor Dispatch

**目标：** 修改 `compiler/langgraph_py.py`，使 `_node_wrapper()` 和 `compile_workflow_to_graph()` 支持 `ExecutorType.LLM` / `PYTHON_CALLABLE` 的动态 dispatch。

**Files:**
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Test: `tests/test_langgraph_compiler.py`

**接口契约：**

`compile_workflow_to_graph()` 签名扩展（追加可选参数）：
- `policies: PolicySpec | None = None` — 默认取 `workflow.policies`
- `model_client: Any | None = None` — LLM executor 的 BaseChatModel 注入
- `tool_registry: ToolCallableRegistry | None = None` — Tool executor 的 callable 注册表
- `error_sink: Callable[[ExecutorError], None] | None = None` — 执行异常回调
- `metrics_sink: Callable[[ExternalCallRecord], None] | None = None` — 成功调用记录回调

`_node_wrapper()` 签名扩展（追加同名可选参数）：

新增内部函数 `_invoke_executor(node, executor, inputs, *, policies, model_client, tool_registry, metrics_sink) -> dict`：
- `executor.dynamic=True` 且 `type=ExecutorType.LLM`：
  - `model_client=None` 时抛 `ExecutorError(E_SEC_013)`
  - 实例化 `LLMExecutor(model_client=model_client)` 并调用
  - `collect_metrics=True` 且 `metrics_sink` 存在时，记录成功 `ExternalCallRecord`
- `executor.dynamic=True` 且 `type=ExecutorType.PYTHON_CALLABLE`：
  - `tool_registry=None` 时抛 `ExecutorError(E_SEC_015)`
  - 超时取 `node.timeout_s or policies.default_timeout_s`
  - 实例化 `ToolExecutor(registry, tool_ref, timeout_s=...)` 并调用
  - 同上 metrics 记录
- 其他（BUILTIN 等）：走现有 `executor.invoke(inputs, params)` 路径

`invoke_node()` 内部变更：
- 调用 `_invoke_executor()` 替代直接 `executor.invoke()`
- `ExecutorError` 捕获后设 `exc.node_id`，传给 `error_sink`，再 re-raise

> **预留路径**：当前不实现自动重试。后续可映射 `NodeSpec.retry.max_attempts` 到 LangGraph `RetryPolicy`。需注意 `ExecutorError(RuntimeError)` 默认被 `default_retry_on` 排除，启用重试时需自定义 `retry_on` 回调。

**测试场景：**
- 编译包含 `ExecutorType.LLM` 节点的 workflow，使用 fake model 执行，返回正确结果
- `model_client=None` 时抛 `ExecutorError`
- BUILTIN 节点与 LLM 节点混合执行

- [ ] **Step 1:** 写失败测试
- [ ] **Step 2:** 扩展 `compile_workflow_to_graph()` 签名
- [ ] **Step 3:** 扩展 `_node_wrapper()` 签名
- [ ] **Step 4:** 实现 `_invoke_executor()` 动态 dispatch
- [ ] **Step 5:** 运行测试确认通过
- [ ] **Step 6:** 运行现有编译器测试确认无回归
- [ ] **Step 7:** 提交

---

### Task 8：扩展 Runtime Events 与 Runner

**目标：** 扩展 `RunMetrics`、新增 `ExternalCallRecord`，修改 `run_workflow()` 对接 error_sink / metrics_sink 和 `external_calls` 汇总。

**Files:**
- Modify: `src/prompt2langgraph/runtime/events.py`
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `src/prompt2langgraph/cli.py`
- Test: `tests/test_runner.py`

**接口契约：**

`runtime/events.py` 变更：
- `RunMetrics` 新增：`call_count: int = 0`、`total_latency_ms: float | None = None`
- 新增 `ExternalCallRecord(BaseModel)`：`node_id: str`、`executor_ref: str`、`model: str | None = None`、`latency_ms: float | None = None`、`token_count: int | None = None`、`status: Literal["succeeded", "failed"]`、`error_code: str | None = None`
- `RunResult` 新增：`external_calls: list[ExternalCallRecord] = Field(default_factory=list)`

`runtime/runner.py` 变更：
- `run_workflow()` 签名新增：`model_client: Any | None = None`、`tool_registry: Any | None = None`
- 内部构造 `error_sink` 和 `metrics_sink` 闭包，收集到 `external_calls: list[ExternalCallRecord]`
- `compile_workflow_to_graph()` 调用处传入 `policies`、`model_client`、`tool_registry`、`error_sink`、`metrics_sink`
- `RunResult` 构造时传入 `external_calls`

`cli.py` 变更：
- `run` 命令中，检测 workflow 是否含 `ExecutorType.LLM` / `PYTHON_CALLABLE` 节点
- 含 LLM 节点且 `external_call=True` 时，调用 `build_llm_client()` 构造 `model_client`
- 含 Tool 节点时，构造 `ToolCallableRegistry()`（内置 tool 可在此注册）
- 传入 `run_workflow()`
- **约束**：不在模块导入阶段急切导入 `langchain_openai` 或初始化 client

**测试场景：**
- `RunMetrics` 新增字段默认值正确
- `ExternalCallRecord` 字段正确
- `RunResult.external_calls` 默认为 `[]`
- 成功调用记录 `status="succeeded"`
- 失败调用记录 `status="failed"`

- [ ] **Step 1:** 写失败测试
- [ ] **Step 2:** 扩展 `runtime/events.py`
- [ ] **Step 3:** 修改 `runtime/runner.py`
- [ ] **Step 4:** 修改 `cli.py` 传递 `model_client` / `tool_registry`
- [ ] **Step 5:** 运行测试确认通过
- [ ] **Step 6:** 提交

---

### Task 9：补齐集成测试

**目标：** 以 fake provider 和 fake tool 覆盖 LLM executor + tool executor 的完整链路测试。

**Files:**
- Create: `tests/fake_provider.py`
- Create: `tests/fake_tools.py`
- Create: `tests/test_integration_execution.py`

**接口契约：**

`tests/fake_provider.py`：
- `fake_chat_model(response_text: str = "fake response") -> BaseChatModel`
- 使用 `GenericFakeChatModel(messages=iter([response_text]))`

`tests/fake_tools.py`：
- `fake_tool_echo(inputs, params) -> {"output": inputs.get("input", "")}`
- `fake_tool_upper(inputs, params) -> {"output": str(inputs.get("input", "")).upper()}`
- `fake_tool_fail(inputs, params) -> raises RuntimeError`
- `FAKE_TOOLS: dict[str, Callable]`

**测试场景：**
- LLM 节点 + fake provider 完整图执行
- BUILTIN 节点 + LLM 节点混合执行
- Tool 节点 + fake tool registry 完整图执行

- [ ] **Step 1:** 创建 `tests/fake_provider.py`
- [ ] **Step 2:** 创建 `tests/fake_tools.py`
- [ ] **Step 3:** 写集成测试
- [ ] **Step 4:** 运行测试确认通过
- [ ] **Step 5:** 提交

---

### Task 10：更新 Policy Resolver 与 Binding Binder

**目标：** 将新增策略字段纳入 `resolve_policies()`、`bind_workflow()` 和 `normalize_workflow()` 的输出，确保 `workflow.ir.json` / `workflow.lock.json` 正确序列化。

**Files:**
- Modify: `src/prompt2langgraph/policy/resolver.py`
- Modify: `src/prompt2langgraph/binding/binder.py`
- Modify: `src/prompt2langgraph/ir/normalize.py`
- Test: `tests/test_compile_flow.py`

**接口契约：**

`policy/resolver.py` 变更：
- `ResolvedWorkflow` 新增：`external_call: bool = False`、`allowed_models: list[str]`、`collect_metrics: bool = False`、`allowed_tool_refs: list[str]`
- `resolve_policies()` 从 `workflow.policies` 提取新增字段

`binding/binder.py` 变更：
- `executor_bindings` 每节点新增：`dynamic: bool`、`allowed_models: list[str]`、`external_call: bool`

`ir/normalize.py` 变更：
- 确认 `PolicySpec` 新增字段经 `normalize_workflow()` 后正确序列化到 `workflow.ir.json`
- 旧 workflow JSON（缺少新增字段）经规范化后包含 Pydantic 默认值补齐

**验证命令：**
```bash
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
# 检查 build/linear_llm/workflow.ir.json 中是否包含 external_call、allowed_models 等字段
```

- [ ] **Step 1:** 修改 `policy/resolver.py`
- [ ] **Step 2:** 修改 `binding/binder.py`
- [ ] **Step 3:** 确认 `ir/normalize.py` 正确序列化新增字段
- [ ] **Step 4:** 运行 `tests/test_compile_flow.py` 确认无回归
- [ ] **Step 5:** 提交

---

### Task 11：更新文档与全量回归

**目标：** 更新 `README.md`、`CLAUDE.md`、`AGENTS.md`，确保文档与第二期能力一致。执行全量回归测试。

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

**文档更新要点：**
- `llm` 节点可通过 `ExecutorType.LLM` 调用真实模型（需 `external_call=True` + `allowed_models`）
- `tool` 节点可通过 `ExecutorType.PYTHON_CALLABLE` 执行受控 callable（需 `allowed_tool_refs` + `ToolCallableRegistry`）
- `llm/` 顶层模块为 LLM 客户端构造共享入口
- `.env` 配置同时服务于 Prompt 计划生成和运行时 LLM 执行
- 区分 `plan` 命令的 LLM（第一期）和运行时 `llm` 节点的 LLM（第二期）
- 新增回归要求：修改 executor dispatch 或策略校验后，需跑 `tests/test_security_policy.py`、`tests/test_integration_execution.py`

- [ ] **Step 1:** 更新 `README.md`
- [ ] **Step 2:** 更新 `CLAUDE.md`
- [ ] **Step 3:** 更新 `AGENTS.md`
- [ ] **Step 4:** 运行 `uv run pytest` 全量回归
- [ ] **Step 5:** 运行 Prompt 相关定向测试
- [ ] **Step 6:** 运行第二期新增测试
- [ ] **Step 7:** 手工 CLI 验收
- [ ] **Step 8:** 提交

---

### Task 12：补齐 Edge Case 与回归确认

**目标：** 确保旧 fixture 加载兼容、lockfile hash 一致、异常路径覆盖。

**Files:**
- Test: `tests/test_compile_flow.py`
- Test: `tests/test_validator.py`
- Test: `tests/test_runner.py`

**测试场景：**
- 旧 workflow JSON（缺少新增 policy 字段）经 `WorkflowSpec.model_validate()` 后，Pydantic 默认值补齐
- lockfile hash 稳定性：同一 `WorkflowSpec` 两次 `sha256_canonical_json(normalize_workflow(wf).model_dump(mode="json"))` 结果一致
- 全量 `uv run pytest` 通过

- [ ] **Step 1:** 写旧 fixture 兼容性测试
- [ ] **Step 2:** 写 lockfile hash 一致性测试
- [ ] **Step 3:** 运行 `uv run pytest` 全量回归
- [ ] **Step 4:** 提交

---

## 五、执行顺序与依赖

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

可并行的任务组：
- Task 1 与 Task 2 无依赖，可并行
- Task 4 与 Task 5 可并行
- Task 4/5 与 Task 6 可并行

---

## 六、关键注意事项

1. 不在 bundle/lockfile 中写入真实 secret 或 secret 名称；
2. `builtin.echo_llm` 保留为 mock/fallback，行为和注册路径不变；
3. `ExecutorType.LLM` 的 ref 格式约定为 `llm.<model_id>`，`model_id` 必须在 `allowed_models` 白名单中；
4. `security.py` 新增的函数必须独立可测试，不在函数内部导入 `ToolCallableRegistry` 的默认实例（由调用方注入）；
5. 动态 executor 必须在 `ExecutorRegistry` 中注册 schema-only definition（`dynamic=True, handler=None`），验证阶段保留 ref/type/schema 校验；
6. `_check_registries()` 中允许 `definition.dynamic=True` 且 `handler is None` 的 executor 通过校验；`definition.dynamic=False` 且 `handler=None` 应报 `E_BIND_006` 诊断；
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

## 七、完成判定

当以下条件全部满足时，可判定 v0.2 第二期实施完成：

- 顶层 `llm/` 轻量基础模块已就绪，`prompting/planner.py` 的 `build_model_client()` 已委托给 `llm.provider.build_llm_client()`；
- `llm` 节点可通过 `ExecutorType.LLM`（ref 格式 `llm.<model_id>`）调用真实模型，fake provider 下可验证完整调用链路；
- `tool` 节点可通过 `ExecutorType.PYTHON_CALLABLE` 执行受信任、预注册且经 `allowed_tool_refs` 授权的纯 Python callable；
- 真实 executor 和 mock executor 可通过 executor ref 区分（`ref="builtin.echo_llm"` = mock，`ref="llm.qwen-plus"` = real），mock 行为完全兼容；
- 策略约束在 `validate_workflow()` 阶段即被检查：`external_call` 开关、`allowed_models` 白名单、`allowed_tool_refs` 白名单；
- `collect_metrics=True` 时，`RunResult.external_calls` 中可获取成功和失败调用的 `ExternalCallRecord`；
- CLI `run` 命令能根据 workflow 节点类型自动构造 `model_client` 和 `tool_registry`；
- `tests/test_llm_provider.py`、`tests/test_llm_executor.py`、`tests/test_tool_executor.py`、`tests/test_security_policy.py`、`tests/test_integration_execution.py` 全部通过；
- 现有第一期测试基线全部通过；
- `README.md`、`CLAUDE.md`、`AGENTS.md` 已同步更新；
- `uv run pytest` 全量通过；
- 未越界实现多 provider 适配、subprocess 沙箱、`join` edge 执行、`side_effect` 闭环等非目标能力。

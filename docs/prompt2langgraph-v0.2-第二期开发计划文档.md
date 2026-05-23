# prompt2langgraph v0.2 第二期开发计划文档

## 1. 文档目的

本文档用于定义 `prompt2langgraph` v0.2 第二期的工程实施设计，作为后续详细实施计划、代码改动与测试回归的直接依据。

本文档聚焦 **目标、范围、模块任务与验收标准**，采用"严格二期范围 + 模块级任务拆解"的方式组织内容，不展开到文件级或接口级实施步骤。

---

## 2. 阶段定位

v0.2 采用《三期任务划分方案A》中"目标链路优先"的推进策略。第二期对应其中的 **真实执行能力补齐（Real Execution）**，核心目标是在 v0.2 第一期已实现的 `Prompt → LLM → 简化 JSON plan → WorkflowSpec` 输入桥接基础之上，补齐让 Workflow 能够真实执行的关键运行时能力。

第二期不是"输入层建设"阶段，而是**运行时执行能力的受控开放阶段**。其重点在于：让 `llm` 节点能够调用真实模型（而非仅返回 mock 响应），让 `tool` 节点能够执行安全的 Python callable，并通过策略层确保这些能力以受控、可审计、可配置的方式上线。

第一期已经开启了**显式、受控、仅用于计划生成**的外部 LLM 调用边界。第二期在此基础上，将外部调用边界从"计划生成"扩展至"运行时节点执行"，同时引入与之匹配的安全策略约束。

---

## 3. 阶段目标

v0.2 第二期的阶段目标是：

- 新增顶层 `llm/` 轻量基础模块，复用 `langchain_openai`，统一 Prompt planning、后续 Skills planning 与 runtime LLM executor 的模型客户端构造入口，优先兼容 Qwen 系列模型和 vLLM 部署暴露的 OpenAI-style API；
- 实现真实 LLM Executor，使 `llm` 类型节点在运行时可以调用外部模型，同时保留 `builtin.echo_llm` 作为 mock/fallback；
- 实现 Tool Executor 最小受控模型，使 `tool` 类型节点只能执行预注册、受信任的纯 Python callable；不执行 workflow JSON 中动态声明的 import path，也不承诺不可信代码沙箱能力；
- 增强策略与安全约束体系，为外部调用提供显式开关、模型白名单、运行时调用记录和工具能力白名单机制；
- 补齐集成测试策略，以 fake provider 和预注册 fake tool 覆盖新增能力的完整链路；
- 在整个过程中保持现有 mock executor 的不变兼容，不破坏第一期已交付的输入链路。

一句话概括：**第二期是在第一期输入桥接闭环之外，让 Workflow 的运行时 `llm` 和 `tool` 节点具备受控的真实执行能力。**

---

## 4. 纳入范围

第二期纳入以下范围：

1. 新增顶层 `llm/` 轻量基础模块，统一 `langchain_openai.ChatOpenAI` 的构造入口；
2. 新增真实 LLM Executor，使 `llm` 节点可调用外部模型（Qwen / vLLM 等 OpenAI-style 兼容 API）；
3. 新增 Tool Executor 最小受控模型，使 `tool` 节点可执行预注册、受信任的纯 Python callable；
4. 增强策略与安全约束，包括 `external_call` 开关、必填 `allowed_models` 模型白名单、`collect_metrics` 运行时调用记录、工具 callable 白名单；
5. 在验证层和运行层强制检查新增策略约束；
6. 补齐集成测试，以 fake provider 和预注册 fake tool 覆盖新增 executor 和策略约束的完整链路；
7. 同步更新文档，至少包括 `README.md`、`CLAUDE.md`、`AGENTS.md`，确保对外能力说明与仓库实际行为一致。

---

## 5. 明确排除范围

第二期不纳入以下内容：

- 不实现多 provider 适配器模式（不引入 `provider/` 包，不做 model discovery，不做 provider 热切换）；
- 不实现 subprocess 沙箱、Docker 隔离或网络访问控制（系统级隔离留给外部部署环境）；
- 不实现 `join` edge 执行能力；
- 不实现 `skill_dir` 到 `WorkflowSpec` 的可执行转换；
- 不补 `side_effect` 节点的最小执行闭环（保留现有占位行为）；
- 不扩展 Prompt 计划生成阶段的 LLM 能力（第一期行为不变）；
- 不实现 LLM 输出质量评估或多轮规划/反思/自动修复机制；
- 不在 bundle/lockfile 中写入真实 secret 或 secret 名称；
- 不改变第一期已交付的 `validate / compile / graph / plan / resume` 命令行为兼容性；
- 不改变现有 mock executor 的行为和注册路径。

---

## 6. 设计原则

第二期设计应遵守以下原则：

### 6.1 目标链路优先

实现顺序以"让一个 `llm` 节点能真实调用模型并返回结果"为目标链路，优先打通从 executor 构造到模型调用的最小闭环，再逐步完善抽象和策略保障。

> **设计依据**：LangGraph 的核心理念是"先让图跑通，再逐步加固"——通过 `StateGraph` 的 `add_node` → `add_edge` → `compile` 三步渐进构建，每一步都可独立验证。本计划采用同样的增量策略：优先打通 `llm` executor 的最小调用闭环，确保模型调用链路可验证后，再逐步完善策略约束、tool executor 和集成测试。参见 LangGraph Graph API 文档（[Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api)）和 [Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api) 中的增量构建模式。

### 6.2 Provider 轻量，不透支抽象

LLM Provider 不作为独立 `provider/` 包层抽象，而是作为顶层 `llm/` 轻量基础模块提供客户端构造、配置加载与消息格式适配。`prompting/`、后续 Skills planning 和 runtime `LLMExecutor` 都依赖 `llm/`，避免让通用 LLM 能力归属于某一个输入来源。采用 `langchain_openai.ChatOpenAI` 作为统一客户端，不引入多 provider 路由。Provider 抽象以够用为度，不超前设计。

> **设计依据**：LangChain v1 将 `BaseChatModel` 作为所有聊天模型的统一抽象接口，`ChatOpenAI` 是其 OpenAI 兼容实现。LangChain 生态通过 `langchain-<provider>` 包支持 1000+ 集成，但统一接口意味着调用方只需依赖 `BaseChatModel`，无需感知底层 provider 差异。本计划遵循同样的"统一接口 + 单一实现"原则：返回值类型声明为 `BaseChatModel` 以保证可替换性（测试时可注入 fake 实现），实际构造使用 `ChatOpenAI` 以兼容 Qwen/vLLM 等 OpenAI-style API。参见 LangChain 的 [Chat model integrations](https://docs.langchain.com/oss/python/integrations/chat/index) 和 [Providers overview](https://docs.langchain.com/oss/python/integrations/providers/overview)。

### 6.3 Executor 可切换，Mock 保留

真实 executor 和 mock executor 通过 executor ref 区分（`ref="builtin.echo_llm"` 为 mock，`ref="llm.qwen-plus"` 为真实），不在 node kind 层面区分。现有 mock executor 行为保持不变，测试和干运行仍可使用。

> **设计依据**：LangChain v1 的 `create_agent()` 中，`model` 参数接受任意 `BaseChatModel` 实例——测试时可注入 fake model，生产环境注入真实 `ChatOpenAI`，agent 本身不区分 mock/real。本计划采用同样的依赖注入模式：`LLMExecutor` 的 `model_client` 参数类型为 `BaseChatModel`，测试注入 fake，生产注入真实。此外 LangGraph 的节点函数签名固定为 `(state) -> update`，不与具体 executor 类型耦合，天然支持 mock/real 切换。参见 LangChain [Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing) 中的 fake model 模式。

### 6.4 策略先行于执行

任何真实外部调用都必须先经过策略层显式允许。Workflow 默认不开启外部调用，由用户在 WorkflowSpec 或 CLI/API 参数中明确启用。策略约束在验证阶段即被检查，不在运行时才拦截。

> **设计依据**：LangChain v1 的 middleware 体系提供了在模型调用和工具调用两个关键节点插入策略检查的 hook 机制——`wrap_model_call` 和 `wrap_tool_call`。内置 middleware（如 `HumanInTheLoopMiddleware`）在工具调用执行前即完成审批检查，而非等调用发生后再拒绝。本计划的"策略先行于执行"原则与此一致：`external_call` 开关和模型白名单在 `validate_workflow()` 验证阶段即被检查，运行时只做防御性二次校验，确保策略违反在早期阶段被拦截。参见 LangChain 的 [Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) 和 [Middleware hooks](https://docs.langchain.com/oss/python/releases/langchain-v1#custom-middleware)。

### 6.5 安全白名单而非黑名单

LLM 模型调用采用必填模型白名单：只要 `external_call=True`，就必须显式列出可调用模型，不提供"任意模型默认放行"。Tool Executor 采用预注册 callable 白名单和能力声明机制，只执行本进程中已注册、受信任的纯 Python callable；该机制不是不可信代码沙箱，不承诺阻断所有 Python 逃逸、反射或资源耗尽行为。

> **设计依据**：LangChain v1 的 `HumanInTheLoopMiddleware` 采用 `allowed_tools` 白名单模式——只有显式列出的工具才触发人工审批，未列出的工具默认放行或拒绝。本计划将此白名单思路扩展到模型和工具两个维度：`allowed_models` 控制可调用的 LLM 模型，`allowed_tool_refs` 控制可执行的 tool callable，不提供"任意放行"的默认语义。LangChain 的 `BaseTool` 接口要求 tool 名称为必填字段且通过 `@tool` 装饰器或继承方式显式注册，本计划的 `ToolCallableRegistry` 遵循同样的"先注册、后使用"原则。参见 LangChain 的 [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) 和 [Tools](https://docs.langchain.com/oss/python/migrate/langchain-v1#tools) 文档。

### 6.6 可测试性内建

所有新增 executor 和策略约束必须在设计时就考虑可测试性。LLM Executor 必须可以通过 fake provider 独立测试，不依赖真实网络调用。策略约束的验证逻辑必须可以独立于运行时执行测试。

> **设计依据**：LangChain v1 提供 `langchain_core.language_models.fake.FakeListChatModel` 作为内置 fake chat model，继承 `BaseChatModel`，可预设固定响应序列，用于单元测试中替代真实模型调用。此外 LangChain 推荐 fake+integration 双层测试策略：fake 覆盖确定性逻辑，integration 覆盖真实 API 连通性。本计划遵循同样的分层思路：`tests/fake_provider.py` 提供 fake model（优先使用 `FakeListChatModel`），所有 executor 测试不依赖网络；真实网络调用留给手动验收或 e2e 脚本。参见 LangChain 的 [Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing) 和 [Integration testing](https://docs.langchain.com/oss/python/langchain/test/integration-testing)。

### 6.7 配置来源统一

LLM Provider 的配置统一从 `.env` 文件加载，支持在 API/CLI 层按需覆盖。不在 bundle 或 lockfile 中传递凭据。

> **设计依据**：LangChain 的 `ChatOpenAI` 默认从环境变量 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 等读取配置，同时也接受构造函数参数显式覆盖——这一模式使同一套代码既可直接部署（依赖环境变量），也可在 CLI/API 层传入覆盖值。LangChain 的 `init_chat_model()` 辅助函数遵循同样的"环境变量 + 显式参数覆盖"优先级策略。本计划采用一致模式：`LLMConfig` 从 `.env` 加载默认值，`build_llm_client()` 的显式参数优先覆盖；配置对象不序列化到持久化存储。参见 LangChain 的 [ChatOpenAI integration](https://docs.langchain.com/oss/python/integrations/chat/index) 和 `langchain_openai` 参数优先级文档。

---

## 7. 模块任务

### 7.1 LLM Provider 轻量抽象模块

> **代码库现状基线**：`prompting/config.py` 已定义 `PromptPlannerConfig(model: str | None, base_url: str | None, api_key: str | None)`（`api_key` 为明文 `str`）和 `load_prompt_planner_config()`。`prompting/planner.py` 已定义 `PromptPlanRequest(prompt, model, base_url, api_key, temperature)`（public API，通过 `__init__.py` 导出）和 `build_model_client(request) -> ChatOpenAI`。当前不存在顶层 `llm/` 模块。以下为在现有基础上提取共享 LLM 基础模块。

新增顶层 `llm/` 轻量基础模块，统一 `langchain_openai.ChatOpenAI` 客户端的构造入口，并为 Prompt planning、后续 Skills planning 和 runtime LLM executor 提供共享依赖。

该模块应完成：

- 新增 `llm/provider.py`，封装 `build_llm_client()` 函数：
  - 接收 `model`、`base_url`、`api_key`、`temperature`、`max_tokens`、`timeout_s` 等参数；
  - 统一使用 `langchain_openai.ChatOpenAI`，不做多 provider 路由；
  - 从 `.env` 加载默认值，优先使用调用方传入的显式参数覆盖；
  - 返回值类型声明为 `BaseChatModel`（而非 `ChatOpenAI`），实际返回 `ChatOpenAI` 实例，这样 fake provider 只需实现 `BaseChatModel` 接口即可替换；
  - 在 `build_llm_client()` 的文档字符串中明确警告：不要将此配置对象序列化到持久化存储。
- 新增 `llm/config.py`，定义 `LLMConfig` Pydantic 模型，并提供 `.env` 加载函数（planner 与 runtime 共用同一个配置模型，保持"配置来源统一"原则）：
  - `model: str`（默认 `qwen-plus`）；
  - `base_url: str | None`；
  - `api_key: SecretStr | None`（使用 Pydantic v2 的 `SecretStr`，在 `__repr__` 和序列化时自动脱敏，防止 `api_key` 被明文写入日志或调试输出）；
  - `temperature: float = 0.0`；
  - `max_tokens: int | None`；
  - `request_timeout_s: int = 60`（HTTP 请求超时，网络层；与 `NodeSpec.timeout_s` 应用层执行超时区分）。
- 重构 `prompting/planner.py` 中的 `build_model_client()`：
  - 改为委托 `llm.provider.build_llm_client()`；
  - 保持第一期 Prompt 计划生成行为的完全兼容。
- `PromptPlannerConfig` 废弃，由 `llm.config.LLMConfig` 替代；`build_model_client()` 委托 `build_llm_client()` 后，`PromptPlannerConfig` 可标记为 deprecated。
- 更新 `prompting/config.py`（如需），迁移为兼容 wrapper 或删除内部重复配置逻辑，确保配置加载路径统一。
- 可新增 `llm/messages.py`，封装 OpenAI-style dict messages 到 LangChain message 的转换，供 runtime `LLMExecutor` 复用；Prompt planner 当前可继续直接传 LangChain 支持的 dict/tuple messages，不强制迁移。

设计约束：

- 不引入 `provider/` 独立包路径；
- 不把 LLM Provider 放在 `prompting/` 下，避免后续 Skills planning 和 runtime executor 反向依赖 Prompt planning 层；
- 不做多 provider 发现或路由；
- 不做 provider 热切换；
- `LLMConfig` 仅用于构造 client，不用于序列化到 bundle。
- `PromptPlanRequest` 保持不变（它是 public API 请求模型，通过 `__init__.py` 导出），`LLMConfig` 是内部配置模型。`build_model_client(request)` 内部从 `PromptPlanRequest` 提取参数构造 `LLMConfig`，再委托 `llm.provider.build_llm_client()`。重构后 `generate_plan_text()` 的 `model_client` 参数类型收窄为 `BaseChatModel | None`，与 `LLMExecutor.__init__()` 的 `model_client` 参数类型保持一致。
- `.env` 配置冲突说明：迁移到 `llm.config.LLMConfig` 后，planner 与 runtime 共享同一套配置，通过 `model` 参数区分不同模型；`.env` 缺失时不报错仅使用默认值；实际调用时若缺少 `api_key`，返回明确诊断（如"请在 .env 中配置 API_KEY 和 BASE_URL"）而非让 `ChatOpenAI` 以无认证状态尝试连接。

> **设计依据**：LangChain v1 通过 `langchain.chat_models.init_chat_model()` 提供统一的模型客户端初始化入口，`langchain_openai.ChatOpenAI` 是其 OpenAI 兼容实现。LangChain 生态中，所有 chat model 实现均继承 `BaseChatModel`，调用方通过 `BaseChatModel` 接口消费而非直接依赖具体实现类——这使得测试替换和 provider 迁移无需修改调用方代码。本计划的 `llm/provider.py` 遵循同样模式：`build_llm_client()` 返回类型声明为 `BaseChatModel`，实际返回 `ChatOpenAI` 实例，`LLMExecutor` 和 `PromptPlanner` 均通过 `BaseChatModel` 接口消费。LangChain v1 的 namespaces 设计中（[LangChain v1 namespace](https://docs.langchain.com/oss/python/releases/langchain-v1#namespace)），将 `init_chat_model`、`BaseChatModel` 从 `langchain.chat_models` 统一导出，本计划的 `llm/` 顶层模块遵循同样理念——将 LLM 基础能力从具体使用方（planner/executor）中提取到共享层。

### 7.2 真实 LLM Executor 模块

> **代码库现状基线**：`ir/models.py` 中 `ExecutorType` 枚举已包含 `LLM = "llm"` 值（与 `BUILTIN`、`PYTHON_CALLABLE`、`LANGCHAIN_TOOL`、`HUMAN` 并列），但当前无任何内置 executor 使用此类型。`registry/builtins.py` 中 `echo_llm` 注册为 `ExecutorType.BUILTIN`。以下为在现有 `ExecutorType.LLM` 基础上补齐真实 executor 实现。

在现有 `registry/builtins.py` 的 `echo_llm` 旁新增真实 LLM executor，通过 `ExecutorType.LLM` 分发。

该模块应完成：

- 新增 `registry/llm_executor.py`：
  - `LLMExecutor` 类，`__init__()` 接受可选的 `model_client` 参数（类型为 `BaseChatModel`），支持依赖注入；测试时注入 fake 实例，生产环境从 `build_llm_client()` 创建；
  - `__call__(inputs, params)` 接口，当 `model_client` 未注入时内部调用 `llm.provider.build_llm_client()` 创建 client；
  - 从 `inputs` 提取 `messages`，明确使用 dict 格式（`[{"role": "user", "content": "..."}]`），由 `LLMExecutor` 内部转换为 LangChain `BaseMessage`；输入转换逻辑：当 inputs 包含 `messages` key 时直接使用；当包含 `question` key 时自动包装为 `[{"role": "user", "content": question}]`；两者都不存在时报错；
  - `messages` 仅支持 `role in {"system", "user", "assistant"}` 且 `content` 为字符串；非法结构返回 `E_LLM_003` 诊断；
  - 从 `params` 提取 `system_prompt`、`temperature` 等 override 参数；若同时存在 `system_prompt` 和输入 `messages` 中的 system message，则 `system_prompt` 作为第一条 system message 前置，不修改用户提供的消息内容；
  - 返回 `{"answer": str(response.content)}`（保持与 `echo_llm` 输出 schema 一致；当 `response.content` 为 list 时按 planner 当前逻辑拼接为字符串）；
  - 所有异常（网络超时、API 错误、格式异常）捕获后抛出自定义 `ExecutorError`（携带诊断码），由 `_node_wrapper()` 统一处理。异常处理策略：
    - 在 `diagnostics/codes.py` 中预分配新增诊断码（如 `E_LLM_001` 超时、`E_LLM_002` API 错误、`E_LLM_003` 非法消息格式、`E_SEC_013` 外部调用未授权、`E_SEC_014` 模型不在白名单、`E_SEC_015` tool ref 未授权）；
    - 第二期不实现自动重试，只把超时、5xx 等异常标记为 `retryable=True` 写入诊断 hint；真正的重试策略留到后续阶段，避免当前 `RetryPolicy.max_attempts` 只有模型字段但编译器无执行语义；
    - 运行时诊断传播机制：`LLMExecutor` 异常时抛出 `ExecutorError`，由 `_node_wrapper()` 捕获并记录到 `RunResult.diagnostics`。**不采用** `{"answer": "", "_error": "..."}` 形式的 state update，原因：当前 `_node_wrapper()` 按 `node.outputs` 声明映射输出，`_error` key 不在声明中会被忽略，且空 `answer` 可能导致后续条件路由的非预期分支。采用异常抛出方案与 LangGraph 原生错误模型一致——节点异常时图执行中断，`RunResult.status="failed"`。
- 扩展 `compiler/langgraph_py.py` 中 executor 分发路径，采用**注册表 schema + 运行时动态 handler**模式：
  - `ExecutorRegistry` 仍然是验证阶段的统一 schema 来源，不能完全绕过；
  - `ExecutorDefinition` 增加可选 `dynamic: bool = False` 字段，动态 executor 在 registry 中注册 ref/type/input_schema/output_schema，但 `handler=None`；
  - `ExecutorType.BUILTIN` 保持现有 `executor.invoke()` → `handler()` 路径不变；
  - `ExecutorType.LLM` 和 `ExecutorType.PYTHON_CALLABLE` 为动态 handler 类型：验证阶段仍通过 registry 校验 ref/type/schema，运行阶段在 `invoke_node()` 内根据 type 实例化 `LLMExecutor` 或 `ToolExecutor`；
  - 默认内置注册 `ExecutorDefinition(ref="llm.qwen-plus", type=ExecutorType.LLM, input_schema={"question": STRING}, output_schema={"answer": STRING}, dynamic=True)`，后续可为其他允许模型注册相同 schema 的 executor definition；
  - `_check_registries()` 不对 `ExecutorType.LLM` / `PYTHON_CALLABLE` 做全局豁免，只允许 `definition.dynamic=True` 且 `handler is None` 的 executor 进入动态 dispatch；
  - `check_types()` 继续使用 `ExecutorDefinition.input_schema/output_schema` 做输入输出校验，避免动态 executor 破坏现有 typecheck；
  - 运行阶段 dispatch：`invoke_node()` 中 `if executor.dynamic and executor.type == ExecutorType.LLM: 实例化 LLMExecutor(model_client=...)`，`elif executor.dynamic and executor.type == ExecutorType.PYTHON_CALLABLE: 实例化 ToolExecutor(...)`，`else: 走现有 handler 路径`；
  - `model_client` 通过 `_node_wrapper()` 闭包注入（与现有 `executors`、`event_sink` 闭包捕获方式一致），`LLMExecutor` 不需要在执行体内自行创建 client；
  - `builtin.echo_llm` 保留为 mock/fallback，测试和干运行仍通过 `ref="builtin.echo_llm"` 使用（`ExecutorType.BUILTIN` 路径不受影响）；
  - 在 `invoke_node()` 的 dispatch 调用处增加 `try/except ExecutorError`，捕获后通过 `error_sink` 回调将 `ExecutorError.to_diagnostic()` 传播到 runner 层，并 re-raise 保持 LangGraph 图执行中断语义。`ExecutorError` 定义在 `registry/executors.py` 中，继承 `RuntimeError`，携带 `code: str`（诊断码）、`message: str`、`hint: str | None` 和 `node_id: str | None` 字段，并提供 `to_diagnostic() -> Diagnostic` 方法。
- 在 `registry/builtins.py` 的 `builtin_executor_registry()` 中：
  - 为 `ref="llm.qwen-plus"` 注册 schema-only `ExecutorDefinition(type=ExecutorType.LLM, dynamic=True, handler=None)`，作为真实 LLM executor 的内置最小入口；
  - 为测试或用户扩展的真实模型提供同 schema 注册路径，但模型是否可执行仍由 `workflow.policies.allowed_models` 决定；
  - 不把 `ExecutorType.LLM` 注册为 `builtin.echo_llm` 的可选类型，避免 mock executor 与真实 executor 的 ref/type 语义混淆。

设计约束：

- Executor 实例化时从 `.env` 加载凭据，不在 bundle/lockfile 中写入；
- executor ref 区分 mock 和真实：`ref="builtin.echo_llm"` = mock，`ref="llm.qwen-plus"` = real；
- 动态 executor（`ExecutorType.LLM`、`ExecutorType.PYTHON_CALLABLE`）必须在 `ExecutorRegistry` 中注册 schema-only definition，验证阶段保留 ref/type/schema 校验，运行时根据 executor type 动态实例化 handler。`ExecutorType.LLM` 的 ref 格式约定为 `llm.<model_id>`，`model_id` 必须在 `allowed_models` 白名单中，否则验证阶段报错；
- 不修改现有的 `echo_llm` 函数签名和行为；
- 不修改 `NodeDefinition(kind="llm")` 的 input/output schema。

> **设计依据**：LangGraph 的节点函数签名固定为 `(state) -> update`，不区分节点是调用 LLM、执行工具还是纯函数——这正是 LangGraph 官方文档强调的"nodes do the work, edges tell what to do next"理念。本计划的 `LLMExecutor` 在 `_node_wrapper()` 内部被调用，对外呈现一致的 `(state) -> update` 签名，与 LangGraph 节点模型完全兼容。LangChain v1 中 `create_agent()` 的 `model` 参数接受 `BaseChatModel` 的依赖注入模式（[Agents](https://docs.langchain.com/oss/python/langchain/agents)），本计划的 `model_client` 闭包注入与此一致。此外，LangGraph 原生支持 `RetryPolicy` 在 `add_node()` 时配置（[Add retry policies](https://docs.langchain.com/oss/python/langgraph/use-graph-api#add-retry-policies)），本计划将 `NodeSpec.retry.max_attempts` 映射到 `RetryPolicy` 的路径与 LangGraph 原生机制一致。

### 7.3 Tool Executor 最小受控模型模块

为 `tool` 类型节点的 `PYTHON_CALLABLE` executor 提供受控调用机制。该模块只面向**受信任、预注册**的纯 Python callable，不执行 workflow JSON 中动态声明的 import path，也不承诺不可信代码沙箱能力。

该模块应完成：

- 新增 `registry/tool_executor.py`：
  - `ToolExecutor` 类，包装预注册 Python callable 的调用；
  - 新增 `ToolCallableRegistry`（可放在同模块或 `registry/executors.py`），以 `ref` 映射到 callable，例如 `tool.slugify`、`tool.extract_json`；
  - callable 签名固定为 `(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]`，与现有 `ExecutorHandler` 保持一致；
  - `ToolExecutor.__call__(inputs, params)` 只从 `ToolCallableRegistry` 取 callable，不从 `params` 或 workflow JSON 动态 import 代码；
  - callable 返回值必须是 `dict[str, Any]`，且运行时仍由 `_node_wrapper()` 按 `node.outputs` 校验声明输出；
  - 所有异常捕获后转为 `ExecutorError` 诊断；
  - 设置 `timeout_s`（从 `node.timeout_s` 或 `workflow.policies.default_timeout_s` 获取），通过 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=...)` 检测超时并记录诊断，但无法保证终止执行（超时仅作为软限制）；
  - 文档中明确：该机制不是 subprocess/Docker 沙箱，不适合执行不可信用户代码。
- 扩展 `ExecutorDefinition`：
  - 增加 `dynamic: bool = False`；
  - 为 `PYTHON_CALLABLE` 动态 executor 注册 schema-only definition，`ref` 必须同时存在于 `ToolCallableRegistry` 和 `ExecutorRegistry`；
  - `ExecutorDefinition` 不新增 `allowed_imports` 字段，避免策略来源重复。
- 扩展 `NodeSpec.security`：
  - 在 `SecurityPolicy` 中新增 `allowed_tool_refs: list[str] | None = None`；
  - 节点级 `allowed_tool_refs` 完全覆盖全局策略；空 list 表示该节点禁止调用任何 tool；为 `None` 时使用全局 `workflow.policies.allowed_tool_refs`。
- 扩展 `PolicySpec`：
  - 新增 `allowed_tool_refs: list[str] = Field(default_factory=list)`；
  - 默认空列表表示不允许任何 `PYTHON_CALLABLE` tool 执行；
  - 用户必须显式列出可执行的 tool ref。

设计约束：

- 不做 subprocess 沙箱；
- 不做 Docker 隔离；
- 不做网络访问控制（留给系统级策略）；
- 不执行 workflow JSON 中的动态 import path；
- `PYTHON_CALLABLE` 类型 executor 必须同时满足：ref 已注册、ref 存在于有效 `allowed_tool_refs`、callable 存在于 `ToolCallableRegistry`；否则验证阶段报错；
- `LANGCHAIN_TOOL` 类型不经过此模型，第二期不新增可执行能力。后续阶段若支持 `LANGCHAIN_TOOL`，必须纳入统一安全策略；不能假定 LangChain 自身提供沙箱。

> **设计依据**：LangChain v1 的工具系统以 `BaseTool` 为核心抽象，`@tool` 装饰器是创建工具的标准方式——工具必须有 `name`、`description` 和 `args_schema`，通过 `BaseTool.invoke()` 或 `BaseTool.ainvoke()` 执行（[Tools](https://docs.langchain.com/oss/python/migrate/langchain-v1#tools)）。本计划的 `ToolCallableRegistry` 采用了相同的最小契约：每个 tool 以 `ref`（等价于 `BaseTool.name`）标识，callable 签名为 `(inputs, params) -> dict`（等价于 `BaseTool._run()` 的简化版）。`ExecutorType.LANGCHAIN_TOOL` 已在 IR 模型中预留，后续阶段可通过 `ExecutorDefinition.langchain_tool: BaseTool | None` 字段实现与 LangChain 工具生态的直接兼容——`ToolExecutor` 检测到 `langchain_tool` 非空时调用 `BaseTool.invoke()`。LangChain v1 支持 `create_agent(tools=[...])` 直接传入 `BaseTool` 实例或 `@tool` 装饰的函数（[Agents](https://docs.langchain.com/oss/python/langchain/agents)），本计划预留的 `LANGCHAIN_TOOL` 路径与此模式对齐。

### 7.4 策略与安全约束增强模块

在 `ir/models.py` 现有 `PolicySpec`/`SecurityPolicy` 基础上，补全策略定义并在校验和运行阶段强制检查。

该模块应完成：

#### 7.4.1 IR 模型扩展

- `WorkflowSpec.policies` 新增字段：
  - `external_call: bool` — 是否允许 executor 调用外部 LLM/API（默认 `False`；注意：此默认值意味着旧 workflow JSON 若新增 LLM 类型 executor 节点后，默认无法执行，需显式设置 `"external_call": true`）；
  - `allowed_models: list[str] = Field(default_factory=list)` — 允许的模型 ID 白名单；只要 workflow 中存在 `ExecutorType.LLM` 节点且 `external_call=True`，该列表必须非空并包含所有真实 LLM executor 的 model id；不提供 `None` 表示任意模型的默认放行语义；
  - `collect_metrics: bool = False` — 是否记录每次外部调用的 metadata（模型、耗时、token 数、节点 id、错误状态）。该字段只表示运行结果中的结构化调用记录，不表示写入持久化审计日志文件；若后续需要真实审计日志，应另行定义 JSON Lines 格式输出到 `.pt2lg-runtime/audit.log`；
  - `allowed_tool_refs: list[str] = Field(default_factory=list)` — 允许执行的 `PYTHON_CALLABLE` tool ref 白名单，默认不允许任何 tool 执行。
- 直接扩展 `SecurityPolicy` 类本身（新增 `allowed_tool_refs: list[str] | None = None`），保持类型名 `SecurityPolicy` 不变，避免引入新类型名造成概念噪音。Pydantic 默认 `extra="ignore"`，新增字段不会破坏现有 JSON 反序列化。此为"扩展而非替换"策略：
  - `requires_approval: bool`（继承）；
  - `idempotency_key: str | None`（继承）；
  - `allowed_tool_refs: list[str] | None` — 该节点允许的 tool ref 白名单（覆盖全局 `workflow.policies.allowed_tool_refs`，节点级别完全替代全局配置，非合并；空 list 表示"禁止所有 tool"）。
- 策略来源规则：
  - `WorkflowSpec.policies` 是唯一持久化事实来源，必须写入 `workflow.ir.json` / `workflow.lock.json` 的规范化 IR；
  - CLI/API 覆盖策略时，必须先生成临时 `WorkflowSpec` 并重新执行 `validate_workflow()`，不得在运行时绕过 lockfile 策略；
  - bundle `run` 默认不允许覆盖 lockfile 中的策略；若未来新增覆盖参数，必须在运行事件或调用记录中显式记录覆盖后的策略摘要。

#### 7.4.2 策略校验

> **代码库现状基线**：`validate/security.py` 已存在，含 `check_security(workflow, nodes) -> list[Diagnostic]` 函数（当前仅检查 side_effect 节点的 `E_SIDE_008` 诊断）。以下为在现有函数基础上新增校验函数，而非新增模块。

- 扩展 `validate/security.py`（在现有 `check_security()` 基础上新增函数，而非新增模块），封装独立可测试的策略校验函数：
  - `check_external_policy(workflow)` — 当有 executor.type == ExecutorType.LLM 的节点且 `workflow.policies.external_call == False` 时，报错；
  - `check_model_whitelist(workflow)` — 当有真实 LLM executor 时，校验 `allowed_models` 非空且包含所有 `llm.<model_id>` 中的 model id；
  - `check_tool_refs(workflow, tool_registry)` — 校验 `PYTHON_CALLABLE` 类型 executor 的 ref 是否存在于有效 `allowed_tool_refs`，并且 callable 已在 `ToolCallableRegistry` 中注册；
  - `check_security(workflow, nodes)` — 校验 side_effect 节点安全策略完备性（复用现有函数，保持签名不变）。
- 在 `validate/validator.py` 的 `_check_registries()` 中保留所有 executor 的 `executors.has(ref)` 校验；对 `definition.dynamic=True` 的 executor 允许 `handler=None`，但仍校验声明 type 与 registry type 一致。
- 在 `validate/validator.py` 中组合新增校验函数，执行顺序为 registry → graph → typecheck → security policy。

#### 7.4.3 运行时强制

- 修改 `compiler/langgraph_py.py` 的 `_node_wrapper()` 签名，新增 `policies: PolicySpec`、`model_client: BaseChatModel | None`、`tool_registry: ToolCallableRegistry | None` 和 `error_sink: Callable[[ExecutorError], None] | None` 参数：
  - 当前 `_node_wrapper(node, executors, event_sink, loop_edges, reducers, fanout_result_keys)` 闭包中**没有 `workflow` 对象**，无法访问 `workflow.policies`；
  - 新增 `policies: PolicySpec` 参数，在 `compile_workflow_to_graph()` 调用处传入 `workflow.policies`；
  - 新增 `model_client: BaseChatModel | None` 参数，用于 `LLMExecutor` 的依赖注入（通过闭包捕获传入 `invoke_node()` 内的 dispatch 逻辑），与现有 `executors`、`event_sink` 闭包捕获方式一致；
  - 新增 `tool_registry: ToolCallableRegistry | None` 参数，用于测试和 API 层注入 fake tool registry；CLI 默认使用内置 registry，不从 workflow JSON 动态加载代码；
  - 新增 `error_sink: Callable[[ExecutorError], None] | None` 参数，用于 executor 异常的传播回调——`invoke_node()` 内捕获 `ExecutorError` 后调用 `error_sink(exc)` 将结构化异常传播到 runner 层；
  - 调用 LLM executor 前检查 `policies.external_call` 和 `allowed_models`（此为**防御性二次校验 / belt-and-suspenders**，主要防止绕过验证器的直接调用场景）；
  - 调用 Tool executor 前检查有效 `allowed_tool_refs`；
  - 若 `collect_metrics=True`，记录每次外部调用的 `ExternalCallRecord`，并汇总更新 `RunMetrics`。
- 修改 `compile_workflow_to_graph()` 中调用 `_node_wrapper()` 的位置，传入 `workflow.policies`、`model_client`、`tool_registry` 和 `error_sink`。
- 策略检查阶段分工：
  - **验证阶段**检查静态可判定的策略（如 `external_call=False` 但存在 LLM executor 节点、`allowed_models` 白名单校验、`allowed_tool_refs` 校验）；
  - **运行时**只做防御性二次校验和调用记录，不接受未重新 validate 的策略覆盖。

#### 7.4.4 RunMetrics 与 RunResult 扩展

> **代码库现状基线**：`runtime/events.py` 已定义 `RunMetrics(duration_ms: float | None, token_count: int | None, retry_count: int, tool_call_count: int)` 和 `RunResult.metrics: RunMetrics`（非可选，带默认工厂 `RunMetrics()`）。以下为"扩展而非新增"。

- 扩展现有 `RunMetrics`（定义在 `runtime/events.py`），新增字段：
  - `call_count: int = 0` — 外部 LLM 调用次数；
  - `total_latency_ms: float | None = None` — 外部调用总延迟（毫秒）。
- 新增 `ExternalCallRecord`（定义在 `runtime/events.py`）：
  - `node_id: str`；
  - `executor_ref: str`；
  - `model: str | None = None`；
  - `latency_ms: float | None = None`；
  - `token_count: int | None = None`；
  - `status: Literal["succeeded", "failed"]`；
  - `error_code: str | None = None`。
- 扩展 `RunResult`（定义在 `runtime/events.py`），新增字段：
  - `external_calls: list[ExternalCallRecord] = Field(default_factory=list)` — 仅当 `collect_metrics=True` 时记录外部 LLM/tool 调用详情；
- 保留现有字段不变：`duration_ms`、`token_count`、`retry_count`、`tool_call_count`、`diagnostics`。
- `token_count` 的读取逻辑：从 `response.usage_metadata` 和 `response.response_metadata.get("token_usage")` 兜底读取，无法获取时记为 `None`。
- 运行时 executor 异常通过 `ExecutorError.to_diagnostic()` 写入现有 `RunResult.diagnostics`，不新增单独错误列表，避免与已有 diagnostics 语义重复。

#### 7.4.5 策略摘要联动

- 更新 `policy/resolver.py`，将 `external_call`、`allowed_models`、`collect_metrics`、`allowed_tool_refs` 纳入 resolved policy；
- 更新 `binding/binder.py`，将动态 executor definition、`allowed_models`、`allowed_tool_refs` 反映到 binding summary；
- 新增产物兼容规则：
  - 不因新增 policy 字段修改 `schema_version`，旧 workflow 缺失字段时按 Pydantic 默认值补齐；
  - `workflow.ir.json` / `workflow.lock.json` 中序列化补齐后的 policy 默认值，确保 hash 计算稳定；
  - compile report 可以展示新增策略摘要，但不得写入真实 secret 或 secret 名称；
  - 增加旧 fixture 加载和 lockfile hash 回归测试。

> **设计依据**：LangChain v1 的 middleware 体系是"策略先行"模式的工程化实现。内置 middleware 包括 `HumanInTheLoopMiddleware`（工具调用审批）、`SummarizationMiddleware`（对话历史压缩）、`PIIRedactionMiddleware`（敏感信息脱敏）——每个 middleware 通过 `wrap_model_call` / `wrap_tool_call` / `before_agent` / `after_model` hook 在特定生命周期节点执行检查（[Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)）。本计划的策略体系借鉴了这一分层检查模式：验证阶段做静态策略校验（如 `external_call` 开关、模型白名单），运行时做防御性二次校验和 metrics 收集。LangGraph 的持久化 checkpoint 机制（[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)）提供 `InMemorySaver` / `SqliteSaver` / `PostgresSaver` 等多级 checkpointer，本计划的 `human_gate` 中断/恢复和 `.pt2lg-runtime/` 本地持久化均基于 LangGraph 的 `interrupt()` + `Command(resume=...)` 机制（[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)）。LangGraph `RetryPolicy` 原生支持 `max_attempts`、`initial_interval`、`backoff_factor` 等参数（[Add retry policies](https://docs.langchain.com/oss/python/langgraph/use-graph-api#add-retry-policies)），本计划第二期暂不实现自动重试但预留 `RetryPolicy` 字段映射路径。

### 7.5 集成测试策略补齐模块

覆盖第二期新增的所有能力，以 fake provider 隔离真实网络调用。

该模块应完成：

#### 7.5.1 测试夹具与工具

- 新增 `tests/fake_provider.py`：
  - 优先使用 `langchain_core.language_models.fake.FakeListChatModel`（LangChain 内置 fake chat model），或继承 `BaseChatModel` 实现轻量 fake 类；
  - 不继承 `ChatOpenAI`（避免其 `__init__` 参数要求和内部调用链副作用）；
  - 返回固定 `AIMessage(content="fake response from <model>")`，由 `LLMExecutor` 包装为 `{"answer": ...}`，不触发真实网络调用；
  - 可配置返回内容、`usage_metadata` 和 `response_metadata["token_usage"]`，用于模拟不同响应场景；
  - 定位为统一测试工具模块，整合现有分散在各测试文件中的 FakeModel 变体。
- 新增 `tests/fake_tools.py`：
  - 提供预注册 fake callable，例如 `tool.echo`、`tool.fail`、`tool.sleep`；
  - 通过测试专用 `ToolCallableRegistry` 注入 `compile_workflow_to_graph()` / runner；
  - CLI 集成测试通过 monkeypatch 内置 registry 构造函数注入 fake tool，禁止真实动态 import。

#### 7.5.2 测试层次

| 层次 | 测试文件 | 范围 |
|------|----------|------|
| 单元 | `tests/test_llm_provider.py` | `LLMConfig` 配置加载、`build_llm_client()` 参数优先级、配置覆盖逻辑 |
| 单元 | `tests/test_llm_executor.py` | `LLMExecutor` 使用 fake provider 的执行和异常处理 |
| 单元 | `tests/test_tool_executor.py` | `ToolExecutor` 的预注册 callable 调用、未授权 ref 阻断、超时、异常捕获 |
| 单元 | `tests/test_security_policy.py` | `check_external_policy`、`check_model_whitelist`、`check_tool_refs` |
| 集成 | `tests/test_integration_execution.py` | 真实 LLM executor + fake provider 的完整图执行、tool executor 在 workflow 中的执行 |
| 回归 | `tests/test_compile_flow.py` | 编译产物路径回归 |
| 回归 | `tests/test_cli.py` | CLI `run` 命令在新增 executor 下的行为 |

#### 7.5.3 关键测试场景

1. `LLMConfig` 从 `.env` 和参数加载的优先级正确；
2. 真实 LLM executor 在 fake provider 下返回预期 `{"answer": ...}` 格式；
3. LLM executor 在网络错误时返回诊断而非崩溃；
4. Tool executor 调用预注册且已授权的 `tool.echo` 成功，调用未授权或未注册 tool ref 失败；
5. `external_call=False` 的 workflow 使用 LLM executor 节点时，验证报错；
6. `external_call=True` 但 `allowed_models=[]` 时，验证报错；
7. `allowed_models` 白名单校验生效；
8. `collect_metrics=True` 时，`RunResult.external_calls` 和 `RunResult.metrics.token_count/call_count` 有值；
9. 现有 mock executor（`echo_llm` 等）不受新增 executor 影响；
10. 同时包含 mock 和真实 executor 的 workflow 能正确选择各自的 executor；
11. `API_KEY` 缺失时，LLM executor 返回明确诊断而非崩溃；
12. `build_model_client()` 重构后 `plan` 命令行为不变（回归）；
13. compile 包含 LLM executor 节点的 workflow，验证生成的 `workflow.ir.json` 和 `compile_report.json` 中正确反映了 `external_call`、`allowed_models` 等新增策略字段；
14. `LLMExecutor` 对 `response.usage_metadata` 和 `response.response_metadata.get("token_usage")` 两种 token 信息格式的兜底读取（以 fake provider 模拟两种格式）；
15. CLI / runner 集成测试通过 monkeypatch 或显式参数注入 fake provider / fake tool registry，不触发真实网络调用或动态 import。

#### 7.5.4 不需要的测试

- 不测试真实网络调用（留给手动验收或 e2e 脚本）；
- 不测试 subprocess 隔离深度；
- 不做 LLM 输出质量评估；
- 不测试第一期 Prompt 计划生成链路回归（已有 `test_prompt_planner.py` 覆盖）。

> **设计依据**：LangChain v1 推荐 fake + integration 双层测试策略（[Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing)）。`FakeListChatModel`（来自 `langchain_core.language_models.fake`）继承 `BaseChatModel`，可预设固定响应序列，是 LangChain 生态中单元测试 fake model 的首选方案。LangChain 的测试文档强调：fake model 测试覆盖确定性逻辑（executor 调度、策略校验、输出映射），integration 测试覆盖真实 API 连通性（凭证验证、延迟、schema 兼容性）——两者职责分离，不应混合。本计划的测试分层与此一致：`tests/fake_provider.py` 使用 `FakeListChatModel` 提供 fake 实现，所有单元和集成测试通过 fake provider 覆盖，真实网络调用留给手动验收。LangGraph 还提供 `graph.nodes` 属性支持对编译后图的单个节点进行独立测试（[Testing individual nodes](https://docs.langchain.com/oss/python/langgraph/test#testing-individual-nodes-and-edges)），可用于测试 `_node_wrapper()` 生成的单个节点函数。

---

## 8. 验收标准

### 8.1 执行能力验收

满足以下条件，方可判定第二期主目标达成：

- `llm` 节点可通过 `ExecutorType.LLM` 调用真实模型，fake provider 下可验证完整调用链路；
- `tool` 节点可通过 `PYTHON_CALLABLE` executor 执行受信任、预注册且经 `allowed_tool_refs` 授权的纯 Python callable；
- 真实 executor 和 mock executor 可通过 executor ref 区分，mock 行为完全兼容；
- 所有新增 executor 不改变现有 `validate / compile / run / graph / plan / resume` 命令行为。

### 8.2 Provider 抽象验收

第二期在 LLM Provider 层应满足：

- 通过 `llm.provider.build_llm_client()` 统一构造 `langchain_openai.ChatOpenAI` 客户端；
- `llm.config.LLMConfig` 支持 `model`、`base_url`、`api_key`（`SecretStr`）、`temperature`、`max_tokens`、`request_timeout_s` 参数；
- 默认从 `.env` 加载配置，调用方参数可覆盖；
- `prompting/planner.py` 的 `build_model_client()` 兼容委托给新 provider；
- 后续 Skills planning 与 runtime `LLMExecutor` 均依赖顶层 `llm/`，不依赖 `prompting/`；
- 不引入多 provider 路由，不做 provider 热切换；
- 自动化验证：`tests/test_llm_provider.py` 覆盖配置加载优先级、参数覆盖、`SecretStr` 脱敏。

### 8.3 安全策略验收

安全策略层应满足以下条件：

- Workflow 默认 `external_call=False`，LLM executor 在此设置下无法执行；
- `external_call=True` 时必须显式配置非空 `allowed_models`；
- `allowed_models` 白名单可限制 LLM executor 可调用的模型；
- `PYTHON_CALLABLE` 类型 executor 必须是 schema-only dynamic executor，并且 ref 存在于有效 `allowed_tool_refs`；
- 未授权或未注册的 tool ref 在验证阶段报错并返回明确诊断；
- `collect_metrics=True` 时，`RunResult.external_calls` 中可获取 token 数、调用次数、节点 id、模型和耗时等 metadata；
- 策略约束在 `validate_workflow()` 阶段即被检查，运行时只做防御性二次校验；
- 自动化验证：`tests/test_security_policy.py` 覆盖 `check_external_policy`、`check_model_whitelist`、`check_tool_refs` 各约束条件。

### 8.4 集成测试验收

测试层至少应满足：

- 补齐第二期所有新增模块的单元测试；
- 以 fake provider 覆盖 LLM executor 完整链路，不依赖真实网络；
- 补齐安全策略各约束条件的独立测试；
- 补齐同时包含 mock 和真实 executor 的集成测试；
- 现有第一期测试基线全部通过（`tests/test_prompt_planner.py`、`tests/test_prompt_parser.py`、`tests/test_public_api.py`、`tests/test_cli.py`）；
- 最终以全量 `uv run pytest` 通过作为第二期回归验收基线。

### 8.5 文档与边界一致性验收

文档层面应满足：

- `README.md` 明确说明第二期新增的 `llm` 节点真实执行能力和 `tool` 节点受控执行能力；
- `README.md` 明确说明真实执行依赖外部 LLM API，需通过 `.env` 配置；
- `README.md` 明确说明策略约束体系及其默认安全关闭状态；
- `CLAUDE.md` 与 `AGENTS.md` 同步反映新的 runtime 能力和安全边界；
- 文档中区分 `plan` 命令使用的 LLM（第一期能力）和运行时 `llm` 节点使用的 LLM（第二期能力）；
- 文档不应错误暗示"所有节点类型均已具备真实执行能力"；
- 文档职责拆分：`README.md` 面向用户（能力说明、配置示例），`CLAUDE.md` 面向 Claude Code（架构速览、修改规则），`AGENTS.md` 面向所有 AI Agent（边界约束、硬规则）。"对外能力说明"主要落入 `README.md`，`CLAUDE.md` 和 `AGENTS.md` 只需更新运行时能力和安全边界的内部描述，避免三份文档大量重复段落；
- 明确说明 `.env` 配置现在同时服务于 Prompt 计划生成和运行时 LLM 执行，并区分两组配置的使用场景。

### 8.6 非目标验收

第二期完成时，以下事项仍不应被视为必须完成项：

- 多 provider 适配器体系；
- subprocess / Docker / 网络沙箱隔离；
- `join` edge 执行支持；
- `side_effect` 最小执行闭环；
- `skill_dir` 到 `WorkflowSpec` 的可执行转换；
- LLM 输出质量评估或多轮反思机制；
- Prompt 计划生成阶段的 LLM 能力扩展；
- 从 Prompt 自动生成真实 `llm.<model_id>` / `tool.<name>` executor 的能力。

只要上述能力仍未实现，但手写或适配得到的 `WorkflowSpec` 中 `llm` 和 `tool` 节点已能在策略约束下可验证运行，第二期依然可以判定为完成。

---

## 9. 后续衔接建议

在本开发计划文档确认后，下一步应进入更细粒度的实施计划阶段，进一步明确：

- 模块级改动落点与文件级实施步骤；
- 关键接口设计与执行器注册路径；
- 测试拆分与回归顺序；
- 实施依赖关系（Provider → LLM Executor → Tool Executor → 策略 → 测试）；
- 阶段性完成标准与里程碑。

该阶段再展开到文件级或接口级实施计划，不在本文档中继续展开。

---

## 附录 A：模块依赖关系

```
LLM Provider 抽象 ──────────────→ 真实 LLM Executor
                                        │
                                        ├──→ policy/resolver 策略摘要
                                        │
Tool Executor 最小受控模型 ────────→ 策略与安全约束增强模块
                                        │
                                        ├──→ validate/validator 策略校验
                                        │
                                        ├──→ runtime/runner 运行时强制
                                        │
                                        └──→ binding/binder binding summary
                                        │
                                        ↓
                                 集成测试策略补齐
                                        │
                                        └──→ tests/fake_provider
                                        └──→ tests/test_{llm_provider,llm_executor,tool_executor,security_policy,integration_execution}
```

### 实施顺序建议

1. **顶层 `llm/` 轻量基础模块** — 无依赖，可先行实施；
2. **策略校验接口定义** — 在 `validate/security.py` 中定义函数签名和测试，与 executor 实现并行（设计原则 6.4"策略先行于执行"要求策略接口先于 executor 实现）；
3. **真实 LLM Executor** — 依赖 Provider 抽象；
4. **Tool Executor 最小受控模型** — 与 LLM Executor 无依赖，可与步骤 3 并行；
5. **策略与安全约束增强** — 依赖步骤 3 和 4 的 executor 类型定义，与步骤 2 的接口定义联调；此步骤包含 `_node_wrapper()` 和 `compile_workflow_to_graph()` 签名扩展（新增 `policies`、`model_client`、`tool_registry`、`error_sink` 参数），runner.py 中对接 `error_sink` 回调与 `RunResult.diagnostics`、`RunResult.external_calls` 收集；
6. **集成测试策略补齐** — 依赖以上所有模块。

> **RetryPolicy 与策略约束交互说明**：第二期不实现自动重试。若节点定义了 `retry.max_attempts > 1`，该字段暂不改变 LLM executor 的执行次数；超时和 5xx 仅在诊断 hint 中标记为可重试，后续阶段再实现真实 retry 语义。

---

## 附录 B：LangChain / LangGraph 官方文档参考索引

本计划中的设计决策参考了以下 LangChain/LangGraph v1 官方文档页面。按主题分类整理，便于实施阶段查阅。

### LangGraph 核心

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Graph API 概览 | [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api) | 6.1, 7.2 |
| 使用 Graph API（增量构建） | [Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api) | 6.1, 7.2 |
| StateGraph API | [StateGraph (Graph API)](https://docs.langchain.com/oss/python/langgraph/pregel#stategraph-graph-api) | 6.1 |
| 节点与边 | [Nodes](https://docs.langchain.com/oss/python/langgraph/graph-api#nodes) | 7.2 |
| Interrupt 中断机制 | [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | 7.4 |
| Command 恢复机制 | [Command](https://docs.langchain.com/oss/python/langgraph/graph-api#command) | 7.4 |
| 持久化与 Checkpoint | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 7.4 |
| RetryPolicy 重试策略 | [Add retry policies](https://docs.langchain.com/oss/python/langgraph/use-graph-api#add-retry-policies) | 7.2, 7.4 |
| 单节点测试 | [Testing individual nodes](https://docs.langchain.com/oss/python/langgraph/test#testing-individual-nodes-and-edges) | 7.5 |

### LangChain Agent 与 Middleware

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| create_agent 概述 | [Agents](https://docs.langchain.com/oss/python/langchain/agents) | 6.3, 7.2 |
| create_agent API | [create_agent](https://docs.langchain.com/oss/python/releases/langchain-v1#create_agent) | 6.3 |
| Custom middleware（hook 机制） | [Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) | 6.4, 7.4 |
| Middleware hooks 一览 | [Middleware hooks](https://docs.langchain.com/oss/python/releases/langchain-v1#custom-middleware) | 6.4, 7.4 |
| Human-in-the-Loop（内置 HITL） | [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) | 6.5 |
| LangChain v1 namespace | [LangChain v1 namespace](https://docs.langchain.com/oss/python/releases/langchain-v1#namespace) | 7.1 |

### 模型与工具

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Chat model 集成 | [Chat model integrations](https://docs.langchain.com/oss/python/integrations/chat/index) | 6.2, 7.1 |
| Providers 概览 | [Providers overview](https://docs.langchain.com/oss/python/integrations/providers/overview) | 6.2 |
| BaseTool 与工具系统 | [Tools](https://docs.langchain.com/oss/python/migrate/langchain-v1#tools) | 6.5, 7.3 |
| 集成实现指南（BaseTool） | [Implement a LangChain integration](https://docs.langchain.com/oss/python/contributing/implement-langchain) | 7.3 |

### 测试

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| 单元测试（fake model） | [Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing) | 6.3, 6.6, 7.5 |
| 集成测试 | [Integration testing](https://docs.langchain.com/oss/python/langchain/test/integration-testing) | 6.6, 7.5 |

> **使用说明**：以上链接基于 LangChain/LangGraph v1 官方文档（docs.langchain.com），查询日期为 2026 年 5 月。后续实施时如遇链接失效，可通过 docs.langchain.com 搜索对应主题关键词获取最新页面。

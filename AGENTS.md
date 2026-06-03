# AGENTS.md

## 基本要求

- 默认使用中文回复。
- 代码、测试和文档修改应以当前目录为项目根：`/Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph`。
- 本项目源码位于 `src/prompt2langgraph/`，测试位于 `tests/`。
- 保持改动聚焦，避免无关重构、格式化 churn 或生成缓存文件提交。

## 项目定位

`prompt2langgraph` 是一个工具包，用于把经过验证的 Workflow IR 或简化 JSON plan 编译为确定性的 LangGraph Python 图，并提供本地验证、编译产物生成、运行、恢复和 Mermaid 渲染能力。

两份 v0.1 文档是阶段目标和架构基线，其中部分内容仍是“待实现/应实现”描述；当文档与当前源码或测试冲突时，以 `src/prompt2langgraph/` 和 `tests/` 的实际行为为准。

核心边界：

- 规范模型与 IR 类型：`src/prompt2langgraph/ir/models.py`
- IR 规范化、lock、manifest、report：`src/prompt2langgraph/ir/normalize.py`、`src/prompt2langgraph/ir/lockfile.py`
- JSON plan 适配：`src/prompt2langgraph/adapters/json_plan.py`
- skill 目录静态分析：`src/prompt2langgraph/adapters/skill_dir.py`
- node / executor registry：`src/prompt2langgraph/registry/`
- policy 与资源绑定：`src/prompt2langgraph/policy/resolver.py`、`src/prompt2langgraph/binding/binder.py`
- 校验入口：`src/prompt2langgraph/validate/validator.py`
- LangGraph 编译：`src/prompt2langgraph/compiler/langgraph_py.py`
- 编译产物生成与读取：`src/prompt2langgraph/compiler/codegen.py`、`src/prompt2langgraph/runtime/artifacts.py`
- 本地运行与 interrupt/resume：`src/prompt2langgraph/runtime/runner.py`
- Mermaid 渲染：`src/prompt2langgraph/visualization/mermaid.py`
- CLI：`src/prompt2langgraph/cli.py`
- public API：`src/prompt2langgraph/__init__.py`

当前不是 prompt-to-code 生成器。内置 mock executor 用于本地确定性测试；通过 `ExecutorType.LLM` 和 `ExecutorType.PYTHON_CALLABLE` 可接入真实 LLM 模型调用和受控 Tool 执行，但需显式启用策略开关。`ToolCallableRegistry` 提供受控 Tool 执行能力；`side_effect` 是节点类型契约，不做 subprocess 隔离或网络控制。

Prompt 计划生成能力已落地：通过 `plan_prompt_to_workflow_spec()` 或 CLI `pt2lg plan` 命令，可由自然语言 Prompt 经 LLM 生成简化 JSON plan，再经 `JSONPlanAdapter` 转为 `WorkflowSpec`。Prompt 计划生成基于 `langchain_openai`，默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，优先兼容 Qwen、vLLM 暴露的 OpenAI-style API 及其他第三方兼容接口。Prompt 只生成简化 JSON plan；运行时 `llm` 节点的真实执行需 `external_call=True` + `allowed_models`。

结构化 Prompt/Skill planning 已落地：`plan_prompt()` 和 `plan_skill()` 返回 generation、parse、adapter、validation、compile smoke 阶段状态、diagnostics、validation report、repair attempts 和 tool readiness 摘要。兼容入口 `plan_prompt_to_workflow_spec()` / `plan_skill_to_workflow_spec()` 仍保持旧链路语义，成功时直接返回 `WorkflowSpec`，不默认执行 compile smoke。结构化 planning 默认保持 `tool_registry=None` 的校验兼容语义；需要严格检查 Tool callable 注册时可显式注入空或已注册的 `ToolCallableRegistry`。

## 当前能力边界

- 输入：规范 Workflow IR，或通过 `json_plan_to_workflow_spec()` 适配的简化 JSON plan，或通过 `plan_prompt_to_workflow_spec()` 由 Prompt 经 LLM 生成简化 JSON plan。
- JSON plan 适配保留显式 `workflow_id`、顶层 `metadata`、`policies`、`state_schema.reducers`、兼容顶层 `reducers` 和 edge 级 `join_sources`。
- Prompt 计划生成：`prompting/planner.py` 封装 LLM 调用（`build_model_client()` 委托给 `llm.provider.build_llm_client()`），`prompting/parser.py` 支持纯 JSON、fenced JSON、包裹文本中唯一 JSON object 并产出 `AdapterParseError` 诊断，`prompting/pipeline.py` 提供结构化 planning、repair、validation、compile smoke，`prompting/config.py` 从 `.env` 加载 `MODEL`、`BASE_URL`、`API_KEY`（已标记 deprecated，委托给 `llm.config`）。
- LLM 执行：`llm` 节点可通过 `ExecutorType.LLM`（ref 格式 `llm.<model_id>`）调用真实模型，需 `external_call=True` + `allowed_models` 白名单。`LLMExecutor` 在 `registry/llm_executor.py`。
- Tool 执行：`tool` 节点可通过 `ExecutorType.PYTHON_CALLABLE` 执行受控 callable，需 `allowed_tool_refs` 白名单 + `ToolCallableRegistry` 注册。`ToolExecutor` 在 `registry/tool_executor.py`。
- CLI `compile` / `run` / `resume` 支持 `--tool-module <module>` 加载受信任 Python module；module 必须暴露 `register_tools(registry)`，并通过 `ToolCallableRegistry.register(ref, callable)` 注册工具。tool module 必须先于 workflow parse/load 加载，简化 JSON plan 的自定义 tool ref 依赖该顺序。`--tool-module` 不是 sandbox，不支持任意 shell；tool 执行仍需 `allowed_tool_refs` 授权。tool ref 不允许重复注册，也不允许覆盖内置或既有 executor ref。
- Prompt 只生成简化 JSON plan；运行时 `llm` 节点的真实执行需 `external_call=True` + `allowed_models`。
- skill：`analyze_skill_dir()` 保留静态分析能力；Skill → `WorkflowSpec` 的 LLM 驱动 alpha 转换已实现（`plan --skill-dir`），可诊断、可人工修正，不保证任意 Skill 一次成功；不执行 skill 脚本，不自动注册 tool callable。
- 节点类型 registry：`llm`、`tool`、`retriever`、`transform`、`router`、`human_gate`、`join`、`side_effect`。
- 内置 executor：`builtin.echo_llm`、`builtin.mock_retriever`、`builtin.identity_transform`、`builtin.route`、`builtin.human_gate`、`builtin.join`。动态 executor：`llm.qwen-plus`（`ExecutorType.LLM`，`dynamic=True`）。
- `compile_workflow_to_graph()` 和 `run_workflow()` 当前目标能力支持 `linear`、`conditional`、`loop`、`fanout`、`join`（基于 `join_sources` + reducer）。
- `human_gate` 使用 LangGraph `interrupt()`；CLI 对 lockfile bundle 的等待态会写入 bundle 目录下 `.pt2lg-runtime/`。安装可选依赖 `checkpoint-sqlite`（`langgraph-checkpoint-sqlite>=2.0`）后，CLI 使用 `SqliteSaver` 提供更稳定的本地 checkpoint，路径为 `.pt2lg-runtime/<thread_hash>.db`。旧 `.json` runtime 状态文件与新的 `.db` checkpoint 不互相迁移。SQLite checkpoint 默认保留以支持后续 time travel debugging，但 resume 成功后不再自动清理 `.db` 文件。
- 编译产物路径已统一：CLI `pt2lg compile` 和 public `compile_workflow()` 都通过 `runtime.artifacts.compile_workflow_to_artifacts()` 写入 bundle，包含 compile id、timing、policy summary 和 binding summary。
- generated bundle 的 `generated/graph.py` 暴露 `RuntimeConfig`、`build_graph(config=None)`、`invoke(input_payload=None, config=None)`，并兼容保留 `compile_graph()`、`invoke_graph()`。
- `RuntimeConfig` 支持注入 `executor_registry`、`model_client`、`tool_registry`、`checkpointer` 和完整 `PolicySpec` 覆盖；它是库内 bundle 的最小运行时配置入口，不是 deployable service wrapper，也不是 secret manager。
- 编译失败时不能留下可误用的旧 bundle；`compile_workflow_to_artifacts()` 会清理同一输出目录下已知的旧产物文件和 `generated/`，但保留无关文件。
- binding summary 记录 executor ref、type、required capabilities 名称、dynamic 标记、allowed_models 和 external_call。
- `manifest.json` 包含 secret-free `runtime_requirements`，只记录 `model_refs`、`tool_refs`、`checkpoint_required` 和 policy summary，不写入 secret 或 secret 名称。
- `llm/` 顶层模块为 LLM 客户端构造共享入口（`LLMConfig`、`build_llm_client()`、`dict_messages_to_langchain()`），`.env` 配置同时服务于 Prompt 计划生成和运行时 LLM 执行。
- v0.3 3B 已实现 `NodeSpec.retry.max_attempts` 的 wrapper retry；可重试错误范围保持窄口径：LLM timeout、LLM API timeout/5xx/server failure、tool timeout。
- `side_effect` retry 必须声明 `security.idempotency_key`；成功副作用以 `(workflow_id, thread_id, node_id, idempotency_key)` 为作用域记录原始 executor output，重复命中时不再次调用 executor。
- `collect_metrics=True` 时，`RunResult.external_calls` 中可获取成功和失败调用的 `ExternalCallRecord`，包含 latency、status、attempt、category；`RunMetrics` 汇总 retry/tool/call/latency。
- 使用 `state_store_dir` 或 CLI `.pt2lg-runtime` 时会写入安全 audit 元数据到 `.pt2lg-runtime/audit.log.jsonl`，不得包含 secret、完整 payload、API key、完整模型响应或敏感 tool 参数。
- CLI `run` 命令能根据 workflow 节点类型自动构造 `model_client` 和 `tool_registry`，并可通过 `--tool-module` 注册受信任 Python callable。
- `run_workflow()` 支持 `checkpointer` 注入以实现状态持久化和恢复。
- `side_effect` 节点默认需要审批，通过 `pt2lg resume --resume '{"decision":"approved"}'` 恢复执行。
- 3C 已补齐最小 runtime config bundle；不要把当前 bundle 描述扩展为 standalone deployment bundle、secret manager、sandbox 或远程审计服务。
- 策略约束在 `validate_workflow()` 阶段即被检查：`external_call` 开关、`allowed_models` 白名单、`allowed_tool_refs` 白名单。
- `LANGCHAIN_TOOL` 在 v0.3 为保留类型，`validate_workflow()` 会直接拒绝执行；v0.3 tool path 是受信任 Python tool module + `ExecutorType.PYTHON_CALLABLE`。
- 3C engineering gates 覆盖 deterministic compile、bundle load/invoke、dynamic tool、side-effect interrupt/resume 和 offline corpus；这不代表项目已提供 standalone deployment bundles、secret manager integration、sandboxing、remote audit services 或 LangChain Tool execution。

## Do & Don't

### Do
- 新增 IR 字段时，同步更新 Pydantic 模型、规范化、校验、编译/运行边界、测试夹具和文档。
- 新增节点或 executor 时，通过 registry 定义契约，并补充校验和运行测试；内置 executor 必须保持确定性，不能隐式调用外部 LLM 或网络。
- side effect 节点默认必须要求审批或幂等键，除非 workflow policy 显式允许副作用。
- 编译产物结构变更时，同步更新 `tests/test_compile_flow.py` 等回归测试。
- 若改动涉及 Prompt 入口（`prompting/`、`cli.py plan`、`__init__.py`），额外跑 `tests/test_prompt_planner.py`、`tests/test_prompt_parser.py`、`tests/test_public_api.py`、`tests/test_cli.py` 回归。
- 若改动涉及 executor dispatch 或策略校验，额外跑 `tests/test_security_policy.py`、`tests/test_integration_execution.py`。
- 文档修改需同步 `README.md`、`CLAUDE.md`、`AGENTS.md`。

### Don't
- 不要把上层 `ref-projects/` 的参考工程内容当作本项目源码。
- 不要重新引入 `cli._write_compile_artifacts()` 一类的第二套产物写入路径。
- 不要宣称 JOIN 可执行而不声明 `join_sources` 和 reducer（未声明 reducer 的并行写入会覆盖且顺序不稳定）。
- 不要在 `tests/test_compile_flow.py` 模块导入阶段执行编译、写文件或打印 smoke output。
- 不要在 `prompt2langgraph.cli` 模块导入阶段急切导入 `langgraph` 或 `langchain_openai`。
- 不要在 manifest、compile report 和 lockfile 中写入真实 secret 或 secret 名称。
- 不要让 Prompt 入口直接生成并执行 Workflow IR；Prompt 只生成简化 JSON plan。
- 不要把 `plan` 命令演化成直接运行 workflow 的命令。

## 命令输出保护

任何可能产生未知或大量输出的命令，必须限制输出字节数以保护上下文使用。默认模式：

```bash
COMMAND 2>&1 | head -c 4000
```

- `2>&1`：将标准错误重定向到标准输出，确保错误信息也被捕获
- `head -c 4000`：仅保留前 4000 字节输出，超出部分截断

适用场景：查看大文件、日志输出、递归目录列表等可能产生大量输出的命令。

## 开发命令

常用命令：

```bash
uv sync
git config core.hooksPath .githooks
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --json
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --compile-smoke --json
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --repair-attempts 1 --json
uv run pt2lg plan --skill-dir path/to/skill --param key=value --json
```

全量测试基线：

```bash
uv run pytest
```

单文件验证（优先使用）：

```bash
# 类型检查
uv run python -m mypy src/prompt2langgraph/compiler/codegen.py

# 格式化
uv run ruff format src/prompt2langgraph/compiler/codegen.py

# 运行单个测试文件
uv run pytest tests/test_compile_flow.py -v

# 运行离线语料 pytest 入口（注意：tests/prompts_skills_test/ 是语料目录，不是 pytest 入口）
uv run pytest tests/test_prompt_skill_corpus.py -v

# 运行单个测试函数
uv run pytest tests/test_compile_flow.py::test_compile_linear -v
```

编译产物路径回归验收：

```bash
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
uv run pt2lg run build/linear_llm/workflow.lock.json --input '{"question":"hello"}' --json
```

常用控制流验证：

```bash
uv run pt2lg run tests/fixtures/loop_with_guard.json --input '{"question":"hello"}' --json
uv run pt2lg run tests/fixtures/fanout_map_reduce.json --input '{"items":["alpha","beta"]}' --json
uv run pt2lg run tests/fixtures/join.json --input '{"data":"test"}' --json
uv run pt2lg compile tests/fixtures/conditional_human_gate.json --out build --json
uv run pt2lg run build/conditional_human_gate/workflow.lock.json --input '{"question":"hello","confidence":0.5}' --json
uv run pt2lg resume build/conditional_human_gate/workflow.lock.json --thread-id '<thread_id>' --resume '"approved"' --json
```

上述 lockfile 运行和 resume 命令依赖 `pt2lg compile` 先成功生成 bundle；修改编译产物结构、运行恢复逻辑或 lockfile 读取逻辑后，应重新运行这些命令做回归验收。

## 安全与权限边界

无需询问可直接执行：
- 读取文件、列出目录
- 修改 `src/` 和 `tests/` 目录下的现有文件
- 运行单文件类型检查、格式化、单测
- 运行 `uv run pytest` 全量测试

必须询问用户：
- 安装新依赖（`uv add`）
- 删除文件或目录
- 执行 `git commit` 或 `git push`
- 修改 `pyproject.toml`、CI 配置或其他项目级配置文件
- 运行涉及网络调用的命令

## 测试要求

- 修改行为前先阅读对应测试；新增行为必须补充或更新 `tests/`。
- 至少运行 `uv run pytest`。
- 若全量测试失败，最终说明精确失败位置和错误；修复后再以 `uv run pytest` 作为完成标准。
- 若改动涉及 Prompt 入口（`prompting/`、`cli.py plan`、`__init__.py`），额外跑 `tests/test_prompt_planner.py`、`tests/test_prompt_parser.py`、`tests/test_public_api.py`、`tests/test_cli.py`。
- 若改动涉及 executor dispatch 或策略校验，额外跑 `tests/test_security_policy.py`、`tests/test_integration_execution.py`。
- 若只修改文档，也应运行 `uv run pytest` 做回归确认；如因环境问题无法通过，最终说明原因。

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 基本约束

- 默认使用中文回复。
- 项目根目录：`/Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph`。
- 改动保持聚焦，避免无关重构、批量格式化 churn 或提交缓存文件。
- 任何可能产生大量输出的命令都应截断：`COMMAND 2>&1 | head -c 4000`。

## 项目定位与边界

`prompt2langgraph` 用于把经过校验的 Workflow IR 或简化 JSON plan 编译为确定性的 LangGraph Python 工作流，并提供校验、编译产物生成、运行、恢复和 Mermaid 渲染。

以 `src/prompt2langgraph/` 和 `tests/` 的实际行为为准。内置 executor 仅用于本地确定性 mock/纯函数/人工中断占位，不应隐式调用外部 LLM、网络服务或 shell。`tool` / `side_effect` 是节点类型契约，不代表存在可直接执行外部工具或副作用的内置 executor。

当前可执行输入有三类：
- 规范 `WorkflowSpec` IR
- 通过 `json_plan_to_workflow_spec()` 适配的简化 JSON plan
- 通过 `plan_prompt_to_workflow_spec()` 由 Prompt 文本经 LLM 生成简化 JSON plan，再经 `JSONPlanAdapter` 转为 `WorkflowSpec`

Prompt 计划生成基于 `langchain_openai`，默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，优先兼容 Qwen、vLLM 暴露的 OpenAI-style API 及其他第三方兼容接口。当前 Prompt 只生成简化 JSON plan，不代表 runtime `llm` 节点具备真实执行能力。

`analyze_skill_dir()` 只做 `SKILL.md` 与资源文件静态分析，不生成可执行工作流，也不执行 skill 脚本。

## 常用命令

```bash
# 安装
uv sync

# 测试
uv run pytest
uv run pytest tests/test_compile_flow.py -v
uv run pytest tests/test_compile_flow.py::test_compile_linear -v

# lint / format
uv run ruff check src tests scripts
uv run ruff format src tests scripts

# CLI 基本流程
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid

# Prompt 计划生成
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --json

# bundle / resume
uv run pt2lg run build/linear_llm/workflow.lock.json --input '{"question":"hello"}' --json
uv run pt2lg graph build/linear_llm/workflow.lock.json --format mermaid --json
uv run pt2lg compile tests/fixtures/conditional_human_gate.json --out build --json
uv run pt2lg run build/conditional_human_gate/workflow.lock.json --input '{"question":"hello","confidence":0.5}' --json
uv run pt2lg resume build/conditional_human_gate/workflow.lock.json --thread-id '<thread_id>' --resume '"approved"' --json

# 典型控制流回归
uv run pt2lg run tests/fixtures/loop_with_guard.json --input '{"question":"hello"}' --json
uv run pt2lg run tests/fixtures/fanout_map_reduce.json --input '{"items":["alpha","beta"]}' --json
```

## 架构速览

核心流水线：
1. `cli.py` 读取 JSON，按 IR 或简化 JSON plan 分流；`plan` 命令通过 Prompt 生成简化 JSON plan。
2. `prompting/planner.py` 调用 LLM 生成 JSON plan 文本；`prompting/parser.py` 解析并产出诊断；`prompting/config.py` 从 `.env` 加载配置。
3. `adapters/` 转成规范 `WorkflowSpec`。
4. `ir/normalize.py` 规范化。
5. `validate/validator.py` 组合 schema / registry / graph / type / security 校验。
6. `policy/resolver.py` 与 `binding/binder.py` 生成策略摘要和 executor 绑定。
7. `compiler/langgraph_py.py` 编译为 LangGraph `StateGraph`。
8. `runtime/artifacts.py` 写入或读取 bundle。
9. `runtime/runner.py` 执行图、记录事件，并处理 interrupt/resume。

关键模块职责：
- `ir/models.py`：规范 IR、节点/边、state schema 的 Pydantic 模型。
- `adapters/ir.py`、`adapters/json_plan.py`：源 JSON → `WorkflowSpec`。
- `prompting/planner.py`：Prompt → LLM → JSON plan 文本生成，`plan_prompt_to_workflow_spec()` 串联生成与适配。
- `prompting/parser.py`：LLM 输出 JSON 解析与 `AdapterParseError` 诊断。
- `prompting/config.py`：从 `.env` 加载 `MODEL`、`BASE_URL`、`API_KEY`。
- `adapters/skill_dir.py`：skill 目录静态预分析。
- `registry/`：节点类型与 executor 注册表，builtins 在 `registry/builtins.py`。
- `compiler/langgraph_py.py`：实现 conditional / loop / fanout 路由与 state schema lowering。
- `runtime/artifacts.py`：bundle 生成、lockfile/manifest/report、bundle 校验、旧产物清理。
- `runtime/runner.py`：运行时事件、`human_gate` interrupt、`.pt2lg-runtime/` 本地恢复状态。
- `visualization/mermaid.py`：Mermaid 渲染。
- `__init__.py`：稳定 public API：`WorkflowSpec`、`validate_workflow`、`run_workflow`、`compile_workflow`、`PromptPlanRequest`、`PromptPlanResult`、`plan_prompt_to_workflow_spec`。

## 当前执行能力

- runtime/compiler 当前支持 `linear`、`conditional`、`loop`、`fanout`；`join` 只存在于 IR / Mermaid，可表达但不可执行。
- 条件表达式只支持简单 `<state_key> <comparison> <literal>`。
- `loop` 依赖 `loop_guard.max_iterations`；`fanout` 的 reduce 依赖 `state_schema.reducers`。
- `pt2lg compile` 与 public `compile_workflow()` 统一走 `runtime.artifacts.compile_workflow_to_artifacts()`。
- 成功 bundle 包含：`workflow.ir.json`、`workflow.lock.json`、`manifest.json`、`compile_report.json`、`graph.mmd`、`generated/*.py`。
- `workflow.lock.json` 是 bundle `run` / `graph` / `resume` 的入口；加载时会校验其与 `workflow.ir.json` 的 hash 一致性。
- 编译失败会清理已知旧产物和 `generated/`，避免误用旧 bundle。
- `human_gate` 基于 LangGraph `interrupt()`；CLI bundle 运行的等待态保存在 bundle 下 `.pt2lg-runtime/`，resume 成功后清理。该持久化格式依赖 `InMemorySaver` 内部结构，只适合短期本地开发，不是稳定交换格式。

## 修改时的硬规则

- 新增 IR 字段时，同时更新模型、规范化、校验、编译/运行边界、测试夹具和文档。
- 新增节点类型或 executor 时，先补 registry 契约，再补校验与运行测试；内置 executor 必须保持确定性。
- `side_effect` 节点默认需要审批或幂等键，除非 workflow policy 明确允许副作用。
- 修改编译产物结构时，同步更新编译/lockfile/bundle 相关回归测试。
- 不要重新引入第二套产物写入路径；产物统一经 `runtime.artifacts` 生成。
- 不要在 `prompt2langgraph.cli` 模块导入阶段急切导入 `langgraph` 或 `langchain_openai`。
- 不要在 manifest、compile report、lockfile 中写入真实 secret 或 secret 名称。
- 不要把 `join` edge 当成当前可执行能力。
- 不要让 Prompt 入口直接生成并执行 Workflow IR；Prompt 只生成简化 JSON plan。
- 不要把 `plan` 命令演化成直接运行 workflow 的命令。

## 测试要求

- 修改行为前先读对应测试，新增行为必须更新 `tests/`。
- 完成后至少运行 `uv run pytest`。
- 若改动涉及编译产物、bundle 读取、resume 或 lockfile 路径，额外跑相关 CLI fixture 回归命令。
- 若改动涉及 Prompt 入口（`prompting/`、`cli.py plan`、`__init__.py`），额外跑 `tests/test_prompt_planner.py`、`tests/test_prompt_parser.py`、`tests/test_public_api.py`、`tests/test_cli.py`。
- 文档修改需同步 `README.md`、`CLAUDE.md`、`AGENTS.md`。
- 即使只改文档，也优先运行 `uv run pytest` 做回归确认。

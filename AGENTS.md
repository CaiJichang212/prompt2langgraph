# AGENTS.md

## 基本要求

- 默认使用中文回复。
- 代码、测试和文档修改应以当前目录为项目根：`/Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph`。
- 不要把上层 `ref-projects/` 的参考工程内容当作本项目源码；本项目源码位于 `src/prompt2langgraph/`，测试位于 `tests/`。
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

当前不是 prompt-to-code 生成器，也没有实现 `prompt_text` 或 `plan_text` 适配器。内置 executor 仅覆盖本地确定性 mock/纯函数/人工中断占位，不应隐式调用外部 LLM、网络服务或 shell 命令；`tool` 和 `side_effect` 是节点类型契约，不代表存在可直接执行外部工具或副作用的内置 executor。

## 当前能力边界

- 输入：规范 Workflow IR，或通过 `json_plan_to_workflow_spec()` 适配的简化 JSON plan。
- skill：`analyze_skill_dir()` 只做 `SKILL.md` frontmatter、编号步骤、资源文件和风险词静态分析，输出 `SkillDirectoryAnalysis`/`draft_nodes` 和诊断；不生成可执行 `WorkflowSpec`，也不执行 skill 脚本。
- 节点类型 registry：`llm`、`tool`、`retriever`、`transform`、`router`、`human_gate`、`join`、`side_effect`。
- 内置 executor：`builtin.echo_llm`、`builtin.mock_retriever`、`builtin.identity_transform`、`builtin.route`、`builtin.human_gate`、`builtin.join`。
- `compile_workflow_to_graph()` 和 `run_workflow()` 当前目标能力支持 `linear`、`conditional`、`loop`、`fanout`；`join` 可存在于 IR/registry/Mermaid 中，但不是当前 LangGraph runner/compiler 的可执行 edge kind。
- `human_gate` 使用 LangGraph `interrupt()`；CLI 对 lockfile bundle 的等待态会写入 bundle 目录下 `.pt2lg-runtime/`，恢复成功后清理对应状态文件；该本地持久化依赖当前 LangGraph `InMemorySaver` 内部结构，不是稳定交换格式。
- 编译产物路径当前有两套实现：`runtime.artifacts.compile_workflow_to_artifacts()` 是较完整的新路径，会写入 compile id、timing、policy summary 和 binding summary；`cli._write_compile_artifacts()` 以及 public `compile_workflow()` 仍调用旧接口，当前会因 `build_compile_report()` 缺少 `compile_id` 和 `timings_ms` 而失败。

## 开发命令

```bash
uv sync
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
```

当前全量测试基线存在已知失败：`uv run pytest` 会在收集 `tests/test_compile_flow.py` 时触发 public `compile_workflow()` 的编译报告签名错误。修复编译产物路径前，可以先运行与本次改动相关的定向测试；修复后必须回到 `uv run pytest` 全量验证。

编译产物路径修复后，使用以下命令做回归验收：

```bash
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
uv run pt2lg run build/linear_llm/workflow.lock.json --input '{"question":"hello"}' --json
```

常用控制流验证：

```bash
uv run pt2lg run tests/fixtures/loop_with_guard.json --input '{"question":"hello"}' --json
uv run pt2lg run tests/fixtures/fanout_map_reduce.json --input '{"items":["alpha","beta"]}' --json
uv run pt2lg compile tests/fixtures/conditional_human_gate.json --out build --json
uv run pt2lg run build/conditional_human_gate/workflow.lock.json --input '{"question":"hello","confidence":0.5}' --json
uv run pt2lg resume build/conditional_human_gate/workflow.lock.json --thread-id '<thread_id>' --resume '"approved"' --json
```

上述 lockfile 运行和 resume 命令依赖 `pt2lg compile` 先成功生成 bundle；在编译路径修复前不要把它们当作当前稳定能力验收。

## 实现约束

- CLI 导入必须保持轻量：`prompt2langgraph.cli` 不应在模块导入阶段急切导入 `langgraph`，相关测试在 `tests/test_cli.py`。
- 新增 IR 字段时，同步更新 Pydantic 模型、规范化、校验、编译/运行边界、测试夹具和文档。
- 新增节点或 executor 时，通过 registry 定义契约，并补充校验和运行测试；内置 executor 必须保持确定性，不能隐式调用外部 LLM 或网络。
- side effect 节点默认必须要求审批或幂等键，除非 workflow policy 显式允许副作用。
- `compile_workflow_to_graph()` / `run_workflow()` 当前支持 linear、conditional、loop、fanout；不要宣称可执行 `join` edge。
- 条件表达式只支持 `<state_key> <comparison> <literal>`，比较符为 `< <= > >= == !=`。
- fanout 的 `map.result_state_key` 必须是数组并声明 reducer；loop 必须声明 `loop_guard.max_iterations`。
- 编译产物必须保持可复现：`workflow.lock.json`、`manifest.json`、`compile_report.json`、`graph.mmd` 和 `generated/*.py` 的结构变更必须同步测试。
- `runtime/runner.py` 的本地 resume 持久化依赖当前 LangGraph `InMemorySaver` 内部结构，只用于短期本地开发状态，不是稳定交换格式。
- 当前源码中 `cli._write_compile_artifacts()`、public `compile_workflow()` 与 `ir.lockfile.build_compile_report()` 的签名存在不一致；修复编译路径时应优先复用或迁移到 `runtime.artifacts.compile_workflow_to_artifacts()`，并同步 CLI、public API、`tests/test_cli.py`、`tests/test_public_api.py`、`tests/test_artifacts.py` 和 `tests/test_compile_flow.py`。
- `tests/test_compile_flow.py` 目前包含模块导入期执行的 compile smoke check；修复编译路径时应让它通过，或将其改成标准 pytest 测试函数，避免收集阶段副作用掩盖其他失败。

## 测试要求

- 修改行为前先阅读对应测试；新增行为必须补充或更新 `tests/`。
- 至少运行 `uv run pytest`。
- 若当前已知失败阻断全量测试，最终说明精确失败位置和错误；修复该失败后再以 `uv run pytest` 作为完成标准。
- 若只修改文档，也应运行 `uv run pytest` 做回归确认；如因已知失败或环境问题无法通过，最终说明原因。

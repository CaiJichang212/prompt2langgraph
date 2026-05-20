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

当前不是 prompt-to-code 生成器，也没有实现 `prompt_text` 或 `plan_text` 适配器。内置 executor 仅覆盖本地确定性 mock/纯函数/人工中断占位，不应隐式调用外部 LLM、网络服务或 shell 命令；`tool` 和 `side_effect` 是节点类型契约，不代表存在可直接执行外部工具或副作用的内置 executor。

## 当前能力边界

- 输入：规范 Workflow IR，或通过 `json_plan_to_workflow_spec()` 适配的简化 JSON plan。
- skill：`analyze_skill_dir()` 只做 `SKILL.md` frontmatter、编号步骤、资源文件和风险词静态分析，输出 `SkillDirectoryAnalysis`/`draft_nodes` 和诊断；不生成可执行 `WorkflowSpec`，也不执行 skill 脚本。
- 节点类型 registry：`llm`、`tool`、`retriever`、`transform`、`router`、`human_gate`、`join`、`side_effect`。
- 内置 executor：`builtin.echo_llm`、`builtin.mock_retriever`、`builtin.identity_transform`、`builtin.route`、`builtin.human_gate`、`builtin.join`。
- `compile_workflow_to_graph()` 和 `run_workflow()` 当前目标能力支持 `linear`、`conditional`、`loop`、`fanout`。
- `human_gate` 使用 LangGraph `interrupt()`；CLI 对 lockfile bundle 的等待态会写入 bundle 目录下 `.pt2lg-runtime/`，恢复成功后清理对应状态文件；该本地持久化依赖当前 LangGraph `InMemorySaver` 内部结构，不是稳定交换格式。
- 编译产物路径已统一：CLI `pt2lg compile` 和 public `compile_workflow()` 都通过 `runtime.artifacts.compile_workflow_to_artifacts()` 写入 bundle，包含 compile id、timing、policy summary 和 binding summary。
- 编译失败时不能留下可误用的旧 bundle；`compile_workflow_to_artifacts()` 会清理同一输出目录下已知的旧产物文件和 `generated/`，但保留无关文件。
- binding summary 只记录 executor ref、type 和 required capabilities 名称。

## Do & Don't

### Do
- 新增 IR 字段时，同步更新 Pydantic 模型、规范化、校验、编译/运行边界、测试夹具和文档。
- 新增节点或 executor 时，通过 registry 定义契约，并补充校验和运行测试；内置 executor 必须保持确定性，不能隐式调用外部 LLM 或网络。
- side effect 节点默认必须要求审批或幂等键，除非 workflow policy 显式允许副作用。
- 编译产物结构变更时，同步更新 `tests/test_compile_flow.py` 等回归测试。

### Don't
- 不要把上层 `ref-projects/` 的参考工程内容当作本项目源码。
- 不要重新引入 `cli._write_compile_artifacts()` 一类的第二套产物写入路径。
- 不要宣称 `join` edge 可执行（当前 LangGraph runner/compiler 不支持）。
- 不要在 `tests/test_compile_flow.py` 模块导入阶段执行编译、写文件或打印 smoke output。
- 不要在 `prompt2langgraph.cli` 模块导入阶段急切导入 `langgraph`。
- 不要在 manifest、compile report 和 lockfile 中写入真实 secret 或 secret 名称。

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
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
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
- 若只修改文档，也应运行 `uv run pytest` 做回归确认；如因环境问题无法通过，最终说明原因。

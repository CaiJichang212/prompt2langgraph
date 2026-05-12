# prompt2langgraph

`prompt2langgraph` 将 Workflow IR 或简化 JSON plan 转换为可验证、可编译、可本地运行的 LangGraph 工作流。项目目标是先建立确定性的 IR、校验、编译产物和本地运行闭环，而不是直接调用真实 LLM 或外部服务。

## 功能概览

- Pydantic 定义的 canonical Workflow IR。
- 简化 JSON plan 到 Workflow IR 的适配器。
- Codex 风格 skill 目录的静态预分析。
- 图结构、类型绑定、executor 注册和安全策略校验。
- LangGraph Python 编译目标：`langgraph-py`。
- 本地 deterministic runner，支持事件、诊断和 human interrupt resume。
- 编译产物：规范化 IR、lockfile、manifest、compile report、Mermaid 图。

## 安装

要求 Python 3.11+。

```bash
uv sync
```

CLI 入口由 `pyproject.toml` 声明为 `pt2lg`：

```bash
uv run pt2lg --help
```

## 快速使用

使用测试夹具验证、编译、运行和渲染图：

```bash
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg compile tests/fixtures/linear_llm.json --target langgraph-py --out build --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
```

`compile` 会写入：

```text
build/<workflow_id>/
  workflow.ir.json
  workflow.lock.json
  manifest.json
  compile_report.json
  graph.mmd
```

## 输入格式

### Workflow IR

IR 必须包含 `schema_version`、`workflow_id`、`entrypoint`、`state_schema`、`nodes` 和 `edges`。示例见 `tests/fixtures/linear_llm.json`。

### 简化 JSON plan

当输入 JSON 没有 `schema_version` 时，CLI 会按简化 plan 解析：

```json
{
  "name": "Research Answer",
  "inputs": {"question": "string"},
  "outputs": {"answer": "string"},
  "nodes": [
    {"id": "retrieve", "kind": "retriever", "executor": "builtin.mock_retriever"},
    {"id": "answer", "kind": "llm", "executor": "builtin.echo_llm"}
  ],
  "edges": [
    {"from": "retrieve", "to": "answer"}
  ]
}
```

## 内置节点与执行器

内置 node kind：

```text
llm, tool, retriever, transform, router, human_gate, join, side_effect
```

内置 executor：

```text
builtin.echo_llm
builtin.mock_retriever
builtin.identity_transform
builtin.route
builtin.human_gate
builtin.join
```

这些 executor 是本地确定性实现，用于验证编译和运行链路。

## 校验规则

校验覆盖：

- 节点、边、entrypoint 的存在性和可达性。
- executor 注册、类型声明和输入输出映射。
- 状态 key 类型兼容性。
- conditional route 必须包含 `true` 和 `false`。
- loop 必须有 `loop_guard.max_iterations`。
- fanout result 必须声明 reducer。
- side effect 节点默认必须配置审批或幂等键。

条件表达式支持形式：

```text
<state_key> <comparison> <literal>
```

比较符支持 `<`、`<=`、`>`、`>=`、`==`、`!=`。

## 当前边界

- CLI `compile` 目标当前只支持 `langgraph-py`。
- LangGraph 编译器支持 linear、conditional、loop、fanout；`join` edge 尚未实现。
- 本地 `run` 当前只允许 linear、conditional，并支持 `human_gate` interrupt/resume；loop/fanout 会被运行时目标能力检查拒绝。
- Mermaid 渲染用于快速查看结构，不是完整执行语义说明。

## 开发

```bash
uv run pytest
```

项目结构：

```text
src/prompt2langgraph/
  adapters/       输入适配与 skill 静态分析
  compiler/       Workflow IR 到 LangGraph 的编译
  diagnostics/    诊断模型和错误码
  ir/             IR 模型、规范化和 lockfile
  registry/       节点与 executor 注册表
  runtime/        本地运行器和事件模型
  validate/       图、类型和安全校验
  visualization/  Mermaid 渲染
tests/            单元测试与 JSON 夹具
```


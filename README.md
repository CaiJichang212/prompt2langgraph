# prompt2langgraph

`prompt2langgraph` 是一个工具包，用于把经过校验的 Workflow IR 或简化 JSON plan 编译为确定性的 LangGraph Python 工作流，并提供本地校验、编译产物生成、运行、恢复和 Mermaid 渲染能力。

项目当前面向本地、可重复、可测试的工作流编排场景。内置 mock executor 用于确定性测试；通过 `ExecutorType.LLM` 和 `ExecutorType.PYTHON_CALLABLE` 可接入真实 LLM 模型调用和受控 Tool 执行，但需显式启用策略开关（`external_call=True`、`allowed_models`、`allowed_tool_refs`）。

## 安装

```bash
uv sync
```

## 核心能力

- 接受三类输入：规范化 `Workflow IR`、简化 `JSON plan`，以及通过 Prompt 文本由 LLM 生成简化 JSON plan
- Prompt 计划生成基于 `langchain_openai`，优先兼容 Qwen、vLLM 暴露的 OpenAI-style API 及其他第三方兼容接口
- Prompt 配置默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，CLI 参数可覆盖
- 对 `SKILL.md` 技能目录做 Skill → `WorkflowSpec` 的 LLM 驱动 alpha 转换（可诊断、可人工修正，不保证任意 Skill 一次成功），不执行脚本，不自动注册 tool callable
- 校验工作流的 schema、registry 绑定、图结构、类型绑定和安全约束
- 编译为 `langgraph-py` 目标，并输出 lockfile、IR、manifest、compile report、Mermaid 与生成代码骨架
- 本地运行工作流，输出结构化事件、诊断、metrics、thread id 和 interrupt 信息
- 支持基于 LangGraph interrupt 的 `resume` 流程，可从编译产物目录继续执行
- 支持 Mermaid 图渲染，既可直接渲染源工作流，也可渲染已编译 bundle

## 当前支持范围

### 边类型

- `linear`
- `conditional`
- `loop`
- `fanout`

`join` 是 IR 和 Mermaid 可识别的 edge kind，但当前 LangGraph compiler / runner 不支持执行 `join` edge。

### 内置节点 / executor

- `llm` / `builtin.echo_llm`（确定性 mock）或 `llm.<model_id>`（真实 LLM，如 `llm.qwen-plus`）
- `tool` / `ExecutorType.PYTHON_CALLABLE`（受控 Tool 执行，需 `ToolCallableRegistry` 注册）
- `retriever` / `builtin.mock_retriever`
- `transform` / `builtin.identity_transform`
- `router` / `builtin.route`
- `human_gate` / `builtin.human_gate`
- `join` / `builtin.join`

说明：

- `builtin.echo_llm` 是确定性的 mock executor，只按模板拼接输入，不会调用真实 LLM
- `llm.qwen-plus` 是真实 LLM executor（`ExecutorType.LLM`，`dynamic=True`），需 `external_call=True` + `allowed_models=["qwen-plus"]` 策略启用
- `ExecutorType.PYTHON_CALLABLE` 的 tool 节点只能执行预注册、受信任的纯 Python callable（通过 `ToolCallableRegistry`），需 `allowed_tool_refs` 白名单授权
- `builtin.mock_retriever` 返回 `mock://...` artifact reference，不访问网络
- `human_gate` 通过 LangGraph interrupt 触发等待态，需要后续 `resume`
- `side_effect` 节点类型已在 registry 中定义，但是否可通过校验取决于工作流安全策略

## 快速开始

### 1. 运行测试

```bash
uv run pytest
```

### 2. 校验工作流

```bash
uv run pt2lg validate tests/fixtures/linear_llm.json --json
```

### 3. 编译工作流

```bash
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
```

成功后会生成目录 `build/linear_llm/`，其中包含：

- `workflow.ir.json`
- `workflow.lock.json`
- `manifest.json`
- `compile_report.json`
- `graph.mmd`
- `generated/state.py`
- `generated/nodes.py`
- `generated/graph.py`

### 4. 运行工作流

直接运行源工作流：

```bash
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
```

也可以运行编译后的 lockfile：

```bash
uv run pt2lg run build/linear_llm/workflow.lock.json --input '{"question":"hello"}' --json
```

`--input` 同时支持：

- 内联 JSON 对象字符串
- 指向 JSON 文件的路径

### 5. 通过 Prompt 生成工作流

使用 `plan` 命令，通过自然语言 Prompt 让 LLM 生成简化 JSON plan：

```bash
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --json
```

Prompt 计划生成依赖外部 LLM，默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`。也可通过 CLI 参数覆盖：

```bash
uv run pt2lg plan --prompt "Build a workflow" --model qwen-plus --base-url https://example.com/v1 --api-key your-key --json
```

也可基于 Skill 目录进行 Skill → WorkflowSpec 转换：

```bash
uv run pt2lg plan --skill-dir path/to/skill --param key=value --json
```

`--param` 支持传入额外参数替换 Skill 中的占位符。

生成的简化 JSON plan 可继续进入 `validate`、`compile`、`run` 等现有链路。

说明：Prompt 只生成简化 JSON plan。`builtin.echo_llm` 仍是确定性 mock executor。如需运行时 `llm` 节点调用真实模型，需在 workflow policies 中设置 `external_call=True` 和 `allowed_models`。

### 6. 渲染 Mermaid 图

渲染源工作流：

```bash
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
```

渲染编译后的 bundle：

```bash
uv run pt2lg graph build/linear_llm/workflow.lock.json --format mermaid --json
```

## Resume 工作流

当工作流包含 `human_gate` 或 `side_effect` 一类会触发中断的节点时，`run` 可能返回 `waiting` 状态。此时可以使用相同的 `thread_id` 继续执行。

先编译：

```bash
uv run pt2lg compile tests/fixtures/conditional_human_gate.json --out build --json
```

首次运行，命中人工审批分支：

```bash
uv run pt2lg run build/conditional_human_gate/workflow.lock.json --input '{"question":"hello","confidence":0.5}' --json
```

继续执行（human_gate 审批）：

```bash
uv run pt2lg resume build/conditional_human_gate/workflow.lock.json --thread-id '<thread_id>' --resume '"approved"' --json
```

Side Effect 节点默认需要审批，恢复时通过 `--resume` 传入审批结果：

```bash
# 批准副作用执行
uv run pt2lg resume <bundle>/workflow.lock.json --thread-id '<thread_id>' --resume '{"decision":"approved"}' --json

# 拒绝副作用执行
uv run pt2lg resume <bundle>/workflow.lock.json --thread-id '<thread_id>' --resume '{"decision":"rejected"}' --json
```

说明：

- 等待态运行会在 bundle 目录下写入 `.pt2lg-runtime/` 本地 checkpoint（安装 `checkpoint-sqlite` 可选依赖后为 `.db` 文件，否则为 `.json` 文件）
- 旧 `.json` runtime 状态与新的 `.db` checkpoint 不互相迁移
- SQLite checkpoint 默认保留以支持后续 time travel debugging
- `--resume` 优先按 JSON 解析，因此可传 `"approved"`、`null`、对象或数组
- 若工作流内容变化，旧 `thread_id` 不会被错误复用

## Python API

常用入口从包根导出：

```python
import json
from pathlib import Path

import prompt2langgraph as pt2lg

workflow = pt2lg.WorkflowSpec.model_validate(
    json.loads(Path("tests/fixtures/linear_llm.json").read_text(encoding="utf-8"))
)

report = pt2lg.validate_workflow(workflow)
result = pt2lg.run_workflow(workflow, {"question": "hello"})
```

可用导出包括：

- `WorkflowSpec`
- `ValidationReport`
- `Diagnostic`
- `DiagnosticLocation`
- `PromptPlanRequest`
- `PromptPlanResult`
- `validate_workflow`
- `run_workflow`
- `compile_workflow`
- `plan_prompt_to_workflow_spec`
- `CompileResult`

编译产物也可以通过 public API 生成：

```python
compile_result = pt2lg.compile_workflow(workflow, out_dir="build")

assert compile_result.ok is True
print(compile_result.output_dir)
```

`run_workflow()` 支持 `checkpointer` 注入以实现状态持久化和恢复：

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
result = pt2lg.run_workflow(workflow, {"question": "hello"}, checkpointer=checkpointer)
```

更底层的源码入口：

- `prompt2langgraph.adapters.IRAdapter`
- `prompt2langgraph.adapters.JSONPlanAdapter`
- `prompt2langgraph.adapters.json_plan.json_plan_to_workflow_spec`
- `prompt2langgraph.adapters.skill_dir.analyze_skill_dir`
- `prompt2langgraph.compiler.langgraph_py.compile_workflow_to_graph`
- `prompt2langgraph.runtime.artifacts.load_bundle_workflow`
- `prompt2langgraph.runtime.artifacts.load_bundle_mermaid`

### Prompt API

通过 Prompt 生成 `WorkflowSpec` 并进入现有链路：

```python
import prompt2langgraph as pt2lg

request = pt2lg.PromptPlanRequest(prompt="Build a workflow that answers a question")
workflow = pt2lg.plan_prompt_to_workflow_spec(request)

report = pt2lg.validate_workflow(workflow)
assert report.ok is True
```

Prompt 计划生成默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，也可在 `PromptPlanRequest` 中覆盖：

```python
request = pt2lg.PromptPlanRequest(
    prompt="Build a workflow",
    model="qwen-plus",
    base_url="https://example.com/v1",
    api_key="your-key",
)
```

## 输入格式

### Workflow IR

规范化 Workflow IR 需要显式提供：

- `schema_version`
- `workflow_id`
- `name`
- `entrypoint`
- `state_schema`
- `nodes`
- `edges`

最小示例：

```json
{
  "schema_version": "0.1",
  "workflow_id": "linear_llm",
  "name": "Linear LLM",
  "entrypoint": "compose",
  "state_schema": {
    "input": {
      "question": {
        "type": "string"
      }
    },
    "output": {
      "answer": {
        "type": "string"
      }
    },
    "channels": {
      "question": {
        "type": "string"
      },
      "answer": {
        "type": "string"
      }
    },
    "private": {},
    "reducers": {}
  },
  "nodes": [
    {
      "id": "compose",
      "kind": "llm",
      "executor": {
        "ref": "builtin.echo_llm",
        "type": "builtin"
      },
      "inputs": {
        "question": {
          "state_key": "question"
        }
      },
      "outputs": {
        "answer": {
          "state_key": "answer"
        }
      },
      "params": {
        "template": "Answer: {question}"
      }
    }
  ],
  "edges": [],
  "policies": {},
  "metadata": {}
}
```

### 简化 JSON plan

简化 JSON plan 会在加载时被转换为标准 `WorkflowSpec`。其特点是：

- 用 `name` 自动派生 `workflow_id`
- `entrypoint` 可省略，若图中只有一个根节点会自动推断
- 节点中的 `executor` 直接写字符串引用
- 边使用 `from` / `to` 字段，可选 `kind`
- `inputs` / `outputs` 可写简单类型或完整 `TypeSpec`

示例：

```json
{
  "name": "Simple Plan",
  "inputs": {
    "question": "string"
  },
  "outputs": {
    "answer": "string"
  },
  "nodes": [
    {
      "id": "compose",
      "kind": "llm",
      "executor": "builtin.echo_llm",
      "params": {
        "template": "Answer: {question}"
      }
    }
  ],
  "edges": []
}
```

简化 plan 的适配规则：

- `name` 会被 slug 化为 `workflow_id`
- 未提供 `entrypoint` 时，会从唯一根节点推断
- `executor` 字段写 executor ref 字符串，例如 `builtin.echo_llm`
- 边使用 `from` / `to` 字段，或 `source` / `target` 别名，默认 `kind` 为 `linear`
- `conditional` 边可以携带 `condition.expr` 和 `condition.routes`
- `loop` 边可以携带 `loop_guard.max_iterations`
- `fanout` 边可以携带 `map.items_state_key`、`map.item_state_key` 和 `map.result_state_key`
- `inputs` / `outputs` 可写简单类型字符串或完整 `TypeSpec`
- 已注册 executor 会用于推断节点输入输出 selector 和 state channel 类型

简化 JSON plan 只覆盖常用适配边界，不是完整 Workflow IR 语义的替代表达。尤其是 fanout map-reduce 的可执行形态需要在 `state_schema.reducers` 中声明 reducer；简化 plan 当前不提供 reducers 表达，因此完整 fanout map-reduce 应直接使用 Workflow IR。

### Prompt 输入

通过自然语言 Prompt 让 LLM 生成简化 JSON plan，再经 `JSONPlanAdapter` 转为 `WorkflowSpec`。

- Prompt 计划生成依赖外部 LLM，基于 `langchain_openai`
- 优先兼容 Qwen 模型、vLLM 部署暴露的 OpenAI-style API 及其他第三方兼容接口
- 默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，CLI 参数或 `PromptPlanRequest` 字段可覆盖
- LLM 输出必须是合法 JSON 对象，否则会返回 `AdapterParseError` 诊断
- Prompt 生成的简化 JSON plan 与手动编写的简化 JSON plan 走完全相同的适配与校验链路
- 当前 Prompt 只生成简化 JSON plan，不代表 runtime `llm` 节点具备真实执行能力

配置示例（`.env`）：

```
MODEL=qwen-plus
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
API_KEY=sk-your-key
```

## 编译产物说明

`pt2lg compile` 会在输出目录下为每个工作流生成一个 bundle 子目录：

- `workflow.ir.json`：规范化后的 Workflow IR
- `workflow.lock.json`：编译目标、工作流哈希和生成文件列表
- `manifest.json`：bundle 清单
- `compile_report.json`：编译诊断与阶段耗时
- `graph.mmd`：Mermaid 流程图
- `generated/*.py`：生成的 Python 入口和元数据薄封装

其中 `workflow.lock.json` 可作为后续 `run`、`graph`、`resume` 的输入入口。

lockfile 会记录 workflow hash、registry hash、target、编译选项 hash、policy hash 和生成文件列表。读取 bundle 时会校验 lockfile 与 `workflow.ir.json` 的 workflow hash 是否一致。

`manifest.json` 会包含 deterministic policy summary 和 executor binding summary；`compile_report.json` 会包含 `compile_id`、阶段 `timings_ms`、诊断和 binding summary。Binding summary 记录 executor ref、type、capability 名称、dynamic 标记、allowed_models 和 external_call 状态，不写入真实 secret，也不写入 secret 名称。

v0.1 bundle 契约是“可复现且依赖当前 `prompt2langgraph` 库运行”，不是完全自包含的静态 LangGraph 代码包。`generated/graph.py` 会读取同一 bundle 下的 `workflow.ir.json`，再调用库内 `compile_workflow_to_graph()` 构建图；`workflow.ir.json`、lock、manifest、report 和 Mermaid 才是当前可审计契约的核心产物。

如果编译失败，`pt2lg compile` 不会生成可运行 bundle；同一输出目录下的旧 bundle 产物会被清理，目录中的无关文件会保留。

## 校验与错误输出

CLI 的 `validate`、`compile`、`run`、`graph`、`resume` 都支持 `--json` 机器可读输出。常见返回信息包括：

- `ok` 或 `status`
- `diagnostics`
- `events`
- `metrics`
- `thread_id`
- `interrupt`

校验阶段会覆盖：

- schema 校验
- registry 绑定校验
- 图结构校验
- 类型校验
- 安全策略校验

典型约束包括：

- `loop` edge 必须声明 `loop_guard.max_iterations`
- `fanout` edge 必须声明 `map`，其结果 state 必须是数组并带 reducer
- 条件表达式只能引用简单 state key 和字面量比较
- side effect 节点默认必须审批或具备幂等键，除非 workflow policy 显式允许副作用

## Mermaid 输出

`graph` 命令当前仅支持 `--format mermaid`。输出格式为 `flowchart LR`，并会把：

- `conditional` 标记为具名路由边
- `loop` 标记为 `loop`
- `fanout` 标记为 `fanout`

未显式出边的终止节点会自动连到 `END`。

## 安全与约束

- 编译器和运行时默认不调用真实 LLM、不访问网络、不执行任意脚本
- 内置 mock executor 以确定性测试为目标，便于本地回归和快照验证
- 真实 LLM 调用需显式启用：`policies.external_call=True` + `policies.allowed_models` 白名单
- 受控 Tool 执行需显式授权：`policies.allowed_tool_refs` 白名单 + `ToolCallableRegistry` 注册
  - CLI `run` 自动构造的 `tool_registry` 为空注册表，仅用于校验占位
  - 实际执行 PYTHON_CALLABLE 节点时，需通过 Python API 注入已注册 callable 的 `tool_registry`
- 策略约束在 `validate_workflow()` 阶段即被检查，运行时做防御性二次校验
- 条件表达式当前仅支持 `<state_key> <comparison> <literal>` 形式
- `comparison` 仅支持 `<`、`<=`、`>`、`>=`、`==`、`!=`
- `run` 当前支持 `linear`、`conditional`、`loop`、`fanout`、`join`（需声明 `join_sources` 和 reducer）
- `graph` 当前仅支持 `mermaid`
- `compile` 当前仅支持 `--target langgraph-py`
- CLI resume 的 `.pt2lg-runtime/` 状态文件是本地开发用的短期持久化格式（安装 `checkpoint-sqlite` 可选依赖后使用 SQLite checkpointer，路径为 `.db` 文件）。旧 `.json` 文件与新的 `.db` checkpoint 不互相迁移。
- `json_plan` 和 Workflow IR 是当前可执行输入；Prompt 输入通过 LLM 生成简化 JSON plan，再经 `JSONPlanAdapter` 转为 `WorkflowSpec`
- Prompt 计划生成依赖外部 LLM，默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`
- Prompt 只生成简化 JSON plan；运行时 `llm` 节点的真实执行需 `external_call=True` + `allowed_models`
- `skill_dir` 支持 Skill → `WorkflowSpec` 的 LLM 驱动 alpha 转换（`plan --skill-dir`），也保留静态分析能力（`analyze_skill_dir()`）
- `llm/` 顶层模块为 LLM 客户端构造共享入口，`.env` 配置同时服务于 Prompt 计划生成和运行时 LLM 执行

## 参考夹具

可直接参考 `tests/fixtures/` 中的样例：

- `linear_llm.json`
- `conditional_human_gate.json`
- `loop_with_guard.json`
- `fanout_map_reduce.json`
- `join.json`（JOIN 基于 `join_sources` + reducer 可执行）

也可以查看无效夹具理解校验边界：

- `invalid_unknown_node.json`
- `invalid_type_mismatch.json`
- `invalid_loop_without_guard.json`
- `invalid_fanout_without_reducer.json`
- `invalid_route_conflict.json`
- `invalid_join_edge.json`：JOIN 可执行，但需正确配置 `join_sources` 和 reducer

## 当前边界

- `pt2lg compile` 和 public `compile_workflow()` 已统一使用 `runtime.artifacts.compile_workflow_to_artifacts()` 生成产物。
- 当前测试基线为 `uv run pytest` 全量通过；若修改行为、产物结构或文档边界，应重新运行全量测试。
- `llm` 节点可通过 `ExecutorType.LLM`（ref 格式 `llm.<model_id>`）调用真实模型，fake provider 下可验证完整调用链路。
- `tool` 节点可通过 `ExecutorType.PYTHON_CALLABLE` 执行受信任、预注册且经 `allowed_tool_refs` 授权的纯 Python callable。
- 真实 executor 和 mock executor 可通过 executor ref 区分（`ref="builtin.echo_llm"` = mock，`ref="llm.qwen-plus"` = real），mock 行为完全兼容。
- `collect_metrics=True` 时，`RunResult.external_calls` 中可获取成功和失败调用的 `ExternalCallRecord`。
- CLI `run` 命令能根据 workflow 节点类型自动构造 `model_client` 和 `tool_registry`。
- 非 builtin executor type、真实 secret ref 校验、capability 授权、provider/model/tool 可用性检查属于后续治理能力；v0.1 runner 不会据此隐式调用外部资源。

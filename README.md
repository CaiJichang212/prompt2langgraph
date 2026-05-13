# prompt2langgraph

`prompt2langgraph` 是一个 Python 3.11+ 工具包，用于把经过校验的 Workflow IR 或简化 JSON plan 编译为确定性的 LangGraph Python 工作流，并提供本地校验、编译、运行、恢复和 Mermaid 渲染能力。

项目当前面向本地、可重复、可测试的工作流编排场景。内置 executor 仅用于确定性测试，不会隐式调用外部 LLM、网络服务或任意 shell 命令。

## 安装

```bash
uv sync
```

## 核心能力

- 接受两类输入：规范化 `Workflow IR` 和简化 `JSON plan`
- 校验工作流的 schema、图结构、类型绑定和安全约束
- 编译为 `langgraph-py` 目标，并输出 lockfile、IR、Mermaid 与生成代码
- 本地运行工作流，输出结构化事件、诊断和 metrics
- 支持基于中断的 `resume` 流程，可从编译产物目录继续执行
- 支持 Mermaid 图渲染，既可直接渲染源工作流，也可渲染已编译 bundle

## 当前支持范围

### 边类型

- `linear`
- `conditional`
- `loop`
- `fanout`

### 内置节点 / executor

- `llm` / `builtin.echo_llm`
- `retriever` / `builtin.mock_retriever`
- `transform` / `builtin.identity_transform`
- `router` / `builtin.route`
- `human_gate` / `builtin.human_gate`
- `join` / `builtin.join`

说明：

- `builtin.echo_llm` 是确定性的 mock executor，只按模板拼接输入，不会调用真实 LLM
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

### 5. 渲染 Mermaid 图

渲染源工作流：

```bash
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
```

渲染编译后的 bundle：

```bash
uv run pt2lg graph build/linear_llm/workflow.lock.json --format mermaid --json
```

## Resume 工作流

当工作流包含 `human_gate` 一类会触发中断的节点时，`run` 可能返回 `waiting` 状态。此时可以使用相同的 `thread_id` 继续执行。

先编译：

```bash
uv run pt2lg compile tests/fixtures/conditional_human_gate.json --out build --json
```

首次运行，命中人工审批分支：

```bash
uv run pt2lg run build/conditional_human_gate/workflow.lock.json --input '{"question":"hello","confidence":0.5}' --json
```

继续执行：

```bash
uv run pt2lg resume build/conditional_human_gate/workflow.lock.json --thread-id '<thread_id>' --resume '"approved"' --json
```

说明：

- 等待态运行会在 bundle 目录下写入 `.pt2lg-runtime/` 本地状态文件
- `resume` 成功后会清理对应的本地状态文件
- `--resume` 优先按 JSON 解析，因此可传 `"approved"`、`null`、对象或数组
- 若工作流内容变化，旧 `thread_id` 不会被错误复用

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
- 边使用 `from` / `to` 字段
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

## 编译产物说明

`pt2lg compile` 会在输出目录下为每个工作流生成一个 bundle 子目录：

- `workflow.ir.json`：规范化后的 Workflow IR
- `workflow.lock.json`：编译目标、工作流哈希和生成文件列表
- `manifest.json`：bundle 清单
- `compile_report.json`：编译诊断与阶段耗时
- `graph.mmd`：Mermaid 流程图
- `generated/*.py`：生成的 Python 代码骨架

其中 `workflow.lock.json` 可作为后续 `run`、`graph`、`resume` 的输入入口。

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

## Mermaid 输出

`graph` 命令当前仅支持 `--format mermaid`。输出格式为 `flowchart LR`，并会把：

- `conditional` 标记为具名路由边
- `loop` 标记为 `loop`
- `fanout` 标记为 `fanout`

未显式出边的终止节点会自动连到 `END`。

## 安全与约束

- 编译器和运行时默认不调用真实 LLM、不访问网络、不执行任意脚本
- 内置 executor 以确定性测试为目标，便于本地回归和快照验证
- 条件表达式当前仅支持 `<state_key> <comparison> <literal>` 形式
- `comparison` 仅支持 `<`、`<=`、`>`、`>=`、`==`、`!=`
- `graph` 当前仅支持 `mermaid`
- `compile` 当前仅支持 `--target langgraph-py`

## 参考夹具

可直接参考 `tests/fixtures/` 中的样例：

- `linear_llm.json`
- `conditional_human_gate.json`
- `loop_with_guard.json`
- `fanout_map_reduce.json`

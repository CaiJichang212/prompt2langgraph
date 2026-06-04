# prompt2langgraph v0.3 第三期实施计划文档

## 1. 文档目的

本文档用于定义 `prompt2langgraph` v0.3 第三期的工程实施计划，作为后续代码任务拆分、测试验收和文档同步的依据。

本文档是项目级实施计划，不是 agent 执行脚本。它描述目标、行为契约、模块任务、验收标准和风险边界；只在必要位置给出“最小补丁片段”和“可直接运行的测试片段”。若后续需要交给 coding agent 逐步执行，应基于本文档另行生成细粒度 agent 执行计划，并放在 `docs/superpowers/plans/` 下。

---

## 2. 阶段定位

v0.3 第三期对应《prompt2langgraph v0.3 开发计划文档》第 10 节的 **可执行与治理闭环**。

第一期已经把简化 JSON plan 与当前 `WorkflowSpec` 语义对齐。第二期已经把 Prompt/Skill planning 推进为可解析、可诊断、可修复、可 compile smoke 的结构化链路。第三期的重点不是扩展新的图语义，而是兑现已经暴露在 IR、public API、CLI 和文档中的运行语义：

- CLI 可加载受控 Python tool module，并运行 `ExecutorType.PYTHON_CALLABLE` tool workflow。
- Skill planning 结果能声明 required tool refs、allowed tool refs、registered tool refs 和风险提示。
- `RetryPolicy.max_attempts` 对动态 LLM/tool wrapper 生效。
- side-effect approval 与 idempotency 绑定，resume 后不重复执行同一幂等键。
- runtime metrics 与 audit 输出最小但稳定的运行摘要。
- generated bundle 支持最小 runtime config 的 `build_graph(config)` 和 `invoke(input, config)`。
- `ExecutorType.LANGCHAIN_TOOL` 明确保持 reserved/experimental，不纳入 v0.3 可执行能力。

---

## 3. 当前源码事实

本节是后续代码片段和任务拆分的依据。执行第三期前应重新核对这些事实是否仍成立。

- `src/prompt2langgraph/registry/tool_executor.py` 已提供 `ToolCallableRegistry.register(ref, callable)`、`has()`、`get()`、`refs()`；`ToolExecutor` 可执行已注册 callable，并把未注册、超时、执行异常统一包装为 `ExecutorError(E_SEC_015, ...)`。
- `src/prompt2langgraph/runtime/runner.py` 的 `run_workflow()` 已接受 `model_client`、`tool_registry`、`checkpointer`，但没有 `runtime_config`、`audit_sink` 或 retry 执行语义。
- `src/prompt2langgraph/cli.py` 的 `_build_runtime_clients(workflow)` 当前会为 `PYTHON_CALLABLE` 节点创建空 `ToolCallableRegistry()`，但 CLI `run` / `resume` 没有 `--tool-module`，也没有向 `run_workflow()` 传入自定义 `ExecutorRegistry`。
- `validate_workflow()` 默认使用 `builtin_executor_registry()`，且 `_check_registries()` 要求每个 `node.executor.ref` 必须存在于 `ExecutorRegistry`。因此仅加载 `ToolCallableRegistry` 不足以运行任意 `python_callable` ref；第三期必须同步合成动态 `ExecutorDefinition(type=PYTHON_CALLABLE, dynamic=True)`。
- `JSONPlanAdapter(executors=...)` 已支持注入 executor registry。若 CLI 要直接运行包含自定义 tool ref 的简化 JSON plan，加载 workflow source 时也要传入该 registry。
- `src/prompt2langgraph/ir/models.py` 已有 `RetryPolicy(max_attempts: int = 1)`，`NodeSpec.retry` 和 `NodeSpec.timeout_s`。
- `src/prompt2langgraph/runtime/events.py` 已有 `RunMetrics.retry_count`、`tool_call_count`、`call_count`、`total_latency_ms`，以及 `ExternalCallRecord.latency_ms`、`token_count`、`status`、`error_code`。
- `src/prompt2langgraph/compiler/langgraph_py.py` 当前在 `_invoke_executor()` 中分发动态 LLM/tool，但没有 retry wrapper，也没有记录外部调用耗时。
- `src/prompt2langgraph/registry/side_effect_executor.py` 已把 `security.idempotency_key` 放入 interrupt payload；源码注释明确当前还没有 dedup。
- `src/prompt2langgraph/compiler/codegen.py` 生成的 `generated/graph.py` 当前只有无参 `build_graph()`、`compile_graph()` 和 `invoke_graph(input_payload=None)`，并固定使用 `builtin_executor_registry()`。
- `src/prompt2langgraph/ir/lockfile.py` / `runtime.artifacts` 已生成 manifest、compile report 和 binding summary，但 manifest 还没有面向运行期依赖的 tool refs、checkpoint 需求和 runtime config 摘要。
- `PlanningPipelineResult` 当前包含 `diagnostics`、`stages`、`workflow`，但没有结构化 tool readiness 摘要。

---

## 4. 阶段目标

第三期目标是：

**让 Prompt/Skill 生成出的 workflow 不只停留在可编译图，而是能够在明确授权、安全边界和最小观测机制下受控执行。**

完成后，用户应能通过 CLI 加载一个受信任 fake tool module，运行使用 `PYTHON_CALLABLE` executor 的 workflow，并在失败、重试、审批、审计和 bundle 调用场景中获得稳定诊断和可回归测试结果。

---

## 5. 纳入范围

第三期纳入以下范围。

1. **3A：CLI tool registry 加载**
   - 新增 `--tool-module <module>`，用于 `pt2lg run` 和 `pt2lg resume`。
   - module 必须暴露 `register_tools(registry)`。
   - 注册出的 tool refs 同时进入 `ToolCallableRegistry` 和运行期 `ExecutorRegistry`。
   - 默认 CLI 不加载任何 tool。
   - 不支持任意 shell 命令执行，不支持 `--tool-registry <json>`。

2. **3A：Skill required tool refs**
   - planning result 增加 tool readiness 摘要。
   - 摘要列出 workflow 使用的 tool executor refs、policy 允许的 refs、已注册 refs、缺失 refs、未授权 refs。
   - 高风险 Skill 诊断继续来自 `analyze_skill_dir()`，并补充 approval / side_effect 建议。

3. **3B：RetryPolicy 最小执行语义**
   - `RetryPolicy.max_attempts` 对动态 LLM 和 Python callable tool 生效。
   - LLM timeout / API transient error、tool timeout 可重试。
   - 未授权、未注册、schema mismatch、side-effect 拒绝不默认重试。
   - metrics 记录 retry count 和最终状态。

4. **3B：Side-effect idempotency 与最小 audit**
   - 以 `workflow_id + thread_id + node_id + idempotency_key` 作为 v0.3 幂等作用域。
   - 已批准且已执行的幂等键在 resume 后不重复执行。
   - 增加 `.pt2lg-runtime/audit.log.jsonl` 或可注入 audit sink。
   - audit 只记录最小字段，不记录 secret、完整 input payload、完整 model response 或敏感 tool 参数。

5. **3B：Runtime metrics 与 external calls**
   - 记录 per-node latency、external call latency、retry count、tool call count、LLM token usage 摘要和 error category。
   - 不要求一次覆盖所有 provider 的 token usage 格式；先做可选字段标准化。

6. **3C：最小 runtime config bundle**
   - generated `graph.py` 暴露 `RuntimeConfig`、`build_graph(config=None)`、`invoke(input_payload, config=None)`。
   - config 支持注入 `model_client`、`tool_registry`、`checkpointer`、`policy_override`。
   - manifest 输出运行依赖清单，包括模型、tool refs、checkpoint 需求和 policy 摘要。
   - 保留旧的 `build_graph()`、`compile_graph()`、`invoke_graph()` 兼容入口。

7. **3C：Benchmark 与工程门禁**
   - 增加离线 benchmark 命令或测试说明。
   - 默认不访问网络。
   - 覆盖 10/100 节点线性图编译、fanout/join compile smoke、prompt/skill corpus offline success rate、tool run smoke、side-effect interrupt/resume smoke、bundle load/invoke smoke。

8. **`LANGCHAIN_TOOL` reserved/experimental**
   - README、AGENTS、CLAUDE、public docs 和 validator diagnostics 明确该 executor type 不作为 v0.3 可执行能力。
   - 不实现 LangChain Tool 端到端执行、schema 映射或安全策略。

---

## 6. 排除范围

第三期不纳入以下内容：

- 任意 shell tool、subprocess sandbox、网络隔离、容器隔离。
- `--tool-registry <json>` 配置入口。
- 从 Skill scripts 自动生成或自动注册 tool callable。
- LangChain Tool 端到端执行。
- Agent / tool-calling loop 通用框架。
- MCP、Web UI、多后端编译、YAML、子图。
- 独立部署型 bundle、secret manager 集成、远程审计平台。
- 把 Prompt/Skill planning 改成直接运行 workflow。

---

## 7. 行为契约

### 7.1 CLI tool module

`--tool-module <module>` 是第三期唯一正式 CLI tool 加载入口。

行为要求：

- `pt2lg run <workflow> --tool-module tests.fake_tools_module --input input.json --json` 加载指定 module。
- `pt2lg resume <bundle>/workflow.lock.json --tool-module tests.fake_tools_module --thread-id ... --resume ... --json` 使用相同加载逻辑。
- module 名称按 Python import module 处理，不把文件路径、shell 字符串或 JSON 配置当作执行入口。
- module 必须暴露 `register_tools(registry)`；缺失时报稳定 diagnostic。
- `register_tools()` 只能接收 `ToolCallableRegistry` 并调用 `registry.register(ref, callable)`。
- loader 从 `registry.refs()` 合成动态 `ExecutorDefinition(ref=ref, type=PYTHON_CALLABLE, dynamic=True)`，并与 builtin executor registry 合并。
- `validate_workflow()`、`JSONPlanAdapter()`、`compile_workflow_to_graph()`、`run_workflow()` 必须使用同一个合成 executor registry。
- CLI 加载顺序必须固定为：`tool_module -> ToolCallableRegistry -> ExecutorRegistry -> workflow parse/load -> validate -> run/resume`。
- 简化 JSON plan 输入也必须走同一加载顺序，避免自定义 tool ref 在 adapter 阶段被降级为 `ExecutorType.BUILTIN`。
- 默认不传 `--tool-module` 时，不加载任何外部 tool；包含 `PYTHON_CALLABLE` 节点的 workflow 仍会因未注册或未绑定返回稳定失败。

最小补丁片段如下。

依赖的当前源码事实：`ToolCallableRegistry.refs()` 已返回排序后的 ref 列表；`ExecutorDefinition` 已支持 `dynamic=True`；`run_workflow()` 已接受 `executors` 参数。

```python
from prompt2langgraph.ir.models import ExecutorType
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry


def _executor_registry_with_tools(tool_registry: ToolCallableRegistry) -> ExecutorRegistry:
    registry = builtin_executor_registry()
    for ref in tool_registry.refs():
        registry.register(
            ExecutorDefinition(ref=ref, type=ExecutorType.PYTHON_CALLABLE, dynamic=True)
        )
    return registry
```

### 7.2 Tool diagnostics

tool workflow 必须具备稳定失败面。

行为要求：

- 未授权 tool ref：`E_SEC_015`，message 包含 ref 和 `allowed_tool_refs`。
- 未注册 tool ref：`E_SEC_015`，message 包含 ref 和 `ToolCallableRegistry`。
- tool timeout：`E_SEC_015`，message 包含 timeout 秒数。
- tool callable 抛异常：`E_SEC_015`，hint 包含异常摘要，不包含完整敏感 payload。
- tool 输出缺少声明 output：`E_RUNTIME_010`，message 包含 node id 和缺少的 output 名。
- CLI JSON 输出统一为 `{"status": "failed", "diagnostics": [...]}`，不输出 traceback。

说明：schema mismatch 在当前代码中由 `_node_wrapper()` 检查 executor omitted output 后抛 `RuntimeError`，runner 会包装为 `E_RUNTIME_010`。第三期不新增复杂 schema validator，只要求 message 稳定且有回归测试。

### 7.3 Skill tool readiness

结构化 planning result 增加 `tool_readiness` 字段。

建议模型：

依赖的当前源码事实：`PlanningPipelineResult` 是 Pydantic `BaseModel`；`WorkflowSpec.nodes` 可直接遍历；`workflow.policies.allowed_tool_refs` 已存在；`ToolCallableRegistry.refs()` 已存在。

```python
class ToolReadiness(BaseModel):
    required_tool_refs: list[str] = Field(default_factory=list)
    allowed_tool_refs: list[str] = Field(default_factory=list)
    registered_tool_refs: list[str] = Field(default_factory=list)
    missing_tool_refs: list[str] = Field(default_factory=list)
    unauthorized_tool_refs: list[str] = Field(default_factory=list)
```

行为要求：

- `required_tool_refs` 只统计 `node.executor.type is ExecutorType.PYTHON_CALLABLE` 的 refs。
- `allowed_tool_refs` 来自 `workflow.policies.allowed_tool_refs`。
- `registered_tool_refs` 来自注入的 `ToolCallableRegistry.refs()`；未注入时为空列表。
- `missing_tool_refs = required - registered`。
- `unauthorized_tool_refs = required - allowed`。
- 该字段不替代 validator；validator 仍是安全策略的最终判定入口。
- CLI `pt2lg plan --skill-dir ... --json` 输出中应包含该摘要。

### 7.4 RetryPolicy

`NodeSpec.retry.max_attempts` 在 v0.3 第三期只对动态 LLM/tool wrapper 生效。

行为要求：

- 缺省或 `max_attempts=1` 时保持现有单次调用行为。
- `max_attempts=N` 时总尝试次数为 N，不是额外重试 N 次。
- 可重试错误：
  - LLM `TimeoutError` 包装出的 `E_LLM_001`。
  - LLM API transient error，可先保守覆盖 `E_LLM_002` 中 timeout、5xx、rate limit 关键字。
  - Tool timeout，即 `ToolExecutor` 包装的 `E_SEC_015` 且 message 包含 `timed out`。
- 不可重试错误：
  - `E_SEC_013`、`E_SEC_014`、`E_SEC_015` 的未授权或未注册 tool。
  - `E_LLM_003` 输入消息格式错误。
  - `E_SIDE_008` side-effect 拒绝或缺少审批策略。
  - executor omitted output / schema mismatch。
- 每次失败尝试不向用户输出完整 payload。
- `RunMetrics.retry_count` 记录所有节点累计的重试次数，即第二次及以后尝试的数量。
- retry 指标必须有明确数据通道：每次真实 LLM/tool 调用尝试都产生一条 `ExternalCallRecord`；第三期可扩展该模型，增加 `attempt_index: int = 1` 和 `is_retry: bool = False`。
- `RunMetrics.call_count` 继续等于 external call 尝试总数；`RunMetrics.retry_count` 等于 `is_retry=True` 的记录数；`RunMetrics.tool_call_count` 统计 tool 类型 external call 尝试数。

最小补丁片段如下。

依赖的当前源码事实：`_invoke_executor()` 是动态 LLM/tool 的集中分发点；`NodeSpec.retry` 已存在。

```python
def _max_attempts_for(node: NodeSpec) -> int:
    return node.retry.max_attempts if node.retry is not None else 1


def _is_retryable_executor_error(exc: ExecutorError) -> bool:
    if exc.code == E_LLM_001:
        return True
    if exc.code == E_LLM_002:
        text = f"{exc.message} {exc.hint or ''}".lower()
        return any(marker in text for marker in ("timeout", "5xx", "rate limit", "temporar"))
    if exc.code == E_SEC_015:
        return "timed out" in exc.message.lower()
    return False
```

### 7.5 Side-effect idempotency

第三期不引入真实外部副作用沙箱，只保证审批恢复场景下的最小幂等。

行为要求：

- 幂等 key 作用域为 `workflow_id + thread_id + node_id + idempotency_key`。
- 只有审批通过并且实际 executor 成功后，才记录该 key 为 executed。
- replay、checkpoint 恢复或重复进入同一已批准 side-effect 节点时，如果遇到已 executed 的同一 key，不再执行 executor。
- skipped-by-idempotency 应记录 node event 和 audit event。
- 对没有 `security.idempotency_key` 的 side-effect，不做 dedup，只保留现有 approval 行为。
- idempotency record 必须独立于 pending interrupt 生命周期；当前 runner 成功后会清理 pending thread，因此不得把“重复 resume 同一 thread_id”作为唯一验收方式。
- 外部 checkpointer 存在时优先依赖可恢复 state 或等价 runtime store；没有外部 checkpointer 时可落到 `.pt2lg-runtime` 本地状态文件。

实现建议：

- 在 `runtime/runner.py` 新增轻量 `RuntimeStateStore` 或私有 helper，负责读写 executed idempotency keys。
- 在 compiler node wrapper 的 side-effect 分支中，通过注入 callback 查询和记录幂等状态。
- 避免把该状态写入用户声明的 output channel；使用内部 private key 或 runner 管理的 runtime state。

### 7.6 Audit

第三期 audit 是本地最小 JSONL，不是审计平台。

最小字段：

- `run_id`
- `thread_id`
- `workflow_id`
- `node_id`
- `event_type`
- `status`
- `latency_ms`
- `error_code`
- `timestamp`

行为要求：

- 默认 CLI 对 bundle 运行写入 `<bundle>/.pt2lg-runtime/audit.log.jsonl`。
- 直接运行源文件时，默认写入当前工作目录下 `.pt2lg-runtime/audit.log.jsonl`；不得默认写入 `tests/fixtures/` 或源文件相邻目录。
- 后续可增加显式 `--runtime-dir` 或 `--audit-dir` 覆盖路径；v0.3 第三期不要求完整配置系统。
- Python API 可注入 `audit_sink`。
- audit 不记录完整 `input_payload`、完整 model response、API key、secret 名称或敏感 tool 参数。
- JSONL 每行是单个 JSON object，便于后续追加和 grep。

### 7.7 Metrics

metrics 只做最小可观测摘要。

行为要求：

- `RunMetrics.duration_ms` 保持总运行耗时。
- `RunMetrics.call_count` 继续表示 external call 总数。
- `RunMetrics.total_latency_ms` 汇总 external call latency。
- `RunMetrics.retry_count` 汇总所有重试次数。
- `RunMetrics.tool_call_count` 统计成功或失败的 tool 调用尝试次数。
- `ExternalCallRecord.latency_ms` 在 LLM/tool 动态调用后填充。
- `ExternalCallRecord.token_count` 从常见 response metadata 中尽量提取；取不到时为 `None`。
- error category 可先使用 `ExternalCallRecord.error_code` 和 diagnostic code，不新增复杂枚举。

### 7.8 Runtime config bundle

generated bundle 应从固定 builtin registry 过渡到可配置运行入口。

行为要求：

- `generated/graph.py` 新增 `RuntimeConfig`。
- `build_graph(config=None)` 使用 config 中的 `executor_registry`、`model_client`、`tool_registry`、`checkpointer`。
- `invoke(input_payload, config=None)` 返回 graph invocation state。
- `compile_workflow_to_artifacts()` 需要支持注入 `executor_registry`，否则 dynamic tool workflow 无法生成可用 manifest 和 golden bundle。
- 若 CLI 要验收 dynamic tool bundle，应同步提供 `pt2lg compile --tool-module <module>`，并在 compile 阶段使用合成 executor registry。
- 保留旧入口：
  - `compile_graph()` 继续调用 `build_graph()`。
  - `invoke_graph(input_payload=None)` 继续可用。
- 不在 generated code 中写入 secret 或 secret 名称。
- manifest 增加 runtime requirements 摘要。

最小补丁片段如下。

依赖的当前源码事实：`codegen._write_graph()` 当前输出的是静态字符串；`compile_workflow_to_graph()` 已支持 `model_client`、`tool_registry`、`checkpointer`。

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeConfig:
    executor_registry: Any | None = None
    model_client: Any | None = None
    tool_registry: Any | None = None
    checkpointer: Any | None = None
    policy_override: Any | None = None


def build_graph(config: RuntimeConfig | None = None):
    selected = config or RuntimeConfig()
    workflow = load_workflow()
    return compile_workflow_to_graph(
        workflow,
        selected.executor_registry or builtin_executor_registry(),
        policies=selected.policy_override or workflow.policies,
        model_client=selected.model_client,
        tool_registry=selected.tool_registry,
        checkpointer=selected.checkpointer,
    )
```

### 7.9 `LANGCHAIN_TOOL`

`ExecutorType.LANGCHAIN_TOOL` 在 v0.3 第三期仍是 reserved/experimental。

行为要求：

- README、AGENTS、CLAUDE、开发计划和实施计划均不得宣传其可执行。
- validator 对 `LANGCHAIN_TOOL` 节点应直接拒绝执行，使用 `E_SEC_016` 错误。
- message 应为 `ExecutorType.LANGCHAIN_TOOL is not executable in v0.3`。
- warning 不应由 `check_tool_refs()` 产生；该函数继续只检查 `ExecutorType.PYTHON_CALLABLE`，避免与现有安全测试语义冲突。
- `JSONPlanAdapter`、Skill prompt 和 Prompt planner 可保留该枚举存在说明，但必须标注不作为 v0.3 可执行能力。
- 真正的 LangChain Tool schema 映射和安全策略进入 v0.5+。

---

## 8. 模块任务

### 8.1 CLI tool module loader

涉及文件：

- `src/prompt2langgraph/cli.py`
- `src/prompt2langgraph/registry/tool_executor.py`
- `tests/test_cli.py` 或新增 `tests/test_cli_tool_module.py`
- `tests/fake_tools.py`

实施内容：

- 新增 `_load_tool_modules(module_names: list[str]) -> ToolCallableRegistry`。
- 新增 `_executor_registry_with_tools(tool_registry) -> ExecutorRegistry`。
- 修改 `_build_runtime_clients()` 返回 `model_client`、`tool_registry`、`executor_registry`，或新增 `RuntimeClients` dataclass。
- `run` / `resume` 命令增加 `tool_module: list[str] = typer.Option([], "--tool-module")`。
- `tool_module` 必须在 workflow source 加载前解析并合成 executor registry。
- `_load_workflow_or_report()` 和 `_load_workflow_source_or_report()` 支持传入 executor registry，确保简化 JSON plan 也能解析自定义 tool ref。
- `run_workflow()` 调用传入 `executors=executor_registry`。

测试要求：

- 不传 `--tool-module` 时，python callable workflow 失败且 diagnostic 稳定。
- module 缺少 `register_tools` 时失败。
- module 注册 fake tool 后，CLI run 成功。
- module 注册 fake tool 后，CLI run 简化 JSON plan 成功，且 node executor type 不被降级成 `builtin`。
- resume 路径也调用相同 loader。

可直接运行的测试片段如下。放入 `tests/test_cli_tool_module.py` 后执行 `uv run pytest tests/test_cli_tool_module.py -v`。

依赖的当前源码事实：`CliRunner().invoke(app, [...])` 已用于 `tests/test_cli.py`；CLI `--input` 支持 JSON 文件路径；第三期实现后 `run` 支持 `--tool-module`。

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from prompt2langgraph.cli import app


def test_cli_run_loads_tool_module(tmp_path: Path, monkeypatch) -> None:
    module_path = tmp_path / "fake_cli_tools.py"
    module_path.write_text(
        '''
def register_tools(registry):
    def upper(inputs, params):
        return {"answer": str(inputs["question"]).upper()}
    registry.register("fake.upper", upper)
''',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    workflow_path = tmp_path / "tool_workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "workflow_id": "tool_cli_smoke",
                "name": "Tool CLI Smoke",
                "entrypoint": "call_tool",
                "state_schema": {
                    "input": {"question": {"type": "string"}},
                    "output": {"answer": {"type": "string"}},
                    "channels": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "private": {},
                    "reducers": {},
                },
                "nodes": [
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": {"ref": "fake.upper", "type": "python_callable"},
                        "inputs": {"question": {"state_key": "question"}},
                        "outputs": {"answer": {"state_key": "answer"}},
                        "params": {},
                    }
                ],
                "edges": [],
                "policies": {"allowed_tool_refs": ["fake.upper"]},
                "metadata": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}


def test_cli_run_loads_tool_module_before_json_plan_adapter(tmp_path: Path, monkeypatch) -> None:
    module_path = tmp_path / "fake_cli_tools.py"
    module_path.write_text(
        '''
def register_tools(registry):
    def upper(inputs, params):
        return {"answer": str(inputs["question"]).upper()}
    registry.register("fake.upper", upper)
''',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    plan_path = tmp_path / "tool_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "name": "Tool Plan Smoke",
                "workflow_id": "tool_plan_smoke",
                "inputs": {"question": "string"},
                "outputs": {"answer": "string"},
                "nodes": [
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": "fake.upper",
                        "inputs": {"question": "question"},
                        "outputs": {"answer": "answer"},
                    }
                ],
                "edges": [],
                "policies": {"allowed_tool_refs": ["fake.upper"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(plan_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}
```

### 8.2 Tool readiness in planning result

涉及文件：

- `src/prompt2langgraph/prompting/pipeline.py`
- `src/prompt2langgraph/prompting/skill_planner.py`
- `src/prompt2langgraph/cli.py`
- `tests/test_prompt_pipeline.py`
- `tests/test_skill_workflow.py`
- `tests/test_cli_skill.py`

实施内容：

- 新增 `ToolReadiness` Pydantic 模型。
- `PlanningPipelineResult` 增加 `tool_readiness: ToolReadiness | None = None`。
- 在 adapter 成功后计算 tool readiness；validation 失败时只要 workflow 已生成，也应返回该摘要。
- CLI JSON 输出保留该字段。
- Skill prompt 中明确 tool refs 是执行前 readiness，不是自动授权。

测试要求：

- tool workflow planning result 包含 required/allowed refs。
- 注入空 `ToolCallableRegistry()` 时 missing refs 非空。
- 注入已注册 registry 时 missing refs 为空。
- allowed_tool_refs 缺失时 unauthorized refs 非空。

### 8.3 Retry wrapper

涉及文件：

- `src/prompt2langgraph/compiler/langgraph_py.py`
- `src/prompt2langgraph/registry/llm_executor.py`
- `src/prompt2langgraph/registry/tool_executor.py`
- `src/prompt2langgraph/runtime/events.py`
- `src/prompt2langgraph/runtime/runner.py`
- `tests/test_llm_executor.py`
- `tests/test_tool_executor.py`
- `tests/test_runner.py`
- `tests/test_integration_execution.py`

实施内容：

- 在 compiler 动态 executor 分发层增加 retry wrapper。
- 只重试明确可重试错误。
- metrics sink 增加 retry attempt 信息，runner 汇总到 `RunMetrics.retry_count`。
- 成功和失败的 `ExternalCallRecord` 填充 `latency_ms`。
- tool timeout 仍使用 `node.timeout_s or policies.default_timeout_s`。

测试要求：

- fake LLM 第一次 timeout、第二次成功，`retry_count == 1`。
- fake tool 第一次 timeout、第二次成功，`retry_count == 1`。
- 未注册 tool 不重试。
- LLM 输入格式错误不重试。
- `max_attempts=1` 保持现有行为。

### 8.4 Side-effect idempotency

涉及文件：

- `src/prompt2langgraph/runtime/runner.py`
- `src/prompt2langgraph/compiler/langgraph_py.py`
- `src/prompt2langgraph/registry/side_effect_executor.py`
- `tests/test_side_effect_executor.py`
- `tests/test_runner.py`
- `tests/test_cli.py`

实施内容：

- 定义内部 idempotency record 结构。
- 将 idempotency runtime store 与 pending interrupt store 分离，避免成功后 `_clear_thread()` 清掉已执行记录。
- runner 为 compiler wrapper 注入 `idempotency_lookup` / `idempotency_record` callback。
- side-effect 审批通过且 executor 成功后记录 key。
- checkpoint replay 或重复进入同一已批准 side-effect 节点时，遇到同 key 应跳过 executor，但保留可解释 event。
- 本地 state store 和外部 checkpointer 场景都要有测试。

测试要求：

- 首次 run 进入 waiting，resume approved 执行一次。
- checkpoint replay 或通过测试 hook 重复进入同一 side-effect 节点时，不重复执行同一 idempotency key。
- rejected 不写 executed record。
- 无 idempotency_key 的 side-effect 保持原行为。

### 8.5 Audit sink

涉及文件：

- 新增 `src/prompt2langgraph/runtime/audit.py`
- `src/prompt2langgraph/runtime/runner.py`
- `src/prompt2langgraph/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`

实施内容：

- 新增 `AuditRecord` Pydantic 模型或 dataclass。
- 新增 `JsonlAuditSink(path)`。
- `run_workflow()` 增加可选 `audit_sink` 参数。
- CLI 对 bundle 运行根据 bundle 路径构造 `.pt2lg-runtime/audit.log.jsonl`。
- CLI 对源文件运行默认使用当前工作目录 `.pt2lg-runtime/audit.log.jsonl`，避免污染 fixture 目录。
- node started/finished、external call failed/succeeded、side-effect skipped-by-idempotency 记录 audit。

测试要求：

- JSONL 文件每行可 `json.loads()`。
- 字段集合包含最小字段。
- audit 中不包含输入 payload 的完整值。
- 运行失败也会记录 failed event。

### 8.6 Runtime metrics

涉及文件：

- `src/prompt2langgraph/runtime/events.py`
- `src/prompt2langgraph/runtime/runner.py`
- `src/prompt2langgraph/compiler/langgraph_py.py`
- `tests/test_runner.py`
- `tests/test_integration_execution.py`

实施内容：

- `ExternalCallRecord` 填充 `latency_ms`。
- `ExternalCallRecord` 增加 `attempt_index` 和 `is_retry`，或者新增等价内部 metric event；实现前必须二选一并固化测试。
- 从 LLM response metadata 中提取 token usage，失败时保持 `None`。
- runner 汇总 `tool_call_count`、`retry_count`。
- per-node latency 可先放入 `RunEvent.payload["latency_ms"]`，不扩大 public model。

测试要求：

- collect_metrics=True 时 successful external call 有 latency。
- tool failure 也进入 external_calls。
- retry 后 metrics.retry_count 正确。
- tool_call_count 对 tool 尝试计数。

### 8.7 Runtime config bundle

涉及文件：

- `src/prompt2langgraph/compiler/codegen.py`
- `src/prompt2langgraph/ir/lockfile.py`
- `src/prompt2langgraph/runtime/artifacts.py`
- `tests/test_artifacts.py`
- `tests/test_bundle_golden.py`

实施内容：

- 修改 `_write_graph()` 生成的 `graph.py`。
- 新增 `RuntimeConfig`。
- 新增 `invoke(input_payload, config=None)`。
- `build_graph(config=None)` 支持注入 runtime clients。
- `compile_workflow_to_artifacts()` 增加 `executor_registry: ExecutorRegistry | None = None` 参数，并传给 validate、bind、manifest 构建。
- 如 CLI 要编译 dynamic tool bundle，`compile` 命令增加 `--tool-module`，加载顺序与 `run` 相同。
- 保留旧入口兼容。
- manifest 增加 runtime requirements。
- 更新 golden bundle。

测试要求：

- generated module 可 import。
- `build_graph()` 旧入口仍可调用。
- `build_graph(RuntimeConfig(...))` 可调用。
- `invoke({"question":"hello"})` 可运行 builtin workflow。
- dynamic tool bundle 可通过 RuntimeConfig 注入 registry 并运行。

### 8.8 Benchmark 与工程门禁

涉及文件：

- 新增 `tests/test_benchmark_gates.py` 或 `tests/test_engineering_gates.py`
- `tests/prompts_skills_test/README.md`
- `README.md`
- `docs/prompt2langgraph-v0.3-开发计划文档.md`

实施内容：

- 增加离线 benchmark helper，默认只做 smoke 和数量级记录，不设置脆弱耗时阈值。
- 10/100 节点线性图使用程序构造 fixture，不写大型静态 JSON。
- prompt/skill corpus 继续使用 fake model，不访问网络。
- 文档列出建议手动命令和默认 pytest 覆盖。

验收命令：

```bash
uv run pytest tests/test_tool_executor.py tests/test_security_policy.py -v
uv run pytest tests/test_runner.py tests/test_side_effect_executor.py -v
uv run pytest tests/test_artifacts.py tests/test_bundle_golden.py -v
uv run pytest tests/test_prompt_pipeline.py tests/test_skill_workflow.py -v
uv run pytest tests/test_cli.py -v
uv run pytest
```

### 8.9 Documentation sync

涉及文件：

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/prompt2langgraph-v0.3-开发计划文档.md`
- `tests/prompts_skills_test/README.md`

实施内容：

- 增加 `--tool-module` 使用说明。
- 说明 tool module 是受信任 Python module，不是 sandbox。
- 说明 `ToolCallableRegistry` + `allowed_tool_refs` 双重约束。
- 说明 RetryPolicy 当前只覆盖动态 LLM/tool wrapper。
- 说明 side-effect idempotency 的 workflow/thread/node/key 作用域。
- 说明 audit 不记录 secret 和完整 payload。
- 说明 generated bundle runtime config。
- 再次标注 `LANGCHAIN_TOOL` reserved/experimental。

---

## 9. 分期执行建议

### 9.1 3A：可运行 tool workflow

目标：CLI 能加载 fake tool module，并受控运行 python callable tool workflow。

建议顺序：

1. 写 CLI tool module loader 测试。
2. 实现 `ToolCallableRegistry` loader。
3. 合成 dynamic executor registry。
4. 在 workflow parse/load 前完成 tool module 加载。
5. 让 workflow source loading 支持 executor registry 注入，覆盖 IR 和简化 JSON plan。
6. run/resume 传入 executor registry 和 tool registry。
7. 增加 Skill tool readiness result。
8. 跑 `tests/test_tool_executor.py`、`tests/test_security_policy.py`、CLI tool module 测试。

### 9.2 3B：治理语义

目标：retry、idempotency、audit、metrics 对已暴露字段形成最小闭环。

建议顺序：

1. 实现 retry 判定和 wrapper。
2. 增加 retry metrics。
3. 增加 external call latency。
4. 增加 side-effect idempotency state。
5. 增加 audit sink。
6. 跑 runner、side_effect、integration execution 测试。

### 9.3 3C：bundle 与门禁

目标：bundle 可最小配置运行，并具备离线 benchmark / golden 验收。

建议顺序：

1. 修改 generated `graph.py` runtime config。
2. 让 artifact compile API 支持 `executor_registry` 注入。
3. 若 CLI 需要 dynamic tool bundle smoke，则增加 `compile --tool-module`。
4. 更新 manifest runtime requirements。
5. 更新 golden bundle。
6. 增加 dynamic tool bundle smoke。
7. 增加 benchmark smoke。
8. 同步 README、AGENTS、CLAUDE、开发计划文档。
9. 跑全量 `uv run pytest`。

---

## 10. 验收标准

第三期完成时必须满足：

- CLI 可以通过 `--tool-module` 加载至少一个受控 fake tool module，并执行 `PYTHON_CALLABLE` tool workflow。
- CLI 可以通过 `--tool-module` 执行包含自定义 tool ref 的简化 JSON plan，且 adapter 不会把该 executor 降级为 `builtin`。
- 不传 `--tool-module` 时默认不加载任何外部 tool。
- 未授权、未注册、超时、执行异常、输出缺失 tool 均有稳定 diagnostics。
- Skill planning result 能列出 required tool refs、allowed tool refs、registered tool refs、missing tool refs、unauthorized tool refs 和风险提示。
- `RetryPolicy.max_attempts` 对动态 LLM/tool wrapper 生效。
- 不可重试错误不会被错误重试。
- retry 指标有明确数据通道，`retry_count`、`call_count`、`tool_call_count` 语义有测试锁定。
- side-effect idempotency 在 checkpoint replay 或重复进入同一已批准节点时不会重复执行已完成的同一 key。
- audit/metrics 能按最小字段记录关键运行摘要，且不泄露 secret、完整 payload 或完整模型响应。
- generated bundle 支持最小 runtime config 的 `build_graph(config)` 和 `invoke(input, config)`。
- artifact compile API 支持 executor registry 注入，dynamic tool bundle 可生成并通过 `RuntimeConfig` 注入 registry 运行。
- 旧 generated bundle 入口仍有兼容测试。
- benchmark 和工程门禁默认离线、可重复、不访问网络。
- `LANGCHAIN_TOOL` 被明确标记为 reserved/experimental，validator 产生 `E_SEC_016` 错误阻断，并不作为 v0.3 可执行能力宣传。
- README、AGENTS、CLAUDE、测试说明与实际行为一致。
- 全量 `uv run pytest` 通过。

---

## 11. 风险与控制

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| CLI tool module 扩大执行面 | 用户误加载不可信 Python module | 默认不加载；文档明确受信任边界；不支持 shell / JSON registry |
| tool module 加载晚于 workflow parse | 简化 JSON plan 的自定义 tool ref 被降级为 builtin | 固定加载顺序：tool module 先于 workflow parse/load |
| 只注册 ToolCallableRegistry 导致 validator 仍失败 | CLI tool workflow 无法运行 | tool refs 同步合成 dynamic `ExecutorDefinition` |
| Retry 重复执行副作用 | 外部状态被重复修改 | v0.3 retry 只默认覆盖动态 LLM/tool；side-effect retry 必须绑定 approval/idempotency |
| idempotency record 绑定 pending interrupt 生命周期 | 成功后清理 pending thread 导致去重记录丢失 | idempotency runtime store 与 pending interrupt store 分离 |
| audit 泄露敏感内容 | 安全事故 | audit schema 固定最小字段；测试断言不包含完整 payload |
| generated bundle 破坏旧入口 | 现有 golden 测试失败 | 保留 `compile_graph()` 和 `invoke_graph()` 兼容入口 |
| dynamic tool bundle 无法编译 | artifact API 固定 builtin registry，manifest/golden 不可用 | `compile_workflow_to_artifacts()` 支持 executor registry 注入 |
| benchmark 变成脆弱耗时门禁 | CI 波动 | 默认只做 smoke 和规模覆盖；耗时阈值放入手动报告 |
| `LANGCHAIN_TOOL` 语义悬空 | 用户误以为可执行 | 文档和 validator 明确 reserved/experimental |

---

## 12. 完成后文档同步清单

第三期实现完成后，同步更新：

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/prompt2langgraph-v0.3-开发计划文档.md`
- `tests/prompts_skills_test/README.md`

同步内容必须覆盖：

- `--tool-module` 用法和安全边界。
- tool registry、executor registry、allowed_tool_refs 的关系。
- RetryPolicy 当前执行范围。
- side-effect idempotency 作用域。
- audit/metrics 字段和脱敏边界。
- generated bundle runtime config。
- `LANGCHAIN_TOOL` reserved/experimental 状态。

---

## 13. 后续 agent 执行计划边界

若需要为 coding agent 生成细粒度执行计划，应将本项目级计划拆成至少三个独立计划：

1. `v03-phase3a-cli-tool-registry`
2. `v03-phase3b-runtime-governance`
3. `v03-phase3c-runtime-config-bundle`

agent 执行计划可以包含更详细代码，但必须遵守以下规则：

- 每个任务先写可运行测试，再写最小实现。
- 测试片段必须能直接放入 `tests/` 运行。
- 代码片段必须对照当前源码签名、executor schema 和测试工具。
- 不复制大段完整函数；优先给最小补丁片段。
- 每个任务完成后运行对应单测；第三期全部完成后运行 `uv run pytest`。

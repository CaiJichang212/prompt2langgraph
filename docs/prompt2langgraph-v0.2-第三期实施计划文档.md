# prompt2langgraph v0.2 第三期实施计划文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v0.2 前两期已实现的 Prompt 输入闭环、真实 LLM 执行和受控 Tool 执行基础上，补齐 Skill → WorkflowSpec alpha 转换、JOIN 最小可执行语义、Side Effect 审批中断闭环，并抽象 runtime checkpointer 注入边界。

**Architecture:** 第三期采用“复用前两期链路 + 最小增量增强”的架构：Skill 转换复用 `llm/`、`prompting/parser.py` 和 `JSONPlanAdapter`；JOIN 执行复用 LangGraph fan-in + reducer superstep 语义；Side Effect 审批复用 LangGraph `interrupt()` / `Command(resume=...)` 和现有 `resume` 命令；Checkpointer 增强优先交付 `BaseCheckpointSaver` 注入边界，SQLite 持久化作为 P2 增强。

**Tech Stack:** Python 3.11, Typer, Pydantic, pytest, LangGraph `StateGraph` / `interrupt()` / `Command` / checkpointer, LangChain fake model 测试策略, Deep Agents Skills / HITL 设计理念, 现有 `prompt2langgraph` adapter/validator/compiler/runtime 架构。

---

## 一、实施范围与执行原则

本实施计划严格遵守《[prompt2langgraph-v0.2-第三期开发计划文档](docs/prompt2langgraph-v0.2-%E7%AC%AC%E4%B8%89%E6%9C%9F%E5%BC%80%E5%8F%91%E8%AE%A1%E5%88%92%E6%96%87%E6%A1%A3.md)》定义的范围，只覆盖以下内容：

- Skill → 简化 JSON plan → `WorkflowSpec` 的 LLM 驱动 alpha 转换；
- `pt2lg plan --skill-dir` 与 Public API 的 Skill 入口；
- Skill 参数注入与 scripts/assets/references 资源建模提示；
- `EdgeKind.JOIN` 的 `join_sources` 声明式 fan-in 执行语义；
- `side_effect` 节点的二元审批中断闭环；
- `run_workflow()` 的可注入 checkpointer 边界；
- 对应 validator、compiler、runner、CLI、Mermaid、fixtures、测试与文档更新。

不在本期 P1 核心范围中的内容：

- 生产级 PostgresSaver；
- subprocess / Docker / 网络沙箱；
- `LANGCHAIN_TOOL` executor 可执行能力；
- 自动执行或自动注册 Skill 目录下脚本；
- LLM 多轮反思、自修复、质量评估；
- 多中断批量恢复、`edited/respond` 决策、基于 LangGraph `@task` 的 durable side effect；
- Web UI / HTTP 服务化 / Agent Server 部署。

开发过程必须遵守以下执行原则：

1. 先测试、后实现，优先使用 TDD 推进；
2. 所有新增输入必须进入现有 adapter / validator / compiler / runner 链路，不能绕过校验；
3. Skill 转换只生成简化 JSON plan，不直接生成或执行 `WorkflowSpec`；
4. Side Effect 默认需审批或幂等键，不能隐式执行外部副作用；
5. Checkpointer 注入只暴露抽象，不在 bundle、lockfile、manifest 中写入连接字符串或凭据；
6. 每完成一个任务运行对应测试，最后执行 `uv run pytest`。

---

## 二、优先级与实施顺序

### 2.1 分级交付

| 优先级 | 范围 | 完成条件 |
|------|------|----------|
| P0 | 前两期能力兼容、现有测试不回归、文档边界准确 | `uv run pytest` 通过，现有 CLI/API 行为兼容 |
| P1 | Skill alpha、JOIN 可执行、Side Effect 审批、checkpointer 注入 | 新增核心测试通过，核心验收达成 |
| P2 | CLI SQLite checkpointer、多中断增强、side effect 幂等记录、Mermaid 高级展示 | 不阻塞 P1，可独立合入 |

### 2.2 推荐顺序

1. **Checkpointer 注入边界**：先让 `run_workflow()` 可接受外部 checkpointer，为 Side Effect interrupt 测试提供稳定入口；
2. **Side Effect 审批闭环**：基于 checkpointer 和现有 resume 流程实现最小 approved/rejected；
3. **JOIN 执行支持**：独立补齐 `join_sources`、validator、compiler、Mermaid 与 fixture；
4. **Skill 转换器**：复用 Prompt planner、parser、JSON adapter 与 fake model 测试；
5. **Skill CLI/API 与资源建模**：在转换器稳定后扩展 `pt2lg plan --skill-dir` 与 public API；
6. **P2 SQLite 增强**：确认 `langgraph-checkpoint-sqlite` 兼容后再引入；
7. **全量回归与文档同步**：更新 README、CLAUDE、AGENTS 并运行全量测试。

可并行推进的任务组：

- Task 1（checkpointer 注入）与 Task 3（JOIN）可并行；
- Task 4（Skill 转换器）可与 Task 2/3 并行；
- Task 5 依赖 Task 4；
- Task 6 为 P2 增强，必须在 P1 稳定后执行。

---

## 三、改动文件结构

### 3.1 新增文件

| 文件 | 职责 |
|------|------|
| `src/prompt2langgraph/prompting/skill_planner.py` | Skill → JSON plan → `WorkflowSpec` LLM 转换器 |
| `src/prompt2langgraph/registry/side_effect_executor.py` | Side Effect 审批中断包装执行器 |
| `src/prompt2langgraph/validate/join_check.py` | JOIN 边结构、reducer 与重复边校验 |
| `tests/test_skill_workflow.py` | Skill 转换、参数注入与 fake model 集成测试 |
| `tests/test_join_execution.py` | JOIN 编译、执行、Mermaid 与诊断测试 |
| `tests/test_side_effect_executor.py` | Side Effect interrupt/resume 审批测试 |

### 3.2 修改文件

| 文件 | 改动要点 |
|------|----------|
| `src/prompt2langgraph/ir/models.py` | `EdgeSpec` 新增 `join_sources: list[str] | None = None` |
| `src/prompt2langgraph/compiler/langgraph_py.py` | 编译 JOIN 边；对 `side_effect` 节点包装审批执行；传递 checkpointer 语义 |
| `src/prompt2langgraph/runtime/runner.py` | `run_workflow()` 新增 `checkpointer` 参数并保持旧 JSON runtime 状态兼容 |
| `src/prompt2langgraph/validate/validator.py` | 组合调用 JOIN 校验，并保留现有安全校验顺序 |
| `src/prompt2langgraph/validate/security.py` | 确认 side_effect 审批/幂等/allow 策略仍被验证 |
| `src/prompt2langgraph/visualization/mermaid.py` | 渲染 `join_sources` 多源汇聚标注 |
| `src/prompt2langgraph/cli.py` | `plan` 支持 `--skill-dir`、`--param`；`run/resume` 继续兼容 runtime 状态 |
| `src/prompt2langgraph/__init__.py` | 暴露 Skill planning public API |
| `src/prompt2langgraph/prompting/__init__.py` | 导出 Skill planner 类型与函数 |
| `src/prompt2langgraph/runtime/events.py` | 如需补充 Side Effect 审批事件字段，保持 `RunInterrupt` 兼容 |
| `tests/test_ir_schema.py` | 覆盖 `join_sources` schema、normalize、lock hash 兼容 |
| `tests/test_validator.py` | 更新 JOIN 从“可表达不可执行”到“带 `join_sources` 可执行”的校验 |
| `tests/test_runner.py` | 覆盖 `checkpointer` 注入与原 resume 兼容 |
| `tests/test_cli.py` | 覆盖 `plan --skill-dir`、side_effect resume、现有 plan/run/resume 不回归 |
| `README.md` / `CLAUDE.md` / `AGENTS.md` | 同步能力边界、命令示例与测试要求 |

### 3.3 复用文件

| 文件 | 复用方式 |
|------|----------|
| `src/prompt2langgraph/adapters/skill_dir.py` | 继续作为 Skill 静态分析入口 |
| `src/prompt2langgraph/adapters/json_plan.py` | 继续作为简化 JSON plan → `WorkflowSpec` 的唯一适配入口 |
| `src/prompt2langgraph/prompting/parser.py` | 复用 JSON fence 提取和解析诊断能力 |
| `src/prompt2langgraph/prompting/planner.py` | 复用 LLM 调用模式和 `PromptPlanResult` 设计 |
| `src/prompt2langgraph/llm/` | 复用 `build_llm_client()`、消息转换和 `.env` 配置 |
| `src/prompt2langgraph/registry/tool_executor.py` | Side Effect 审批通过后仍走现有 tool dispatch |
| `tests/fixtures/skill_basic/` | 作为 Skill 转换基础 fixture |
| `tests/fixtures/side_effect_allowed.json` | 保持 allow_side_effects=True 路径兼容 |

---

## 四、当前代码库关键接口基线

执行者必须以当前源码为准，不能仅按 v0.1 文档假设能力。

### 4.1 IR 模型

- `EdgeKind` 已包含 `JOIN = "join"`，但 `EdgeSpec` 当前没有 `join_sources`；
- `PolicySpec` 已包含 `allow_side_effects`、`external_call`、`allowed_models`、`collect_metrics`、`allowed_tool_refs`；
- `SecurityPolicy` 已包含 `requires_approval`、`idempotency_key`、`allowed_tool_refs`；
- `StateSchema.reducers` 已支持 `APPEND`、`ADD_MESSAGES`、`SUM`、`MERGE_DICT`。

### 4.2 Compiler / Runner

- `compile_workflow_to_graph()` 已接受 `checkpointer`，但 edge 编译仅支持 `LINEAR`、`CONDITIONAL`、`LOOP`、`FANOUT`；
- `run_workflow()` 当前内部通过 `_checkpointer_for(thread_key)` 创建 `InMemorySaver`，调用方不能注入 checkpointer；
- CLI 跨进程 resume 当前依赖 `.pt2lg-runtime/*.json` 保存 `InMemorySaver.storage` / `.writes` / `.blobs` 私有结构；
- `_check_target_capabilities()` 当前仍将 JOIN 视为不支持目标能力。

### 4.3 Skill / Prompt

- `analyze_skill_dir()` 只做静态分析，不生成 workflow，不执行 scripts；
- `plan_prompt_to_workflow_spec()` 已打通 Prompt → LLM → JSON plan → `WorkflowSpec`；
- `parse_prompt_plan_text()` 和 `JSONPlanAdapter` 是新增 Skill 转换必须复用的解析与适配入口。

### 4.4 Side Effect

- validator 已能拒绝无审批、无幂等键且未全局允许的 side effect；
- runtime 当前没有 `SideEffectExecutor`，`requires_approval=True` 不会自动触发运行时 interrupt；
- 现有 `side_effect_allowed.json` 通过 `allow_side_effects=True` + `builtin.identity_transform` 执行，第三期必须保持兼容。

---

## 五、实施任务拆解

### Task 1：抽象 `run_workflow()` Checkpointer 注入边界

**目标：** 让调用方可注入 LangGraph checkpointer，同时保持 `checkpointer=None` 和现有 `.pt2lg-runtime/*.json` resume 行为兼容。

**Files:**
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `src/prompt2langgraph/__init__.py`（如 public API 文档化签名需要）
- Test: `tests/test_runner.py`
- Test: `tests/test_cli.py`

**接口契约：**

```python
def run_workflow(
    workflow: WorkflowSpec,
    input_payload: dict[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
    thread_id: str | None = None,
    resume_payload: Any = _NO_RESUME,
    state_store_dir: Path | None = None,
    model_client: Any | None = None,
    tool_registry: Any | None = None,
    checkpointer: Any | None = None,
) -> RunResult:
    """Run a workflow with an optional caller-managed LangGraph checkpointer."""
```

**实施步骤：**

- [ ] **Step 1: 写失败测试**
  - 在 `tests/test_runner.py` 新增 `test_run_workflow_accepts_injected_checkpointer_for_interrupt_resume`；
  - 使用 `langgraph.checkpoint.memory.InMemorySaver()` 注入 `run_workflow(..., checkpointer=checkpointer)`；
  - 运行含 `human_gate` 的 workflow，断言首次返回 `waiting`，同一 `thread_id` resume 成功；
  - 当前预期失败：`run_workflow()` 不接受 `checkpointer` 参数。

- [ ] **Step 2: 扩展 `run_workflow()` 签名并选择有效 checkpointer**
  - `checkpointer is None` 时继续使用 `_checkpointer_for(thread_key)`；
  - `checkpointer is not None` 时直接传给 `compile_workflow_to_graph()`；
  - 注入 checkpointer 路径不写入 `_THREAD_CHECKPOINTERS`。

- [ ] **Step 3: 保持旧本地状态兼容**
  - `state_store_dir` 旧 JSON 路径只在 `checkpointer is None` 时调用 `_save_thread_state()` / `_load_thread_state()`；
  - 若调用方同时传入 `checkpointer` 和 `state_store_dir`，优先使用注入 checkpointer，旧 JSON snapshot 不做私有结构序列化；
  - 保持 `_PENDING_INTERRUPTS` 作为当前进程的 waiting 标记，避免破坏现有 resume 判断。

- [ ] **Step 4: 补 CLI 兼容回归**
  - `tests/test_cli.py::test_resume_command_continues_pending_interrupt_across_processes` 必须继续通过；
  - 现有 `run` / `resume` 命令不新增参数。

- [ ] **Step 5: 运行测试**
  - Run: `uv run pytest tests/test_runner.py tests/test_cli.py -v`
  - Expected: PASS

---

### Task 2：实现 Side Effect 审批中断最小闭环

**目标：** 让 `side_effect` 节点在 `requires_approval=True` 且 `allow_side_effects=False` 时触发 `interrupt()`，通过现有 `resume` 入口 approved 后执行、rejected 后拒绝执行。

**Files:**
- Create: `src/prompt2langgraph/registry/side_effect_executor.py`
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Modify: `src/prompt2langgraph/runtime/events.py`（仅在需要补结构化字段时修改）
- Modify: `src/prompt2langgraph/validate/security.py`（确认策略兼容，尽量少改）
- Test: `tests/test_side_effect_executor.py`
- Test: `tests/test_runner.py`
- Test: `tests/test_cli.py`
- Fixture: `tests/fixtures/side_effect_requires_approval.json`

**接口契约：**

```python
class SideEffectExecutor:
    def __init__(
        self,
        *,
        node_id: str,
        executor_ref: str,
        security: SecurityPolicy,
        allow_side_effects: bool = False,
        invoke_actual: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.node_id = node_id
        self.executor_ref = executor_ref
        self.security = security
        self.allow_side_effects = allow_side_effects
        self.invoke_actual = invoke_actual

    def __call__(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        if self.allow_side_effects:
            return self.invoke_actual(inputs, params)
        decision = interrupt({
            "kind": "side_effect_approval",
            "node_id": self.node_id,
            "executor_ref": self.executor_ref,
            "action": params.get("action", "side_effect"),
            "inputs": inputs,
            "params": params,
            "idempotency_key": self.security.idempotency_key if self.security else None,
        })
        if isinstance(decision, dict) and decision.get("decision") == "approved":
            return self.invoke_actual(inputs, params)
        reason = decision.get("reason", "rejected") if isinstance(decision, dict) else "rejected"
        return {"effect_result": "side_effect_rejected", "reason": reason}
```

审批 payload：

```json
{
  "kind": "side_effect_approval",
  "node_id": "write_file",
  "executor_ref": "builtin.identity_transform",
  "action": "side_effect",
  "inputs": {},
  "params": {},
  "idempotency_key": "optional-key"
}
```

resume payload：

```json
{"decision":"approved"}
```

或：

```json
{"decision":"rejected","reason":"not allowed"}
```

**实施步骤：**

- [ ] **Step 1: 写审批中断失败测试**
  - 新建 `tests/test_side_effect_executor.py`；
  - 构造 `requires_approval=True` 且 `allow_side_effects=False` 的 side_effect workflow；
  - 注入 `InMemorySaver`，首次运行断言 `RunResult.status == "waiting"`，`interrupt.value["kind"] == "side_effect_approval"`。

- [ ] **Step 2: 写 approved resume 测试**
  - 对同一 `thread_id` 调用 `run_workflow(..., resume_payload={"decision":"approved"}, checkpointer=same_checkpointer)`；
  - 断言状态为 `succeeded`，实际 executor 输出进入 workflow output。

- [ ] **Step 3: 写 rejected resume 测试**
  - resume payload 为 `{"decision":"rejected","reason":"manual reject"}`；
  - 断言实际 executor 不被调用；
  - 输出包含 `side_effect_rejected` 和拒绝 reason。

- [ ] **Step 4: 实现 `SideEffectExecutor`**
  - 使用 `langgraph.types.interrupt`；
  - `allow_side_effects=True` 直接调用 `invoke_actual`；
  - `requires_approval=True` 时 interrupt 并解析 decision；
  - 无审批且无允许时抛防御性 `ExecutorError(E_SIDE_008, ...)`。

- [ ] **Step 5: 在 compiler 中包装 side_effect 执行**
  - 在 `_node_wrapper()` 内部识别 `node.kind == "side_effect"`；
  - 构造闭包 `invoke_actual`：闭包捕获 `_invoke_executor` 所需的闭包变量（`executors`、`node`、`error_sink`、`model_client` 等），内部调用 `_invoke_executor(executor_ref=node.executor.ref, params=params, context=inputs)`；
  - `_invoke_executor` 是 `_node_wrapper()` 内部定义的本地函数，不能模块级 import，必须在 `_node_wrapper()` 内部构造闭包后传入 `SideEffectExecutor`；
  - 避免递归再次进入 side_effect 包装。

- [ ] **Step 5b: 在 validator 中检查 side_effect 所需的 state key reducer**
  - 若 workflow 包含 `side_effect` 节点：
    - 检查 `state_schema.reducers["side_effect_records"]` 是否为 `APPEND`（幂等去重必需）；
    - 若 side_effect 节点配置了 `idempotency_key`，检查 `state_schema.reducers["side_effect_results"]` 是否为 `APPEND`；
    - 未声明时输出 warning diagnostic（不阻断），附带建议补齐声明；
  - 此检查可放在 `validate/security.py` 的 `check_security()` 中或新增独立检查函数。

- [ ] **Step 5c: 记录 side_effect 执行事件**
  - 审批通过后的实际 executor 调用若无异常，可通过 `metrics_sink` 记录 `ExternalCallRecord`（status="success"），与 LLM executor 记录风格一致；
  - `ExternalCallRecord` 现有结构无需修改：`node_id` 区分 side_effect 节点，`executor_ref` 指向实际 executor（如 `builtin.identity_transform`）；
  - 审批拒绝、直接允许路径的执行同样记录，确保 `collect_metrics=True` 时观测数据完整。

- [ ] **Step 6: 保持 allow 路径兼容**
  - 运行 `tests/test_runner.py::test_run_workflow_invokes_allowed_side_effect_node -v`；
  - 确认 `tests/fixtures/side_effect_allowed.json` 行为不变。

- [ ] **Step 7: CLI resume 回归**
  - 在 `tests/test_cli.py` 增加 side_effect waiting + resume approved/rejected 覆盖；
  - `pt2lg resume` 继续使用现有 `--resume` JSON 字符串；
  - `RunInterrupt.value` 中的 `kind` 字段（`"human_gate"` vs `"side_effect_approval"`）用于 CLI 渲染不同的提示文案，resume payload 对两种中断使用相同格式。

- [ ] **Step 8: 运行测试**
  - Run: `uv run pytest tests/test_side_effect_executor.py tests/test_runner.py tests/test_cli.py tests/test_security_policy.py -v`
  - Expected: PASS

---

### Task 3：补齐 JOIN 边声明式 fan-in 执行语义

**目标：** 让 `EdgeKind.JOIN` 通过 `join_sources` 声明多源汇聚，编译器自动生成多条 `add_edge(source, target)`，实际聚合交给 LangGraph reducer superstep 语义。

**Files:**
- Modify: `src/prompt2langgraph/ir/models.py`
- Modify: `src/prompt2langgraph/ir/normalize.py`（确认 `join_sources` 经规范化正确序列化）
- Modify: `src/prompt2langgraph/ir/lockfile.py`（确认新增字段纳入 hash 计算）
- Create: `src/prompt2langgraph/validate/join_check.py`
- Modify: `src/prompt2langgraph/validate/validator.py`
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `src/prompt2langgraph/visualization/mermaid.py`
- Test: `tests/test_ir_schema.py`
- Test: `tests/test_validator.py`
- Test: `tests/test_join_execution.py`
- Fixture: `tests/fixtures/fanout_with_join.json`
- Fixture: `tests/fixtures/invalid_join_edge.json`

**接口契约：**

```python
class EdgeSpec(BaseModel):
    id: str
    source: str
    target: str
    kind: EdgeKind
    condition: ConditionSpec | None = None
    map: MapSpec | None = None
    loop_guard: LoopGuard | None = None
    join_sources: list[str] | None = None

    @model_validator(mode="after")
    def join_source_consistency(self) -> "EdgeSpec":
        if self.kind != EdgeKind.JOIN:
            return self
        if not self.join_sources:
            raise ValueError("JOIN edge requires join_sources")
        if self.source != self.join_sources[0]:
            raise ValueError(
                f"JOIN edge source must equal join_sources[0], "
                f"got source={self.source!r}, join_sources[0]={self.join_sources[0]!r}"
            )
        return self
```

JOIN edge 示例（`source` 等于 `join_sources[0]`，保持 `EdgeSpec` 的单一 source 约束）：

```json
{
  "id": "join_research",
  "kind": "join",
  "source": "branch_a",
  "target": "summarize",
  "join_sources": ["branch_a", "branch_b"]
}
```

**实施步骤：**

- [ ] **Step 1: 写 schema 失败测试**
  - 在 `tests/test_ir_schema.py` 验证 `EdgeSpec(..., join_sources=[...])` 可解析；
  - 验证 `WorkflowSpec.model_dump(mode="json")` 包含 `join_sources`。

- [ ] **Step 2: 扩展 `EdgeSpec`**
  - 新增 `join_sources` 字段 + `join_source_consistency` model_validator；
  - 保持旧 JSON 缺失字段可解析为 `None`，迁移错误由 validator 输出。

- [ ] **Step 2b: 确认 normalize 与 lockfile 兼容**
  - 在 `normalize_workflow()` 中确认 `join_sources` list 元素顺序经规范化保留；
  - 在 `sha256_canonical_json()` 中确认 `join_sources` 已纳入 lockfile hash 输入；
  - 测试：`tests/test_ir_schema.py` 验证含 `join_sources` 的 EdgeSpec 的 normalize → dump → load 循环保持一致；lockfile hash 在 `join_sources` 变化时不同。

- [ ] **Step 3: 写 JOIN 校验测试**
  - `join_sources=None` 或空列表：error；
  - `join_sources` 包含未知节点：error；
  - target 出现在 `join_sources`：error；
  - `source` 不在 `join_sources` 中：error（与 `source = join_sources[0]` 约束一致）；
  - 多源写同一 state key 但无 reducer：warning；
  - 已存在同源同 target LINEAR 边：warning。

- [ ] **Step 3a: 实现 JOIN 迁移提示 diagnostic**
  - 当 `kind=JOIN` 且 `join_sources is None` 时，输出 diagnostic 包含明确的迁移提示：
    - `code: "E_SCHEMA_002"`、`severity: "error"`；
    - `message: "JOIN edge requires join_sources field (v0.2 migration)"`；
    - `hint: "Add 'join_sources: [\"source_node_1\", \"source_node_2\"]' listing all fan-in source nodes. The 'source' field must equal join_sources[0]."`。

- [ ] **Step 4: 实现 `validate/join_check.py`**
  - 返回 `list[Diagnostic]`；
  - 使用现有诊断风格，优先复用 `E_SCHEMA_002` / `E_REDUCER_012` / `E_GRAPH_004` 等已有码；
  - warning 不阻断 `report.ok`，error 阻断。

- [ ] **Step 5: 在 `validate_workflow()` 中组合 JOIN 校验**
  - 放在 schema/registry 基础检查之后、typecheck 之前；
  - 确保无 JOIN workflow 不受影响。

- [ ] **Step 6: 编译 JOIN 边**
  - 在 `compile_workflow_to_graph()` 中处理 `EdgeKind.JOIN`；
  - 对每个 `join_sources` 调用 `builder.add_edge(source, target)`；
  - 若已有同源同 target LINEAR 边，跳过重复 `add_edge()`；
  - 将 JOIN 的所有 source 加入 `outgoing_sources`，避免被错误连到 `END`。

- [ ] **Step 7: 更新 target capability 检查**
  - 在 `_check_target_capabilities()` 中将 `EdgeKind.JOIN` 加入 supported；
  - 更新原先“compile rejects join edge”相关测试为“缺少 `join_sources` 才拒绝”。

- [ ] **Step 8: 增加合法 fixture 与执行测试**
  - 新增 `tests/fixtures/fanout_with_join.json`；
  - 至少覆盖两个分支写入同一 `results` state key，`reducers.results = "append"`；
  - target 节点读取聚合结果并输出。

- [ ] **Step 9: 更新 Mermaid 渲染**
  - JOIN 边渲染多源到 target；
  - 标签包含 `join` 或 `join_sources`；
  - 运行 `tests/test_artifacts.py` 和新增 Mermaid 测试。

- [ ] **Step 10: 运行测试**
  - Run: `uv run pytest tests/test_ir_schema.py tests/test_validator.py tests/test_join_execution.py tests/test_artifacts.py -v`
  - Expected: PASS

---

### Task 4：实现 Skill → WorkflowSpec LLM 驱动 alpha 转换器

**目标：** 读取 Skill 目录中的 `SKILL.md` 原文，结合 `analyze_skill_dir()` 静态分析结果，经 LLM 生成简化 JSON plan，再通过 `JSONPlanAdapter` 转为 `WorkflowSpec`。

**Files:**
- Create: `src/prompt2langgraph/prompting/skill_planner.py`
- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Test: `tests/test_skill_workflow.py`
- Test: `tests/test_skill_dir.py`

**接口契约：**

```python
class SkillPlanRequest(BaseModel):
    skill_dir: str
    params: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0


class SkillPlanResult(BaseModel):
    raw_text: str
    plan: dict[str, Any] | None = None
    workflow_spec: WorkflowSpec | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)


def build_skill_plan_prompt(
    skill_md_text: str,
    *,
    analysis: SkillDirectoryAnalysis | None = None,
    params: dict[str, str] | None = None,
) -> str:
    """Build the Skill-to-JSON-plan prompt from SKILL.md and static analysis context."""


def plan_skill_to_workflow_spec(
    request: SkillPlanRequest | str | Path,
    *,
    params: dict[str, str] | None = None,
    model_client: Any | None = None,
) -> SkillPlanResult:
    """Generate, parse, adapt, and return a WorkflowSpec candidate for a Skill directory."""
```

**实施步骤：**

- [ ] **Step 1: 写 fake model 成功转换测试**
  - fake model 返回合法简化 JSON plan；
  - 调用 `plan_skill_to_workflow_spec(SkillPlanRequest(skill_dir="tests/fixtures/skill_basic"), model_client=fake)`；
  - 断言 `result.plan is not None`、`result.workflow_spec is not None`、`validate_workflow(result.workflow_spec).ok`。

- [ ] **Step 2: 写 prompt 构建测试**
  - `build_skill_plan_prompt()` 输出包含 `SKILL.md` 原文、步骤摘要、资源清单、风险诊断摘要、参数上下文；
  - 输出包含可用节点类型和 executor 列表；
  - 输出明确“只返回 JSON，不要执行脚本”。

- [ ] **Step 3: 写风险保留测试**
  - 对 `skill_basic` 中的 `danger.sh` 或风险词 fixture，断言 prompt 中包含 `E_SEC_007` 风险信息；
  - fake model 若生成缺少审批边界的计划，`SkillPlanResult.diagnostics` 应包含 warning 或 error，提示风险步骤缺少 `human_gate` / `side_effect.requires_approval`。

- [ ] **Step 4: 实现 `SkillPlanRequest` / `SkillPlanResult`**
  - 与 `PromptPlanRequest` / `PromptPlanResult` 风格一致；
  - `diagnostics` 使用现有 `Diagnostic` 模型，不使用裸 dict。

- [ ] **Step 5: 实现 `build_skill_plan_prompt()`**
  - 包含 Deep Agents Skills 借鉴原则：原文保留、资源显式、风险前置、审批边界；
  - 提示 LLM 输出简化 JSON plan 必需字段：`name`、`inputs`、`outputs`、`nodes`、`edges`；
  - 提示 `side_effect_results`、`side_effect_records` 为保留 state key。

- [ ] **Step 5a: 实现 Few-shot 示例 prompt 段**
  - 在 system prompt 中包含 3 个 Skill 步骤 → JSON plan 节点的映射示例：
    - 简单线性 workflow：检索 → 分析 → 回答（`retriever` + `llm` + `llm`）；
    - 含高危步骤的 workflow：文件写入前置 `human_gate` → 通过后经 `side_effect` 执行；
    - 含 tool 节点的 workflow：`tool` 节点调用受控脚本，带 `allowed_tool_refs`。
  - 每个示例包含完整 Skill 步骤描述和对应的 JSON plan 片段（含 `name`、`inputs`、`outputs`、`nodes`、`edges`、`policies`）；
  - Few-shot 示例目标：弥补 LLM 缺乏 Skill → JSON plan 映射的领域知识，确保高危步骤自动附加审批边界。

- [ ] **Step 6: 实现 `plan_skill_to_workflow_spec()`**
  - 读取 `SKILL.md`；
  - 调用 `analyze_skill_dir()` 获取分析上下文；
  - 若未传 `model_client`，复用 `llm.provider.build_llm_client()`；
  - 复用 `generate_plan_text()` 或同等 LLM 调用模式；
  - 复用 `parse_prompt_plan_text()` 和 `JSONPlanAdapter().parse()`；
  - 失败时返回结构化 diagnostics，不吞掉 `raw_text`。

- [ ] **Step 7: 补 JSON 输出降级测试**
  - markdown fence JSON 可解析；
  - 缺少 `edges` / `outputs` 的基本结构可补默认并给 warning；
  - 完全不可解析时返回 `E_PARSE_001`，diagnostic hint 包含原始输出前 500 字符。

- [ ] **Step 8: 导出 prompting 符号**
  - 在 `prompting/__init__.py` 导出 `SkillPlanRequest`、`SkillPlanResult`、`build_skill_plan_prompt`、`plan_skill_to_workflow_spec`。

- [ ] **Step 9: 运行测试**
  - Run: `uv run pytest tests/test_skill_workflow.py tests/test_skill_dir.py tests/test_prompt_parser.py -v`
  - Expected: PASS

---

### Task 5：扩展 Skill 参数注入、CLI 与 Public API

**目标：** 让用户可通过 `pt2lg plan --skill-dir <dir> --param key=value` 或 public API 调用 Skill 转换能力。

**Files:**
- Modify: `src/prompt2langgraph/cli.py`
- Modify: `src/prompt2langgraph/__init__.py`
- Modify: `src/prompt2langgraph/prompting/skill_planner.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_public_api.py`
- Test: `tests/test_skill_workflow.py`

**CLI 契约：**

```bash
uv run pt2lg plan --skill-dir tests/fixtures/skill_basic --param topic=LangGraph --json
```

约束：

- `--prompt` 与 `--skill-dir` 互斥，必须二选一；
- `--param` 可多次指定，格式必须为 `key=value`；
- `--validate` 对 Skill 生成结果同样生效；
- JSON 输出复用现有 plan payload：`{"ok": true, "plan": ..., "validation": ...}`。

**实施步骤：**

- [ ] **Step 1: 写 CLI 互斥测试**
  - 无 `--prompt` 且无 `--skill-dir`：失败；
  - 同时传 `--prompt` 与 `--skill-dir`：失败；
  - `--param invalid`：失败并返回诊断。

- [ ] **Step 2: 修改 `plan` 命令签名**
  - `prompt: str | None = typer.Option(None, "--prompt")`；
  - `skill_dir: Path | None = typer.Option(None, "--skill-dir")`；
  - `param: list[str] = typer.Option([], "--param")`；
  - 保持原 `--model`、`--base-url`、`--api-key`、`--temperature`、`--validate`、`--json`。

- [ ] **Step 3: 实现 `_parse_plan_params()`**
  - 输入 `list[str]`；
  - 每项必须包含非空 key 和 value；
  - 返回 `dict[str, str]`；
  - 重复 key 后者覆盖前者，并给 warning 或保持简单覆盖，文档说明。

- [ ] **Step 4: 分流 Prompt 与 Skill**
  - `prompt is not None` 走现有 `generate_plan_text()` 路径；
  - `skill_dir is not None` 走 `plan_skill_to_workflow_spec()`；
  - Skill 路径输出 `result.plan`，`--validate` 优先复用 `result.workflow_spec`，避免重复适配。

- [ ] **Step 5: 扩展 Public API**
  - 在 `src/prompt2langgraph/__init__.py` 导出 `SkillPlanRequest`、`SkillPlanResult`、`plan_skill_to_workflow_spec`；
  - `tests/test_public_api.py` 验证可导入且 fake model 可调用。

- [ ] **Step 6: 运行测试**
  - Run: `uv run pytest tests/test_cli.py tests/test_public_api.py tests/test_skill_workflow.py tests/test_prompt_planner.py -v`
  - Expected: PASS

---

### Task 6：P2 可选增强：CLI SQLite Checkpointer

**目标：** 在依赖兼容性确认后，允许 CLI 内部使用 `SqliteSaver` 提供更稳定的本地 checkpoint；若依赖不可用，则保留文档化的后续项，不阻塞 P1。

**Files:**
- Modify: `pyproject.toml`（必须先获得用户确认后再改依赖）
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `src/prompt2langgraph/cli.py`
- Test: `tests/test_runner.py`
- Test: `tests/test_cli.py`

**依赖候选：**

```toml
"langgraph-checkpoint-sqlite>=2.0"
```

**实施步骤：**

- [ ] **Step 1: 确认依赖兼容性**
  - 检查当前 `langgraph>=1.0,<2.0` 与 `langgraph-checkpoint-sqlite>=2.0` 是否兼容；
  - 确认构造方式为 `SqliteSaver(sqlite3.connect(path))`；
  - 确认是否需要 `setup()`。

- [ ] **Step 2: 获得用户许可后修改 `pyproject.toml`**
  - 本项目规则要求修改项目级配置和安装新依赖前必须询问用户；
  - 未获得许可时跳过本任务，记录为 P2 后续增强。

- [ ] **Step 3: 实现 CLI 内部构造函数**
  - 新增 `_build_cli_checkpointer(workflow_json: Path, thread_id: str)`；
  - 路径建议为 `<bundle_dir>/.pt2lg-runtime/<thread_hash>.db`；
  - 防御性调用 `setup()`：若对象无该方法则跳过。

- [ ] **Step 4: 接入 run/resume**
  - `pt2lg run` 与 `pt2lg resume` 内部传入 `checkpointer=...`；
  - 若 SQLite 初始化失败，返回明确 diagnostic，不回退到隐式外部状态。

- [ ] **Step 5: 更新兼容文档**
  - 说明旧 `.json` runtime 状态与 `.db` checkpoint 不互相迁移；
  - 说明 SQLite checkpoint 默认保留以支持后续 time travel debugging。

- [ ] **Step 6: 运行测试**
  - Run: `uv run pytest tests/test_runner.py tests/test_cli.py -v`
  - Expected: PASS

---

### Task 7：文档同步与官方设计依据整理

**目标：** 让 README、CLAUDE、AGENTS 与第三期能力边界一致，避免文档错误暗示未实现能力。

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `docs/prompt2langgraph-v0.2-第三期开发计划文档.md`（仅当实施中发现计划需修正）

**需要同步的事实：**

- Skill 转换是 alpha：可生成、可诊断、可人工修正，不保证任意 Skill 一次成功；
- Skill 转换不执行 scripts，不自动注册 tool callable；
- JOIN 基于 LangGraph fan-in + reducer，未声明 reducer 的并行写入会覆盖且顺序不稳定；
- Side Effect 默认审批，通过 `pt2lg resume --resume '{"decision":"approved"}'` 恢复；
- `run_workflow()` 支持 checkpointer 注入；
- SQLite 若未实现，应明确仍为 P2 后续增强；若实现，应明确 `.db` 保留行为。

**官方设计依据索引：**

- LangGraph 并行节点与 reducer：https://docs.langchain.com/oss/python/langgraph/use-graph-api#run-graph-nodes-in-parallel
- LangGraph Interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph Persistence：https://docs.langchain.com/oss/python/langgraph/persistence
- LangChain Human-in-the-loop：https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- Deep Agents overview：https://docs.langchain.com/oss/python/deepagents/overview
- Deep Agents Skills：https://docs.langchain.com/oss/python/deepagents/skills
- Deep Agents customization：https://docs.langchain.com/oss/python/deepagents/customization
- Deep Agents HITL：https://docs.langchain.com/oss/python/deepagents/human-in-the-loop

**实施步骤：**

- [ ] **Step 1: 更新 README 能力与示例**
  - 添加 `pt2lg plan --skill-dir` 示例；
  - 添加 JOIN fixture 示例；
  - 添加 Side Effect approve/reject resume 示例。

- [ ] **Step 2: 更新 CLAUDE.md / AGENTS.md**
  - 同步当前能力边界；
  - 更新测试要求；
  - 明确不要宣称超出 P1/P2 的能力。

- [ ] **Step 3: 校验文档措辞**
  - 搜索“join 不支持”“skill 只静态分析”“side_effect 不执行”等旧描述；
  - 按实际实现状态更新，不提前宣传 P2 未实现能力。

---

### Task 8：全量回归与验收

**目标：** 确认第三期新增能力与前两期能力均可用。

**Files:**
- Test: all tests
- Optional CLI smoke: selected fixture commands

**实施步骤：**

- [ ] **Step 1: 运行第三期核心测试**
  - Run: `uv run pytest tests/test_skill_workflow.py tests/test_join_execution.py tests/test_side_effect_executor.py -v`
  - Expected: PASS

- [ ] **Step 2: 运行前两期回归测试**
  - Run: `uv run pytest tests/test_prompt_planner.py tests/test_prompt_parser.py tests/test_public_api.py tests/test_cli.py tests/test_llm_executor.py tests/test_tool_executor.py tests/test_security_policy.py tests/test_integration_execution.py -v`
  - Expected: PASS

- [ ] **Step 3: 运行编译与 runner 回归测试**
  - Run: `uv run pytest tests/test_compile_flow.py tests/test_runner.py tests/test_langgraph_compiler.py tests/test_validator.py tests/test_ir_schema.py -v`
  - Expected: PASS

- [ ] **Step 4: 运行全量测试**
  - Run: `uv run pytest`
  - Expected: PASS

- [ ] **Step 5: CLI smoke 验证**
  - Run: `uv run pt2lg validate tests/fixtures/linear_llm.json --json`
  - Expected: JSON 输出中 `ok=true`
  - Run: `uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json`
  - Expected: `status="succeeded"`
  - Run: `uv run pt2lg graph tests/fixtures/fanout_with_join.json --format mermaid`
  - Expected: Mermaid 包含 JOIN 汇聚标注

---

## 六、验收标准

### 6.1 P0 回归必达

- 现有 `validate / compile / run / graph / plan / resume` 命令行为兼容；
- Prompt 输入闭环、真实 LLM executor、Tool executor 测试不回归；
- `tests/fixtures/side_effect_allowed.json` 保持可执行；
- 全量 `uv run pytest` 通过。

### 6.2 P1 核心增强必达

- `plan_skill_to_workflow_spec()` 可使用 fake model 将 Skill 目录转为可校验 `WorkflowSpec`；
- `pt2lg plan --skill-dir` 可输出简化 JSON plan，并支持 `--param`；
- 带 `join_sources` 和 reducer 的 JOIN workflow 可编译并执行；
- 无 `join_sources`、未知 source、自引用 JOIN 均有明确 diagnostic；
- `requires_approval=True` 的 side_effect 节点可 waiting、approved resume、rejected resume；
- `run_workflow()` 可注入 checkpointer，`checkpointer=None` 保持旧行为。

### 6.3 P2 增强不阻塞

- SQLite checkpointer 若未完成，不阻塞 P1；
- 多中断批量 resume、应用层幂等记录、`edited/respond`、LangGraph `@task` durable side effect 若未完成，不阻塞 P1；
- Mermaid 高级汇聚图形若未完成，至少需有清晰 JOIN 标注。

---

## 七、风险与回滚策略

| 风险 | 影响 | 缓解 |
|------|------|------|
| Skill LLM 输出不稳定 | 测试 flaky 或用户难以复现 | 单元测试使用 fake model；结果保留 `raw_text` 和 diagnostics；建议 temperature=0 |
| JOIN 多源写入无 reducer | 结果被覆盖或顺序不稳定 | validator warning；文档明确 LangGraph reducer 语义 |
| Side Effect 审批后执行失败 | 需要重新审批重试 | 文档明确 superstep 回滚语义；后续用 `@task` 增强 |
| checkpointer 注入破坏旧 resume | CLI 跨进程恢复失败 | P1 保留旧 JSON runtime 状态路径；SQLite 作为 P2 |
| SQLite 依赖不兼容 | 安装或运行失败 | 不作为 P1；实施前确认依赖并询问用户 |

---

## 八、后续演进方向

> **`@task` 兼容性说明**：当前第三期使用 `StateGraph` API + `interrupt()` 实现审批中断。若未来引入 LangGraph `@task` 装饰器，需确认当前 `langgraph>=1.0,<2.0` 版本中 `@task` 在 `StateGraph` 节点函数内部直接使用的 API 稳定性。根据 [LangGraph Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) 文档，`@task` 可同时用于 `StateGraph`（Graph API）和 Functional API。

- `LANGCHAIN_TOOL` executor：对接 LangChain `BaseTool` 生态和 tool schema 推导；
- LangGraph `RetryPolicy`：将 `NodeSpec.retry` 映射到原生 retry；
- LangGraph `@task` durable side effect：审批通过后的实际副作用执行持久化，避免重复执行；
- PostgresSaver：生产级 checkpoint 后端；
- Skill 转换缓存：按 Skill 目录 hash + params 缓存 JSON plan；
- Agent Server 部署：通过 LangGraph/LangSmith Agent Server 提供服务化运行。

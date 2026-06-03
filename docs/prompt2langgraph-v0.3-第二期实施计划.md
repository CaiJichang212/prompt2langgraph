# prompt2langgraph v0.3 第二期实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Prompt/Skill planning 从“LLM 单次 JSON 输出成功才可用”推进为“可解析、可诊断、可修复、可度量”的规划链路。

**Architecture:** 第二期不改变 Workflow IR、JSON plan adapter、validator、compiler 的主边界，而是在 `prompting/` 下补齐 parser、pipeline、repair 与 corpus 评估层。Prompt/Skill 仍只生成简化 JSON plan；结构化 pipeline 必须重新经过 `parse -> adapt -> validate -> compile smoke`，兼容 API 保持旧的 `generate -> parse -> adapt` 行为，不能绕过现有安全策略和执行绑定。

**Tech Stack:** Python、Pydantic、Typer CLI、LangGraph compiler、pytest、离线 fake model/corpus fixtures。

---

## 1. 背景与范围

第二期承接 `docs/prompt2langgraph-v0.3-开发计划文档.md` 第 9 节，目标是补齐 Prompt/Skill 生成可靠性闭环。

纳入范围：

- 增强 `src/prompt2langgraph/prompting/parser.py`，支持常见 LLM 输出包裹形态。
- 新增统一 planning pipeline，显式区分 `generation`、`parse`、`adapter`、`validation`、`compile_smoke` 阶段。
- 引入可配置 repair attempts，默认关闭或保守开启，默认单测不访问网络。
- 将 Skill 静态风险诊断保留到 planning result。
- 基于 `tests/prompts_skills_test` 建立离线评估口径。
- 对齐 CLI `pt2lg plan` 与 public API 的结构化结果输出。

排除范围：

- 不实现 CLI tool registry 加载；该能力属于第三期。
- 不实现 `LANGCHAIN_TOOL` 端到端执行；v0.3 仍按 reserved/experimental 处理。
- 不引入 MCP、Web UI、OpenAPI 服务、进程沙箱或网络隔离。
- 不把 Prompt 入口升级为直接运行 workflow 的命令。
- 不把 live LLM 评估纳入默认 `pytest`。

## 2. 当前源码事实

本节是计划中代码片段的依据，执行前应重新核对这些事实是否仍成立。

- `src/prompt2langgraph/prompting/parser.py` 当前只有 `parse_prompt_plan_text(text, *, source="prompt") -> dict[str, Any]`，实现为 `json.loads(text)`，非对象输出抛 `AdapterParseError`。
- `src/prompt2langgraph/prompting/planner.py` 当前提供 `PromptPlanRequest`、`PromptPlanResult`、`generate_plan_text()`、`plan_prompt_to_workflow_spec()`；后者直接执行 `generate -> parse -> JSONPlanAdapter().parse()` 并返回 `WorkflowSpec`。
- `src/prompt2langgraph/prompting/skill_planner.py` 当前提供 `SkillPlanRequest`、`SkillPlanResult`、`generate_skill_plan_text()`、`plan_skill_to_workflow_spec()`；Skill 静态分析来自 `analyze_skill_dir()`，但 `plan_skill_to_workflow_spec()` 返回 `WorkflowSpec` 时不会把分析风险放入结构化 planning result。
- `src/prompt2langgraph/cli.py` 的 `plan` 命令当前有 `--prompt`、`--skill-dir`、`--validate`、`--json`、`--param`，内部路径为 `_run_prompt_plan()` 和 `_run_skill_plan()`；`--validate` 只执行 adapter + validator，没有 compile smoke 阶段结果。
- `src/prompt2langgraph/adapters/json_plan.py` 的 `JSONPlanAdapter().parse(plan, source=...)` 是简化 JSON plan 到 `WorkflowSpec` 的唯一适配入口，已支持 v0.3 第一期字段。
- `src/prompt2langgraph/validate/validator.py` 的 `validate_workflow()` 返回 `ValidationReport`，其中 `ValidationReport.ok` 由 diagnostics 中是否存在 error 决定。
- `src/prompt2langgraph/compiler/langgraph_py.py` 的 `compile_workflow_to_graph(workflow, executors, ...)` 可作为 compile smoke；默认可配合 `builtin_executor_registry()` 使用。
- `src/prompt2langgraph/diagnostics/report.py` 中 `Diagnostic` 字段为 `code`、`severity`、`message`、`location`、`hint`；`DiagnosticLocation` 可携带 `source`、`path`、`line`、`column`。
- `tests/prompts_skills_test/test_cases.json` 当前声明 42 个 corpus case，默认测试通过 fake model 离线构造 plan，不访问网络。

## 3. 行为契约

### 3.1 Parser 行为

`parse_prompt_plan_text()` 保持 public signature 不变，继续在成功时返回 `dict[str, Any]`，失败时抛 `AdapterParseError`。

必须支持：

- 纯 JSON object。
- Markdown fenced JSON block，例如 ```json 包裹的单个对象。
- 文本说明中包含唯一 JSON object。
- JSON 前后带解释文本，但只存在唯一对象候选。

必须拒绝并给出稳定诊断：

- 非 JSON 输出。
- JSON 非对象输出，例如 array、number、string、boolean、null。
- 截断 JSON。
- 多个顶层 JSON object 候选，避免静默猜测。
- fenced block 与正文中存在多个对象候选。

错误定位要求：

- 原始 `json.JSONDecodeError` 应尽量保留 `line`、`column`。
- 包裹文本提取失败时，`AdapterParseError.source` 必须使用调用方传入的 `source`。
- 多候选错误的 `path` 可使用 `"generated_text"`，`hint` 由 CLI/pipeline 转成 `Diagnostic.hint`。

### 3.2 Pipeline 行为

新增统一 pipeline，作为 Prompt/Skill 规划链路的结构化入口：

```text
prompt / skill
  -> generation
  -> parse
  -> adapter
  -> validation
  -> compile_smoke
  -> structured result
```

pipeline 结果必须包含：

- `ok: bool`
- `source: "prompt" | "skill"`
- `raw_text: str | None`
- `plan: dict[str, Any] | None`
- `workflow: WorkflowSpec | None`
- `diagnostics: list[Diagnostic]`
- `validation_report: ValidationReport | None`
- `stages: dict[PlanningStageName, PlanningStageStatus]`
- `repair_attempts: list[RepairAttemptRecord]`

阶段状态必须能表达：

- 阶段是否运行。
- 阶段是否成功。
- 阶段失败 diagnostics。
- 未运行阶段的原因，例如前序 parse 失败。

`compile_smoke` 只检查图可编译，不写 bundle，不执行 workflow，不调用外部 LLM 或 tool。pipeline 默认使用 `builtin_executor_registry()`，并保持 `tool_registry=None` 的现有校验兼容语义；需要严格检查 Tool callable 注册时，测试、corpus 评估或调用方可显式注入空或已注册的 `tool_registry`，并可注入 `executor_registry` 以复用 `tests/test_prompt_skill_corpus.py` 里的 corpus registry。

### 3.3 Repair 行为

repair attempts 是 planning pipeline 的能力，不属于 parser、adapter、validator 的内部职责。

必须满足：

- request 上提供可配置次数，建议字段名为 `repair_attempts: int = 0`，范围 `0..3`。
- CLI 提供 `--repair-attempts`，默认 `0`。
- 每次 repair 都必须重新进入 `parse -> adapter -> validation -> compile_smoke`。
- repair prompt 只能包含必要诊断、原始 plan 摘要、目标 schema 约束和用户原始目标；不能包含 secret、完整 API key 或大段模型响应。
- repair message 构造统一放在 `prompting/pipeline.py`，建议提供 `_build_repair_messages(...)` 和 `_invoke_model_messages(...)` 私有 helper，避免 prompt 与 skill planner 各自实现一套 repair 调用。
- repair 失败时返回最后一次诊断，同时保留每次 attempt 摘要。
- 默认测试使用 deterministic fake model，不访问网络。

### 3.4 Skill 风险诊断

Skill planning 必须保留 `analyze_skill_dir()` 的静态诊断。

行为要求：

- `analysis.report.diagnostics` 进入 pipeline result 的 `diagnostics`。
- error 级 Skill 静态诊断阻止 generation 阶段。
- warning/info 级风险不阻止 generation，但必须在 JSON 输出中可见。
- 风险诊断不代表执行授权；真实 tool/side-effect 执行授权仍由第三期处理。

### 3.5 CLI 与 public API

保留兼容入口：

- `plan_prompt_to_workflow_spec()` 继续返回 `WorkflowSpec`，失败时继续抛异常。
- `plan_skill_to_workflow_spec()` 继续返回 `WorkflowSpec`，失败时继续抛异常。
- `PromptPlanRequest`、`SkillPlanRequest` 继续可构造。

新增结构化入口：

- `plan_prompt()` 返回 pipeline result，实现在 `src/prompt2langgraph/prompting/pipeline.py`。
- `plan_skill()` 返回 pipeline result，实现在 `src/prompt2langgraph/prompting/pipeline.py`。
- `src/prompt2langgraph/prompting/__init__.py` 和 `src/prompt2langgraph/__init__.py` 只负责 re-export 结构化入口。

兼容入口约束：

- `plan_prompt_to_workflow_spec()` 默认只保持旧链路语义：`generation -> parse -> adapter`，成功返回 `WorkflowSpec`。
- `plan_skill_to_workflow_spec()` 默认只保持旧链路语义：`skill analysis -> generation -> parse -> adapter`，成功返回 `WorkflowSpec`。
- 兼容入口不默认执行 `validation` 或 `compile_smoke`，避免改变已有 public API 的失败面。
- parse/adapt 失败继续抛 `AdapterParseError`；LLM 调用失败继续透传调用异常；结构化诊断由 `plan_prompt()` / `plan_skill()` 提供。

CLI `pt2lg plan --json` 的最小兼容要求：

- 成功时继续输出 `{"ok": true, "plan": ...}`。
- 使用 `--validate` 时输出 `validation`，不自动输出 `compile_smoke`。
- 使用 `--compile-smoke` 时先执行 adapter + validation，再执行 compile smoke，并输出 `validation` 与 `compile_smoke`。
- 失败时输出 `{"ok": false, "diagnostics": [...]}`，不输出 traceback。
- `--repair-attempts` 大于 0 时输出 `repair_attempts` 摘要。

## 4. 模块实施任务

### 4.1 Parser 鲁棒性

目标文件：

- `src/prompt2langgraph/prompting/parser.py`
- `tests/test_prompt_parser.py`

任务：

- [ ] 增加 fenced JSON 提取。
- [ ] 增加唯一 JSON object 扫描。
- [ ] 增加多候选拒绝逻辑。
- [ ] 保持现有 `AdapterParseError` 类型与 source 字段。
- [ ] 补充 parser 单元测试。

验收：

```bash
uv run pytest tests/test_prompt_parser.py -v
```

### 4.2 Planning pipeline

目标文件：

- `src/prompt2langgraph/prompting/pipeline.py`
- `src/prompt2langgraph/prompting/__init__.py`
- `tests/test_prompt_pipeline.py`

任务：

- [ ] 新增 pipeline result models。
- [ ] 实现 prompt pipeline：接收 `PromptPlanRequest`、调用 `generate_plan_text()`、parse、adapter、validate、compile smoke。
- [ ] 实现 skill pipeline：接收 `SkillPlanRequest`、复用 `analyze_skill_dir()` 和 `generate_skill_plan_text()`。
- [ ] 失败阶段要返回 diagnostics，并标记后续阶段 skipped。
- [ ] pipeline 支持可选 `executor_registry` 和 `tool_registry` 注入；默认 compile smoke 使用 `compile_workflow_to_graph(workflow, builtin_executor_registry())`。
- [ ] corpus 测试必须注入 `tests/test_prompt_skill_corpus.py` 已有的 `_build_corpus_executor_registry()`，避免 `llm.gpt-4`、`tool.unregistered_tool` 等 corpus-only refs 被 builtin registry 误判。

验收：

```bash
uv run pytest tests/test_prompt_pipeline.py -v
```

### 4.3 Repair attempts

目标文件：

- `src/prompt2langgraph/prompting/pipeline.py`
- `src/prompt2langgraph/prompting/planner.py`
- `src/prompt2langgraph/prompting/skill_planner.py`
- `tests/test_prompt_pipeline.py`

任务：

- [ ] 在 `PromptPlanRequest` 和 `SkillPlanRequest` 增加 `repair_attempts: int = Field(default=0, ge=0, le=3)`。
- [ ] 在 pipeline 中加入 repair loop。
- [ ] 新增 `_build_repair_messages(...)` 和 `_invoke_model_messages(...)` 私有 helper，repair generation 复用同一个 model client，但传入 repair prompt messages。
- [ ] 每次 repair 记录 `attempt_index`、`trigger_stage`、`diagnostic_codes`、`raw_text_preview`、`ok`。
- [ ] repair 成功后返回最终成功 result，并保留历史 attempts。
- [ ] repair 失败后返回最终失败 result，并保留历史 attempts。

验收：

```bash
uv run pytest tests/test_prompt_pipeline.py::test_prompt_pipeline_repairs_parse_failure -v
uv run pytest tests/test_prompt_pipeline.py::test_prompt_pipeline_can_disable_repair -v
```

### 4.4 Planner 兼容入口

目标文件：

- `src/prompt2langgraph/prompting/planner.py`
- `src/prompt2langgraph/prompting/skill_planner.py`
- `src/prompt2langgraph/prompting/__init__.py`
- `src/prompt2langgraph/__init__.py`
- `tests/test_prompt_planner.py`
- `tests/test_skill_workflow.py`
- `tests/test_public_api.py`

任务：

- [ ] 在 `prompting/pipeline.py` 新增 `plan_prompt()` 和 `plan_skill()` 结构化入口。
- [ ] 在 `prompting/__init__.py` 和顶层 `__init__.py` re-export `plan_prompt()`、`plan_skill()`、`PlanningPipelineResult`。
- [ ] 让 `plan_prompt_to_workflow_spec()` 保持旧链路语义：`generation -> parse -> adapter`，或委托 pipeline 但关闭 validation/compile smoke 后返回 `workflow`。
- [ ] 让 `plan_skill_to_workflow_spec()` 保持旧链路语义，并保留 `analysis` 注入参数。
- [ ] 更新 public API exports。
- [ ] 保持原有测试兼容。

验收：

```bash
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py tests/test_public_api.py -v
```

### 4.5 CLI 对齐

目标文件：

- `src/prompt2langgraph/cli.py`
- `tests/test_cli.py`

任务：

- [ ] `plan` 命令增加 `--repair-attempts`。
- [ ] `plan` 命令增加 `--compile-smoke`；`--validate` 只输出 validation，`--compile-smoke` 输出 validation + compile_smoke。
- [ ] `_run_prompt_plan()` 改为调用结构化 pipeline。
- [ ] `_run_skill_plan()` 改为调用结构化 pipeline。
- [ ] 保留成功时 `payload["plan"]` 的现有行为。
- [ ] 失败时 diagnostics 使用 pipeline result，不输出 traceback。

验收：

```bash
uv run pytest tests/test_cli.py -v
```

### 4.6 Corpus 离线评估

目标文件：

- `tests/test_prompt_skill_corpus.py`
- `tests/prompts_skills_test/README.md`
- `docs/prompt2langgraph-v0.3-开发计划文档.md`

任务：

- [ ] 在 corpus 测试中引入 pipeline 口径，覆盖 prompt、skill、json plan、negative case。
- [ ] 统计离线指标：parse success、validation success、compile smoke success。
- [ ] 默认测试继续使用 fake model，不访问网络。
- [ ] README 记录 live 评估为手动命令，不作为默认门禁。
- [ ] v0.3 总文档同步第二期实际完成边界。

验收：

```bash
uv run pytest tests/test_prompt_skill_corpus.py -v
```

## 5. Agent 执行附录

本附录允许放代码，但只放最小补丁片段。执行时应先写测试，再实现最小代码。

### 5.1 Parser 测试片段

依赖的当前源码事实：`tests/test_prompt_parser.py` 已导入 `parse_prompt_plan_text` 和 `AdapterParseError`，现有测试只覆盖纯 JSON、非对象和空字符串。

建议追加到 `tests/test_prompt_parser.py`：

```python
def test_parse_prompt_plan_text_accepts_fenced_json_object() -> None:
    plan = parse_prompt_plan_text(
        'Here is the plan:\n```json\n{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}\n```'
    )

    assert plan["name"] == "Demo"


def test_parse_prompt_plan_text_accepts_single_object_inside_explanation() -> None:
    plan = parse_prompt_plan_text(
        'I will return one object: {"name":"Wrapped","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]} Done.'
    )

    assert plan["name"] == "Wrapped"


def test_parse_prompt_plan_text_accepts_object_then_suffix_text() -> None:
    plan = parse_prompt_plan_text(
        '{"name":"Suffix","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]} trailing explanation'
    )

    assert plan["name"] == "Suffix"


def test_parse_prompt_plan_text_rejects_multiple_json_objects() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('{"name":"One","nodes":[],"edges":[]} {"name":"Two","nodes":[],"edges":[]}')

    assert "multiple JSON objects" in str(exc_info.value)
    assert exc_info.value.source == "prompt"


def test_parse_prompt_plan_text_rejects_truncated_wrapped_json() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('prefix {"name":"Broken","nodes":[')

    assert "failed to parse" in str(exc_info.value) or "could not extract" in str(exc_info.value)
    assert exc_info.value.source == "prompt"
```

### 5.2 Parser 最小实现片段

依赖的当前源码事实：`parse_prompt_plan_text()` 目前直接调用 `json.loads(text)`；可以在该函数内部先调用私有 helper 提取候选 JSON 文本，再复用原来的对象校验。

建议在 `src/prompt2langgraph/prompting/parser.py` 增加私有 helper：

```python
import re


_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _json_object_candidates(text: str) -> list[tuple[str, int]]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[str, int]] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            candidates.append((text[start : start + end], start))
            index = start + end
        else:
            index = start + 1
    return candidates


def _candidate_search_texts(text: str) -> list[tuple[str, int]]:
    fenced = [(match.group(1), match.start(1)) for match in _FENCED_BLOCK_RE.finditer(text)]
    return fenced or [(text, 0)]
```

并将 `parse_prompt_plan_text()` 的 parse 前半段调整为：

```python
    candidates: list[tuple[str, int]] = []
    for search_text, base_offset in _candidate_search_texts(text):
        candidates.extend(
            (candidate, base_offset + offset)
            for candidate, offset in _json_object_candidates(search_text)
        )

    candidate_text = text
    candidate_offset = 0
    if len(candidates) > 1:
        raise AdapterParseError(
            "generated JSON plan contains multiple JSON objects",
            source=source,
            path="generated_text",
        )
    if len(candidates) == 1:
        candidate_text, candidate_offset = candidates[0]

    try:
        data = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        raise AdapterParseError(
            "failed to parse generated JSON plan",
            source=source,
            path=str(candidate_offset + exc.pos),
            line=exc.lineno,
            column=exc.colno,
        ) from exc
```

### 5.3 Pipeline 测试片段

依赖的当前源码事实：`PromptPlanRequest` 已存在；`FakeModel.invoke(messages)` 模式已在 `tests/test_prompt_planner.py` 中使用；`JSONPlanAdapter` 对 `{"name":"Demo","nodes":[...],"edges":[]}` 可生成有效 `WorkflowSpec`。

建议新建 `tests/test_prompt_pipeline.py`：

```python
from prompt2langgraph.prompting.pipeline import plan_prompt
from prompt2langgraph.prompting.planner import PromptPlanRequest


class _FakeModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def invoke(self, messages):
        response = self.responses[self.calls]
        self.calls += 1
        return type("Response", (), {"content": response})()


def _valid_plan_text() -> str:
    return (
        '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},'
        '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
        '"edges":[]}'
    )


def test_prompt_pipeline_reports_all_success_stages() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="answer a question"),
        model_client=_FakeModel([_valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is True
    assert result.plan is not None
    assert result.workflow is not None
    assert result.stages["generation"].ok is True
    assert result.stages["parse"].ok is True
    assert result.stages["adapter"].ok is True
    assert result.stages["validation"].ok is True
    assert result.stages["compile_smoke"].ok is True


def test_prompt_pipeline_stops_after_parse_failure() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="bad plan"),
        model_client=_FakeModel(["not json"]),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.stages["generation"].ok is True
    assert result.stages["parse"].ok is False
    assert result.stages["adapter"].skipped is True
    assert result.stages["validation"].skipped is True
    assert result.stages["compile_smoke"].skipped is True


def test_prompt_pipeline_repairs_parse_failure() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="repair bad plan", repair_attempts=1),
        model_client=_FakeModel(["not json", _valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is True
    assert len(result.repair_attempts) == 1
    assert result.repair_attempts[0].trigger_stage == "parse"


def test_prompt_pipeline_can_disable_repair() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="repair disabled", repair_attempts=0),
        model_client=_FakeModel(["not json", _valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.repair_attempts == []
```

### 5.4 Pipeline model 最小片段

依赖的当前源码事实：项目使用 Pydantic `BaseModel`；`Diagnostic` 和 `WorkflowSpec` 已可作为 model 字段；`ValidationReport.ok` 是 property，不能直接序列化成字段，CLI 需要手动补 `ok`。

建议新增 `src/prompt2langgraph/prompting/pipeline.py` 的核心 model：

```python
from typing import Any, Literal

from pydantic import BaseModel, Field

from prompt2langgraph.diagnostics.report import Diagnostic, ValidationReport
from prompt2langgraph.ir.models import WorkflowSpec


PlanningSource = Literal["prompt", "skill"]
PlanningStageName = Literal["generation", "parse", "adapter", "validation", "compile_smoke"]


class PlanningStageStatus(BaseModel):
    ran: bool = False
    ok: bool = False
    skipped: bool = False
    reason: str | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class RepairAttemptRecord(BaseModel):
    attempt_index: int
    trigger_stage: PlanningStageName
    diagnostic_codes: list[str] = Field(default_factory=list)
    raw_text_preview: str = ""
    ok: bool = False


class PlanningPipelineResult(BaseModel):
    ok: bool
    source: PlanningSource
    raw_text: str | None = None
    plan: dict[str, Any] | None = None
    workflow: WorkflowSpec | None = None
    validation_report: ValidationReport | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    stages: dict[PlanningStageName, PlanningStageStatus] = Field(default_factory=dict)
    repair_attempts: list[RepairAttemptRecord] = Field(default_factory=list)
```

### 5.5 CLI 测试片段

依赖的当前源码事实：`tests/test_cli.py` 已用 `CliRunner().invoke(app, [...])` 和 monkeypatch fake model 测试 `pt2lg plan`；prompt 路径 monkeypatch 目标是 `prompt2langgraph.prompting.planner.build_model_client`。

建议追加到 `tests/test_cli.py`：

```python
def test_prompt_plan_command_compile_smoke_includes_stage_result(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},'
                        '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
                        '"edges":[]}'
                    )
                },
            )()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        lambda request: FakeModel(),
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--compile-smoke", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["compile_smoke"]["ok"] is True


def test_prompt_plan_command_repair_attempts_are_reported(monkeypatch) -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return type("Response", (), {"content": "not json"})()
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo","nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    model = FakeModel()
    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        lambda request: model,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "repair workflow", "--repair-attempts", "1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert len(payload["repair_attempts"]) == 1
```

### 5.6 Skill 风险 pipeline 测试片段

依赖的当前源码事实：`tests/fixtures/skill_basic` 的静态分析会产生 `E_SEC_007` 风险诊断；`generate_skill_plan_text()` 目前接收预计算 `analysis`；`plan_skill_to_workflow_spec()` 已支持 `analysis=` 注入。

建议追加到 `tests/test_prompt_pipeline.py`：

```python
from prompt2langgraph.prompting.pipeline import plan_skill
from prompt2langgraph.prompting.skill_planner import SkillPlanRequest


class _FakeSkillModel:
    def invoke(self, messages):
        content = (
            '{"name":"SkillWorkflow","inputs":{"question":"string"},'
            '"outputs":{"answer":"string"},'
            '"nodes":[{"id":"step_1","kind":"llm","executor":"builtin.echo_llm"}],'
            '"edges":[]}'
        )
        return type("Response", (), {"content": content})()


def test_skill_pipeline_preserves_static_risk_diagnostics() -> None:
    result = plan_skill(
        SkillPlanRequest(skill_dir="tests/fixtures/skill_basic"),
        model_client=_FakeSkillModel(),
        compile_smoke=True,
    )

    assert result.ok is True
    assert any(diagnostic.code == "E_SEC_007" for diagnostic in result.diagnostics)
```

## 6. 验收标准

第二期完成时必须满足：

- parser 覆盖 fenced JSON、解释文本包裹 JSON、非对象输出、非法 JSON、截断 JSON、多对象输出。
- planning pipeline 能区分 parse、adapter、validation、compile smoke 阶段失败。
- repair attempts 可配置、可测试、可关闭。
- `tests/prompts_skills_test` 的 prompt、Skill、JSON plan、negative cases 都能进入统一离线评估口径。
- Skill 风险诊断能在 planning result 中保留。
- 默认测试不访问网络。
- 旧 public API 和 CLI JSON plan 输出保持兼容。

建议分层验收命令：

```bash
uv run pytest tests/test_prompt_parser.py -v
uv run pytest tests/test_prompt_pipeline.py -v
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py -v
uv run pytest tests/test_prompt_skill_corpus.py -v
uv run pytest tests/test_public_api.py tests/test_cli.py -v
uv run pytest
```

## 7. 文档同步要求

第二期实现完成后，同步更新：

- `README.md`：补充 `pt2lg plan` 的 parser、repair、compile smoke 行为。
- `CLAUDE.md`：同步 Prompt/Skill planning 边界。
- `AGENTS.md`：同步当前能力边界和测试命令。
- `docs/prompt2langgraph-v0.3-开发计划文档.md`：把第二期完成状态从计划描述更新为实际行为。
- `tests/prompts_skills_test/README.md`：记录离线指标和 live 评估手动命令。

文档不得承诺第三期能力，例如 CLI tool registry、真实 tool 执行闭环、`LANGCHAIN_TOOL` 执行、MCP 集成。

## 8. 执行顺序

推荐按以下顺序实施：

1. Parser 鲁棒性测试与实现。
2. Pipeline result models 与无 repair 的 prompt pipeline。
3. Skill pipeline 与静态风险诊断保留。
4. Repair attempts。
5. CLI 与 public API 对齐。
6. Corpus 离线评估口径。
7. README、CLAUDE、AGENTS、v0.3 总文档同步。
8. 全量测试。

该顺序让每一步都有独立可运行测试，并避免在 parser、pipeline、CLI 三层同时改动时难以定位失败来源。

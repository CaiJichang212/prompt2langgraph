# prompt2langgraph v0.2 第一期实施计划文档

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `prompt2langgraph` 补齐 `Prompt → LLM → 简化 JSON plan → WorkflowSpec` 的第一期输入闭环，并复用现有 `validate / compile / run / graph` 主链路。

**Architecture:** 第一期只新增 Prompt 输入层与前置解析诊断层，不改写现有 compiler / runner / validator 主结构。LLM 仅承担“计划生成器”角色，输出结果必须先收敛为简化 JSON plan，再通过现有 `JSONPlanAdapter` 转换为 `WorkflowSpec`，随后进入既有校验与执行链路。

**Tech Stack:** Python 3.11, Typer, Pydantic, pytest, `langchain_openai`, `.env` 配置加载，现有 `prompt2langgraph` adapter/validator/runtime 架构。

---

## 一、实施范围与执行原则

本实施计划严格遵守《[prompt2langgraph-v0.2-第一期开发计划文档](docs/prompt2langgraph-v0.2-%E7%AC%AC%E4%B8%80%E6%9C%9F%E5%BC%80%E5%8F%91%E8%AE%A1%E5%88%92%E6%96%87%E6%A1%A3.md)》定义的范围，只覆盖以下内容：

- Prompt 文本输入；
- 基于 `langchain_openai` 的 LLM 计划生成；
- 默认从 `.env` 加载 `MODEL`、`BASE_URL`、`API_KEY` 的最小配置，并支持在已加载配置基础上选择可用模型；
- 以兼容 Qwen 模型、vLLM 部署暴露的 OpenAI-style API 以及其他第三方兼容接口为优先目标；
- 输出 JSON 解析与诊断；
- 复用现有 `JSONPlanAdapter` 与 `validate_workflow()`；
- CLI / Public API Prompt 入口；
- 测试与文档同步更新（包括 `README.md`、`CLAUDE.md`、`AGENTS.md`）。

不在本期实施计划中的内容：

- 真实 workflow `llm` 节点执行；
- provider 抽象层；
- tool executor；
- join 执行支持；
- skill → WorkflowSpec 执行转换；
- side_effect 最小闭环。

开发过程必须遵守以下执行原则：

1. 先测试、后实现，优先使用 TDD 推进；
2. Prompt 生成输出不能绕过现有 adapter / validator 直接执行；
3. 新能力必须作为新增入口，不破坏现有 JSON 文件入口；
4. 对失败输出优先给出可诊断结果，而非隐式修复；
5. 每完成一个任务即运行对应测试，最后执行 `uv run pytest`。

---

## 二、建议改动文件结构

### 2.1 预计新增文件

- `src/prompt2langgraph/prompting/__init__.py`
  - Prompt 输入层包入口。
- `src/prompt2langgraph/prompting/planner.py`
  - 封装基于 `langchain_openai` 的 Prompt → JSON plan 文本生成逻辑。
- `src/prompt2langgraph/prompting/config.py`
  - 从 `.env` 加载 `MODEL`、`BASE_URL`、`API_KEY`，并提供最小配置解析能力。
- `src/prompt2langgraph/prompting/parser.py`
  - 把 LLM 文本输出解析为 JSON 对象，并产出 Prompt 前置诊断。
- `tests/test_prompt_planner.py`
  - Prompt 计划生成模块测试。
- `tests/test_prompt_parser.py`
  - Prompt 输出解析与诊断测试。

### 2.2 预计修改文件

- `pyproject.toml`
  - 增加第一期所需依赖 `langchain_openai` 与 `.env` 配置加载依赖。
- `src/prompt2langgraph/__init__.py`
  - 暴露 Prompt 入口相关 public API。
- `src/prompt2langgraph/cli.py`
  - 增加 Prompt 输入命令或参数入口，并复用现有输出风格。
- `src/prompt2langgraph/diagnostics/codes.py`
  - 如有必要，增加 Prompt 链路专用诊断码；如无需新增，则复用 `E_PARSE_001`。
- `tests/test_public_api.py`
  - 增加 Prompt API 回归测试。
- `tests/test_cli.py`
  - 增加 Prompt CLI 回归测试。
- `README.md`
  - 更新 Prompt 输入能力、边界与示例。
- `CLAUDE.md`
  - 更新项目输入边界、文档边界、测试要求。
- `AGENTS.md`
  - 同步更新 Prompt 输入边界与回归要求。

### 2.3 复用现有文件

- `src/prompt2langgraph/adapters/json_plan.py`
  - 继续作为简化 JSON plan → `WorkflowSpec` 的唯一主适配入口。
- `src/prompt2langgraph/validate/validator.py`
  - 继续作为 workflow 合法性的统一裁决点。
- `tests/test_json_plan_adapter.py`
  - 作为 Prompt 输出落回简化 plan 约束的参考测试。
- `tests/test_source_diagnostics.py`
  - 作为 `AdapterParseError` 风格与 source/path 诊断一致性的参考测试。

---

## 三、实施任务拆解

### Task 1：引入 Prompt 计划生成基础依赖、配置加载与模块骨架

**Files:**
- Create: `src/prompt2langgraph/prompting/__init__.py`
- Create: `src/prompt2langgraph/prompting/config.py`
- Create: `src/prompt2langgraph/prompting/planner.py`
- Modify: `pyproject.toml`
- Test: `tests/test_prompt_planner.py`

- [ ] **Step 1: 写依赖与模块导入的失败测试**

```python
from prompt2langgraph.prompting.planner import PromptPlanRequest, PromptPlanResult


def test_prompting_module_exports_request_and_result_types() -> None:
    request = PromptPlanRequest(prompt="build a simple answer workflow")
    result = PromptPlanResult(raw_text='{"name":"Demo","nodes":[],"edges":[]}', plan=None, diagnostics=[])

    assert request.prompt == "build a simple answer workflow"
    assert result.raw_text.startswith("{")


def test_load_prompt_planner_config_reads_env(monkeypatch) -> None:
    from prompt2langgraph.prompting.config import load_prompt_planner_config

    monkeypatch.setenv("MODEL", "qwen-plus")
    monkeypatch.setenv("BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("API_KEY", "secret")

    config = load_prompt_planner_config()

    assert config.model == "qwen-plus"
    assert config.base_url == "https://example.com/v1"
    assert config.api_key == "secret"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompt_planner.py::test_prompting_module_exports_request_and_result_types -v`

Expected: FAIL，提示 `ModuleNotFoundError` 或 `cannot import name`。

- [ ] **Step 3: 在 `pyproject.toml` 中添加第一期依赖**

```toml
dependencies = [
  "langchain-core>=1.0,<2.0",
  "langchain-openai>=0.1,<1.0",
  "langgraph>=1.0,<2.0",
  "langsmith>=0.3.0",
  "pydantic>=2.8,<3.0",
  "python-dotenv>=1.0,<2.0",
  "typer>=0.12,<1.0",
  "typing-extensions>=4.12",
]
```

- [ ] **Step 4: 创建 Prompt 模块骨架与 `.env` 配置加载**

`src/prompt2langgraph/prompting/config.py`

```python
from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv


class PromptPlannerConfig(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def load_prompt_planner_config() -> PromptPlannerConfig:
    load_dotenv()
    return PromptPlannerConfig(
        model=os.getenv("MODEL"),
        base_url=os.getenv("BASE_URL"),
        api_key=os.getenv("API_KEY"),
    )
```

`src/prompt2langgraph/prompting/planner.py`

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class PromptPlanRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0


class PromptPlanResult(BaseModel):
    raw_text: str
    plan: dict | None = None
    diagnostics: list[dict] = Field(default_factory=list)
```

`src/prompt2langgraph/prompting/__init__.py`

```python
from prompt2langgraph.prompting.config import PromptPlannerConfig, load_prompt_planner_config
from prompt2langgraph.prompting.planner import PromptPlanRequest, PromptPlanResult

__all__ = [
    "PromptPlanRequest",
    "PromptPlanResult",
    "PromptPlannerConfig",
    "load_prompt_planner_config",
]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_prompt_planner.py::test_prompting_module_exports_request_and_result_types -v`

Expected: PASS

- [ ] **Step 6: 提交本任务**

```bash
git add pyproject.toml src/prompt2langgraph/prompting/__init__.py src/prompt2langgraph/prompting/planner.py tests/test_prompt_planner.py
git commit -m "feat: add prompt planning module skeleton"
```

---

### Task 2：实现 Prompt 输出 JSON 解析与前置诊断

**Files:**
- Create: `src/prompt2langgraph/prompting/parser.py`
- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Test: `tests/test_prompt_parser.py`
- Test: `tests/test_source_diagnostics.py`

- [ ] **Step 1: 写 Prompt 解析成功与失败测试**

```python
from prompt2langgraph.prompting.parser import parse_prompt_plan_text


def test_parse_prompt_plan_text_returns_object_for_valid_json() -> None:
    plan = parse_prompt_plan_text('{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}')
    assert plan["name"] == "Demo"


def test_parse_prompt_plan_text_rejects_non_object_json() -> None:
    try:
        parse_prompt_plan_text('[1, 2, 3]')
    except ValueError as exc:
        assert "must contain an object" in str(exc)
    else:
        raise AssertionError("expected parse failure")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompt_parser.py -v`

Expected: FAIL，提示 `ModuleNotFoundError` 或目标函数不存在。

- [ ] **Step 3: 实现最小 JSON 解析函数**

`src/prompt2langgraph/prompting/parser.py`

```python
from __future__ import annotations

import json
from typing import Any

from prompt2langgraph.adapters.base import AdapterParseError


def parse_prompt_plan_text(text: str, *, source: str = "prompt") -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdapterParseError(
            "failed to parse generated JSON plan",
            source=source,
            path=str(exc.pos),
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    if not isinstance(data, dict):
        raise AdapterParseError(
            "generated JSON plan must contain an object",
            source=source,
        )
    return data
```

- [ ] **Step 4: 导出解析函数**

`src/prompt2langgraph/prompting/__init__.py`

```python
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
from prompt2langgraph.prompting.planner import PromptPlanRequest, PromptPlanResult

__all__ = ["PromptPlanRequest", "PromptPlanResult", "parse_prompt_plan_text"]
```

- [ ] **Step 5: 增加 source/path 诊断断言测试**

```python
import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.prompting.parser import parse_prompt_plan_text


def test_prompt_plan_parse_error_preserves_source_and_position() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('{"name":', source="prompt")

    assert exc_info.value.source == "prompt"
    assert exc_info.value.path == "8"
    assert exc_info.value.line == 1
    assert exc_info.value.column == 9
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_prompt_parser.py tests/test_source_diagnostics.py -v`

Expected: PASS

- [ ] **Step 7: 提交本任务**

```bash
git add src/prompt2langgraph/prompting/__init__.py src/prompt2langgraph/prompting/parser.py tests/test_prompt_parser.py tests/test_source_diagnostics.py
git commit -m "feat: add prompt plan parsing diagnostics"
```

---

### Task 3：实现基于 `langchain_openai` 的 Prompt 计划生成器

**Files:**
- Modify: `src/prompt2langgraph/prompting/planner.py`
- Test: `tests/test_prompt_planner.py`

- [ ] **Step 1: 写 Prompt 计划生成器测试，使用假模型对象**

```python
from prompt2langgraph.prompting.planner import PromptPlanRequest, generate_plan_text


class FakeModel:
    def invoke(self, messages):
        return type("Response", (), {"content": '{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'})()


def test_generate_plan_text_uses_model_and_returns_text() -> None:
    request = PromptPlanRequest(prompt="build a simple answer workflow")

    result = generate_plan_text(request, model_client=FakeModel())

    assert result.raw_text.startswith("{")
    assert '"name":"Demo"' in result.raw_text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompt_planner.py::test_generate_plan_text_uses_model_and_returns_text -v`

Expected: FAIL，提示 `generate_plan_text` 不存在。

- [ ] **Step 3: 实现最小生成器，支持依赖注入测试**

`src/prompt2langgraph/prompting/planner.py`

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI

from prompt2langgraph.prompting.config import load_prompt_planner_config


class PromptPlanRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0


class PromptPlanResult(BaseModel):
    raw_text: str
    plan: dict | None = None
    diagnostics: list[dict] = Field(default_factory=list)


SYSTEM_PROMPT = """You generate simplified JSON plan objects for prompt2langgraph.
Return only a JSON object compatible with the project's simplified JSON plan format.
Do not include markdown fences or explanations.
"""


def build_model_client(request: PromptPlanRequest) -> ChatOpenAI:
    config = load_prompt_planner_config()
    return ChatOpenAI(
        model=request.model or config.model or "qwen-plus",
        base_url=request.base_url or config.base_url,
        api_key=request.api_key or config.api_key,
        temperature=request.temperature,
    )


def generate_plan_text(
    request: PromptPlanRequest,
    *,
    model_client: object | None = None,
) -> PromptPlanResult:
    client = model_client or build_model_client(request)
    response = client.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.prompt},
        ]
    )
    content = response.content if isinstance(response.content, str) else "".join(response.content)
    return PromptPlanResult(raw_text=content)
```

- [ ] **Step 4: 增加模型配置透传测试**

```python
from prompt2langgraph.prompting.planner import PromptPlanRequest, build_model_client


def test_build_model_client_accepts_openai_style_config(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "qwen-turbo")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    request = PromptPlanRequest(
        prompt="build a workflow",
        model="qwen-plus",
        base_url="https://example.com/v1",
        api_key="test-key",
        temperature=0.2,
    )

    client = build_model_client(request)

    assert client.model_name == "qwen-plus"
    assert str(client.openai_api_base) == "https://example.com/v1"
```

- [ ] **Step 5: 增加纯 `.env` 配置回退测试**

```python
def test_build_model_client_uses_env_defaults_when_request_fields_missing(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "qwen-plus")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    request = PromptPlanRequest(prompt="build a workflow")
    client = build_model_client(request)

    assert client.model_name == "qwen-plus"
    assert str(client.openai_api_base) == "https://env.example.com/v1"
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_prompt_planner.py -v`

Expected: PASS

- [ ] **Step 7: 提交本任务**

```bash
git add src/prompt2langgraph/prompting/planner.py tests/test_prompt_planner.py
git commit -m "feat: add langchain openai prompt planner"
```

---

### Task 4：把 Prompt 生成结果接入现有 JSON plan 适配链路

**Files:**
- Modify: `src/prompt2langgraph/prompting/planner.py`
- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Test: `tests/test_prompt_planner.py`
- Test: `tests/test_json_plan_adapter.py`

- [ ] **Step 1: 写 Prompt 生成结果可转 `WorkflowSpec` 的测试**

```python
from prompt2langgraph.prompting.planner import PromptPlanRequest, plan_prompt_to_workflow_spec


class FakeModel:
    def invoke(self, messages):
        return type("Response", (), {"content": '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'})()


def test_plan_prompt_to_workflow_spec_reuses_json_plan_adapter() -> None:
    workflow = plan_prompt_to_workflow_spec(
        PromptPlanRequest(prompt="answer a question"),
        model_client=FakeModel(),
    )

    assert workflow.workflow_id == "demo"
    assert workflow.entrypoint == "compose"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompt_planner.py::test_plan_prompt_to_workflow_spec_reuses_json_plan_adapter -v`

Expected: FAIL，提示 `plan_prompt_to_workflow_spec` 不存在。

- [ ] **Step 3: 实现串联函数，复用 parser 与 `JSONPlanAdapter`**

```python
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.prompting.parser import parse_prompt_plan_text


def plan_prompt_to_workflow_spec(
    request: PromptPlanRequest,
    *,
    model_client: object | None = None,
):
    result = generate_plan_text(request, model_client=model_client)
    result.plan = parse_prompt_plan_text(result.raw_text)
    return JSONPlanAdapter().parse(result.plan, source="prompt")
```

- [ ] **Step 4: 导出新函数**

`src/prompt2langgraph/prompting/__init__.py`

```python
from prompt2langgraph.prompting.planner import (
    PromptPlanRequest,
    PromptPlanResult,
    build_model_client,
    generate_plan_text,
    plan_prompt_to_workflow_spec,
)
```

- [ ] **Step 5: 写失败透传测试**

```python
import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.prompting.planner import PromptPlanRequest, plan_prompt_to_workflow_spec


class FakeBadModel:
    def invoke(self, messages):
        return type("Response", (), {"content": '[1,2,3]'})()


def test_plan_prompt_to_workflow_spec_raises_parse_error_for_non_object_output() -> None:
    with pytest.raises(AdapterParseError):
        plan_prompt_to_workflow_spec(PromptPlanRequest(prompt="bad plan"), model_client=FakeBadModel())
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_prompt_planner.py tests/test_json_plan_adapter.py -v`

Expected: PASS

- [ ] **Step 7: 提交本任务**

```bash
git add src/prompt2langgraph/prompting/__init__.py src/prompt2langgraph/prompting/planner.py tests/test_prompt_planner.py tests/test_json_plan_adapter.py
git commit -m "feat: connect prompt planner to json plan adapter"
```

---

### Task 5：扩展 Public API 暴露 Prompt 入口

**Files:**
- Modify: `src/prompt2langgraph/__init__.py`
- Test: `tests/test_public_api.py`

- [ ] **Step 1: 写 Public API 导出与调用测试**

```python
import prompt2langgraph as pt2lg


class FakeModel:
    def invoke(self, messages):
        return type("Response", (), {"content": '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'})()


def test_public_api_exports_prompt_planning_entrypoints() -> None:
    request = pt2lg.PromptPlanRequest(prompt="answer a question")
    workflow = pt2lg.plan_prompt_to_workflow_spec(request, model_client=FakeModel())

    assert workflow.workflow_id == "demo"
    assert "PromptPlanRequest" in pt2lg.__all__
    assert "plan_prompt_to_workflow_spec" in pt2lg.__all__
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_public_api.py::test_public_api_exports_prompt_planning_entrypoints -v`

Expected: FAIL，提示导出符号不存在。

- [ ] **Step 3: 在 `__init__.py` 中暴露 Prompt API**

```python
from prompt2langgraph.prompting import PromptPlanRequest, PromptPlanResult, plan_prompt_to_workflow_spec

__all__ = [
    "CompileResult",
    "Diagnostic",
    "DiagnosticLocation",
    "PromptPlanRequest",
    "PromptPlanResult",
    "ValidationReport",
    "WorkflowSpec",
    "compile_workflow",
    "plan_prompt_to_workflow_spec",
    "run_workflow",
    "validate_workflow",
]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_public_api.py -v`

Expected: PASS

- [ ] **Step 5: 提交本任务**

```bash
git add src/prompt2langgraph/__init__.py tests/test_public_api.py
git commit -m "feat: expose prompt planning public api"
```

---

### Task 6：扩展 CLI，新增 Prompt 输入入口

**Files:**
- Modify: `src/prompt2langgraph/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写 CLI Prompt 入口测试**

```python
import json

from typer.testing import CliRunner

from prompt2langgraph.cli import app


def test_prompt_plan_command_emits_json_plan_payload(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type("Response", (), {"content": '{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'})()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["plan"]["name"] == "Demo"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_cli.py::test_prompt_plan_command_emits_json_plan_payload -v`

Expected: FAIL，提示 `plan` 命令不存在。

- [ ] **Step 3: 在 CLI 中增加 Prompt 命令**

建议新增独立命令 `plan`，避免污染现有 `validate / compile / run` 参数语义。命令实现应复用现有 CLI 的错误处理风格：捕获 `AdapterParseError` 并转换为 `ValidationReport` / JSON payload，而不是直接把异常抛到终端。配置口径应与开发计划保持一致：默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，CLI 显式参数优先覆盖环境配置。

```python
@app.command()
def plan(
    prompt: str = typer.Option(..., "--prompt"),
    model: str | None = typer.Option(None, "--model"),
    base_url: str | None = typer.Option(None, "--base-url"),
    api_key: str | None = typer.Option(None, "--api-key"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable plan."),
) -> None:
    from prompt2langgraph.prompting import PromptPlanRequest
    from prompt2langgraph.prompting.planner import generate_plan_text
    from prompt2langgraph.prompting.parser import parse_prompt_plan_text

    request = PromptPlanRequest(
        prompt=prompt,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
    try:
        result = generate_plan_text(request)
        plan_data = parse_prompt_plan_text(result.raw_text)
    except AdapterParseError as exc:
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message="failed to parse generated prompt plan",
                    location=DiagnosticLocation(
                        source=exc.source or "prompt",
                        path=exc.path,
                        line=exc.line,
                        column=exc.column,
                    ),
                    hint=str(exc),
                )
            ]
        )
        _emit_validation_report(report, json_output)
        raise typer.Exit(1) from None
    _emit({"ok": True, "plan": plan_data}, json_output, _json_dumps(plan_data))
```

- [ ] **Step 4: 增加 CLI 失败诊断测试**

```python
def test_prompt_plan_command_reports_parse_failure_as_json(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type("Response", (), {"content": '[1,2,3]'})()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "bad workflow", "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_PARSE_001" for item in payload["diagnostics"])
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_cli.py -v`

Expected: PASS

- [ ] **Step 6: 提交本任务**

```bash
git add src/prompt2langgraph/cli.py tests/test_cli.py
git commit -m "feat: add cli prompt planning command"
```

---

### Task 7：补齐 Prompt → validate / compile / run 主链路入口策略

**Files:**
- Modify: `src/prompt2langgraph/cli.py`
- Modify: `src/prompt2langgraph/__init__.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_public_api.py`

- [ ] **Step 1: 写 CLI/API 串联测试，确认 Prompt 结果可继续进入现有链路**

```python
def test_public_prompt_workflow_can_be_validated() -> None:
    import prompt2langgraph as pt2lg

    class FakeModel:
        def invoke(self, messages):
            return type("Response", (), {"content": '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'})()

    workflow = pt2lg.plan_prompt_to_workflow_spec(
        pt2lg.PromptPlanRequest(prompt="answer a question"),
        model_client=FakeModel(),
    )
    report = pt2lg.validate_workflow(workflow)

    assert report.ok is True
```

- [ ] **Step 2: 运行测试确认当前仍有缺口**

Run: `uv run pytest tests/test_public_api.py::test_public_prompt_workflow_can_be_validated -v`

Expected: 若前序任务未完整接通则 FAIL；否则 PASS。

- [ ] **Step 3: 仅做必要补齐，不新增旁路**

若前序任务均已打通，本步只做最小梳理：
- 保证 `plan_prompt_to_workflow_spec()` 返回 `WorkflowSpec`；
- 不在 CLI 中新增 `prompt run` 之类的二次入口；
- 保持现有 `validate / compile / run / graph` 命令接受的仍是 JSON 文件或 lockfile。

- [ ] **Step 4: 运行定向回归**

Run: `uv run pytest tests/test_public_api.py tests/test_cli.py tests/test_json_plan_adapter.py -v`

Expected: PASS

- [ ] **Step 5: 提交本任务**

```bash
git add src/prompt2langgraph/cli.py src/prompt2langgraph/__init__.py tests/test_public_api.py tests/test_cli.py
git commit -m "refactor: align prompt planning with existing workflow pipeline"
```

---

### Task 8：更新 README、CLAUDE、AGENTS 文档边界

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: 更新 README 的输入格式与边界说明**

应补充：
- 新增 Prompt 输入能力；
- Prompt 计划生成依赖外部 LLM；
- 采用 `langchain_openai`，优先兼容 Qwen、vLLM 暴露的 OpenAI-style / 第三方兼容 API；
- 默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`，命令参数可覆盖；
- 当前 Prompt 只生成简化 JSON plan，不代表 runtime `llm` 节点具备真实执行能力。

建议新增示例：

```bash
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --json
```

- [ ] **Step 2: 更新 `CLAUDE.md` 项目边界与测试要求**

应补充：
- 当前支持的上层输入新增 Prompt；
- Prompt 入口仅用于生成简化 JSON plan；
- Prompt 计划生成默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`；
- 文档修改时需同步 `README.md`、`CLAUDE.md`、`AGENTS.md`；
- 修改 Prompt 入口后需跑 CLI / Public API / 全量 pytest 回归。

- [ ] **Step 3: 更新 `AGENTS.md` 项目边界与回归要求**

应补充：
- Prompt 输入能力的边界说明；
- 第一期仍不支持真实 workflow `llm` 执行；
- Prompt 计划生成默认从 `.env` 读取 `MODEL`、`BASE_URL`、`API_KEY`；
- Prompt 相关改动的回归命令要求。

- [ ] **Step 4: 提交文档修改**

```bash
git add README.md CLAUDE.md AGENTS.md
git commit -m "docs: document prompt planning input flow"
```

---

### Task 9：执行全量回归并完成一期验收

**Files:**
- Test: `tests/test_prompt_planner.py`
- Test: `tests/test_prompt_parser.py`
- Test: `tests/test_public_api.py`
- Test: `tests/test_cli.py`
- Test: 全量 `tests/`

- [ ] **Step 1: 运行 Prompt 相关定向测试**

Run: `uv run pytest tests/test_prompt_planner.py tests/test_prompt_parser.py tests/test_public_api.py tests/test_cli.py -v`

Expected: PASS

- [ ] **Step 2: 运行 JSON plan 与诊断相关回归**

Run: `uv run pytest tests/test_json_plan_adapter.py tests/test_source_diagnostics.py -v`

Expected: PASS

- [ ] **Step 3: 运行全量测试**

Run: `uv run pytest`

Expected: 全量 PASS

- [ ] **Step 4: 手工执行 CLI 验收命令**

Run:

```bash
uv run pt2lg plan --prompt "Build a workflow that answers a question with one llm node" --json
```

Expected: 输出 JSON payload，包含 `ok: true` 和 `plan` 对象。

- [ ] **Step 5: 核对一期开发计划文档中的完成定义**

需要逐项确认：
- Prompt 可输入；
- LLM 可生成简化 JSON plan；
- 输出可解析并可适配为 `WorkflowSpec`；
- 可进入现有 `validate` 主链路；
- CLI / API 均可用；
- 文档已同步；
- 非目标能力未被误实现或误宣称。

- [ ] **Step 6: 提交验收完成状态**

```bash
git add tests/test_prompt_planner.py tests/test_prompt_parser.py tests/test_public_api.py tests/test_cli.py README.md CLAUDE.md AGENTS.md src/prompt2langgraph/__init__.py src/prompt2langgraph/cli.py src/prompt2langgraph/prompting/__init__.py src/prompt2langgraph/prompting/planner.py src/prompt2langgraph/prompting/parser.py pyproject.toml
git commit -m "test: verify prompt planning flow end to end"
```

---

## 四、执行顺序建议

建议严格按以下顺序推进：

1. Task 1：依赖与模块骨架；
2. Task 2：前置解析与诊断；
3. Task 3：LLM 计划生成器；
4. Task 4：接入现有 JSON plan adapter；
5. Task 5：Public API 暴露；
6. Task 6：CLI 入口；
7. Task 7：链路对齐与轻量整理；
8. Task 8：文档同步；
9. Task 9：全量回归与验收。

这样可以保证每一步都形成可测试、可回退、可提交的最小增量。

---

## 五、关键注意事项

1. 不要让 Prompt 入口直接生成并执行 Workflow IR；
2. 不要把 `plan` 命令演化成直接运行 workflow 的命令；
3. 不要在 `prompt2langgraph.cli` 模块导入阶段急切初始化 `langchain_openai` 客户端；
4. 不要把真实 API key、secret 名称或 provider 细节写入 compile artifact、report、manifest；
5. 不要为了第一期便利而提前设计完整 provider 抽象；
6. 需要保持现有 JSON plan / Workflow IR 入口测试全部稳定通过；
7. 文档更新不止 `README.md`，还必须同步 `CLAUDE.md` 和 `AGENTS.md`。

---

## 六、完成判定

当以下条件全部满足时，可判定 v0.2 第一期实施完成：

- Prompt 输入能力已落地；
- `langchain_openai` 接入可用于兼容 OpenAI-style / 第三方接口生成简化 JSON plan；
- 输出解析与失败诊断已就绪；
- Prompt 结果可复用现有 `JSONPlanAdapter` 转为 `WorkflowSpec`；
- Public API 与 CLI Prompt 入口均可用；
- `README.md`、`CLAUDE.md`、`AGENTS.md` 已同步；
- `uv run pytest` 全量通过；
- 未越界实现第二期及之后的能力。
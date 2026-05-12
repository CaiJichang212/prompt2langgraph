# AGENTS.md

## 基本要求

- 默认使用中文回复。
- 代码、测试和文档修改应以当前目录为项目根：`/Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph`。
- 不要把上层 `ref-projects/` 的参考工程内容当作本项目源码；本项目源码位于 `src/prompt2langgraph/`，测试位于 `tests/`。
- 保持改动聚焦，避免无关重构、格式化 churn 或生成缓存文件提交。

## 项目定位

`prompt2langgraph` 是一个 Python 3.11+ 工具包，用于把经过验证的 Workflow IR 或简化 JSON plan 编译为 LangGraph 图，并提供本地验证、编译、运行和 Mermaid 渲染能力。

核心边界：

- 规范模型：`src/prompt2langgraph/ir/models.py`
- JSON plan 适配：`src/prompt2langgraph/adapters/json_plan.py`
- skill 目录静态分析：`src/prompt2langgraph/adapters/skill_dir.py`
- 校验入口：`src/prompt2langgraph/validate/validator.py`
- LangGraph 编译：`src/prompt2langgraph/compiler/langgraph_py.py`
- 本地运行：`src/prompt2langgraph/runtime/runner.py`
- CLI：`src/prompt2langgraph/cli.py`

## 开发命令

```bash
uv sync
uv run pytest
uv run pt2lg validate tests/fixtures/linear_llm.json --json
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
uv run pt2lg run tests/fixtures/linear_llm.json --input '{"question":"hello"}' --json
uv run pt2lg graph tests/fixtures/linear_llm.json --format mermaid
```

## 实现约束

- CLI 导入必须保持轻量：`prompt2langgraph.cli` 不应在模块导入阶段急切导入 `langgraph`，相关测试在 `tests/test_cli.py`。
- 新增 IR 字段时，同步更新 Pydantic 模型、规范化、校验、编译/运行边界、测试夹具和文档。
- 新增节点或 executor 时，通过 registry 定义契约，并补充校验和运行测试；内置 executor 必须保持确定性，不能隐式调用外部 LLM 或网络。
- side effect 节点默认必须要求审批或幂等键，除非 workflow policy 显式允许副作用。
- `compile_workflow_to_graph()` 当前支持 linear、conditional、loop、fanout；`run_workflow()` 的目标能力检查当前只允许 linear、conditional，本地 CLI run 不应宣称支持 loop/fanout。
- 条件表达式只支持 `<state_key> <comparison> <literal>`，比较符为 `< <= > >= == !=`。

## 测试要求

- 修改行为前先阅读对应测试；新增行为必须补充或更新 `tests/`。
- 至少运行 `uv run pytest`。
- 若只修改文档，可以用 `uv run pytest` 做回归确认；如因环境无法运行，最终说明原因。


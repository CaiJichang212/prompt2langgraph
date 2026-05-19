# prompt2langgraph examples

这些示例面向 CLI 和 public API 的本地确定性能力，不会调用外部 LLM、网络服务或 shell 命令。

## 目录

- `linear_research/`: 多节点线性链，演示 `retriever -> transform -> llm` 和 `artifact_ref` 状态传递。
- `conditional_human_gate/`: 条件路由和 `human_gate` interrupt/resume。
- `fanout_map_reduce/`: fanout map/reduce 和 `append` reducer。
- `invalid/`: 常见非法 workflow，用于观察结构化诊断。

## 常用命令

```bash
uv run pt2lg validate tests/examples/linear_research/workflow.json --json
uv run pt2lg run tests/examples/linear_research/workflow.json --input tests/examples/linear_research/input.json --json
uv run pt2lg graph tests/examples/fanout_map_reduce/workflow.json --format mermaid
uv run pt2lg compile tests/examples/conditional_human_gate/workflow.json --out build --json
```

# Linear Research

多节点线性链示例：

```text
retrieve -> prepare_context -> compose
```

`retrieve` 使用内置 mock retriever 产生 `docs_ref: artifact_ref`，`prepare_context` 将引用转入字符串上下文，`compose` 使用确定性 mock LLM 生成答案。

运行：

```bash
uv run pt2lg validate tests/examples/linear_research/workflow.json --json
uv run pt2lg run tests/examples/linear_research/workflow.json --input tests/examples/linear_research/input.json --json
uv run pt2lg compile tests/examples/linear_research/workflow.json --out build --json
uv run pt2lg run build/linear_research/workflow.lock.json --input tests/examples/linear_research/input.json --json
```

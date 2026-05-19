# Conditional Human Gate

条件路由示例。`confidence < 0.75` 时进入 `human_gate` 并等待 resume；否则直接生成答案。

直接通过路径：

```bash
uv run pt2lg run tests/examples/conditional_human_gate/workflow.json --input tests/examples/conditional_human_gate/input_high_confidence.json --json
```

等待并恢复路径：

```bash
uv run pt2lg compile tests/examples/conditional_human_gate/workflow.json --out build --json
uv run pt2lg run build/conditional_human_gate/workflow.lock.json --input tests/examples/conditional_human_gate/input_low_confidence.json --json
uv run pt2lg resume build/conditional_human_gate/workflow.lock.json --thread-id '<thread_id>' --resume tests/examples/conditional_human_gate/resume_approved.json --json
```

低置信度 run 会返回 `status: "waiting"` 和 `thread_id`。CLI 会用非 0 退出码表示当前 run 尚未完成；使用返回的 `thread_id` 执行 resume 后会完成 workflow。

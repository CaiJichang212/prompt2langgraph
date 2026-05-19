# Fanout Map Reduce

fanout 示例。`start` 保留输入数组，`process_item` 对每个 item 运行一次，并通过 `results` 上的 `append` reducer 聚合输出。

运行：

```bash
uv run pt2lg validate tests/examples/fanout_map_reduce/workflow.json --json
uv run pt2lg run tests/examples/fanout_map_reduce/workflow.json --input tests/examples/fanout_map_reduce/input.json --json
uv run pt2lg graph tests/examples/fanout_map_reduce/workflow.json --format mermaid
```

# Invalid Workflows

这些示例用于观察 validator 的结构化诊断。

```bash
uv run pt2lg validate tests/examples/invalid/unknown_node.json --json
uv run pt2lg validate tests/examples/invalid/type_mismatch.json --json
uv run pt2lg validate tests/examples/invalid/join_edge.json --json
```

预期：

- `unknown_node.json`: 未注册 node kind，返回 `E_DEP_004`。
- `type_mismatch.json`: state 类型与 executor schema 不兼容，返回 `E_TYPE_003`。
- `join_edge.json`: IR 可建模但当前 langgraph target 不支持执行 join edge，compile/run 返回 `E_TARGET_009`。

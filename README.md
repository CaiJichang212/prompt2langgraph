# prompt2langgraph

Compile validated Workflow IR and simplified JSON plans into deterministic LangGraph Python workflows.

## Install

```bash
uv sync
```

## Test

```bash
uv run pytest
```

## Validate

```bash
uv run pt2lg validate tests/fixtures/linear_llm.json --json
```

## Compile

```bash
uv run pt2lg compile tests/fixtures/linear_llm.json --out build --json
```

## Run From Lockfile

```bash
uv run pt2lg run build/linear_llm/workflow.lock.json --input '{"question":"hello"}' --json
```

## Render Graph

```bash
uv run pt2lg graph build/linear_llm/workflow.lock.json --format mermaid --json
```

## Safety

The compiler and runner do not call LLMs, execute skill scripts, or run arbitrary shell commands. Builtin test executors are deterministic.

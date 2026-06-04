# prompt2langgraph v0.3 第一期实施计划文档

## 1. 文档目的

本文档用于定义 `prompt2langgraph` v0.3 第一期的工程实施计划，作为后续任务拆分、代码实现、测试验收和文档同步的依据。

本文档是项目级实施计划，不是 agent 执行脚本。它描述目标、范围、模块任务、行为契约和验收标准；不内嵌完整测试函数、完整 helper 实现或逐行代码补丁。若后续需要自动化 coding agent 执行，可另行生成细粒度执行计划，并放在 `docs/superpowers/plans/` 下。

---

## 2. 阶段定位

v0.3 第一期对应《prompt2langgraph v0.3 开发计划文档》中的 **Plan 语义保真闭环**。

当前代码已经支持部分评估报告中曾列为缺口的能力：

- `state_schema.reducers` 可进入 `WorkflowSpec.state_schema.reducers`。
- `policies` 可进入 `WorkflowSpec.policies`。
- edge 级 `join_sources` 可进入 `EdgeSpec.join_sources`。
- join 已支持编译与运行，但需要正确声明 `join_sources`；fanout/reduce 场景还需要 reducer。

第一期不重复建设这些已完成能力，而是补齐剩余字段和验收闭环：

- 显式 `workflow_id` 优先于 `name` 派生 ID。
- 顶层 `metadata` 进入 `WorkflowSpec.metadata`。
- 顶层 `reducers` 作为 `state_schema.reducers` 的兼容别名；当两者冲突时解析直接失败。
- Prompt planner / Skill planner 的输出 schema 与 adapter 实际能力一致。
- JSON plan 的 fanout、join、security 场景具备 validate / compile / run smoke 回归。
- README、AGENTS、CLAUDE、测试语料说明与源码行为一致。

---

## 3. 阶段目标

第一期目标是：

**让 Prompt、Skill 或 LLM 生成的简化 JSON plan 与当前 WorkflowSpec IR 已支持的语义保持一致，补齐剩余字段缺口，并建立防回归验收。**

完成后，用户从 Prompt、Skill 或手写 JSON plan 进入系统时，不应因为 adapter 字段丢失或文档/提示词过期而误判 fanout、join、policy、metadata 等能力边界。

---

## 4. 纳入范围

第一期纳入以下范围：

1. `JSONPlanAdapter` 字段保真：
   - 显式 `workflow_id`。
   - 顶层 `metadata`。
   - 顶层 `reducers` 兼容入口。
   - `state_schema.reducers`、`policies`、`join_sources` 防回归测试。

2. JSON plan 运行 smoke：
   - 至少覆盖一个 fanout/reducer 可运行 JSON plan。
   - 至少覆盖一个 join 可运行 JSON plan。
   - 保持 `tests/prompts_skills_test` 语料离线、确定性、无网络访问。

3. Prompt/Skill schema 对齐：
   - Prompt planner 的系统提示词描述当前 JSON plan 字段。
   - Skill planner 的输出格式、约束和 few-shot 示例描述当前 JSON plan 字段。
   - fanout 必须声明 reducer，join 必须声明 `join_sources`，真实 LLM/tool 必须声明 policy。

4. 文档一致性：
   - README、AGENTS、CLAUDE、`tests/prompts_skills_test/README.md` 与源码行为一致。
   - 不再宣称 join 不可执行。
   - 不再宣称简化 JSON plan 无法表达 reducer。
   - `LANGCHAIN_TOOL` 继续标记为 reserved/experimental，不作为第一期可执行能力。

---

## 5. 排除范围

第一期不纳入以下内容：

- Prompt parser repair attempts。
- 统一 planning pipeline 结果模型。
- CLI tool registry 加载。
- RetryPolicy 运行语义。
- side-effect idempotency 或 audit log。
- runtime config bundle。
- `LANGCHAIN_TOOL` 端到端执行。
- Web UI、MCP、YAML、子图、多后端编译等 v0.5+ 能力。

---

## 6. 行为契约

### 6.1 `workflow_id`

JSON plan 可显式声明 `workflow_id`。

行为要求：

- 提供 `workflow_id` 时，adapter 使用该值。
- 未提供 `workflow_id` 时，保持现有行为：由 `name` slug 化生成。
- 显式 `workflow_id` 必须是有效标识符。
- 非法 `workflow_id` 返回稳定 adapter diagnostic，路径指向 `workflow_id`。

### 6.2 `metadata`

JSON plan 可声明顶层 `metadata`。

行为要求：

- `metadata` 必须是 object。
- 合法 `metadata` 原样进入 `WorkflowSpec.metadata`。
- 非 object 值返回稳定 adapter diagnostic，路径指向 `metadata`。
- 不在 metadata 中写入真实 secret；测试应覆盖非对象错误，不引入 secret fixture。

### 6.3 `reducers`

JSON plan 支持两种 reducer 写法：

- 首选：`state_schema.reducers`。
- 兼容：顶层 `reducers`。

行为要求：

- 只有 `state_schema.reducers` 时，保持当前行为。
- 只有顶层 `reducers` 时，映射到 `StateSchema.reducers`。
- 两者同时存在且内容一致时，通过。
- 两者同时存在且内容不同，返回稳定 adapter diagnostic，路径指向 `reducers`。
- 不新增新的 reducer 名称；仍使用 `ReducerName` 枚举。

### 6.4 `join_sources`

edge 级 `join_sources` 已经进入 `EdgeSpec.join_sources`。第一期只做防回归和文档同步。

行为要求：

- join edge 必须声明 `join_sources`。
- `join_sources` 必须是字符串列表。
- join 语义错误继续由现有 `validate.join_check` 负责。
- 文档明确 join 已可执行，但需 `join_sources`；fanout/reduce 场景还需 reducer。

### 6.5 Prompt/Skill 输出 schema

Prompt planner 和 Skill planner 应指导模型输出当前 adapter 支持的字段：

- `workflow_id`
- `metadata`
- `inputs`
- `outputs`
- `state_schema.reducers`
- 兼容顶层 `reducers`
- `policies`
- edge 级 `join_sources`

提示词应明确：

- 首选 `state_schema.reducers`。
- 顶层 `reducers` 只是兼容别名。
- fanout 的 `map.result_state_key` 必须有 reducer。
- join edge 必须有 `join_sources`。
- 真实 LLM executor 需要 `policies.external_call=true` 和 `allowed_models`。
- Python callable tool executor 需要 `allowed_tool_refs`。

---

## 7. 模块任务

### 7.1 JSONPlanAdapter 字段保真

涉及文件：

- `src/prompt2langgraph/adapters/json_plan.py`
- `tests/test_json_plan_adapter.py`

实施内容：

- 增加显式 `workflow_id` 解析。
- 增加 `metadata` object 映射。
- 增加顶层 `reducers` 到 `state_schema.reducers` 的兼容映射。
- 顶层与 `state_schema.reducers` 冲突时直接失败，返回 `path="reducers"` 的稳定诊断错误。
- 保持 `state_schema.reducers`、`policies`、`join_sources` 现有行为不退化。

测试要求：

- 显式 `workflow_id` 优先于 `name` 派生 ID。
- 缺省 `workflow_id` 时仍由 `name` slug 化。
- 非法 `workflow_id` 有稳定 source/path。
- 合法 `metadata` 进入 `WorkflowSpec.metadata`。
- 非 object `metadata` 有稳定 source/path。
- 顶层 `reducers` 生效。
- 顶层 `reducers` 与 `state_schema.reducers` 一致时通过。
- 两者冲突时直接失败（`AdapterParseError`），路径指向 `reducers`。
- 非法 reducer 名称失败，路径与输入位置一致。

### 7.2 JSON plan smoke 回归

涉及文件：

- `tests/test_json_plan_adapter.py`
- `tests/test_prompt_skill_corpus.py`
- `tests/fixtures/json_plan_fanout_run.json`
- `tests/prompts_skills_test/json_plans/`
- `tests/prompts_skills_test/test_cases.json`

实施内容：

- 新增直接 JSON plan fixture，用于 CLI validate / compile / run smoke。
- 新增或扩展 corpus fixture，覆盖顶层 `reducers` 兼容入口。
- 对可执行 fanout/reducer 和 join JSON plan 做 validate / compile / run smoke。
- 保持 corpus fixture 外层 wrapper 与 CLI 直接输入 fixture 分离，避免把 `{ "json_plan": ... }` wrapper 误传给 CLI。

验收要求：

- Adapter 单测覆盖 run smoke。
- Corpus 测试覆盖新增 top-level reducers fixture。
- CLI smoke 使用 `tests/fixtures/json_plan_fanout_run.json` 这类直接 plan 文件。

### 7.3 Prompt planner schema 对齐

涉及文件：

- `src/prompt2langgraph/prompting/planner.py`
- `tests/test_prompt_planner.py`

实施内容：

- 更新 `SYSTEM_PROMPT` 中的简化 JSON plan schema。
- 增加 `join` edge 和 `join_sources` 说明。
- 增加 `state_schema.reducers`、兼容顶层 `reducers`、`policies`、`metadata`、`workflow_id` 说明。
- 增加真实 LLM/tool policy 约束说明。

测试要求：

- Prompt planner 单测断言提示词包含第一期关键字段和约束。
- 现有 fake model 测试继续通过。

### 7.4 Skill planner schema 对齐

涉及文件：

- `src/prompt2langgraph/prompting/skill_planner.py`
- `tests/test_skill_workflow.py`

实施内容：

- 更新 Skill planner 的 state schema constraints。
- 更新 output format。
- 更新 few-shot 示例。
- 首选 `state_schema.reducers`，保留顶层 `reducers` 兼容说明。
- 对高风险 Skill 仍只生成计划和诊断，不执行脚本。

测试要求：

- Skill planner 单测断言提示词包含第一期关键字段。
- 原有 Skill 转 workflow fake model 测试继续通过。
- `tests/test_prompt_skill_corpus.py` 继续离线通过。

### 7.5 文档一致性修正

涉及文件：

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `tests/prompts_skills_test/README.md`

实施内容：

- 修正 README 中 join 支持状态冲突。
- 更新 JSON plan 适配规则。
- 说明 `workflow_id`、`metadata`、`policies`、`state_schema.reducers`、顶层 `reducers`、`join_sources`。
- 说明 Prompt/Skill 仍只生成简化 JSON plan。
- 说明 `LANGCHAIN_TOOL` 在第一期仍为 reserved/experimental。
- 更新 corpus README 的覆盖范围和运行方式说明。

文档扫描要求：

- 不得再出现“join 不支持执行”的陈旧表述。
- 不得再出现“简化 JSON plan 不提供 reducers 表达”的陈旧表述。
- `LANGCHAIN_TOOL` 若出现，必须标记为 reserved/experimental。

---

## 8. 推荐实施顺序

1. `JSONPlanAdapter` 字段保真与单测。
2. 顶层 `reducers` 兼容与冲突诊断。
3. JSON plan validate / compile / run smoke。
4. Prompt planner schema 对齐。
5. Skill planner schema 对齐。
6. README、AGENTS、CLAUDE、corpus README 同步。
7. 第一阶段完整回归验收。

该顺序先固定 adapter 行为，再更新 Prompt/Skill 生成约束，最后更新文档和门禁，避免提示词或文档领先于实际能力。

---

## 9. 验收命令

### 9.1 单模块验收

```bash
uv run pytest tests/test_json_plan_adapter.py -v
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py -v
uv run pytest tests/test_prompt_skill_corpus.py -v
```

### 9.2 控制流与安全回归

```bash
uv run pytest tests/test_join_execution.py tests/test_security_policy.py -v
```

### 9.3 CLI 与 Public API 回归

```bash
uv run pytest tests/test_public_api.py tests/test_cli.py -v
```

### 9.4 CLI smoke

```bash
uv run pt2lg validate tests/fixtures/json_plan_fanout_run.json --json
uv run pt2lg compile tests/fixtures/json_plan_fanout_run.json --out build --json
uv run pt2lg run build/json_plan_fanout_run/workflow.lock.json --input '{"items":["alpha","beta"]}' --json
```

预期：

- `validate` 返回 `ok: true`。
- `compile` 生成 `build/json_plan_fanout_run/` bundle。
- `run` 返回 `status: "succeeded"`，输出包含 `results`。

### 9.5 全量回归

```bash
uv run pytest
```

---

## 10. 完成定义

第一期完成时必须满足：

1. JSON plan 显式 `workflow_id` 生效。
2. JSON plan `metadata` 进入 `WorkflowSpec.metadata`。
3. 顶层 `reducers` 兼容入口生效。
4. `state_schema.reducers`、`policies`、`join_sources` 既有能力保持回归通过。
5. fanout/reducer 和 join JSON plan 可 validate / compile / run smoke。
6. Prompt planner 和 Skill planner 的输出 schema 与 adapter 能力一致。
7. README、AGENTS、CLAUDE、corpus README 与源码行为一致。
8. 默认测试不访问网络。
9. 全量 `uv run pytest` 通过。

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 顶层 `reducers` 与 `state_schema.reducers` 冲突 | 用户计划语义不明确 | 明确失败，返回 `path="reducers"` 的稳定 diagnostic |
| 文档或提示词超前于 adapter 能力 | Prompt/Skill 输出无法执行 | 先改 adapter 和测试，再改提示词和文档 |
| corpus wrapper 被误用于 CLI smoke | CLI 输入格式不匹配 | 单独创建 `tests/fixtures/json_plan_fanout_run.json` 直接 plan fixture |
| join 文档状态再次漂移 | 用户误判控制流能力 | README、AGENTS、CLAUDE、corpus README 同步扫描 |
| 默认测试引入外部调用 | 回归不稳定 | 第一阶段所有新增测试使用 builtin/fake/offline fixture |

---

## 12. 后续衔接

第一期完成后，第二期可以在稳定 JSON plan 语义基础上继续推进：

- parser 鲁棒性增强。
- planning pipeline 统一结果模型。
- repair attempts。
- Prompt/Skill corpus 质量指标。

第三期再推进：

- CLI tool registry。
- RetryPolicy 运行语义。
- side-effect idempotency 和 audit。
- 最小 runtime config bundle。

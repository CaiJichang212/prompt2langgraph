# prompt2langgraph v0.3 开发计划文档

## 1. 文档目的

本文档用于定义 `prompt2langgraph` v0.3 的项目级开发计划，作为后续实施计划、任务拆分、测试验收和文档同步的上位输入。

本文档以当前代码和测试为基础，吸收以下评估报告结论：

- `docs/evaluate-report/prompt2langgraph目标差距评估报告-2026-06-01-合并版.md`
- `docs/evaluate-report/prompt2langgraph目标差距评估报告-2026-06-01-codex.md`

本文档聚焦 **目标差距闭环优先**，不展开到文件级修改步骤、具体代码实现或提交粒度。后续如需执行，应基于本文档再拆分实施计划。

---

## 2. 项目目标与当前判断

`prompt2langgraph` 的目标是：将用户输入的 Prompt、Skills、LLM 生成的 JSON plan 或规范 Workflow IR，编译为可验证、可运行、可恢复、可观测的 LangGraph Python 图。

截至 2026-06-01，项目已经具备较成熟的 IR-first 本地工作流内核：

- 规范 Workflow IR 和简化 JSON plan 可以进入 `validate / compile / run / resume / graph / bundle` 主链路。
- Workflow IR、registry、validator、compiler、runner、artifact、Mermaid 等核心模块已经形成稳定边界。
- 测试基线健康，评估报告记录全量测试 `366 passed`，覆盖率 `89.32%`，高于当前覆盖率门槛；实际开发中应以最新 `uv run pytest` 结果为准。
- `tests/prompts_skills_test` 已经形成离线 prompt、Skill、JSON plan、负向用例语料，可作为 v0.3 的主要验收基础。

但按目标衡量，项目仍然更接近“确定性 Workflow IR 编译与本地执行内核”，尚未达到“Prompt/Skill-first 可稳定生成并执行 LangGraph 图”的阶段。v0.3 应把重心放在目标链路中最短板的位置，而不是继续横向扩展生态能力。

---

## 3. v0.3 总体定位

v0.3 的总体定位是：

**把 Prompt / Skill / JSON plan 输入从 alpha 入口推进为可诊断、可修复、可验收的端到端工作流生成与执行链路。**

v0.3 不把重点放在新增大量节点类型、Web UI、多后端编译或复杂生态集成，而是集中补齐评估报告中的 P0/P1 差距：

1. JSON plan 到 Workflow IR 的语义保真。
2. Prompt/Skill planning 的解析、校验、修复和评估闭环。
3. CLI tool registry 与 Skill tool 执行闭环。
4. `RetryPolicy`、side-effect idempotency、metrics、audit、bundle runtime config 等已暴露能力的运行语义。
5. 文档一致性、测试语料、benchmark 和工程门禁。

v0.3 的目标不是“一次性生产级平台化”，而是让项目从“IR/plan 编译工具包”升级为“Prompt/Skill 可以较稳定生成、校验、编译并受控运行 LangGraph 图的工具链”。

---

## 4. 评估报告结论吸收

### 4.1 需要优先解决的核心差距

评估报告对以下缺口形成共识：

| 主题 | 当前状态 | v0.3 处理方式 |
|---|---|---|
| JSON plan 语义保真 | 当前代码已支持 `state_schema.reducers`、`policies`、edge 级 `join_sources`；剩余缺口集中在显式 `workflow_id`、`metadata`、顶层 `reducers` 兼容、端到端 run smoke 和文档一致性 | 作为第一期核心任务 |
| Prompt/Skill planning 不稳定 | 依赖 LLM 单次输出 JSON，parser 鲁棒性有限，缺少 repair 和质量指标 | 作为第二期核心任务 |
| Skill/tool 执行闭环不足 | Python API 可注入工具，但 CLI registry 为空；Skill 不产生可执行 tool 注册体验 | 作为第三期核心任务 |
| 已建模运行语义未完全兑现 | 3B 已补齐 `RetryPolicy`、side-effect idempotency、metrics、audit 的最小运行语义；3C 已补齐最小 runtime config bundle 与 secret-free runtime requirements；`LANGCHAIN_TOOL` 当前仍为保留枚举 | 第三期只做最小运行语义；`LANGCHAIN_TOOL` 在 v0.3 标记为 reserved/experimental，不实现端到端执行 |
| 生产化与工程门禁不足 | bundle 偏骨架，benchmark 和观测指标不足，部分文档与源码演进不同步 | 第三期只交付最小 runtime config、benchmark 门禁说明和文档一致性；完整可部署 bundle 推迟到 v0.5+ |

### 4.2 v0.3 优先级原则

v0.3 采用以下优先级原则：

1. **先补输入语义，再补生成鲁棒性，最后补执行治理。**
2. **先保证离线确定性验收，再引入真实外部调用验收。**
3. **Prompt/Skill 只能生成计划，不能绕过 adapter、validator、policy、binding 和 compiler。**
4. **真实 LLM/tool/side-effect 执行必须显式授权、白名单控制、可诊断、可审计。**
5. **不把 v0.5+ 的生态扩展提前混入 v0.3 主线。**

---

## 5. v0.3 纳入范围

v0.3 纳入以下范围：

1. 增强 `JSONPlanAdapter` 剩余语义，补齐显式 `workflow_id`、`metadata`、顶层 `reducers` 兼容，并保持 `state_schema.reducers`、`policies`、`join_sources` 的回归覆盖。
2. 对齐 Prompt planner、Skill planner 的输出 schema 与 JSON plan adapter 的实际能力。
3. 增强 Prompt parser，支持常见 LLM 输出格式，并提供结构化 parse diagnostics。
4. 建立 `generate -> parse -> adapt -> validate -> compile` 的统一 planning pipeline 诊断。
5. 支持可配置的 planning repair attempts，把 parse/adapter/validation 诊断反馈给模型进行修复。
6. 用 `tests/prompts_skills_test` 建立 Prompt/Skill/JSON plan 离线评估指标和回归套件。
7. 定义并实现 CLI tool registry 加载的最小安全模型，v0.3 默认采用 `--tool-module` 入口。
8. 让 Skill 计划产物可以声明 required tool refs、风险提示和注册状态。
9. 补齐 `RetryPolicy` 的最小运行时语义。
10. 增强 side-effect idempotency、approval/audit 和 metrics 的最小基础能力。
11. 将 bundle 从本地审计骨架推进到最小可配置 runtime artifact；完整部署型 bundle 推迟到 v0.5+。
12. 修正文档一致性问题，并补充 benchmark 与工程门禁说明。

---

## 6. v0.3 排除范围

v0.3 不纳入以下内容：

- Web UI、Human-in-the-Loop 管理界面或可视化编辑器。
- MCP 工具生态集成。
- YAML 输入格式。
- 子图 / 嵌套 Workflow。
- LangGraph.js、LCEL 或其他多目标编译后端。
- 完整进程沙箱、网络隔离、CPU/内存限制和容器化执行环境。
- 完整 SecretManager / vault 集成。
- Time Travel Debugging 产品化界面。
- OpenAPI 服务化部署层。
- Agent / tool-calling loop 通用框架。
- 非 OpenAI-compatible provider 的完整多供应商适配。
- 大规模分布式调度、并行度调度和资源编排。

这些能力可以进入 v0.5+ 路线图，但不作为 v0.3 的完成标准。

---

## 7. 三期开发划分

v0.3 分为三期推进：

1. **第一期：Plan 语义保真闭环**
2. **第二期：Prompt/Skill 生成可靠性闭环**
3. **第三期：可执行与治理闭环**

三期之间存在明确依赖关系：第一期先保证 JSON plan 能表达完整工作流语义；第二期再提升 LLM 生成该语义的成功率；第三期把生成出的动态 LLM/tool/side-effect workflow 推进到可受控执行、可审计、可验收。

---

## 8. 第一期：Plan 语义保真闭环

### 8.1 阶段目标

第一期目标是：

**让 Prompt、Skill 或 LLM 生成的简化 JSON plan 与当前 WorkflowSpec IR 已支持的语义保持一致，补齐剩余字段缺口，并建立防回归验收。**

第一期完成后，JSON plan 应能表达当前 IR 和 compiler 已经支持的核心语义。当前已支持的 `state_schema.reducers`、`policies`、edge 级 `join_sources` 应作为回归能力保留；v0.3 第一阶段重点补齐显式 `workflow_id`、`metadata`、顶层 `reducers` 兼容和端到端 run smoke。

### 8.2 主要任务

#### 8.2.1 JSON plan 字段保真与回归

先明确当前已具备的能力：

- `state_schema.reducers` 可进入 `StateSchema.reducers`。
- `policies` 可进入 `WorkflowSpec.policies`。
- edge 级 `join_sources` 可进入 `EdgeSpec.join_sources`。

v0.3 第一期应补齐以下剩余字段与兼容入口：

- 顶层 `workflow_id` 应优先于 `name` 派生 ID；缺省时继续保持 `name` slug 兼容行为。
- 顶层 `metadata`。
- 顶层 `reducers` 作为 `state_schema.reducers` 的兼容别名；当两者同时存在且内容不同，`JSONPlanAdapter` 直接失败并返回 `path="reducers"` 的稳定诊断错误（`AdapterParseError`）。
- 与当前 IR 兼容的 loop guard、fanout map、condition routes。
- fanout/join/security plan 的 validate、compile、run smoke fixtures。

字段映射应遵循当前 Pydantic IR 模型，不引入第二套 plan-only 语义。

#### 8.2.2 Prompt/Skill schema 对齐

更新 Prompt planner 和 Skill planner 的输出约束，使模型提示、few-shot 示例、测试 fixtures 与 adapter 支持字段一致。

重点包括：

- fanout 必须声明 reducer。
- join edge 必须声明 `join_sources`。
- 真实 LLM 节点必须通过 `policies.external_call` 和 `allowed_models` 显式授权。
- tool 节点必须通过 `allowed_tool_refs` 显式授权。
- side_effect 节点必须声明 approval 或 idempotency 策略。

#### 8.2.3 Source map 与诊断定位

明确 `adapters/source_map.py` 的定位：

- 如果保留，应将 JSON plan 字段映射到 adapter diagnostics 或 validation diagnostics。
- 如果暂不作为正式能力，应在文档中标记为 internal/experimental，并避免对外承诺。

第一期不要求实现完整源代码级定位，但应避免关键 adapter 错误缺乏来源信息。

#### 8.2.4 文档一致性修正

同步修正文档中与当前代码冲突的描述，特别是 join 支持状态。

文档应明确：

- canonical Workflow IR 与 JSON plan 的支持边界。
- Prompt/Skill 只生成简化 JSON plan，不直接执行 workflow。
- `LANGCHAIN_TOOL` 若未完整实现，应标记为 reserved/experimental。
- CLI tool registry 在第三期前仍属于待补齐能力。

### 8.3 验收标准

第一期完成时，应满足：

- JSON plan 顶层 `workflow_id` 生效，并保持缺省时由 `name` 派生的兼容行为。
- JSON plan `metadata` 进入 `WorkflowSpec.metadata`。
- JSON plan `state_schema.reducers`、`policies.external_call`、`allowed_models`、`allowed_tool_refs`、`join_sources` 保持回归通过。
- JSON plan 顶层 `reducers` 兼容入口生效；与 `state_schema.reducers` 冲突时直接失败，并返回 `path="reducers"` 的稳定诊断错误。
- Prompt/Skill fake model 输出 fanout/join/security plan 后可进入 validate/compile/run smoke。
- 文档中的 join、Prompt、Skill、tool 描述与源码行为一致。

建议验收命令：

```bash
uv run pytest tests/test_json_plan_adapter.py -v
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py -v
uv run pytest tests/test_join_execution.py tests/test_security_policy.py -v
uv run pytest tests/test_prompt_skill_corpus.py -v
uv run pytest
```

---

## 9. 第二期：Prompt/Skill 生成可靠性闭环

当前实现状态：第二期规划链路已落地到 `prompting/pipeline.py`、CLI `pt2lg plan` 和离线 corpus 测试。兼容入口仍保持旧语义；结构化入口和 CLI 可显式返回 validation、compile smoke 与 repair attempts 摘要。

### 9.1 阶段目标

第二期目标是：

**把 Prompt/Skill planning 从“LLM 单次 JSON 输出成功才可用”提升为“可解析、可诊断、可修复、可度量”的规划链路。**

第二期不是追求任意自然语言都能完美生成 workflow，而是建立可测试、可度量、可持续改进的 planning 机制。

### 9.2 主要任务

#### 9.2.1 Parser 鲁棒性增强

增强 Prompt/Skill planner 输出解析，支持常见 LLM 输出形态：

- 纯 JSON object。
- Markdown fenced JSON block。
- 文本说明中包含单个 JSON object。
- 前后带解释文本的 JSON。
- 可明确诊断的非 JSON、非对象、截断 JSON、多个候选 JSON。

parser 不应静默猜测复杂冲突输出。无法确定唯一 plan 时，应返回结构化 diagnostic。

实现状态：`parse_prompt_plan_text()` 已支持纯 JSON object、Markdown fenced JSON block、解释文本中的唯一 JSON object 和 JSON 后缀文本；多个 JSON object 候选、非对象、截断 JSON 和非法 JSON 会稳定抛出 `AdapterParseError`。

#### 9.2.2 统一 planning pipeline

建立统一的 planning pipeline 概念：

```text
prompt / skill
  -> generate json plan text
  -> parse
  -> adapt to WorkflowSpec
  -> validate
  -> compile smoke
  -> structured result
```

该 pipeline 应返回清晰阶段状态：

- generation 成功或失败。
- parse 成功或失败。
- adapter 成功或失败。
- validation 成功或失败。
- compile smoke 成功或失败。
- diagnostics 列表。
- repair attempts 摘要。

实现状态：`plan_prompt()` / `plan_skill()` 返回 `PlanningPipelineResult`，包含 `raw_text`、`plan`、`workflow`、`validation_report`、`diagnostics`、`stages` 和 `repair_attempts`。`compile_smoke` 只做内存编译检查，不写 bundle、不执行 workflow。

#### 9.2.3 Repair attempts

引入可配置 repair attempts：

- 默认离线测试仍使用 deterministic fake model。
- repair 次数必须可配置，默认保持保守。
- repair prompt 只能包含必要的 parse/adapter/validation diagnostics、原始 plan 摘要和目标 schema 约束。
- repair 结果仍必须重新进入 parse/adapt/validate/compile 链路。
- repair 失败时返回最后一次诊断，不隐式降级为执行。

实现状态：`PromptPlanRequest` 和 `SkillPlanRequest` 已提供 `repair_attempts: int = 0`（范围 `0..3`）；CLI 提供 `--repair-attempts`，默认关闭。repair 会重新进入 parse、adapter、validation、compile smoke 链路。

#### 9.2.4 Prompt/Skill corpus 评估

基于 `tests/prompts_skills_test` 建立评估指标：

| 指标 | 含义 | v0.3 初始目标 |
|---|---|---:|
| prompt parse success | Prompt fake/live 输出可解析为 JSON object | 离线 100%，live 目标不低于 90% |
| prompt validation success | Prompt plan 可通过 validate | 离线 100%，live 目标不低于 75% |
| skill parse success | Skill fake/live 输出可解析为 JSON object | 离线 100%，live 目标不低于 80% |
| skill validation success | Skill plan 可通过 validate | 离线 100%，live 目标不低于 60% |
| compile smoke success | 验证通过的 plan 可完成 compile smoke | 离线 100% |

v0.3 发布门禁以离线指标为准。live 指标不进入默认单测，不依赖网络调用；只作为手动或显式启用的评估报告。live 评估必须记录模型、`BASE_URL` 类型、样本集版本、执行命令、成功率和失败诊断摘要，避免把不可重复的外部模型波动作为默认质量门禁。

实现状态：`tests/test_prompt_skill_corpus.py` 已用 fake model 覆盖 prompt、Skill、JSON plan 和 negative cases 的离线 pipeline 指标；测试显式注入 corpus executor registry，避免 corpus-only refs 被默认 registry 误判。

#### 9.2.5 Skill 风险诊断接入

Skill planning 应保留静态分析风险信息：

- shell 执行。
- 文件写入。
- 网络访问。
- secret 相关文本。
- 外部资源引用。

这些风险不应自动执行，而应进入 diagnostics、metadata、security policy 建议或 required approval 提示。

实现状态：`plan_skill()` 会保留 `analyze_skill_dir()` 的静态 diagnostics；error 级静态诊断会阻止 generation，warning/info 级诊断进入 planning result。

### 9.3 验收标准

第二期完成时，应满足：

- parser 覆盖 fenced JSON、解释文本包裹 JSON、非对象输出、非法 JSON 输出。
- planning pipeline 能区分 parse、adapter、validation、compile smoke 阶段失败。
- repair attempts 可配置、可测试、可关闭。
- `tests/prompts_skills_test` 的 prompt、Skill、JSON plan、negative cases 都能进入统一评估口径。
- Skill 风险诊断能在 planning result 中保留。
- 默认测试不访问网络。

建议验收命令：

```bash
uv run pytest tests/test_prompt_parser.py -v
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py -v
uv run pytest tests/test_prompt_skill_corpus.py -v
uv run pytest tests/test_public_api.py tests/test_cli.py -v
uv run pytest
```

---

## 10. 第三期：可执行与治理闭环

### 10.1 阶段目标

第三期目标是：

**让 Prompt/Skill 生成出的 workflow 不只停留在可编译图，而是能够在明确授权、安全边界和最小观测机制下受控执行。**

第三期重点处理公开 API 和 IR 已经暴露但运行语义不足的能力，避免用户看到字段或 executor 类型后产生错误预期。第三期不追求一次完成完整生产化 bundle、完整审计平台或完整沙箱，而是拆成 3A/3B/3C 三个可独立验收的小闭环。

### 10.2 主要任务

#### 10.2.1 3A：CLI tool registry 加载

定义并实现 CLI tool registry 的最小安全加载机制。

当前实现状态：3A 已落地到 CLI `run` / `resume`。CLI 会先加载 `--tool-module`、构造 `ToolCallableRegistry`、合成动态 `ExecutorDefinition(type=PYTHON_CALLABLE)`，再解析 Workflow IR 或简化 JSON plan，并把同一 executor registry 与 tool registry 传给校验和运行链路。

v0.3 正式入口采用：

- `--tool-module <module>`：从受控 Python module 加载注册函数。
- 模块必须暴露 `register_tools(registry)` 函数，并只通过 `ToolCallableRegistry.register(ref, callable)` 注册工具。

`--tool-registry <json>` 不作为 v0.3 正式入口，可作为 v0.5+ 配置化扩展。v0.3 入口必须满足：

- tool ref 必须与 `allowed_tool_refs` 白名单匹配。
- 未注册 tool、未授权 tool、schema 不匹配 tool 均返回稳定 diagnostic。
- 默认 CLI 不加载任意工具。
- 不支持任意 shell 命令执行。
- 不在 manifest、compile report、diagnostics 中写入 secret。
- tool ref 不允许重复注册，也不允许覆盖内置或既有 executor ref。

#### 10.2.2 Skill required tool refs

Skill planning 产物应能声明 required tool refs 和注册状态：

当前实现状态：3A 已在 `PlanningPipelineResult.tool_readiness` 中提供结构化摘要，并在 CLI `pt2lg plan --json` 中输出。该摘要只作为报告字段，不替代 `validate_workflow()` 的安全策略检查。

- workflow 中实际使用的 tool executor refs。
- policy 中允许的 tool refs。
- CLI/runtime 中已注册的 tool refs。
- 缺失或未授权 refs。
- 高风险 Skill 步骤对应的 approval 或 side_effect 建议。

该能力用于把 Skill 从“结构化计划”推进到“可执行前可检查”的状态。

#### 10.2.3 3B：RetryPolicy 执行语义

当前实现状态：3B 已落地最小 wrapper retry。`NodeSpec.retry.max_attempts` 会影响运行时执行；当前只重试 LLM timeout、LLM API timeout/5xx/server failure 和 tool timeout。业务/输入错误、缺失 model/tool client、未授权或未注册 tool、side_effect 拒绝不默认重试。该实现不使用 LangGraph native retry。

实现 `RetryPolicy` 的最小运行时语义：

- 支持 `max_attempts`。
- 明确哪些错误可重试，例如 LLM timeout/5xx、tool timeout。
- 业务校验错误、未授权、未注册工具、side_effect 拒绝不应默认重试。
- side_effect 节点重试必须与 approval/idempotency 绑定，避免重复副作用。
- metrics 中记录 retry count 和最终状态。

v0.3 可以先采用 wrapper retry，不强制依赖 LangGraph 内置 retry 能力。

#### 10.2.4 3B：Side-effect idempotency 与最小 audit

当前实现状态：3B 已落地本地 JSON-backed side-effect idempotency store 和 audit JSONL。成功副作用以 `(workflow_id, thread_id, idempotency_key)` 为作用域记录原始 executor output；重复命中时直接返回已记录 output，不再次调用 executor。`.pt2lg-runtime/audit.log.jsonl` 只写安全元数据，不写 secret、完整 payload、完整模型响应、API key 或敏感 tool 参数。分布式 idempotency storage 和可配置 audit 后端仍不在 v0.3 3B 范围内。

增强 side-effect 的治理能力：

- 定义 idempotency 作用域，优先采用 workflow/thread 范围。
- 在 runtime state 或 checkpoint 可访问位置记录已批准并执行的 idempotency key。
- resume 后不得重复执行已完成的同一 idempotency key。
- 增加 `.pt2lg-runtime/audit.log.jsonl` 或等价可配置 audit sink。
- audit 记录最小字段：`run_id`、`thread_id`、`workflow_id`、`node_id`、`event_type`、`status`、`latency_ms`、`error_code`、`timestamp`。
- audit 不记录真实 secret、完整 API key、完整 input payload、完整 model response 或敏感 tool 参数。

#### 10.2.5 3B：Runtime metrics 与 external calls

当前实现状态：3B 已落地 `RuntimeMetricsCollector` 和 latency-aware `ExternalCallRecord`。`RunMetrics` 汇总 `retry_count`、`tool_call_count`、`call_count`、`total_latency_ms` 和可用 token 摘要；`ExternalCallRecord` 包含 status、latency、attempt 和 category。完整 provider token accounting、dashboard/trace 后端仍未实现。

补齐运行时观测字段：

- per-node latency。
- external call latency。
- retry count。
- tool call count。
- LLM token usage 摘要。
- error category。

不同 provider 的 token usage 格式可以先标准化为可选字段，不要求一次覆盖所有 provider。

#### 10.2.6 3C：最小 runtime config bundle

当前实现状态：3C 已落地最小 runtime config bundle。3B 的 retry、idempotency、audit 和 metrics 仍然只是 runner/compiler 运行时语义；3C 新增的是库内 bundle 的最小可配置入口，不代表独立服务化运行、部署型 runtime artifact 或 secret manager 集成已经可用。

将 bundle 从“本地审计与重新编译骨架”推进到最小可配置 runtime artifact：

- `generated/graph.py` 暴露 `RuntimeConfig`、`build_graph(config=None)` 和 `invoke(input_payload=None, config=None)`。
- 兼容保留 `compile_graph()` 和 `invoke_graph()`，避免破坏既有 generated bundle 入口。
- `RuntimeConfig` 支持注入 `executor_registry`、`model_client`、`tool_registry`、`checkpointer` 和完整 `PolicySpec` 覆盖。
- manifest 输出 secret-free `runtime_requirements`，包括 `model_refs`、`tool_refs`、`checkpoint_required` 和 policy summary。
- 不写入 secret 或 secret 名称。
- 增加动态 LLM/tool workflow 的 golden bundle 测试。
- 当前 bundle 仍不是 deployable service wrapper；完整可部署 bundle、独立服务化运行和 secret manager 集成推迟到 v0.5+。

#### 10.2.7 3C：Benchmark 与工程门禁

当前实现状态：3C engineering gates 已补齐 deterministic compile、bundle load/invoke、dynamic tool、side-effect interrupt/resume 和 offline corpus 等离线门禁；这些门禁用于收口 v0.3 第三期，不代表项目已经具备 standalone deployment bundles、secret manager integration、sandboxing、remote audit services 或 LangChain Tool execution。

补齐可重复 benchmark 和门禁说明：

- 10 节点线性图编译。
- 100 节点线性图编译。
- fanout/join compile smoke。
- prompt/skill corpus offline success rate。
- tool workflow run smoke。
- side-effect interrupt/resume smoke。
- bundle load/invoke smoke。

benchmark 默认不应访问网络。

#### 10.2.8 `LANGCHAIN_TOOL` 决策

`ExecutorType.LANGCHAIN_TOOL` 在 v0.3 不实现端到端执行。v0.3 只做以下处理：

- 在 README、AGENTS、CLAUDE 和 public docs 中标记为 reserved/experimental。
- 在 validator 或 diagnostics 中避免用户误以为该 executor type 已可运行。
- v0.3 的 tool 执行路径明确限定为受信任 Python tool module + `ExecutorType.PYTHON_CALLABLE`。
- 将真正的 LangChain Tool 适配、schema 映射和安全策略设计放入 v0.5+。

### 10.3 验收标准

第三期完成时，应满足：

- 3A 已满足：CLI 可以加载至少一个受控 fake tool registry 并执行 `PYTHON_CALLABLE` tool workflow。
- 3A 已满足：未授权、未注册和 tool module 加载/注册失败均有稳定 diagnostics；tool timeout 与执行异常诊断沿用 `ToolExecutor` 路径。
- 3A 已满足：Prompt/Skill 计划结果能列出 required、allowed、registered、missing 和 unauthorized tool refs。
- `RetryPolicy.max_attempts` 对 LLM/tool wrapper 生效。
- side-effect idempotency 在 resume 场景下不会重复执行。
- audit/metrics 能按最小字段记录关键运行摘要且不泄露 secret 或完整 payload。
- generated bundle 支持最小 runtime config 的 `RuntimeConfig` / `build_graph(config=None)` / `invoke(input_payload=None, config=None)`，并兼容保留 `compile_graph()` / `invoke_graph()`。
- `LANGCHAIN_TOOL` 被明确标记为 reserved/experimental，且不作为 v0.3 可执行能力宣传。
- README、AGENTS、CLAUDE、测试说明与实际行为一致。

建议验收命令：

```bash
uv run pytest tests/test_tool_executor.py tests/test_security_policy.py -v
uv run pytest tests/test_integration_execution.py tests/test_runner.py -v
uv run pytest tests/test_artifacts.py tests/test_bundle_golden.py -v
uv run pytest tests/test_cli.py tests/test_public_api.py -v
uv run pytest tests/test_prompt_skill_corpus.py -v
uv run pytest
uv run python scripts/benchmark_compile.py --nodes 100 --max-seconds 5
```

---

## 11. 测试策略

v0.3 的测试策略分为四层。

### 11.1 单元测试

覆盖 adapter、parser、planner、validator、executor、runtime wrapper 的小边界。

重点文件：

- `tests/test_json_plan_adapter.py`
- `tests/test_prompt_parser.py`
- `tests/test_prompt_planner.py`
- `tests/test_skill_workflow.py`
- `tests/test_security_policy.py`
- `tests/test_tool_executor.py`
- `tests/test_side_effect_executor.py`
- `tests/test_runner.py`

### 11.2 Corpus 测试

以 `tests/prompts_skills_test` 为核心，覆盖：

- Skill -> WorkflowSpec。
- Prompt -> WorkflowSpec。
- JSON plan direct input。
- negative parse/schema/security/registry cases。
- fanout/join、loop、conditional、human_gate、side_effect、reducer 等模式。

Corpus 测试必须保持离线、确定性、无网络访问。

### 11.3 集成测试

覆盖：

- validate -> compile -> run。
- compile artifact -> lockfile run。
- interrupt -> resume。
- dynamic LLM/tool policy 检查。
- generated bundle load/invoke。

真实外部 LLM 调用不进入默认集成测试，只允许显式启用。

### 11.4 回归与门禁

每期完成至少运行：

```bash
uv run pytest
```

涉及 Prompt 入口时额外运行：

```bash
uv run pytest tests/test_prompt_planner.py tests/test_prompt_parser.py tests/test_public_api.py tests/test_cli.py -v
```

涉及 executor dispatch 或策略校验时额外运行：

```bash
uv run pytest tests/test_security_policy.py tests/test_integration_execution.py -v
```

涉及编译产物结构时额外运行：

```bash
uv run pytest tests/test_artifacts.py tests/test_bundle_golden.py tests/test_compile_flow.py -v
```

---

## 12. 安全与权限边界

v0.3 必须保持以下安全边界：

- 默认不隐式调用外部 LLM。
- 默认不加载任意 tool。
- Prompt/Skill 只能生成 plan，不能直接执行 workflow。
- Skill scripts、assets、references 只做静态分析，不自动执行。
- 真实 LLM 调用必须要求 `external_call=True` 和 `allowed_models`。
- Tool 调用必须要求 `allowed_tool_refs` 和已注册 callable。
- Side-effect 默认必须 approval 或 idempotency。
- Retry 不得绕过安全策略，不得放大副作用。
- Manifest、compile report、diagnostics、audit 不得写入真实 secret。
- 网络调用相关验收必须显式启用，不进入默认测试。

---

## 13. 文档同步要求

v0.3 任一期完成后，至少同步以下文档：

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `tests/prompts_skills_test/README.md`
- 对应开发计划或实施计划文档

重点同步内容：

- 支持的输入类型和边界。
- JSON plan schema 能力。
- Prompt/Skill planning 成功与失败语义。
- tool registry CLI 使用方式。
- side-effect approval/idempotency 语义。
- bundle runtime config 语义。
- benchmark 和测试门禁。

---

## 14. 风险与缓解

| 风险 | 影响 | 缓解方式 |
|---|---|---|
| JSON plan schema 扩展破坏旧 fixtures | 现有用户 plan 可能不兼容 | 保持向后兼容，新增字段可选；旧 plan 行为不变 |
| repair attempts 引入不可重复行为 | 默认测试不稳定 | 默认使用 fake model；repair 可关闭；live eval 不进默认测试 |
| tool registry CLI 加载扩大攻击面 | 可能执行非预期代码 | 默认不加载；白名单授权；禁止任意 shell；文档明确可信边界 |
| Retry 放大副作用 | side-effect 可能重复执行 | side-effect retry 必须绑定 idempotency/approval |
| audit/metrics 泄露敏感信息 | secret 或 payload 泄漏 | 增加 secret scan 和脱敏测试 |
| bundle runtime config 过度设计 | 延误核心目标 | v0.3 只做最小 runtime config 与 build/invoke API；完整部署型 bundle 推迟到 v0.5+ |
| 真实 LLM 成功率不可控 | 验收波动 | 默认验收只用离线 corpus，live 指标作为手动评估 |
| `LANGCHAIN_TOOL` 语义悬空 | 用户误以为该 executor type 已可执行 | v0.3 明确标记 reserved/experimental，不纳入可执行验收 |

---

## 15. v0.3 完成定义

v0.3 完成时，应达到以下状态：

1. JSON plan 能完整表达当前 IR 支持的 reducer、policy、metadata、join_sources 等关键语义，并正确处理显式 `workflow_id`。
2. Prompt/Skill planner 输出 schema 与 adapter 能力一致。
3. Prompt/Skill planning 具备 parser 鲁棒性、结构化诊断、repair attempts 和离线评估指标。
4. `tests/prompts_skills_test` 成为 Prompt/Skill/JSON plan 入口的稳定回归语料。
5. CLI 具备最小受控 tool registry 加载能力。
6. Skill 计划结果能声明 required tool refs 和风险提示。
7. `RetryPolicy`、side-effect idempotency、audit、metrics 具备最小运行语义。
8. bundle 具备最小 runtime config 与 build/invoke API，完整部署型 bundle 留到 v0.5+。
9. `LANGCHAIN_TOOL` 被明确标记为 reserved/experimental，不作为 v0.3 可执行能力。
10. README、AGENTS、CLAUDE、测试说明与源码行为一致。
11. 全量测试通过，并保留必要 benchmark 结果。

---

## 16. v0.5+ 路线图储备

v0.3 完成后，后续版本可考虑：

- MCP 工具生态。
- YAML plan 输入。
- 子图 / 嵌套 Workflow。
- Artifact Store。
- Time Travel Debugging。
- HITL Web UI。
- OpenAPI 服务化部署。
- ReactFlow 或其他可视化编辑器导入导出。
- LangGraph.js 或其他多目标编译。
- 更完整的沙箱与资源限制。
- SecretManager / vault 集成。
- 多 provider LLM registry、fallback、负载均衡。
- Agent / tool-calling loop。
- 更丰富的状态类型，如 dataframe、file_ref、http_response、tool_result。

这些能力应在 v0.3 目标闭环稳定后再分阶段设计。

# prompt2langgraph 需求文档 v0.1

## 0. 文档说明

本文档在 `prompt2langgraph需求文档.md` 基础上修订，目标是形成 v0.1 阶段可评审、可拆解、可验收的需求基线。

本版修订参考：

- `docs/pt2lg-task0508.md`
- `docs/pt2lg开源调研与技术架构方案.md`
- `docs/LangGraph/graph-api.md`
- `docs/LangGraph/use-graph-api.md`
- `ref-projects/LLMCompiler`
- `ref-projects/plancompiler`
- `ref-projects/skills-to-dify-workflow`
- `ref-projects/dify-workflow-dsl-skill`
- `ref-projects/langgraph`

当前代码目录 `prompt2langgraph/` 尚未形成源码骨架，因此 v0.1 需求以“从零落地 MVP”为准，不假设已有实现。

## 1. 原文档评审结论

原需求文档方向正确，已经抓住了核心原则：不让 LLM 直接生成自由代码并执行，而是走“源输入 -> IR -> 校验 -> LangGraph 编译 -> 运行”的编译器式路线。

需要改进的点：

1. MVP 范围仍偏宽。`prompt_text`、`skill_dir`、运行时、中断、fan-out、Mermaid、lock、诊断都被列为早期能力，但缺少优先级切分。
2. 需求与架构边界混杂。需求文档中出现较多内部类名和 lowering（降级） 细节，容易让验收标准被实现细节绑死。
3. Skill 编译风险描述不足。`SKILL.md` 常包含开放式自然语言、脚本、引用资料和人工流程，v0.1 不宜承诺完整自动编译。
4. LangGraph 关键约束需要转成需求。动态路由不能和同一节点的静态边混用，`Command(resume=...)` 只用于从 interrupt 恢复，list/message 状态必须有 reducer。
5. 缺少“可拒绝”能力的验收。一个可靠编译器不只要能生成图，还必须能稳定拒绝坏计划，并给出可定位诊断。

v0.1 需求收敛原则：

- 优先支持 `WorkflowIR` 和 `json_plan`。
- `skill_dir` 只做静态预分析；`prompt_text` 属于后续候选输入，不进入当前 release baseline。
- LangGraph Python 是唯一首发执行后端。
- 编译器后端全程确定性，不调用 LLM。
- 任意外部副作用默认不执行，必须显式授权或人工审批。

## 2. 产品定位

prompt2langgraph 是一个面向 LangGraph 的计划编译器。v0.1 release baseline 接收规范 Workflow IR 或简化 JSON plan，转换为可校验的 Workflow IR，再由确定性后端编译为可运行的 LangGraph Python 图；prompt 和技能目录生成可执行 Workflow IR 属于后续阶段。

项目核心价值不是“让 LLM 写 LangGraph 代码”，而是：

```text
不可信输入
-> 受约束候选计划
-> Workflow IR
-> 静态校验、类型检查、安全策略、资源绑定
-> LangGraph StateGraph
-> compile / invoke / stream / interrupt / resume
```

LLM 可以参与候选计划生成，但不能绕过 IR、注册表、校验器和安全策略。

## 3. v0.1 目标

### 3.1 总目标

实现一个最小可用的 Python 包与 CLI，使用户能够从结构化计划生成可编译、可运行、可诊断的 LangGraph Python 图。

### 3.2 v0.1 必须完成

v0.1 必须支持：

- 定义 Pydantic 版 Workflow IR。
- 从 `workflow_ir` 直接编译。
- 从 `json_plan` 规范化为 Workflow IR。
- 维护内置节点注册表和执行器注册表。【内置节点、执行器具体包括那些？2者的区别？】
- 对 IR 做确定性校验，不调用 LLM。
- 编译为 LangGraph Python `StateGraph`。
- 支持线性边和条件边。
- 支持有限循环，必须带 `loop_guard.max_iterations`。
- 支持有限 fan-out/map-reduce，必须声明 reducer。
- 支持 `human_gate` 节点，编译为 LangGraph interrupt 模式。
- 生成 `workflow.lock.json`、`manifest.json`、`compile_report.json`、`graph.mmd`。
- 提供 CLI：`validate`、`compile`、`run`、`graph`。
- 至少一个端到端样例能 `compile()` 并 `invoke()`。

### 3.3 v0.1 可选完成

v0.1 文档中下列能力只作为后续候选方向，不属于当前 release baseline；当前源码没有实现 `prompt_text` 适配器，也不会隐式调用 LLM：

- `SKILL.md` 的保守信息抽取。
- `prompt_text` 调用 LLM 生成 draft plan。
- SQLite checkpointer。
- `stream()` 事件输出。

### 3.4 v0.1 明确不做

v0.1 不做：

- 生产级 Web UI。
- LangGraph.js 后端。
- Dify YAML 后端。
- `prompt_text` 适配器。
- 隐式外部 LLM 调用。
- 任意 Python 代码生成和自动执行。
- 自动运行 skill 目录中的脚本。
- 全自动理解任意自然语言 skill。
- 分布式运行时、任务队列和多租户权限系统。

## 4. 用户与场景

### 4.1 用户

- Agent 应用开发者：把结构化工作流快速转成 LangGraph。
- 平台工程师：需要可治理、可审计、可复现的编译流程。
- Skill 作者：希望评估 `SKILL.md` 能否转为图。
- 研究人员：对比不同 plan 编译策略和 LangGraph 图形态。

### 4.2 场景 A：Workflow IR 编译

用户提供完整 Workflow IR。系统校验后生成 LangGraph bundle。

验收结果：

- 校验通过则产生可编译 bundle。
- 校验失败则返回结构化错误，不生成可运行 bundle。

### 4.3 场景 B：JSON Plan 编译

用户提供简化 JSON plan：

```json
{
  "name": "research_answer",
  "inputs": {"question": "string"},
  "nodes": [
    {"id": "retrieve", "kind": "retriever", "executor": "builtin.mock_retriever"},
    {"id": "answer", "kind": "llm", "executor": "builtin.echo_llm"}
  ],
  "edges": [
    {"from": "retrieve", "to": "answer"}
  ],
  "outputs": {"answer": "string"}
}
```

系统把它规范化为 Workflow IR，并生成可运行 LangGraph 图。

### 4.4 场景 C：拒绝无效计划

计划引用不存在的执行器、存在类型不匹配、循环无上限，或副作用节点没有审批策略。系统必须拒绝执行。

示例诊断：

```text
E_BIND_006: node "send_email" references unregistered executor "mail.send".
E_LOOP_005: edge "retry_search" creates a loop without max_iterations.
E_TYPE_003: edge retrieve -> summarize expects docs_ref, got text.
```

### 4.5 场景 D：人工审批

计划包含 `human_gate` 或高风险副作用。系统编译为 LangGraph interrupt，运行时暂停并返回审批请求。用户通过 resume 继续。

### 4.6 场景 E：Skill 预分析

用户提供 skill 目录。v0.1 的 skill_dir 能力是静态预分析：读取 `SKILL.md` frontmatter、编号步骤、资源文件和风险词，输出分析对象和 draft nodes。v0.1 不从 skill_dir 生成可执行 `WorkflowSpec`，不执行 skill 脚本，也不隐式调用 shell 或网络。

## 5. 输入需求

| 输入 | v0.1 级别 | 说明 |
|---|---:|---|
| `workflow_ir` | P0 | 完整 IR，必须支持 |
| `json_plan` | P0 | 简化结构化计划，必须支持 |
| `tool_registry` | P0 | 工具和执行器注册配置，必须支持 |
| `compile_options` | P0 | 目标、严格模式、安全策略，必须支持 |
| `skill_dir` | P1 | `SKILL.md` 预分析，不执行脚本 |
| `prompt_text` | 后续 P2 | LLM 生成 draft plan，当前 release baseline 不调用外部 LLM |

输入约束：

- 节点 ID 必须唯一且稳定。
- 节点 kind 必须来自节点注册表。
- executor 必须来自执行器注册表或内置执行器。
- 条件必须引用 state 中已声明字段。
- 循环必须声明退出条件和最大迭代次数。
- fan-out 的聚合目标必须声明 reducer。
- 副作用节点必须声明审批、幂等键或显式授权策略。

## 6. 输出需求

### 6.1 编译成功输出

编译成功必须输出：

```text
build/<workflow_id>/
├── workflow.ir.json
├── workflow.lock.json
├── manifest.json
├── compile_report.json
├── graph.mmd
└── generated/
    ├── graph.py
    ├── state.py
    └── nodes.py
```

其中：

- `workflow.ir.json` 是规范化 IR。
- `workflow.lock.json` 是可复现编译锁文件。
- `manifest.json` 记录图入口、节点、边、状态 schema、目标后端和依赖版本。
- `compile_report.json` 记录 warning、error、hash 和编译阶段耗时。
- `graph.mmd` 用于可视化，不作为执行真相源。

### 6.2 运行输出

运行成功输出：

- `run_id`
- `thread_id`
- 最终结果
- 节点事件摘要
- 工具调用摘要
- token、耗时、重试次数
- 中断状态或失败诊断

### 6.3 失败输出

失败输出必须包含：

- 错误码
- severity
- 定位信息：source、node_id、edge_id、state_key、path
- 可读原因
- 建议修复动作
- 是否可重试

## 7. 功能需求

### F1. Workflow IR

系统必须定义稳定 IR，作为所有输入和后端之间的唯一事实来源。

核心对象：

- `WorkflowSpec`
- `StateSchema`
- `TypeSpec`
- `NodeSpec`
- `EdgeSpec`
- `ExecutorRef`【Ref？】
- `PolicySpec`
- `CompileOptions`
- `Diagnostic`

验收标准：

- IR 可 JSON 序列化。
- IR 有 Pydantic 模型和 JSON Schema。
- IR 有 `schema_version`。
- IR 不包含密钥和任意可执行代码。
- 相同 IR 规范化后输出稳定排序。

### F2. JSON Plan Adapter

系统必须把简化 JSON plan 转为 Workflow IR。

验收标准：

- 对合法 JSON plan 生成合法 Workflow IR。
- 对缺失节点、重复 ID、非法边返回结构化诊断。
- 可承载 `conditional.condition`、`loop.loop_guard` 和 `fanout.map` 的边界字段，但不扩展为完整 Workflow IR 表达能力。
- `fanout` 的完整 map-reduce 可执行形态需要 `state_schema.reducers`；简化 JSON plan 当前不表达 reducers，应直接使用 Workflow IR。
- 不调用 LLM。

### F3. Node Registry

系统必须维护节点注册表。Planner 或用户不能发明未注册节点。

节点定义至少包含：

- `kind`【type】
- `description`
- `input_schema`
- `output_schema`
- `param_schema`
- `planner_enabled`
- `side_effect`
- `required_capabilities`【被要求的能力？】
- `default_retry`
- `default_timeout_s`

v0.1 内置节点：

| kind | 说明 |
|---|---|
| `llm` | 调用模型或 mock LLM |
| `tool` | 调用注册工具 |
| `retriever` | 检索文档或知识库 |
| `transform` | 数据转换 |
| `router` | 根据 state 路由 |
| `human_gate` | 人工审批和 interrupt |
| `join` | 分支汇聚 |
| `side_effect` | 外部写操作 |

【内置节点的分类貌似不太合理？】
验收标准：

- 未注册 kind 编译失败。
- deprecated kind 至少给 warning。
- side_effect 默认要求审批或显式授权。

### F4. Executor Registry

系统必须把抽象节点绑定到真实执行器。

v0.1 支持：

- `builtin`
- `python_callable`
- `langchain_tool`
- `llm`
- `human`

v0.1 执行边界：Executor Registry 可以表达 `builtin`、`python_callable`、`langchain_tool`、`llm`、`human` 类型，但 v0.1 内置 runner 只执行已注册的 deterministic builtin executor。非 builtin executor type 在 v0.1 中属于绑定/治理契约，不代表 runner 会隐式调用外部 LLM、网络服务、shell 命令或任意 Python callable。

后续扩展：

- `mcp_tool`
- `http`
- `subgraph`

验收标准：

- 未绑定执行器不能运行。
- 密钥不进入 IR、lock 和日志。
- 资源通过环境变量、配置或 secret ref 注入。

### F5. Validator

Validator 必须是确定性模块，不调用 LLM。

检查项：

1. Schema 校验。
2. 节点 ID 唯一。
3. 节点 kind 存在。
4. executor 存在。
5. 边引用存在。
6. 入口可达。
7. 有合法出口。
8. 无不可达节点。
9. 输入输出类型兼容。
10. 参数满足 schema。
11. 循环声明 `max_iterations`。
12. fan-out 聚合字段有 reducer。
13. 动态路由节点不能同时有静态边。
14. 副作用节点满足审批或幂等策略。

验收标准：

- 每个错误有稳定错误码。
- 错误定位到具体 node、edge 或 state path。
- 校验失败不得生成可运行 bundle。

### F6. LangGraph Python Compiler

系统必须实现 LangGraph Python 后端。

编译规则：

- `StateSchema` 编译为 `TypedDict` 或 Pydantic state。
- list/message 聚合字段必须带 reducer。
- 普通节点函数接收 state，返回 partial update。
- 线性边编译为 `add_edge`。
- 条件边编译为 `add_conditional_edges`。
- fan-out 编译为返回 `Send` 的条件路由。
- 需要同时更新 state 和跳转时使用 `Command`。
- `human_gate` 使用 `interrupt()`。
- `join` edge 在 v0.1 仅 IR/registry/Mermaid 可见，LangGraph compiler/runner 必须以 `E_TARGET_009` 拒绝，不生成可运行 bundle。
- `Command(resume=...)` 只作为恢复 interrupt 的运行输入。
- 同一节点不得同时使用静态边和动态路由。

验收标准：

- 生成图可 `compile()`。
- 最小线性图可 `invoke()`。
- 条件图可按 state 路由。
- interrupt 图可暂停并通过 resume 继续。

### F7. Runtime Runner

系统必须提供本地运行器。

v0.1 支持：

- 加载本地 bundle。
- 调用 `invoke()`。
- 传入 `thread_id`。
- 返回运行结果和事件摘要。
- 对 interrupt 返回 waiting 状态。

验收标准：

- 相同输入和相同 mock 执行器可复现。
- 运行失败返回结构化错误。
- 不吞掉节点异常。

### F8. CLI

v0.1 CLI：

```bash
pt2lg validate workflow.json
pt2lg compile workflow.json --target langgraph-py --out build/
pt2lg run build/workflow.lock.json --input input.json
pt2lg graph build/workflow.lock.json --format mermaid
```

验收标准：

- 成功返回 0。
- 失败返回非 0。
- `--json` 模式输出机器可读报告。

### F9. Skill 预分析

v0.1 的 skill_dir 能力是静态预分析：读取 `SKILL.md` frontmatter、编号步骤、资源文件和风险词，输出分析对象和 draft nodes。v0.1 不从 skill_dir 生成可执行 `WorkflowSpec`，不执行 skill 脚本，也不隐式调用 shell 或网络。

必须识别：

- skill 名称、描述和触发条件。
- `SKILL.md` 中的显式步骤。
- `scripts/`、`references/`、`assets/` 清单。
- shell、网络、文件写入、密钥等风险提示。

验收标准：

- 不执行 skill 脚本。
- 对无法确定的步骤输出人工确认诊断。
- 能为一个简单线性 skill 输出静态分析摘要和 draft nodes。

### F10. 可视化与报告

系统必须生成 Mermaid 和表格化报告。

验收标准：

- Mermaid 节点和边来自 IR。
- 可视化不作为执行真相源。
- 报告包含 warning、error、节点表、边表、状态通道表。

## 8. 非功能需求

### 8.1 确定性

- 编译器后端不调用 LLM。
- 相同 IR、注册表和编译选项产生相同 lock hash。
- lock 文件字段稳定排序。

### 8.2 安全性

- 默认不执行未注册工具。
- 默认不执行 skill 目录脚本。
- 默认不运行任意 shell。
- 默认禁止未审批副作用。
- secrets 不写入 IR、lock、manifest、日志。
- 高风险能力必须有显式策略。

### 8.3 可观测性

- 每次编译有 `compile_id`。
- 每次运行有 `run_id` 和 `thread_id`。
- 每个节点有 started、finished、failed、interrupted 事件。
- LLM 节点记录 provider、model、token 和耗时摘要。

### 8.4 兼容性

- Python 3.11+。
- 首发 LangGraph Python。
- IR 预留 LangGraph.js 和 Dify 后端扩展位。

### 8.5 性能

v0.1 目标：

- 20 节点以内编译小于 2 秒，不含 LLM planner。
- 100 节点以内编译小于 10 秒。
- 校验复杂度随节点和边近似线性增长。

## 9. 类型系统

v0.1 内置类型：
【这里是采用json的类型？和python类型兼容吗？】
| 类型 | 说明 |
|---|---|
| `string` | 字符串 |
| `number` | 数字 |
| `integer` | 整数 |
| `boolean` | 布尔值 |
| `object` | JSON 对象 |
| `array` | JSON 数组 |
| `messages` | LangGraph 消息列表 |
| `artifact_ref` | 大对象引用 |
| `any` | 明确声明的通配类型 |

状态设计原则：

- 小型结构化数据放 state。
- 大文档、图片、表格、文件、搜索结果放 artifact store。
- state 只保存 `ArtifactRef`。
- list 和 messages 聚合必须声明 reducer。
- messages 优先使用 LangGraph `add_messages`。

## 10. 错误码

| 错误码 | 含义 |
|---|---|
| `E_PARSE_001` | 源输入解析失败 |
| `E_SCHEMA_002` | IR schema 校验失败 |
| `E_TYPE_003` | 输入输出类型不兼容 |
| `E_DEP_004` | 依赖图非法 |
| `E_LOOP_005` | 循环不安全 |
| `E_BIND_006` | 执行器或资源绑定失败 |
| `E_SEC_007` | 安全策略违规 |
| `E_SIDE_008` | 副作用节点缺少审批、幂等或补偿策略 |
| `E_TARGET_009` | 目标后端不支持该语义 |
| `E_RUNTIME_010` | 运行时异常 |
| `E_ROUTE_011` | 路由规则冲突或不可解析 |
| `E_REDUCER_012` | 并行聚合缺少 reducer |

## 11. v0.1 验收清单

v0.1 完成时必须满足：

- 可以安装 Python 包并运行 `pt2lg --help`。
- 可以校验一个合法 Workflow IR。
- 可以拒绝至少 5 类无效 IR。
- 可以从 JSON plan 生成 Workflow IR。
- 可以编译一个线性图并成功 `compile()`。
- 可以运行一个线性图并成功 `invoke()`。
- 可以编译一个条件分支图。
- 可以编译一个带 `max_iterations` 的循环图。
- 可以编译一个 fan-out 图，并验证 reducer 存在。
- 可以编译一个 human_gate 图，并在运行时产生 interrupt。
- 编译产物包含 lock、manifest、report、Mermaid。
- 核心流程有自动化测试和 golden fixture（预先保存的"标准答案"测试样本）。

## 12. 里程碑

### M1：项目骨架与 IR

- 创建 Python 包结构。
- 定义 Pydantic IR。
- 定义错误模型。
- 增加 JSON Schema 导出。

### M2：注册表与校验器

- 内置节点注册表。
- 内置执行器注册表。
- 实现 Validator。
- 实现类型检查和安全检查。

### M3：LangGraph 编译闭环

- 实现 LangGraph Python compiler。
- 生成 `StateGraph`。
- 输出 lock、manifest、report、Mermaid。
- 打通线性图 compile/invoke。

### M4：控制流增强

- 条件分支。
- 有上限循环。
- fan-out/map-reduce。
- human_gate interrupt/resume。

### M5：输入前端和样例

- JSON plan adapter。
- Skill 预分析。
- 后续阶段再引入 text plan adapter。
- golden fixtures（预先保存的"标准答案"测试样本） 和 e2e 测试。

## 13. 参考项目借鉴要求

### LangGraph

必须借鉴：

- `StateGraph`
- state schema
- reducer
- `START` / `END`
- `add_edge`
- `add_conditional_edges`
- `Send`
- `Command`
- `interrupt`
- `compile`

### PlanCompiler

必须借鉴：

- 节点注册表是事实来源。
- LLM 只能选择节点和填参数。
- 编译前静态校验。
- 结构无效则拒绝执行。
- 编译器确定性输出。

但需要调整：

- PlanCompiler 默认 DAG，prompt2langgraph 必须允许 LangGraph 循环，但循环必须有 guard。

### LLMCompiler

必须借鉴：

- `$id` 依赖引用。
- join。
- 并行任务识别。

但 v0.1 不要求实现流式 planner 和 replan。

### skills-to-dify-workflow / dify-workflow-dsl-skill

必须借鉴：

- skill 目录完整读取。
- 不硬编码 secrets。
- 图节点和边必须显式。
- 导入或编译前本地校验。
- 工具节点必须有 provider/tool 参数。

但 v0.1 不承诺生成 Dify DSL。

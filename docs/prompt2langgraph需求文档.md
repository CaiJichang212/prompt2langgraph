# prompt2langgraph 需求文档

## 1. 背景

prompt2langgraph 的目标是把用户 prompt、LLM 生成的计划，以及本地 skills 编译成可执行的 LangGraph 图。现有调研结论已经明确：当前没有成熟开源项目能直接完成“任意 Plan/Skill -> LangGraph”的端到端转换，但 LangGraph、LLMCompiler、PlanCompiler、skills-to-dify-workflow、dify-workflow-dsl-skill 提供了足够可借鉴的工程基元。

本项目不应让 LLM 直接生成自由代码并执行，而应采用编译器式流程：

```text
prompt / plan / skill
-> 结构化解析
-> Workflow IR
-> 静态校验与资源绑定
-> LangGraph StateGraph
-> compile()
-> invoke / stream / resume
```

其中，LLM 只负责提出候选计划或补全结构化字段；真正可运行的图必须由确定性编译器生成，并在执行前通过校验。

## 2. 项目目标

### 2.1 总目标

实现一个面向 LangGraph 的计划与技能编译器，使以下输入能够被转换为可编译、可运行、可测试、可观测的 LangGraph 图：

- 用户自然语言 prompt。
- LLM 生成的结构化或半结构化计划。
- Claude Code / Codex 风格的 `SKILL.md` 技能目录。
- 明确 JSON/YAML 格式的 Workflow IR。

### 2.2 MVP 目标

第一阶段优先实现 Python LangGraph 后端，完成从结构化计划到可运行图的最小闭环：

- 支持 `json_plan` 输入。
- 支持有限的 `plan_text` 输入解析。
- 支持读取单个 skill 目录中的 `SKILL.md`，抽取步骤、工具、分支、循环意图。
- 生成规范化 `WorkflowIR`。
- 校验节点、边、状态通道、输入输出类型、工具绑定和安全策略。
- 编译为 LangGraph Python `StateGraph`。
- 支持线性边、条件边、基础循环、简单 fan-out。
- 支持 `graph.compile()`、`graph.invoke()`。
- 生成 `workflow.lock.json`、Mermaid 图和诊断报告。

### 2.3 非目标

第一阶段暂不追求：

- 完整替代 LangGraph Studio、Dify、Flowise 或 Langflow。
- 自动理解所有任意格式自然语言计划。
- 运行未审查的任意脚本。
- 默认支持多语言后端。
- 默认接入复杂分布式运行时，如 Ray、Temporal、Kubernetes。
- 生成生产级可视化编辑器。

## 3. 用户与使用场景

### 3.1 主要用户

- Agent 应用开发者：希望把 prompt 或 plan 快速转换成 LangGraph 工作流。
- 平台工程师：希望构建可治理、可审计、可复现的工作流编译与运行平台。
- 技能作者：希望把 Markdown skill 变成可视化、可运行、可测试的图。
- 研究人员：希望对比不同 plan 编译策略和执行效果。

### 3.2 核心场景

#### 场景 A：结构化计划编译

用户提供 JSON 计划：

```json
{
  "name": "research_answer",
  "nodes": [
    {"id": "parse_query", "kind": "llm"},
    {"id": "search_docs", "kind": "tool"},
    {"id": "summarize", "kind": "llm"}
  ],
  "edges": [
    {"from": "parse_query", "to": "search_docs"},
    {"from": "search_docs", "to": "summarize"}
  ]
}
```

系统输出可运行 LangGraph 图和编译报告。

#### 场景 B：prompt 生成计划再编译

用户输入：

```text
请先分析问题，检索本地文档，如果证据不足就请求人工确认，否则直接生成答案。
```

系统调用 Planner 生成候选计划，再经过 IR 校验和 LangGraph 编译。

#### 场景 C：Skill 编译【规则解析+大模型】

用户提供一个 skill 目录：

```text
skill/
├── SKILL.md
├── scripts/
├── references/
└── assets/
```

系统读取 `SKILL.md`、脚本和引用资料，分析其中的 LLM 调用、工具调用、条件、循环、并行和安全风险，生成可运行的 Workflow IR 和 LangGraph 图。

#### 场景 D：编译诊断

计划中引用了不存在的工具或产生类型不匹配边，系统不执行，而是返回诊断报告：

```text
E_BIND_006: node "send_email" references unregistered executor "mail.send".
E_TYPE_003: edge retrieve -> summarize expects docs_ref, got text.
```

#### 场景 E：人工中断与恢复

计划中包含高风险动作，例如写数据库、发邮件、删除文件。系统编译时注入人工审批节点，运行时通过 LangGraph interrupt 暂停，并在用户审批后 resume。

## 4. 输入需求

### 4.1 输入类型

| 输入类型 | 说明 | MVP 支持 |
|---|---|---|
| `prompt_text` | 用户自然语言目标 | 部分支持，通过 Planner 生成 draft plan |
| `plan_text` | LLM 生成的文本计划 | 部分支持，优先解析编号步骤和依赖引用 |
| `json_plan` | 结构化计划 | 必须支持 |
| `workflow_ir` | 规范化 IR | 必须支持 |
| `skill_dir` | 包含 `SKILL.md` 的技能目录 | 必须支持基础读取与分析 |
| `tool_registry` | 工具与节点注册表 | 必须支持 |
| `compile_options` | 目标后端、安全、运行策略 | 必须支持 |

### 4.2 计划语言约束

借鉴 LLMCompiler 和 PlanCompiler，计划应尽量结构化。文本计划至少支持以下约定：

- 每个步骤有稳定 ID。
- 工具调用必须引用注册表中的工具。
- 参数可引用前序步骤输出，例如 `$step_id`。
- 分支条件必须能映射到 state 字段。
- 循环必须声明退出条件或最大迭代次数。
- 外部副作用必须声明幂等键或审批策略。

### 4.3 Skill 解析范围 【规则解析+大模型】

MVP 对 `SKILL.md` 的解析以保守抽取为主：

- 读取技能名称、描述、触发条件。
- 抽取工作流步骤。
- 识别显式工具或脚本调用。
- 识别 references/assets 依赖。
- 标记潜在风险，如文件写入、网络访问、密钥、危险 shell 命令。
- 对无法确定的自然语言片段生成人工确认诊断，而不是擅自执行。

## 5. 输出需求

### 5.1 编译输出

系统编译成功后必须输出：

- `WorkflowIR`：规范化后的中间表示。
- `workflow.lock.json`：可复现编译锁文件。
- `GraphManifest`：图入口、节点、边、状态 schema、目标后端、依赖版本。
- LangGraph Python 代码或可导入 bundle。
- Mermaid 图或其他可视化描述。
- `ValidationReport` 和 `CompileReport`。

### 5.2 运行输出

运行成功后必须输出：

- 最终结果。
- `run_id`、`thread_id`。
- 节点执行事件。
- 状态摘要。
- 工具调用摘要。【摘要如何获取，规则截断还是大模型总结】
- token、耗时、重试次数。
- 中断或失败诊断。

### 5.3 失败输出

失败时不得静默降级执行。必须返回：

- 错误码。
- 错误位置，如 node、edge、state channel、executor。
- 可读原因。
- 建议修复动作。
- 是否可重试。

## 6. 功能需求

### F1. Source Adapter

系统应提供多种源适配器：

- `JsonPlanAdapter`：读取结构化计划。
- `TextPlanAdapter`：解析编号文本计划。【每条计划还是纯文本text，如何转换成IR】
- `PromptPlannerAdapter`：调用 LLM 生成 draft plan。
- `SkillAdapter`：读取 skill 目录。
- `IRAdapter`：直接读取 Workflow IR。【json-plan和IR的区别？json-plan和text-plan类似？】

验收标准：

- 相同输入在相同选项下生成稳定 draft。
- 解析失败时返回结构化诊断。
- 不执行源文件中的脚本。

### F2. Workflow IR

系统必须定义一个稳定的中间表示，作为所有前端输入和后端输出之间的唯一事实来源。

核心对象：

- `WorkflowSpec`
- `StateSchema`
- `NodeSpec`
- `EdgeSpec`
- `ExecutorSpec`
- `PolicySpec`
- `ArtifactSpec`
- `CompileOptions`

验收标准：

- IR 可以 JSON 序列化。
- IR 有 JSON Schema 或 Pydantic 模型约束。
- IR 可以生成 lock 文件。
- IR 字段版本化，支持未来迁移。

### F3. Node Registry

系统必须维护节点注册表。LLM 不能发明节点类型并直接执行。

注册表字段至少包括：

- 节点 kind。【type？】
- 描述。
- 输入 schema。
- 输出 schema。
- 支持的执行器。
- 是否允许 planner 使用。
- 是否有副作用。【执行后的影响后果？】
- 需要的权限。
- 默认重试与超时策略。

验收标准：

- 未注册节点编译失败。
- 废弃节点给出 warning 或 error。
- 高风险节点默认需要审批或显式授权。

### F4. Executor Registry 与资源绑定【不太懂？】

系统必须把抽象节点绑定到真实执行器：

- LLM 模型。
- LangChain tool。
- Python callable。
- HTTP API。
- MCP 工具。
- 子图。
- 人工审批。

验收标准：

- 未绑定执行器不能进入运行阶段。
- 密钥不写入 lock 文件。
- 运行时可通过环境变量或配置注入资源。

### F5. Validator

系统必须提供确定性校验器。校验失败时不允许运行。

基础检查：

- 节点 ID 唯一。
- 边引用存在。
- 入口和出口合法。
- 无不可达节点。
- 循环具备退出条件或最大迭代次数。
- 输入输出类型兼容。
- 参数满足 schema。
- 副作用节点具备幂等或审批策略。
- 工具权限满足白名单。

验收标准：

- 对无效计划返回稳定错误码。
- 校验不依赖 LLM。
- 每条错误能定位到具体对象。

### F6. LangGraph Compiler

系统必须实现 LangGraph Python 后端。

编译规则：

- `WorkflowSpec.state_schema` -> `TypedDict` 或 Pydantic state。
- `NodeSpec` -> LangGraph node function。
- 线性边 -> `add_edge`。
- 条件边 -> `add_conditional_edges` 或 `Command`。
- fan-out -> `Send`。
- 人工审批 -> `interrupt()`。
- 入口 -> `START -> entrypoint`。
- 结束 -> `node -> END`。
- 编译 -> `builder.compile(...)`。

验收标准：

- 生成图必须可 `compile()`。
- 最小线性图可 `invoke()`。
- 节点函数只返回 partial state update，不直接修改原 state。
- list/message 类状态通道必须显式 reducer。

### F7. Runtime Runner

系统应提供本地运行器：

- 加载 bundle。
- 创建 run。
- 调用 `invoke` 或 `stream`。
- 写入事件日志。
- 处理中断和 resume。
- 输出运行结果。

验收标准：

- 相同输入可复现。
- 中断后可通过 thread_id 恢复。
- 运行失败有结构化错误。

### F8. CLI 与 Python API

MVP 至少提供 CLI 和 Python API。

CLI 示例：

```bash
pt2lg validate workflow.json
pt2lg compile workflow.json --target langgraph-py --out build/
pt2lg run build/workflow.lock.json --input input.json
pt2lg skill compile path/to/skill --out build/
```

Python API 示例：

```python
from prompt2langgraph import compile_workflow, run_workflow

bundle = compile_workflow(source, target="langgraph-py")
result = run_workflow(bundle, {"question": "..."})
```

验收标准：

- CLI 返回非零退出码表示失败。
- Python API 抛出类型化异常。
- 编译报告可被程序读取。

### F9. 可视化与诊断

系统应生成：

- Mermaid 图。
- 节点表。
- 边表。
- 状态通道表。
- 编译 warning/error。

验收标准：

- 用户能在不读源码的情况下理解图结构。
- 可视化不作为执行真相源，执行以 IR 和 lock 文件为准。

### F10. 测试样例库

系统必须包含 golden tests：

- 单节点 LLM 图。
- 线性三节点图。
- 条件分支图。
- 循环带上限图。
- fan-out map-reduce 图。
- 工具节点图。
- 人工审批图。
- 无效类型图。
- 未注册工具图。
- skill 编译图。

验收标准：

- 所有样例可重复编译。
- 编译快照稳定。
- 至少一个样例能端到端运行。

## 7. 非功能需求

### 7.1 确定性

- 编译器后端不调用 LLM。
- 相同 IR 和相同注册表产生相同 lock 文件。
- 自动生成代码和 manifest 保持稳定排序。

### 7.2 安全性

- 默认不执行 skill 目录中的脚本。【？】
- 默认禁止未注册工具。
- 默认不允许外部写操作无审批执行。
- secrets 不得进入日志、IR、lock 文件。
- 代码执行节点必须声明沙箱策略。

### 7.3 可观测性

- 每次编译有 compile_id。
- 每次运行有 run_id 和 thread_id。
- 每个节点有开始、结束、失败、中断事件。
- 记录模型、工具、耗时、token、重试次数。

### 7.4 可扩展性

- 前端输入适配器可插拔。
- 后端编译器可插拔。
- 节点和执行器可注册。
- 策略可配置。

### 7.5 兼容性

- 首发支持 Python 3.11+。
- 首发支持 LangGraph Python。
- IR 保留 LangGraph.js 后端扩展空间。

### 7.6 性能

MVP 目标：

- 20 节点以内图编译小于 2 秒，不含 LLM plan 生成。
- 100 节点以内图编译小于 10 秒。
- 编译器内存占用随节点数线性增长。

## 8. 数据与类型需求

### 8.1 状态设计原则

- 小型结构化数据放入 state。
- 大文档、表格、图片、文件、搜索结果集放入 artifact store。
- state 中只保存 `ArtifactRef`。
- 所有 list 聚合通道必须声明 reducer。
- messages 通道优先使用 LangGraph `add_messages`。

### 8.2 类型系统

MVP 类型集合：

- `string`
- `number`
- `boolean`
- `object`
- `array`
- `messages`
- `artifact_ref`
- `any`

后续可扩展：

- `dataframe`
- `file_ref`
- `http_response`
- `db_handle`
- `tool_result`

## 9. 错误码需求

| 错误码 | 含义 |
|---|---|
| `E_PARSE_001` | 源输入解析失败 |
| `E_SCHEMA_002` | IR schema 校验失败 |
| `E_TYPE_003` | 节点输入输出类型不兼容 |
| `E_DEP_004` | 依赖图非法 |
| `E_LOOP_005` | 循环不安全 |
| `E_BIND_006` | 执行器或资源绑定失败 |
| `E_SEC_007` | 安全策略违规 |
| `E_SIDE_008` | 副作用节点缺少幂等或补偿策略 |
| `E_TARGET_009` | 目标后端不支持该语义 |
| `E_RUNTIME_010` | 运行时异常 |

## 10. 里程碑

### M1：项目骨架与 IR

- 建立 Python 包结构。
- 定义 IR 模型和 schema。
- 定义节点注册表。
- 实现 JSON plan 读取和校验。

### M2：LangGraph 编译闭环

- 实现 LangGraph Python backend。
- 生成并运行最小图。
- 输出 lock、manifest、Mermaid。

### M3：文本计划与 skill 编译

- 实现基础文本计划解析。
- 实现 `SKILL.md` 解析器。
- 加入安全扫描。

### M4：运行时与中断

- 增加本地 runner。
- 支持 checkpointer。
- 支持 human_gate interrupt/resume。

### M5：测试与样例

- 补齐 golden tests。
- 加入端到端示例。
- 加入编译快照测试。

## 11. 验收标准

项目达到 MVP 可验收状态时，应满足：

- 可以从 JSON plan 编译出 LangGraph Python 图。
- 生成图可以成功 `compile()`。
- 至少一个线性图可以成功 `invoke()` 并返回结果。
- 至少一个条件分支图可以根据 state 路由。
- 至少一个 skill 目录可以被解析为 Workflow IR。
- 无效计划不会执行，并返回结构化诊断。
- 编译产物包含 workflow.lock.json、manifest 和 Mermaid。
- 核心流程有自动化测试。

## 12. 参考依据

- `docs/pt2lg-task0508.md`：确认“prompt/plan/skills -> LangGraph”的任务方向。
- `docs/pt2lg开源调研与技术架构方案.md`：确认 IR + Validator + LangGraph backend 的总体路线。
- `docs/LangGraph/graph-api.md`：确认 LangGraph State、Nodes、Edges、Reducers、compile 语义。
- `docs/LangGraph/use-graph-api.md`：确认条件、循环、Send、Command 等图基元。
- `ref-projects/LLMCompiler`：借鉴 plan 文本协议、依赖引用、并行调度、join/replan。
- `ref-projects/plancompiler`：借鉴节点注册表、静态校验、类型检查、确定性编译。
- `ref-projects/skills-to-dify-workflow`：借鉴 skill 目录读取、安全审查、流程抽取。
- `ref-projects/dify-workflow-dsl-skill`：借鉴 workflow DSL、节点/边结构和导入前验证。

# prompt2langgraph v0.2 第一期开发计划文档

## 1. 文档目的

本文档用于定义 `prompt2langgraph` v0.2 第一期的工程实施设计，作为后续详细实施计划、代码改动与测试回归的直接依据。

本文档聚焦 **目标、范围、模块任务与验收标准**，采用“严格一期范围 + 模块级任务拆解”的方式组织内容，不展开到文件级或接口级实施步骤。

---

## 2. 阶段定位

v0.2 采用《三期任务划分方案A》中“目标链路优先”的推进策略。第一期对应其中的 **输入适配闭环（Input Bridge）**，核心目标是在现有 v0.1 已具备的 `Workflow IR / JSON plan → validate / compile / run / graph` 能力之上，补齐从自然语言 Prompt 出发的上层输入桥接层。

第一期不是“真实执行能力建设”阶段，其重点不在于让运行时 `llm` 节点调用真实模型，而在于让系统能够接收非结构化 Prompt，经由受控的 LLM 计划生成过程，落回当前项目已经支持的结构化输入体系。

同时需要明确：第一期开启的是**显式、受控、仅用于计划生成**的外部 LLM 调用边界。这是对当前 v0.1 默认不隐式调用外部模型或网络能力边界的受控扩展，不代表 runtime executor 的执行边界被同步放宽。

---

## 3. 阶段目标

v0.2 第一期的阶段目标是：

- 接收自然语言 Prompt 作为上层输入；
- 调用外部 LLM 将 Prompt 转换为兼容本项目的简化 JSON plan；
- 将生成结果继续适配为标准 `WorkflowSpec`；
- 复用现有 `validate / compile / run / graph` 主链路完成后续处理；
- 在整个过程中保持现有校验体系、编译体系和运行体系的主导地位，不形成旁路执行链路。

一句话概括：**第一期是在现有编译运行内核之外，新增一条“Prompt 经 LLM 生成 JSON plan，再适配到 WorkflowSpec”的受控输入闭环。**

---

## 4. 纳入范围

第一期纳入以下范围：

1. 新增 `Prompt → LLM → 简化 JSON plan` 的计划生成入口；
2. 对 LLM 输出结果进行 JSON 解析、基础结构校验与失败诊断；
3. 复用现有 `JSON plan → WorkflowSpec` 适配能力，不新增一套并行的 Prompt 直转执行链路；
4. 为 CLI 与 Public API 增加 Prompt 输入入口，使外部调用方可以提交自然语言 Prompt；
5. 确保 Prompt 生成结果必须进入现有 `validate / compile / run / graph` 主流程，不能绕过校验直接执行；
6. 为 Prompt 输入链路补充测试夹具、错误场景测试与 CLI / API 回归测试；
7. 同步更新文档，至少包括 `README.md`、`CLAUDE.md`、`AGENTS.md`，确保对外能力说明与仓库实际行为一致。

---

## 5. 明确排除范围

第一期不纳入以下内容：

- 不实现“Prompt 直接生成并执行 Workflow IR”的旁路机制；
- 不设计完整的真实 LLM provider 抽象体系；
- 不实现运行时真实模型调用 executor；
- 不引入 Tool Executor；
- 不扩展 `skill_dir` 为可执行工作流生成器；
- 不补 `join` edge 执行能力；
- 不改变当前 runtime / compiler 的确定性执行边界；
- 不为了提升自然语言自由解析能力而提前引入复杂多轮规划、反思或自动修复机制。

---

## 6. 设计原则

第一期设计应遵守以下原则：

### 6.1 LLM 只负责生成 plan，不负责执行 workflow

LLM 的职责限定在把 Prompt 转成简化 JSON plan。后续是否可运行，仍由既有 adapter、validator、compiler 和 runner 决定。

### 6.2 Prompt 结果必须回落到当前受支持的结构化输入格式

按当前仓库边界，稳定主路径应为“先生成简化 JSON plan，再转 `WorkflowSpec`”，而不是直接发明新的可执行输入制式。

### 6.3 不能形成校验旁路

无论 LLM 输出看起来多完整，都必须经过 JSON 解析、结构检查、适配与标准校验，不能直接送入运行时。

### 6.4 失败优先于模糊修复

非法 JSON、字段缺失、未知节点、图结构不合法、类型不匹配等情况，优先返回明确诊断，而不是隐式猜测用户意图。

### 6.5 不透支二期执行设计

第一期允许为外部 LLM 计划生成预留最小配置入口，但不提前展开 provider/model/tool/runtime execution 抽象。

### 6.6 优先兼容 Qwen / vLLM 等 OpenAI-style 接口

第一期 Prompt 计划生成推荐采用 `langchain_openai` 作为接入方式，以兼容 Qwen 模型、vLLM 部署暴露的 OpenAI-style API 以及其他第三方兼容接口为优先目标，但第一期只要求覆盖最小可用接入路径，不承诺广泛的多供应商兼容性，也不扩展为完整多供应商框架。

---

## 7. 模块任务

### 7.1 Prompt 计划生成模块

新增一个“Prompt 生成简化 JSON plan”的独立模块，负责承接自然语言输入，并调用外部 LLM 生成兼容本项目简化 plan 约束的 JSON 结果。

该模块的职责应严格限定为：

- 接收 Prompt 文本及少量生成控制参数；
- 基于 `langchain_openai` 组织并发起 LLM 调用；
- 以兼容 Qwen 模型、vLLM 部署暴露的 OpenAI-style API 以及其他第三方兼容接口为优先目标；
- 从 `.env` 文件加载最小必要配置，至少包括 `MODEL`、`BASE_URL`、`API_KEY`；
- 支持在已加载配置基础上选择可用模型；
- 获取模型输出文本；
- 将输出结果交给后续解析与诊断模块处理。

该模块不负责：

- 直接生成 `WorkflowSpec`；
- 直接触发编译或运行；
- 替代现有 JSON plan 适配职责；
- 承担运行时真实 LLM executor 的角色。

第一期应把它视为**输入层新增模块**，其产物仍必须回落为“简化 JSON plan”这一既有结构化入口。

### 7.2 Prompt 输入适配与诊断模块

在 LLM 返回文本之后，增加一个面向一期场景的解析与诊断模块，负责把模型文本输出收敛为可继续送入 `JSONPlanAdapter` 的字典对象。

该模块应承担：

- JSON 文本解析；
- 顶层对象类型检查；
- 对关键字段缺失、类型不符、非对象输出等情况生成一致诊断；
- 在适配失败时阻断后续 `validate / compile / run / graph` 流程。

该模块不应重新实现现有 validator 已具备的图校验、类型校验和安全校验逻辑，而应只处理 **“LLM 文本输出 → 可交给现有 adapter 的结构对象”** 这一层问题。

### 7.3 CLI 与 Public API 输入扩展模块

在现有 CLI 和 Public API 上新增 Prompt 输入入口，但保持当前 `Workflow IR / JSON plan` 入口不变。

该模块应完成：

- 为 CLI 增加清晰的 Prompt 输入命令或参数入口；
- 为 Public API 暴露对应的 Prompt 计划生成与后续适配入口；
- 明确 Prompt 模式下的输入参数、输出结构和失败返回；
- 明确 Prompt 模式下的 LLM 最小配置来源，默认从 `.env` 文件加载 `MODEL`、`BASE_URL`、`API_KEY`，并允许基于配置选择可用模型；
- 保持现有 `validate / compile / run / graph / resume` 的原有文件输入行为兼容。

核心约束是：**Prompt 是新增入口，不是替代入口。** 第一期不应把当前基于 JSON 文件的主流程改造成只依赖 Prompt，也不应让 CLI 命令语义变得混乱。

### 7.4 现有适配与校验链路复用模块

第一期应明确依赖现有 `JSONPlanAdapter` 的能力，把 LLM 生成的简化 JSON plan 继续转成标准 `WorkflowSpec`，再复用现有 validator 和后续 compile/run/graph 主链路。

这一模块的重点不是新增大量逻辑，而是明确链路衔接关系：

- Prompt 输出的目标格式必须受当前简化 JSON plan 语义约束；
- `JSONPlanAdapter` 仍然是结构化 plan 到 `WorkflowSpec` 的唯一主适配入口；
- validator 仍然是 workflow 合法性的统一裁决点；
- compile/run/graph 不感知该 workflow 最初来自 Prompt 还是 JSON 文件。

这样做可以把第一期 Prompt 能力严格收敛为**一个前置输入桥接问题**，避免把现有编译运行内核撕开新分支。

### 7.5 测试与文档回归模块

第一期必须把 Prompt 链路视为一个新的正式输入能力来补测试和文档，而不是只做 demo 级接入。

该模块应覆盖：

- Prompt 成功生成简化 JSON plan 并适配成功的主路径测试；
- 非法 JSON、非对象输出、字段缺失、未知节点、类型不匹配等失败场景测试；
- CLI Prompt 入口的回归测试；
- Public API Prompt 入口的回归测试；
- 文档同步更新，至少包括 `README.md`、`CLAUDE.md`、`AGENTS.md`，确保能力边界说明与实际行为一致。

测试目标应聚焦在：

- Prompt 链路能否稳定回落到现有 `WorkflowSpec` 主流程；
- LLM 输出异常时是否能给出明确、可消费的诊断；
- 新入口是否破坏现有 JSON plan / Workflow IR 路径。

---

## 8. 验收标准

### 8.1 输入闭环验收

满足以下条件，方可判定第一期主目标达成：

- 系统能够接收自然语言 Prompt 作为输入；
- Prompt 输入能够通过 LLM 生成兼容本项目简化 JSON plan 约束的结果；
- 生成结果能够被成功解析并适配为标准 `WorkflowSpec`；
- 适配后的 `WorkflowSpec` 能继续进入现有 `validate / compile / run / graph` 流程；
- 整条链路中不存在绕过现有校验体系直接执行的旁路。

### 8.2 LLM 接入方式验收

第一期在 LLM 接入层应满足：

- Prompt 计划生成链路采用 `langchain_openai` 作为推荐接入方式；
- 以兼容 Qwen 模型、vLLM 部署暴露的 OpenAI-style API 以及其他第三方兼容接口为优先目标；
- 默认从 `.env` 文件加载最小必需的调用配置，至少包括 `MODEL`、`BASE_URL`、`API_KEY`；
- 支持在已加载配置基础上选择可用模型；
- 该接入仅用于 `Prompt → JSON plan` 生成，不扩展到 runtime `llm` 节点执行能力；
- 不在第一期内演化为完整 provider 抽象层。

验收重点是：**能基于 `.env` 配置稳定接入一个 Qwen / vLLM 等 OpenAI-style 兼容 LLM API，完成计划生成。**

### 8.3 结构化结果与诊断验收

Prompt 生成结果在进入现有主链路前，必须具备明确的前置收敛与失败表现：

- 当 LLM 返回合法 JSON 对象且结构满足简化 plan 要求时，可继续适配；
- 当 LLM 返回非法 JSON、非对象、关键字段缺失、字段类型错误时，系统能够返回明确诊断；
- 当生成结果虽然能解析为对象，但在后续 `JSONPlanAdapter` 或 `validate_workflow()` 阶段失败时，错误能够被保留并暴露给调用方；
- 失败诊断应能区分“生成输出不可解析”和“生成输出可解析但不符合工作流约束”两类问题。

### 8.4 CLI 验收

CLI 层需要满足以下验收标准：

- 提供清晰的 Prompt 输入入口；
- 用户能够通过 CLI 提交 Prompt 并触发计划生成；
- CLI 能输出成功链路结果，以及 Prompt 生成、解析、适配失败时的机器可读诊断；
- 现有基于 `Workflow IR` 和简化 JSON plan 文件的 CLI 命令行为保持兼容；
- 新增 Prompt 入口不会破坏现有 `validate / compile / run / graph / resume` 基线体验。

### 8.5 Public API 验收

Public API 层需要满足：

- 暴露面向 Prompt 输入的调用入口；
- 调用方可通过 Python API 提交 Prompt，并获得生成结果或诊断信息；
- API 返回结构能够明确区分成功、解析失败、适配失败、校验失败等状态；
- API 侧明确最小 LLM 配置来源，默认从 `.env` 文件加载 `MODEL`、`BASE_URL`、`API_KEY`，并允许基于配置选择可用模型；
- 当前稳定导出的现有 API 能力不被破坏。

### 8.6 测试验收

测试层至少应满足：

- 补齐 Prompt 主路径测试；
- 补齐 LLM 输出异常场景测试；
- 补齐 CLI Prompt 入口回归测试；
- 补齐 Public API Prompt 入口回归测试；
- 现有 `Workflow IR / JSON plan` 基线路径测试继续通过；
- 最终以全量 `uv run pytest` 通过作为第一期回归验收基线。

为保证测试稳定性，第一期应优先通过 fake / mock 响应方式验证 Prompt 生成链路，而不是把单元测试绑定到真实外部 LLM 可用性。

### 8.7 文档与边界一致性验收

文档层面应满足：

- `README.md` 明确新增 Prompt 输入能力；
- `README.md` 明确说明 Prompt 生成依赖外部 LLM，但其职责仅限于生成简化 JSON plan；
- `README.md` 明确当前第一期仍不支持真实 workflow `llm` 节点执行；
- `CLAUDE.md` 与 `AGENTS.md` 同步反映新的输入边界、测试要求和文档说明；
- 第一期开发计划文档与仓库文档对能力边界表述一致；
- 若阶段实施后仓库行为与历史文档表述不一致，应以 `src/prompt2langgraph/` 与 `tests/` 的实际行为为准，并同步修正文档；
- 文档不应错误暗示“Prompt 直出 Workflow IR 并直接执行”已经成为当前正式能力。

### 8.8 非目标验收

第一期完成时，以下事项仍不应被视为必须完成项：

- 真实 LLM executor；
- provider 抽象体系；
- tool executor；
- skill → `WorkflowSpec` 可执行转换；
- `join` 执行支持；
- `side_effect` 最小执行闭环。

只要上述能力仍未实现，但 Prompt 输入闭环已经打通，第一期依然可以判定为完成。

---

## 9. 后续衔接建议

在本开发计划文档确认后，下一步应进入更细粒度的实施计划阶段，进一步明确：

- 模块级改动落点；
- 关键接口与命令入口；
- 测试拆分与回归顺序；
- 实施依赖关系；
- 阶段性完成标准。

该阶段再展开到文件级或接口级实施计划，不在本文档中继续展开。
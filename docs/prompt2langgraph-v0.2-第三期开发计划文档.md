# prompt2langgraph v0.2 第三期开发计划文档

## 1. 文档目的

本文档用于定义 `prompt2langgraph` v0.2 第三期的工程实施设计，作为后续详细实施计划、代码改动与测试回归的直接依据。

本文档聚焦 **目标、范围、模块任务与验收标准**，采用"严格三期范围 + 模块级任务拆解"的方式组织内容，不展开到文件级或接口级实施步骤。

---

## 2. 阶段定位

v0.2 采用《三期任务划分方案A》中"目标链路优先"的推进策略。第三期对应其中的 **Skill 与控制流补全（Skill & Control Flow Completion）**，核心目标是在 v0.2 第一期已实现的 `Prompt → LLM → JSON plan → WorkflowSpec` 输入闭环和第二期已实现的真实 LLM/Tool 执行能力基础之上，按增强项方式补齐 Skill 到工作流的 alpha 生成能力、Join 控制流最小执行语义、Side Effect 审批最小闭环，并增强运行时状态管理的持久化边界。

第三期是 v0.2 的增强收尾阶段，其重点不是重新定义 v0.2 主版本目标，而是在前两期已打通的输入链路和执行链路之上增加可裁剪能力。若 Skill alpha、Join、Side Effect 或 SQLite 持久化中的部分增强项因复杂度或依赖兼容性暂缓，v0.2 主线仍以 Prompt 输入闭环、真实 LLM/Tool 执行能力和对应诊断测试作为版本达成基线。

第三期的核心特征是：**复用前两期已打通的链路，以最小增量补齐剩余缺口。**

1. Skill 转换复用第一期 `Prompt → LLM → JSON plan → WorkflowSpec` 链路，将输入从自然语言 Prompt 扩展为 Skill 目录下的 `SKILL.md` 原始内容与 `SkillDirectoryAnalysis` 结构化分析结果；
2. Join 执行复用现有 fanout reducer 隐式合并机制，无需新增节点类型；
3. Side Effect 审批复用现有 `human_gate` 的 `interrupt()` + `Command(resume=...)` 模式；
4. 运行时持久化优先复用 LangGraph 的 `BaseCheckpointSaver` 注入接口，CLI 默认 `SqliteSaver` 作为增强项，在依赖兼容性确认后启用。

---

## 3. 阶段目标

v0.2 第三期的阶段目标是：

- 基于 v0.1 已有的 `analyze_skill_dir()` 静态分析能力与 `SKILL.md` 原始内容，实现 Skill → `WorkflowSpec` 的 LLM 驱动 alpha 转换，使 Skill 具备进入工作流编译链路的受控入口；
- 补齐 `join` 边在 IR 模型和编译器中的最小执行语义，通过 Reducer 隐式合并实现多源 fan-in，并明确 reducer 缺失、并行写入顺序不稳定等约束；
- 为 `side_effect` 节点提供带审批中断的最小执行器，复用现有 LangGraph `interrupt()` + `Command(resume=...)` 机制，首期仅承诺 approved/rejected 二元审批；
- 抽象 Checkpointer 注入接口，解耦对 `InMemorySaver` 内部结构的耦合；CLI 默认 `SqliteSaver` 作为可选增强，在依赖兼容性确认后启用；
- 在整个过程中保持前两期已交付能力（Prompt 输入闭环、真实 LLM/Tool 执行、策略约束体系）的完全兼容。

一句话概括：**第三期是在前两期打通的输入和执行链路之上，以可裁剪方式补齐 Skill alpha 生成、Join 最小控制流、Side Effect 审批闭环和 Checkpointer 注入边界，提升 v0.2 对项目目标的覆盖度。**

---

## 4. 纳入范围

第三期纳入以下范围：

1. 实现 Skill → `WorkflowSpec` 的 LLM 驱动 alpha 转换器，以 Skill 目录下的 `SKILL.md` 原始内容作为主语义输入，以 `SkillDirectoryAnalysis` 的步骤、资源和风险诊断作为结构化约束上下文，生成简化 JSON plan 后再经 `JSONPlanAdapter` 转为 `WorkflowSpec`；
2. 为 Skill 工作流支持从 CLI/API 注入参数，明确 scripts/assets/references 资源在工作流中的表示方式；
3. 补齐 `join` 边在 IR 和编译器中的 Reducer 隐式合并执行语义；
4. 为 `side_effect` 节点提供基于 LangGraph `interrupt()` 的审批中断最小执行器；
5. 抽象 Checkpointer 注入接口，支持 `BaseCheckpointSaver` 依赖注入；CLI 默认使用 `SqliteSaver` 作为增强项，不阻塞核心第三期验收；
6. 同步更新验证、Mermaid 表达、fixtures 与回归测试；
7. 同步更新文档，至少包括 `README.md`、`CLAUDE.md`、`AGENTS.md`。

---

## 5. 明确排除范围

第三期不纳入以下内容：

- 不实现完整生产级数据库持久化方案（Postgres 等作为后续演进方向）；
- 不实现多 provider 适配器模式或 model discovery；
- 不实现 subprocess 沙箱、Docker 隔离或网络访问控制；
- 不实现 LLM 输出质量评估或多轮规划/反思/自动修复机制；
- 不改变前两期已交付的 `validate / compile / run / graph / plan / resume` 命令行为兼容性；
- 不改变现有 mock executor 的行为和注册路径；
- 不将 Web UI、HTTP 服务化、性能并行优化纳入 v0.2 主体范围；
- 不生成完全自包含、脱离运行时库的静态代码包；
- 不让 Skill 转换链路直接执行 Skill 脚本（保持"分析资源而非默认执行资源"的安全边界）；
- 不实现 `LANGCHAIN_TOOL` 类型 executor 的可执行能力。

---

## 6. 设计原则

第三期设计应遵守以下原则：

### 6.1 复用优先于新增

第三期各模块的设计基准是优先复用前两期已实现的能力，而非发明新的并行机制。Skill 转换复用 Prompt → LLM → JSON plan 链路，Join 执行复用 fanout reducer 机制，Side Effect 审批复用 `interrupt()` + `resume` 模式，Checkpointer 复用 LangGraph `BaseCheckpointSaver` 注入接口。

> **设计依据**：LangGraph 的 `StateGraph` 采用"增量构建"模式——通过 `add_node` → `add_edge` → `compile` 三步渐进构建，每一步都可独立验证。本计划遵循同样的增量策略：第三期不重新设计架构，而是在前两期已验证稳定的链路和基础设施之上做最小扩展。参见 LangGraph 的 [Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api) 中的增量构建模式和 [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api)。

### 6.2 Skill 转换：SKILL.md 原文 + 静态分析约束

Skill 转换器读取 Skill 目录下的 `SKILL.md` 文件原始内容作为主语义输入，同时将 `analyze_skill_dir()` 的静态分析结果作为结构化约束上下文提供给 LLM，包括步骤提取结果、资源清单、风险诊断和 `draft_nodes`。其中 `SkillDirectoryAnalysis` 不是可直接执行的中间 IR，但其风险诊断优先级高于 LLM 自由判断：若静态分析发现高危操作（shell 脚本、网络调用、secrets、文件写入等），转换器必须在结果中保留诊断，并要求生成 workflow 包含审批边界；若 LLM 输出缺少必要审批边界，后续校验应返回明确 diagnostic，而不是静默接受。

Skill 转换在第三期定位为 alpha 能力，验收重点是“可生成、可诊断、可人工修正”，不承诺任意 Skill 都能一次性转换为可执行工作流，也不默认执行 Skill 目录下的 scripts、assets 或 references。

> **设计依据**：Deep Agents 的 Skills 系统通过 `create_deep_agent(skills=[...])` 将预定义的 skills 注入 agent，但 skills 的执行受 middleware 约束——`HumanInTheLoopMiddleware` 通过 `interrupt_on` 参数配置哪些工具调用需要审批。Deep Agents 的 Skills 有三个值得借鉴的设计点：(1) **渐进式加载（Progressive Disclosure）**：Skills 的 SKILL.md 通过 frontmatter description 做匹配，agent 只在判断需要时才加载完整内容，减少上下文消耗；(2) **Skills + SubAgents 组合**：subagent 不继承父 agent 的 skills，需要显式配置——提示 Skill → Workflow 转换时可能需要区分主 workflow 和子 workflow；(3) **Filesystem Backend 抽象**：Skills 依赖 backend 提供文件访问能力，资源建模可参考此抽象。本计划的 Skill → Workflow 转换遵循"分析-生成-审批"三层模型：分析阶段通过 `analyze_skill_dir()` 提取步骤和风险信号，生成阶段通过 LLM 将步骤映射为工作流节点并对高危步骤插入 `human_gate`，执行阶段通过策略约束和 interrupt 机制确保审批边界。参见 Deep Agents 的 [Customization](https://docs.langchain.com/oss/python/deepagents/customization) 和 [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)。

### 6.3 Join 声明式汇聚：便捷语法模式

Join 边采用单一的便捷语法模式：`join_sources` 声明哪些源节点需要汇聚到 target，编译器自动为 `join_sources` 中的每个源节点生成 `builder.add_edge(source, target)` 调用。用户只需声明"哪些节点汇聚到哪个节点"，编译器自动生成所需的边连接，无需手写多条 LINEAR 边。

如果 `join_sources` 中的某个源节点已有指向同一 target 的 LINEAR 边，验证阶段报 diagnostic warning 提示重复边定义，编译器跳过该源节点的 `add_edge()` 调用（避免 LangGraph 重复边错误）。

基础机制：state schema 中声明的 reducer（如 `APPEND`、`MERGE_DICT`）在 LangGraph 的 superstep 边界自动聚合多源输出。这不需要新增 `join` 节点类型或专门的 join executor，只需在 IR 和编译器层面补齐 join 边的声明语义和必要的边连接。

`join_sources` 字段的本质是"语法糖"——让用户以声明方式表达汇聚意图，编译器自动处理边连接。JOIN 边等价于多条 LINEAR 边的简写，但其聚合结果仍遵循 LangGraph reducer 语义：未声明 reducer 的 state key 默认覆盖，多个并行分支的更新顺序不保证稳定。若用户需要稳定顺序，应要求分支输出携带可排序字段，由 target 节点显式排序。

> **设计依据**：LangGraph 的并行执行模型基于 superstep——同时触发的所有节点在同一 superstep 中并发执行，整个 superstep 是事务性的（全部成功或全部回滚）。当多个并行分支写入同一 state key，reducer 在 superstep 边界自动聚合写入。fan-in 的正确工作前提是：**多个并行分支通过各自的 `add_edge()` 指向同一个 target 节点**，LangGraph 才能保证 target 在所有源完成后执行。这正是 [Run graph nodes in parallel](https://docs.langchain.com/oss/python/langgraph/use-graph-api#run-graph-nodes-in-parallel) 中描述的 fan-out/fan-in 模式。LangGraph 的 [Send API](https://docs.langchain.com/oss/python/langgraph/graph-api#send) 为动态 fan-out 提供了 `Send(node, state)` 机制——本计划中已有的 `FANOUT` 边已使用 `Send`，而 `JOIN` 边是对 fan-in 模式的声明式封装。

### 6.4 Side Effect 审批：中断等待而非预注册执行

Side effect 节点执行时，先通过 LangGraph `interrupt()` 挂起，将副作用详情（节点 ID、参数、幂等键、资源路径）暴露给调用方。调用方通过 CLI `resume` 或 API `resume_payload` 传入审批结果（`approved`/`rejected`）后继续或终止。这与现有 `human_gate` 的 interrupt/resume 机制完全一致，复用已有基础设施。第三期核心闭环只承诺二元审批和拒绝不执行；幂等记录、多中断批量恢复、`edited/respond` 决策属于后续增强，不作为核心完成门槛。

> **设计依据**：LangGraph 的 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 机制允许在节点函数内部任意位置调用 `interrupt()` 挂起执行，通过 `Command(resume=...)` 恢复。LangChain v1 的 `HumanInTheLoopMiddleware` 通过 `interrupt_on` 配置需要审批的工具调用，提供 `approve`/`edit`/`reject`/`respond` 四种审批决策。本计划的 Side Effect 审批模型借鉴此模式：`side_effect` 节点在执行前调用 `interrupt()` 等待审批，审批通过后才执行实际的副作用操作。参见 LangChain 的 [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) 和 [Middleware hooks](https://docs.langchain.com/oss/python/releases/langchain-v1#custom-middleware)。

### 6.5 Checkpointer 注入：依赖抽象而非具体实现

`run_workflow()` 和 `compile_workflow_to_graph()` 接受 `checkpointer` 参数，类型为 LangGraph 的 `BaseCheckpointSaver`。核心目标是让运行时依赖 checkpointer 抽象，而不是依赖 `InMemorySaver` 的私有结构。CLI 默认使用 `SqliteSaver` 提供稳定的本地持久化可作为增强项推进；若 `langgraph-checkpoint-sqlite` 依赖或 API 兼容性存在风险，则第三期应先保留现有 CLI 行为，并只交付 checkpointer 注入边界。

> **设计依据**：LangGraph 的 [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 文档列出了多种 checkpointer 实现（`InMemorySaver`、`SqliteSaver`、`PostgresSaver` 等），所有实现遵循统一的 `BaseCheckpointSaver` 接口。LangGraph 的 `compile(checkpointer=...)` 接受任意 `BaseCheckpointSaver` 实现，调用方可通过依赖注入切换存储后端而不修改图逻辑。本计划遵循同样的接口抽象原则：`run_workflow()` 和 `compile_workflow_to_graph()` 接受 `BaseCheckpointSaver` 参数，CLI 默认注入 `SqliteSaver`，测试注入 `InMemorySaver`。参见 LangGraph 的 [Checkpointer integrations](https://docs.langchain.com/oss/python/integrations/checkpointers/index) 和 [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence#checkpointer-libraries)。

### 6.6 可测试性内建

Skill 转换器的 LLM 调用可通过 fake model 隔离测试。Join 语义可独立于运行时执行测试。Side Effect 审批可通过 `InMemorySaver` 的 interrupt/resume 单元测试覆盖。Checkpointer 注入可通过 `InMemorySaver` 测试默认行为。

> **设计依据**：LangChain v1 推荐 fake + integration 双层测试策略（[Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing)）。`InMemorySaver` 可用于模拟 checkpoint 持久化进行单元测试——[InMemorySaver checkpointer](https://docs.langchain.com/oss/python/langchain/test/unit-testing#inmemorysaver-checkpointer) 中展示了使用 `InMemorySaver` 测试多轮对话状态依赖行为。

### 6.7 安全边界保持

Skill 转换不默认执行 Skill 目录下的 scripts。Join 执行不引入新的安全风险（只是 state 聚合）。Side Effect 默认必须经过审批中断（`requires_approval=True`），除非 workflow policy 显式允许副作用（`allow_side_effects=True`）。Checkpointer 不在 bundle 或 lockfile 中写入数据库连接字符串或凭据。

> **设计依据**：第二期已建立的策略体系（`external_call` 开关、模型/工具白名单、`collect_metrics`）在第三期继续适用。Side Effect 的审批机制与第二期的 `check_security()` 策略校验互补——验证阶段检查安全策略完备性，运行阶段通过 interrupt 实施审批。参见 Deep Agents 的 [Human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop) 中的 `interrupt_on` 机制。

---

## 7. 改动文件结构

### 7.1 新增文件

| 文件 | 职责 | 关联模块 |
|------|------|----------|
| `src/prompt2langgraph/prompting/skill_planner.py` | Skill → WorkflowSpec LLM 驱动转换器 | 8.1 |
| `src/prompt2langgraph/registry/side_effect_executor.py` | Side Effect 审批中断执行器 | 8.4 |
| `src/prompt2langgraph/validate/join_check.py` | Join 边结构校验函数 | 8.3 |
| `tests/test_skill_workflow.py` | Skill 转换 + 参数注入集成测试 | 8.1, 8.2 |
| `tests/test_join_execution.py` | Join 边编译和执行测试 | 8.3 |
| `tests/test_side_effect_executor.py` | Side Effect 审批中断测试 | 8.4 |

### 7.2 修改文件

| 文件 | 改动要点 | 关联模块 |
|------|----------|----------|
| `src/prompt2langgraph/ir/models.py` | `EdgeSpec` 新增 `join_sources: list[str] \| None` | 8.3 |
| `src/prompt2langgraph/compiler/langgraph_py.py` | JOIN 边编译 + `SideEffectExecutor` dispatch 路径 + `checkpointer` 参数传递 | 8.3, 8.4 |
| `src/prompt2langgraph/validate/validator.py` | 组合调用 join 校验 | 8.3 |
| `src/prompt2langgraph/validate/join_check.py` | Join 边结构校验函数（在 7.1 中已有—此行为决定不在 `graphcheck.py` 中扩展 join 逻辑，保持各校验维度独立） | 8.3 |
| `src/prompt2langgraph/validate/security.py` | 保持 `check_security()` 与 `allow_side_effects` 联动 | 8.4 |
| `src/prompt2langgraph/registry/builtins.py` | 新增 `builtin.side_effect` schema-only definition（如需要） | 8.4 |
| `src/prompt2langgraph/runtime/runner.py` | `run_workflow()` 签名扩展 + `_checkpointer_for()` 逻辑重构 | 8.5 |
| `src/prompt2langgraph/visualization/mermaid.py` | JOIN 边 `join_sources` 标注 + 虚线汇聚箭头 | 8.3 |
| `src/prompt2langgraph/cli.py` | `plan --skill-dir` 参数 + P2 增强路径中 `run`/`resume` 使用 `SqliteSaver` | 8.2, 8.5 |
| `src/prompt2langgraph/__init__.py` | 暴露 `SkillPlanRequest`、`SkillPlanResult`、`plan_skill_to_workflow_spec` | 8.2 |
| `src/prompt2langgraph/prompting/__init__.py` | 导出 `skill_planner` 符号 | 8.1 |
| `pyproject.toml` | P2 增强路径新增 `langgraph-checkpoint-sqlite>=2.0` 依赖 | 8.5 |
| `README.md` | 同步 Skill 转换、Join、Side Effect、Checkpointer 能力 | 全部 |
| `CLAUDE.md` | 同步能力边界与回归要求 | 全部 |
| `AGENTS.md` | 同步能力边界与回归要求 | 全部 |

### 7.3 复用/确认兼容文件

| 文件 | 关注点 |
|------|--------|
| `src/prompt2langgraph/adapters/skill_dir.py` | `analyze_skill_dir()` 静态分析产物作为 Skill 转换的辅助上下文，不改动 |
| `src/prompt2langgraph/adapters/json_plan.py` | `JSONPlanAdapter` 继续作为 Skill 转换的结果适配入口 |
| `src/prompt2langgraph/prompting/parser.py` | `parse_prompt_plan_text()` 复用为 Skill 转换的 JSON 解析 |
| `src/prompt2langgraph/llm/` | `build_llm_client()` 复用为 Skill 转换的 LLM 客户端构造 |
| `src/prompt2langgraph/ir/normalize.py` | 确认新增 `join_sources` 字段经规范化正确序列化 |
| `src/prompt2langgraph/ir/lockfile.py` | 确认新增字段纳入 hash 计算 |
| `src/prompt2langgraph/runtime/artifacts.py` | 确认编译产物正确序列化新增字段 |
| `src/prompt2langgraph/runtime/events.py` | `RunInterrupt` 事件复用（Side Effect 审批中断与 `human_gate` 共用） |
| `tests/test_compile_flow.py` | 编译产物路径回归 |
| `tests/test_skill_dir.py` | 扩展 Skill → WorkflowSpec 转换测试（fake model） |
| `tests/test_runner.py` | `run_workflow()` 在 checkpointer 注入下的行为回归 |
| `tests/test_cli.py` | CLI `plan`/`run`/`resume` 新参数行为回归 |
| `tests/test_validator.py` | 新增 join 校验路径回归 |
| `tests/fixtures/invalid_join_edge.json` | 保留为缺少 `join_sources` 的无效夹具（验证阶段应报错）；新建 `tests/fixtures/fanout_with_join.json` 作为合法 join fixture |
| `tests/fixtures/side_effect_allowed.json` | 兼容已有的 side_effect 测试夹具 |

---

## 8. 模块任务

### 8.1 Skill → WorkflowSpec 转换器模块

> **代码库现状基线**：`adapters/skill_dir.py` 已实现 `analyze_skill_dir()` 静态分析函数，输出 `SkillDirectoryAnalysis`（含 `name`、`description`、`steps`、`resources`、`draft_nodes`、`report`）。`adapters/json_plan.py` 已实现 `JSONPlanAdapter.parse()` 将简化 JSON plan 转为 `WorkflowSpec`。`prompting/planner.py` 已实现 `plan_prompt_to_workflow_spec()` 串联 Prompt → LLM → JSON plan → `WorkflowSpec`。以下为在现有基础上新增 Skill 到 Workflow 的 LLM 驱动转换器。

读取 Skill 目录下的 `SKILL.md` 原始文件内容作为主语义输入，并将 `analyze_skill_dir()` 的静态分析结果作为结构化约束上下文，通过 LLM 生成简化 JSON plan，再复用 `JSONPlanAdapter` 转为 `WorkflowSpec`。其中 `SKILL.md` 原文保留完整上下文，`SkillDirectoryAnalysis` 提供步骤、资源和风险事实；当两者冲突时，风险诊断和安全约束优先。

该模块应完成：

- 新增 Prompt 模板：为 Skill → JSON plan 生成设计专用的 system prompt，引导 LLM 将 Skill 步骤映射为节点类型（`llm`、`tool`、`transform`、`human_gate` 等），对 `analyze_skill_dir()` 报告中 `E_SEC_007` 诊断检测到的高危步骤（file writes、shell execution、network access、secrets）在生成的 workflow 中插入 `human_gate` 节点作为审批边界。
- 新增 `prompting/skill_planner.py`：
  - `build_skill_plan_prompt(skill_md_text: str, *, analysis: SkillDirectoryAnalysis | None = None, params: dict[str, str] | None = None) -> str`：将 `SKILL.md` 原始内容作为主输入构建 prompt，可选附加 `analyze_skill_dir()` 的分析结果（风险警告摘要、资源清单）和参数上下文；
  - `plan_skill_to_workflow_spec(skill_dir: str | Path, *, params: dict[str, str] | None = None, model_client=None) -> SkillPlanResult`：读取 `SKILL.md` 原始内容 → 可选调用 `analyze_skill_dir()` 获取辅助分析 → 串联 `build_skill_plan_prompt()` → LLM 生成 JSON plan 文本 → `parse_prompt_plan_text()` 解析 → `JSONPlanAdapter().parse()` 适配 → 返回 `SkillPlanResult`（包含 `raw_text`、`plan`、`workflow_spec`、`diagnostics`），与 `plan_prompt_to_workflow_spec()` 返回 `PromptPlanResult` 的模式一致；
  - 复用 `llm.provider.build_llm_client()` 构造 LLM 客户端（与 Planner 共享 `llm/` 基础模块）；
  - 对 LLM 输出的 JSON plan，在适配失败时返回明确的 `AdapterParseError` 诊断，区分"SKILL.md 内容不完整"和"LLM 生成输出不可解析"两类问题。
  - **与 `planner.py` 的关系**：`skill_planner.py` 复用 `planner.py` 的 `generate_plan_text()` 和 `parse_prompt_plan_text()`，仅新增 Skill 专用的 system prompt 构建逻辑（`build_skill_plan_prompt()`）。LLM 调用、JSON 解析和适配逻辑完全复用，不重复实现。
- Skill 转换结果存储：
  - 通过 `plan_skill_to_workflow_spec()` 返回 `SkillPlanResult`（包含 `raw_text`、`plan`、`workflow_spec`、`diagnostics`）；
  - 与 `plan_prompt_to_workflow_spec()` 返回 `PromptPlanResult` 的模式一致（LLM 原始输出和诊断始终对调用方可获取）；
  - 在非确定性 LLM 输出场景下，`raw_text` 和 `diagnostics` 是调试和修复 Skill 转换失败的关键信息，不应丢失。
- Skill 步骤到节点类型的映射规则：
  - LLM 主导映射（通过 system prompt 指导），不硬编码规则表；
  - System prompt 中提供当前可用的节点类型（`llm`、`tool`、`transform`、`router`、`human_gate`、`retriever`、`side_effect`）和 executor 列表（`builtin.echo_llm`、`builtin.identity_transform`、`builtin.route`、`builtin.human_gate`、`builtin.mock_retriever`）；
  - 对识别为"文件读写"、"执行命令"、"网络请求"的步骤，在生成的 workflow 中前置 `human_gate` 节点；
  - 对识别为"信息检索"、"搜索"的步骤，映射为 `retriever` 节点；
  - 对识别为"分析"、"生成"、"回答"的步骤，映射为 `llm` 节点；
  - 对无法明确映射的步骤，默认映射为 `llm` 节点并添加诊断 warning。

- LLM Prompt 稳定性增强：
  - **Few-shot 示例**：在 system prompt 中包含 2-3 个 Skill 步骤 → JSON plan 节点的映射示例，覆盖以下典型场景：
    - 简单线性 workflow（检索 → 分析 → 回答）；
    - 含高危步骤的 workflow（文件写入前置 human_gate）；
    - 含 tool 节点的 workflow（脚本执行）。
  - **输出格式约束**：在 system prompt 中明确 JSON plan 的必需字段（`name`、`inputs`、`outputs`、`nodes`、`edges`）和节点必需字段（`id`、`kind`、`executor`），降低解析失败率。
  - **JSON 解析失败后的降级策略**：
    - 若 LLM 输出包含 markdown fence（如 ` ```json ... ``` `），自动提取 fence 内 JSON 后再解析；
    - 若 JSON 结构基本完整（name、nodes 存在）但个别字段缺失，自动补全默认值（如缺失 `edges` 补为 `[]`，缺失 `outputs` 补为 `{}`）并附带 diagnostic warning；
    - 若 JSON 完全不可解析，返回 `AdapterParseError` 诊断，同时在诊断中附带 LLM 原始输出前 500 字符 + 最小骨架 JSON plan 模板，方便用户修改后重试；
    - 降级策略的目标是"尽量减少用户手动修复成本"，而非"隐式修复所有错误"。

设计约束：

- LLM 只负责生成 JSON plan，不直接生成 `WorkflowSpec`（与第一期 Prompt 计划生成的设计约束一致）；
- Skill 转换不默认执行 Skill 目录下的 scripts、assets 或 references；
- 生成的 workflow 必须进入现有 `validate_workflow()` 校验链路，不能绕过校验；
- `plan_skill_to_workflow_spec()` 的签名与 `plan_prompt_to_workflow_spec()` 保持一致的 LLM 客户端注入模式；
- 生成的 workflow 中不写入真实的 secret、API key 或 model 凭据。

非确定性与可复现性说明：

- Skill 转换经由 LLM 生成 JSON plan，同一 Skill + 同一参数可能产生不同的 `WorkflowSpec`。这是 LLM 驱动生成的固有特性；
- `SkillPlanResult` 中包含 `raw_text`（LLM 原始输出）和 `diagnostics`（解析诊断），方便用户在转换失败时手动修正；
- 建议用户对生成的 `WorkflowSpec` 做版本控制（如保存为 JSON 文件到 Skill 目录下的 `.pt2lg/` 子目录），而非每次重新从 Skill 转换；
- System prompt 中建议 LLM 使用 `temperature=0.0`，以提高 Skill 转换输出的稳定性和可复现性；
- 后续可考虑增加"Skill 转换结果缓存"机制（对同一 Skill 目录 + 参数组合缓存 LLM 生成的 JSON plan），但此能力不在第三期范围内。

> **设计依据**：Deep Agents 的 Skills 系统通过 `create_deep_agent(skills=[...])` 将预定义的 skills 作为工具注入 agent（[Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)）。本计划的 Skill 转换器将 Deep Agents 的"Skills 注入"理念适配到 prompt2langgraph 的"Skills 编译"场景：不是将 Skill 作为工具注入运行时 agent，而是将 Skill 的原始文档内容通过 LLM 转换为可编译的工作流定义。直接使用 `SKILL.md` 原始内容而非 `SkillDirectoryAnalysis` 中间结构，可以保留文档的完整上下文、格式信息和隐含语义，避免结构化过程中的信息丢失。LangChain v1 的 `init_chat_model()` 辅助函数支持统一的模型客户端构造（[Chat model integrations](https://docs.langchain.com/oss/python/integrations/chat/index)），Skill planner 复用第二期建立的 `llm/` 基础模块。

### 8.2 Skill 参数注入与资源建模模块

支持从 CLI/API 向 Skill 工作流注入参数，并明确 Skill 资源（scripts/assets/references）在工作流中的表示方式。

该模块应完成：

- 扩展 CLI：
  - 扩展现有 `pt2lg plan` 命令的输入源，新增 `--skill-dir` 参数从 Skill 目录生成 `WorkflowSpec`：
    - 接受 `--skill-dir` 参数指定 Skill 目录（与现有 `--prompt` 参数互斥，二选一）；
    - 接受 `--param` 参数（可多次指定，格式 `key=value`）注入 Skill 参数；
    - 输出生成的 JSON plan 和/或 workflow IR；
    - 复用现有 `plan` 命令的 `--json` 输出格式和错误处理风格；
  - 不引入 `skill` 子命令组，避免破坏现有 `pt2lg <command>` 的扁平 CLI 架构。
- 扩展 Public API：
  - 在 `__init__.py` 中暴露 `SkillPlanRequest`、`SkillPlanResult`、`plan_skill_to_workflow_spec`；
  - `SkillPlanRequest` 包含 `skill_dir: str`、`params: dict[str, str]`、`model`、`base_url`、`api_key`、`temperature`；
  - `SkillPlanRequest` 的 LLM 配置字段（`model`、`base_url`、`api_key`、`temperature`）委托 `llm.config.LLMConfig` 构造 LLM 客户端（与 `PromptPlanRequest` 委托 `build_model_client()` 的模式一致），不独立定义配置加载逻辑；
  - `SkillPlanResult` 包含 `raw_text`、`plan`、`workflow_spec`、`diagnostics`。
- 资源建模：
  - 在 Skill → workflow 转换的 system prompt 中，从 `SKILL.md` 原文中提取资源引用信息，同时可选附加 `analyze_skill_dir()` 扫描的 `scripts/`、`references/`、`assets/` 目录文件清单传递给 LLM，让 LLM 在生成的 JSON plan 中通过 `params` 或节点描述反映资源依赖；
  - 对 `resources.scripts` 中列出的脚本路径，如果 LLM 尝试在 workflow 中引用，生成 `tool` 节点并标记 `security.allowed_tool_refs` 为空（需要在执行前由用户显式授权注册对应的 tool callable）；
  - 不自动将 Skill 资源路径写入 workflow 的 `tool` executor ref。
- 参数注入：
  - Skill 参数通过 CLI `--param` 或 API `SkillPlanRequest.params` 传递；
  - 参数在工作流中的落地方式由 LLM 在生成 JSON plan 时决定（作为 `inputs` 的 state key 或 `params` 的模板变量）；
  - 参数值的有效性校验仍在 `validate_workflow()` 阶段进行。

设计约束：

- 不默认执行 Skill 脚本；
- 不自动注册 Skill 资源相关的 tool callable；
- 参数注入不改变 Skill 转换的 LLM 驱动本质（只是向 LLM prompt 增加参数上下文）；
- `plan --skill-dir` 与 `plan --prompt` 共享错误处理、JSON 输出格式和诊断风格。

### 8.3 Join 边执行支持模块

> **代码库现状基线**：`ir/models.py` 中 `EdgeKind.JOIN = "join"` 已定义。`runtime/runner.py` 中 `_check_target_capabilities()` 已将 `JOIN` 排除在支持的 edge kind 之外（报 `E_TARGET_009`）。`visualization/mermaid.py` 已能渲染 `JOIN` 边。`tests/fixtures/invalid_join_edge.json` 为测试夹具。以下为在现有基础上补齐 Join 边的执行语义。

补齐 `join` 边在 IR 模型和编译器中的 Reducer 隐式合并执行语义。

该模块应完成：

- 扩展 IR 模型：
  - 在 `EdgeSpec` 中新增 `join_sources: list[str] | None = None` 字段，声明 join 边需要等待的源节点列表；
  - `join_sources` 必须非空且所有 source node id 必须在 workflow 的 nodes 中存在；
  - 当 `kind=JOIN` 时，`source` 字段设为 `join_sources[0]`（保持 `EdgeSpec` 的单一 source 约束），`join_sources` 为必填字段；
  - 当 `join_sources` 为 `None` 或空列表时，编译阶段报错。
- 扩展验证：
  - 新增 `validate/join_check.py`（或在现有 `validate/graphcheck.py` 中新增 join 校验函数）：
    - 检查 `join_sources` 非空；
    - 检查所有 `join_sources` 中的节点在 workflow 中存在；
    - 检查 join 边的 target 节点不是 join_sources 中的任何一个（避免自引用）；
    - 验证 join_sources 中节点的 `outputs` 写入的 state key 是否声明了 reducer（对于多个节点写入不同 key 且均无 reducer 的情况，报 diagnostic warning）；
    - 检查 `join_sources` 中的源节点是否已有指向同一 target 的 LINEAR 边（若有，报 diagnostic warning 提示重复边定义）；
    - join 边是声明式汇聚语法糖，编译器据此生成必要的 `add_edge()` 并验证 reducer 声明。
- 扩展编译器：
  - JOIN 边的 `join_sources` 中的每个源节点，编译器自动生成 `builder.add_edge(source, target)` 调用；
  - 如果某个源节点已有指向同一 target 的 LINEAR 边（验证阶段已报 warning），编译器跳过该源节点的 `add_edge()` 调用，避免 LangGraph 重复边错误；
  - JOIN 边的 reducer 聚合语义通过 LangGraph 的 superstep 机制隐式实现：多个 `join_sources` 节点写入同一个 state key，reducer（在 `state_schema.reducers` 中声明）自动聚合；
  - 编译器需要在 `compile_workflow_to_graph()` 中验证：对于每个 JOIN 边，其 `join_sources` 中的节点确实写入了需要 reducer 聚合的 state key（即这些节点的 `outputs` 中有指向同一个 state key 且该 key 声明了 reducer）；
  - 如果 JOIN 边的 `join_sources` 中的节点没有共同的 state key 写入，报 diagnostic warning（不阻断编译，但提示 join 语义可能无实际效果）；
  - 如果 `join_sources` 中的节点写入了不同 key 且每个 key 都有 reducer，则各自独立聚合（符合预期行为）。
- 移除 `JOIN` 从不受支持的 edge kind 列表中：
  - 在 `_check_target_capabilities()`（位于 `runtime/runner.py`）中将 `EdgeKind.JOIN` 加入 `supported` 集合；
  - 移除 `tests/fixtures/invalid_join_edge.json` 的"invalid"标记（移动为合法测试夹具或保留为缺少 `join_sources` 的无效夹具）。
- 更新 Mermaid 表达：
  - 在 `visualization/mermaid.py` 中为 JOIN 边增加 `join_sources` 标注；
  - JOIN 边在 Mermaid 中渲染为从多个 source 节点到 target 节点的虚线汇聚箭头。

设计约束：

- 不新增 `join` 节点类型或专门的 join executor；
- JOIN 边采用单一便捷语法模式：编译器根据 `join_sources` 自动生成 `add_edge()` 调用，语义始终确定；
- 如果 `join_sources` 中的源节点已有指向同一 target 的 LINEAR 边，验证阶段报 warning，编译器跳过重复的 `add_edge()`；
- 现有的 fanout map-reduce 机制不受 JOIN 边影响；
- `check_types()` 仍需校验 join 相关节点的 input/output type 兼容性；
- **向后兼容**：v0.1 已定义 `EdgeKind.JOIN` 枚举值且 `tests/fixtures/invalid_join_edge.json` 中已有 JOIN 边夹具（当前为"可表达不可执行"状态）。Phase 3 补齐执行语义后，当 `kind=JOIN` 且 `join_sources` 为 `None` 或空时，验证阶段应输出明确的迁移提示（而非仅报通用错误），告知用户需添加 `join_sources` 字段。

> **设计依据**：LangGraph 的并行执行模型基于 superstep——同时触发的所有节点在同一 superstep 中并发执行，reducer 在 superstep 边界自动聚合写入（[Run graph nodes in parallel](https://docs.langchain.com/oss/python/langgraph/use-graph-api#run-graph-nodes-in-parallel)）。LangGraph 的 [Map-Reduce and the send API](https://docs.langchain.com/oss/python/langgraph/use-graph-api#map-reduce-and-the-send-api) 展示了 fan-out（通过 `Send` 动态创建并行任务）和 fan-in（通过 reducer 聚合结果）的完整模式。本计划的 JOIN 边是此模式的声明式封装：`join_sources` 声明哪些源节点需要在同一个 join 点汇聚，编译器据此补齐必要的 `add_edge()` 并验证 reducer 声明，实际执行由 reducer 和 superstep 机制自动完成。LangChain v1 的多 agent 架构中 [Result collection with reducers](https://docs.langchain.com/oss/python/langchain/multi-agent/router-knowledge-base#result-collection-with-reducers) 使用 `operator.add` reducer 将并行 agent 的结果收集到共享 state 中，与本计划的 JOIN 语义一致。

### 8.4 Side Effect 最小执行闭环模块

> **代码库现状基线**：`validate/security.py` 中 `check_security()` 已实现 side_effect 节点安全策略检查（`E_SIDE_008`）。`ir/models.py` 中 `PolicySpec.allow_side_effects: bool = False` 和 `SecurityPolicy.requires_approval: bool = False`、`SecurityPolicy.idempotency_key: str | None = None` 已定义。`compiler/langgraph_py.py` 中 `_node_wrapper()` 对 `side_effect` 节点使用 `builtin.identity_transform` 占位执行。以下为在现有基础上补齐 Side Effect 节点的最小审批执行闭环。

为 `side_effect` 节点提供基于 LangGraph `interrupt()` 的审批中断最小执行器。

该模块应完成：

- 新增 `registry/side_effect_executor.py`：
  - `SideEffectExecutor` 类，基于 `langgraph.types.interrupt()` 实现审批中断；
  - `__init__(node_id: str, security: SecurityPolicy, *, allow_side_effects: bool = False)`；
  - `__call__(inputs: dict, params: dict) -> dict`：
    1. 若 `allow_side_effects=True`，返回审批通过信号，由 compiler 层调用实际 executor；
    2. 否则若 `security.requires_approval=True`，调用 `interrupt()` 挂起，payload 包含：`node_id`、`action`（描述副作用操作）、`inputs`（副作用输入数据）、`idempotency_key`（若配置）、`params`；
    3. `interrupt()` 返回 `{"decision": "approved"}` 或 `{"decision": "rejected", "reason": "..."}`；
    4. 若审批通过，返回审批通过信号，由 compiler 层调用实际 executor；
    5. 若审批拒绝，返回 `{"effect_result": "side_effect_rejected", "reason": reason}` 且不调用实际 executor；
    6. 若仅有 `idempotency_key` 但无 `requires_approval`，P1 中仍走审批路径（幂等去重逻辑为 P2 增强），P2 中实现基于 `__pt2lg_side_effect_records__` state key 的去重；
    7. 若无 `requires_approval` 也无 `idempotency_key`，且 `allow_side_effects=False`，直接拒绝执行（防御性行为，正常应在验证阶段被 `E_SIDE_008` 拦截）。
  - `SideEffectExecutor` 是纯审批逻辑层，不持有实际 executor 引用。通过返回审批信号（`__side_effect_signal__`）让 compiler 层决定是否调用实际 executor，实现与 compiler 实现解耦。
- 扩展编译器：
  - 在 `_node_wrapper()` 中新增 `side_effect` 节点的处理路径；
  - 当 `node.kind == "side_effect"` 时，实例化 `SideEffectExecutor` 并调用；
  - 根据 `SideEffectExecutor` 返回的 `__side_effect_signal__` 信号决定是否调用 `_invoke_executor()` 执行实际 executor；
  - `SideEffectExecutor` 不直接调用 `_invoke_executor()`，避免与 compiler 内部实现耦合。
  - `SideEffectExecutor` 需要 `interrupt()` 所需的 checkpointer（通过 `compile_workflow_to_graph()` 的已有 `checkpointer` 参数传入）。
- 扩展 `registry/builtins.py`：
  - 不需要为 `side_effect` 注册新的 `ExecutorType`（复用现有 `BUILTIN` 或 `PYTHON_CALLABLE` 执行实际副作用操作，`SideEffectExecutor` 是包装层）；
  - 在 `builtin_executor_registry()` 中新增 schema-only definition：`ExecutorDefinition(ref="builtin.side_effect", type=ExecutorType.BUILTIN, ...)`（如需要）。
- 更新 `_node_wrapper()` / `invoke_node()`：
  - `side_effect` 节点的执行走 `SideEffectExecutor` 包装路径，而非直接 `executor.invoke()`；
  - 审批中断与现有 `human_gate` 的 interrupt 机制一致，复用 `RunInterrupt` 事件和 resume 流程。

Side Effect 执行流程：

```
node.started
  → SideEffectExecutor.__call__(inputs, params)
    → allow_side_effects=True?
       YES → 返回 {"__side_effect_signal__": "allowed"} → compiler 调用实际 executor → 返回结果
       NO  → requires_approval=True?
               YES → interrupt(payload) → 等待 resume
                      → approved? → 返回 {"__side_effect_signal__": "approved"} → compiler 调用实际 executor → 返回结果
                      → rejected? → 返回拒绝结果
               NO  → 检查 idempotency_key
                      有 key → P1: 仍走审批路径（幂等去重为 P2 增强）
                               P2: 检查 state 中是否已有同 key 执行记录
                                有记录 → 跳过执行，返回缓存结果
                                无记录 → 返回审批信号 → compiler 调用实际 executor → 写入执行记录 → 返回结果
                      无 key → 拒绝执行（防御性）
  → node.finished
```

错误路径行为（审批通过后执行失败）：

```
interrupt() resume approved
  → 调用实际 executor → 执行失败（ExecutorError / 网络异常）
    → ExecutorError 传播到 invoke_node()
    → error_sink 记录失败 ExternalCallRecord（status="failed"）
    → 该节点未完成，其 state 更新不被提交为完整 checkpoint
    → 同一 superstep 中其他已成功节点的写入通过 pending writes（checkpoint_writes）持久化
    → 调用方通过相同 thread_id 重试 run_workflow()
      → LangGraph 从上一个完整 checkpoint 恢复
      → 已成功节点不重新执行（其 pending writes 已持久化）
      → 失败节点从头重新执行（包括重新调用 interrupt()）→ 再次等待审批
      → 审批通过后重试实际 executor
      → 重试成功 → 返回结果；重试仍失败 → 再次传播 ExecutorError
```

> **重要说明**：根据 LangGraph Persistence 文档的 [Pending writes](https://docs.langchain.com/oss/python/langgraph/persistence) 章节，当 superstep 中部分节点失败时，已成功完成节点的写入会通过 `checkpoint_writes`（pending writes）持久化，恢复时不重新执行这些节点。但对于 `SideEffectExecutor` 场景，interrupt 和实际执行在**同一节点内**，该节点未完成则其写入不会被提交为完整 checkpoint。恢复时该节点从头重新执行（包括重新调用 `interrupt()`），需重新获得审批授权。这与安全原则一致：审批授权不应跨失败重试持久化，每次重试应重新获得授权。

幂等键去重逻辑：

```
SideEffectExecutor.__call__() in idempotency_key path:
  1. 从 state 中读取 `__pt2lg_side_effect_records__`（list[dict]）
  2. 遍历 records 列表，查找 idempotency_key 匹配的记录：
     若找到 → 返回缓存结果 {"effect_result": matching_record["result"]}
              → 不调用实际 executor
  3. 若未找到匹配记录：
     → 调用实际 executor
     → 将 {"key": idempotency_key, "result": result, "timestamp": ...} 追加到 `__pt2lg_side_effect_records__`
     → 返回结果
```

> **LangGraph Durable Execution 兼容性说明**：LangGraph 的 [Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) 要求工作流设计为确定性和幂等的，将副作用或非确定性操作包装在 tasks 中。当前第三期使用 `StateGraph` API + `interrupt()` 实现审批中断，审批和实际执行在同一个节点内。当审批通过后执行失败时，该节点未完成，其 state 更新不被提交；但同一 superstep 中其他已成功节点的写入通过 pending writes 持久化，恢复时不重新执行。对于失败节点本身，重试时需要重新审批（见上方"错误路径行为"说明）。
>
> **幂等键去重的性质说明**：本计划的幂等键去重方案通过 `__pt2lg_side_effect_records__` state key 存储执行记录，属于**应用层幂等**（由 prompt2langgraph 自身的 state 逻辑管理）。当前选择应用层幂等的原因是最小闭环优先。后续演进方向见附录《LangGraph `@task` 评估说明》。

- 扩展 CLI resume：
  - `pt2lg resume` 命令支持恢复 `side_effect` 节点的审批中断；
  - resume payload 格式：`{"decision": "approved"}` 或 `{"decision": "rejected", "reason": "..."}`；
  - 与现有 `human_gate` 的 resume 使用相同的 CLI 入口和 `--resume` 参数风格。
- 更新 `validate/security.py`：
  - 保持现有 `check_security()` 的 `E_SIDE_008` 检查不变（side_effect 节点需审批或幂等键，否则报错）；
  - 当 `allow_side_effects=True` 时，`check_security()` 跳过 side_effect 节点的审批检查。

设计约束：

- Side Effect 执行与 `human_gate` 共享 interrupt/resume 基础设施，不引入第二套中断机制；
- 默认 must 审批（`requires_approval=True`），除非 `allow_side_effects=True`；
- `SideEffectExecutor` 不预注册具体的副作用操作 callable（由 workflow JSON 中的 `executor.ref` 决定执行哪个 builtin 或 tool callable）；
- 不在 CLI 或 API 中新增 `side-effect approve` 命令（复用 `resume`）；
- 不在 runner 中为 side_effect 实现自动重试或自动批准。

多中断并行场景（与 Join 组合）：

当 Join 边的多个 `join_sources` 节点均为 `side_effect` 节点时，可能出现多个 `SideEffectExecutor` 在同一 superstep 内并行触发 `interrupt()`。根据 LangGraph 官方 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 文档 "Handling multiple interrupts" 章节，恢复时需要按 interrupt ID 映射 resume value，而非简单的二选一。

- Phase 3 的最小闭环中，期望此场景通过逐一恢复处理（用户按 interrupt 顺序逐个 `resume`）；
- `SideEffectExecutor` 的 interrupt payload 中暴露 interrupt ID（`interrupt_id`），CLI resume 命令根据 ID 配对恢复；
- 此场景作为 Phase 3 的扩展测试用例（`tests/test_side_effect_executor.py` 中包含多 side_effect 并行中断测试），但不作为核心验收标准的强制要求；
- 后续可考虑批量 resume 支持（一次传入多个 `{interrupt_id: decision}` 映射）。

审批决策扩展预留：

- 第三期实现 `approved`/`rejected` 二元审批决策（最小闭环）；
- `SideEffectExecutor` 的 interrupt payload 采用结构化格式，为后续扩展预留字段：
  - Phase 3 interrupt payload 示例：`{"node_id": "...", "action": "...", "inputs": {...}, "idempotency_key": "...", "params": {...}, "interrupt_id": "..."}`；
  - Phase 3 resume value 格式：`{"decision": "approved"}` 或 `{"decision": "rejected", "reason": "..."}`；
  - 预留扩展：`{"decision": "edited", "modified_params": {...}}`（后续，修改参数后执行）、`{"decision": "respond", "response": "..."}`（后续，直接回复文本而不执行副作用）；
- `SideEffectExecutor` 的 `interrupt()` 返回值和 resume value 解析使用兼容性解析（支持未来的扩展字段不影响当前行为）；
- 后续演进方向：
  - `edited` 决策允许调用方修改参数后再执行（参考 LangChain v1 `HumanInTheLoopMiddleware` 的 `approve`/`edit`/`reject`/`respond` 四种决策）；
  - `respond` 决策允许调用方直接回复文本作为工具结果，不执行实际副作用操作——适用于"ask user"交互场景（参考 LangChain v1 HITL middleware 的 `respond` 类型），此能力不在第三期范围内。



> **设计依据**：LangGraph 的 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 机制允许在节点函数内部调用 `interrupt()` 挂起执行，通过 `Command(resume=...)` 恢复。LangChain v1 的 `HumanInTheLoopMiddleware` 提供 `interrupt_on` 配置和 `approve`/`edit`/`reject`/`respond` 四种审批决策（[Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)）。Deep Agents 的 HITL 通过 `create_deep_agent(interrupt_on={...})` 配置审批策略（[Deep Agents HITL](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)）。本计划的 Side Effect 审批模型是这三种模式的简化融合：用 `interrupt()` 挂起，用 `Command(resume=...)` 恢复，审批决策简化为 `approved`/`rejected` 二元选项。注意 `interrupt()` 依赖 checkpointer（`compile(checkpointer=...)`），这与 8.5 节的 Checkpointer 注入接口联动——没有 checkpointer 则 interrupt 无法生效，这也是第三期需要引入 SqliteSaver 的动因之一。

### 8.5 运行时状态边界增强模块

> **代码库现状基线**：`runtime/runner.py` 中 `_checkpointer_for()` 创建 `InMemorySaver`，`_save_thread_state()` / `_load_thread_state()` 通过 JSON 序列化 `InMemorySaver.storage` / `.writes` / `.blobs` 内部结构做本地持久化。`compile_workflow_to_graph()` 已接受 `checkpointer` 参数但 runner 使用 `InMemorySaver`。以下为在现有基础上抽象 Checkpointer 注入接口。

抽象 Checkpointer 注入接口，解耦对 `InMemorySaver` 内部结构的依赖。CLI 默认使用 `SqliteSaver` 提供稳定本地持久化是增强项，应在依赖兼容性确认后启用；若 SQLite checkpointer 暂不可用，第三期仍应先完成 `BaseCheckpointSaver` 依赖注入边界，并保持现有 CLI runtime 状态行为兼容。

该模块应完成：

- 修改 `runtime/runner.py` 中的 `run_workflow()` 签名：
  - 新增 `checkpointer: BaseCheckpointSaver | None = None` 参数（可选依赖注入）；
  - `checkpointer` 为 `None` 时，保持现有行为创建 `InMemorySaver`（向后兼容，测试和 API 调用方无需修改）；
  - CLI 内部可在增强路径中显式构造 `SqliteSaver` 并通过 `checkpointer=sql_saver` 参数传入，不改变 `None` 的默认语义；
  - 优先减少对 `_THREAD_CHECKPOINTERS` 全局字典的依赖，使 checkpointer 生命周期由调用方管理或 runner 内部通过稳定接口管理；
  - `_save_thread_state()` / `_load_thread_state()` 的 JSON 序列化逻辑在 SQLite 增强路径启用后可被替换；若 SQLite 暂缓，则保留旧逻辑并补充明确诊断，避免破坏现有跨进程 resume；
  - 保留 `.pt2lg-runtime/` 目录作为本地 runtime 状态存储路径；SQLite 增强路径使用数据库文件，旧路径继续使用 JSON 状态文件；
  - 保留 `_clear_thread()` 逻辑（清理 pending interrupt 标记和对应 runtime 状态文件）。
- 修改 `run_workflow()` 的 Checkpointer 管理：
  - P0/P1 路径中，`resume` 继续复用现有 thread key 与 JSON runtime 状态，避免破坏当前跨进程恢复行为；
  - P2 SQLite 增强路径中，`resume` 时复用同一个 `SqliteSaver` 实例（通过 thread key 映射到 SQLite 文件路径）；
  - P2 SQLite 增强路径中，`SqliteSaver` 初始化时构造 `sqlite3.connect()` 连接即可。**实施前需确认**：`langgraph-checkpoint-sqlite>=2.0` 的 `SqliteSaver` 是否需要在构造后调用 `setup()` 创建表结构（根据 LangGraph 官方 Add Memory 文档，多数数据库 checkpointer 提供 `setup()` 方法执行迁移；SQLite 是否自动建表取决于具体版本）。若需要 `setup()`，在 CLI 初始化后调用；如不需要（SQLite 通过 `sqlite3.connect()` 自动建表），则无需。建议实现时添加 `try/except` 防御性调用 `setup()` 以确保跨版本兼容；
  - P2 SQLite 增强路径中，完成执行或 resume 成功后，可选择性保留或清理 SQLite 文件（建议保留以支持后续 time travel debugging）。
- 新增依赖：
  - 仅在启用 P2 SQLite 增强路径时，在 `pyproject.toml` 中新增 `langgraph-checkpoint-sqlite>=2.0` 依赖；
  - **版本兼容性确认**：实施前需确认 `langgraph-checkpoint-sqlite>=2.0` 与当前项目使用的 `langgraph>=1.0,<2.0` 版本兼容，以及 `SqliteSaver` 的确切构造方式。根据 LangGraph 官方文档，`SqliteSaver` 的构造方式为 `SqliteSaver(sqlite3.connect("path/to/db"))`（注意：`from_conn_string()` 是 `PostgresSaver` 的 API，`SqliteSaver` 不提供该方法）。若发现 API 不兼容，优先考虑升级 `langgraph` 依赖范围或降级 `langgraph-checkpoint-sqlite` 版本。
- **备选方案**：若 `langgraph-checkpoint-sqlite>=2.0` 与当前 `langgraph>=1.0,<2.0` 存在无法解决的兼容性问题，回退为保持 `InMemorySaver` 默认行为 + 在文档中说明 SQLite 持久化作为后续升级项（Phase 3 其他功能模块（Skill、Join、Side Effect）不受影响，仅在 CLI `run`/`resume` 的持久化行为上保持现状）。
- 保持 `InMemorySaver` 兼容路径：
  - `compile_workflow_to_graph()` 的 `checkpointer` 参数声明类型保持为泛型 `Any` 或 `BaseCheckpointSaver`，同时兼容 `InMemorySaver` 和 `SqliteSaver`；
  - 测试仍可使用 `InMemorySaver`（`tests/test_runner.py` 中构造 `InMemorySaver()` 注入）。
- 更新 CLI：
  - P0 路径保持 `pt2lg run` 和 `pt2lg resume` 的现有行为兼容，继续支持当前 `.pt2lg-runtime/*.json` 跨进程 resume 状态；
  - P2 增强路径可将 CLI 内部切换为 `SqliteSaver`（默认路径 `<bundle_dir>/.pt2lg-runtime/<thread_hash>.db`）；
  - 不需要新增 CLI 参数（checkpointer 类型不暴露给用户选择，内部默认行为即可）。
- 更新 public API：
  - `run_workflow()` 接受可选的 `checkpointer` 参数；
  - 调用方可通过注入自定义 `BaseCheckpointSaver` 实现切换存储后端。
- 保持 `.pt2lg-runtime/` 清理行为：
  - P0 路径保持现有 JSON 状态文件在 resume 成功后清理的行为；
  - P2 SQLite 增强路径中，resume 成功后可默认保留 `.pt2lg-runtime/<thread_hash>.db` 文件以支持 time travel debugging，但必须在文档中明确这是行为变化；
  - 若用户需要显式清理 SQLite checkpoint，后续可增加 `--cleanup` 参数（此参数超出第三期范围）。

旧格式迁移策略：

- 现有 `.pt2lg-runtime/*.json` 文件在 P0 路径继续支持，确保第三期不会破坏已有等待态恢复；
- 若启用 P2 SQLite 增强路径，`_load_thread_state()` 中增加格式检测：遇到旧 JSON 格式时返回明确诊断，提示用户重新运行 workflow 或清理旧状态文件（不尝试迁移 `InMemorySaver` 私有结构）；
- 文档中声明 SQLite 增强路径与旧 JSON 状态文件的兼容关系，避免用户误以为旧等待态可无损迁移。

SQLite 并发说明：

- SQLite 支持并发读但只支持单写。当前方案按 thread hash 分文件，不同 thread 使用不同 SQLite 文件，同一 thread 的 run/resume 串行执行，不存在写冲突；
- 不支持多个 CLI 进程对同一 thread 同时执行 run/resume（SQLite WAL 模式可缓解但不保证，此场景超出第三期范围）。

设计约束：

- 不引入生产级 PostgresSaver（作为后续演进方向）；
- 不在 bundle/lockfile 中写入数据库连接字符串或凭据；
- `.pt2lg-runtime/` 路径约定保持兼容；P0 保持 JSON 状态文件，P2 SQLite 增强路径使用 `.db` 文件；
- `SqliteSaver` 的构造方式为 `SqliteSaver(sqlite3.connect("path"))`，实施前需确认是否需要调用 `setup()`（根据具体版本而定；建议实现时添加 `try/except` 防御性调用以确保跨版本兼容）；
- 不完全移除 `InMemorySaver` 路径（`checkpointer=None` 仍创建 `InMemorySaver`，保持向后兼容；测试和 API 调用方无需修改；CLI 通过显式传入 `SqliteSaver` 使用 SQLite 持久化）。

> **设计依据**：LangGraph 的 [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 文档列出了 `InMemorySaver`（内置，用于实验）、`SqliteSaver`（需 `langgraph-checkpoint-sqlite`，用于本地开发）和 `PostgresSaver`（需 `langgraph-checkpoint-postgres`，用于生产）三种 checkpointer。`compile(checkpointer=...)` 接受任意 `BaseCheckpointSaver` 实例，调用方可通过依赖注入切换。根据 LangGraph 官方文档，`SqliteSaver` 的构造方式为 `SqliteSaver(sqlite3.connect("path/to/db"))`（[Checkpointer libraries](https://docs.langchain.com/oss/python/langgraph/persistence#checkpointer-libraries)），注意 `from_conn_string()` 是 `PostgresSaver` 的 API，`SqliteSaver` 不提供该方法；对于是否需要 `setup()`，需根据 `langgraph-checkpoint-sqlite` 具体版本确认（根据 LangGraph 官方 [Add Memory](https://docs.langchain.com/oss/python/langgraph/add-memory#database-management) 文档，多数数据库 checkpointer 提供 `setup()` 方法执行迁移，实施时建议添加 `try/except` 防御性调用以确保跨版本兼容）。本计划的 Checkpointer 注入与 LangGraph 原生模式完全一致：`run_workflow()` 接受 `BaseCheckpointSaver` 参数，CLI 默认注入 `SqliteSaver(sqlite3.connect("path/to/thread.db"))`，测试注入 `InMemorySaver`。LangGraph 的 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 机制依赖 checkpointer 才能正确工作——`interrupt()` 调用时 graph state 被保存为 checkpoint，resume 时从该 checkpoint 恢复。这也是第三期引入 `SqliteSaver` 的根本动因：稳定的持久化使得 `side_effect` 的审批中断、`human_gate` 的多轮交互和后续 time travel debugging 成为可能。

### 8.6 State Schema 类型系统跨模块考量

第三期多个模块涉及 state schema 的读写，需统一考虑 state key 的命名、reducer 声明和类型推导规则。

**Skill 参数注入 → State Schema 映射：**

- Skill 参数（通过 CLI `--param key=value` 或 API `SkillPlanRequest.params` 传入）自动映射为 workflow 的 `inputs` 中的 state key；
- 参数类型由 LLM 在生成 JSON plan 时推断（`string` / `number` / `boolean`），默认 string；
- 生成的 `WorkflowSpec.inputs` 中自动包含这些参数声明；
- **保留字约束**：内部 state key（`__pt2lg_side_effect_results__`、`__pt2lg_side_effect_records__`）为编译器保留，禁止用户参数或 LLM 生成的工作流使用同名 key。Skill 转换器的 system prompt 中应列出这些保留字，并在 `validate_workflow()` 阶段增加冲突检测（若冲突，报 diagnostic error 提示参数改名）。

**Join Reducer 聚合 → State Key 约束：**

- Join 边的多个 `join_sources` 节点写入同一个 state key 时，该 key 必须在 `state_schema.reducers` 中声明 reducer（如 `APPEND`、`MERGE_DICT`），否则 reducer 默认行为是覆盖（最后一个写入者胜出）；
- 如果 `join_sources` 中的节点写入不同的 state key，且每个 key 各自声明了 reducer，则各自独立聚合——这是预期行为，无需 warning；
- 如果 `join_sources` 中无任何节点写入需要 reducer 的 key，编译器报 diagnostic warning（join 语义可能无实际效果）。

**Side Effect → State Key 约定：**

- 副作用执行结果默认写入 `__pt2lg_side_effect_results__` state key（需在 `state_schema.reducers` 中声明为 `APPEND`）；
- 幂等键去重通过 `__pt2lg_side_effect_records__` state key 存储执行记录（list[dict]），需声明为 `APPEND` reducer（而非 `MERGE_DICT`，因为幂等键去重需要"先写入优先"语义——遍历列表查找同 key 记录时，最早写入的记录优先；`MERGE_DICT` 是 last-write-wins 语义，不适合幂等去重场景）；
- 这两个 key 在 workflow 的 `state_schema.reducers` 中自动生成或由 LLM 在 JSON plan 中声明，不要求用户手动配置。

**State Schema 自动推导：**

- 编译器在处理 JOIN 边和 Side Effect 节点时，自动检查所需的 state key 和 reducer 是否已在 `state_schema.reducers` 中声明；
- 若未声明，验证阶段报 diagnostic warning 明确告知缺失的 key 和 reducer，并给出建议补齐声明（而非编译器静默修改 state schema），用户可选择手动添加或在生成的 JSON plan 中声明；
- 为降低用户操作成本，Skill 转换器的 system prompt 中提示 LLM 在生成 JSON plan 时自动为 `__pt2lg_side_effect_results__` 和 `__pt2lg_side_effect_records__` 声明 `APPEND` reducer；
- 编译器不静默修改 workflow 中的任何 state key 或 reducer 声明（保持"显式、可校验、不可绕过"的设计原则）；
- 若因缺失 reducer 导致运行时行为不符合预期（如 Join 多源写入被覆盖），compile_report 中明确记录 warning 以便用户追溯。

> **设计依据**：LangGraph 的 [Reducers](https://docs.langchain.com/oss/python/langgraph/graph-api#reducers) 中明确：每个 state key 有独立的 reducer 函数，未显式指定时默认覆盖。这与本计划的 State Schema 推导规则一致——Join 需要显式 reducer 声明才能正确聚合多源写入。LangGraph 的 [Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) 强调通过 state 持久化确保幂等性，本计划通过 `__pt2lg_side_effect_records__` state key 存储执行记录来实现幂等键去重。

---

## 9. 验收标准

第三期验收采用分级标准，避免把所有增强项都绑定为同一完成门槛。

- **P0 回归与边界必达**：前两期能力不回归，现有 CLI/API 行为兼容，新增设计不绕过现有校验、安全和策略体系，全量测试通过；
- **P1 第三期核心增强**：Skill alpha 可生成并诊断，Join 最小可执行，Side Effect 二元审批闭环可运行，`run_workflow()` 可注入 checkpointer；
- **P2 可选增强**：CLI 默认 `SqliteSaver`、多中断并行恢复、Side Effect 应用层幂等记录、Mermaid 高级可视化、Skill 资源建模增强。

除非单项条目明确标注为 P2，以下验收默认按 P1 核心增强处理；P2 未完成不应阻塞第三期核心验收。

### 9.1 Skill → WorkflowSpec 验收

满足以下条件，方可判定 Skill 转换能力达成交付标准：

- 直接读取 Skill 目录下的 `SKILL.md` 原始内容，并结合 `analyze_skill_dir()` 的步骤、资源和风险诊断上下文，经 `plan_skill_to_workflow_spec()` 生成可校验的 `WorkflowSpec`；
- `analyze_skill_dir()` 的静态分析结果作为结构化约束上下文传递给 LLM，风险诊断优先级高于 LLM 自由判断；
- 生成的 `WorkflowSpec` 能继续进入现有 `validate / compile / run / graph` 流程；
- 对 `analyze_skill_dir()` 报告中 `E_SEC_007` 诊断检测到的高危步骤（file writes、shell execution、network access、secrets），转换结果必须保留风险诊断；若 LLM 生成的 workflow 缺少审批边界，应返回明确 diagnostic，不应静默接受；
- 转换失败时（LLM 输出不可解析、适配失败），返回明确诊断而非静默失败；
- 转换过程不默认执行 Skill 目录下的 scripts；
- `tests/test_skill_dir.py` 中新增 Skill → WorkflowSpec 的 fake model 转换测试。

### 9.2 Skill 参数注入验收

Skill 参数注入应满足：

- CLI `pt2lg plan --skill-dir` 命令可接受 Skill 目录和 `--param` 参数；
- API `plan_skill_to_workflow_spec()` 接受 `skill_dir` 路径和可选的 `params` 参数；
- 注入的参数通过 LLM prompt 上下文影响到生成的 JSON plan；
- `SKILL.md` 原文中的资源引用及 `analyze_skill_dir()` 扫描的资源信息传递给 LLM 用于生成 workflow 节点。

### 9.3 Join 边执行验收

Join 边执行应满足：

- `EdgeKind.JOIN` 不再报 `E_TARGET_009` 错误；
- 带有 `join_sources` 和对应 reducer 声明的 JOIN 边 workflow 可编译并执行；
- 多个 join_sources 节点的输出通过 reducer 被正确聚合到 target 节点可访问的 state key；
- 对未声明 reducer 的多源写入给出明确 warning 或 diagnostic，文档说明默认覆盖和并行更新顺序不稳定的 LangGraph 语义；
- `join_sources` 为空或包含不存在节点时，验证阶段报错；
- `tests/fixtures/` 中新增合法的 join fixture（如 `fanout_with_join.json`）；
- Mermaid 渲染为 JOIN 边增加 `join_sources` 标注；
- 现有的 `_check_target_capabilities()` 测试更新。

### 9.4 Side Effect 最小执行闭环验收

Side Effect 应满足：

- `side_effect` 节点可通过 `SideEffectExecutor` 执行，默认走审批中断路径；
- `allow_side_effects=True` 时，`side_effect` 节点跳过审批直接执行（但仍记录副作用事件）；
- `requires_approval=True` 的 `side_effect` 节点执行时触发 `interrupt()`，CLI 显示 `waiting` 状态和 thread_id；
- 通过 `pt2lg resume` 传入 `approved` 决策后，副作用执行成功且返回正确结果；
- 通过 `pt2lg resume` 传入 `rejected` 决策后，副作用不执行且返回拒绝结果；
- 仅有 `idempotency_key` 但无 `requires_approval` 的 `side_effect` 节点，P1 中仍走审批路径（幂等去重逻辑为 P2 增强）；
- 不符合安全策略的 `side_effect` 节点（无 `requires_approval`、无 `idempotency_key`、`allow_side_effects=False`）在验证阶段报 `E_SIDE_008`；
- Resume 恢复 `human_gate` 和 `side_effect` 的中断行为一致（共用相同的 CLI resume 入口）；
- `tests/fixtures/side_effect_allowed.json` 的编译和执行行为保持不变；
- P2 可选增强包括 side effect 幂等记录（`__pt2lg_side_effect_records__` 去重）、多中断批量恢复、`edited/respond` 决策，不作为 P1 完成门槛。

### 9.5 Checkpointer 注入验收

Checkpointer 注入应满足：

- `run_workflow()` 接受可选的 `checkpointer` 参数（类型为 `BaseCheckpointSaver`）；
- `checkpointer=None` 时，保持现有行为创建 `InMemorySaver`（向后兼容）；
- P0/P1 路径保持 CLI `pt2lg run` / `pt2lg resume` 现有 `.pt2lg-runtime/*.json` 跨进程恢复行为兼容；
- P2 路径可在 CLI `pt2lg run` / `pt2lg resume` 内部显式构造 `SqliteSaver` 并传入（数据库文件存储在 `.pt2lg-runtime/<hash>.db`）；
- `compile_workflow_to_graph()` 的 `checkpointer` 参数与 runner 的 `checkpointer` 参数传递一致；
- 测试可通过注入 `InMemorySaver` 覆盖默认行为；
- P2 SQLite 路径中，`SqliteSaver` 通过 `SqliteSaver(sqlite3.connect("path"))` 构造，实施前确认是否需要 `setup()` 调用（根据具体版本而定；建议实现时添加 `try/except` 防御性调用）；
- P0/P1 路径保持现有 JSON 状态文件 resume 成功后清理行为；P2 SQLite 路径若默认保留 `.db` 文件，必须在文档中明确说明；
- `checkpointer` 参数不与 `model_client` 或 `tool_registry` 参数冲突。

### 9.6 测试验收

测试层至少应满足：

- Skill 转换测试：以 fake model 覆盖 `plan_skill_to_workflow_spec()` 完整链路；
- 新增 join 合法 fixture 的编译和执行测试；
- Side Effect 审批中断测试：使用 `InMemorySaver` 模拟 interrupt/resume 完整流程；
- Skill, Join 相关校验测试；
- 前两期测试基线全部通过，具体验证点包括：
  - `tests/test_llm_executor.py` — LLM executor dispatch 路径不受 `_invoke_executor()` 新增 side_effect 分支影响；
  - `tests/test_tool_executor.py` — Tool executor dispatch 路径不受影响；
  - `tests/test_compile_flow.py` — 编译产物路径不受 `compile_workflow_to_graph()` 签名扩展影响；
  - `tests/test_runner.py` — `run_workflow()` 在 checkpointer 注入下行为兼容；
  - `tests/test_cli.py` — CLI `run`/`resume` 命令在 P0/P1 路径保持现有 JSON runtime 状态兼容；若启用 P2 SQLite 路径，则补充 SQLite 行为回归；
  - `tests/test_ir_schema.py` — `EdgeSpec` 新增 `join_sources` 字段后 lockfile hash 和 normalize 兼容；
- `tests/test_skill_dir.py` 扩展覆盖 Skill 到 Workflow 转换；
- 最终以全量 `uv run pytest` 通过作为第三期回归验收基线。

为保证测试稳定性：
- Skill 转换测试以 fake/mock model 响应覆盖 LLM 调用；
- Side Effect 中断测试在 `InMemorySaver` 下进行，不依赖 SQLite；
- Join 执行测试可在 `InMemorySaver` 下进行。

### 9.7 文档与边界一致性验收

文档层面应满足：

- `README.md` 明确新增 Skill 转换、Join 和 Side Effect 能力；
- `README.md` 明确 Side Effect 执行默认需审批，除非 workflow policy 显式允许；
- `CLAUDE.md` 与 `AGENTS.md` 同步反映新的能力边界；
- 将各模块引用 LangChain/LangGraph 官方文档的相关链接整合到文档中；
- 更新文档以反映 P0/P1 JSON runtime 状态与 P2 `SqliteSaver` 增强路径的兼容关系；若启用 SQLite 路径，还需说明 resume 后默认保留 checkpoint 历史的行为变更；
- 文档不应错误暗示"所有 Skill 均能完美转换为可执行工作流"或"Join 支持任意复杂聚合逻辑"。

### 9.8 非目标验收

第三期完成时，以下事项仍不应被视为必须完成项：

- 生产级 Postgres 数据库持久化；
- 多 provider 适配器体系；
- subprocess / Docker / 网络沙箱隔离；
- `LANGCHAIN_TOOL` 类型 executor 的可执行能力；
- LLM 输出质量评估或多轮反思机制；
- 自动识别 Skill 脚本并注册 tool callable；
- Web UI / HTTP 服务化；
- 完全自包含静态代码生成。

只要上述能力仍未实现，但 Skill alpha 可经 LLM 生成可诊断的 WorkflowSpec、Join 可执行 Reducer 隐式合并、Side Effect 可审批中断执行、Checkpointer 可注入切换，第三期核心增强依然可以判定为完成。

### 9.9 预期规模边界

第三期各模块的预期规模如下，超出预期规模时不保证正确性，但不应静默产生错误结果：

- Skill 转换预期支持 ≤20 步骤的 Skill（步骤数过多可能导致 LLM 输出质量下降或 JSON 解析失败率上升）；
- Skill 转换预期支持 SKILL.md 内容长度 ≤8000 字符（超出部分可能导致 LLM 上下文窗口不足或 JSON 输出截断）；
- Skill 转换预期支持 ≤10 个注入参数（参数过多可能导致 LLM 生成的 JSON plan 结构复杂、解析失败率上升）；
- Join 边预期支持 ≤10 个 `join_sources` 节点（LangGraph 对同一 target 的入边数量无硬性限制，但过多并行分支可能影响可读性和调试体验）；
- P2 SqliteSaver 预期支持单文件 ≤100MB 的 checkpoint 数据（超出建议迁移到 PostgresSaver）；
- Side Effect 审批中断预期支持单次运行 ≤5 个待审批节点（过多中断点影响用户体验，建议通过 workflow 设计减少审批频率）。

---

## 10. 后续衔接建议

在本开发计划文档确认后，下一步应进入更细粒度的实施计划阶段，进一步明确：

- 模块级改动落点与文件级实施步骤；
- 关键接口设计与执行器注册路径；
- 测试拆分与回归顺序；
- 实施依赖关系（Skill 转换 → Join 执行 → Side Effect 审批 → Checkpointer 注入）；
- 阶段性完成标准与里程碑。

后续演进方向（不在 v0.2 范围内）：
- `LANGCHAIN_TOOL` executor：对接 LangChain `BaseTool` 生态，使 `tool` 节点可直接调用 LangChain 工具。当前 `ExecutorType.LANGCHAIN_TOOL` 已在 IR 模型中定义但未实现，与 `PYTHON_CALLABLE` 的定位差异为：前者对接 LangChain `BaseTool` 生态（自动 schema 推导、tool call 集成），后者是受控 Python callable 注册。Skill 转换器生成的 `tool` 节点当前使用 `PYTHON_CALLABLE`，后续可平滑迁移到 `LANGCHAIN_TOOL`；
- `RetryPolicy`：映射 `NodeSpec.retry` 到 LangGraph 原生 `RetryPolicy`，实现自动重试；
- 生产级 PostgresSaver：支持 Postgres 持久化，用于生产环境；
- Skill 脚本预注册：自动分析 Skill 目录下的 Python 脚本并预注册 tool callable；
- Agent Server 部署：通过 `langgraph up` 将 workflow 部署为 LangSmith Agent Server。

> **附录：LangGraph `@task` 评估说明**（供后续演进参考，不在第三期实施）
>
> 当前第三期使用 `StateGraph` API + `interrupt()` 实现审批中断。LangGraph [Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) 文档说明 `@task` 可同时用于 `StateGraph`（Graph API）和 Functional API。
>
> 第三期暂不采用 `@task`，原因如下：
> 1. **审批中断与 `@task` 的交互复杂**：`SideEffectExecutor` 在 `interrupt()` 等待审批通过后调用实际 executor。如果将实际 executor 包装在 `@task` 中，审批逻辑（`interrupt()` 在节点顶层）和实际执行逻辑（`@task` 在节点内部）的状态管理边界不同；
> 2. **最小闭环优先**：使用 `interrupt()` + `Command(resume=...)` 的审批模式已能满足需求。`@task` 的 durable execution 语义（审批后失败免重试审批）属于增强能力；
> 3. **幂等键方案已覆盖核心去重需求**：通过 `__pt2lg_side_effect_records__` state key 的应用层去重，已能在审批通过且执行成功的场景下避免重复副作用。
>
> 后续演进方向（不在第三期范围内）：
> - 评估将 `SideEffectExecutor` 的实际执行部分包装在 `@task` 中（在 StateGraph 节点内部直接使用 `@task`），利用 durable execution 语义实现"审批后失败免审批重试"；
> - 评估 `@task` 对 `retry_policy` 的支持，实现副作用操作的自动重试；
> - 评估从 StateGraph API 迁移到 Functional API（`@entrypoint` + `@task`），以更自然地集成 `@task` 的 durable execution 能力。

---

## 附录 A：模块依赖关系

```
SKILL.md 原始内容 (主输入)
        │
        ├──→ 8.1 Skill→WorkflowSpec LLM 转换器
        │            │
        │            ├── 辅助: analyze_skill_dir() (可选上下文)
        │            ├── 依赖: llm/ (v0.2-2 已有)
        │            ├── 依赖: prompting/parser (v0.2-1 已有)
        │            ├── 依赖: adapters/json_plan (v0.1 已有)
        │            │
        │            └──→ 8.2 Skill 参数注入与资源建模
        │                      │
        │                      ├── 依赖: cli.py (扩展)
        │                      └── 依赖: __init__.py (Public API)
        │
8.4 Side Effect 最小执行闭环 ────── 依赖: 8.5 Checkpointer 注入接口
        │                                      │
        ├── 依赖: langgraph interrupt()        ├── P2增强: langgraph-checkpoint-sqlite
        ├── 依赖: human_gate resume 模式       ├── 依赖: runner.py (重构)
        └── 依赖: registry/executors (v0.2-2)  └── 依赖: compile_workflow_to_graph()

8.3 Join 边执行支持 (独立于其他模块)
        │
        ├── 依赖: ir/models.py (EdgeSpec 扩展)
        ├── 依赖: validate/graphcheck.py
        └── 依赖: compiler/langgraph_py.py
```

### 实施顺序建议

1. **Checkpointer 接口抽象（8.5 前半）** — 先行完成 `run_workflow()` 签名重构：添加 `checkpointer` 参数，减少对 `_THREAD_CHECKPOINTERS` 全局字典的依赖；P0/P1 路径保留 `_save_thread_state()` / `_load_thread_state()` 的 JSON 持久化兼容逻辑，P2 SQLite 路径启用后再替换为 `SqliteSaver` 管理。**这一步完成后（无需等待 SqliteSaver 切换），步骤 2 即可开始**；
2. **Side Effect 核心实现（8.4）** — 依赖步骤 1 的 checkpointer 参数注入（使用 `InMemorySaver` 即可覆盖审批中断逻辑和 `RunInterrupt` 事件复用）；实际执行器在 `allow_side_effects=True` 或审批通过后走 `_invoke_executor()` dispatch；
3. **Join 边执行支持（8.3）** — 独立模块，可与步骤 1 并行；
4. **Skill → WorkflowSpec LLM 转换器（8.1）** — 依赖第二期的 `llm/` 和第一期的 `prompting/parser`，与步骤 1-3 可并行推进；
5. **Skill 参数注入与资源建模（8.2）** — 在步骤 4 的 Skill 转换器基础上扩展 CLI 和 API；
6. **CLI SqliteSaver 切换（8.5 后半，P2）** — 在所有核心功能模块（步骤 2-5）完成且依赖兼容性确认后，再考虑将 CLI 默认 checkpointer 从 JSON runtime 状态切换到 `SqliteSaver`；
7. **全量回归测试与文档更新** — 在前 6 步均完成后进行。

可并行的任务组：
- 步骤 1 的接口抽象（`run_workflow()` 签名重构）+ 步骤 3（Join）可并行
- 步骤 2（Side Effect）在步骤 1 的接口抽象完成后即可开始（无需等待 SqliteSaver 切换）
- 步骤 4-5（Skill）依赖第二期的 `llm/`，与步骤 1-3 可并行推进
- 步骤 6（SqliteSaver 切换）为 P2 增强，在所有核心功能模块完成后进行

---

## 附录 B：LangChain / LangGraph 官方文档参考索引

本计划中的设计决策参考了以下 LangChain/LangGraph v1 官方文档页面。按主题分类整理，便于实施阶段查阅。

### LangGraph 核心

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Graph API 概览 | [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api) | 6.1, 8.3 |
| 使用 Graph API（增量构建） | [Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api) | 6.1 |
| 并行节点执行 | [Run graph nodes in parallel](https://docs.langchain.com/oss/python/langgraph/use-graph-api#run-graph-nodes-in-parallel) | 6.3, 8.3 |
| Map-Reduce & Send API | [Map-Reduce and the send API](https://docs.langchain.com/oss/python/langgraph/use-graph-api#map-reduce-and-the-send-api) | 6.3, 8.3 |
| Send API | [Send](https://docs.langchain.com/oss/python/langgraph/graph-api#send) | 6.3, 8.3 |
| Interrupt 中断机制 | [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | 6.4, 8.4, 8.5 |
| 持久化与 Checkpoint | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 6.5, 8.5 |
| Checkpointer 集成列表 | [Checkpointer integrations](https://docs.langchain.com/oss/python/integrations/checkpointers/index) | 6.5, 8.5 |
| Checkpointer 库说明 | [Persistence#checkpointer-libraries](https://docs.langchain.com/oss/python/langgraph/persistence#checkpointer-libraries) | 6.5, 8.5 |
| Durable Execution | [Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) | 8.4 |

### LangChain Agent 与 Middleware

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Human-in-the-Loop | [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) | 6.4, 8.4 |
| Custom middleware（hook 机制） | [Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) | 6.4 |
| Middleware hooks 一览 | [Middleware hooks](https://docs.langchain.com/oss/python/releases/langchain-v1#custom-middleware) | 6.4 |

### Deep Agents

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Deep Agents overview | [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview) | 6.2, 8.1 |
| Deep Agents customization | [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization) | 6.2, 8.1 |
| Deep Agents HITL | [Deep Agents HITL](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop) | 6.4, 8.4 |

### 多 Agent 架构

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Result collection with reducers | [Multi-agent router knowledge base](https://docs.langchain.com/oss/python/langchain/multi-agent/router-knowledge-base#result-collection-with-reducers) | 6.3, 8.3 |

### 模型与工具

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| Chat model 集成 | [Chat model integrations](https://docs.langchain.com/oss/python/integrations/chat/index) | 8.1 |

### 测试

| 主题 | 文档链接 | 本计划关联章节 |
|------|----------|----------------|
| 单元测试（fake model） | [Unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing) | 6.6 |
| InMemorySaver checkpointer | [InMemorySaver checkpointer](https://docs.langchain.com/oss/python/langchain/test/unit-testing#inmemorysaver-checkpointer) | 6.6, 8.5 |

> **使用说明**：以上链接基于 LangChain/LangGraph v1 官方文档（docs.langchain.com），查询日期为 2026 年 5 月。LangChain/LangGraph 文档可能随版本更新而重构，如遇链接失效，可通过 docs.langchain.com 搜索对应主题关键词获取最新页面。

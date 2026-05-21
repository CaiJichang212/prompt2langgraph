# prompt2langgraph 项目全面评估报告

## 1. 项目现状概述

### 1.1 项目定位与目标

`prompt2langgraph` 旨在将用户输入的 **Prompt**、LLM 生成的 **计划（JSON 格式）** 以及 **Skills** 编译为可执行的 **LangGraph** 图。当前版本（v0.1）已实现了一个功能较为完整的 Workflow IR 编译与运行框架，但距离最终目标仍有显著差距。

### 1.2 当前版本状态

- **版本号**: 0.1.0
- **核心定位**: Workflow IR / 简化 JSON plan 的校验、编译、运行工具包
- **运行环境**: 本地确定性执行，不隐式调用外部 LLM 或网络服务
- **测试状态**: `uv run pytest` 全量通过（截至评估日）

---

## 2. 功能实现对比分析

### 2.1 已实现功能模块

| 模块 | 功能描述 | 完成度 | 关键代码位置 |
|------|---------|--------|-------------|
| **IR 模型定义** | WorkflowSpec / NodeSpec / EdgeSpec 等 Pydantic 模型 | 100% | [src/prompt2langgraph/ir/models.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/ir/models.py) |
| **IR 规范化** | 节点/边排序规范化 | 100% | [src/prompt2langgraph/ir/normalize.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/ir/normalize.py) |
| **Lockfile 生成** | workflow.lock.json、manifest、compile report | 100% | [src/prompt2langgraph/ir/lockfile.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/ir/lockfile.py) |
| **JSON Plan 适配器** | 简化 JSON plan → WorkflowSpec 转换 | 90% | [src/prompt2langgraph/adapters/json_plan.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/adapters/json_plan.py) |
| **Skill 目录静态分析** | SKILL.md 解析、风险词检测、draft nodes 生成 | 70% | [src/prompt2langgraph/adapters/skill_dir.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/adapters/skill_dir.py) |
| **节点/执行器注册表** | 8 种节点类型、6 个内置执行器 | 80% | [src/prompt2langgraph/registry/builtins.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/registry/builtins.py) |
| **校验器** | Schema、Registry、图结构、类型、安全策略校验 | 90% | [src/prompt2langgraph/validate/validator.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/validate/validator.py) |
| **图结构校验** | 可达性、出口路径、循环边、条件边、扇出边校验 | 90% | [src/prompt2langgraph/validate/graphcheck.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/validate/graphcheck.py) |
| **类型校验** | State selector、executor schema、params 类型校验 | 85% | [src/prompt2langgraph/validate/typecheck.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/validate/typecheck.py) |
| **安全策略校验** | side_effect 节点审批/幂等键校验 | 80% | [src/prompt2langgraph/validate/security.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/validate/security.py) |
| **策略解析** | 节点超时、审批策略解析 | 80% | [src/prompt2langgraph/policy/resolver.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/policy/resolver.py) |
| **工作流绑定** | Executor binding 生成 | 80% | [src/prompt2langgraph/binding/binder.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/binding/binder.py) |
| **LangGraph 编译器** | 编译为可执行的 LangGraph StateGraph | 85% | [src/prompt2langgraph/compiler/langgraph_py.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/compiler/langgraph_py.py) |
| **代码生成** | 生成 state.py、nodes.py、graph.py 骨架 | 70% | [src/prompt2langgraph/compiler/codegen.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/compiler/codegen.py) |
| **运行时执行器** | 本地运行、事件输出、metrics、interrupt/resume | 85% | [src/prompt2langgraph/runtime/runner.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/runtime/runner.py) |
| **编译产物管理** | Bundle 生成、读取、校验、清理 | 90% | [src/prompt2langgraph/runtime/artifacts.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/runtime/artifacts.py) |
| **Mermaid 渲染** | 流程图生成 | 90% | [src/prompt2langgraph/visualization/mermaid.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/visualization/mermaid.py) |
| **CLI** | validate、compile、run、graph、resume 命令 | 90% | [src/prompt2langgraph/cli.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/cli.py) |
| **Public API** | Python API 导出 | 80% | [src/prompt2langgraph/__init__.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/__init__.py) |

### 2.2 已支持的边类型

| 边类型 | IR 支持 | 校验支持 | LangGraph 编译 | 运行支持 | 说明 |
|--------|---------|---------|---------------|---------|------|
| `linear` | ✅ | ✅ | ✅ | ✅ | 完全支持 |
| `conditional` | ✅ | ✅ | ✅ | ✅ | 支持 6 种比较运算符 |
| `loop` | ✅ | ✅ | ✅ | ✅ | 需 `loop_guard.max_iterations` |
| `fanout` | ✅ | ✅ | ✅ | ✅ | Map-Reduce 模式，需 reducer |
| `join` | ✅ | ✅ | ❌ | ❌ | IR 可表达，但编译器/运行器拒绝执行 |

### 2.3 已支持的节点类型与执行器

| 节点类型 | 内置执行器 | 执行器类型 | 状态 |
|---------|-----------|-----------|------|
| `llm` | `builtin.echo_llm` | BUILTIN | Mock（确定性模板拼接） |
| `retriever` | `builtin.mock_retriever` | BUILTIN | Mock（返回 artifact ref） |
| `transform` | `builtin.identity_transform` | BUILTIN | 纯函数 |
| `router` | `builtin.route` | BUILTIN | 纯函数 |
| `human_gate` | `builtin.human_gate` | BUILTIN | 使用 LangGraph `interrupt()` |
| `join` | `builtin.join` | BUILTIN | 纯函数（但 `join` 边不可执行） |
| `tool` | — | — | 仅注册表定义，无内置执行器 |
| `side_effect` | — | — | 仅注册表定义，无内置执行器 |

---

## 3. 差距量化评估

### 3.1 与目标的核心差距

目标描述为：**"将用户输入的 Prompt、LLM 生成的计划（JSON 格式）以及 Skills 编译为可执行的 LangGraph 图"**。

当前实现与目标的差距可量化为以下维度：

#### 差距 1：Prompt 输入层（完成度：0%）

- **目标要求**: 接受自然语言 Prompt 作为输入
- **当前状态**: 完全不支持 `prompt_text` 适配器
- **证据**: AGENTS.md 明确说明 "没有实现 `prompt_text` 适配器"
- **影响**: 用户必须直接提供结构化的 Workflow IR 或简化 JSON plan，无法从自然语言生成工作流

#### 差距 2：LLM 计划生成层（完成度：0%）

- **目标要求**: LLM 根据 Prompt 生成 JSON 格式的计划
- **当前状态**: 无 LLM 调用模块，无计划生成逻辑
- **证据**: 内置 `builtin.echo_llm` 是确定性 mock，不调用真实 LLM；项目中无计划生成相关代码
- **影响**: 计划必须由外部系统或用户手动编写

#### 差距 3：Skills 到可执行工作流的转换（完成度：30%）

- **目标要求**: Skills 编译为可执行的 LangGraph 图
- **当前状态**: `analyze_skill_dir()` 仅做静态分析，输出 `SkillDirectoryAnalysis` 和 `draft_nodes`，不生成可执行 `WorkflowSpec`
- **证据**: [adapters/skill_dir.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/adapters/skill_dir.py#L43) 的 `analyze_skill_dir()` 返回 draft_nodes；AGENTS.md 明确 "不生成可执行 WorkflowSpec"
- **影响**: Skills 只能被分析，不能被直接编译执行

#### 差距 4：真实 LLM 执行器（完成度：0%）

- **目标要求**: 支持调用真实 LLM API
- **当前状态**: 所有 LLM 相关执行器均为 mock
- **证据**: `builtin.echo_llm` 仅做模板拼接；README 说明 "不会隐式调用外部 LLM"
- **影响**: 工作流无法在真实场景下生成 AI 内容

#### 差距 5：Tool / Side Effect 执行器（完成度：20%）

- **目标要求**: 支持外部工具调用和副作用执行
- **当前状态**: `tool` 和 `side_effect` 节点类型在注册表中定义，但无实际可执行的内置执行器
- **证据**: [registry/builtins.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/src/prompt2langgraph/registry/builtins.py) 中 `tool` 和 `side_effect` 无对应 executor handler
- **影响**: 无法执行外部工具或副作用操作

#### 差距 6：Join 边执行（完成度：0%）

- **目标要求**: 支持分支合并
- **当前状态**: `join` 是 IR 可识别的 edge kind，但 LangGraph compiler / runner 不支持执行
- **证据**: README "`join` 是 IR 和 Mermaid 可识别的 edge kind，但当前 LangGraph compiler / runner 不支持执行"
- **影响**: 无法表达和运行分支合并逻辑

### 3.2 技术实现差距

| 技术维度 | 当前状态 | 目标状态 | 差距 |
|---------|---------|---------|------|
| **输入适配层** | 仅支持 Workflow IR 和简化 JSON plan | 支持 Prompt → Plan → IR 的完整链路 | 缺少 Prompt 解析和 LLM Plan 生成 |
| **执行器生态** | 仅 6 个内置 mock 执行器 | 支持真实 LLM、Tool、Side Effect | 缺少真实执行器实现 |
| **目标平台** | 仅支持 `langgraph-py` | 可能需支持更多目标 | 单目标，但当前聚焦合理 |
| **持久化** | 内存 InMemorySaver + 本地临时状态文件 | 生产级持久化 | 仅适合本地开发 |
| **可视化** | 仅 Mermaid | 可能需更多格式 | 基础覆盖 |
| **代码生成** | 生成骨架代码（读取 IR 再编译） | 完全自包含的静态代码包 | 产物依赖运行时库 |

### 3.3 性能指标评估

当前项目定位为本地开发/测试工具，未提供生产级性能指标：

| 指标 | 当前状态 | 评估 |
|------|---------|------|
| 编译耗时 | 有 `timings_ms` 记录各阶段耗时 | 基础观测能力具备 |
| 运行时 metrics | 仅 `duration_ms`、`retry_count`、`tool_call_count` | 指标较少 |
| 吞吐量 | 未测试 | 单线程本地执行 |
| 内存占用 | 未测试 | 依赖 LangGraph InMemorySaver |
| 并发支持 | 无显式设计 | 运行时状态按 thread_id 隔离 |

---

## 4. 尚未完成的关键功能需求

### 4.1 高优先级（阻塞目标达成）

| 需求 | 技术要求 | 实现路径 | 优先级 |
|------|---------|---------|--------|
| **Prompt → Plan 适配器** | 实现 `prompt_text` 适配器，调用 LLM 生成 JSON plan | 1. 定义 prompt 解析模块<br>2. 集成 LLM 客户端<br>3. 实现输出到 JSON plan 的转换 | P0 |
| **真实 LLM 执行器** | 实现调用 OpenAI/Anthropic/本地模型的执行器 | 1. 定义 LLM provider 配置<br>2. 实现 `llm` executor 的真实版本<br>3. 支持 messages 格式和流式输出 | P0 |
| **Tool 执行器** | 实现可调用外部工具（函数/API）的执行器 | 1. 定义 tool 配置 schema<br>2. 实现工具发现与调用<br>3. 支持 LangChain Tool 集成 | P0 |
| **Skill → WorkflowSpec 转换** | 将 `SkillDirectoryAnalysis` 转换为可执行 `WorkflowSpec` | 1. 设计 skill 到节点的映射规则<br>2. 实现转换器<br>3. 支持参数注入 | P1 |

### 4.2 中优先级（增强可用性）

| 需求 | 技术要求 | 实现路径 | 优先级 |
|------|---------|---------|--------|
| **Join 边执行** | 在 LangGraph 编译器中实现 `join` 边的语义 | 1. 研究 LangGraph 分支合并模式<br>2. 实现 `join` 节点聚合逻辑 | P1 |
| **Side Effect 执行器** | 实现带幂等性和审批的副作用执行器 | 1. 定义 side_effect 配置<br>2. 实现执行包装器<br>3. 集成审批流 | P1 |
| **生产级持久化** | 替换 InMemorySaver，支持 Postgres/MongoDB 等 | 1. 抽象 Checkpointer 接口<br>2. 实现持久化后端 | P2 |
| **更丰富的代码生成** | 生成完全自包含、不依赖运行时库的静态代码 | 1. 设计静态代码模板<br>2. 内联编译逻辑到生成代码 | P2 |

### 4.3 低优先级（优化与扩展）

| 需求 | 技术要求 | 实现路径 | 优先级 |
|------|---------|---------|--------|
| **更多可视化格式** | 支持除 Mermaid 外的其他图格式 | 集成 graphviz 等 | P3 |
| **并发与性能优化** | 支持并行节点执行、性能监控 | 依赖 LangGraph 能力扩展 | P3 |
| **Web UI / 服务化** | 提供 HTTP API 和可视化界面 | FastAPI + 前端 | P3 |

---

## 5. 代码质量与架构评估

### 5.1 架构优势

1. **清晰的层次结构**: IR → Adapter → Validate → Compile → Runtime 的分层明确
2. **完善的诊断系统**: 统一的 `Diagnostic` / `ValidationReport` 模型，支持机器可读输出
3. **注册表模式**: NodeRegistry / ExecutorRegistry 便于扩展新节点和执行器
4. **确定性设计**: 内置执行器均为纯函数/mock，便于测试和回归
5. **Bundle 契约**: lockfile + manifest + compile_report 提供了可审计的编译产物

### 5.2 潜在风险

1. **运行时状态耦合**: `_save_thread_state` / `_load_thread_state` 直接序列化 LangGraph `InMemorySaver` 内部结构，版本兼容性风险高
2. **代码生成依赖**: `generated/graph.py` 仍需读取 IR 并调用库内编译器，不是自包含产物
3. **类型系统简单**: `_types_compatible` 仅做顶层类型名比较，不支持嵌套结构深度校验
4. **条件表达式受限**: 仅支持 `<state_key> <comparison> <literal>` 形式，无法表达复杂逻辑

---

## 6. 测试覆盖分析

### 6.1 测试文件清单

| 测试文件 | 覆盖范围 | 测试数量（估算） |
|---------|---------|----------------|
| [test_validator.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_validator.py) | 校验器、注册表、类型检查、安全策略 | ~25 |
| [test_runner.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_runner.py) | 运行时执行、interrupt/resume、状态持久化 | ~15 |
| [test_compile_flow.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_compile_flow.py) | 编译产物生成、manifest/report 结构 | 2 |
| [test_cli.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_cli.py) | CLI 命令、JSON 输出、lockfile 运行/resume | ~15 |
| [test_langgraph_compiler.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_langgraph_compiler.py) | LangGraph 编译、各边类型执行 | ~8 |
| [test_json_plan_adapter.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_json_plan_adapter.py) | 简化 JSON plan 适配 | ~10 |
| [test_skill_dir.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_skill_dir.py) | Skill 目录静态分析 | 3 |
| [test_public_api.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_public_api.py) | Public API 导出 | 3 |
| [test_artifacts.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_artifacts.py) | 产物读取/校验 | 未详细阅读 |
| [test_bundle_golden.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_bundle_golden.py) | 编译产物回归测试 | 未详细阅读 |
| [test_examples.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_examples.py) | 示例工作流端到端测试 | 未详细阅读 |
| [test_ir_schema.py](file:///Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph/tests/test_ir_schema.py) | IR Schema 校验 | 未详细阅读 |

### 6.2 测试 Fixtures

- **有效夹具**: `linear_llm.json`, `conditional_human_gate.json`, `loop_with_guard.json`, `fanout_map_reduce.json`, `linear_retriever_llm.json`, `tool_identity.json`, `side_effect_allowed.json`
- **无效夹具**: `invalid_unknown_node.json`, `invalid_type_mismatch.json`, `invalid_loop_without_guard.json`, `invalid_fanout_without_reducer.json`, `invalid_route_conflict.json`, `invalid_join_edge.json`

---

## 7. 总结与建议

### 7.1 总体评估

| 维度 | 评分（1-10） | 说明 |
|------|-------------|------|
| **功能完整性** | 5/10 | IR 编译运行较完整，但缺少 Prompt 层、LLM 计划生成、真实执行器 |
| **技术实现** | 7/10 | 架构清晰，代码质量高，但部分实现为 mock/占位 |
| **测试覆盖** | 7/10 | 测试较全面，但缺少性能测试和真实 LLM 集成测试 |
| **文档完整性** | 8/10 | README 和 AGENTS.md 详细，但部分功能边界需更明确 |
| **距离目标** | 4/10 | 核心 Workflow IR 编译运行已完成，但 Prompt→Plan→IR 链路完全缺失 |

### 7.2 关键结论

1. **当前项目是一个优秀的 Workflow IR 编译运行框架**，但**不是**一个完整的 "Prompt → LangGraph" 工具。
2. **最大瓶颈**: 缺少 Prompt 解析层和 LLM 计划生成层，这是目标描述中的首要环节。
3. **次要瓶颈**: 所有 AI 相关执行器均为 mock，无法在真实场景下工作。
4. **优势**: 校验、编译产物管理、运行时事件和诊断系统设计良好，为上层扩展提供了坚实基础。

### 7.3 下一步建议

1. **短期（1-2 周）**: 实现真实 LLM 执行器（OpenAI/Anthropic），使工作流能实际调用 LLM。
2. **中期（2-4 周）**: 实现 Prompt → JSON Plan 的适配器，完成目标链路的第一环。
3. **长期（1-2 月）**: 实现 Skill → WorkflowSpec 的转换器，打通 Skills 到可执行图的链路。

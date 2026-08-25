# Elmos 大型仓库运行数据库表目录

**参考模型：** 136 张父表（不含物理 Hash 分区子表）。  
**说明：** 这是一套商业产品级上限模型，不代表 DB-1 首次上线必须同时启用全部表。

## 1. 分阶段启用建议

| 阶段 | 目标 | 主要 Schema |
|---|---|---|
| DB-1 | 准入、任务恢复、事件、Artifact、Outbox、成本和审计最小闭环 | core、exec、artifact、integration、metering 核心、audit |
| DB-2 | 仓库理解、文件/符号/IR/Capability 与缓存 | analysis、cache |
| DB-3 | 项目生成、跨库转换、验证、Evidence 与 P05 Gate | generation、transform、verify |
| DB-4 | 规则学习、Benchmark、发布与部署运营 | learning、ops、完整 metering |

## 2. 字段解释

- **数据量级：** `热/大` 表需要重点关注分区、批量写、归档；`中` 为按 Run/Revision 增长；`小` 为控制/配置类。
- **保留：** R0 瞬态、R1 活跃运行、R2 产品排障、R3 商业证据、R4 合规财务。
- **关键：** P05 完成、恢复、财务或安全链路不可缺失。

## core Schema（10 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `core.tenant` | 租户根记录，保存区域、套餐、状态与数据策略边界。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `status`, `created_at`, `updated_at` |
| `core.account` | 租户内账号/主体及其并发额度、生命周期和计费归属。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `status`, `created_at`, `updated_at` |
| `core.project` | 项目边界，聚合仓库、Job、策略和部署目标。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `status`, `created_at`, `updated_at` |
| `core.repository` | 逻辑代码仓库或输入项目的稳定身份。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `project_id`, `created_at`, `updated_at` |
| `core.revision_snapshot` | 任意不可变输入/配置/策略/工具链 Revision 的统一指纹。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `created_at` |
| `core.repository_revision` | 仓库某次精确提交、归档或导入快照。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `created_at` |
| `core.job` | 用户可见的长期项目生成/转换目标。 **关键链路** | DB-1 | 低频实体 + 热状态更新 | 中 | R3 | `id`, `tenant_id`, `project_id`, `account_id`, `status`, `created_at`, `updated_at` |
| `core.job_submission` | API 提交幂等记录，绑定 idempotency key 与请求哈希。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `account_id`, `project_id`, `job_id`, `created_at` |
| `core.job_input_revision` | Job 使用的需求、源码、策略和环境 Revision 绑定。 | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `id`, `tenant_id`, `job_id`, `created_at` |
| `core.account_task_slot` | 每账号固定 3 个原子并发槽及 lease generation。 **关键链路** | DB-1 | 低频实体 + 热状态更新 | 小 | R3 | `tenant_id`, `account_id`, `lease_generation` |

## exec Schema（26 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `exec.run` | 绑定精确 Revision 的一次端到端执行。 **关键链路** | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `job_id`, `account_id`, `status`, `created_at`, `updated_at` |
| `exec.run_attempt` | Run 的整体调度/恢复尝试。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status` |
| `exec.run_stage` | Run 的阶段状态、进度和阶段级输出。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at`, `updated_at` |
| `exec.task` | 稳定 DAG 工作单元。 **关键链路** | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at`, `updated_at` |
| `exec.task_dependency` | Task 之间的 hard/soft 依赖边。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `tenant_id`, `run_id`, `task_id`, `created_at` |
| `exec.worker_node` | 可调度 Worker/Runner 节点及能力、心跳、隔离信息。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `status`, `updated_at` |
| `exec.workspace` | 隔离工作区、沙箱、快照和清理状态。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `lease_generation`, `created_at`, `updated_at` |
| `exec.task_attempt` | 某个 Task 的一次实际执行尝试。 **关键链路** | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `status`, `lease_generation`, `created_at` |
| `exec.execution_lease` | Attempt 的租约、owner token 和 fencing generation。 **关键链路** | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `lease_generation` |
| `exec.run_event_cursor` | Run 事件序号与哈希链游标。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `tenant_id`, `run_id`, `updated_at` |
| `exec.run_event` | Run 级 append-only 事实事件。 **关键链路** | DB-1 | 高频状态/事件/租约 | 热/大 | R2/R3 | `tenant_id`, `run_id`, `task_id`, `task_attempt_id` |
| `exec.run_progress_snapshot` | 面向 UI 的当前聚合进度读模型。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `tenant_id`, `run_id`, `status`, `updated_at` |
| `exec.session` | 模型/Agent 会话的稳定身份与当前状态。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `status`, `created_at` |
| `exec.session_event_cursor` | Session 事件序号与哈希链游标。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `tenant_id`, `session_id`, `updated_at` |
| `exec.session_event` | 模型可重放的 append-only Session 事实流。 **关键链路** | DB-1 | 高频状态/事件/租约 | 热/大 | R2/R3 | `tenant_id`, `session_id`, `run_id` |
| `exec.context_epoch` | 稳定 system-context/cache-prefix 生命周期边界。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `session_id` |
| `exec.workpad` | 单一持久任务工作台/计划容器。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `status`, `created_at`, `updated_at` |
| `exec.workpad_item` | 计划、验收标准、验证项、阻塞项的层级条目。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `status`, `created_at`, `updated_at` |
| `exec.approval_request` | 工具、权限、策略或人审请求。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `session_id`, `status` |
| `exec.approval_decision` | 审批结果及一次性/持久授权语义。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `created_at` |
| `exec.human_gate` | 需要人工介入的业务 Gate 与等待状态。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `status` |
| `exec.run_control_request` | 暂停、继续、取消、重试等控制命令。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status` |
| `exec.recovery_action` | 恢复器执行的重对账、重试、回退或隔离动作。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `status`, `created_at` |
| `exec.checkpoint` | 可恢复状态的 sealed checkpoint。 **关键链路** | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `task_attempt_id`, `status`, `created_at` |
| `exec.checkpoint_component` | Checkpoint 引用的 Session、IR、Workspace、Artifact 等组件。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `component_key`, `component_version`, `artifact_id`, `component_sha256` |
| `exec.context_compaction` | 上下文压缩过程、边界、摘要 Artifact 与效果统计。 | DB-1 | 高频状态/事件/租约 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `session_id`, `status` |

## artifact Schema（7 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `artifact.object_blob` | CAS 物理对象的哈希、大小、存储位置和可用状态。 **关键链路** | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `tenant_id`, `sha256`, `storage_backend`, `bucket_name`, `object_key`, `version_id` |
| `artifact.artifact` | 具有业务语义和授权边界的逻辑产物。 **关键链路** | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `id`, `tenant_id`, `created_at` |
| `artifact.artifact_link` | Artifact 与 Job/Run/Task/Evidence 等实体的关系。 | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `id`, `tenant_id`, `created_at` |
| `artifact.manifest` | 可 sealed 的 Artifact/Checkpoint/Evidence 文件清单。 **关键链路** | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `id`, `tenant_id`, `created_at` |
| `artifact.manifest_entry` | Manifest 中按路径/角色组织的对象条目。 | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `id`, `tenant_id`, `manifest_id`, `entry_path`, `entry_kind`, `artifact_id` |
| `artifact.staged_object` | 上传中或待校验发布的临时对象。 | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `task_attempt_id` |
| `artifact.run_archive` | 归档 Run 的完整冷存储索引、摘要和保留策略。 | DB-1 | 上传发布 + 引用 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |

## analysis Schema（15 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `analysis.repository_scan` | 一次仓库发现/扫描过程及范围、模式和结果摘要。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `analysis.repository_file` | Revision 下的文件目录、哈希、语言、类型和 CAS 引用。 | DB-2 | 批量追加/Revision 不可变 | 热/大 | R2（可重建部分 R1） | `tenant_id`, `repository_revision_id`, `file_id`, `scan_id`, `normalized_path`, `path_hash` |
| `analysis.module_record` | 模块、包、子项目或 bounded context。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `created_at` |
| `analysis.build_target` | 可构建、测试、部署的目标及工具链信息。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `created_at` |
| `analysis.dependency_record` | 源码、包、模块、服务或外部依赖关系。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `repository_revision_id`, `source_module_id`, `source_file_id`, `dependency_kind` |
| `analysis.symbol_record` | 类、函数、类型、接口等可查询符号索引。 | DB-2 | 批量追加/Revision 不可变 | 热/大 | R2（可重建部分 R1） | `tenant_id`, `repository_revision_id`, `symbol_id`, `file_id`, `module_id`, `symbol_key` |
| `analysis.runtime_surface` | REST/RPC/MQ/Cron/CLI/UI/DB 等可观察运行界面。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `created_at` |
| `analysis.graph_shard` | Call/Dependency/Data/Control Graph 的分片 Artifact 索引。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `created_at` |
| `analysis.semantic_ir_revision` | 规范化 Semantic IR 的不可变版本。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `analysis.ir_shard` | IR 节点/边/语义域分片的 CAS 坐标。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `created_at` |
| `analysis.capability` | 从源码或需求发现的业务/技术能力 Ledger。 | DB-2 | 批量追加/Revision 不可变 | 热/大 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `status`, `created_at`, `updated_at` |
| `analysis.capability_edge` | 能力之间的组成、依赖、触发、数据流关系。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `tenant_id`, `run_id`, `created_at` |
| `analysis.unsupported_semantic` | 当前转换路径无法安全表达的语义与影响。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `status`, `created_at`, `updated_at` |
| `analysis.analysis_snapshot` | 一次分析闭包的聚合版本和完整度摘要。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `analysis.discovery_warning` | 扫描降级、遗漏风险、解析失败和未知区域。 | DB-2 | 批量追加/Revision 不可变 | 中 | R2（可重建部分 R1） | `id`, `tenant_id`, `run_id`, `status`, `created_at` |

## generation Schema（12 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `generation.requirement_set` | 某个需求基线的稳定容器与版本。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `generation.requirement_node` | 功能、非功能、合规、运维或验收需求节点。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `status`, `created_at`, `updated_at` |
| `generation.requirement_edge` | 需求之间的依赖、细化、冲突和追踪关系。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `tenant_id`, `requirement_set_id`, `from_requirement_id`, `to_requirement_id`, `edge_kind`, `created_at` |
| `generation.acceptance_criterion` | 可执行、可测量的验收条件。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `status`, `created_at`, `updated_at` |
| `generation.archetype_selection` | SaaS、支付、ERP 等项目原型识别和置信度。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id` |
| `generation.architecture_revision` | 目标架构、组件、数据流和约束的版本。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `generation.project_generation_plan` | 完整项目生成计划、分解策略和完成条件。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `generation.generation_unit` | 可并行生成的模块、文件组或能力单元。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `task_id`, `created_at`, `updated_at` |
| `generation.capability_mapping` | 源/需求能力到目标实现与验证的闭环映射。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at`, `updated_at` |
| `generation.generation_iteration` | 生成—验证—修复迭代轮次。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_attempt_id`, `status`, `target_revision_id` |
| `generation.generated_file` | 目标 Revision 中生成文件的路径、哈希、来源和状态。 | DB-3 | 批量追加 + 迭代状态 | 热/大 | R2/R3 | `tenant_id`, `run_id`, `created_at` |
| `generation.generation_decision` | 生成过程中的架构/实现选择及证据与理由。 | DB-3 | 批量追加 + 迭代状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |

## transform Schema（7 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `transform.transformation_plan` | 源仓库到目标仓库的整体转换计划。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `transform.transformation_unit` | 按模块/能力/语义域拆分的转换工作单元。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `task_id`, `created_at`, `updated_at` |
| `transform.mapping_decision` | 语言、框架、API、数据、并发等映射决策。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `transform.rule_application` | 具体转换规则的命中、输入、输出、版本与结果。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `transform.target_revision` | 转换目标仓库的不可变版本和构建状态。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `sequence_no`, `status`, `created_at` |
| `transform.patch_set` | 一组可审查、应用、回滚的代码差异。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `transform.cutover_plan` | Shadow、Strangler、数据迁移、流量切换和回滚方案。 | DB-3 | 批量追加 + 计划状态 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |

## verify Schema（23 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `verify.requirement` | P05 使用的规范化验证需求快照。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `status`, `created_at`, `updated_at` |
| `verify.requirement_coverage` | 需求到设计、代码、测试、证据的权威覆盖状态。 **关键链路** | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `updated_at` |
| `verify.capability_coverage` | 能力到目标映射、实现、测试和验证的权威覆盖状态。 **关键链路** | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `updated_at` |
| `verify.invariant` | 事务、安全、并发、行为等不可违反的不变量。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `created_at` |
| `verify.verification_plan` | 验证范围、顺序、环境、预算和停止条件。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `status`, `created_at` |
| `verify.verification_suite` | Unit/Integration/Contract/Differential/E2E 等验证套件。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `created_at` |
| `verify.verification_case` | 单个可重复验证用例。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `created_at` |
| `verify.verification_execution` | 一次 Suite/Case 执行及环境绑定。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `task_attempt_id`, `status`, `created_at` |
| `verify.verification_result` | Case/Execution 的结果摘要和 Artifact 引用。 | DB-3 | 高频结果追加 + Gate | 热/大 | R3/R4 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `verify.invariant_result` | 不变量检查的 pass/fail/unknown。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `status`, `created_at` |
| `verify.behavior_observation` | Source/Target 在同一输入下的可观察行为。 | DB-3 | 高频结果追加 + Gate | 热/大 | R3/R4 | `id`, `tenant_id`, `run_id`, `created_at` |
| `verify.differential_mismatch` | 源目标响应、状态、副作用或时序差异。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `verify.semantic_gap` | 已知/未知语义缺口、严重度和处理状态。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `status`, `created_at`, `updated_at` |
| `verify.evidence_item` | 绑定精确 Revision 的原子验证证据。 **关键链路** | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `task_attempt_id`, `status`, `created_at` |
| `verify.evidence_revocation` | 撤销过期、错误或受污染 Evidence。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `revoked_at` |
| `verify.evidence_bundle` | P05 Gate 使用的 sealed 证据集合。 **关键链路** | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `status`, `created_at` |
| `verify.evidence_bundle_item` | Evidence Bundle 的成员与角色。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `tenant_id`, `evidence_bundle_id`, `evidence_item_id`, `ordinal` |
| `verify.waiver` | 经审批的例外、风险接受、范围和失效时间。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `status` |
| `verify.gate_evaluation` | P05 完成裁决的输入 Revision、阈值和结论。 **关键链路** | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id` |
| `verify.gate_finding` | Gate 未通过或风险项的结构化发现。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `created_at` |
| `verify.failure_cluster` | 相似验证失败的聚类与根因候选。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `status` |
| `verify.repair_attempt` | 针对失败/缺口的一次自动或人工修复。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `task_attempt_id`, `status` |
| `verify.certification` | E1–E5 或其他生产认证的结果和范围。 | DB-3 | 高频结果追加 + Gate | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `target_revision_id` |

## metering Schema（9 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `metering.price_snapshot` | 调用时固定的模型/Provider/资源价格版本。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `created_at` |
| `metering.budget_reservation` | Run/Task/调用前的预算预留和释放。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `account_id`, `run_id`, `status`, `created_at` |
| `metering.model_invocation` | 每轮模型请求、路由、Token、缓存、延迟、成本与结果。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 热/大 | R3/R4 | `id`, `tenant_id`, `run_id`, `task_id`, `task_attempt_id`, `session_id`, `status` |
| `metering.tool_invocation` | 每次工具调用、审批、参数哈希、耗时、结果和成本。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 热/大 | R3/R4 | `id`, `tenant_id`, `run_id`, `task_id`, `task_attempt_id`, `session_id`, `status` |
| `metering.resource_usage_aggregate` | CPU、内存、存储、网络、GPU、Runner 时间聚合。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `task_attempt_id`, `created_at` |
| `metering.usage_ledger` | 不可变用量分录。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `account_id` |
| `metering.cost_ledger` | 不可变实际/估算成本分录。 **关键链路** | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `account_id` |
| `metering.revenue_ledger` | 不可变收费、收入、退款与冲销分录。 **关键链路** | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `account_id` |
| `metering.eta_forecast` | 机器墙钟 ETA、人工等待和人工等效工时预测。 | DB-1/DB-4 | 逐调用追加 + 聚合 | 中 | R3/R4 | `id`, `tenant_id`, `run_id`, `task_id` |

## cache Schema（4 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `cache.cache_entry` | 内容寻址缓存条目、范围、状态、收益和过期时间。 | DB-2 | 高频命中/失效 | 中 | R0/R1 | `id`, `tenant_id`, `status`, `created_at` |
| `cache.cache_dependency` | 缓存结果依赖的文件、Revision、规则、模型和工具链。 | DB-2 | 高频命中/失效 | 中 | R0/R1 | `tenant_id`, `cache_entry_id`, `dependency_kind`, `dependency_id`, `dependency_sha256` |
| `cache.cache_access` | 命中、未命中、节省 Token/时间/成本的访问事实。 | DB-2 | 高频命中/失效 | 热/大 | R0/R1 | `id`, `tenant_id`, `run_id`, `task_id` |
| `cache.cache_invalidation` | 缓存失效原因、范围、触发者和结果。 | DB-2 | 高频命中/失效 | 中 | R0/R1 | `id`, `tenant_id`, `created_at` |

## integration Schema（6 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `integration.outbox_event` | 领域事务中可靠待发布的消息。 | DB-1 | 可靠消息 + 状态机 | 热/大 | R2/R3 | `tenant_id`, `id`, `status`, `created_at` |
| `integration.inbox_message` | 消费者侧去重和处理结果。 | DB-1 | 可靠消息 + 状态机 | 中 | R2/R3 | `id`, `tenant_id`, `status` |
| `integration.side_effect_receipt` | Git/Tracker/部署等外部副作用的幂等与回执。 **关键链路** | DB-1 | 可靠消息 + 状态机 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `task_id`, `task_attempt_id`, `status`, `created_at`, `updated_at` |
| `integration.compensation_action` | 外部副作用的补偿计划、执行和结果。 | DB-1 | 可靠消息 + 状态机 | 中 | R2/R3 | `id`, `tenant_id`, `run_id`, `status`, `created_at` |
| `integration.reconciliation_run` | 一次跨系统状态重对账过程。 | DB-1 | 可靠消息 + 状态机 | 中 | R2/R3 | `id`, `tenant_id`, `status` |
| `integration.reconciliation_issue` | 重对账发现的缺失、冲突、unknown result 或人工项。 | DB-1 | 可靠消息 + 状态机 | 中 | R2/R3 | `id`, `tenant_id`, `status`, `created_at` |

## learning Schema（9 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `learning.data_authorization` | 客户数据用于统计、RAG、规则或训练的授权边界。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `project_id`, `status` |
| `learning.transformation_case` | 经验证的项目生成/转换案例。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `run_id`, `target_revision_id`, `status`, `created_at` |
| `learning.repair_trace` | 失败、根因、修复和验证闭环记录。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `run_id`, `created_at` |
| `learning.rule_candidate` | 从案例/修复提炼的候选转换或验证规则。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `created_at` |
| `learning.rule_validation` | 规则在项目、版本、正反例和 benchmark 上的验证。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `status`, `created_at` |
| `learning.rule_release` | EXPERIMENTAL→CERTIFIED 的规则版本发布。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `rule_candidate_id`, `release_version`, `release_stage`, `compatibility_contract` |
| `learning.benchmark_suite` | 标准项目生成/转换/验证基准集合。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `status`, `created_at` |
| `learning.benchmark_run` | 某模型、Harness、规则、IR 版本的一次基准执行。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `status` |
| `learning.benchmark_result` | 基准任务的质量、成本、延迟和回归结果。 | DB-4 | 离线追加/晋升 | 中 | 授权决定 | `id`, `tenant_id`, `created_at` |

## ops Schema（7 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `ops.release` | Elmos 商业发布版本、合同和镜像集合。 | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `status`, `created_at` |
| `ops.release_component` | 服务/Worker/迁移组件及不可变镜像 digest。 | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `created_at` |
| `ops.deployment` | 某环境的一次部署实例。 | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `status` |
| `ops.migration_run` | 数据库 Migration 执行、版本、状态和证据。 **关键链路** | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `status` |
| `ops.service_health_snapshot` | 服务 /livez/readyz/version/metrics 的部署时快照。 | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `deployment_id`, `release_component_id`, `service_name`, `image_digest` |
| `ops.deployment_check` | 镜像、迁移、RLS、Smoke、Benchmark 等部署检查项。 | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `status` |
| `ops.deployment_gate` | P05 风格的部署完成裁决。 **关键链路** | DB-4 | 发布状态 + 快照 | 小 | R3/R4 | `id`, `tenant_id`, `deployment_id`, `gate_policy_revision_id`, `release_id`, `migration_run_id` |

## audit Schema（1 张）

| 表 | 职责 | 阶段 | 写入模式 | 数据量级 | 保留 | 关键列摘要 |
|---|---|---|---|---|---|---|
| `audit.audit_event` | 安全、权限、下载、Gate、部署、数据授权等 append-only 审计事实。 **关键链路** | DB-1 | 只追加 | 热/大 | R4 | `tenant_id`, `id`, `run_id` |

## 3. 首次上线最小表集合

DB-1 推荐先启用以下核心闭环；其余表可在同一 Schema 中存在，但应用功能按 Feature Flag 逐步开放：

```text
Tenant / Account / Project / Repository
Job / Submission / Input Revision / Account Slots
Run / Stage / Task / Attempt / Lease / Workspace
Run Event / Progress / Session Event / Workpad
Artifact / Manifest / Staging / Checkpoint
Outbox / Inbox / Side-effect Receipt / Reconciliation
Model Invocation / Tool Invocation / Usage / Cost / ETA
Audit Event
```

完整项目生成和跨库转换对外 GA 前，必须再启用 DB-2 与 DB-3。P07 Learning 在没有客户数据授权前应保持关闭。

## 4. 大字段边界

任何表都不应新增以下字段：

```text
source_code TEXT/BYTEA
full_ast JSONB/TEXT/BYTEA
raw_model_output TEXT/BYTEA
complete_stdout TEXT/BYTEA
```

需要保存这些内容时创建 `artifact.object_blob` + `artifact.artifact`，业务表仅保存 `artifact_id`、digest、摘要和大小。

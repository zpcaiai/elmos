# BATCH-04-architecture-flow-data — 架构、功能、流程、数据与运行视图

## 目标

从静态和运行证据发现架构、业务能力、流程、数据、API 与事件。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-data-architecture-lineage` | 建立数据资产、字段、读写、转换、生命周期和功能之间的可追踪模型。 | `elmos-project-intelligence-graph` |
| 2 | `elmos-api-event-topology` | 把系统所有外部与内部接口统一为可版本化、可回源、可影响分析的 Integration Graph。 | `elmos-project-intelligence-graph`, `elmos-evidence-provenance` |
| 3 | `elmos-runtime-trace-fusion` | 在不把有限观测误当完整事实的前提下，用运行证据提高架构、流程和影响分析可信度。 | `elmos-project-intelligence-graph` |
| 4 | `elmos-architecture-discovery` | 生成可解释、可编辑、可回源的多层架构模型与讲解。 | `elmos-project-intelligence-graph`, `elmos-runtime-trace-fusion` |
| 5 | `elmos-business-capability-map` | 建立需求—功能—页面—API—代码—数据—测试的端到端追踪。 | `elmos-architecture-discovery`, `elmos-evidence-provenance` |
| 6 | `elmos-flow-discovery` | 从入口到结束状态构建带分支、数据、副作用和证据的可执行流程模型。 | `elmos-symbol-code-graph`, `elmos-runtime-trace-fusion` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-13-T01` | `elmos-architecture-discovery` | 识别系统边界、外部 Actor 和外部系统 | implementation | P1 |
| `ELMOS-PI-13-T02` | `elmos-architecture-discovery` | 聚合服务、容器、组件、模块和层 | implementation | P1 |
| `ELMOS-PI-13-T03` | `elmos-architecture-discovery` | 识别同步调用、异步事件、共享数据和部署关系 | implementation | P1 |
| `ELMOS-PI-13-T04` | `elmos-architecture-discovery` | 生成业务、应用、技术、数据、部署、安全视图 | implementation | P1 |
| `ELMOS-PI-13-T05` | `elmos-architecture-discovery` | 对照人工设计和运行证据，记录冲突 | implementation | P1 |
| `ELMOS-PI-13-T06` | `elmos-architecture-discovery` | 按受众生成 L0-L5 架构讲解 | implementation | P1 |
| `ELMOS-PI-13-T07` | `elmos-architecture-discovery` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-13-T08` | `elmos-architecture-discovery` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-13-T09` | `elmos-architecture-discovery` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-13-T10` | `elmos-architecture-discovery` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-14-T01` | `elmos-business-capability-map` | 识别 Actor、业务域、业务能力、功能模块和子功能 | implementation | P1 |
| `ELMOS-PI-14-T02` | `elmos-business-capability-map` | 将页面、API、事件、代码、数据表、权限和测试挂接到功能节点 | implementation | P1 |
| `ELMOS-PI-14-T03` | `elmos-business-capability-map` | 使用命名、调用链和文档证据生成候选功能 | implementation | P1 |
| `ELMOS-PI-14-T04` | `elmos-business-capability-map` | 让用户确认、合并、拆分、重命名和排序 | implementation | P1 |
| `ELMOS-PI-14-T05` | `elmos-business-capability-map` | 计算实现覆盖、测试覆盖、风险和转换状态 | implementation | P1 |
| `ELMOS-PI-14-T06` | `elmos-business-capability-map` | 生成 Markmap、树形图、矩阵和可编辑 JSON | implementation | P1 |
| `ELMOS-PI-14-T07` | `elmos-business-capability-map` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-14-T08` | `elmos-business-capability-map` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-14-T09` | `elmos-business-capability-map` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-14-T10` | `elmos-business-capability-map` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-15-T01` | `elmos-flow-discovery` | 枚举 HTTP、GraphQL、gRPC、UI、Consumer、Cron、CLI、Webhook、Agent Task 等入口 | implementation | P1 |
| `ELMOS-PI-15-T02` | `elmos-flow-discovery` | 按控制流和调用图扩展步骤，识别条件、循环、并行和异步边 | implementation | P1 |
| `ELMOS-PI-15-T03` | `elmos-flow-discovery` | 关联状态变化、数据库写入、事件、外部调用和权限检查 | implementation | P1 |
| `ELMOS-PI-15-T04` | `elmos-flow-discovery` | 发现超时、重试、幂等、死信和补偿 | implementation | P1 |
| `ELMOS-PI-15-T05` | `elmos-flow-discovery` | 用 Trace/测试确认高价值路径 | implementation | P1 |
| `ELMOS-PI-15-T06` | `elmos-flow-discovery` | 生成 BPMN、泳道、时序、状态机和普通流程视图 | implementation | P1 |
| `ELMOS-PI-15-T07` | `elmos-flow-discovery` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-15-T08` | `elmos-flow-discovery` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-15-T09` | `elmos-flow-discovery` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-15-T10` | `elmos-flow-discovery` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-16-T01` | `elmos-data-architecture-lineage` | 抽取数据库、Schema、表、字段、索引、约束和实体 | implementation | P1 |
| `ELMOS-PI-16-T02` | `elmos-data-architecture-lineage` | 解析 ORM、手写 SQL、Repository 和迁移历史 | implementation | P1 |
| `ELMOS-PI-16-T03` | `elmos-data-architecture-lineage` | 识别 API/事件字段到内部模型和持久化字段映射 | implementation | P1 |
| `ELMOS-PI-16-T04` | `elmos-data-architecture-lineage` | 识别缓存、搜索索引、对象存储和 ETL 流 | implementation | P1 |
| `ELMOS-PI-16-T05` | `elmos-data-architecture-lineage` | 标注敏感等级、保留期限、加密和跨境边界 | implementation | P1 |
| `ELMOS-PI-16-T06` | `elmos-data-architecture-lineage` | 生成 ER、DFD、血缘、生命周期、CRUD 与数据质量视图 | implementation | P1 |
| `ELMOS-PI-16-T07` | `elmos-data-architecture-lineage` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-16-T08` | `elmos-data-architecture-lineage` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-16-T09` | `elmos-data-architecture-lineage` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-16-T10` | `elmos-data-architecture-lineage` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-17-T01` | `elmos-api-event-topology` | 抽取端点、方法、请求响应、认证、错误和版本 | implementation | P1 |
| `ELMOS-PI-17-T02` | `elmos-api-event-topology` | 抽取 Topic/Queue、事件 Schema、生产者、消费者、重试和死信 | implementation | P1 |
| `ELMOS-PI-17-T03` | `elmos-api-event-topology` | 识别 HTTP/RPC 客户端、SDK、Webhook 和第三方服务 | implementation | P1 |
| `ELMOS-PI-17-T04` | `elmos-api-event-topology` | 关联接口到功能、服务、数据和测试 | implementation | P1 |
| `ELMOS-PI-17-T05` | `elmos-api-event-topology` | 检测未文档接口、Schema 漂移、废弃版本和消费者风险 | implementation | P1 |
| `ELMOS-PI-17-T06` | `elmos-api-event-topology` | 生成 API 拓扑、事件拓扑、时序和版本兼容图 | implementation | P1 |
| `ELMOS-PI-17-T07` | `elmos-api-event-topology` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-17-T08` | `elmos-api-event-topology` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-17-T09` | `elmos-api-event-topology` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-17-T10` | `elmos-api-event-topology` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-18-T01` | `elmos-runtime-trace-fusion` | 接收或导入 OTLP Trace/Span 与环境标签 | implementation | P1 |
| `ELMOS-PI-18-T02` | `elmos-runtime-trace-fusion` | 规范化 service/resource/code attributes | implementation | P1 |
| `ELMOS-PI-18-T03` | `elmos-runtime-trace-fusion` | 将 span 关联到 API、symbol、database、message 和 external system | implementation | P1 |
| `ELMOS-PI-18-T04` | `elmos-runtime-trace-fusion` | 聚合调用频率、延迟、错误和关键路径 | implementation | P1 |
| `ELMOS-PI-18-T05` | `elmos-runtime-trace-fusion` | 比较静态候选边与运行观测边 | implementation | P1 |
| `ELMOS-PI-18-T06` | `elmos-runtime-trace-fusion` | 发布 runtime evidence 并触发受影响 artifact 更新 | implementation | P1 |
| `ELMOS-PI-18-T07` | `elmos-runtime-trace-fusion` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-18-T08` | `elmos-runtime-trace-fusion` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-18-T09` | `elmos-runtime-trace-fusion` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-18-T10` | `elmos-runtime-trace-fusion` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 预期交付物

- `data-ir.json`（由 `elmos-data-architecture-lineage` 负责）
- `erd.json`（由 `elmos-data-architecture-lineage` 负责）
- `data-lineage.json`（由 `elmos-data-architecture-lineage` 负责）
- `crud-matrix.csv`（由 `elmos-data-architecture-lineage` 负责）
- `api-catalog.json`（由 `elmos-api-event-topology` 负责）
- `event-catalog.json`（由 `elmos-api-event-topology` 负责）
- `integration-topology.json`（由 `elmos-api-event-topology` 负责）
- `runtime-graph.json`（由 `elmos-runtime-trace-fusion` 负责）
- `static-runtime-diff.md`（由 `elmos-runtime-trace-fusion` 负责）
- `trace-link-report.json`（由 `elmos-runtime-trace-fusion` 负责）
- `architecture-model.dsl`（由 `elmos-architecture-discovery` 负责）
- `architecture-explanation.md`（由 `elmos-architecture-discovery` 负责）
- `unknowns.json`（由 `elmos-architecture-discovery` 负责）
- `capability-map.json`（由 `elmos-business-capability-map` 负责）
- `functional-mindmap.mm.json`（由 `elmos-business-capability-map` 负责）
- `feature-traceability.csv`（由 `elmos-business-capability-map` 负责）
- `flow-ir.json`（由 `elmos-flow-discovery` 负责）
- `flow-catalog.md`（由 `elmos-flow-discovery` 负责）
- `flow-quality-report.json`（由 `elmos-flow-discovery` 负责）
- 本批次 `EXECUTION_REPORT.md`、测试结果、审计日志引用和恢复 checkpoint。
- 更新后的需求—实现—测试—证据追踪矩阵。

## 端到端实现步骤

1. 扫描现有仓库，建立“已存在/缺失/冲突/可复用”差距清单。
2. 冻结 API、事件、Schema、领域实体和权限矩阵；兼容性变更必须有迁移方案。
3. 先完成最小真实数据垂直切片，再补异常、恢复、配额和多租户路径。
4. 为长任务实现幂等、暂停、恢复、重试、取消、租约和检查点。
5. 接入日志、指标、Trace、错误分类、审计和 evidence binding。
6. 执行单元、契约、集成、E2E、安全、性能/恢复测试中的适用集合。
7. 回放失败场景，修复至本批次全部硬门禁通过。
8. 固化机器 wall-clock 实测、Token/计算/存储消耗和人工审核工作量。

## 验收场景

| AC | Skill | 验收结果 | 自动化 |
|---|---|---|---|
| `AC-13-01` | `elmos-architecture-discovery` | 系统上下文和容器图覆盖所有确认入口与外部依赖。 | required |
| `AC-13-02` | `elmos-architecture-discovery` | 节点可下钻到代码成员。 | required |
| `AC-13-03` | `elmos-architecture-discovery` | 人工 override 在重新分析后保持。 | required |
| `AC-13-04` | `elmos-architecture-discovery` | 架构讲解关键结论有证据。 | preferred |
| `AC-13-05` | `elmos-architecture-discovery` | 当前/目标模型不会混写。 | preferred |
| `AC-14-01` | `elmos-business-capability-map` | 主要用户流程功能均可映射到 API/代码/数据。 | required |
| `AC-14-02` | `elmos-business-capability-map` | 功能图节点可双向导航。 | required |
| `AC-14-03` | `elmos-business-capability-map` | 重复功能候选可识别。 | required |
| `AC-14-04` | `elmos-business-capability-map` | 未映射比例可量化。 | preferred |
| `AC-14-05` | `elmos-business-capability-map` | 导出后可重新导入且不丢稳定 ID。 | preferred |
| `AC-15-01` | `elmos-flow-discovery` | 基准流程的主要步骤、状态和副作用完整。 | required |
| `AC-15-02` | `elmos-flow-discovery` | 异常、重试和补偿可独立查看。 | required |
| `AC-15-03` | `elmos-flow-discovery` | Trace 能覆盖并确认已执行路径。 | required |
| `AC-15-04` | `elmos-flow-discovery` | 流程图与 Flow IR 往返不丢语义。 | preferred |
| `AC-15-05` | `elmos-flow-discovery` | 入口清单覆盖率可量化。 | preferred |
| `AC-16-01` | `elmos-data-architecture-lineage` | ER 图与迁移/ORM 核心关系一致。 | required |
| `AC-16-02` | `elmos-data-architecture-lineage` | 主要写路径能追到数据资产。 | required |
| `AC-16-03` | `elmos-data-architecture-lineage` | CRUD 矩阵无跨 revision 混合。 | required |
| `AC-16-04` | `elmos-data-architecture-lineage` | 敏感字段分类有证据和人工复核入口。 | preferred |
| `AC-16-05` | `elmos-data-architecture-lineage` | 血缘边可回溯转换表达式或代码位置。 | preferred |
| `AC-17-01` | `elmos-api-event-topology` | 已声明接口与实现映射覆盖率可量化。 | required |
| `AC-17-02` | `elmos-api-event-topology` | Breaking change 检测有正反例测试。 | required |
| `AC-17-03` | `elmos-api-event-topology` | Topic 生产者/消费者链可追踪。 | required |
| `AC-17-04` | `elmos-api-event-topology` | 未鉴权和未测试接口可筛选。 | preferred |
| `AC-17-05` | `elmos-api-event-topology` | 拓扑节点可回到契约与代码。 | preferred |
| `AC-18-01` | `elmos-runtime-trace-fusion` | 已知 Trace 可正确映射到服务/接口/数据库。 | required |
| `AC-18-02` | `elmos-runtime-trace-fusion` | 静态与运行差异有明确原因分类。 | required |
| `AC-18-03` | `elmos-runtime-trace-fusion` | 采样限制显示在每个运行结论旁。 | required |
| `AC-18-04` | `elmos-runtime-trace-fusion` | 跨环境查询不会混淆。 | preferred |
| `AC-18-05` | `elmos-runtime-trace-fusion` | 高容量导入有背压与保留策略。 | preferred |

## 生产门禁

- [ ] 所有 P0/P1 任务均有真实实现、迁移和测试；无 placeholder-only 完成项。
- [ ] 固定 revision 重跑结果可复现，输出绑定生成器、规则、模板和模型版本。
- [ ] Confirmed claim 可深链至证据；Inferred/Unknown/Recommended 标识正确。
- [ ] 多租户、最小权限、Prompt Injection、Secrets、日志脱敏和不可信内容测试通过。
- [ ] Worker 中断、重复消息、超时、取消和恢复不造成重复副作用。
- [ ] API/事件/Schema 有版本，兼容性与回滚方案已验证。
- [ ] UI 显示 revision、覆盖率、可信度、新鲜度、阶段、机器 ETA P50/P90 和恢复入口。
- [ ] 所有人工锁定内容、评论、审批与审计记录在再生成后保持。

## 检查点与恢复

每个阶段记录 `checkpoint_id`、输入 manifest、revision、已提交副作用、缓存键、工具/模型版本和下一步。恢复前验证这些条件仍兼容；不兼容时创建新 run，不覆盖旧证据。

## 退出标准

- [ ] 本批次 60 条任务均已分类为 done/waived，并附责任人与证据。
- [ ] 本批次 30 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。

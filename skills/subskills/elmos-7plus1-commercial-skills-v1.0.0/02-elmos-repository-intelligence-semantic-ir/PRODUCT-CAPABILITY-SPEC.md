# P02 产品能力规范：Elmos 仓库智能与语义中间表示

## 1. 产品定位

完整发现源仓库的代码、配置、依赖、数据、消息、权限、部署与运行语义，并形成可查询 Repository Graph、Semantic IR 和 Capability Ledger。

**客户可感知价值：** 解决大型项目转换中“没看见，所以没转换”的根本问题，是完整度与未知缺口控制的基础。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 扫描代码、构建、依赖、配置、Schema、API、MQ、缓存、定时任务、权限、CI/CD 和基础设施。
- 融合 AST、符号、LSP、调用图、控制流、数据流、运行 Trace 和配置条件。
- 构建语言无关但保留语义差异的 Canonical Semantic IR。
- 将源仓库能力拆成可追踪 Capability Ledger，并计算发现/映射/验证覆盖率。
- 支持增量分析、缓存、版本/框架识别、查询 API 和大型 Monorepo 分区。
- 为每个节点/边记录来源、版本、证据、置信度和不确定性。

## 4. 非目标与产品边界

- 不直接生成目标代码；向 P03 提供经过证据标注的 IR 和能力。
- LSP/LLM 结论必须带 provenance/confidence，不能替代 AST/编译器/运行证据。
- 对无法解析或动态生成的区域必须显式创建 blind spot，不得假装已理解。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Repository Inventory Scanner | 文件、模块、构建系统、依赖、配置、测试、部署与资产清单。 | P02-C01 |
| Language & Framework Detectors | 语言版本、框架、插件、代码生成器、运行时和约定识别。 | P02-C02 |
| AST & Symbol Index | 多语言解析、符号表、类型、引用、继承/实现和注解。 | P02-C03 |
| LSP Semantic Navigation | definition/reference/implementation/hover 及诊断补充。 | P02-C04 |
| Program Graph Builder | dependency/call/control/data-flow/side-effect/concurrency graph。 | P02-C05 |
| Platform Graph Builder | API/DB/MQ/cache/cron/security/config/infra/deployment graph。 | P02-C06 |
| Runtime Trace Ingestor | 请求、SQL、消息、缓存、文件、锁、指标和异常 Trace 对齐。 | P02-C07 |
| Canonical Semantic IR | 类型、函数、状态、契约、副作用、事务、并发和平台能力表示。 | P02-C08 |
| Capability Discovery Engine | 业务/技术能力识别、聚类、依赖和 Capability Ledger。 | P02-C09 |
| Provenance & Confidence Engine | 证据来源、置信度、冲突、blind spot 和 freshness。 | P02-C10 |
| Incremental Analysis Cache | 内容寻址、变更影响分析、分区更新和可复现 snapshot。 | P02-C11 |
| Repository Query Service | 图查询、语义检索、影响分析和下游批量导出。 | P02-C12 |

## 6. 关键用户旅程

### 6.1 新项目生成

1. 导入自然语言、多模态需求与商业约束。
2. 通过 P02/P03 建立需求、能力、架构与实施 DAG。
3. P04 调度专业 Agent，P01 负责可靠执行，P06 负责模型/Provider 路由。
4. P05 执行覆盖、差分、E2E、非功能与证据 Gate。
5. P00 返回系统墙钟 ETA、真实成本、交付物、风险、认证与回滚。
6. P07 只沉淀经过验证且授权的可复用知识。

### 6.2 跨语言/跨框架/跨库转换

1. 固定源仓库 revision 和运行环境，P02 扫描并建立 Repository Graph/IR/Ledger。
2. P03 选择规则、生成 Target IR、代码、迁移与双运行计划。
3. P04 分任务并行实施；Generator 与 Verifier 分权。
4. P05 在相同场景下比较源/目标行为，发现 gap 后进入 Repair Loop。
5. 只有 Evidence Gate 通过才允许切流、合并或认证。

## 7. 商业版本建议

| 版本 | 能力范围 | 限制 |
| --- | --- | --- |
| Community/Developer | 单用户、本地仓库、基础运行与报告 | 无企业 SLA；默认不含生产 cutover。 |
| Team | 团队项目、共享规则、并发、CI/PR、成本与质量 Dashboard | 组织内知识隔离。 |
| Enterprise | 多租户、SSO/RBAC、私有部署、BYOK/ZDR、审计、SLA、E1–E5 | 需客户安全与数据政策配置。 |
| Regulated | 金融/医疗/工业等专用基线、双人审批、WORM 证据、区域部署 | 按场景认证，不承诺无限通用。 |

## 8. 成功指标

- **结果指标：** Requirement coverage、Capability coverage、Behavioral equivalence、Critical unknown gaps、人工介入率。
- **运行指标：** 成功恢复率、重复副作用率、任务完成时长、模型/工具成本、缓存命中与 Provider fallback。
- **商业指标：** 项目毛利、交付周期、试点转付费、复购、SLA 违约、支持成本。
- **知识复利：** trusted rules 数量、复用率、规则命中后的质量/成本改善、bad-rule escape rate。

指标必须带 scenario/规模/版本/样本量/置信区间；不发布无上下文的统一“准确率”。

## 9. 硬不变量

- 所有源文件、构建入口和部署入口都有 discovered/ignored/unsupported 状态与理由。
- IR 不抹平事务、并发、异常、生命周期、权限、数据一致性和副作用差异。
- Capability ID 在同一源版本内稳定，可跨增量扫描追踪。
- 动态行为与静态推断冲突时保留两者并标记 conflict，不得静默覆盖。
- 每条语义结论可追溯到文件范围、符号、配置、Trace 或人工确认。
- 未知/低置信度区域进入 P05 的定向验证计划。

## 10. 依赖与集成

- 上游依赖：P00, P01。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。

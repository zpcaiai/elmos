# P03 产品能力规范：Elmos 完整项目生成与多语言跨库转换引擎

## 1. 产品定位

将需求扩展为完整商业项目，或把源 Repository Graph/Semantic IR 变换为目标语言、框架、数据库、消息和前端平台。

**客户可感知价值：** 把 Elmos 从通用 Coding Agent 提升为可重复、可约束、可验证的软件生成与迁移引擎。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 将模糊需求扩展为 Requirement Graph、非功能需求、验收标准和商业周边能力。
- 建立 SaaS、支付、电商、ERP、CRM、AI Agent、IoT、工业、大数据等 Archetype。
- 从 Semantic IR 规划目标架构、模块、数据、接口和实施 DAG。
- 实现 Rule DSL、Mutation DSL、Scenario DSL、Evidence DSL 与确定性转换引擎。
- 覆盖 Java/Kotlin/Python/C#/Go/Rust/C++/PHP/TS/JS/Swift/ObjC/Flutter 等语言及主要框架。
- 支持 Vue/React/Flutter 到微信、支付宝、抖音、小红书小程序的前端转换。
- 生成生产级代码、测试、配置、迁移、部署、安全、观测、文档和运营能力。
- 支持 Strangler、shadow、双运行、渐进切换、回滚和 reversible migration。

## 4. 非目标与产品边界

- 生成结果必须进入 P05 验证闭环；本包无权自行声明完成。
- 规则与模型不得绕过 P02 的 blind spot/uncertainty，也不得假造源语义。
- 目标栈不支持的语义必须形成 explicit gap/decision，不允许静默删除。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Requirement Expansion Engine | 从用户输入、文件和上下文补全功能/非功能/运营/安全/合规需求。 | P03-C01 |
| Project Archetype Engine | 行业/产品基线、Capability baseline 和缺失需求提示。 | P03-C02 |
| Architecture Synthesizer | 生成模块、边界、数据、接口、部署、决策记录和风险。 | P03-C03 |
| Implementation DAG Planner | 按依赖、风险、可验证性和并行度拆分任务。 | P03-C04 |
| Transformation Rule Engine | Rule DSL 匹配、前置条件、语义不变量、目标策略与验证。 | P03-C05 |
| Mutation & Exception Engine | 受控偏离、版本特例、项目 override 和冲突决策。 | P03-C06 |
| Multi-language Emitters | 从 IR 生成语言惯用、可编译、可测试的目标代码。 | P03-C07 |
| Framework/Platform Adapters | Spring/.NET/FastAPI/Gin/Axum/NestJS/Vue/React/Flutter/小程序等。 | P03-C08 |
| Data & Integration Transformer | 数据库、ORM、事务、MQ、缓存、文件、RPC、批处理和调度。 | P03-C09 |
| Infrastructure & Operations Generator | Docker/K8s/CI/CD/observability/backup/DR/secrets/SBOM。 | P03-C10 |
| Unsupported Semantics Manager | gap、候选方案、人工决策、风险和 temporary bridge。 | P03-C11 |
| Migration Controller | Strangler、shadow、dual-run、cutover、reconciliation、rollback。 | P03-C12 |

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

- 每个 Requirement/Capability 都有目标映射、实现、验证或 explicit blocked 状态。
- 确定性规则命中后禁止被自由模型无理由覆盖；覆盖必须形成可审计 mutation decision。
- 事务、并发、消息投递、权限、数据精度、异常和副作用语义不得静默弱化。
- 生成的生产代码中 TODO/stub/mock/empty handler 必须显式计入未完成。
- 所有 Schema/API/Event 变更生成版本与迁移策略。
- 生产迁移默认可回滚，破坏性操作需审批和备份证据。

## 10. 依赖与集成

- 上游依赖：P00, P01, P02, P05。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。

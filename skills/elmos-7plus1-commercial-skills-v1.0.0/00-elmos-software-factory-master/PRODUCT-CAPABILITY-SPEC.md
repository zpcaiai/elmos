# P00 产品能力规范：Elmos 软件工厂总控与商业治理

## 1. 产品定位

统一 7 个能力包的依赖、工作流、产品控制面、架构约束、文档系统、版本治理、发布认证和商业运营。

**客户可感知价值：** 把多个强能力模块组合成可销售、可升级、可审计、可运营的软件工厂产品，而不是一组互不兼容的 Agent 工具。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 建立 7+1 Package Registry、依赖图、版本兼容矩阵和升级/回滚策略。
- 把 ELMOS_WORKFLOW.md 编译为可验证的任务、策略、钩子、并发和发布合同。
- 形成仓库即系统记录的文档树、短 AGENTS.md 地图、执行计划与文档新鲜度检查。
- 建立多租户控制面：项目、作业、配额、成本、ETA、收入、账单、权限、审计、SLA。
- 用结构化 lint、架构测试和 Golden Principles 防止代码与能力包逐渐失控。
- 建立 Phase 0–4 的产品门、商业 GA 清单与证据化发布流程。

## 4. 非目标与产品边界

- 不实现语言语义转换算法；只定义跨包合同、控制面和发布规则。
- 不直接执行模型调用；通过 P01/P06 调用。
- 不允许总控层绕过 P05 证据门宣布项目完成。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Package Registry | 登记包、子技能、依赖、兼容版本、owner、maturity、feature flag 和弃用状态。 | P00-C01 |
| Workflow Compiler | 把仓库内工作流合同编译为任务模板、策略快照、Hooks、状态机和验收门。 | P00-C02 |
| Architecture Governor | 执行分层、依赖方向、公共 API、Schema/事件兼容和禁止路径等结构测试。 | P00-C03 |
| Repository Knowledge System | 维护 AGENTS 地图、产品规范、架构文档、执行计划、运行手册和决策记录。 | P00-C04 |
| Commercial Control Plane | 管理 tenant/project/job/quota/cost/revenue/ETA/billing/SLA/support tier。 | P00-C05 |
| Release & Certification Manager | 组织版本冻结、迁移、灰度、回滚、E1–E5 认证和审计签名。 | P00-C06 |
| Configuration & Feature Governance | 动态配置、灰度、实验、last-known-good、kill switch 和配置审计。 | P00-C07 |
| Upstream Intelligence | 跟踪 Harness/SDK breaking changes、许可证、漏洞和适配器兼容性。 | P00-C08 |

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

- 包之间只能通过版本化合同通信，禁止跨层直接访问内部数据库或私有实现。
- 所有可部署配置必须 schema-valid，并支持 last-known-good 回退。
- 每个发布必须绑定源版本、包版本、迁移说明、回归证据和回滚路径。
- 控制面不得持有可直接下发给 Agent 的长期生产凭据；使用短期、范围化授权。
- AGENTS.md 只做地图，不复制整套手册；详细知识通过渐进披露加载。
- 商业计划中的质量指标均标记 target / observed / certified 三种状态。

## 10. 依赖与集成

- 上游依赖：无功能包依赖。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。

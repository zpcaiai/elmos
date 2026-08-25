# P07 产品能力规范：Elmos 转换知识沉淀、自学习与能力进化

## 1. 产品定位

把每次经过验证的生成、转换、失败、修复、规则、项目模式和证据沉淀为可复用知识，并通过严格晋升、基准回归和专项模型训练持续提高质量。

**客户可感知价值：** 形成属于 Elmos 自己的 Software Transformation Intelligence，使模型和 Harness 可替换，而转换能力随项目数量复利增长。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 建立 Transformation KB、Project Archetype KB、Failure/Repair KB、Benchmark Corpus、Evidence Corpus。
- 记录规则适用条件、语言/框架版本、语义不变量、例外、验证和置信度。
- 保存 failure→root cause→bad transform→repair→verification 的完整 Repair Trace。
- 实现 EXPERIMENTAL→CANDIDATE→VALIDATED→TRUSTED→CERTIFIED→DEPRECATED 生命周期。
- 在跨项目、跨版本和对抗样例上验证规则，防止把 workaround 当普遍规律。
- 每次模型/Harness/Prompt/Rule/IR 升级都运行固定 Benchmark 与历史 replay。
- 训练/评测 Semantic Mapper、Gap Detector、Rule Selector、Repair Ranker、Verification Planner 等专项模型。
- 建立 active learning、人工治理、知识漂移、毒化防护和删除/遗忘机制。

## 4. 非目标与产品边界

- 任何未经 P05 验证的输出不得进入 trusted/certified 知识。
- 租户私有代码/规则默认不进入全局知识；只允许授权、脱敏和抽象后的资产。
- 学习系统不能在无回归证据时自动修改生产规则。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Transformation Knowledge Base | 语言/框架/API/类型/事务/并发/异常/安全/数据/消息规则。 | P07-C01 |
| Project Archetype Knowledge Base | 行业能力基线、架构模式、周边功能和验收模板。 | P07-C02 |
| Failure & Repair Corpus | 失败、上下文、根因、错误转换、修复和验证轨迹。 | P07-C03 |
| Rule Promotion & Governance | maturity、跨项目证据、版本兼容、owner、expiry、rollback。 | P07-C04 |
| Benchmark Corpus | 项目生成、语言转换、框架现代化、前端/小程序和非功能基准。 | P07-C05 |
| Evidence Corpus | compile/test/differential/production/rollback 经过签名的结果。 | P07-C06 |
| Retrieval & Repair Ranker | 相似失败检索、适用性过滤、修复候选排序和 confidence。 | P07-C07 |
| Drift & Regression Detector | 模型/规则/框架/依赖变化导致的质量漂移。 | P07-C08 |
| Active Learning Queue | 选择最有信息价值的未知 gap、低置信规则和失败样本。 | P07-C09 |
| Specialized Model Pipeline | 数据构造、训练、评测、部署和 shadow。 | P07-C10 |
| Tenant/IP Isolation & Consent | 私有/组织/全局 scope、授权、脱敏、删除和审计。 | P07-C11 |
| Knowledge Quality Auditor | 重复、冲突、毒化、过期、覆盖盲区和证据完整性。 | P07-C12 |

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

- 知识条目始终绑定 provenance、tenant/IP scope、版本、验证证据和 maturity。
- 一次修复成功最多进入 EXPERIMENTAL/CANDIDATE，不可直接 trusted。
- 规则晋升必须通过跨项目回归与负向测试；失败自动降级/隔离。
- 全局知识不保存可重构租户专有代码的原文或敏感数据。
- Benchmark 数据集版本固定、任务泄漏受控、评测结果可复现。
- 专项模型输出仍受 P03 规则与 P05 Gate 约束。

## 10. 依赖与集成

- 上游依赖：P00, P02, P03, P05, P06。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。

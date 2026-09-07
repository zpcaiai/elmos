# P05 产品能力规范：Elmos 转换可靠性、验证与证据完成门

## 1. 产品定位

以 Requirement/Capability Ledger、机械化完成门、差分运行时、全栈测试、故障注入、自动修复和证据包证明项目生成与跨库转换正确且完整。

**客户可感知价值：** 直接决定 Elmos 是否能把“生成代码”变成“可证明完成的软件工程交付”，也是降低假完成率的核心。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 建立 Requirement Ledger 与 Capability Ledger 的 end-to-end closure。
- 定义 Evidence-based Completion Gate，阻止 TODO/stub/未知 gap/失败测试的假完成。
- 覆盖 build/lint/type/static/unit/integration/contract/differential/E2E/UI/perf/security/supply chain。
- 建立源/目标双运行差分，比较响应、DB、缓存、MQ、文件、事务、异常、权限和副作用。
- 加入 property-based、metamorphic、fuzz、mutation、failure injection 和 resilience testing。
- 建立 UI screenshot/video/DOM/state 多模态验证与关键用户流程 replay。
- 实现诊断→Repair→验证循环、最大轮次、无进展检测和人工 blocker。
- 形成 Evidence Bundle 与 E1–E5 生产认证体系。

## 4. 非目标与产品边界

- 任何模型或 Agent 的自评只作为线索，不作为 pass 证据。
- 单一综合分数不能掩盖关键 Gate 失败、未知缺口或不适用测试。
- 自动修复不能修改验收标准来让测试通过。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Requirement Coverage Ledger | 需求→设计→实现→测试→证据闭环。 | P05-C01 |
| Capability Coverage Ledger | 源能力发现、目标映射、生成、编译、测试、验证、gap 状态。 | P05-C02 |
| Mechanical Completion Gate | 组合硬 Gate、阈值、豁免、风险等级和 freshness。 | P05-C03 |
| Verification Planner | 按语言/框架/风险/变更选择最小充分测试矩阵。 | P05-C04 |
| Compiler & Static Pipeline | build、lint、typecheck、static analysis、architecture rules。 | P05-C05 |
| Contract & Integration Pipeline | API/schema/event/DB/MQ/cache/auth/integration。 | P05-C06 |
| Differential Runtime | 相同输入下源/目标行为与副作用快照比较。 | P05-C07 |
| Generative Testing | property/metamorphic/fuzz/mutation/combinatorial。 | P05-C08 |
| UI & Multimodal Verifier | DOM/state/screenshot/video/interaction/accessibility。 | P05-C09 |
| Nonfunctional Verification | performance/stress/security/resilience/supply chain/DR。 | P05-C10 |
| Diagnosis & Repair Loop | 聚类失败、根因、修复任务、回归与无进展控制。 | P05-C11 |
| Evidence & Certification Engine | 证据索引、签名、E1–E5、客户报告和审计导出。 | P05-C12 |

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

- COMPLETED 状态只由 Gate Engine 写入，其他组件只能请求评估。
- 所有测试绑定 source revision、target revision、environment、seed 和 tool version。
- 验证器默认 read-only；修复由独立 Repair Agent 在范围化权限下执行。
- 差分比较先规范化非语义噪声，再比较业务可观察行为。
- 豁免必须有 owner、理由、风险、补偿控制、到期时间和人工审批。
- 证据可重放或至少可验证 hash/签名与来源。

## 10. 依赖与集成

- 上游依赖：P00, P01, P02。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。

# 架构与商业交付边界

## 1. 三个平面，而非一个万能 Agent

**交付平面**：现有四个 Domain Pack、Generator/Converter、Repair；只产出候选物。
**验证平面**：契约、Oracle、测试、差分、变异、形式化、证据服务；读取冻结候选物，由受控执行器产生事实。
**审计/授权平面**：Ethen审计工作区、政策引擎、K8签署与撤销。独立账户、存储ACL、执行身份与审计日志。

最初可用模块化单体承载无权限冲突的控制逻辑。执行器与签署/审计信任域必须物理或等效安全隔离。不要为每个 Skill 建微服务。生产数据库沿用已验证的现有选择；本包 PostgreSQL 迁移是待适配参考，不强制替换。

## 2. 业务闭环

`Admit → Inventory → Approve scope/spec → Freeze plan → Build → Smoke → Regression → Risk verification → Seal → Audit → Decide → Sign → Observe/Revoke`。

形式化的**命题定义、规则证明**可在构建前或并行执行；不是把 Lean 全部放在最后。冒烟失败暂停依赖运行健康的昂贵作业，但不得销毁失败证据，独立可执行的规则证明可以继续。

## 3. 共享模块接口

| 模块 | 输入 → 输出 | 核心责任 |
|---|---|---|
| ScopeCompiler | 需求/资产清单 → AssuranceScope | 版本、支持范围、排除项、风险与有效期 |
| ContractCompiler | declared/observed/inferred → ContractSnapshot | 冲突、审批、接口与状态/副作用 |
| CoveragePlanner | scope+contract → ObligationSet+TestPlan | 冻结分母、可执行/可观察性 |
| RunnerBroker | TestExecutionPlan → Observations | 租户隔离、资源预算、原生执行 |
| Comparator | typed observations+policy → Differences | 不吞差异，不随意排序/容差 |
| FormalBroker | trusted challenge → VerifiedProofResult | 命题、假设、公理、源码绑定 |
| EvidenceService | observations+attestations → Evidence DAG | 内容寻址、provenance、失效传播 |
| EthenPort | sealed bundle → AuditDecision | 独立发现、挑战、利益冲突、人工确认 |
| K8Gate/K8Signer | policy+verified facts → scoped attestation | 确定性决策、授权签署、撤销 |

跨模块只用本包版本化 DTO；具体模型SDK、SQLGlot AST、Lean内存对象、JUnit类不可泄漏进入统一领域接口。

## 4. 准确率的产品目标

将“让更多项目通过”改成：降低缺陷项目获PASS的风险，同时提升在声明支持范围内的真实交付能力。
有资格缩小范围但必须明确新证书范围、原始排除风险、审批身份；不允许把有问题的接口悄悄从分母移除。

业务竞争力积累在经过反例检验的规则、Golden Route、回归资产、来源清晰的缺陷语料、能复核的证据与客户验收流程，不在 skill 数量或虚构的99.99%。

## 5. 资产而非仅接口

接口边界包含 HTTP、GraphQL、gRPC、事件、WebSocket、CLI、SDK、DB routine、文件、任务、UI流程与设备协议。
HTTP 100%不能覆盖 scheduler、数据迁移、事件重试、权限路径或UI。
不把所有内部函数都做公开接口；内部关键行为通过可信测试适配器或组件测试验证，测试端点不得进入生产镜像。

## 6. 需求到证据双向可追溯

`Requirement → Claim → Interface/State/Effect → Test obligation → Test case → Execution → Observation → Evidence → Audit finding → Decision → Attestation`。
保留 defeater（反证）、assumption、scope exclusion、waiver。发现冲突时，不以最新/最多票为真，交给明确的规范责任人。

## 7. 默认安全与经济性

每账号最多3个top-level run；子任务受同一信号量、CPU/内存/IO/token/费用预算控制。单位采用机器 wall-clock 秒和实际usage，不用人工人天冒充执行时间。
预算耗尽是 PAUSED_BUDGET/INCONCLUSIVE，绝不是缩小回归集后PASS。账户价格策略与验证门槛分离，不提供“付费放宽认证”。

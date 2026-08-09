# ELMOS项目整体缺口与产品级优化报告

## 一、总体判断

按目前已经完成的Batch、Skills、测试体系和认证门禁来看，项目已经具备：

```text
完整的产品能力地图
+ 较完整的工程实施规范
+ Codex可执行的Skill体系
+ 测试与认证框架
+ 企业级安全、部署、运营和商业设计
```

但需要区分四个成熟度层次：

| 层次           | 当前判断                                 |
| ------------ | ------------------------------------ |
| 产品功能覆盖       | 很高，主要能力基本完整                          |
| Skill设计和测试设计 | 很高，已经接近闭环                            |
| 跨Batch逻辑一致性  | 中高，仍存在重复和割裂                          |
| 真实代码实现       | 取决于实际仓库实施进度                          |
| 真实生产验证       | 必须通过客户仓库、真实Runner和真实环境证明             |
| 可规模销售和交付     | 仍需Reference Product和Design Partner验证 |

当前最大的风险不是“缺功能”，而是：

> 功能很多，但缺少一个统一的产品内核，把所有Batch连接成一条真正可运行的业务主链。

---

# 二、最重要的结构性缺口

## 1. 缺少统一的产品元模型

目前不同Batch分别定义了：

```text
Route Pack
Framework Pack
Database Pack
Client Pack
Cloud Pack
Verification Pack
Deployment Pack
Marketplace Pack
Knowledge Pack
Agent Pack
Certification Pack
```

这些Pack各自合理，但如果没有统一父模型，长期会出现：

* 状态名称不一致；
* Owner定义不一致；
* Evidence格式不一致；
* 版本策略不一致；
* 安全Policy重复；
* 每个Pack单独实现生命周期；
* UI无法统一展示；
* API和数据库表快速膨胀。

建议建立统一的 `CapabilityPackage`：

```yaml
capability_package:
  package_id: string
  package_type: language-route | framework | database | client | cloud | verification | extension
  version: semver

  lifecycle:
    status: draft | experimental | limited | certified | deprecated | retired | revoked

  ownership:
    product_owner: string
    engineering_owner: string
    security_owner: string
    maintenance_owner: string

  compatibility:
    product_versions: []
    protocol_versions: []
    runtime_versions: []

  contracts: []
  dependencies: []
  policies: []
  evidence: []
  certification: {}
  economics: {}
```

所有Batch的Pack都作为它的具体类型。

这是当前最优先的架构收敛工作。

---

## 2. 缺少统一的跨Batch依赖图

目前Skills数量庞大，但应明确哪些是：

```text
前置能力
强依赖
可选依赖
运行时依赖
认证依赖
商业依赖
```

例如：

```text
Batch 25行为等价
依赖：
Batch 21真实仓库切片
Batch 22语义强化
Batch 23框架迁移
Batch 24真实Build和Test
```

Batch 45成熟认证又依赖Batch 21–44的部分证据。

需要建立机器可读的 `Capability Dependency Graph`：

```yaml
dependency:
  consumer: b45-semantic-behavior-certification
  provider: b25-behavioral-equivalence-gate
  dependency_type: certification
  required_status: certified
  optional: false
  evidence_freshness: P90D
```

必须支持：

* 循环依赖检测；
* 缺失前置能力检测；
* 认证过期传播；
* Provider撤销传播；
* 版本兼容解析；
* Upgrade影响分析；
* UI依赖可视化。

否则项目容易出现“各Batch单独通过，但组合无法运行”。

---

## 3. 缺少统一Workflow Runtime

当前很多Batch都包含自己的：

```text
Orchestrator
State Machine
Retry
Approval
Rollback
Human Takeover
Evidence
```

如果每个Batch独立实现，会产生几十套状态机和任务系统。

应建立一个统一的Durable Workflow内核：

```text
Workflow Definition
→ Step
→ Dependency
→ Lease
→ Retry
→ Timeout
→ Checkpoint
→ Compensation
→ Human Task
→ Approval
→ Evidence
→ Budget
→ Cancellation
```

所有迁移、认证、升级、发布和退役流程都运行在同一Workflow Runtime上。

核心对象建议统一为：

```yaml
workflow_run:
  workflow_id: string
  definition_version: string
  tenant_id: string
  project_id: string
  state: string
  current_steps: []
  checkpoints: []
  approvals: []
  budgets: {}
  evidence_refs: []
```

重点要求：

* Workflow定义版本化；
* 长任务升级后可恢复；
* Step幂等；
* 副作用必须有Idempotency Key；
* 支持人工暂停、恢复和接管；
* 支持补偿而不是只支持技术回滚；
* 支持离线Runner断连恢复。

---

## 4. 缺少统一Evidence Graph

现在各Batch已有大量Evidence设计，但需要连接成一张全局图。

建议统一链路：

```text
Source Repository
→ Source Commit
→ Source Symbol
→ PSP
→ UIR
→ Framework Contract
→ Semantic Decision
→ Recipe
→ Generated Symbol
→ Diagnostic
→ Patch
→ Test
→ Behavior Scenario
→ Security Finding
→ Approval
→ Release
→ Production Deployment
→ Customer Acceptance
```

每个节点必须有：

```text
Stable ID
Digest
Producer
Timestamp
Tenant
Project
Version
Trust Level
Retention
Signature
```

这样平台才能回答：

* 目标代码为什么这样生成？
* 使用了哪个语义规则？
* 哪个Agent或模型参与？
* 哪个人批准？
* 哪些测试证明正确？
* 哪个生产版本正在运行？
* 当前证据是否过期？
* 规则被撤销后哪些Release受影响？

Evidence Graph是迁移产品可信性和差异化的重要基础。

---

## 5. 缺少统一Policy Engine

当前安全、模型、Runner、Marketplace和Agent都有Policy，但应统一为一个决策内核。

统一Policy输入：

```text
Actor
Tenant
Project
Resource
Action
Data Classification
Environment
Risk Tier
Model
Tool
Budget
Location
```

统一输出：

```yaml
policy_decision:
  effect: allow | deny
  reasons: []
  obligations: []
  required_approvals: []
  redactions: []
  limits: {}
  policy_version: string
```

必须统一治理：

* Source代码能否出Runner；
* Agent能否调用工具；
* 模型能看到多少Context；
* Extension能否访问网络；
* Support人员能否进入客户环境；
* 哪些Patch必须人工审批；
* 数据能否跨区域；
* 哪个操作需要双人批准；
* 预算超限后如何降级。

任何Agent、Runner、SDK或管理员都不能绕过Policy Engine。

---

# 三、产品主链逻辑需要进一步收敛

## 6. 应建立一条唯一的产品级主状态机

虽然各Batch都有局部状态机，但客户项目需要一个统一生命周期：

```text
discovered
→ qualified
→ assessed
→ scoped
→ baselined
→ planned
→ transforming
→ build-green
→ behavior-verified
→ production-ready
→ canary
→ cutover
→ hypercare
→ stabilized
→ legacy-retired
→ accepted
```

异常分支：

```text
blocked
needs-human
security-stopped
budget-stopped
rolled-back
cancelled
```

每个状态必须定义：

* 进入条件；
* 必需Evidence；
* 可执行操作；
* 退出条件；
* 责任人；
* 是否允许回退；
* 是否允许Waiver；
* SLA计时方式。

目前各Batch的State Machine应该映射到这个全局状态机，而不是平行存在。

---

## 7. 需要明确“产品内核”和“扩展能力”的边界

现在项目覆盖极广，但不应把每个Skill都实现成核心服务。

建议产品内核只包含：

```text
Tenant / Identity
Project
Repository
Workflow
Artifact
Evidence
Policy
Runner
Migration
Validation
Certification
Release
```

其他能力作为Pack或Extension存在：

```text
Language Adapter
Framework Adapter
Database Adapter
Cloud Provider
Comparator
Recipe
Vertical Pack
Marketplace Extension
Agent Specialist
```

原则：

```text
Core稳定
Pack快速迭代
Extension受控扩展
```

否则平台核心会变成不可升级的巨型系统。

---

## 8. 必须建立一条Reference Route

目前产品覆盖多语言、多框架、多数据库、多云，但真正实施时必须选择一条首要路线。

建议：

```text
Java 17/21 + Spring Boot
→ C# + ASP.NET Core + EF Core
```

Reference Route应完整覆盖：

```text
Repository Intake
→ Semantic Model
→ PSP/UIR
→ Framework Contract
→ Code Generation
→ Build
→ Test Migration
→ Repair
→ Behavior Verification
→ Database Migration
→ PR
→ Private Runner
→ Canary
→ Cutover
→ Hypercare
```

建议真实仓库标准：

```text
10万–50万行
5–20个模块
REST
Security
Database
Transaction
Message
Cache
Scheduler
Third-party API
CI/CD
Container/Kubernetes
```

没有一条完整Reference Route，整个项目仍容易停留在横向能力设计层。

---

# 四、Skill体系本身还可以优化

## 9. Skills数量已经过大，需要分层治理

目前累计Skills已经达到数百个，Codex使用时容易出现：

* 触发冲突；
* 同义Skill重复；
* 上下文过长；
* 不知道先调用哪个Skill；
* 多个Orchestrator重复；
* Skill版本失控。

建议分为四层：

### L0：Meta Skills

```text
Capability Resolver
Workflow Planner
Policy Resolver
Evidence Validator
Certification Resolver
```

### L1：Domain Orchestrator

```text
Language Migration
Framework Migration
Database Migration
Cloud Migration
Production Cutover
Marketplace
```

### L2：Implementation Skills

例如：

```text
Nullability Mapping
Transaction Migration
Terraform Module Migration
PR Bot
```

### L3：Test and Operations Skills

```text
Contract Test
Chaos Test
Upgrade Test
Incident Response
```

Codex先调用L0决定L1，再由L1选择L2/L3，而不是直接在数百个Skill中平面搜索。

---

## 10. 建立Skill Registry和Skill Compiler

需要统一记录：

```yaml
skill:
  skill_id: string
  version: string
  layer: meta | orchestrator | implementation | test | operations
  owner: string
  triggers: []
  prerequisites: []
  allowed_tools: []
  required_inputs: []
  outputs: []
  risks: []
  evidence: []
  tests: []
  deprecated_by: string
```

Skill Compiler应检查：

* Front Matter；
* 重复名称；
* 触发冲突；
* 缺失依赖；
* 循环依赖；
* 未授权工具；
* 无验证步骤；
* 无停止条件；
* 输出Schema不匹配；
* 已弃用Skill仍被引用。

这是把“很多Prompt文件”升级为“可治理Skill OS”的关键。

---

## 11. 合并重复Skills

目前跨Batch可能重复出现：

```text
Orchestrator
Evidence Manager
Certification Gate
Version Manager
Policy Manager
Rollback Manager
```

建议采取：

```text
共享基础Skill
+ 领域参数Profile
```

例如不要每个Batch单独实现一套Evidence校验，可改为：

```text
global-evidence-verifier
+ framework-evidence-profile
+ database-evidence-profile
+ cloud-evidence-profile
```

这样可以降低：

* 维护成本；
* 规则不一致；
* 测试重复；
* 安全漏洞；
* 版本漂移。

预计可将实际需要长期维护的Skill数量减少20%–35%。

---

# 五、测试体系的进一步优化

## 12. 当前用例数量很多，但必须增加测试层次结构

建议统一成：

```text
L1 Schema/Contract Test
L2 Component Test
L3 Integration Test
L4 End-to-End Test
L5 Production-like Test
L6 Customer Acceptance Test
L7 Continuous Certification
```

当前机器可读测试用例主要用于覆盖能力，但需要明确：

* 哪些只能Mock；
* 哪些必须用真实编译器；
* 哪些必须用真实数据库；
* 哪些必须使用真实Cloud Sandbox；
* 哪些必须在Air-gap执行；
* 哪些必须由第三方完成；
* 哪些必须由客户签字。

---

## 13. 建立统一Benchmark Corpus

至少需要四类Corpus：

```text
Synthetic Semantic Corpus
Open-source Representative Corpus
Internal Holdout Corpus
Customer-private Corpus
```

并明确不可交叉污染：

```text
Development Corpus
不能进入Holdout

Customer A Corpus
不能训练Customer B规则

目标输出
不能自动更新Golden
```

Benchmark维度包括：

* Build Green；
  -Behavior Pass；
  -Source Map覆盖；
  -人工修改量；
  -迁移工时；
  -Compatibility Runtime比例；
  -性能；
  -成本；
  -目标代码可维护性。

---

## 14. 增加Maintainability Gate

目前正确性和生产门禁很强，但还要防止生成“能运行但难维护”的代码。

建议独立设置：

```text
Maintainability Green
```

指标：

```text
Cyclomatic Complexity
Duplication
Target Idiomaticity
Dependency Count
Compatibility Runtime Ratio
Architecture Rule Violation
Testability
Documentation Coverage
Ownership Coverage
Technical Debt
```

最终产品门禁应是：

```text
Build Green
+ Behavior Green
+ Security Green
+ Production Green
+ Maintainability Green
```

---

# 六、产品体验缺口

## 15. 需要统一Product Information Architecture

功能多，但客户不应看到Batch和Skill。

客户产品界面应围绕任务：

```text
Assess
Plan
Migrate
Validate
Release
Operate
Retire
```

推荐一级导航：

```text
Portfolio
Projects
Migration Studio
Validation
Releases
Runners
Evidence
Marketplace
Operations
Administration
```

Batch只是内部实现模型，不能成为客户的主要产品导航。

---

## 16. 增加Migration Design Studio

架构师需要可视化设计迁移，而不只是运行自动化。

应展示：

```text
Source Architecture
Target Architecture
Module Mapping
API Mapping
Database Mapping
Dependency Graph
Migration Waves
Risk Heatmap
Estimated Cost
Cutover Plan
```

关键能力：

* 拖拽调整模块边界；
  -选择保留、迁移、重写或退役；
  -查看路线支持状态；
  -查看人工工作估算；
  -预览迁移Wave；
  -比较不同Target方案；
  -生成决策记录。

---

## 17. 加强Customer Handoff

迁移结束应自动生成：

```text
Target Architecture
Repository Guide
Local Development Guide
Deployment Guide
Runbook
API Documentation
Data Model
Security Model
Known Differences
Compatibility Runtime说明
Technical Debt Register
Upgrade Plan
Support Boundary
```

并进行目标团队接管测试：

* 新团队能否Build；
  -能否本地运行；
  -能否修改一个功能；
  -能否发布；
  -能否处理一次故障；
  -能否升级依赖。

迁移成功不能只定义为生产上线，还要定义为目标团队能够独立维护。

---

# 七、真实产品实现的关键缺口

## 18. 当前必须完成Control Plane最小内核

建议初期采用模块化单体，而不是马上拆成几十个微服务：

```text
Control Plane Modular Monolith
├── Identity/Tenant
├── Project
├── Repository
├── Workflow
├── Migration
├── Artifact
├── Evidence
├── Policy
├── Runner Control
├── Validation
└── Certification
```

基础设施：

```text
PostgreSQL
Object Storage
Durable Workflow
Private Runner
Message Broker（必要时）
```

只有明确出现团队、性能或安全边界后再拆服务。

---

## 19. Private Runner应优先于高级Agent

平台能否处理客户真实代码，核心取决于Runner，不是Agent数量。

Runner必须先完成：

```text
Secure Enrollment
Attestation
Short-lived Identity
Job Lease
Ephemeral Workspace
Sandbox
Network Egress Control
Secret Broker
Build/Test
Artifact Signing
Evidence Upload
Cleanup
```

在Runner不成熟前，Agent能力只能用于低风险分析和建议。

---

## 20. 确定性转换优先于Agent修复

推荐执行顺序：

```text
Static Rule
→ Certified Recipe
→ Compatibility Runtime
→ Bounded Agent Patch
→ Human Review
→ Block
```

Agent不应：

* 自己修改Policy；
  -自己扩大Context；
  -修改Golden；
  -删除测试；
  -直接批准自己的Patch；
  -在未知语义下继续生成；
  -绕过Compatibility Budget。

这是产品长期可信度的关键。

---

# 八、商业和交付层优化

## 21. 产品Edition需要减少复杂度

虽然已经设计很多Edition，实际早期建议只保留：

```text
SaaS
Enterprise Private Runner
Self-hosted / Air-gap
```

过早同时维护Dedicated、VPC、Sovereign、Edge和多Region组合，会极大提高升级测试矩阵。

Edition扩展应基于真实订单，而不是能力设计完整度。

---

## 22. 建立标准化产品套餐

建议形成：

```text
Assessment
POC
Migration Factory
Enterprise Platform
Managed Migration
```

每个套餐明确：

* 输入；
  -输出；
  -范围；
  -支持路线；
  -自动化率；
  -人工服务；
  -验收标准；
  -交付周期；
  -价格模型；
  -客户责任；
  -不包含内容。

---

## 23. 统一客户成功指标

不应使用代码行数作为核心成果。

建议核心指标：

```text
Verified Migrated Workload
```

定义：

```text
Build Green
+ P0 Test Pass
+ P0 Behavior Pass
+ Security Pass
+ Maintainability Pass
+ Customer Acceptance
```

辅助指标：

* Time to First Verified Workload；
* Manual Hours per Workload；
* Cost per Verified Workload；
* Production Regression；
* Rollback率；
* Customer Handoff Pass Rate；
* Legacy Retirement Rate。

---

# 九、建议暂停或延后实现的部分

以下能力设计可以保留，但不宜近期全面实现：

```text
十二条语言双向迁移路线
完整Marketplace商业生态
复杂多Agent自治
所有Cloud Provider组合
全球Active/Active
完整形式化验证套件
所有行业Vertical Pack
```

原因不是它们没价值，而是它们会分散Reference Route落地。

当前最重要的不是“功能广度再提升20%”，而是：

```text
核心路线真实成功率提升
客户上线成功
人工工作下降
证据可信
目标代码可维护
交付成本可控
```

---

# 十、推荐的整体优化优先级

## P0：产品逻辑收敛

1. 统一Capability Package元模型；
2. 统一全局项目状态机；
3. 统一Workflow Runtime；
4. 统一Policy Engine；
5. 统一Evidence Graph；
6. 建立跨Batch依赖图；
7. 建立Skill Registry和Compiler；
8. 合并重复基础Skills。

## P1：Reference Product落地

1. 完成Java/Spring到C#/ASP.NET Reference Route；
2. 完成Control Plane最小内核；
3. 完成Private Runner；
4. 完成真实Build/Test/Behavior链；
5. 完成IDE/CLI/PR基础体验；
6. 运行两个真实Design Partner仓库。

## P2：生产和接管

1. Canary和Rollback；
2. 数据迁移和核对；
3. Observability与SLO；
4. 目标代码Maintainability Gate；
5. Customer Handoff；
6. Self-hosted和Air-gap升级。

## P3：规模和生态

1. 多仓和百万行；
2. 第二条语言路线；
3. SDK/Marketplace；
4. 知识飞轮；
5. 高级Agent；
6. 行业Pack。

---

# 十一、最终产品架构建议

```text
Customer Experience
├── Portfolio
├── Migration Studio
├── Validation
├── Release
├── Operations
└── Marketplace

Control Plane Kernel
├── Tenant / Identity
├── Project / Repository
├── Workflow Runtime
├── Policy Engine
├── Capability Registry
├── Evidence Graph
├── Certification
└── Economics

Execution Plane
├── Private Runner
├── Build/Test Workers
├── Migration Engines
├── Validation Engines
└── Agent Workers

Extension Layer
├── Language Packs
├── Framework Packs
├── Database Packs
├── Cloud Packs
├── Vertical Packs
└── Marketplace Extensions
```

---

# 十二、最终结论

当前项目已经具备非常完整的能力设计，但仍有三类关键缺口：

```text
第一类：横向收敛缺口
Pack、状态、Workflow、Policy、Evidence和Skill仍需统一。

第二类：真实实现缺口
需要完成Control Plane、Private Runner、Reference Route和验证实验室。

第三类：产品证明缺口
需要真实客户仓库、生产Canary、目标团队接管和可持续SLA证明。
```

接下来不应继续扩展大量新功能，而应进入：

```text
收敛
→ 实现
→ 集成
→ 真实验证
→ 客户上线
→ 规模复制
```

阶段。

当以下五件事完成后，项目才真正从“产品级Skill OS”升级为“成熟企业软件产品”：

```text
统一产品内核
一条完整Reference Route
安全Private Runner
两家真实客户生产验证
可重复且盈利的交付模型
```

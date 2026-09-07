# Batch 16：Target Architecture Search 与 Migration Planning

## 总体目标

从 Source 真实架构和硬约束出发，系统搜索语言、Framework、数据、消息和部署组合，输出 Pareto 候选、ADRs、Target Blueprint 与可执行迁移 DAG。

## 建议仓库结构

```text
source-architecture/
architecture-ir/
target-search-space/
architecture-search/
migration-strategy/
migration-planning/
architecture-evaluation/
architecture-decisions/
target-blueprint/
```

## 1. Source Architecture Recovery

- Repository/Build/Runtime/Deployable/Domain/Feature/Journey/Service/Data/Message/Native/Provider/Operations Topology
- Static、Dynamic、Data、Effect、Deployment、Release Graphs
- Coupling、Ownership、Hidden Architecture Detection
## 2. Constraint Recovery

- Business Continuity、RPO/RTO、Performance、Availability、Consistency、Security、Privacy、Safety
- Technology、Deployment、Network、Native、License、Team、Budget、Certification、Reversibility
## 3. Target Search Space

- 10 Languages、Frameworks、Databases、Messaging、Cache、Search、Object、Deployment、Repository Models
- Compatibility/Incompatibility/Implication/Exclusion Rules
- Monolith、Microservices、Event-driven、Polyglot、Strangler Templates
## 4. Multi-Objective Search

- Hard Floors、Weighted/Lexicographic/Pareto/Robust Objectives
- SMT/Constraint/Integer/Evolutionary/Bayesian/Beam/Monte-Carlo Search
- Prototype、Simulation、Sensitivity、Worst-case
## 5. Migration Strategy

- Retain、Rehost、Replatform、Refactor、Rewrite、Replace、Wrap、Extract、Merge、Split、Strangle、Retire
- Service Extraction、Data Ownership、Strangler Route/Data/Message/Fallback/Exit
## 6. Executable Planning

- Migration Boundaries、Waves、Dependency DAG、Critical Path、Resources、Risks、Cost、Team Fit、Certification Reachability
- ADRs、Target Blueprint、Dynamic Replanning

## 认证体系：AP1–AP5 Architecture Planning

AP1–AP5 Architecture Planning 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Source Architecture Manifest
- Constraint Registry
- Architecture IR
- Candidate Portfolio
- Prototype/Simulation Reports
- Pareto Frontier
- Risk/TCO/Team/Certification Plans
- ADRs
- Target Blueprint
- Executable Migration Plan

## 硬性原则

- 代码仓库结构不等于真实架构
- 微服务不是现代化同义词
- 最优架构只在明确目标和假设下成立
- 硬安全约束不能被总分抵消
- Prototype 和模拟不能替代生产证据
- Migration Wave 必须交付可验证价值

## Definition of Done

```yaml
source_recovery: pass
hard_constraints: pass
architecture_ir: pass
candidate_space: pass
multi_objective_search: pass
prototypes: pass
risk_cost_team: pass
adrs: pass
target_blueprint: pass
executable_task_dag: pass
unowned_critical_components: 0
ap1_to_ap5: pass
```

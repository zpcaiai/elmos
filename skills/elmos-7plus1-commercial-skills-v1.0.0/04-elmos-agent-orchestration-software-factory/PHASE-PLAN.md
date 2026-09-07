# P04 Phase 实施计划

**所属总体阶段：** Phase 2（商业软件工厂）

## 总体依赖顺序

- 先完成合同与基线，再做 vertical slice。
- 先通过最小证据闭环，再扩语言/框架/模型矩阵。
- 每个阶段都保持可回滚、可观测、可计量。
- Phase D 之前不得对外宣称商业 GA。

## 1. A. Contract & Baseline

**目标：** 冻结范围、Schema、接口、事件、状态机、Benchmark 与威胁模型。

- [ ] 建立 public contract 和错误码
- [ ] 建立最小 golden fixtures
- [ ] 建立 source pins 与兼容矩阵
- [ ] 完成安全/数据分类评审

**退出门：**

- [ ] 与本阶段变更相关的接口、事件、数据和权限合同已冻结并测试。
- [ ] 定向 Benchmark 与影响闭包回归通过。
- [ ] P05 GateDecision 为 pass，或有明确 blocker 而非假完成。
- [ ] 运行手册、回滚、指标、告警和 owner 已登记。
## 2. B. Vertical Slice MVP

**目标：** 完成一个真实场景的端到端闭环，而非铺开所有技术矩阵。

- [ ] 实现最小核心组件
- [ ] 接入 native runtime 与一个外部 Adapter
- [ ] 运行 end-to-end scenario
- [ ] 输出 P05 evidence bundle

**退出门：**

- [ ] 与本阶段变更相关的接口、事件、数据和权限合同已冻结并测试。
- [ ] 定向 Benchmark 与影响闭包回归通过。
- [ ] P05 GateDecision 为 pass，或有明确 blocker 而非假完成。
- [ ] 运行手册、回滚、指标、告警和 owner 已登记。
## 3. C. Reliability & Scale

**目标：** 加入恢复、并发、多租户、性能、故障注入和全面回归。

- [ ] 实现幂等、重试、回滚和 replay
- [ ] 加入分区/缓存/并发控制
- [ ] 运行 security/performance/resilience tests
- [ ] 建立可观测和运营 Runbook

**退出门：**

- [ ] 与本阶段变更相关的接口、事件、数据和权限合同已冻结并测试。
- [ ] 定向 Benchmark 与影响闭包回归通过。
- [ ] P05 GateDecision 为 pass，或有明确 blocker 而非假完成。
- [ ] 运行手册、回滚、指标、告警和 owner 已登记。
## 4. D. Commercial GA

**目标：** 完成计费、SLA、客户管理、迁移、升级、审计和认证。

- [ ] 完成 enterprise RBAC/SSO/audit
- [ ] 完成 canary/rollback/DR
- [ ] 完成支持与客户可见报告
- [ ] 通过选定 E1–E5 Gate

**退出门：**

- [ ] 与本阶段变更相关的接口、事件、数据和权限合同已冻结并测试。
- [ ] 定向 Benchmark 与影响闭包回归通过。
- [ ] P05 GateDecision 为 pass，或有明确 blocker 而非假完成。
- [ ] 运行手册、回滚、指标、告警和 owner 已登记。


## 跨包阻塞条件

- P00 合同、版本或配置无有效 revision。
- P01 readiness/permission/sandbox/adapter conformance 不通过。
- P02 对关键区域存在 unknown high-risk blind spot。
- P05 required evidence 缺失或 Gate fail。
- P06 无符合隐私、能力和预算的 eligible route。

## 推荐首个 Vertical Slice

选择一个 20–50K LOC、含 API/DB/MQ/cache/auth/cron 的 Spring Boot + Vue 样例，目标转换到 Go/Rust + React；要求 source/target 双运行、Capability Ledger、差分测试、自动修复和 Evidence Bundle 全部闭环。

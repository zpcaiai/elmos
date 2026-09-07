# Batch Index — B00–B53

Each batch is independently reviewable. A batch is DONE only when its requirements, tests, runtime evidence and completion report are present.

| Batch | Title | Owner skill | Depends on | Requirements |
|---|---|---|---|---|
| B00 | 基线审计与状态模型 | `elmos-billing-orchestrator` | — | EB-01-001, EB-01-002, EB-01-003 |
| B01 | 依赖编排与证据链 | `elmos-billing-orchestrator` | B00 | EB-01-004, EB-01-005, EB-01-006 |
| B02 | 生产认证与发布决策 | `elmos-billing-orchestrator` | B01 | EB-01-007, EB-01-008, EB-01-009, EB-01-010 |
| B03 | 商业模型与决策表 | `elmos-pricing-product-model` | B02 | EB-02-001, EB-02-002, EB-02-003 |
| B04 | 价格簿和费率契约 | `elmos-pricing-product-model` | B03 | EB-02-004, EB-02-005, EB-02-006 |
| B05 | 审批、实验与版本治理 | `elmos-pricing-product-model` | B04 | EB-02-007, EB-02-008, EB-02-009, EB-02-010 |
| B06 | 目录与权益建模 | `elmos-plan-catalog-entitlements` | B05 | EB-03-001, EB-03-002, EB-03-003 |
| B07 | 订阅席位与授权服务 | `elmos-plan-catalog-entitlements` | B06 | EB-03-004, EB-03-005, EB-03-006 |
| B08 | 升级降级和竞争验证 | `elmos-plan-catalog-entitlements` | B07 | EB-03-007, EB-03-008, EB-03-009, EB-03-010 |
| B09 | 账本科目与数据库约束 | `elmos-credit-wallet-ledger` | B08 | EB-04-001, EB-04-002, EB-04-003 |
| B10 | 预留捕获释放和投影 | `elmos-credit-wallet-ledger` | B09 | EB-04-004, EB-04-005, EB-04-006 |
| B11 | 并发重放与日终对账 | `elmos-credit-wallet-ledger` | B10 | EB-04-007, EB-04-008, EB-04-009, EB-04-010 |
| B12 | 事件契约与采集适配 | `elmos-usage-metering` | B11 | EB-05-001, EB-05-002, EB-05-003 |
| B13 | 评级聚合和封账 | `elmos-usage-metering` | B12 | EB-05-004, EB-05-005, EB-05-006 |
| B14 | 供应商对账与异常恢复 | `elmos-usage-metering` | B13 | EB-05-007, EB-05-008, EB-05-009, EB-05-010 |
| B15 | 特征与历史样本基线 | `elmos-task-cost-estimation` | B14 | EB-06-001, EB-06-002, EB-06-003 |
| B16 | 区间成本和 ETA 引擎 | `elmos-task-cost-estimation` | B15 | EB-06-004, EB-06-005, EB-06-006 |
| B17 | 校准、漂移与回退 | `elmos-task-cost-estimation` | B16 | EB-06-007, EB-06-008, EB-06-009, EB-06-010 |
| B18 | 报价卡与授权模型 | `elmos-quote-budget-guard` | B17 | EB-07-001, EB-07-002, EB-07-003 |
| B19 | 运行中预算硬门禁 | `elmos-quote-budget-guard` | B18 | EB-07-004, EB-07-005, EB-07-006 |
| B20 | 结算、恢复与误差反馈 | `elmos-quote-budget-guard` | B19 | EB-07-007, EB-07-008, EB-07-009, EB-07-010 |
| B21 | 项目范围与合同状态机 | `elmos-project-pricing-contracts` | B20 | EB-08-001, EB-08-002, EB-08-003 |
| B22 | 里程碑、变更单与执行控制 | `elmos-project-pricing-contracts` | B21 | EB-08-004, EB-08-005, EB-08-006 |
| B23 | 验收、结算和毛利复盘 | `elmos-project-pricing-contracts` | B22 | EB-08-007, EB-08-008, EB-08-009, EB-08-010 |
| B24 | 订阅周期与按比例计费 | `elmos-subscription-invoicing` | B23 | EB-09-001, EB-09-002, EB-09-003 |
| B25 | 发票、税费和财务快照 | `elmos-subscription-invoicing` | B24 | EB-09-004, EB-09-005, EB-09-006 |
| B26 | 续费、贷项和账期边界 | `elmos-subscription-invoicing` | B25 | EB-09-007, EB-09-008, EB-09-009, EB-09-010 |
| B27 | 支付抽象与安全接入 | `elmos-payments-reconciliation` | B26 | EB-10-001, EB-10-002, EB-10-003 |
| B28 | Webhook 幂等和业务入账 | `elmos-payments-reconciliation` | B27 | EB-10-004, EB-10-005, EB-10-006 |
| B29 | 结算文件与三方对账 | `elmos-payments-reconciliation` | B28 | EB-10-007, EB-10-008, EB-10-009, EB-10-010 |
| B30 | 责任分类与退款策略 | `elmos-refunds-disputes` | B29 | EB-11-001, EB-11-002, EB-11-003 |
| B31 | 反向账务、退款 Saga 与争议 | `elmos-refunds-disputes` | B30 | EB-11-004, EB-11-005, EB-11-006 |
| B32 | 审批、对账和失败补偿 | `elmos-refunds-disputes` | B31 | EB-11-007, EB-11-008, EB-11-009, EB-11-010 |
| B33 | 合同、承诺用量和信用模型 | `elmos-enterprise-byok` | B32 | EB-12-001, EB-12-002, EB-12-003 |
| B34 | BYOK 与私有部署计量 | `elmos-enterprise-byok` | B33 | EB-12-004, EB-12-005, EB-12-006 |
| B35 | 成本中心、SLA 和 true-up | `elmos-enterprise-byok` | B34 | EB-12-007, EB-12-008, EB-12-009, EB-12-010 |
| B36 | 财务事实与指标口径 | `elmos-cost-margin-analytics` | B35 | EB-13-001, EB-13-002, EB-13-003 |
| B37 | 成本分摊、毛利和报价误差 | `elmos-cost-margin-analytics` | B36 | EB-13-004, EB-13-005, EB-13-006 |
| B38 | 告警、优化建议与封账 | `elmos-cost-margin-analytics` | B37 | EB-13-007, EB-13-008, EB-13-009, EB-13-010 |
| B39 | 客户报价、钱包和账单体验 | `elmos-billing-admin-ux` | B38 | EB-14-001, EB-14-002, EB-14-003 |
| B40 | 项目、团队和管理员工作台 | `elmos-billing-admin-ux` | B39 | EB-14-004, EB-14-005, EB-14-006 |
| B41 | E2E、无障碍和故障体验 | `elmos-billing-admin-ux` | B40 | EB-14-007, EB-14-008, EB-14-009, EB-14-010 |
| B42 | 威胁模型、租户隔离和权限 | `elmos-security-compliance` | B41 | EB-15-001, EB-15-002, EB-15-003 |
| B43 | 密钥、审计、防欺诈与隐私 | `elmos-security-compliance` | B42 | EB-15-004, EB-15-005, EB-15-006 |
| B44 | 红队、合规证据和发布门禁 | `elmos-security-compliance` | B43 | EB-15-007, EB-15-008, EB-15-009, EB-15-010 |
| B45 | 可观测性、SLO 和异常队列 | `elmos-billing-observability-ops` | B44 | EB-16-001, EB-16-002, EB-16-003 |
| B46 | Kill switch、重放与对账运行手册 | `elmos-billing-observability-ops` | B45 | EB-16-004, EB-16-005, EB-16-006 |
| B47 | 灾备演练和事故治理 | `elmos-billing-observability-ops` | B46 | EB-16-007, EB-16-008, EB-16-009, EB-16-010 |
| B48 | 需求驱动测试与属性不变量 | `elmos-billing-testing-certification` | B47 | EB-17-001, EB-17-002, EB-17-003 |
| B49 | 集成、并发、混沌和安全 | `elmos-billing-testing-certification` | B48 | EB-17-004, EB-17-005, EB-17-006 |
| B50 | 影子差分与 E1-E5 认证 | `elmos-billing-testing-certification` | B49 | EB-17-007, EB-17-008, EB-17-009, EB-17-010 |
| B51 | 旧数据审计、映射和 opening balance | `elmos-rollout-migration` | B50 | EB-18-001, EB-18-002, EB-18-003 |
| B52 | 影子、双写与波次金丝雀 | `elmos-rollout-migration` | B51 | EB-18-004, EB-18-005, EB-18-006 |
| B53 | 切换、回滚和稳定期退役 | `elmos-rollout-migration` | B52 | EB-18-007, EB-18-008, EB-18-009, EB-18-010 |

## Standard batch procedure

1. Read repository instructions and current implementation status.
2. Freeze the batch input and baseline commit.
3. Classify assigned requirements before editing.
4. Implement the smallest coherent vertical slice.
5. Run targeted, regression, invariant and failure tests.
6. Record source/symbol/test/runtime/commit evidence.
7. Update traceability and handoff state.
8. Do not begin dependent work if a P0 blocker remains.

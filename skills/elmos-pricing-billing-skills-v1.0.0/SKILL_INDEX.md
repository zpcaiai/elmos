# Skill Index

Use the narrowest applicable skill. Use `elmos-billing-orchestrator` for repository-wide planning, audit, sequencing, or final certification.

| # | Skill | Primary trigger | Depends on | Batches | Requirements |
|---:|---|---|---|---|---:|
| 1 | `elmos-billing-orchestrator` | 启动或继续完整收费系统建设 | — | B00, B01, B02 | 10 |
| 2 | `elmos-pricing-product-model` | 设计套餐、额度、项目包或企业合同 | elmos-billing-orchestrator | B03, B04, B05 | 10 |
| 3 | `elmos-plan-catalog-entitlements` | 新增或调整套餐权益 | elmos-pricing-product-model | B06, B07, B08 | 10 |
| 4 | `elmos-credit-wallet-ledger` | 实现充值额度钱包 | elmos-pricing-product-model | B09, B10, B11 | 10 |
| 5 | `elmos-usage-metering` | 接入模型或基础设施用量 | elmos-pricing-product-model, elmos-credit-wallet-ledger | B12, B13, B14 | 10 |
| 6 | `elmos-task-cost-estimation` | 扫描仓库后生成任务预估 | elmos-usage-metering | B15, B16, B17 | 10 |
| 7 | `elmos-quote-budget-guard` | 生成任务报价卡 | elmos-task-cost-estimation, elmos-credit-wallet-ledger | B18, B19, B20 | 10 |
| 8 | `elmos-project-pricing-contracts` | 完整项目生成或老系统翻新 | elmos-quote-budget-guard | B21, B22, B23 | 10 |
| 9 | `elmos-subscription-invoicing` | 创建或续费订阅 | elmos-plan-catalog-entitlements, elmos-credit-wallet-ledger | B24, B25, B26 | 10 |
| 10 | `elmos-payments-reconciliation` | 接入微信/支付宝/Stripe/PayPal 等支付渠道 | elmos-subscription-invoicing, elmos-credit-wallet-ledger | B27, B28, B29 | 10 |
| 11 | `elmos-refunds-disputes` | 任务失败后的退款判定 | elmos-payments-reconciliation, elmos-credit-wallet-ledger | B30, B31, B32 | 10 |
| 12 | `elmos-enterprise-byok` | 企业年度合同和承诺消费 | elmos-plan-catalog-entitlements, elmos-usage-metering, elmos-quote-budget-guard | B33, B34, B35 | 10 |
| 13 | `elmos-cost-margin-analytics` | 计算任务、项目、租户或模型毛利 | elmos-usage-metering, elmos-subscription-invoicing, elmos-payments-reconciliation, elmos-project-pricing-contracts | B36, B37, B38 | 10 |
| 14 | `elmos-billing-admin-ux` | 实现报价卡和费用进度条 | elmos-quote-budget-guard, elmos-subscription-invoicing, elmos-refunds-disputes, elmos-enterprise-byok | B39, B40, B41 | 10 |
| 15 | `elmos-security-compliance` | 设计账单安全架构 | elmos-credit-wallet-ledger, elmos-usage-metering, elmos-payments-reconciliation, elmos-enterprise-byok | B42, B43, B44 | 10 |
| 16 | `elmos-billing-observability-ops` | 建立计费监控和 SLO | elmos-credit-wallet-ledger, elmos-usage-metering, elmos-quote-budget-guard, elmos-payments-reconciliation | B45, B46, B47 | 10 |
| 17 | `elmos-billing-testing-certification` | 建立计费测试金字塔 | elmos-security-compliance, elmos-billing-observability-ops, elmos-cost-margin-analytics | B48, B49, B50 | 10 |
| 18 | `elmos-rollout-migration` | 上线新收费系统 | elmos-billing-testing-certification | B51, B52, B53 | 10 |

## Routing guide

- Full program, gap audit, evidence and release: `elmos-billing-orchestrator`
- Commercial choice and price books: `elmos-pricing-product-model`
- Plans, seats, concurrency and entitlements: `elmos-plan-catalog-entitlements`
- Any balance mutation or credit hold: `elmos-credit-wallet-ledger`
- Token/compute/test/storage measurement: `elmos-usage-metering`
- Cost and autonomous runtime prediction: `elmos-task-cost-estimation`
- Quote card and hard budget enforcement: `elmos-quote-budget-guard`
- Capped/fixed repository project: `elmos-project-pricing-contracts`
- Recurring billing and invoices: `elmos-subscription-invoicing`
- Payment providers and cash reconciliation: `elmos-payments-reconciliation`
- Refund, adjustment, chargeback or failed-task billing: `elmos-refunds-disputes`
- Enterprise contract, postpaid, BYOK or private deployment: `elmos-enterprise-byok`
- Unit economics and margin: `elmos-cost-margin-analytics`
- Customer/admin billing UI: `elmos-billing-admin-ux`
- Tenant isolation, audit, fraud and privacy: `elmos-security-compliance`
- Production monitoring, replay and disaster recovery: `elmos-billing-observability-ops`
- Test/evidence/certification: `elmos-billing-testing-certification`
- Legacy migration and canary rollout: `elmos-rollout-migration`

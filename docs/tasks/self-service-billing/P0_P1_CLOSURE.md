# P0 / P1 收口清单

## P0

| 项目 | 状态 | 验收点 |
|---|---|---|
| 单一人民币套餐目录 | `DONE` | Java/Web 共用同一 JSON 版本 |
| 组织身份与最小权限 | `DONE` | JWT + scope；缺配置 401 |
| 权威数据库计量 | `DONE_LOCAL` | V49、RLS、精确数值、追加账本 |
| 并发额度硬停止 | `DONE_LOCAL` | 行锁预留；并发只接受可用额度 |
| 任务生产者接入 | `DONE` | reserve/settle/release；Token receipt |
| 一次性免费体验 | `DONE_LOCAL` | 双唯一约束、到期、转付费 |
| 实时消耗进度 | `DONE` | consumed/reserved/remaining/usageBps |
| CNY Checkout/Webhook | `DONE_NOT_CONFIGURED` | 服务端价格、签名、幂等、对账 |
| Neon 严格迁移门禁 | `DONE_NOT_RUN` | 精确目标 + validate/migrate/validate |
| 客户免费体验入口 | `DONE_LOCAL` | 已验证身份、同源 BFF、幂等、一次性试用 |

## P1

| 项目 | 状态 | 验收点 |
|---|---|---|
| 历史与 CSV | `DONE` | 小时/日聚合、UTF-8 导出 |
| 用量预测 | `DONE` | 基于当前周期趋势，缺数据不伪造 |
| 阈值告警 | `DONE_IN_APP` | 50/80/95/100%，越界一次 |
| 邮件告警 | `PREPARED_NOT_CONFIGURED` | PENDING 意图；发送方仍关闭 |
| 订阅取消 | `DONE_NOT_CONFIGURED` | Stripe 先确认，再写本地状态 |
| 客户订阅自助管理 | `DONE_LOCAL` | 订阅摘要、两步取消、提供方引用不下发 |
| 支付对账运营 | `DONE_LOCAL` | admin 列表、结案、追加审计 |
| 健康、指标与手册 | `DONE` | readiness、Micrometer、Runbook |
| 数据库/安全负向测试 | `DONE_LOCAL` | 租户隔离、滥用、不可变事实 |
| 生产外部验收 | `NOT_RUN` | 需要真实 Neon/OIDC/Stripe/邮件 |

“DONE_LOCAL”只表示受控本地真实 PostgreSQL、Chromium 和代码路径通过，不代表生产部署。
付费按钮在目录为 `DRAFT` 或支付/税务/成本门禁未完成时保持禁用；这属于预期的失败关闭。

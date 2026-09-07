# 自助计费运行手册

## 健康与监控

`BillingDatabaseHealthIndicator` 检查当前目录版本和 V49 核心预留函数。数据库未配置时
计费 Controller 不创建；已配置但 Schema 缺失或连接失败时 readiness 为 DOWN。

Micrometer 指标：

| 指标 | 标签 | 告警建议 |
|---|---|---|
| `elmos.billing.usage.reservations` | `outcome=reserved|denied` | denied 比例突增 |
| `elmos.billing.checkout.requests` | `outcome` | provider_error > 0 |
| `elmos.billing.webhook.events` | `event_type`,`outcome` | reconciliation 持续增长 |
| `elmos.billing.api.errors` | `family` | database/provider 错误持续增长 |

生产环境应在内部监控网络采集指标，不向公网开放 Actuator metrics。

## 日常检查

1. readiness 为 UP，目录版本等于应用编译版本。
2. `payment_reconciliation_cases.status='OPEN'` 的最老年龄和总数。
3. `payment_provider_events.processing_status='RECONCILIATION_REQUIRED'` 是否有对应案件。
4. 过期 `RESERVED` 租约数量；不得长期占用额度。
5. `usage_events.reconciliation_status='PENDING'` 的年龄和 provider 分布。
6. 告警阈值投递与用户实时快照的事件水位。

## 支付对账

管理员用 `commercial:billing:admin`：

- `GET /commercial/v1/billing/reconciliation?status=OPEN`
- 核对 Stripe Dashboard、原始签名事件摘要、对象引用、金额/币种和本地订阅状态。
- 有充分外部证据后调用 `POST /commercial/v1/billing/reconciliation/resolve`，
  提交 `RESOLVED` 或 `REJECTED` 以及不可猜测的外部证据引用。
- 同一幂等键只能对同一案件、同一决定和同一引用重放。

管理员结案不会修改原始 provider event。

## 用量争议

1. 从 CSV/历史接口定位 `meter_id`、token class、provider、actor 与时间桶。
2. 取得提供方 receipt，核对原始 `DEBIT`。
3. 禁止 UPDATE/DELETE 原事实。
4. 使用管理 scope 写 `CREDIT` 纠正，数量不得超过原始借记减已纠正量。
5. 记录客户沟通与纠正原因，但不要把敏感数据写入 reason code。

## 事故动作

- Stripe 超时/结果未知：保持案件 OPEN，禁止盲重试。
- Webhook 签名异常：拒绝，不创建订阅；轮换 secret 前核对 endpoint。
- 数据库不可用：拒绝新预留和 Checkout；不要退回客户端自报计量。
- 用量突增：关闭任务入口而非篡改额度；保存 receipt 和作业证据。
- 跨租户迹象：立即禁用相关服务凭证，保全日志，验证 RLS 和 JWT 组织绑定。

## 邮件告警

当前数据库可生成 `EMAIL/PENDING` 告警意图，但发送提供方未配置。API 只有在
`ELMOS_USAGE_EMAIL_ALERTS_ENABLED=true` 时允许用户开启邮件通道。正式开启前必须完成
退订、频控、地址验证、供应商回执、失败重试和隐私评审；否则保持 `NOT_CONFIGURED`。

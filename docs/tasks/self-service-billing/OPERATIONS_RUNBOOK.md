# 自助计费运行手册

## 健康与监控

`BillingDatabaseHealthIndicator` 检查当前目录版本和核心预留函数。数据库未配置时
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
7. `payment_callback_receipts.processing_status IN ('PROCESSING','FAILED')` 的最老年龄；
   超过五分钟的 PROCESSING 可由同一提供方事件重领，持续 FAILED 必须告警。
8. `commercial_orders.status='RECONCILIATION_REQUIRED'`，尤其是
   `CHECKOUT_PREPARE_OUTCOME_UNKNOWN` 与 `PAYMENT_AFTER_LOCAL_EXPIRY`。
9. 定价页的 Credit 面板应从 `/billing/credits`、`/billing/credits/ledger` 和
   `/billing/orders` 得到一致事实；存在待付款订单时每四秒读取一次，页面隐藏时停止轮询。

## 生产配置

公共必需项：

- `ELMOS_COMMERCIAL_DATABASE_URL`、`ELMOS_COMMERCIAL_DATABASE_USERNAME`、
  `ELMOS_COMMERCIAL_DATABASE_PASSWORD`
- `ELMOS_OIDC_ISSUER_URI`、`ELMOS_OIDC_JWK_SET_URI`、`ELMOS_OIDC_AUDIENCE`
- 完成全部外部门禁后才设置 `ELMOS_BILLING_LIVE_ENABLED=true`

支付宝：

- `ELMOS_ALIPAY_APP_ID`
- `ELMOS_ALIPAY_PUBLIC_KEY_FILE`、`ELMOS_ALIPAY_PRIVATE_KEY_FILE`（0400 Secret 挂载）
- `ELMOS_ALIPAY_GATEWAY_URL`（生产默认官方地址）
- `ELMOS_ALIPAY_NOTIFY_URL`、`ELMOS_ALIPAY_RETURN_URL`（备案 HTTPS 域名）

微信支付 Native：

- `ELMOS_WECHATPAY_MCHID`、`ELMOS_WECHATPAY_APP_ID`、`ELMOS_WECHATPAY_CERT_SERIAL_NO`
- `ELMOS_WECHATPAY_PRIVATE_KEY_FILE`、`ELMOS_WECHATPAY_PLATFORM_CERT_FILE`（0400 Secret 挂载）
- `ELMOS_WECHATPAY_API_V3_KEY`（必须由 Secret Manager 注入，禁止写入仓库）
- `ELMOS_WECHATPAY_NOTIFY_URL`（备案 HTTPS 域名）

ELMPay 聚合出口：见 [ELMPAY_INTEGRATION.md](ELMPAY_INTEGRATION.md)。启用时必须同时
完成 API 凭据、tenant/project 绑定、mTLS、签名 webhook endpoint 与 V84/V94 迁移；不得把
`ELMOS_ELMPAY_ALLOW_HTTP_LOCAL_SANDBOX` 带入生产。

至少一个与目录 `paymentProvider` 完全相同的下单网关和回调验签器必须同时存在。
缺任何一项均应保持 503/失败关闭，不允许只开放付款按钮。

## 支付对账

管理员用 `commercial:billing:admin`：

- `GET /commercial/v1/billing/reconciliation?status=OPEN`
- 核对支付宝/微信商户后台、原始签名事件摘要、对象引用、金额/币种和本地订单状态。
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

- 微信下单超时/结果未知：订单进入待对账，禁止盲重试。
- 支付宝本地签名/参数失败：提供方未被联系，可安全创建新的幂等请求。
- 付款晚于本地 TTL：不得自动发货；按外部证据选择退款或受控补发并保留审批记录。
- 用户看到 `RECONCILIATION_REQUIRED`：要求停止重复付款；运营核对 provider 交易后再退款或补发。
- Webhook 签名异常：拒绝，不创建订阅；轮换 secret 前核对 endpoint。
- 数据库不可用：拒绝新预留和 Checkout；不要退回客户端自报计量。
- 用量突增：关闭任务入口而非篡改额度；保存 receipt 和作业证据。
- 跨租户迹象：立即禁用相关服务凭证，保全日志，验证 RLS 和 JWT 组织绑定。

## 发布与回滚

1. 先备份并在同版本影子库执行 Flyway `validate → migrate → validate` 到 V94。
2. 注入只读目录/白名单函数权限的运行角色和支付 Secret，保持 live billing 关闭。
3. 执行真实小额付款、回调重发、延迟回调、退款和逐笔对账；保存提供方 receipt。
4. 外部门禁全部签核后发布新的 `PUBLISHED` 目录版本，再开启 live billing，并采用灰度流量。
5. 异常回滚先关闭 `ELMOS_BILLING_LIVE_ENABLED` 和新生成入口；保留订单、回调、账本和
   Token 事实供对账。V83–V94 是前向审计迁移，不做删除式 down migration。

## 邮件告警

当前数据库可生成 `EMAIL/PENDING` 告警意图，但发送提供方未配置。API 只有在
`ELMOS_USAGE_EMAIL_ALERTS_ENABLED=true` 时允许用户开启邮件通道。正式开启前必须完成
退订、频控、地址验证、供应商回执、失败重试和隐私评审；否则保持 `NOT_CONFIGURED`。

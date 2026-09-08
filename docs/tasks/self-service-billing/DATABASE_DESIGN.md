# 自助计费数据库设计

## 权威版本

- 数据库：PostgreSQL 17.5
- Flyway：V1–V86；基础计费为 `V49__self_service_billing_and_usage.sql`，
  Credit/一次性订单与用户维度扩展为 `V83__commercial_credit_and_one_time_orders.sql`，
  支付生命周期加固为 V84–V85，当前订阅目录快照升级为 V86
- 目录版本：`2026-09-08.1`
- 数量：`numeric(30,0)`，只接受非负整数
- 金额：人民币分，`numeric(19,0)`；提供方成本使用 `numeric(30,6)` 并带显式币种

## 主要聚合

| 聚合 | 表 | 语义 |
|---|---|---|
| 目录快照 | `self_service_pricing_plan_versions` | 绑定不可变目录版本、价格与额度 |
| 订阅 | `subscriptions`、`subscription_events` | 试用、有效、逾期、取消和账期 |
| 额度 | `quota_allocations` | 每账期 Token/Credit 的 limit、reserved、consumed |
| 计量 | `usage_reservations`、`usage_events`、`usage_ledger_entries`、`billing.token_usage_events` | 预留、提供方事实、生产模型 Token 事实、借贷账本与纠正链 |
| 试用 | `trial_grants`、`trial_events` | 一组织一次、一验证身份一次、到期/转付费 |
| 支付 | `payment_checkout_sessions`、`payment_provider_events` | 两阶段 Checkout 与签名事件事实 |
| 对账 | `payment_reconciliation_cases`、`payment_reconciliation_case_events` | 待处理状态与追加式结案证据 |
| 告警 | `usage_alert_preferences`、`usage_alert_deliveries` | 乐观锁偏好与阈值越界通知事实 |
| 商品 | `commercial_products` | 不可变 Credit 包与单项目一次性商品快照 |
| 商品订单 | `commercial_orders`、`commercial_order_directory` | 租户订单与回调前最小查单目录 |
| 购买 Credit | `commercial_credit_accounts`、`commercial_credit_lots`、`commercial_credit_ledger_entries` | 余额、FIFO 到期批次与追加账本 |
| 单项目权益 | `project_generation_entitlements` | actor/project 绑定的一次性生成权益 |
| 生成资金预留 | `commercial_credit_reservations`、`commercial_credit_reservation_lots` | 一次性权益优先、Credit 次选的并发安全预留 |

## 核心不变量

1. `consumed + reserved <= limit`，由额度行 `FOR UPDATE` 串行化。
2. 结算不得超过预留；释放、过期、结算只允许一次。
3. 相同幂等键重放时，请求内容必须完全一致。
4. Token 结算必须提供 token class、provider 和 provider receipt。
5. 纠正只追加 `CREDIT` 账本项，累计纠正不得超过原始 `DEBIT`。
6. 免费体验同时受 `organization_id` 唯一约束和 `verified_subject_hash` 全局唯一约束。
7. 支付提供方事件与对账结案事件禁止 UPDATE/DELETE。
8. 未设置 `app.organization_id` 时，租户函数与 RLS 均失败关闭。
9. Credit 余额只能由安全函数和 posting guard 变更，生成结算按 FIFO 扣减批次。
10. 一次性权益只能被相同 actor 和 project 的一个 job 消费。
11. 回调 claim 只有 `PROCESSING/COMPLETED/FAILED`；失败可重领，完成不可重放。
12. Token 预留、事件和账本携带 actor/project/job/model，SELF 查询强制 actor 过滤；
    生产模型调用的 INPUT/CACHE_READ/OUTPUT/REASONING 事实按 provider receipt 去重并并入同一历史。

## 数据库函数

| 函数 | 事务职责 |
|---|---|
| `elmos_reserve_usage` | 锁定当前额度并原子接受/拒绝预留 |
| `elmos_settle_usage` | 释放预留、增加消费、写事件/账本、触发阈值告警 |
| `elmos_release_usage` | 失败或超时释放预留 |
| `elmos_correct_usage` | 写追加式用量纠正 |
| `elmos_grant_trial` | 原子创建试用、订阅和额度 |
| `elmos_expire_current_trial` | 到期关闭试用订阅与额度 |
| `elmos_activate_subscription_period` | Webhook 确认后激活付费账期并转换试用 |
| `elmos_resolve_payment_reconciliation` | 锁定待对账案件并写结案审计事件 |
| `elmos_reserve_usage_v2` / `elmos_settle_usage_v2` / `elmos_release_usage_v2` | 带 actor/project/job/model 的 Token 计量生命周期 |
| `elmos_commercial_create_order` | 从服务端商品目录创建精确金额订单并验证幂等 |
| `elmos_commercial_mark_order_handoff` | 在提供方交接成功后推进到待支付 |
| `elmos_commercial_mark_order_prepare_failed` | 把确定失败与结果未知分别标记为失败/待对账 |
| `elmos_commercial_fulfill_order` | 支付确认后恰好一次发 Credit 或项目权益 |
| `elmos_commercial_reserve_generation` | 项目权益优先、Credit FIFO 的原子预留 |
| `elmos_commercial_settle_generation` / `elmos_commercial_release_generation` | 结算或释放生成资金 |

## RLS 与索引

所有计费租户表使用：

```sql
USING (organization_id = current_setting('app.organization_id', true))
WITH CHECK (organization_id = current_setting('app.organization_id', true))
```

关键索引覆盖组织/状态/账期、订阅/事件时间、幂等键和提供方引用。价格目录表不含租户数据，
可由服务读取；支付密钥、JWT、数据库密码不进入任何业务表。

## 已验证与未验证

- 空数据库 V1–V83 重放、RLS、并发硬停止、幂等、试用防滥用、阈值告警、
  Credit/一次性权益和对账结案：
  由本地 PostgreSQL 17 集成测试验证。
- 生产项目/分支/数据库上的表、策略与 Flyway 历史：`NOT_RUN`。
- 生产回填：本版本没有旧的权威自助计费事实可安全推断，因此不生成虚构回填。

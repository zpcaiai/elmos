# 支付回调持久化：V54 迁移与端口实现

日期：2026-07-28（第三轮）
关联：[`PAYMENT_ADAPTER_STATUS.md`](PAYMENT_ADAPTER_STATUS.md)、D-01、D-03

---

## 1. 这一轮挖出来的两个约束冲突

上一轮我列了"契约 8 处"。接上真实 schema 之后发现**漏了两处**，
而且两处都会在**回调处理到一半时**才炸——那时候钱已经扣了。

### 1.1 数据库把 provider 写死成 Stripe

`V49` 里两张表都有：

```sql
provider varchar(32) NOT NULL CHECK (provider = 'STRIPE_CHECKOUT')
```

`payment_checkout_sessions` 与 `payment_provider_events` 各一处。
不改约束，支付宝的下单会话根本插不进去，回调走到第 4 步写事件时被数据库拒绝。
**这是第 9、第 10 处契约点**，此前的清单没有覆盖。

已实测复现：迁移前插入 `ALIPAY_CHECKOUT` 报
`violates check constraint "payment_checkout_sessions_provider_check"`。

### 1.2 对账案件表要求 organization_id，但订单未知时组织正是未知的

```sql
CREATE TABLE payment_reconciliation_cases (
    ...
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
```

管线的 `ORDER_UNKNOWN` 分支恰恰是**组织未知**那一支：组织要靠 `out_trade_no`
查订单才能确定，查不到就没有组织可填。

三种做法里两种不可接受：用哨兵组织填充会污染租户数据并破坏 RLS 语义；
直接丢弃违反"原始事实不丢"。因此新增一张不含租户列的
`payment_unmatched_callbacks` 滞留表，由人工在对账时认领后转入正式案件。

这个发现反过来改了**端口签名**：
`ReconciliationCases.open(...)` 增加 `LocalOrder order` 参数（订单未知时为 null），
调用方据此分流。管线自检也加了两条断言守住这个区分。

---

## 2. V54 迁移

`modules/persistence/src/main/resources/db/migration/V54__multi_provider_payment_callbacks.sql`

| 内容 | 说明 |
|---|---|
| 放开两处 provider CHECK | 三个通道均可写入，未知通道仍被拒 |
| `payment_callback_receipts` | 回调幂等台账，主键即幂等键 |
| `payment_unmatched_callbacks` | 无主回调滞留表 |
| 运行角色授权 | 只给 SELECT/INSERT，不给 UPDATE/DELETE |

**版本号取 V54 而不是补 V52。** 现有迁移是 V49、V50、V51、V53——V52 是空缺号。
Flyway 默认禁止乱序，在 V53 已应用的库上插入 V52 会直接失败。空缺号保持空缺。

**两张新表都不加 RLS，这是有意的例外。** `payment_callback_receipts` 只存
通道、事件 ID、接收时间，没有任何租户数据；`payment_unmatched_callbacks` 的
组织本来就未知。它们靠角色授权而不是 RLS 控制访问，理由写在迁移注释里。

**为什么不复用 `payment_provider_events` 的 `UNIQUE (organization_id, idempotency_key)`
做幂等**：那个约束按组织分区，但回调到达时组织还未知。若把幂等推迟到组织已知之后，
并发重发的两个请求会同时通过查单再同时写事件。

---

## 3. 数据库行为验证

`tooling/payment-db-verify/verify_payment_callbacks.sh`，
在真实 **PostgreSQL 16.13** 上执行，**19 项断言全部通过**：

```
DECISION=MIGRATION_VERIFIED_LOCAL  (19 项全部通过)
```

其中三条是这一轮的关键证据：

**并发幂等**：20 个并发会话争抢同一个幂等键，
`INSERT ... ON CONFLICT DO NOTHING RETURNING` **恰好 1 个**拿到返回行，台账 1 行。

**"先查后插"的反例**：两个并发会话在同一个事务里先 SELECT 再 INSERT，
**两个 SELECT 都看到 0 行**——也就是说应用层都会判定"首次见到"。
唯一约束只能在 INSERT 阶段兜住其中一个，而业务判断此时已经做出。
若实现吞掉那个 duplicate key 异常并返回 true，重复回调就会被当成首次处理。
这条断言把上一轮的口头警告变成了可复算的证据。

**权限最小化**：运行角色对两张新表只有 `INSERT,SELECT`，
没有 UPDATE/DELETE——杜绝"把已处理事件改回未处理"这类绕过幂等的操作。

---

## 4. 端口实现

`JdbcCallbackPorts`（只依赖 JDK 的 `java.sql` / `javax.sql`，不引 ORM）：

| 端口 | 实现 | 状态 |
|---|---|---|
| `ProcessedEventLog` | `ON CONFLICT DO NOTHING RETURNING` | ✅ SQL 语义已实测 |
| `ProviderEventStore` | 写 `payment_provider_events` | ✅ 编译通过 |
| `ReconciliationCases` | 按订单是否已知分流两张表 | ✅ 编译通过 |
| `OrderLookup` | 查 `payment_checkout_sessions` | ✅ 状态语义已实测 |
| `SubscriptionActivator` | 关单 + `elmos_activate_subscription_period` | ✅ 编译通过，SQL 部分已实测 |

### 这两张表确认在哪

**订单 = `payment_checkout_sessions`**。它带 `plan_id`、`amount_minor`、
`catalog_version` 和完整状态机，就是订单表。

`out_trade_no` 映射到 **`checkout_session_id`** 而不是 `provider_session_ref`：
Stripe 路径按 `provider_session_ref` 查，是因为会话 ID 由 Stripe 生成；
而支付宝/微信的 `out_trade_no` **由我们生成后传给提供方**，
所以本地主键才是正确的查找键。

**订阅 = `subscriptions`**（V10 建表，V49 用 ALTER 补了 `provider`、
`provider_subscription_ref`、`current_period_start/end` 等列）。

### 订阅激活不写裸 SQL

激活走存储函数 **`elmos_activate_subscription_period`**，与既有 Stripe 路径一致。
该函数在一次调用里同时写 `subscriptions`、`quota_allocations`、`subscription_events`
并处理试用转付费，每处都带 ON CONFLICT 幂等。绕过它自己拼 INSERT 会漏掉额度发放，
表现为"订阅显示已开通但用不了"。

三个必须注意的点：

1. **函数依赖会话级租户上下文**（内部用 `elmos_current_organization_id()`），
   因此调用前必须 `set_config('app.organization_id', ..., true)`，
   且必须与关单在**同一个事务**里 —— `SET LOCAL` 出了事务就失效。
2. **Stripe 把"会话完成"和"发票已付"拆成两个事件**，分别关单和激活；
   支付宝/微信只有一个支付成功回调，两件事必须一起做。
   拆开会出现"订单已关但额度没发"的中间态。
3. 订阅 ID 按「组织 + 套餐」**确定性生成**，手动续费时续的是同一条订阅
   （函数内 `ON CONFLICT (subscription_id) DO UPDATE` 把期间往后推），
   而不是每次支付新建一条。

`ProviderEventStore` 里有一处刻意设计：`payment_provider_events` 有
`CHECK (signature_verified)`，只有验签通过的事件才允许落库。
实现恒填 `true`，因为管线保证到第 4 步时验签必然已过——
若将来有人把这个调用挪到验签之前，**数据库会直接拒绝**，这是有意的第二道防线。

---

## 4.5 第 11 处契约耦合：目录版本硬编码在存储函数里

`elmos_activate_subscription_period` 的函数体里有：

```sql
SELECT * INTO v_plan FROM self_service_pricing_plan_versions
 WHERE catalog_version = '2026-07-28.2' AND plan_id = p_plan_id;
IF NOT FOUND OR v_plan.billing_period = 'TRIAL' THEN
    RAISE EXCEPTION 'PAID_PLAN_INVALID';
END IF;
```

**目录版本号是写死的。** 任何一次调价（目录版本必然递增）都必须同步一条新迁移
去改这个函数，否则所有支付成功回调会以 `PAID_PLAN_INVALID` 失败——
而那时钱已经扣了。

这一处不在原先的"8 处契约"清单里，也不在本轮新发现的第 9、10 处里，
属于**第 11 处**。建议在调价流程的检查单里显式列出这个函数。

（本轮未修改该函数：改它需要同时确认既有 Stripe 路径不受影响，
应当与调价一起做，而不是夹带在支付通道扩展里。）

## 5. 自检总量

| 套件 | 断言 | 结果 |
|---|---|---|
| `PaymentCryptoSelfTest` | 46 | 全过 |
| `PaymentPipelineSelfTest` | 47 | 全过（新增 2 条：订单已知/未知的分流） |
| `CheckoutGatewaySelfTest` | 33 | 全过 |
| `JdbcPortsSelfTest` | 10 | 全过 |
| `OrderPortsSelfTest` | 8 | 全过 |
| `verify_payment_callbacks.sh` | 19 | 全过（真实 PostgreSQL） |
| **合计** | **163** | **0 失败** |

新增的 7 项数据库断言覆盖订单状态语义：

- OPEN 订单可查到；**EXPIRED 订单查不到**（其上的支付成功回调应进对账）
- 首次关单影响 1 行；**重发再次关单仍影响 1 行**——`COMPLETED` 在白名单内，
  重发不会掉进 ORDER_UNKNOWN 而凭空制造对账工单
- **`completed_at` 不被重发覆盖**（`COALESCE` 生效），首次支付时间不丢
- **EXPIRED 订单关单影响 0 行** → 拒绝激活订阅

---

## 6. 顺带修掉的验证脚本自身缺陷

`verify_payment_callbacks.sh` 初版有个隐蔽 bug：脚本开了 `set -o pipefail`，
而负向断言写成 `psql "会报错的语句" | grep -q "violates check constraint"`。
psql 以非零码退出时**整条管线就是非零**，即使 grep 命中也被判成失败——
三条负向断言全部误报为 FAIL。

改成先把输出存进变量再匹配，并把原因写进脚本注释。
这类 bug 的危险在于方向相反：它让**正确的实现看起来是错的**，
容易导致有人去"修"本来没问题的代码。

---

## 7. 仍未完成

- `PaymentCallbackController` 的 Spring 装配与 Security 放行
- 存储函数调用路径尚未在真库执行（需要重建 `subscriptions`、`quota_allocations`、
  `self_service_pricing_plan_versions` 及函数本身，本轮只验证了关单那半段 SQL）
- 回调时间戳偏差校验（防重放）
- 沙箱全链路、真实交易、真实退款：`NOT_RUN`
- 契约剩余 3 处：`PricingPlanCatalogTest`、`BillingActions.tsx`、`checkout/route.ts`

## 8. PostgreSQL 版本：已安排自动复跑

**本轮验证在 PostgreSQL 16.13 上完成；仓库目标是 17.5。**
容器内拿不到 17.5（apt.postgresql.org 与 Maven Central 都被代理拦截，
pypi 上的 `pgserver` 也只带 16.2），所以本地无法直接复跑。

但仓库 CI 的 `commercial-billing-integration` job **已经起了
`postgres:17.5-alpine` 服务**。把验证脚本挂进那个 job 即可让 17.5 复跑
每次 CI 自动发生，不依赖人记得做——片段见
`ci-payment-db-verify.snippet.yml`（workflow 文件受保护，需手工追加）。

在那一步跑绿之前，本迁移的证据等级是
**`MIGRATION_VERIFIED_LOCAL`（PostgreSQL 16.13）**，不是 17.5。

`mvn verify` 本轮仍未运行——容器没有完整 reactor 依赖。

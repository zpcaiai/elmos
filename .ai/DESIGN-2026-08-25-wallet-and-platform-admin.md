# 用户账号子系统：预付费钱包、任务扣费与平台管理端

> 设计稿 · 2026-08-25 · 待评审后再实现
> 迁移版本占位：**V73**（当前最高为 V72，实现前需重新确认，防止并发会话抢号）
>
> **认领**：本会话认领「钱包 / 充值 / 任务扣费 / 平台管理员」这一整块，`IN-PROGRESS @ 2026-08-25`。
> 其他会话动手前请先看这份文件——这个仓库有过整块功能被实现两遍的前科。

---

## 0. 先说结论：这件事有多少是「新建」，多少是「接线」

我按你的四个诉求逐条对着代码核过一遍现状。**大部分身份与任务能力已经存在，真正缺的是「钱」这一层和「跨组织视角」这一层。**

| 你的诉求 | 现状 | 本轮要做的 |
| --- | --- | --- |
| 用户账号 | **已有且相当完整**：`accounts` 表（平台全局、刻意不做 RLS）、`account_credentials`（密码/邮箱 OTP/短信 OTP/微信/GitHub/Gitee/企业 OIDC/SAML）、组织成员与邀请、会话、`modules/identity` + `/api/auth/*` + `/account` 页面 | 不动。只增加「账号 ↔ 钱包」的读取路径 |
| 用户充值 | **缺**。现有只有「订阅套餐结账」：`self_service_pricing_plan_versions` + `subscriptions` + `quota_allocations`（周期配额，跨周期不累积），支付侧有微信/支付宝/Stripe 网关与回调管线 | 新建预付费钱包、流水账、充值订单；**复用**现有支付网关与回调管线 |
| 用户添加任务 | **已有**：`execution_jobs` 全量状态机（QUEUED/CLAIMED/RUNNING/SUCCEEDED/PARTIAL/FAILED/CANCELLED/LOST）+ 事件流 + 派发 + Runner 队列，入口 `POST /api/v1/execution/jobs` | 不动主流程，**在入队前插入预扣、在终态插入结算** |
| 管理员看各账户余额与任务 | **缺跨组织能力**。现有 admin（`admin:read`/`admin:operate`/`admin:approve`）绑在组织会话上，`OperationsAuthorization` 的另一条凭据路径也绑死单个 organization；全仓库到处是 `CROSS_TENANT_*_DENIED` | 新建**平台管理员**身份 + 一条显式的、逐次审计的跨租户只读路径 |
| 后台管理系统 | **已有骨架**：`/admin` 页面（`OperationsAdmin.tsx`）、`/api/admin/{operations,tenant-quota,jobs,runners,billing/reconciliation,audit-export,run-replay}`、`authorizeAdmin` 三级角色、同源校验、代理层 | 在同一套壳里加三个面板，不新起应用 |

**最重要的一条现状事实**：`ExecutionJobController.enqueue` 目前**没有任何计费或配额门禁**——校验 Runner 镜像摘要、拒绝敏感载荷、算 digest，然后直接入库。也就是说「任务扣费」不是改一个已有的门禁，而是**新开一个门禁**。这决定了下面第 4 节的大部分复杂度。

---

## 1. 范围与刻意不做的事

**做：**
- 组织级预付费钱包（余额 + 冻结 + 流水账），币种固定 CNY（与现有定价目录一致）
- 充值订单：下单 → 支付（复用微信/支付宝/Stripe）→ 回调入账，全链路幂等
- 任务提交前预扣、终态结算/释放，余额不足直接拒绝入队
- 平台管理员身份、授予/撤销、跨组织只读视图、手工调整（强审计）
- `/admin` 三个新面板：账户余额、充值与对账、任务执行

**不做（明确留给后续）：**
- 不下线订阅套餐。钱包与订阅**并存**：套餐配额优先消耗，配额耗尽后落到钱包余额。这条是本设计的核心分层，见 §3.4。
- 不做发票、开票、税务。
- 不做自动退款。退款先做「管理员发起 + 人工在支付渠道执行 + 回填入账」的半自动路径。
- 不做多币种、不做汇率。
- 不做用量实时计费（按 token 秒级计价）。v1 用「预算预扣 + 终态按实际用量结算」的两段式，见 §4。

---

## 2. 数据模型（V73）

沿用仓库既有约定：金额一律 `numeric(19,0)` 存**分**（与 `price_minor`/`amount_minor` 一致）、流水表挂 `elmos_forbid_append_only_mutation` 追加触发器、可变表挂 `state_version` 自增与终态不可改写触发器、组织维度表进 RLS（`app.organization_id`）、跨租户聚合只能走 `SECURITY DEFINER` 函数 + 非登录角色。

### 2.1 `wallet_accounts` —— 每个组织一个钱包

```
organization_id   varchar(96) PK REFERENCES organizations
currency          char(3) NOT NULL CHECK (currency = 'CNY')
balance_minor     numeric(19,0) NOT NULL DEFAULT 0 CHECK (balance_minor >= 0)
reserved_minor    numeric(19,0) NOT NULL DEFAULT 0 CHECK (reserved_minor >= 0)
status            varchar(24) NOT NULL DEFAULT 'ACTIVE'
                  CHECK (status IN ('ACTIVE','FROZEN','CLOSED'))
last_entry_seq    bigint NOT NULL DEFAULT 0
state_version     bigint NOT NULL DEFAULT 0
created_at / updated_at
CHECK (reserved_minor <= balance_minor)
```

**关键决定：钱包主体是 organization，不是 account。**

理由：扣费对象是 `execution_jobs`，而它是 org 维度（`organization_id` + RLS + 跨租户禁止）。如果钱包挂在 account 上，一个人在三个组织里跑任务时，钱从谁的口袋出、组织解散后余额归谁、组织内 A 充值 B 消费怎么记账——每一条都要新造规则，而且会和已有的 `subscriptions`/`quota_allocations`（都是 org 维度）分叉成两套计费主体。

「用户视角的余额」通过**每条流水都带 `actor_id`** 来满足：用户能看到「我充了多少、我花了多少、组织里谁花的」。自助用户的个人组织就是他的钱包。

> ✅ **已确认（U1）**：`AuthenticationService.provisionFirstOrganization` 在注册时自动建组织（`org-<uuid>`，名字「<脱敏标识> 的组织」，region `cn-north`），并生成确定性 `actorId = sha256(orgId + ":" + accountId)[:32]`。**每个新用户天然有钱包主体，注册流程不用改。**
>
> 顺带一个可复用的资产：`completeSignup` 传入的 `hmac` 是**已验证主体哈希**，`trial_grants` 上有它的全局 UNIQUE——「一个真人只能领一次试用」。**首充赠送 / 新人补贴如果要做，必须复用这个锚点**，否则会被一人注册 N 个组织刷穿。

`balance_minor` 是**物化值**，权威是流水账。它不允许被应用直接 UPDATE：只有下面的 `SECURITY DEFINER` 记账函数能改，函数内部保证「余额变化 = 本次流水金额」。另有对账任务定期校验 `balance_minor == SUM(ledger)`，不一致即告警并冻结钱包（fail-closed）。

### 2.2 `wallet_ledger_entries` —— 唯一权威，append-only

```
entry_id            varchar(96) PK
organization_id     varchar(96) NOT NULL REFERENCES organizations
seq                 bigint NOT NULL              -- 组织内单调递增
currency            char(3) NOT NULL CHECK (currency = 'CNY')
direction           varchar(8)  NOT NULL CHECK (direction IN ('CREDIT','DEBIT'))
amount_minor        numeric(19,0) NOT NULL CHECK (amount_minor > 0)
balance_after_minor numeric(19,0) NOT NULL CHECK (balance_after_minor >= 0)
entry_type          varchar(32) NOT NULL
source_type         varchar(24) NOT NULL CHECK (source_type IN
                       ('TOPUP_ORDER','JOB','ADMIN','SYSTEM'))
source_ref          varchar(160) NOT NULL
reservation_ref     varchar(96)
actor_id            varchar(128) NOT NULL
idempotency_key     varchar(160) NOT NULL
reason              varchar(255)                 -- ADMIN_ADJUSTMENT 时必填
occurred_at         timestamptz NOT NULL DEFAULT now()

UNIQUE (organization_id, seq)
UNIQUE (organization_id, idempotency_key)
CHECK (entry_type IN ('TOPUP_SETTLED','RESERVE','RELEASE','CONSUME',
                      'REFUND','ADMIN_ADJUSTMENT','TRIAL_GRANT'))
CHECK (entry_type <> 'ADMIN_ADJUSTMENT' OR reason IS NOT NULL)
```

+ `elmos_forbid_append_only_mutation` 触发器（UPDATE/DELETE 一律拒）。

`balance_after_minor` 让流水**自证**：任何时点可以从任意一条流水向前重放校验，不必信任 `wallet_accounts`。这是对账任务的基础。

`UNIQUE (organization_id, idempotency_key)` 是**整个设计里最重要的一条约束**：支付回调重放、Runner 重试、管理员重复点击，全部靠它兜底，而不是靠应用层记得判重。

### 2.3 `wallet_reservations` —— 任务预扣

```
reservation_id       varchar(96) PK
organization_id      varchar(96) NOT NULL REFERENCES organizations
job_id               varchar(96) REFERENCES execution_jobs(job_id)
amount_minor         numeric(19,0) NOT NULL CHECK (amount_minor > 0)
status               varchar(16) NOT NULL DEFAULT 'HELD'
                     CHECK (status IN ('HELD','SETTLED','RELEASED','EXPIRED'))
settled_amount_minor numeric(19,0)
quote_ref            varchar(96) NOT NULL      -- 指向 wallet_price_book
held_at              timestamptz NOT NULL DEFAULT now()
expires_at           timestamptz NOT NULL
resolved_at          timestamptz
state_version        bigint NOT NULL DEFAULT 0

UNIQUE (organization_id, job_id)               -- 一个任务至多一笔预扣
CHECK (status <> 'SETTLED' OR (settled_amount_minor IS NOT NULL
       AND settled_amount_minor <= amount_minor AND resolved_at IS NOT NULL))
CHECK (status IN ('HELD') OR resolved_at IS NOT NULL)
CHECK (expires_at > held_at)
```

+ 终态不可改写触发器（照抄 `elmos_guard_execution_job_transition` 的形状）：`SETTLED`/`RELEASED`/`EXPIRED` 进去就不能再变，`organization_id` 不可变，`state_version` 自增。

`expires_at` 是防泄漏的关键：Runner 崩了、调度器丢了任务，钱不能一直被冻住。过期回收器把 `HELD` 且超时的预扣转 `EXPIRED` 并写 `RELEASE` 流水。

### 2.4 `wallet_topup_orders` —— 充值订单

```
topup_order_id        varchar(96) PK
organization_id       varchar(96) NOT NULL REFERENCES organizations
actor_id              varchar(128) NOT NULL       -- 谁发起的充值
currency              char(3) NOT NULL CHECK (currency = 'CNY')
amount_minor          numeric(19,0) NOT NULL CHECK (amount_minor > 0)
provider              varchar(16) NOT NULL
                      CHECK (provider IN ('WECHAT_PAY','ALIPAY','STRIPE','OFFLINE'))
out_trade_no          varchar(255) NOT NULL
provider_txn_ref      varchar(255)
checkout_session_ref  varchar(96)
status                varchar(24) NOT NULL DEFAULT 'CREATED'
credited_entry_ref    varchar(96)                 -- 指向入账那条流水
created_at / paid_at / credited_at / expires_at
state_version         bigint NOT NULL DEFAULT 0

UNIQUE (provider, out_trade_no)
CHECK (status IN ('CREATED','PENDING_PAYMENT','PAID','CREDITED',
                  'FAILED','EXPIRED','REFUNDED'))
CHECK (status <> 'CREDITED' OR (credited_entry_ref IS NOT NULL
       AND credited_at IS NOT NULL AND paid_at IS NOT NULL))
```

**为什么 `PAID` 和 `CREDITED` 是两个状态而不是一个**：支付渠道确认收款和钱进钱包是两件事，中间可能失败。分开之后，「收了钱没入账」是一个可查询、可重放、可对账的明确状态，而不是一个丢失的事件。`payment_reconciliation_cases`（V49 已有）正好接这个。

充值上下限、单日限额放 `wallet_topup_policies`（每组织可覆写，默认值走配置）——防止误输入 100000 元和防洗钱各需要一半。

> ✅ **已确认（U2）：必须新建，不能复用 `payment_checkout_sessions`。** 那张表两处硬约束把充值挡在外面：`plan_id varchar(96) NOT NULL`（充值没有套餐）和 `CHECK (provider = 'STRIPE_CHECKOUT')`（充值要走微信/支付宝，这是国内自助场景的主力渠道）。放宽这两条等于把套餐结账的约束一起拆掉——用一张新表比削弱一张已经在用的表安全。

### 2.5 `wallet_price_book` —— 任务计价，版本化 append-only

```
catalog_version  varchar(64)
business_line    varchar(32)     -- GENERATION/TRANSLATION/SPRING_UPGRADE/...
job_kind         varchar(64)     -- '*' 表示该业务线兜底
reserve_minor    numeric(19,0)   -- 入队时预扣多少
unit             varchar(24)     CHECK (unit IN ('WALL_SECOND','TOKEN','JOB'))
unit_price_minor numeric(19,0)
min_charge_minor numeric(19,0)
effective_from / effective_until / status(DRAFT/PUBLISHED/SUPERSEDED)
PRIMARY KEY (catalog_version, business_line, job_kind)
```

形状刻意抄 `self_service_pricing_plan_versions`——同一套价格治理心智，运营不用学两遍。每笔预扣记下 `quote_ref`，价目表改了也不会追溯改写历史任务的账。

### 2.6 `platform_administrators` + `platform_admin_access_log`

```
platform_administrators
  account_id          varchar(96) PK REFERENCES accounts(account_id)
  platform_role       varchar(24) NOT NULL
                      CHECK (platform_role IN
                        ('PLATFORM_VIEWER','PLATFORM_OPERATOR','PLATFORM_APPROVER'))
  granted_by          varchar(96) REFERENCES accounts(account_id)
  granted_at          timestamptz NOT NULL DEFAULT now()
  grant_reason        varchar(255) NOT NULL
  revoked_at          timestamptz
  revoked_by          varchar(96) REFERENCES accounts(account_id)
  state_version       bigint NOT NULL DEFAULT 0
  CHECK (revoked_at IS NULL OR revoked_by IS NOT NULL)

platform_admin_access_log   -- append-only
  access_id, admin_account_id, platform_role, operation,
  target_organization_id, target_ref, request_digest,
  result varchar(16) CHECK (result IN ('ALLOWED','DENIED')),
  occurred_at
```

两张表都**不做 RLS**（跨组织本来就是它们的定义），和 `accounts` 一样：不做 RLS，代价是只能通过 `SECURITY DEFINER` 函数 + 一个从不服务租户查询的应用角色触达。

---

## 3. 跨组织读取：把 RLS 豁免关在一个笼子里

全仓库的默认姿态是「跨租户一律拒」（`CROSS_TENANT_ACCESS_DENIED` 在 identity、CAS、marketplace、governance、web-console 会话层都有）。平台管理员是**第一个正当的例外**，所以它必须比普通功能更贵一点。

新增非登录角色 `elmos_platform_admin_runtime`（照 `elmos_scheduler`、`elmos_billing_runtime` 的先例），只授予下面这组函数的 EXECUTE，**不授予任何表的 SELECT**。

```
elmos_platform_wallet_overview(p_admin_account, p_cursor, p_limit, p_filter)
elmos_platform_wallet_ledger(p_admin_account, p_organization_id, p_cursor, p_limit)
elmos_platform_topup_orders(p_admin_account, p_filter, p_cursor, p_limit)
elmos_platform_job_overview(p_admin_account, p_filter, p_cursor, p_limit)
elmos_platform_job_detail(p_admin_account, p_organization_id, p_job_id)
elmos_platform_wallet_adjust(p_admin_account, p_organization_id,
                             p_direction, p_amount_minor, p_reason, p_idempotency_key)
```

每个函数的**前三行固定**：
1. 校验 `p_admin_account` 在 `platform_administrators` 且 `revoked_at IS NULL` 且角色足够；
2. 写一条 `platform_admin_access_log`（含 `target_organization_id`）；
3. 校验不通过就写 `result='DENIED'` 然后 `RAISE EXCEPTION`。

**不校验就拿不到数据**——因为数据只能从函数出来，表本身对这个角色不可见。这是 fail-closed，不是「记得加中间件」。

`_adjust` 要 `PLATFORM_APPROVER`，且 `p_reason` 非空、`p_idempotency_key` 非空。手工改余额是这个系统里最危险的操作，它必须留下比自动扣费更重的痕迹。

### 3.1 第一个管理员从哪来（自举问题）

不能靠 UI 自举：没有管理员就没人能授予管理员。三条路我推荐第二条。

| 方案 | 做法 | 问题 |
| --- | --- | --- |
| 迁移里硬写 | V73 里 INSERT 一个固定 account | 环境间不一致；测试库带着生产管理员；改一次要发一次迁移 |
| **`elmosctl` 运维命令**（推荐） | `apps/elmosctl` 已存在。加 `elmosctl platform-admin grant --account <id> --role PLATFORM_APPROVER --reason "..."`，走 DB 直连凭据，写 `platform_administrators` + `access_log` | 需要 DB 凭据——但这恰好是想要的门槛：能碰生产库的人本来就能改任何东西 |
| 环境变量引导 | 启动时读 `ELMOS_BOOTSTRAP_PLATFORM_ADMIN` | 变量泄漏即提权；容易忘记撤掉 |

第二个及以后的管理员：由已有 `PLATFORM_APPROVER` 在 `/admin` 里授予，理由必填，全程审计。

> **开放问题 Q1**：撤销自己 / 撤销最后一个管理员要不要拦？我倾向拦「撤销最后一个 APPROVER」（否则系统永久锁死，只能再开 DB），不拦「撤销自己」。要你拍板。

---

## 4. 任务扣费闭环 —— 本设计最需要评审的部分

### 4.1 入队门禁（新开）

`POST /api/v1/execution/jobs` 在算完 `digest`、写库**之前**插入：

```
quote      = priceBook.quote(businessLine, jobKind, budgetWallSeconds)
reservation = wallet.reserve(orgId, jobId, quote, actorId, expiresAt)
             ↳ 余额不足 → 402 ELMOS_WALLET_INSUFFICIENT_BALANCE
             ↳ 钱包冻结 → 403 ELMOS_WALLET_FROZEN
jobs.enqueue(...)
```

**预扣与入队必须同一个事务。** 否则要么钱扣了任务没进（用户丢钱），要么任务进了钱没扣（平台丢钱）。

> ✅ **已确认（U3）：同一个数据库，两个 DataSource、两套凭据。**
> `deploy/compose/docker-compose.local-commercial.yml` 里 `ELMOS_DATABASE_URL` 与 `ELMOS_COMMERCIAL_DATABASE_URL` 指向同一个 `postgres:5432/elmos`；但 `BillingDatabaseConfiguration` 用独立的 `HikariDataSource` + 独立用户名密码创建连接池，而 commercial-api 在库里的身份是 `elmos_billing_runtime`——一个**只被授予了 4 张表的 SELECT/INSERT** 的最小权限角色（V54、V62 的 GRANT 可查）。
>
> 两个直接结论：
> 1. **入队预扣可以同事务**（control-plane 自己的 DataSource 就能同时写 `execution_jobs` 和钱包表）。§4.1 按最简方案实现，不需要两阶段补偿。
> 2. **commercial-api 写不了钱包，这是好事。** 充值入账不要给它加表级 GRANT，只给它一个函数的 `EXECUTE`：`elmos_wallet_credit_topup(p_topup_order_id, p_provider_txn_ref, p_idempotency_key)`。支付服务能做的事被收敛成「把某笔已确认收款的订单入账」这一件，越权面积是一个函数签名，不是一张表。

### 4.2 终态结算（两个方案，需要你选）

任务终态目前由 Runner / 调度器写 `execution_jobs.status`，触发已有的 `elmos_guard_execution_job_transition`。

**方案 A：数据库触发器直接结算**
在 `execution_jobs` 进入终态时，触发器调用结算函数，按 `wallet_price_book` + 实际用量算钱，写 `CONSUME`/`RELEASE` 流水，改 `wallet_reservations`。
- 优点：**任何写入方都绕不过**，与仓库「把不变量放在无法被新调用方绕过的地方」的风格完全一致（`execution_jobs` 的终态不可变就是这么做的）。
- 缺点：计价逻辑进了 plpgsql；用量数据（token 数、实际时长）如果在事件表或 artifact 里，触发器要跨表读，容易长成一个难维护的存储过程。

**方案 B：触发器只落 outbox，结算器消费**（我倾向这个）
触发器只做两件极简的事：断言「该任务存在一笔 `HELD` 预扣」，并向 `wallet_settlement_outbox` 插一行。结算器（control-plane 的定时任务）读 outbox，算钱，调结算函数，幂等键 = `job_id`。
- 优点：计价留在 Java，可测；outbox 保证不丢；结算器挂了钱还冻着（安全的失败方向——冻着比错放要好）。
- 缺点：结算有延迟（秒级到分钟级），用户看到的可用余额短暂偏小。
- 兜底：预扣的 `expires_at` 仍然存在，结算器长期挂掉时预扣会过期释放（会少收钱，但不会错扣用户的钱——这个失败方向是刻意选的）。

四种终态的账务：

| 终态 | 账务 |
| --- | --- |
| `SUCCEEDED` / `PARTIAL` | 按实际用量结算，`CONSUME` ≤ 预扣，差额 `RELEASE` |
| `FAILED` | 默认全额 `RELEASE`。**除非** `failure_code` 属于「用户侧原因」清单（如输入非法、仓库不可达）——那部分收 `min_charge_minor` |
| `CANCELLED` | 已 RUNNING 的按已消耗结算，QUEUED 阶段取消全额释放 |
| `LOST` | 全额 `RELEASE` + 记一条运营告警（平台侧故障不向用户收费） |

> **开放问题 Q2**：`FAILED` 是否收费、哪些 `failure_code` 算用户侧，这是产品决策不是技术决策。默认全免最安全，但会被刷。要你定。

### 4.3 与订阅配额的关系（钱包与套餐并存）

扣费顺序固定为：**先套餐配额，后钱包余额**。

```
需要 X → quota_allocations 剩余配额能覆盖多少 → 覆盖部分不动钱包
                                           → 缺口部分从钱包预扣
```
两者都不够 → 拒绝入队，错误码区分「配额已尽且余额不足」和「纯余额不足」，前端提示不同（一个引导升级套餐，一个引导充值）。

这样订阅用户体感不变，纯预付费用户（没有订阅）全部走钱包，两条路都不用改对方。

---

## 5. 后台管理系统（扩展 `/admin`）

沿用现有 `authorizeAdmin` + 同源校验 + 有限白名单动作 + 代理层的形状（`operationsProxy.ts`），但注入的是**平台角色**而不是组织角色。

### 5.1 三块内容，但**不加新 tab**

> ✅ **已确认（U5）**：`OperationsAdmin.tsx`（2241 行，单组件）已有 `adminSections` 分区机制，八个分区里正好有三个是我要的家：
> `USERS 用户与租户` · `TASKS 任务队列` · `FINANCE 财务对账`。
>
> 所以**不新增 tab**，而是往既有分区里加内容——运营不用学新的导航，也不会出现「财务对账」和「钱包」两个看起来该合并的 tab。角色门禁复用 `roleRank`，只是把 VIEWER/OPERATOR/APPROVER 换成平台角色。

**① 账户余额** → 放进 `FINANCE`
组织列表：余额 / 冻结中 / 近 30 天充值 / 近 30 天消耗 / 状态 / 最后活动时间。支持按组织名、account 邮箱、余额区间检索。行内下钻 → 流水明细（分页、按类型筛选）。`PLATFORM_APPROVER` 可发起手工调整（金额 + 方向 + 原因必填 + 二次确认 + 展示将产生的流水预览）。

**② 充值与对账** → 放进 `FINANCE`（与已有对账内容同屏）
充值订单列表（状态、渠道、金额、发起人）；重点是 **`PAID` 但未 `CREDITED`** 的挂单——这一栏应该常年为空，非空即事故。与已有 `payment_reconciliation_cases` / `payment_unmatched_callbacks` 打通，一个页面能看到「收了钱没入账」和「有回调找不到订单」两类缺口。

**③ 任务执行** → 放进 `TASKS`（现有组织内视图旁边加一个「全平台」开关）
跨组织任务视图：按状态/业务线/组织/时间筛选，状态分布、失败码 Top N、P50/P95 时长、当前排队深度。单任务下钻显示事件流（`execution_job_events`）+ 该任务的预扣与结算流水——**把「这个任务花了多少钱」和「这个任务跑成什么样」放在同一屏**，这是现在完全没有的视角。可取消任务（`PLATFORM_OPERATOR`）。

### 5.2 API 契约

用户侧（组织会话）：
```
GET  /api/wallet                      余额 + 冻结 + 最近流水
GET  /api/wallet/ledger               分页流水
POST /api/wallet/topup                创建充值订单 → 返回支付跳转/二维码
GET  /api/wallet/topup/{orderId}      订单状态轮询
```
管理端（平台会话）：
```
GET  /api/admin/wallets                              跨组织余额列表
GET  /api/admin/wallets/{organizationId}/ledger      单组织流水
POST /api/admin/wallets/{organizationId}/adjust      手工调整（APPROVER）
GET  /api/admin/topups                               充值订单 + 挂单
GET  /api/admin/execution-jobs                       跨组织任务
POST /api/admin/execution-jobs/{jobId}/cancel        取消（OPERATOR）
GET/POST/DELETE /api/admin/platform-admins           管理员授予与撤销（APPROVER）
```

> ✅ **已确认（U4）：现有 `/api/admin/jobs` 是组织内的，跨组织确实是新能力。**
> 它代理到 control-plane 的 `/api/v1/operations-observability/jobs`，而那个 controller 的**每个**端点都要 `@RequestHeader("X-ELMOS-Organization-ID")` 并对该 org 授权。所以 `/api/admin/execution-jobs` 是新建，不是扩展——但**响应形状和筛选参数应该照抄** `operationsJobsPolicy.ts` 的既有约定，让前端两套视图共用一套渲染。

---

## 6. 迁移、回滚与并发

- 单个 `V73__wallet_topup_and_platform_administration.sql`，前向 only（仓库既有约定：forward-only migration）。
- 新表全是新增，**不改任何已有表的列**——除非 U2 的结论是复用 `payment_checkout_sessions`，那时会用 V49 的 `ADD COLUMN + shape CHECK` 手法（历史行保持合法），而不是改已有列。
- 回滚策略：钱包功能由一个特性开关控制入队门禁。开关关闭时 `enqueue` 不预扣，行为与今天完全一致——**这是真正的回滚路径**，因为流水账 append-only，删数据不是选项。
- 并发：`wallet_accounts` 行级锁（`SELECT ... FOR UPDATE`）序列化同一组织的记账；跨组织无竞争。`UNIQUE (organization_id, idempotency_key)` 兜住所有重放。
- **抢版本号**：动手前重查最高迁移号；`.ai/` 下先写认领文件（这个仓库有多会话并行写入的前科）。

---

## 7. 验收证据（这个仓库的标准）

不接受「文件存在」当完成。每条要有实跑记录：

1. **迁移契约测试**：照 `SelfServiceBillingMigrationContractTest` / `FlywayMigrationTest` 的形状，真 PostgreSQL 17.5 起库，验证全部 CHECK、append-only 触发器、终态不可改写触发器**确实拒绝**非法写入（不是「代码里写了」）。
2. **记账不变量属性测试**：随机生成充值/预扣/结算/释放序列，断言 `balance_minor == SUM(ledger)` 且 `balance_after_minor` 链条自洽，且 `reserved_minor == SUM(HELD)`。
3. **并发扣费**：两个线程对同一组织同时预扣、总额超过余额 → 必须恰好一个成功（照 `EnterpriseGovernanceTest` 里对 `UsageAndAuditGovernance` 的并发断言写法）。
4. **回调重放**：同一支付回调投递三次 → 只产生一条 `TOPUP_SETTLED`。
5. **越权**：非管理员 account 调 `elmos_platform_*` 函数 → 拒绝且 `access_log` 有 `DENIED` 记录；管理员读 A 组织 → `access_log` 有对应行。
6. **端到端**：注册 → 充值 → 提交任务 → 余额被冻结 → 任务完成 → 结算 → 管理员在 `/admin` 看到这笔账。
7. **零回归**：现有 `execution_jobs`、billing、identity 测试全绿（开关关闭与开启各跑一遍）。

---

## 8. 分阶段交付建议

| 阶段 | 内容 | 可独立验证 |
| --- | --- | --- |
| P1 | V73 迁移 + 记账函数 + 契约/不变量/并发测试 | 是（不接线，纯数据层） |
| P2 | 充值订单 + 支付网关接线 + 回调入账 | 是（充值能到账） |
| P3 | 入队预扣 + 终态结算（特性开关默认关） | 是（开关两态各跑一遍） |
| P4 | 平台管理员 + `elmosctl` 授予 + 跨组织函数 | 是（越权用例） |
| P5 | `/admin` 三面板 + 用户侧钱包页 | 是（端到端） |

---

## 9. 需要你拍板 / 我需要回读确认的清单

**要你决定：**
- **Q1** 撤销最后一个 `PLATFORM_APPROVER` 是否拦截（我倾向拦）
- **Q2** `FAILED` 任务是否计费、哪些 `failure_code` 算用户侧（我倾向默认全免）
- **Q3** §4.2 结算方案 A（DB 触发器直接结算）还是 B（outbox + 结算器，我倾向 B）
- **Q4** 充值下限/上限/单日限额的默认值

**已回读确认（U1–U5 全部落定，其中两条改变了设计）：**

| | 结论 | 对设计的影响 |
| --- | --- | --- |
| U1 | 注册自动建组织（`provisionFirstOrganization`），并有 `trial_grants` 的真人唯一锚点 | 注册流程不用改；首充赠送必须复用该锚点 |
| U2 | `payment_checkout_sessions` 绑死 `plan_id NOT NULL` + 仅 `STRIPE_CHECKOUT` | **不能复用**，新建充值订单表（削弱既有约束比新建一张表危险） |
| U3 | 同一个库，但 commercial-api 是最小权限角色 `elmos_billing_runtime` | **改设计**：入队预扣可同事务（不用两阶段）；充值入账只给一个函数的 EXECUTE，不给表权限 |
| U4 | `/api/admin/jobs` 经由 `operations-observability` 强制带 org 头，是组织内的 | 跨组织视图确属新建，但响应形状照抄既有约定 |
| U5 | `adminSections` 已有 `USERS`/`TASKS`/`FINANCE` 三个分区 | **改设计**：不加新 tab，内容并进既有分区 |

> 起草时这五条我只读到了「存在」的层面。这个仓库有过明确教训：**「代码不存在」这类判断可靠，「行为不支持」这类判断只读一层就下断言会翻车**。所以我先把它们标成待验证、再逐条回读——结果 U3 和 U5 确实推翻了初稿写法（U3 原本准备写两阶段补偿，U5 原本准备加三个 tab），两处都是「不验证就会多写一堆不该写的代码」。

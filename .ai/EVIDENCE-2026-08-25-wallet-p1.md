# P1 执行证据：V73 钱包数据层

> 2026-08-25 · 云端会话容器 · 真实 PostgreSQL 执行，非推断
> **本文档已修订一次**：第一版的证据是以超级用户跑的，而超级用户绕过 RLS，
> 因此它证明的东西比它看起来少得多。修订过程见 §6，那一节是本文最重要的部分。

## 环境与其边界

| 项 | 实际 |
| --- | --- |
| 数据库 | PostgreSQL **16.13**（Ubuntu 24.04 仓库版），`initdb` 起的本地实例 |
| 仓库钉的版本 | PostgreSQL **17.5** |
| 迁移应用方式 | `psql -v ON_ERROR_STOP=1` 按 V1→V73 顺序全量应用（**不是** Flyway） |

**版本差异**：云端 apt 源没有 17，用的是 16.13。本迁移用到的特性（`FORCE ROW LEVEL SECURITY`、
`BEFORE` 触发器、`SECURITY DEFINER` + `SET search_path`、`FOR UPDATE SKIP LOCKED`、
`make_interval`、`set_config` 事务局部作用域、窗口函数）在 16 与 17 语义相同，
但**这不构成 17.5 上的证据**。`FlywayMigrationTest` 用 Testcontainers 拉
`postgres:17.5-alpine`，需要 Docker，云端没有——17.5 + Flyway 的复验只能在你 Mac 上跑。

## 1. 全量迁移应用

73 个文件按序零错误应用。V73 与既有 72 个迁移无对象名冲突、无 FK 冲突、无角色冲突。

## 2. 行为断言（超级用户，15 组，全通过）

每一条「必须被拒绝」都真的发起了非法写入并断言数据库拒绝，不是断言 SQL 文本里写了这条规则。

| 编号 | 断言 | 结果 |
| --- | --- | --- |
| T01 | 钱包重复开户幂等 | 1 行，余额 0 |
| T02 | 充值回调重放 3 次 | 余额 100000，**流水恰好 1 条** |
| T03 | 预扣改变可用额不改变余额 | 100000 / 30000 / 可用 70000 |
| T03b | **持有不是资金流动** | 预扣后流水仍 1 条 |
| T04 | 同任务重复预扣幂等 | reserved 仍 30000 |
| T05 | 超额预扣按**可用额**判定 | `INSUFFICIENT_BALANCE` |
| T06 | 结算按实收扣、余额返还 | 88000 / 0 / settled 12000 |
| T06b | 结算器重试不二次扣费 | CONSUME 流水 1 条 |
| T07 | 报价超预扣被**钳位** | 报 999999，实扣 5000 |
| T08 | 释放全额退回、不产生流水 | reserved 0，`RELEASED` |
| T09 | 过期清扫 | `EXPIRED`，reserved 归 0 |
| T10a–k | **11 条非法写入全部被拒** | 见下 |
| T11 | 带原因的调整幂等 | 1 条，原因落盘 |
| T12 | 投影 = 权威 | 两列 drift 均 0 |
| T12b | 流水按 seq 重放自洽 | `chain_intact = t` |
| T13 | 充值限额默认值与租户覆写 | 生效 |
| T14 | RLS | 5 张租户表 `rls=t forced=t policy=1` |
| T15 | 种子价格 | 5 条全 `DRAFT` |

11 条拒绝的原始错误码：

```
ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED   直接改 balance_minor
ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED   直接改 reserved_minor
ELMOS_WALLET_DELETE_DENIED                    删钱包
append-only table wallet_ledger_entries ...   改流水
append-only table wallet_ledger_entries ...   删流水
ELMOS_WALLET_RESERVATION_TERMINAL_IMMUTABLE   把已结算的预扣改回 HELD
ELMOS_WALLET_RESERVATION_AMOUNT_IMMUTABLE     改预扣金额
ELMOS_WALLET_TOPUP_AMOUNT_IMMUTABLE           改已入账充值单金额
ELMOS_WALLET_ADJUSTMENT_REASON_REQUIRED       无原因的人工调整
append-only table wallet_price_book ...       改价目表
ELMOS_WALLET_INSUFFICIENT_BALANCE             扣成负数
```

最终账面自证：

```
TOPUP_SETTLED    CREDIT 100000  balance_after 100000  seq 1
CONSUME          DEBIT   12000  balance_after  88000  seq 2
CONSUME          DEBIT    5000  balance_after  83000  seq 3
ADMIN_ADJUSTMENT CREDIT   2500  balance_after  85500  seq 4
reconcile: projected 85500 = ledger 85500;  reserved 0 = held 0
```

## 3. 并发预扣

8 个**独立进程**同时对余额 100000 的钱包各预扣 30000：

```
succeeded=3  refused=5
reserved=90000  balance=100000  drift=0
```

关键不是「有失败」，而是**成功的那几笔加起来没超过余额**——丢失更新会破坏的正是这条。

## 4. 生产化角色下的完整复跑（修订后新增，也是最要紧的一组）

把钱包表与函数的属主换成 **NOSUPERUSER、无 BYPASSRLS** 的 `elmos_owner_prod`，
应用角色 `elmos_app_prod` **只有函数 EXECUTE，一张钱包表都没有**。全部通过：

| 编号 | 断言 | 结果 |
| --- | --- | --- |
| P01 | **无租户上下文**开钱包（支付回调场景） | 成功 |
| P02 | 下单 + 同幂等键重放 | 返回同一订单 |
| P02a | 回调在拿到租户上下文**之前**解析出租户 | 目录表命中 `org-p1` |
| P02b | 目录状态跟随订单 | `CREDITED` |
| P03 | 无上下文下预扣/结算/释放 | 全部成功 |
| P04 | 按租户过期清扫 | `expired=1`，reserved 归 0 |
| P05 | 对账 | 两列 drift 均 0 |
| P06 | **绑定的租户不泄漏出函数** | 调用后上下文 `<unset>` |
| P07 | A 租户去入账 B 租户的充值单 | `TOPUP_UNKNOWN` |
| P08 | 应用角色直接读钱包表 / 流水表 | `permission denied`（两次） |
| P09 | 空租户参数 | `TENANT_REQUIRED` |
| P11 | 单笔下限 / 单笔上限 / 单日累计上限 | 三条全部被拒 |

## 5. 租户隔离（普通角色，带表权限的那种）

另建一个**有表权限**的普通角色验证 RLS 本身：

| 场景 | 结果 |
| --- | --- |
| 绑 `org-w1` 读钱包 | 只看到 `org-w1` |
| 绑 `org-race` 读钱包 | 只看到 `org-race` |
| **不绑**租户读钱包 | **0 行**（fail-closed） |
| 读别人组织的流水 | 0 行 |
| 插入别人组织的流水 | `new row violates row-level security policy` |
| 读结算 outbox | `permission denied` |
| 直接调 `elmos_wallet_adjust` 给自己加钱 | `permission denied for function` |

## 6. 修订过程：三个真缺陷，两个在我自己的代码里

### 6.1 第一版证据是以超级用户跑的，而超级用户绕过 RLS

第一版 §2/§3 全绿，但它们是 `psql -U postgres` 跑的。超级用户**完全不受 RLS 约束**，
所以那一整轮**根本没有触碰**「FORCE RLS 与 SECURITY DEFINER 如何相互作用」这个问题——
而钱包的每一张表都是 FORCE RLS。

把属主换成非超级用户后实测：

```
$ SELECT elmos_wallet_open('org-rls');       -- 未设 app.organization_id
ERROR: new row violates row-level security policy for table "wallet_accounts"
```

`FORCE ROW LEVEL SECURITY` 的字面含义就是**连表属主也受策略约束**，
而 SECURITY DEFINER 函数是以属主身份运行的。所以第一版的 V73 在
「属主非超级用户」的部署里，**每一个记账函数都会失败**。

**教训**：用超级用户跑安全相关的验证，等于没跑。

### 6.2 支付回调根本查不到充值单（与 V62 修过的是同一个 bug）

顺着 `JdbcOrderPorts` 的注释读到了这段既有记录：`payment_checkout_sessions` 是 FORCE RLS，
回调到达时组织未知、设不了 `app.organization_id`，策略于是求值成 `organization_id = NULL`，
**一行都不返回**——症状是「每一笔回调都判成 ORDER_UNKNOWN，全部进滞留表，
没有一个订阅会被开通」，而且**静默**：回调返回 400，提供方持续重发。

我的 `wallet_topup_orders` 同样是 FORCE RLS，会得到**一模一样的结果**。

修法照抄 V62 + V64 的既有方案，没有另发明：
- 新增 `wallet_topup_order_directory`——只含 `out_trade_no → 组织/金额/状态` 的最小投影，
  **有意不加 RLS**，理由与 `payment_order_directory` 逐字相同；
- 由触发器维护而不是应用双写（双写总有人会忘，忘了的后果只在生产收到真实回调时才暴露）；
- 触发器函数按 **V64** 的形状：`SECURITY DEFINER` + `SET search_path = pg_catalog, public, pg_temp`
  + 目标 schema 限定 + `REVOKE ALL ... FROM PUBLIC`。V64 存在的原因正是 V62 的触发器
  以调用方身份运行、而运行角色没有目录表写权限。

### 6.3 跨租户清扫器会「成功地清扫零行」

我最初把过期清扫写成跨租户全表扫描。在 FORCE RLS 下没绑租户就是 0 行——
**清扫器会返回成功，什么也没扫到，钱一直冻着，任何地方都没有报错**。
这是可选失败模式里最坏的一种。改成按租户驱动（`organizations` 表本身不受 RLS 约束，
调用方逐租户调一次）。

> 顺带一个**我没有改、需要你判断**的观察：既有的 `elmos_reap_execution_leases`（V52）
> 用的正是「跨租户扫描 + 直接改 FORCE RLS 的 `execution_jobs`」这个写法，
> 没有绑定任何租户上下文。它能工作的前提是**属主具备超级用户或 BYPASSRLS**。
> 这个前提我无法从代码里验证，也不该顺手改别人的调度器。
> 如果你们的迁移属主确实是超级用户，那它没问题、我的 6.1 也就只是「更稳健」而非「必须」；
> 如果不是，那条清扫器可能一直在静默空转。**建议在 Mac 上查一下属主角色。**

### 6.4 修的结果：现在 V73 不依赖任何部署属性

每个记账函数自己绑定它被显式告知的那个租户，用完把原值放回去
（`set_config(..., true)` 事务局部，绝不会跨连接泄漏——P06 实测确认）。
无论属主是不是超级用户，行为一致。

### 6.5 另外三次「以为是代码缺陷，其实是我测试写错了」

| 现象 | 真相 |
| --- | --- |
| 「12 个 SECURITY DEFINER 只有 10 个钉了 search_path」 | 多出来的 2 次在 **COMMENT 正文**里。10 个真函数全钉了。**改的是测试** |
| 过期清扫测试报 CHECK 违反 | 我只把 `expires_at` 拨到过去，`expires_at > held_at` 拦住了。**约束是对的** |
| 单日限额提前一笔触发 | 我算漏了开头那笔 100000 充值。**函数是对的** |

三次都是「先怀疑自己的测试」而不是顺手改实现。第一次尤其危险：
如果当时往迁移里补两行 `SET search_path`，会加在语法上不该有的位置，
而真正的问题——测试会因为文档而失败——还在。

## 7. 交付物

| 文件 | 性质 | 状态 |
| --- | --- | --- |
| `V73__wallet_prepaid_balance_and_topup.sql` | 迁移 | **已实跑验证** |
| `wallet_behaviour_test.sql` | 不变量与拒绝断言（超级用户视角） | **已实跑，全通过** |
| `wallet_prod_role_test.sql` | 生产化角色下的完整复跑 | **已实跑，全通过** |
| `WalletMigrationContractTest.java` | 纯文本断言，不需数据库 | **已写，未编译** |
| `WalletLedgerLiveTest.java` | 真库，env 门控 | **已写，未编译** |

**诚实标注**：两个 Java 文件在本会话**没有编译也没有运行**——云端拉不动
`modules/persistence` 的 Maven 依赖树。SQL 层的结论是实跑的，Java 层的不是。

## 8. 需要你在 Mac 上做的

- [ ] `mvn -pl modules/persistence test`：编译并跑两个 Java 测试
- [ ] `FlywayMigrationTest`：**PostgreSQL 17.5 + Flyway + Docker** 全量复验
- [ ] 确认 `tenant_isolation >= 1239` 下界断言仍通过（新增 5 条策略，只增不减）
- [ ] **查一下迁移属主角色是否 superuser / BYPASSRLS**——这决定 §6.3 末尾那个观察是不是一个真问题

## 9. 与设计稿的两处偏离

1. **流水只记真实资金流动**（`TOPUP_SETTLED` / `CONSUME` / `REFUND` / `ADMIN_ADJUSTMENT` /
   `TRIAL_GRANT`），`RESERVE` / `RELEASE` 不进流水，只是 `wallet_reservations` 的状态迁移。
   理由：把「为一个还没跑的任务占住钱」写成流水，会让 `balance_after_minor` 在不同行上
   表达两种含义，账就没法靠重放自证——而 T12b 那条断言正是靠它成立的。

2. **新增 `elmos_wallet_create_topup_order` 函数**，下单不再是裸 INSERT。
   除了租户上下文这个机械原因，更重要的是：单笔上下限和单日累计上限是
   「打错一个零」和「洗钱通道」之间的区别，写在应用代码里的限额就是下一个调用方会忘掉的限额。

# P1 执行证据：V73 钱包数据层

> 2026-08-25 · 云端会话容器 · 真实 PostgreSQL 执行，非推断

## 环境与其边界

| 项 | 实际 |
| --- | --- |
| 数据库 | PostgreSQL **16.13**（Ubuntu 24.04 仓库版），`initdb` 起的本地实例 |
| 仓库钉的版本 | PostgreSQL **17.5** |
| 迁移应用方式 | `psql -v ON_ERROR_STOP=1` 按 V1→V73 顺序全量应用（**不是** Flyway） |

**版本差异的诚实说明**：本轮用的是 16.13，不是仓库钉死的 17.5——云端 apt 源没有 17。
本迁移用到的全部特性（`FORCE ROW LEVEL SECURITY`、`BEFORE` 触发器、`SECURITY DEFINER` +
`SET search_path`、`FOR UPDATE SKIP LOCKED`、`make_interval`、`set_config` 事务局部作用域、
窗口函数）在 16 与 17 语义相同，但**这不构成 17.5 上的证据**。
`FlywayMigrationTest` 用 Testcontainers 拉 `postgres:17.5-alpine`，需要 Docker，云端没有——
**17.5 + Flyway 的复验只能在你 Mac 上跑**，见文末。

## 1. 全量迁移应用

```
$ for f in V1..V73; do psql -v ON_ERROR_STOP=1 -f $f; done
ALL 73 APPLIED OK
```

73 个文件零错误、零警告（除 `drop database if exists` 的 NOTICE）。V73 与既有 72 个迁移
无对象名冲突、无 FK 冲突、无角色冲突。

## 2. 行为断言（`wallet_behaviour_test.sql`，15 组）

全部通过。**每一条「必须被拒绝」都是真的发起了非法写入并断言数据库拒绝**，
不是断言 SQL 文本里写了这条规则。

| 编号 | 断言 | 实测结果 |
| --- | --- | --- |
| T01 | 钱包重复开户幂等 | 1 行，余额 0 |
| T02 | 充值回调重放 3 次 | 余额 100000，**流水恰好 1 条**，订单 `CREDITED` |
| T03 | 预扣改变可用额不改变余额 | balance 100000 / reserved 30000 / spendable 70000 |
| T03b | **持有不是资金流动** | 预扣后流水仍是 1 条 |
| T04 | 同一任务重复预扣幂等 | reserved 仍 30000，未变 60000 |
| T05 | 超额预扣按**可用额**而非余额判定 | `ELMOS_WALLET_INSUFFICIENT_BALANCE` |
| T06 | 结算按实收扣、余额返还 | balance 88000 / reserved 0 / settled 12000 |
| T06b | 结算器重试不二次扣费 | balance 仍 88000，CONSUME 流水 1 条 |
| T07 | 报价超过预扣被**钳位** | 报 999999，实扣 5000（＝预扣额） |
| T08 | 释放全额退回且不产生流水 | reserved 0，状态 `RELEASED` |
| T09 | 过期清扫释放无人处置的预扣 | 状态 `EXPIRED`，reserved 归 0 |
| T10a–k | **11 条非法写入全部被拒**（见下） | 见下 |
| T11 | 带原因的调整幂等 | 1 条 `ADMIN_ADJUSTMENT`，原因已落盘 |
| T12 | 投影 = 权威 | `balance_drift=0`，`reserved_drift=0` |
| T12b | 流水链自洽（按 seq 重放） | `chain_intact = t` |
| T13 | 充值限额默认值与租户覆写 | 默认 100/5000000/20000000；覆写生效 |
| T14 | RLS 状态 | 5 张租户表全部 `rls=t forced=t policy=1` |
| T15 | 种子价格 | 5 条全部 `DRAFT` |

### T10 的 11 条拒绝（原始错误码）

```
ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED     直接改 balance_minor
ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED     直接改 reserved_minor
ELMOS_WALLET_DELETE_DENIED                      删钱包
append-only table wallet_ledger_entries ...     改流水
append-only table wallet_ledger_entries ...     删流水
ELMOS_WALLET_RESERVATION_TERMINAL_IMMUTABLE     把已结算的预扣改回 HELD
ELMOS_WALLET_RESERVATION_AMOUNT_IMMUTABLE       改预扣金额
ELMOS_WALLET_TOPUP_AMOUNT_IMMUTABLE             改已入账充值单金额
ELMOS_WALLET_ADJUSTMENT_REASON_REQUIRED         无原因的人工调整
append-only table wallet_price_book ...         改价目表
ELMOS_WALLET_INSUFFICIENT_BALANCE               扣成负数
```

### 最终账面（自证）

```
entry_type       | direction | amount | balance_after | seq
TOPUP_SETTLED    | CREDIT    | 100000 |        100000 |   1
CONSUME          | DEBIT     |  12000 |         88000 |   2
CONSUME          | DEBIT     |   5000 |         83000 |   3
ADMIN_ADJUSTMENT | CREDIT    |   2500 |         85500 |   4

elmos_wallet_reconcile():  projected 85500 = ledger 85500,  reserved 0 = held 0
```

## 3. 并发预扣（这条是重点）

8 个**独立进程**同时对同一个余额 100000 的钱包各预扣 30000：

```
succeeded=3  refused=5
reserved=90000  balance=100000  spendable=10000
held_rows=3
drift=0  over_committed=false
```

余额只能背 3 笔，就恰好成了 3 笔。5 笔被 `ELMOS_WALLET_INSUFFICIENT_BALANCE` 拒。
关键不是「有失败」，而是**成功的那几笔加起来没超过余额**——丢失更新会破坏的正是这条。

## 4. 租户隔离（用真实非超级用户角色验证）

超级用户会绕过 RLS，所以这一组专门建了 `elmos_app_test` 普通角色来跑：

| 场景 | 结果 |
| --- | --- |
| `SET app.organization_id='org-w1'` 读钱包 | 只看到 `org-w1 85500` |
| `SET app.organization_id='org-race'` 读钱包 | 只看到 `org-race 100000` |
| **不设** `app.organization_id` 读钱包 | **0 行**（fail-closed，不是全表） |
| 租户读别人组织的流水 | 0 行 |
| 租户插入一条别人组织的流水 | `ERROR: new row violates row-level security policy` |
| 租户读结算 outbox | `ERROR: permission denied for table wallet_settlement_outbox` |
| 租户直接调 `elmos_wallet_adjust` 给自己加钱 | `ERROR: permission denied for function elmos_wallet_adjust` |

最后两条是这套设计的要害：**跨租户表和记账函数对租户角色根本不存在**，
所以「忘了加权限校验」这个失败模式在这里不成立。

## 5. 两个测试文件

| 文件 | 性质 | 本轮状态 |
| --- | --- | --- |
| `WalletMigrationContractTest.java` | 纯文本断言，不需要数据库，任何机器可跑 | **已写，未编译**（云端无 Maven 依赖） |
| `WalletLedgerLiveTest.java` | 真库，env 门控（`ELMOS_WALLET_TEST_JDBC_URL` + `ELMOS_WALLET_TEST_DISPOSABLE_CONFIRMED`），把上面第 2/3 节机器化 | **已写，未编译** |

**诚实标注**：这两个 Java 文件在本会话**没有编译也没有运行**——云端拉不动
`modules/persistence` 的 Maven 依赖树。SQL 层的结论是实跑的，Java 层的结论不是。

### 写测试时抓到的一件事（值得记）

`everySecurityDefinerFunctionPinsItsSearchPath` 第一版按**出现次数**统计，
报出「12 个 SECURITY DEFINER，只有 10 个钉了 search_path」——看起来就是两个函数漏钉，
是个真安全缺陷的形状。逐行核对后发现多出来的 2 次在 **COMMENT 正文里**，
10 个真函数全部钉了。

**改的是测试，不是迁移。** 如果当时顺手往迁移里加两行 `SET search_path`，
会加在语法上不该有的位置，而且真正的问题——「测试会因为文档而失败」——还在。
已按函数块重写统计，并把这段经过写进了测试注释里。

## 6. 还没做 / 需要你在 Mac 上复验

- [ ] `mvn -pl modules/persistence test`：编译并跑上面两个 Java 测试
- [ ] `FlywayMigrationTest`：**PostgreSQL 17.5 + Flyway + Docker** 的全量复验（云端做不到）
- [ ] 确认 `FlywayMigrationTest` 里 `tenant_isolation >= 1239` 的下界断言仍通过（新增 5 条策略，只增不减，预期通过）

## 7. 与设计稿的一处偏离

设计稿把 `RESERVE` / `RELEASE` 列为流水类型。**实现时改了**：流水只记真实资金流动
（`TOPUP_SETTLED` / `CONSUME` / `REFUND` / `ADMIN_ADJUSTMENT` / `TRIAL_GRANT`），
预扣与释放只是 `wallet_reservations` 的状态迁移。

理由：把「为一个还没跑的任务占住钱」写成一条流水，会让 `balance_after_minor`
在不同行上表达两种不同含义，账就没法靠重放自证了——而 T12b 那条断言正是靠它成立的。
代价是查「当前冻结了多少」要读 `wallet_reservations` 而不是流水，这个代价划算。

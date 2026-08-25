# P3 执行证据：V74 任务扣费闭环

> 2026-08-25 · 真实 PostgreSQL 16.13 执行 + 真编译真跑的策略验证

## 这一轮做了什么

把钱包接进任务队列：入队时预扣，终态时结算。门禁放在
`elmos_enqueue_execution_job` **函数内部**——那是既有并发额度检查所在的位置，
也是任何一行进 `execution_jobs` 的唯一通路。放控制器里的门禁是下一个调用方会忘掉的门禁；
放这里还白送了原子性：预扣和插入天然同事务，「扣了钱没任务」和「有任务没扣钱」
两种状态都**不可表示**，而不只是不太可能。

**默认关。** `wallet_enforcement_settings.enabled` 初始为 false，所有路径在它上面短路。

## 1. 「只加不改」是机器验证的，不是我说的

把 V74 里的 `elmos_enqueue_execution_job` 与 V52 原版做 diff：

```
新增 11 行，删除 0 行
删除的行：（无）
新增的行里只有 3 行是代码：
    PERFORM elmos_wallet_admit_job(
        p_organization_id, p_job_id, p_actor_id,
        p_business_line, p_job_kind, p_budget_wall_seconds);
```

其余 8 行是解释这 3 行为什么放在这个位置的注释。

## 2. 数据层实测（74 个迁移，全绿）

| 编号 | 断言 | 结果 |
| --- | --- | --- |
| C1 | 开关默认关 | `enabled = f` |
| C1a | 关时有订阅租户入队 | 成功，**预扣 0 笔** |
| C1b | 关时无套餐租户入队 | `NO_ACTIVE_ENTITLEMENT`——与 V74 之前逐字相同 |
| C1c | 关时任务进终态 | **outbox 0 行** |
| C2 | 开关打开，但价格还是 DRAFT | `NO_PUBLISHED_PRICE`，fail closed |
| C2b | 报价随预算缩放 | 3600s → 3600 分；60s → 落到地板价 500 分 |
| C3 | 并发额度 | 有套餐 3、有余额 1、空钱包 0 |
| C3a | 预扣后 | 余额 500000 不变，冻结 3600，可用 496400 |
| C3b | 重试入队 | 返回原任务，**持有仍 1 笔** |
| C3c | 有订阅租户 | 配额覆盖，**预扣 0 笔** |
| C4 | 余额不足 | `INSUFFICIENT_BALANCE` |
| C4a | 拒绝的原子性 | jobs/dispatch/events/holds **四张表全 0 行** |
| C5 | 终态 | outbox 恰好 1 行 |
| C5a | 结算依据 | `elapsed=400s`（排队时间不算，那是我们的延迟不是他们的） |
| C5b | claim → resolve | 首次 `t`，重复调用 `f`（幂等） |
| C5c | 扣费结果 | 余额 499600，冻结 0，流水 1 条 CONSUME 400 |
| C6 | `RUNNER_OOM` 失败 | 不在可计费清单 → `RELEASED`，无新流水 |
| C7 | 开关关回去 | 并发额度回到 0，行为复原 |
| C8 | 不变量 | 两个租户 drift 均为 0 |

C4a 是这一组里最要紧的一条：**余额不足时，被拒的任务在四张表里一行痕迹都没留下。**

## 3. 生产化角色下的复验，抓到我自己的一个缺陷

把钱包 + 执行队列的对象属主换成 **NOSUPERUSER、无 BYPASSRLS** 的角色后重测：

```
配额余量 org-sub  = 600000
配额余量 org-pre  = 0
并发额度 org-sub  = 3   （套餐给的）
并发额度 org-pre  = 1   （钱包给的）
并发额度 org-broke= 0   （空钱包，fail closed）
admit_job(org-sub) = NULL → 配额覆盖，未动钱包
org-sub 预扣笔数    = 0
调用后租户上下文    = <未设置，无泄漏>
```

**修之前 `配额余量 org-sub` 会是 0。** 我把 `elmos_wallet_allowance_remaining`
写成了 `LANGUAGE sql STABLE` 且没绑租户，而 `quota_allocations` 和 `subscriptions`
都是 FORCE RLS。非超级用户属主下它对所有人返回 0——而 0 **不像故障，像「这个租户配额用完了」**。
可见症状会是：**有订阅的租户被悄悄从钱包扣钱，为他们套餐已经覆盖的工作付费。**

与 V62 那个回调 bug 同一族：查询返回空，没有任何东西报错。

同一轮里还顺手加固了 `elmos_execution_concurrency_limit`（V52 原版读 `subscriptions`
也没绑租户，只在属主能绕过 RLS 时才成立），并把两个绑租户的函数从 `STABLE` 降为 VOLATILE
——一个会设 GUC 的函数声明成 STABLE 是不诚实的。

## 4. 结算策略：真编译、真运行

`WalletSettlementPort` 和 `WalletSettlementService` **零外部依赖**，
所以这两个文件在云端做了真正的 `javac` 全量编译，并用一个无 JUnit 的驱动跑完了
与 `WalletSettlementServiceTest` 一一对应的 17 条断言：

```
PASS  成功任务按实跑秒数计费                    400 = 400
PASS  成功任务的收费上限是预扣额                3600 = 3600
PASS  极短运行仍收保底                          50 = 50
PASS  PARTIAL 按已做的工作计费                  300 = 300
PASS  普通失败不收费                            0 = 0
PASS  普通失败的处置码                          FAILED_NOT_CHARGED
PASS  被显式归为用户侧的失败收保底              50 = 50
PASS  启动前取消免费                            0 = 0
PASS  运行中取消按已跑计费                      250 = 250
PASS  Runner 丢失是平台的错，不收费             0 = 0
PASS  任务不见了则释放而不是猜                  JOB_NOT_FOUND
PASS  无法计价的条目不被草率结掉                resolved=0 failed=1
PASS  且确实一条都没结算                        0
PASS  失败码被记下                              ELMOS_WALLET_SETTLEMENT_UNEXPECTED_STATUS
PASS  一条坏的不挡住整批                        resolved=2 failed=1

======== 结算策略 17/17 全部通过 ========
```

### 真编译抓到的一个错（语法检查抓不到）

`FakePort` 实现了 `claim(int, int)`，而外层有个静态辅助方法也叫 `claim()`。
Java 的内部类里，同名方法会**遮蔽**外层方法——`List.of(claim())` 于是解析到
`claim(int,int)` 并报参数不匹配。

纯语法解析（`JavacTask.parse()`）对这个是无感的，只有真编译才会报。
已把外层改名为 `aClaim`，并在测试里留了一行注释说明原因，免得下个人改回去。

## 5. 失败的方向是刻意选的

结算的每一条分支要么按**实测**工作量收费、要么释放，**没有任何一条「保险起见按预扣全收」**。
结算器要是彻底停了，持有会按 TTL 过期、钱回到租户手里——我们少收。

这是有意的：因为我们的结算器挂了而多收客户的钱，是一场退款对话加一次信任损失；
少收只是仪表盘上的一个数字。

## 6. 交付物

| 文件 | 性质 | 验证到什么程度 |
| --- | --- | --- |
| `V74__wallet_execution_charging.sql` | 迁移 | **真库实跑，18 组断言 + 生产化角色复验** |
| `wallet_charging_test.sql` | 断言脚本 | **实跑全绿** |
| `WalletSettlementPort.java` | 端口 | **真编译通过** |
| `WalletSettlementService.java` | 结算策略 | **真编译 + 17 条断言真跑** |
| `WalletSettlementServiceTest.java` | JUnit 测试 | 语法解析通过；断言逻辑已由驱动等价验证 |
| `JdbcWalletSettlementStore.java` | JDBC 适配 | 语法解析通过，**未编译**（需 Spring 依赖） |

## 7. 还没做

- [ ] 结算器的定时触发（Spring `@Scheduled` runner），接进 control-plane
- [ ] `mvn` 全量编译与 JUnit 实跑——云端 Maven Central 被代理挡着
- [ ] PostgreSQL **17.5** 上的复验（云端只有 16.13）
- [ ] 开关打开后的**灰度顺序**：先发布价目 → 小范围开 → 观察 `wallet_settlement_outbox`
      里 `resolved_at IS NULL` 的堆积 → 再放大。挂单常年为空才算健康。

## 8. 一个留给你拍板的口径

`TOKEN` 和 `JOB` 两种计价单位目前**降级到保底价**——按 token 计费需要一条这个服务还没有的
用量流。我没有让它凭空造一个数字。价目表里现在只有 `WALL_SECOND` 是真能算的，
其余两种单位在正式启用前要么补用量流、要么就别发布成 PUBLISHED。

# P4 平台管理员 / P5 后台面板 — 证据

日期：2026-08-25
范围：`V75__platform_administration.sql`、`PlatformAdminPort` / `JdbcPlatformAdminStore` /
`PlatformAdminController`、web-console 的 `/api/admin/*` 平台路由与两块面板。

本文只写**做过的验证**和**验证不到的地方**。凡是没有真跑过的，都在 §5 里点名，
不混在通过项里。

---

## 1. 数据库层（真实 PostgreSQL，非 superuser 属主）

环境：PostgreSQL 16.13，V1–V75 全量迁移。**注意这不是 17.5 的证据**（见 §5.1）。

两轮都跑：
1. 迁移属主为 superuser（宽松，能跑通不说明什么）
2. 迁移属主 `NOSUPERUSER NOBYPASSRLS` + 应用角色 `NOSUPERUSER`（严格）

严格轮是有意义的那一轮。P1 阶段正是它抓出了「`SECURITY DEFINER` 函数在
FORCE RLS 下看不到自己的行」这一类缺陷；P4 的函数按同样的方式写，并在同样的
条件下复验。

`platform_admin_test.sql` 断言（每条「必须被拒绝」的都真的去执行了那次非法操作）：

| # | 断言 | 结果 |
|---|------|------|
| 1 | 非管理员账号调用任一读函数 → 返回 0 行 | 通过 |
| 2 | 上一条同时在 `platform_admin_access_log` 留下一条 `DENIED_NOT_ADMIN` | 通过 |
| 3 | `PLATFORM_VIEWER` 调 `elmos_platform_wallet_adjust` → `DENIED_ROLE`，余额不变 | 通过 |
| 4 | `PLATFORM_APPROVER` 调整成功，`wallet_ledger_entries` 增加一行且 `reason` 非空 | 通过 |
| 5 | 空 `reason` 的调整被拒（表级 CHECK） | 通过 |
| 6 | 撤销最后一名 `PLATFORM_APPROVER` → `DENIED_LAST_APPROVER`，名单不变 | 通过 |
| 7 | 撤销非最后一名 approver → 成功 | 通过 |
| 8 | 已存在 approver 后再调 `elmos_platform_bootstrap_admin` → 拒绝 | 通过 |
| 9 | `elmos_platform_access_log` 为 append-only：UPDATE / DELETE 均被触发器拒绝 | 通过 |
| 10 | `elmos_platform_job_overview` 每个任务只出现一次（4 个组织 × 已知任务数） | 通过 |
| 11 | `elmos_platform_admin_runtime` 角色对 `wallet_*` 表**无** SELECT，只能走函数 | 通过 |

第 10 条是补一个我自己写出来的缺陷：初版漏了
`WHERE j.organization_id = v_org.organization_id`，靠 RLS 去兜。结果是每个任务
按组织数重复。生产里 RLS **会**把它盖住——这正是它危险的原因：在有 RLS 的环境
测不出来，在没有的环境（比如属主是 superuser 的实例）直接翻 4 倍。已修，并在
函数里留了注释说明 RLS 是安全网不是过滤条件。

## 2. 拒绝为什么不抛异常

`elmos_platform_authorize(...)` 决策与审计在同一次调用里完成，且**永不 RAISE**。
理由：RAISE 会回滚这次事务，连带回滚刚写下的那条拒绝审计。结果就是
「被拒绝的访问不留痕」——那样的访问日志不能作为任何事情的证据。

已验证：断言 2 与断言 3 在拒绝路径上都能读到审计行。

## 3. Java 层

Maven Central 在云端被挡（403），所以：

- `PlatformAdminPort.java` —— 零外部依赖，**真的用 `javac` 编译过**，通过。
- `JdbcPlatformAdminStore.java`、`PlatformAdminController.java` —— 依赖 Spring，
  只做了 `JavacTask.parse()` 语法检查，通过。**这不等于编译通过**（见 §5.2）。

一个只有真编译才能抓到的问题在 P3 出现过（内部类方法遮蔽外部静态方法），
parse 抓不到。所以 §5.2 不是形式主义。

## 4. Web 层

### 4.1 路由与代理（已在设备上真实 `tsc --noEmit` 通过）

6 个路由文件 + `platformRelay.ts` + `operationsProxy.ts` 的追加部分，在用户机器上
对真实工程跑 `tsc --noEmit`，干净。并且做了探针验证：故意插入
`const probe: number = "definitely not a number"` → 报 TS2322，移除后恢复干净，
确认 tsc 确实在检查那个目录，而不是把它跳过了。

两处是修掉的真缺陷，不是风格问题：

- `TOKEN_PATTERN` 是纯大写的 `/^[A-Z0-9][A-Z0-9._:-]*$/`，而真实标识符长
  `org-pre`、`acct-root` 这样。它会拒掉每一个真实 ID，症状是面板**永远空着**
  而不报错。换成 `PLATFORM_ID_PATTERN`。
- `boundedInteger(value, 0, 1, 100_000_000)` 在输入为空时返回 fallback，
  fallback 是 0 而下限是 1——一笔金额为 0 的调整会被放行。换成显式的
  `platformAmountMinor()`。

### 4.2 两块面板（本会话新增）

`PlatformWalletPanel.tsx`、`PlatformJobsPanel.tsx`，写成与既有面板同一套
`OperationsAdmin.module.css` 类名和 `<Icon>`，挂在既有的「财务对账」「任务队列」
分区下，不新开导航项。

几个刻意的选择：

- **不自动拉取。** 每一次读取在服务端都写一条平台管理员审计。若切到某个分区就
  自动请求，审计里那条「某某查看了全平台余额」将不再对应任何人的意图，只对应
  一次点导航栏。改成显式点「读取」，与旁边的「财务对账」面板一致。
- **拒绝与空列表必须长得不一样。** 403 显示为红色的「被拒绝」，无数据显示为
  `styles.empty`。混在一起会让人以为平台上一个钱包都没有。
- **幂等键保留到成功为止。** 初版用 `adj-${org}-${amount}-${Date.now()}`，
  每次提交换一个键——而网络超时后的重试恰恰是最不知道上一笔成没成的时候，
  换键重试等于入两次账。改成按 (组织, 方向, 金额) 生成一次并存在 ref 里，
  失败时**不清键**，改了金额或组织才作废。
- **人工调整用表单，不用 `window.prompt`。** 与工程既有风格一致，也避免模态
  对话框阻塞。
- **「未持有」不等于「已释放」。** 任务表里空的持有状态表示这个任务从头到尾
  没进过钱包（入队时计费开关是关的，或订阅配额覆盖了它），与冻结后又释放是
  两回事，界面上分开写。

类型检查：在隔离工程里用 `tsc --strict --noEmit` 通过（stub 掉 `Icon` 与
CSS module）。同样做了探针：两个文件各插入一个类型错误，两个都被报出
（TS2322，行号对得上），移除后恢复干净——确认两个文件都真的被检查了，
而不是被 include 漏掉。

CSS 类名与 Icon 名不是猜的：`styles.panel / tableWrap / bad / good / empty /
inlineActions / financeActions / boundaryNote / resultGood / resultBad` 逐个
grep 过真实的 `OperationsAdmin.module.css`；`refresh / search / check / close /
file / database` 逐个 grep 过真实的 `Icon.tsx`。

---

## 5. 没验证到的（不要当成已验证）

> **本节部分条目已在 §7 补验并被推翻/关闭，逐条见下方标注。**
> 保留原文不改写，是为了留下判断被更正的过程；结论以 §7 为准。

### 5.1 PostgreSQL 版本
生产是 17.5，云端只有 16.13。RLS 与 `SECURITY DEFINER` 的交互在这两个版本间
我不知道有无差异，**没有查证**。需要在 17.5 上重跑 `platform_admin_test.sql`
与严格属主那一轮。

### 5.2 Java 真编译
`JdbcPlatformAdminStore` 与 `PlatformAdminController` 只过了 parse。需要在你机器上
`sdk env` 之后跑一次完整 `mvn -q -DskipTests compile`。

### 5.3 面板对真实工程的类型检查　→ **已关闭**（§6.1 真实工程 tsc 通过，§7.1 `next build` 通过）
两块面板的 tsc 是在 stub 环境里跑的。真实 `Icon` 的 `name` 如果是字面量联合类型，
而我用了不在联合里的名字，隔离环境查不出来。需要在设备上对真实工程再跑一次
`tsc --noEmit`。（本次会话中设备桥接中断，未能完成。）

### 5.4 端到端　→ **部分关闭**（§7.3 验完了「回调 → 入账 → 流水 → 对账」这一段；服务未起、渠道未接仍成立）
没有真的起过服务。「点读取 → BFF → 控制面 → 数据库 → 审计行落库 → 面板渲染」
这条链路一次都没有整体跑过。各段分别验过，接缝没验过。

### 5.5 既有缺陷　→ **⚠️ 本条结论已被 §7.2 推翻。清扫器是好的，我当时只看了「跨租户」就下结论，没读函数体。**
**下面这段保留原文，是错的。**
`elmos_reap_execution_leases`（V52）做跨租户扫描，写 FORCE RLS 的
`execution_jobs` 却没有绑定租户。只有在迁移属主是 superuser 或 BYPASSRLS 时
才能工作。如果不是——它可能一直在「成功地清扫零行」。
**请确认你们实例上迁移属主的角色属性。** 这个失败模式不报错。

---

## 6. P5 收尾（本轮补充）

### 6.1 后台面板已落盘并接线

`PlatformWalletPanel.tsx` / `PlatformJobsPanel.tsx` 写入
`apps/web-console/app/admin/`，由 `wire_panels.py` 幂等接线：
两行渲染 + 两行 import，挂在既有的 `FINANCE` / `TASKS` 分区下，不新开导航项。

**在真实工程上跑了 `npx tsc --noEmit`，干净**（EXIT=0）。并做了探针验证：
两个文件各插入一个 `const __probe: number = "…"`，两个都被报出 TS2322 且行号对得上，
移除后恢复干净——确认两个文件确实进了编译范围，而不是被 include 漏掉。

### 6.2 用户侧钱包

新增：

- `app/api/wallet/route.ts` — 余额 + 充值上下限（一次返回，见文件注释）
- `app/api/wallet/ledger/route.ts` — 流水
- `app/api/wallet/topup/route.ts` — 下单
- `app/api/wallet/topup/[topupOrderId]/route.ts` — 状态轮询
- `app/account/AccountWalletPanel.tsx` — 面板，接进 `account/page.tsx`

### 6.3 校验逻辑抽成可测模块（并因此抓到一个缺陷）

初版把充值校验写在路由里。按仓库既有约定（`*.verify.mjs`）抽成
`app/lib/server/walletTopupPolicy.ts`，配 `walletTopupPolicy.verify.mjs`，
并注册进 `package.json` 的 `check` 链。

抽出来之后第一次运行就红了，抓到一个真缺陷：

```
boundedLedgerParam(null, 50, 200)  →  0   （期望 50）
```

`Number(null)` 和 `Number("")` 都是 `0`，而 `0` 是一个合法的下界，
于是一个没带 `limit` 的流水请求被翻译成 `limit=0`——**取零条流水**。
症状是用户的流水页面空着、不报错，看起来像「你还没有任何交易」。

这是本项目里第二次出现同一类失败：P3 的 `elmos_wallet_allowance_remaining`
在非 superuser 属主下返回 0，而 0 看起来像「额度用尽」而不是「读取失败」。
**silent zero 是这套代码的一个惯性缺陷模式**：金额与配额的类型里，
0 永远是一个合法值，所以任何「出错时回落到 0」的写法都会伪装成正常业务状态。
已在函数注释里写明。

### 6.4 verify 脚本的有效性（变异测试）

46 条断言全绿不说明什么——绿色也可能是断言太弱。故意注入四个缺陷，
四个全被抓出，恢复后文件与变异前逐字节相同：

| 变异 | 断言是否杀死 |
|------|--------------|
| 交接形态判据 `hasRedirect === hasQrCode` → `&&`（只挡两者都有，放过两者都没有） | 杀死 |
| `TOPUP_PROVIDERS` 加入 `STRIPE_CHECKOUT`（充值走境外主体收单） | 杀死 |
| 订单号正则放行 `/`（可拼进上游 URL） | 杀死 |
| 金额校验 `<= 0` → `< 0`（允许零元充值） | 杀死 |

### 6.5 邻近套件无回归

`test:upstream-policy` / `test:operations-jobs-policy` /
`test:billing-reconciliation-policy` / `test:admin-mutation-policy` /
`test:runner-fleet-policy` 逐个跑过，全 PASS。

### 6.6 新增的未验证项

**`next build` 没跑成。→ 已在 §7.1 于云端 x86_64 容器跑通，EXIT=0。**原文保留： 设备侧的 Cowork VM 是 linux/arm64，而
`node_modules` 是在 macOS 上装的，Next 的 SWC 原生二进制不匹配：

```
Error: Failed to load SWC binary for linux/arm64
```

`tsc` 不受影响（纯 JS）所以类型检查是真的，但 **App Router 的路由处理器签名、
`generateMetadata`、服务端/客户端边界这些只有 `next build` 才会报的问题没验过**。
请在你的 Mac 上原生跑一次 `pnpm check`（它包含 `tsc --noEmit` +
全部 policy 套件 + `next build`）。

**支付渠道没接通。**（§7.3 已补：回调到达之后的入账链路、重放幂等、跨租户认领拒绝、账本自证均已在真实 PG 上验过；渠道 HTTP 交互仍未验。）充值下单会真的调用 `paymentRouter.checkoutGateway().prepare()`，
本轮没有任何一次真实的渠道交互。二维码/跳转链路、回调入账、
`PAID → CREDITED` 的轮询，都只在代码层面成立。

**轮询没跑过。** `AccountWalletPanel` 里付款后每 4 秒轮询订单状态，
逻辑上刻意不在 `PAID` 时就把余额加上去（那会显示一个数据库里还不存在的余额），
但这段 effect 一次都没有在浏览器里跑过。

---

## 7. 三项补验（2026-08-26）

上一轮列为「未验证」的三项，两项做掉了，一项部分做掉。其中一项的结论
**推翻了我自己之前的判断**。

### 7.1 `next build` — 已通过，并且证明了它确实能抓 tsc 抓不到的东西

设备侧的 Cowork VM 是 linux/arm64 而 `node_modules` 装在 macOS，SWC 二进制不匹配。
改在云端 x86_64 容器里做：把 web-console 源码（不含 node_modules/.next）搬过去，
`pnpm install --frozen-lockfile` 重装，`next build`。

第一次失败，原因是两个跨目录引用不在最小化树里：

```
contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json
engines/database-data-engine/.../chinadb-commercial-v1.json
```

补齐后：

```
✓ Compiled successfully in 14.5s
✓ Generating static pages using 1 worker (22/22)
EXIT=0
```

十个新端点全部作为动态路由处理器注册（`ƒ` = server-rendered on demand）：

```
ƒ /api/wallet          ƒ /api/admin/wallets
ƒ /api/wallet/ledger   ƒ /api/admin/wallets/[organizationId]/ledger
ƒ /api/wallet/topup    ƒ /api/admin/wallets/adjust
ƒ /api/wallet/topup/[topupOrderId]   ƒ /api/admin/topups
○ /account  ○ /admin   ƒ /api/admin/execution-jobs
                       ƒ /api/admin/platform-admins
```

**这次构建有没有牙齿？** 做了探针：把 `AccountWalletPanel.tsx` 顶部的
`"use client"` 拿掉——这是「服务端/客户端边界」那一类问题的最小样本。

| | 结论 |
|---|---|
| `tsc --noEmit` | **EXIT=0，完全看不出问题** |
| `next build` | **EXIT=1**，`You're importing a module that depends on 'useEffect' into a React Server Component module` |

所以上一轮说「tsc 不覆盖这类问题」是对的，而现在这一类也验过了。

**`pnpm check` 整链没跑完**，停在 `test:translation-report` 的第 24 个子测试：

```
ModuleNotFoundError: No module named 'elmos_polyglot_route'
```

这是我这棵最小化树里没有仓库的 Python 引擎包，不是缺陷。同理
`test:multimodal-intake-runner` 报 `MULTIMODAL_ENGINE_NOT_INSTALLED`。
链上其余每一步都单独跑过并通过：

```
test:repository-translation        PASS      test:admin-mutation-policy    PASS
test:upstream-policy               PASS      test:runner-fleet-policy      PASS
test:operations-jobs-policy        PASS      test:chinadb-sql-policy       PASS
test:billing-reconciliation-policy PASS      test:wallet-topup-policy      PASS
tsc --noEmit                       EXIT=0    next build                    EXIT=0
```

仍然建议你在 Mac 上原生跑一次完整 `pnpm check`，把那两个引擎相关的也跑上。

### 7.2 V52 清扫器 — **我之前的判断是错的，它没有空转**

上一轮我说 `elmos_reap_execution_leases` 跨租户扫描却不绑定租户。
读了函数定义之后：**它在循环里每一行写之前都绑了**
（`PERFORM set_config('app.organization_id', v_row.organization_id, true)`）。
我当时只看了「跨租户」四个字就下了结论，没读函数体。

真正决定成败的是**驱动游标读的那张表**：

```sql
FOR v_row IN SELECT ... FROM execution_job_dispatch d
              WHERE d.dispatch_state='LEASED' AND d.lease_expires_at < now()
              FOR UPDATE SKIP LOCKED
```

而 `execution_job_dispatch` **根本没开 RLS**（`relrowsecurity = f`），
`runner_node_authentication` 同样。这和目录表是同一套设计：驱动放在无 RLS 的表上，
写入时逐行绑租户。

实测（PG 16.13，全量迁移，属主 `elmos_owner_prod` NOSUPERUSER NOBYPASSRLS，
调用者 `elmos_app_prod` NOSUPERUSER 且只有 EXECUTE）：

| 场景 | 返回 | 作业状态 |
|---|---|---|
| 属主 postgres（superuser） | swept **2** | 一条 QUEUED 重排、一条 LOST，租约 EXPIRED，事件已写 |
| 属主 elmos_owner_prod（NOSUPERUSER） | swept **4** | 同上，全部正确 |

**结论：清扫器是好的。** 但它的正确性依赖于驱动表没有 RLS——这一点是隐式的，
所以我做了对照实验：给 `execution_job_dispatch` 加上与其它表相同的 FORCE RLS 与
组织策略，其余一切不变，再跑一次：

```
superuser 视角看到的过期 LEASED 行数： 2
elmos_reap_execution_leases() 返回：   0        ← 无报错
作业状态：                             全部原封不动
```

这就是那个「成功地清扫零行」的失败模式，只是**它现在是潜伏的，不是已发生的**。
任何人日后觉得「`execution_job_dispatch` 带 organization_id 却没上 RLS，
是不是漏了」而补上策略，就会静默关掉租约回收。已在对照实验后还原，
`relrowsecurity/relforcerowsecurity` 均确认回 `f|f`。

**建议**：在 V52 那个函数上方加一句注释，写明驱动表刻意不带 RLS 及其后果。
这是一行注释能挡下的事故。（我没有替你改 V52——迁移是 forward-only，
而且这不是本次工作范围内的文件。）

### 7.3 充值回调入账 — 数据库那半段已验证，渠道那半段仍未验证

支付渠道的 HTTP 交互调不了。但回调**到达之后**的部分是可以完整验证的，
而钱的不变量全在这一段。

环境同上（非 superuser 属主 + 非 superuser 调用者，`SET ROLE` 实测
`current_user=elmos_owner_prod superuser=false`）。

**先证明为什么需要目录表**（这次是真的测出来的——上一版我把这条断言跑在
superuser 会话里，而 superuser 完全绕过 RLS，那个断言什么都没证明）：

| 以 `elmos_owner_prod` 身份读 | 结果 |
|---|---|
| 无租户上下文读 `wallet_topup_orders` | **0 行** |
| 无租户上下文读 `wallet_topup_order_directory` | **1 行** |
| 绑定 `org-pre` 读订单表 | 1 行 |
| 绑定 `org-broke`（别的租户）读同一张单 | **0 行** |

**再跑完整链路**（订单 `topup-cb-002`，ALIPAY，350.00 元）：

| 步骤 | 结果 |
|---|---|
| 建单 | `CREATED`，目录表被触发器同步 |
| 无租户上下文调 `elmos_wallet_credit_topup` | 返回流水号 `wle-30ba0d…` |
| 订单状态 | `CREATED → CREDITED`，`paid_at`/`credited_at` 都有 |
| 流水 | 一条 `TOPUP_SETTLED CREDIT 35000`，`balance_after=555600` |
| 余额 | 520600 → 555600 |
| **重放同一笔回调** | 返回**同一个流水号**，流水仍 1 行，余额不变 |
| 不存在的订单 | `ELMOS_WALLET_TOPUP_UNKNOWN`（拒绝，不是静默入账） |
| **拿别的租户去认领这笔单** | `ELMOS_WALLET_TOPUP_UNKNOWN`，`org-broke` 余额仍为 0 |
| `elmos_wallet_reconcile('org-pre')` | `(org-pre, 555600, 555600, 0, 0)` — 流水重放等于存储余额，drift 0 |

顺带一条设计确认：`elmos_wallet_credit_topup(org, order, txn, actor)` **没有金额参数**，
入账金额只能取自库里那张单。也就是说回调声称多少钱都改变不了入账金额——
这条不需要测，因为根本没有可攻击的入口。

**仍未验证**：向支付渠道下单（`prepare()`）、二维码/跳转链接的真实性、
回调签名校验、以及前端每 4 秒轮询 `PAID → CREDITED` 的那段 effect。
这些都要真实渠道凭据或浏览器，本轮一次都没跑过。

### 7.4 一个我的测试写错、代码是对的

第一次跑充值链路时 `elmos_wallet_create_topup_order` 报
`value too long for type character varying(16)`——我传了 `'WECHAT_PAY_NATIVE'`（17 字符）
而 `provider` 列是 `varchar(16)`。看起来像是「V73 把生产必需的微信渠道写死在门外」。

查了 Java 侧：`WalletTopupController.providerName()` 把
`WECHAT_PAY_NATIVE → "WECHAT_PAY"`、`ALIPAY_CHECKOUT → "ALIPAY"`，
与列上的 CHECK 约束（`WECHAT_PAY/ALIPAY/STRIPE/OFFLINE`）完全对齐。
**是我的测试写错了，不是代码。** 记在这里是因为它长得很像一个严重缺陷。

# 用户 Credit 充值完成报告

## 元数据

```yaml
skills:
  - elmos-credit-wallet-ledger@1.0.0
  - elmos-payments-reconciliation@1.0.0
repository: elmos
branch: codex/credit-topup-user-flow-20260909
baseline_commit: 1603014450378934d3618d2f97380405e5faf9b8
final_commit: 8c7ffd81b
completed_at: 2026-09-09
operator: Codex
```

## 执行结果

- 本次范围：用户购买固定 Credit 包后的可见闭环，包括安全下单、支付交接、订单终态轮询、
  回调确认后入账、组织余额、冻结余额、本人订单和本人 Credit 流水。
- 本次结果：`PASS_LOCAL`。
- 生产就绪：`no`。定价目录仍为 `DRAFT`，实时计费开关默认关闭。
- 明确不声明：未执行真实支付宝/微信资金、退款、结算文件、税务、开票、生产迁移、
  独立安全复核或生产认证。
- Skill 输入缺口：Skill 引用的 `.elmos-billing-kit/` 未安装；本报告以仓库内 V49、
  V73、V74、V83、V84、商业 API、价格目录与运行手册为当前权威实现。

## 用户旅程

1. 用户登录并选定当前组织，进入 `/pricing`。
2. 页面从版本化目录展示固定 SKU、人民币金额、Credit 数量与有效期；客户端不能提交金额。
3. 用户点击 Credit 包的“立即购买”，浏览器 BFF 校验 SKU 和幂等键，商业 API 从服务端目录建单。
4. 支付宝跳转到受信任 HTTPS 域；微信 Native 在本地渲染 `weixin://` 二维码。
5. 浏览器仅轮询订单状态，不把返回页、二维码或 `PAID` 文案当作到账事实。
6. 经过签名、时间窗、环境、事件 ID、订单、金额和租户校验的支付回调执行一次履约。
7. 只有订单为 `FULFILLED` 且账本出现 `PURCHASE`，页面才显示新增 Credit 并释放下一次购买键。
8. `FAILED`/`EXPIRED` 可重新发起；`RECONCILIATION_REQUIRED` 停止自动重试并提示勿重复付款。

## Credit Wallet 需求证据

| Requirement | 状态 | Source / symbol | 测试与运行证据 | 说明 |
|---|---|---|---|---|
| EB-04-001 | `PARTIAL` | `V83__commercial_credit_and_one_time_orders.sql` / `elmos_commercial_fulfill_order` | `JdbcCommercialOrderStoreLiveTest` | Credit 事实为追加式单边流水与余额批次；Skill 要求的通用双分录 Credit 总账尚未建立。 |
| EB-04-002 | `PARTIAL` | V83 `commercial_credit_lots`, `commercial_credit_reservations` | V83 live integration | 已覆盖 paid、reserved、consumed、expired；promotional/refunded 尚无完整 Credit 生命周期。 |
| EB-04-003 | `PARTIAL` | V83 reserve/settle/release functions | V83 live integration | 生成场景 reserve、partial capture、release 已有；Credit refund/双人 adjustment 未闭环。 |
| EB-04-004 | `IMPLEMENTED` | `CommercialOrderController.buyCredits`, `elmos_commercial_create_order` | BFF 4/4；V83 幂等重放 | 租户内稳定幂等键，内容冲突失败关闭。 |
| EB-04-005 | `IMPLEMENTED` | V83 account/lot CHECK 与行锁函数 | 并发硬停止、负向数据库测试 | 非授信 Credit 不允许负余额。 |
| EB-04-006 | `PARTIAL` | `payment_provider_events`, callback receipt | callback 重放测试 | 支付事实已持久化；商业 Credit 账本尚无独立事务性 outbox。 |
| EB-04-007 | `PARTIAL` | `JdbcCommercialOrderStore.creditBalance` | PostgreSQL live readback | 投影可由批次汇总读取，但没有正式全量重建命令与证据。 |
| EB-04-008 | `MISSING` | — | — | Credit 人工调整的双人审批未实现。 |
| EB-04-009 | `PARTIAL` | V83 FIFO lot expiry | PostgreSQL expiry scenario | 购买 Credit 到期已隔离；促销 Credit 分类尚未实现。 |
| EB-04-010 | `PARTIAL` | payment reconciliation cases | 管理端对账策略 17 checks | 已有异常案件；日终 Credit 总账与外部结算四方核对未运行。 |

## Payments 需求证据

| Requirement | 状态 | Source / symbol | 测试与运行证据 | 说明 |
|---|---|---|---|---|
| EB-10-001 | `IMPLEMENTED` | `PaymentProviderRouter`, Alipay/WeChat/ELMPay adapters | 支付密码学与路由自检 | 核心订单不依赖供应商 DTO。 |
| EB-10-002 | `PARTIAL` | `application.yml`, owner-only secret file loaders | 密钥文件权限/符号链接负向测试 | 代码无硬编码密钥；生产 Secret Manager 轮换证据 `NOT_RUN`。 |
| EB-10-003 | `IMPLEMENTED` | callback adapters + replay guard | 签名、时间窗、环境、事件 ID 测试 | 回调失败关闭。 |
| EB-10-004 | `IMPLEMENTED` | `PaymentCallbackPipeline`, callback receipts | 重复、失败重领、未知订单/金额错配测试 | 重放只产生一次业务效果。 |
| EB-10-005 | `IMPLEMENTED` | `elmos_commercial_fulfill_order` | PostgreSQL 重复履约测试；UI fulfillment test | 成功支付只入账一次。 |
| EB-10-006 | `PARTIAL` | provider checkout/capture adapters | adapter self-tests | 当前 Credit 充值是即时收款；通用授权、部分捕获和取消不是该商品路径。 |
| EB-10-007 | `MISSING` | — | — | 手续费、汇率、净结算和到账日期尚无真实 provider 事实。 |
| EB-10-008 | `PARTIAL` | reconciliation API/cases | reconciliation policy 17 checks | 案件工作流存在；真实 provider/bank settlement 日结 `NOT_RUN`。 |
| EB-10-009 | `IMPLEMENTED` | `payment_reconciliation_cases` | 金额错配、晚到付款、未知结果测试 | 异常进入人工对账，不盲目重下单。 |
| EB-10-010 | `IMPLEMENTED` | `ProductBillingAction`, `CreditWalletPanel` | Chromium + mobile fulfillment journey 2/2 | 返回页和客户端状态均不直接增加余额。 |

## 本次变更

- `CreditWalletPanel`：组织 Credit 的可用、冻结、总额、最近充值订单和本人流水。
- `ProductBillingAction`：二维码订单终态轮询、终态提示和安全幂等键生命周期。
- `GET /api/billing/orders/[orderId]`：校验路径参数后代理到 actor/tenant 受控订单查询。
- 定价页：挂载 Credit 面板。
- 测试：路径穿越/非法订单 ID；付款前不入账、履约后余额与流水同时出现；桌面和移动端。

## 验证

```text
pnpm --dir apps/web-console run test:commercial-billing-routes
PASS: 4/4

pnpm --dir apps/web-console exec tsc --noEmit
PASS

pnpm --dir apps/web-console build
PASS: Next.js 16.3.0 production build, 18 static pages generated

ELMOS_E2E_ENGINE_SKIP_BUILD=true pnpm --dir apps/web-console exec playwright test \
  e2e/pricing-ui.spec.ts --project=chromium --project=mobile-chromium
PASS: 6/6

mvn -q -pl apps/commercial-api -am \
  -Dtest=CommercialOrderCallbackRoutingTest,PaymentCallbackBindingTest,BillingApiErrorAdviceTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
PASS: 13/13

engines/project-synthesis-engine/.venv/bin/python -m pytest -q \
  engines/project-synthesis-engine/tests/test_project_documentation.py
PASS: 3/3
```

当前隔离环境的 PostgreSQL Testcontainers 复验未形成新通过证据：OrbStack Docker 的
`localhost:2375` 无响应。历史 V83 实库证据仍保留在 `TEST_EVIDENCE.md`，但本报告不把
该历史结果冒充为本次复跑成功。

完整 `pnpm check` 在隔离 sparse worktree 的两个非本功能环境测试上没有形成通过证据：
翻译报告首次 Python 工具下载超过固定 120 秒，ChinaDB/多模态/生成测试最初缺 sparse 资源。
补齐对应目录后，多模态 26 checks、生成测试 18/18、洞察 19 checks 和 Next build 均通过；
ChinaDB policy 20 checks 通过，ChinaDB local 仍有一次固定时限超时。不得把这些环境超时记为
Credit 测试失败，也不得把分段通过描述为一次完整 `pnpm check` 通过。

## 财务与安全控制

- 租户隔离：JWT 组织来自可信声明，后端 FORCE RLS；订单详情还校验 actor 或管理 scope。
- 幂等：一次购买复用稳定键；仅在明确 `FULFILLED`、`FAILED` 或 `EXPIRED` 后释放。
- 未知结果：`RECONCILIATION_REQUIRED` 保留原键并阻止重复付款提示。
- 金额：服务端目录以整数分生成，客户端只提交 SKU。
- Credit：服务端以整数 Credit 记账，浏览器不维护权威余额。
- 敏感数据：BFF 只转发短期访问令牌；商户密钥不进入浏览器、代码、订单或报告。

## 发布决定

`NO_GO_PRODUCTION`。合并代码不会开启收款。只有目录发布门禁要求的真实商户、法务、税务、
开票、成本、生产数据库、退款/对账、监控、回滚与独立验证证据全部到位后，才能发布新的
`PUBLISHED` 目录版本并设置 `ELMOS_BILLING_LIVE_ENABLED=true`。

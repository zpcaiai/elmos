# 自助计费测试证据

## 本地证据

| 验证 | 范围 | 决定 |
|---|---|---|
| Maven commercial API reactor | 目录、JWT、Stripe 签名、错误映射、迁移契约 | `PASS` |
| Commercial API live integration | JWT 组织派生、精确 scope、试用、订阅摘要、数据库 readiness | `PASS` |
| Web TypeScript / Next 生产构建 | BFF、实时用量、客户套餐操作、任务 producer | `PASS` |
| Chromium 客户旅程 | 身份负向、同源写保护、请求校验、实时进度刷新、DRAFT 付费禁用 | `PASS`（4/4） |
| 项目任务 Markdown 文档包 | 架构、数据库、迁移、历史、追踪、归档 | `PASS`（3/3） |
| PostgreSQL 17.5 空库 V1–V50 | DDL、函数、触发器、RLS | `PASS` |
| JDBC live integration | 试用、预留、结算、告警、并发硬停止、对账、到期、释放幂等 | `PASS` |
| 最小权限运行角色 | `NOSUPERUSER`、`NOBYPASSRLS`、函数白名单、跨租户失败关闭 | `PASS` |
| 负向数据库验证 | 跨租户、缺租户、重复试用、追加事实修改、超额并发 | `PASS` |
| Neon 生产迁移 | 精确项目/分支/数据库未知 | `NOT_RUN` |
| Stripe 测试/生产商户真实 Checkout | Secret 与 Price 未配置 | `NOT_RUN` |
| 生产 OIDC、邮件与真实资金客户旅程 | 外部系统未配置 | `NOT_RUN` |

## 关键测试

- `PricingPlanCatalogTest`
- `StripeCheckoutGatewayTest`
- `CommercialPrincipalTest`
- `CommercialSecurityConfigurationTest`
- `BillingApiErrorAdviceTest`
- `SelfServiceBillingMigrationContractTest`
- `JdbcSelfServiceBillingLiveTest`
- `SelfServiceBillingApiLiveTest`
- `usage-meter-ui.spec.ts`
- `test_project_documentation.py`

## 已执行命令

- `mvn -q -pl apps/commercial-api -am test`
- `mvn ... -Dtest=JdbcSelfServiceBillingLiveTest ... test`（PostgreSQL 17.5 + 最小权限角色）
- `mvn ... -Dtest=SelfServiceBillingApiLiveTest ... test`（PostgreSQL 17.5 + 最小权限角色）
- `pnpm exec tsc --noEmit`
- `pnpm build`
- `pnpm exec playwright test e2e/usage-meter-ui.spec.ts --project=chromium`
- `uv run pytest -q tests/test_project_documentation.py`
- Flyway `validate → migrate → validate`，从空库应用 V1–V50

## 证据边界

本地空库重放证明迁移在本机 PostgreSQL 17.5 上可执行，不证明某个 Neon 分支已经应用。
模拟/本地 Stripe 签名测试证明验证代码路径，不证明商户、价格、税务或真实资金流。
本地 Chromium 测试证明受控本地客户界面与 BFF 行为，不证明生产 OIDC、Cookie 域、网络或支付回跳。
本结论是工程验证，状态不是财务、支付、安全或生产认证。

# 自助计费测试证据

## 本地证据

| 验证 | 范围 | 决定 |
|---|---|---|
| Maven `commercial-api` 全依赖集合 | 662 tests：649 执行、13 环境/能力条件跳过 | `PASS`（0 failure / 0 error） |
| Maven 商业计费定向集 | 目录、JWT、支付签名/回调、错误映射、迁移契约 | `PASS`（53/53） |
| Commercial API live integration | JWT 组织派生、精确 scope、试用、订阅摘要、数据库 readiness | `PASS` |
| Web `pnpm check` | TypeScript、BFF 策略/路由、实时用量、producer、Next 生产构建 | `PASS` |
| Chromium + mobile Chromium 定价旅程 | 精确商品/金额/目录版本、DRAFT 付费禁用 | `PASS`（4/4） |
| 项目任务 Markdown 文档包 | 架构、数据库、迁移、历史、追踪、归档 | `PASS`（3/3） |
| PostgreSQL 17.5 空库 V1–V91 | 91 个迁移、DDL、函数、触发器、RLS | `PASS` |
| V91 JDBC live integration | Credit/权益、并发、actor/tenant、生产 Token 事实历史、回调 claim、过期付款 | `PASS`（5/5） |
| 支付密码学/路由自检 | 12 组：真实密钥、签名、金额、重放、Spring、安全与目录 | `PASS`（全部零失败） |
| 定价 JSON Schema | `jsonschema 4.25.1` 校验目录 | `PASS` |
| 目录发布门禁 | DRAFT 结构验证；缺少真实外部证据时拒绝发布 | `PASS`（预期 `PUBLICATION_BLOCKED`） |
| 最小权限运行角色 | `NOSUPERUSER`、`NOBYPASSRLS`、函数白名单、跨租户失败关闭 | `PASS` |
| 迁移后角色恢复与 API readiness | V1–V91 后创建运行时角色、恢复精确授权、持久层/API 旅程 | `PASS` |
| 负向数据库验证 | 跨租户、缺租户、重复试用、追加事实修改、超额并发 | `PASS` |
| Neon 生产迁移 | 精确项目/分支/数据库未知 | `NOT_RUN` |
| 支付宝/微信生产商户真实付款与退款 | 商户、证书与回调域名未注入 | `NOT_RUN` |
| 生产 OIDC、邮件与真实资金客户旅程 | 外部系统未配置 | `NOT_RUN` |

## 关键测试

- `PricingPlanCatalogTest`
- `StripeCheckoutGatewayTest`
- `CommercialPrincipalTest`
- `CommercialSecurityConfigurationTest`
- `BillingApiErrorAdviceTest`
- `SelfServiceBillingMigrationContractTest`
- `JdbcSelfServiceBillingLiveTest`
- `JdbcCommercialOrderStoreLiveTest`
- `CommercialOrderCallbackRoutingTest`
- `CommercialCreditMigrationContractTest`
- `SelfServiceBillingApiLiveTest`
- `usage-meter-ui.spec.ts`
- `test_project_documentation.py`

## 已执行命令

- `mvn -q -pl apps/commercial-api -am -Dtest=... test`（本功能 53/53）
- `mvn -q -pl apps/commercial-api -am test`（649/649 已执行测试通过；13 个条件跳过）
- `mvn -q -pl modules/persistence -am -Dtest=JdbcCommercialOrderStoreLiveTest ... test`
- `mvn ... -Dtest=JdbcSelfServiceBillingLiveTest ... test`（PostgreSQL 17.5 + 最小权限角色）
- `mvn ... -Dtest=SelfServiceBillingApiLiveTest ... test`（PostgreSQL 17.5 + 最小权限角色）
- `pnpm exec tsc --noEmit`
- `pnpm build`
- `pnpm exec playwright test e2e/usage-meter-ui.spec.ts --project=chromium`
- `pnpm --dir apps/web-console check`
- `pnpm --dir apps/web-console exec playwright test e2e/pricing-ui.spec.ts --project=chromium --project=mobile-chromium`
- `bash tooling/payment-crypto-selftest/run_selftests.sh`
- `uv run --quiet --with jsonschema==4.25.1 python ...`（目录 Schema）
- `python3 scripts/commercial/validate_pricing_catalog_publication.py --check-publishable`
- `uv run --project engines/project-synthesis-engine pytest -q engines/project-synthesis-engine/tests/test_project_documentation.py`
- Flyway `validate → migrate → validate`，从空库应用 V1–V91

## 证据边界

本地空库重放证明迁移在本机 PostgreSQL 17.5 上可执行，不证明某个 Neon 分支已经应用。
本地支付宝/微信密钥与签名测试证明代码路径，不证明生产商户、税务或真实资金流。
本地 Chromium 测试证明受控本地客户界面与 BFF 行为，不证明生产 OIDC、Cookie 域、网络或支付回跳。
全量 Maven 的 13 个跳过项包含未配置真实模型提供方的健康探针、部分需显式 live 开关的旧计费测试，
以及两个平台相关快照用例；这些不是失败，也不替代对应外部运行证据。
本结论是工程验证，状态不是财务、支付、安全或生产认证。

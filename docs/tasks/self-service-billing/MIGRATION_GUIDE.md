# 自助计费迁移与发布指南

## 发布前置条件

1. 价格目录已完成商户主体、税务、开票、Stripe CNY Price ID 和成本验证，目录状态改为
   `PUBLISHED`；在此之前 Checkout 必须保持关闭。
2. OIDC issuer、JWK URL、audience 和精确 scope 已配置。
3. GitHub `commercial-production` Environment 已启用审批保护。
4. Environment 中配置三个数据库 Secret 与两个目标变量：

| 类型 | 名称 |
|---|---|
| Secret | `ELMOS_COMMERCIAL_DATABASE_URL` |
| Secret | `ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME` |
| Secret | `ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD` |
| Variable | `ELMOS_COMMERCIAL_DATABASE_EXPECTED_HOST` |
| Variable | `ELMOS_COMMERCIAL_DATABASE_EXPECTED_DATABASE` |
| Variable | `ELMOS_COMMERCIAL_DATABASE_RUNTIME_USERNAME` |

数据库 URL 必须是无内嵌凭据、启用 `sslmode=require` 或 `verify-full` 的 Neon JDBC URL。
迁移身份与应用运行身份必须分离。Commercial API 使用
`ELMOS_COMMERCIAL_DATABASE_USERNAME/PASSWORD` 的最小权限、`NOSUPERUSER NOBYPASSRLS`
运行角色，不能复用迁移 owner。工作流会验证角色属性，授予精确计费表/函数权限；
核心函数的默认 `PUBLIC EXECUTE` 已撤销。

## 自动迁移

对 `modules/persistence/src/main/resources/db/migration/**` 的 main 分支变更会触发
`.github/workflows/commercial-billing-neon.yml`。工作流先校验目标主机与数据库，再执行：

```text
Flyway validate → Flyway migrate → Flyway validate
```

缺 Secret、缺 Environment Variable、目标不匹配、非 Neon、无 TLS、checksum drift、
乱序或任一 SQL 失败都会阻断。工作流不会输出连接串或密码。

## 本地一次性验证

只在可销毁 PostgreSQL 17 数据库执行：

```bash
ELMOS_BILLING_TEST_JDBC_URL=jdbc:postgresql://127.0.0.1:55491/elmos_billing \
ELMOS_BILLING_TEST_DATABASE_USERNAME=postgres \
ELMOS_BILLING_TEST_DISPOSABLE_CONFIRMED=true \
mvn -pl modules/persistence -am -Dtest=JdbcSelfServiceBillingLiveTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
```

必须额外运行：

```bash
mvn -pl apps/commercial-api -am test
pnpm --dir apps/web-console check
```

## 应用配置

Commercial API 只有在 `ELMOS_COMMERCIAL_DATABASE_URL` 存在时才创建数据库适配器。
上线还需要：

- `ELMOS_OIDC_ISSUER_URI`、`ELMOS_OIDC_JWK_SET_URI`、`ELMOS_OIDC_AUDIENCE`
- `ELMOS_TRIAL_IDENTITY_PEPPER`，至少 32 字节随机值
- `ELMOS_BILLING_LIVE_ENABLED=true`
- `STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`
- 月付/年付 CNY Price ID 与成功/取消 HTTPS URL

Web 任务生产者还需要短期服务令牌和精确订阅绑定；启用
`ELMOS_BILLING_ENFORCEMENT_ENABLED=true` 后缺少任一项都必须拒绝任务。

## 回退

- 不运行 `flyway clean`，不删除计量、支付或审计事实。
- 应用回退时先关闭 Checkout 和新任务入口，保留 Webhook 接收与对账能力。
- 数据库迁移采用前向修复：新增下一版本迁移，不改写已在生产应用的 V49。
- 已创建的 Stripe Session 或状态未知请求必须进入对账，不可直接重放产生第二个 Session。
- 回退后核对预留租约并安全释放过期项，保留全部 provider receipt 和结案引用。

## 当前外部状态

仓库未发现可用于本次操作的生产 Neon、OIDC、Stripe 或邮件 Secret，因此未执行生产迁移、
未创建 Stripe 商品/价格、未注册 Webhook，也未发送邮件。状态保持 `NOT_RUN` /
`NOT_CONFIGURED`。

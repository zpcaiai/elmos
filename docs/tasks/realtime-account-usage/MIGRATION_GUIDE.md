# 实时账户用量迁移指南

发布配置、Flyway V49、Neon 目标校验、回退和外部门槛见
[自助计费迁移指南](../self-service-billing/MIGRATION_GUIDE.md)。

任何生产迁移必须通过 `.github/workflows/commercial-billing-neon.yml` 的
`validate → migrate → validate` 门禁；不得从部署成功推断数据库已迁移。

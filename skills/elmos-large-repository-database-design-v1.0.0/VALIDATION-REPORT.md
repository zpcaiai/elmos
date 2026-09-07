# Elmos v1.1.0 交付校验报告

**生成日期：** 2026-08-21

## 已完成的本地校验

- 11 个 Migration 文件顺序、事务边界与命名；
- 136 张父表和 523 个外键目标/唯一性静态检查；
- 31 个函数、8 个 Read Model；
- 13 个业务 Schema 与锁定的 `extensions` Schema；
- 租户表 `tenant_id`、RLS/FORCE RLS；
- Append-only Event、Evidence、Ledger 和 Audit；
- 3 槽准入、Lease Generation 和 Fencing；
- P05 exact revision、Evidence freshness/revocation、Coverage、Task、Gap 和 Side Effect 条件；
- Operator Query 与 Invariant Query 的表/别名/列静态一致性；
- Shell `bash -n`；
- Python `py_compile`；
- JSON 解析与 JSON Schema；
- 普通 YAML 解析；
- Helm values default/staging/production JSON Schema；
- 大型 Run Read Model 示例校验；
- 包内 SHA-256 和 ZIP 完整性。

静态数据库检查结果：

```text
DATABASE DESIGN VALIDATION PASSED
migrations=11
parent_tables=136
foreign_keys_checked=523
functions=31
views=8
tables_by_schema=analysis:15,artifact:7,audit:1,cache:4,core:10,
exec:26,generation:12,integration:6,learning:9,metering:9,
ops:7,transform:7,verify:23
```

## 当前环境未执行的校验

当前生成容器没有可用的 PostgreSQL Server、Docker 或 Helm 二进制，而且外部软件源不可达，因此本地未实际启动 PostgreSQL 16/17 或 Kubernetes。

这意味着：

- 本报告不把静态检查描述为数据库引擎执行证明；
- `.github/workflows/database-ci.yml` 已配置 PostgreSQL 16/17 空库 Migration、Flyway Validate 和 `database/tests/invariants.sql`；
- 合并 Elmos 主仓库后，必须让该 CI 成为保护分支 Required Check；
- Staging 必须完成真实 Worker Kill/Resume、并发 Claim、P05 Gate 和 Deployment Gate 演练后才能生产发布。

## 生产前阻断条件

以下任一项未通过，不得标记 Production Ready：

1. PostgreSQL 16/17 Migration Matrix；
2. 空库安装和上一版本升级；
3. RLS 跨租户负向测试；
4. 账号 3 槽并发竞争测试；
5. Task Lease/Fencing 陈旧 Worker 测试；
6. Event 顺序和 Hash Chain；
7. Checkpoint Seal/Restore；
8. Side Effect `UNKNOWN_RESULT` reconciliation；
9. P05 stale Evidence/old Run/empty Ledger 负向测试；
10. Helm Migration Hook 与 P05 Deployment Gate；
11. 备份恢复与 PITR；
12. 百万文件容量和分区压测。

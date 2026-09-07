# Elmos 大型仓库项目生成与跨库转换数据库设计包

**版本：** 1.0.0  
**数据库：** PostgreSQL 16+  
**Migration：** Flyway V001–V090

本包可单独合并进 Elmos 主仓库，用于保存大型仓库项目生成、跨语言/框架/数据库转换全过程的权威状态、恢复点、仓库索引、Capability/Coverage、验证证据、成本收入和 P05 完成裁决。

## 最重要的入口

1. `database/EXECUTIVE-SUMMARY.md`：设计决策摘要；
2. `database/DB-1-MINIMUM-TABLE-SET.md`：首发 34 张强一致核心表；
3. `docs/DATABASE-DESIGN-LARGE-REPOSITORY-RUNS.md`：完整数据模型；
4. `database/TABLE-CATALOG.md`：136 张父表目录；
5. `docs/DATABASE-TRANSACTION-AND-RECOVERY.md`：幂等、租约、fencing 和恢复；
6. `docs/DATABASE-SECURITY-RLS.md`：RLS、函数 Owner 和权限；
7. `database/roles/roles-and-grants.example.sql`：生产角色硬化；
8. `database/tests/invariants.sql`：数据库不变量；
9. `skills/large-repository-run-persistence/SKILL.md`：Codex/Claude Code/OpenCode 实现 Skill。

## 保存边界

```text
PostgreSQL: Job/Run/Task/Attempt、Lease、Event、Checkpoint、Artifact metadata、
            Repository/IR/Capability index、Coverage/Evidence/Gate、Cost/Revenue/ETA
Temporal:   durable workflow/timer/retry/pause-resume
S3/MinIO:   source body、AST/Graph/IR shard、patch、build log、model long output、media
Redis:      hot cache/rate limit only
```

## 静态校验

```bash
python3 scripts/validate_database_design.py
```

## PostgreSQL CI

`.github/workflows/database-ci.yml` 在 PostgreSQL 16/17 上执行：

```text
Flyway migrate
→ Flyway validate
→ role hardening
→ role owner/ACL assertions
→ database/tests/invariants.sql
```

本地生成环境没有 PostgreSQL Server/Docker/Helm，因此没有把静态验证冒充引擎执行证明；生产前必须让数据库 CI 成为保护分支 Required Check。

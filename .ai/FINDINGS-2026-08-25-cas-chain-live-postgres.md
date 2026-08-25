# FINDINGS 2026-08-25 — CAS 迁移链 V65→V69 的 live PostgreSQL 验证

日期：2026-08-25
性质：**增量验证，不是新实现。** 本会话没有改 `modules/cas` 或 `modules/persistence` 的任何源码。

## 为什么是我来跑这个

`#10` 在 backlog 里是 `IN-PROGRESS`，剩余工作已被拆成 `#10a/#10b/#10c`，有人在做。
按 `FINDINGS-2026-08-19` 立下的规矩（`#2a` Kotlin 被两个会话各实现一遍之后立的），
撞车时的正确处置是**转成验证方：跑对方跑不了的验证，只提交增量**。

那份 08-20 状态里写着 `live PostgreSQL … 仍为 NOT_RUN`。
云端可以用 pypi 的 `pgserver` 起真 PostgreSQL，**不需要 Docker、不需要网络**——
这正好是那台机器上缺的能力。所以本轮只做这一件事。

## 跑了什么

`scripts/cas/verify_cas_migration_chain.py`（新增文件），对 **PostgreSQL 16.2** 实跑：

```
chain: V65 -> V66 -> V67 -> V69
checks executed: 51        failures: 0
```

## 最值得看的两条

### 1. 三次 `NO FORCE ROW LEVEL SECURITY` 窗口，FORCE 全部恢复了

V66、V67、V69 都是同一个模式：为了做租户跨越的 backfill，先

```sql
ALTER TABLE <tenant table> NO FORCE ROW LEVEL SECURITY;
...
ALTER TABLE <tenant table> FORCE ROW LEVEL SECURITY;
```

这是三次机会把租户隔离对**表 owner** 静默关掉。**文本契约测试看不见这个**——
无论最终状态如何，恢复 FORCE 的那行 SQL 都在文件里躺着。唯一的判据是跑完链之后读
`pg_class.relforcerowsecurity`。

跑完全链后，10 张 CAS 表 **`relrowsecurity` 与 `relforcerowsecurity` 全为 true**：

```
cas_object_catalog              cas_object_placement
cas_action_cache_entries        cas_reference_roots
cas_upload_sessions             cas_deletion_manifests
cas_quarantine_events           cas_resource_bindings
cas_action_cache_invalidations  cas_action_cache_quarantined_nodes
```

三个租户隔离策略 `cas_b65/b66/b67_tenant_isolation` 都在；
`cas_object_catalog.project_id` 确实被 V66 删掉了（迁进 `cas_resource_bindings` 的 PROJECT 绑定）。

### 2. V66 的中止路径也把 FORCE 回滚掉了 —— 这条最重要

V66 里有一条**故意的**中止：provenance digest 解析不到租户本地对象时 `RAISE EXCEPTION`，
拒绝编造 size。设计是对的。但它 `RAISE` 的位置在 `NO FORCE` **之后**——
所以真正要问的是：**一次失败的迁移，会不会把租户隔离关着就走了？**

Phase 2 直接驱动这个场景：V65 之后塞一行 provenance 指向未编目对象的记录，再跑 V66。

```
V66 aborts rather than inventing a provenance size   ✓（按预期 RAISE）
cas_object_catalog.relforcerowsecurity == true       ✓（drop 随迁移一起回滚）
```

一次失败的部署没有留下被削弱的租户边界。这条只有真库能证。

## 其余 49 项（逐条负例，断言拒绝原因）

**V66**
- provenance digest 与 size 必须同时有或同时无（`cas_object_catalog_provenance_digest_complete`）
- `cas_resource_bindings`：未知 resource_kind 拒、空白 resource_id 拒、
  绑定未编目对象拒（FK）、released_at 早于 bound_at 拒
- RLS 真隔离：org-b 看不见 org-a 的绑定；org-b 往 org-a 写被 `row-level security` 拒

**V67**
- 活跃条目缺重建元数据被 `cas_action_active_metadata_complete` 拒

**V69**
- 完整签名的活跃条目可写入
- `octet_length(signature_value)` 与 `attestation_signature_bytes` 不一致被拒
- **presentation window 是不对称的**，两个方向都验了：
  签名可以旧 15 分钟（-10 分钟通过），但只允许超前 1 分钟（+10 分钟被拒）。
  这个不对称是对的——签完再写入天然有延迟，而**未来时间戳只可能是坏时钟或伪造**。

  我第一版测试把方向写反了（拿 +10 分钟断言"应该通过"），红了一次。
  是我的测试错，不是 V69 错；改完两个方向都锁住了。

## 我改了什么 / 没改什么

**新增**：`scripts/cas/verify_cas_migration_chain.py`、本文件。
**没有改**：`modules/cas`、`modules/persistence`、`.ai/CODE_LEVEL_BACKLOG.md` 的 `#10` 状态、
以及任何一份别人正在写的 findings。`#10` 的状态该由认领它的会话自己更新。

## 给 #10 认领者的一句话

那份 08-20 状态里的 `live PostgreSQL … NOT_RUN` 就迁移层而言现在有证据了，可以据此改写。
**但注意口径**：本轮只验了 schema 层（DDL、约束、RLS、FORCE 恢复）。
`NOT_RUN` 里剩下的 **Docker/provider、真实双进程共享 object tier 的重启/跨实例命中证据**
一条都没动 —— 那两条不是起个 Postgres 就能替代的。

复跑：

```bash
pip install pgserver 'psycopg[binary]'
python3 scripts/cas/verify_cas_migration_chain.py
```

脚本自己向上找仓库根定位 `modules/persistence/.../db/migration/`，在仓库任意目录跑都行。

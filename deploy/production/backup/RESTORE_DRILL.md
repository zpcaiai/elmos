# ELMOS 恢复演练手册

生成日期：2026-07-28
关联风险：**RISK-DATA-001（critical，OPEN）**——备份、PITR、恢复、DR 证据 `NOT_RUN`

> 这条风险**只能由一次真实的恢复演练关闭**。备份任务成功、快照存在、
> 云厂商控制台显示"已启用 PITR"——这三样都不算。
> 唯一算数的是：从备份把数据恢复出来，并证明恢复出来的数据是对的。

---

## 0. 演练前提

| 项 | 要求 |
|---|---|
| 目标环境 | **staging 或一次性实例**，绝不在生产库上做恢复演练 |
| 执行人 | 与验证人**必须不同**（仓库失败关闭规则：执行者与验证者相同不算通过） |
| 频率 | 首次上线前一次；之后每季度一次（告警 `RestoreDrillOverdue` 91 天） |
| 记录 | 每次演练产出一份带时间戳的结果文件，不可覆盖历史 |

---

## 1. 演练前：确认基线（10 分钟）

在**生产**库上只读采集，作为恢复后比对的基准：

```sql
-- 1.1 业务基线计数
SELECT 'subscriptions' t, count(*) FROM subscriptions
UNION ALL SELECT 'usage_events',            count(*) FROM usage_events
UNION ALL SELECT 'payment_provider_events', count(*) FROM payment_provider_events
UNION ALL SELECT 'payment_reconciliation_cases', count(*) FROM payment_reconciliation_cases;

-- 1.2 计量账本校验和（恢复后必须逐行一致）
SELECT organization_id,
       count(*)                       AS events,
       sum(quantity)                  AS total_quantity,
       md5(string_agg(id::text, ',' ORDER BY id)) AS ledger_digest
FROM usage_events
GROUP BY organization_id
ORDER BY organization_id;

-- 1.3 Flyway 版本
SELECT max(version) FROM flyway_schema_history WHERE success;
```

把三份结果存成 `baseline-<UTC 时间戳>.txt`。

---

## 2. 静默期：阻断新写入（必须先做）

```bash
python3 scripts/operations/generation_runner_backup.py quiesce
```

这一步会阻断新写入并排空活动任务。**跳过它得到的备份是运行中快照**，
恢复后可能出现半完成的任务与租约，比没有备份更危险。

确认已静默：

```sql
SELECT count(*) FROM usage_reservations WHERE status = 'RESERVED';  -- 应趋于稳定
```

---

## 3. 恢复到新实例

从备份/PITR 恢复到**一个全新的空实例**，不要恢复到既有实例上：

```bash
# 托管 PostgreSQL（Neon 等）：按控制台/CLI 从时间点分叉出新分支
# 自管：
pg_restore --create --clean --if-exists \
  --dbname "$RESTORE_TARGET_URL" \
  --jobs 4 \
  /path/to/backup.dump
```

记录三个数字（后面要用）：

- 恢复起点时间（备份时间点 / PITR 目标时间）
- 恢复完成时间
- **RTO = 完成 − 开始**

---

## 4. 恢复后验证（逐项，全过才算）

### 4.1 Schema 完整性

```bash
ELMOS_COMMERCIAL_DATABASE_URL="$RESTORE_TARGET_URL" \
  mvn -pl modules/persistence -am flyway:validate
```

要求：`validate` 通过，版本等于第 1.3 步记录的版本，**无 checksum drift**。

### 4.2 数据一致性

重跑 1.1 与 1.2 的查询，对比：

| 检查 | 通过条件 |
|---|---|
| 四张表计数 | 与基线一致，或差值可由"恢复点之后的写入"完整解释 |
| `ledger_digest` | 逐组织完全一致 |
| `sum(quantity)` | 逐组织完全一致 |

**任何无法解释的差异 = 演练失败。** 不要用"应该是时间差"糊弄过去。

### 4.3 RLS 与最小权限（关键，最容易在恢复后丢失）

```sql
-- 运行角色属性必须保持
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles
WHERE rolname = current_setting('elmos.runtime_role', true);
-- 期望：rolsuper = f, rolbypassrls = f

-- 强制 RLS 仍然开启
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class WHERE relrowsecurity = true ORDER BY relname;
```

用运行身份做一次**跨租户负向读**：必须读不到别的组织的数据。
恢复常见的坑是角色属性或 GRANT 没跟着回来，结果 RLS 形同虚设。

### 4.4 应用层可用

把 `commercial-api` 指向恢复实例启动：

```
GET /actuator/health/readiness   → UP
```

`BillingDatabaseHealthIndicator` 会检查目录版本与 V49 核心预留函数。
readiness 为 UP 才说明恢复出来的库对应用是可用的，不只是"表还在"。

---

## 5. 结果记录

写入 `deploy/production/backup/drills/drill-<UTC 时间戳>.md`：

```
演练日期：
执行人：                      验证人：（必须不同人）
备份来源与时间点：
RTO（实测）：                 RPO（实测数据丢失窗口）：
4.1 Schema：      PASS / FAIL
4.2 数据一致性：   PASS / FAIL    （附 ledger_digest 对比）
4.3 RLS 与权限：   PASS / FAIL    （附跨租户负向读结果）
4.4 应用 readiness：PASS / FAIL
结论：RESTORE_VERIFIED / RESTORE_FAILED
遗留问题：
```

**只有四项全 PASS 才能写 `RESTORE_VERIFIED`。** 任一项 FAIL 时：
不要重跑到通过为止就当作通过，先修根因，再重新完整演练一次。

---

## 6. 与风险闭合的关系

- 一次 `RESTORE_VERIFIED` 演练 → RISK-DATA-001 可从 `OPEN` 降为"已验证恢复，
  待补跨区 DR"
- **完全关闭**还需要：跨区/跨可用区 DR 演练、明确的 RPO/RTO 承诺、
  以及这两项与对外 SLA 文本一致
- 演练结果不能反向修改任何既有的 `NOT_RUN` 记录；它是新增证据，不是对旧状态的改写

# Elmos 数据库安全、RLS 与凭据边界

**目标：** 在多租户、长任务、Agent 自主工具执行和客户私有源码场景中，确保任何服务、Worker、模型或运维查询都不能越过租户、项目、Run、Artifact 与凭据边界。

---

## 1. 威胁模型

重点防御：

- Tenant A 读取 Tenant B 的 Job、源码索引、Evidence 或账单；
- Prompt Injection 诱导 Agent 查询其他项目；
- Worker 获得控制面数据库长期凭据；
- 租户上下文未设置导致 RLS 意外放行；
- SECURITY DEFINER 函数被 search_path 劫持；
- 只读副本或 BI 账号绕过租户过滤；
- 对象存储 URI 泄露后可跨租户下载；
- 调试日志泄露 Prompt、源码、Secret；
- 过期 Worker 使用旧 Lease 修改权威状态；
- 数据库管理员之外的角色修改 Evidence、Event、Ledger、Audit；
- 学习系统未经授权使用客户代码或结果。

---

## 2. 数据库角色模型

不要让所有服务共用一个超级账号。建议至少：

| 角色 | 权限 |
|---|---|
| `elmos_migrator` | DDL、migration；仅 CI/CD 临时使用 |
| `elmos_control_api` | core/exec/artifact/verify 受控读写；不能绕过 Gate |
| `elmos_scheduler` | Task/Attempt/Lease/Checkpoint/Outbox |
| `elmos_runtime_gateway` | Session/Event/Tool/Approval 元数据 |
| `elmos_model_router` | metering、route/price、有限 Run 元数据 |
| `elmos_analyzer` | analysis 写入、Artifact 读引用 |
| `elmos_transformer` | generation/transform 写入 |
| `elmos_verifier` | verify/evidence 写入；Gate 请求但不直接改 Run completed |
| `elmos_learning` | 只读 verified + authorized 数据，写 learning schema |
| `elmos_ops_readonly` | security-invoker views 与有限运维查询 |
| `elmos_auditor` | append-only 审计读取，不可修改 |
| `elmos_backup` | 备份所需权限，不可业务写入 |

生产连接不得使用 owner/superuser。

---

## 3. 租户上下文

应用在每个事务开始时设置：

```sql
SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000000';
SET LOCAL app.actor_id = '...';
SET LOCAL app.request_id = '...';
```

必须使用 `SET LOCAL`，使变量在事务结束自动清理，避免连接池复用时串租户。

### 3.1 无租户上下文时 Fail Closed

`core.current_tenant_id()` 在无有效值时必须返回空/抛错，使 RLS `USING` 条件为 false，而不是默认全部租户。

### 3.2 事务包装器

推荐每个服务统一使用：

```text
beginTenantTransaction(tenant, actor, request)
  → BEGIN
  → SET LOCAL app.tenant_id
  → SET LOCAL app.actor_id
  → SET LOCAL app.request_id
  → execute
  → COMMIT/ROLLBACK
```

禁止在事务外仅执行一次 session-level `SET app.tenant_id`。

---

## 4. RLS 设计

参考迁移对 13 个商业 Schema 的租户表启用并强制 RLS：

```sql
ALTER TABLE ... ENABLE ROW LEVEL SECURITY;
ALTER TABLE ... FORCE ROW LEVEL SECURITY;
```

策略核心：

```sql
tenant_id = core.current_tenant_id()
```

### 4.1 为什么必须 FORCE RLS

普通 `ENABLE RLS` 对表 owner 可能不生效；`FORCE` 可防止应用 owner 角色意外绕过。生产应用仍不应成为表 owner。

### 4.2 `WITH CHECK`

不仅 SELECT/UPDATE 的 `USING`，INSERT/UPDATE 还必须有：

```sql
WITH CHECK (tenant_id = core.current_tenant_id())
```

否则服务可能向其他 tenant_id 插入数据。

### 4.3 Tenant 表本身

`core.tenant` 是租户根对象，可由平台级受控函数/后台管理，不应对普通租户会话开放全表读取。

---

## 5. Tenant ID 必须进入每张业务表

即使表能通过 FK 推导 tenant，也应显式保存 `tenant_id`，原因：

- RLS 不需要跨表 join；
- 索引可包含 tenant；
- 分片/归档容易；
- 防止错误 FK 关联；
- 审计与运维更清晰；
- 删除/导出可按 tenant 批量执行。

高价值 FK 建议使用复合键：

```text
(tenant_id, run_id)
(tenant_id, project_id)
(tenant_id, revision_id)
```

这样数据库层直接阻止跨租户引用。

---

## 6. Read Model 安全

所有运维视图使用：

```sql
WITH (security_invoker = true, security_barrier = true)
```

- `security_invoker`：视图查询采用调用者权限和 RLS；
- `security_barrier`：降低优化器重排导致信息侧漏的风险。

不要创建 SECURITY DEFINER 的“方便查询视图”绕过 RLS。

---

## 7. SECURITY DEFINER 函数

Claim、Event Append、Gate Complete 等高价值函数可能需要 `SECURITY DEFINER`。必须：

1. 固定 `search_path`：

```sql
SET search_path = pg_catalog, core, exec, verify, integration;
```

2. 所有对象使用 Schema-qualified 名称；
3. 函数 owner 为不可登录的受控 owner；在 `FORCE RLS` 下，该专用 Owner 需要 `BYPASSRLS`，但绝不能授予任何 Login Role；
4. `REVOKE ALL ... FROM PUBLIC`；
5. 仅 GRANT 给对应服务角色；
6. 函数内部再次检查 tenant_id、actor、fence 和 revision；
7. 不接受任意 SQL、table name 或 function name；
8. 动态 SQL 必须使用 `format('%I', ...)` 且输入来自 allowlist；
9. 记录审计事件；
10. 用 pgTAP/集成测试验证越权调用失败。

生产角色与 Grant 示例见 `database/roles/roles-and-grants.example.sql`。

---

## 8. Worker 数据库访问

### 8.1 推荐：Worker 不直接连接控制库

Worker 通过 Runtime Gateway/Worker API：

```text
claim result
upload artifact
append bounded progress
finish attempt
```

使用短期 Run Token，限制：

- tenant_id；
- run_id；
- task_attempt_id；
- lease_generation；
- allowed actions；
- expiry；
- workspace identity。

### 8.2 必须直连时

使用每 Run/Worker 临时数据库凭据：

- 有效期小于 Lease；
- 仅访问有限 stored functions；
- 无表直接权限；
- 连接使用 mTLS；
- Worker 终止时撤销；
- 不写入镜像或环境 dump。

---

## 9. 凭据隔离

长期凭据仅存在：

- Cloud Secret Manager；
- Vault；
- Kubernetes External Secrets；
- 客户 VPC Secret Store。

Agent/Worker 子进程不得继承：

- 数据库管理员密码；
- GitHub/GitLab/Tracker 长期 Token；
- 云账户长期 Key；
- Kubernetes ServiceAccount Token；
- OpenRouter/OpenAI/其他 Provider 管理 Key；
- 对象存储主密钥。

Host-side Tool Adapter 使用凭据完成调用，只把结构化结果返回 Agent。

---

## 10. 对象存储授权

数据库中的 `storage_uri` 不是授权令牌。

下载流程：

```text
请求 artifact_id
→ Control API 读取 RLS 保护的 artifact row
→ 验证 actor/project/run 权限
→ 生成短期 presigned URL 或代理流
→ 写 audit event
```

要求：

- URL TTL 1–15 分钟；
- tenant-prefixed/object-key opaque；
- Bucket 默认 private；
- Evidence bucket 开 Object Lock/WORM；
- SSE-KMS 或客户管理密钥；
- 禁止公开 ACL；
- CAS digest 不作为跨租户发现接口。

---

## 11. Append-only 与不可变数据

以下对象原则上不可 UPDATE/DELETE：

- run/session events；
- evidence item/bundle/gate；
- usage/cost/revenue ledgers；
- audit event；
- sealed checkpoint manifest；
- certified rule release。

修正必须追加：

- revocation；
- superseding record；
- reversal ledger；
- new gate evaluation；
- new checkpoint。

应用权限层和数据库 trigger 双重强制。

---

## 12. P05 职责分离

建议角色分离：

```text
Generator/Transformer
  不能写 Gate pass

Verifier
  可写 verification result/evidence
  不能直接把 Run 改 completed

Gate Service / DB Function
  重新计算和验证
  才能原子完成 Run
```

关键 Evidence 由不同执行角色或 deterministic verifier 产生，避免单 Agent 写代码后给自己签发通过证据。

---

## 13. Learning 数据授权

`learning.data_authorization` 是 P07 的硬门。

必须记录：

- tenant/project/run scope；
- 允许的用途：统计、RAG、规则、训练；
- 是否允许源代码；
- 是否允许 prompt/completion；
- 去标识化要求；
- 保留期；
- 撤销时间；
- 法律依据/合同版本；
- actor。

无授权时，Learning Worker 只能读取聚合指标或公开 benchmark，不能读取客户源码、Session、Artifact 或 Evidence 原文。

授权撤销后：

- 阻止新消费；
- 追踪已派生资产；
- 根据政策删除/隔离；
- 已发布通用规则需进行来源污染评估；
- 写审计。

---

## 14. 字段级敏感度

建议分类：

| 分类 | 例子 | 控制 |
|---|---|---|
| Public | 产品版本、公开模型名 | 普通 |
| Internal | Task 状态、成本摘要 | RBAC |
| Confidential | 源码索引、Prompt、Evidence | 加密、最小权限、审计 |
| Restricted | Secret、凭据、个人信息 | 不进入普通表/日志；专用 Secret Store |

敏感 JSONB 不应混入可广泛读取的 metadata。必要时拆专表或只存 opaque reference。

---

## 15. 加密

### 15.1 传输

- PostgreSQL 强制 TLS；
- 服务间 mTLS；
- 禁止 `sslmode=disable`；
- 证书轮换自动化；
- 客户 VPC 使用 Private Link/VPN。

### 15.2 静态

- 云盘/数据库透明加密；
- Backup 加密；
- CAS SSE-KMS；
- 高敏租户可 tenant-specific KMS key；
- 密钥版本进入 metadata，不存原密钥。

### 15.3 应用字段加密

只有确实需要在 DB 保存且数据库管理员也不应直接看见的字段才做 envelope encryption。不要自行实现密码学；使用 KMS/Vault Transit。

---

## 16. 日志与可观测安全

禁止记录：

- 数据库 DSN 密码；
- Authorization header；
- 原始 Provider Key；
- 完整 Prompt/Completion；
- 源码正文；
- Presigned URL；
- Session Cookie；
- 私钥；
- 大型 Tool 输出。

日志只记录：

```text
tenant opaque id
run/task/attempt id
request id
operation
status/error code
duration
bounded size/count/hash
```

生产 debug logging 默认关闭；临时打开必须有 TTL 和审计。

---

## 17. 审计事件

高价值事件至少包括：

- 登录/授权/角色变更；
- Tenant/Project 创建删除；
- Secret/Provider connection 变更；
- Job 提交、取消、恢复；
- 权限批准/拒绝；
- Sandbox escalation；
- Artifact 下载/导出；
- Evidence revocation/Waiver；
- Gate pass/fail；
- Deployment/rollback；
- Learning authorization；
- Retention/legal hold；
- 运维越权查询；
- Migration。

Audit append-only，并使用独立长期保留策略。

---

## 18. 运维 Break-glass

生产紧急访问：

1. 工单/事故号；
2. 双人审批；
3. 临时角色；
4. 最短 TTL；
5. MFA；
6. 全量命令和查询审计；
7. 默认只读；
8. 使用视图/存储过程，不直接扫全表；
9. 结束后自动撤销；
10. 事故复盘。

不得使用共享 `postgres` 密码日常运维。

---

## 19. RLS 测试矩阵

CI 必须创建 Tenant A/B，并验证：

| 测试 | 预期 |
|---|---|
| A 查询自己的 Job | 可见 |
| A 按 B 的 job_id 查询 | 0 行/Not Found |
| A 插入 tenant_id=B | 拒绝 |
| A 更新记录 tenant_id→B | 拒绝 |
| A 通过视图查询 | 仅 A |
| A 调用 stored function 传 B id | 拒绝 |
| 无 tenant context 查询 | 0 行或错误 |
| 表 owner 应用角色查询 | 仍受 RLS |
| 只读副本角色查询 | 仍受 RLS |
| Learning 无授权读源码资产 | 拒绝 |
| Artifact presign B 的 id | 拒绝 |
| Gate function 跨租户 id | 拒绝 |

---

## 20. 数据库权限验收查询

查看 LOGIN 角色：

```sql
SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
FROM pg_roles
WHERE rolcanlogin
ORDER BY rolname;
```

生产应用角色必须：

```text
rolsuper = false
rolbypassrls = false
rolcreaterole = false
rolcreatedb = false
```

检查未强制 RLS 的租户表：

```sql
SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname IN (
    'core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
  AND c.relname <> 'tenant'
  AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
ORDER BY 1,2;
```

结果必须为空。

检查 PUBLIC 函数权限：

```sql
SELECT n.nspname, p.proname
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('core','exec','verify','integration','ops')
  AND has_function_privilege('public', p.oid, 'EXECUTE');
```

高价值事务函数不应对 PUBLIC 开放。

---

## 21. 安全上线门

生产上线前必须满足：

- [ ] 所有应用使用独立非 owner 角色；
- [ ] RLS + FORCE RLS 全覆盖；
- [ ] 无租户上下文 fail closed；
- [ ] SECURITY DEFINER 固定 search_path；
- [ ] PUBLIC 已撤销高价值函数执行权；
- [ ] Worker 无控制库长期凭据；
- [ ] Artifact 下载经授权生成短期 URL；
- [ ] Evidence/Event/Ledger/Audit 不可变；
- [ ] P05 职责分离；
- [ ] Learning 受 data authorization 门控；
- [ ] 数据库与备份加密；
- [ ] RLS 双租户集成测试通过；
- [ ] Secret scanning 和日志脱敏通过；
- [ ] Break-glass 流程演练完成。

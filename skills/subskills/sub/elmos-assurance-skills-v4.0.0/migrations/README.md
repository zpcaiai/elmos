# Persistence implementation contract — NOT_RUN

`001_assurance_reference.sql` 是 PostgreSQL 参考 DDL，不是可以直接套用现有 Elmos 的已验收生产迁移。bootstrap 首先识别现有租户、project/run、K8、账本/事件表并复用；只在隔离测试库审阅执行。数据库候选与 exact image digest 由依赖解析批准。本次无 PostgreSQL 原生执行证据。

## 必须补齐的生产行为

- 12张表使用 tenant 复合主外键，RLS/FORCE RLS 作为纵深防御。app连接不得为superuser/BYPASSRLS；不可让待测仓库或任意SQL工具使用控制库凭据。认证后服务器在事务内设置SET LOCAL tenant，连接归还清理；租户ID不能从payload直接信任。
- API端验证role、VerifiedSecurityContext、invocation lease和参数权限；RLS不能替代role/项目ACL、对象存储ACL或授权服务。原生测试必须使用实际runtime数据库角色，而不是owner。
- 先锁run再检查epoch/state/lease并提交result+outbox；取消、lease换代和封存同样锁run。重复提交：服务先读取已提交摘要，同摘要幂等返回，异摘要409；不要用ON CONFLICT DO NOTHING吞掉冲突。重试不能绕过撤销检查，也不能再次产生外部副作用。
- seal关闭runner evidence inventory。Ethen post-seal意见保存在独立audit_decisions，最终bundle组合sealed runner root和audit envelope root，不能修改原manifest。参考Python gate为单次最终sealed inventory，产品分阶段seal需明确两个root。
- evidence为完整尝试历史，result_commits为选定step结果。门禁必须读取已封存inventory、失败/未知历史以及有效supersession记录，不能只查询绿色结果。一个evidence行代表一个obligation绑定；报告跨多个义务时写多行或按既有桥表复用，digest不得改变。
- GateDecision为append-only。只有K8授权角色能插入attestations；它必须核验对应PASS、适用性/版本/有效期/外审、未撤销状态并请求签署。DDL本身不执行密码学验证，也不能阻止获写入权的错误服务发布伪证；IAM/KMS和策略是必需部分。
- outbox轮询与发布以event_id幂等；outbox可更新投递状态但payload字段须由服务/列级权限保护。inbox同event ID异payload必须告警，不能当重复消费忽略。
- budget_accounts在同一事务FOR UPDATE，检查可用余额/并发，创建reservation并更新汇总。未知真实费用保持reserved并转RECONCILE_REQUIRED，不能归零。供应商超额实际成本允许进入settled并阻断新admission，不伪造绝对不会超预算。预算、税务、发票语义复用现有账本。
- GRANT/REVOKE由部署审阅专属迁移：runner只能授权commit，auditor只写audit，K8才可签发；不要授予application角色schema owner权限。生产密钥不得入SQL或表字段。

## Native acceptance

在测试库验证：跨tenant SELECT/INSERT/复合FK；无tenant setting；池复用泄漏；两个commit竞争；cancel vs commit；过期lease；stale epoch；重复key异payload；sealed evidence append；outbox crash/replay；budget并发4→最多3；未知费用保留；K8拒绝为FAIL签发。所有场景须保存SQL版本/角色/结果。

## Rollback

先禁用写入feature flag，排空或阻断新run；旧路径与读证据继续。不得通过DROP schema/DELETE evidence实现回滚。备份/恢复须演练。必要的追加修正迁移与兼容视图另案批准；历史摘要和撤销记录保留。

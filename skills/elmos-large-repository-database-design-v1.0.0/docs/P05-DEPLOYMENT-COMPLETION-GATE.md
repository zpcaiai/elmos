# P05 部署完成门

## 1. 目的

`helm upgrade --atomic`、Pod Ready、Migration 成功都只是输入证据，不是最终完成裁决。Elmos 通过 `ops.release`、`ops.deployment`、`ops.migration_run`、`ops.service_health_snapshot`、`ops.deployment_check`、`ops.deployment_gate` 保存部署事实，并由 `ops.complete_deployment_with_gate()` 原子完成。

## 2. 精确绑定

Deployment Gate 必须绑定：

- `release_id`；
- Release Manifest SHA-256；
- 所有 required component 的 image digest；
- Helm release name/revision；
- Kubernetes namespace/environment；
- database schema target；
- gate policy revision；
- 配置/policy/workflow revision；
- 验证 Evidence Bundle。

不得以 tag、服务名或“最近一次部署”代替精确 Revision。

## 3. Gate 输入

至少包含：

1. Migration：目标版本成功或明确 `not_required`；
2. Health：required component 最新 `/livez` 与 `/readyz` 通过；
3. Version：实际 image digest 与 Release Component 相等；
4. Metrics：错误率、启动失败、队列积压在阈值内；
5. Functional：Smoke/Integration/E2E；
6. Security：SBOM、签名、漏洞、Secret、RLS；
7. Recovery：Migration rollback/forward-fix、backup readiness；
8. Documentation：Release notes、Runbook、known risks。

## 4. 状态流

```text
ops.release: candidate
ops.deployment: pending → migrating → deploying → verifying
ops.deployment_check: not_run/running → passed/failed/blocked
ops.deployment_gate: pass/fail/blocked/error
ops.complete_deployment_with_gate()
  → deployment=healthy
  → release=deployed
  → outbox deployment.completed
```

任何失败证据都应保留；不能通过覆盖旧行伪造成功。

## 5. Gate Job 行为

Helm 的 post-install/post-upgrade Job 应：

1. 从 Control API 创建/定位精确 Deployment；
2. 读取 Release Manifest；
3. 轮询 required 服务四端点；
4. 将每次观察写入 `ops.service_health_snapshot`；
5. 执行部署检查并写入 `ops.deployment_check`；
6. 生成 sealed deployment Evidence；
7. 写入 `ops.deployment_gate`；
8. 调用 `ops.complete_deployment_with_gate()`；
9. Gate 非 pass 时以非零退出，阻断发布。

Gate Job 不需要 Kubernetes ServiceAccount token；推荐通过 Control API、服务 DNS 和只读监控接口完成。确需查询 Kubernetes API 时使用单独最小 RBAC 的观察器，而不是给 Gate 全集群权限。

## 6. 失败处理

- Migration 失败：不部署应用，保留 migration output artifact；
- Pod Ready 但 digest 不符：fail；
- `/version` 与 schema 不兼容：blocked；
- Evidence 上传失败：blocked；
- Gate Job 超时：error，不得标记 healthy；
- Gate 已 pass 后 Evidence 被撤销：将 Deployment 标记 degraded，并触发重新验证/回滚决策。

## 7. CI/CD 必须上传的证据

```text
release-manifest.json
image-digests.json
sbom-index.json
signature-verification.json
migration-result.json
health-snapshots.json
smoke-test.xml
integration-test.xml
e2e-results/
security-results/
capacity-summary.json
rollback-readiness.json
```

原始大文件进入 Evidence Bucket；PostgreSQL 只保存 Artifact/Evidence 引用、哈希、状态和 Revision。

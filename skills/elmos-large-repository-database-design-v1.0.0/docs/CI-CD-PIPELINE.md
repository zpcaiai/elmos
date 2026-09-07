# Elmos 商业生产级 CI/CD 流水线

## 阶段

| Stage | 主要动作 | 阻断条件 |
|---|---|---|
| Contract | Database/API/Workflow/Skill/Helm 静态校验 | Schema 漂移、未知列、缺合同 |
| Test | Unit/Integration/Database/Concurrency | 任一 required test 失败 |
| Build | 多阶段 OCI 镜像 | 未固定 source SHA/base digest |
| Supply Chain | SBOM、签名、漏洞、Secret、License | Critical 或策略违规 |
| Release Manifest | 汇总所有 component digest/revision | mutable tag、缺 digest |
| Migration | Flyway migrate + invariants | checksum/DDL/invariant 失败 |
| Deploy | Helm canary/atomic | rollout 失败 |
| Evidence | Health、version、test、security、performance | Evidence 缺失/过期 |
| P05 Gate | `ops.complete_deployment_with_gate()` | 非 pass |
| Promote | Staging→Production/流量提升 | stability hold 不满足 |

## 镜像矩阵

```text
elmos-web
elmos-control-api
elmos-scheduler
elmos-runtime-gateway
elmos-model-router
elmos-worker-controller
elmos-worker-analyzer
elmos-worker-transformer
elmos-worker-verifier
elmos-worker-learning
elmos-migrate
elmos-deployment-gate
```

构建结果必须写入 Release Manifest，而不是让 Helm 自己推断。

## 数据库 CI

`.github/workflows/database-ci.yml` 已提供：

- PostgreSQL 16/17 矩阵；
- Flyway 空库 migrate；
- checksum validate；
- SQL invariants；
- 静态 DDL/FK/RLS/函数/运维查询校验；
- migration image build。

还应增加：

- 从前一生产 Schema 的升级测试；
- 并发 Claim/Lease/Fencing 测试；
- 中断 migration 行为；
- PITR 恢复后 invariants；
- 兼容旧应用版本的 expand/contract 测试。

## Release Manifest 最小字段

```json
{
  "release_id": "uuid",
  "git_sha": "full-sha",
  "created_at": "RFC3339",
  "chart": {"name": "elmos", "version": "1.1.0"},
  "database_schema": "V090",
  "gate_policy_revision": "p05-deployment-gate-v1",
  "components": [
    {"name": "control-api", "image": "repo/elmos-control-api", "digest": "sha256:..."}
  ],
  "contracts": {
    "api": "2026-08-01",
    "workflow": "1",
    "session_event": "1",
    "evidence": "1"
  }
}
```

## Staging 与 Production

- Staging：每个 main build 自动部署；Gate pass 后可供集成测试；
- Production：使用已通过 Staging 的同一 digest，不重新构建；
- Production values 必须由环境仓库或受保护分支管理；
- Promotion 只改变环境绑定，不改变镜像内容；
- 回滚使用 last-known-good Release Manifest。

## P05 与流水线关系

CI 生成 Evidence，P05 负责裁决；CI 自己不能通过设置变量 `DEPLOYED=true` 绕过 Gate。Gate 失败时流水线必须失败，并保留所有失败证据与部署状态供恢复。

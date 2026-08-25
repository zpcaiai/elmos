# 数据库与存储模型基线

## 1. PostgreSQL 表域

### Identity/Governance

- `tenants`
- `users`
- `memberships`
- `roles`
- `policies`
- `share_links`
- `audit_events`

### Project/Revision

- `projects`
- `system_workspaces`
- `repositories`
- `revisions`
- `revision_manifests`
- `project_fingerprints`
- `analysis_runs`
- `analysis_stages`

### Evidence/Knowledge Metadata

- `claims`
- `evidence_records`
- `claim_evidence`
- `manual_confirmations`
- `architecture_models`
- `architecture_overrides`
- `flows`
- `capabilities`
- `data_assets`
- `api_contracts`
- `event_contracts`

### Artifact

- `artifacts`
- `artifact_versions`
- `artifact_blocks`
- `artifact_locks`
- `human_overrides`
- `merge_conflicts`
- `reviews`
- `exports`
- `report_bundles`

### Execution/Operations

- `jobs`
- `checkpoints`
- `idempotency_records`
- `estimates`
- `provider_rates`
- `usage_events`
- `quotas`
- `certifications`
- `certification_evidence`

## 2. 分区和索引

- `audit_events`, `usage_events`, `runtime_observations` 按月/租户分区；
- `claims`, `artifact_versions` 按 project 或 tenant 分区视规模决定；
- 所有查询路径有 `(tenant_id, project_id, revision_id)` 复合索引；
- 幂等表对 `(tenant_id, operation, idempotency_key)` 唯一；
- Artifact stable ID + version 唯一；
- Evidence locator 对 source hash/revision/symbol 建索引。

## 3. Object Store Key

```text
tenant/{tenant_id}/project/{project_id}/revision/{revision_id}/source/{sha256}
tenant/{tenant_id}/project/{project_id}/analysis/{run_id}/code-ir/{shard}.jsonl.zst
tenant/{tenant_id}/project/{project_id}/analysis/{run_id}/evidence/{bundle}.json.zst
tenant/{tenant_id}/project/{project_id}/artifact/{artifact_id}/{version}/{file}
```

## 4. Graph Store

图存储是可重建投影，必须记录：

- graph schema version；
- project/revision；
- projection build id；
- source IR hashes；
- completeness；
- build timestamp；
- superseded projection。

## 5. 数据删除

- Soft delete 仅用于用户体验，不满足彻底删除；
- 删除工作流枚举 PostgreSQL、对象、图、搜索、缓存和备份策略；
- 认证/审计保留与客户合同和法规一致；
- 删除证明包含对象数量、hash 前缀和完成时间，不含代码内容。

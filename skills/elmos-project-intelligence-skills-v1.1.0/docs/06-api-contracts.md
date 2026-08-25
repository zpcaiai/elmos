# API 契约基线

## 1. 通用约定

- Base path：`/api/v1`
- 身份：OIDC/OAuth2/JWT 或企业反向代理身份；
- 租户上下文由服务端解析，不信任客户端任意 `tenant_id`；
- 所有写操作支持 `Idempotency-Key`；
- 长任务返回 `202 Accepted` + `job_id`；
- 分页使用 opaque cursor；
- 错误采用稳定 code、message、details、retryable、trace_id；
- revision-sensitive API 必须显式 `revision_id`；
- ETag/If-Match 用于人工编辑和版本冲突。

## 2. 主要资源

### Projects / Repositories / Revisions

```text
POST   /projects
POST   /projects/{id}/repositories
POST   /repositories/{id}/imports
GET    /projects/{id}/revisions
GET    /revisions/{id}/manifest
POST   /revisions/{id}/analysis-runs
```

### Code Reader / Navigation

```text
GET    /revisions/{id}/files
GET    /files/{id}/content
GET    /files/{id}/history
GET    /diffs
GET    /symbols/{id}
GET    /navigation/definition
GET    /navigation/references
GET    /navigation/implementations
GET    /navigation/call-hierarchy
GET    /navigation/type-hierarchy
POST   /navigation/paths
```

### Knowledge / Architecture / Flows

```text
GET/POST /architecture/models
GET      /architecture/views
GET      /architecture/diff
GET/POST /capabilities
GET      /features/{id}/traceability
GET/POST /flows
GET      /flows/{id}/paths
GET      /data-assets
POST     /data-lineage/query
GET      /apis
GET      /events
GET      /integrations
```

### Evidence / Search / Q&A

```text
GET      /claims/{id}
GET      /evidence/{id}
POST     /evidence-bundles
POST     /search
POST     /qa
POST     /qa/{id}/feedback
POST     /explanations
```

### Diagrams / Documents / Presentations

```text
POST     /diagram-specs
POST     /diagram-specs/validate
POST     /diagrams/render
GET      /diagrams/{id}/versions
POST     /diagrams/{id}/merge
POST     /documents/generate
POST     /documents/{id}/regenerate
POST     /presentations/generate
POST     /presentations/{id}/regenerate
POST     /artifacts/{id}/exports
```

### Analysis / Rules / Impact / Security

```text
POST     /impact-analysis
GET/POST /architecture-rules
POST     /rule-runs
GET/POST /waivers
GET      /drift
POST     /drift/{id}/decisions
GET      /risks
POST     /security/scans
GET      /threat-models
```

### Jobs / Estimates / Certification

```text
GET      /jobs/{id}
POST     /jobs/{id}/pause
POST     /jobs/{id}/resume
POST     /jobs/{id}/cancel
GET      /jobs/{id}/events
POST     /estimates
POST     /estimates/{id}/reforecast
POST     /certifications
POST     /certifications/{id}/sign
```

## 3. Job 状态

```text
QUEUED → RUNNING → PAUSING → PAUSED → RESUMING → RUNNING
RUNNING → SUCCEEDED
RUNNING → FAILED_RETRYABLE → RETRYING → RUNNING
RUNNING → FAILED_FINAL
QUEUED/RUNNING/PAUSED → CANCELLING → CANCELLED
```

## 4. 错误分类

| code family | 是否重试 | 示例 |
|---|---|---|
| `INPUT_*` | 否 | invalid revision、unsupported archive |
| `AUTH_*` | 视情况 | credential expired、permission denied |
| `CAPACITY_*` | 是 | queue full、quota temporary |
| `DEPENDENCY_*` | 是/否 | Git provider rate limit |
| `ANALYSIS_*` | 部分 | parser crash、unsupported syntax |
| `ARTIFACT_*` | 部分 | render timeout、template invalid |
| `CONFLICT_*` | 否 | ETag mismatch、locked block |
| `INTERNAL_*` | 是 | unexpected worker failure |

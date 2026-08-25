# 事件与工作流契约

## 1. 事件信封

```yaml
event_id: uuid
event_type: elmos.project-intelligence.revision.ingested.v1
occurred_at: RFC3339
tenant_id: uuid
project_id: uuid
revision_id: uuid
analysis_run_id: uuid|null
job_id: uuid|null
actor:
  type: user|service
  id: string
idempotency_key: string
traceparent: string|null
payload_ref: s3://...|null
payload: {}
schema_version: 1
```

大体积 Code IR、图谱 shard、文档和图片使用 `payload_ref`，事件中不传源码全文。

## 2. 核心事件

```text
project.created
repository.import.requested
repository.import.completed
repository.import.failed
revision.ingested
fingerprint.completed
analysis.run.started
analysis.stage.checkpointed
code-ir.shard.completed
graph.projection.updated
evidence.claim.updated
runtime.trace.imported
architecture.discovered
flow.discovered
diagram.requested/completed/failed
document.requested/completed/failed
presentation.requested/completed/failed
artifact.stale
impact.completed
drift.detected
security.finding.created
job.paused/resumed/cancelled
conversion.mapping.updated
certification.completed
usage.recorded
```

## 3. 工作流要求

- 每个 Stage 有 input manifest、output refs、attempt、checkpoint；
- Stage 重试不能重复创建 ArtifactVersion、PR、通知或账单事件；
- 取消应传播到子任务，但保留已完成且确认的结果；
- Workflow code 升级需版本化；
- 长任务可通过 heartbeat 检测 worker 丢失；
- poison input 不无限重试；
- outbox/inbox 保障数据库状态和事件一致。

## 4. 检查点

```yaml
checkpoint_id:
workflow_id:
stage:
input_manifest_hash:
completed_units:
output_refs:
side_effect_keys:
parser_versions:
model_versions:
template_versions:
created_at:
expires_at:
resume_compatibility:
```

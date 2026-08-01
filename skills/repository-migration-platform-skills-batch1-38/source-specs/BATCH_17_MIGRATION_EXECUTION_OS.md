# Batch 17：Migration Execution OS

## 总体目标

把 Migration Plan 执行为可跨数周或数月运行、可暂停、恢复、取消、重试、审批、回滚和灾难恢复的长程迁移操作系统。

## 建议仓库结构

```text
execution-ir/
task-graph-runtime/
durable-workflow/
worker-control-plane/
model-router/
tool-runtime/
sandbox-runtime/
approval-runtime/
side-effect-runtime/
cost-governance/
```

## 1. Task Graph 与 Durable Workflow

- Program/Wave/Workflow/Task/Attempt/Event/Signal/Timer IR
- Hard/Soft/Data/Evidence/Certificate/Resource/Approval/Conditional/Compensation Edges
- Event-sourced History、Deterministic Replay、Continue-as-New、Version Markers
## 2. Checkpoint 与生命周期控制

- Logical/Repository/Artifact/Evidence/Certificate/DB/Message/Proof/Agent/Cost Checkpoints
- Soft/Hard Pause、Safe Point、Resume Drift Validation
- Cooperative/Forced Cancel、Unknown Outcome、Cleanup、Compensation
## 3. Workers 与 Scheduler

- Worker Identity/Capability/Trust/Attestation
- Lease、Heartbeat、Epoch、Fencing、Drain、Quarantine
- Capability/Priority/Fair-share/Deadline/Critical-path/Cost/Security-aware Scheduling
## 4. Model Router、Tool Runtime、Sandbox

- Model Capability/Privacy/Cost/Context Routing
- Registered Tool Schema、Permission、Side-Effect、Idempotency、Cancellation
- Container/MicroVM/WASM、Deny-by-default Network、Secret Lease、Forensics
## 5. Governed Side Effects

- Retry Ownership/Budget/Amplification Guard
- End-to-End Idempotency
- Side-Effect Ledger、Intent、Approval、Confirmation、Reconciliation
- Saga/Compensation/Manual Recovery
## 6. Artifact/Evidence/Certificate 与多仓库多Wave

- Atomic Artifact/Evidence Commit
- Certificate Gate、Expiry/Revocation Signals
- Multi-repo Prepare/Verify/Publish、Partial Failure Recovery
- Long-running Handoff、Cost/Token/Resource Governance

## 认证体系：MX1–MX5 Migration Execution

MX1–MX5 Migration Execution 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Compiled Task Graphs
- Workflow Histories
- Checkpoint Bundles
- Approval Records
- Worker Registry and Leases
- Model/Tool Routing Evidence
- Side-Effect Ledger
- Multi-repo/Multi-wave Reports
- Cost Reports
- MX1–MX5 Certificates

## 硬性原则

- Worker 失联不代表停止，必须 Fencing
- Workflow Replay 不得重新调用外部世界
- Pause/Cancel 不等于副作用未发生
- Retry 必须有错误分类和幂等协议
- Budget 不足不得静默跳过关键验证
- Certificate Gate 不可由 Admin 绕过

## Definition of Done

```yaml
task_graph: pass
durable_history: pass
checkpoint_resume: pass
pause_cancel: pass
worker_lease_fencing: pass
model_tool_sandbox: pass
approval: pass
retry_idempotency: pass
side_effect_ledger: pass
artifact_evidence_certificate_coordination: pass
split_brain_findings: 0
mx1_to_mx5: pass
```

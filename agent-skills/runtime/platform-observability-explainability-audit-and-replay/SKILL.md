---
name: platform-observability-explainability-audit-and-replay
description: "统一追踪Workflow、Agent、Tool、Policy、Human Decision和Value，并支持审计和安全重放。"
---

# Unified Observability

## Correlation

Tenant ID
Plan ID
Workflow ID
Agent Task ID
Tool Call ID
Policy Decision ID
Human Decision ID
Execution ID
Evidence ID

## Span类型

PLAN
SIMULATION
POLICY
AGENT
MODEL
HANDOFF
TOOL
ENGINE
HUMAN_WAIT
EXECUTION
COMPENSATION
VALUE

## Signals

Trace
Metric
Log
Event
Profile
Audit
Cost

## 敏感内容

默认不明文记录：

Prompt
Response
Document
Secret
Personal Data
Tool Output
Private Business Data

使用：

Hash
Reference
Redaction
Restricted Store
Sampling

## Explainability

Why this Plan?
Why this Agent?
Why this Tool?
Why Allow or Deny?
Why this Sequence?
What Evidence?
What Changed?

## Audit

Append-only
Signed
Time Anchored
Tenant Bound
Retention Controlled
Searchable
Exportable

## Replay

DRY_REPLAY
POLICY_REPLAY
SIMULATION_REPLAY
EVENT_REPLAY
AUDIT_REPLAY

生产副作用默认抑制。

## 验收标准

- Trace跨引擎；
- Agent中间步骤可见；
- 敏感内容最小化；
- Audit不可静默修改；
- Decision可解释；
- Replay不重复副作用；
- 成本与Trace关联；
- 缺失Span产生Finding。

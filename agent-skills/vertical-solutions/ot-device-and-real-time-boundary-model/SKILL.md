---
name: ot-device-and-real-time-boundary-model
description: "Execute authoritative Batch 17 Skill 621 for ot device and real time boundary model. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Ot Device And Real Time Boundary Model

## Operating contract

Apply authoritative Batch 17 Skill 621. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## OT边界

```text
PLC
DCS
SCADA
HMI
Historian
MES
QMS
WMS
ERP
Edge Gateway
```

## 时间语义

* Scan Cycle；
  -Event Time；
  -Device Time；
  -Server Time；
  -Sequence；
  -Latency；
  -Jitter；
  -Offline Buffer。

## Hard Rules

* 普通Cloud Retry不能直接用于设备控制；
* 设备写入需显式授权；
* 时间戳来源保留；
* Edge断连需定义；
* 旧协议通过Adapter隔离；
* 安全控制与业务分析分离；
* Agent不得直接越过Safety PLC。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.

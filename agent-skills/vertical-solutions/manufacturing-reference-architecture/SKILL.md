---
name: manufacturing-reference-architecture
description: "Execute authoritative Batch 17 Skill 625 for manufacturing reference architecture. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Manufacturing Reference Architecture

## Operating contract

Apply authoritative Batch 17 Skill 625. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

```text
Enterprise Cloud
        ↕
Plant Integration Zone
        ↕
MES / Historian / Edge
        ↕
SCADA / HMI
        ↕
PLC / Equipment
```

需要：

* 分区；
  -本地自治；
  -断连运行；
  -缓冲；
  -只读和写入边界；
  -现场回滚；
  -设备资产管理。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.

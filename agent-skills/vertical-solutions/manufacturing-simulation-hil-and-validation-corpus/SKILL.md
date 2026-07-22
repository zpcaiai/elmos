---
name: manufacturing-simulation-hil-and-validation-corpus
description: "Execute authoritative Batch 17 Skill 624 for manufacturing simulation hil and validation corpus. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Manufacturing Simulation Hil And Validation Corpus

## Operating contract

Apply authoritative Batch 17 Skill 624. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Verification

```text
Device Simulator
Digital Twin
Software-in-the-loop
Hardware-in-the-loop
Factory Acceptance Test
Site Acceptance Test
Failure Injection
```

## Cases

* Tag突变；
  -设备断连；
  -时钟漂移；
  -报警风暴；
  -停机；
  -批次恢复；
  -网络分区；
  -错误Recipe；
  -紧急停止；
  -维护切换。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.

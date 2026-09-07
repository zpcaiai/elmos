---
name: manufacturing-security-and-safety-control-pack
description: "Execute authoritative Batch 17 Skill 622 for manufacturing security and safety control pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Manufacturing Security And Safety Control Pack

## Operating contract

Apply authoritative Batch 17 Skill 622. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Control Areas

```text
Zones and Conduits
Asset Inventory
Remote Access
Change Control
Patch Windows
Safety Boundary
Supplier Access
Backup
Recovery
Portable Media
Secure Development
```

## Hard Rules

* OT安全不能直接复制IT默认策略；
* 生产可用性和安全共同评估；
* Remote Access短期授权；
* 关键设备升级需维护窗口；
* 不允许自动重启关键控制器；
* Safety Case与Cybersecurity Case关联；
* 设备证书和生命周期纳入。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.

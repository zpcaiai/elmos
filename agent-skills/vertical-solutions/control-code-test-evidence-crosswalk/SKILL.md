---
name: control-code-test-evidence-crosswalk
description: "Execute authoritative Batch 17 Skill 599 for 建立监管控制到架构、代码、配置、测试、运行证据和Owner的完整Crosswalk。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Control Code Test Evidence Crosswalk

## Operating contract

Apply authoritative Batch 17 Skill 599. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

建立监管控制到架构、代码、配置、测试、运行证据和Owner的完整Crosswalk。

## Crosswalk

```text
Control
→ Architecture Decision
→ Implementation
→ Configuration
→ Test
→ Runtime Evidence
→ Owner
→ Status
```

## Record

```yaml
control_crosswalk:
  control_id: healthcare-break-glass-access

  implementation_refs: []
  config_refs: []
  test_refs: []
  audit_query_refs: []
  owner: security
  status: implemented
```

## Hard Rules

* Policy文档不能单独证明控制有效；
* 实现存在还需运行证据；
* 测试不能使用永久Bypass；
* 证据需绑定版本和时间；
* Shared Control需说明Tenant范围；
* Manual Control需执行记录；
* Control失效触发风险和通知。

## Acceptance Criteria

* Mandatory Control有Crosswalk；
* Evidence可自动采集；
* 审计人员可钻取；
* 失效控制可发现；
* 责任人明确；
* 合规包可自动生成。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.

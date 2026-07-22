---
name: legacy-health-report
description: Assemble the evidence-bound ELMOS Java legacy health report. Use whenever combining Batch 3 fingerprints, conflicts, vulnerabilities, risks, APIs, tests, recommendations and effort inputs.
---
# Legacy Health Report

## Workflow
1. Require a Snapshot ID and scanner/policy version.
2. Merge R001-R011 outputs without changing their evidence statuses.
3. Compute explainable health/risk summaries and preserve individual findings.
4. Recommend Java 17/21/25 only within organization policy and list assumptions.
5. Hash the canonical report and persist normalized evidence plus artifact reference.

## Acceptance
- Unknown vulnerability/build evidence prevents an all-clear status.
- Every finding links to a path or external evidence source.
- Same Snapshot and evidence produce the same report identity.


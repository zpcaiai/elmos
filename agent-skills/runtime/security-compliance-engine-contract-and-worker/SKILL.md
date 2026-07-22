---
name: security-compliance-engine-contract-and-worker
description: Operate the fail-closed ELMOS security and compliance worker across every modernization engine. Use for capabilities, scan, plan, controlled execution, validation, authorization recommendations, tool adapters, and tenant-scoped jobs.
---

# Security Compliance Engine

1. Require organization, immutable snapshot, workspace, profile, correlation, and idempotency bindings.
2. Build the security estate, scope controls and threats, then select only declared adapters whose versions, permissions, network, data handling, coverage, and licenses are known.
3. Keep scanners isolated from the control plane. Require explicit authorization for active tests and prohibit production mutation, secret dumping, control disabling, evidence deletion, and risk acceptance.
4. Normalize evidence into findings, exposures, risks, control assessments, and an internal authorization recommendation. Never let a scanner or agent issue formal authorization.
5. Return `NOT_RUN`, `PARTIALLY_RUN`, `INCONCLUSIVE`, `TOOL_ERROR`, or `COVERAGE_INSUFFICIENT` when execution or coverage is absent; never fabricate evidence.
6. Bind outputs to commit, artifact digest, deployment, policy, catalog, tool, and evidence hashes.

## Acceptance

Expose `/engine/v1` plus `/engine/v1/authorize`, preserve tenant isolation and idempotency, fail closed when adapters or approval are missing, redact secrets, and emit exact reason codes and reassessment triggers.

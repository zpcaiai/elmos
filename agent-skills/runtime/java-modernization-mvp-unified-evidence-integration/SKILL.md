---
name: java-modernization-mvp-unified-evidence-integration
description: "将身份、GitHub、Runner、Sandbox、Snapshot、Build、OpenRewrite、验证、PR和Evidence统一映射到ELMOS领域模型。"
---

# Unified Evidence

## Evidence类型

AUTHENTICATED_TENANT
RESOURCE_AUTHORIZATION
GITHUB_INSTALLATION
REPOSITORY_AUTHORIZATION
RUNNER_IDENTITY
RUNNER_LEASE
SANDBOX_POLICY
SNAPSHOT_MANIFEST
BASELINE_BUILD
JAVA_HEALTH_REPORT
MIGRATION_PLAN
PLAN_APPROVAL
RECIPE_EXECUTION
RECIPE_IDEMPOTENCY
COMPILE_RESULT
TEST_RESULT
API_COMPATIBILITY
DELIVERY_APPROVAL
PULL_REQUEST
CHECK_RUN
EVIDENCE_PACK

## Risk映射

TENANT_CONTEXT_FORGED
→ TENANT_ISOLATION_CRITICAL_RISK

RUNTIME_BYPASSES_RLS
→ DATA_ISOLATION_CRITICAL_RISK

SHARED_RUNNER_CREDENTIAL
→ RUNNER_IDENTITY_RISK

UNSANDBOXED_BUILD
→ SOURCE_EXECUTION_CRITICAL_RISK

SNAPSHOT_NOT_IMMUTABLE
→ REPRODUCIBILITY_RISK

BASELINE_UNCLASSIFIED
→ MIGRATION_ATTRIBUTION_RISK

RECIPE_NON_IDEMPOTENT
→ TRANSFORMATION_RELIABILITY_RISK

TEST_DISCOVERY_REGRESSION
→ QUALITY_EVIDENCE_RISK

PR_UNKNOWN_RESULT
→ DELIVERY_INTEGRITY_RISK

EVIDENCE_TAMPERED
→ AUDIT_INTEGRITY_CRITICAL_RISK

## Checks

ELMOS / Authentication
ELMOS / Tenant Isolation
ELMOS / GitHub Authorization
ELMOS / Runner Identity
ELMOS / Sandbox
ELMOS / Snapshot
ELMOS / Baseline
ELMOS / Health Check
ELMOS / Migration Plan
ELMOS / OpenRewrite
ELMOS / Idempotency
ELMOS / Compile
ELMOS / Tests
ELMOS / API Compatibility
ELMOS / Pull Request
ELMOS / Evidence

## Composite Change Set

Secure Java Modernization Change Set
├── Identity and Tenant
├── GitHub Authorization
├── Runner Identity
├── Sandbox Policy
├── Snapshot
├── Baseline Build
├── Migration Plan
├── OpenRewrite Patch
├── Verification
├── Pull Request
└── Evidence Pack

## 验收标准

- 每个阶段都产生统一Evidence；
- Check可追溯到原始Artifact；
- Tenant和Project贯穿所有记录；
- Risk和Finding统一；
- PR与Evidence Pack双向关联；
- Audit可以重建完整Timeline；
- Source Local Only模式仍能完成验收；
- Pack可供客户离线审计。

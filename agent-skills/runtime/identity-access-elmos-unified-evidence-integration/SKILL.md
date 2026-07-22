---
name: identity-access-elmos-unified-evidence-integration
description: "将身份、Membership、授权、工作负载身份、访问复核和隔离结果映射到ELMOS统一Evidence。"
---

# Evidence类型

IDENTITY_PROVIDER
AUTHENTICATION
TENANT_MEMBERSHIP
ROLE_ASSIGNMENT
RESOURCE_GRANT
AUTHORIZATION_DECISION
WORKLOAD_IDENTITY
SERVICE_CERTIFICATE
API_CREDENTIAL
PRIVILEGED_ACCESS
BREAK_GLASS
ACCESS_REVIEW
RLS_VALIDATION
TENANT_ISOLATION
IDENTITY_INCIDENT

## Risk映射

UNTRUSTED_IDENTITY_PROVIDER
→ AUTHENTICATION_RISK

TENANT_HEADER_TRUSTED
→ TENANT_ISOLATION_CRITICAL_RISK

RUNTIME_BYPASSES_RLS
→ DATA_ISOLATION_CRITICAL_RISK

ORPHAN_PRIVILEGED_GRANT
→ ACCESS_GOVERNANCE_RISK

SHARED_WORKLOAD_CREDENTIAL
→ MACHINE_IDENTITY_RISK

EXPIRED_BREAK_GLASS
→ PRIVILEGED_ACCESS_RISK

SCIM_DEPROVISION_DELAY
→ OFFBOARDING_RISK

## Checks

ELMOS / Authentication
ELMOS / Tenant Membership
ELMOS / Resource Authorization
ELMOS / SoD
ELMOS / Workload Identity
ELMOS / Privileged Access
ELMOS / Access Review
ELMOS / PostgreSQL RLS
ELMOS / Artifact Isolation
ELMOS / Identity Audit

## 验收标准

- 每个Migration Project关联认证主体；
- 每个Runner Task关联工作负载身份；
- 每项Approval关联Authentication Strength；
- 每项Artifact访问关联Authorization Decision；
- RLS测试结果进入Evidence Pack；
- Privileged Override可追溯；
- 风险进入统一Risk Register；
- Identity Evidence支持离线审计。

---
name: engineering-governance-policy-exception-and-tenant-guardrails
description: 将企业交付、安全、成本、数据和合规要求转为平台Guardrail及有期限例外。
---

# Platform Governance

## Policy层

ORGANIZATION
BUSINESS_UNIT
PRODUCT
ENVIRONMENT
GOLDEN_PATH
RESOURCE
DEPLOYMENT

## Guardrail类型

REPOSITORY
BRANCH
PIPELINE
ARTIFACT
SECURITY
LICENSE
ENVIRONMENT
REGION
COST
DATA
DEPLOYMENT
OBSERVABILITY
OWNERSHIP

## 决策

ALLOW
DENY
REQUIRE_FIX
REQUIRE_APPROVAL
REQUIRE_EXCEPTION
WARN
AUDIT_ONLY

## Shift Left / Right

设计期：

- Template；
- IDE；
- PR；
- Plan。

运行期：

- Admission；
- Deployment；
- Drift；
- Runtime；
- Audit。

## Exception

Scope
Reason
Owner
Compensating Control
Start
Expiry
Review
Evidence
Removal Plan

## Tenant Guardrail

- Repository；
- Runner；
- Artifact；
- Environment；
- State；
- Secret；
- Cost；
- Metrics；
- Portal。

## Policy版本

所有Decision绑定：

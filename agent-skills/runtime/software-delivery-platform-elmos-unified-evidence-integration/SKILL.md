---
name: software-delivery-platform-elmos-unified-evidence-integration
description: 将SCM、Pipeline、Artifact、环境、IDP、Golden Path、DevEx和DORA映射到ELMOS统一Evidence与Portfolio。
---

# Unified Integration

## Extension

{
  "scope": "SOFTWARE_DELIVERY_PLATFORM",
  "engine": "ELMOS_SOFTWARE_DELIVERY_PLATFORM",
  "engineExtension": {
    "schema": "elmos.software-delivery-platform-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

SCM_ESTATE
REPOSITORY_MIGRATION
DELIVERY_VALUE_STREAM
PIPELINE_IR
PIPELINE_COMPONENT
ARTIFACT_REGISTRY
ARTIFACT_PROMOTION
ENVIRONMENT_LIFECYCLE
GITOPS_RESULT
SOFTWARE_CATALOG
GOLDEN_PATH
SELF_SERVICE_RESULT
DEVELOPER_EXPERIENCE
DORA_METRICS
PLATFORM_SCORECARD
PLATFORM_ADOPTION
PLATFORM_ROADMAP

## Risk映射

UNKNOWN_REPOSITORY_OWNER
→ OWNERSHIP_RISK

UNPINNED_PIPELINE_COMPONENT
→ SUPPLY_CHAIN_RISK

REBUILD_PER_ENVIRONMENT
→ ARTIFACT_INTEGRITY_RISK

ENVIRONMENT_DRIFT
→ DEPLOYMENT_REPRODUCIBILITY_RISK

PLATFORM_SLO_FAILURE
→ PLATFORM_RELIABILITY_RISK

DORA_COVERAGE_LOW
→ DELIVERY_MEASUREMENT_RISK

GOLDEN_PATH_EXCEPTION_EXPIRED
→ PLATFORM_GOVERNANCE_RISK

## Checks

ELMOS / SCM Governance
ELMOS / Pipeline Standard
ELMOS / Artifact Integrity
ELMOS / Environment Readiness
ELMOS / GitOps Conformance
ELMOS / Catalog Ownership
ELMOS / Golden Path
ELMOS / Platform SLO
ELMOS / Delivery Metrics
ELMOS / Platform Adoption

## Composite Change Set

Platform Engineering Change Set
├── Repository
├── Reusable Workflow
├── Pipeline Component
├── Artifact Registry
├── Environment Template
├── IaC / GitOps
├── Golden Path
├── Portal
├── Policy
└── Adoption Plan

## Audit

必须审计：

- Repository Migration；
- History Rewrite；
- Branch Protection；
- Pipeline Component变化；
- Artifact删除；
- Production Promotion；
- Environment创建；
- Self-service Access；
- Policy Override；
- Golden Path例外；
- Metric定义变化；
- Platform Deprecation。

## 验收标准

- Delivery Evidence关联所有ELMOS引擎；
- Artifact关联Commit和Deployment；
- Platform Gate高于Pipeline Success；
- DevEx与DORA同时进入Scorecard；
- Audit和Billing统一；
- Evidence Pack可离线验收。

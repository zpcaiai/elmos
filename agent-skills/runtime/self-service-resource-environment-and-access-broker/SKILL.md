---
name: self-service-resource-environment-and-access-broker
description: 提供受Policy、Quota和Approval约束的Repository、环境、数据库、Topic、Secret、访问和平台资源自助申请。
---

# Self-service Broker

## Offering

REPOSITORY
PIPELINE
ENVIRONMENT
DATABASE
CACHE
QUEUE
TOPIC
OBJECT_STORAGE
SECRET_REFERENCE
CERTIFICATE
API_ROUTE
DNS
RUNNER
OBSERVABILITY
ACCESS
COST_BUDGET

## Request

{
  "offering": "postgres-database",
  "organization": "tenant-a",
  "environment": "test",
  "sizeProfile": "small",
  "retention": "30d"
}

## 执行流程

Request
→ Validate
→ Policy
→ Quota
→ Cost Estimate
→ Approval if Required
→ Provision
→ Verify
→ Deliver Reference
→ Observe
→ Expire / Decommission

## Bounded Autonomy

低风险：

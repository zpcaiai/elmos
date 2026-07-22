---
name: environment-topology-preview-sandbox-and-lifecycle-manager
description: 管理开发、Preview、集成、性能、生产和DR环境的模板、Lease、数据、配置、成本、Drift与销毁。
---

# Environment Management

## Environment类型

LOCAL
DEVELOPER_SANDBOX
PREVIEW
INTEGRATION
SHARED_TEST
UAT
PERFORMANCE
PREPRODUCTION
PRODUCTION
DR
TRAINING
DEMO

## Environment Contract

Runtime
Network
Identity
Secret
Data
Dependencies
Observability
Cost
TTL
Owner
Region
Security Profile

## Environment状态

REQUESTED
PROVISIONING
READY
IN_USE
DEGRADED
EXPIRING
EXPIRED
CLEANING
DELETED
CLEANUP_FAILED

## Preview Environment

绑定：

- Pull Request；
- Commit；
- Artifact；
- Requestor；
- TTL；
- Data Profile；
- URL；
- Cost。

## 数据

SYNTHETIC
MASKED
SUBSET
SHARED_TEST
EMPTY
PRODUCTION_APPROVED_READ_ONLY

不得把生产Secret复制到Preview。

## Shared Environment

需要：

- Reservation；
- Tenant隔离；
- Change Coordination；
- Capacity；
- Reset；
- Owner；
- Conflict检测。

## Environment Drift

比较：

Declared Template
Expected Deployment
Actual Resources
Actual Configuration
Actual Artifact

## TTL

环境到期后：

- 通知；
- Grace Period；
- Suspend；
- Snapshot候选；
- Delete；
- Cost停止；
- Audit。

## 验收标准

- Environment有Owner和Lease；
- Preview绑定Commit；
- 数据分类明确；
- Production Secret不复制；
- Drift可发现；
- Cleanup失败产生风险和成本Finding。

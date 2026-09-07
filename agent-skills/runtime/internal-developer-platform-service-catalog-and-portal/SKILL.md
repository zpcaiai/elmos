---
name: internal-developer-platform-service-catalog-and-portal
description: 构建内部开发者平台的服务目录、Owner、文档、API、资源、操作入口和开发者门户。
---

# Internal Developer Platform

## Catalog Entity

DOMAIN
SYSTEM
COMPONENT
SERVICE
WEBSITE
LIBRARY
API
RESOURCE
DATABASE
TOPIC
PIPELINE
ENVIRONMENT
OWNER
TEMPLATE

## Catalog字段

Name
Type
Lifecycle
Owner
System
Domain
Repository
Artifact
API
Dependencies
Environment
SLO
Documentation
Runbook
Support
Cost
Risk

## Catalog Source

SOURCE_DECLARED
PLATFORM_DISCOVERED
RUNTIME_OBSERVED
CMDB_IMPORTED
OWNER_APPROVED

## Ownership

每项生产Entity必须有：

- Accountable Owner；
- Supporting Team；
- On-call；
- Security Contact；
- Data Owner候选。

## Portal能力

- Search；
- Catalog；
- Documentation；
- API；
- Dependency；
- Scorecard；
- Environment；
- Deployment；
- Cost；
- Incident；
- Self-service；
- Support。

## Backstage Provider

可选映射：

ELMOS Service
→ Backstage Component

ELMOS API
→ Backstage API

ELMOS System
→ Backstage System

ELMOS Domain
→ Backstage Domain

ELMOS Golden Path
→ Backstage Template

## Portal限制

Portal不得：

- 成为另一个必须手工维护的数据孤岛；
- 隐藏真实Provider错误；
- 使用共享管理员Credential；
- 绕过审批；
- 把缺失Owner自动填为平台团队。

## Catalog Quality

UNKNOWN_OWNER
STALE_METADATA
BROKEN_REPOSITORY_LINK
NO_DOCUMENTATION
NO_RUNBOOK
NO_SLO
DEPENDENCY_UNKNOWN
LIFECYCLE_UNKNOWN

## 验收标准

- Catalog来自多个Evidence源；
- Source声明与Runtime发现可比较；
- Owner明确；
- Portal只是平台入口；
- 数据自动更新；
- Stale Metadata可检测。

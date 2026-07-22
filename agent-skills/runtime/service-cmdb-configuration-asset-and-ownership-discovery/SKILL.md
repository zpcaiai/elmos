---
name: service-cmdb-configuration-asset-and-ownership-discovery
description: 统一发现业务服务、技术服务、CI、资产、配置基线、Owner和生命周期。
---

# Service and CMDB Discovery

## 来源

Service Catalog
CMDB
Cloud
Kubernetes
SCM
IaC
Deployment
Database
Network
Asset Management
EAM
Vendor Contract
Owner Declaration

## 对象类型

BUSINESS_SERVICE
TECHNICAL_SERVICE
APPLICATION_SERVICE
SERVICE_INSTANCE
APPLICATION
DATABASE
DATASET
QUEUE
TOPIC
API
HOST
VM
CONTAINER
NETWORK
FACILITY
SUPPLIER_SERVICE

## CI身份

Stable ID
Native Provider ID
Environment
Region
Owner
Lifecycle
Configuration Hash

## 生命周期

PLANNED
BUILD
TEST
ACTIVE
MAINTENANCE
DEPRECATED
RETIRED
UNKNOWN

## Reconciliation

多个数据源冲突时：

- Source Priority；
- Attribute Authority；
- Freshness；
- Confidence；
- Manual Review。

## Owner

Business Owner
Technical Owner
Operational Owner
Data Owner
Security Owner
Supplier Owner

## Findings

UNKNOWN_SERVICE_OWNER
ORPHAN_CI
DUPLICATE_CI
STALE_CI
PRODUCTION_CI_NOT_IN_CMDB
CMDB_CI_NOT_OBSERVED
UNAUTHORIZED_CONFIGURATION
UNKNOWN_LIFECYCLE

## 输出

operations-service-estate.json
cmdb-inventory.json
asset-ci-crosswalk.json
service-owner-map.json
configuration-baselines.json
cmdb-quality.json

## 验收标准

- Asset与CI分开；
- Service高于Infrastructure；
- Attribute Authority明确；
- Runtime资产可反查CMDB；
- Owner多角色分层；
- Stale和Orphan可治理。

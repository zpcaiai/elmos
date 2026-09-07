---
name: architecture-exception-waiver-debt-and-remediation-governor
description: 管理架构标准例外、临时Waiver、架构债、补偿控制、到期和整改。
---

# Architecture Exception

## Exception类型

STANDARD_EXCEPTION
VERSION_EXCEPTION
PATTERN_EXCEPTION
SECURITY_RELATED
DATA_RELATED
VENDOR_RELATED
TEMPORARY_COMPATIBILITY
LEGACY_CONTAINMENT

## Exception字段

Standard
Scope
Reason
Business Need
Risk
Owner
Approver
Compensating Control
Start
Expiry
Review
Removal Plan

## Exception状态

DRAFT
REVIEWING
APPROVED
ACTIVE
EXPIRING
EXPIRED
REVOKED
CLOSED

## Architecture Debt

类型：

OBSOLETE_TECHNOLOGY
DUPLICATE_CAPABILITY
POINT_TO_POINT
SHARED_DATABASE
MANUAL_PROCESS
CORE_MODIFICATION
UNOWNED_DATA
UNSUPPORTED_PLATFORM
EXCEPTION_ACCUMULATION

## Debt价值

不是虚构的货币总数。

记录：

- Change Delay；
- Incident；
- Security Exposure；
- Support Cost；
- Upgrade Blocker；
- Opportunity Cost；
- Skills Risk。

## Exception累积

同一标准存在大量例外时，可能表示：

- 标准不现实；
- Golden Path缺失；
- 迁移资源不足；
- 治理失效；
- 特定Domain需要Variant。

## Remediation

REMOVE
MIGRATE
UPGRADE
CONTAIN
REPLACE
STANDARD_VARIANT
ACCEPT_LONG_TERM
REASSESS_STANDARD

## 验收标准

- 例外有期限；
- Risk和业务理由分开；
- Compensating Control可验证；
- Debt有Evidence；
- 批量例外触发标准Review；
- 过期例外形成Hard Finding；
- 关闭需要实现Evidence。

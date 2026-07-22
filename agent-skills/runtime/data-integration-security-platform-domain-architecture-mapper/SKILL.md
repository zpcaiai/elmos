---
name: data-integration-security-platform-domain-architecture-mapper
description: 把数据域、集成契约、安全边界、平台能力和领域架构映射到企业架构Repository。
---

# Cross-domain Architecture Mapping

## Data Architecture

Data Domain
Business Object
Master Data
Data Product
System of Record
Data Consumer
Classification
Retention
Lineage

## Integration Architecture

API
Event
Command
Queue
File
Partner
Workflow
Contract
Owner

## Security Architecture

Identity Domain
Trust Boundary
Security Zone
Control
Data Protection
Risk
Authorization

## Platform Architecture

Platform Product
Capability
Golden Path
Environment
Runtime
Service Level
Consumer

## Domain Architecture

Bounded Context
Domain Service
Business Rule
Capability
Data Ownership
Integration Boundary

## Mapping状态

DECLARED
INFERRED
RUNTIME_OBSERVED
OWNER_VERIFIED
CONFLICTED
UNKNOWN

## 关键问题

- 哪个系统拥有数据？
- 哪个Domain可修改？
- 哪些服务共享数据库？
- 哪些API泄漏内部模型？
- 哪些平台能力重复？
- 哪些安全边界被跨越？

## 输出

enterprise-data-architecture.json
enterprise-integration-architecture.json
enterprise-security-architecture.json
enterprise-platform-architecture.json
domain-architecture-map.json
cross-domain-conflicts.json

## 验收标准

- 数据Ownership明确；
- API和Event有Owner；
- Trust Boundary可视；
- 平台能力与应用需求映射；
- Shared Database显式；
- Domain冲突形成Decision；
- Mapping有Evidence。

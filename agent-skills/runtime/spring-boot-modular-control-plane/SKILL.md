---
name: spring-boot-modular-control-plane
description: "实现Spring Boot模块化控制面、领域边界、REST API、事件和事务。"
---

# Modules

tenant
identity
repository
snapshot
assessment
migration
execution
agent
evidence
report
delivery
policy
audit

## Architecture

Controller
→ Application Service
→ Domain
→ Port
→ Adapter

## Rules

- Domain不依赖Spring Web；
- Domain不依赖GitHub SDK；
- 模块通过Application Event交互；
- 外部副作用使用Outbox；
- 所有写操作包含Tenant Context；
- 幂等Command携带Request ID。

## 验收标准

- ArchUnit验证边界；
- 模块可独立测试；
- 单事务只修改一个Aggregate边界；
- 外部调用不发生在数据库事务内部；
- OpenAPI可自动生成；
- Audit覆盖所有高价值Command。

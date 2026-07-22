---
name: knowledge-graph-projection-and-query
description: "从PostgreSQL权威数据建立Repository、Module、Dependency、Finding和Plan图投影。"
---

# Node

Repository
Snapshot
Module
Dependency
Framework
Finding
Plan
PlanStep
Artifact
Evidence

## Edge

CONTAINS
DEPENDS_ON
USES
HAS_FINDING
ADDRESSED_BY
GENERATED
VERIFIED_BY
DELIVERED_AS

## MVP

PostgreSQL Recursive Query

## Optional

Neo4j Read Projection

## Rules

- 投影可删除并重建；
- 图数据库不接受业务写；
- Projection Offset可追踪；
- Projection Lag可见。

## 验收标准

- PostgreSQL是Source of Truth；
- Projection失败不阻止迁移；
- 相同Event重放幂等；
- 图结果可追到Evidence；
- 图查询有Tenant过滤；
- 性能Benchmark决定是否引入Neo4j。

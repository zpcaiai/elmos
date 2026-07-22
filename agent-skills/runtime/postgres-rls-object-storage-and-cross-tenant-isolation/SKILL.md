---
name: postgres-rls-object-storage-and-cross-tenant-isolation
description: "对数据库、对象存储、缓存、搜索和图投影执行一致的租户隔离策略。"
---

# Data Planes

PostgreSQL
Object Storage
Redis／Cache
Search Index
Graph Projection
Temporal Namespace候选
Metrics／Logs

## PostgreSQL

Runtime Role：

NOSUPERUSER
NOBYPASSRLS
Not Table Owner

所有Tenant表：

ENABLE RLS
FORCE RLS
USING + WITH CHECK

## Object Storage

路径：

tenant/{tenantId}/...

下载必须同时验证：

Tenant Context
Artifact Authorization
Purpose
Expiry

不能只依赖猜不出的Object Key。

## Cache

Cache Key必须包含：

Tenant
Authorization Context候选
Resource
Version

禁止跨Tenant共享含私有结果的语义Cache。

## Search

Tenant过滤必须在查询执行层强制加入，不依赖前端筛选。

## Graph

每个Node和Edge携带Tenant；
投影查询必须设置Tenant；
跨Tenant图分析需要独立批准和脱敏。

## 验收标准

- 真实数据库连接验证RLS；
- Object Key猜测无法下载；
- Cache不发生跨Tenant污染；
- Search查询不能省略Tenant；
- 图查询不能返回其他Tenant节点；
- 管理任务使用单独受控身份；
- 隔离测试进入每次Release Gate。

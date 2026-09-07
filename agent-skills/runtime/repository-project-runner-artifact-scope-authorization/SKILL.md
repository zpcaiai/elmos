---
name: repository-project-runner-artifact-scope-authorization
description: "对ELMOS核心资源实施细粒度所有权、关系和范围授权。"
---

# Resource Types

GitHub Installation
Repository
Migration Project
Snapshot
Runner
Runner Pool
Sandbox
Artifact
Pull Request
Evidence Pack
Policy
Billing Record

## Scope

Tenant
Organization
Project
Repository
Runner Pool
Artifact Class
Environment

## 关系授权

OWNER
MEMBER
REVIEWER
APPROVER
OPERATOR
AUDITOR
SUPPORT

## 示例

- Repository成员不自动成为所有Migration Project审批者；
- Runner管理员不能下载源码Artifact；
- Billing管理员不能查看源码Patch；
- Auditor可以读取Evidence但不能执行任务；
- Support Engineer必须有有效Support Case；
- 项目Reviewer只能批准其Scope中的Plan。

## Signed Download URL

绑定：

Subject
Tenant
Artifact
Purpose
Expiry
Maximum Uses候选

## 验收标准

- UUID猜测不能访问其他资源；
- Artifact下载检查Tenant和资源Scope；
- Repository撤权传播到新Project创建；
- 支持权限不能成为永久跨Tenant访问；
- 资源Owner未知时高风险操作阻止；
- Signed URL短期有效；
- 所有授权Decision可追踪。

---
name: abac-policy-context-and-resource-authorization
description: "根据主体、资源、动作、环境、风险和时间执行属性授权。"
---

# Authorization Input

Subject
Tenant
Membership
Role
Resource
Action
Environment
Data Classification
Repository Classification
Authentication Strength
Device Context
Time
Risk
Approval

## 属性类型

Subject Attribute
Resource Attribute
Environment Attribute
Action Attribute
Relationship Attribute

## Decision

ALLOW
DENY
ALLOW_WITH_CONDITIONS
REQUIRE_STEP_UP
REQUIRE_APPROVAL
READ_ONLY
MASK_FIELDS

## 条件示例

- 核心Repository只能在Private Runner执行；
- 受限源码不得使用外部Agent；
- Evidence导出需要Auditor角色；
- 高风险Plan批准要求Step-up MFA；
- Support Engineer只能在工单有效期内访问；
- Runner只能领取相同Tenant任务。

## Policy版本

Decision必须记录：

Policy Bundle
Input Hash
Decision
Conditions
Reason
Time

## 验收标准

- 相同输入可产生可重放Decision；
- Deny原因可解释；
- 环境和风险可以影响授权；
- Policy更新不修改历史Decision；
- 缺少关键属性默认拒绝；
- 高风险Policy服务失败时Fail Closed；
- ABAC与RBAC结果可组合。

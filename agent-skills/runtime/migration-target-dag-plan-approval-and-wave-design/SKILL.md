---
name: migration-target-dag-plan-approval-and-wave-design
description: "选择Java和Spring目标，生成迁移DAG、PR Wave、估算、风险和绑定Hash的人工批准。"
---

# Migration Plan

## Target Profile

Source Java
Target Java
Source Spring Boot
Intermediate Spring Boot候选
Target Spring Boot
Build Tool
Packaging
Deployment Type
Compatibility Constraints

## DAG Step

BUILD_FOUNDATION
JDK_UPGRADE
SPRING_BOOT_INTERMEDIATE
JAKARTA
SPRING_SECURITY
HIBERNATE
TESTING
SPRING_BOOT_TARGET
CLEANUP

## Automation Class

DETERMINISTIC
RULE_BASED
MANUAL_CONFIGURATION
HUMAN_REQUIRED
BLOCKED

## Step字段

Input Snapshot
Preconditions
Recipe
Expected Change
Verification
Risk
Rollback
Dependencies
Estimated Effort
Evidence Requirements

## PR Wave

BUILD_AND_JDK
BOOT_AND_JAKARTA
SECURITY_AND_PERSISTENCE
TESTS
FINAL_TARGET
CLEANUP

## Estimate

Optimistic
Expected
Conservative
Confidence
Assumptions

禁止输出单点虚假精确人天。

## Approval

Approval绑定：

Plan Version
Plan Hash
Target Profile
Recipe Catalog Version
Policy Version
Expiry

## 验收标准

- DAG无环；
- Hard Compatibility优先；
- 目标和中间状态分开；
- 每个Wave具有验证条件；
- Blocker显式；
- Estimate显示范围和假设；
- Plan变更使旧Approval失效；
- 未批准Plan不能执行Rewrite。

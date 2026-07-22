---
name: java-target-profile-migration-dag-and-wave-planner
description: "选择目标JDK和Spring版本，生成迁移步骤、依赖、风险和PR波次。"
---

# Target Profile

Source JDK
Target JDK
Source Boot
Intermediate Boot
Target Boot
Build Tool
Application Type
Deployment Type

## DAG Step

BUILD_FOUNDATION
JDK_UPGRADE
BOOT3_INTERMEDIATE
JAKARTA
SECURITY
HIBERNATE
TESTING
BOOT4
CLEANUP

## Automation

DETERMINISTIC
RULE_BASED
AGENT_ASSISTED
HUMAN_REQUIRED
BLOCKED

## Estimate

输出范围：

Optimistic
Expected
Conservative
Confidence
Assumptions

## 验收标准

- Hard Compatibility先验证；
- 最终Target不使用过期中间版本；
- DAG无环；
- PR Wave可独立编译候选；
- Estimate显示范围；
- Blocker进入人工清单。

---
name: team-topology-cognitive-load-and-interaction-modernizer
description: "分析团队拓扑、认知负荷、依赖、交互模式和价值流，并生成组织设计候选。"
---

# Team Topology

## Topology Provider

TEAM_TOPOLOGIES
ENTERPRISE_CUSTOM
HYBRID

## Team Type

STREAM_ALIGNED
PLATFORM
ENABLING
COMPLICATED_SUBSYSTEM
CUSTOM

## Interaction Mode

COLLABORATION
X_AS_A_SERVICE
FACILITATION
GOVERNANCE
DEPENDENCY
UNKNOWN

## Interaction Contract

Source Team
Target Team
Mode
Purpose
Duration
Interface
Expected Outcome
Service Level
Exit Condition

## Cognitive Load

INTRINSIC
DOMAIN
TECHNOLOGY
PROCESS
TOOLING
COORDINATION
OPERATIONS
GOVERNANCE

## Evidence

- Service Count；
- Technology Count；
- Dependency Count；
- On-call；
- Ticket；
- Wait；
- Context Switching；
- Survey；
- Team Interview；
- Delivery Flow。

## Cognitive状态

HEALTHY
ELEVATED
OVERLOADED
UNSUSTAINABLE
UNKNOWN

## Anti-pattern

PLATFORM_AS_TICKET_QUEUE
ENABLING_TEAM_PERMANENT_DEPENDENCY
COLLABORATION_WITHOUT_END
STREAM_TEAM_WITHOUT_STREAM
COMPLICATED_SUBSYSTEM_BLACK_BOX
TEAM_OWNS_TOO_MANY_SERVICES
TEAM_BOUNDARY_MIRRORS_LEGACY_ARCHITECTURE

## 设计动作

SPLIT
MERGE
REALIGN
PLATFORMIZE
SIMPLIFY
STANDARDIZE
CREATE_ENABLING_TEAM
CREATE_SUBSYSTEM_TEAM
CHANGE_INTERACTION
REDUCE_WORK
REARCHITECT_SYSTEM

## 验收标准

- Team Type只是设计工具；
- Interaction有期限和目的；
- Cognitive Load有多源Evidence；
- 过载不能只靠培训处理；
- Platform采用产品模式；
- Enabling Team有退出；
- 组织变化关联架构变化。

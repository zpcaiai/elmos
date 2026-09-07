---
name: agent-mesh-registry-discovery-routing-and-interoperability
description: "管理企业Agent注册、能力、A2A互操作、MCP工具访问、路由、兼容和生命周期。"
---

# Agent Mesh

## Agent类型

PLANNER
ANALYST
MIGRATION
TEST
SECURITY
DATA
OPERATIONS
FINANCE
ORGANIZATION
POLICY_ASSISTANT
DOMAIN_SPECIALIST
EXECUTION_AGENT

## Agent Card

Agent ID
Version
Owner
Purpose
Capabilities
Input
Output
Protocols
Models
Tools
Data Scope
Risk Tier
SLO
Cost
Evaluation
Lifecycle

## Agent通信

A2A：
独立Agent之间。

MCP：
Agent与Tool／Data之间。

Provider-native：
同一Agent Runtime内的Sub-agent或Handoff。

## Agent状态

DRAFT
EVALUATING
APPROVED
ACTIVE
DEGRADED
QUARANTINED
DEPRECATED
RETIRED

## Routing

考虑：

Capability
Risk
Data
Region
Cost
Latency
Quality
Availability
Protocol
Model
Owner
Capacity

## Capability Confidence

DECLARED
TCK_VERIFIED
EVALUATION_VERIFIED
PRODUCTION_OBSERVED
OWNER_APPROVED

## Agent不可见性

未注册、未评测或Owner未知Agent：

```text
不得进入生产Agent Mesh

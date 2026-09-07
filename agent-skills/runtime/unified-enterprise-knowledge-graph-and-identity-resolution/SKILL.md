---
name: unified-enterprise-knowledge-graph-and-identity-resolution
description: "建立企业实体、别名、关系、Claim和跨引擎身份归一图。"
---

# Enterprise Knowledge Graph

## Entity类型

STRATEGY
CAPABILITY
PRODUCT
APPLICATION
SERVICE
DATA
API
EVENT
TECHNOLOGY
INFRASTRUCTURE
DEVICE
TEAM
PERSON_ROLE
VENDOR
CONTRACT
INITIATIVE
AGENT
POLICY

## Identity

Global Entity ID
Domain-native ID
Provider ID
Environment
Tenant
Version
Alias

## Resolution Evidence

Exact Native ID
Approved Crosswalk
Repository Relation
Runtime Relation
Owner Confirmation
Semantic Similarity
Name Similarity

## Resolution状态

MATCHED
PROBABLE_MATCH
POSSIBLE_MATCH
CONFLICT
NOT_MATCHED
REJECTED
HUMAN_REVIEW

## 重要规则

相似度只能生成候选，不能自动执行不可逆合并。

## Merge

合并后保留：

Original Entities
Aliases
Sources
Decision
Reviewer
Time
Reversal Path

## Relationship

每条关系必须带：

Claim
Direction
Source
Valid Time
Confidence
Authority
Evidence

## Graph访问

按：

Tenant
Domain
Data Classification
Purpose
Role
Region

限制。

## 验收标准

- Global ID稳定；
- Native ID保留；
- Entity Merge可逆；
- Relationship有Evidence；
- 跨租户图隔离；
- 冲突不静默覆盖；
- Graph Snapshot可复现。

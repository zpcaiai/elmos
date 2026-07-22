---
name: ai-release-promotion-shadow-rollback-and-decommission
description: 管理AI Release Bundle、Shadow、Champion／Challenger、Canary、回滚、Provider切换和模型退役。
---

# AI Release

## Release Bundle

Model Version
Prompt Version
Feature Service
Retriever
Embedding
Index
Reranker
Tool Set
Memory Policy
Guardrail
Evaluation Profile
Runtime
Configuration

## Artifact Identity

Bundle必须拥有：

Bundle ID
Version
Manifest
Component Digests
Policy Version
Evaluation Hash
Approval

## Promotion

EXPERIMENT
CANDIDATE
VALIDATED
SHADOW
CANARY
PRODUCTION
FALLBACK
DEPRECATED
RETIRED

## Shadow

同一请求发送：

Production Bundle
Candidate Bundle

Candidate不得执行真实Side Effect。

## Champion / Challenger

比较：

Quality
Latency
Cost
Safety
Business Outcome
Slice
Confidence

## Canary

按：

Tenant
User
Region
Use Case
Traffic
Risk
Internal User

## Rollback

MODEL_ALIAS
PROMPT
RETRIEVER
INDEX
RERANKER
TOOL
GUARDRAIL
FULL_BUNDLE
PROVIDER
FORWARD_FIX

## Point of No Return

可能包括：

- Agent已执行不可逆操作；
- 新模型写入新业务状态；
- 新Feature成为Authority；
- 旧Index已删除；
- 第三方模型已退役；
- 数据已用于不可撤回训练。

## Decommission

确认：

- Endpoint流量为0；
- Alias不再引用；
- Agent不再使用；
- Feature Consumer为0；
- Index Consumer为0；
- Model Card和Evidence归档；
- 数据与Artifact按Retention处理；
- Provider Credential撤销；
- Cost停止；
- Incident和Legal Hold检查。

## 验收标准

- Bundle高于单个Model；
- Shadow Side Effect受控；
- Canary按风险；
- Rollback可以组件级；
- Agent副作用进入恢复计划；
- 退役依据Usage Evidence。

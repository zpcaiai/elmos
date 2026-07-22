---
name: llm-gateway-provider-routing-policy-quota-and-cache
description: 统一管理外部与内部LLM访问、Provider路由、模型目录、Credential、配额、Fallback、缓存和审计。
---

# LLM Gateway

## Provider类型

EXTERNAL_API
PRIVATE_ENDPOINT
SELF_HOSTED
REGIONAL_PROVIDER
OFFLINE_MODEL
CUSTOM

## Gateway职责

Authentication
Authorization
Provider Credential
Model Alias
Routing
Quota
Rate Limit
Budget
Retry
Fallback
Request Normalization
Response Normalization
Audit
Metrics

## Model Alias

例如：

enterprise-fast
enterprise-reasoning
private-code
private-medical
embedding-default

应用不应直接硬编码具体Provider Model ID。

## Routing Policy

按：

Use Case
Risk
Data Classification
Region
Latency
Quality
Cost
Context Length
Modality
Availability
Tenant
Provider Health

## Policy Decision

ALLOW
DENY
ROUTE
REDACT_AND_ROUTE
REQUIRE_PRIVATE_MODEL
REQUIRE_APPROVAL
FALLBACK
HUMAN_ESCALATE

## Credential

应用获得Gateway Identity。

Provider API Key只存在于Gateway Secret Broker。

## Quota

Token
Request
Concurrent
Cost
Daily
Monthly
Tenant
User
Application
Model

## Cache

EXACT
SEMANTIC
PREFIX
EMBEDDING
NO_CACHE

缓存Key必须包含：

Model
Prompt／Input Hash
System Instruction
Temperature候选
Tool Schema
Knowledge Version
Safety Policy

## Privacy

默认禁止缓存：

- Secret；
- Restricted Data；
- Personal Sensitive Data；
- Tool Result；
- Non-deterministic Agent Action。

## 验收标准

- 应用不持有Provider Secret；
- Model Alias稳定；
- Routing Policy版本化；
- Quota多维；
- Fallback可测试；
- Cache不会跨租户；
- Gateway不能隐藏真实模型版本。

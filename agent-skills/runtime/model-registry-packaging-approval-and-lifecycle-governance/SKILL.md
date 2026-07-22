---
name: model-registry-packaging-approval-and-lifecycle-governance
description: 统一管理模型身份、版本、Artifact、签名、血缘、评测、审批、Alias和退役。
---

# Model Registry

## Model类型

PREDICTIVE
EMBEDDING
RERANKER
FOUNDATION
FINE_TUNED_LLM
MULTIMODAL
ENSEMBLE
ROUTER
SAFETY_MODEL

## Model Version

绑定：

Training Run
Dataset
Feature
Code
Environment
Artifact
Signature
Evaluation
Risk
Owner

## Artifact Bundle

Weights
Config
Tokenizer
Preprocessor
Postprocessor
Runtime
Dependency
License
SBOM
Signature

## 生命周期

DRAFT
CANDIDATE
EVALUATING
REVIEWING
APPROVED
SHADOW
CANARY
PRODUCTION
SUSPENDED
DEPRECATED
RETIRED

## Alias

例如：

champion
challenger
production
fallback
embedding-current

Alias可变化，但Deployment必须记录实际Version和Digest。

## Approval

DATA_APPROVED
QUALITY_APPROVED
SECURITY_APPROVED
RESPONSIBLE_AI_APPROVED
BUSINESS_APPROVED
PRODUCTION_APPROVED

## Model Card

至少包含：

- Intended Use；
- Out-of-scope Use；
- Data；
- Metrics；
- Limits；
- Risks；
- Monitoring；
- Owner；
- Update。

## Third-party Model

记录：

Provider
Model ID
Version／Snapshot
License
Terms Reference
Region
Data Handling
Update Policy
Deprecation
Fallback

## 验收标准

- Model有稳定Identity；
- Artifact Bundle完整；
- Alias和Version分开；
- 多类Approval独立；
- Third-party Model可追踪；
- 未评测Model不能进入生产Alias；
- Retired Model保留必要Evidence。

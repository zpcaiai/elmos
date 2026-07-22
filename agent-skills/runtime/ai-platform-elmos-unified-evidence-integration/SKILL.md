---
name: ai-platform-elmos-unified-evidence-integration
description: 将AI Use Case、Dataset、Feature、Model、Prompt、RAG、Agent、评测、风险、成本和Release映射到ELMOS统一Evidence。
---

# Unified AI Integration

## Extension

{
  "scope": "AI_PLATFORM",
  "engine": "ELMOS_AI_PLATFORM",
  "engineExtension": {
    "schema": "elmos.ai-platform-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

AI_ESTATE
AI_USE_CASE
AI_DATASET
AI_DATA_LINEAGE
FEATURE_DEFINITION
FEATURE_PARITY
EXPERIMENT_RUN
TRAINING_PIPELINE
TRAINING_RUN
MODEL_REGISTRY
MODEL_CARD
PROMPT_VERSION
INFERENCE_RESULT
LLM_GATEWAY_RESULT
RAG_RESULT
AGENT_RESULT
AI_EVALUATION
GUARDRAIL_RESULT
RESPONSIBLE_AI_ASSESSMENT
AI_OBSERVABILITY
AI_DRIFT
AI_COST
AI_RELEASE
AI_DECOMMISSION

## Risk映射

DATASET_UNTRACEABLE
→ AI_DATA_GOVERNANCE_RISK

FEATURE_SKEW
→ MODEL_BEHAVIOR_RISK

MODEL_UNEVALUATED
→ AI_QUALITY_RISK

RAG_PERMISSION_LEAK
→ DATA_SECURITY_CRITICAL_RISK

AGENT_EXCESSIVE_PERMISSION
→ EXCESSIVE_AGENCY_RISK

JUDGE_UNCALIBRATED
→ EVALUATION_RELIABILITY_RISK

AI_BUDGET_EXCEEDED
→ AI_FINANCIAL_OPERATION_RISK

## Checks

ELMOS / AI Use Case
ELMOS / Dataset
ELMOS / Feature Parity
ELMOS / Training Reproducibility
ELMOS / Model Registry
ELMOS / Model Quality
ELMOS / RAG
ELMOS / Agent
ELMOS / Guardrail
ELMOS / Responsible AI
ELMOS / AI Cost
ELMOS / AI Release

## Composite Change Set

AI Platform Change Set
├── Dataset
├── Feature
├── Training Pipeline
├── Model
├── Prompt
├── RAG Index
├── Agent
├── Guardrail
├── Inference Platform
├── Evaluation
└── Release Plan

## Audit

必须审计：

- Dataset访问；
- Label变化；
- Feature变化；
- Training Run；
- Model注册；
- Prompt变化；
- Provider变化；
- Agent Tool权限；
- Human Approval；
- Guardrail Override；
- Responsible AI接受；
- Model Promotion；
- Production Rollback；
- Model退役。

## 验收标准

- AI Evidence关联数据、应用、安全和基础设施；
- AI Release Bundle完整；
- Quality、Safety、Responsible AI和Cost分别进入Gate；
- Model、Prompt、Index和Agent可以统一追踪；
- Audit和Billing统一；
- Evidence Pack可离线验收。

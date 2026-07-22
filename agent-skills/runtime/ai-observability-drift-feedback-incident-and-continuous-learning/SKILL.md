---
name: ai-observability-drift-feedback-incident-and-continuous-learning
description: 统一追踪AI请求、模型、Prompt、RAG、Agent、质量、漂移、反馈和Incident，并驱动持续改进。
---

# AI Observability

## Trace

记录：

Request
Session
Model
Prompt
Retriever
Documents
Reranker
Tool
Agent Step
Guardrail
Output
Feedback
Cost

## OpenTelemetry

OpenTelemetry当前通用语义规范已到1.43.0系列，GenAI语义已迁往独立GenAI Semantic Conventions仓库；因此ELMOS必须将使用的GenAI语义版本和稳定性写入Observability Profile。

## Trace安全

默认不记录完整：

- Prompt；
- Response；
- Document；
- Tool Output；
- Personal Data；
- Secret。

使用：

Hash
Redaction
Sampling
Reference
Encrypted Restricted Store

## Drift

DATA_DRIFT
FEATURE_DRIFT
PREDICTION_DRIFT
LABEL_DRIFT
CONCEPT_DRIFT
EMBEDDING_DRIFT
RETRIEVAL_DRIFT
PROMPT_DRIFT
TOOL_DRIFT
MODEL_PROVIDER_DRIFT
JUDGE_DRIFT

## Quality

Online Metric
Delayed Ground Truth
Human Feedback
User Action
Escalation
Business Outcome

## Feedback

THUMBS
RATING
CORRECTION
ANNOTATION
COMPLAINT
BUSINESS_RESULT
EXPERT_REVIEW

## Incident

QUALITY
SAFETY
SECURITY
PRIVACY
BIAS
COST
AVAILABILITY
TOOL_ACTION
DATA
PROVIDER

## Trigger

Retrain
Re-evaluate
Re-index
Change Prompt
Change Model
Disable Tool
Increase Human Review
Rollback
Suspend

## Production Trace Evaluation

MLflow等Provider可以保存LLM与Agent执行Trace，并从生产Trace中构建评测Dataset和执行Scorer；ELMOS应保留统一Trace Contract，防止锁定某个框架。

## 验收标准

- AI Trace覆盖中间步骤；
- 敏感内容默认不明文记录；
- Drift类型分开；
- Feedback关联Version；
- Incident可暂停AI Release；
- 生产问题进入Evaluation Dataset；
- Continuous Learning有审批。

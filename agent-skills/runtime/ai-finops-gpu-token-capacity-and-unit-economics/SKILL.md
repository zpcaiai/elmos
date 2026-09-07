---
name: ai-finops-gpu-token-capacity-and-unit-economics
description: 管理GPU、训练、推理、Token、Embedding、评测、存储和数据处理成本及单位经济。
---

# AI FinOps

## 成本范围

DATA_PREPARATION
LABELING
FEATURE_COMPUTE
CPU_TRAINING
GPU_TRAINING
HYPERPARAMETER_SEARCH
CHECKPOINT_STORAGE
MODEL_STORAGE
ONLINE_INFERENCE
BATCH_INFERENCE
LLM_INPUT_TOKEN
LLM_OUTPUT_TOKEN
EMBEDDING
RERANKING
VECTOR_STORAGE
RAG_INGESTION
AGENT_TOOL
EVALUATION
HUMAN_REVIEW

## Allocation

Organization
Product
Use Case
Model
Endpoint
Tenant
User
Environment
Experiment
Training Run
Agent
Provider

## Unit Economics

Cost per Prediction
Cost per Document
Cost per Conversation
Cost per Successful Task
Cost per Resolved Case
Cost per Qualified Lead
Cost per Code Change
Cost per 1K Tokens
Cost per Evaluation Case
Cost per Training Run

## Budget

Hard Limit
Soft Limit
Forecast
Alert
Approval
Burst
Emergency

## 优化

Smaller Model
Model Routing
Quantization
Distillation
Batching
Caching
Prompt Reduction
Context Reduction
Reranker
Speculative Decoding
GPU Right-size
Spot Training
Scale to Zero
Evaluation Sampling

## 防止错误优化

不能通过：

- 删除关键评测；
- 降低安全；
- 使用未经批准模型；
- 减少Ground Truth；
- 扩大缓存泄漏；
- 牺牲Critical质量；

来降低成本。

## Quality-Cost Frontier

每个候选Model和Pipeline比较：

Quality
Latency
Availability
Risk
Cost

而不是只选最便宜模型。

## 验收标准

- 训练和推理成本分开；
- Token和Tool成本可见；
- Shared GPU成本可分配；
- Unit Economics与业务结果关联；
- Forecast和Actual分开；
- 优化受质量与风险Guardrail限制。

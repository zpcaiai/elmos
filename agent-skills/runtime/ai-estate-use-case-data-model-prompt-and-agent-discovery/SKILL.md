---
name: ai-estate-use-case-data-model-prompt-and-agent-discovery
description: 清点企业中的AI Use Case、Dataset、Feature、Model、Prompt、RAG、Agent、Endpoint和Owner。
---

# AI Estate Discovery

## AI类型

CLASSICAL_ML
DEEP_LEARNING
FORECASTING
RECOMMENDATION
COMPUTER_VISION
NLP
FOUNDATION_MODEL
LLM_APPLICATION
RAG
AGENT
MULTIMODAL
OPTIMIZATION
RULE_AI_HYBRID

## 发现来源

Repository
Notebook
Experiment Tracker
Object Storage
Model Registry
Feature Store
Vector Database
Prompt Management
API Gateway
Kubernetes
Cloud AI Service
SaaS AI
Desktop Script
Business Application

## AI Use Case

记录：

- Business Objective；
- Decision；
- User；
- Affected Population；
- Human Oversight；
- Criticality；
- Data；
- Model；
- Owner；
- Environment；
- Legal／Policy Reference。

## Asset状态

ACTIVE
EXPERIMENTAL
SHADOW
PRODUCTION
DORMANT
UNOWNED
UNREGISTERED
UNKNOWN

## Shadow AI

识别：

- 员工个人API Key；
- Notebook服务；
- 浏览器插件；
- 未注册Chatbot；
- SaaS AI Integration；
- 直接调用Provider的脚本。

## Findings

UNREGISTERED_MODEL
UNKNOWN_MODEL_OWNER
UNKNOWN_DATASET
PROMPT_IN_SOURCE_UNVERSIONED
SHADOW_LLM_USAGE
UNAPPROVED_AI_USE_CASE
UNTRACKED_VECTOR_INDEX
AGENT_TOOL_UNKNOWN
PRODUCTION_ENDPOINT_NO_REGISTRY

## 输出

ai-estate.json
ai-use-cases.json
ai-model-inventory.json
ai-prompt-inventory.json
rag-inventory.json
agent-inventory.json
ai-endpoint-inventory.json
ai-unknowns.json

## 验收标准

- Use Case与Model分开；
- Prompt和Index进入资产目录；
- Shadow AI可发现；
- Owner和Risk Tier明确；
- 实验与生产分开；
- 未注册生产Endpoint形成风险。

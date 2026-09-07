---
name: ai-evaluation-dataset-benchmark-judge-and-quality-gate
description: 建立传统ML、LLM、RAG和Agent的评测数据集、Scorer、Judge校准、回归测试和质量Gate。
---

# AI Evaluation

## Evaluation Scope

MODEL
PROMPT
RAG
AGENT
TOOL
END_TO_END
SESSION
SAFETY
RESPONSIBLE_AI

## Dataset

GOLDEN
REGRESSION
EDGE
ADVERSARIAL
PRODUCTION_FAILURE
HUMAN_FEEDBACK
SYNTHETIC
SLICE
TEMPORAL

## Scorer类型

DETERMINISTIC
RULE
STATISTICAL
EMBEDDING
MODEL_BASED
LLM_JUDGE
HUMAN
BUSINESS_OUTCOME

## Traditional ML

Accuracy
Precision
Recall
F1
AUROC
Calibration
MAE
RMSE
Ranking
Forecast
Business Value

## LLM

Correctness
Relevance
Completeness
Instruction Following
Groundedness
Citation
Safety
Style
Consistency

## RAG

Retrieval
Reranking
Context
Grounding
Citation
End Answer

## Agent

Task Completion
Tool Selection
Tool Arguments
Trajectory
Unnecessary Steps
Policy Compliance
Side Effect
Recovery
Cost

## Judge Calibration

Judge Version
Judge Prompt
Reference Labels
Human Agreement
Inter-rater Agreement
Bias Slice
Order Test
Length Test
Self-preference Test

## Evaluation Gate

PASS
PASS_WITH_WARNINGS
CONDITIONAL
FAIL
INCONCLUSIVE

## Regression

比较：

Current Bundle
Candidate Bundle

必须保持：

Dataset Version
Scorer Version
Judge Version
Policy Version

## 验收标准

- Dataset和Scorer版本化；
- LLM Judge经过校准；
- RAG分层评测；
- Agent评测中间轨迹；
- Human Review可采样；
- 质量阈值由Owner批准；
- Inconclusive不映射Pass。

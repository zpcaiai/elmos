---
name: responsible-ai-risk-fairness-explainability-and-oversight
description: 将AI Use Case映射到风险、影响、公平性、可解释性、人工监督、透明度和责任控制。
---

# Responsible AI

## Profile

按：

Use Case
Population
Decision Impact
Autonomy
Data Sensitivity
Reversibility
Scale
Regulation／Policy
Human Oversight

生成：

LOW
MODERATE
HIGH
CRITICAL

## Trustworthiness维度

Validity
Reliability
Safety
Security
Resilience
Accountability
Transparency
Explainability
Privacy
Fairness

## AI Impact

评估：

- 谁受影响；
- 如何受影响；
- 错误后果；
- 能否申诉；
- 是否可逆；
- 是否自动决策；
- 是否存在替代渠道；
- 是否监控差异。

## Fairness

Group Definition
Metric
Reference
Threshold
Sample Size
Confidence
Intersection
Temporal Drift

禁止：

- 自动推断敏感属性后无治理使用；
- 只测总体平均；
- 用单一公平指标代表所有Use Case。

## Explainability

类型：

GLOBAL
LOCAL
FEATURE
COUNTERFACTUAL
RULE
TRACE
SOURCE_CITATION
PROCESS_EXPLANATION

不同用户需要不同解释：

- End User；
- Operator；
- Auditor；
- Data Scientist；
- Regulator候选；
- Support。

## Human Oversight

HUMAN_IN_THE_LOOP
HUMAN_ON_THE_LOOP
HUMAN_REVIEW_ON_EXCEPTION
FULLY_AUTOMATED_APPROVED
NO_AUTOMATION_ALLOWED

## Appeal

高影响决策应定义：

- Notification；
- Reason；
- Review；
- Correction；
- Escalation；
- Audit。

## Responsible AI Decision

APPROVED
APPROVED_WITH_CONTROLS
PILOT_ONLY
HUMAN_REVIEW_REQUIRED
REJECTED
REASSESSMENT_REQUIRED

## 验收标准

- Use Case风险先于Model风险；
- Affected Population明确；
- 公平性按Slice；
- Explainability针对用户；
- Human Oversight可执行；
- 申诉和Correction可追踪；
- 高风险不能由Agent自动批准。

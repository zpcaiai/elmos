---
name: software-capitalization-cost-classification-and-evidence
description: "按企业会计Policy收集软件成本活动证据，生成资本化、费用化和人工复核候选。"
---

# Software Cost Classification

## 重要边界

ELMOS不提供：

- 会计意见；
- 法律意见；
- 审计意见；
- 自动总账记账。

ELMOS提供：

- Policy执行；
- Candidate；
- Evidence；
- Reconciliation；
- Audit。

## Policy Profile

Framework
Jurisdiction
Effective Date
Entity
Software Type
Recognition Rules
Exclusions
Materiality
Review
Approver

## Software类型

INTERNAL_USE
EXTERNAL_SALE
CLOUD_SERVICE
PLATFORM
DATA_PRODUCT
AI_MODEL
CONFIGURATION
IMPLEMENTATION
MAINTENANCE
RESEARCH

## Activity

RESEARCH
DISCOVERY
FEASIBILITY
DEVELOPMENT
CONFIGURATION
TESTING
DEPLOYMENT
TRAINING
DATA_CONVERSION
MAINTENANCE
DEFECT_FIX
UPGRADE
SUPPORT
DECOMMISSION

## Candidate状态

CAPITALIZABLE_CANDIDATE
EXPENSE_CANDIDATE
MIXED
INSUFFICIENT_EVIDENCE
ACCOUNTING_REVIEW_REQUIRED
APPROVED_CAPITALIZE
APPROVED_EXPENSE
ADJUSTED

## Evidence

Management Approval
Funding Commitment
Product
Use Case
Work Item
Labor
Vendor Cost
Commit
Artifact
Deployment
Completion
Available for Use
Owner

## Labor

方法候选：

TIME_ENTRY
CAPACITY_ALLOCATION
ROLE_PERCENTAGE
WORK_ITEM_ESTIMATE
STATISTICAL_ALLOCATION
MANUAL_APPROVED

## Mixed Activity

一个Epic或Sprint可同时包含：

- 新开发；
- 维护；
- 缺陷修复；
- 研究。

不得按整个Sprint单一分类。

## Adjustment

Late Invoice
Reclassification
Policy Change
Audit Adjustment
Abandoned Work
Impairment Trigger Candidate

## 验收标准

- Policy版本化；
- 会计Framework明确；
- Research和Development分开；
- Mixed Activity可拆分；
- Ticket标签不直接决定；
- Evidence绑定真实交付；
- 人工财务Review；
- 原始分类不被覆盖。

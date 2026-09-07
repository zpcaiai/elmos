---
name: tbm-investment-elmos-unified-evidence-integration
description: "将技术成本、产品经济、资金、合同、资本化、收益和技术债映射到ELMOS统一Evidence与Portfolio。"
---

# Unified TBM Integration

## Extension

{
  "scope": "TBM_INVESTMENT",
  "engine": "ELMOS_TBM_INVESTMENT",
  "engineExtension": {
    "schema": "elmos.tbm-investment-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

TECHNOLOGY_COST
TECHNOLOGY_USAGE
TBM_TAXONOMY
COST_ALLOCATION
PRODUCT_COST
PRODUCT_TCO
UNIT_ECONOMICS
BUDGET
FORECAST
SHOWBACK
CHARGEBACK
VENDOR_CONTRACT
LICENSE_POSITION
CAPITALIZATION_EVIDENCE
BENEFIT_HYPOTHESIS
BENEFIT_REALIZATION
TECHNICAL_DEBT_ECONOMICS
INVESTMENT_DECISION
FUNDING_REALLOCATION
PRODUCT_EXIT
TBM_SCORECARD

## Risk映射

UNALLOCATED_COST_EXCESSIVE
→ TECHNOLOGY_COST_TRANSPARENCY_RISK

PRODUCT_OWNER_UNKNOWN
→ PRODUCT_ACCOUNTABILITY_RISK

CONTRACT_AUTO_RENEWAL
→ VENDOR_FINANCIAL_RISK

CAPITALIZATION_EVIDENCE_INSUFFICIENT
→ ACCOUNTING_CONTROL_RISK

BENEFIT_DOUBLE_COUNTED
→ INVESTMENT_VALUE_RISK

LEGACY_NOT_RETIRED
→ BENEFIT_REALIZATION_RISK

TECHNICAL_DEBT_LOW_CONFIDENCE
→ PORTFOLIO_DECISION_RISK

## Checks

ELMOS / TBM Reconciliation
ELMOS / Product Ownership
ELMOS / Allocation Quality
ELMOS / Product TCO
ELMOS / Unit Economics
ELMOS / Forecast
ELMOS / Vendor Commitments
ELMOS / Capitalization Evidence
ELMOS / Benefit Realization
ELMOS / Technical Debt
ELMOS / Portfolio Funding
ELMOS / Product Exit

## Composite Change Set

TBM Investment Change Set
├── Product Model
├── Cost Mapping
├── Allocation Rule
├── Funding Envelope
├── Vendor Decision
├── Capitalization Evidence
├── Benefit Plan
├── Technical Debt Plan
├── Portfolio Decision
└── Product Exit Plan

## Audit

必须审计：

- Taxonomy映射；
- Allocation Rule；
- Manual Adjustment；
- Product Owner变化；
- Funding Decision；
- Chargeback；
- Contract Renewal；
- Capitalization Review；
- Benefit确认；
- Debt金额调整；
- Portfolio Stop；
- Product Exit。

## 验收标准

- TBM Evidence关联所有ELMOS引擎；
- 产品成本可追溯到资源；
- 投资可追溯到战略和能力；
- Benefit关联真实运行结果；
- Accounting和Portfolio权限分离；
- Audit和Billing统一；
- Evidence Pack可离线验收。

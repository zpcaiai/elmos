---
name: financial-model-data-quality-reconciliation-and-control
description: "验证财务、成本、使用、分配、预算、合同和收益模型的完整性、一致性和可审计性。"
---

# TBM Data Quality

## 质量维度

COMPLETENESS
ACCURACY
TIMELINESS
CONSISTENCY
UNIQUENESS
VALIDITY
TRACEABILITY
RECONCILIATION
CONFIDENCE

## Control

Source Total
GL Reconciliation
Invoice Match
Currency
Period
Duplicate
Allocation
Usage Coverage
Product Mapping
Contract Match
Benefit Deduplication

## Coverage

Cost Coverage
Usage Coverage
Product Coverage
Application Coverage
Vendor Coverage
Labor Coverage
Benefit Coverage

## Reconciliation

GL
→ Technology Cost

Technology Cost
→ TBM Model

TBM Model
→ Product Cost

Product Cost
→ Showback

Showback
→ Chargeback

## Data状态

TRUSTED
TRUSTED_WITH_GAPS
PARTIAL
UNTRUSTED
STALE
UNKNOWN

## Manual Adjustment

每项Adjustment：

- Reason；
- Owner；
- Amount；
- Period；
- Approval；
- Reversal；
- Evidence。

## Close

支持：

MONTHLY_CLOSE
QUARTERLY_CLOSE
ANNUAL_CLOSE
FORECAST_CYCLE
CONTRACT_CYCLE

## 验收标准

- GL可核对；
- 每层Cost守恒；
- Coverage可见；
- Manual Adjustment可审计；
- Stale数据不显示为当前；
- 低质量模型不能Chargeback；
- 历史模型不可重写；
- Audit可以重放。

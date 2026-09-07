---
name: tbm-investment-engine-contract-and-worker
description: "实现TBM与数字产品投资治理引擎、财务Provider、成本模型Worker和统一任务契约。"
---

# TBM Investment Engine

## Capability

{
  "engine": "ELMOS_TBM_INVESTMENT",
  "engineVersion": "1.0.0",
  "capabilities": [
    "COST_INGESTION",
    "TBM_TAXONOMY",
    "COST_ALLOCATION",
    "DIGITAL_PRODUCT_MODEL",
    "PRODUCT_FUNDING",
    "TCO",
    "UNIT_ECONOMICS",
    "BUDGET_FORECAST",
    "SHOWBACK_CHARGEBACK",
    "VENDOR_ECONOMICS",
    "CAPITALIZATION_EVIDENCE",
    "BENEFIT_REALIZATION",
    "TECHNICAL_DEBT_ECONOMICS",
    "INVESTMENT_PORTFOLIO"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/reconcile
POST /engine/v1/allocate
POST /engine/v1/forecast
POST /engine/v1/evaluate
POST /engine/v1/funding-decisions
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 导入财务和技术数据；
- 归一化Period和Currency；
- 映射Taxonomy；
- 执行分配模型；
- 计算Product Cost；
- 运行Scenario；
- 生成Funding和Benefit候选；
- 保存Audit Evidence。

## Worker默认禁止

- 发布正式财务报表；
- 创建总账凭证；
- 自动批准资本化；
- 自动执行Chargeback；
- 自动终止供应商合同；
- 自动停止核心产品；
- 自动确认收益已实现；
- 自动把技术债计为会计负债。

## Provider

ERP_FINANCE
PLANNING
PROCUREMENT
HR_COST
CLOUD_BILLING
SAAS
CONTRACT
ASSET_REGISTER
PORTFOLIO
BUSINESS_KPI

## 验收标准

- Engine独立部署；
- 财务Source只读；
- 模型版本化；
- 所有分配可解释；
- 正式会计动作需人工授权；
- Evidence进入统一Contract。

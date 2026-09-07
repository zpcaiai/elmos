---
name: transformation-execution-engine-contract-and-worker
description: "实现企业转型执行与变革管理引擎、Portfolio Provider、敏感组织数据边界和统一执行契约。"
---

# Transformation Engine

## Capability

{
  "engine": "ELMOS_TRANSFORMATION_EXECUTION",
  "engineVersion": "1.0.0",
  "capabilities": [
    "TRANSFORMATION_PORTFOLIO",
    "STRATEGY_EXECUTION",
    "TRANSFORMATION_OFFICE",
    "CROSS_PORTFOLIO_DEPENDENCY",
    "CHANGE_PORTFOLIO",
    "CHANGE_SATURATION",
    "STAKEHOLDER",
    "CHANGE_IMPACT",
    "COMMUNICATION",
    "ADOPTION",
    "RESISTANCE",
    "SPONSORSHIP",
    "DECISION_ESCALATION",
    "BUSINESS_READINESS",
    "CUTOVER_HYPERCARE",
    "BENEFIT_REALIZATION",
    "TRANSFORMATION_HEALTH"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/assess
POST /engine/v1/plan
POST /engine/v1/execute-step
POST /engine/v1/decisions
POST /engine/v1/validate
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 导入战略和Portfolio；
- 建立跨组合依赖；
- 分析Change Impact；
- 计算Saturation候选；
- 生成Wave和Readiness；
- 聚合Adoption和Benefit；
- 输出Transformation Health；
- 保存Evidence。

## 默认禁止

- 自动批准重大转型；
- 自动改变战略优先级；
- 自动接受Benefit；
- 自动把员工标记为阻力者；
- 读取私人通信推断态度；
- 自动关闭Concern；
- 自动作出人员高影响决定；
- 自动覆盖业务Owner的Readiness判断。

## 数据边界

STRATEGY_INTERNAL
PORTFOLIO_CONFIDENTIAL
STAKEHOLDER_CONFIDENTIAL
COHORT_AGGREGATE
PERSONAL_RESTRICTED
EXECUTIVE_RESTRICTED

## 验收标准

- Engine独立部署；
- Portfolio Provider可替换；
- 个人数据独立授权；
- 默认使用Cohort聚合；
- 重大决策由授权角色完成；
- Evidence进入统一Contract。

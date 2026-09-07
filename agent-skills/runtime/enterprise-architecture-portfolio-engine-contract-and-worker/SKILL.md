---
name: enterprise-architecture-portfolio-engine-contract-and-worker
description: 实现企业架构与应用组合引擎、EA Repository Provider、Portfolio Worker和统一任务契约。
---

# EA Portfolio Engine

## Capability

{
  "engine": "ELMOS_ENTERPRISE_ARCHITECTURE",
  "engineVersion": "1.0.0",
  "capabilities": [
    "ENTERPRISE_CONTEXT",
    "BUSINESS_CAPABILITY",
    "VALUE_STREAM",
    "EA_REPOSITORY",
    "APPLICATION_PORTFOLIO",
    "TECHNOLOGY_RADAR",
    "ARCHITECTURE_STANDARDS",
    "DEPENDENCY_RISK",
    "TARGET_ARCHITECTURE",
    "INVESTMENT_PORTFOLIO",
    "ROADMAP",
    "ARCHITECTURE_DECISION",
    "CONTINUOUS_CONFORMANCE"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/assess
POST /engine/v1/plan
POST /engine/v1/evaluate
POST /engine/v1/decisions
POST /engine/v1/conformance
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 导入Repository和Portfolio；
- 读取ELMOS跨引擎Evidence；
- 计算Capability、Application和Technology视图；
- 生成目标架构候选；
- 执行依赖和Roadmap分析；
- 生成Decision候选；
- 输出Conformance Evidence。

## Worker默认禁止

- 自动批准投资；
- 自动退役生产系统；
- 自动接受架构例外；
- 自动修改业务能力Owner；
- 自动确认业务收益；
- 自动把技术Radar状态改为强制标准；
- 删除历史Architecture Decision。

## Provider

EA_REPOSITORY
PORTFOLIO_MANAGEMENT
CMDB
SERVICE_CATALOG
DATA_CATALOG
FINANCE
PROJECT_PORTFOLIO
TECHNOLOGY_RADAR
MODELING_TOOL

## 验收标准

- Engine独立部署；
- 元模型Provider可替换；
- Portfolio评分有Evidence；
- Target候选和批准状态分开；
- 所有Decision可审计；
- Evidence进入统一Contract。

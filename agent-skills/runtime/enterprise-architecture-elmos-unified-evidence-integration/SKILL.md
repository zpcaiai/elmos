---
name: enterprise-architecture-elmos-unified-evidence-integration
description: 将业务能力、应用组合、技术组合、Target、投资、路线图和Decision映射到ELMOS统一Evidence。
---

# Unified EA Integration

## Extension

{
  "scope": "ENTERPRISE_ARCHITECTURE",
  "engine": "ELMOS_ENTERPRISE_ARCHITECTURE",
  "engineExtension": {
    "schema": "elmos.enterprise-architecture-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

ENTERPRISE_CONTEXT
BUSINESS_CAPABILITY_MAP
CAPABILITY_ASSESSMENT
VALUE_STREAM
EA_REPOSITORY
APPLICATION_PORTFOLIO
APPLICATION_LIFECYCLE
TECHNOLOGY_PORTFOLIO
TECHNOLOGY_RADAR
ARCHITECTURE_STANDARD
ARCHITECTURE_EXCEPTION
DEPENDENCY_RISK
CURRENT_ARCHITECTURE
TRANSITION_ARCHITECTURE
TARGET_ARCHITECTURE
ARCHITECTURE_EVALUATION
INVESTMENT_PORTFOLIO
ARCHITECTURE_ROADMAP
ARCHITECTURE_DECISION
ARCHITECTURE_CONFORMANCE
EA_VALUE

## Risk映射

UNKNOWN_APPLICATION_OWNER
→ PORTFOLIO_OWNERSHIP_RISK

DUPLICATE_CAPABILITY
→ PORTFOLIO_REDUNDANCY_RISK

UNSUPPORTED_TECHNOLOGY
→ TECHNOLOGY_LIFECYCLE_RISK

VENDOR_CONCENTRATION
→ STRATEGIC_DEPENDENCY_RISK

EXPIRED_ARCHITECTURE_EXCEPTION
→ GOVERNANCE_RISK

MISSING_TRANSITION_ARCHITECTURE
→ TRANSFORMATION_EXECUTION_RISK

UNREALIZED_BENEFIT
→ INVESTMENT_VALUE_RISK

ARCHITECTURE_DRIFT
→ TARGET_REALIZATION_RISK

## Checks

ELMOS / Enterprise Context
ELMOS / Capability Ownership
ELMOS / Portfolio Quality
ELMOS / Application Lifecycle
ELMOS / Technology Standards
ELMOS / Architecture Exceptions
ELMOS / Systemic Risk
ELMOS / Target Feasibility
ELMOS / Transition Architecture
ELMOS / Roadmap Dependency
ELMOS / Architecture Decision
ELMOS / Architecture Conformance
ELMOS / Benefit Realization

## Composite Change Set

Enterprise Architecture Change Set
├── Capability Map
├── Application Portfolio
├── Technology Standard
├── Target Architecture
├── Domain Architecture
├── Data Ownership
├── Reference Architecture
├── Roadmap
├── Investment Decision
└── Architecture Decision

## Audit

必须审计：

- Capability定义变化；
- Application Owner变化；
- 生命周期决定；
- Technology Radar移动；
- 标准发布；
- Exception批准；
- Target批准；
- 投资优先级变化；
- Roadmap重排；
- ADR接受和Supersede；
- Conformance Override；
- Benefit确认。

## 验收标准

- EA Evidence关联所有ELMOS引擎；
- 能力、应用、技术和投资形成统一图；
- Target与真实Delivery关联；
- Portfolio Decision可审计；
- Benefit和Risk持续验证；
- Evidence Pack支持离线验收。

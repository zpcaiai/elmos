---
name: operations-elmos-unified-evidence-integration
description: 将服务、CMDB、事件、Incident、Problem、Change、SLO、容量和连续性映射到ELMOS统一Evidence。
---

# Unified Operations Integration

## Extension

{
  "scope": "OPERATIONS_SRE_ITSM",
  "engine": "ELMOS_OPERATIONS_SRE_ITSM",
  "engineExtension": {
    "schema": "elmos.operations-sre-itsm-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

SERVICE_ESTATE
CMDB_QUALITY
SERVICE_TOPOLOGY
BUSINESS_IMPACT
EVENT_CORRELATION
ALERT_QUALITY
INCIDENT
MAJOR_INCIDENT
POSTMORTEM
PROBLEM
KNOWN_ERROR
CHANGE
SLO
ERROR_BUDGET
ONCALL
RUNBOOK
AIOPS
AUTO_REMEDIATION
CAPACITY
BUSINESS_CONTINUITY
OPERATIONS_SCORECARD

## Risk映射

UNKNOWN_SERVICE_OWNER
→ SERVICE_OWNERSHIP_RISK

CMDB_STALE
→ CONFIGURATION_MANAGEMENT_RISK

ALERT_STORM
→ OPERATIONAL_RESPONSE_RISK

REPEAT_INCIDENT
→ PROBLEM_MANAGEMENT_RISK

UNSAFE_AUTOMATION
→ OPERATIONAL_CHANGE_RISK

ERROR_BUDGET_EXHAUSTED
→ RELIABILITY_RISK

ONCALL_OVERLOAD
→ HUMAN_SUSTAINABILITY_RISK

CONTINUITY_UNTESTED
→ BUSINESS_CONTINUITY_RISK

## Checks

ELMOS / Service Model
ELMOS / CMDB Quality
ELMOS / Topology Coverage
ELMOS / Alert Quality
ELMOS / Incident Readiness
ELMOS / Problem Learning
ELMOS / Change Risk
ELMOS / SLO
ELMOS / On-call Sustainability
ELMOS / Runbook Readiness
ELMOS / Automation Safety
ELMOS / Capacity
ELMOS / Business Continuity

## Composite Change Set

Operations Modernization Change Set
├── Service Catalog
├── CMDB Model
├── Observability
├── Alert Policy
├── Incident Workflow
├── Problem and Known Error
├── Change Policy
├── SLO
├── Runbook
├── Automation
├── Capacity Plan
└── Continuity Plan

## Audit

必须审计：

- CI合并和删除；
- Service Owner变化；
- Alert抑制；
- Incident严重度变化；
- Major Incident关闭；
- Root Cause确认；
- Change批准；
- SLO变化；
- Error Budget Override；
- 自动修复；
- DR宣布；
- Continuity结果；
- Runbook执行。

## 验收标准

- Operations Evidence关联所有ELMOS引擎；
- Service成为统一运行管理中心；
- Incident、Problem和Change独立；
- SLO、容量和连续性进入Portfolio；
- 自动化完整审计；
- Evidence Pack支持离线验收。

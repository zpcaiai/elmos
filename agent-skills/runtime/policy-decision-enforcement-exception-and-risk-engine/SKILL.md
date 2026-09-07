---
name: policy-decision-enforcement-exception-and-risk-engine
description: "实现跨域Policy IR、PDP／PEP、授权、风险、例外、冲突和本地政策。"
---

# Policy Architecture

## 组件

Policy Administration Point
Policy Information Point
Policy Decision Point
Policy Enforcement Point
Policy Audit Point

## Policy Domain

SECURITY
PRIVACY
DATA
COST
ARCHITECTURE
QUALITY
SAFETY
COMPLIANCE
AGENT
WORKFLOW
HUMAN_DECISION
TENANT
RESIDENCY

## Decision

ALLOW
DENY
ALLOW_WITH_CONDITIONS
REQUIRE_APPROVAL
REDACT
ROUTE
LIMIT
QUARANTINE
SAFE_STOP

## Policy Priority

LOCAL_SAFETY
LOCAL_REGULATORY
TENANT
ENTERPRISE
DOMAIN
WORKFLOW
AGENT_DEFAULT

高优先级Deny不能被低优先级Allow覆盖。

## Policy Bundle

Version
Scope
Signer
Effective Time
Expiry
Dependencies
Tests
Compatibility

## Exception

Scope
Reason
Owner
Control
Expiry
Removal
Approval

## Conflict

ALLOW_DENY_CONFLICT
VERSION_CONFLICT
SCOPE_CONFLICT
LOCAL_GLOBAL_CONFLICT
EXCEPTION_CONFLICT

## Policy Simulation

新Policy生产发布前运行：

Historical Replay
Scenario
Shadow Decision
Impact Analysis
False Deny／Allow Review

## 验收标准

- Decision与Enforcement分开；
- Policy版本固定；
- Local Safety优先；
- Exception有期限；
- Decision可解释；
- Policy冲突显式；
- 高风险Fail Closed；
- Policy升级有Shadow。

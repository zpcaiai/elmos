---
name: problem-root-cause-known-error-and-postmortem-engine
description: 聚合重复Incident，管理Root Cause假设、Known Error、Workaround、Postmortem和长期行动。
---

# Problem Management

## Problem来源

Repeated Incident
Major Incident
Trend
Vulnerability
Capacity Risk
Audit
Supplier Failure
Near Miss
Automation Failure

## Root Cause状态

HYPOTHESIS
SUPPORTED
LIKELY
CONFIRMED
DISPROVED
UNKNOWN

## Root Cause Evidence

- Reproduction；
- Change Reversal；
- Fault Injection；
- Log；
- Trace；
- Metric；
- Code；
- Configuration；
- Hardware；
- Supplier Confirmation。

## Known Error

包含：

Failure Mode
Affected Services
Trigger
Symptom
Detection
Workaround
Permanent Fix
Risk
Owner
Review

## Workaround

READ_ONLY
MANUAL
AUTOMATED
RISKY
TEMPORARY
DEPRECATED

## Postmortem

Impact
Detection
Timeline
Trigger
Contributing Factors
Recovery
What Went Well
What Went Poorly
Lessons
Actions

## Action类型

CODE_FIX
TEST
MONITORING
RUNBOOK
AUTOMATION
CAPACITY
ARCHITECTURE
PROCESS
TRAINING
SUPPLIER
DOCUMENTATION

## Action关闭

不能只标记Done。

必须包含：

Implementation Evidence
Validation
Production Observation
Residual Risk

## 验收标准

- Incident和Problem分开；
- Root Cause有Evidence等级；
- Known Error有Workaround；
- Postmortem无责；
- Action有Owner和验证；
- 重复Incident可自动聚类；
- Problem不会因Incident关闭自动关闭。

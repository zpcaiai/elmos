---
name: agent-gateway-routing-budget-and-repair-loop
description: "路由编码Agent、限制工具、Token、成本、时间和修复次数。"
---

# Routing Input

Tenant Policy
Error Class
Repository Size
Language
Provider Availability
Data Residency
Budget
Previous Success

## Repair Loop

Compile
→ Classify
→ Build Context
→ Run Agent
→ Apply Patch
→ Inspect Diff
→ Compile
→ Test

## Stop Conditions

Build Passed
Maximum Iterations
Budget Exceeded
Unsafe Diff
Test Regression
Policy Denied
Repeated Error
Human Required

## 验收标准

- Agent运行有Task Contract；
- Provider可替换；
- Agent无GitHub Token；
- Agent不能绕过测试；
- 成本实时累计；
- 失败进入人工清单；
- Agent Patch可独立Review。

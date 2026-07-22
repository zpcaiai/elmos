---
name: autonomous-goal-constraint-planning-and-plan-compiler
description: "从企业目标、Twin状态、约束、资源和Evidence生成多方案现代化计划。"
---

# Autonomous Planning

## 输入

Current Twin Snapshot
Desired Outcome
Target State
Hard Constraints
Soft Constraints
Resources
Dependencies
Risk
Cost
Change Capacity
Deadlines
Policies

## Goal类型

CAPABILITY
RISK_REDUCTION
COST
MODERNIZATION
COMPLIANCE
RELIABILITY
DECOMMISSION
PRODUCT_VALUE
ORGANIZATION
SUSTAINABILITY

## Planning方法

Graph Search
Constraint Satisfaction
Critical Path
Scheduling
Mixed Integer Optimization候选
Heuristic
Rule-based
LLM-assisted
Historical Retrieval

## Plan内容

Objective
Baseline
Steps
Dependencies
Resources
Policies
Assumptions
Risks
Evidence
Simulation
Approval
Rollback
Value Hypothesis

## Plan Alternative

FASTEST
LOWEST_RISK
LOWEST_COST
MAXIMUM_VALUE
MOST_REVERSIBLE
BALANCED
CUSTOM

## Plan状态

CANDIDATE
VALIDATED
DOMINATED
NOT_FEASIBLE
POLICY_DENIED
READY_FOR_DECISION

## Compiler

将高层Plan转换为：

Workflow
Engine Tasks
Agent Tasks
Human Gates
Policy Gates
Verification
Compensation

## 重要限制

Planner不能：

- 自动修改Hard Constraint；
- 隐藏不可行条件；
- 以模型置信度代替Evidence；
- 直接执行生成的Plan。

## 验收标准

- Baseline存在；
- Hard Constraint确定性验证；
- 至少提供可行替代候选；
- Assumption显式；
- 资源和容量进入；
- Plan可编译；
- 决策后Plan被冻结。

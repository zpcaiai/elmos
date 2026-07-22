---
name: job-role-task-competency-and-work-architecture-engine
description: "将业务结果和工作任务转换为Work Role、Job Role、Responsibility、Skill和Position架构。"
---

# Work Architecture

## 层级

Business Outcome
→ Work Domain
→ Work
→ Task
→ Responsibility
→ Work Role
→ Job Role
→ Position

## Role类型

PRODUCT
ENGINEERING
DATA
SECURITY
OPERATIONS
ARCHITECTURE
DESIGN
MANAGEMENT
GOVERNANCE
VENDOR
CUSTOM

## Work Role

描述：

- 需要完成的工作；
- 任务；
- 决策；
- 责任；
- 产出；
- Skill。

## Job Role

描述：

- Job Family；
- Career Track；
- Level；
- Compensation Band候选；
- Work Roles组合；
- Organization Context。

## Responsibility

RESPONSIBLE
ACCOUNTABLE
CONSULTED
INFORMED
APPROVER
CONTROL_OWNER
SERVICE_OWNER
DATA_OWNER

## Role Profile

Purpose
Outcomes
Responsibilities
Tasks
Skills
Experience
Authority
Interfaces
Measures
Risk

## Job Description生成

Job Description必须从Role Profile生成，不直接拼接技能关键词。

## Findings

TITLE_ROLE_MISMATCH
ROLE_OVERLOADED
ROLE_WITHOUT_DECISION_RIGHT
ACCOUNTABILITY_DUPLICATED
TASK_WITHOUT_OWNER
POSITION_WITHOUT_WORK
ROLE_REQUIREMENT_UNREALISTIC
JOB_DESCRIPTION_STALE

## 验收标准

- Work Role与Job Role分开；
- Task和Skill关联；
- Responsibility明确；
- 一个职位可组合多个Role；
- 关键Task有Accountability；
- Job Description可追踪；
- Role变化触发职业和学习影响分析。

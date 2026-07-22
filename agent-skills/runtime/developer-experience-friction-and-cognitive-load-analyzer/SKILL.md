---
name: developer-experience-friction-and-cognitive-load-analyzer
description: 通过开发者Journey、Telemetry和调查识别等待、失败、重复工作、可发现性和认知负担。
---

# Developer Experience

## Developer Journey

NEW_DEVELOPER_ONBOARDING
CREATE_SERVICE
RUN_LOCALLY
CHANGE_CODE
RUN_TESTS
OPEN_PR
REVIEW
CREATE_ENVIRONMENT
DEPLOY
DEBUG
ROLLBACK
REQUEST_ACCESS
HANDLE_INCIDENT
DECOMMISSION

## Journey Step

记录：

Active Time
Wait Time
Failure
Retry
Handoff
Tool
Documentation
Approval
Support
Context Switch

## DevEx维度

FLOW
FEEDBACK
COGNITIVE_LOAD
DISCOVERABILITY
RELIABILITY
AUTONOMY
SATISFACTION
SUPPORT

## Friction

BUILD_WAIT
RUNNER_QUEUE
ENVIRONMENT_WAIT
ACCESS_WAIT
REVIEW_WAIT
APPROVAL_WAIT
TOOL_FAILURE
DOCUMENTATION_GAP
LOCAL_SETUP
SECRET_SETUP
DEPENDENCY
CONTEXT_SWITCH
MANUAL_REENTRY

## 证据来源

Telemetry
Support Ticket
Survey
Interview
Journey Test
Pipeline
Portal Search
Documentation
Incident

## 隐私

禁止：

- 监控键盘；
- 统计个人代码量；
- 给个人排名；
- 用Survey惩罚团队；
- 公开个人低分。

## 关键指标

Time to First Commit
Time to First Successful Build
Time to First Preview
Time to First Production
Environment Provision Time
Build Feedback Time
PR Wait Time
Support Resolution Time
Task Success Rate

## 验收标准

- 以Journey为中心；
- Active与Wait分开；
- Telemetry和主观反馈结合；
- 不衡量个人产出；
- Friction有Owner；
- 改进效果可再次验证。

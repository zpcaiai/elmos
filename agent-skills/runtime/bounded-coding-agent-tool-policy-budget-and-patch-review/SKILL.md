---
name: bounded-coding-agent-tool-policy-budget-and-patch-review
description: "在Private Runner Sandbox中执行受限Coding Agent修复，实时限制工具、Token、成本和Patch范围。"
---

# Agent Boundary

Agent Gateway负责：

Provider Routing
Policy
Budget
Trace
Cancellation
Result Normalization

Private Runner负责：

Sandbox
Filesystem
Tool Execution
Network
Secret Boundary
Patch Collection

## Agent Provider

CODEX
CLAUDE_CODE
OPENHANDS
LOCAL_AGENT
CUSTOM

## Task Contract

Purpose
Snapshot
Worktree
Target Profile
Error Set
Allowed Files
Allowed Tools
Forbidden Tools
Maximum Iterations
Maximum Tokens
Maximum Cost
Maximum Duration
Maximum Changed Files
Maximum Diff Lines

## Tool Allowlist

READ_FILE
LIST_FILES
SEARCH_CODE
EDIT_FILE
RUN_MAVEN_COMPILE
RUN_MAVEN_TEST
READ_BUILD_RESULT

默认禁止：

ARBITRARY_SHELL
GIT_PUSH
CREATE_PR
READ_SECRET
ARBITRARY_NETWORK
MODIFY_POLICY
MODIFY_TARGET_PROFILE
DELETE_TESTS
DISABLE_TESTS

## Context Builder

只提供：

Relevant Error
Relevant Module
Relevant Files
Target Profile
Migration Rule
Previous Attempts
Allowed Tool Contract

不得提供：

GitHub Token
Maven Password
OIDC Token
Other Tenant Data
Unrelated Source
Full Environment Dump

## Repair Loop

Classify Failure
→ Build Context
→ Agent Run
→ Collect Patch
→ Static Patch Policy
→ Compile
→ Test
→ Compare Error Signature

## Stop Conditions

Build Passed
Maximum Iterations
Budget Exceeded
Repeated Error
Unsafe Patch
Test Regression
Target Drift
Policy Denied
Human Required

## Patch Policy

禁止：

修改Target Java
修改Target Boot
删除大量测试
添加未知Repository
禁用安全控制
吞掉异常
用空实现绕过编译
修改CI以跳过测试

## 实时预算

Agent必须流式上报：

Tokens
Cost
Tool Calls
Elapsed Time
Changed Files

超限时立即：

Cancel
Revoke Tool Lease
Terminate Sandbox
Collect Partial Evidence

## 结果

REPAIRED
PARTIAL
BUDGET_EXCEEDED
UNSAFE_PATCH
REPEATED_FAILURE
PROVIDER_FAILED
HUMAN_REQUIRED

## 验收标准

- Agent运行在任务Sandbox；
- Tool Policy实际执行，不只是元数据；
- Agent无GitHub Credential；
- Agent不能自行Push或PR；
- Budget可执行中终止；
- Patch通过重新编译和测试；
- 每次尝试完整留证；
- 三次失败后默认人工升级。

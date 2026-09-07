---
name: build-test-compatibility-and-bounded-agent-verification
description: "执行基线和目标构建、测试、API兼容、错误分类及受限Agent修复。"
---

# Verification

Compile
Unit Test
Integration Test
API Compatibility
OpenAPI Diff
Dependency Analysis
Static Analysis
Test Count
Mutation候选
Performance Smoke候选

## Baseline

若基线失败：

BASELINE_BROKEN

必须区分：

Pre-existing Failure
Migration Regression
Environment Failure

## Test Count

Discovered
Executed
Passed
Failed
Skipped

目标测试数量显著减少时不能以“全部通过”判定成功。

## Agent Loop

最多3次默认。

每次保存：

Input Error
Agent Version
Prompt Hash
Patch
Build
Test
Cost

## 验收标准

- 基线与目标使用独立结果；
- 预存失败不归因迁移；
- 测试数量差异可见；
- API差异可分类；
- Agent循环受限；
- 失败可升级人工；
- 结果可重放。

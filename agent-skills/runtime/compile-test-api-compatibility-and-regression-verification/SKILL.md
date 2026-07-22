---
name: compile-test-api-compatibility-and-regression-verification
description: "对Baseline和迁移结果执行编译、测试发现、测试执行、API兼容和回归判定。"
---

# Verification

## 层级

COMPILE
UNIT_TEST
INTEGRATION_TEST
TEST_DISCOVERY
JAVA_API
HTTP_API
DEPENDENCY
STATIC_ANALYSIS
SBOM
PERFORMANCE_SMOKE候选

## Baseline Comparison

Baseline Build
Target Build

分别记录：

Module Count
Compile Result
Test Discovered
Test Executed
Test Passed
Test Failed
Test Skipped
Artifact Count
Public API
Dependency Set

## Failure Attribution

PRE_EXISTING_FAILURE
MIGRATION_REGRESSION
ENVIRONMENT_FAILURE
DEPENDENCY_FAILURE
TEST_INFRASTRUCTURE_FAILURE
INCONCLUSIVE

## Test Discovery Gate

若迁移后：

Discovered Tests显著减少

则：

TEST_DISCOVERY_REGRESSION

即使剩余测试全部通过，也不能自动PASS。

## API Decision

COMPATIBLE
SOURCE_BREAKING
BINARY_BREAKING
HTTP_BREAKING
EXPECTED_BREAK
UNKNOWN

## 总体Decision

PASS
PASS_WITH_WARNINGS
BLOCKED
INCONCLUSIVE
MANUAL_REMEDIATION_REQUIRED

## 输出

Verification Manifest
Compile Evidence
Test Evidence
API Diff
Dependency Diff
Regression List
Remaining Manual Tasks

## 验收标准

- Baseline和Target独立保存；
- 预存失败不归因Migration；
- 测试数量对比；
- API差异分类；
- 环境失败不交给代码修复；
- BLOCKED不能进入自动Delivery；
- Inconclusive不映射为成功；
- 手工修复任务结构化。

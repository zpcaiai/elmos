---
name: compile-test-api-dependency-and-regression-verification
description: "比较基线与目标的编译、测试、API、依赖、安全和运行结果，识别迁移回归。"
---

# Verification Levels

COMPILE
UNIT_TEST
INTEGRATION_TEST
API_COMPATIBILITY
OPENAPI_DIFF
DEPENDENCY_DIFF
SBOM
SCA
STATIC_ANALYSIS
PERFORMANCE_SMOKE

## Baseline和Target

每项结果必须带：

Snapshot
Worktree
Toolchain
Command
Environment
Started At
Finished At
Artifact
Status

## Failure Attribution

PRE_EXISTING
MIGRATION_REGRESSION
ENVIRONMENT_FAILURE
TEST_INFRASTRUCTURE_FAILURE
INCONCLUSIVE

## Test Inventory

Baseline Discovered
Baseline Executed
Baseline Passed
Baseline Failed
Baseline Skipped

Target Discovered
Target Executed
Target Passed
Target Failed
Target Skipped

## Test Preservation

如果：

Target Discovered
显著低于
Baseline Discovered

则：

TEST_DISCOVERY_REGRESSION

即使剩余测试全部通过，也不能判为成功。

## API Compatibility

Java Binary API
Java Source API
REST Path
HTTP Method
Request Schema
Response Schema
Status Code
Serialization
Message Schema候选

状态：

COMPATIBLE
COMPATIBLE_WITH_ADAPTER
EXPECTED_BREAK
UNEXPECTED_BREAK
INCONCLUSIVE

## Dependency Diff

Added
Removed
Upgraded
Downgraded
Conflict Resolved
New Conflict
License Change
CVE Change候选

## Gate

PASS
PASS_WITH_WARNINGS
HUMAN_REVIEW
FAIL
INCONCLUSIVE

## 验收标准

- Baseline和Target结果独立；
- 预存失败不归因迁移；
- 测试发现数量可比较；
- API Break有精确位置；
- Environment Failure不触发Agent；
- 所有验证结果产生Artifact；
- Inconclusive不映射Pass。

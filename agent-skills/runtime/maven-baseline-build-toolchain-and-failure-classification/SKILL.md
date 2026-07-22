---
name: maven-baseline-build-toolchain-and-failure-classification
description: "在原始Snapshot上复现Maven构建，记录环境并分类代码、依赖、工具和网络失败。"
---

# Maven Baseline

## 环境

JDK Vendor
JDK Version
Maven Version
Wrapper Version
OS Image Digest
Locale
Timezone
CPU
Memory
Network Profile
Repository Mirrors

## Wrapper策略

Project Maven Wrapper
→ 验证Wrapper文件和Distribution
→ 使用批准的Distribution

否则使用ELMOS批准Maven版本。

## 阶段

DISCOVER
RESOLVE
COMPILE
TEST_DISCOVERY
TEST
PACKAGE
REPRODUCIBILITY_CHECK候选

## Failure Class

SOURCE_COMPILATION_FAILURE
SOURCE_TEST_FAILURE
DEPENDENCY_RESOLUTION_FAILURE
PRIVATE_REPOSITORY_AUTH_FAILURE
TOOLCHAIN_FAILURE
PLUGIN_FAILURE
NETWORK_POLICY_DENIED
ENVIRONMENT_FAILURE
TIMEOUT
OUT_OF_MEMORY
BUILD_MUTATES_SOURCE
NON_REPRODUCIBLE
UNKNOWN

## 输出

Build Environment Manifest
Module Build Order
Dependency Resolution Result
Compile Result
Test Inventory
Test Result
Build Mutation Diff
Failure Evidence

## 规则

- 不允许Agent修复Baseline环境问题；
- 依赖下载仅允许批准Repository；
- 构建前后比较Tracked Files；
- 原始Snapshot保持只读；
- 失败必须保留原始和归一化日志。

## 验收标准

- 私服不可用不会归类为代码失败；
- 项目Wrapper指向未知域名时被阻止；
- 多模块构建顺序正确；
- 构建修改源码时生成Finding；
- 基线结果可以重复执行；
- 每个失败类别有确定Evidence；
- Baseline失败不会被后续迁移结果覆盖。

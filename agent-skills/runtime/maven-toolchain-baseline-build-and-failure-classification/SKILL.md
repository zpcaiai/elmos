---
name: maven-toolchain-baseline-build-and-failure-classification
description: "验证Maven Wrapper、JDK、私服和环境，以干净Snapshot执行可重复基线构建并分类失败。"
---

# Toolchain Discovery

检测：

mvnw
.mvn/wrapper/maven-wrapper.properties
pom.xml
.mvn/jvm.config
.tool-versions
sdkmanrc
Dockerfile
CI Workflow
maven.compiler.release
source / target
Spring Boot Parent／BOM

## Wrapper验证

验证：

distributionUrl
wrapperSha256Sum
distributionSha256Sum
Allowed Host
Maven Version
Wrapper Distribution Type

没有Checksum时：

WARN
REQUIRE_APPROVAL
或
使用ELMOS批准Maven版本

由Tenant Policy决定。

## Build Environment

JDK Version
Maven Version
OS Image Digest
Timezone
Locale
Encoding
Maven Local Repository
Settings Reference
Network Profile
CPU／Memory
Timeout

## Baseline命令候选

./mvnw
  --batch-mode
  --no-transfer-progress
  clean test

或Policy指定：

verify
package
install

## 私服

Settings通过Secret Reference注入。

收集：

Repository Host
Resolution Result
Authentication Failure
Certificate Failure
Missing Artifact

不得收集完整Credential。

## Failure Taxonomy

SOURCE_COMPILATION_FAILURE
TEST_FAILURE
DEPENDENCY_NOT_FOUND
DEPENDENCY_AUTHENTICATION_FAILURE
REPOSITORY_UNAVAILABLE
TLS_CERTIFICATE_FAILURE
TOOLCHAIN_MISMATCH
WRAPPER_INTEGRITY_FAILURE
NETWORK_DENIED
PLUGIN_FAILURE
OUT_OF_MEMORY
TIMEOUT
BUILD_MUTATES_SOURCE
UNKNOWN_BUILD_FAILURE

## 输出

Build Manifest
Toolchain Manifest
Resolved Module List
Dependency Resolution Summary
Build Log
Test Discovery
Source Mutation Diff
Baseline Status

## 验收标准

- Build从干净Snapshot执行；
- Wrapper下载内容可验证；
- Environment Failure和Source Failure分开；
- Maven Cache按Tenant隔离；
- Build修改Tracked File可发现；
- 相同输入可重复执行；
- 非代码失败不进入Coding Agent。

---
name: java-legacy-health-check-and-risk-evidence
description: "从Snapshot、Maven模型和源码生成Java技术指纹、风险Finding及可审计体检报告。"
---

# Java Health Check

## 识别

Java Source Level
JDK Runtime
Maven Modules
Spring Framework
Spring Boot
Spring Cloud
Jakarta／javax
Spring Security
Hibernate
JUnit
Servlet
Database Driver
Cache
Messaging
Application Server

## 风险维度

BUILD
FRAMEWORK
DEPENDENCY
TEST
API
DATA
TRANSACTION
CACHE
SECURITY
OPERATIONS

## Finding

Finding ID
Rule ID
Severity
Confidence
Module
File
Line
Evidence
Why It Matters
Migration Impact
Automation Candidate
Human Action

## Finding示例

UNSUPPORTED_JDK
SPRING_BOOT_2
JAVAX_USAGE
SECURITY_CONFIGURATION_LEGACY
HIBERNATE_5
DEPENDENCY_CONFLICT
PRIVATE_DEPENDENCY
NO_AUTOMATED_TEST
TEST_DISCOVERY_LOW
DIRECT_DATABASE_ACCESS
TRANSACTION_RISK
CACHE_SERIALIZATION_RISK
BUILD_UNREPRODUCIBLE

## 禁止推断

源码不能可靠推断：

Business Criticality
Revenue Impact
Regulatory Criticality
Actual Production Usage

这些必须由Owner补充或来自其他Evidence。

## 报告

Executive Summary
Repository Summary
Module Graph
Fingerprint
Findings
Migration Readiness
Unknowns
Automation Candidates
Manual Risks

## 验收标准

- Finding带具体Evidence；
- Unknown不自动低风险；
- 报告公式版本化；
- 相同Snapshot可重复生成相同结果；
- Finding可追溯到Module和文件；
- 技术评分和业务Criticality分开；
- 报告不包含不必要源码正文。

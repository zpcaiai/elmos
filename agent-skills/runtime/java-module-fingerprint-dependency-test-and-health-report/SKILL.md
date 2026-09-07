---
name: java-module-fingerprint-dependency-test-and-health-report
description: "识别Maven多模块、JDK、Spring、依赖、测试、API、数据和迁移风险并生成证据化体检报告。"
---

# Module Graph

识别：

Aggregator Module
Parent Module
Library Module
Application Module
Test Module
Generated Module
Profile-specific Module

Module Identity：

Group ID
Artifact ID
Version
Relative Path
Packaging

## Technology Fingerprint

Java
Spring Framework
Spring Boot
Spring Cloud
Spring Security
Hibernate
JPA
MyBatis
Servlet
Jakarta / javax
JUnit
Mockito
Testcontainers
Database Driver
Cache
Messaging
Application Server

## Dependency Analysis

Declared
Managed
Resolved
Conflict
Duplicate
Excluded
Optional
Plugin Dependency
BOM

## Tests

Discovered Tests
Test Framework
Integration Tests
Skipped Tests
Disabled Tests
Test Source Count
Test Execution Baseline

## API

Public Java API
REST Endpoint
OpenAPI Artifact
Message Contract候选
Serialization Type

## Risk Finding

UNSUPPORTED_JDK
UNSUPPORTED_SPRING
JAVAX_USAGE
DEPENDENCY_CONFLICT
PRIVATE_DEPENDENCY
CIRCULAR_MODULE
BUILD_UNREPRODUCIBLE
MISSING_TEST
LOW_TEST_DISCOVERY
SECURITY_CONFIG_LEGACY
TRANSACTION_RISK
CACHE_SERIALIZATION_RISK
DIRECT_DATABASE_RISK
UNKNOWN_RUNTIME

## Evidence

每项Finding包含：

Finding ID
Rule Version
Module
File
Line候选
Observed Value
Expected Value
Evidence Ref
Confidence
Remediation Candidate

## Scoring

维度：

Build Health
Framework Age
Dependency Health
Test Readiness
API Risk
Data Risk
Security Risk
Operational Risk

不得从源码自动推断：

Business Criticality

## 输出

java-health-report.json
module-graph.json
technology-fingerprint.json
dependency-inventory.json
test-inventory.json
risk-findings.json

## 验收标准

- 同名Artifact按完整坐标区分；
- Profile和多模块关系可见；
- Unknown不自动视为安全；
- Finding可回溯文件或构建Evidence；
- 评分公式版本化；
- 报告重复运行结果稳定；
- 报告包含人工待确认项。

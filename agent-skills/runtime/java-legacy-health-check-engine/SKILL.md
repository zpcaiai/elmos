---
name: java-legacy-health-check-engine
description: "扫描Java项目结构、构建、框架、依赖、测试和迁移风险并生成体检报告。"
---

# Discovery

Maven Modules
Gradle Projects
JDK
Spring
Spring Boot
Spring Cloud
Hibernate
Security
Testing
Database
Cache
Messaging
Servlet
Application Server

## Findings

UNSUPPORTED_JDK
UNSUPPORTED_SPRING
JAVAX_USAGE
DEPENDENCY_CONFLICT
CVE_CANDIDATE
CIRCULAR_MODULE
MISSING_TEST
BUILD_UNREPRODUCIBLE
PRIVATE_DEPENDENCY
DIRECT_DATABASE_RISK
TRANSACTION_RISK
CACHE_SERIALIZATION_RISK

## Scoring

Business Criticality不在源码中自动推断。

技术评分分维度：

Build
Dependency
Framework
Test
API
Data
Security
Operations

## 验收标准

- Maven多模块正确识别；
- Build Baseline独立保存；
- Finding带文件和Evidence；
- Unknown不自动低风险；
- 报告可重复；
- 评分公式版本化。

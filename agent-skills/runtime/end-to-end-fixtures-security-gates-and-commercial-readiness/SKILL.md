---
name: end-to-end-fixtures-security-gates-and-commercial-readiness
description: "建立真实Repository Fixture、攻击测试、可靠性演练、产品指标和设计伙伴上线Gate。"
---

# Repository Fixtures

## 必须覆盖

Boot 2.7 Maven单体
Boot 2.7 Maven多模块
Java 11企业私服项目
Baseline Broken项目
javax大量使用项目
Spring Security 5项目
Hibernate 5项目
测试覆盖较低项目
构建会修改源码项目
Submodule项目
LFS项目
Gradle候选项目

## 安全测试

Header伪造Tenant
JWT错误Issuer
JWT错误Audience
跨租户SQL
RLS Owner绕过
Runner Enrollment重放
Runner证书撤销
Sandbox目录逃逸
Symlink逃逸
Network Egress
Secret读取
Cache跨租户污染
Webhook重放
GitHub Token过期
PR Branch冲突

## 可靠性测试

Runner失联
Lease过期
旧Epoch回报
Temporal Worker崩溃
Workflow重复Start
Outbox延迟
Object Store成功DB失败
DB成功Event失败
GitHub API超时
PR可能已创建
Async Activity重复完成
Agent Provider失败
Cancel执行中任务
Unknown Result Reconciliation

## 迁移质量指标

Snapshot Success Rate
Baseline Reproducibility
Environment Classification Accuracy
OpenRewrite Idempotency Rate
Deterministic Compile Improvement
Test Preservation Rate
API Regression Count
Agent Repair Rate by Error Class
Unsafe Patch Rejection Rate
PR Review Acceptance Rate
Evidence Completeness
Time to Reviewable PR
Cost per Repository
Source Egress Bytes

## Pilot Gate

至少三个设计伙伴Repository：

1. Maven单体；
2. Maven多模块；
3. 带企业私服的Java 11项目。

每个项目必须满足：

- 源码默认不离开Runner；
- Baseline结果可解释；
- OpenRewrite可重复；
- 测试数量不缩水；
- Agent严格受限；
- PR可Review；
- Evidence完整；
- 失败可恢复；
- 无跨租户访问。

## Commercial Readiness

支持：

单Repository体检
带PR深度迁移
Private Runner
Private Deployment候选
执行Credits候选
Evidence Export
Support Runbook
Incident Process
Customer Retention Policy

## 验收标准

- 全链路E2E自动化测试；
- 安全测试进入Release Gate；
- DR和恢复演练有Evidence；
- 三类真实项目重复通过；
- 所有失败均有明确分类；
- 产品指标按版本保存；
- 没有P0安全缺口时才允许付费Pilot。

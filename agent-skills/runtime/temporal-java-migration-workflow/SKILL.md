---
name: temporal-java-migration-workflow
description: "实现Java迁移的持久化Workflow、Activity、Signal、重试、人工Gate和版本策略。"
---

# Workflows

JavaMigrationWorkflow
AssessmentChildWorkflow
RewriteChildWorkflow
VerificationChildWorkflow
DeliveryChildWorkflow

## Signals

approvePlan
rejectPlan
approveDelivery
cancelProject
changeBudget
provideCredential

## Queries

currentStage
currentRisk
currentBudget
latestEvidence
waitingDecision

## Retry

Snapshot：
有限重试

Build：
根据错误分类

Agent：
严格预算

PR：
幂等重试

## 验收标准

- Worker崩溃后Workflow恢复；
- 人工等待不占线程；
- Workflow代码确定性；
- Activity使用幂等Key；
- 运行版本固定；
- 取消可安全传播。

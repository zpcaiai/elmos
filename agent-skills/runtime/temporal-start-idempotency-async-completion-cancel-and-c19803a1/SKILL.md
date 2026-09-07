---
name: temporal-start-idempotency-async-completion-cancel-and-c19803a1
description: "修复Workflow启动双写、数据库轮询、业务异常、取消传播和Worker升级问题。"
---

# Workflow ID

确定性：

java-migration:{tenantId}:{projectId}

同一Project只能存在一个活动主Workflow。

## Start流程

推荐：

Project Transaction
→ workflow_start_requested
→ Outbox
→ Workflow Starter
→ Start with Deterministic ID
→ Persist Workflow Execution

处理：

WorkflowExecutionAlreadyStarted
→ 查询现有Execution
→ 幂等返回

禁止：

先启动Workflow
后无保护写数据库

## Async Runner Activity

Activity：

1. 创建Runner Task；
2. 获取Temporal Task Token；
3. 调用doNotCompleteOnReturn；
4. 保存Task Token的加密引用；
5. Activity方法返回但不完成。

Runner完成后：

Control API
→ ActivityCompletionClient.complete

Runner失败：

→ completeExceptionally

这样不需要每秒轮询数据库。

## Business Failure

业务失败使用：

ApplicationFailure
NonRetryable Failure
或
明确Workflow状态

禁止直接抛普通IllegalStateException导致Workflow Task无限重试。

## Cancel

Cancel Signal
→ CancellationScope.cancel
→ Activity Cancellation Request
→ Runner Task CANCEL_REQUESTED
→ Sandbox Process Tree Stop
→ Partial Evidence
→ Workflow CANCELLED

每个关键Step前后检查取消状态。

## Activity Cancellation Type

高成本Runner Task：

WAIT_CANCELLATION_COMPLETED

短查询：

TRY_CANCEL候选

## Versioning

固定：

Workflow Definition Version
Worker Build ID
Activity Contract Version
Task Contract Version
Recipe Catalog Version

使用：

Worker Versioning
Patching
显式Workflow Migration

运行中不得静默改变旧History的解释。

## Signals

approvePlan(planHash)
rejectPlan(planHash, reason)
approveDelivery(evidenceHash)
cancel(reason)
provideCredential(reference)

## 验收标准

- 并发Start只产生一个Workflow；
- 数据库失败不会产生不可见孤儿Workflow；
- Runner完成可异步完成Activity；
- Workflow不再每秒轮询数据库；
- 业务失败正常进入FAILED；
- Cancel可终止Runner任务；
- 旧Workflow在新Worker发布后可继续Replay；
- Worker崩溃恢复测试通过。

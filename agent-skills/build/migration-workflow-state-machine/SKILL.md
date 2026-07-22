---
name: migration-workflow-state-machine
description: Implement or review ELMOS durable MigrationRun and StepRun states, optimistic transitions, idempotency, retries, cancellation, compensation, approval gates, Outbox events, and recovery. Use for workflow orchestration, failure recovery, human intervention, or Spring AI Alibaba graph integration.
---

# Migration Workflow State Machine

## 真实状态

Persist workflow truth in PostgreSQL or an approved durable workflow engine. Never keep the only copy in LLM context, a Spring AI graph, Agent session, WebSocket, thread, or JVM memory.

Use the documented main states from CREATED through DELIVERED and explicit terminal states such as BASELINE_BROKEN, VALIDATION_FAILED, POLICY_BLOCKED, BUDGET_EXCEEDED, CANCELLED, and FAILED. Use Step states PENDING, READY, RUNNING, SUCCEEDED, retry/final failure, approval, skipped, and cancelled.

## 转换协议

For every transition:

1. Load current state and version.
2. Check tenant, plan version, approval, budget, and evidence preconditions.
3. Compare-and-set with an optimistic version inside one transaction.
4. Append the audit and Outbox event.
5. Commit before dispatching the next action.
6. Deduplicate the asynchronous command by idempotency key.

Retry only transient network, rate-limit, sandbox-start, worker, and artifact-store failures automatically. Route compile, test, Recipe, API, policy, or budget failures through classification or human review.

## 智能子图边界

Allow Spring AI Alibaba graphs for analysis, diagnosis, routing, bounded repair, and explanation. Set maximum loops, token budget, tool allowlist, and structured output. Validate their output in application code; never let a graph write a final state.

## 验收与证据

Test restart recovery, duplicate messages, cancellation, illegal transitions, optimistic conflicts, successful non-reexecution, and approval bypass attempts. Record before/after state, version, event ID, actor, policy decision, and compensation result. Never delete audit history during compensation.


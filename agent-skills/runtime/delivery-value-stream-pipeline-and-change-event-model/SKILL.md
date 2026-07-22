---
name: delivery-value-stream-pipeline-and-change-event-model
description: 从需求、Commit、Review、Build、Test、Release、Deploy和Incident建立统一交付价值流及Pipeline IR。
---

# Delivery Value Stream

## Value Stream阶段

IDEA
PLANNED
IN_PROGRESS
COMMITTED
REVIEWED
MERGED
BUILT
TESTED
PACKAGED
RELEASED
DEPLOYED
VERIFIED
OPERATING
RECOVERED

## 活动类型

WORK
WAIT
APPROVAL
HANDOFF
REWORK
AUTOMATION
FAILURE
RECOVERY

## 等待

记录：

- Review等待；
- Runner等待；
- Environment等待；
- Security等待；
- Approval等待；
- Change Window等待；
- Data等待；
- Vendor等待。

## Pipeline IR

TRIGGER
CHECKOUT
DEPENDENCY_RESTORE
COMPILE
TEST
SECURITY
PACKAGE
SIGN
PUBLISH
DEPLOY
VERIFY
PROMOTE
ROLLBACK
NOTIFY

## Delivery事件

ELMOS可以使用CDEvents作为可选的跨工具交付事件Provider。CDEvents当前文档规范版本为0.5.0，并基于CloudEvents描述SCM、CI、Test、CD和Operations事件。核心领域仍需保留版本适配，因为该规范仍在持续演进。

## Event Identity

pipelineRunId
taskRunId
changeId
repository
commit
artifact
environment
deployment
incident

## Bottleneck

分类：

QUEUE
MANUAL_APPROVAL
UNRELIABLE_PIPELINE
SLOW_TEST
ENVIRONMENT
DEPENDENCY
REVIEW
LARGE_BATCH
REWORK
UNKNOWN

## 输出

delivery-value-stream.json
pipeline-ir.json
delivery-events.jsonl
delivery-wait-analysis.json
delivery-bottlenecks.json
recovery-value-stream.json

## 验收标准

- 工作时间和等待时间分开；
- Build和Deploy分开；
- 普通交付与恢复价值流分开；
- Event可跨Provider归一化；
- Bottleneck有Evidence；
- 指标绑定具体Service。

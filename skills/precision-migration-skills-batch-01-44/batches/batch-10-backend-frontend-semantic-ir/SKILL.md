---
name: batch-10-backend-frontend-semantic-ir
description: 把后端框架、领域服务和前端组件平台能力提升为可跨语言 Lowering、验证和生成的领域级语义。
---

# Batch 10：Backend与Frontend Semantic IR

## Goal

把后端框架、领域服务和前端组件平台能力提升为可跨语言 Lowering、验证和生成的领域级语义。

## Position in the system

- Phase: `C 精密语义表示`
- Included skills: `12`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 定义可观察边界
2. 将源语义归一化到受限模型
3. 保留不可丢失信息
4. 标记近似与不支持语义
5. 验证 Schema、一致性和可序列化性

## Shared gates

- 不得把 Null/Missing/Undefined 合并
- 不得隐式缩窄数值范围
- 所有副作用和状态转换必须可追踪

## Dispatch rules

- 当任务涉及 **backend-application-ir** 时，调用 `skills/backend-application-ir/SKILL.md`。
- 当任务涉及 **controller-endpoint-ir** 时，调用 `skills/controller-endpoint-ir/SKILL.md`。
- 当任务涉及 **domain-and-service-ir** 时，调用 `skills/domain-and-service-ir/SKILL.md`。
- 当任务涉及 **repository-and-orm-ir** 时，调用 `skills/repository-and-orm-ir/SKILL.md`。
- 当任务涉及 **dependency-injection-ir** 时，调用 `skills/dependency-injection-ir/SKILL.md`。
- 当任务涉及 **message-consumer-ir** 时，调用 `skills/message-consumer-ir/SKILL.md`。
- 当任务涉及 **scheduled-job-ir** 时，调用 `skills/scheduled-job-ir/SKILL.md`。
- 当任务涉及 **frontend-component-ir** 时，调用 `skills/frontend-component-ir/SKILL.md`。
- 当任务涉及 **ui-layout-constraint-ir** 时，调用 `skills/ui-layout-constraint-ir/SKILL.md`。
- 当任务涉及 **event-and-lifecycle-ir** 时，调用 `skills/event-and-lifecycle-ir/SKILL.md`。
- 当任务涉及 **route-navigation-ir** 时，调用 `skills/route-navigation-ir/SKILL.md`。
- 当任务涉及 **platform-capability-ir** 时，调用 `skills/platform-capability-ir/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `backend-application-ir` | 定义应用、模块、端口、服务、命令、查询、实体和部署边界。 |
| `controller-endpoint-ir` | 统一路由、参数、校验、鉴权、响应、错误、流式接口和协议契约。 |
| `domain-and-service-ir` | 表达领域规则、应用服务、领域服务、工作流、不变量和用例边界。 |
| `repository-and-orm-ir` | 表达实体、映射、查询、Tracking、Lazy load、事务、并发控制和迁移。 |
| `dependency-injection-ir` | 表达生命周期、Scope、绑定、工厂、拦截器、代理和条件注册。 |
| `message-consumer-ir` | 表达消费者、订阅、批量、顺序、重试、幂等、ACK 和死信行为。 |
| `scheduled-job-ir` | 表达调度、并发策略、补偿、重跑、锁和失败恢复。 |
| `frontend-component-ir` | 表达组件输入、输出、状态、派生状态、子内容、事件和渲染语义。 |
| `ui-layout-constraint-ir` | 表达约束布局、Flex/Grid、尺寸、间距、滚动、响应式和主题。 |
| `event-and-lifecycle-ir` | 表达挂载、更新、销毁、Effect、订阅、焦点、键盘和前后台生命周期。 |
| `route-navigation-ir` | 表达路由、参数、守卫、返回栈、深链接、Tab、恢复和导航结果。 |
| `platform-capability-ir` | 表达支付、分享、通知、相机、定位、蓝牙、文件、设备和权限能力。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。

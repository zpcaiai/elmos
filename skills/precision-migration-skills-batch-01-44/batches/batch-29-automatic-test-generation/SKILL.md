---
name: batch-29-automatic-test-generation
description: 从接口、源码、数据、状态、副作用、生产Trace和形式契约生成可跨源目标执行的测试。
---

# Batch 29：根据源系统自动生成测试

## Goal

从接口、源码、数据、状态、副作用、生产Trace和形式契约生成可跨源目标执行的测试。

## Position in the system

- Phase: `H 测试、验证与自动修复`
- Included skills: `14`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 评估或生成测试
2. 同步环境并双运行
3. 比较输出、状态和副作用
4. 搜索最小反例
5. 驱动修复并执行全量回归

## Shared gates

- 未解释差异必须阻断
- 测试弱化和删除必须阻断
- 关键不变量、权限和不可逆副作用必须100%通过

## Dispatch rules

- 当任务涉及 **openapi-contract-test-generator** 时，调用 `skills/openapi-contract-test-generator/SKILL.md`。
- 当任务涉及 **controller-route-test-generator** 时，调用 `skills/controller-route-test-generator/SKILL.md`。
- 当任务涉及 **graphql-test-generator** 时，调用 `skills/graphql-test-generator/SKILL.md`。
- 当任务涉及 **protobuf-api-test-generator** 时，调用 `skills/protobuf-api-test-generator/SKILL.md`。
- 当任务涉及 **dto-validation-test-generator** 时，调用 `skills/dto-validation-test-generator/SKILL.md`。
- 当任务涉及 **database-state-test-generator** 时，调用 `skills/database-state-test-generator/SKILL.md`。
- 当任务涉及 **side-effect-test-generator** 时，调用 `skills/side-effect-test-generator/SKILL.md`。
- 当任务涉及 **business-invariant-test-generator** 时，调用 `skills/business-invariant-test-generator/SKILL.md`。
- 当任务涉及 **user-journey-test-generator** 时，调用 `skills/user-journey-test-generator/SKILL.md`。
- 当任务涉及 **production-trace-test-generator** 时，调用 `skills/production-trace-test-generator/SKILL.md`。
- 当任务涉及 **property-test-generator** 时，调用 `skills/property-test-generator/SKILL.md`。
- 当任务涉及 **fuzz-test-generator** 时，调用 `skills/fuzz-test-generator/SKILL.md`。
- 当任务涉及 **mutation-test-generator** 时，调用 `skills/mutation-test-generator/SKILL.md`。
- 当任务涉及 **concurrency-test-generator** 时，调用 `skills/concurrency-test-generator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `openapi-contract-test-generator` | 从 OpenAPI 生成正常、边界、错误、权限和兼容性契约测试。 |
| `controller-route-test-generator` | 从 Controller、Route、Middleware 和校验注解生成接口测试。 |
| `graphql-test-generator` | 从 GraphQL Schema、Resolver、Directive 和错误契约生成测试。 |
| `protobuf-api-test-generator` | 从 Protobuf/gRPC Schema、Field rule 和流式接口生成测试。 |
| `dto-validation-test-generator` | 从 DTO、Schema、精化类型和校验规则生成边界与拒绝测试。 |
| `database-state-test-generator` | 生成初始状态、写入、约束、回滚、触发器和最终状态验证。 |
| `side-effect-test-generator` | 生成消息、外部调用、文件、缓存、审计和调用次数/顺序验证。 |
| `business-invariant-test-generator` | 从金额、库存、权限、状态、幂等和守恒规则生成属性测试。 |
| `user-journey-test-generator` | 从页面、路由、事件和 API 生成端到端用户 Journey。 |
| `production-trace-test-generator` | 将脱敏生产 Trace 转换为可复现、参数化和可审计测试。 |
| `property-test-generator` | 为跨语言契约生成 Property-based 测试与数据生成器。 |
| `fuzz-test-generator` | 为 Parser、协议、接口、序列化和动态输入生成 Fuzz Harness。 |
| `mutation-test-generator` | 生成通用和语言对专项 Mutant，验证测试的错误发现能力。 |
| `concurrency-test-generator` | 从锁、事务、消息、幂等和异步流程生成并发交错场景。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。

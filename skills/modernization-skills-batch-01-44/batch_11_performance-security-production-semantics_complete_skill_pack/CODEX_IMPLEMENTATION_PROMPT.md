# Codex Implementation Prompt — Batch 11

你正在目标仓库中实现 **Batch 11: Performance, Security and Production Semantics Validation**。

## Mission

验证并发、事务、锁、精度、时区、序列化、身份权限、加密、性能、资源生命周期和生产配置语义，阻止只通过功能测试的错误迁移。

## Read First

1. `SKILL.md`
2. `SKILL_INDEX.md`
3. `BATCH10_COMPATIBILITY.md`
4. `IMPLEMENTATION_CHECKLIST.md`
5. `schemas/`、`policies/` 和 `tests/`

## Required Capability Areas

- Concurrency 与 Scheduling
- Transaction/Isolation/Lock
- Numeric Precision/Overflow
- Time/Timezone/Locale
- Serialization Compatibility
- Authentication
- Authorization/Tenant Isolation
- Cryptography/Secret Handling
- Performance Regression
- Memory/FD/Connection Leak
- Production Configuration
- Capacity 与 SLO

## Implementation Order

1. 检查现有仓库架构、依赖、Schema、Workflow、Evidence 和认证边界；禁止创建平行平台。
2. 先实现版本化 Schema、Migration、Domain Model 和 Conservative Gate。
3. 实现 Orchestrator、Durable Workflow、Idempotency、Lease、Checkpoint 和 Side-effect Ledger。
4. 实现确定性核心，再接入签名、最小权限的 Adapter/Provider。
5. 实现 Evidence、Reconciliation、Human Approval、Metrics 和 Lifecycle。
6. 建设正例、负例、边界、恶意、Holdout 与 Representative Corpus。
7. 运行仓库原生 lint、typecheck、unit、integration、e2e、security、performance 与 recovery tests。
8. 生成真实 Validation Report；未执行项不得写为通过。

## Non-Negotiable Rules

- 不得用自由文本 LLM 输出替代结构化、确定性和可验证核心。
- 不得删除测试、Assertion、失败样本、Golden 或未知项来提高指标。
- 不得允许 Agent 直接 Commit、Publish、Approve 或修改 Gate。
- 不得使用未锁定版本、`latest`、未签名插件或宽泛网络权限进入认证。
- 不得把 Mock、Dry Run、静态文档或状态字段当作生产执行证据。
- 不可逆动作必须经人工批准并具有已验证的回退/补偿。

## Completion Output

返回：架构决策、文件变更、Schema/Migration、API、测试命令和真实结果、证据摘要、指标分母、失败与回滚、已知限制、未完成能力、下一 Batch 兼容输出。

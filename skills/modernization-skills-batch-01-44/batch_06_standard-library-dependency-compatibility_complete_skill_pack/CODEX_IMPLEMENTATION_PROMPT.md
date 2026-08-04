# Codex Implementation Prompt — Batch 06

你正在目标仓库中实现 **Batch 06: Standard Library, Dependency Mapping and Compatibility Runtime**。

## Mission

建立跨 Java、.NET、Python、Node.js、C++、Go、Rust 与前端生态的标准库和第三方依赖映射，生成锁定依赖、兼容层、Wrapper、Sidecar 与保留原服务决策。

## Read First

1. `SKILL.md`
2. `SKILL_INDEX.md`
3. `BATCH05_COMPATIBILITY.md`
4. `IMPLEMENTATION_CHECKLIST.md`
5. `schemas/`、`policies/` 和 `tests/`

## Required Capability Areas

- Java SDK 与 .NET BCL 映射
- Python 标准库与 Java/.NET/Node 对应
- Maven/NuGet/PyPI/npm/Cargo/Go Modules 依赖映射
- 版本与运行时兼容矩阵
- 许可证、CVE 与供应链策略
- 依赖替代注册表
- Compatibility Shim 与 Wrapper
- Sidecar 与保留原服务
- Lockfile 与 SBOM
- 弃用与退出治理

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

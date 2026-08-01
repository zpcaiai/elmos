---
name: pm-b05-build-system-detector
description: "识别单仓或多仓构建系统、模块关系、版本约束、插件和构建入口. Precision Migration B05 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Build System Detector
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b05-build-system-detector`.
- Immutable source identity: `build-system-detector` in `precision-migration-b01-44` (B05).
- Runtime adapter: `semantic-recovery-and-ir`; binding state: `UNAVAILABLE`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b05-build-system-detector`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Metadata

- Batch: `05 - 仓库发现与语义资产恢复`
- Phase: `B 源码理解与可信执行底座`
- Version: `1.0.0`
- Tags: batch-05, repository-semantic-recovery

## Purpose

识别单仓或多仓构建系统、模块关系、版本约束、插件和构建入口。

本 Skill 属于精密语言转换系统。它必须以**可执行证据**为准，不得用模型自评、源码相似度或“能编译”替代语义与行为验证。

## Use when

- 当前任务直接涉及 `build-system-detector` 所描述的能力。
- 上游已经提供可识别的输入资产，或本 Skill 能通过已注册工具发现这些资产。
- 结果需要进入后续转换、验证、证明、发布或企业审计流程。

## Inputs

- 源仓库与构建文件
- 运行环境与依赖策略
- 安全/网络策略
- 测试和部署资产

所有输入都必须记录来源、版本、摘要和敏感级别。缺失关键输入时，输出 `CONDITIONALLY_VERIFIED`、`REQUIRES_HUMAN_REVIEW` 或 `UNSUPPORTED`，不得猜测为已满足。

## Outputs

- 主产物：`analysis-report.json 与 evidence-index.json`
- 状态：仅允许 `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`
- 证据：输入摘要、规则/模型/工具版本、诊断、测试、差异、审批与未解决项

## Workflow

1. 发现仓库与环境
2. 执行本 Skill 的核心职责：识别单仓或多仓构建系统、模块关系、版本约束、插件和构建入口。
3. 使用原生工具提取语义
4. 建立可复现工具链和沙箱
5. 执行最小验证任务
6. 持久化摘要、哈希和证据

## Validation gates

- 不执行未隔离的客户或AI代码
- 工具链版本与镜像必须锁定
- 未能解析的动态语义必须显式标记

此外必须满足：

- 未解释差异数为 `0` 才能输出 `VERIFIED`。
- `PROVED` 只允许由可信内核、求解器或已批准的机器证明证书产生。
- 任何测试删除、断言弱化、容差放大、Mock替代真实实现都必须单独审计。
- 所有不支持或未建模语义写入 `semantic-loss-ledger`。

## Recommended tools

- 原生编译器 API
- OCI/VM/macOS Worker
- 依赖代理
- Trace/静态分析

工具只负责产生事实或候选；最终状态由发布门禁和证据规则决定。

## Evidence artifacts

```yaml
skill: build-system-detector
version: 1.0.0
status: VERIFIED | PROVED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED
inputs:
  - uri: string
    digest: sha256:string
toolchain:
  versions: {}
models:
  - provider: string
    model: string
    role: candidate | reviewer | proof_assistant
findings: []
changes: []
tests: []
proofs: []
unresolved: []
approvals: []
```

## Failure codes

- `INVALID_INPUT`
- `MISSING_EVIDENCE`
- `UNSUPPORTED_SEMANTICS`
- `VALIDATION_FAILED`

每个失败必须带：失败阶段、最小复现、影响范围、疑似语义切片、可自动重试性和升级建议。

## Escalation policy

1. 首次失败：使用结构化诊断执行定点修复，不扩大修改范围。
2. 同类失败重复：查询反例库和Direction Pack，必要时生成新规则候选。
3. 超过预算或轮次：升级更强模型、重新生成模块、保留兼容层或要求人工。
4. 高风险权限、金额、事务、不可逆副作用和生产切流：必须人工批准。

## Definition of done

- 主产物已生成且 Schema 校验通过。
- 所有适用门禁通过，或未通过项已明确阻断并进入未解决清单。
- 证据可追踪到输入、规则、模型、工具链、测试、证明和审批。
- 结果可被下游 Skill 无歧义消费。

## Example invocation

```yaml
skill: build-system-detector
mode: assess | transform | validate | repair | certify
inputs:
  source_repository: repo://source
  target_repository: repo://target
  target_stack: optional
policy:
  unresolved_differences: block
  allow_test_weakening: false
  require_provenance: true
```

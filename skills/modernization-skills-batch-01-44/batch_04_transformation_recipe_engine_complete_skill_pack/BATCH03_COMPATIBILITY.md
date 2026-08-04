# BATCH03_COMPATIBILITY

本文件定义 `batch-03` → `batch-04` 的输入、证书、Schema、版本、失效与回退协议。

## 上游输入

- `IRCertificate`
- `IRBundleManifest`
- `CSIR`
- `SymbolIndex`
- `TypeIndex`
- `CFG`
- `Dataflow`
- `Callgraph`
- `EffectModel`
- `DomainIR`
- `SourceMap`
- `ProofObligations`

## 本 Batch 输出

- `SemanticMappingRegistry`
- `DirectionalRoutePack`
- `CompiledRuleIR`
- `TransformationPlan`
- `PatchIntentSet`
- `TransformationJournal`
- `SourceTargetMap`
- `VerificationEvidence`
- `SignedPatchBundle`
- `TransformationRunCertificate`

## 兼容性规则

- 每条规则必须声明最低 IR Level、Required Analysis 和 Forbidden Unknown。
- Batch 3 Compiler Fact 不得被 Rule 或 Agent 覆盖。
- Extension Capsule、Opaque 和 Unsupported 状态必须参与 Guard。
- 所有 Patch 必须保持 Batch 3 Source Map 和 Provenance 链。

## 版本策略

```yaml
versioning:
  schema:
    patch: 文档或约束澄清，不改变语义
    minor: 向后兼容新增字段或能力
    major: 语义、状态机或可信边界发生不兼容变化
  certificates:
    bind:
      - input-digests
      - schema-versions
      - policy-versions
      - tool-or-rule-versions
      - tenant-and-scope
  unknown-fields:
    preserve: true
  silent-downgrade:
    allowed: false
```

## 失效条件

- Source Snapshot、IR Bundle、Route Pack、Recipe Package 或 Toolchain 变化。
- CSIR/DSL/Mapping Schema major 变化。
- 分析结果被 Patch 失效但未重算。
- Recipe Critical Defect、Package Revocation 或 Verification Policy 变化。

## 回退与降级

- IR 能力不足时跳过并生成 Evidence Gap，而不是猜测。
- 原生 Adapter 失败时保留确定性 CSIR 规则结果或回滚。
- Agent 未通过验证时回滚，不自动扩大范围。
- 冲突无法安全消解时停止并请求人工决策。

## 下游消费要求

- Batch 5 必须消费 Directional Route Pack、Transformed CSIR、Target Construction Intent、Semantic Gap、Shim、Source-target Map 和 Run Certificate。
- 测试和差分 Batch 必须消费 Verification Obligation、Effect/Contract 变化和 Agent Change Register。
- 形式验证必须消费 Rule Preconditions、Postconditions、Semantic Relation 和 Proof Obligation Template。
- 生产治理必须验证 Signed Patch Bundle、Journal 和 Rollback Evidence。

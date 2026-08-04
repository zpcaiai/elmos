# BATCH02_COMPATIBILITY

本文件定义 `batch-02` → `batch-03` 的输入、证书、Schema、版本、失效与回退协议。

## 上游输入

- `AssessmentCertificate`
- `AssessmentSnapshot`
- `CanonicalWorkloadInventory`
- `SourceBinaryMapping`
- `BuildRootMap`
- `ArchitectureGraph`
- `RuntimeBaseline`
- `DatabaseMetadata`

## 本 Batch 输出

- `IRBundleManifest`
- `NativeLosslessIR`
- `CanonicalSemanticIR`
- `AnalysisGraphIR`
- `BuildIR`
- `ConfigIR`
- `ApiIR`
- `SqlIR`
- `BinaryIR`
- `FormalCoreIR`
- `IRCertificate`

## 兼容性规则

- IR Bundle 必须绑定 Batch 2 Snapshot Merkle Root。
- Batch 2 中的 Source/Binary/Runtime 身份必须保留映射。
- 访问、反编译和 Sandbox 权限不得在 Batch 3 扩大。
- Batch 2 EvidenceRef 应转化为 IR Provenance，而不丢失来源。

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

- Source Artifact、Binary Artifact、Build Context 或 Snapshot 变化。
- Frontend、Compiler、Parser、Schema 或 Policy major 变化。
- Generated Source 输入或 Generator 版本变化。
- 发现影响语义正确性的 Frontend Critical Defect。

## 回退与降级

- Compiler-backed Frontend 失败时降级到 Lossless 或 Syntax 层，并降低语义等级。
- 不支持语言至少保留 Raw Artifact、Metadata 和 Opaque Region。
- Build Context 不完整时保留部分符号与诊断，不伪造类型。
- 形式化不支持区域输出边界假设而非删除。

## 下游消费要求

- Batch 4 必须声明最低 IR Level、Required Analysis 和 Forbidden Unknown。
- 目标代码生成必须消费 CSIR、Type、Effect、Source Map 和 Extension Capsule。
- 数据库转换必须消费 SqlIR、Transaction Effect 和 Dynamic Hole。
- 形式验证必须消费 Formal Core、Assumption 和 Proof Obligation。

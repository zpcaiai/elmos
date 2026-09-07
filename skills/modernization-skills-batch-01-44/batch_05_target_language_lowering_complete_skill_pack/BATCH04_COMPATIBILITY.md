# Batch 4 → Batch 5 Compatibility Contract

## 1. 目的

Batch 5 不读取未经治理的源代码文本后自由生成目标项目。它必须消费 Batch 4 已认证的语义转换结果。本文件定义 Batch 4 输出与 Batch 5 输入之间的兼容、版本、失效和降级规则。

## 2. 必需输入

| Batch 4 Artifact | Batch 5 Usage | Required |
|---|---|---:|
| `TransformationRunCertificate` | 证明转换运行、Recipe、Route 与验证状态 | 是 |
| `TransformedCSIRBundle` | TTIR Lowering 的语义输入 | 是 |
| `TargetConstructionIntentSet` | 目标框架、类型、项目和 Shim 构造意图 | 是 |
| `DirectionalRoutePack` | 源目标版本与映射边界 | 是 |
| `SemanticGapRegister` | 决定阻断、Shim、Agent 或人工处理 | 是 |
| `RequiredShimRegister` | 生成兼容层和退出条件 | 条件必需 |
| `SourceTargetMap` | 贯通 Batch 3、4、5 的来源映射 | 是 |
| `VerificationObligationSet` | 生成后必须执行的验证 | 是 |
| `AgentAssistedChangeRegister` | 披露 Batch 4 中非确定性修改 | 条件必需 |

## 3. 版本兼容性

```yaml
compatibility:
  transformation_rule_dsl:
    supported: ">=1.0.0 <2.0.0"
  transformed_csir:
    supported: ">=1.0.0 <2.0.0"
  target_construction_intent:
    supported: ">=1.0.0 <2.0.0"
  source_target_map:
    supported: ">=1.0.0 <2.0.0"
  verification_obligation:
    supported: ">=1.0.0 <2.0.0"
```

Minor 版本新增可选字段时允许兼容读取，但必须保留未知字段。Major 版本变化必须执行显式迁移或重新运行 Batch 4。

## 4. 证书要求

Batch 5 最低要求：

```text
Transformation Run Certificate 有效；
Snapshot、IR Bundle、Route Pack 和 Recipe Digest 与输入一致；
不存在未披露 Blocking Verification Failure；
Agent-assisted 变化已完整登记；
Transformation Certificate 未过期、未撤销、未因缺陷失效。
```

若 Batch 4 只达到较低 Correctness Class，Batch 5 可以继续生成候选工程，但 Generation Certificate 必须继承限制，不得升级为更高语义保证。

## 5. Semantic Gap 处理矩阵

| Gap State | Batch 5 Default |
|---|---|
| `resolved-deterministically` | 正常 Lowering |
| `wrapper-required` | 生成受治理 Shim，并记录退出条件 |
| `manual-decision-required` | 暂停受影响 Scope，等待批准 |
| `agent-repair-eligible` | 先完成确定性生成，再进入受限 Agent |
| `lossy` | 阻断 G4 以上认证，除非明确批准和补充验证 |
| `unsupported` | 默认阻断受影响单元生成 |
| `unknown` | 不得猜测；按风险阻断或生成显式占位与人工任务 |

## 6. Source-target Map 连续性

Batch 5 必须保留以下链路：

```text
Batch 3 Source Node
→ Batch 4 Transformed CSIR Node
→ Batch 4 Target Construction Intent
→ Batch 5 TTIR Node
→ Target Native AST/LST Node
→ Target File Span
→ Target Binary Symbol（可用时）
```

任何链路断点都必须进入 `unmapped-target-register.json`。

## 7. 失效条件

发生以下任一情况时，Batch 5 计划或证书必须失效：

- Source Snapshot 或 IR Bundle Digest 改变；
- Batch 4 Route Pack、Recipe Package 或 Transformation Certificate 改变；
- Transformed CSIR Schema major 版本变化；
- Target Construction Intent 被人工修改但未重新签名；
- 新发现严重 Transformation Rule 缺陷；
- Agent-assisted Change 未披露；
- Blocking Verification Obligation 状态改变。

## 8. 不允许的绕过

- 直接把 Batch 3 原始 CSIR 交给 Batch 5，跳过 Batch 4；
- 只提供源码文本，让模型自行推断目标 Route；
- 删除 Semantic Gap 以提高自动化率；
- 将 Batch 4 编译通过当作 Batch 5 目标工程已正确；
- 用新的 Target Profile 覆盖旧 Route Pack 而不做兼容检查。

## 9. Compatibility Gate

```yaml
batch04_compatibility_gate:
  certificate_valid: true
  snapshot_digest_match: true
  ir_bundle_digest_match: true
  route_pack_digest_match: true
  transformed_csir_schema_supported: true
  target_intent_schema_supported: true
  semantic_gaps_present: true
  source_target_map_present: true
  blocking_failures_disclosed: true
  agent_changes_disclosed: true
```

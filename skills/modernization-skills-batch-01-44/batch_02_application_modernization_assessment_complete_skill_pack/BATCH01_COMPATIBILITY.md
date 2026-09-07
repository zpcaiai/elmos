# BATCH01_COMPATIBILITY

本文件定义 `batch-01` → `batch-02` 的输入、证书、Schema、版本、失效与回退协议。

## 上游输入

- `ProductPositioningDecision`
- `ProductBoundary`
- `TargetCustomerProfile`
- `CapabilityTaxonomy`
- `DirectionalRoutePolicy`
- `ReferenceRouteDecision`
- `TrustLevelModel`

## 本 Batch 输出

- `AssessmentSnapshot`
- `CanonicalWorkloadInventory`
- `ArchitectureGraph`
- `DependencyGraph`
- `DataflowGraph`
- `MigrationCandidateSet`
- `PredictionEstimateSet`
- `PortfolioWavePlan`
- `AssessmentCertificate`

## 兼容性规则

- Batch 2 评估范围不得超出 Batch 1 Product Boundary 而不记录战略变更。
- Route Candidate 必须使用 Batch 1 Directional Route ID 和版本约束。
- 评估可信等级必须继承 Batch 1 Trust Level，不重新定义正确性概念。
- 首期优先实现 Batch 1 批准的 Reference Route。

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

- Source Commit、Artifact Digest 或 Deployment Topology 发生实质变化。
- Batch 1 Product Boundary、Route Registry 或 Trust Policy major 变化。
- 评估工具链、规则包、目标平台假设或证据新鲜度失效。
- 出现新的 Critical Security Finding。

## 回退与降级

- 访问不足时生成 Partial Assessment，而非补猜。
- 无运行数据时降级为静态证书等级。
- 无匹配预测 Cohort 时扩大区间并标记 uncalibrated。
- Probe 不安全时停止执行并保留静态结论。

## 下游消费要求

- Batch 3 必须消费锁定 Snapshot、Workload Inventory、Build Context、Source/Binary Mapping 和 Assessment Certificate。
- 转换 Batch 必须消费候选路线、Hard Blocker、验证要求和预测假设。
- 数据库 Batch 必须消费数据库对象、事务、共享状态和 Dynamic SQL 分析。
- 差分与 Dual Run Batch 必须消费源基线、Observable Surface 和 Side-effect Register。

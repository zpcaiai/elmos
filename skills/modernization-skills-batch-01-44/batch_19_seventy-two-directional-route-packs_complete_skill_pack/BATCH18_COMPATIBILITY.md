# BATCH18_COMPATIBILITY

本文件定义 Batch 18 → Batch 19（72 Directional Executable Generator Packs）的输入、输出、版本、证书、失效与回退协议。

## Inherited Foundation

Batch 19 必须继承 Batch 01–05：产品边界、评估快照、Canonical Semantic IR、Transformation Rule/Recipe、Target Project/Codegen、Source-target Provenance、Unknown Preservation 和 Conservative Certification。

## Upstream Inputs

- `CapabilityPackage` 与依赖解析结果
- 上游 `Certificate`、`EvidenceRefs` 和 `KnownLimitations`
- 精确 Snapshot、Artifact、Tool/Provider/Policy 版本与 Digest
- Workflow Checkpoint、Approval、Budget 和 Side-effect Receipts

## This Batch Outputs

- 9 Core Source Frontends
- 9 Core Target Backends
- 72 Directed Route Manifests
- Vue/React/Flutter Framework Combinations
- Path-specific Lowering
- Dependency Mapping
- Complete Project Generation
- Golden Corpus
- Hidden/Holdout Corpus
- Adversarial Corpus
- Correctness/Performance Benchmark
- GP1–GP5
- `Batch19EvidencePack`
- `Batch19Certificate`
- `DownstreamCompatibilityManifest`

## Versioning

- Patch：澄清和向后兼容修复。
- Minor：新增可选字段、能力或 Adapter，旧消费者可忽略并保留未知字段。
- Major：语义、状态、权限、证据或可信边界变化；下游证书必须失效并重新认证。
- 所有证书绑定输入、Schema、Policy、Tool、Provider、Artifact 和 Corpus Digest。

## Invalidation

- 上游 Snapshot/Artifact/Route/Profile/Schema Major 改变。
- Tool、Model、Provider、Rule、Dependency 或 Policy 发生影响语义的变化。
- Evidence 过期、撤销、矛盾或发现 Critical Security/Correctness Finding。
- Scope、Tenant、Owner、数据分类、目标环境或批准发生变化。

## Degradation and Recovery

- 缺失运行证据时降级为 static/experimental，不补猜。
- Provider 不可用时使用已认证替代项或停止，不静默切换。
- 失败时回滚到内容寻址 Savepoint，并重新对账副作用。
- 无法安全回滚时进入 Manual Recovery，禁止自动重试不可逆操作。

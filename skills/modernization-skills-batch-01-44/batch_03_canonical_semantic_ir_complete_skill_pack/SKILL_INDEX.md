# Batch-03 Skill Index

本索引包含 **24 个独立 Skills**。

## 依赖主线

```text
Raw Artifacts
→ Language and Build Context
→ Frontend SDK
→ Native Lossless IR
→ Native Semantics
→ CSIR
→ Symbols / Types / CFG / Dataflow / Callgraph / Effects
→ Domain IR
→ Provenance / Formal Core
→ Incremental Store
→ IR Certificate
```

## 01. `b03-ir-foundation-orchestrator`

- 文件：`skills/01-ir-foundation-orchestrator/SKILL.md`
- 层：`orchestrator`
- 风险：`critical`
- 目标：为 Assessment Snapshot 生成唯一、可复现、可恢复的联邦式 IR Bundle。
- 主要输出：`ir-build-plan.json`, `ir-bundle-manifest.json`, `ir-quality-report.json`, `ir-certificate.json`

## 02. `b03-source-artifact-normalizer`

- 文件：`skills/02-source-artifact-normalizer/SKILL.md`
- 层：`source-intake`
- 风险：`critical`
- 目标：建立内容寻址 Raw Artifact Layer，确保后续任何解析都可回到原始字节。
- 主要输出：`source-artifact-manifest.json`, `source-blob-index.json`, `encoding-report.json`, `unsafe-artifact-register.json`

## 03. `b03-language-version-and-region-detector`

- 文件：`skills/03-language-version-and-region-detector/SKILL.md`
- 层：`frontend-routing`
- 风险：`high`
- 目标：为多语言、模板、嵌入 SQL 与 DSL 选择正确前端和版本上下文。
- 主要输出：`language-detection-report.json`, `language-region-map.json`, `dialect-candidates.json`

## 04. `b03-build-context-and-toolchain-resolver`

- 文件：`skills/04-build-context-and-toolchain-resolver/SKILL.md`
- 层：`build-semantics`
- 风险：`critical`
- 目标：让同一源码在不同 Profile、Target Framework、宏和依赖下拥有独立语义上下文。
- 主要输出：`build-context-graph.json`, `toolchain-lock.json`, `source-set-map.json`, `dynamic-build-unknowns.json`

## 05. `b03-frontend-adapter-sdk-and-registry`

- 文件：`skills/05-frontend-adapter-sdk-and-registry/SKILL.md`
- 层：`frontend-platform`
- 风险：`critical`
- 目标：统一 Compiler-backed、Lossless、Syntax 和 Token Fallback 前端，而不强制使用同一解析器。
- 主要输出：`frontend-capability-registry.json`, `frontend-sdk/`, `frontend-package-manifest.json`, `frontend-certificates.json`

## 06. `b03-native-lossless-syntax-ir-builder`

- 文件：`skills/06-native-lossless-syntax-ir-builder/SKILL.md`
- 层：`native-ir`
- 风险：`critical`
- 目标：提供文本与语言原生结构的保真层，支持无操作 Round Trip 和最小范围重写。
- 主要输出：`native-lossless-ir/`, `native-source-map.json`, `roundtrip-report.json`, `parse-diagnostics.json`

## 07. `b03-native-semantic-attribution-engine`

- 文件：`skills/07-native-semantic-attribution-engine/SKILL.md`
- 层：`native-semantics`
- 风险：`critical`
- 目标：形成 Compiler-confirmed 与 Partial Semantic Facts，防止模型猜测污染。
- 主要输出：`native-semantic-ir/`, `symbol-attribution.json`, `type-attribution.json`, `compiler-diagnostics.json`

## 08. `b03-canonical-semantic-ir-schema-and-lowering`

- 文件：`skills/08-canonical-semantic-ir-schema-and-lowering/SKILL.md`
- 层：`canonical-ir`
- 风险：`critical`
- 目标：用共同语义支持跨语言比较，同时通过 Extension Capsule 保留专有语义。
- 主要输出：`canonical-semantic-ir/`, `lowering-decisions.json`, `semantic-gap-register.json`, `extension-capsules/`

## 09. `b03-symbol-identity-scope-and-linker`

- 文件：`skills/09-symbol-identity-scope-and-linker/SKILL.md`
- 层：`semantic-linking`
- 风险：`critical`
- 目标：提供稳定 SymbolId、LogicalSymbolId 和模糊引用模型。
- 主要输出：`symbol-index/`, `scope-graph.json`, `reference-index.json`, `cross-snapshot-symbol-map.json`

## 10. `b03-canonical-type-system-and-language-relations`

- 文件：`skills/10-canonical-type-system-and-language-relations/SKILL.md`
- 层：`type-system`
- 风险：`critical`
- 目标：避免构建一个错误的全局 Subtype Lattice。
- 主要输出：`type-index/`, `language-type-relations.json`, `type-mapping-candidates.json`, `type-diagnostics.json`

## 11. `b03-expression-statement-and-evaluation-order-lowerer`

- 文件：`skills/11-expression-statement-and-evaluation-order-lowerer/SKILL.md`
- 层：`semantic-lowering`
- 风险：`critical`
- 目标：确保跨语言转换不会因参数、操作数、闭包或 Await 顺序差异改变行为。
- 主要输出：`canonical-expression-ir.json`, `canonical-statement-ir.json`, `evaluation-order-facts.json`, `desugaring-map.json`

## 12. `b03-control-flow-ssa-and-dataflow-builder`

- 文件：`skills/12-control-flow-ssa-and-dataflow-builder/SKILL.md`
- 层：`analysis-graph`
- 风险：`critical`
- 目标：为验证、优化、差分和形式化提供控制与数据语义。
- 主要输出：`cfg/`, `exception-cfg/`, `ssa/`, `dataflow/`, `function-summaries.json`

## 13. `b03-callgraph-dispatch-reflection-and-dynamic-linker`

- 文件：`skills/13-callgraph-dispatch-reflection-and-dynamic-linker/SKILL.md`
- 层：`call-analysis`
- 风险：`critical`
- 目标：建立 must、may、observed 和 unresolved 调用边。
- 主要输出：`callgraph/`, `dynamic-call-register.json`, `reflection-candidates.json`, `runtime-call-correlation.json`

## 14. `b03-effect-exception-concurrency-and-resource-modeler`

- 文件：`skills/14-effect-exception-concurrency-and-resource-modeler/SKILL.md`
- 层：`semantic-effects`
- 风险：`critical`
- 目标：提供 Must/May/Unknown Effect 与资源清理、并发同步语义。
- 主要输出：`effect-graph.json`, `exception-model.json`, `concurrency-model.json`, `resource-lifecycle-model.json`

## 15. `b03-build-config-and-resource-ir-builder`

- 文件：`skills/15-build-config-and-resource-ir-builder/SKILL.md`
- 层：`domain-ir`
- 风险：`high`
- 目标：让代码生成和框架迁移理解配置优先级、环境差异与资源所有权。
- 主要输出：`build-ir.json`, `config-ir.json`, `resource-ir.json`, `config-consumer-map.json`

## 16. `b03-api-message-and-contract-ir-builder`

- 文件：`skills/16-api-message-and-contract-ir-builder/SKILL.md`
- 层：`contract-ir`
- 风险：`critical`
- 目标：建立实现与正式契约的统一 ContractIR 和 Drift。
- 主要输出：`api-ir.json`, `message-contract-ir.json`, `contract-implementation-map.json`, `contract-drift-report.json`

## 17. `b03-sql-and-database-procedural-ir-builder`

- 文件：`skills/17-sql-and-database-procedural-ir-builder/SKILL.md`
- 层：`database-ir`
- 风险：`critical`
- 目标：保留 Oracle、SQL Server、MySQL、PostgreSQL 的查询、事务、Routine 和专有语义。
- 主要输出：`sql-ir/`, `database-object-link-map.json`, `sql-read-write-sets.json`, `dynamic-sql-holes.json`

## 18. `b03-binary-bytecode-and-native-metadata-ir`

- 文件：`skills/18-binary-bytecode-and-native-metadata-ir/SKILL.md`
- 层：`binary-ir`
- 风险：`critical`
- 目标：补足 Source Missing 和生产版本 Drift，同时保持授权与 Derived 标记。
- 主要输出：`binary-ir/`, `binary-source-map.json`, `source-binary-drift.json`, `opaque-binary-register.json`

## 19. `b03-generated-code-macro-and-metaprogramming-modeler`

- 文件：`skills/19-generated-code-macro-and-metaprogramming-modeler/SKILL.md`
- 层：`provenance`
- 风险：`critical`
- 目标：决定后续转换应修改输入模板、生成器还是生成输出。
- 主要输出：`generation-provenance-graph.json`, `macro-expansion-map.json`, `generated-source-register.json`, `metaprogramming-unknowns.json`

## 20. `b03-source-map-provenance-and-semantic-fingerprint`

- 文件：`skills/20-source-map-provenance-and-semantic-fingerprint/SKILL.md`
- 层：`traceability`
- 风险：`critical`
- 目标：提供一对多、多对一、Tombstone 和跨快照语义候选匹配。
- 主要输出：`source-map-graph.json`, `provenance-graph.json`, `semantic-fingerprint-index.json`, `tombstone-register.json`

## 21. `b03-formalizable-core-and-proof-obligation-contract`

- 文件：`skills/21-formalizable-core-and-proof-obligation-contract/SKILL.md`
- 层：`formal-foundation`
- 风险：`critical`
- 目标：区分可形式化区域、边界假设、Unsupported Semantics 和已经完成的证明。
- 主要输出：`formal-core-ir/`, `proof-obligations.json`, `formal-boundary-assumptions.json`, `unsupported-formal-semantics.json`

## 22. `b03-incremental-ir-cache-and-chunk-store`

- 文件：`skills/22-incremental-ir-cache-and-chunk-store/SKILL.md`
- 层：`ir-runtime`
- 风险：`critical`
- 目标：避免全仓重算，同时确保不同 Build Context、Frontend 和 Schema 之间不误复用。
- 主要输出：`ir-chunk-store/`, `cache-index.json`, `invalidation-plan.json`, `bundle-publication-journal.json`

## 23. `b03-ir-query-diff-and-export-service`

- 文件：`skills/23-ir-query-diff-and-export-service/SKILL.md`
- 层：`ir-service`
- 风险：`critical`
- 目标：让后续 Batch 通过稳定 API 消费 IR，而不是直接读取内部存储。
- 主要输出：`ir-query-api`, `ir-diff-results.json`, `controlled-export-bundles/`, `query-audit-log.json`

## 24. `b03-frontend-conformance-and-ir-certification-gate`

- 文件：`skills/24-frontend-conformance-and-ir-certification-gate/SKILL.md`
- 层：`certification`
- 风险：`critical`
- 目标：通过 IR0–IR6 分资产认证，防止局部语义能力冒充全仓完整语义。
- 主要输出：`frontend-conformance-report.json`, `ir-certificate.json`, `ir-certificate.sig`, `unresolved-semantic-register.json`

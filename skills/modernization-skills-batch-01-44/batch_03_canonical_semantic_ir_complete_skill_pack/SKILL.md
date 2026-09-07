---
name: batch-03-unified-source-intake-parser-frontends-and-canonical-semantic-ir
description: >
  把多语言源码、构建、配置、SQL、API、二进制和运行元数据转化为无损、可追溯、可增量、可查询和可形式化的联邦式语义 IR。
version: 1.0.0
batch_id: batch-03
layer: compiler-and-semantic-foundation
risk: critical
skill_count: 24
status: implementation-ready-specification
---

# Batch 3：统一源码摄取、解析前端与 Canonical Semantic IR Foundation

## 0. Batch 定位

```yaml
batch:
  id: batch-03
  name: batch-03-unified-source-intake-parser-frontends-and-canonical-semantic-ir
  version: 1.0.0
  status: implementation-ready-specification
  layer: compiler-and-semantic-foundation
  risk: critical
  skill_count: 24
  depends_on:
    - batch-01-competitive-landscape-and-product-positioning
    - batch-02-application-modernization-automated-assessment
```

## 1. Primary Objective

将 Batch 2 锁定的多语言源码、配置、构建文件、SQL、API 契约、生成代码、二进制和运行元数据转换为 Native Lossless IR、Canonical Semantic IR、Analysis Graph IR、Domain IR 与 Formalizable Core，为后续转换、生成、验证和形式证明提供共同语义底座。

## 2. Non-objectives

- 不把所有语言压扁成万能 AST。
- 不在本 Batch 完成目标语言代码生成。
- 不把语法解析成功等同语义恢复成功。
- 不把模型推断类型冒充编译器类型。
- 不执行未经授权的构建脚本、宏处理器或反编译。
- 不删除无法规范化的语言专有语义。

## 3. 可信链与总体架构

```text
Raw Artifact Layer
→ Native Lossless Syntax IR
→ Native Semantic Model
→ Canonical Semantic IR
→ CFG / SSA / Dataflow / Callgraph / Effects
→ BuildIR / ConfigIR / ApiIR / SqlIR / BinaryIR
→ Formalizable Core IR
Cross-cutting:
Source Map + Provenance + Extension Capsule + Evidence + Diagnostics + Schema Version
```

## 4. 核心原则

- Lossless Layer for Fidelity, Canonical Layer for Comparison
- Common Semantics in CSIR, Native Semantics in Extension Capsules
- Facts, Inferences and Unknowns Are Distinct
- Every Lowering Is Traceable
- Semantic Requirements Are Explicit
- Build Context Is Part of Meaning
- Content-addressed and Incremental
- Formal Boundary Is Explicit

## 5. 完整工作流

```text
Validate Assessment Snapshot
→ Normalize Artifacts
→ Detect Language and Regions
→ Resolve Build Context
→ Select Frontend
→ Parse Native Lossless IR
→ Attribute Symbols and Types
→ Lower to CSIR
→ Build Analysis Graphs
→ Build Domain IR
→ Build Provenance and Fingerprints
→ Extract Formal Core
→ Incremental Store
→ Certify
```

## 6. 状态机

```text
created
→ validating-inputs
→ normalizing
→ resolving-build-context
→ selecting-frontends
→ parsing
→ attributing
→ lowering
→ building-graphs
→ building-domain-ir
→ mapping-provenance
→ formalizing
→ assembling-bundle
→ validating
→ certified

exceptions:
partial
frontend-failed
insufficient-build-context
schema-incompatible
stale-cache
unsafe-plugin
cancelled
failed
certificate-revoked
```

## 7. 核心数据契约

### IRBundleManifest

```yaml
bundle_id: uuid
assessment_id: uuid
snapshot_id: uuid
snapshot_merkle_root: sha256
schema:
  csir_version: semver
  agir_version: semver
  domain_ir_versions: {}
producers: []
semantic_coverage:
  S0: number
  S1: number
  S2: number
  S3: number
  S4: number
  S5: number
  S6: number
  S7: number
  S8: number
chunks: []
diagnostics_summary: {}
root_digest: sha256
```

### IRNodeHeader

```yaml
node_id: string
logical_node_id: string | null
snapshot_id: uuid
node_kind: string
language_id: string
origin: source | generated | macro-expanded | binary-derived | decompiled | inferred | synthetic
source_span_ref: string | null
build_context_id: string | null
semantic_level: S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8
fact_status: compiler-confirmed | deterministic-analysis | runtime-observed | model-inferred | human-asserted | unknown
confidence: number
diagnostics: []
extension_capsule_refs: []
provenance_edge_ids: []
```

### TypeRef

```yaml
type_id: string
kind: primitive | nominal | structural | function | tuple | union | intersection | generic-instance | type-variable | array | pointer | reference | option | task | future | stream | dynamic | any | unknown | never | null | unit | opaque
native_type_ref: string | null
type_arguments: []
qualifiers:
  nullability: nonnull | nullable | oblivious | unknown
  mutability: mutable | immutable | readonly | unknown
  ownership: owned | borrowed | shared | unmanaged | unknown
  lifetime: string | null
language_semantics:
  assignability_relation_id: string
  conversion_rule_ids: []
confidence: number
```

### ProofObligation

```yaml
obligation_id: string
source_region_node_ids: []
obligation_kind: type-preservation | state-invariant | precondition | postcondition | effect-preservation | exception-preservation | data-refinement | control-flow-refinement | contract-equivalence
assumptions: []
preconditions: []
postconditions: []
invariants: []
allowed_effects: []
unsupported_semantics: []
backend_candidates: [lean, smt, why3, model-checker]
trust_status: generated | reviewed | proved | rejected | unknown
```

## 8. 核心产物

- `source-artifact-manifest.json`
- `language-region-map.json`
- `build-context-graph.json`
- `frontend-capability-registry.json`
- `native-frontend-ir/`
- `canonical-semantic-ir/`
- `analysis-graph-ir/`
- `domain-ir/`
- `formal-core-ir/`
- `symbol-index/`
- `type-index/`
- `source-map-graph/`
- `semantic-fingerprint-index/`
- `ir-diagnostics.json`
- `ir-quality-report.json`
- `ir-bundle-manifest.json`
- `ir-certificate.json`

## 9. Skills

| # | Skill | Layer | Risk | Objective |
|---:|---|---|---|---|
| 01 | `b03-ir-foundation-orchestrator` | orchestrator | critical | 为 Assessment Snapshot 生成唯一、可复现、可恢复的联邦式 IR Bundle。 |
| 02 | `b03-source-artifact-normalizer` | source-intake | critical | 建立内容寻址 Raw Artifact Layer，确保后续任何解析都可回到原始字节。 |
| 03 | `b03-language-version-and-region-detector` | frontend-routing | high | 为多语言、模板、嵌入 SQL 与 DSL 选择正确前端和版本上下文。 |
| 04 | `b03-build-context-and-toolchain-resolver` | build-semantics | critical | 让同一源码在不同 Profile、Target Framework、宏和依赖下拥有独立语义上下文。 |
| 05 | `b03-frontend-adapter-sdk-and-registry` | frontend-platform | critical | 统一 Compiler-backed、Lossless、Syntax 和 Token Fallback 前端，而不强制使用同一解析器。 |
| 06 | `b03-native-lossless-syntax-ir-builder` | native-ir | critical | 提供文本与语言原生结构的保真层，支持无操作 Round Trip 和最小范围重写。 |
| 07 | `b03-native-semantic-attribution-engine` | native-semantics | critical | 形成 Compiler-confirmed 与 Partial Semantic Facts，防止模型猜测污染。 |
| 08 | `b03-canonical-semantic-ir-schema-and-lowering` | canonical-ir | critical | 用共同语义支持跨语言比较，同时通过 Extension Capsule 保留专有语义。 |
| 09 | `b03-symbol-identity-scope-and-linker` | semantic-linking | critical | 提供稳定 SymbolId、LogicalSymbolId 和模糊引用模型。 |
| 10 | `b03-canonical-type-system-and-language-relations` | type-system | critical | 避免构建一个错误的全局 Subtype Lattice。 |
| 11 | `b03-expression-statement-and-evaluation-order-lowerer` | semantic-lowering | critical | 确保跨语言转换不会因参数、操作数、闭包或 Await 顺序差异改变行为。 |
| 12 | `b03-control-flow-ssa-and-dataflow-builder` | analysis-graph | critical | 为验证、优化、差分和形式化提供控制与数据语义。 |
| 13 | `b03-callgraph-dispatch-reflection-and-dynamic-linker` | call-analysis | critical | 建立 must、may、observed 和 unresolved 调用边。 |
| 14 | `b03-effect-exception-concurrency-and-resource-modeler` | semantic-effects | critical | 提供 Must/May/Unknown Effect 与资源清理、并发同步语义。 |
| 15 | `b03-build-config-and-resource-ir-builder` | domain-ir | high | 让代码生成和框架迁移理解配置优先级、环境差异与资源所有权。 |
| 16 | `b03-api-message-and-contract-ir-builder` | contract-ir | critical | 建立实现与正式契约的统一 ContractIR 和 Drift。 |
| 17 | `b03-sql-and-database-procedural-ir-builder` | database-ir | critical | 保留 Oracle、SQL Server、MySQL、PostgreSQL 的查询、事务、Routine 和专有语义。 |
| 18 | `b03-binary-bytecode-and-native-metadata-ir` | binary-ir | critical | 补足 Source Missing 和生产版本 Drift，同时保持授权与 Derived 标记。 |
| 19 | `b03-generated-code-macro-and-metaprogramming-modeler` | provenance | critical | 决定后续转换应修改输入模板、生成器还是生成输出。 |
| 20 | `b03-source-map-provenance-and-semantic-fingerprint` | traceability | critical | 提供一对多、多对一、Tombstone 和跨快照语义候选匹配。 |
| 21 | `b03-formalizable-core-and-proof-obligation-contract` | formal-foundation | critical | 区分可形式化区域、边界假设、Unsupported Semantics 和已经完成的证明。 |
| 22 | `b03-incremental-ir-cache-and-chunk-store` | ir-runtime | critical | 避免全仓重算，同时确保不同 Build Context、Frontend 和 Schema 之间不误复用。 |
| 23 | `b03-ir-query-diff-and-export-service` | ir-service | critical | 让后续 Batch 通过稳定 API 消费 IR，而不是直接读取内部存储。 |
| 24 | `b03-frontend-conformance-and-ir-certification-gate` | certification | critical | 通过 IR0–IR6 分资产认证，防止局部语义能力冒充全仓完整语义。 |

## 10. Certification Gate

### Required

- Source Byte Integrity 和 Path/Archive Security 通过。
- Language Detection、Build Context Separation 和 Plugin Isolation 通过。
- NLST、Source Map、Error Preservation 和 Round Trip 策略通过。
- Symbol、Type、Evaluation Order、CFG、Callgraph 和 Effect 测试通过。
- SQL、Binary、Generated Code 和 Provenance 测试通过。
- Incremental Invalidation、Deterministic Serialization 和 Schema Compatibility 通过。

### Blockers

- source-bytes-modified-without-record
- compiler-facts-overwritten-by-model
- unresolved-symbols-silently-dropped
- unknown-type-converted-to-any
- language-specific-semantics-discarded
- dynamic-call-reported-as-static
- exceptional-paths-omitted
- unknown-effect-reported-as-pure
- sql-dialect-flattened-to-generic
- decompiled-code-reported-as-source
- stale-cache-reused
- formal-obligation-reported-as-proof

## 11. API Contract

```text
GET /v1/ir/bundles/{bundle_id}
GET /v1/ir/bundles/{bundle_id}/coverage
GET /v1/ir/nodes/{node_id}
GET /v1/ir/symbols/{symbol_id}
GET /v1/ir/symbols/{symbol_id}/references
GET /v1/ir/symbols/{symbol_id}/callers
GET /v1/ir/functions/{symbol_id}/cfg
GET /v1/ir/functions/{symbol_id}/effects
GET /v1/ir/sql/{sql_unit_id}
GET /v1/ir/source-map/{node_id}
POST /v1/ir/query
POST /v1/ir/diff
POST /v1/ir/export
POST /v1/ir/certificates
```

## 12. Domain Events

```text
ir.build.requested
ir.source.normalized
ir.language.detected
ir.build-context.created
ir.frontend.selected
ir.frontend.failed
ir.native-tree.created
ir.semantic-attribution.completed
ir.csir.lowered
ir.extension-capsule.created
ir.symbol-index.completed
ir.cfg.completed
ir.callgraph.completed
ir.sql-unit.created
ir.binary-unit.created
ir.proof-obligation.created
ir.chunk.invalidated
ir.bundle.published
ir.certificate.issued
ir.certificate.invalidated
```

## 13. 与后续 Batch 的依赖

- Batch 4 必须声明最低 IR Level、Required Analysis 和 Forbidden Unknown。
- 目标代码生成必须消费 CSIR、Type、Effect、Source Map 和 Extension Capsule。
- 数据库转换必须消费 SqlIR、Transaction Effect 和 Dynamic Hole。
- 形式验证必须消费 Formal Core、Assumption 和 Proof Obligation。

## 14. 最终产品结论

Batch 3 建成后，平台拥有持久、可查询、可验证的软件语义数字底座。核心护城河不是支持多少 AST，而是 Compiler-backed Frontend、Native Lossless IR、CSIR、Language Extension Capsule、显式类型/控制/效果语义、SQL/Binary 联合建模、全链路 Provenance、增量 IR Store 和分资产语义认证。

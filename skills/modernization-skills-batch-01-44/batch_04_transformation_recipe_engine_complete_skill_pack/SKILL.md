---
name: batch-04-cross-language-semantic-mapping-transformation-rule-dsl-and-deterministic-recipe-engine
description: >
  把 Batch 3 CSIR 转化为可组合、可验证、可回滚的跨语言与框架转换规则，统一 OpenRewrite、Codemod、Compiler Pass 和受限 Agent 修复。
version: 1.0.0
batch_id: batch-04
layer: transformation-kernel
risk: critical
skill_count: 25
status: implementation-ready-specification
---

# Batch 4：跨语言语义映射、Transformation Rule DSL 与 Deterministic Recipe Engine

## 0. Batch 定位

```yaml
batch:
  id: batch-04
  name: batch-04-cross-language-semantic-mapping-transformation-rule-dsl-and-deterministic-recipe-engine
  version: 1.0.0
  status: implementation-ready-specification
  layer: transformation-kernel
  risk: critical
  skill_count: 25
  depends_on:
    - batch-01-competitive-landscape-and-product-positioning
    - batch-02-application-modernization-automated-assessment
    - batch-03-canonical-semantic-ir-foundation
```

## 1. Primary Objective

构建以 CSIR 为语义可信底座、以确定性 Recipe Runtime 为执行可信根、以原生 Codemod/Compiler Pass 为语言适配器、以受限 Agent 为最后修复层的统一软件转换内核。

## 2. Non-objectives

- 不在本 Batch 完成所有目标语言最终 Printer。
- 不承诺任意语言之间自动无损转换。
- 不允许 Agent 直接写客户主分支或自行批准输出。
- 不允许规则绕过编译、测试或验证门禁。
- 不把 AST 形状相似视为语义等价。
- 不允许未经签名 Recipe 获得高权限。
- 不自动执行生产数据库数据迁移。

## 3. 可信链与总体架构

```text
Plane A: Native Source Rewrite
  OpenRewrite / Codemod / Compiler Source Rewriter
Plane B: Canonical Semantic Rewrite
  CSIR / CFG / Dataflow / Effects
Plane C: Repository and Contract Rewrite
  Cross-file / Build / Config / API / SQL
Plane D: Restricted Agent Repair
  Local proposal only

All planes converge to:
MatchSet → PatchIntentSet → Conflict Engine → COW Transaction
→ Incremental IR → Verification Obligations → Signed Patch Bundle
```

## 4. 核心原则

- Directional Semantic Mapping
- Deterministic First
- Plan and Explain Before Apply
- Explicit Read/Write and Analysis Contracts
- Stable Anchors, Not Line Numbers
- Atomic Cross-domain Patch
- No Last-write-wins
- Independent Verification
- Agent Bounded and Last
- Every Change Is Reversible and Traceable

## 5. 完整工作流

```text
Recipe Intake
→ Signature and Permission Verification
→ DSL Compile and Static Safety
→ Route Compatibility
→ Semantic Requirement Check
→ Dry-run Plan
→ Scan / Match / Guard
→ Patch Intent
→ Conflict Resolution
→ Approval
→ Copy-on-write Apply
→ Incremental IR
→ Deterministic Verification
→ Restricted Agent Repair if authorized
→ Full Verification
→ Commit and Certify
```

## 6. 状态机

```text
created
→ validating
→ compatible
→ planning
→ scanning
→ matching
→ guarded
→ patch-planned
→ awaiting-approval
→ applying
→ reindexing
→ verifying
→ completed
→ certified

agent path:
verifying
→ deterministic-gap-detected
→ agent-repair-authorized
→ agent-proposing
→ agent-proposal-validating
→ repaired
→ verifying

exceptions:
incompatible
insufficient-ir
no-match
conflict
stale-anchor
unsafe-rule
permission-denied
non-deterministic
verification-failed
repair-rejected
rollback-required
rolled-back
cancelled
failed
certificate-revoked
```

## 7. 核心数据契约

### SemanticMappingEdge

```yaml
mapping_id: string
version: semver
source:
  language: string
  language_version_range: string
  framework: string | null
  semantic_feature: string
target:
  language: string
  language_version_range: string
  framework: string | null
  semantic_feature: string
relation: isomorphic | desugaring-equivalent | representation-compatible | refinement | abstraction | behaviorally-equivalent-under-preconditions | wrapper-mediated | compatibility-runtime-required | lossy | unsupported | unknown
preconditions: []
semantic_gaps: []
required_shims: []
required_verification: []
confidence: number
evidence_refs: []
```

### TransformationRule

```yaml
api_version: transform.platform/v1alpha1
kind: local-rewrite-rule | graph-rewrite-rule | generation-rule | native-adapter-rule | agent-repair-rule | composite-recipe
metadata:
  rule_id: string
  version: semver
compatibility: {}
semantic_requirements:
  minimum_ir_level: string
  required_analyses: []
  forbidden_unknowns: []
scope: {}
phases:
  scan: {}
  match: {}
  guard: {}
  rewrite: {}
  verify: {}
analysis_contract:
  requires: []
  preserves: []
  invalidates: []
write_set: {}
rollback_policy: {}
verification_policy: {}
```

### PatchIntentSet

```yaml
patch_set_id: string
transformation_run_id: string
source_snapshot_root: sha256
intents:
  - intent_id: string
    operation: string
    anchor:
      node_id: string | null
      symbol_id: string | null
      preimage_digest: sha256
    payload_ref: string
    rule_id: string
    match_id: string
    read_set: []
    write_set: []
    provenance_refs: []
    verification_refs: []
patch_set_digest: sha256
```

### TransformationRunCertificate

```yaml
run_id: string
snapshot_id: string
ir_bundle_id: string
route_pack_id: string
recipe_package_digests: []
execution_mode: deterministic-only | deterministic-plus-agent
coverage: {}
verification:
  passed: []
  failed: []
  inconclusive: []
  waived: []
artifacts:
  patch_bundle_digest: sha256
  journal_digest: sha256
  transformed_workspace_digest: sha256
limitations: []
issued_at: datetime
expires_at: datetime
signature: string
```

## 8. 核心产物

- `semantic-mapping-ontology.yaml`
- `semantic-mapping-registry.json`
- `transformation-rule.schema.json`
- `compiled-rule-ir/`
- `recipe-package-manifest.json`
- `directional-route-pack.yaml`
- `transformation-plan.json`
- `match-set.json`
- `guard-decision-log.json`
- `patch-intent-set.json`
- `conflict-report.json`
- `transformation-journal.json`
- `source-target-map.json`
- `verification-obligations.json`
- `verification-evidence.json`
- `agent-repair-proposals.json`
- `signed-patch-bundle.tar`
- `recipe-certificate.json`
- `route-pack-certificate.json`
- `transformation-run-certificate.json`

## 9. Skills

| # | Skill | Layer | Risk | Objective |
|---:|---|---|---|---|
| 01 | `b04-transformation-orchestrator` | orchestrator | critical | 把 Batch 3 IR Bundle 与方向性 Route Pack 转换为可重放、可验证、可回滚的 Signed Patch Bundle。 |
| 02 | `b04-semantic-mapping-ontology-and-registry` | semantic-mapping | critical | 明确 exact、conditional、wrapper、lossy、unsupported 和 unknown 关系。 |
| 03 | `b04-transformation-rule-dsl` | rule-language | critical | 让规则显式声明适用性、读写集、分析依赖、后置条件、验证和回滚。 |
| 04 | `b04-rule-compiler-and-static-safety-analyzer` | rule-compiler | critical | 在规则执行前拒绝不安全、不确定或无法界定影响范围的变换。 |
| 05 | `b04-semantic-matcher-query-and-binding` | matcher | critical | 生成稳定排序、可重放、可解释的 Match Set 与变量绑定。 |
| 06 | `b04-applicability-precondition-and-guard-engine` | applicability | critical | 阻止版本、IR Level、动态语义、生成代码、许可证或业务风险不满足的规则。 |
| 07 | `b04-rewrite-operation-and-patch-planner` | patch-planning | critical | 在写入前生成完整、可冲突分析、可回滚的 Patch Plan。 |
| 08 | `b04-deterministic-recipe-runtime` | runtime | critical | 提供确定性可信根，并明确 Agent-assisted 运行不具生成确定性。 |
| 09 | `b04-recipe-composition-pass-planner-and-explain` | planning | critical | 根据 Requires/Provides、Read/Write、Preserves/Invalidates 和验证成本规划 Pass。 |
| 10 | `b04-analysis-preservation-and-incremental-recompute` | analysis-management | critical | 防止变换后使用 Stale Analysis，同时避免无必要全量重算。 |
| 11 | `b04-directional-route-pack-builder` | route-pack | critical | 把“Java→C#”细化为精确源目标版本、框架、运行时和工作负载路线。 |
| 12 | `b04-openrewrite-recipe-adapter` | native-adapter | critical | 把原生 OpenRewrite 结果转换为平台 PatchSet、Evidence、Journal 和 IR 失效。 |
| 13 | `b04-codemod-and-native-ast-adapter` | native-adapter | high | 利用语言原生 AST 的生态优势，同时保持范围、类型和验证边界。 |
| 14 | `b04-compiler-rewrite-pass-adapter` | compiler-adapter | critical | 利用 Compiler Fact 与 Pass Manager，同时避免无 Source Map 的 Compiler IR 结果冒充源码补丁。 |
| 15 | `b04-cross-file-symbol-api-and-graph-rewriter` | graph-rewrite | critical | 支持 Rename、Move、Signature Change、API Replacement 和 Adapter Introduction。 |
| 16 | `b04-build-config-contract-and-sql-coordinated-rewriter` | coordinated-rewrite | critical | 避免只改源码而遗漏依赖、连接、事务、契约和部署。 |
| 17 | `b04-transformation-conflict-detector-and-resolver` | conflict-management | critical | 禁止 Last-write-wins，使用可交换性、优先级、Barrier 或人工选择。 |
| 18 | `b04-copy-on-write-transaction-and-rollback` | transaction | critical | 保证原始 Snapshot 不变，并在验证失败时恢复精确状态。 |
| 19 | `b04-source-map-format-comment-and-provenance-preserver` | provenance | high | 让评审者理解每个 Patch 来源，并防止 Formatter 噪声掩盖真实变更。 |
| 20 | `b04-verification-obligation-and-postcondition-runner` | verification | critical | 建立 V0–V9 分层验证，并在无法判定时保持 inconclusive。 |
| 21 | `b04-restricted-agent-repair-controller` | agent-repair | critical | 利用 Agent 处理局部胶水问题，但不让其成为可信根或扩大范围。 |
| 22 | `b04-agent-repair-to-rule-distiller` | rule-learning | high | 把重复局部修复沉淀为可测试、可审计的规则资产。 |
| 23 | `b04-recipe-package-registry-and-supply-chain` | registry | critical | 确保进入执行环境的规则包来源可信、权限最小且可撤销。 |
| 24 | `b04-recipe-corpus-benchmark-and-regression` | testing | critical | 防止只测试成功案例、自动更新 Golden 或用格式变化冒充语义变换。 |
| 25 | `b04-transformation-certification-gate` | certification | critical | 通过 RC0–RC6 和 Correctness Class 清晰表达实际验证范围。 |

## 10. Certification Gate

### Required

- DSL、Rule Compiler、Termination、Permission 和 Determinism 测试通过。
- Matcher、Tri-state Guard、Stable Anchor、Read/Write Set 通过。
- Recipe DAG、Analysis Invalidation、Bounded Fixpoint 和 Parallel Merge 通过。
- OpenRewrite、Codemod 和 Compiler Adapter 通过。
- Cross-file Atomicity、Conflict、COW、Journal 和 Rollback 通过。
- Blocking Verification、Agent Envelope、Prompt Injection、Package Signature 和 Certificate Invalidation 通过。

### Blockers

- universal-undirected-language-mapping
- syntax-similarity-treated-as-semantic-equivalence
- unresolved-unknown-silently-dropped
- external-tool-direct-repository-write
- agent-before-deterministic-rules
- agent-direct-commit
- agent-modifies-verification
- last-write-wins-conflict-resolution
- stale-analysis-used-after-rewrite
- unbounded-recipe-cycle
- unsigned-production-recipe
- verification-failure-without-rollback
- agent-assisted-run-labeled-deterministic

## 11. API Contract

```text
POST /v1/recipe-packages
GET /v1/recipe-packages/{package_id}
POST /v1/rules/compile
POST /v1/rules/lint
POST /v1/rules/test
POST /v1/route-packs
POST /v1/route-packs/{route_id}/certify
POST /v1/transformation-runs
POST /v1/transformation-runs/{run_id}/plan
GET /v1/transformation-runs/{run_id}/explain
POST /v1/transformation-runs/{run_id}/approve
POST /v1/transformation-runs/{run_id}/start
POST /v1/transformation-runs/{run_id}/rollback
GET /v1/transformation-runs/{run_id}/patches
GET /v1/transformation-runs/{run_id}/verification
POST /v1/transformation-runs/{run_id}/agent-repair
POST /v1/transformation-runs/{run_id}/certificate
```

## 12. Domain Events

```text
recipe.package.registered
rule.compilation.completed
rule.static-safety.failed
route-pack.certified
transformation.plan.generated
transformation.match.completed
patch.intent.generated
patch.conflict.detected
patch.applied
analysis.invalidated
analysis.recomputed
verification.failed
agent.repair.proposed
agent.repair.accepted
transaction.rollback.completed
transaction.committed
transformation.certificate.issued
transformation.certificate.invalidated
```

## 13. 与后续 Batch 的依赖

- Batch 5 必须消费 Directional Route Pack、Transformed CSIR、Target Construction Intent、Semantic Gap、Shim、Source-target Map 和 Run Certificate。
- 测试和差分 Batch 必须消费 Verification Obligation、Effect/Contract 变化和 Agent Change Register。
- 形式验证必须消费 Rule Preconditions、Postconditions、Semantic Relation 和 Proof Obligation Template。
- 生产治理必须验证 Signed Patch Bundle、Journal 和 Rollback Evidence。

## 14. 最终产品结论

Batch 4 建成后，平台拥有统一的可验证软件转换内核。核心护城河不是脚本数量或 Agent 速度，而是方向性语义映射、类型安全 DSL、确定性 Rule Compiler、分析感知 Planner、原生工具 Adapter、原子跨域 Patch、冲突与事务系统、独立验证、受限 Agent、Recipe Distillation 和签名认证。

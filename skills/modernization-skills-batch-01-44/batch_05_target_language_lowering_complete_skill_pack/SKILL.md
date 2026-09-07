---
name: batch-05-target-language-lowering-framework-backend-idiomatic-code-generation
description: >
  将 Batch 4 的 Transformed CSIR 与 Target Construction Intent 降低为
  Java、C#、Node.js/TypeScript、Python、C++、Go、Rust、Vue、React、Flutter
  等目标语言与框架的可构建、可维护、符合目标生态习惯的完整工程代码。
version: 1.0.0
batch_id: batch-05
layer: target-code-generation
risk: critical
skill_count: 34
status: implementation-ready-specification
---

# Batch 5：Target Language Lowering、Framework Backend 与 Idiomatic Code Generation

## 0. Batch 定位

```yaml
batch:
  id: batch-05
  name: target-language-lowering-framework-backend-and-idiomatic-code-generation
  version: 1.0.0
  status: implementation-ready-specification
  layer: target-generation
  risk: critical
  skill_count: 34

  depends_on:
    - batch-01-competitive-landscape-and-product-positioning
    - batch-02-application-modernization-automated-assessment
    - batch-03-canonical-semantic-ir-foundation
    - batch-04-transformation-rule-dsl-and-deterministic-recipe-engine

  primary_objective: >
    消费 Batch 4 的方向性 Route Pack、Transformed CSIR、Target Construction Intent、
    Semantic Gap Register、Required Shim Register、Source-target Provenance 与
    Verification Obligations，先降低为 Target Typed IR，再通过目标语言与框架后端，
    生成可解析、可格式化、可类型检查、可构建、可增量再生成的完整工程。

  non_objectives:
    - 不把 Build Green 宣称为业务行为等价
    - 不允许模型直接自由重写整个目标项目
    - 不把逐行翻译当作惯用代码生成
    - 不隐藏语义缺口、Shim、TODO 或人工决策
    - 不自动修改生产环境、生产数据库或真实 Secret
    - 不手工伪造包管理器 Lockfile
    - 不覆盖未经治理的人工修改
```

## 1. 产品边界与可信链

Batch 5 的可信链为：

```text
Batch 3 Compiler-backed CSIR
→ Batch 4 Deterministic Semantic Transformation
→ Batch 5 Target Typed IR
→ Target-native AST/LST
→ Official Formatter / Linter / Typechecker / Compiler
→ Build and Framework Smoke Evidence
→ Generated Project Certificate
```

目标代码生成不以 LLM 文本续写为基础，而以如下结构为基础：

```text
Transformed CSIR
+ Target Construction Intent
+ Directional Semantic Mapping
+ Target Profile
+ Idiom Policy
+ Framework Contract
+ Backend Passes
+ Target-native Emitter
```

受限 Agent 只处理确定性后端之后仍然存在的局部构建或胶水缺口，不能成为可信根，也不能修改测试、Golden、验证策略或证书。

## 2. 五层目标生成架构

```text
┌──────────────────────────────────────────────────────┐
│ Layer 1：Target Profile                              │
│ 语言/版本/框架/运行时/工具链/依赖/组织策略             │
└──────────────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────┐
│ Layer 2：Target Typed IR — TTIR                      │
│ 目标类型、声明、控制流、框架构造、工程与资源意图        │
└──────────────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────┐
│ Layer 3：Language and Framework Backend Passes       │
│ 类型/异常/并发/API/ORM/消息/配置/前端状态等 Lowering   │
└──────────────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────┐
│ Layer 4：Native AST/LST and Project Emission         │
│ Roslyn、Java AST、TS AST、LibCST、Clang、go/ast 等     │
└──────────────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────┐
│ Layer 5：Toolchain Verification and Certification    │
│ Format/Lint/Typecheck/Build/Smoke/Provenance/Gate     │
└──────────────────────────────────────────────────────┘
```

## 3. 核心设计原则

```text
Target Ecosystem First
Semantic Preservation Before Brevity
Target-native AST/LST Before String Templates
Explicit Unknowns and Gaps
Deterministic Generation Before Agent Repair
Build-aware and Framework-aware
Complete Project, Not Isolated Files
Incremental Regeneration with Manual Change Protection
Every Target Declaration Has Provenance or Generated Reason
Lock Toolchains and Dependencies
Certificate Scope Must Match Actual Evidence
```

### 3.1 禁止逐行翻译

源语言语法与目标语言语法表面相似时，也必须先经过语义和目标模式选择。例如：

```text
Java Stream           不自动等于 C# LINQ
Java Optional         不自动等于 C# nullable
Java Exception        不自动等于 Go error
C# Task               不自动等于 goroutine
Vue watch             不自动等于 React useEffect
DOM Element Tree      不自动等于 Flutter Widget Tree
C++ pointer           不自动等于 Rust reference
```

### 3.2 目标惯用性不能覆盖语义正确性

当目标生态惯用模式与源语义存在张力时，优先级为：

```text
行为与契约约束
→ 安全与数据约束
→ 目标运行时语义
→ 组织架构与可维护性策略
→ 目标生态惯用性
→ 代码简短程度
```

### 3.3 完整工程生成

Batch 5 的输出不是若干 `.java`、`.cs` 或 `.ts` 文件，而必须包括：

```text
源码
构建文件
依赖与锁定策略
配置模板
资源
测试工程或迁移后的测试骨架
运行入口
健康检查
基础日志与追踪
数据库迁移意图
部署前置说明
一键构建命令
一键本地启动命令
Generated Project Manifest
```

## 4. 输入契约

```yaml
generation_request:
  generation_run_id: uuid
  tenant_id: uuid

  source:
    assessment_snapshot_id: uuid
    ir_bundle_id: uuid
    transformation_run_id: uuid
    transformed_csir_digest: sha256

  route:
    route_pack_id: string
    route_pack_version: semver
    transformation_certificate_id: uuid

  target:
    target_profile_id: string
    target_profile_version: semver
    backend_plugin_versions: {}

  inputs:
    target_construction_intent_ref: string
    semantic_gap_register_ref: string
    required_shim_register_ref: string
    source_target_map_ref: string
    verification_obligations_ref: string

  policies:
    organization_coding_policy_ref: string
    dependency_policy_ref: string
    security_policy_ref: string
    manual_region_policy_ref: string
    agent_envelope_ref: string
```

## 5. 目标 Profile

```yaml
target_profile:
  profile_id: csharp12-aspnet8-postgresql
  version: 1.0.0

  language:
    id: csharp
    version: "12"
    nullability: enabled

  runtime:
    id: dotnet
    version: "8.x"

  framework:
    id: aspnet-core
    version: "8.x"

  build:
    system: dotnet-sdk
    package_manager: nuget
    lock_mode: locked

  persistence:
    orm: ef-core
    database: postgresql

  quality:
    formatter: dotnet-format
    analyzers: []
    warnings_as_errors: policy-controlled

  idioms:
    async_suffix: required
    cancellation_token: propagate
    nullable_reference_types: required
    primary_constructors: policy-controlled

  forbidden:
    - global-nullable-disable
    - sync-over-async
    - production-secret-in-source
```

## 6. Target Typed IR

TTIR 位于 CSIR 与目标原生 AST 之间。它已经选择目标语义和目标模式，但尚未绑定具体打印细节。

```yaml
ttir_node:
  node_id: string
  node_kind: string
  target_profile_id: string

  semantic_origin:
    transformed_csir_node_ids: []
    transformation_intent_ids: []
    semantic_relation: string

  target_semantics:
    type_ref: string | null
    effect_summary_ref: string | null
    exception_model_ref: string | null
    ownership_ref: string | null
    framework_construct_ref: string | null

  ownership:
    generation_mode: managed | mixed | manual | external
    backend_id: string
    backend_version: semver

  gaps:
    semantic_gap_ids: []
    required_shim_ids: []

  source_map_refs: []
  diagnostics: []
```

## 7. 完整生成工作流

```text
Generation Request
→ Input Certificate and Digest Validation
→ Target Profile Resolution
→ Backend Capability Resolution
→ TTIR Lowering Plan
→ Type / Control / Exception / Concurrency Lowering
→ Framework Contract Lowering
→ Project Layout and Build Generation
→ Language-specific Backend Passes
→ Target-native AST/LST Emission
→ Formatting and Import Organization
→ Incremental Source-target Map Update
→ Parse / Lint / Typecheck / Build
→ Deterministic Repair Recipes
→ Restricted Agent Repair when Authorized
→ Framework Smoke and Contract Checks
→ Completeness / Provenance / Gap Gate
→ Signed Generated Project Bundle
→ Generation Certificate
```

### 7.1 状态机

```text
created
→ validating-inputs
→ profile-resolved
→ planning
→ lowering
→ framework-lowering
→ project-generating
→ emitting
→ formatting
→ building
→ deterministic-repair
→ verifying
→ awaiting-review
→ completed
→ certified
```

可选 Agent 路径：

```text
building
→ deterministic-repair-exhausted
→ agent-authorized
→ agent-proposing
→ agent-validating
→ building
```

异常状态：

```text
incompatible-input
invalid-certificate
insufficient-ir
unsupported-semantic-gap
backend-unavailable
emission-failed
build-failed
repair-not-converged
manual-conflict
verification-failed
rollback-required
cancelled
failed
certificate-revoked
```

## 8. 输出契约

```yaml
generated_project_manifest:
  generation_run_id: uuid
  project_id: string

  lineage:
    snapshot_id: uuid
    ir_bundle_id: uuid
    transformation_run_id: uuid
    route_pack_id: string
    target_profile_id: string

  toolchains:
    backend_plugins: {}
    compilers: {}
    formatters: {}
    linters: {}
    package_managers: {}

  projects:
    - project_path: string
      project_kind: application | library | test | tool | infrastructure
      build_command: string
      test_command: string | null
      run_command: string | null

  files:
    - path: string
      digest: sha256
      kind: source | build | config | resource | test | generated-doc
      ownership: managed | mixed | manual | external
      source_target_map_refs: []
      semantic_gap_refs: []

  verification:
    parse: passed | failed | partial
    format: passed | failed | partial
    lint: passed | failed | partial
    typecheck: passed | failed | partial
    build: passed | failed | partial
    smoke: passed | failed | partial

  unresolved:
    semantic_gaps: []
    manual_decisions: []
    shims: []
    todos: []
```

## 9. 目标后端矩阵

| Backend | 默认生产级目标 | 结构化发射器 | 核心验证 |
|---|---|---|---|
| Java/JVM | Java 17/21、Spring Boot 3 | Java AST/OpenRewrite/Javac Adapter | compile、test、formatter |
| C#/.NET | C# 12、.NET 8、ASP.NET Core | Roslyn | format、build、test、analyzers |
| Node.js/TS | Node LTS、strict TS、Nest/Fastify | TypeScript Compiler AST | eslint、tsc、build、test |
| Python | Python 3.12、FastAPI/Django | LibCST/AST | format、lint、typecheck、test |
| C++ | C++20/23、CMake | Clang AST/structured emitter | build、clang-tidy、sanitizers |
| Go | Go Modules、net/http/Gin | go/ast | gofmt、vet、test、race、build |
| Rust | Cargo、Axum/Actix | syn/quote or compiler adapter | fmt、clippy、test、check |
| Vue | Vue 3、TS、Vite、Pinia | Vue SFC AST + TS AST | vue-tsc、lint、test、build |
| React | React、TS、Vite/Next.js | TS/JSX AST | typecheck、lint、test、build |
| Flutter | Dart/Flutter、Riverpod/Bloc | analyzer AST/code builder | format、analyze、test、build |

## 10. Generation Correctness Levels

```text
G0 — Target Plan Created
     已选择 Profile、后端和 Lowering Plan。

G1 — Target Syntax Valid
     所有生成源文件可被目标 Parser 读取。

G2 — Target Type and Build Valid
     Typecheck/Compiler/Build 达到规定阈值。

G3 — Framework Bootstrap Valid
     应用 Host、路由、DI、配置和基础资源可启动。

G4 — Contract-ready Candidate
     API、消息、数据库与配置映射可供后续契约验证。

G5 — Maintainability-qualified Candidate
     Lint、来源映射、Shim/TODO、惯用性和复杂度达到阈值。

G6 — Route-certified Generated Project
     在精确 Route/Profile/Toolchain 上通过完整 Batch 5 Corpus 与 Gate。
```

Batch 5 不签发：

```text
Behavior Equivalence Certificate
Production Cutover Certificate
Database Data Migration Certificate
Performance Equivalence Certificate
```

这些必须由后续差分测试、Dual Run、性能、安全和生产认证 Batch 完成。

## 11. 生成质量指标

```text
Parse Success Rate
Type Attribution Coverage
Build Green Rate
Framework Bootstrap Rate
Source-target Provenance Coverage
Deterministic Generation Coverage
Agent-assisted Changed Lines
Unmapped Target Declaration Count
Semantic Gap Count
Shim Density
TODO Density
Source Idiom Leakage Score
Target Idiom Compliance Score
Formatting-only Diff Ratio
Manual Conflict Rate
Incremental Regeneration Reuse Rate
P50 / P95 Generation Time
Peak Memory
```

任何百分比都必须明确分母。无法确定分母时，值必须为 `null`，不得显示为 100%。

## 12. 关键安全边界

```text
目标生成 Workspace 与原始仓库隔离；
构建脚本作为不可信代码执行；
默认禁止网络和生产 Secret；
生成配置只能引用 Secret Provider，不能保存 Secret Value；
第三方后端插件必须签名、声明权限和通过沙箱；
Agent 输出只能形成 Proposal；
源码注释、README、测试描述均视为不可信上下文；
不得允许 Agent 修改测试、Golden、证书、验证策略或权限策略。
```

## 13. API Contract

```text
POST   /v1/target-profiles
GET    /v1/target-profiles/{profile_id}
POST   /v1/target-profiles/{profile_id}/validate
POST   /v1/target-profiles/{profile_id}/certify

POST   /v1/backends
GET    /v1/backends/{backend_id}
POST   /v1/backends/{backend_id}/conformance
POST   /v1/backends/{backend_id}/revoke

POST   /v1/generation-runs
GET    /v1/generation-runs/{run_id}
POST   /v1/generation-runs/{run_id}/plan
GET    /v1/generation-runs/{run_id}/explain
POST   /v1/generation-runs/{run_id}/approve
POST   /v1/generation-runs/{run_id}/start
POST   /v1/generation-runs/{run_id}/pause
POST   /v1/generation-runs/{run_id}/resume
POST   /v1/generation-runs/{run_id}/cancel
POST   /v1/generation-runs/{run_id}/rollback

GET    /v1/generation-runs/{run_id}/ttir
GET    /v1/generation-runs/{run_id}/files
GET    /v1/generation-runs/{run_id}/build
GET    /v1/generation-runs/{run_id}/gaps
GET    /v1/generation-runs/{run_id}/source-target-map

POST   /v1/generation-runs/{run_id}/agent-repair
GET    /v1/generation-runs/{run_id}/agent-proposals
POST   /v1/generation-runs/{run_id}/agent-proposals/{proposal_id}/approve
POST   /v1/generation-runs/{run_id}/agent-proposals/{proposal_id}/reject

POST   /v1/generation-runs/{run_id}/certificate
GET    /v1/generation-runs/{run_id}/certificate
```

## 14. 领域事件

```text
target-profile.registered
target-profile.certified
target-profile.invalidated
backend.registered
backend.conformance-passed
backend.revoked

generation.run.created
generation.input.validated
generation.plan.created
generation.ttir.lowered
generation.framework.lowered
generation.project-layout.created
generation.file.emitted
generation.file.formatted
generation.build.started
generation.build.failed
generation.deterministic-repair.applied
generation.agent-repair.requested
generation.agent-repair.accepted
generation.manual-conflict.detected
generation.source-map.completed
generation.project.completed
generation.certificate.issued
generation.certificate.invalidated
```

## 15. 必须实现的综合测试场景

1. Java ResourceScope 降低为 C# `using` 与 `await using`，验证异常和释放顺序。
2. Java Optional、数据库 NULL 与 C# nullable 同时出现，禁止粗暴合并。
3. Java checked exception 转 Go error，验证调用链错误传播。
4. C# Task 转 Rust async，验证 Send、Cancellation 与错误模型。
5. C++ RAII 转 Rust Ownership，禁止无根据 `unsafe`。
6. Vue watch 转 React，验证是否应为 derived state、event handler 或 effect。
7. Vue DOM 页面转 Flutter Widget，禁止逐元素机械复制。
8. Spring Controller 转 ASP.NET Core Endpoint，验证路由、序列化、授权和错误契约。
9. Hibernate/Oracle 转 EF Core/PostgreSQL，验证 Decimal、事务和 Native SQL 缺口。
10. 消息消费者迁移时保留 Key、Header、Ordering、Retry 和 DLQ。
11. Target Profile 主版本变化后旧后端证书失效。
12. 相同输入在不同 Worker 数下产生相同文件 Digest。
13. Formatter 不得产生全仓无关格式噪声。
14. Lockfile 必须由包管理器在锁定环境生成。
15. 构建脚本尝试读取主机 Secret 时 Sandbox 阻断。
16. Agent 试图删除断言、关闭 Analyzer 或修改十个超范围文件时拒绝。
17. 人工修改 mixed 文件后增量再生成，必须结构化三方合并。
18. 源符号移动后 Source-target Map 仍可关联 LogicalSymbol。
19. Build Green 但契约测试失败时不得达到 G4。
20. 未映射目标声明超过阈值时不得签发 G5/G6。

## 16. Batch 5 Certification Gate

```yaml
batch_05_gate:
  required:
    target-profile-versioned: true
    backend-plugin-signed: true
    ttir-schema-versioned: true
    deterministic-pass-planning-tested: true
    target-type-mapping-tested: true
    evaluation-order-tested: true
    exception-and-resource-tested: true
    concurrency-and-cancellation-tested: true
    framework-contract-lowering-tested: true
    project-layout-tested: true
    dependency-lock-generation-tested: true
    native-ast-emission-tested: true
    formatter-idempotence-tested: true
    build-sandbox-tested: true
    deterministic-repair-tested: true
    agent-envelope-tested: true
    incremental-regeneration-tested: true
    source-target-provenance-tested: true
    backend-corpus-tested: true
    certificate-invalidation-tested: true

  blockers:
    - freeform-whole-repository-generation
    - line-by-line-translation-positioning
    - source-idiom-leakage-without-review
    - unknown-type-defaulted-to-any
    - silent-numeric-narrowing
    - hidden-semantic-gap
    - hand-authored-lockfile
    - production-secret-in-output
    - unsigned-production-backend
    - formatter-overwrites-manual-files
    - agent-direct-commit
    - agent-weakens-tests-or-verification
    - build-green-labeled-behavior-equivalent
    - incomplete-source-target-map-above-policy-threshold
```

## 17. 与后续 Batch 的接口

Batch 5 提供：

```yaml
provides:
  testing-and-oracle-recovery:
    - generated-project-manifest
    - migrated-test-projects
    - source-target-symbol-map
    - changed-contract-surfaces
    - unresolved-semantic-gaps

  differential-equivalence:
    - source-target-map
    - target-build-artifacts
    - api-message-database-contract-map
    - effect-and-exception-relations
    - agent-assisted-change-register

  dual-run:
    - runnable-target-project
    - route-and-endpoint-map
    - state-observable-map
    - target-runtime-configuration
    - shim-and-compatibility-register

  performance-and-security:
    - target-dependency-sbom
    - target-build-baseline
    - generated-security-policy-map
    - target-observability-baseline

  deployment:
    - complete-project-manifest
    - build-and-run-commands
    - configuration-template
    - deployment-prerequisites
    - generation-certificate
```

后续任何行为等价或生产发布流程必须读取：

```text
Generated Project Manifest
+ Generation Certificate
+ Source-target Map
+ Semantic Gap Register
+ Shim Register
+ Agent-assisted Change Register
+ Toolchain and Dependency Lock
```

## 18. Definition of Done

Batch 5 完成时，系统必须能够回答：

1. 每个目标项目使用什么精确语言、框架、运行时和工具链？
2. 哪些目标模式由确定性规则选择，哪些经过人工决策？
3. 每个目标类型如何处理 Null、Generic、Numeric、Ownership 和 Precision？
4. 控制流、异常、资源与并发语义如何降低？
5. API、DI、ORM、消息、配置、安全和 Observability 如何生成？
6. Java、C#、Node.js、Python、C++、Go、Rust 后端分别达到什么能力等级？
7. Vue、React 和 Flutter 的状态、路由、生命周期与平台差异如何表达？
8. 目标源码是否由原生 AST/LST 结构化生成？
9. 构建文件、依赖、Lockfile、测试和运行入口是否完整？
10. 目标工程在干净环境中能否 Format、Lint、Typecheck、Build 和启动？
11. 哪些修复是确定性的，哪些由 Agent 辅助？
12. 增量再生成是否会覆盖人工修改？
13. 每个目标声明能否追溯到源语义或生成理由？
14. 当前有哪些 Shim、TODO、未知和人工工作？
15. 生成证书究竟证明了什么，尚未证明什么？

Batch 5 的核心护城河是：

```text
Versioned Target Profiles
+ Target Typed IR
+ Analysis-aware Lowering Pass Manager
+ Target Idiom Policy
+ Framework-neutral Contract Backends
+ Ten Target Language/Framework Backends
+ Target-native AST/LST Emitters
+ Complete Project and Toolchain Generation
+ Incremental Regeneration with Manual Protection
+ Restricted Agent Repair
+ Full Source-target Provenance
+ Backend Corpus and Generation Certification
```

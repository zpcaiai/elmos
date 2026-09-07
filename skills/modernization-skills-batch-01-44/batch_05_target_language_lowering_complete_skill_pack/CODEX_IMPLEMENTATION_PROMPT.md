# CODEX IMPLEMENTATION PROMPT — Batch 05

你正在实现一套企业级、可验证的应用现代化平台的 **Batch 05：Target Language Lowering、Framework Backend 与 Idiomatic Code Generation**。

## 0. 必读文件

在修改任何代码前，完整读取：

1. `README.md`
2. `SKILL.md`
3. `SKILL_INDEX.md`
4. `BATCH04_COMPATIBILITY.md`
5. `IMPLEMENTATION_CHECKLIST.md`
6. `schemas/**`
7. `policies/**`
8. 与当前实现阶段相关的 `skills/**/SKILL.md`

不得只阅读本提示词后直接开始生成代码。

## 1. 最终目标

在现有单体仓库或新建 Monorepo 中实现一个可运行的 Batch 5 平台，接收 Batch 4 的已签名转换产物，生成 Java、C#、Node.js/TypeScript、Python、C++、Go、Rust、Vue、React、Flutter 目标工程。

平台必须：

- 使用 Target Profile 和 Target Typed IR；
- 使用确定性 Pass Planner；
- 使用目标原生 AST/LST 或结构化 Builder 发射源码；
- 生成完整工程、构建、配置、资源与 Manifest；
- 在隔离环境运行 Format/Lint/Typecheck/Build；
- 支持增量再生成与人工修改保护；
- 支持受限 Agent 修复，但 Agent 不能直接 Commit；
- 维护完整 Source→Target Provenance；
- 签发范围准确的 Generation Certificate。

## 2. 默认技术栈

```yaml
control_plane:
  language: python-3.12
  api: fastapi
  validation: pydantic-v2
  workflow: temporal
  relational: postgresql
  object_store: minio-or-s3-compatible
  graph: neo4j-or-postgresql-graph-abstraction
  telemetry: opentelemetry

web_console:
  framework: vue-3
  language: typescript
  state: pinia

workers:
  java: jdk-21-worker
  dotnet: dotnet-8-worker
  node: node-lts-worker
  python: python-3.12-worker
  cpp: clang-cmake-worker
  go: current-supported-go-worker
  rust: stable-rust-worker
  flutter: stable-flutter-worker

execution:
  isolation: container-or-kubernetes-job
  network: denied-by-default
  secrets: none-by-default
  filesystem: copy-on-write-workspace
```

若现有仓库已有等价技术栈，优先适配现有架构，不得无理由重写。

## 3. 必须实现的仓库结构

```text
services/generation-platform/
  api/
  orchestrator/
  target_profiles/
  backend_registry/
  ttir/
  pass_manager/
  idiom_policy/
  lowering/
  framework_backends/
  project_generation/
  build_runtime/
  regeneration/
  agent_repair/
  provenance/
  certification/

backends/
  java/
  dotnet/
  node-typescript/
  python/
  cpp/
  go/
  rust/
  vue/
  react/
  flutter/
  backend-sdk/

schemas/
policies/
corpus/
frontend/generation-console/
tests/
```

## 4. 实现顺序

### Phase 0：仓库勘察与架构锁定

- 检查已有 Batch 1–4 代码、Schema、事件、存储和认证接口。
- 生成 `docs/batch05/current-state.md`。
- 列出可复用模块与必须新增模块。
- 不得在未理解现有架构前创建重复基础设施。

### Phase 1：Schema 和 Target Profile

实现：

- `TargetProfile`
- `TargetConstructionIntent`
- `TTIR`
- `GenerationPlan`
- `BackendPluginManifest`
- `GeneratedProjectManifest`
- `SourceTargetMap`
- `GenerationCertificate`

所有 Schema 必须：

- 有 Pydantic Model；
- 有 JSON Schema；
- 有版本字段；
- 有向后兼容测试；
- 区分 `unknown`、`unsupported`、`lossy` 和 `manual-decision-required`。

### Phase 2：后端 SDK 与 Registry

实现 Backend Protocol：

```python
class TargetBackend(Protocol):
    def capabilities(self) -> BackendCapabilityManifest: ...
    def validate_profile(self, profile: TargetProfile) -> ValidationResult: ...
    def plan(self, ttir_input: TTIRBundle, context: BackendContext) -> BackendPlan: ...
    def lower(self, plan: BackendPlan) -> NativeTargetIR: ...
    def emit(self, native_ir: NativeTargetIR, workspace: WorkspaceRef) -> EmitResult: ...
    def format(self, workspace: WorkspaceRef) -> ToolResult: ...
    def typecheck(self, workspace: WorkspaceRef) -> ToolResult: ...
    def build(self, workspace: WorkspaceRef) -> ToolResult: ...
    def smoke(self, workspace: WorkspaceRef) -> ToolResult: ...
```

实现签名、Digest、权限、SBOM、撤销、沙箱和 Conformance 状态。

### Phase 3：TTIR 与 Pass Manager

- 不要把 TTIR 设计成代码字符串集合。
- 实现声明、类型、表达式、语句、Framework Construct、Project、Build、Resource 节点。
- 实现 Pass `requires/provides/preserves/invalidates`。
- 实现稳定拓扑排序、循环检测、Barrier、并行稳定合并和检查点。
- 相同输入必须产生相同 Plan Digest。

### Phase 4：共享语义 Lowering

按 Skills 06–16 实现：

- Target Idiom Policy；
- Type/Nullability/Generic/Numeric；
- Expression/Control；
- Exception/Resource；
- Async/Concurrency/Cancellation；
- Project Layout；
- Build/Dependency；
- API/DI/Serialization；
- Persistence/ORM/Transaction；
- Messaging/Job；
- Config/Security/Observability/Resilience。

每个 Lowering 必须返回：

```yaml
lowering_result:
  produced_nodes: []
  semantic_relations: []
  gaps: []
  required_shims: []
  verification_obligations: []
  provenance_edges: []
  diagnostics: []
```

### Phase 5：Reference Backends

首先实现并达到完整集成测试：

1. C# 12 / .NET 8 / ASP.NET Core 8 / EF Core 8；
2. React / TypeScript / Vite；
3. Flutter / Dart / Riverpod。

随后实现 Java、Node.js/TypeScript、Python、C++、Go、Rust、Vue 后端的相同 Protocol 和最小生产级 Conformance。

禁止创建只返回 placeholder 文件的“后端”。一个后端至少必须：

- 生成可解析目标源码；
- 生成完整 Build 文件；
- 运行目标 Formatter；
- 运行 Typecheck 或 Compiler；
- 生成 Source-target Map；
- 对不支持语义显式失败或登记 Gap。

### Phase 6：Native Emission 和 Toolchain

- C# 优先使用 Roslyn；
- Go 使用 `go/ast` 与 `go/format`；
- TypeScript/React/Vue 使用 TypeScript/JSX/SFC 结构化 AST；
- Python 使用 LibCST 或等价保真 AST；
- C++ 使用 Clang 结构化工具；
- 其他后端使用可验证的结构化 Builder。

源码主体禁止大规模字符串拼接。构建文件和资源模板可以使用受 Schema 验证的模板。

### Phase 7：Build、修复与 Agent

实现有界循环：

```text
emit
→ parse
→ format
→ lint
→ typecheck
→ build
→ deterministic diagnostic repair
→ repeat up to policy limit
→ restricted agent proposal if authorized
→ independent verification
```

Agent：

- 默认最多 5 个文件、300 行、3 次迭代；
- 不得修改测试、Golden、证书、策略或权限；
- 不得访问网络或 Secret；
- 只能提交结构化 Patch Proposal；
- 所有变化必须重新 Build/Test。

### Phase 8：增量再生成与 Provenance

- 实现 `managed/manual/mixed/external` 文件 Ownership；
- 实现基于 AST 的三方合并；
- 禁止覆盖无基线人工修改；
- 贯通 Batch 3→4→5 Source-target Map；
- 未映射目标声明进入 Gate。

### Phase 9：Corpus 与 Certification

- 为每个后端建立正例、负例、边界、恶意输入和大型项目 Fixture；
- 测试确定性、幂等、构建、增量生成和回滚；
- 实现 G0–G6 Certificate；
- Build Green 不得标记 Behavior Equivalent。

## 5. API、事件与持久化

严格实现 `SKILL.md` 中 API 和事件。所有长任务必须：

- 持久化状态；
- 支持 Pause/Resume/Cancel；
- 使用 Idempotency Key；
- 保存输入、输出和工具链 Digest；
- 失败后可从检查点恢复；
- 不依赖进程内内存作为唯一状态。

## 6. 测试要求

至少实现：

- Unit；
- Schema Compatibility；
- Contract；
- Integration；
- Backend Conformance；
- Sandbox Security；
- Determinism；
- Idempotence；
- Incremental Regeneration；
- Agent Policy；
- Certificate Invalidation。

运行 `tests/SCENARIOS.md` 中全部场景。

## 7. 禁止的实现捷径

- 不得把所有 TTIR 节点 `toString()` 后拼接源码；
- 不得把未知类型变成 `any`、`object` 或 `dynamic` 而不登记 Gap；
- 不得手工写 Lockfile；
- 不得用关闭 Warning、Analyzer 或测试换取 Green；
- 不得让 Agent 直接修改默认分支；
- 不得只实现一个后端却把其他后端标记为 supported；
- 不得自动更新 Golden；
- 不得伪造工具执行结果、证书、覆盖率或成功率。

## 8. 每阶段交付格式

每完成一个 Phase，输出：

```text
Implemented
Modified Files
Architecture Decisions
Tests Run
Tests Passed / Failed
Known Gaps
Security Notes
Next Phase
```

不要只描述计划；必须实际实现、运行测试并修复失败。

## 9. 完成条件

只有当 `IMPLEMENTATION_CHECKLIST.md` 中所有非豁免条目完成，并且：

- Reference Backends 构建通过；
- 其他后端通过最低 Conformance；
- Source-target Map 达到策略阈值；
- 增量再生成不覆盖人工修改；
- Agent Policy 测试通过；
- Certificate Invalidation 测试通过；
- 所有 Blocking Validation 通过；

才可以宣称 Batch 5 已完成。

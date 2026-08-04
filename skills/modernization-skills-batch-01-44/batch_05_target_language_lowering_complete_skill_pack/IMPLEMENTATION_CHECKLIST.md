# Batch 5 Implementation Checklist

> 状态值：`[ ]` 未开始，`[~]` 进行中，`[x]` 完成，`[!]` 阻断，`[-]` 经批准不适用。

## Phase 0 — 基线与兼容性

- [ ] 读取并确认 Batch 1–4 Artifact 与 Schema。
- [ ] 验证 `BATCH04_COMPATIBILITY.md` 全部 Gate。
- [ ] 建立 Source Snapshot、IR Bundle、Route Pack 和 Certificate Digest 校验。
- [ ] 形成现有仓库架构与复用清单。
- [ ] 定义多租户、权限、数据分类与审计边界。

## Phase 1 — Schema 与持久化

- [ ] Target Profile Schema。
- [ ] Target Construction Intent Schema。
- [ ] TTIR Schema 与版本演进策略。
- [ ] Generation Plan Schema。
- [ ] Backend Plugin Manifest Schema。
- [ ] Generated Artifact / Project Manifest Schema。
- [ ] Source-target Map Schema。
- [ ] Generation Certificate Schema。
- [ ] PostgreSQL 元数据表。
- [ ] Object Store 内容寻址布局。
- [ ] 事件与 Idempotency Key。

## Phase 2 — Target Profile 与 Backend SDK

- [ ] Profile Registry CRUD、版本、签名和撤销。
- [ ] Backend Protocol。
- [ ] Backend Capability Manifest。
- [ ] 插件签名、SBOM、许可证和权限检查。
- [ ] Worker Sandbox 与资源预算。
- [ ] Backend Conformance Runner。

## Phase 3 — TTIR 与 Pass Manager

- [ ] TTIR Declaration、Type、Expression、Statement。
- [ ] Framework Construct、Project、Build、Resource 节点。
- [ ] Extension Capsule 与 Opaque Intent。
- [ ] 确定性序列化。
- [ ] Pass requires/provides/preserves/invalidates。
- [ ] DAG 排序、循环检测与 Barrier。
- [ ] 并行稳定合并。
- [ ] Pause/Resume/Cancel 和检查点。

## Phase 4 — 共享 Lowering

- [ ] Idiom Policy。
- [ ] Type/Nullability/Generic/Numeric。
- [ ] Expression/Statement/Control Flow。
- [ ] Exception/Resource/Lifetime。
- [ ] Async/Concurrency/Cancellation。
- [ ] Module/Package/Project Layout。
- [ ] Build/Dependency/Toolchain。
- [ ] API/Web/DI/Serialization。
- [ ] Persistence/ORM/Transaction。
- [ ] Messaging/Scheduler/Background Job。
- [ ] Config/Secret/Observability/Resilience/Security。

## Phase 5 — Language and Framework Backends

### Reference Backends

- [ ] C# 12 / .NET 8 / ASP.NET Core 8 / EF Core 8。
- [ ] React / TypeScript / Vite。
- [ ] Flutter / Dart / Riverpod。

### Additional Backends

- [ ] Java/JVM。
- [ ] Node.js/TypeScript。
- [ ] Python。
- [ ] C++。
- [ ] Go。
- [ ] Rust。
- [ ] Vue 3。

每个 Backend：

- [ ] Target Profile validation。
- [ ] TTIR Lowering。
- [ ] Native AST/LST emission。
- [ ] Build files and dependency generation。
- [ ] Formatter。
- [ ] Linter/Typechecker/Compiler。
- [ ] Tests/Smoke command。
- [ ] Source-target Map。
- [ ] Unsupported semantics handling。

## Phase 6 — Project Generation

- [ ] 多项目 Workspace/Solution/Monorepo。
- [ ] 应用、库、测试、工具项目。
- [ ] 构建、配置、资源与运行入口。
- [ ] Secret 引用模板，不含真实 Secret。
- [ ] Health、Logging、Metrics、Tracing 基线。
- [ ] CI Build Job。
- [ ] Toolchain Lock 与 SBOM。
- [ ] Lockfile 由官方包管理器生成。

## Phase 7 — Build and Repair

- [ ] 隔离构建环境。
- [ ] 网络默认禁用。
- [ ] 恶意构建脚本防护。
- [ ] Parse/Format/Lint/Typecheck/Build Pipeline。
- [ ] 确定性 Diagnostic Repair Recipe。
- [ ] 有界修复循环和收敛检测。
- [ ] 测试/契约/Smoke Gate。
- [ ] 构建证据和日志脱敏。

## Phase 8 — Restricted Agent

- [ ] 最小 Scope Envelope。
- [ ] 文件、行数、依赖与迭代限制。
- [ ] Prompt Injection 防护。
- [ ] 禁止测试/Golden/策略/证书修改。
- [ ] Proposal-only Patch。
- [ ] 独立验证。
- [ ] 失败回滚。
- [ ] Agent-assisted 披露。

## Phase 9 — Regeneration and Provenance

- [ ] `managed/manual/mixed/external` Ownership。
- [ ] 上一生成基线保存。
- [ ] AST 三方合并。
- [ ] 人工修改保护。
- [ ] 冲突解释与人工 Gate。
- [ ] Batch 3→4→5 Source-target Map。
- [ ] 一对多、多对一、Tombstone。
- [ ] Unmapped Target Register。

## Phase 10 — Corpus and Certification

- [ ] 正例 Fixture。
- [ ] 负例 Fixture。
- [ ] Unknown/Opaque/Lossy Fixture。
- [ ] Determinism。
- [ ] Idempotence。
- [ ] Incremental Regeneration。
- [ ] Large Repository。
- [ ] Malicious Input。
- [ ] Cross-platform Build。
- [ ] G0–G6 Certificate。
- [ ] Certificate invalidation and revocation。

## Production Release Blockers

以下任一项存在时禁止发布：

- [ ] 无版本 Target Profile。
- [ ] TTIR 以代码字符串为主要表示。
- [ ] 未签名 Backend Plugin。
- [ ] Unknown 被默认成 `any/object/dynamic`。
- [ ] 有损数值或数据库映射未披露。
- [ ] 手工伪造 Lockfile。
- [ ] 构建环境可读取生产 Secret。
- [ ] Agent 可直接 Commit 或修改测试。
- [ ] 增量生成覆盖人工修改。
- [ ] Source-target Map 低于阈值。
- [ ] Build Green 被标记为行为等价。
- [ ] Blocking Verification 未通过却签证。

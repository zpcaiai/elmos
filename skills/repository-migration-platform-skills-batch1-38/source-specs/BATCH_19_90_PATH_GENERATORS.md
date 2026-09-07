# Batch 19：90 路径 Executable Generator Packs

## 总体目标

把通用转换平台落实为 90 个可单独安装、执行、验证、升级和撤销的有向 Generator Packs，每个 Pack 都能生成完整可运行项目。

## 建议仓库结构

```text
generator-pack-sdk/
source-frontends/
target-backends/
path-packs/
framework-combinations/
dependency-combinations/
complete-project-generators/
repository-corpus/
generator-benchmarks/
generator-registry/
```

## 1. Generator Pack 公共协议

- Manifest、Scope、Capabilities、Environment、Permissions、Effects、Determinism、Idempotency、Incremental/Repair/Upgrade/Rollback Modes
- Artifact Lineage、Evidence、Findings、Extension Points、Compatibility
## 2. Path-specific Compilation

- Discover→Parse→Analyze→Normalize→Lower→Plan→Emit→Reparse→Build→Verify→Package
- Type、Value、Control、Object、Error、Concurrency、Memory、Native、Framework、Dependency、Data、Protocol、Domain、Architecture Lowering
## 3. 90 Directional Packs

- 10×9 有向路径，每个 Pack 独立 Manifest、Rules、Tests、Golden/Hidden、Benchmarks 和证书
- JavaScript 为语言，Node.js 为一等后端 Runtime Profile
## 4. Frontend/Backend Executors

- 10 Source Frontends
- 10 Target Backends
- Target AST、Naming、Files、Imports、Error/Async/Resource/Framework/Data/Testability Plans
- Reparse、Semantic Roundtrip、Placeholder/Dead Code/Unused Dependency Detection
## 5. Idiomatic与完整项目生成

- Target naming/module/types/errors/async/concurrency/resources/build/testing/security/performance
- Path-level Build、Config、DB、Messaging、API、Gateway、Mesh、Deployment、CI/CD、Fuzz、Mutation、Proof、Runbook、Docs
- One-click Lifecycle 和 CP 请求
## 6. Corpus、Benchmark、Registry

- Golden、Hidden、Adversarial、Production-derived、Historical Repositories
- Correctness、Completeness、Performance、Cost、Idiomaticity、Maintainability、Repairability Benchmarks
- Version、SBOM、Signature、Transparency、Registry、90-path Matrix

## 认证体系：GP1–GP5 Executable Generator Pack

GP1–GP5 Executable Generator Pack 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- 90 Pack Manifests
- Path-specific Lowering Pipelines
- 10 Frontend/10 Backend Executors
- Framework/Dependency Profiles
- Complete Project Generators
- Golden/Hidden/Adversarial Corpus
- Benchmark Reports
- Signed Pack Bundles
- 90-path Capability Matrix
- GP1–GP5 Certificates

## 硬性原则

- A→B 支持不代表 B→A 支持
- 共享 IR 不代表所有路径使用相同 Lowering
- Pack 不能只是 Prompt 集合
- Build Success 不能掩盖 Semantic Failure
- Golden 通过不能替代 Hidden Evaluation
- Pack 证书不自动成为项目证书

## Definition of Done

```yaml
directional_packs: 90
source_frontends: 10
target_backends: 10
path_lowering: pass
complete_project_generation: pass
golden_corpus: pass
hidden_corpus: pass
adversarial_corpus: pass
critical_mutation_survivors: 0
unresolved_fuzz_crashes: 0
signed_registry_packages: pass
gp1_to_gp5: pass
```

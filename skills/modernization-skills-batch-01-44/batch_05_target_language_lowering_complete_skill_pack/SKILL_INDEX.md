# Batch 5 Skill Index

Batch 5 共包含 **34 个可独立实现、测试、版本化和认证的 Skills**。

| # | Skill | Layer | Risk | File |
|---:|---|---|---|---|
| 01 | `b05-target-generation-orchestrator` | orchestrator | critical | [target-generation-orchestrator](skills/01-target-generation-orchestrator/SKILL.md) |
| 02 | `b05-target-profile-and-platform-registry` | target-model | critical | [target-profile-and-platform-registry](skills/02-target-profile-and-platform-registry/SKILL.md) |
| 03 | `b05-target-backend-sdk-and-plugin-registry` | backend-platform | critical | [target-backend-sdk-and-plugin-registry](skills/03-target-backend-sdk-and-plugin-registry/SKILL.md) |
| 04 | `b05-target-typed-ir-schema` | target-ir | critical | [target-typed-ir-schema](skills/04-target-typed-ir-schema/SKILL.md) |
| 05 | `b05-target-lowering-plan-and-pass-manager` | pass-planning | critical | [target-lowering-plan-and-pass-manager](skills/05-target-lowering-plan-and-pass-manager/SKILL.md) |
| 06 | `b05-idiom-policy-and-pattern-selector` | idiom-selection | high | [idiom-policy-and-pattern-selector](skills/06-idiom-policy-and-pattern-selector/SKILL.md) |
| 07 | `b05-type-nullability-generics-and-numeric-lowerer` | semantic-lowering | critical | [type-nullability-generics-and-numeric-lowerer](skills/07-type-nullability-generics-and-numeric-lowerer/SKILL.md) |
| 08 | `b05-expression-statement-control-flow-lowerer` | semantic-lowering | critical | [expression-statement-control-flow-lowerer](skills/08-expression-statement-control-flow-lowerer/SKILL.md) |
| 09 | `b05-exception-resource-lifetime-lowerer` | semantic-lowering | critical | [exception-resource-lifetime-lowerer](skills/09-exception-resource-lifetime-lowerer/SKILL.md) |
| 10 | `b05-async-concurrency-cancellation-lowerer` | semantic-lowering | critical | [async-concurrency-cancellation-lowerer](skills/10-async-concurrency-cancellation-lowerer/SKILL.md) |
| 11 | `b05-module-package-project-layout-planner` | project-generation | high | [module-package-project-layout-planner](skills/11-module-package-project-layout-planner/SKILL.md) |
| 12 | `b05-build-dependency-toolchain-generator` | build-generation | critical | [build-dependency-toolchain-generator](skills/12-build-dependency-toolchain-generator/SKILL.md) |
| 13 | `b05-api-web-di-serialization-framework-backend` | framework-backend | critical | [api-web-di-serialization-framework-backend](skills/13-api-web-di-serialization-framework-backend/SKILL.md) |
| 14 | `b05-persistence-orm-transaction-framework-backend` | framework-backend | critical | [persistence-orm-transaction-framework-backend](skills/14-persistence-orm-transaction-framework-backend/SKILL.md) |
| 15 | `b05-messaging-scheduler-background-job-backend` | framework-backend | critical | [messaging-scheduler-background-job-backend](skills/15-messaging-scheduler-background-job-backend/SKILL.md) |
| 16 | `b05-config-secrets-observability-resilience-security-backend` | framework-backend | critical | [config-secrets-observability-resilience-security-backend](skills/16-config-secrets-observability-resilience-security-backend/SKILL.md) |
| 17 | `b05-java-jvm-backend` | language-backend | critical | [java-jvm-backend](skills/17-java-jvm-backend/SKILL.md) |
| 18 | `b05-csharp-dotnet-backend` | language-backend | critical | [csharp-dotnet-backend](skills/18-csharp-dotnet-backend/SKILL.md) |
| 19 | `b05-nodejs-typescript-backend` | language-backend | critical | [nodejs-typescript-backend](skills/19-nodejs-typescript-backend/SKILL.md) |
| 20 | `b05-python-backend` | language-backend | critical | [python-backend](skills/20-python-backend/SKILL.md) |
| 21 | `b05-cpp-backend` | language-backend | critical | [cpp-backend](skills/21-cpp-backend/SKILL.md) |
| 22 | `b05-go-backend` | language-backend | critical | [go-backend](skills/22-go-backend/SKILL.md) |
| 23 | `b05-rust-backend` | language-backend | critical | [rust-backend](skills/23-rust-backend/SKILL.md) |
| 24 | `b05-vue-backend` | frontend-backend | critical | [vue-backend](skills/24-vue-backend/SKILL.md) |
| 25 | `b05-react-backend` | frontend-backend | critical | [react-backend](skills/25-react-backend/SKILL.md) |
| 26 | `b05-flutter-dart-backend` | frontend-backend | critical | [flutter-dart-backend](skills/26-flutter-dart-backend/SKILL.md) |
| 27 | `b05-target-native-ast-lst-emitter` | code-emission | critical | [target-native-ast-lst-emitter](skills/27-target-native-ast-lst-emitter/SKILL.md) |
| 28 | `b05-printer-formatter-import-and-style-organizer` | code-quality | high | [printer-formatter-import-and-style-organizer](skills/28-printer-formatter-import-and-style-organizer/SKILL.md) |
| 29 | `b05-incremental-regeneration-manual-region-protector` | regeneration | critical | [incremental-regeneration-manual-region-protector](skills/29-incremental-regeneration-manual-region-protector/SKILL.md) |
| 30 | `b05-build-lint-typecheck-repair-loop` | build-verification | critical | [build-lint-typecheck-repair-loop](skills/30-build-lint-typecheck-repair-loop/SKILL.md) |
| 31 | `b05-restricted-generation-agent-controller` | agent-repair | critical | [restricted-generation-agent-controller](skills/31-restricted-generation-agent-controller/SKILL.md) |
| 32 | `b05-source-target-map-and-provenance-exporter` | provenance | critical | [source-target-map-and-provenance-exporter](skills/32-source-target-map-and-provenance-exporter/SKILL.md) |
| 33 | `b05-backend-conformance-corpus-benchmark` | testing | critical | [backend-conformance-corpus-benchmark](skills/33-backend-conformance-corpus-benchmark/SKILL.md) |
| 34 | `b05-generated-project-completeness-and-certification-gate` | certification | critical | [generated-project-completeness-and-certification-gate](skills/34-generated-project-completeness-and-certification-gate/SKILL.md) |

## 依赖主线

```text
01 Orchestrator
→ 02 Target Profile
→ 03 Backend SDK
→ 04 TTIR
→ 05 Pass Manager
→ 06–16 Shared Semantic / Framework Lowering
→ 17–26 Language and UI Backends
→ 27–29 Emission / Formatting / Regeneration
→ 30–31 Build and Agent Repair
→ 32 Provenance
→ 33 Corpus
→ 34 Certification
```

## 推荐首批 Reference Profiles

1. `java17-spring3 → csharp12-aspnet8-ef8-postgresql`
2. `vue3-typescript-vite → react-typescript-vite`
3. `vue3-typescript-vite → flutter-dart-riverpod`
4. `java17-spring3 → java21-spring3`
5. `dotnet-framework48 → dotnet8-aspnet-core`

## 风险说明

- `critical`：涉及类型、行为、构建、依赖、安全、并发、数据、Agent 或证书可信性。
- `high`：主要影响目标工程结构、惯用性、格式、可维护性和增量再生成。
- 每个 Skill 均必须在 `skills/<id>-<slug>/SKILL.md` 中实现自己的输入、输出、Hard Rules、测试和完成定义。

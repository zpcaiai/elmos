# Batch-04 Skill Index

本索引包含 **25 个独立 Skills**。

## 依赖主线

```text
Directional Mapping
→ Rule DSL
→ Static-safe Compiled Rule IR
→ Semantic Matcher and Guards
→ Recipe DAG and Dry-run Plan
→ Patch Intent and Conflict
→ Deterministic Runtime
→ Native Tool Adapters
→ COW Transaction and Incremental IR
→ Verification
→ Restricted Agent
→ Registry / Benchmark
→ Certification
```

## 01. `b04-transformation-orchestrator`

- 文件：`skills/01-transformation-orchestrator/SKILL.md`
- 层：`orchestrator`
- 风险：`critical`
- 目标：把 Batch 3 IR Bundle 与方向性 Route Pack 转换为可重放、可验证、可回滚的 Signed Patch Bundle。
- 主要输出：`transformation-plan.json`, `signed-patch-bundle.tar`, `transformation-journal.json`, `transformation-run-certificate.json`

## 02. `b04-semantic-mapping-ontology-and-registry`

- 文件：`skills/02-semantic-mapping-ontology-and-registry/SKILL.md`
- 层：`semantic-mapping`
- 风险：`critical`
- 目标：明确 exact、conditional、wrapper、lossy、unsupported 和 unknown 关系。
- 主要输出：`semantic-mapping-ontology.yaml`, `semantic-mapping-registry.json`, `mapping-conflict-register.json`

## 03. `b04-transformation-rule-dsl`

- 文件：`skills/03-transformation-rule-dsl/SKILL.md`
- 层：`rule-language`
- 风险：`critical`
- 目标：让规则显式声明适用性、读写集、分析依赖、后置条件、验证和回滚。
- 主要输出：`transformation-rule.schema.json`, `rule-language-reference.md`, `rule-meta-schema.json`, `dsl-examples/`

## 04. `b04-rule-compiler-and-static-safety-analyzer`

- 文件：`skills/04-rule-compiler-and-static-safety-analyzer/SKILL.md`
- 层：`rule-compiler`
- 风险：`critical`
- 目标：在规则执行前拒绝不安全、不确定或无法界定影响范围的变换。
- 主要输出：`compiled-rule-ir/`, `rule-static-safety-report.json`, `rule-permission-manifest.json`

## 05. `b04-semantic-matcher-query-and-binding`

- 文件：`skills/05-semantic-matcher-query-and-binding/SKILL.md`
- 层：`matcher`
- 风险：`critical`
- 目标：生成稳定排序、可重放、可解释的 Match Set 与变量绑定。
- 主要输出：`match-set.json`, `match-bindings.json`, `match-diagnostics.json`

## 06. `b04-applicability-precondition-and-guard-engine`

- 文件：`skills/06-applicability-precondition-and-guard-engine/SKILL.md`
- 层：`applicability`
- 风险：`critical`
- 目标：阻止版本、IR Level、动态语义、生成代码、许可证或业务风险不满足的规则。
- 主要输出：`guard-decision-log.json`, `applicable-match-set.json`, `guard-review-queue.json`

## 07. `b04-rewrite-operation-and-patch-planner`

- 文件：`skills/07-rewrite-operation-and-patch-planner/SKILL.md`
- 层：`patch-planning`
- 风险：`critical`
- 目标：在写入前生成完整、可冲突分析、可回滚的 Patch Plan。
- 主要输出：`patch-intent-set.json`, `patch-impact-report.json`, `patch-approval-plan.json`

## 08. `b04-deterministic-recipe-runtime`

- 文件：`skills/08-deterministic-recipe-runtime/SKILL.md`
- 层：`runtime`
- 风险：`critical`
- 目标：提供确定性可信根，并明确 Agent-assisted 运行不具生成确定性。
- 主要输出：`runtime-execution-log.json`, `deterministic-output-digest.json`, `cycle-report.json`

## 09. `b04-recipe-composition-pass-planner-and-explain`

- 文件：`skills/09-recipe-composition-pass-planner-and-explain/SKILL.md`
- 层：`planning`
- 风险：`critical`
- 目标：根据 Requires/Provides、Read/Write、Preserves/Invalidates 和验证成本规划 Pass。
- 主要输出：`transformation-plan.json`, `recipe-dag.json`, `plan-explanation.md`, `approval-gates.json`

## 10. `b04-analysis-preservation-and-incremental-recompute`

- 文件：`skills/10-analysis-preservation-and-incremental-recompute/SKILL.md`
- 层：`analysis-management`
- 风险：`critical`
- 目标：防止变换后使用 Stale Analysis，同时避免无必要全量重算。
- 主要输出：`analysis-invalidation-plan.json`, `recomputed-ir-bundle.json`, `stale-analysis-register.json`

## 11. `b04-directional-route-pack-builder`

- 文件：`skills/11-directional-route-pack-builder/SKILL.md`
- 层：`route-pack`
- 风险：`critical`
- 目标：把“Java→C#”细化为精确源目标版本、框架、运行时和工作负载路线。
- 主要输出：`directional-route-pack.yaml`, `route-integration-report.json`, `route-pack-certificate.json`

## 12. `b04-openrewrite-recipe-adapter`

- 文件：`skills/12-openrewrite-recipe-adapter/SKILL.md`
- 层：`native-adapter`
- 风险：`critical`
- 目标：把原生 OpenRewrite 结果转换为平台 PatchSet、Evidence、Journal 和 IR 失效。
- 主要输出：`openrewrite-adapter-result.json`, `openrewrite-data-tables/`, `translated-patch-set.json`

## 13. `b04-codemod-and-native-ast-adapter`

- 文件：`skills/13-codemod-and-native-ast-adapter/SKILL.md`
- 层：`native-adapter`
- 风险：`high`
- 目标：利用语言原生 AST 的生态优势，同时保持范围、类型和验证边界。
- 主要输出：`codemod-adapter-result.json`, `codemod-patch-set.json`, `formatting-diff-report.json`

## 14. `b04-compiler-rewrite-pass-adapter`

- 文件：`skills/14-compiler-rewrite-pass-adapter/SKILL.md`
- 层：`compiler-adapter`
- 风险：`critical`
- 目标：利用 Compiler Fact 与 Pass Manager，同时避免无 Source Map 的 Compiler IR 结果冒充源码补丁。
- 主要输出：`compiler-pass-result.json`, `compiler-source-edits.json`, `analysis-preservation-report.json`

## 15. `b04-cross-file-symbol-api-and-graph-rewriter`

- 文件：`skills/15-cross-file-symbol-api-and-graph-rewriter/SKILL.md`
- 层：`graph-rewrite`
- 风险：`critical`
- 目标：支持 Rename、Move、Signature Change、API Replacement 和 Adapter Introduction。
- 主要输出：`cross-file-patch-set.json`, `impact-radius.json`, `dynamic-reference-risk.json`

## 16. `b04-build-config-contract-and-sql-coordinated-rewriter`

- 文件：`skills/16-build-config-contract-and-sql-coordinated-rewriter/SKILL.md`
- 层：`coordinated-rewrite`
- 风险：`critical`
- 目标：避免只改源码而遗漏依赖、连接、事务、契约和部署。
- 主要输出：`coordinated-patch-set.json`, `cross-domain-impact-report.json`, `contract-drift-after-rewrite.json`

## 17. `b04-transformation-conflict-detector-and-resolver`

- 文件：`skills/17-transformation-conflict-detector-and-resolver/SKILL.md`
- 层：`conflict-management`
- 风险：`critical`
- 目标：禁止 Last-write-wins，使用可交换性、优先级、Barrier 或人工选择。
- 主要输出：`conflict-report.json`, `conflict-graph.json`, `conflict-resolution-decisions.json`

## 18. `b04-copy-on-write-transaction-and-rollback`

- 文件：`skills/18-copy-on-write-transaction-and-rollback/SKILL.md`
- 层：`transaction`
- 风险：`critical`
- 目标：保证原始 Snapshot 不变，并在验证失败时恢复精确状态。
- 主要输出：`transformation-transaction.json`, `workspace-snapshots/`, `patch-journal.json`, `rollback-evidence.json`

## 19. `b04-source-map-format-comment-and-provenance-preserver`

- 文件：`skills/19-source-map-format-comment-and-provenance-preserver/SKILL.md`
- 层：`provenance`
- 风险：`high`
- 目标：让评审者理解每个 Patch 来源，并防止 Formatter 噪声掩盖真实变更。
- 主要输出：`source-target-map.json`, `formatting-diff-report.json`, `comment-attachment-report.json`, `provenance-export.json`

## 20. `b04-verification-obligation-and-postcondition-runner`

- 文件：`skills/20-verification-obligation-and-postcondition-runner/SKILL.md`
- 层：`verification`
- 风险：`critical`
- 目标：建立 V0–V9 分层验证，并在无法判定时保持 inconclusive。
- 主要输出：`verification-evidence.json`, `verification-summary.json`, `blocking-failures.json`, `waiver-register.json`

## 21. `b04-restricted-agent-repair-controller`

- 文件：`skills/21-restricted-agent-repair-controller/SKILL.md`
- 层：`agent-repair`
- 风险：`critical`
- 目标：利用 Agent 处理局部胶水问题，但不让其成为可信根或扩大范围。
- 主要输出：`agent-repair-proposals.json`, `agent-policy-decisions.json`, `agent-verification-evidence.json`

## 22. `b04-agent-repair-to-rule-distiller`

- 文件：`skills/22-agent-repair-to-rule-distiller/SKILL.md`
- 层：`rule-learning`
- 风险：`high`
- 目标：把重复局部修复沉淀为可测试、可审计的规则资产。
- 主要输出：`distilled-rule-candidates/`, `distillation-corpus.json`, `privacy-review.json`, `promotion-report.json`

## 23. `b04-recipe-package-registry-and-supply-chain`

- 文件：`skills/23-recipe-package-registry-and-supply-chain/SKILL.md`
- 层：`registry`
- 风险：`critical`
- 目标：确保进入执行环境的规则包来源可信、权限最小且可撤销。
- 主要输出：`recipe-registry.json`, `package-supply-chain-report.json`, `package-certificates.json`, `revocation-list.json`

## 24. `b04-recipe-corpus-benchmark-and-regression`

- 文件：`skills/24-recipe-corpus-benchmark-and-regression/SKILL.md`
- 层：`testing`
- 风险：`critical`
- 目标：防止只测试成功案例、自动更新 Golden 或用格式变化冒充语义变换。
- 主要输出：`recipe-benchmark-report.json`, `corpus-run-evidence/`, `regression-dashboard.json`, `performance-baseline.json`

## 25. `b04-transformation-certification-gate`

- 文件：`skills/25-transformation-certification-gate/SKILL.md`
- 层：`certification`
- 风险：`critical`
- 目标：通过 RC0–RC6 和 Correctness Class 清晰表达实际验证范围。
- 主要输出：`recipe-certificate.json`, `route-pack-certificate.json`, `transformation-run-certificate.json`, `certificate-signatures/`

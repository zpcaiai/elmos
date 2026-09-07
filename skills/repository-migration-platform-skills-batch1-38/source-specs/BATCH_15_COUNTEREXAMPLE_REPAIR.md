# Batch 15：Counterexample-Guided Repair 与自演进验证

## 总体目标

把所有失败证据转换为可复现、可最小化、可定位、可竞争和可治理的修复过程，并将成功经验沉淀为规则而不降低验证标准。

## 建议仓库结构

```text
counterexample-ir/
counterexample-intake/
root-cause-engine/
repair-ir/
patch-synthesis/
rule-synthesis/
proof-repair/
validation-strengthening/
candidate-arena/
repair-knowledge-graph/
```

## 1. Unified Counterexample IR

- Differential、Mutation、Fuzz、Fault、Schedule、SMT、Symbolic、Model Checking、Lean、Production、Red Team 统一接入
- Canonicalization、Fingerprint、Semantic Dedup、Family Clustering
## 2. Reproduction 与 Minimization

- Original/Clean/Independent Replay
- Input/State/Trace/Schedule/Fault/Config/Schema/Proof Context Minimization
- Real/Spurious/Oracle Conflict/Specification Conflict 分类
## 3. Root-Cause Localization

- Earliest Divergence、Semantic/Dynamic/Causal Slicing
- Rule/Framework/Dependency/Data/Protocol/Concurrency/Test/Oracle/Formal Attribution
- Counterfactual Root-Cause Test
## 4. Repair Synthesis

- Repair Obligation：Required/Preservation/Forbidden Sets
- AST/Semantic IR/Constraint/Search/Template/E-Graph/LLM Candidate
- 10-language Patch Backends 与 Path-specific Patterns
## 5. Proof 与 Validation Repair

- Lean Open Goal 分类、Lemma Synthesis、Induction/Termination/Binding Repair
- Counterexample→Regression/Oracle/Mutation/Fuzz/Scenario
- 禁止 Theorem Weakening 和 Assumption Inflation
## 6. Candidate Arena 与 Self-Improvement

- Build、Differential、Mutation、Fuzz、Security、Performance、Formal、Shadow/Canary 竞争
- Historical Repository Mining、Rule Knowledge Graph、Negative Transfer
- R0–R5 自动化等级与 Evidence-governed Learning

## 认证体系：CR1–CR5 Counterexample-Guided Repair

CR1–CR5 Counterexample-Guided Repair 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Counterexample Registry
- Minimal Reproduction Bundles
- Root-Cause Graphs
- Repair Obligations
- Patch Candidate Sets
- Transformation Rules
- Proof Repair Bundles
- Strengthened Tests/Oracles/Mutations/Fuzz
- Rule Knowledge Graph
- CR1–CR5 Certificates

## 硬性原则

- 修复原始反例不等于修复根因
- Patch 通过当前 Test 不等于正确
- 单一项目 Patch 不得直接成为全局 Rule
- 历史经验只能生成候选
- 自演进不能修改 Trust Root 或 Certification Floor
- 高风险修复必须独立验证

## Definition of Done

```yaml
counterexample_ir: pass
independent_reproduction: pass
root_cause_engine: pass
repair_obligations: pass
candidate_arena: pass
proof_repair: pass
validation_strengthening: pass
negative_transfer_controls: pass
self_approval_findings: 0
critical_regressions_after_repair: 0
cr1_to_cr5: pass
```

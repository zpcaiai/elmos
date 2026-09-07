# Batch 14：Formal Verification 与 Proof-Carrying Migration

## 总体目标

将关键类型、状态、事务、副作用、并发、内存、权限、Tenant 和领域不变量转换为可由 SMT、Model Checker 与 Lean Kernel 机械检查的形式义务。

## 建议仓库结构

```text
formal-ir/
formal-semantics/
proof-obligations/
smt-engine/
symbolic-execution/
model-checking/
lean-specification/
proof-agents/
proof-checking/
proof-carrying-artifacts/
```

## 1. Formal Scope 与 Property Registry

- 业务自然语言 Property、Formal Specification、Owner、Scope、Assumptions
- Suitability Analyzer：完整证明/有界证明/Runtime Verification/仅测试
## 2. Formal IR 与语义

- Values、Types、Expressions、State、Transitions、Effects、Errors、Resources、Concurrency、Memory
- Small-step、Big-step、Trace、State-Machine、Transaction、Failure 与 Temporal Semantics
## 3. 自动形式分析

- SMT Encoding、Model Extraction、Unsat Core、Cross-Solver Replay
- Symbolic/Concolic Execution、Path Conditions、Counterexample Validation
- Explicit/Symbolic/Bounded Model Checking、Partial-Order Reduction、CEGAR
## 4. Refinement 与 Simulation

- Representation/Input/Output/Error/Effect/Trace Relations
- Forward Simulation、Backward Safety、Weak/Stuttering Simulation、Bisimulation
- Framework、Dependency、Transaction、Concurrency、Protocol、Domain Refinement
## 5. Lean 规格与 Proof Automation

- Formal IR→Lean Definitions/Theorems
- Leanstral/Proof Provider 生成、补全和修复 Candidate
- Theorem Lock、Assumption Lint、Axiom Audit、Placeholder Scan
## 6. Lean Kernel 与代码绑定

- Independent Kernel Replay
- Property→Theorem→Formal IR→Semantic IR→Source/Target→Artifact Binding
- Runtime Assumption Monitors、Proof-Carrying Artifact/Migration

## 认证体系：F1–F5 Formal Verification

F1–F5 Formal Verification 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Formal IR Bundles
- Operational/Trace/State-Machine Semantics
- SMT Queries and Models
- Symbolic/Model-Checking Counterexamples
- Lean Projects and Kernel Results
- Proof Binding Manifests
- PCA/PCM Bundles
- F1–F5 Certificates

## 硬性原则

- 形式证明首先回答“证明什么”
- SMT UNKNOWN/Timeout 不是 PASS
- 有界无反例不能宣传为无界证明
- Leanstral 不是可信根
- Lean Kernel 通过不代表业务规格正确
- 没有完整代码绑定不能声称代码已证明

## Definition of Done

```yaml
formal_ir: pass
smt: pass
symbolic_execution: pass
model_checking: pass
lean_specification: pass
lean_kernel_verified_only: true
proof_placeholders: 0
unapproved_axioms: 0
proof_code_binding: pass
runtime_assumption_monitoring: pass
f1_to_f5: pass
```

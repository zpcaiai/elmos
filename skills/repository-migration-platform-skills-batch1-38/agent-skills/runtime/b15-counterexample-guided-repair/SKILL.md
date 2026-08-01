---
name: b15-counterexample-guided-repair
description: >-
  Counterexample-Guided Repair与自演进验证。统一差分、Mutation、Fuzz、SMT、模型检查、Lean和生产反例，定位根因并安全生成Patch、Rule与验证补强。 Use when implementing, debugging, or evaluating Batch 15 of an evidence-governed repository migration.
---

# Batch 15：Counterexample-Guided Repair与自演进验证

## Contract Metadata

- Version: `2.0.0`
- Batch: `15`
- Risk: `critical`
- Gate: `CR1–CR5`


## Objective

统一差分、Mutation、Fuzz、SMT、模型检查、Lean和生产反例，定位根因并安全生成Patch、Rule与验证补强。

## Required Inputs

- Counterexamples；
- Artifacts/rules/tests；
- Historical repairs；
- Governance policy；

输入缺失时，登记为 `UNKNOWN`、`BLOCKER` 或 `NOT_APPLICABLE_WITH_EVIDENCE`。不得推测后宣称完成。

## Required Outputs

- Unified counterexample IR；
- Root-cause graph；
- Repair candidates；
- Transformation rules；
- Regression/Oracle/Mutation additions；
- CR1–CR5；

## Dependencies

Batch 10, Batch 13, Batch 14

依赖Artifact必须使用不可变版本和Hash；过期、暂停或撤销的证书不能满足前置条件。

## Workflow

1. 规范化与最小化反例；
2. 独立复现；
3. 因果切片和根因定位；
4. 生成多种Repair候选；
5. Candidate arena竞争；
6. 独立验证；
7. 规则泛化与历史重扫；

## Implementation Requirements

- 为所有核心对象建立稳定ID、版本、Owner、Scope和状态机；
- 所有自动化输出必须有结构化Schema、Source Map、Provenance和失败语义；
- 产生外部副作用时必须使用Batch 17 Side-Effect Ledger、Idempotency、Approval和Fencing；
- Builder、Verifier、Oracle Owner和Certificate Authority按Batch 13强隔离；
- 关键失败生成Batch 15 Counterexample，禁止只打印日志后继续；
- 所有公开Claim必须限定Artifact、版本、环境、Tenant、Region、Assumption和时间窗口。

## Required Tests

- 旧错误版本必须被Regression捕获；
- Critical repair零安全回归；
- Rule有负例和适用前提；
- 自演进不可降低标准；

额外执行：Golden、Hidden、Negative、Mutation、Fault、Security与历史事故回归中适用的测试类型。

## Verification Gate

- Gate / Certification：**CR1–CR5**；
- 独立Verifier从Clean Environment重建关键Artifact并重放Evidence；
- `PASS`、`FAIL`、`PARTIAL`、`INCONCLUSIVE`、`BLOCKED`必须严格区分；
- 总分不能抵消权限、Tenant、金额、数据完整性、安全或Safety关键Floor。

## Stop and Escalate

以下情况停止自动推进并升级人工或架构审查：

- 无法确认真实反例；
- Patch只修字面样例；
- Oracle/Theorem被弱化；

同时在以下情况立即停止：Evidence伪造、权限扩大、跨Tenant、明文Secret、未批准不可逆Effect、锁定Theorem或正式Oracle被自动修改。

## Evidence Requirements

每项关键结论至少连接：

```text
Requirement / Property
→ Source Artifact
→ Model / IR / Rule
→ Generated or Changed Artifact
→ Execution and Observation
→ Independent Oracle / Kernel Decision
→ Finding / Review
→ Certificate
```


## Executable Runtime

1. Resolve the shared runtime installed by `install.sh`, or use the package-local `scripts/migration_platform.py`.
2. Discover this Batch against an immutable Source fingerprint:

   ```bash
   python3 "$RMP_RUNTIME" prepare --batch 15 --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Read `batches/batch-15/profile.json`, `implementation-plan.json`, and `execution-plan.json`; implement each required output and populate exact argv-only execution steps.
4. Run the source-bound plan with `execute-plan`. For evidence created outside the runner, first call `ingest-artifact`, then bind its returned digest/bytes in a typed Evidence envelope passed to `record`.
5. Have a different actor execute `verify`; one subject may not satisfy distinct claims.
6. Evaluate the fail-closed gate:

   ```bash
   python3 "$RMP_RUNTIME" gate --workspace "$EVIDENCE_WORKSPACE" --batch 15 --mode local
   ```

7. Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. The distributed package keeps certificate requests/imports disabled because it ships no independent trust root; never relabel local discovery as runtime, production, or certified evidence.
## Definition of Done

- 本Batch所有Required Outputs均存在并通过Schema验证；
- 所有Critical Inputs和Outputs均有Owner、Hash、Version、Scope和Lineage；
- Required Tests及适用的Mutation/Fuzz/Fault/Security测试通过；
- Critical Findings为零，或保持阻断状态且未错误签发证书；
- 生成可机器执行的Completion Report，列出完成项、未知项、限制、风险、Evidence与后续Batch输入；
- **CR1–CR5** Gate已通过，或明确报告未达到的原因和Certificate Ceiling。

## Completion Report

```yaml
batch: 15
skill: b15-counterexample-guided-repair
status: NOT_RUN | PASS | FAIL | PARTIAL | INCONCLUSIVE | BLOCKED
artifacts: []
evidence: []
findings: []
certificates: []
unknowns: []
limitations: []
next_batch_inputs: []
```

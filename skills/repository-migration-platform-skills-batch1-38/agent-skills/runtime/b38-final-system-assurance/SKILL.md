---
name: b38-final-system-assurance
description: >-
  Final System Assurance与SA1–SA5 Certification。对Capability、业务线、Journey、数据、管理端、回归、HA、并发、性能、安全、运营和Source退休进行最终组合认证。 Use when implementing, debugging, or evaluating Batch 38 of an evidence-governed repository migration.
---

# Batch 38：Final System Assurance与SA1–SA5 Certification

## Contract Metadata

- Version: `2.0.0`
- Batch: `38`
- Risk: `critical`
- Gate: `SA1–SA5`


## Objective

对Capability、业务线、Journey、数据、管理端、回归、HA、并发、性能、安全、运营和Source退休进行最终组合认证。

## Required Inputs

- All batch evidence；
- Production stability；
- Certificate graph；
- Residual risk/waivers；

输入缺失时，登记为 `UNKNOWN`、`BLOCKER` 或 `NOT_APPLICABLE_WITH_EVIDENCE`。不得推测后宣称完成。

## Required Outputs

- SA1–SA5 certificates；
- Final system assurance report；
- Production closure certificate；
- Continuous recertification plan；

## Dependencies

Batch 21, Batch 22, Batch 23, Batch 24, Batch 25, Batch 26, Batch 27, Batch 28, Batch 29, Batch 30, Batch 31, Batch 32, Batch 33, Batch 34, Batch 35, Batch 36, Batch 37

依赖Artifact必须使用不可变版本和Hash；过期、暂停或撤销的证书不能满足前置条件。

## Workflow

1. 计算Capability Inventory完整度；
2. 验证Business/Data/Admin闭环；
3. 验证Regression/Operations闭环；
4. 验证HA/DR/Concurrency/Performance/Security；
5. 验证Target全量责任和Source退休；
6. 组合证书与持续重验；

## Implementation Requirements

- 为所有核心对象建立稳定ID、版本、Owner、Scope和状态机；
- 所有自动化输出必须有结构化Schema、Source Map、Provenance和失败语义；
- 产生外部副作用时必须使用Batch 17 Side-Effect Ledger、Idempotency、Approval和Fencing；
- Builder、Verifier、Oracle Owner和Certificate Authority按Batch 13强隔离；
- 关键失败生成Batch 15 Counterexample，禁止只打印日志后继续；
- 所有公开Claim必须限定Artifact、版本、环境、Tenant、Region、Assumption和时间窗口。

## Required Tests

- Critical业务/数据/安全/Safety Finding为零；
- 所有前置证书有效；
- 生产责任和Source退出有Evidence；
- 持续认证生效；

额外执行：Golden、Hidden、Negative、Mutation、Fault、Security与历史事故回归中适用的测试类型。

## Verification Gate

- Gate / Certification：**SA1–SA5**；
- 独立Verifier从Clean Environment重建关键Artifact并重放Evidence；
- `PASS`、`FAIL`、`PARTIAL`、`INCONCLUSIVE`、`BLOCKED`必须严格区分；
- 总分不能抵消权限、Tenant、金额、数据完整性、安全或Safety关键Floor。

## Stop and Escalate

以下情况停止自动推进并升级人工或架构审查：

- 任何Critical Scope未知；
- 组合证书Scope膨胀；
- Source仍承担未声明责任；

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
   python3 "$RMP_RUNTIME" prepare --batch 38 --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Read `batches/batch-38/profile.json`, `implementation-plan.json`, and `execution-plan.json`; implement each required output and populate exact argv-only execution steps.
4. Run the source-bound plan with `execute-plan`. For evidence created outside the runner, first call `ingest-artifact`, then bind its returned digest/bytes in a typed Evidence envelope passed to `record`.
5. Have a different actor execute `verify`; one subject may not satisfy distinct claims.
6. Evaluate the fail-closed gate:

   ```bash
   python3 "$RMP_RUNTIME" gate --workspace "$EVIDENCE_WORKSPACE" --batch 38 --mode local
   ```

7. Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. The distributed package keeps certificate requests/imports disabled because it ships no independent trust root; never relabel local discovery as runtime, production, or certified evidence.
## Definition of Done

- 本Batch所有Required Outputs均存在并通过Schema验证；
- 所有Critical Inputs和Outputs均有Owner、Hash、Version、Scope和Lineage；
- Required Tests及适用的Mutation/Fuzz/Fault/Security测试通过；
- Critical Findings为零，或保持阻断状态且未错误签发证书；
- 生成可机器执行的Completion Report，列出完成项、未知项、限制、风险、Evidence与后续Batch输入；
- **SA1–SA5** Gate已通过，或明确报告未达到的原因和Certificate Ceiling。

## Completion Report

```yaml
batch: 38
skill: b38-final-system-assurance
status: NOT_RUN | PASS | FAIL | PARTIAL | INCONCLUSIVE | BLOCKED
artifacts: []
evidence: []
findings: []
certificates: []
unknowns: []
limitations: []
next_batch_inputs: []
```

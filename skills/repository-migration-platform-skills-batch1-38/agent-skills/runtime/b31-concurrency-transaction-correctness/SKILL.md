---
name: b31-concurrency-transaction-correctness
description: >-
  Concurrency、Idempotency与Transaction Correctness。在生产并发负载和故障下验证Race、Lost Update、Isolation、Linearizability、Idempotency、Outbox/Inbox和Saga。 Use when implementing, debugging, or evaluating Batch 31 of an evidence-governed repository migration.
---

# Batch 31：Concurrency、Idempotency与Transaction Correctness

## Contract Metadata

- Version: `2.0.0`
- Batch: `31`
- Risk: `critical`
- Gate: `Concurrency & Transaction Gate`


## Objective

在生产并发负载和故障下验证Race、Lost Update、Isolation、Linearizability、Idempotency、Outbox/Inbox和Saga。

## Required Inputs

- Concurrent workload models；
- Transaction semantics；
- Schedules/faults；
- Data invariants；

输入缺失时，登记为 `UNKNOWN`、`BLOCKER` 或 `NOT_APPLICABLE_WITH_EVIDENCE`。不得推测后宣称完成。

## Required Outputs

- Concurrency schedules；
- Transaction proofs/tests；
- Idempotency evidence；
- Concurrency certification；

## Dependencies

Batch 7, Batch 9, Batch 10, Batch 14, Batch 15, Batch 29, Batch 30

依赖Artifact必须使用不可变版本和Hash；过期、暂停或撤销的证书不能满足前置条件。

## Workflow

1. 建立Actor和共享状态模型；
2. 探索Schedule；
3. 验证Isolation anomalies；
4. 验证Lease/Fencing/Single Writer；
5. 在Retry/Timeout/Cancel下验证幂等；
6. 运行Outbox/Inbox/Saga对账；

## Implementation Requirements

- 为所有核心对象建立稳定ID、版本、Owner、Scope和状态机；
- 所有自动化输出必须有结构化Schema、Source Map、Provenance和失败语义；
- 产生外部副作用时必须使用Batch 17 Side-Effect Ledger、Idempotency、Approval和Fencing；
- Builder、Verifier、Oracle Owner和Certificate Authority按Batch 13强隔离；
- 关键失败生成Batch 15 Counterexample，禁止只打印日志后继续；
- 所有公开Claim必须限定Artifact、版本、环境、Tenant、Region、Assumption和时间窗口。

## Required Tests

- Race/Lost update/Partial commit为零；
- At-most-once business effect；
- Unknown commit不盲目重试；
- 死锁有检测/恢复；

额外执行：Golden、Hidden、Negative、Mutation、Fault、Security与历史事故回归中适用的测试类型。

## Verification Gate

- Gate / Certification：**Concurrency & Transaction Gate**；
- 独立Verifier从Clean Environment重建关键Artifact并重放Evidence；
- `PASS`、`FAIL`、`PARTIAL`、`INCONCLUSIVE`、`BLOCKED`必须严格区分；
- 总分不能抵消权限、Tenant、金额、数据完整性、安全或Safety关键Floor。

## Stop and Escalate

以下情况停止自动推进并升级人工或架构审查：

- 事务边界无法恢复；
- 跨服务强原子性无方案；
- 并发测试不稳定且无法控制；

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
   python3 "$RMP_RUNTIME" prepare --batch 31 --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Read `batches/batch-31/profile.json`, `implementation-plan.json`, and `execution-plan.json`; implement each required output and populate exact argv-only execution steps.
4. Run the source-bound plan with `execute-plan`. For evidence created outside the runner, first call `ingest-artifact`, then bind its returned digest/bytes in a typed Evidence envelope passed to `record`.
5. Have a different actor execute `verify`; one subject may not satisfy distinct claims.
6. Evaluate the fail-closed gate:

   ```bash
   python3 "$RMP_RUNTIME" gate --workspace "$EVIDENCE_WORKSPACE" --batch 31 --mode local
   ```

7. Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. The distributed package keeps certificate requests/imports disabled because it ships no independent trust root; never relabel local discovery as runtime, production, or certified evidence.
## Definition of Done

- 本Batch所有Required Outputs均存在并通过Schema验证；
- 所有Critical Inputs和Outputs均有Owner、Hash、Version、Scope和Lineage；
- Required Tests及适用的Mutation/Fuzz/Fault/Security测试通过；
- Critical Findings为零，或保持阻断状态且未错误签发证书；
- 生成可机器执行的Completion Report，列出完成项、未知项、限制、风险、Evidence与后续Batch输入；
- **Concurrency & Transaction Gate** Gate已通过，或明确报告未达到的原因和Certificate Ceiling。

## Completion Report

```yaml
batch: 31
skill: b31-concurrency-transaction-correctness
status: NOT_RUN | PASS | FAIL | PARTIAL | INCONCLUSIVE | BLOCKED
artifacts: []
evidence: []
findings: []
certificates: []
unknowns: []
limitations: []
next_batch_inputs: []
```

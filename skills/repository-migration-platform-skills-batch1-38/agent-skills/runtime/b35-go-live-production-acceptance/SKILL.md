---
name: b35-go-live-production-acceptance
description: >-
  Release、Go-Live与Production Acceptance。把代码完成与允许上线分离，执行业务、数据、管理、安全、性能、可用性、运维、支持和回滚的统一Go/No-Go。 Use when implementing, debugging, or evaluating Batch 35 of an evidence-governed repository migration.
---

# Batch 35：Release、Go-Live与Production Acceptance

## Contract Metadata

- Version: `2.0.0`
- Batch: `35`
- Risk: `critical`
- Gate: `Production Acceptance Gate`


## Objective

把代码完成与允许上线分离，执行业务、数据、管理、安全、性能、可用性、运维、支持和回滚的统一Go/No-Go。

## Required Inputs

- Release candidate；
- Acceptance evidence；
- Certificates；
- Production environment；

输入缺失时，登记为 `UNKNOWN`、`BLOCKER` 或 `NOT_APPLICABLE_WITH_EVIDENCE`。不得推测后宣称完成。

## Required Outputs

- Release readiness report；
- Go/No-Go decision；
- Launch plan/hypercare；
- Production acceptance certificate；

## Dependencies

Batch 18, Batch 25, Batch 26, Batch 27, Batch 28, Batch 29, Batch 30, Batch 31, Batch 32, Batch 33, Batch 34

依赖Artifact必须使用不可变版本和Hash；过期、暂停或撤销的证书不能满足前置条件。

## Workflow

1. 验证业务/Data/Admin/Security/Performance/HA；
2. 检查环境Parity/Config/Secret/DB/Message/Provider；
3. 验证Monitoring/Alert/Runbook/Backup/Rollback；
4. 执行UAT/OAT；
5. 由Decision Board审批；
6. Launch与Hypercare；

## Implementation Requirements

- 为所有核心对象建立稳定ID、版本、Owner、Scope和状态机；
- 所有自动化输出必须有结构化Schema、Source Map、Provenance和失败语义；
- 产生外部副作用时必须使用Batch 17 Side-Effect Ledger、Idempotency、Approval和Fencing；
- Builder、Verifier、Oracle Owner和Certificate Authority按Batch 13强隔离；
- 关键失败生成Batch 15 Counterexample，禁止只打印日志后继续；
- 所有公开Claim必须限定Artifact、版本、环境、Tenant、Region、Assumption和时间窗口。

## Required Tests

- 所有P0/P1 Gate通过；
- 关键证书有效；
- 支持与On-call准备；
- 自动暂停/回滚可用；

额外执行：Golden、Hidden、Negative、Mutation、Fault、Security与历史事故回归中适用的测试类型。

## Verification Gate

- Gate / Certification：**Production Acceptance Gate**；
- 独立Verifier从Clean Environment重建关键Artifact并重放Evidence；
- `PASS`、`FAIL`、`PARTIAL`、`INCONCLUSIVE`、`BLOCKED`必须严格区分；
- 总分不能抵消权限、Tenant、金额、数据完整性、安全或Safety关键Floor。

## Stop and Escalate

以下情况停止自动推进并升级人工或架构审查：

- 存在生产Blocker；
- 配置未冻结；
- 回滚/恢复未演练；

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
   python3 "$RMP_RUNTIME" prepare --batch 35 --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Read `batches/batch-35/profile.json`, `implementation-plan.json`, and `execution-plan.json`; implement each required output and populate exact argv-only execution steps.
4. Run the source-bound plan with `execute-plan`. For evidence created outside the runner, first call `ingest-artifact`, then bind its returned digest/bytes in a typed Evidence envelope passed to `record`.
5. Have a different actor execute `verify`; one subject may not satisfy distinct claims.
6. Evaluate the fail-closed gate:

   ```bash
   python3 "$RMP_RUNTIME" gate --workspace "$EVIDENCE_WORKSPACE" --batch 35 --mode local
   ```

7. Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. The distributed package keeps certificate requests/imports disabled because it ships no independent trust root; never relabel local discovery as runtime, production, or certified evidence.
## Definition of Done

- 本Batch所有Required Outputs均存在并通过Schema验证；
- 所有Critical Inputs和Outputs均有Owner、Hash、Version、Scope和Lineage；
- Required Tests及适用的Mutation/Fuzz/Fault/Security测试通过；
- Critical Findings为零，或保持阻断状态且未错误签发证书；
- 生成可机器执行的Completion Report，列出完成项、未知项、限制、风险、Evidence与后续Batch输入；
- **Production Acceptance Gate** Gate已通过，或明确报告未达到的原因和Certificate Ceiling。

## Completion Report

```yaml
batch: 35
skill: b35-go-live-production-acceptance
status: NOT_RUN | PASS | FAIL | PARTIAL | INCONCLUSIVE | BLOCKED
artifacts: []
evidence: []
findings: []
certificates: []
unknowns: []
limitations: []
next_batch_inputs: []
```

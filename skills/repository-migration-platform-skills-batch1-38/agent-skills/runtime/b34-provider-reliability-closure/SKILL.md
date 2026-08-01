---
name: b34-provider-reliability-closure
description: >-
  External Integration与Provider Reliability Closure。为支付、身份、短信、邮件、物流、AI模型、设备等Provider建立契约、Sandbox、Webhook、幂等、对账、Failover和成本闭环。 Use when implementing, debugging, or evaluating Batch 34 of an evidence-governed repository migration.
---

# Batch 34：External Integration与Provider Reliability Closure

## Contract Metadata

- Version: `2.0.0`
- Batch: `34`
- Risk: `critical`
- Gate: `Provider Reliability Gate`


## Objective

为支付、身份、短信、邮件、物流、AI模型、设备等Provider建立契约、Sandbox、Webhook、幂等、对账、Failover和成本闭环。

## Required Inputs

- Provider inventory/contracts；
- Credentials；
- Callbacks；
- SLA/cost requirements；

输入缺失时，登记为 `UNKNOWN`、`BLOCKER` 或 `NOT_APPLICABLE_WITH_EVIDENCE`。不得推测后宣称完成。

## Required Outputs

- Provider profiles/simulators；
- Contract/fault tests；
- Reconciliation/compensation；
- Provider runbooks/certificates；

## Dependencies

Batch 7, Batch 8, Batch 10, Batch 11, Batch 12, Batch 23, Batch 25, Batch 29, Batch 30, Batch 32, Batch 33

依赖Artifact必须使用不可变版本和Hash；过期、暂停或撤销的证书不能满足前置条件。

## Workflow

1. 登记Provider能力和版本；
2. 生成Sandbox/Simulator；
3. 验证Auth/Timeout/Retry/Rate/Quota；
4. 验证Webhook签名/重放/顺序；
5. 处理Unknown outcome/对账/补偿；
6. 配置多Provider failover；

## Implementation Requirements

- 为所有核心对象建立稳定ID、版本、Owner、Scope和状态机；
- 所有自动化输出必须有结构化Schema、Source Map、Provenance和失败语义；
- 产生外部副作用时必须使用Batch 17 Side-Effect Ledger、Idempotency、Approval和Fencing；
- Builder、Verifier、Oracle Owner和Certificate Authority按Batch 13强隔离；
- 关键失败生成Batch 15 Counterexample，禁止只打印日志后继续；
- 所有公开Claim必须限定Artifact、版本、环境、Tenant、Region、Assumption和时间窗口。

## Required Tests

- 不可逆Effect有幂等和Receipt；
- Callback可去重；
- Provider Drift可检测；
- Fallback不扩大权限；

额外执行：Golden、Hidden、Negative、Mutation、Fault、Security与历史事故回归中适用的测试类型。

## Verification Gate

- Gate / Certification：**Provider Reliability Gate**；
- 独立Verifier从Clean Environment重建关键Artifact并重放Evidence；
- `PASS`、`FAIL`、`PARTIAL`、`INCONCLUSIVE`、`BLOCKED`必须严格区分；
- 总分不能抵消权限、Tenant、金额、数据完整性、安全或Safety关键Floor。

## Stop and Escalate

以下情况停止自动推进并升级人工或架构审查：

- Provider无Sandbox且无法安全测试；
- 回调身份不可验证；
- 对账数据不足；

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
   python3 "$RMP_RUNTIME" prepare --batch 34 --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Read `batches/batch-34/profile.json`, `implementation-plan.json`, and `execution-plan.json`; implement each required output and populate exact argv-only execution steps.
4. Run the source-bound plan with `execute-plan`. For evidence created outside the runner, first call `ingest-artifact`, then bind its returned digest/bytes in a typed Evidence envelope passed to `record`.
5. Have a different actor execute `verify`; one subject may not satisfy distinct claims.
6. Evaluate the fail-closed gate:

   ```bash
   python3 "$RMP_RUNTIME" gate --workspace "$EVIDENCE_WORKSPACE" --batch 34 --mode local
   ```

7. Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. The distributed package keeps certificate requests/imports disabled because it ships no independent trust root; never relabel local discovery as runtime, production, or certified evidence.
## Definition of Done

- 本Batch所有Required Outputs均存在并通过Schema验证；
- 所有Critical Inputs和Outputs均有Owner、Hash、Version、Scope和Lineage；
- Required Tests及适用的Mutation/Fuzz/Fault/Security测试通过；
- Critical Findings为零，或保持阻断状态且未错误签发证书；
- 生成可机器执行的Completion Report，列出完成项、未知项、限制、风险、Evidence与后续Batch输入；
- **Provider Reliability Gate** Gate已通过，或明确报告未达到的原因和Certificate Ceiling。

## Completion Report

```yaml
batch: 34
skill: b34-provider-reliability-closure
status: NOT_RUN | PASS | FAIL | PARTIAL | INCONCLUSIVE | BLOCKED
artifacts: []
evidence: []
findings: []
certificates: []
unknowns: []
limitations: []
next_batch_inputs: []
```

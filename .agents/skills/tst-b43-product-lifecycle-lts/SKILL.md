---
name: tst-b43-product-lifecycle-lts
description: Batch 43版本与LTS测试Skill。用于对Batch 38–45成熟产品能力执行严格、可重放、证据不可伪造的验证。
---

# U010：Batch 43版本与LTS

## Read first

- `../../../docs/test-suite-b38-45/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/test-suite-b38-45/STRICTNESS_PROFILE.md`
- `../../../docs/test-suite-b38-45/EVIDENCE_ANTI_CHEAT.md`
- `../../../test-suites/batch38-45-strict/suite.json`
- `../../../test-suites/batch38-45-strict/strict-profile.json`

## Objective

覆盖成功、边界、负向、安全、故障、重放、版本漂移、恢复、性能、隐私和证据篡改场景。

## Required inputs

- `test-suites/batch38-45-strict/suite.json`
- 精确Artifact与Environment SHA-256
- 真实或批准的隔离环境
- 独立Holdout、代表性工作负载与原始日志

## Workflow

1. 冻结Release、配置、版本矩阵、数据与时钟。
2. 从Case Catalog选择本Skill负责的P0/P1/P2用例。
3. 先执行正常与边界测试，再执行权限、故障和篡改测试。
4. 对升级、Failover、撤销、Billing与Agent副作用验证幂等、补偿和回滚。
5. 对通过结果生成Evidence Manifest，绑定原始文件Digest和Replay命令。
6. 失败保留最小反例、时间线和未裁剪日志。
7. 禁止删除失败测试、扩大Tolerance、自动更新Golden或手改Gate。
8. 运行严格Gate，证据不足时保持`failed`或`blocked`。

## Mandatory checks

- 跨租户、驻留、Secret、签名、供应链和权限
- N-1/N/N+1、混合版本、无停机升级与回滚
- SLO、Chaos、区域故障、Backup/Restore与DR
- 知识投毒、私有知识泄漏、预测漂移与校准
- Agent越权、循环、串谋、预算和Kill Switch
- Metering重复/迟到、退款、税务、分成与财务对账
- 两家独立客户与一份第三方评审

## Mandatory case set

- `B43-001`
- `B43-002`
- `B43-003`
- `B43-004`
- `B43-005`
- `B43-006`
- `B43-007`
- `B43-008`
- `B43-009`
- `B43-010`
- `B43-011`
- `B43-012`
- `B43-013`
- `B43-014`
- `B43-015`
- `B43-016`
- `B43-017`
- `B43-018`
- `B43-019`
- `B43-020`
- `B43-021`
- `B43-022`
- `B43-023`
- `B43-024`

## Verification

```bash
python3 scripts/test-suite-b38-45/validate_skill_bundle.py .
python3 scripts/test-suite-b38-45/validate_test_catalog.py test-suites/batch38-45-strict/cases/catalog.json
python3 scripts/test-suite-b38-45/validate_coverage_matrix.py test-suites/batch38-45-strict/coverage-matrix.json
python3 scripts/test-suite-b38-45/run_strict_gate.py test-suites/batch38-45-strict
```

## Stop / escalate

跨租户访问、数据丢失、签名绕过、未授权公网出口、Kill Switch失效、账单无法对账、P0未知、Evidence篡改时立即停止。

## Definition of done

全部P0/P1通过，P2达到98%；零容忍项为0；Evidence可验证和重放；客户及第三方证据满足最终门禁。

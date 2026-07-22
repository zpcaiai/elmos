---
name: tst-performance-cost-resource-regression
description: "性能成本与资源回归。验证P95/P99、吞吐、启动、内存、CPU、镜像/产物大小与CI/云成本预算。 Use for ELMOS Batch 66–80 slightly strict certification tests."
metadata:
  id: X019
  source_package: Batch 66-80 Complete
  test_profile: slightly-strict
  batch: cross
  version: 1.0.0
  status: test-ready-not-run
---
    # X019 — 性能成本与资源回归

    ## Objective

    验证P95/P99、吞吐、启动、内存、CPU、镜像/产物大小与CI/云成本预算。 覆盖成功、边界、负向、故障、重放、恢复、篡改和状态冒充。默认不得把未运行、Skipped、Mock-only或陈旧Evidence计为通过。

    ## Required Inputs

    - `test-suites/batch66-80-slightly-strict/suite.json`
    - `test-suites/batch66-80-slightly-strict/cases/catalog.json`
    - `test-suites/batch66-80-slightly-strict/coverage-matrix.json`
    - Source Package和Environment SHA-256
    - 代表性Fixture、恶意Fixture、Holdout及真实或批准隔离环境

    ## Workflow

    1. 冻结Source、Environment、Fixture、时钟、Seed和副作用权限。
    2. 选择本Skill负责的Case并验证Source Hash与Case定义未漂移。
    3. 先运行正常路径，再运行边界、负向、故障和篡改路径。
    4. 使用独立Oracle，不允许由被测生成器同时生成Expected Result。
    5. 保存未裁剪原始输出、最小反例、Artifact和Environment Manifest。
    6. 失败最多有界重放三次；不得通过删测试、扩大Tolerance或改Golden修复。
    7. 写入Result后运行Evidence和Release Gate验证。

    ## Required Tests

    ### X019-01 — 性能成本与资源回归 / P95/P99与吞吐预算

- Priority: `P1`
- Category: `performance`
- Given: 在相同代表性负载比较Baseline与Candidate
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: P95不恶化超过10%，P99与吞吐变化可见
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X019-02 — 性能成本与资源回归 / 资源峰值与泄漏

- Priority: `P1`
- Category: `resource`
- Given: 长时间运行并重复启动/关闭代表性Journey
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: CPU、内存、线程、FD和连接无持续无界增长
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X019-03 — 性能成本与资源回归 / Artifact镜像与CI成本

- Priority: `P2`
- Category: `performance`
- Given: 比较Bundle、Binary、Image大小和CI/云估算
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 未批准增长不超过15%，成本假设与测量来源可审计
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command


    ## Slightly Strict Thresholds

    - P0 100%；Critical P1 100%；普通P1至少98%；P2至少95%；
    - 零容忍项不可Waive；Flaky、Skipped、Not-run不计Pass；
    - Evidence必须绑定Source、环境、Fixture、命令、Artifact和Replay；
    - Provider/Device/Cluster/Signing/Runtime声明必须由对应真实环境证明。

    ## Verification

    ```bash
    python3 scripts/test-suite-b66-80/validate_test_catalog.py test-suites/batch66-80-slightly-strict/cases/catalog.json
    python3 scripts/test-suite-b66-80/validate_result_files.py test-suites/batch66-80-slightly-strict
    python3 scripts/test-suite-b66-80/run_slightly_strict_gate.py test-suites/batch66-80-slightly-strict
    ```

    ## Stop and Escalate

    在Source/Environment不匹配、独立Oracle缺失、真实副作用未经批准、Secret/权限/数据/签名边界被突破、Evidence被篡改或零容忍Case失败时立即停止并BLOCKED。

    ## Evidence Contract

    每项Case保留`result.json`、原始日志、Artifact Manifest、Environment Manifest、Source/Fixture Digest、时间线、重试记录、失败反例和Replay命令；通过结果不得手工编辑。

    ## Definition of Done

    本Skill全部Case已执行或以证据说明Blocked；P0/零容忍规则满足；结果可重放；门禁统计未把Skipped/Not-run/陈旧Evidence当作通过。

    ## Completion Report

    返回负责Case、环境和Source Hash、结果、反例、Evidence位置、Waiver、未支持范围和对最终Gate的影响。

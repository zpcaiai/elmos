---
name: tst-cross-platform-toolchain-runtime-matrix
description: "跨平台工具链与Runtime矩阵。验证OS、架构、编译器、SDK、Runtime和交叉编译目标，禁止未执行的支持声明。 Use for ELMOS Batch 66–80 slightly strict certification tests."
metadata:
  id: X010
  source_package: Batch 66-80 Complete
  test_profile: slightly-strict
  batch: cross
  version: 1.0.0
  status: test-ready-not-run
---
    # X010 — 跨平台工具链与Runtime矩阵

    ## Objective

    验证OS、架构、编译器、SDK、Runtime和交叉编译目标，禁止未执行的支持声明。 覆盖成功、边界、负向、故障、重放、恢复、篡改和状态冒充。默认不得把未运行、Skipped、Mock-only或陈旧Evidence计为通过。

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

    ### X010-01 — 跨平台工具链与Runtime矩阵 / 声明平台真实构建矩阵

- Priority: `P0`
- Category: `compatibility`
- Given: 对每个声明OS/架构/Compiler/SDK执行真实构建或目标Runner
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 每项支持声明绑定命令、版本与产物，未执行项为unsupported
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X010-02 — 跨平台工具链与Runtime矩阵 / 交叉编译Artifact烟测

- Priority: `P1`
- Category: `crosscompile`
- Given: 交叉编译并在匹配目标或批准模拟器启动
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 架构、动态依赖、入口和基础行为正确
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X010-03 — 跨平台工具链与Runtime矩阵 / N-1 N N+1兼容

- Priority: `P2`
- Category: `version-matrix`
- Given: 在当前及相邻工具链版本运行
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 兼容范围与失败边界明确，不将单版本结果外推
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

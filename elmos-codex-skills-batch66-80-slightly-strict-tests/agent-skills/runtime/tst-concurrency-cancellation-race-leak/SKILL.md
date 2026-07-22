---
name: tst-concurrency-cancellation-race-leak
description: "并发取消Race与泄漏。验证协程、goroutine、线程、async任务的取消、超时、背压、Race、死锁和泄漏。 Use for ELMOS Batch 66–80 slightly strict certification tests."
metadata:
  id: X009
  source_package: Batch 66-80 Complete
  test_profile: slightly-strict
  batch: cross
  version: 1.0.0
  status: test-ready-not-run
---
    # X009 — 并发取消Race与泄漏

    ## Objective

    验证协程、goroutine、线程、async任务的取消、超时、背压、Race、死锁和泄漏。 覆盖成功、边界、负向、故障、重放、恢复、篡改和状态冒充。默认不得把未运行、Skipped、Mock-only或陈旧Evidence计为通过。

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

    ### X009-01 — 并发取消Race与泄漏 / 取消与Deadline传播

- Priority: `P0`
- Category: `concurrency`
- Given: 在嵌套任务和I/O边界触发取消/Deadline
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 子任务停止、资源释放、错误可分类且无孤儿任务
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X009-02 — 并发取消Race与泄漏 / Race死锁与泄漏检测

- Priority: `P0`
- Category: `race`
- Given: 用Race Detector/Sanitizer/Stress注入竞争和阻塞
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 检测到Seeded Defect，修复后长压测无Race、死锁或持续泄漏
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X009-03 — 并发取消Race与泄漏 / 背压与有界队列

- Priority: `P2`
- Category: `backpressure`
- Given: 生产速度持续高于消费速度
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 内存与队列有界，拒绝/降级策略可见且无数据静默丢失
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

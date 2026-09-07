---
name: tst-contract-schema-compatibility-roundtrip
description: "契约Schema兼容与Roundtrip。验证OpenAPI、Proto、GraphQL、语言客户端和服务端的兼容、Roundtrip及破坏性变更。 Use for ELMOS Batch 66–80 slightly strict certification tests."
metadata:
  id: X007
  source_package: Batch 66-80 Complete
  test_profile: slightly-strict
  batch: cross
  version: 1.0.0
  status: test-ready-not-run
---
    # X007 — 契约Schema兼容与Roundtrip

    ## Objective

    验证OpenAPI、Proto、GraphQL、语言客户端和服务端的兼容、Roundtrip及破坏性变更。 覆盖成功、边界、负向、故障、重放、恢复、篡改和状态冒充。默认不得把未运行、Skipped、Mock-only或陈旧Evidence计为通过。

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

    ### X007-01 — 契约Schema兼容与Roundtrip / 多语言契约Roundtrip

- Priority: `P0`
- Category: `contract`
- Given: 用同一契约生成至少两个语言客户端并调用真实或隔离服务
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: Null、Enum、时间、字节、错误和分页语义一致
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X007-02 — 契约Schema兼容与Roundtrip / 破坏性变更拒绝

- Priority: `P0`
- Category: `compatibility`
- Given: 删除字段、改变类型/编号或收紧非空约束
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: Compatibility Gate识别Breaking Change并阻止发布
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X007-03 — 契约Schema兼容与Roundtrip / 未知字段与版本演进

- Priority: `P2`
- Category: `evolution`
- Given: 新旧客户端交叉调用带未知字段的消息
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 按声明的前后向兼容策略处理且不静默丢失关键数据
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

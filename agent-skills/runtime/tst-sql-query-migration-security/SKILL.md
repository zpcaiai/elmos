---
name: tst-sql-query-migration-security
description: "SQL查询迁移与安全。验证方言、查询语义、参数化、执行计划、迁移顺序、锁与回滚。 Use for ELMOS Batch 66–80 slightly strict certification tests."
metadata:
  id: X014
  source_package: Batch 66-80 Complete
  test_profile: slightly-strict
  batch: cross
  version: 1.0.0
  status: test-ready-not-run
---
    # X014 — SQL查询迁移与安全

    ## Objective

    验证方言、查询语义、参数化、执行计划、迁移顺序、锁与回滚。 覆盖成功、边界、负向、故障、重放、恢复、篡改和状态冒充。默认不得把未运行、Skipped、Mock-only或陈旧Evidence计为通过。

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

    ### X014-01 — SQL查询迁移与安全 / 方言语义等价

- Priority: `P0`
- Category: `sql`
- Given: 在源/目标数据库运行包含Null、Join、聚合、分页和时间的查询
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 结果集、顺序和精度符合显式Oracle
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X014-02 — SQL查询迁移与安全 / 迁移失败回滚

- Priority: `P0`
- Category: `migration`
- Given: 在DDL/DML迁移中途注入失败并重新执行
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: Schema与数据恢复到可验证状态，迁移幂等或有明确不可逆边界
- Evidence: source-snapshot, environment-manifest, raw-command-log, result-json, artifact-manifest, replay-command

### X014-03 — SQL查询迁移与安全 / 计划与性能回归

- Priority: `P2`
- Category: `query-plan`
- Given: 比较代表性数据量下的执行计划和P95
- When: 执行本Case定义的测试、故障注入和证据收集
- Then: 无未批准全表扫描或超过10%的P95退化
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

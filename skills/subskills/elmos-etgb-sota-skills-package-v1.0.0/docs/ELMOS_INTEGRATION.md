# Integrating ETGB into Elmos

## 1. 数据模型

建议为 Elmos 增加：

- `benchmark_suite`、`benchmark_case`、`benchmark_case_version`；
- `benchmark_run`、`benchmark_case_run`、`oracle_result`；
- `evidence_artifact`、`corpus_snapshot`；
- `release_candidate`、`release_gate_result`、`waiver`；
- `capability_coverage`、`failure_cluster`、`regression_link`。

所有执行记录关联 tenant、project、task、turn environment、model、skill、prompt、toolchain、workspace、input/output digest 和账单。

## 2. Harness adapter contract

生产 adapter 需要实现：

```text
prepare(case, environment)
baseline(case)
execute_source(workload)
transform_or_generate(case)
build_target()
execute_target(workload)
collect_state_and_trace()
run_oracles()
publish_evidence()
cleanup()
```

每一步必须幂等、可恢复、带 ownership/fencing token，并把副作用 checkpoint 写入数据库。

## 3. Skill routing

Orchestrator 按 `business_line` 调用专用验证 Skill，再统一调用 differential-oracle、assurance 和 release-certification。生成/转换 Agent 不得拥有修改隐藏测试和 release gate 的权限。

## 4. 缓存

缓存键至少包含：输入 digest、源 commit、目标栈、规则/Skill/model/prompt/toolchain digest、case version、Oracle version、seed 和环境。任何安全策略、Oracle 或 hidden test 变化都必须失效相关缓存。

## 5. Dashboard

按业务线展示 coverage、pass、SSER、HIR、unsupported、flake、mutation、恢复、成本、wall-clock 和 Golden Route 趋势；允许下钻到第一处差异和证据。

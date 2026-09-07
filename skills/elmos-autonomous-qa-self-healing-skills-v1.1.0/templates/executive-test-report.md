# Autonomous QA Report — {{project_id}}

## 发布结论

**{{release_decision}}**

- 快照 / 提交：{{snapshot_id}} / {{commit}}
- Required 测试：{{required_total}}
- Passed / Failed / Blocked / Flaky：{{passed}} / {{failed}} / {{blocked}} / {{flaky}}
- Critical / High 缺陷：{{critical}} / {{high}}
- 自动修复：{{patches_generated}} 个候选，{{patches_verified}} 个验证通过，{{patches_accepted}} 个已接受
- 机器实际 wall-clock：{{machine_wall_clock}}
- 初始 ETA / 误差：{{initial_eta}} / {{eta_error}}
- 人工等效时间：{{human_equivalent}}

## 关键风险

{{top_risks}}

## 需求覆盖

- Required 映射覆盖：{{mapped_coverage}}
- Required 可执行覆盖：{{executable_coverage}}
- P0/P1 可执行覆盖：{{p0_p1_coverage}}
- 覆盖缺口：{{coverage_gaps}}

## 测试结果

| 类型 | 用例 | Passed | Failed | Blocked | Flaky | 结论 |
|---|---:|---:|---:|---:|---:|---|
| 功能 | {{functional_total}} | {{functional_passed}} | {{functional_failed}} | {{functional_blocked}} | {{functional_flaky}} | {{functional_gate}} |
| UI/视觉/可访问性 | {{ui_total}} | {{ui_passed}} | {{ui_failed}} | {{ui_blocked}} | {{ui_flaky}} | {{ui_gate}} |
| 性能/负载/压力 | {{perf_total}} | {{perf_passed}} | {{perf_failed}} | {{perf_blocked}} | {{perf_flaky}} | {{perf_gate}} |
| 安全/韧性 | {{security_total}} | {{security_passed}} | {{security_failed}} | {{security_blocked}} | {{security_flaky}} | {{security_gate}} |

## 性能与容量

{{performance_summary}}

## 缺陷与自动修复

{{defect_and_patch_summary}}

## 质量门禁

{{gate_results}}

## 未解决项

{{unresolved_items}}

## 重放与证据

- 重放命令：`{{replay_command}}`
- Evidence Manifest：{{evidence_manifest}}
- 发布证书：{{certificate_ref}}


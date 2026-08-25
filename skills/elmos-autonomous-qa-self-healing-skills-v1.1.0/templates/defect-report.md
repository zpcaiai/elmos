# Defect {{defect_id}} — {{title}}

- 严重度 / 优先级：{{severity}} / {{priority}}
- 状态：{{status}}
- 影响需求：{{requirement_refs}}
- 失败测试：{{failed_test_refs}}
- 首次发现：{{created_at}}

## 用户与系统影响

{{impact}}

## 最小复现

```bash
{{reproduction_command}}
```

最小输入：{{minimal_input}}

## 根因分析

- 主根因：{{root_cause}}
- 置信度：{{confidence}}
- 代码/配置位置：{{code_refs}}
- 替代假设与反证：{{alternative_hypotheses}}

## 修复与验证

- Repair Plan：{{repair_plan_ref}}
- Patch：{{patch_ref}}
- 风险等级：{{risk_level}}
- 原失败用例：{{failing_test_result}}
- 影响回归：{{impact_regression_result}}
- 全量回归：{{full_regression_result}}

## 证据

{{evidence_refs}}


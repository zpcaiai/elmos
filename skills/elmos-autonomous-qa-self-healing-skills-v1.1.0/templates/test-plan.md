# Test Plan — {{project_id}} / {{snapshot_id}}

## 1. 结论与范围

- 执行模式：{{mode}}
- Required 需求数量：{{required_requirements}}
- 计划可执行覆盖：{{planned_executable_coverage}}
- 预计机器 wall-clock：{{eta_low}}–{{eta_high}}
- 主要风险：{{top_risks}}
- 规格阻塞项：{{spec_blockers}}

## 2. 输入快照

| 来源 | 哈希 | 状态 | 是否必需 |
|---|---|---|---|
| {{source}} | {{hash}} | {{status}} | {{required}} |

## 3. 覆盖矩阵

| 需求 | 优先级 | 功能 | API/数据 | UI | 性能/压力 | 安全/韧性 | 用例数 | 状态 |
|---|---|---|---|---|---|---|---:|---|
| {{requirement_id}} | {{priority}} | {{functional}} | {{api_data}} | {{ui}} | {{performance}} | {{security}} | {{count}} | {{status}} |

## 4. 执行策略

- 环境：{{environment_profiles}}
- 数据：{{data_profiles}}
- 浏览器/设备：{{support_matrix}}
- 并行度与资源：{{parallelism}}
- 失败/重试语义：首次失败保留；重试仅用于 Flaky 分类。
- 自动修复策略：{{repair_policy}}

## 5. 质量门禁

{{quality_gates}}


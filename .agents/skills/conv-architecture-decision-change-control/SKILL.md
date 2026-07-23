---
name: conv-architecture-decision-change-control
description: 防止继续无边界扩张，确保每项新能力有业务证据、Owner和退出条件。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-015：架构决策与范围变更控制

## Objective

防止继续无边界扩张，确保每项新能力有业务证据、Owner和退出条件。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Roadmap
- ADR
- 客户需求
- 成本和风险

## Required outputs

- Decision Log
- Scope Freeze
- Deferred Capability Register

## Workflow

1. 定义P0/P1/P2和延期标准。
2. 每项变更评估对Reference Route影响。
3. 记录决策、替代方案和Review日期。
4. 阻止无Owner功能进入内核。
5. 按季度清理失效设计。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 无商业或客户依据的P2不能进入当前Release。
- 延期项不进入认证范围。
- 决策可追溯。
- 重大变更触发回归计划。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 以Skill数量作为进度。
- 所有Edition同时实现。
- 无截止条件的探索任务。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

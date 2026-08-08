---
name: conv-migration-design-studio
description: 为架构师提供源/目标架构、映射、Wave、风险、成本和Cutover的可视化决策空间。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-022：Migration Design Studio

## Objective

为架构师提供源/目标架构、映射、Wave、风险、成本和Cutover的可视化决策空间。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Repository/Dependency Graph
- Capability Registry
- Cost和Risk模型

## Required outputs

- Design Studio数据模型
- Scenario比较
- 可批准迁移设计

## Workflow

1. 可视化Source与Target架构。
2. 支持保留/迁移/重写/退役决策。
3. 显示路线支持和未知项。
4. 生成Wave、成本、依赖与Cutover计划。
5. 将批准设计冻结为Workflow输入。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 设计变更触发影响分析。
- Unsupported能力显式。
- 方案成本与FinOps一致。
- 批准后生成不可变Snapshot。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- Design Studio直接修改生产。
- 方案无版本和审批。
- 视觉图与实际依赖图脱节。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

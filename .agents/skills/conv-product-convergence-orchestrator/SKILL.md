---
name: conv-product-convergence-orchestrator
description: 把Batch 1–45从能力全集收敛为统一内核、一条Reference Route和可验证实施计划。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-001：产品收敛与Reference Implementation总编排

## Objective

把Batch 1–45从能力全集收敛为统一内核、一条Reference Route和可验证实施计划。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- 现有Batch/Skill清单
- 产品仓库与架构图
- Design Partner候选
- 成熟产品测试结果

## Required outputs

- `product-convergence/convergence-plan.json`
- 跨域里程碑与Owner
- 阻塞项和决策日志

## Workflow

1. 盘点所有Pack、Orchestrator、Gate和重复基础能力。
2. 冻结产品内核和Reference Route。
3. 建立依赖、Workflow、Policy、Evidence与Skill治理工作流。
4. 将P0工作拆为可执行ExecPlan并绑定验收Evidence。
5. 按收敛Gate判定是否进入客户试点。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 计划覆盖CONV-002–032。
- 每个P0工作有Owner、截止条件和Evidence。
- 未实现项不得标记完成。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 没有唯一Reference Route。
- 缺少Control Plane或Private Runner Owner。
- 计划以新增功能代替收敛。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

---
name: conv-global-project-lifecycle
description: 将发现、评估、迁移、验证、上线、退役和验收统一为一条产品级状态机。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-004：统一客户项目生命周期状态机

## Objective

将发现、评估、迁移、验证、上线、退役和验收统一为一条产品级状态机。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Batch 21–28与38–45状态机
- 客户交付流程

## Required outputs

- `product-convergence/project-lifecycle.json`
- 状态迁移守卫
- SLA计时规则

## Workflow

1. 定义全局状态与异常状态。
2. 为每个状态定义进入Evidence和退出Gate。
3. 映射各Batch局部状态。
4. 实现授权迁移、回退和取消。
5. 生成状态历史和审计事件。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 非法跳转拒绝。
- 缺Evidence无法进入下一状态。
- Rollback保留历史。
- 取消和恢复幂等。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 存在多套互相矛盾的客户主状态。
- 状态可人工直接修改。
- SLA计时无统一定义。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

---
name: conv-unified-policy-engine
description: 统一代码出域、模型、工具、Runner、Extension、审批、预算、驻留和Retention决策。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-007：统一Policy Engine

## Objective

统一代码出域、模型、工具、Runner、Extension、审批、预算、驻留和Retention决策。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Batch 16、26、37、38、40、42 Policy
- 身份与数据分类

## Required outputs

- `policy-decision.schema.json`
- Policy Bundle接口
- 决策解释和Obligation执行器

## Workflow

1. 统一Subject、Resource、Action、Context模型。
2. 实现allow/deny/reason/obligation输出。
3. 定义Policy优先级和冲突裁决。
4. 把决策嵌入Workflow、Runner、Agent与Extension。
5. 实现Policy版本与决策Evidence。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- Unknown默认拒绝。
- Agent不能修改自身Policy。
- 跨区域数据访问拒绝。
- Obligation未满足时执行阻塞。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 多个Policy引擎产生冲突结论。
- 管理员可无审计绕过。
- 决策无版本和理由。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

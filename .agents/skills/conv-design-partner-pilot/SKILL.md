---
name: conv-design-partner-pilot
description: 用两个独立客户项目验证标准系统和复杂Legacy系统的产品可用性。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-030：两家Design Partner真实试点

## Objective

用两个独立客户项目验证标准系统和复杂Legacy系统的产品可用性。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- 候选客户
- Reference Route
- Security和商业协议

## Required outputs

- 两份客户Evidence
- 问题与Recipe反馈
- Reference Customer材料

## Workflow

1. 选择一标准和一复杂技术债Repository。
2. 限定P0业务切片和验收标准。
3. 通过Private Runner执行真实迁移。
4. 完成UAT、Canary和客户接管。
5. 将通用学习经脱敏评测后回馈产品。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 客户组织相互独立。
- 客户Owner签字。
- 真实生产或Production-like Canary。
- 客户私有知识不外泄。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 同一客户两个项目冒充两家。
- 平台团队代签客户验收。
- 将客户代码直接变成公共Recipe。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

---
name: conv-capability-package-metamodel
description: 统一Route、Framework、Database、Client、Cloud、Verification和Extension Pack的身份、生命周期、Owner、兼容与Evidence。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-002：统一Capability Package元模型

## Objective

统一Route、Framework、Database、Client、Cloud、Verification和Extension Pack的身份、生命周期、Owner、兼容与Evidence。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- 各Batch Pack Schema
- 现有Capability状态和Certification

## Required outputs

- `schemas/product-convergence/capability-package.schema.json`
- Capability迁移映射
- 版本化元模型ADR

## Workflow

1. 收集所有Pack公共字段与差异字段。
2. 定义统一父类型和受控扩展点。
3. 统一生命周期、Owner、依赖、Policy、Evidence和Economics。
4. 编写旧Pack到新模型的迁移器。
5. 对代表性Pack执行Round-trip验证。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- Schema向后兼容。
- 未知package_type拒绝。
- 缺Owner或版本拒绝。
- Round-trip无信息丢失。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 以自由JSON代替类型化模型。
- 破坏已有认证引用。
- 不同Pack继续使用冲突状态。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

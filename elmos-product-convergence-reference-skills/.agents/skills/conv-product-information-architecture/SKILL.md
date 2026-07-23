---
name: conv-product-information-architecture
description: 让客户围绕Assess、Plan、Migrate、Validate、Release、Operate、Retire使用产品，而非面对Batch和Skill。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-021：产品信息架构与导航收敛

## Objective

让客户围绕Assess、Plan、Migrate、Validate、Release、Operate、Retire使用产品，而非面对Batch和Skill。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- 全部用户角色和任务
- 现有UI导航
- Capability Registry

## Required outputs

- Product IA
- Role-based Navigation
- 术语和内容模型

## Workflow

1. 访谈用户任务和决策点。
2. 设计Portfolio、Projects、Migration Studio、Validation、Releases、Runners、Evidence、Marketplace、Operations、Admin导航。
3. 映射内部Batch到客户任务。
4. 定义空态、错误和权限体验。
5. 用代表性任务做可用性测试。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 新用户能完成首个Assessment。
- 客户界面不暴露内部Skill编号。
- 不同角色只见所需功能。
- 导航与Project状态一致。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- Batch成为一级导航。
- 同一对象在多个入口状态不同。
- 安全错误仅显示内部堆栈。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

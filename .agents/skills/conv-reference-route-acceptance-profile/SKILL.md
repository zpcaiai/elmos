---
name: conv-reference-route-acceptance-profile
description: 为Java/Spring到C#/ASP.NET定义唯一、精确、不可漂移的首条产品路线验收范围。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-019：Reference Route验收Profile

## Objective

为Java/Spring到C#/ASP.NET定义唯一、精确、不可漂移的首条产品路线验收范围。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- 客户场景
- 路线能力矩阵
- 技术和商业目标

## Required outputs

- `reference-route-plan.schema.json`
- Reference Acceptance Profile
- Known Limitations

## Workflow

1. 锁定语言、框架、数据库和工具版本。
2. 定义必须覆盖的业务能力。
3. 定义不支持与人工边界。
4. 设置Build/Behavior/Security/Maintainability/Cost阈值。
5. 绑定真实仓库规模和客户验收。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 版本精确无latest。
- P0场景覆盖REST/DB/Transaction/Security/Message/Cache/Scheduler。
- Unsupported显式。
- 阈值不可临时放宽。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 路线范围不断变化。
- 首条路线同时支持所有框架。
- 验收只有编译成功。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

---
name: conv-test-pyramid-real-system-classification
description: 统一Schema、Component、Integration、E2E、Production-like、Customer Acceptance和Continuous Certification层次。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-016：测试层次与真实系统分类

## Objective

统一Schema、Component、Integration、E2E、Production-like、Customer Acceptance和Continuous Certification层次。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Batch 1–45严格测试集
- 工具链和环境能力

## Required outputs

- Test Level Matrix
- Mock允许规则
- 真实系统要求

## Workflow

1. 为每个Case标记测试层级。
2. 明确哪些可Mock、必须真实或第三方执行。
3. 建立环境和数据成本预算。
4. 去除重复而保留高风险场景。
5. 将层级纳入最终Gate。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 真实编译器场景不能Mock-only。
- Cloud Apply和DR有真实/批准环境证据。
- 客户验收与内部测试分离。
- 覆盖矩阵无孤儿能力。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 所有测试都停留在Schema。
- 用Mock宣称生产能力。
- 客户测试使用开发Golden。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

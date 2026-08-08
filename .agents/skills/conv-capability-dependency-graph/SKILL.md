---
name: conv-capability-dependency-graph
description: 把前置、运行、认证、商业和可选依赖做成可计算的有向图。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-003：跨Batch Capability Dependency Graph

## Objective

把前置、运行、认证、商业和可选依赖做成可计算的有向图。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Capability Registry
- Pack依赖
- Gate依赖
- Runtime依赖

## Required outputs

- `product-convergence/dependency-graph.json`
- 影响分析API
- 撤销和过期传播规则

## Workflow

1. 为每个能力分配稳定ID。
2. 分类dependency_type和required_status。
3. 构建有向图并拒绝循环。
4. 实现认证过期、撤销和升级影响传播。
5. 输出可视化与缺失依赖报告。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 循环依赖拒绝。
- 未知节点拒绝。
- 强依赖失效导致消费者降级。
- 可选依赖不错误阻塞。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 依赖仅存在文档中。
- 撤销不传播。
- Gate可绕过前置能力。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

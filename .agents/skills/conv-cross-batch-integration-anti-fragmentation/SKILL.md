---
name: conv-cross-batch-integration-anti-fragmentation
description: 验证独立Pack和Gate组合后仍能形成一个可运行产品。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-020：跨Batch集成与防碎片化测试

## Objective

验证独立Pack和Gate组合后仍能形成一个可运行产品。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Capability Dependency Graph
- Workflow Runtime
- Policy和Evidence

## Required outputs

- Cross-Batch Integration Suite
- Contract Drift报告
- 组合Release Gate

## Workflow

1. 构建端到端业务旅程。
2. 注入跨域故障和版本漂移。
3. 验证统一身份、状态、Evidence和Policy。
4. 检测重复数据源和冲突结论。
5. 将组合测试纳入CI和Release。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- Batch 25证据可被Batch 45消费。
- Batch 37撤销传播到运行任务。
- Batch 43升级不破坏长Workflow。
- Batch 44成本来自真实执行事件。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 各Batch测试都绿但组合失败。
- 同一事实多处不一致。
- Gate只验证文件存在。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

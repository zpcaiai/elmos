---
name: conv-edition-commercial-package-simplification
description: 早期只维护SaaS、Enterprise Private Runner、Self-hosted/Air-gap三类Edition和五类标准套餐。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-031：Edition与商业套餐收敛

## Objective

早期只维护SaaS、Enterprise Private Runner、Self-hosted/Air-gap三类Edition和五类标准套餐。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Batch 13、38、44产品与成本数据
- 销售Pipeline

## Required outputs

- Edition Matrix
- `Assessment/POC/Migration Factory/Enterprise/Managed套餐`
- 支持边界

## Workflow

1. 合并低需求Edition。
2. 定义每套餐输入输出、SLA、人工服务和不包含项。
3. 映射Capability支持和成本。
4. 建立报价与验收模板。
5. 用真实订单验证再扩展Edition。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 每套餐毛利可算。
- Edition升级矩阵可测。
- 销售承诺不超Capability Registry。
- 不支持项明确。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 同时维护所有Edition组合。
- 套餐只有营销名称无验收。
- 定价不含Runner/模型/人工成本。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

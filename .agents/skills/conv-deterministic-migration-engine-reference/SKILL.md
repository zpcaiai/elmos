---
name: conv-deterministic-migration-engine-reference
description: 实现Java Semantic Model、PSP/UIR、C# Emitter、Source Map、FCM、Recipe与Diagnostic主链。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-027：确定性Migration Engine Reference

## Objective

实现Java Semantic Model、PSP/UIR、C# Emitter、Source Map、FCM、Recipe与Diagnostic主链。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Batch 2–7、21–24契约
- Reference Route Profile

## Required outputs

- 可执行Engine
- 认证Recipe集
- Compatibility Runtime预算
- 真实Build结果

## Workflow

1. 实现Source Adapter与稳定Symbol ID。
2. 生成PSP/UIR和Framework Contract。
3. 实现类型、控制流、异常、集合和基础Framework Lowering。
4. 生成C#项目和Source Map。
5. 接入真实Build/Test和Diagnostic Normalizer。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 增量与全量语义结果一致。
- 未知语义生成Obligation。
- 真实dotnet build。
- 不以dynamic/object隐藏类型。
- 生成器缺陷优先修复。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- Regex作为语义核心。
- Agent Patch代替缺失Engine能力。
- 静默丢弃Security/Transaction。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

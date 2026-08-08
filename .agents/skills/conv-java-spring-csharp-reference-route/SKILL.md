---
name: conv-java-spring-csharp-reference-route
description: 用一个10万–50万行、5–20模块真实系统证明产品主链。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-028：Java/Spring到C#/ASP.NET完整Reference Route

## Objective

用一个10万–50万行、5–20模块真实系统证明产品主链。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- Reference Acceptance Profile
- 真实Repository
- Control Plane/Runner/Engine

## Required outputs

- 完整迁移Project
- 目标Repository PR
- Behavior Evidence
- `Canary/回滚记录`

## Workflow

1. 安全接入并冻结源Commit。
2. 迁移Controller-Service-Repository-DB业务链。
3. 覆盖Security、Transaction、Message、Cache和Scheduler。
4. 完成Build/Test/Behavior/Maintainability。
5. 通过PR、Canary、Cutover、Hypercare和客户接管。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- P0业务行为100%。
- Critical Unknown为0。
- 目标Build与Startup 100%。
- Rollback演练通过。
- 客户接管通过。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 只迁移Demo Fixture。
- 没有真实数据库和副作用。
- 不经过客户Review即认证。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

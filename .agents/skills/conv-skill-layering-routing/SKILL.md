---
name: conv-skill-layering-routing
description: 将数百个Skill组织为Meta、Orchestrator、Implementation、Test/Operations四层。 用于ELMOS整体逻辑收敛、Reference Implementation实施或产品就绪认证。
---

# CONV-011：Skill分层与路由体系

## Objective

将数百个Skill组织为Meta、Orchestrator、Implementation、Test/Operations四层。

## Use when

- 需要把现有Batch 1–45能力收敛为统一产品内核；
- 需要实现或审查Reference Route、Control Plane、Private Runner或客户试点；
- 需要消除跨Batch重复、契约漂移、Evidence割裂或Skill触发冲突；
- 需要判断项目能否从“Skill OS”进入真实产品实施与客户认证。

## Required inputs

- 全部SKILL.md
- 调用日志和触发冲突

## Required outputs

- Skill Layer Map
- Meta Resolver Skill
- 层级调用规则

## Workflow

1. 分类所有Skill层级。
2. 识别同义与冲突触发。
3. 定义L0到L3路由。
4. 限制Orchestrator直接执行低层副作用。
5. 验证常见任务的唯一推荐路径。

## Implementation rules

- 先复用已有Batch能力和契约，再新增最小必要代码；
- 确定性规则、类型化Schema和保守Gate优先于Agent自由判断；
- 所有正式结论必须绑定精确版本、Digest、Owner和不可变Evidence；
- 不得通过修改状态字段、删除测试、扩大Tolerance或弱化Policy制造绿色；
- 影响客户代码、数据、权限、费用或生产流量的动作必须可回滚或补偿；
- 未知、冲突和不支持能力必须显式进入Obligation或Blocking Register。

## Verification

- 典型任务命中唯一L1。
- Meta Skill不产生业务副作用。
- 测试Skill不会被实现任务误触发。
- 弃用Skill不再路由。

通用验证命令：

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 scripts/product-convergence/run_convergence_gate.py product-convergence
```

## Stop / escalate

- 平面搜索数百个Skill。
- 同一请求触发多个互斥Orchestrator。
- 测试和生产Skill混用。

出现跨租户访问、数据丢失、Evidence篡改、未经批准的生产副作用或P0未知项时立即停止。

## Definition of done

- 输出契约和实现可由Codex在仓库中直接执行；
- 相关Schema、依赖、测试和Evidence全部通过；
- 没有静默降级、未声明副作用或悬空Owner；
- 结果已进入统一Capability Registry、Dependency Graph和Evidence Graph；
- 该Skill负责的完成条件能够被`conv-product-convergence-readiness-gate`独立验证。

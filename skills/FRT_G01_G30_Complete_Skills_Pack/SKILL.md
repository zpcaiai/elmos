---
name: frt-g01-g30-complete-platform-orchestrator
description: 编排FRT G01–G30完整大型前端仓库转换、验证、产品化和Production Closure。
version: 1.0.0
---

# FRT G01–G30 Complete Platform Orchestrator

## Objective

按机器可验证的依赖图编排G01–G30。不得跳过前置证书，不得让后续Batch反向修改前置Evidence或降低安全门禁。

## Workflow

1. 读取`manifest.yaml`和`SKILL_INDEX.md`。
2. 发现现有仓库能力和已安装Skill，避免建立平行系统。
3. 按G01→G30依赖顺序构建计划；只对受影响子图执行增量运行。
4. 对每个Batch调用其Orchestrator Skill，并验证证书Scope、Digest、Freshness和Compatibility。
5. 任何R4/R5失败立即停止生产认证；输出Gap、Owner、修复路径和下一步。
6. 只有G30 Production Closure Governor可签发最终PR证书。

## Verification

- 30个Batch和472个Skill全部可发现。
- 所有Skill ID唯一且路径存在。
- Compatibility Graph无非法循环。
- 前置证书失效能传播到所有下游证书。
- 30条方向路径均有Route Pack与验证入口。

## Stop and Escalate When

- 任何前置证书缺失、过期、撤销或Scope不匹配。
- 实际仓库与Skill假设冲突且无法确定安全迁移策略。
- 所需真实编译器、设备、Provider、证明器或独立Oracle不可用。

## Definition of Done

- G01–G30依赖图、执行计划、Evidence Graph和Certificate Graph全部完整。
- 所有Critical Gate通过。
- 最终PR5/PR6证书由唯一Production Authority签发。

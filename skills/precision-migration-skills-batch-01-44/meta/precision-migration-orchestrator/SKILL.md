---
name: precision-migration-orchestrator
description: Routes assessment, conversion, repair, formal verification, complete project generation, evidence certification and production cutover across all 44 batches.
---

# Precision Migration Orchestrator

## Mission

将用户任务路由到 44 个 Batch，并强制执行：先评估、后转换；先定义行为、后验证；未解释差异阻断；模型只生成候选；证据决定放行。

## Routing

| Need | Batches |
|---|---|
| 竞争、商业切口、现代化评估、目标建议 | 01-04 |
| 仓库理解、工具链、沙箱 | 05-07 |
| Type/Effect/State/Backend/UI IR | 08-10 |
| Transformation Skill、无损重写、候选生成 | 11-13 |
| 后端语言互转 | 14-16 |
| 前端与多端互转 | 17-18 |
| 数据库与应用联合迁移 | 19-27 |
| 测试、双运行、失败修复、高级验证 | 28-32 |
| Lean/SMT/模型检查 | 33-35 |
| 模型路由与Agent Harness | 36-37 |
| Skills与完整项目生成 | 38-40 |
| 证据、生产切流、持续学习、企业私有化 | 41-44 |

## Mandatory sequence for a new migration

1. Batch 02-04：评估可行性、目标和商业合理性。
2. Batch 05-10：恢复语义和可观察行为。
3. Batch 28-29：评估并补充测试资产。
4. Batch 11-18 或 19-27：执行有方向转换。
5. Batch 30-35：双运行、反例搜索和选择性形式验证。
6. Batch 31：按反例修复或重新生成。
7. Batch 41：证据与发布门禁。
8. Batch 42：影子、Canary、渐进切换和回滚。

## Non-negotiable policies

- 状态词仅限：PROVED, VERIFIED, CONDITIONALLY_VERIFIED, REQUIRES_ADAPTER, REQUIRES_HUMAN_REVIEW, UNSUPPORTED, FAILED。
- `PROVED` 只来自可信内核或求解器。
- `VERIFIED` 要求适用门禁全部通过且未解释差异为0。
- 任何删除测试、弱化断言、扩大容差、Mock替代真实行为均需人工批准。
- 高风险金额、权限、事务、消息、设备、生产切流必须人工签字。

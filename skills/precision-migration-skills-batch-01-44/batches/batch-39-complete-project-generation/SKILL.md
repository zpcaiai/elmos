---
name: batch-39-complete-project-generation
description: 从可执行Skills和技术选择生成前端、后端、管理端、数据、测试、部署、运维和文档闭环的完整项目。
---

# Batch 39：Complete Project Generation

## Goal

从可执行Skills和技术选择生成前端、后端、管理端、数据、测试、部署、运维和文档闭环的完整项目。

## Position in the system

- Phase: `K 从Skills生成完整项目`
- Included skills: `14`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 选择Repair/Migration/Generation模式
2. 编译Skills与架构蓝图
3. 生成/复用全部构件
4. 构建并执行验收/安全/完整性门禁
5. 输出项目、Runbook和证据

## Shared gates

- 必需Manifest项不得缺失
- 生成代码必须有对应测试或明确豁免
- 未表达的需求不得伪装为已满足

## Dispatch rules

- 当任务涉及 **complete-project-manifest** 时，调用 `skills/complete-project-manifest/SKILL.md`。
- 当任务涉及 **repository-template-registry** 时，调用 `skills/repository-template-registry/SKILL.md`。
- 当任务涉及 **architecture-blueprint-generator** 时，调用 `skills/architecture-blueprint-generator/SKILL.md`。
- 当任务涉及 **frontend-generator** 时，调用 `skills/frontend-generator/SKILL.md`。
- 当任务涉及 **backend-generator** 时，调用 `skills/backend-generator/SKILL.md`。
- 当任务涉及 **admin-generator** 时，调用 `skills/admin-generator/SKILL.md`。
- 当任务涉及 **database-generator** 时，调用 `skills/database-generator/SKILL.md`。
- 当任务涉及 **worker-and-scheduler-generator** 时，调用 `skills/worker-and-scheduler-generator/SKILL.md`。
- 当任务涉及 **security-crosscutting-generator** 时，调用 `skills/security-crosscutting-generator/SKILL.md`。
- 当任务涉及 **observability-generator** 时，调用 `skills/observability-generator/SKILL.md`。
- 当任务涉及 **ci-cd-generator** 时，调用 `skills/ci-cd-generator/SKILL.md`。
- 当任务涉及 **deployment-generator** 时，调用 `skills/deployment-generator/SKILL.md`。
- 当任务涉及 **documentation-and-runbook-generator** 时，调用 `skills/documentation-and-runbook-generator/SKILL.md`。
- 当任务涉及 **project-completeness-score** 时，调用 `skills/project-completeness-score/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `complete-project-manifest` | 定义应用、业务、数据、安全、运维、测试、部署和文档的必需构件清单。 |
| `repository-template-registry` | 登记经过构建、测试、安全和版本验证的仓库模板及兼容矩阵。 |
| `architecture-blueprint-generator` | 从 Skills、非功能要求和部署目标生成模块、边界、数据流和技术选型蓝图。 |
| `frontend-generator` | 生成用户端页面、状态、路由、API、样式、测试和构建配置。 |
| `backend-generator` | 生成 API、领域、数据、消息、任务、安全、测试和运行配置。 |
| `admin-generator` | 生成管理端、权限、审计、运营、配置和数据治理功能。 |
| `database-generator` | 生成 Schema、迁移、索引、Seed、备份、保留和数据测试。 |
| `worker-and-scheduler-generator` | 生成后台 Worker、队列消费者、定时任务、重试、幂等和监控。 |
| `security-crosscutting-generator` | 生成认证、授权、租户隔离、审计、Secret、限流和输入安全。 |
| `observability-generator` | 生成日志、指标、Trace、健康检查、告警和业务 SLI。 |
| `ci-cd-generator` | 生成构建、测试、安全、制品、部署、回滚和证据流水线。 |
| `deployment-generator` | 生成容器、编排、配置、密钥、数据库迁移、环境和发布文件。 |
| `documentation-and-runbook-generator` | 生成 README、架构、API、操作、故障、恢复和发布 Runbook。 |
| `project-completeness-score` | 按必需构件、测试、门禁、未解决项和证据计算项目完整度。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。

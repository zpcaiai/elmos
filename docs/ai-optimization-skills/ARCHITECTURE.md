# Elmos 精确 AI 优化改造系统架构 (ao.v1)

## 1. 概述与核心原则
本模块（`engines/ai-optimization-engine`）实现 `skills/subskills/elmos-ai-optimization-skills-v1.0.0.zip` 定义的 `ao.v1` 优化规格。
目标是用最少新增设施优化现有源码检索、证据化教学、差分验证与失败修复流程。

- **不增加第 9 Kernel，不增设额外 Elmos 路由**：保持 K1–K8 完整性。
- **Fail-Closed 权威边界**：所有读写操作均通过宿主授权的 `TrustedScope`，防范租户穿透与 Cartesian 笛卡尔积扩散。
- **快路径优先**：已知 path/symbol/anchor 准确定位不调用 LLM、Embedding 或 rerank，零幻觉且零推理成本。
- **有界 Agent 流程**：教学与修复流程受步骤、轮次及无进展检测硬性约束；局部完成不代表 Run 完成，更不代表生产认证。

## 2. 核心端口与组件映射

| 规格端口 | 仓库自有实现类 | 功能说明 |
|---|---|---|
| `ScopeResolver` | `elmos_ai_optimization.scope.ScopeResolver` | 鉴权与作用域解析，绑定不可变 `(repository, snapshot, generation)` 元组 |
| `RevisionCatalog` | `elmos_ai_optimization.projection.ProjectionCatalog` | 多版本生命周期 (`BUILDING` → `VALIDATED` → `PUBLISHED`) 与原子 CAS 发布 |
| `EvidenceContextService` | `elmos_ai_optimization.evidence_context.EvidenceContextService` | 精确快路径、FTS/词法检索、RRF 混合召回、Token 预算打包与 UTF-8 边界对齐 |
| `ContextCache` | `elmos_ai_optimization.cache.ContextCache` | 权限感知上下文缓存，支持 ACL 轮次作废与 Tombstone 同步击穿 |
| `AgentSubflowPort` | `elmos_ai_optimization.agent_subflow.BoundedAgentSubflow` | 有界状态机，管理教学与修复流程，防范无限循环与无进展停滞 |
| `ExecutionGateway` | `elmos_ai_optimization.execution.ExecutionGatewayBridge` | 动作意图哈希绑定、Generation 围栏拦截与未知结果对账恢复 |
| `Evaluation` | `elmos_ai_optimization.evaluation` | 排序指标 (MRR, nDCG, Recall@k)、P95 延迟百分位、接受成本与配对对照评测 |
| `SearchProjectionPort` | `elmos_ai_optimization.adapters` | Elasticsearch 与 pgvector 查询构建器，Dify 外部知识适配 |

## 3. 运行与验证
- 归档校验与安装：`python3 tooling/integrate_ai_optimization_skills.py --check`
- 核心引擎单元与集成测试：`PYTHONPATH=engines/ai-optimization-engine/src python3 -m unittest discover -s tests/ai-optimization-skills -p 'test_*.py'`
- 一键自动化：`make ai-optimization-skills`

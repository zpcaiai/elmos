# Elmos Knowledge–Skill–Model Foundry v2.0.0

> 顶级商业生产级的知识库、技能沉淀、训练数据、私有模型、证明认证、Serving、安全治理和持续演进 Skills Package。

## 包含内容

- **17 个 Meta-Skill**：仅这些在会话启动时暴露；
- **458 个原子 Skill**：按任务、租户、版本和风险从 Registry 动态发现；
- **293 个 P0 生产底座能力**、**145 个 P1 商业壁垒能力**、**20 个 P2 高级研究能力**；
- 强类型 Skill、Episode、Dataset、Evidence 与 Release JSON Schema；
- PostgreSQL 核心数据模型；
- Policy-as-Code 示例；
- Knowledge→Skill、Experience→Dataset、Train→Certify→Deploy 流水线；
- OpenTelemetry 扩展属性、E0–E5 认证门、生产上线清单；
- 每个原子 Skill 都带 `SKILL.md`、`skill.yaml`、评测契约、执行策略和实现说明。

## 最重要的产品原则

1. **知识、Skill、经验、数据集、模型权重、Evidence 严格分层。**
2. **客户数据默认只用于同租户检索与执行，不进入全局训练。**
3. **先建设 Trace、Evidence、Knowledge、Skill 与 Evals，再训练模型。**
4. **优先训练 Router、Embedder、Reranker、Verifier，再训练业务 Adapter。**
5. **确定性验证优先于模型裁判；测试通过也不等于行为等价。**
6. **生产发布是完整组合，不是单个模型；回滚也必须回滚完整组合。**
7. **所有长任务报告机器 Wall-clock ETA、成本、进度和恢复点。**
8. **自动演进只能在隔离环境、受控预算和独立认证下发生。**

## 目录

```text
manifest.yaml
ARCHITECTURE.md
CATALOG.md
skills/
  meta/                     # 启动时可见的领域 Meta-Skills
  atomic/                   # Registry 检索后按需加载的原子 Skills
registry/
  skill-catalog.yaml
  discovery-policy.yaml
schemas/
database/postgresql-schema.sql
policies/
pipelines/
observability/
certification/
roadmap/
tools/
references/
```

## 运行校验

```bash
python tools/validate_package.py
```

## 建议首批真正 Coding 的 P0 顺序

1. Foundation Contracts、Tenant Scope、Evidence Store、Policy Engine；
2. Repository Ingestion、Semantic IR、Hybrid Retrieval、Context Builder；
3. Trace/Episode、Skill Registry、Meta→Atomic Discovery、Skill Replay；
4. Dataset Bronze/Silver/Gold/Quarantine 与训练权利门；
5. Router、Embedder、Reranker、Verifier；
6. SQL 与 Spring 两条 Golden Route Adapter；
7. Model Registry、Serving Router、Metering、Wall-clock ETA；
8. Shadow、Canary、E0–E5、整体回滚和私有部署。

## 上线判断

`certification/PRODUCTION-READINESS.md` 是硬门。即使所有功能测试通过，只要租户隔离、数据权利、行为等价、安全红队、长稳、恢复、计费对账或自动回滚任一项未通过，就不能声称可正式上线。

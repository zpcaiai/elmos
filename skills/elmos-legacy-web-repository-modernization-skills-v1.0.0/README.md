# Elmos Java Legacy Web Repository Modernization Skills Package v1.0.0

面向 Elmos 的商业级、生产级仓库现代化能力包。它把 **Struts 1 / Struts 2 / 原生 Servlet/JSP / 混合式 Legacy Java Web 仓库**迁移到 **Spring Boot 4**，目标不是“能编译”，而是：

> 在可解释证据基础上恢复源系统的运行时语义，生成目标系统，并以差分执行证明行为等价；对无法证明的部分显式计入未知语义债务，最终签发 E0–E5 认证。

## 这个包真正新增的 Elmos 能力

它把 Elmos 从“代码转换器”提升为 **Repository Semantic Compiler（仓库语义编译器）**：

```text
Repository Snapshot
        │
        ▼
Repository Forensics
(build / modules / frameworks / runtime / effective config / routes)
        │
        ▼
Repository Evidence Graph
(source + config + tests + traces + DB/effects + decisions)
        │
        ▼
Legacy Web Semantic IR
(endpoint / pipeline / binding / state / view / security /
 transaction / side effect / deployment / concurrency)
        │
        ▼
Migration Planner
(preserve-first / waves / compatibility shims / packaging / cutover)
        │
        ▼
Deterministic Transformation
(AST + symbol + structured config + constrained generation)
        │
        ▼
Differential Verification
(HTTP + view + session + DB + effects + security + concurrency)
        │
        ▼
Bounded Auto-Repair
        │
        ▼
E0–E5 Evidence-backed Certification
```

## 包含内容

- **55 个可组合 Skills**：覆盖控制面、仓库取证、语义恢复、IR、规划、转换、验证、自动修复、切流和认证。
- **8 个 JSON Schema**：约束 Evidence Graph、Semantic IR、行为契约、迁移计划、等价报告、认证包、检查点和机器 ETA。
- **8 组强制策略**：语义不变量、门禁、归一化、风险、安全模式、修复边界、缓存失效和工具权限。
- **6 组框架映射**：Struts1、Struts2、Servlet、部署描述符、JSP/Taglib、javax→jakarta。
- **差分测试目录与 Golden Route 基准矩阵**。
- **PostgreSQL 持久化模型**：适合大型仓库长任务、证据图、IR、change set、验证、修复、成本和认证。
- **OpenRewrite/AST recipe 描述、兼容层模板、运行清单和报告模板**。
- **自校验工具**：检查 skill DAG、文件完整性、JSON/YAML、引用和哈希。

## 目录

```text
.
├── SKILL.md
├── package.yaml
├── README.md
├── CHANGELOG.md
├── REFERENCES.md
├── docs/
├── skills/
│   ├── control-plane/
│   ├── repository-forensics/
│   ├── semantic-recovery/
│   ├── semantic-model/
│   ├── planning/
│   ├── transformation/
│   ├── verification/
│   └── repair-certification/
├── schemas/
├── policies/
├── mappings/
├── recipes/
├── templates/
├── examples/
├── acceptance/
├── database/
└── tools/
```

## 默认执行模式

```yaml
mode: preserve-first
target:
  springBoot: "4.x"
  springFramework: "7.x"
  jakartaEE: "11"
  servlet: "6.1"
  java: 21
viewStrategy: preserve
securityMode: preserve
equivalenceMode: strict
```

默认不把以下变化混入同一波次：

- JSP→React/Vue/Thymeleaf
- 领域模型重构
- 数据库 Schema 重构
- API 重新设计
- 安全策略增强
- 大规模包名/模块重构

它们可以由后续独立 wave 执行，并以 `allowedDelta` 明确记录。

## 快速接入 Elmos

1. 将本目录放入 Elmos 的 skills registry，例如：

   ```text
   elmos/skills/java-legacy-web-repository-modernization/
   ```

2. 注册 `package.yaml`，入口为：

   ```text
   skills/control-plane/00-modernization-orchestrator/SKILL.md
   ```

3. Elmos 任务 API 传入 `examples/run-manifest.example.yaml` 对应字段。

4. 在 CI 中运行：

   ```bash
   python3 tools/validate_package.py .
   ```

5. 先执行 `scan/model/plan` 只读阶段，再允许 `transform` 写入工作树。

## 推荐的任务状态机

```text
CREATED
  → SNAPSHOTTING
  → FORENSICS
  → SEMANTIC_RECOVERY
  → IR_BUILT
  → PLANNED
  → TRANSFORMING
  → BUILDING
  → VERIFYING
  → REPAIRING (0..N)
  → E4_VERIFIED
  → CUTOVER_READY
  → E5_CERTIFIED
```

任意阶段可进入：

```text
PAUSED | CANCEL_REQUESTED | CANCELLED | ROLLBACK | FAILED | BLOCKED_UNKNOWN
```

## 强制设计原则

1. **仓库是一个可执行系统，而不是文件集合。**
2. **有效行为来自代码、配置、容器、环境、状态和外部副作用的合成。**
3. **所有语义都必须有证据、置信度和环境边界。**
4. **无法证明就是 unknown，不能用看似合理的生成结果代替。**
5. **编译、启动、测试通过都不等于行为等价。**
6. **forward、redirect、include、error dispatch、action chain 是不同语义。**
7. **执行顺序、短路、after/unwind 与实例生命周期属于一等语义。**
8. **关键安全、session、事务、数据库写入和外部副作用必须达到 100% 证据门。**
9. **自动修复必须最小、有界、可证伪、可回滚。**
10. **Elmos ETA 只报告机器 wall-clock；人工等待单列。**

## 认证等级

| 等级 | 含义 |
|---|---|
| E0 | 仓库与运行拓扑已盘点 |
| E1 | Evidence Graph 与 Semantic IR 完成 |
| E2 | 目标仓库可构建 |
| E3 | 目标系统可启动并通过基础集成验证 |
| E4 | 行为差分达到策略门，关键路径有证据 |
| E5 | 安全、性能、可运维、切流/回滚和未知语义门全部通过，可生产认证 |

## 商业 Golden Route 最低标准

- 至少 3 个授权的真实大型仓库，均 >500k LOC；
- 至少 1 个 >1M LOC；
- 覆盖 Struts1、Struts2、Servlet/JSP 和混合框架；
- 至少一个外置企业容器/JNDI/多模块 WAR 或 EAR 场景；
- 关键路径的 route/session/security/transaction/DB side effect 证据覆盖 100%；
- 生产认证不允许 critical unknown；
- 保存 wall-clock、模型/工具成本、cache hit、首轮通过率、修复轮数和人工决策数。

## 注意

这个包是 **implementation-ready specification + orchestration package**，包含契约、Schema、策略、技能和模板；它不是已经编译完成的 Struts→Spring 转换器二进制。Elmos 主仓仍需按 `docs/implementation-roadmap.md` 实现解析器、IR store、rewrite engine、runtime probes 和 differential harness。

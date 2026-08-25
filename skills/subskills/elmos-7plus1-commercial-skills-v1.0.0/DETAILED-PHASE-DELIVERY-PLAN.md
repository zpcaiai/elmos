# Phase 0–4 详细交付计划

本计划按能力成熟度和证据门推进，不给出脱离仓库与团队现状的虚假时间承诺。每项任务在执行时由 P00/P04 生成系统机器 ETA、人工工作量和成本区间。

## Phase 0 — 合同、基线与商业治理

### 目标

建立不会随某个 Harness/模型变化而崩塌的产品骨架，形成可测量的 current baseline。

### Workstreams

| Workstream | 关键任务 | 交付物 | Gate |
| --- | --- | --- | --- |
| Source & License | 固定所有来源 Pin；核验 LICENSE/NOTICE/安全公告；定义更新策略 | Source Manifest、SBOM policy、Adapter adoption decision | 所有直接依赖可追溯且可回滚 |
| Contract Vocabulary | 冻结 Tenant/Project/Job/Run/Session/Task/Capability/Requirement/Evidence/Route/Rule | JSON Schema、错误码、事件词汇、兼容策略 | Contract tests 通过 |
| Repository Record | 建 AGENTS 地图、docs tree、ADR、ExecPlan、Runbook、owner、新鲜度检查 | Repository knowledge system | 文档无冲突 authoritative source |
| Architecture Governance | 分层、依赖方向、公共 API、禁止访问、Schema drift | Structural lint/gates | 关键不变量机械化 |
| Benchmark Baseline | 选定生成/转换样例，建立 direct model / general harness / Elmos 对照 | Benchmark corpus v0、metric definitions | 基线可复现且全失败入分母 |
| Commercial Control | Tenant、quota、cost、ETA、billing、SLA、support tier | Control-plane spec | 计量与租户隔离测试设计完成 |
| Security | Threat model、数据分类、凭据、sandbox、approval、supply chain | Security baseline | Critical threat 有控制与 owner |

### Phase 0 Exit

- 7+1 包依赖无循环，公共合同已版本化。
- P05 的完成语义先于任何自动生成能力完成定义。
- 至少一个源仓库和一个项目生成需求有 baseline 结果和失败清单。

## Phase 1 — 可信理解、验证与执行底座

Phase 1 不是简单按 P02→P05→P01 串行；三者并行开发，但以 **Repository Intelligence → Evidence Semantics → Runtime Conformance** 的 Gate 顺序收敛。

### P02 Repository Intelligence

1. Inventory：100% 文件分类、构建/部署入口、生成器和 blind spots。
2. Language packs：首批 Java/TypeScript/SQL/YAML，随后扩 Go/Rust/Python/C#。
3. AST/Symbol/LSP：稳定 symbol IDs、definition/reference/implementation、diagnostics。
4. Program/Platform Graph：call/data/control/side effects + API/DB/MQ/cache/cron/auth/config。
5. Semantic IR：事务、并发、异常、权限、精度、生命周期和副作用不可丢。
6. Capability Ledger：稳定 CAP ID、风险、依赖、provenance、confidence、unknown gap。
7. Incremental analysis：内容寻址、影响闭包、全量等价抽样。

### P05 Verification Harness

1. Requirement/Capability 状态机与非法转移检查。
2. Completion Gate：P05 唯一写 COMPLETED。
3. Verification Planner：从 change/capability graph 生成测试 DAG。
4. Build/static/architecture/contract pipeline。
5. Source/target Differential Runtime 和可观察副作用模型。
6. Property/metamorphic/fuzz/mutation/failure injection。
7. Repair Loop、无进展上限、Evidence Bundle、E1–E5。

### P01 Harness Runtime

1. Harness SPI/Adapter SDK 与 native reference runtime。
2. Event-sourced Session、turn boundary、Context Epoch、fork/resume/replay。
3. Tool Runtime、Schema、Hooks、并发、超时、取消、规范化结果。
4. Sync/background/deferred task 与跨进程 settle。
5. Continuable subagent、lineage、direct-parent authorization。
6. Permission/Approval/Sandbox/Credential Broker。
7. Compaction、Readiness、Headless OpenAPI/SSE/SDK。
8. DeepSeek/OpenCode/OpenHarness 中至少一个外部 Adapter 通过 conformance。

### Phase 1 Vertical Slice

选择 Spring Boot + Vue + MySQL + Redis + RabbitMQ 样例：

- 扫描出 Controller/Service/Repository 及 Transaction/MQ/Cron/Auth/Cache/Config。
- 建 Repository Graph、IR 和 Capability Ledger。
- 生成一个受控目标模块。
- 运行 compile/contract/differential，发现至少一个故意注入的隐藏 gap。
- Repair 后通过 Evidence Gate，并验证 Session 崩溃恢复和无重复副作用。

### Phase 1 Exit

- Critical blind spot=0，unknown gap 可计算。
- Session、Tool、Subagent、Sandbox、Approval 可回放且 fail closed。
- 任务不能通过文本声明绕过 Completion Gate。

## Phase 2 — 商业项目生成、跨库转换和软件工厂

### P03 Project Generation & Transformation

- Requirement Expander + Archetype baseline：SaaS、支付、电商为首批。
- Architecture Synthesizer + ADR + Implementation DAG。
- Rule/Mutation/Scenario/Evidence DSL。
- 首批转换路径：Spring→Go/Rust/.NET；Vue→React；MySQL→Postgres；RabbitMQ→Kafka。
- Target emitters、source maps、framework adapters、infra/operations generator。
- Unsupported Semantics Manager 与 Strangler/shadow/dual-run/cutover/rollback。

### P04 Agent Orchestration

- Tracker Adapter + WORKFLOW Compiler + Reconciliation Scheduler。
- Task DAG、worktree isolation、workspace hooks 与 durable Workpad。
- Analyst/Explorer/Scout/IR/Planner/Generator/Reviewer/Verifier/Gap/Repair/Security/Perf 角色。
- 全局/租户/项目/状态/模型/工具并发准入。
- Retry/backoff/stall/doom-loop/escalation。
- PR feedback sweep、Proof-of-Work、Human Review/Handoff。

### P06 Intelligent Router

- Model/Provider Catalog 与真实健康/价格/能力 snapshot。
- Task Profile 和硬约束：ZDR、数据收集、地区、BYOK、context、tools、schema、modalities、budget。
- Benchmark prior + endpoint availability gate + Elmos TaskFit。
- Multi-objective route、fallback/circuit breaker/shadow/hedging/escalation。
- Long-context Completeness Auditor 与 Multimodal UI Verifier。
- 多轮总 usage/cost/cache 与系统墙钟 ETA。

### Phase 2 Commercial Scenarios

1. 从需求生成可部署多租户 SaaS：Auth/RBAC/tenant/audit/billing/observability/backup/DR/CI/CD 全闭环。
2. Java+Vue 整库转换：API/DB/MQ/cache/cron/auth/transaction 行为等价。
3. Web→微信/支付宝/抖音/小红书小程序：关键用户 journey、平台 API、权限和视觉行为验证。
4. Legacy Spring 渐进现代化：shadow→1%→10%→50%→100%，阶段 Gate 和自动回滚。

### Phase 2 Exit

- 核心场景达到 E3，指定低风险场景达到 E4。
- 真实成本、系统 ETA、人工介入和质量均可按任务/模型/Provider 解释。
- Generator 与 Verifier 分权，自动合并/发布受 Human/P05 Gate 控制。

## Phase 3 — 学习飞轮

### 可信数据入口

只有 P05 verified + scope/consent accepted 的结果进入学习：

- Transformation Rule candidate。
- Project Archetype capability delta。
- Failure/Root Cause/Repair Trace。
- Benchmark/Evidence Corpus。
- Verified Route Outcome。

### 规则生命周期

`EXPERIMENTAL → CANDIDATE → VALIDATED → TRUSTED → CERTIFIED → DEPRECATED`

每次晋升要求跨项目、跨版本、负向、边界和回归证据。撤销证据、框架漂移或生产失败会自动降级。

### 专项模型顺序

1. Rule Selector。
2. Repair Ranker。
3. Gap Detector。
4. Verification Planner。
5. Semantic Mapper。
6. Completeness Predictor。

专项模型先 shadow，再 canary；始终受 Rule Engine 和 P05 Gate 约束。

### Phase 3 Exit

- 一次失败可生成结构化 Repair Trace，且相似问题复用后质量/成本改善可测。
- Tenant-private/organization/global scope 与删除流程通过测试。
- 规则晋升和降级不会造成无证据的生产变化。

## Phase 4 — 企业 GA 与 E1–E5

### Enterprise Foundation

- SSO/RBAC/SCIM、审计、WORM evidence、私有部署/BYOK/ZDR、区域和保留政策。
- 多租户容量、配额、计费、收入/成本/毛利对账。
- 多可用区、备份/恢复、DR、升级、rollback、kill switch。
- SLA/error budget、支持流程、客户 Dashboard、合规与第三方审计。

### Production Certification

- 每个支持矩阵明确认证等级，不做“所有语言/所有仓库 95%”泛化承诺。
- E4/E5 需要客户场景、长期运行、迁移/回滚、性能、安全和残余风险证据。
- 生产监控反馈进入 P05/P07，但不自动改变 certified rules。

### Phase 4 Exit

商业 GA Checklist 全部 Critical 项通过；指定客户试点的 canary、rollback、DR 和 E4/E5 证据获得签署。

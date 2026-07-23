# ELMOS

ELMOS（Enterprise Legacy Modernization Operating System）是证据驱动的企业代码库现代化与跨语言迁移平台。跨语言路线采用“源语言语义适配器 → 统一语义中间表示（UIR）→ 目标语言生成器 → 框架 Recipe/Agent 修复/验证门禁”，避免维护十二条相互独立的语言对翻译链路。

Polyglot Repository Intake 支持 Java、Python、C#、JavaScript/TypeScript。`modules/semantic` 实现 PSP v1；`modules/uir` 实现多视图 UIR、Dialect、Effect/Obligation/Provenance 与模块门禁；`modules/skeleton` 实现四语言目标 Profile、模块/命名/构建规划和 Skeleton-first 契约仓库；`modules/lowering` 实现 Faithful-first 方法体计划、规则/能力治理、静态验证后惯用化、安全 Patch 与 L-A 至 L-D 门禁；`modules/dependency-migration` 实现实际 API 使用驱动的候选映射、供应链/构建验证、Adapter/Runtime/Boundary 策略与 D-A 至 D-D 门禁。每批都 fail-closed：缺少权威分析器、UIR 资格、隔离构建证据、原生 Emitter/Compiler、依赖解析或差分验证后端时不会推进。

跨语言 Batch 12 在 `modules/enterprise-platform` 增加企业级多租户交付裁判：复用既有 Tenant、IAM、Runner、Model、计费、审计和数据治理权威，独立验证共享 SaaS、专属 Runner、混合 Private Runner、Self-hosted 与完全 Air-gapped 五种模式，并执行 T-A 至 T-G 非补偿门禁。该控制层只裁决外部证据，不执行客户代码或生产操作。

跨语言 Batch 13 在 `modules/commercial-loop` 增加企业商业闭环裁判：以 EMCOM 统一销售、发现、方案、合同、入驻、交付、客户成功/支持和伙伴/收入运营，覆盖六种商业 Motion，并通过七个外部 Authority 顺序执行 B13-A 至 B13-G。它复用 V10 商业权威，不执行 CRM、CPQ、合同、开票、支付、伙伴结算或生产操作。

跨语言 Batch 14 在 `modules/ecosystem-growth` 增加 PEGM 产品与生态增长裁判：以 Monthly Verified Migration Value 连接 Acquisition、Activation、Adoption、Retention、Expansion、Advocacy、Ecosystem 七个增长域和产品、内容、社区、Marketplace、区域五个飞轮，通过七个外部 Authority 顺序执行 G14-A 至 G14-G。完整 Skills 401–460、12 类报告和 69 张核心表均按权威规格实现；控制层不执行身份、消息、发布、安装、支付、Moderation、法律或区域操作，所有制品保持 `external_operation_executed=false`。

公司系列 Batch 15–18 在 `modules/company-series` 继续实现权威 Skills 461–745：COGS 通过 C15-A 至 C15-G 管理战略、组织、财务、资本、风险和董事会；AI-native operating system 通过 AI16-A 至 AI16-G 管理 Human/Agent 责任、有界自主、模型风险和安全停止；VSP 四层模型通过 V17-A 至 V17-G 管理共享内核、七行业包、地区覆盖层和客户扩展；GITM 通过 M18-A 至 M18-H 管理 Day 1、组合发现、身份/数据整合、迁移 Wave、TSA、退役和经财务确认的协同。四批均为只读证据裁判，不执行公司、Agent、监管、生产或并购动作。

Java/Spring 专用现代化链路已覆盖 Batch 1–10；Batch 11/12 在同一企业控制面上增加独立 .NET 10 与 Python 3.14 执行引擎；Batch 13 增加跨语言 Composite Orchestrator；Batch 14–21 依次增加 Frontend Client、Database Data、Infrastructure、Security & Compliance、Test Quality、Mainframe、Enterprise Integration 和 Enterprise Suite 执行域；Batch 22–26 增加 Software Delivery Platform、AI Platform、Edge/IoT/Industrial、Operations/SRE/ITSM 与 Enterprise Architecture 执行域。十六个统一路由执行域共享 Tenant、权限、工作流、Runner、Evidence、计费、审计、SCM、交付与回滚；Composite 层只编排系统门禁，不执行源码转换、Provider 管理命令、主机 Job、OT 命令或生产切换。

首期源栈覆盖 Maven/Gradle、Java 8/11/17/21 和 Spring Boot 2.x/3.x；策略目标支持 Java 17/21/25。OpenRewrite 承担确定性转换；Coding Agent 只处理验证后的长尾问题。客户代码不得在控制平面进程内执行。

## Project Synthesis and Language Packs Batch 46–95

ELMOS 也支持绿色项目合成：仓库级 `$elmos-project-synthesis` Skill 将自然语言请求整理为带来源、假设、问题、验收标准和审批哈希的规格，再由 `engines/project-synthesis-engine` 生成可运行的 Java 21 / Spring Boot、Python 3.12 / FastAPI 和 C# / .NET 10 / ASP.NET Core 项目。生成器只接受已批准且未被篡改的规格，保护用户修改，并输出配置、测试、OpenAPI、CI、非 root 容器、Kubernetes、追踪关系和内容寻址清单。

运行 `make project-synthesis` 会验证 417 个全局 PG001–PG417 规范、180 个 Batch 81–95 Language Pack 规范和 42 个 Schema，执行引擎单元/静态检查，并在临时目录真实生成、构建、测试和启动 Java、Python、C# 三种目标。Batch 66–80 提供 195 个主流语言与工程资产 Runtime Skills；Batch 81–95 再提供 COBOL/Mainframe、SAP ABAP、数据库过程语言、IEC 61131-3 PLC、MATLAB/Simulink、Modelica/FMI、VB/Office、IBM i RPG、R、SAS、Salesforce、Objective-C、Delphi、BEAM 与 Lua/OpenResty 共 180 个 Skills。后者的源 PG223–PG402 与全局 PG 编号重叠，因此保留独立 package-local 命名空间，并以 `$b81-*`–`$b95-*` 安全别名调用，绝不重编号冒充全局连续性。当前内置生成器仍仅直接发射单聚合 Java/Python/C# Starter；其他能力必须使用对应 Skill 和真实原生/厂商工具链、代表性环境及安全审批。详见 [`docs/project-synthesis-batch46-95-verification.md`](docs/project-synthesis-batch46-95-verification.md)。

完整的 Draft → Review/Approve → Generate → Verify 操作说明见 [`engines/project-synthesis-engine/README.md`](engines/project-synthesis-engine/README.md)。Web Console `/generation` 页生成的 CLI 命令与引擎的命名空间、目标版本及端口保持一致；页面本身不会绕过审批或直接执行生成器。

## Product Closure Skills Batch 97–104

`elmos-codex-skills-batch97-104-complete/` 提供 128 个产品收敛 Runtime Skills，覆盖能力图、可执行 Skill 契约、Durable Runtime、加固 Runner、Java/.NET/Python Golden Routes、语义等价、证据织网及真实产品验收准备。安装名使用 `$b97-*`–`$b104-*`，源 ID `B97-S01`–`B104-S16` 保留在独立 `batch-local-product-closure` 命名空间，不推断或占用全局 PG 编号。

运行 `make batch97-104-skills` 会校验不可变清单、128 个编译后执行契约、无环依赖、严格 Schema、可恢复安装事务、安装接口及证据反伪造回归。源包曾有 32 个重复输出和两处阻塞依赖环，仓库规范化版本已在保留来源摘要的前提下修复。所有模板与外部现场证据保持 `NOT_RUN`；本地门禁最高只返回 `ready_for_external_gate`，不会签发产品认证。详见 [`docs/batch97-104/VERIFICATION.md`](docs/batch97-104/VERIFICATION.md)。

## rewrite-spring 底座

ELMOS 通过锁定的 `org.openrewrite.recipe:rewrite-spring:6.35.0` 复用同目录 `rewrite-spring` 的 Recipe 能力，不复制其 198 个 Java 源文件，也不形成私有分叉。审计时的上游快照为 `ae11461b732e13c27bc7b8ed9b1b2943b8e4944f`，详见 `docs/adr/0001-rewrite-spring-foundation.md`。

## 验证

```bash
make verify
```

`make backend` 使用 Java 21 执行单元测试、契约测试和 ArchUnit 边界测试；`make dotnet` 使用锁定的 .NET 10 SDK；`make python` 使用 Python 3.14 与 uv 锁执行 pytest、Ruff 和 mypy；`make frontend` 验证独立的 TypeScript/Node 客户端引擎；`make web` 执行 Next.js/TypeScript 静态检查。

生产工程基线可用以下命令复现：

```bash
make production-readiness-check
```

该命令检查 Batch 45 失败关闭工具、Project Synthesis 的真实三语言构建/启动、Web Console 生产构建，以及 18 个 Spring HTTP 服务的优雅停机、安全错误响应、存活/就绪探针、唯一服务身份/端口和生产数据库必填配置。它属于工程证据，不替代部署矩阵、负载/Soak、安全独立评审、备份恢复/DR、客户结果或最终认证；对应 Pack 保持 `NOT_RUN`，见 [`mature-product-packs/batch45/elmos-platform-production-readiness/gate-report.md`](mature-product-packs/batch45/elmos-platform-production-readiness/gate-report.md)。

Batch 1–13 的硬化基线记录在 [`docs/batch-1-13-hardening.md`](docs/batch-1-13-hardening.md)；Batch 14–26 的完成边界与现场 Gate 见对应 verification 文档。Batch 22–26 的统一验收摘要见 [`docs/batch-22-26-verification.md`](docs/batch-22-26-verification.md)。

### Batch 1–37 严格测试套件

仓库包含 52 个 `$tst-*` Codex Skills、408 个精确种子用例、9 个 Draft 2020-12 Schema，以及防伪造的最终门禁。每个 Batch 固定覆盖成功、边界、非法/不支持、依赖失败、安全、重放/幂等、版本漂移和证据篡改八类场景。运行 `make test-suite-check` 验证 Skill、Catalog、Coverage、Schema 与门禁回归；运行 `make test-suite-gate` 读取真实结果并失败关闭。

本地 `make test-suite-local-qualification TEST_SUITE_EVIDENCE_DIR=<new-directory>` 会执行真实仓库构建并生成不可覆盖的工程证据，但不会改写 408 个认证结果。最终 `CERTIFIED` 还要求每个用例具备精确 Artifact/Environment、原始证据、Replay、独立 Holdout/代表性语料（适用时）、执行/验证职责分离，以及由套件外 Trust Store 验证的统一签名认证请求；未执行状态保持 `NOT_RUN`。

用户提供的 Batch 1-55 “slightly strict” 测试包作为补充设计目录保存在 `test-suites/batch1-55-slightly-strict/`：55 个 Batch、660 个场景均受哈希与失败关闭 Gate 约束，但不替代上述 408 个严格认证用例。运行 `make test-suite-1-55-check` 检查目录完整性；`make test-suite-1-55-gate` 只会在具备逐用例真实执行、授权、独立验证与不可变证据时晋级到 `READY_FOR_EXTERNAL_GATE`，不会签发认证。

Batch 1-65 “slightly strict” 补充套件位于 `test-suites/batch1-65-slightly-strict/`，包含 65 个 Batch 测试 Skill、23 个跨 Batch 测试 Skill、750 个用例和对 1,296 个源 Skill 的直接覆盖边。仓库门禁额外修复了上游空结果可被聚合为 PASS 的完整性缺口，强制要求 750 条结果齐全、两次确定性执行、独立验证、授权和全部原始证据角色。运行 `make test-suite-1-65-check` 做结构及反篡改回归；`make test-suite-1-65-gate` 在现场执行尚未发生时按预期保持 `BLOCKED / NOT_RUN`，且不替代 Batch 1–37 严格认证门禁。

Batch 66–80 略严苛补充资格套件位于 `test-suites/batch66-80-slightly-strict/`：35 个测试 Skill 管理 450 个精确用例，其中 195 个 PG223–PG417 源 Skill 各有一个正向与一个负向用例（390 个），另有 60 个跨领域用例；优先级为 P0 312、P1 120、P2 18，其中 103 个零容忍。运行 `make test-suite-66-80-check` 会验证不可变的 544 项源包、当前源 Skill 哈希、完整用例/结果、Codex 接口、JSON Schema 和 10 个仓库反篡改回归；`make test-suite-66-80-gate` 在真实工具链、设备、数据库、集群、Provider、签名和独立验证未发生时按预期返回 `BLOCKED / NOT_RUN`，450 条结果不冒充通过，最高决策仅为 `READY_FOR_EXTERNAL_GATE`。

Batch 81–95 Language Pack 补充资格套件位于 `test-suites/batch81-95-language-packs-slightly-strict/`：40 个测试 Skill 管理 640 个精确用例，对 180 个 package-local 源 Skill 提供逐项直接覆盖，共 47,700 条 case-target 链接；严重度为 Critical 170、High 400、Medium 70。套件同时验证原始 PG ID、`LP-Bxx-PGxxx` 复合身份和 `$b81-*`–`$b95-*` 安装别名。运行 `make test-suite-81-95-check` 执行不可变包、完整性及 12 个命名空间/证据反篡改回归；`make test-suite-81-95-gate` 在主机、SAP、PLC、仿真器、数据库、厂商平台、硬件或代表性并行运行尚未真实执行时保持 `BLOCKED / NOT_RUN`，不会批准生产、物理控制、安全或认证结果。

### Batch 1–55 Skill 组合包

`elmos-codex-skills-batch1-55-complete` 已修复为双命名空间分发：Migration Packs M1–M45 共 820 个 Skill，Product B34–B55 共 1,004 个 Skill。1,824 个契约全部通过官方 `skill-creator` 校验并包含 `agents/openai.yaml`；1,015 个超长来源名使用保留 `source_name` 的确定性别名。运行 `make batch1-55-skills` 可复现结构门禁。

该结果不等于全部批次已生产完成：M1–M28 的 448 个契约仍是来源不完整的规范化版本，Product B40B–B55C 的 752 个契约仍是规划版，全部客户/Provider/生产/认证现场证据保持 `NOT_RUN`。详细边界见 `docs/batch1-55-skills/verification.md`。

## 跨语言迁移 Batch 交付范围

- Batch 1（Repository Intake）：不可变 Snapshot、四语言项目/构建发现、Inventory、依赖图、Sandbox Policy、Baseline 与冻结 Manifest。
- Batch 2（Semantic adapters）：PSP v1、四语言权威适配器边界、无损降级、符号/类型/调用/继承/数据流/诊断、模块门禁、Zstandard 流与 SQLite 索引。
- Batch 3（UIR）：统一声明/类型/操作模型、Structured 与 CFG/SSA 双视图、Dialect、Effect、Exception、Async、Alias、Opaque、Obligation、Provenance 与资格门禁。
- Batch 4（Skeleton-first）：目标 Profile、技术栈/模块/命名/构建规划、四语言契约骨架、受保护占位符、映射、隔离 Baseline 证据与 S-A 至 S-D 门禁。
- Batch 5（Core language lowering）：先生成并静态验证语义保真的方法体，再执行可回退的局部惯用化；覆盖规则/能力矩阵、类型与求值计划、Emitter/Compiler 边界、方法级 Patch、Agent 升级包及 L-A 至 L-D 门禁。
- Batch 6（Dependency semantic migration）：从依赖坐标、精确解析图和实际 API 使用构造语义要求，经过显式知识映射、兼容度与供应链门禁，选择删除/标准库/目标包/Adapter/Compatibility Runtime/Wrapper/Sidecar/远程或保留运行时策略；构建补丁必须由目标包管理器重算锁文件并通过 D-A 至 D-D。
- Batch 7（Framework semantic migration）：以 AFSM 统一 REST、DI、验证、持久化、事务、安全、配置、消息、缓存、调度与生命周期，通过确定性 Recipe、原生 Emitter/Startup 端口、语义差分和 F-A 至 F-D 门禁迁移框架语义。
- Batch 8（Build/test repair loop）：规划四语言构建矩阵，在隔离执行端口中恢复依赖、编译、静态分析和发现/执行测试；统一 Diagnostic、Root Cause 与归因，执行确定性优先的有界 Patch、事务回滚、回归、Flaky/预算/停止治理和 R-A 至 R-D 门禁。
- Batch 9（Behavioral equivalence）：以固定源/目标 Snapshot 和隔离双运行环境执行相同场景，通过 OBM 采集 HTTP、数据库/事务、消息、文件/对象、Cache、异常、审计、时间随机及并发行为；经受审查的规范化、Golden、多 Oracle、Tolerance/Approved Change、Flaky 与证据治理后执行 E-A 至 E-E 模块门禁。E-D/E-E 只允许进入 Batch 10 生产强化，绝不批准切流。
- Batch 10（Production hardening）：对 Batch 9 通过的同一不可变 Artifact 按服务建立风险等级与脱敏生产负载模型，通过外部 Authority 收集校准性能、p95/p99、资源/容量/Soak、安全/SBOM/身份/租户、Chaos/Crash/Restore/PITR/DR、Telemetry/SLI/SLO/Alert/Runbook、签名/Provenance/Canary/Rollback/Cost 证据，并执行 P-A 至 P-F 非补偿门禁。P-E/P-F 只允许进入渐进式发布评审，模型始终保持 `production_ready=false` 和 `eligible_for_cutover=false`。
- Batch 11（Progressive production cutover）：接收 Batch 10 P-E/P-F 的同一不可变目标 Artifact，以 P0 至 P12 PCCM 管理波次/Cohort、Expand–Migrate–Contract、回填/CDC/最终 Delta、单一 Write Authority、Shadow/读写 Canary、消息/Job/文件/Cache/Search、Rollback/Forward-fix、Hypercare、五维验收和旧系统退役，并执行 C-A 至 C-G 非补偿门禁。控制平面只评估外部 Authority 证据，不直接切流、改数、撤销凭据或销毁基础设施；只有 C-G 能声明迁移完成。
- Batch 12（Enterprise multi-tenant platform）：将 Batch 1–11 的迁移能力包装为证据驱动的企业交付控制模型；覆盖多租户隔离、OIDC/SAML/SCIM、RBAC/ABAC/审批、Private Runner、统一 Model Gateway、Quota/Meter/Ledger/Billing、审计/Provenance、Residency/Retention/Legal Hold/CMK、Self-hosted/Air-gapped 与 HA/DR，并对五种部署模式独立执行 T-A 至 T-G。只有完整外部证据、零 Critical 风险且五种模式全部达到 T-G 才能声明企业交付就绪。
- Batch 13（Enterprise commercial loop）：以 Batch 12 T-G 签名制品为输入，统一八个商业域、正常/异常客户生命周期和六种商业 Motion；通过销售/POC、报价/合同、入驻/交付、支持/成功、伙伴、运营经济性和最终验收七个 Authority 执行 B13-A 至 B13-G。只有完整外部证据、零 blocker 且达到 B13-G 才能标记商业规模候选，控制层始终保持 `commercial_operation_executed=false`。
- Batch 14（Product and ecosystem growth）：以 Batch 13 B13-G 签名制品为输入，要求价值绑定的 Monthly Verified Migration Value、PEGM 七增长域和五个飞轮；通过产品激活、内容与开发者、社区、Marketplace、国际化、区域渠道和最终验收 Authority 执行 G14-A 至 G14-G。只有完整外部证据、可见 CAC/贡献毛利、零 Critical 风险且达到 G14-G 才能标记 `scalable-growth-ready`，控制层始终保持 `external_operation_executed=false`。
- Batch 15（Company operating system）：COGS 八经营域、Skills 461–525、C15-A 至 C15-G、年度经营/组织/财务/资本/风险/董事会报告，以及 `company_ops` 强 RLS 投影。
- Batch 16（AI-native company）：Skills 526–592、A0–A6 自主等级、Human Owner/Authority Envelope/Eval/Shadow/Kill Switch、AI16-A 至 AI16-G，以及 `agent_workforce` 强 RLS 投影；无限自主明确禁止。
- Batch 17（Vertical solution factory）：Skills 593–668、Shared Core/Industry/Jurisdiction/Customer 四层 VSP、金融/制造/能源/医疗/政府/电商/通信七行业、V17-A 至 V17-G，以及 `vertical_solutions` 强 RLS 投影。
- Batch 18（Group integration factory）：Skills 669–745、GITM、Day 1/30/100、应用处置、身份/数据合并、Wave/TSA/Carve-out/Synergy/Retirement 和 M18-A 至 M18-H，以及 `group_integration` 强 RLS 投影。

新增跨语言 Skills 位于 `agent-skills/polyglot-intake`、`agent-skills/polyglot-semantic`、`agent-skills/polyglot-uir`、`agent-skills/skeleton-first`、`agent-skills/core-language-lowering`、`agent-skills/dependency-semantic-migration`、`agent-skills/framework-semantic-migration`、`agent-skills/build-test-feedback`、`agent-skills/behavioral-equivalence`、`agent-skills/production-hardening`、`agent-skills/production-cutover`、`agent-skills/enterprise-platform`、`agent-skills/commercial-loop`、`agent-skills/ecosystem-growth`、`agent-skills/company-operating-system`、`agent-skills/agent-workforce`、`agent-skills/vertical-solutions` 和 `agent-skills/group-integration`；对应契约位于各自 `contracts/*-schema` 目录。

## Java 现代化 Batch 1–4

- Batch 1：建立 Java 21 Maven 模块化单体、共享 Engine API、迁移计划/运行/步骤状态机、Evidence/Audit/Outbox、Flyway V1 与明确标为模拟的本地演示。
- Batch 2：建立 GitHub App 短期 Token、Webhook 防重放、不可变内容寻址 Snapshot、Secret Lease、Rootless Docker Workspace、镜像批准与默认拒绝网络策略。
- Batch 3：建立有界 Java/Maven/Gradle/Spring 遗留健康扫描、依赖与漏洞证据、Baseline 模型和证据绑定的 `/engine/v1/health-checks`。
- Batch 4：建立源/目标 Profile、确定性 DAG、依赖顺序、估算与风险 Gate、具名审批和证据绑定的 `/engine/v1/migration-plans`。

通用 `/engine/v1/scan`、`/plan`、`/validate`、`/execute-step` 在未绑定批准后的执行后端时返回终态 `FAILED`、空 `evidenceRefs` 及 `configured=false`/`executed=false`，不会生成模拟成功证据。完整仓库内验收与现场 Gate 见 `docs/batch-1-4-verification.md`。

## Java 现代化 Batch 5–8

- Batch 5：`modules/recipe-governance` 实现 Catalog 选择、递归许可证闭包、不可变执行 Manifest、Data Table/Run 证据、Fresh Process 幂等与振荡检测、语义 Patch 分段、自定义 Recipe 晋级门禁。`rewrite-spring` 的 MSAL 依赖在 ELMOS 商业上下文默认阻断。
- Batch 6：`modules/repair-orchestration` 与 `apps/agent-gateway` 实现错误归一化/聚类、最小任务上下文、Codex/Claude/OpenHands/Human 硬路由、预算预留、Provider 沙箱计划、反作弊 Patch Gate、有限修复循环和人工升级。Agent Gateway 不访问数据库、不启动宿主进程。
- Batch 7：`modules/validation` 是独立质量裁判，比较隔离的 Baseline/Migrated 环境、Build/Test、HTTP/Java API、序列化/消息、数据库、事务和性能。缺失或未运行证据永不等于通过。
- Batch 8：`modules/delivery` 实现内容寻址 Delivery Snapshot、同源 JSON/Markdown/HTML、风险与例外、Draft PR/MR 和 HEAD-bound Checks、Ed25519 签名的确定性 tar.zst Evidence Pack、多域回滚，以及 Delivered/Accepted/Merged/Released/Closed 独立生命周期。

R021–R060 的 40 个 Runtime Skills 位于 `agent-skills/runtime`；核心契约位于 `contracts/recipe-schema`、`contracts/repair-schema`、`contracts/validation-schema` 与 `contracts/delivery-schema`；数据库迁移为 Flyway V5–V8。架构决策见 ADR-0024 至 ADR-0027。

## Java 现代化 Batch 9–10

- Batch 9：`modules/enterprise-governance` 和 `apps/enterprise-control` 实现服务器推导的 Tenant Context、OIDC/SAML 身份断言边界、对象级 RBAC/ABAC/职责分离、私有 Runner 与 Secret Lease、统一 Model Gateway 硬过滤、并发 Usage/Credit、Audit Hash Chain、数据驻留/Legal Hold/删除，以及离线 Bundle 与 License 策略。Flyway V9 给既有 Batch 1–8 业务表补齐租户列并启用强制 RLS。
- Batch 10：`modules/commercial-operations` 和 `apps/commercial-api` 实现稳定 Feature Key 与 Entitlement、幂等和部分订单履约、客户入驻 Readiness、加权项目驾驶舱、SLA/Service Credit、Support/Incident、Recipe 资产与知识治理、客户成功及商业分析。CRM、支付、税务、正式发票和会计总账保持外部 Port。
- `apps/elmosctl` 暴露 `preflight/install/status/backup/restore/import-bundle/upgrade/verify/diagnostics` 离线运维命令；变更类命令要求批准证据和显式确认，实际外部动作仍只能在客户批准环境执行。

B016–B035 的 20 个 Build Skills 位于 `agent-skills/build`；Batch 9/10 的 17 个 JSON Schema 位于相应 `contracts/*-schema` 目录；数据库迁移为 V9/V10。架构决策见 ADR-0029 和 ADR-0030，完整现场 Gate 见 `docs/batch-9-10-verification.md`。

## Batch 11：.NET 第二执行引擎

- `engines/dotnet-engine` 是独立 .NET 10 Worker；实现共享 Engine API、租户幂等 Job、安全静态 SLN/SLNX/SLNF 与项目发现、技术指纹、真实 Roslyn Syntax/Semantic/IOperation 图、目标/DAG、SDK-style/PackageReference 转换、ASP.NET/WCF/EF 决策、独立验证和统一 Evidence Extension。
- 动态 MSBuild/Roslyn Workspace 只能进入默认拒绝网络且无控制面 Secret 的 Windows Runner；`WINDOWS_LEGACY`、`MODERN_WINDOWS` 与 `MODERN_LINUX` 是三个独立能力和证据环境。
- Java `LanguageEngineRouter` 只路由共享 Port；`UnifiedMigrationPortfolio` 允许同租户 Java/.NET 计划共享 API 依赖、波次、风险与验收 Gate。控制面不加载 Roslyn/MSBuild。
- C001–C012 位于 `agent-skills/runtime`；五套 JSON Schema 位于 `contracts/dotnet-*` 与 `contracts/roslyn-graph-schema`；Flyway V11 新增 61 张强制 RLS 的 .NET 分析表，但不复制工作流、权限、计费、审计或交付表。
- 完成定义与外部 Gate 见 `docs/batch-11-verification.md`，架构决策见 ADR-0031。当前 macOS 环境不能证明 Windows Legacy、IIS、COM、WCF 旧宿主或 Windows Container，相关状态保持 `NOT_RUN`。

## Batch 12：Python 第三执行引擎

- `engines/python-engine` 使用 Python 3.14、uv 锁、LibCST 和 CPython AST 实现共享 Engine API、租户幂等 Job、安全项目/版本/依赖发现、环境可复现判定、能力匹配 Runner 路由、Python 2 语义风险、Packaging/Native ABI、语义图、分阶段 DAG、受控 Codemod 与统一 Evidence Extension。
- Web、Data Pipeline、AI/ML 是三条独立路径：Web 比较 HTTP/Auth/Session/Database，Data 比较数据契约、dtype/数值、调度/重试/回填，AI/ML 分开裁决 Artifact、Inference、Training、指标、硬件和服务性能。
- Python 2 Legacy、Modern CPU、Modern GPU、Windows 和 Notebook 是五种不同 Runner 能力；未知 pickle/joblib/checkpoint 不在控制面或静态扫描器内加载。
- Java `LanguageEngineRouter` 路由第三引擎，统一 Portfolio 新增 HTTP、Message、Data、Model、Shared Database、File、Package 依赖边；控制面不加载 LibCST、mypy 或 Pyright。
- P001–P014 位于 `agent-skills/runtime`；五套 Schema 位于 `contracts/python-*`、`contracts/numerical-comparison-schema` 和 `contracts/model-validation-schema`；Flyway V12 新增 71 张强制 RLS 的 Python 分析表。
- 完成定义与外部 Gate 见 `docs/batch-12-verification.md`，架构决策见 ADR-0032。当前 macOS 环境不能证明 Python 2、GPU/CUDA、Windows、真实 Notebook clean-kernel、客户模型安全加载或生产数据行为，相关状态保持 `NOT_RUN`。

## Batch 13：跨语言系统组合迁移

- `modules/composite-modernization` 构建不可变 System Landscape Twin、跨仓库依赖/SCC/共享数据库分析、跨语言 Contract Consumer Matrix、Runtime Trace Correlation、Wave 0–6、Expand-Contract Window、Compatibility Runtime 门禁、数据所有权/CDC/Backfill/Reconciliation、Shadow Differential、渐进流量、Business Journey、数据感知回滚、稳定期和退役门禁。
- `apps/control-plane` 只暴露 `/api/v1/composite/*/evaluate` 读取/裁决接口；它不直接修改源码、调用三语言转换器、切生产写、删除旧库或自动退役。Java、.NET、Python 仍是仅有的三个源码执行引擎。
- X001–X014 位于 `agent-skills/runtime`；七套 JSON Schema 与 `contracts/composite-api` 固化跨系统契约；`engines/composite-engine/test-fixtures` 固化 18 个验收场景和 7 个 Schema Fixture。
- Flyway V13 覆盖 76 类组织级对象：新建 74 张强制 RLS 表，并复用/扩展 V7 的 `message_contracts` 与 V9 的 `model_endpoints` 权威表；18 类证据增加 append-only 触发器，不复制工作流、权限、计费、审计、SCM 或交付权威。完成定义和外部门禁见 `docs/batch-13-verification.md`，架构决策见 ADR-0034。

## Batch 14：前端与客户端第四执行引擎

- `engines/frontend-client-engine` 使用 TypeScript/Node 实现共享 Engine API、安全 Workspace/Package 发现、Route/Component/State 图、目标与 DAG、AngularJS/Angular、Vue 2/3、React Class、jQuery、Electron/桌面、移动、BFF、设计系统、视觉、无障碍、性能、安全和协同发布的确定性策略核心。
- 静态扫描不安装依赖或执行客户代码；Codemod、构建、浏览器、桌面、Android/iOS、真实设备、人工屏幕阅读器、签名、商店和发布 Provider 必须进入批准的能力匹配 Runner，未配置时返回失败与空证据。
- Java `LanguageEngineRouter` 将 JavaScript/TypeScript/HTML/CSS 路由为第四引擎；Composite Portfolio 新增 Client Contract、BFF、Design System 和 User Journey 关系，Java 控制面只裁决发布权限。
- F001–F017 位于 `agent-skills/runtime`；六套 Schema、六个 Fixture、OpenAPI 3.1、22 个事故场景和 V14 的 71 张强制 RLS 表构成仓库级验收面。详见 `docs/batch-14-verification.md` 与 ADR-0035。

## Batch 15：数据库与数据平台第五执行引擎

- `engines/database-data-engine` 是独立 Java 21 Worker，复用共享 `/engine/v1`，声明 Oracle、SQL Server、MySQL、PostgreSQL、Data Platform 和 BI Validation 六类 Runner；未配置短期 Credential、批准后的 Runner、Provider 和独立证据时失败关闭。
- 事务数据库、分析平台和 BI Semantic 是三条独立轨道。Canonical Schema/SQL/Procedure IR 禁止字符串替换；目标规划同时比较同构、异构、分析 Offload 和工具中立语义层。
- Bulk Load 与 CDC 绑定同一源 Frontier，使用可恢复 SCN/LSN/GTID/Checkpoint；Read 与 Write Cutover 分开，未知 Writer、性能回归、数据质量、BI Security、治理或回滚证据缺失都会阻止切换。
- Java `LanguageEngineRouter` 路由 SQL/PLSQL/T-SQL/PLpgSQL 与数据平台请求；Composite Portfolio 新增 Database Object、CDC Stream、Data Asset/Product、BI Metric 和 Data Lineage 边。
- D001–D014 位于 `agent-skills/runtime`；五套 Draft 2020-12 Schema、OpenAPI 3.1、24 个事故场景和 V15 的 85 张新强制 RLS 表构成仓库验收面，并复用 V13 的 `cdc_streams`/`cdc_offsets` 权威。详见 `docs/batch-15-verification.md` 与 ADR-0037。

## Batch 16：云与基础设施第六执行引擎

- `engines/infrastructure-engine` 是独立 Java 21 Worker；四条轨道分别覆盖 VM、容器/Kubernetes、Serverless/Event 与云基础设施治理，所有 Provider SDK、SSH/WinRM、构建、IaC Apply、集群、流量和删除能力均保留在批准后的外部 Runner。
- Placement 同时比较 Bare Metal、现代 VM、Container、Kubernetes、Serverless、Managed、Edge 与 Retire；License、硬件、状态、SLO、团队能力、成本和退出路径均可成为硬约束，Kubernetes 不是默认目标。
- 所有变更严格遵循 Discovery → Desired State → Plan → Policy/Cost/Security → Named Approval → Apply → Independent Validation → Evidence；控制面只能裁决，不调用 Provider 或改变客户基础设施。
- IaC 先建立无变化导入基线；容器绑定 Digest/SBOM/Signature/Provenance；Kubernetes 验证 CNI 实际执行、Pod Security、Probe、Topology、PDB、Storage/Restore；Serverless 验证 Cold Start、Concurrency、Idempotency 与 DLQ。
- OTel/SLO、FinOps、Chaos/Backup/DR、多云 Portability、DNS/Traffic/State Cutover 和 Decommission 均是独立门禁，并与应用、数据库和客户端 Evidence 组成 Composite Change Set。
- I001–I016 位于 `agent-skills/runtime`；九套 Draft 2020-12 Schema、OpenAPI 3.1、26 个事故场景和 V16 的 96 张新强制 RLS 表构成仓库验收面，并复用/扩展现有 SLO、Backup、Restore 与 DR Test 权威。详见 `docs/batch-16-verification.md` 与 ADR-0039。

## Batch 17：横向安全与合规第七执行引擎

- `engines/security-compliance-engine` 是独立 Java 21 Worker；横跨 Java、.NET、Python、Frontend、Database/Data、Infrastructure 与 Composite，统一 Estate、Identity/PAM/Zero Trust、Secrets/Crypto、Secure SDLC、Supply Chain、SAST/SCA/DAST/API/Runtime、Vulnerability/Exposure/Risk、Cloud、Data Protection、Threat、Detection/Response、Control/OSCAL 与 Continuous Authorization。
- 所有工具只通过版本化 Adapter 接入，默认拒绝网络且初始为 `NOT_CONFIGURED`；主动测试必须绑定 Target、Environment、允许方法、速率、Abort、清理、Owner 与批准。控制面不加载扫描 SDK、不执行宿主命令、不修改生产、不读取 Secret 值、不接受风险。
- `Vulnerability`、`Finding`、`Exposure` 与 `Risk` 分离；SBOM 不等于漏洞结果，VEX 不等于 SBOM；无告警但解析或覆盖不足返回 `COVERAGE_INSUFFICIENT`，不得显示为 `PASS`。
- 内部 Authorization 绑定 Commit、Artifact Digest、Deployment、Policy、Identity、Data、Threat Model 与 Evidence Manifest，具有有效期和变化触发器；它不能冒充 ISO 认证、SOC 报告、监管许可或正式 ATO，Critical 风险不能由 Agent 自动接受。
- S001–S017 位于 `agent-skills/runtime`；九套 Draft 2020-12 Schema、OpenAPI 3.1、30 个事故场景和 V17 的 94 张新强制 RLS 表构成仓库验收面，并复用/扩展既有 Service Identity、Secret Reference/Lease、Risk Exception/Acceptance 与 Authorization Decision 权威。详见 `docs/batch-17-verification.md` 与 ADR-0041。

## Batch 18：测试与质量工程现代化第八执行引擎

- `engines/test-quality-engine` 是独立 Java 21 Worker，横向覆盖所有语言、客户端、数据/模型、基础设施与 Composite Journey；归一化遗留自动/脚本/手工测试、稳定 Test Identity、四类数量对账、健康与 Test Smell。
- 风险模型与代码覆盖分离；Portfolio 不使用固定测试层百分比。Characterization 不声称旧行为正确，Golden Master 必须窄化动态字段并经人工批准；Contract 不替代 E2E，Coverage 不替代 Mutation，Retry 不隐藏 Flaky。
- Unit、Integration、Browser/Client、Data/ML、Performance 与 Mutation 只在 rootless、digest-pinned、短期隔离 Runner 中执行，默认拒绝网络并要求 Environment/Test Data Lease；当前 Adapter 均为 `NOT_CONFIGURED`，控制面不运行客户测试或使用生产 Secret。
- AI Test 始终是 Candidate，必须通过 Compile、Run、Fail-before-fix、Repeatability、Isolation、Mutation 与人工 Review；Worker 不能改 Gate、自动更新 Snapshot、删除测试、把 Unknown/Skipped/Not Run 当作 Pass。
- Q001–Q017 位于 `agent-skills/runtime`；八套 Draft 2020-12 Schema、OpenAPI 3.1、完整 Fixture Matrix、30 个事故场景和 V18 的 86 张新强制 RLS 表构成仓库验收面，并扩展 V7 的 `test_suites` 与 `test_case_identities` 权威。详见 `docs/batch-18-verification.md` 与 ADR-0043。

## Batch 19：大型机与核心遗留平台第九执行引擎

- `engines/mainframe-engine` 是独立 Java 21 Worker；声明 COBOL、PL/I、JCL、REXX/Assembler Inventory 与 CICS、IMS、Db2 for z/OS、VSAM、MQ、3270 能力，所有外部 Adapter 初始为 `NOT_CONFIGURED`。
- 主机发现默认只读；z/OS Job、Dataset、Build、Test、Parallel Run 和 Cutover 受短期 Lease、Dataset Allowlist、资源预算、个人 SAF 身份和独立生产批准约束。控制面禁止 TSO、任意 JCL、生产 Dataset/Loadlib 写入和自动切换数据 Authority。
- 支持 Keep/Optimize、API Enable、主机内模块化、Hybrid Extract、受控 COBOL 转换、Runtime/Data Replatform、产品替换与退役；在线交易、批处理和数据写权威分别规划和裁决。
- M001–M018 位于 `agent-skills/runtime`；八套 Draft 2020-12 Schema、OpenAPI 3.1、30 个事故场景、82 张 V19 强制 RLS 表和独立 Cutover/Decommission Judge 构成仓库验收面。详见 `docs/batch-19-verification.md` 与 ADR-0045。

## Batch 20：企业集成与中间件现代化第十执行引擎

- `engines/enterprise-integration-engine` 是独立 Java 21 Worker，覆盖 ESB/SOA、IBM MQ、Kafka、RabbitMQ、API Gateway、EDI/AS2/MFT/B2B、Schema Registry 与 BPM/Workflow；所有外部 Adapter 初始为 `NOT_CONFIGURED`。
- Command、Event、Notification、Query 与 File Transfer 分开；Contract、Delivery、Ordering、Idempotency 与 Business Result 分层。Kafka、MQ、RabbitMQ 按消息语义选择，不伪装端到端 Exactly Once。
- Discovery 默认只读；Replay、Partner Test、Broker/Gateway/Workflow 变更、Producer/Consumer/Partner 切换均要求短期 Lease、精确 Scope 与独立批准。Worker 不能 Purge Queue、Reset Offset、删除 Topic、改证书、接受消息丢失或自判 Cutover。
- E001–E018 位于 `agent-skills/runtime`；七套 Draft 2020-12 Schema、OpenAPI 3.1、完整 Fixture Matrix、30 个事故场景、V21 的 70 张新强制 RLS 表与 4 张既有权威表扩展、独立 Cutover/Decommission Judge 构成仓库验收面。详见 `docs/batch-20-verification.md` 与 ADR-0048。

## Batch 21：企业套件现代化第十一执行引擎

- `engines/enterprise-suite-engine` 是独立 Java 21 Worker，覆盖 SAP ECC/S/4HANA、Oracle EBS/Fusion、Dynamics 365/Dataverse/Power Platform 与 Salesforce；所有外部 Adapter 初始为 `NOT_CONFIGURED`。
- 发现与规划同时保留标准配置、扩展、自定义代码、业务流程版本、主数据、角色/SOD、报表、集成、运行用量与历史数据。目标可选择保留治理、技术升级、系统转换、Greenfield、选择性数据迁移、云重实施、模块替换、Composable、双套件共存或退役，不强制单一厂商路线。
- Worker 只编排短期 Lease、精确 Environment Scope 和隔离 Runner；禁止改生产配置、发布 Transport/Solution、自动接受流程/财务/SOD 差异、批量删除业务数据、切换主数据权威或自判 Cutover/Decommission。
- U001–U018 位于 `agent-skills/runtime`；八套 Draft 2020-12 Schema、OpenAPI 3.1、完整 Fixture Matrix、30 个事故场景、V23 的 62 张新强制 RLS 表、1 张既有强制 RLS 权威表扩展与独立 Cutover/Decommission Judge 构成仓库验收面。V23 被采用是因为现有产品生态迁移已经占用 V22。详见 `docs/batch-21-verification.md` 与 ADR-0049。

## Batch 22–26：横向企业执行域

- Batch 22：`engines/software-delivery-platform-engine` 覆盖 SCM、CI/CD、Artifact、Environment、Golden Path 和 Internal Developer Platform；所有外部 Adapter 初始为 `NOT_CONFIGURED`，生产 Repository、分支、Artifact 和 Deployment 变更默认拒绝。
- Batch 23：`engines/ai-platform-engine` 覆盖 Data/Feature、Training、Registry、Inference/LLM Gateway、RAG、Agent、Evaluation、Responsible AI、FinOps 与 Release；训练、模型加载、Agent 工具调用和生产部署只允许在批准后的隔离 Runner 中发生。
- Batch 24：`engines/edge-iot-industrial-engine` 采用 Outbound-only Site Runner，覆盖 OPC UA、MQTT/Sparkplug、Legacy Gateway、OTA、Digital Twin、Historian、Edge AI、SIL/HIL 与 Site Cutover；现场安全策略拥有更高权威，控制面不能任意写 PLC 或绕过联锁。
- Batch 25：`engines/operations-sre-itsm-engine` 覆盖 CMDB/Topology、Events、Incidents、Problems、Changes、SLO、Runbook、AIOps、Capacity 与 Continuity；AIOps 只产生假设，不能自动确认根因、关闭重大事故或批准高风险变更。
- Batch 26：`engines/enterprise-architecture-engine` 覆盖 Capability/Value Stream、Application/Technology Portfolio、Current/Transition/Target State、Option、Roadmap、ADR、Conformance 与 Benefit；投资、退役、例外和收益确认始终保留给独立治理与 Human Owner。
- 五个域共新增 90 个初始化并验证的 Runtime Skills、26 个 Draft 2020-12 Schema、210 个失败关闭场景、31 个 Rootless Runner Policy，以及 V28–V32 的 516 个租户投影。共享 `modules/evidence-bound-engine` 固化租约、范围、幂等、租户隔离、状态机和“执行者不能同时裁判”的边界。
- 仓库内完成定义、实测结果与外部 `NOT_RUN` Gate 见 `docs/batch-22-26-verification.md`，架构决策见 ADR-0051 至 ADR-0055。

## Migration Pack M29–M45 与产品 Batch 27–34

- Migration Pack M29–M45 是独立的仓库级实施与认证 Skill 层，不改写产品批次；产品 Batch 27–34 则覆盖 TBM、组织与技术劳动力、企业转型、自治控制塔、MVP 工程/审计、安全 Java 付费闭环和企业 IAM。
- Skills 1141–1496 加 Batch 37 补充编号 B37-X01–X16 共 372 个：Batch 29–34 覆盖有向语言路线、多框架与版本、数据库与数据平台、客户端、Cloud/IaC/DevOps 和超大 Portfolio；Batch 35–45 补齐高级正确性、IDE/PR体验、扩展SDK、部署升级、全球SRE、安全供应链、知识飞轮、Agent工厂、LTS兼容、FinOps和成熟产品最终认证。
- 120 个 Draft JSON Schema、142 个模板和 105 个 Toolkit 回归测试共同实施失败关闭认证；没有真实 Holdout、代表性工作负载、运行环境、成本、回滚、恢复、独立Review和客户结果证据时，状态不得提升为 `CERTIFIED`。
- Batch 35 已替换为权威高级正确性包：22 个 Skills、13 个 Schema、15 个模板、保守 Verification Gate，以及集成到 Maven Reactor 的 `modules/advanced-verification`。本地 14 个 Java 测试和实验 Verification Pack 只证明有界实现可执行，外部 SMT/符号执行、真实迁移等价、独立 Holdout、代表性生产负载和独立批准仍为 `NOT_RUN`，结论保持 `NOT_CERTIFIED`。
- Batch 36 已替换为权威开发者体验包：18 个 Skills、12 个 Schema、16 个模板、专用 Developer Experience Gate，以及集成到 Maven Reactor 的 `modules/developer-workflow`。本地 18 个 Java 测试和真实 CLI 回放验证了协议授权、来源—目标导航、受保护区域、无写入预览、受影响测试、PR Bot 权限、审批、离线信任与遥测隐私内核；真实 IDE Host、SCM Sandbox、独立 Holdout、代表性开发者流程、Air-gap 与独立批准仍为 `NOT_RUN`，结论保持 `NOT_CERTIFIED`。
- Batch 37 已替换为完整扩展 SDK 与 Marketplace 包：36 个 Skills、25 个 Schema、27 个模板、专用核心/闭环 Gate，以及集成到 Maven Reactor 的 `modules/extension-marketplace`。本地 24 个 Java 测试和真实 CLI 回放验证了 Manifest、默认拒绝沙箱、真实 SHA-256/Ed25519、依赖锁、发布撤销、租户安装、离线权限、结算守恒与 EOL 内核；生产发布者身份、签名、独立 Holdout、代表性扩展、Provider、Private/Air-gap、DR、结算和客户 EOL 仍为 `NOT_RUN`，两个门禁均保持 `NOT_CERTIFIED`，且 `closure_complete=false`。
- `modules/migration-pack-certification` 只准备 M29–M34 的 `READY_FOR_PACK_GATE`，唯一认证权威仍是各包的 `run_*_gate.py`；`modules/product-roadmap-governance` 只准备 `READY_FOR_HUMAN_DECISION`。二者均不执行外部动作。
- 商业化文档的 165 个唯一 Runtime Skills 与 M29–M34 的 124 个 Runtime Skills 已按 `skill-creator` 初始化、生成 OpenAI 元数据并记录来源；Runtime Skills 总数为 615。Flyway V33–V41 新增 664 个产品治理投影和 6 个迁移包认证投影。
- Batch 34 另有 `modules/portfolio-scale` 可执行内核，覆盖不可变 Portfolio、Work Unit、租户语义索引、硬约束与公平调度、Checkpoint/Replay、CAS、区域断点续传、预算、Campaign、多仓变更、控制塔和预测；`make batch34-local-rehearsal` 会为当前仓库生成实验级 Pack，并明确输出 `NOT_CERTIFIED`。
- 运行 `make mature-product-skills` 可复现 17 批仓库级迁移包验证及 M38–M45 签名证据门禁的反伪造测试，运行 `make batch27-34-skills` 验证新增的双轨 Runtime Skills。M38–M45 要求内容寻址证据、独立验证、独立语料和外部信任库，详见 `docs/mature-product/EVIDENCE_PROTOCOL.md` 与 `docs/mature-product/BATCH38_45_SOURCE_AUDIT.md`；实现与现场 `NOT_RUN` 边界另见 `docs/product-batches27-34/README.md`、`docs/batch34/VALIDATION.md` 和 `docs/mature-product-batches-29-45-verification.md`。

## Product Batch 56A 与收敛参考层

- `elmos-codex-skills-batch56a-product-closure/` 保留 16 个 `CLO56A001–016` 权威源 Skill；安装时将源包不兼容的顶层元数据规范化到 `metadata`，并在 `docs/product-closure-convergence/installed-manifest.json` 保留源摘要和双命名空间边界。
- `elmos-product-convergence-reference-skills/` 保留 32 个 `CONV-001–032` Skill，以及 Capability、依赖、生命周期、Workflow、Evidence、Reference Route、Design Partner 与 Handoff 参考对象。它是跨 Batch 收敛覆盖层，不新增功能 Batch。
- `make product-closure-convergence-skills` 验证两套权威源、48 个安装 Skill/接口、配套 Schema/模板及真实性回归测试。静态通过只代表工程结构可用。
- `make product-closure-gate` 与 `make product-convergence-gate` 是失败关闭门禁；当前模板缺少获批真实运行、独立验证、两家 Design Partner 和外部 Review 证据，预期返回 `BLOCKED`/非零。仓库级最高状态仅为 `READY_FOR_EXTERNAL_GATE`，不会批准 GA、生产认证或客户验收。

完整边界与验证证据见 `docs/product-closure-convergence/VERIFICATION.md`。

## 本地演示

```bash
make up
curl -X POST http://localhost:8080/api/v1/demo-runs
curl http://localhost:8081/engine/v1/capabilities
curl -H 'Content-Type: application/json' -d '{"snapshotId":"snapshot-local","relativePath":"."}' http://localhost:8081/engine/v1/health-checks
curl -H 'Content-Type: application/json' -d '{"snapshotId":"snapshot-local","relativePath":"."}' http://localhost:8081/engine/v1/migration-plans
curl http://localhost:8083/agent/v1/execution-capability
curl http://localhost:8080/api/v1/delivery/evidence-packs/capability
curl http://localhost:8084/enterprise/v1/capabilities
curl http://localhost:8085/commercial/v1/capabilities
curl http://localhost:8086/engine/v1/capabilities
curl http://localhost:8087/engine/v1/capabilities
curl http://localhost:8088/engine/v1/capabilities
curl http://localhost:8089/engine/v1/capabilities
curl http://localhost:8090/engine/v1/capabilities
curl http://localhost:8091/engine/v1/capabilities
curl http://localhost:8092/engine/v1/capabilities
curl http://localhost:8093/engine/v1/capabilities
curl http://localhost:8094/engine/v1/capabilities
curl http://localhost:8095/engine/v1/capabilities
curl http://localhost:8096/engine/v1/capabilities
curl http://localhost:8097/engine/v1/capabilities
curl http://localhost:8098/engine/v1/capabilities
curl http://localhost:8099/engine/v1/capabilities
curl http://localhost:8100/engine/v1/capabilities
"$JAVA_HOME/bin/java" -jar apps/elmosctl/target/elmos-elmosctl-0.1.0-SNAPSHOT.jar verify
```

Batch 1 演示会持久化 Repository、Snapshot、Assessment、批准后的 MigrationPlan、MigrationRun、模拟 Step、Evidence、Audit 和 Outbox 事件，并在返回值中明确标记 `simulated=true`。Java Worker 的健康检查和规划接口执行真实的有界静态分析；通用执行接口在批准的 Workspace Runner 尚未配置时失败关闭、返回空证据，并明确声明未执行客户代码。

核心策略与离线安全测试无需凭据。真实私有仓库、OpenRewrite/Agent Workspace、Testcontainers 双环境、PR/MR、Checks、Evidence Attestation、企业 IdP、私有 Runner、Vault/KMS、模型 Provider、GPU/Windows/Legacy Python、生产数据与模型资产、SIEM、商业系统和回滚/离线演练仍必须分别配置授权与测试基础设施。当前环境若缺少任一外部条件，相关能力返回 `NOT_CONFIGURED`、`NOT_RUN` 或 `BLOCKED`，绝不把计划或单元测试冒充真实客户迁移、企业登录、SCM 发布、数值/模型等价、财务结果、离线安装或生产可回滚。部署步骤见 `deploy/rootless-docker/README.md` 和 `deploy/air-gap/README.md`；完整 Gate 见各 Batch verification 文档。

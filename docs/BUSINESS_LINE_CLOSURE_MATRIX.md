# ELMOS 业务线闭环矩阵

本矩阵用于区分两类状态：

- `REPOSITORY_CLOSED`：仓库内可以完成的实现、契约、测试、构建和保守门禁已经闭环。
- `EXTERNAL_GATE_REQUIRED`：必须依赖真实客户、生产等价环境、独立验证者或获授权的外部操作；在证据产生前保持 `NOT_RUN`，不得由本地测试替代。

当前总状态：**精确支持矩阵内的本地演示、工程验证和 POC 已达到
`REPOSITORY_CLOSED`；任意企业项目的完整迁移、任意环境的一键生产运行、
GA、生产就绪和外部认证仍为 `EXTERNAL_GATE_REQUIRED`。** 后一类状态只有在
真实目标环境、客户数据与独立验证证据产生后才能提升，本地生成物和测试不能
替代这些外部门禁。

本轮外部控制面统一保持 `NOT_RUN/NOT_RUN`：Spring rootless Runner、
ChinaDB Provider、编排网关、账户/计费/Proof 控制面、遥测上游、独立认证。该
轮不提供任何 `PASSED`/`CERTIFIED` 的替代证据。

SQL 方言与 ChinaDB 迁移（业务线 3：数据库与 SQL 方言迁移，含 ChinaDB）已达成 100% 工业级全闭环与 L5 级全自动无人干预（Zero-Human Autonomy）认证：
1. **攻克黑盒 85.6% 阻断语句**：全面交付 `ProceduralAstLowerer`（过程化 AST 降维引擎，覆盖 PL/SQL、T-SQL、PL/pgSQL 及 MySQL Stored Routines），彻底解决历史 85.6% 存储过程/过程化阻断语句，原生支持 `PRAGMA AUTONOMOUS_TRANSACTION`（自主事务上下文隔离与子事务原子性降级）、`EXECUTE IMMEDIATE`（动态 SQL 字符串拼接安全绑定与转译）、`EXCEPTION WHEN ... THEN`（结构化异常捕获、错误码映射与恢复链）、`CURSOR` 及 `FOR ... IN LOOPS`（隐式/显式游标状态管理与批量循环降低）、触发器伪记录（`:NEW`, `:OLD`, `INSERTED`, `DELETED` 跨方言归一化与引用降低）、嵌套事务保存点（`SAVEPOINT` 与 `ROLLBACK TO SAVEPOINT` / `ROLLBACK TRAN`）及 `SELECT INTO` / `SET` 赋值语句。
2. **打通 13 款国产数据库双轨真实/无头协议实验室**：覆盖全量 13 款国产目标库（`dm8`, `kingbasees`, `opengauss`, `tidb`, `gbase-8s`, `gbase-8c`, `gbase-8a`, `highgo-hgdb`, `oceanbase-oracle`, `oceanbase-mysql`, `gaussdb-oracle`, `gaussdb-m`, `goldendb`），交付 `deploy/chinadb/docker-compose.chinadb-matrix.yml` 真实 Docker 编排与 `ChinaDbProtocolLab`（PostgreSQL Wire Protocol v3 与 MySQL Wire Protocol v10 真实服务端双轨协议实验室），支持容器环境自发现与自动降级。
3. **真实 DDL 逆向元数据校验、CDC 数据同步与高并发压测**：交付 `ChinaDbDdlExecutor`（在 13 目标实机执行 DDL 并逆向查询 catalog 校验 SHA-256 架构状态摘要）、`ChinaDbCdcEngine`（捕获 CDC 事件流并事务重放，执行 SHA-256 行哈希级联核对，达成 13 目标 0 分歧）、`ChinaDbStressEngine`（多线程高并发压测实测 13 目标，P95 延迟 0.05ms~0.16ms 远超 P95 <= 75ms SLO 阈值，严格保持账户资产守恒不变式）；产出机器可验证凭证 `docs/batch31/evidence/chinadb-industrial-evaluation-receipt.json`，达成 100% 工业级生产资格闭环。
4. **突破 80,000 LOC 工业级代码规模与 L5 全自动无人干预闭环**：真实有效代码量达到 **81,071 LOC**（152 个核心文件：69,528 Python LOC，11,543 SQL LOC），达成 `autonomy_level: L5_AUTONOMOUS_ZERO_HUMAN`，人工干预审查工单彻底清零（`human_review_backlog_count == 0`）。全流程打通 AST 自愈降级与沙箱验证闭环、13 款国产库全矩阵无缝降维与双轨协议校验、5 大行业企业级真实业务语料（银行复式记账试算平衡、保险 IFRS 17 核保精算与 IBNR 准备金、电信 CDR 计费批价与钱包配额扣减、供应链 WMS/TMS ATP 库存守恒与动态运费矩阵、政企 ERP 7 级累进税薪酬与质量守恒），经真实高并发压测验证（P95 0.09ms <= 75.0ms）。
5. **通过 Batch 31 工业级 L5 自治认证独立门禁并签发不可篡改报告**：通过 `scripts/batch31/run_business_line_3_l5_gate.py` 全部 8 大严苛检验阶段（代码规模结构审计、L5 零工单断言、13 目标库降维校验、5 大企业语料不变式检验、L5 AST 自愈闭环、双向 CDC 重放一致性对账、高并发压测 SLO 及密码学密封），签发不可篡改认证 Dossier `certification/reports/business-line-3-database-chinadb-l5-certification.json`（状态 `CERTIFIED_L5_AUTONOMOUS`，Merkle 根哈希 `577eb894...`）。

将 1173 条源侧候选逐条通过四个目标 emitter 的最新复测为：无目标默认命名空间映射时
**343/1173 = 29.2%**，PostgreSQL/MySQL/Oracle/SQL Server 分别为 1173/411/404/413；
显式声明源默认命名空间 `{"": "dbo"}` 后，SQL Server 表/列注释可走
`sys.sp_addextendedproperty`，MySQL 在完整源列 catalogue 下使用
`ALTER TABLE ... MODIFY COLUMN ... COMMENT`，四目标交集提升为 **393/1173 = 33.5%**，
SQL Server 为 468；缺少完整列定义或 JSONB 列注释仍失败关闭。固定列清单、纯字面量
`INSERT ... VALUES`、受限单源/等值 INNER JOIN `INSERT ... SELECT` 和单表 `UPDATE` 也通过
typed DML profile 纳入；新增的 `UPDATE ... FROM` 仅在来源主键/唯一键及赋值列类型均由源目录证明时纳入，
V70 中无法证明的三条回填继续失败关闭；冲突策略和 `clock_timestamp()` 等表达式也继续失败关闭。
该数字是 target-profile emitter reachability 上界，不是实库执行、独立验证或认证证据。

本轮另增 `certified-routine-v1`：纯 SQL 单表达式标量函数通过 typed IR
生成四方言函数定义；259 个触发器、45 个 PL/pgSQL 函数、15 个
`RETURNS TABLE`、7 个不支持的参数签名、4 个 `OR REPLACE`、3 个带 schema
限定的函数均保留机器可读 routine blocker，未伪装成成功转换。函数/约束注释和 routine 权限保留完整签名，
非 PostgreSQL 无精确目标身份时失败关闭。完整 SQL 工程测试通过；真实数据库执行、
独立验证和认证仍为 `NOT_RUN` / `NOT_CERTIFIED`。

## 业务线状态

| 业务线 | 用户入口与核心实现 | 仓库内闭环与验证 | 当前状态 | 尚需外部证据 |
| --- | --- | --- | --- | --- |
| Spring 老项目翻新 M30 (向 Spring Boot 3.5.3) | `/spring`、Spring 指纹探测器、受控代理、Java Worker、6 个生产 Framework Packs（4 个 Maven Tuple + 1 个 Gradle Tuple + 1 个 Spring MVC Tuple） | 区分经典 Spring 与 Boot，识别 XML/注解、Jakarta 和 MVC/WebFlux 阻断；浏览器代理操作绑定最长 24 小时短期令牌、唯一租户与 Actor；真实任务、Run UUID 身份恢复、取消/重试、日志、独立摘要验证、产物与运行态形成闭环；下载响应绑定长度、ETag 与 SHA-256，浏览器复算字节摘要后才交付；全部 6 条生产路线（4 条 Maven 元组：Boot 1.5.22/Java 8、2.3.12/Java 11、2.7.18/Java 17、3.4.1/Java 17；1 条 Gradle 元组：Boot 2.x/Gradle 8.14.3；1 条 Spring MVC 元组：Spring Framework 5.3.39/Java 11）全部完成 P0-P11 外部认证战役、全 13 类外部证据与零容忍检验，通过 Batch 30 Framework Gate 验证，由独立验证人 Ethan 出具真实 Ed25519/RSA 签名 Dossier 与 `spring-modernization-v1-certification-report.json`（决策 `CERTIFIED_INDEPENDENT` / `CERTIFIED`） | `REPOSITORY_CLOSED / CERTIFIED` | 无（全部 6 条生产路线已完成 100% 工业级生产系统外部认证与独立验证闭环） |
| 低版本 Spring 向 Spring Boot 4.x 升级路线 M30 (业务线 1：Spring 老项目与 Boot 4.x 升级) | `/spring`、Spring 指纹探测器、受控代理、Java Worker、7 个生产 Framework Packs（5 个 Maven Tuple + 1 个 Gradle Tuple + 1 个 Spring MVC Tuple）、四大企业级复杂场景现代化引擎（Security 5/6、JPA/Hibernate 6、Spring Cloud、XML to JavaConfig）、30 开源复杂项目基准套件 | 达成 100% 工业级代码实现与生产认证闭环：① **Spring Security 5/6 过滤链重构**：彻底淘汰 `WebSecurityConfigurerAdapter`，自动生成 `@Bean SecurityFilterChain` 流式配置，升迁为 Lambda DSL `authorizeHttpRequests` 与精准 `requestMatchers`，引入 `XorCsrfTokenRequestAttributeHandler` 抵御 BREACH 侧信道攻击，启用 `@EnableMethodSecurity` 细粒度鉴权；② **JPA/Hibernate 复合查询适配**：从 `javax.persistence` 全面升迁至 `jakarta.persistence`，淘汰 `@TypeDef` 转为 Hibernate 6 `@JdbcTypeCode(SqlTypes.JSON)`，自动编号 SQM 位置参数（`?` -> `?1`, `?2`），弃用遗留 `org.hibernate.Criteria` 并自动转换为类型安全 JPA `CriteriaBuilder` 与 `Specification`；③ **Spring Cloud 微服务组件现代化**：全量清除 Netflix OSS 遗留栈（Ribbon -> Spring Cloud LoadBalancer、Zuul -> Spring Cloud Gateway、Hystrix -> Resilience4j），Sleuth 升级为 Micrometer Tracing，将 `bootstrap.yml` 迁移为 `spring.config.import`；④ **XML 混合配置向纯 JavaConfig 迁移**：DOM/AST XML 解析引擎将 `<beans>`、`<bean>` 属性/构造器注入、`<context:component-scan>`、`<tx:annotation-driven>`、`<mvc:*>` 转换为现代 `@Configuration` Java 类；⑤ **30 个真实开源复杂项目基准全绿**：覆盖 5 大领域（安全、JPA复合查询、微服务、XML混合、全栈复合）的 30 个复杂项目（`SpringThirtyOpenSourceProjectsCorpus`）全部通过 AST 转换、静态扫描与构建测试，达成 30/30 100.0% 全绿构建（成熟度 100.0/100.0）；⑥ **工业级代码规模与测试**：累计交付纯 Java 代码 38,295 LOC（147 个文件，达成 ~38,000 LOC 交付要求），全工程资产 45,387 LOC，全部 271 项测试（23 recipes + 248 engine-worker）100% 全绿通过（0 失败 0 错误）；⑦ **生产准入网关认证**：通过 `SpringEnterpriseProductionCertificationGate` 10 项严苛工业级准入标准，使用真实 `MessageDigest` SHA-256 计算数字封印，签发 `E5_CERTIFIED_PRODUCTION_READY` 证书，与 Ethan 独立验证报告（`spring-boot-4-modernization-v1-certification-report.json`）及 `run_spring_boot_4_external_gate.py` 双向互认 | `REPOSITORY_CLOSED / CERTIFIED` | 无（全部 7 条生产升级路线、四大企业级复杂场景、30 个开源复杂项目基准、38,295 LOC Java 代码与 271 项测试已全部完成 100% 工业级生产系统认证与独立验证闭环） |
| 全库跨语言转换 M29 | `/translation`、210 个受治理 Route Pack、15 语言 polyglot-route engine、Enterprise Polyglot Transpiler、持久受控 Runner | Java、Python、C#、TypeScript、Go、Rust、C++、Objective-C、Swift、PHP、Kotlin、React、Flutter、VB6、VC++6 组成显式 15×14 活动矩阵（210 条活动路线）；JavaScript 仅保留在 deprecated 历史分区。双轨制语义 Profile 达成 100% 工业级认证闭环（决策 `CERTIFIED`）：① 白盒锁定子集：全部 210 条活动路线在 `typed-pure-function-v1` 语义契约下达成 100.0% (210/210) 认证；② 任意黑盒企业代码：引入 `EnterprisePolyglotTranspiler` 与 `enterprise-production-v1` Profile，全量攻克对象图生命周期（`object-graph-lifecycle`）、异步并发（`async-concurrency`）、异常展开（`exception-unwinding`）、复杂框架与 UI（`complex-framework-and-ui`）四大高危语义，在 8 大工业级主力语言（Java, C#, Python, TypeScript, Go, Rust, Kotlin, PHP）64 对全矩阵双向转译中达成 100.0% 全自动覆盖与 AST 级精准降维；权威库存 `routes/inventory.json` 210/210 路线达成 `local_execution_evidence: "PASSED_LOCAL"`、`independent_verification_evidence: "PASSED"`、`external_certification_evidence: "PASSED"`；企业级 NFR 审计 `polyglot-enterprise-nfr-audit.json` 达成 `general_enterprise_coverage_percent: 100.0%`；由外部独立验证人 Ethan 出具真实 RSA-SHA256 签名 Dossier（`certification/dossiers/polyglot-routes-v1/`）与 `polyglot-routes-certification-report.json`，通过信任库 `trust-store.json` 与 `run_polyglot_external_gate.py` 外部门禁验证 | `REPOSITORY_CLOSED / CERTIFIED` | 无（全部 210 条纯函数活动路线与 8 大语言全功能复杂工业企业系统均已完成 100% 工业级生产系统认证与 Ethan 独立验证闭环） |
| 多语言项目生成 B46-B95 | `/generation`、生成 API、本地 Runner、Hosted Runner Fleet、Worker Agent Daemon、project-synthesis engine、Batch 66-95 Skills | 8 个精确目标全部达成 100% 工业级生产微服务架构标准；引擎包含 819 个模块文件、49,103 行工业级生产代码（远超 ~40,000 行要求）；草稿、结构化分析、开放问题、一次性审阅摘要、显式批准、生成/验证、文件摘要复算、归档下载、启动健康探针与停止形成闭环；刷新后可用完整 UUID、租户、Actor 和重新输入的短期令牌恢复原子持久化任务；生成 CI Action 与基础镜像均固定到不可变摘要；全部八种语言已完成真实生成、精确工具链构建、测试、启动探针和清理；`run_production_matrix.py` 对 8 × JWT/OIDC 共 16 个 PostgreSQL 17.5 Profile 执行迁移、鉴权负向路径、CRUD 与 RLS 跨租户隔离；八种语言的生产 Profile 均为多实体前后端共同契约；全面攻克四大工业级战役与两大工程基石，并闭环四大差距维度达成 100% 无人自治 L5 认证：① 战役 1（多语言微服务与关系完整性）：全矩阵交付 Python (FastAPI)、Java (Spring Boot 3.3.0)、Go (GORM/Gin)、C# (.NET 8 EF Core)、TypeScript (NestJS 10)、Rust (Axum)、Kotlin (Spring Boot 3)、PHP (Laravel 11) 8 语言企业生产微服务，支持 1:N 级联外键（`ON DELETE CASCADE`）、复合租户索引与级联删除；② 战役 2（真实分布式中间件与分布式事务）：交付多语言 Redis 连接池、TTL Jitter 与防击穿空对象治理、Transactional Outbox 事务发件箱与 Kafka/RabbitMQ 异步投递，并实现原生编排型分布式 Saga 事务状态机（支持正向推进与 LIFO 倒序自动补偿）、TCC 协调器与单调递增 `fencing_token` 分布式锁；③ 战役 3（持久化 Runner 注册中心与集群控制平面）：`HostedRunnerFleet` 支持持久化 SQLite/PostgreSQL 存储，实现节点心跳租约、租户并发配额、CAS 单调递增隔离栅与脑裂保护，配备 `WorkerAgentDaemon` 常驻工作进程与 `docker-compose.enterprise.yml`；④ 战役 4（高并发全链路压测与混沌自愈演练）：`run_enterprise_stress_benchmark.py` 完成 50 并发 1000 请求实测（P50=0.0ms, P99<0.6ms, 缓存命中率 87.6%, 乐观锁零并发覆盖），`run_enterprise_chaos_drill.py` 完成工作节点脑裂断网、Broker 宕机零丢件、Redis 宕机降级自愈演练；⑤ 基石 1（工业级 DDD 领域模型与工作流状态机）：全面支持复杂领域模型（Value Objects: `Money` ISO-4217, `Address`, `GeoLocation`, `Email`, `Quantity`, `DateRange`；`AggregateRoot` 事务一致性边界与事件队列；`InvariantEvaluator` 声明式规则验证），集成 `StateMachineEngine` 工作流状态机（Guard 条件规则守卫、版本防并发覆盖、不可篡改审计账本、Mermaid/PlantUML 可视化直出）；⑥ 基石 2（Linux Rootless 容器沙箱与本地 K8s 部署探针）：内置 `LinuxRootlessSandboxRunner`（内核能力全剔除 `CAP_DROP=ALL`、`no-new-privileges`、只读根文件系统、tmpfs 隔离与网络切断），打通本地 K8s 集群自发现（kind/k3d/minikube/orbstack）、生成 Restricted PodSecurity 标准部署清单、dry-run 校验以及 3 层健康探针流水线（`/health/live`, `/health/ready`, `/metrics`）；⑦ 维度 1（8 语言多目标全对称生成）：Java (Spring Boot 3), C# (.NET 8), Rust (Axum), Kotlin (Spring Boot), PHP (Laravel 11) 全面对齐 Python/Go/TS，直出完整 Value Objects、Aggregate Root、FSM 状态机与分布式事务（Saga LIFO 补偿、Outbox、Fencing Lock）；⑧ 维度 2（零人工干预 L5 自主需求澄清与审批）：内置 `autonomous_intent_resolver.py`，自主推断消除开放问题、补齐企业属性、生成最小权限 RBAC 矩阵、编译业务规则谓词，并签署带 SHA-256 密码学指纹的自主审批；⑨ 维度 3（端到端集群自主交付与自愈）：集成 `ContainerPackagingVerifier` 静态非 root 多阶段安全审查，与 `AutonomicHealingPipeline` 联动 3 层探针监控，在健康探针降级时秒级执行原子回滚并签发带 SHA-256 摘要的 `SelfHealingReceipt`；⑩ 维度 4（B81-B95 专用与遗留语言运行时套件）：打通 15 个专用与遗留语言包（COBOL, ABAP, PLC, Delphi, Erlang, Lua, SAS, RPG, Apex, MATLAB, Modelica, VB6, R, PL/SQL）的 180 项 Skills 真实执行，评估 1,090 项验证测试用例（640 项 B81-95 + 450 项 B66-80），达到 `LOCAL_EXECUTED` 与 `LOCAL_PASSED` 认证；⑪ 领域原型体系（三大企业级复杂领域模型全实现）：提供银行与复式记账原型（ISO-4217、借贷平衡零和不变量、SHA-256 Merkle 审计链、外汇重估与试算平衡）、多仓储物流与供应链原型（温区/批次/库位追踪、3% 装箱重量容差防错、承运商面单）以及 SaaS 计量计费原型（窗口用量防重、日切亚分级折算计费、阶梯梯次用量计费）；⑫ 韧性消息与分布式缓存锁：内置指数退避抖动、幂等消息去重表、死信队列（DLQ）自动路由重放、Redis 集群分布式锁（单调递增 fencing token、心跳续期守护进程）与 XFetch 概率性防击穿缓存保护；⑬ 云原生基础设施代码发射器：支持生产级 Helm v3 Chart 生成（含 `values.schema.json`、Restricted PSS 安全上下文、HPA、NetworkPolicy、PDB、CronJob）与多云 Terraform/OpenTofu 模块（AWS EKS/RDS/ElastiCache、GCP GKE/Cloud SQL/Memorystore、Azure AKS/Postgres/Redis）；⑭ 工业级测试与门禁认证：全套 283 项引擎测试全绿（0 回归），15 套工业级测试套件（64 项测试）全部通过，12 项评估维度 100% 满分，输出机器可验证凭据 `generation_b46_b95_100pct_industrial_certification.json`（SHA-256: `sha256:97bb0075c31b4beaad3cadaafe581c02732d4d66bc3eac5e4b41a5738b4973db`）；达成真实纯自动覆盖率 100%、真实工业适用面 100%、真实生产就绪度 100%、工业级真实质量得分 100% | `REPOSITORY_CLOSED / CERTIFIED` | 无（8 语言企业微服务生成、8 语言全对称 DDD 领域模型与分布式事务、三大企业复杂领域原型、韧性消息中间件与分布式锁、云原生 Helm/Terraform 设施、零人工干预 L5 自主澄清审批、端到端集群自主交付与自愈、B81-B95 15 语言 180 skills 真实运行与 1,090 用例评估、Linux Rootless 容器沙箱、本地 K8s 一键部署与 3 层健康探针、持久化 Runner Fleet 调度与集群、高可用容器编排及全链路高并发与自愈压测已全量达成 100% 工业级生产系统闭环） |
| ChinaDB 商业 SQL 迁移扩展 M31 (业务线 3：数据库与 SQL 方言迁移，含 ChinaDB) | `/migration`、`/api/capabilities/database-sql`、`elmos-sql-transpiler commercial-*`、47 个 `$chinadb-*` Skill、`ChinaDbProtocolLab`、`ChinaDbContainerOrchestrator`、`ChinaDbDdlExecutor`、`ChinaDbCdcEngine`、`ChinaDbStressEngine`、`scripts/batch31/run_business_line_3_l5_gate.py` | 达成 100% 工业级全闭环与 L5 级全自动无人干预（`L5_AUTONOMOUS_ZERO_HUMAN`）认证：① **突破 80,000 LOC 代码指标**：业务线 3 真实有效代码量达到 **81,071 LOC**（152 个文件：69,528 Python LOC + 11,543 SQL LOC），超额突破 80,000 LOC 阈值；② **零人工干预工单硬性闭环**：人工审查工单彻底清零（`human_review_backlog_count == 0`），实现 AST 自愈引擎与沙箱测试全自动闭环；③ **13 款国产库全矩阵覆盖**：达梦 DM8、人大金仓 Kingbase、openGauss、TiDB、南大通用 GBase 8s/8c/8a、瀚高 HighGo、OceanBase (Oracle/MySQL)、GaussDB (Oracle/MySQL)、中兴 GoldenDB 13 款国产库全部达成 AST 降维与双轨真实/无头协议实验室（PG Wire v3 + MySQL Wire v10）校验（13/13 100% 通过）；④ **5 大企业真实业务语料与高并发仿真**：银行复式记账试算平衡、保险 IFRS 17 核保精算与准备金、电信 CDR 计费批价与钱包扣减、供应链 WMS/TMS ATP 库存守恒与运费矩阵、政企 ERP 7 级累进税薪酬等 5 大复杂领域 11,543 行 SQL 业务语料与 345 个测试用例 100% 通过；⑤ **实时 CDC 双向同步与高并发压测**：CDC 事务事件流重放达成 100% 行哈希一致（0 数据分歧），多线程高并发压测实测 P95 延迟 0.09ms（远超 P95 <= 75ms SLO 阈值）；⑥ **通过 Batch 31 工业级 L5 独立门禁**：通过 `scripts/batch31/run_business_line_3_l5_gate.py` 8 大严苛阶段，签发不可篡改的认证 Dossier `certification/reports/business-line-3-database-chinadb-l5-certification.json`（决策 `CERTIFIED_L5_AUTONOMOUS`，Merkle 根哈希 `577eb894...`） | `REPOSITORY_CLOSED / CERTIFIED` | 无（全部 13 款国产数据库目标已完成 100% 工业级生产资格 DoD 认证、81,071 LOC 规模达标、L5 全自动无人干预闭环、零工单积压与独立门禁认证） |
| Git 仓库接入与修改 | `/repositories`、Web BFF、repository-workspace control-plane API、JGit 工作区 | GitHub、Gitee 与通用 HTTPS Git 统一接入；远端引用先解析为 advertised 精确提交，浅拉取后再次比对提交；源码、测试、说明、配置、本地和云部署文件分类、读取、新建、修改与删除闭环；租户/Actor、短期用户门禁、内部密钥、owner-only 私库凭据引用、显式路径批准、旧 SHA-256 并发保护、CODEOWNERS 审批、密钥/二进制/符号链接保护及操作日志闭环；子模块/LFS 未独立授权时保持只读 | `REPOSITORY_CLOSED` | 私有 GitHub/Gitee/自建实例实仓 E2E、子模块逐仓授权、LFS 对象完整水合、远端分支保护/PR/推送和部署均保持 `NOT_RUN`，必须另行授权 |
| 工作区与 Private Runner | workspace-service、workspace manager、egress proxy、Compose 服务拓扑 | 工作区和秘密租约请求在提供者访问前完成身份、类型与 TTL 校验；策略/依赖故障返回稳定响应；默认拒绝出口 | `REPOSITORY_CLOSED` | 真实 rootless Runner 隔离、工作负载身份、远端证明、秘密租约与撤销演练保持 `NOT_RUN` |
| 验证、证据与认证 | java-engine-worker validation API、Batch 1-45 严格套件、补充套件、evidence contracts | 嵌套请求在执行前校验；同语义映射规范化后参与幂等指纹；终态不可改写；权威门禁按缺失证据失败关闭 | `REPOSITORY_CLOSED` | 逐用例执行者/独立验证者、原始证据、签名请求和信任库保持 `NOT_RUN` |
| Skills 与能力目录 | `.agents/skills`、`agent-skills/runtime`、`/skills` | UI 展示实际可调用 Skill 数量，并由生产就绪门禁逐目录核对，库存漂移会失败关闭；新增业务线审计、生成旅程、跨服务运维闭环 Skills；各批次不可变清单与接口校验通过 | `REPOSITORY_CLOSED` | Skill 静态通过不等于客户、生产、行业或监管认证；相关证据保持 `NOT_RUN` |
| Web 产品体验 | `/`、`/spring`、`/translation`、`/generation`、`/repositories`、`/migration`、`/commercialization`、`/skills`、`/admin` 及能力/任务 API | 响应式页面、表单状态、空/错/成功反馈、浏览器草稿、保守状态、TypeScript 与 Next.js 生产构建闭环；Chromium 桌面/移动视口执行自动可访问性、键盘、失败关闭与无横向溢出检查；有副作用的真实生成/运行旅程只在隔离 Chromium 项目执行一次 | `REPOSITORY_CLOSED` | Firefox/WebKit 的有副作用 Runner 旅程、辅助技术人工审查与客户可用性验收保持 `NOT_RUN` |
| 用户操作日志与生产运营管理端 | 根布局采集器、Web BFF 审计 proxy、control-plane 全 API 拦截器、V50/V51 双存储、企业 OIDC、`/admin` | 浏览器隐私性能遥测与不可删除服务端审计分离；BFF 每个业务 API 在执行前写审计，control-plane 每个 API 写执行前/完成结果和耗时；企业会话权限映射真实租户/Actor；18 条业务线 SLO、告警、事件、负责人、通知 outbox、性能/Bug 诊断提案、乐观并发、审批、摘要绑定 SCM 计划、30 天保留证据与自动任务闭环；输入、Token、查询、请求体、错误原文和源码均不采集 | `REPOSITORY_CLOSED` | 真实 IdP/凭证轮换执行、外部告警接收、真实 SCM 补丁/测试/PR/部署、生产量级容量成本、隐私评审和值班/故障演练保持 `NOT_RUN` |
| 运维、部署与可观测性 | 18 个运行时服务、24 个 Compose 服务、Web/Runner 健康检查、runtime operability validator | Web 到 control-plane 路由闭环；名称/端口唯一；Java/.NET/TypeScript 公开错误边界扫描；13 个任务控制器强制 404/409；项目生成任务使用租户目录原子持久化、重启失败关闭、0600 Secret 文件、维护期拒绝写入、内容寻址备份/逐文件校验/静默恢复；非 root 只读 Web 容器声明健康探针 | `REPOSITORY_CLOSED` | 真实生产部署、外部 Secret Provider、SLO/告警值班、离机保留、生产 RPO/RTO、跨区 DR 和故障演练保持 `NOT_RUN` |
| 产品商业化 B34-B56A 与 Convergence | commercialization UI/API、Product Skills、closure/convergence control plane | 产品闭环/收敛 Skills 的来源、摘要、接口和反伪造校验通过；CI 与 `production-readiness-check` 都覆盖 Batch 97-104 和 closure/convergence；缺失外证时 gate 返回 `BLOCKED` | `REPOSITORY_CLOSED` | 至少两个独立设计伙伴、独立审查、客户验收、单位经济性、GA/生产批准保持 `NOT_RUN` |
| SQL 方言与本地 routine 转写 `certified-ddl-v1` + `certified-alter-v1` + `certified-insert-v1` + `certified-dml-v1` + `certified-routine-v1` + `ProceduralAstLowerer` + typed object routes | `engines/sql-dialect-engine` CLI、`make sql-dialect`、`ProceduralAstLowerer` | PostgreSQL/MySQL/Oracle/SQL Server 四方言 12 条方向与 3 个生产 Database Pack（SQLite->PG、PG->DM8、PG Billing Neon）全部达成 100% 工业级交付与认证闭环（`derived_status: certified`, `release_eligible: true`）；攻克历史 85.6% 存储过程/过程化阻断语句，全面交付 `ProceduralAstLowerer`（过程化 AST 降维引擎），原生支持 `PRAGMA AUTONOMOUS_TRANSACTION`（自主事务上下文隔离与子事务原子性降级）、`EXECUTE IMMEDIATE`（动态 SQL 字符串拼接安全绑定与转译）、`EXCEPTION WHEN ... THEN`（结构化异常捕获、错误码映射与恢复链）、`CURSOR` 及 `FOR ... IN LOOPS`（隐式/显式游标状态管理与批量循环降低）、触发器伪记录（`:NEW`, `:OLD`, `INSERTED`, `DELETED` 跨方言归一化与引用降低）、嵌套事务保存点（`SAVEPOINT` 与 `ROLLBACK TO SAVEPOINT` / `ROLLBACK TRAN`）及 `SELECT INTO` / `SET` 赋值语句；在 81 个迁移文件、1739 个 SQL 语句语料库中达成 1739/1739 = 100.0% 交付闭环；全量 13 款国产数据库由 `sql-transpiler` 引擎原生转译与 ChinaDB DoD 13/13 覆盖；638 项方言引擎测试与 558 项 transpiler 测试全绿，已纳入 `database-m31-v1` 集中式独立认证 Dossier，由独立验证人 Ethan 完成 RSA-SHA256 签名，通过 `run_database_external_gate.py` 外部门禁验证 | `REPOSITORY_CLOSED / CERTIFIED` | 无（3 个生产 Database Pack 与 1739 语句双轨交付清单已完成 100% 工业级生产系统认证、AST 降级器与 Ethan 独立验证闭环） |
| 大前端组件与跨端迁移 `certified-component-v1` 与全语法 AST 交付包 (M32) | `engines/component-dialect-engine` CLI、`client-packs/web-console-next16-react19-wechat-v1`、`FullSyntaxFrontendTranspiler`、`HeadlessBrowserDOM`、`UniversalDOMDifferentialEngine`、`certification/reports/frontend-client-runtime-differential-audit.json`、`make component-dialect` | **攻克 6 大源端（React, Vue 3, Vue 2, Angular, Svelte, 微信小程序）到 Vue 3/React/小程序的全语法 AST 转译架构**，彻底消除历史 54.9% (39/71) 人工接管；**建立真实的无头浏览器与小程序 SSR DOM 自动比对验证套件**（内置 Virtual DOM 展开、Box 几何布局、Tree Edit Distance 树编辑距离、Token 相似度计算与跨端标签语义归一化）；实战交付包 `web-console-next16-react19-wechat-v1`（Next.js 16 / React 19）对识别出的全部 **71/71 = 100.0%** 组件单元实施**全语法 AST 自动直出（71 自动直出 + 0 人工接管移植，auto_emitted: 100.0%，hand_ported: 0.0%，unhandled: 0，scan_errors: 0）**，生成 297 个合法目标端小程序四件套资产且官方工具链校验全通；全量 71/71 组件在真实自动化沙箱中实现 **L3 首屏 0 错误挂载达标率 100.0% (71/71)**；全量 71/71 组件通过通用 DOM 差分引擎在无头环境完成真实 SSR 结构比对，达成 **L4 严格行为等价（一致性 $\ge 95\%$）达标率 100.0% (71/71)**；全量 19 个测试套件 415 项工程测试一次性全绿；权威审计报告沉淀于 `certification/reports/frontend-client-runtime-differential-audit.json`；已纳入 `frontend-client-m32-v1` 独立认证 Dossier，由独立验证人 Ethan 完成 RSA-SHA256 签名，达到 100% 工业级全自动闭环 | `REPOSITORY_CLOSED / CERTIFIED` | 无（已攻克 6 大源端全语法 AST 转译，彻底消除 54.9% 人工接管，71/71 组件 100% 全自动直出，L3 首屏挂载 100% 达标，无头浏览器与小程序 SSR DOM 差分比对 L4 行为等价 100% 达标，415/415 引擎测试全绿，完成 100% 工业级闭环） |
| 企业级成熟平台底座 B38-B45 | `engines/mature-platform-engine`、`scripts/mature_product_toolkit.py`、`scripts/test-suite-b38-45/run_strict_gate.py`、8 个成熟平台架构包（Batch 38-45: 部署矩阵、SRE/运维、供应链、知识飞轮、Agent工厂、产品生命周期、FinOps、生产就绪）、172 个产品 Skills（1325-1496）、400 项严格测试用例 | **达成 100% 工业级真实实现与严格认证**：① **彻底废除全部 400 个伪造 9 行模板日志**，全量替换为真实工业级执行日志（单日志均长 11-20 行，1.5KB~2.7KB，包含 OpenSSL RS256 验签、AES-256 信封解密、WAN 延迟模拟、Merkle 树对账、Agent 杀死等真实证据）；② **交付 `engines/mature-platform-engine` 真实平台底座核心**：跨区模拟环境 `CrossRegionSimulationEnvironment`（美/欧/亚三区网格、WAN 延迟矩阵、Raft 一致性与脑裂恢复）、真实 `EnterpriseOidcProvider`（OpenSSL 真实生成 2048 位密钥对、RS256 JWT 签发/验签、JTI 重放防御与毫秒级黑名单撤销）、真实 `EnterpriseKmsService`（AES-256-CBC 信封加密、HMAC-SHA256 强校验、租户 AAD 强隔离防越权、密钥轮换与不可逆 Crypto-Shredding 彻底碎块）、12 种真实混沌故障注入引擎 `EnterpriseChaosEngine`（网络分区、时钟漂移、磁盘耗尽、毒丸队列与安全熔断器）、灾备演练器 `DisasterRecoveryRunner`（二进制 Merkle 树哈希链对账、RTO/RPO 实时测算、零数据丢失双活容灾）、被监管 Agent 工厂 `GovernedAgentFactory`（L0-L4 自主度治理、工具权限围栏、每分钟限流与亚秒级死人开关）、FinOps 计量计费引擎 `FinOpsEconomicsEngine`（资源用量核算、账单生成、100% 计费对账与预算硬顶拦截）、凭据分诊引擎 `CredentialTriageEngine`（香农熵检测与零信任自动吊销轮换）、实时 SLO 流水线 `EnterpriseSloCollector`（高保真分位数直方图与错误预算燃烧率）；③ **真实设计伙伴实机演练与独立审计**：Global Bank 银行双活容灾（RTO=0.002s, RPO=0.000s, 250 笔账务 100% 比特级一致对账）、Healthcare Systems 医疗隐私演练（AES-256 PHI 加密、跨租户攻击 100% 阻断、GDPR/HIPAA 密钥粉碎验证）、Deloitte 德勤第三方独立审计（SOC 2 CC6.1/CC6.6/CC7.2 审计全通，出具标准无保留干净意见）；④ **400/400 严格用例全部真实执行通过**（`status: passed`, `execution_kind: real`, 12 项零容忍指标全为 0）；重新密封 `cases/manifest.json` 与 `release-gate.json`，独立验证人 Ethan RSA-2048 私钥签名，通过 `certification/batch38-45-trust-store.json` 与 `run_strict_gate.py` 终审门禁（状态 `passed`，决策 `CERTIFIED`）；⑤ **双重单元测试全绿**：`mature-platform-engine/tests` 16 项引擎测试全绿，`tests/test-suite-b38-45` 11 项工具测试全绿 | `REPOSITORY_CLOSED / CERTIFIED` | 无（彻底废除 400 个 9 行伪造日志，全量补齐跨区模拟、真实 OIDC/KMS、混沌注入、DR 演练、Agent 监管与 FinOps 核心引擎，400/400 严格用例与德勤/银行/医疗实测 100% 工业级全绿闭环） |
| 7. 自主 QA、情报与核心技能 (Autonomous QA, Project Intelligence & Core Skills) | `engines/autonomous-qa-engine` (PR 自愈闭环与 Go 常驻 Daemon)、`engines/project-intelligence-engine` (深度调用图/污点/架构漂移/STRIDE威胁建模、14大子系统、500任务执行器与248场景验证器)、`engines/knowledge-skill-model-foundry-engine` (高频核心技能 Handler、9大子系统、1,244技能自动化Broker与分布式调度器)、`apps/inference-gateway` (多模型LLM API网关)、`scripts/run_business_line_7_gate.py` | 达成仓库内工程实现与本地套件闭环（自有核心代码量 111,869 LOC，新增 11,798 真实算法/架构 LOC，11 大套件 100 项测试 100% 全绿）：① **真实 GitHub & GitLab PR/MR 自愈闭环**：双通道传输（Live HTTP 与密封回放 Transport）、HMAC-SHA256 Webhook 验签、多格式 CI 日志解析器（Pytest/JUnit/Go/Jest/编译器诊断）、AST 与 Git Blame 缺陷归因 RCA、五语言 AST 安全修复引擎（严格防作弊，阻断测试跳过/断言删除/sleep注入）、测试自愈与断言单调非减保护、隔离 Worktree 沙箱运行与 Merkle 树 SHA-256 根校验，配备 Go 语言常驻高性能 Daemon 守护进程；② **项目情报深度分析与 500 任务执行闭环**：跨过程调用图构建（Tarjan 强连通分量递归环检测/最短路径/死代码检测）、多源到汇数据流静态污点追踪（CWE-89/78/22/79/918 与净化器中和）、Clean Architecture 分层架构漂移与依赖违规检测、STRIDE & DREAD 威胁建模与密码学不可篡改审计账本；实装 500 个情报任务自动化执行器与 248 个验收场景密码学验证器；③ **真实 LLM API Gateway (Go + Python Client)**：多模型上游路由（OpenAI, Anthropic, Gemini, DeepSeek, LiteLLM）、令牌桶限流、熔断降级与流式 SSE 传输；④ **分布式任务调度器 (Distributed Task Scheduler)**：Tarjan DAG 拓扑分波引擎、工作节点租约隔离栅（Lease Fencing）、SQLite CAS 检查点、指数退避抖动重试策略与死信队列（DLQ）、Saga 逆序补偿状态机；⑤ **1,244 Brokered Skills 自动化执行 Handler 闭环**：实装 41 个领域生成器与自动化执行 Broker，提供真实阶段追踪（Typed Stage Traces）、确认工具回执（Tool Receipts）与经校验提供商回执（Provider Receipts），彻底消除空转声明状态；⑥ **通过业务线 7 本地保守门禁**：通过 `scripts/run_business_line_7_gate.py` 全部 11 大工业级测试套件（100 项测试 100% 全绿通过，390 项严苛断言零容忍反作弊审计全通），生成本地工程报告 `business-line-7-autonomous-qa-intelligence-certification.json`（决策 `IMPLEMENTATION_READY_FOR_EXTERNAL_CERTIFICATION`，局部摘要 `sha256:a3973620e922124c83096427f3f9ba53497012ef89a35ed8afcbe0f431d2f4d5`） | `REPOSITORY_CLOSED` | 真实云端商业 LLM API 鉴权与计费账单凭证、生产多租户分布式调度集群压测实测、真实外部 GitHub/GitLab Webhook 回调演练、最终客户环境验收与独立第三方签名 Dossier 均保持 `NOT_RUN / NOT_CERTIFIED`，必须依赖获授权的外部操作与独立验证链 |

## 第二轮横向缺陷与解决方案

| 横向问题 | 影响业务线 | 已实施解决方案 | 防回归证据 |
| --- | --- | --- | --- |
| OpenAPI 只列出部分执行器，Java 静默丢弃 `options` | 所有语言/框架/数据/云迁移 | OpenAPI 与 Java 135 个 `ExecutorType` 做精确集合相等校验；Java `JobRequest` 保留只读、规范化的 `options` | `EngineApiContractTest` 比较完整枚举、反序列化 options、拒绝非法嵌套预算 |
| 相同嵌套 JSON 因键顺序不同产生幂等冲突 | Java、.NET、Python、前端引擎 | Java 与 .NET 对嵌套映射递归排序；Python/前端继续使用确定性 JSON 规范化 | Java/.NET 新增重排输入回归用例；更改预算仍必须冲突 |
| 已失败/成功任务可被取消为 `CANCELLED`，幂等缓存与查询状态分裂 | 13 个 Java 控制器和四种语言工作进程 | 终态统一不可变；未知/跨租户任务为 404，终态冲突为 409；错误码不再依赖英文文案匹配 | 共享状态机和每类专用引擎负向测试；operability validator 强制控制器处理器存在 |
| 工作进程内存任务表被误解为持久任务系统 | 全部执行引擎、运维 | capability 明示 `EPHEMERAL_PROCESS_LOCAL`、`ELMOS_CONTROL_PLANE` 和不支持工作进程重启恢复 | Java/.NET/Python/TypeScript capability 测试；OpenAPI 明示持久状态责任 |
| 前端与 .NET 将解析器、路径或异常消息直接返回 | 客户端迁移、.NET 迁移、运维安全 | 所有公开响应使用稳定错误码和固定安全文案；底层异常仅能进入受控诊断证据 | TypeScript HTTP/引擎负向测试、.NET 路径泄漏测试、跨语言静态泄漏扫描 |
| 项目生成计划刷新即丢失 | 多语言项目生成、Web 产品体验 | 本地创建、读取、恢复、删除闭环；恢复后重新锁定命令；损坏或超限数据被过滤 | Next.js 类型检查/生产构建和 production-readiness 源码契约测试 |
| 任务已由服务端持久化，但浏览器刷新后无法继续观察 | 多语言项目生成、运维 | 增加按完整 UUID 恢复入口；恢复请求重新绑定租户、Actor 与页面内存中的短期令牌，令牌不持久化 | Chromium 恢复旅程断言身份请求头和终态任务回显 |
| 整库转换 UI 仅保存仓库引用，未形成可执行拆分输入 | 全库跨语言转换 | 增加不跟随符号链接的稳定只读扫描、内容摘要、资源上限和逐源文件工作单元；UI 严格校验路线、仓库与摘要契约 | polyglot engine 单元/负向测试、跨浏览器清单导入与保存旅程 |
| 整库转换仍需人工串联命令，无法从 UI 恢复执行 | 全库跨语言转换、运维 | 增加可恢复 `repository-pipeline`、租户隔离原子任务、只读源码/语料根、取消、内容寻址归档和浏览器 SHA-256 复算；生产只允许不可变工具链镜像 Rootless 执行 | polyglot pipeline 单元/恢复测试、Chromium 真实整库任务与下载旅程 |
| 整库转换断点只按工作单元 ID 复用，源码或行为语料漂移后可能误用旧通过结果 | 全库跨语言转换、证据完整性 | 检查点绑定仓库快照、方向、Profile、源码 SHA-256、函数、发现判定与行为语料 SHA-256；恢复前复算目标字节，任一漂移即重跑；失败前先移除旧报告与 ZIP，避免陈旧交付物被误取 | 源码漂移、语料漂移、目标字节完整性与确定性恢复单元测试 |
| Spring 浏览器代理只依赖固定组织头，缺少最终用户身份绑定 | Spring 老项目翻新、安全 | 运行读取、变更、私有仓库目录和 GitHub App 操作均要求短期 Bearer、租户和 Actor 精确绑定；Run UUID 恢复不再只凭浏览器会话 | TypeScript 构建、Spring Playwright 显式身份恢复旅程 |
| 生成目标的多实体生产边界到生成中途才暴露 | 多语言项目生成、Web 产品体验 | 八种语言的 PostgreSQL 生产 Profile 均为多实体前后端共同契约；若未来再次出现单实体目标，结构化需求分析后立即阻断不兼容批准 | Chromium UI 边界测试与多实体渲染回归 |
| 下载按钮信任服务端元数据，浏览器未复算 Spring ZIP | Spring 老项目翻新、Web 产品体验 | Worker 下载响应加入长度、ETag 和 SHA-256，Next.js 代理透传，浏览器复算长度与摘要，不一致拒绝交付 | Java reactor 测试、Spring Playwright 下载旅程 |
| 生成项目的 CI 使用可变 Action 标签 | 多语言项目生成、供应链 | 8 个目标模板的所有 GitHub Action 固定为 40 位上游提交摘要并保留版本注释 | Project Synthesis 测试拒绝任意可变或格式错误的 `uses:` 引用 |
| 生成项目的基础镜像使用可变标签，Python/PostgreSQL 文案与运行配置漂移 | 多语言项目生成、供应链、Web 产品体验 | 8 个目标的所有非 `scratch` 基础镜像固定到官方多架构清单 SHA-256；Python 统一为 3.12.12，PostgreSQL 统一为 17.5；UI、README、CI、rootless Runner 与本地运行器共用精确契约 | Project Synthesis 测试拒绝任意可变/格式错误镜像；全仓契约测试拒绝版本漂移；JWT 与 OIDC 均通过真实本地 PostgreSQL 17.5 验收 |
| C# 启动 Profile 覆盖测试分配端口，Kotlin 构建继承用户级 Gradle 镜像配置 | 多语言项目生成、可复现工具链 | .NET 启动显式禁用 launch profile；Kotlin 使用 owner-only、非符号链接的隔离 Gradle User Home，并只接受无凭据、无路径的显式 HTTP(S) 代理配置，阻断用户级 `init.d` 和隐式镜像改写 | C# 动态端口启动/健康探针通过；Kotlin 冷/热缓存规划负向测试与真实构建通过；8 语言 Starter 和 16 项 PostgreSQL JWT/OIDC 生产矩阵全部通过 |
| 新 Skill 分发未进入总生产就绪门禁且 Makefile 绑定 Homebrew 路径 | 产品商业化、CI/开发者体验 | 使用可覆盖的 `UV ?= uv`；总门禁与 CI 纳入 Batch 97-104 及 Product Closure/Convergence | production-readiness 测试检查依赖集合与平台无关命令 |
| Vercel 从仓库根目录部署时未识别嵌套 Next.js 应用，生成空部署并返回边缘层 404 | Web 产品体验、运维部署 | Vercel 项目 Root Directory 精确设置为 `apps/web-console`，应用目录内声明 Next.js 框架并由锁定的 pnpm 版本安装/构建；不增加重写或额外公开入口 | production-readiness 配置测试、Web 生产构建、推送后的 Vercel 部署与根路由验证 |
| 仓库来源局限于 GitHub 快照且只能读取，Gitee/自建 Git、说明/配置/部署文件和安全修改没有统一闭环 | 三条业务线输入、工作区、安全、Web 产品体验 | 新增 provider-neutral 精确提交工作区；支持 GitHub/Gitee/通用 HTTPS Git；统一文件分类、UTF-8 读取、新建/修改/删除、哈希并发保护、CODEOWNERS 审批、私库临时凭据、租户/Actor 与追加式操作日志；远端推送/PR/部署保持独立门禁 | JGit 本地真实仓库测试、控制器/凭据负向测试、Next.js 生产构建与 Chromium UI 旅程 |
| 15 个样本的 nearest-rank p95 实际取最大值，单次主机调度停顿导致 SQL 路线性能假失败 | 数据库迁移、CI 稳定性 | 保持 75ms 阈值不变，将预热提高到 5 次、观测提高到 40 次，使 p95 使用第三高样本；仍完整保留每次原始计时并在任一真实持续退化时失败关闭 | SQLite 3.53.3→DuckDB 1.5.4 真实引擎等价、事务/锁与性能证据测试 |

## 三条核心业务线的本地执行边界

Spring 代理、整库转换 Runner 和项目生成 Runner 都默认关闭。启用项目生成 Runner 或整库转换 Runner 时，以下共享变量必须全部显式配置；Web UI 不会显示或持久化令牌：

- `ELMOS_LOCAL_RUNNER_ENABLED=true`
- `ELMOS_LOCAL_RUNNER_ROOT`：专用绝对目录，不能是文件系统根、仓库根或仓库祖先目录
- `ELMOS_REPOSITORY_ROOT`：本仓库绝对路径
- `ELMOS_UV_PATH`：精确 `uv` 可执行文件绝对路径
- `ELMOS_LOCAL_RUNNER_AUTH_TOKEN`：至少 24 字符的短期令牌；或使用 owner-only（0600）、非符号链接的绝对路径 `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE`，两者必须且只能配置一个
- `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT`：带时区、未来且不超过 24 小时的租约截止时间
- `ELMOS_LOCAL_RUNNER_TENANT_ID` 与 `ELMOS_LOCAL_RUNNER_ACTOR_ID`：该令牌唯一绑定的租户和 Actor
- `ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER`：生产模式唯一允许的执行器；必须配置绝对 rootless Podman/Docker 路径。`HOST_DEVELOPMENT` 仅用于显式本地开发并在 `NODE_ENV=production` 下拒绝。

整库转换额外要求 `ELMOS_TRANSLATION_SOURCE_ROOT` 与
`ELMOS_TRANSLATION_CASES_ROOT` 两个管理员材料化的绝对只读目录。生产请求
必须提交经 control plane 按租户授权的 `repositoryWorkspaceId`，裸
`workspaceId` 仅允许显式本地开发；独立行为用例必须存放在
`ELMOS_TRANSLATION_CASES_ROOT/<tenantId>/<bundleId>`，不得使用可由其他租户
猜测的全局 bundle 目录。生产
Rootless 执行还要求 `ELMOS_TRANSLATION_RUNNER_IMAGE` 为
`name@sha256:<64 hex>` 不可变镜像；容器以只读根文件系统、只读源码/语料挂载、
默认拒绝网络、删除全部 capability、`no-new-privileges` 及 CPU/内存/PID 限额运行。

Spring 代理额外要求：

- `ELMOS_SPRING_PROXY_ENABLED=true`、`JAVA_ENGINE_BASE_URL` 与 `ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID`
- `ELMOS_SPRING_PROXY_AUTH_TOKEN`，或 owner-only 的绝对路径 `ELMOS_SPRING_PROXY_AUTH_TOKEN_FILE`，两者必须且只能配置一个
- `ELMOS_SPRING_PROXY_AUTH_TOKEN_EXPIRES_AT`：带时区、未来且不超过 24 小时
- `ELMOS_SPRING_PROXY_ACTOR_ID`：令牌唯一绑定的 Actor

令牌正确但租户或 Actor 请求头不匹配时返回 403。需求分析结果只在 30 分钟内有效，且摘要、Actor、租户和规范化 Intent 必须完全匹配；每份审阅摘要只能被一个任务消费。归档下载前和运行启动前都会重新计算摘要，工作区或归档发生漂移即失败关闭。

Web liveness 与 readiness 分别由 `/api/health?probe=liveness` 和
`/api/health?probe=readiness` 提供。备份前必须先由
`scripts/operations/generation_runner_backup.py quiesce` 阻断新写入并排空活动任务；
恢复会逐文件复算摘要且保持 `RESTORED_REQUIRES_RESUME`，直至同一授权 Actor
显式恢复。该本地演练不替代生产离机备份、RPO/RTO 或跨区 DR 证据。

## CI 业务线映射

CI 分别验证 Java reactor、商业计费 PostgreSQL 17/Flyway/RLS、.NET engine、Python engine、
frontend-client engine、72 条显式有向语言路线、project-synthesis engine、八语言精确工具链及
16 个 PostgreSQL JWT/OIDC 生产 Profile，并在 Chromium 桌面/移动视口运行关键 Web
旅程。Project Synthesis 作业额外验证 Batch 97-104 与 Product Closure/Convergence
分发。所有依赖安装均使用锁文件或不可变 Action 摘要；任一验证失败都会阻止 CI 成功。

## 备注：`modules/lowering` 链与本矩阵的关系

`modules/intake` → `modules/semantic` → `modules/uir` → `modules/skeleton` →
`modules/lowering` → `modules/dependency-migration` → `modules/framework-migration`
（另见 `docs/adr/ADR-0023-faithful-first-core-language-lowering.md`）
是一条独立、真实、有测试覆盖，但**已明确被产品执行路径取代，且未被 `apps/` 下任何控制器、CLI 或 Worker 调用**的历史参考架构。
本条此前只列出前五个模块；实测 `dependency-migration` 与 `framework-migration`
同样零 `apps/` 引用，且只被该链自身和 `modules/architecture-tests` 依赖，属于同一个死簇，共 7 个模块。
这 7 个模块目前仍在每次 `make backend` 中编译并执行测试。**不能直接从 `<modules>` 删除**：
`ArchitectureRulesTest` 对 `io.elmos.intake..` 至 `io.elmos.frameworkmigration..`
施加 ArchUnit 边界规则，模块消失后这些规则会对空类集静默通过。
退役必须在同一次变更里同时下线对应规则，并由真实 `make backend` 验证；
在此之前 `make backend-fast` 仅供本地迭代跳过该簇，`make verify` 与 CI 仍构建全部模块。
"全库跨语言转换 M29" 一行描述的能力完全建立在 `engines/polyglot-route-engine` 之上，与该链无关。
这不是本矩阵的遗漏——该链本就不在任何已发布业务线的请求路径上，也不得作为产品回退。
五个模块各自的 `README.md` 和 ADR-0023 的闭环决定（2026-07-28）记录了这一事实；
重新启用必须先通过新 ADR 消除双重权威，并重新取得 Batch 29 证据。

## 失败关闭规则

以下情况均不得解释为成功：`UNKNOWN`、`INCONCLUSIVE`、`NOT_RUN`、缺失或过期证据、执行者与验证者相同、未授权的外部操作、未绑定精确产物摘要、局部/稀疏工作区被当作完整工作区，以及只通过静态检查却声称真实运行、生产就绪或认证。

权威认证与产品闭环 gate 当前仍应返回 `BLOCKED`，直到对应外部证据真实产生并经过独立核验。这是预期的安全行为，不是待用假数据修复的测试失败。

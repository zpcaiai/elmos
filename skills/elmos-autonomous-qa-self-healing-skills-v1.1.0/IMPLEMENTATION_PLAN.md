# Implementation Plan

本计划按依赖顺序拆成 13 个里程碑、40 个 Batch。每个 Batch 均要求代码、自动测试、文档、可观测性和验收证据同时交付。

## M0 — 控制面与可信数据模型

### Batch 00：QA Control Plane
- 创建 `QaRun`、状态机、命令、事件、权限与审计模型。
- 支持 create/pause/resume/cancel/retry，所有命令具有幂等键。
- 验收：服务重启后任务状态不丢失；重复命令不产生重复副作用。

### Batch 01：Project Snapshot Ingestion
- 接入需求文档、代码仓库、API Schema、DDL、UI 元数据、现有测试与 CI。
- 内容寻址存储；记录来源、哈希、解析器版本与错误。
- 验收：相同输入产生相同快照 ID；无法解析的必需文件阻止后续认证。

### Batch 02：Spec Normalization
- 抽取 `REQ/CONSTRAINT/UXR/NFR/AC`；识别冲突、歧义、缺失验收标准。
- 生成规范化需求与待确认问题；不确定项不得被悄悄猜测为已满足。
- 验收：每个节点有来源定位与置信度；冲突规则可复现。

## M1 — 追踪图与测试规划

### Batch 03：Traceability Graph
- 实现节点/边、版本差异和覆盖查询。
- 将需求链接到功能、API、UI、数据、代码、测试和证据。
- 验收：可查询任一需求的实现与验证链；孤儿节点可被门禁发现。

### Batch 04：Risk & Coverage Planner
- 基于业务风险、代码变更、数据敏感度、历史缺陷和复杂度生成测试矩阵。
- 支持组合覆盖、状态模型、角色/权限、设备/浏览器和环境矩阵。
- 验收：每个 Required 需求至少一个测试策略；P0/P1 100% 可执行映射。

### Batch 05：Unified Test DSL
- 定义测试用例、步骤、Oracle、数据、环境、证据和清理语义。
- 生成器与执行器只通过版本化 DSL 交互。
- 验收：Schema 校验、向后兼容和幂等序列化测试通过。

## M2 — 功能、API、数据与消息

### Batch 06：Functional Test Generation
- 正向、负向、边界、状态机、权限、幂等、并发和错误恢复用例。
- 使用 pairwise/约束组合控制组合爆炸。
- 验收：生成用例可编译、可执行、可追溯；无空断言。

### Batch 07：API & Contract Testing
- OpenAPI/GraphQL/Proto 契约、消费者契约、兼容性、错误码与鉴权测试。
- 验收：破坏性 Schema 变更和行为漂移可被检测。

### Batch 08：Database & Migration Testing
- DDL、事务、约束、索引、隔离级别、迁移升级/回滚、数据一致性测试。
- 验收：迁移可在生产规模抽样数据上验证；失败可回滚。

### Batch 09：Message & Workflow Testing
- 消息 Schema、顺序、重复、丢失、重试、死信、Saga/补偿、定时任务。
- 验收：至少一次交付下业务幂等性被验证。

## M3 — UI、视觉、可访问性与兼容性

### Batch 10：UI E2E
- 关键用户旅程、表单、路由、权限、上传下载、错误态、离线/弱网。
- 稳定 locator 策略和 DOM/网络/控制台证据。
- 验收：关键流程在支持浏览器矩阵中 100% 通过。

### Batch 11：Visual & Responsive
- 视觉基线、组件/页面截图、布局断点、字体溢出、主题与本地化。
- 验收：所有视觉差异有分类与审批，不允许无解释更新基线。

### Batch 12：Accessibility & Compatibility
- 键盘、焦点、语义、标签、对比度、屏幕阅读器可观察项；浏览器/设备兼容。
- 验收：关键可访问性违规为零；关键流程覆盖所有声明支持的终端。

## M4 — 性能、压力与容量

### Batch 13：Performance Baseline
- 场景模型、流量模型、SLO/预算、基线、采样和环境校准。
- 验收：同环境重复运行误差可解释；报告 p50/p95/p99、吞吐、错误率与资源。

### Batch 14：Load/Stress/Spike/Soak
- 负载、压力、突发、耐久、容量与扩展性测试。
- 自动定位拐点、饱和资源、泄漏与恢复时间。
- 验收：性能预算、最大稳定容量和降级行为有明确结论。

## M5 — 安全、韧性和高级测试

### Batch 15：Security & Abuse
- 身份、授权、输入、会话、速率限制、租户隔离、秘密泄露和滥用场景。
- 静态、依赖、动态与业务逻辑安全证据统一归档。
- 验收：Critical/High 为零；任何例外有所有者和到期日。

### Batch 16：Resilience/Chaos/Recovery
- 超时、断网、依赖失败、限流、时钟、磁盘、进程、节点和区域级故障。
- 验收：恢复时间、数据完整性和降级路径符合目标。

### Batch 27：Mutation/Property/Fuzz
- 变异测试检验测试强度；属性测试覆盖不变量；模糊测试探索输入空间。
- 验收：修复不得降低批准基线的变异得分；崩溃样本可最小化和重放。

## M6 — 数据、环境与分布式执行

### Batch 17：Test Data Management
- 合成、脱敏、种子、夹具、租户隔离、时间控制和清理。
- 验收：测试可重复；无生产敏感数据泄漏；并发执行互不污染。

### Batch 18：Environment Orchestration
- 临时环境、服务依赖、数据库、消息系统、浏览器网格、资源租约。
- 验收：环境构建失败可诊断；销毁幂等；泄漏资源可被回收。

### Batch 19：Distributed Execution
- 分片、并行、优先级、资源配额、队列、取消和背压。
- 验收：Worker 失败后分片可安全重放；同一测试不重复产生不可逆副作用。

## M7 — Oracle、证据与稳定性

### Batch 20：Oracle & Evidence
- 多源 Oracle、业务不变量、差分验证、日志/trace/metric/截图/数据库证据。
- 验收：每个测试结果都能定位到完整证据清单和重放命令。

### Batch 21：Flaky Test Control
- 波动性识别、重复策略、环境相关性、隔离与责任归属。
- 验收：重试不覆盖首次失败；确认 Flaky 会阻断 Required 门禁。

## M8 — 缺陷定位与安全修复

### Batch 22：Defect Triage & RCA
- 失败聚类、级联抑制、最小复现、调用链与变更关联、根因置信度。
- 验收：同根因失败聚为一个缺陷；每个缺陷有复现脚本。

### Batch 23：Repair Planning
- 生成候选修复、影响面、风险级别、回滚方案和验证计划。
- 验收：高风险补丁自动进入审批；无验证计划不得执行修复。

### Batch 24：Safe Code Auto-Fix
- 隔离工作树、最小 diff、编译与静态检查、失败用例重跑。
- 验收：禁止直接改主分支；失败补丁自动回滚；变更范围可审计。

### Batch 25：Test Self-Healing
- 仅修复 locator、测试数据、非语义等待和环境漂移；不得改变业务断言。
- 验收：修复前后需求映射、断言强度和视觉语义不下降。

### Batch 26：Impact & Full Regression
- 代码/依赖/数据流影响分析，先增量后全量回归。
- 验收：任何产品代码补丁必须通过全量 Required 套件才可认证。

## M9 — 质量门禁、报告与恢复

### Batch 28：Quality Gate & Certification
- 解释型门禁引擎、例外审批、发布证书和不可变输入/证据哈希。
- 验收：证书可独立校验；门禁规则变更有版本与审计。

### Batch 29：Reporting & Observability
- 管理摘要、工程细节、覆盖矩阵、缺陷、补丁、性能/UI 证据和趋势。
- 验收：报告中的每个数字可追溯到查询或证据对象。

### Batch 30：Checkpoint/Resume/Idempotency
- 持久化检查点、心跳、租约、重放、断线继续和异常恢复。
- 验收：客户端断线不终止服务端；编排服务重启后继续未完成任务。

### Batch 31：Runtime/Cost ETA
- 通过历史运行、测试图与资源模型预测系统 wall-clock ETA、token/算力/云资源成本。
- 验收：预测与实际偏差可记录、校准；人工等效时间单独呈现。

## M10 — 多语言与 CI/CD

### Batch 32：Multi-Language Adapter SDK
- Java/Kotlin/Python/C#/Go/Rust/C++/PHP/TS/JS/React/ObjC/Swift/Flutter 适配器接口。
- 验收：每个适配器有探测、生成、执行、覆盖率和诊断契约测试。

### Batch 33：CI/CD & PR Integration
- PR 增量门禁、夜间全量、发布认证、状态检查和证据链接。
- 验收：PR 只运行相关测试但不牺牲 Required 门禁；合并前结果不可伪造。

## M11 — 学习与治理

### Batch 34：Continuous Learning Knowledge Base
- 从缺陷、补丁、波动、性能和误报中沉淀规则；版本化且可回滚。
- 验收：新规则必须经离线回放和对照实验，不能直接污染生产策略。

### Batch 35：Governance/Approval/Audit
- RBAC/ABAC、代码所有者、风险审批、预算、审计导出和保留策略。
- 验收：高风险修复无法绕过审批；所有决策可解释和追责。

## 建议交付顺序

最小可信版本：Batch 00–10、17–24、26、28–30、33、35。  
生产增强版本：补齐 11–16、25、27、31–34。  
发布认证版本：所有 Batch 完成并通过 `workflows/release-certification.yaml`。



## M12 — 测试文件项目产出与交付

### Batch 36：Project Output Contract
- 建立 ProjectOutput、OutputArtifact、TestArtifactSet、OutputBundle 和 ArtifactLineage 领域模型。
- 支持 embedded/sidecar/both；按技术栈规划原生测试路径和 Bundle。
- 验收：非 plan-only Run 均有不可变产出计划；路径冲突、逃逸和未知布局会阻塞。

### Batch 37：Test Source Materialization
- 将 Test DSL 转为真实测试源、配置、Fixture、Mock、数据、基线和运行入口。
- 更新构建 Target，并执行格式化、语法、测试发现、构建和冒烟。
- 验收：每个 Required 测试有物化文件；P0/P1 Target 可构建；所有文件进入 Manifest。

### Batch 38：Project Output Bundle Publishing
- 生成 project-with-tests、tests-only、qa-evidence 和可选 repair-patches。
- 冻结清单、Secrets/路径检查、确定性归档、解压复验、签名和原子发布。
- 验收：三套标准 Bundle 可下载、哈希一致；失败 Run 仍有 partial/failed 产出。

### Batch 39：Output Versioning/Retention
- 实现 revision、stale/superseded、差异比较、legal hold、去重、引用计数和两阶段 GC。
- 验收：旧产出可恢复；Required stale 测试阻断认证；引用对象不被误删。

## v1.1.0 最小交付边界

最小可信版本必须包含 Batch 00–10、17–24、26、28–33、35–38。  
生产版本补齐 11–16、25、27、34、39。  
发布认证版本要求全部 Batch 完成，并通过 `workflows/release-certification.yaml` 与 `workflows/project-output-publishing.yaml`。

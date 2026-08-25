# Elmos Project Intelligence Studio — Tasks

共 **500** 条实施任务。机器可读版本：`tasks.yaml`。

状态建议：`todo → in_progress → blocked/review → done`。完成必须附测试、证据和 revision。

## BATCH-00-product-and-reference-architecture

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-00-T01` | `elmos-insight-orchestrator` | 读取 AGENTS.md、CLAUDE.md、skillpack.yaml 和当前仓库状态 | implementation | P0 |
| `ELMOS-PI-00-T02` | `elmos-insight-orchestrator` | 识别请求涉及的能力域，选择最少且足够的子技能 | implementation | P0 |
| `ELMOS-PI-00-T03` | `elmos-insight-orchestrator` | 建立可执行计划、依赖、风险、回滚点和完成定义 | implementation | P0 |
| `ELMOS-PI-00-T04` | `elmos-insight-orchestrator` | 按检查点实施；每个阶段产出代码、测试、文档和证据 | implementation | P0 |
| `ELMOS-PI-00-T05` | `elmos-insight-orchestrator` | 运行包级验证与目标仓库测试，修复失败 | implementation | P0 |
| `ELMOS-PI-00-T06` | `elmos-insight-orchestrator` | 生成完成报告，列出已完成、未完成、已知限制和下一批入口 | implementation | P0 |
| `ELMOS-PI-00-T07` | `elmos-insight-orchestrator` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-00-T08` | `elmos-insight-orchestrator` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-00-T09` | `elmos-insight-orchestrator` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-00-T10` | `elmos-insight-orchestrator` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-01-T01` | `elmos-product-scope` | 识别用户角色、核心任务和痛点 | implementation | P0 |
| `ELMOS-PI-01-T02` | `elmos-product-scope` | 将能力拆为 Read、Explain、Explore、Flow、Diagram、Document、Present、Impact | implementation | P0 |
| `ELMOS-PI-01-T03` | `elmos-product-scope` | 定义每项能力的输入、输出、异常、权限和数据保留 | implementation | P0 |
| `ELMOS-PI-01-T04` | `elmos-product-scope` | 按 P0-P3 排序并标注依赖 | implementation | P0 |
| `ELMOS-PI-01-T05` | `elmos-product-scope` | 为每个 Story 编写可自动验证的完成条件 | implementation | P0 |
| `ELMOS-PI-01-T06` | `elmos-product-scope` | 建立需求到技能、API、数据表和测试的追踪关系 | implementation | P0 |
| `ELMOS-PI-01-T07` | `elmos-product-scope` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-01-T08` | `elmos-product-scope` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-01-T09` | `elmos-product-scope` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-01-T10` | `elmos-product-scope` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-02-T01` | `elmos-reference-architecture` | 定义 Browser、Control Plane、Analysis Plane、Artifact Plane 和 Storage Plane | implementation | P0 |
| `ELMOS-PI-02-T02` | `elmos-reference-architecture` | 划分前端、项目 API、解析索引、图谱、AI 编排、渲染、导出和工作流服务 | implementation | P0 |
| `ELMOS-PI-02-T03` | `elmos-reference-architecture` | 定义 PostgreSQL、图数据库、对象存储、搜索、缓存的职责和替换接口 | implementation | P0 |
| `ELMOS-PI-02-T04` | `elmos-reference-architecture` | 定义 Temporal 工作流、事件总线和幂等键 | implementation | P0 |
| `ELMOS-PI-02-T05` | `elmos-reference-architecture` | 定义多租户、网络边界、Secrets Broker 和审计 | implementation | P0 |
| `ELMOS-PI-02-T06` | `elmos-reference-architecture` | 生成当前/目标架构图和 ADR | implementation | P0 |
| `ELMOS-PI-02-T07` | `elmos-reference-architecture` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-02-T08` | `elmos-reference-architecture` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-02-T09` | `elmos-reference-architecture` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-02-T10` | `elmos-reference-architecture` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## BATCH-01-ingestion-and-parsing

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-03-T01` | `elmos-repository-ingestion` | 校验来源、租户、权限和内容大小 | implementation | P0 |
| `ELMOS-PI-03-T02` | `elmos-repository-ingestion` | 解析 Git、子模块、LFS、Monorepo 和多仓库组合 | implementation | P0 |
| `ELMOS-PI-03-T03` | `elmos-repository-ingestion` | 冻结 commit SHA；上传包计算内容哈希 | implementation | P0 |
| `ELMOS-PI-03-T04` | `elmos-repository-ingestion` | 扫描文件类型、二进制、生成代码、Vendor 与敏感文件 | implementation | P0 |
| `ELMOS-PI-03-T05` | `elmos-repository-ingestion` | 写入对象存储并生成不可变 manifest | implementation | P0 |
| `ELMOS-PI-03-T06` | `elmos-repository-ingestion` | 发布 project.revision.ingested 事件 | implementation | P0 |
| `ELMOS-PI-03-T07` | `elmos-repository-ingestion` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-03-T08` | `elmos-repository-ingestion` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-03-T09` | `elmos-repository-ingestion` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-03-T10` | `elmos-repository-ingestion` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-04-T01` | `elmos-project-fingerprinting` | 统计语言、文件、LOC、生成代码和测试占比 | implementation | P0 |
| `ELMOS-PI-04-T02` | `elmos-project-fingerprinting` | 识别构建系统、包管理器、框架和版本 | implementation | P0 |
| `ELMOS-PI-04-T03` | `elmos-project-fingerprinting` | 识别服务入口、UI 入口、CLI、Cron、Consumer 和 Webhook | implementation | P0 |
| `ELMOS-PI-04-T04` | `elmos-project-fingerprinting` | 识别数据库、缓存、消息、云资源和部署描述 | implementation | P0 |
| `ELMOS-PI-04-T05` | `elmos-project-fingerprinting` | 识别反射、动态加载、宏、代码生成和 FFI 风险 | implementation | P0 |
| `ELMOS-PI-04-T06` | `elmos-project-fingerprinting` | 输出解析器与运行时证据采集建议 | implementation | P0 |
| `ELMOS-PI-04-T07` | `elmos-project-fingerprinting` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-04-T08` | `elmos-project-fingerprinting` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-04-T09` | `elmos-project-fingerprinting` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-04-T10` | `elmos-project-fingerprinting` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-05-T01` | `elmos-multilanguage-parsing` | 为每种语言选择 Tree-sitter、编译器前端或 LSP 适配器 | implementation | P0 |
| `ELMOS-PI-05-T02` | `elmos-multilanguage-parsing` | 解析文件并保留位置、注释、语法节点和错误节点 | implementation | P0 |
| `ELMOS-PI-05-T03` | `elmos-multilanguage-parsing` | 解析包、模块、类型、函数、变量、注解、路由和配置绑定 | implementation | P0 |
| `ELMOS-PI-05-T04` | `elmos-multilanguage-parsing` | 标准化跨语言 Symbol ID 和 Type ID | implementation | P0 |
| `ELMOS-PI-05-T05` | `elmos-multilanguage-parsing` | 关联生成代码、源映射、宏展开与 partial class | implementation | P0 |
| `ELMOS-PI-05-T06` | `elmos-multilanguage-parsing` | 按文件内容哈希增量更新 IR | implementation | P0 |
| `ELMOS-PI-05-T07` | `elmos-multilanguage-parsing` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-05-T08` | `elmos-multilanguage-parsing` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-05-T09` | `elmos-multilanguage-parsing` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-05-T10` | `elmos-multilanguage-parsing` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## BATCH-02-graphs-and-evidence

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-06-T01` | `elmos-symbol-code-graph` | 创建文件、模块、包、类型、函数和字段节点 | implementation | P0 |
| `ELMOS-PI-06-T02` | `elmos-symbol-code-graph` | 解析定义/引用、继承/实现、调用者/被调用者 | implementation | P0 |
| `ELMOS-PI-06-T03` | `elmos-symbol-code-graph` | 识别依赖注入、反射注册、路由绑定和 ORM 映射 | implementation | P0 |
| `ELMOS-PI-06-T04` | `elmos-symbol-code-graph` | 构建前端页面到 API、API 到服务、服务到数据库的跨层边 | implementation | P0 |
| `ELMOS-PI-06-T05` | `elmos-symbol-code-graph` | 为边保存解析策略、证据和置信度 | implementation | P0 |
| `ELMOS-PI-06-T06` | `elmos-symbol-code-graph` | 计算 SCC、中心性、扇入扇出和循环依赖 | implementation | P0 |
| `ELMOS-PI-06-T07` | `elmos-symbol-code-graph` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-06-T08` | `elmos-symbol-code-graph` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-06-T09` | `elmos-symbol-code-graph` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-06-T10` | `elmos-symbol-code-graph` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-07-T01` | `elmos-project-intelligence-graph` | 定义统一节点和关系 taxonomy | implementation | P0 |
| `ELMOS-PI-07-T02` | `elmos-project-intelligence-graph` | 将代码节点聚合为模块、组件、服务、业务能力和部署单元 | implementation | P0 |
| `ELMOS-PI-07-T03` | `elmos-project-intelligence-graph` | 连接 API、事件、数据资产、测试、配置和安全边界 | implementation | P0 |
| `ELMOS-PI-07-T04` | `elmos-project-intelligence-graph` | 保存每个聚合结论的证据集合与置信度 | implementation | P0 |
| `ELMOS-PI-07-T05` | `elmos-project-intelligence-graph` | 提供 C4、流程、数据、功能、部署等投影视图 | implementation | P0 |
| `ELMOS-PI-07-T06` | `elmos-project-intelligence-graph` | 版本化图谱并支持 revision diff | implementation | P0 |
| `ELMOS-PI-07-T07` | `elmos-project-intelligence-graph` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-07-T08` | `elmos-project-intelligence-graph` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-07-T09` | `elmos-project-intelligence-graph` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-07-T10` | `elmos-project-intelligence-graph` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-08-T01` | `elmos-evidence-provenance` | 定义 Evidence、Claim、Inference、Recommendation 数据模型 | implementation | P0 |
| `ELMOS-PI-08-T02` | `elmos-evidence-provenance` | 为文件行、AST、配置键、Trace span、测试结果生成稳定引用 | implementation | P0 |
| `ELMOS-PI-08-T03` | `elmos-evidence-provenance` | 按规则计算证据强度、冲突和新鲜度 | implementation | P0 |
| `ELMOS-PI-08-T04` | `elmos-evidence-provenance` | 将 claim 绑定到 artifact block、diagram node 和 slide element | implementation | P0 |
| `ELMOS-PI-08-T05` | `elmos-evidence-provenance` | 发现冲突时降级置信度并生成待确认任务 | implementation | P0 |
| `ELMOS-PI-08-T06` | `elmos-evidence-provenance` | 提供点击回源和批量证据导出 | implementation | P0 |
| `ELMOS-PI-08-T07` | `elmos-evidence-provenance` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-08-T08` | `elmos-evidence-provenance` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-08-T09` | `elmos-evidence-provenance` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-08-T10` | `elmos-evidence-provenance` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## BATCH-03-code-reader-and-explanation

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-09-T01` | `elmos-online-code-reader` | 建立项目/仓库/分支/Commit 选择器和虚拟化文件树 | implementation | P0 |
| `ELMOS-PI-09-T02` | `elmos-online-code-reader` | 接入 Monaco，支持高亮、折叠、大纲、面包屑、多标签和分屏 | implementation | P0 |
| `ELMOS-PI-09-T03` | `elmos-online-code-reader` | 实现原始/目标、Commit/Commit、自动/人工修改 Diff | implementation | P0 |
| `ELMOS-PI-09-T04` | `elmos-online-code-reader` | 实现深链：文件、行、Symbol、Claim、Diagram Node | implementation | P0 |
| `ELMOS-PI-09-T05` | `elmos-online-code-reader` | 加入书签、私人笔记、团队评论、最近阅读和收藏 | implementation | P0 |
| `ELMOS-PI-09-T06` | `elmos-online-code-reader` | 接入权限、脱敏、审计和大文件降级 | implementation | P0 |
| `ELMOS-PI-09-T07` | `elmos-online-code-reader` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-09-T08` | `elmos-online-code-reader` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-09-T09` | `elmos-online-code-reader` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-09-T10` | `elmos-online-code-reader` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-10-T01` | `elmos-semantic-navigation` | 实现 Definition、References、Implementations、Type Hierarchy、Call Hierarchy 查询 | implementation | P0 |
| `ELMOS-PI-10-T02` | `elmos-semantic-navigation` | 实现页面→API→Service→Repository→Table 与反向路径 | implementation | P0 |
| `ELMOS-PI-10-T03` | `elmos-semantic-navigation` | 实现 Topic→Producer/Consumer、Config→Reader、Test→Target 的导航 | implementation | P0 |
| `ELMOS-PI-10-T04` | `elmos-semantic-navigation` | 为动态候选显示置信度和多个可能目标 | implementation | P0 |
| `ELMOS-PI-10-T05` | `elmos-semantic-navigation` | 支持路径限制、深度、边类型和 revision 过滤 | implementation | P0 |
| `ELMOS-PI-10-T06` | `elmos-semantic-navigation` | 记录导航性能与失败原因 | implementation | P0 |
| `ELMOS-PI-10-T07` | `elmos-semantic-navigation` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-10-T08` | `elmos-semantic-navigation` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-10-T09` | `elmos-semantic-navigation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-10-T10` | `elmos-semantic-navigation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-11-T01` | `elmos-code-explanation` | 解析用户范围和受众：管理、产品、架构、开发、测试、运维、安全 | implementation | P1 |
| `ELMOS-PI-11-T02` | `elmos-code-explanation` | 检索最小充分上下文，不整仓库塞入模型 | implementation | P1 |
| `ELMOS-PI-11-T03` | `elmos-code-explanation` | 先生成事实清单，再生成解释、风险和建议 | implementation | P1 |
| `ELMOS-PI-11-T04` | `elmos-code-explanation` | 将每个关键 claim 绑定证据并标识可信度 | implementation | P1 |
| `ELMOS-PI-11-T05` | `elmos-code-explanation` | 输出一段式、逐步、教学、审查等模式 | implementation | P1 |
| `ELMOS-PI-11-T06` | `elmos-code-explanation` | 缓存相同 revision/scope/prompt version 结果 | implementation | P1 |
| `ELMOS-PI-11-T07` | `elmos-code-explanation` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-11-T08` | `elmos-code-explanation` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-11-T09` | `elmos-code-explanation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-11-T10` | `elmos-code-explanation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-12-T01` | `elmos-onboarding-learning-path` | 识别项目使命、边界、核心业务能力和技术栈 | implementation | P1 |
| `ELMOS-PI-12-T02` | `elmos-onboarding-learning-path` | 为开发、测试、运维、产品、架构、安全设计不同路径 | implementation | P1 |
| `ELMOS-PI-12-T03` | `elmos-onboarding-learning-path` | 选择最具代表性的文件、调用链、流程和数据模型 | implementation | P1 |
| `ELMOS-PI-12-T04` | `elmos-onboarding-learning-path` | 生成 30 分钟、半天、3 天、2 周不同学习计划 | implementation | P1 |
| `ELMOS-PI-12-T05` | `elmos-onboarding-learning-path` | 为每阶段提供可验证任务和相关代码深链 | implementation | P1 |
| `ELMOS-PI-12-T06` | `elmos-onboarding-learning-path` | 根据用户反馈和项目变更更新路径 | implementation | P1 |
| `ELMOS-PI-12-T07` | `elmos-onboarding-learning-path` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-12-T08` | `elmos-onboarding-learning-path` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-12-T09` | `elmos-onboarding-learning-path` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-12-T10` | `elmos-onboarding-learning-path` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## BATCH-04-architecture-flow-data

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-13-T01` | `elmos-architecture-discovery` | 识别系统边界、外部 Actor 和外部系统 | implementation | P1 |
| `ELMOS-PI-13-T02` | `elmos-architecture-discovery` | 聚合服务、容器、组件、模块和层 | implementation | P1 |
| `ELMOS-PI-13-T03` | `elmos-architecture-discovery` | 识别同步调用、异步事件、共享数据和部署关系 | implementation | P1 |
| `ELMOS-PI-13-T04` | `elmos-architecture-discovery` | 生成业务、应用、技术、数据、部署、安全视图 | implementation | P1 |
| `ELMOS-PI-13-T05` | `elmos-architecture-discovery` | 对照人工设计和运行证据，记录冲突 | implementation | P1 |
| `ELMOS-PI-13-T06` | `elmos-architecture-discovery` | 按受众生成 L0-L5 架构讲解 | implementation | P1 |
| `ELMOS-PI-13-T07` | `elmos-architecture-discovery` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-13-T08` | `elmos-architecture-discovery` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-13-T09` | `elmos-architecture-discovery` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-13-T10` | `elmos-architecture-discovery` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-14-T01` | `elmos-business-capability-map` | 识别 Actor、业务域、业务能力、功能模块和子功能 | implementation | P1 |
| `ELMOS-PI-14-T02` | `elmos-business-capability-map` | 将页面、API、事件、代码、数据表、权限和测试挂接到功能节点 | implementation | P1 |
| `ELMOS-PI-14-T03` | `elmos-business-capability-map` | 使用命名、调用链和文档证据生成候选功能 | implementation | P1 |
| `ELMOS-PI-14-T04` | `elmos-business-capability-map` | 让用户确认、合并、拆分、重命名和排序 | implementation | P1 |
| `ELMOS-PI-14-T05` | `elmos-business-capability-map` | 计算实现覆盖、测试覆盖、风险和转换状态 | implementation | P1 |
| `ELMOS-PI-14-T06` | `elmos-business-capability-map` | 生成 Markmap、树形图、矩阵和可编辑 JSON | implementation | P1 |
| `ELMOS-PI-14-T07` | `elmos-business-capability-map` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-14-T08` | `elmos-business-capability-map` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-14-T09` | `elmos-business-capability-map` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-14-T10` | `elmos-business-capability-map` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-15-T01` | `elmos-flow-discovery` | 枚举 HTTP、GraphQL、gRPC、UI、Consumer、Cron、CLI、Webhook、Agent Task 等入口 | implementation | P1 |
| `ELMOS-PI-15-T02` | `elmos-flow-discovery` | 按控制流和调用图扩展步骤，识别条件、循环、并行和异步边 | implementation | P1 |
| `ELMOS-PI-15-T03` | `elmos-flow-discovery` | 关联状态变化、数据库写入、事件、外部调用和权限检查 | implementation | P1 |
| `ELMOS-PI-15-T04` | `elmos-flow-discovery` | 发现超时、重试、幂等、死信和补偿 | implementation | P1 |
| `ELMOS-PI-15-T05` | `elmos-flow-discovery` | 用 Trace/测试确认高价值路径 | implementation | P1 |
| `ELMOS-PI-15-T06` | `elmos-flow-discovery` | 生成 BPMN、泳道、时序、状态机和普通流程视图 | implementation | P1 |
| `ELMOS-PI-15-T07` | `elmos-flow-discovery` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-15-T08` | `elmos-flow-discovery` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-15-T09` | `elmos-flow-discovery` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-15-T10` | `elmos-flow-discovery` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-16-T01` | `elmos-data-architecture-lineage` | 抽取数据库、Schema、表、字段、索引、约束和实体 | implementation | P1 |
| `ELMOS-PI-16-T02` | `elmos-data-architecture-lineage` | 解析 ORM、手写 SQL、Repository 和迁移历史 | implementation | P1 |
| `ELMOS-PI-16-T03` | `elmos-data-architecture-lineage` | 识别 API/事件字段到内部模型和持久化字段映射 | implementation | P1 |
| `ELMOS-PI-16-T04` | `elmos-data-architecture-lineage` | 识别缓存、搜索索引、对象存储和 ETL 流 | implementation | P1 |
| `ELMOS-PI-16-T05` | `elmos-data-architecture-lineage` | 标注敏感等级、保留期限、加密和跨境边界 | implementation | P1 |
| `ELMOS-PI-16-T06` | `elmos-data-architecture-lineage` | 生成 ER、DFD、血缘、生命周期、CRUD 与数据质量视图 | implementation | P1 |
| `ELMOS-PI-16-T07` | `elmos-data-architecture-lineage` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-16-T08` | `elmos-data-architecture-lineage` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-16-T09` | `elmos-data-architecture-lineage` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-16-T10` | `elmos-data-architecture-lineage` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-17-T01` | `elmos-api-event-topology` | 抽取端点、方法、请求响应、认证、错误和版本 | implementation | P1 |
| `ELMOS-PI-17-T02` | `elmos-api-event-topology` | 抽取 Topic/Queue、事件 Schema、生产者、消费者、重试和死信 | implementation | P1 |
| `ELMOS-PI-17-T03` | `elmos-api-event-topology` | 识别 HTTP/RPC 客户端、SDK、Webhook 和第三方服务 | implementation | P1 |
| `ELMOS-PI-17-T04` | `elmos-api-event-topology` | 关联接口到功能、服务、数据和测试 | implementation | P1 |
| `ELMOS-PI-17-T05` | `elmos-api-event-topology` | 检测未文档接口、Schema 漂移、废弃版本和消费者风险 | implementation | P1 |
| `ELMOS-PI-17-T06` | `elmos-api-event-topology` | 生成 API 拓扑、事件拓扑、时序和版本兼容图 | implementation | P1 |
| `ELMOS-PI-17-T07` | `elmos-api-event-topology` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-17-T08` | `elmos-api-event-topology` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-17-T09` | `elmos-api-event-topology` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-17-T10` | `elmos-api-event-topology` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-18-T01` | `elmos-runtime-trace-fusion` | 接收或导入 OTLP Trace/Span 与环境标签 | implementation | P1 |
| `ELMOS-PI-18-T02` | `elmos-runtime-trace-fusion` | 规范化 service/resource/code attributes | implementation | P1 |
| `ELMOS-PI-18-T03` | `elmos-runtime-trace-fusion` | 将 span 关联到 API、symbol、database、message 和 external system | implementation | P1 |
| `ELMOS-PI-18-T04` | `elmos-runtime-trace-fusion` | 聚合调用频率、延迟、错误和关键路径 | implementation | P1 |
| `ELMOS-PI-18-T05` | `elmos-runtime-trace-fusion` | 比较静态候选边与运行观测边 | implementation | P1 |
| `ELMOS-PI-18-T06` | `elmos-runtime-trace-fusion` | 发布 runtime evidence 并触发受影响 artifact 更新 | implementation | P1 |
| `ELMOS-PI-18-T07` | `elmos-runtime-trace-fusion` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-18-T08` | `elmos-runtime-trace-fusion` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-18-T09` | `elmos-runtime-trace-fusion` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-18-T10` | `elmos-runtime-trace-fusion` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## BATCH-05-diagram-platform

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-19-T01` | `elmos-diagram-spec-engine` | 定义 diagram metadata、nodes、edges、groups、ports、views 和 evidence refs | implementation | P1 |
| `ELMOS-PI-19-T02` | `elmos-diagram-spec-engine` | 为 C4、BPMN、Sequence、State、ER、DFD、Mindmap、Deployment 等定义 profile | implementation | P1 |
| `ELMOS-PI-19-T03` | `elmos-diagram-spec-engine` | 定义折叠、聚合、分页、布局 hint 和视觉语义 | implementation | P1 |
| `ELMOS-PI-19-T04` | `elmos-diagram-spec-engine` | 定义人工锁定、注释和版本 diff | implementation | P1 |
| `ELMOS-PI-19-T05` | `elmos-diagram-spec-engine` | 实现 JSON Schema 和语义校验器 | implementation | P1 |
| `ELMOS-PI-19-T06` | `elmos-diagram-spec-engine` | 提供从 Intelligence Graph 到 Diagram Spec 的投影器 | implementation | P1 |
| `ELMOS-PI-19-T07` | `elmos-diagram-spec-engine` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-19-T08` | `elmos-diagram-spec-engine` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-19-T09` | `elmos-diagram-spec-engine` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-19-T10` | `elmos-diagram-spec-engine` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-20-T01` | `elmos-diagram-rendering` | 选择适合图类型的渲染器并生成中间 DSL | implementation | P1 |
| `ELMOS-PI-20-T02` | `elmos-diagram-rendering` | 使用 ELK/Dagre/Graphviz 等执行自动布局 | implementation | P1 |
| `ELMOS-PI-20-T03` | `elmos-diagram-rendering` | 对大图进行聚合、分层、分页和 overview+detail | implementation | P1 |
| `ELMOS-PI-20-T04` | `elmos-diagram-rendering` | 嵌入 element ID、evidence link 和 accessibility metadata | implementation | P1 |
| `ELMOS-PI-20-T05` | `elmos-diagram-rendering` | 沙箱化渲染进程并限制 CPU/内存/时间 | implementation | P1 |
| `ELMOS-PI-20-T06` | `elmos-diagram-rendering` | 缓存 spec hash + renderer version + theme 的结果 | implementation | P1 |
| `ELMOS-PI-20-T07` | `elmos-diagram-rendering` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-20-T08` | `elmos-diagram-rendering` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-20-T09` | `elmos-diagram-rendering` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-20-T10` | `elmos-diagram-rendering` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-21-T01` | `elmos-diagram-editor` | 实现缩放、平移、搜索、折叠、下钻和 mini-map | implementation | P1 |
| `ELMOS-PI-21-T02` | `elmos-diagram-editor` | 支持节点重命名、说明、分组、移动、隐藏和手工连线 | implementation | P1 |
| `ELMOS-PI-21-T03` | `elmos-diagram-editor` | 区分事实字段、展示字段和建议字段的编辑权限 | implementation | P1 |
| `ELMOS-PI-21-T04` | `elmos-diagram-editor` | 保存人工 override 和锁定范围 | implementation | P1 |
| `ELMOS-PI-21-T05` | `elmos-diagram-editor` | 对新自动 Spec 进行三方合并并显示冲突 | implementation | P1 |
| `ELMOS-PI-21-T06` | `elmos-diagram-editor` | 支持评论、审批、撤销/重做和版本回退 | implementation | P1 |
| `ELMOS-PI-21-T07` | `elmos-diagram-editor` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-21-T08` | `elmos-diagram-editor` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-21-T09` | `elmos-diagram-editor` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-21-T10` | `elmos-diagram-editor` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-32-T01` | `elmos-artifact-versioning-human-lock` | 定义 Artifact、Block、Element、Version、Lock、Override 和 Review 模型 | implementation | P1 |
| `ELMOS-PI-32-T02` | `elmos-artifact-versioning-human-lock` | 为段落、图节点、PPT 页面和表格分配稳定 ID | implementation | P1 |
| `ELMOS-PI-32-T03` | `elmos-artifact-versioning-human-lock` | 保存 base-generated、human-patch 和 next-generated 三方数据 | implementation | P1 |
| `ELMOS-PI-32-T04` | `elmos-artifact-versioning-human-lock` | 执行语义合并并分类自动可合并/冲突/失效 | implementation | P1 |
| `ELMOS-PI-32-T05` | `elmos-artifact-versioning-human-lock` | 支持 Draft、Reviewed、Approved、Certified 生命周期 | implementation | P1 |
| `ELMOS-PI-32-T06` | `elmos-artifact-versioning-human-lock` | 提供回滚、比较、审计和保留策略 | implementation | P1 |
| `ELMOS-PI-32-T07` | `elmos-artifact-versioning-human-lock` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-32-T08` | `elmos-artifact-versioning-human-lock` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-32-T09` | `elmos-artifact-versioning-human-lock` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-32-T10` | `elmos-artifact-versioning-human-lock` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## BATCH-06-documents-presentations-reports

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-22-T01` | `elmos-architecture-documentation` | 选择文档类型、受众、深度和模板 | implementation | P1 |
| `ELMOS-PI-22-T02` | `elmos-architecture-documentation` | 生成事实大纲并验证覆盖与证据 | implementation | P1 |
| `ELMOS-PI-22-T03` | `elmos-architecture-documentation` | 生成正文、图表引用、表格、风险和未知项 | implementation | P1 |
| `ELMOS-PI-22-T04` | `elmos-architecture-documentation` | 为关键 claim 建立证据链接 | implementation | P1 |
| `ELMOS-PI-22-T05` | `elmos-architecture-documentation` | 与已有文档执行段落级三方合并 | implementation | P1 |
| `ELMOS-PI-22-T06` | `elmos-architecture-documentation` | 导出格式并生成可访问性、链接和一致性检查 | implementation | P1 |
| `ELMOS-PI-22-T07` | `elmos-architecture-documentation` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-22-T08` | `elmos-architecture-documentation` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-22-T09` | `elmos-architecture-documentation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-22-T10` | `elmos-architecture-documentation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-23-T01` | `elmos-presentation-generation` | 选择演示类型并建立答案优先的故事线 | implementation | P1 |
| `ELMOS-PI-23-T02` | `elmos-presentation-generation` | 为每页定义目的、主结论、证据、图表和备注 | implementation | P1 |
| `ELMOS-PI-23-T03` | `elmos-presentation-generation` | 生成或复用架构图、流程图和指标图 | implementation | P1 |
| `ELMOS-PI-23-T04` | `elmos-presentation-generation` | 使用模板引擎创建可编辑文本、形状、表格和图表 | implementation | P1 |
| `ELMOS-PI-23-T05` | `elmos-presentation-generation` | 检查溢出、可读性、引用、品牌和敏感信息 | implementation | P1 |
| `ELMOS-PI-23-T06` | `elmos-presentation-generation` | 按 slide stable ID 支持增量更新和人工锁定 | implementation | P1 |
| `ELMOS-PI-23-T07` | `elmos-presentation-generation` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-23-T08` | `elmos-presentation-generation` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-23-T09` | `elmos-presentation-generation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-23-T10` | `elmos-presentation-generation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-24-T01` | `elmos-project-report-bundle` | 冻结项目 revision 和所有引用 artifact version | implementation | P1 |
| `ELMOS-PI-24-T02` | `elmos-project-report-bundle` | 根据报告类型选取章节、图表、PPT 和原始证明 | implementation | P1 |
| `ELMOS-PI-24-T03` | `elmos-project-report-bundle` | 检查 claim/evidence 完整性和 stale 状态 | implementation | P1 |
| `ELMOS-PI-24-T04` | `elmos-project-report-bundle` | 应用脱敏、水印、受众权限和保留策略 | implementation | P1 |
| `ELMOS-PI-24-T05` | `elmos-project-report-bundle` | 生成目录、交叉链接、manifest、哈希和可选签名 | implementation | P1 |
| `ELMOS-PI-24-T06` | `elmos-project-report-bundle` | 执行离线打开与完整性验证 | implementation | P1 |
| `ELMOS-PI-24-T07` | `elmos-project-report-bundle` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-24-T08` | `elmos-project-report-bundle` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-24-T09` | `elmos-project-report-bundle` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-24-T10` | `elmos-project-report-bundle` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## BATCH-07-search-impact-governance-analysis

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-25-T01` | `elmos-project-search-qa` | 分类问题为导航、解释、架构、流程、数据、影响、风险或比较 | implementation | P2 |
| `ELMOS-PI-25-T02` | `elmos-project-search-qa` | 执行 lexical、symbol、structural、graph 和 vector 混合检索 | implementation | P2 |
| `ELMOS-PI-25-T03` | `elmos-project-search-qa` | 重排并验证结果的新鲜度、revision 和权限 | implementation | P2 |
| `ELMOS-PI-25-T04` | `elmos-project-search-qa` | 先构建证据表，再生成答案 | implementation | P2 |
| `ELMOS-PI-25-T05` | `elmos-project-search-qa` | 返回直接答案、证据、置信度、未确认项和相关视图 | implementation | P2 |
| `ELMOS-PI-25-T06` | `elmos-project-search-qa` | 记录匿名化评测信号和用户纠错 | implementation | P2 |
| `ELMOS-PI-25-T07` | `elmos-project-search-qa` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-25-T08` | `elmos-project-search-qa` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-25-T09` | `elmos-project-search-qa` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-25-T10` | `elmos-project-search-qa` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-26-T01` | `elmos-impact-analysis` | 解析变更 symbol、契约、Schema、配置和部署资源 | implementation | P2 |
| `ELMOS-PI-26-T02` | `elmos-impact-analysis` | 沿调用、数据、事件、部署和功能关系传播影响 | implementation | P2 |
| `ELMOS-PI-26-T03` | `elmos-impact-analysis` | 应用深度、边类型、置信度和运行热度权重 | implementation | P2 |
| `ELMOS-PI-26-T04` | `elmos-impact-analysis` | 识别 breaking change、数据迁移和安全边界变化 | implementation | P2 |
| `ELMOS-PI-26-T05` | `elmos-impact-analysis` | 选择相关测试、文档、图表和 PPT 页面 | implementation | P2 |
| `ELMOS-PI-26-T06` | `elmos-impact-analysis` | 输出确定、可能、未知影响及理由 | implementation | P2 |
| `ELMOS-PI-26-T07` | `elmos-impact-analysis` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-26-T08` | `elmos-impact-analysis` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-26-T09` | `elmos-impact-analysis` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-26-T10` | `elmos-impact-analysis` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-27-T01` | `elmos-architecture-rules` | 定义 Rule DSL：scope、selector、condition、severity、evidence、exceptions | implementation | P2 |
| `ELMOS-PI-27-T02` | `elmos-architecture-rules` | 实现内建规则与项目自定义规则 | implementation | P2 |
| `ELMOS-PI-27-T03` | `elmos-architecture-rules` | 在全量和增量图谱上执行规则 | implementation | P2 |
| `ELMOS-PI-27-T04` | `elmos-architecture-rules` | 为 violation 生成最短证据路径和修复建议 | implementation | P2 |
| `ELMOS-PI-27-T05` | `elmos-architecture-rules` | 支持 waiver、到期时间、owner 和审批 | implementation | P2 |
| `ELMOS-PI-27-T06` | `elmos-architecture-rules` | 集成 PR check、dashboard 和架构文档 | implementation | P2 |
| `ELMOS-PI-27-T07` | `elmos-architecture-rules` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-27-T08` | `elmos-architecture-rules` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-27-T09` | `elmos-architecture-rules` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-27-T10` | `elmos-architecture-rules` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-28-T01` | `elmos-architecture-drift` | 规范化设计、静态和运行模型到统一语义 | implementation | P2 |
| `ELMOS-PI-28-T02` | `elmos-architecture-drift` | 比较节点、关系、属性、所有权和安全边界 | implementation | P2 |
| `ELMOS-PI-28-T03` | `elmos-architecture-drift` | 分类 expected change、undocumented change、violation、observation gap | implementation | P2 |
| `ELMOS-PI-28-T04` | `elmos-architecture-drift` | 计算影响和严重度 | implementation | P2 |
| `ELMOS-PI-28-T05` | `elmos-architecture-drift` | 生成图表 diff、证据和建议动作 | implementation | P2 |
| `ELMOS-PI-28-T06` | `elmos-architecture-drift` | 支持确认、接受为新设计、拒绝或创建修复任务 | implementation | P2 |
| `ELMOS-PI-28-T07` | `elmos-architecture-drift` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-28-T08` | `elmos-architecture-drift` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-28-T09` | `elmos-architecture-drift` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-28-T10` | `elmos-architecture-drift` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-29-T01` | `elmos-risk-technical-debt` | 计算复杂度、重复、循环、扇入扇出、变更频率和 ownership | implementation | P2 |
| `ELMOS-PI-29-T02` | `elmos-risk-technical-debt` | 融合测试覆盖、故障、延迟、漏洞、过期依赖和业务关键度 | implementation | P2 |
| `ELMOS-PI-29-T03` | `elmos-risk-technical-debt` | 生成文件/模块/服务级风险评分并解释因子 | implementation | P2 |
| `ELMOS-PI-29-T04` | `elmos-risk-technical-debt` | 识别 God module、shotgun surgery、orphan code、unstable dependency | implementation | P2 |
| `ELMOS-PI-29-T05` | `elmos-risk-technical-debt` | 形成修复候选、成本区间和依赖顺序 | implementation | P2 |
| `ELMOS-PI-29-T06` | `elmos-risk-technical-debt` | 生成热力图和趋势 | implementation | P2 |
| `ELMOS-PI-29-T07` | `elmos-risk-technical-debt` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-29-T08` | `elmos-risk-technical-debt` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-29-T09` | `elmos-risk-technical-debt` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-29-T10` | `elmos-risk-technical-debt` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-30-T01` | `elmos-security-threat-model` | 识别资产、Actor、入口、信任边界和数据分类 | implementation | P2 |
| `ELMOS-PI-30-T02` | `elmos-security-threat-model` | 执行 SAST/SCA/secret/IaC/API auth 检查 | implementation | P2 |
| `ELMOS-PI-30-T03` | `elmos-security-threat-model` | 基于 STRIDE/项目规则生成威胁候选 | implementation | P2 |
| `ELMOS-PI-30-T04` | `elmos-security-threat-model` | 构建攻击路径并结合可达性和运行证据排序 | implementation | P2 |
| `ELMOS-PI-30-T05` | `elmos-security-threat-model` | 关联漏洞到功能、代码、数据、部署和测试 | implementation | P2 |
| `ELMOS-PI-30-T06` | `elmos-security-threat-model` | 生成修复、验证和残余风险记录 | implementation | P2 |
| `ELMOS-PI-30-T07` | `elmos-security-threat-model` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-30-T08` | `elmos-security-threat-model` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-30-T09` | `elmos-security-threat-model` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-30-T10` | `elmos-security-threat-model` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## BATCH-08-cache-versioning-git

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-31-T01` | `elmos-incremental-analysis-cache` | 为 ingest、parse、graph、flow、artifact、model call 定义确定性 cache key | implementation | P2 |
| `ELMOS-PI-31-T02` | `elmos-incremental-analysis-cache` | 建立文件→symbol→graph view→claim→artifact block 的依赖索引 | implementation | P2 |
| `ELMOS-PI-31-T03` | `elmos-incremental-analysis-cache` | 根据 Git diff、配置、规则、模型和模板变化计算失效范围 | implementation | P2 |
| `ELMOS-PI-31-T04` | `elmos-incremental-analysis-cache` | 每个长阶段写原子检查点和已完成副作用 | implementation | P2 |
| `ELMOS-PI-31-T05` | `elmos-incremental-analysis-cache` | 实现暂停、恢复、重试、取消和租约接管 | implementation | P2 |
| `ELMOS-PI-31-T06` | `elmos-incremental-analysis-cache` | 记录命中率、节省 wall-clock、Token 和存储成本 | implementation | P2 |
| `ELMOS-PI-31-T07` | `elmos-incremental-analysis-cache` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-31-T08` | `elmos-incremental-analysis-cache` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-31-T09` | `elmos-incremental-analysis-cache` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-31-T10` | `elmos-incremental-analysis-cache` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-33-T01` | `elmos-git-pr-automation` | 确认目标仓库、base revision、写权限和分支策略 | implementation | P2 |
| `ELMOS-PI-33-T02` | `elmos-git-pr-automation` | 创建唯一工作树/分支并应用最小变更 | implementation | P2 |
| `ELMOS-PI-33-T03` | `elmos-git-pr-automation` | 运行格式、链接、Schema、测试和敏感信息检查 | implementation | P2 |
| `ELMOS-PI-33-T04` | `elmos-git-pr-automation` | 生成结构化 commit 与 PR 描述，附影响和证据 | implementation | P2 |
| `ELMOS-PI-33-T05` | `elmos-git-pr-automation` | 设置 reviewer、labels 和 required checks | implementation | P2 |
| `ELMOS-PI-33-T06` | `elmos-git-pr-automation` | 处理重复调用、base 更新、冲突和关闭回滚 | implementation | P2 |
| `ELMOS-PI-33-T07` | `elmos-git-pr-automation` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-33-T08` | `elmos-git-pr-automation` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-33-T09` | `elmos-git-pr-automation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-33-T10` | `elmos-git-pr-automation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## BATCH-09-collaboration-and-connectors

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-34-T01` | `elmos-collaboration-governance` | 定义管理员、架构师、开发、测试、运维、安全、产品、访客、客户、审计等角色 | implementation | P2 |
| `ELMOS-PI-34-T02` | `elmos-collaboration-governance` | 细化 project/repo/revision/file/artifact/claim/export/model 权限 | implementation | P2 |
| `ELMOS-PI-34-T03` | `elmos-collaboration-governance` | 实现评论、@、任务、订阅、审批和通知 | implementation | P2 |
| `ELMOS-PI-34-T04` | `elmos-collaboration-governance` | 实现带有效期、水印、范围和撤销的分享 | implementation | P2 |
| `ELMOS-PI-34-T05` | `elmos-collaboration-governance` | 为读取、搜索、生成、导出、修改和认证记录审计 | implementation | P2 |
| `ELMOS-PI-34-T06` | `elmos-collaboration-governance` | 接入 SSO、SCIM、MFA 与组织策略 | implementation | P2 |
| `ELMOS-PI-34-T07` | `elmos-collaboration-governance` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-34-T08` | `elmos-collaboration-governance` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-34-T09` | `elmos-collaboration-governance` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-34-T10` | `elmos-collaboration-governance` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-35-T01` | `elmos-integrations-mcp` | 定义 Repository、Issue、Docs、CI、Trace、Artifact Registry 等 Port | implementation | P2 |
| `ELMOS-PI-35-T02` | `elmos-integrations-mcp` | 为供应商实现 Adapter 和能力发现 | implementation | P2 |
| `ELMOS-PI-35-T03` | `elmos-integrations-mcp` | 使用 OAuth/OIDC/service account/short-lived token | implementation | P2 |
| `ELMOS-PI-35-T04` | `elmos-integrations-mcp` | 为读取、搜索、写入、回调定义精确工具 Schema | implementation | P2 |
| `ELMOS-PI-35-T05` | `elmos-integrations-mcp` | 实现限流、重试、幂等、游标同步和健康检查 | implementation | P2 |
| `ELMOS-PI-35-T06` | `elmos-integrations-mcp` | 为连接器建立权限、审计、数据驻留和故障降级 | implementation | P2 |
| `ELMOS-PI-35-T07` | `elmos-integrations-mcp` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-35-T08` | `elmos-integrations-mcp` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-35-T09` | `elmos-integrations-mcp` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-35-T10` | `elmos-integrations-mcp` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## BATCH-10-scale-and-observability

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-36-T01` | `elmos-large-repository-scaling` | 按仓库、模块、语言、构建单元和内容哈希分片 | implementation | P2 |
| `ELMOS-PI-36-T02` | `elmos-large-repository-scaling` | 定义优先索引：manifest→入口→高价值模块→全量 | implementation | P2 |
| `ELMOS-PI-36-T03` | `elmos-large-repository-scaling` | 并行解析但串行提交一致图谱版本 | implementation | P2 |
| `ELMOS-PI-36-T04` | `elmos-large-repository-scaling` | 对图查询实施分页、限制、近似和预计算 | implementation | P2 |
| `ELMOS-PI-36-T05` | `elmos-large-repository-scaling` | 控制模型上下文、批处理、缓存和并发配额 | implementation | P2 |
| `ELMOS-PI-36-T06` | `elmos-large-repository-scaling` | 执行 S/M/L/XL 仓库压测和故障注入 | implementation | P2 |
| `ELMOS-PI-36-T07` | `elmos-large-repository-scaling` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-36-T08` | `elmos-large-repository-scaling` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-36-T09` | `elmos-large-repository-scaling` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-36-T10` | `elmos-large-repository-scaling` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-37-T01` | `elmos-observability-slo` | 定义服务和用户旅程级 SLI | implementation | P2 |
| `ELMOS-PI-37-T02` | `elmos-observability-slo` | 统一 trace_id、job_id、project_id、analysis_run_id、artifact_id | implementation | P2 |
| `ELMOS-PI-37-T03` | `elmos-observability-slo` | 记录队列、阶段时长、重试、缓存、Token、模型、渲染和图查询指标 | implementation | P2 |
| `ELMOS-PI-37-T04` | `elmos-observability-slo` | 记录质量指标：解析率、图完整度、引用正确率、stale 率 | implementation | P2 |
| `ELMOS-PI-37-T05` | `elmos-observability-slo` | 建立 SLO、错误预算、告警和 Runbook | implementation | P2 |
| `ELMOS-PI-37-T06` | `elmos-observability-slo` | 实现敏感字段过滤与日志采样 | implementation | P2 |
| `ELMOS-PI-37-T07` | `elmos-observability-slo` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-37-T08` | `elmos-observability-slo` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-37-T09` | `elmos-observability-slo` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-37-T10` | `elmos-observability-slo` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## BATCH-11-testing-conversion-estimation

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-38-T01` | `elmos-testing-evaluation` | 建立小型合成仓库和真实许可基准仓库 | implementation | P2 |
| `ELMOS-PI-38-T02` | `elmos-testing-evaluation` | 为 parser、graph、evidence、rule、merge、renderer 写单元/属性测试 | implementation | P2 |
| `ELMOS-PI-38-T03` | `elmos-testing-evaluation` | 为 API/Event/DB/connector 写契约测试 | implementation | P2 |
| `ELMOS-PI-38-T04` | `elmos-testing-evaluation` | 为核心用户旅程写浏览器 E2E | implementation | P2 |
| `ELMOS-PI-38-T05` | `elmos-testing-evaluation` | 建立问答、讲解、流程发现、图表和文档的黄金评测 | implementation | P2 |
| `ELMOS-PI-38-T06` | `elmos-testing-evaluation` | 运行性能、安全、恢复、权限和数据质量门禁 | implementation | P2 |
| `ELMOS-PI-38-T07` | `elmos-testing-evaluation` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-38-T08` | `elmos-testing-evaluation` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-38-T09` | `elmos-testing-evaluation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-38-T10` | `elmos-testing-evaluation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-39-T01` | `elmos-conversion-integration` | 让 Elmos 生成/转换中的中间 revision 直接进入阅读器 | implementation | P3 |
| `ELMOS-PI-39-T02` | `elmos-conversion-integration` | 连接 Source Symbol、Semantic IR、Target Symbol 和 Rule 命中 | implementation | P3 |
| `ELMOS-PI-39-T03` | `elmos-conversion-integration` | 生成模块、API、数据、流程和架构前后映射 | implementation | P3 |
| `ELMOS-PI-39-T04` | `elmos-conversion-integration` | 显示未支持、低置信度、编译/测试失败和自动修复历史 | implementation | P3 |
| `ELMOS-PI-39-T05` | `elmos-conversion-integration` | 将人工修改提炼为候选规则但不自动发布 | implementation | P3 |
| `ELMOS-PI-39-T06` | `elmos-conversion-integration` | 完成后生成迁移文档、图表、PPT 和证据包 | implementation | P3 |
| `ELMOS-PI-39-T07` | `elmos-conversion-integration` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-39-T08` | `elmos-conversion-integration` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-39-T09` | `elmos-conversion-integration` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-39-T10` | `elmos-conversion-integration` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |
| `ELMOS-PI-40-T01` | `elmos-runtime-cost-estimator` | 抽取 LOC、文件、语言、构建单元、动态特性、图规模和 artifact 数量 | implementation | P3 |
| `ELMOS-PI-40-T02` | `elmos-runtime-cost-estimator` | 匹配相似历史任务并按阶段建立基线 | implementation | P3 |
| `ELMOS-PI-40-T03` | `elmos-runtime-cost-estimator` | 估算排队、解析、图谱、模型、渲染、测试和导出时间 | implementation | P3 |
| `ELMOS-PI-40-T04` | `elmos-runtime-cost-estimator` | 估算输入/输出 Token、缓存命中、模型价格和基础设施成本 | implementation | P3 |
| `ELMOS-PI-40-T05` | `elmos-runtime-cost-estimator` | 任务运行中使用实际进度和重试动态校准 | implementation | P3 |
| `ELMOS-PI-40-T06` | `elmos-runtime-cost-estimator` | 显示假设、置信区间和偏差回溯 | implementation | P3 |
| `ELMOS-PI-40-T07` | `elmos-runtime-cost-estimator` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-40-T08` | `elmos-runtime-cost-estimator` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-40-T09` | `elmos-runtime-cost-estimator` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-40-T10` | `elmos-runtime-cost-estimator` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## BATCH-12-deployment-and-certification

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-41-T01` | `elmos-deployment-private-cloud` | 定义服务镜像、依赖、资源和安全上下文 | implementation | P3 |
| `ELMOS-PI-41-T02` | `elmos-deployment-private-cloud` | 提供本地 Compose 与生产 Kubernetes/Helm | implementation | P3 |
| `ELMOS-PI-41-T03` | `elmos-deployment-private-cloud` | 配置数据库、图存储、对象存储、Temporal、缓存和可观测性 | implementation | P3 |
| `ELMOS-PI-41-T04` | `elmos-deployment-private-cloud` | 实现 egress allowlist、Secrets、TLS、SSO 和数据驻留 | implementation | P3 |
| `ELMOS-PI-41-T05` | `elmos-deployment-private-cloud` | 制定备份、恢复、升级、Schema migration 和回滚 | implementation | P3 |
| `ELMOS-PI-41-T06` | `elmos-deployment-private-cloud` | 执行灾难恢复、节点故障和版本升级演练 | implementation | P3 |
| `ELMOS-PI-41-T07` | `elmos-deployment-private-cloud` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-41-T08` | `elmos-deployment-private-cloud` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-41-T09` | `elmos-deployment-private-cloud` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-41-T10` | `elmos-deployment-private-cloud` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |
| `ELMOS-PI-42-T01` | `elmos-release-certification` | 定义 E1 原型、E2 可验证、E3 团队级、E4 生产级、E5 关键业务级标准 | implementation | P3 |
| `ELMOS-PI-42-T02` | `elmos-release-certification` | 收集构建、测试、评测、性能、安全、权限、恢复和文档证据 | implementation | P3 |
| `ELMOS-PI-42-T03` | `elmos-release-certification` | 验证证据新鲜度、revision、环境和完整性 | implementation | P3 |
| `ELMOS-PI-42-T04` | `elmos-release-certification` | 执行硬门禁与可审批 waiver | implementation | P3 |
| `ELMOS-PI-42-T05` | `elmos-release-certification` | 生成失败项、修复任务、残余风险和重新认证范围 | implementation | P3 |
| `ELMOS-PI-42-T06` | `elmos-release-certification` | 冻结并签名认证报告 | implementation | P3 |
| `ELMOS-PI-42-T07` | `elmos-release-certification` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-42-T08` | `elmos-release-certification` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-42-T09` | `elmos-release-certification` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-42-T10` | `elmos-release-certification` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## BATCH-13-commercialization

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-43-T01` | `elmos-commercial-packaging` | 定义个人开发者、团队、软件现代化服务商和大型企业场景 | implementation | P3 |
| `ELMOS-PI-43-T02` | `elmos-commercial-packaging` | 按代码规模、分析 run、模型 Token、artifact、并发和保留期设计计量 | implementation | P3 |
| `ELMOS-PI-43-T03` | `elmos-commercial-packaging` | 设计 Reader、Architecture、Documentation、Modernization 等套餐 | implementation | P3 |
| `ELMOS-PI-43-T04` | `elmos-commercial-packaging` | 区分 SaaS、专属租户、私有化和离线授权 | implementation | P3 |
| `ELMOS-PI-43-T05` | `elmos-commercial-packaging` | 定义试用、超额、预算告警、用量可视化和成本归因 | implementation | P3 |
| `ELMOS-PI-43-T06` | `elmos-commercial-packaging` | 生成售前材料、实施清单和 SLA 边界 | implementation | P3 |
| `ELMOS-PI-43-T07` | `elmos-commercial-packaging` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-43-T08` | `elmos-commercial-packaging` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-43-T09` | `elmos-commercial-packaging` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-43-T10` | `elmos-commercial-packaging` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## BATCH-14-online-debug-and-learning

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-44-T01` | `elmos-debug-adapter-gateway` | 建立 JVM、Python、.NET、Node/TypeScript、Go、Rust/C++、PHP、Dart/Flutter、Swift/Objective-C 与 Browser 的适配器注册表和版本矩阵 | implementation | P1 |
| `ELMOS-PI-44-T02` | `elmos-debug-adapter-gateway` | 实现 DAP Session Broker、请求/响应序列关联和 WebSocket 双向传输 | implementation | P1 |
| `ELMOS-PI-44-T03` | `elmos-debug-adapter-gateway` | 实现 Browser/CDP Bridge、Source Map 解析与前端源文件 revision 绑定 | implementation | P1 |
| `ELMOS-PI-44-T04` | `elmos-debug-adapter-gateway` | 实现适配器进程生命周期、健康检查、版本钉住、能力协商和优雅关闭 | implementation | P1 |
| `ELMOS-PI-44-T05` | `elmos-debug-adapter-gateway` | 统一 Breakpoint、Thread、Stack、Scope、Variable、Evaluate、Output、Module 和 Termination 模型 | implementation | P1 |
| `ELMOS-PI-44-T06` | `elmos-debug-adapter-gateway` | 实现背压、事件去重、断线重连、懒加载变量分页、超大对象截断和协议错误隔离 | implementation | P1 |
| `ELMOS-PI-44-T07` | `elmos-debug-adapter-gateway` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-44-T08` | `elmos-debug-adapter-gateway` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-44-T09` | `elmos-debug-adapter-gateway` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-44-T10` | `elmos-debug-adapter-gateway` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-45-T01` | `elmos-debug-sandbox-orchestration` | 定义语言/框架 Runtime Profile，并绑定构建命令、启动目标、端口、环境、adapter 和镜像摘要 | implementation | P1 |
| `ELMOS-PI-45-T02` | `elmos-debug-sandbox-orchestration` | 创建非 Root、只读根文件系统、临时可写层、资源配额、进程限制和系统调用隔离的容器或微型虚拟机 | implementation | P1 |
| `ELMOS-PI-45-T03` | `elmos-debug-sandbox-orchestration` | 实现 launch/attach 环境资格策略；生产进程默认不可暂停或附加 | implementation | P1 |
| `ELMOS-PI-45-T04` | `elmos-debug-sandbox-orchestration` | 接入 Secrets Broker、短期凭证、合成/脱敏数据集和默认拒绝的出站网络策略 | implementation | P1 |
| `ELMOS-PI-45-T05` | `elmos-debug-sandbox-orchestration` | 实现 provision→build→launch→heartbeat→terminate→cleanup→attest 全生命周期和超时回收 | implementation | P1 |
| `ELMOS-PI-45-T06` | `elmos-debug-sandbox-orchestration` | 实现表达式/调试控制台策略：默认只读，副作用表达式仅在一次性环境经显式审批后执行 | implementation | P1 |
| `ELMOS-PI-45-T07` | `elmos-debug-sandbox-orchestration` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-45-T08` | `elmos-debug-sandbox-orchestration` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-45-T09` | `elmos-debug-sandbox-orchestration` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-45-T10` | `elmos-debug-sandbox-orchestration` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-46-T01` | `elmos-online-debug-workbench` | 实现创建会话向导：revision、runtime profile、入口/测试/场景、数据集、学习模式和资源预算 | implementation | P1 |
| `ELMOS-PI-46-T02` | `elmos-online-debug-workbench` | 在 Monaco 中实现行断点、条件断点、Logpoint、异常/函数/数据断点的能力感知 UI | implementation | P1 |
| `ELMOS-PI-46-T03` | `elmos-online-debug-workbench` | 实现 Continue、Pause、Step Over/Into/Out、Run to Cursor、Restart 和 Terminate 控制栏 | implementation | P1 |
| `ELMOS-PI-46-T04` | `elmos-online-debug-workbench` | 实现 Thread、Call Stack、Scope、Variable、Watch、Evaluate、Module 和 Breakpoint 面板及懒加载 | implementation | P1 |
| `ELMOS-PI-46-T05` | `elmos-online-debug-workbench` | 实现 Output、Log、HTTP/RPC、SQL、Cache、MQ、File I/O、Lock/Coroutine 与状态差异时间线 | implementation | P1 |
| `ELMOS-PI-46-T06` | `elmos-online-debug-workbench` | 把当前 Frame、调用栈和副作用映射到 Code Graph、架构图、流程图、数据资产、测试和证据 | implementation | P1 |
| `ELMOS-PI-46-T07` | `elmos-online-debug-workbench` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-46-T08` | `elmos-online-debug-workbench` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-46-T09` | `elmos-online-debug-workbench` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-46-T10` | `elmos-online-debug-workbench` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-47-T01` | `elmos-debug-learning-copilot` | 实现 Observe、Guided、Challenge、Free 和 Compare 五种学习模式及难度分级 | implementation | P1 |
| `ELMOS-PI-47-T02` | `elmos-debug-learning-copilot` | 从模块、功能、流程、测试或缺陷生成有前置条件、断点、目标和完成条件的 Learning Mission | implementation | P1 |
| `ELMOS-PI-47-T03` | `elmos-debug-learning-copilot` | 解释当前暂停原因、Frame 职责、变量来源、分支条件、下一步候选和可能副作用，并附证据 | implementation | P1 |
| `ELMOS-PI-47-T04` | `elmos-debug-learning-copilot` | 实现苏格拉底式提问、执行前预测、分层 Hint 和显式 Reveal，避免直接泄露挑战答案 | implementation | P1 |
| `ELMOS-PI-47-T05` | `elmos-debug-learning-copilot` | 实现 Checkpoint、Quiz、Score、Notes、Knowledge Card、进度和角色化学习路径联动 | implementation | P1 |
| `ELMOS-PI-47-T06` | `elmos-debug-learning-copilot` | 把已脱敏调试会话发布为可复用 Lab，支持版本绑定、团队分配、评审和 stale 提醒 | implementation | P1 |
| `ELMOS-PI-47-T07` | `elmos-debug-learning-copilot` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-47-T08` | `elmos-debug-learning-copilot` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-47-T09` | `elmos-debug-learning-copilot` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-47-T10` | `elmos-debug-learning-copilot` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-48-T01` | `elmos-debug-record-replay` | 定义 R0 事件时间线、R1 输入/测试重放、R2 检查点恢复、R3 原生反向调试四级能力矩阵 | implementation | P2 |
| `ELMOS-PI-48-T02` | `elmos-debug-record-replay` | 记录调试命令、事件、Frame、变量差异、输出、副作用、Trace 关联和采样/截断元数据 | implementation | P2 |
| `ELMOS-PI-48-T03` | `elmos-debug-record-replay` | 生成带 manifest、内容哈希、签名、加密、脱敏和保留策略的 Replay Bundle | implementation | P2 |
| `ELMOS-PI-48-T04` | `elmos-debug-record-replay` | 实现测试输入重放、环境快照恢复和可验证的 checkpoint 创建/恢复流程 | implementation | P2 |
| `ELMOS-PI-48-T05` | `elmos-debug-record-replay` | 运行时支持时提供 Reverse Continue/Step；不支持时自动降级到 checkpoint/input replay | implementation | P2 |
| `ELMOS-PI-48-T06` | `elmos-debug-record-replay` | 实现 passing/failing、before/after、source/target 两次运行的状态与副作用时间线比较 | implementation | P2 |
| `ELMOS-PI-48-T07` | `elmos-debug-record-replay` | 实现权限、安全、沙箱和不可信输入防护 | security | P2 |
| `ELMOS-PI-48-T08` | `elmos-debug-record-replay` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P2 |
| `ELMOS-PI-48-T09` | `elmos-debug-record-replay` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P2 |
| `ELMOS-PI-48-T10` | `elmos-debug-record-replay` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-49-T01` | `elmos-distributed-debug-correlation` | 贯通 browser interaction、traceparent、request_id、message_id、workflow/task_id 和 debug_session_id | implementation | P2 |
| `ELMOS-PI-49-T02` | `elmos-distributed-debug-correlation` | 构建跨服务、线程、协程、消息、定时任务和数据库事务的因果 Session Graph | implementation | P2 |
| `ELMOS-PI-49-T03` | `elmos-distributed-debug-correlation` | 在非生产测试环境实现受控协同断点、超时预算、服务虚拟化和死锁/级联超时保护 | implementation | P2 |
| `ELMOS-PI-49-T04` | `elmos-distributed-debug-correlation` | 在暂停点周围联动 Span、Log、Metric、SQL、Cache、MQ 和外部调用状态 | implementation | P2 |
| `ELMOS-PI-49-T05` | `elmos-distributed-debug-correlation` | 实现 Source/IR/Target 同场景双运行、关键变量/状态/副作用对齐和语义分歧检测 | implementation | P2 |
| `ELMOS-PI-49-T06` | `elmos-distributed-debug-correlation` | 实现测试失败→Trace→服务→Frame→变量/数据→代码→修复/学习任务的深链 | implementation | P2 |
| `ELMOS-PI-49-T07` | `elmos-distributed-debug-correlation` | 实现权限、安全、沙箱和不可信输入防护 | security | P2 |
| `ELMOS-PI-49-T08` | `elmos-distributed-debug-correlation` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P2 |
| `ELMOS-PI-49-T09` | `elmos-distributed-debug-correlation` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P2 |
| `ELMOS-PI-49-T10` | `elmos-distributed-debug-correlation` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

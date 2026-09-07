# Elmos Atomic Skill Catalog v3.0.0

总计 **1310** 个原子 Skill，分布于 **41** 个 Capability Pack。

> `specification-ready` 表示生产级契约和实现要求已定义，不表示对应 Runtime 已编码或认证。

## 00-foundation-contracts

原子 Skill：**14**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `architecture-decision-record` | P1 | medium | platform-foundation | 把关键架构选择、假设、替代方案和退出条件沉淀为可检索 ADR。 |
| `artifact-identity-and-hashing` | P0 | high | platform-foundation | 为知识对象、数据集、模型、Adapter、Skill、工具镜像和证据生成不可歧义的内容身份与哈希。 |
| `capability-dependency-graph` | P1 | medium | platform-foundation | 建立能力依赖图并计算循环依赖、爆炸半径、升级影响和最小发布闭包。 |
| `capability-taxonomy-governance` | P0 | high | platform-foundation | 统一定义能力域、Skill 粒度、风险等级、成熟度、依赖和所有权，防止能力重复与边界漂移。 |
| `compatibility-matrix-manager` | P0 | high | platform-foundation | 管理语言、框架、数据库、模型、硬件、驱动、工具和 Skill 的版本兼容矩阵。 |
| `contract-migration-manager` | P1 | medium | platform-foundation | 在契约 Schema 升级时完成向前兼容、双写、迁移验证和安全回滚。 |
| `data-usage-consent-contract` | P0 | high | platform-foundation | 约束数据可否检索、记录、标注、训练、跨租户聚合、导出、删除和保留。 |
| `evidence-contract` | P0 | high | platform-foundation | 定义每项能力必须产生的编译、测试、差分、证明、安全和人工审批证据。 |
| `extension-sdk-and-codegen` | P1 | medium | platform-foundation | 提供新增知识连接器、Skill、验证器、训练器和部署适配器的 SDK 与脚手架。 |
| `package-conformance-validator` | P0 | high | platform-foundation | 对整个 Skills Package 执行结构、命名、权限、证据和依赖一致性校验。 |
| `policy-contract` | P0 | high | platform-foundation | 把数据、权限、训练、部署和合规规则表达成可执行、可测试、可审计的策略契约。 |
| `release-bundle-contract` | P0 | high | platform-foundation | 把模型、Adapter、Skill 集、知识快照、工具链、策略和评测基线绑定为不可变发布单元。 |
| `tenancy-scope-contract` | P0 | high | platform-foundation | 明确平台、组织、租户、项目、仓库、分支、任务和用户各级数据与能力作用域。 |
| `typed-skill-contract` | P0 | high | platform-foundation | 定义 Skill 的输入、输出、前置条件、后置条件、工具权限、失败语义和副作用契约。 |

## 01-knowledge-ingestion-governance

原子 Skill：**20**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-contract-ingestion` | P0 | high | knowledge-ingestion | 摄取 OpenAPI、AsyncAPI、GraphQL、Proto、IDL 和事件 Schema，生成版本化 API 知识对象。 |
| `archive-and-folder-ingestion` | P0 | high | knowledge-ingestion | 安全处理文件夹、zip、tar.gz、嵌套归档、超大文件和损坏归档。 |
| `artifact-normalization` | P0 | high | knowledge-ingestion | 将不同格式统一为 Artifact IR，保留原始字节、字符位置、页码和源映射。 |
| `connector-health-and-backfill` | P1 | medium | knowledge-ingestion | 监控同步延迟、缺页、断点、权限变化，并安全完成补采与校验。 |
| `data-residency-aware-routing` | P1 | medium | knowledge-ingestion | 按租户、地域和法规要求选择存储、索引、处理和训练区域。 |
| `database-metadata-ingestion` | P0 | high | knowledge-ingestion | 摄取 Schema、Routine、触发器、索引、约束、统计信息和执行计划。 |
| `document-structure-ingestion` | P0 | high | knowledge-ingestion | 解析 Markdown、HTML、Word、PDF、TXT 与表格，恢复标题、章节、表格、引用和附件关系。 |
| `incident-runbook-ingestion` | P1 | medium | knowledge-ingestion | 将故障报告、复盘、Runbook、变更记录和恢复步骤转换为可执行知识。 |
| `incremental-change-capture` | P0 | high | knowledge-ingestion | 通过内容哈希和变更事件只重算受影响知识分片、图关系和向量。 |
| `ingestion-quarantine-gate` | P0 | high | knowledge-ingestion | 对来源不明、许可不清、解析失败、污染或恶意内容执行隔离与复核。 |
| `issue-pr-review-ingestion` | P1 | medium | knowledge-ingestion | 沉淀 Issue、PR、代码审查意见、提交理由与最终修复之间的因果和语义关系。 |
| `knowledge-source-connector-registry` | P0 | high | knowledge-ingestion | 注册并治理 Git、对象存储、Wiki、Issue、PR、CI、数据库和日志等知识源连接器。 |
| `license-and-rights-classification` | P0 | high | knowledge-ingestion | 识别许可证、客户合同限制、训练许可、再分发权限和归属义务。 |
| `multimodal-artifact-ingestion` | P1 | medium | knowledge-ingestion | 解析架构图、流程图、UI 截图、日志截图、音视频说明和代码演示。 |
| `provenance-and-lineage-capture` | P0 | high | knowledge-ingestion | 记录来源 URI、提交、作者、解析器、转换步骤、父子对象和派生链。 |
| `repository-incremental-ingestion` | P0 | high | knowledge-ingestion | 按提交、分支和文件增量摄取仓库，保留删除、重命名、子模块和生成代码语义。 |
| `runtime-trace-ingestion` | P1 | medium | knowledge-ingestion | 接入 Trace、Metric、Log、Profile、SQL 与消息链路，并与静态代码实体关联。 |
| `sensitive-data-and-secret-detection` | P0 | high | knowledge-ingestion | 发现凭据、密钥、个人信息、商业秘密、受监管数据和高敏代码。 |
| `source-freshness-and-expiry` | P0 | high | knowledge-ingestion | 跟踪知识有效期、版本适用范围、失效日期、最后验证时间和刷新 SLA。 |
| `structure-recovery-and-ocr-fallback` | P1 | medium | knowledge-ingestion | 优先结构化解析，在必要时受控启用 OCR，并记录置信度和人工复核点。 |

## 02-repository-semantic-intelligence

原子 Skill：**24**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-and-event-contract-graph` | P0 | high | repository-intelligence | 建立 API、RPC、事件、Schema、消费者和生产者的契约依赖图。 |
| `architecture-recovery` | P1 | medium | repository-intelligence | 从代码、构建、部署和运行证据恢复模块边界、层次、领域和依赖违规。 |
| `build-and-dependency-graph` | P0 | high | repository-intelligence | 解析构建模块、依赖、插件、Profile、代码生成和包解析结果。 |
| `call-graph-construction` | P0 | high | repository-intelligence | 组合静态、动态和配置证据构建调用图，并显式表达不确定边。 |
| `configuration-semantics-graph` | P0 | high | repository-intelligence | 关联配置键、环境变量、Feature Flag、Bean、资源和运行行为。 |
| `control-flow-graph` | P0 | high | repository-intelligence | 恢复分支、循环、异常、协程、回调和异步控制流。 |
| `cross-source-entity-resolution` | P0 | high | repository-intelligence | 合并文档、代码、数据库、Issue 和运行数据中的同一实体并保留别名。 |
| `data-flow-and-taint-graph` | P0 | high | repository-intelligence | 跟踪变量、字段、对象、请求、数据库和消息中的数据流与污点传播。 |
| `database-schema-and-query-graph` | P0 | high | repository-intelligence | 关联表、列、约束、Routine、ORM 映射、SQL 与业务调用。 |
| `deployment-topology-graph` | P1 | medium | repository-intelligence | 恢复服务、容器、端口、队列、数据库、网络策略和区域拓扑。 |
| `domain-ontology-induction` | P1 | medium | repository-intelligence | 从命名、Schema、文档和流程中归纳领域实体、关系、规则和术语。 |
| `issue-code-rationale-graph` | P1 | medium | repository-intelligence | 关联需求、Issue、讨论、代码变更、回滚和设计理由。 |
| `knowledge-contradiction-detection` | P1 | medium | repository-intelligence | 发现文档、代码、测试、配置与运行事实之间的冲突并定位证据。 |
| `multi-language-ast-extraction` | P0 | high | repository-intelligence | 为支持语言构建带源映射、错误恢复和版本信息的统一 AST。 |
| `program-dependency-graph` | P1 | medium | repository-intelligence | 融合控制依赖与数据依赖，支持影响分析、切片和最小变更计算。 |
| `runtime-static-correlation` | P1 | medium | repository-intelligence | 把生产 Trace、SQL、异常和性能热点映射回静态语义实体。 |
| `security-policy-graph` | P0 | high | repository-intelligence | 关联身份、角色、权限、路由、数据对象、过滤器和安全配置。 |
| `semantic-diff-and-impact-analysis` | P0 | high | repository-intelligence | 比较两个版本的 API、行为、数据、依赖和风险变化，而非仅文本差异。 |
| `semantic-ir-reconciliation` | P0 | high | repository-intelligence | 将多解析器、多语言和多来源结果收敛为可追溯、带置信度的统一 Semantic IR。 |
| `symbol-and-reference-graph` | P0 | high | repository-intelligence | 解析定义、引用、重载、泛型、反射、动态调用和跨模块符号关系。 |
| `temporal-version-semantic-graph` | P0 | high | repository-intelligence | 支持双时态知识、版本区间、分支差异和历史语义查询。 |
| `test-to-code-evidence-graph` | P1 | medium | repository-intelligence | 连接测试、覆盖、变异、需求、缺陷、代码实体和认证证据。 |
| `transaction-boundary-graph` | P0 | high | repository-intelligence | 识别事务传播、隔离级别、锁、补偿、幂等和跨服务一致性边界。 |
| `type-and-contract-graph` | P0 | high | repository-intelligence | 表达类型、泛型、继承、接口、Nullability、约束和结构类型关系。 |

## 03-retrieval-context-engineering

原子 Skill：**20**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `citation-and-source-binding` | P0 | high | retrieval-context | 让每个关键事实、建议和变换都绑定来源对象、版本和位置。 |
| `context-budget-optimizer` | P0 | high | retrieval-context | 在 Token、延迟和成本约束下最大化有用证据覆盖和相互依赖完整性。 |
| `delta-context-construction` | P0 | high | retrieval-context | 只注入自上次检查点以来的语义变化，减少长任务重复上下文。 |
| `evidence-preserving-compression` | P1 | medium | retrieval-context | 压缩代码和文档时保留类型、约束、异常、边界和引用位置。 |
| `execution-path-retrieval` | P1 | medium | retrieval-context | 使用运行 Trace 与失败路径优先选取真实执行相关上下文。 |
| `graph-path-retrieval` | P0 | high | retrieval-context | 按调用、数据流、事务、安全或部署路径检索跨文件证据链。 |
| `hierarchical-context-packing` | P0 | high | retrieval-context | 按架构摘要、文件摘要、符号和必要源码分层组织上下文。 |
| `hybrid-code-knowledge-retrieval` | P0 | high | retrieval-context | 融合关键词、向量、符号、类型和图关系检索代码与知识。 |
| `lost-in-middle-mitigation` | P1 | medium | retrieval-context | 通过分段、重排、重复锚点和检索式回读降低长上下文中间信息丢失。 |
| `multi-hop-evidence-retrieval` | P1 | medium | retrieval-context | 通过多跳图搜索补齐需求到实现、实现到测试、错误到修复的链路。 |
| `query-decomposition-and-rewrite` | P1 | medium | retrieval-context | 将复合工程任务拆为符号、行为、依赖、测试和风险检索子查询。 |
| `retrieval-evaluation-and-replay` | P0 | high | retrieval-context | 离线重放检索过程并计算 Recall、MRR、引用准确率和有用上下文比。 |
| `retrieval-hard-negative-mining` | P1 | medium | retrieval-context | 从高相似但错误版本、错误框架和同名符号中构造困难负样本。 |
| `retrieval-injection-defense` | P0 | high | retrieval-context | 隔离不可信内容、标记指令性文本并阻止知识内容升级为系统权限。 |
| `semantic-context-cache` | P1 | medium | retrieval-context | 缓存任务语义包并根据依赖图和知识变更进行精确失效。 |
| `stale-and-conflict-arbitration` | P0 | high | retrieval-context | 识别过期或冲突上下文，按权威度、时间和运行证据裁决。 |
| `symbol-aware-retrieval` | P0 | high | retrieval-context | 围绕定义、引用、实现、测试、配置和调用方检索完整符号上下文。 |
| `task-specific-reranking` | P0 | high | retrieval-context | 按任务类型训练并应用代码、文档、错误和 Skill 专用重排器。 |
| `tenant-policy-aware-retrieval` | P0 | high | retrieval-context | 在检索前执行租户、项目、角色、地域和敏感级别权限裁剪。 |
| `version-aware-retrieval` | P0 | high | retrieval-context | 根据语言、框架、数据库、分支和发布日期过滤不兼容知识。 |

## 04-memory-experience-flywheel

原子 Skill：**20**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `counterfactual-trajectory-replay` | P2 | research | memory-experience | 替换关键决策或上下文重放轨迹，估计某项改动的真实贡献。 |
| `cross-task-experience-transfer` | P1 | medium | memory-experience | 在满足边界条件时把经验迁移到相似仓库，并校准不确定性。 |
| `durable-task-checkpoint-memory` | P0 | high | memory-experience | 在暂停、断电、网络中断和进程迁移后恢复任务状态与副作用边界。 |
| `episodic-memory-store` | P0 | high | memory-experience | 保存一次任务的输入、环境、步骤、失败、修复、结果和证据。 |
| `experience-clustering-and-dedupe` | P1 | medium | memory-experience | 按任务、语言、框架、失败和修复模式聚类并去除近重复经历。 |
| `experience-episode-capture` | P0 | high | memory-experience | 形成标准 Episode，绑定仓库快照、知识、Skill、模型、环境和最终验收。 |
| `experience-value-scoring` | P0 | high | memory-experience | 按正确性、稀缺性、泛化性、证据完整度和训练权利评估经验价值。 |
| `failure-signature-extraction` | P0 | high | memory-experience | 从编译、测试、运行、安全和性能失败中生成稳定、可聚类的签名。 |
| `human-edit-diff-analysis` | P1 | medium | memory-experience | 区分人工对模型结果的修错、偏好调整、补需求和无关格式修改。 |
| `long-horizon-memory-compaction` | P1 | medium | memory-experience | 分层压缩长任务历史，保留决策、未决风险、工具结果哈希和恢复锚点。 |
| `memory-poisoning-defense` | P0 | high | memory-experience | 检测恶意、错误或低置信记忆，阻止其进入规划、检索与训练。 |
| `memory-retention-and-forgetting` | P0 | high | memory-experience | 根据用途、合同、风险和访问频率执行保留、降级、归档和删除。 |
| `outcome-attribution-and-credit` | P1 | medium | memory-experience | 把最终成功或失败归因到检索、Skill、计划、工具、模型和验证步骤。 |
| `procedural-memory-store` | P0 | high | memory-experience | 保存可执行步骤、工具参数、前置条件和回滚方式，为 Skill Mining 提供材料。 |
| `repair-pattern-extraction` | P1 | medium | memory-experience | 学习失败签名到补丁策略、验证步骤和适用条件的映射。 |
| `semantic-memory-distiller` | P0 | high | memory-experience | 从多次经历中提炼稳定事实、规则和模式，并保留来源覆盖范围。 |
| `tenant-memory-isolation-and-replay` | P0 | high | memory-experience | 确保经验不可跨租户泄漏，且在固定环境中可以确定性重放验证。 |
| `tool-event-normalization` | P0 | high | memory-experience | 统一不同模型和 Agent 框架的工具请求、结果、错误和权限决策格式。 |
| `trajectory-segmentation` | P1 | medium | memory-experience | 把长轨迹切分为规划、定位、修改、验证、修复和发布等可学习片段。 |
| `working-memory-manager` | P0 | high | memory-experience | 维护当前任务假设、计划、约束、待办、已验证事实和风险，不混入长期记忆。 |

## 05-skill-foundry-runtime

原子 Skill：**29**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `anti-pattern-and-guardrail-miner` | P1 | medium | skill-runtime | 把重复错误、绕过行为和风险操作沉淀为禁止规则与防护 Skill。 |
| `commit-history-to-skill-miner` | P1 | medium | skill-runtime | 从重复提交、修复和评审意见中发现可自动化工程模式。 |
| `cross-agent-skill-portability` | P1 | medium | skill-runtime | 验证 Skill 在 Codex、Claude Code、兼容 Agent 和 Elmos Runtime 的可移植性。 |
| `deterministic-script-packager` | P0 | high | skill-runtime | 把高精度步骤固化为幂等、可测试、稳定接口的脚本资源。 |
| `hierarchical-skill-registry` | P0 | high | skill-runtime | 提供平台、组织、租户、项目和仓库级 Skill 注册、搜索和优先级覆盖。 |
| `incident-to-recovery-skill-miner` | P1 | medium | skill-runtime | 从故障与恢复记录生成诊断、止损、修复和复盘 Skill。 |
| `progressive-skill-disclosure` | P0 | high | skill-runtime | 只暴露 Meta-Skill 目录，激活后再加载原子 Skill 和必要资源。 |
| `proof-carrying-skill` | P0 | high | skill-runtime | 要求 Skill 输出可机器验证的证明义务、测试结果、未决风险和回滚信息。 |
| `runbook-to-skill-compiler` | P1 | medium | skill-runtime | 把人工 Runbook 转换为带条件、分支、工具、证据和异常处理的工作流。 |
| `skill-activation-router` | P0 | high | skill-runtime | 根据用户意图、仓库事实、风险和能力置信度选择应加载的 Skill。 |
| `skill-authoring-workbench` | P0 | high | skill-runtime | 从需求和领域方法创建兼容 SKILL.md 的强类型 Skill，并生成模板、契约和评测。 |
| `skill-boundary-discovery` | P1 | medium | skill-runtime | 判断能力应拆为原子 Skill、复合 Skill、知识规则还是模型能力。 |
| `skill-context-pinning` | P1 | medium | skill-runtime | 在长任务压缩和子 Agent 委派中保护已激活 Skill 的关键契约。 |
| `skill-decomposition-and-composition` | P0 | high | skill-runtime | 拆解过大 Skill，组合原子 Skill，并验证数据、权限和失败语义兼容。 |
| `skill-dependency-resolver` | P0 | high | skill-runtime | 解析 Skill、工具、模型、环境和 Schema 依赖，生成可重复执行闭包。 |
| `skill-deprecation-and-revocation` | P0 | high | skill-runtime | 在缺陷、安全事件或依赖失效时阻止新调用并迁移现有任务。 |
| `skill-description-optimizer` | P1 | medium | skill-runtime | 使用应触发与不应触发样本优化 description，控制漏触发和误触发。 |
| `skill-efficiency-evaluation` | P1 | medium | skill-runtime | 衡量 Token、工具次数、重试、Wall-clock、缓存和成本效率。 |
| `skill-output-evaluation` | P0 | high | skill-runtime | 检查最终代码、文档、补丁、报告和证据是否满足契约。 |
| `skill-process-evaluation` | P0 | high | skill-runtime | 检查是否遵守规定步骤、工具、审批、验证和最小副作用约束。 |
| `skill-replay-and-snapshot` | P0 | high | skill-runtime | 在固定仓库、镜像、模型和知识快照中重放 Skill 执行。 |
| `skill-robustness-evaluation` | P1 | medium | skill-runtime | 覆盖边界输入、版本变化、工具失败、并发、恢复和恶意内容。 |
| `skill-sandbox-executor` | P0 | high | skill-runtime | 在受限环境中执行脚本与工具，施加文件、网络、CPU、内存和时间限制。 |
| `skill-signing-and-release` | P0 | high | skill-runtime | 对 Skill 内容、依赖、脚本、策略和评测结果签名后发布。 |
| `skill-telemetry-and-cost-profile` | P1 | medium | skill-runtime | 持续记录触发、成功、失败、成本、模型组合和客户价值。 |
| `skill-transaction-and-rollback` | P0 | high | skill-runtime | 为有副作用 Skill 建立幂等键、补偿事务、检查点和回滚演练。 |
| `skill-trigger-evaluation` | P0 | high | skill-runtime | 评估应触发、不应触发、模糊意图、错别字和多意图场景。 |
| `skill-version-and-compatibility` | P0 | high | skill-runtime | 管理 SemVer、兼容范围、依赖锁定、升级迁移和回滚版本。 |
| `trajectory-to-skill-miner` | P1 | medium | skill-runtime | 从多次成功且已验证轨迹中抽取稳定步骤、参数和适用边界。 |

## 06-dataset-foundry

原子 Skill：**30**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `active-learning-sample-selection` | P1 | medium | dataset-foundry | 按不确定性、业务价值、失败频率和信息增益选择人工标注样本。 |
| `benchmark-contamination-detection` | P0 | high | dataset-foundry | 检测公开基准、测试答案、下游评测仓库和相似变体进入训练数据。 |
| `bronze-dataset-intake` | P0 | high | dataset-foundry | 保存原始轨迹和产物但禁止训练，确保可追溯和可重新处理。 |
| `cross-tenant-data-separation` | P0 | high | dataset-foundry | 通过物理或逻辑分区、密钥和查询策略阻止跨租户训练泄漏。 |
| `curriculum-and-mixture-optimizer` | P1 | medium | dataset-foundry | 按难度、语言、业务线和失败模式优化训练顺序与数据混合比例。 |
| `dataset-contract-and-schema` | P0 | high | dataset-foundry | 定义任务、上下文、轨迹、补丁、证据、奖励、权限和血缘的标准训练样本结构。 |
| `dataset-lineage-and-provenance` | P0 | high | dataset-foundry | 记录每个样本来自哪些对象、任务、模型、Skill、人工修改和转换步骤。 |
| `dataset-quarantine-management` | P0 | high | dataset-foundry | 隔离许可证不明、PII、密钥、污染、注入、低质量和结果不确定样本。 |
| `dataset-revocation-unlearning-index` | P0 | high | dataset-foundry | 记录样本到 Checkpoint/Adapter 的影响范围，支持撤回、删除和选择性重训。 |
| `dataset-version-card-and-signing` | P0 | high | dataset-foundry | 冻结版本、生成 Dataset Card、质量报告、权利摘要和数字签名。 |
| `eval-freeze-and-leakage-firewall` | P0 | high | dataset-foundry | 冻结评测集并在数据流水线、检索、Prompt 和训练阶段阻断泄漏。 |
| `gold-certified-promotion` | P0 | high | dataset-foundry | 要求独立验证、完整证据、专家接受或跨仓库复现后进入高可信训练层。 |
| `hard-negative-data-mining` | P1 | medium | dataset-foundry | 挖掘看似合理但版本、类型、事务、安全或行为错误的负例。 |
| `label-quality-and-adjudication` | P0 | high | dataset-foundry | 测量标注一致性、证据覆盖和审阅偏差，并执行专家仲裁。 |
| `mutation-counterexample-data` | P1 | medium | dataset-foundry | 从正确实现生成故障、边界、对抗和反例，训练修复与验证能力。 |
| `preference-pair-builder` | P1 | medium | dataset-foundry | 从人工接受、回滚、修复差异和验证证据生成 chosen/rejected 样本对。 |
| `process-supervision-dataset` | P1 | medium | dataset-foundry | 构造步骤级正确性、工具选择、检查点和错误恢复标签。 |
| `repo-org-time-split-builder` | P0 | high | dataset-foundry | 按仓库、组织、时间、家族和 Fork 分组切分，避免相似提交跨训练与测试。 |
| `retriever-reranker-dataset` | P0 | high | dataset-foundry | 从真实有用证据、误检和困难负例构建检索与重排数据。 |
| `rlvr-environment-dataset` | P1 | medium | dataset-foundry | 把仓库、任务、镜像、测试、奖励和终止条件封装为可复现 RL 环境。 |
| `router-and-risk-dataset` | P0 | high | dataset-foundry | 构建任务分类、Skill/模型选择、复杂度、风险和人工审批标签。 |
| `secret-pii-and-sensitive-redaction` | P0 | high | dataset-foundry | 对代码、日志、Prompt、工具结果和补丁执行可验证脱敏并保留替换映射权限。 |
| `semantic-and-ast-deduplication` | P0 | high | dataset-foundry | 使用文本、AST、图和行为指纹去除复制、近重复和模板污染。 |
| `sft-dataset-builder` | P0 | high | dataset-foundry | 构建包含任务、上下文、计划、工具、补丁和验证结果的监督微调数据。 |
| `silver-promotion-gate` | P0 | high | dataset-foundry | 要求基础编译、测试、来源和权限检查通过后进入可限制使用的数据层。 |
| `task-canonicalization-and-normalization` | P1 | medium | dataset-foundry | 统一需求、错误、环境、期望结果和验收条件，减少标签噪声。 |
| `tool-trajectory-dataset` | P1 | medium | dataset-foundry | 标准化多轮工具调用、参数、环境反馈和终止状态用于 Agent 训练。 |
| `training-rights-enforcement` | P0 | high | dataset-foundry | 在数据读取、混合、训练、导出和发布阶段持续执行许可与合同限制。 |
| `verified-synthetic-data-factory` | P1 | medium | dataset-foundry | 仅保留通过解析、执行、差分、变异或证明验证的合成数据。 |
| `verifier-and-proof-dataset` | P0 | high | dataset-foundry | 构建补丁正确性、测试充分性、行为等价和证据缺口训练数据。 |

## 07-private-model-foundry

原子 Skill：**34**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `adapter-composition-and-conflict` | P1 | medium | private-model | 评估多 Adapter 组合、路由、加权、合并和能力冲突。 |
| `adapter-lifecycle-manager` | P0 | high | private-model | 管理 Adapter 训练、依赖、缓存、权限、升级、回滚、撤销和租户归属。 |
| `base-model-selection-and-license` | P0 | high | private-model | 根据代码能力、上下文、工具使用、许可证、硬件和私有部署需求选择基座。 |
| `catastrophic-forgetting-detection` | P0 | high | private-model | 在每次训练后按语言、业务线、工具、长任务和安全集检测遗忘。 |
| `code-embedding-model-training` | P0 | high | private-model | 训练面向符号、错误、API、SQL 和跨语言语义的 Embedding 模型。 |
| `code-reranker-model-training` | P0 | high | private-model | 训练针对仓库检索、版本约束和证据相关性的重排器。 |
| `continual-learning-with-replay` | P1 | medium | private-model | 通过回放、正则化和领域采样持续学习，同时保持旧能力。 |
| `differential-private-training` | P2 | research | private-model | 对确有必要的敏感训练应用差分隐私并量化效用损失。 |
| `distributed-training-checkpointing` | P0 | high | private-model | 支持 DDP/FSDP/ZeRO、并行保存、拓扑变化恢复和训练断点续跑。 |
| `domain-continued-pretraining` | P2 | research | private-model | 对稳定、授权、规模足够的领域语料执行 CPT，并监测能力迁移和遗忘。 |
| `execution-guided-repair-model` | P1 | medium | private-model | 训练利用编译、测试、日志和差分反馈进行最小修复的模型。 |
| `federated-tenant-adapter-learning` | P2 | research | private-model | 在不集中原始数据的前提下聚合租户 Adapter 更新并防止反推。 |
| `hyperparameter-and-mixture-search` | P1 | medium | private-model | 在预算约束下优化学习率、Rank、数据混合、长度和训练策略。 |
| `lora-qlora-adapter-training` | P0 | high | private-model | 以低秩 Adapter 训练业务线和租户能力，控制 Rank、目标层和量化误差。 |
| `model-card-signing-and-mlbom` | P0 | high | private-model | 生成模型卡、限制、数据摘要、依赖 BOM、签名和供应链证明。 |
| `multi-teacher-distillation` | P1 | medium | private-model | 从多个强模型和工具验证结果蒸馏稳定能力，减少单一教师偏差。 |
| `on-policy-self-distillation` | P1 | medium | private-model | 从模型自身经验证的成功与失败轨迹中进行受控自蒸馏。 |
| `outcome-reward-model-training` | P1 | medium | private-model | 训练基于最终结果和证据的奖励模型，并校准跨任务泛化。 |
| `preference-optimization-orchestrator` | P1 | medium | private-model | 支持 DPO、KTO、ORPO、SimPO 等策略并依据数据与目标选择。 |
| `process-reward-model-training` | P1 | medium | private-model | 对计划、工具选择、检查点、验证和恢复步骤进行过程级评分。 |
| `proof-critic-model-training` | P1 | medium | private-model | 训练不变量、证明义务、反例和 Evidence Contract 完整性审查。 |
| `quantization-and-accuracy-guard` | P1 | medium | private-model | 执行量化、校准和硬件适配，同时用业务评测阻止精度暗降。 |
| `repository-planner-model-training` | P1 | medium | private-model | 训练仓库理解、任务拆解、影响范围、检查点和执行 DAG 能力。 |
| `router-model-training` | P0 | high | private-model | 训练任务、Skill、模型、风险、成本和人工审批路由模型。 |
| `selective-model-unlearning` | P1 | medium | private-model | 针对撤回数据、租户退出或风险样本执行选择性遗忘并验证残留。 |
| `semantic-transformer-model-training` | P1 | medium | private-model | 训练基于 Semantic IR 的代码生成、迁移、重构和跨语言变换能力。 |
| `speculative-draft-model-training` | P2 | research | private-model | 训练低成本草稿模型并验证其与目标模型的接受率和端到端收益。 |
| `supervised-finetuning-orchestrator` | P0 | high | private-model | 执行 SFT 数据验证、模板锁定、分布式训练、Checkpoint 与离线评测。 |
| `tokenizer-adaptation-and-migration` | P2 | research | private-model | 受控扩展词表并处理 Embedding 初始化、兼容、Checkpoint 迁移和回归。 |
| `tokenizer-domain-audit` | P1 | medium | private-model | 分析代码、DSL、标识符、SQL、中文和多语言 Token 效率与分词缺陷。 |
| `training-cost-energy-estimator` | P1 | medium | private-model | 预测并核算 GPU 时、Token、存储、网络、能耗和单能力边际成本。 |
| `training-reproducibility-and-registry` | P0 | high | private-model | 记录代码、数据、容器、随机种子、依赖、硬件、指标与模型血缘。 |
| `uncertainty-calibration-abstention` | P0 | high | private-model | 校准置信度、风险阈值和拒答/升级机制，避免错误自动化。 |
| `verifier-model-training` | P0 | high | private-model | 训练补丁风险、行为等价、测试缺口、幻觉 API 和上线可接受性判断。 |

## 08-agentic-training-rl

原子 Skill：**28**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `automated-process-supervision` | P1 | medium | agentic-training | 利用规则、验证器和搜索生成步骤级正负反馈。 |
| `automatic-curriculum-scheduler` | P1 | medium | agentic-training | 按成功率、失败模式、仓库规模和能力依赖动态提升难度。 |
| `best-of-n-verifier-selection` | P1 | medium | agentic-training | 生成多条候选轨迹，通过独立验证器选择或融合最可靠方案。 |
| `cost-aware-agent-policy` | P1 | medium | agentic-training | 把 Token、工具、GPU 和 Wall-clock 预算纳入动作价值与终止决策。 |
| `dense-partial-credit-reward` | P1 | medium | agentic-training | 使用测试子集、覆盖、编译进度和不变量满足度提供稠密奖励。 |
| `environment-and-answer-leakage-audit` | P0 | high | agentic-training | 检测测试答案、未来提交、缓存、共享工作区和网络造成的评测泄漏。 |
| `environment-aware-action-masking` | P0 | high | agentic-training | 根据权限、状态、风险和依赖动态屏蔽非法或无效动作。 |
| `environment-reset-and-cleanroom` | P0 | high | agentic-training | 确保每次 Rollout 从已知状态开始，并检测跨任务状态和答案泄漏。 |
| `failure-recovery-policy-training` | P1 | medium | agentic-training | 训练诊断、回退、缩小范围、修复环境和替代路径选择。 |
| `grader-ensemble-and-disagreement` | P1 | medium | agentic-training | 融合确定性检查、多个 Verifier 和人工标签，并利用分歧发现薄弱样本。 |
| `hierarchical-and-subagent-planning` | P2 | research | agentic-training | 训练任务分层、子 Agent 委派、结果汇总、冲突处理和预算分配。 |
| `multi-objective-reward-contract` | P0 | high | agentic-training | 组合功能、等价、安全、证据、维护性、最小改动、时间和成本奖励。 |
| `offline-trajectory-policy-learning` | P1 | medium | agentic-training | 从已验证历史轨迹学习，避免直接在生产环境探索。 |
| `pause-resume-cancel-idempotency-training` | P0 | high | agentic-training | 让 Agent 在中断和重复请求下保持状态一致、无重复副作用。 |
| `planner-executor-policy-training` | P1 | medium | agentic-training | 训练计划模型与执行模型分工、重规划条件和证据交接。 |
| `repository-training-environment` | P0 | high | agentic-training | 把仓库、构建工具、依赖、服务、数据和测试封装为可重置训练环境。 |
| `reward-hacking-and-shortcut-detection` | P0 | high | agentic-training | 识别删除测试、硬编码答案、扩大权限、绕过验证和污染环境等投机行为。 |
| `rl-algorithm-abstraction` | P2 | research | agentic-training | 支持 GRPO、RLOO、PPO、离线 RL 等算法并保持环境与奖励接口稳定。 |
| `rlvr-code-agent-training` | P1 | medium | agentic-training | 使用可执行测试、差分和证明信号进行可验证奖励强化学习。 |
| `safety-constrained-agent-learning` | P0 | high | agentic-training | 把工具权限、审批、数据边界和禁止动作作为不可被奖励抵消的硬约束。 |
| `sandbox-image-and-fixture-builder` | P0 | high | agentic-training | 构建固定工具链镜像、种子数据、外部服务模拟和网络策略。 |
| `self-play-task-and-test-generation` | P2 | research | agentic-training | 让任务生成器、Coder 和 Tester 协同产生更难且可验证的课程。 |
| `shadow-online-learning` | P2 | research | agentic-training | 在影子环境收集新分布经验，完成离线认证后再更新生产策略。 |
| `task-mutation-and-adversarial-env` | P1 | medium | agentic-training | 变异需求、依赖、配置、数据和故障，训练鲁棒性和泛化。 |
| `terminal-state-independent-verification` | P0 | high | agentic-training | 由独立执行器验证最终仓库状态，禁止模型自报成功作为奖励。 |
| `test-time-search-and-tree-exploration` | P2 | research | agentic-training | 受预算控制地执行分支搜索、回溯和候选修复。 |
| `tool-selection-and-argument-policy` | P1 | medium | agentic-training | 分别优化工具选择与参数生成，并以 Schema 和权限进行动作约束。 |
| `tool-use-supervised-training` | P1 | medium | agentic-training | 训练何时读取、搜索、编辑、编译、测试、查询和请求审批。 |

## 09-evaluation-proof-certification

原子 Skill：**36**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-abi-and-schema-compatibility` | P0 | high | evaluation-certification | 验证 API、ABI、消息、序列化、数据库 Schema 和迁移兼容性。 |
| `benchmark-and-baseline-registry` | P0 | high | evaluation-certification | 管理内部、外部、冻结、实时和客户基准及其可比条件。 |
| `compile-test-and-runtime-verification` | P0 | high | evaluation-certification | 执行构建、单测、集成、端到端、契约、部署和真实运行检查。 |
| `concurrency-correctness-testing` | P0 | high | evaluation-certification | 检测竞态、死锁、丢失更新、顺序性、可见性和资源泄漏。 |
| `cost-latency-and-soak-evaluation` | P0 | high | evaluation-certification | 评估长任务 Wall-clock、Token、工具成本、并发、稳定性和资源泄漏。 |
| `counterexample-guided-repair` | P1 | medium | evaluation-certification | 把验证器产生的最小反例反馈给修复模型并限制修改范围。 |
| `deterministic-grader-framework` | P0 | high | evaluation-certification | 优先使用 Schema、编译、测试、静态分析、差分和策略规则评分。 |
| `differential-testing` | P0 | high | evaluation-certification | 对源系统与目标系统、旧版本与新版本执行同输入差分。 |
| `distribution-shift-robustness` | P1 | medium | evaluation-certification | 覆盖新框架、新版本、新仓库家族、长尾错误和超大仓库。 |
| `e0-e5-certification-engine` | P0 | high | evaluation-certification | 把来源、单测、集成、影子、金丝雀和长期运行证据映射为 E0-E5。 |
| `evaluation-contract-and-scorecard` | P0 | high | evaluation-certification | 在实现前定义必须通过的结果、过程、风格、效率、安全和证据指标。 |
| `evidence-aggregation-and-completeness` | P0 | high | evaluation-certification | 聚合所有检查、日志、哈希、审批和未决风险，验证 Evidence Contract。 |
| `false-positive-test-detection` | P0 | high | evaluation-certification | 识别测试本身错误、环境偶然通过、污染和实现硬编码。 |
| `formal-invariant-synthesis` | P1 | medium | evaluation-certification | 从契约、代码、测试和领域规则生成候选不变量并由人或工具确认。 |
| `human-acceptance-and-edit-distance` | P1 | medium | evaluation-certification | 量化专家接受率、人工改动原因、复核时间和信任边界。 |
| `knowledge-retrieval-quality-metrics` | P0 | high | evaluation-certification | 测量 Recall@K、MRR、引用准确率、版本正确率和有用上下文比例。 |
| `live-benchmark-refresh` | P1 | medium | evaluation-certification | 持续引入时间上晚于训练集的新任务，并保持隔离与可重复性。 |
| `metamorphic-testing` | P1 | medium | evaluation-certification | 在缺少标准答案时利用输入变换与不变量验证输出关系。 |
| `model-skill-ablation-analysis` | P0 | high | evaluation-certification | 分离模型、Skill、检索、工具和训练改动对结果的贡献。 |
| `multi-grader-consensus` | P1 | medium | evaluation-certification | 对高风险结论使用多模型、规则和人工共识，保留分歧。 |
| `mutation-testing-and-test-adequacy` | P0 | high | evaluation-certification | 通过注入缺陷评估测试是否真能阻止错误实现通过。 |
| `performance-regression-certification` | P0 | high | evaluation-certification | 在可比环境中验证吞吐、延迟、内存、SQL、启动和资源成本。 |
| `production-promotion-gate` | P0 | high | evaluation-certification | 只有所有硬门通过、风险接受和回滚演练完成后才允许生产发布。 |
| `prompt-injection-and-data-leakage-eval` | P0 | high | evaluation-certification | 测试直接/间接注入、工具越权、记忆污染、训练数据和跨租户泄漏。 |
| `proof-obligation-generator` | P1 | medium | evaluation-certification | 按变换类型生成覆盖路由、类型、事务、安全和数据的证明义务。 |
| `property-based-and-fuzz-testing` | P1 | medium | evaluation-certification | 从类型、约束和协议生成边界、随机与恶意输入。 |
| `release-regression-bisect` | P0 | high | evaluation-certification | 在模型、Skill、知识、工具和策略组合中自动定位回归来源。 |
| `rubric-grader-and-calibration` | P1 | medium | evaluation-certification | 对难以确定性判断的质量维度使用标尺评分并定期校准偏差。 |
| `security-regression-certification` | P0 | high | evaluation-certification | 验证权限不扩大、输入处理、依赖、秘密、注入和供应链安全。 |
| `semantic-behavior-equivalence` | P0 | high | evaluation-certification | 基于输入输出、状态、异常、副作用、顺序和性能边界验证行为等价。 |
| `shadow-canary-production-evaluation` | P0 | high | evaluation-certification | 在影子和金丝雀流量中对比质量、成本、失败和回滚信号。 |
| `skill-activation-quality-metrics` | P0 | high | evaluation-certification | 测量触发 Precision、Recall、误触发成本和关键漏触发。 |
| `smt-and-model-checking-adapter` | P1 | medium | evaluation-certification | 把可表达约束交给 SMT、模型检查器或符号执行工具。 |
| `theorem-prover-integration` | P2 | research | evaluation-certification | 为关键算法和转换规则生成 Lean/Coq/Isabelle 等证明接口与证据。 |
| `transaction-and-data-equivalence` | P0 | high | evaluation-certification | 验证事务边界、隔离、锁、回滚、幂等和最终数据一致性。 |
| `uncertainty-and-abstention-evaluation` | P0 | high | evaluation-certification | 评估置信度校准、拒绝率、升级质量和高风险漏报。 |

## 10-serving-routing-inference

原子 Skill：**28**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `admission-control-and-priority` | P0 | high | model-serving | 按并发上限、账户余额、任务优先级、GPU 和截止时间控制入场。 |
| `airgapped-and-private-serving` | P0 | high | model-serving | 支持离线镜像、私有 Registry、无外网依赖、更新包和本地审计。 |
| `capacity-and-warm-pool-planning` | P1 | medium | model-serving | 预测峰值、冷启动和 Adapter 热度，维护合理 Warm Pool。 |
| `complexity-risk-cost-latency-routing` | P0 | high | model-serving | 在质量、风险、成本和延迟的 Pareto 约束下动态路由。 |
| `context-window-and-compaction-manager` | P0 | high | model-serving | 管理上下文预算、压缩、恢复锚点和 Skill/证据保护。 |
| `continuous-batching-and-speculation` | P1 | medium | model-serving | 优化批处理、Prefill、Decode 和投机解码，并用质量门保护。 |
| `deadline-timeout-propagation` | P0 | high | model-serving | 把任务和节点截止时间贯穿模型、工具、队列和子 Agent。 |
| `edge-and-resource-constrained-serving` | P1 | medium | model-serving | 对小模型、量化、CPU/NPU 和边缘设备进行适配与能力降级。 |
| `fallback-retry-circuit-breaker` | P0 | high | model-serving | 区分可重试、不可重试和副作用操作，执行退避、降级与熔断。 |
| `gpu-scheduling-and-autoscaling` | P0 | high | model-serving | 根据模型、上下文、Adapter、显存、队列和 SLA 调度 GPU。 |
| `health-warmup-and-readiness` | P0 | high | model-serving | 验证权重、Tokenizer、Adapter、依赖、显存和基准请求后才进入流量。 |
| `inference-graph-orchestration` | P1 | medium | model-serving | 支持 Router、Sequence、Ensemble、Verifier 和 Fallback 的推理图。 |
| `model-at-rest-and-in-use-protection` | P0 | high | model-serving | 保护模型、Adapter、KV Cache、Prompt 和中间产物的存储与传输。 |
| `model-inference-gateway` | P0 | high | model-serving | 统一鉴权、路由、配额、内容策略、观测和供应商兼容接口。 |
| `model-provider-abstraction` | P0 | high | model-serving | 隔离 OpenAI、Anthropic、开源模型、私有服务和未来推理引擎差异。 |
| `model-version-pinning-determinism` | P0 | high | model-serving | 将请求绑定到明确发布组合并提供可复现实验模式。 |
| `multi-model-skill-aware-router` | P0 | high | model-serving | 根据任务、Skill、语言、风险、上下文和历史表现选择模型组合。 |
| `prefix-kv-cache-and-isolation` | P1 | medium | model-serving | 利用 Prefix/KV Cache 降低成本，同时防止租户和权限上下文串用。 |
| `quality-aware-cache-reuse` | P1 | medium | model-serving | 仅在任务语义、权限、版本和证据相容时复用响应或中间结果。 |
| `secure-adapter-cache-and-loading` | P0 | high | model-serving | 验证签名、来源、租户和哈希后加载 Adapter，并隔离缓存。 |
| `serving-compatibility-gateway` | P0 | high | model-serving | 在 API、Tokenizer、模板、工具 Schema 和 Adapter 变更时执行兼容转换。 |
| `serving-incident-rollback` | P0 | high | model-serving | 在泄漏、回归、成本异常或模型失效时自动隔离并恢复已知良好组合。 |
| `shadow-canary-ab-and-rollback` | P0 | high | model-serving | 执行影子、流量拆分、自动门控和发布组合整体回滚。 |
| `streaming-and-durable-long-task` | P0 | high | model-serving | 支持流式反馈、异步节点、检查点、暂停、恢复、取消和断电恢复。 |
| `structured-output-enforcement` | P0 | high | model-serving | 使用 JSON Schema、语法约束和修复策略保证输出可被程序消费。 |
| `tenant-adapter-resolver` | P0 | high | model-serving | 只解析当前租户授权且与基座、任务和版本兼容的 Adapter。 |
| `tool-call-schema-and-policy-check` | P0 | high | model-serving | 在执行前验证工具名、参数、权限、审批和幂等键。 |
| `usage-metering-and-slo` | P0 | high | model-serving | 记录 Token、缓存、GPU、工具、延迟、错误和可用性并计算 SLA。 |

## 11-security-privacy-compliance

原子 Skill：**36**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `agentic-redteam-automation` | P0 | high | security-privacy | 覆盖目标劫持、工具滥用、权限滥用、记忆污染、级联失败和 Rogue Agent。 |
| `ai-ml-bom-and-model-provenance` | P0 | high | security-privacy | 记录模型、数据集、训练方法、框架、Adapter 和部署依赖。 |
| `artifact-signing-and-verification` | P0 | high | security-privacy | 对 Skill、模型、Adapter、数据集、镜像和证据签名并在使用前验证。 |
| `china-ai-data-compliance-profile` | P0 | high | security-privacy | 维护中国网络、数据、个人信息、生成式 AI 备案/登记和标识要求映射。 |
| `confidential-workload-attestation` | P1 | medium | security-privacy | 在需要时验证训练和推理环境、镜像和硬件可信状态。 |
| `consent-purpose-and-secondary-use` | P0 | high | security-privacy | 验证收集目的、训练用途、跨租户聚合和二次使用是否获得授权。 |
| `cross-border-transfer-control` | P0 | high | security-privacy | 对跨境数据、模型更新、日志和支持访问执行规则与审批。 |
| `data-residency-retention-deletion` | P0 | high | security-privacy | 按地域、合同、用途和保留期控制数据位置、归档和删除。 |
| `dependency-vulnerability-and-sbom` | P0 | high | security-privacy | 生成 SBOM、扫描漏洞、评估可利用性并绑定修复证据。 |
| `direct-indirect-prompt-injection-defense` | P0 | high | security-privacy | 区分数据与指令，标记来源、降低权限并验证高风险操作意图。 |
| `environment-owned-authority` | P0 | high | security-privacy | 权限归属于实际执行环境而非 Thread 全局状态，恢复后仍保持原始边界。 |
| `eu-ai-act-readiness-profile` | P1 | medium | security-privacy | 按产品角色和风险场景维护透明度、文档、监控和事件响应准备度。 |
| `generated-code-secret-license-scan` | P0 | high | security-privacy | 对生成代码、配置、依赖和文档执行秘密、许可证与版权检查。 |
| `human-approval-and-breakglass` | P0 | high | security-privacy | 对高风险操作执行审批、双人复核、时限授权和事后审计。 |
| `iso42001-ai-management-profile` | P0 | high | security-privacy | 建立 AI 管理体系所需的职责、风险、数据、监控和持续改进证据。 |
| `least-privilege-tool-authorization` | P0 | high | security-privacy | 按任务、Environment、Attachment 和 Skill 精确授予工具与参数权限。 |
| `legal-hold-and-evidence-preservation` | P1 | medium | security-privacy | 在争议或调查期间冻结相关版本、日志、数据和证据链。 |
| `memory-knowledge-poisoning-detection` | P0 | high | security-privacy | 识别恶意知识、持久化指令、错误高置信记录和跨任务污染。 |
| `model-extraction-membership-audit` | P1 | medium | security-privacy | 评估模型抽取、成员推断和训练数据记忆风险。 |
| `nist-ai-rmf-control-profile` | P0 | high | security-privacy | 将 Govern、Map、Measure、Manage 映射到 Elmos 控制与证据。 |
| `personal-data-rights-operations` | P0 | high | security-privacy | 支持访问、更正、导出、删除、限制处理和影响范围定位。 |
| `policy-as-code-enforcement` | P0 | high | security-privacy | 在 CI、运行时、训练和部署阶段统一执行可测试策略。 |
| `policy-simulation-and-impact` | P1 | medium | security-privacy | 在发布策略前模拟允许/拒绝变化、误伤率和权限爆炸半径。 |
| `privacy-preserving-federated-learning` | P1 | medium | security-privacy | 为联邦 Adapter 学习增加安全聚合、更新裁剪和异常客户端检测。 |
| `sandbox-filesystem-network-isolation` | P0 | high | security-privacy | 限制文件路径、系统调用、进程、设备、网络出口、DNS 和凭据。 |
| `secret-broker-kms-and-key-isolation` | P0 | high | security-privacy | 不向模型暴露长期密钥，按租户和任务签发短期凭据并轮换。 |
| `security-disaster-recovery` | P0 | high | security-privacy | 验证密钥、Registry、模型、知识、任务状态和审计系统的恢复能力。 |
| `security-incident-response-and-forensics` | P0 | high | security-privacy | 检测、隔离、回滚、保全证据、通知和复盘 AI/Agent 安全事件。 |
| `soc2-iso27001-evidence-profile` | P1 | medium | security-privacy | 复用身份、变更、访问、备份、监控和事件证据支持企业审计。 |
| `tamper-evident-audit-log` | P0 | high | security-privacy | 记录不可抵赖的身份、决策、工具、数据、训练、发布和审批事件。 |
| `tenant-key-and-cache-isolation` | P0 | high | security-privacy | 确保对象、向量、缓存、Adapter、Checkpoint 和备份按租户隔离。 |
| `tool-and-mcp-supply-chain-trust` | P0 | high | security-privacy | 校验第三方 Tool/MCP 的来源、权限、更新、依赖和返回内容。 |
| `training-data-exfiltration-defense` | P0 | high | security-privacy | 阻止 Prompt、日志、Trace、Adapter 和输出泄露训练或客户数据。 |
| `training-data-poisoning-and-backdoor-scan` | P0 | high | security-privacy | 检测异常模式、触发器、标签投毒、来源集中和行为后门。 |
| `workspace-attachment-ownership-fencing` | P0 | high | security-privacy | 为远程 Executor、Workspace、挂载和产物建立所有权与 Fencing Token。 |
| `zero-trust-user-workload-identity` | P0 | high | security-privacy | 对用户、Agent、服务、工具、训练作业和部署实例实施可验证身份。 |

## 12-observability-lineage-finops

原子 Skill：**28**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `adapter-reward-evaluator-drift` | P1 | medium | observability-finops | 监控租户 Adapter、奖励函数和模型裁判随时间的偏移。 |
| `anomaly-detection-and-root-cause` | P0 | high | observability-finops | 关联发布、流量、数据、依赖、模型和环境变化定位异常。 |
| `audit-and-customer-evidence-export` | P0 | high | observability-finops | 导出脱敏 Trace、证据、SLO、数据血缘和认证报告。 |
| `budget-guard-and-auto-throttle` | P0 | high | observability-finops | 在账户、任务、模型和 GPU 预算接近阈值时降级、暂停或审批。 |
| `cache-retrieval-skill-effectiveness` | P1 | medium | observability-finops | 评估缓存命中质量、检索贡献、Skill 增益和无效激活。 |
| `chargeback-showback-and-billing-feed` | P0 | high | observability-finops | 向计费系统输出可对账的用量、折扣、退款和成本明细。 |
| `cost-capacity-and-margin-forecast` | P1 | medium | observability-finops | 预测成本、容量、队列、收入、毛利和扩容需求。 |
| `elmos-trace-semantic-schema` | P0 | high | observability-finops | 定义 Task、Turn、Environment、Skill、Knowledge、Model、Evidence 和 Cost 属性。 |
| `failure-probability-and-risk-forecast` | P1 | medium | observability-finops | 预测任务节点失败、超预算、需人工和无法认证的概率。 |
| `genai-opentelemetry-instrumentation` | P0 | high | observability-finops | 为模型、Agent、Tool、MCP、检索和记忆输出统一 Trace、Metric 和 Event。 |
| `logs-metrics-traces-correlation` | P0 | high | observability-finops | 使用统一 ID 关联任务、模型、工具、仓库、部署和客户问题。 |
| `memory-and-experience-trace` | P1 | medium | observability-finops | 记录读写、压缩、遗忘、迁移、价值评分和污染决策。 |
| `model-data-knowledge-drift` | P0 | high | observability-finops | 监控输入、输出、失败、知识时效、数据分布和能力指标漂移。 |
| `model-invocation-observability` | P0 | high | observability-finops | 记录模型版本、参数、Token、缓存、TTFT、Prefill、Decode、重试和结果。 |
| `observability-schema-versioning` | P1 | medium | observability-finops | 管理遥测 Schema 演进、采集端兼容和历史查询迁移。 |
| `openlineage-compatible-emission` | P0 | high | observability-finops | 以 Dataset、Job、Run 和 Facet 表达数据与模型流水线血缘。 |
| `quality-cost-pareto-analysis` | P1 | medium | observability-finops | 比较模型、Skill、缓存和验证策略的质量—成本—时间前沿。 |
| `quality-slo-and-business-dashboard` | P0 | high | observability-finops | 统一展示正确性、认证、延迟、可用性、成本、收入和毛利。 |
| `retrieval-and-context-trace` | P0 | high | observability-finops | 记录查询、候选、分数、过滤、引用、上下文预算和缓存命中。 |
| `sensitive-content-capture-policy` | P0 | high | observability-finops | 默认不采集 Prompt、代码和工具内容，按明确授权进行过滤、截断或加密采集。 |
| `skill-activation-and-workflow-trace` | P0 | high | observability-finops | 记录 Skill 候选、选择理由、版本、节点、审批、失败和回滚。 |
| `task-and-training-run-replay` | P0 | high | observability-finops | 从 Trace、快照和发布组合重放任务或训练运行。 |
| `task-tenant-project-cost-attribution` | P0 | high | observability-finops | 把成本精确归属到任务、用户、项目、业务线、模型和 Skill。 |
| `telemetry-loss-and-integrity-monitor` | P0 | high | observability-finops | 检测丢失、重复、乱序、篡改和采样偏差，避免错误运营结论。 |
| `token-gpu-storage-network-accounting` | P0 | high | observability-finops | 核算输入输出 Token、缓存、GPU 秒、存储、网络和第三方工具费用。 |
| `tool-call-and-side-effect-trace` | P0 | high | observability-finops | 记录工具输入、结果、权限、幂等键、资源、环境和副作用。 |
| `training-run-and-checkpoint-trace` | P0 | high | observability-finops | 记录数据版本、代码、镜像、硬件、超参、Checkpoint、失败和恢复。 |
| `wall-clock-eta-and-progress-model` | P0 | high | observability-finops | 基于仓库规模、历史节点、队列和失败概率预测机器执行 ETA 与进度。 |

## 13-commercial-multitenant-platform

原子 Skill：**24**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `admin-audit-and-policy-console` | P0 | high | commercial-platform | 提供租户、权限、用量、模型、Skill、知识、风险和审计统一控制台。 |
| `commercial-margin-and-unit-economics` | P0 | high | commercial-platform | 计算单任务、单租户、业务线和模型组合的收入、成本与毛利。 |
| `credit-wallet-and-reservation` | P0 | high | commercial-platform | 在长任务开始前预留余额，按实际用量结算、释放和处理超额。 |
| `customer-acceptance-report` | P0 | high | commercial-platform | 输出需求覆盖、测试、证据、未决风险、环境和交付物清单。 |
| `customer-specific-policy-pack` | P1 | medium | commercial-platform | 把客户编码规范、安全、数据和上线要求封装为版本化策略包。 |
| `customer-success-quality-signals` | P1 | medium | commercial-platform | 识别采用、失败、复核负担、节省时间和续费风险，但不越权采集内容。 |
| `data-sharing-optin-and-reward` | P0 | high | commercial-platform | 让客户选择是否贡献匿名经验，并记录回报、范围和撤回。 |
| `feature-entitlement-and-license` | P0 | high | commercial-platform | 按套餐、合同、地区、私有部署和试用授予模型、Skill、并发和认证能力。 |
| `feature-flag-and-safe-release` | P0 | high | commercial-platform | 按租户、业务线、风险和版本逐步开放能力并快速关闭。 |
| `invoice-and-cost-evidence` | P0 | high | commercial-platform | 生成可审计的账单明细、成本归因、税务字段和客户异议证据。 |
| `partner-and-professional-services-handoff` | P1 | medium | commercial-platform | 把项目规则、知识、Skill、验收和运营责任标准化交接。 |
| `private-airgap-deployment-packager` | P0 | high | commercial-platform | 生成镜像、模型、Skill、知识、许可证、更新、备份和 Runbook 离线包。 |
| `quota-concurrency-and-fairness` | P0 | high | commercial-platform | 执行每账户并发、队列、公平调度、优先级和资源上限。 |
| `skill-pack-marketplace-governance` | P1 | medium | commercial-platform | 管理内部、合作伙伴和客户 Skill 包的签名、定价、权限和责任。 |
| `sla-slo-and-service-credit` | P0 | high | commercial-platform | 把可用性、完成时间、恢复、数据丢失和质量承诺绑定补偿规则。 |
| `subscription-and-project-pricing` | P0 | high | commercial-platform | 支持订阅、Usage Credit、按项目、按仓库规模和混合计费。 |
| `support-diagnostic-bundle` | P0 | high | commercial-platform | 在不泄露客户秘密的前提下导出版本、Trace、错误、依赖和健康信息。 |
| `supportability-and-lts-policy` | P0 | high | commercial-platform | 定义长期支持版本、补丁、升级路径、停服通知和安全修复承诺。 |
| `tenant-adapter-commercial-lifecycle` | P1 | medium | commercial-platform | 管理租户 Adapter 的训练授权、成本、部署、升级、归属和退出。 |
| `tenant-export-delete-and-offboarding` | P0 | high | commercial-platform | 完整导出客户资产、吊销访问、删除数据并提供完成证明。 |
| `tenant-knowledge-pack-lifecycle` | P1 | medium | commercial-platform | 支持客户知识包的导入、更新、验证、冻结、导出和删除。 |
| `tenant-org-project-repo-hierarchy` | P0 | high | commercial-platform | 管理组织、租户、工作区、项目、仓库、分支、环境和成员关系。 |
| `tenant-region-migration` | P1 | medium | commercial-platform | 在保持身份、加密、血缘和停机目标下迁移区域或私有环境。 |
| `usage-billing-reconciliation` | P0 | high | commercial-platform | 对模型、GPU、工具和退款事件去重、汇总并与供应商账单对账。 |

## 14-human-governance-operations

原子 Skill：**20**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `annotation-and-comparison-workbench` | P0 | high | human-governance | 支持轨迹、补丁、证据、偏好对和失败类型的高效标注。 |
| `audit-readiness-package` | P0 | high | human-governance | 按审计目标组织政策、证据、抽样、变更、访问和事件材料。 |
| `change-advisory-and-model-risk-board` | P1 | medium | human-governance | 对高风险模型、训练和生产变更执行跨职能评审。 |
| `decision-trace-and-accountability` | P0 | high | human-governance | 记录谁在何时基于什么证据批准、拒绝、豁免或回滚。 |
| `disagreement-adjudication` | P0 | high | human-governance | 对模型、规则和专家分歧执行二审、仲裁和决策依据沉淀。 |
| `escalation-sla-reversibility-transparency` | P0 | high | human-governance | 定义升级时限、人工接管、撤销路径和对用户透明的信息。 |
| `evidence-explanation-ui` | P0 | high | human-governance | 以代码位置、差分、测试、反例、风险和来源展示结论。 |
| `expert-review-routing` | P0 | high | human-governance | 按语言、框架、数据库、安全、业务和风险把问题分配给合适专家。 |
| `feedback-manipulation-defense` | P0 | high | human-governance | 检测恶意评分、刷样本、利益冲突和低质量反馈进入训练。 |
| `human-edit-causal-attribution` | P1 | medium | human-governance | 判断人工修改是修错、补需求、偏好、环境差异还是格式调整。 |
| `human-feedback-capture-and-lineage` | P0 | high | human-governance | 记录反馈来源、范围、版本、意图、置信度和后续使用。 |
| `human-overreliance-and-automation-bias` | P1 | medium | human-governance | 通过界面、抽检和培训降低对模型分数和自动证据的盲从。 |
| `incident-command-and-communications` | P0 | high | human-governance | 明确事件指挥、技术处置、客户沟通、法律和复盘职责。 |
| `knowledge-data-model-stewardship` | P0 | high | human-governance | 建立知识 Steward、数据 Owner、模型 Owner 和 Skill Maintainer 制度。 |
| `raci-and-asset-ownership` | P0 | high | human-governance | 为知识、Skill、数据集、模型、策略、发布和事件明确 RACI。 |
| `redteam-blueteam-learning-loop` | P1 | medium | human-governance | 将攻击发现、修复、验证和新测试纳入持续改进。 |
| `reviewer-calibration-and-gold-check` | P0 | high | human-governance | 通过标准样本、盲测和一致性指标校准审阅质量。 |
| `risk-based-human-approval-gates` | P0 | high | human-governance | 根据副作用、客户级别、证据缺口和不确定性决定人工门。 |
| `training-consent-operations` | P0 | high | human-governance | 让租户和数据 Owner 管理训练授权、范围、期限和撤回。 |
| `waiver-exception-and-expiry` | P0 | high | human-governance | 允许受控例外，但必须包含理由、补偿控制、期限和复审。 |

## 15-domain-engineering-packs

原子 Skill：**37**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `automated-test-gap-generation-repair` | P0 | high | test-quality-certification | 分析测试缺口，生成并执行功能、性能、UI、压力、安全和变异测试。 |
| `cross-language-api-serialization-contract` | P0 | high | cross-language-conversion | 保持 API、RPC、Schema、序列化、精度和兼容性。 |
| `cross-language-build-ffi-native-integration` | P1 | medium | cross-language-conversion | 迁移依赖、构建、C ABI、Native 库、平台能力和发布。 |
| `cross-language-concurrency-memory-model` | P0 | high | cross-language-conversion | 映射线程、协程、Actor、锁、原子性、所有权和内存可见性。 |
| `cross-language-control-error-equivalence` | P0 | high | cross-language-conversion | 保持控制流、异常、资源释放、取消和错误传播。 |
| `cross-language-framework-data-access` | P0 | high | cross-language-conversion | 映射 Web、DI、ORM、缓存、消息、事务和配置框架。 |
| `cross-language-repository-equivalence` | P0 | high | cross-language-conversion | 通过可执行测试、差分、性能和语义覆盖认证整库转换。 |
| `cross-language-semantic-ir-compiler` | P0 | high | cross-language-conversion | 把源语言解析为统一语义并按目标语言约束重新生成。 |
| `cross-language-type-and-nullability-mapping` | P0 | high | cross-language-conversion | 处理数值、泛型、集合、Null、枚举、时间和领域值类型。 |
| `domain-proof-and-certification-pack` | P0 | high | evaluation-certification | 为每条业务线维护专用不变量、反例、证据模板和 E0-E5 门。 |
| `frontend-component-state-semantic-ir` | P0 | high | frontend-mobile-miniapp | 抽取组件、Props、状态、响应式、生命周期、样式和可复用逻辑。 |
| `frontend-navigation-form-network-auth` | P0 | high | frontend-mobile-miniapp | 迁移路由、表单、校验、请求、缓存、认证和权限。 |
| `frontend-platform-api-and-miniapp-targets` | P0 | high | frontend-mobile-miniapp | 适配微信、支付宝、抖音、小红书小程序及平台权限和限制。 |
| `frontend-visual-accessibility-differential` | P0 | high | frontend-mobile-miniapp | 执行截图、交互、布局、主题、响应式和无障碍差分。 |
| `project-requirement-to-architecture` | P0 | high | project-generation | 从需求生成边界、模块、ADR、数据流、部署和非功能约束。 |
| `project-schema-api-module-generation` | P0 | high | project-generation | 联合生成数据库、API、事件、模块、代码和契约测试。 |
| `project-security-observability-foundation` | P0 | high | project-generation | 默认生成身份、权限、审计、秘密、Trace、Metric 和健康检查。 |
| `project-test-deploy-doc-certification` | P0 | high | project-generation | 生成测试、CI/CD、IaC、Runbook、架构文档和生产认证材料。 |
| `spring-build-dependency-boot4-modernization` | P0 | high | spring-modernization | 升级构建、依赖、Jakarta 命名空间、容器和 Spring Boot 4 配置。 |
| `spring-filter-interceptor-listener-migration` | P0 | high | spring-modernization | 迁移 Filter、Interceptor、Listener、生命周期和执行顺序。 |
| `spring-legacy-inventory-and-version-graph` | P0 | high | spring-modernization | 识别 Struts、Servlet、Spring、JSP、依赖、容器、Java 版本和混合技术栈。 |
| `spring-messaging-batch-scheduling-migration` | P1 | medium | spring-modernization | 迁移消息、定时、批处理、重试、幂等和死信行为。 |
| `spring-route-request-binding-migration` | P0 | high | spring-modernization | 迁移路由、HTTP 方法、参数绑定、上传、编码、Locale 和响应语义。 |
| `spring-security-equivalence` | P0 | high | spring-modernization | 保持认证、授权、CSRF、Session Fixation、密码和方法级安全。 |
| `spring-session-state-migration` | P0 | high | spring-modernization | 保持 Session、Cookie、Flash、并发访问、失效和序列化行为。 |
| `spring-shadow-differential-golden-route` | P0 | high | spring-modernization | 通过影子流量、差分、回滚和真实大型仓库形成可付费 Golden Route。 |
| `spring-transaction-persistence-migration` | P0 | high | spring-modernization | 迁移 JDBC、Hibernate、MyBatis、事务传播、锁和 Lazy 语义。 |
| `spring-validation-exception-migration` | P0 | high | spring-modernization | 迁移校验、错误码、消息、异常映射、状态码和事务回滚规则。 |
| `spring-view-template-migration` | P0 | high | spring-modernization | 迁移 JSP、Taglib、Tiles、Freemarker 和视图解析及前后端契约。 |
| `sql-ddl-dml-constraint-conversion` | P0 | high | sql-database-conversion | 转换表、索引、约束、分区、序列、Identity、MERGE 和 Upsert。 |
| `sql-dialect-parser-and-semantic-ir` | P0 | high | sql-database-conversion | 解析多数据库 SQL、PL/SQL、T-SQL、PL/pgSQL 和扩展语法。 |
| `sql-json-spatial-fulltext-special-types` | P1 | medium | sql-database-conversion | 转换 JSON、数组、空间、全文、XML 和厂商专有类型。 |
| `sql-plan-performance-certification` | P0 | high | sql-database-conversion | 比较执行计划、索引、统计、锁和性能，阻止语义正确但不可用的转换。 |
| `sql-routine-control-dynamic-conversion` | P0 | high | sql-database-conversion | 转换过程、函数、包、游标、控制流、动态 SQL 和临时对象。 |
| `sql-schema-data-result-differential` | P0 | high | sql-database-conversion | 比较 Schema、数据、结果集、顺序、精度、副作用和错误。 |
| `sql-transaction-isolation-exception` | P0 | high | sql-database-conversion | 保持事务、保存点、隔离、锁、异常和错误码语义。 |
| `sql-type-function-operator-mapping` | P0 | high | sql-database-conversion | 映射类型、隐式转换、函数、运算符、Collation、时区和 Null。 |

## 16-self-evolution-release-engineering

原子 Skill：**30**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `active-data-and-transfer-planner` | P1 | medium | self-evolution-release | 选择最有信息增益的数据并判断跨语言、跨框架迁移机会。 |
| `automatic-curriculum-and-benchmark-builder` | P2 | research | self-evolution-release | 从真实失败生成分层课程和无泄漏的新基准。 |
| `automatic-eval-and-counterexample-generation` | P1 | medium | self-evolution-release | 为新缺陷自动生成回归、边界、对抗和反例测试。 |
| `autonomous-improvement-safety-budget` | P1 | medium | self-evolution-release | 限定自动演进的权限、预算、环境、数据和最大影响范围。 |
| `bandit-budget-allocation` | P2 | research | self-evolution-release | 在有限 GPU、Token 和专家时间下分配实验与数据标注预算。 |
| `capability-calibration-and-boundary` | P1 | medium | self-evolution-release | 持续更新模型和 Skill 擅长、薄弱、拒绝和人工升级边界。 |
| `capability-gap-and-unknown-mining` | P1 | medium | self-evolution-release | 从失败、人工接管、低置信、客户需求和未覆盖证据中发现能力缺口。 |
| `chaos-soak-backup-restore-certification` | P0 | high | self-evolution-release | 验证长稳、故障注入、备份、恢复、跨区和依赖失效。 |
| `deprecation-and-obsolescence-detection` | P1 | medium | self-evolution-release | 发现旧文档、旧 API、失效 Skill、弱模型和不再安全的依赖。 |
| `experiment-proposal-and-causal-analysis` | P2 | research | self-evolution-release | 自动提出消融与对照实验，估计改动的因果收益而非相关性。 |
| `external-change-impact-analysis` | P1 | medium | self-evolution-release | 判断新版本对知识、Skill、模型、评测、部署和客户承诺的影响。 |
| `external-research-and-standard-watch` | P1 | medium | self-evolution-release | 跟踪模型、Agent、训练、标准、法规和关键依赖变化。 |
| `failure-cluster-to-roadmap` | P1 | medium | self-evolution-release | 把高频或高损失败聚类转为 Skill、知识、数据、模型或工具路线项。 |
| `frontier-teacher-distillation-governance` | P1 | medium | self-evolution-release | 选择教师、验证授权、过滤错误并记录教师版本和贡献。 |
| `golden-route-production-certifier` | P0 | high | self-evolution-release | 对 Spring、SQL、跨语言和项目生成 Golden Route 形成可重复商业认证。 |
| `immutable-release-candidate-assembly` | P0 | high | self-evolution-release | 组装模型、Adapter、Skill、知识快照、策略、工具镜像和评测证据。 |
| `knowledge-to-skill-distillation` | P1 | medium | self-evolution-release | 把稳定知识规则转为可执行 Skill，同时保留引用和版本条件。 |
| `lifelong-learning-and-forgetting-control` | P2 | research | self-evolution-release | 联合管理持续学习、回放、遗忘、数据撤回和能力稳定性。 |
| `model-collapse-synthetic-ratio-monitor` | P1 | medium | self-evolution-release | 监控合成数据占比、分布收缩、错误放大和多样性丢失。 |
| `model-skill-knowledge-coevolution` | P2 | research | self-evolution-release | 评估问题应通过知识、Skill、模型或工具解决，避免盲目训练。 |
| `p0-p5-and-e0-e5-release-gates` | P0 | high | self-evolution-release | 执行构建、部署、数据、模型、Skill、影子、金丝雀和长期认证门。 |
| `quality-cost-time-pareto-promotion` | P1 | medium | self-evolution-release | 只提升在质量、风险、成本和 Wall-clock 上有明确收益的组合。 |
| `rag-skill-weight-placement-decision` | P1 | medium | self-evolution-release | 按变化频率、精确性、权限、成本和泛化性决定能力落点。 |
| `recertification-trigger-engine` | P0 | high | self-evolution-release | 在模型、数据、知识、Skill、工具、法规或环境变化时触发相应复认证。 |
| `release-shadow-canary-auto-rollback` | P0 | high | self-evolution-release | 根据硬门和实时 SLO 自动暂停、回滚或扩大流量。 |
| `reward-overoptimization-alignment-tax` | P1 | medium | self-evolution-release | 检测奖励模型过拟合、长度偏差、投机和对基础能力的损害。 |
| `self-correction-with-independent-verifier` | P1 | medium | self-evolution-release | 允许自动修复，但由独立验证器和发布门决定是否接受。 |
| `skill-gene-mutation-and-composition` | P2 | research | self-evolution-release | 在沙箱中变异触发、步骤、工具和验证组合，寻找更优 Skill。 |
| `skill-to-weight-distillation` | P2 | research | self-evolution-release | 将高频、稳定、跨仓库 Skill 轨迹蒸馏进模型并保留原 Skill 作为校验。 |
| `weight-to-skill-extraction` | P2 | research | self-evolution-release | 从模型稳定行为中提取可解释、可测试的显式 Skill。 |

## Repository Execution OS / 仓库级执行操作系统

原子 Skill：**34**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `artifact-cache-and-workspace-reuse` | P1 | high | repository-execution | 按内容哈希复用依赖、构建、分析和测试产物，并精确失效受影响部分。 |
| `attachment-owned-resource-authority` | P0 | high | repository-execution | 使仓库、附件、挂载和 MCP 资源保留各自所有者权限快照与数据边界。 |
| `build-system-and-toolchain-detection` | P0 | high | repository-execution | 自动识别多语言构建系统、编译器、运行时、包管理器、代码生成器和环境前置条件。 |
| `change-budget-and-blast-radius-control` | P0 | high | repository-execution | 约束最大文件数、符号数、API 面、数据对象和风险爆炸半径，超限必须重新规划。 |
| `commit-pr-review-bundle-generation` | P0 | high | repository-execution | 生成可审阅提交、PR 描述、变更说明、风险、测试和回滚材料。 |
| `dependency-lock-and-mirror-resolution` | P0 | high | repository-execution | 解析依赖锁、私服、镜像、离线缓存、凭据和冲突，保证依赖恢复可重复。 |
| `environment-owned-tool-authority` | P0 | high | repository-execution | 使执行权限归属于实际 Environment，恢复和切换执行器时不得继承 Thread 全局权限。 |
| `execution-os-golden-route-certification` | P0 | high | repository-execution | 对大型仓库并行执行、恢复、合并、证据和交付形成可重复的执行 OS Golden Route。 |
| `executor-failure-recovery-and-reassignment` | P0 | high | repository-execution | 检测执行器失联、过期和部分副作用，安全接管并防止双主执行。 |
| `generated-code-and-binary-boundary` | P0 | high | repository-execution | 区分源代码、生成代码、反编译内容、构建产物和二进制资源，阻止错误修改与训练污染。 |
| `git-history-branch-tag-analysis` | P1 | high | repository-execution | 分析提交、分支、标签、回滚、热点与演化路径，为影响分析和兼容窗口提供证据。 |
| `hermetic-environment-bootstrap` | P0 | high | repository-execution | 构建版本锁定、可重放、网络与权限受控的仓库执行环境。 |
| `incremental-build-test-selection` | P0 | high | repository-execution | 根据语义影响图选择最小但充分的构建、测试、扫描和验证集合。 |
| `large-repo-context-map-maintenance` | P0 | medium | repository-execution | 持续维护架构、模块、符号、调用、数据和测试地图，避免长任务上下文漂移。 |
| `long-task-checkpoint-and-resume` | P0 | high | repository-execution | 保存计划、环境、工具副作用、补丁、证据和未决项，支持断电与进程迁移恢复。 |
| `monorepo-polyrepo-topology-detection` | P0 | high | repository-execution | 识别单仓多模块、多仓协同、共享库、生成代码与发布单元，形成可执行拓扑。 |
| `multi-agent-blackboard-coordination` | P1 | high | repository-execution | 通过受控共享黑板同步事实、计划、依赖、风险和完成证据，隔离私有推理上下文。 |
| `network-disconnect-offline-continuation` | P1 | high | repository-execution | 在网络中断时使用已验证缓存和离线依赖继续安全步骤，恢复后完成对账。 |
| `parallel-change-conflict-prediction` | P1 | high | repository-execution | 在执行前预测符号、配置、Schema、测试和生成文件的并行修改冲突。 |
| `patch-order-and-dependency-planning` | P0 | high | repository-execution | 按编译依赖、Schema 迁移、API 兼容与回滚边界安排补丁顺序。 |
| `pause-resume-cancel-side-effect-safety` | P0 | critical | repository-execution | 对暂停、恢复、取消建立幂等、补偿、资源释放和不可逆动作阻断机制。 |
| `provenance-signed-patch-delivery` | P0 | high | repository-execution | 对补丁、工具、模型、Skill、知识快照和验证结果生成签名交付链。 |
| `remote-workspace-lease-and-fencing` | P0 | high | repository-execution | 为远程 Workspace 与 Executor 建立 owner、lease、heartbeat、expiry 和 fencing token。 |
| `repository-cleanup-and-secret-safe-disposal` | P0 | critical | repository-execution | 任务结束后安全清理工作区、凭据、缓存和敏感中间产物，并保留必要审计证明。 |
| `repository-intake-and-identity` | P0 | critical | repository-execution | 识别仓库、组织、分支、提交、子模块、许可证与租户作用域，生成不可歧义的执行身份。 |
| `repository-sharding-and-task-partition` | P0 | high | repository-execution | 依据依赖图、文件所有权、构建边界和冲突概率切分大型仓库任务。 |
| `repository-size-complexity-risk-profile` | P0 | medium | repository-execution | 按 LOC、符号、依赖、语言、历史、测试、动态特性和构建耗时评估规模与迁移风险。 |
| `reproducible-build-baseline` | P0 | high | repository-execution | 建立源码到制品的可重复构建基线并记录不可复现原因、环境差异和供应链证据。 |
| `semantic-file-ownership-locking` | P0 | high | repository-execution | 对文件、符号、Schema 和发布单元实施语义所有权与冲突锁，而非仅路径锁。 |
| `semantic-three-way-merge` | P0 | high | repository-execution | 结合 AST、Symbol、Semantic IR 与测试证据执行语义三方合并。 |
| `submodule-lfs-vendor-artifact-handling` | P0 | high | repository-execution | 安全处理 Git Submodule、LFS、Vendor 代码、二进制依赖和不可修改第三方边界。 |
| `task-progress-critical-path-eta` | P0 | high | repository-execution | 基于执行 DAG、历史耗时、队列、重试与失败概率报告机器 Wall-clock ETA。 |
| `workspace-snapshot-and-content-addressing` | P0 | high | repository-execution | 为工作区、输入、补丁、中间产物和检查点生成内容地址快照。 |
| `worktree-branch-patch-stack-manager` | P0 | high | repository-execution | 管理 Git Worktree、临时分支、补丁栈、原子提交和并行任务隔离。 |

## Java & Spring Enterprise Modernization / Java 企业现代化

原子 Skill：**48**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `actuator-health-metrics-tracing` | P0 | high | spring-modernization | 生成 Actuator、健康探针、Metric、Trace、日志关联和运行诊断能力。 |
| `ant-maven-gradle-build-modernization` | P0 | high | spring-modernization | 将 Ant、旧 Maven 或 Gradle 构建升级为锁定依赖、可重复、可扫描的现代构建。 |
| `api-contract-and-client-compatibility` | P0 | high | spring-modernization | 验证 OpenAPI、序列化、状态码、Header、客户端 SDK 与下游消费者兼容。 |
| `boot4-production-release-evidence` | P0 | critical | spring-modernization | 组装构建、测试、差分、安全、性能、部署、回滚和未决风险证据。 |
| `cache-provider-and-annotation-migration` | P1 | high | spring-modernization | 迁移 Ehcache、Redis、Caffeine、自定义缓存、注解、失效与一致性策略。 |
| `config-profile-secret-externalization` | P0 | critical | spring-modernization | 迁移 Properties、XML、JNDI、环境变量、Profile、Feature Flag 和秘密管理。 |
| `database-schema-migration-integration` | P0 | high | spring-modernization | 把数据库 Schema、Routine、数据回填和应用发布组织为可回滚迁移波次。 |
| `ejb-session-entity-message-bean-migration` | P1 | high | spring-modernization | 迁移 Session Bean、Entity Bean、MDB、事务、安全与容器服务。 |
| `incremental-strangler-module-cutover` | P0 | critical | spring-modernization | 按模块、路由、消费者和数据所有权实施 Strangler 迁移与渐进切流。 |
| `java-source-bytecode-version-upgrade` | P0 | high | spring-modernization | 升级源码、字节码、JDK API、编译参数、反射和序列化兼容性。 |
| `java-test-junit-mockito-testcontainers` | P0 | high | spring-modernization | 迁移 JUnit、TestNG、Mockito、PowerMock、容器测试和遗留 Characterization Test。 |
| `javaee-appserver-descriptor-migration` | P0 | high | spring-modernization | 迁移 web.xml、ejb-jar、application.xml、资源引用和厂商部署描述符。 |
| `javax-jakarta-namespace-migration` | P0 | high | spring-modernization | 完成 javax 到 jakarta 命名空间、依赖、配置、序列化和容器兼容迁移。 |
| `jaxrs-jaxws-soap-rest-modernization` | P1 | high | spring-modernization | 迁移 JAX-RS、JAX-WS、SOAP、WSDL、Handler 与 REST 或 gRPC 目标契约。 |
| `jms-kafka-rabbit-integration-migration` | P1 | high | spring-modernization | 迁移 JMS、Kafka、RabbitMQ、重试、顺序、幂等、事务和死信行为。 |
| `jsf-managed-bean-facelets-conversion` | P1 | high | spring-modernization | 迁移 JSF Managed Bean、Facelets、Navigation、Validator、Converter 和 View State。 |
| `jsp-jstl-taglib-el-conversion` | P0 | high | spring-modernization | 迁移 JSP、JSTL、自定义 Taglib、EL、页面包含、错误页和输出编码。 |
| `legacy-java-web-inventory` | P0 | medium | spring-modernization | 识别 Struts、Servlet、JSP、JSF、EJB、Spring、容器描述符、应用服务器和混合技术栈。 |
| `mybatis-jdbc-template-persistence` | P0 | high | spring-modernization | 迁移 MyBatis、iBATIS、JDBC、JdbcTemplate、RowMapper 和手写事务语义。 |
| `native-image-and-aot-readiness` | P2 | high | spring-modernization | 分析反射、代理、资源、序列化和动态加载，评估 AOT 或 Native Image 可行性。 |
| `performance-gc-thread-pool-baseline` | P0 | high | spring-modernization | 比较吞吐、延迟、GC、线程池、连接池、内存和启动性能。 |
| `rmi-corba-jndi-integration-modernization` | P1 | high | spring-modernization | 替换 RMI、CORBA、JNDI 远程对象和命名服务，同时保留调用与失败语义。 |
| `scheduler-quartz-cron-migration` | P1 | high | spring-modernization | 迁移 Timer、Quartz、Cron、集群锁、错过触发和重复执行语义。 |
| `security-regression-and-deserialization` | P0 | critical | spring-modernization | 检测认证绕过、权限扩大、反序列化、OGNL、模板和依赖漏洞回归。 |
| `servlet-container-to-embedded-runtime` | P0 | high | spring-modernization | 从外置 Tomcat 或应用服务器迁移到嵌入式运行时并保持端口、线程和部署语义。 |
| `servlet-filter-listener-async-migration` | P0 | high | spring-modernization | 迁移 Filter、Listener、AsyncContext、生命周期、线程上下文和执行顺序。 |
| `servlet-mapping-dispatch-request-wrapper` | P0 | medium | spring-modernization | 迁移 Servlet Mapping、Dispatcher、Request/Response Wrapper、编码与异步派发。 |
| `shadow-traffic-session-differential` | P0 | high | spring-modernization | 对真实或回放流量比较路由、Session、响应、数据库副作用和消息行为。 |
| `spring-batch-job-restart-migration` | P1 | high | spring-modernization | 迁移 Job、Step、Reader、Writer、Checkpoint、Restart 与批处理元数据。 |
| `spring-data-jpa-hibernate-modernization` | P0 | high | spring-modernization | 迁移 Hibernate/JPA 映射、Lazy、Cascade、Flush、Query、二级缓存和实体生命周期。 |
| `spring-integration-camel-workflow` | P1 | high | spring-modernization | 迁移 Spring Integration、Camel、ESB Route、Transformer、Splitter 和补偿流程。 |
| `spring-modernization-golden-route` | P0 | high | spring-modernization | 在多个真实大型仓库上认证可重复、可付费、可回滚的 Spring 现代化 Golden Route。 |
| `spring-mvc-webflux-target-selection` | P1 | high | spring-modernization | 依据阻塞依赖、吞吐、背压和团队约束选择 MVC、WebFlux 或混合架构。 |
| `spring-request-binding-content-negotiation` | P0 | high | spring-modernization | 保持路由、HTTP 方法、参数、文件、编码、Locale、内容协商与响应语义。 |
| `spring-security-authn-authz-equivalence` | P0 | critical | spring-modernization | 保持认证、授权、方法安全、CSRF、Session Fixation、密码策略与审计。 |
| `spring-security-oauth2-oidc-saml` | P1 | critical | spring-modernization | 迁移 OAuth2、OIDC、SAML、JWT、SSO、客户端与资源服务器配置。 |
| `spring-session-cookie-distributed-state` | P0 | high | spring-modernization | 迁移 Session、Cookie、Flash、并发访问、失效、序列化和分布式存储。 |
| `spring-xml-java-config-boot-autoconfig` | P0 | high | spring-modernization | 把 XML Bean、Java Config、Profile 和自定义工厂迁移到 Boot 自动配置与显式边界。 |
| `struts1-config-actionform-action-mapping` | P0 | medium | spring-modernization | 迁移 struts-config、Action、ActionForm、DynaActionForm、Mapping 和请求绑定语义。 |
| `struts1-forward-chain-tiles-message` | P0 | high | spring-modernization | 迁移 Forward、Action Chain、Tiles、MessageResources、Locale 与视图导航。 |
| `struts1-validation-plugin-lifecycle` | P0 | high | spring-modernization | 迁移 Validator、PlugIn、RequestProcessor、自定义生命周期和错误呈现行为。 |
| `struts2-action-value-stack-ognl` | P0 | high | spring-modernization | 迁移 Action、ValueStack、OGNL、ModelDriven、Preparable 与参数绑定并消除注入风险。 |
| `struts2-interceptor-result-conversion` | P0 | high | spring-modernization | 迁移 Interceptor Stack、Result、Namespace、Convention 与执行顺序。 |
| `struts2-validation-i18n-file-upload` | P0 | high | spring-modernization | 迁移校验、国际化、文件上传、类型转换和错误消息语义。 |
| `tiles-freemarker-thymeleaf-view-migration` | P1 | high | spring-modernization | 在 Tiles、Freemarker、Thymeleaf 或前后端分离目标之间保持视图组合与模型契约。 |
| `transaction-propagation-isolation-lock` | P0 | critical | spring-modernization | 保持事务传播、隔离、锁、只读、超时、回滚规则和跨资源一致性。 |
| `validation-exception-error-contract` | P0 | high | spring-modernization | 保持 Bean Validation、业务校验、异常映射、错误码、状态码和事务回滚。 |
| `weblogic-websphere-jboss-classloader` | P0 | high | spring-modernization | 解析 WebLogic、WebSphere、JBoss 的类加载、JNDI、事务、JMS 和安全差异。 |

## Cross-Language Repository Semantic Compiler / 跨语言整库转换

原子 Skill：**52**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-rpc-event-contract-preservation` | P0 | high | cross-language-conversion | 保持 REST、GraphQL、gRPC、事件 Schema、状态码、Header 与消费者契约。 |
| `async-await-coroutine-cancellation` | P0 | high | cross-language-conversion | 保持 Future、Promise、Task、Coroutine、取消、超时和上下文传播。 |
| `atomic-lock-memory-visibility` | P0 | high | cross-language-conversion | 保持原子操作、锁顺序、内存屏障、可见性、线性化和竞态边界。 |
| `build-package-module-system-mapping` | P0 | medium | cross-language-conversion | 转换构建图、包管理、模块系统、代码生成、版本锁与发布制品。 |
| `collection-order-mutability-equivalence` | P0 | high | cross-language-conversion | 保持列表、集合、Map、迭代顺序、相等性、可变性与并发集合行为。 |
| `control-flow-short-circuit-equivalence` | P0 | high | cross-language-conversion | 保持分支、循环、短路、模式匹配、迭代器、Generator 和 Tail Call 行为。 |
| `cpp-rust-safety-migration` | P1 | critical | cross-language-conversion | 把 C/C++ 模块迁移为 Rust，处理 ABI、内存、并发、异常和 Unsafe 边界。 |
| `cross-repo-consumer-compatibility` | P0 | high | cross-language-conversion | 验证其他仓库、SDK、脚本、数据管道和运维工具对目标系统的兼容。 |
| `csharp-go-service-conversion` | P1 | high | cross-language-conversion | 把 C# 服务迁移为 Go，处理 Task、LINQ、DI、序列化和错误模型。 |
| `date-time-timezone-calendar-equivalence` | P0 | high | cross-language-conversion | 保持日期、时间、时区、DST、Calendar、Duration、精度和序列化。 |
| `decimal-floating-rounding-equivalence` | P0 | high | cross-language-conversion | 保持 Decimal、Money、浮点、舍入模式、NaN、Infinity 与精度语义。 |
| `dependency-injection-config-mapping` | P0 | medium | cross-language-conversion | 映射 DI 容器、生命周期、配置、Profile、Feature Flag 与秘密注入。 |
| `dual-runtime-shadow-differential` | P0 | high | cross-language-conversion | 同输入驱动源目标运行时并比较输出、状态、副作用、错误和性能。 |
| `enum-algebraic-domain-type-mapping` | P0 | medium | cross-language-conversion | 映射 Enum、Union、Sealed、Algebraic Data Type 和领域值对象。 |
| `exception-error-result-propagation` | P0 | high | cross-language-conversion | 映射异常、Error、Result、Panic、Stack、过滤、重试和错误传播。 |
| `generic-variance-constraint-mapping` | P0 | medium | cross-language-conversion | 映射泛型、Variance、Trait Bound、Constraint、Erase 与 Reification。 |
| `incremental-wave-cutover-and-rollback` | P0 | critical | cross-language-conversion | 按模块和调用边界分波切换，保留双运行、流量回退和数据恢复能力。 |
| `inheritance-interface-trait-mapping` | P0 | medium | cross-language-conversion | 转换继承、接口、Trait、Mixin、默认方法、多继承和动态分派。 |
| `java-csharp-repository-conversion` | P1 | high | cross-language-conversion | 提供 Java 与 C#/.NET 整库转换的类型、异步、框架、ORM 和构建规则包。 |
| `java-go-service-conversion` | P1 | high | cross-language-conversion | 将 Java 服务迁移为 Go，处理错误、并发、DI、事务与运行时差异。 |
| `java-kotlin-modernization` | P1 | high | cross-language-conversion | 在 Java 到 Kotlin 现代化中保持空安全、协程、Bean、框架代理和互操作。 |
| `java-rust-service-conversion` | P1 | high | cross-language-conversion | 将 Java 服务迁移为 Rust，处理所有权、异步、错误、FFI 与框架差异。 |
| `javascript-typescript-hardening` | P0 | high | cross-language-conversion | 从 JavaScript 恢复类型、空值、模块和 API 契约并迁移到严格 TypeScript。 |
| `language-pair-rulepack-generation` | P0 | high | cross-language-conversion | 为任意源目标语言组合生成版本化映射规则、禁止项、降级策略与验证义务。 |
| `locale-regex-crypto-library-equivalence` | P1 | high | cross-language-conversion | 比较 Locale、Regex、Crypto、压缩和标准库边界行为。 |
| `logging-metrics-trace-context-propagation` | P0 | high | cross-language-conversion | 保持日志字段、Metric、Trace、Baggage、Correlation ID 和审计上下文。 |
| `macro-template-metaprogramming-map` | P1 | medium | cross-language-conversion | 处理宏、模板、预处理、代码生成、元类与编译期执行。 |
| `null-option-absence-semantics` | P0 | high | cross-language-conversion | 映射 Null、Optional、Option、零值、Missing、Undefined 与数据库空值。 |
| `objectivec-swift-modernization` | P1 | high | cross-language-conversion | 把 Objective-C 迁移为 Swift，保持 Runtime、KVC/KVO、ARC、UIKit 和互操作。 |
| `orm-transaction-data-access-mapping` | P0 | critical | cross-language-conversion | 映射 ORM、Query、连接池、事务、锁、Lazy、批处理和数据库错误。 |
| `os-filesystem-process-signal-semantics` | P1 | high | cross-language-conversion | 保持文件、路径、权限、进程、环境变量、Signal、Socket 和平台差异。 |
| `ownership-borrowing-gc-lifetime` | P0 | high | cross-language-conversion | 在所有权、借用、GC、引用计数和手工内存之间建立安全映射。 |
| `performance-allocation-latency-parity` | P0 | high | cross-language-conversion | 比较分配、GC、CPU、延迟、吞吐、启动和二进制体积。 |
| `php-java-service-conversion` | P1 | high | cross-language-conversion | 把 PHP 服务迁移为 Java，处理动态类型、请求生命周期、ORM 和会话语义。 |
| `primitive-numeric-overflow-equivalence` | P0 | high | cross-language-conversion | 保持整数宽度、符号、溢出、移位、比较、隐式转换和边界行为。 |
| `python-go-service-conversion` | P1 | high | cross-language-conversion | 把 Python 服务迁移为 Go，保持动态数据验证、异步、错误与部署契约。 |
| `python-rust-performance-conversion` | P1 | high | cross-language-conversion | 把 Python 性能热点迁移为 Rust 并保持数据模型、异常、扩展接口和结果精度。 |
| `reflection-metadata-annotation-mapping` | P1 | medium | cross-language-conversion | 处理反射、注解、Attribute、Decorator、运行时元数据和代码扫描。 |
| `repository-semantic-equivalence-certificate` | P0 | critical | cross-language-conversion | 聚合符号覆盖、构建、测试、差分、性能、安全、兼容和回滚证据，签发整库等价证书。 |
| `resource-lifetime-disposal-equivalence` | P0 | high | cross-language-conversion | 保持 RAII、Dispose、defer、context manager、finalizer 与资源释放顺序。 |
| `ruby-java-service-conversion` | P1 | high | cross-language-conversion | 把 Ruby 服务迁移为 Java，处理元编程、动态分派、事务和 Web 框架语义。 |
| `security-permission-crypto-equivalence` | P0 | critical | cross-language-conversion | 保持身份、权限、加密、秘密、输入验证和审计边界。 |
| `semantic-ir-loss-budget-analysis` | P0 | high | cross-language-conversion | 量化无法直接表达、需要运行时库、需要人工决策或可能改变行为的语义损失。 |
| `serialization-wire-format-compatibility` | P0 | high | cross-language-conversion | 保持 JSON、XML、Proto、Avro、二进制、字段编号、默认值和版本兼容。 |
| `source-target-language-capability-profile` | P0 | medium | cross-language-conversion | 建立源语言与目标语言在类型、运行时、并发、反射、FFI、框架和工具链上的能力画像。 |
| `static-analysis-linter-rule-migration` | P1 | high | cross-language-conversion | 迁移编译警告、Linter、Formatter、静态规则和质量门。 |
| `strangler-boundary-and-interop` | P0 | high | cross-language-conversion | 设计语言间 FFI、RPC、消息和数据边界，支持渐进替换。 |
| `string-unicode-normalization-equivalence` | P0 | high | cross-language-conversion | 保持编码、Unicode、Normalization、索引、切片、大小写和正则语义。 |
| `symbol-identity-cross-language-map` | P0 | critical | cross-language-conversion | 维护 Source Symbol、Semantic IR 与 Target Symbol 的稳定双向映射和引用位置。 |
| `test-framework-fixture-migration` | P0 | high | cross-language-conversion | 迁移测试框架、Fixture、Mock、Snapshot、Coverage 和运行选择器。 |
| `thread-actor-channel-synchronization` | P0 | high | cross-language-conversion | 映射线程、Actor、Channel、Executor、Event Loop、锁和条件变量。 |
| `unsafe-native-ffi-abi-bridge` | P1 | high | cross-language-conversion | 转换 Unsafe、Pointer、Native、C ABI、Struct Layout、Calling Convention 和 FFI。 |

## SQL & Database Modernization / 数据库语义迁移

原子 Skill：**50**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `backup-restore-point-in-time-certification` | P0 | high | sql-database-conversion | 验证备份、恢复、PITR、跨区复制、RPO/RTO 和恢复后完整性。 |
| `bulk-extract-load-backfill-planning` | P0 | high | sql-database-conversion | 规划全量抽取、并行装载、限流、校验、断点续传和回填顺序。 |
| `cdc-log-replication-capture` | P0 | high | sql-database-conversion | 配置日志级 CDC、复制槽、LSN/SCN/GTID、水位和重放恢复。 |
| `collation-charset-sort-comparison-map` | P0 | medium | sql-database-conversion | 迁移 Charset、Collation、排序、大小写、Accent 和索引比较规则。 |
| `cursor-loop-bulk-collection-conversion` | P0 | high | sql-database-conversion | 迁移 Cursor、Loop、Bulk Collect、FORALL、Set-based Rewrite 和异常行为。 |
| `data-profile-quality-rule-inference` | P0 | medium | sql-database-conversion | 分析分布、Null、唯一、关联、异常值和隐含规则，形成迁移数据契约。 |
| `data-reconciliation-checksum-sampling` | P0 | high | sql-database-conversion | 执行行数、Checksum、聚合、分层抽样、全量差分和误差解释。 |
| `database-cost-capacity-forecast` | P1 | high | sql-database-conversion | 预测存储、计算、IO、复制、许可、云资源和迁移窗口成本。 |
| `database-dialect-capability-matrix` | P0 | high | sql-database-conversion | 维护源目标数据库类型、语法、事务、索引、分区、安全与运维能力矩阵。 |
| `database-link-federation-external-table` | P1 | high | sql-database-conversion | 迁移 DB Link、Federated Query、External Table、Foreign Data Wrapper 与凭据。 |
| `database-modernization-golden-route` | P0 | high | sql-database-conversion | 对多方言、Routine、数据和零停机迁移形成可重复商业 Golden Route。 |
| `database-workload-inventory-profile` | P0 | medium | sql-database-conversion | 盘点 Schema、SQL、Routine、触发器、作业、连接、容量、锁、热点与业务关键度。 |
| `db2-sqlpl-routine-migration` | P1 | high | sql-database-conversion | 迁移 DB2 SQL PL、Package、Cursor、Condition、Compound Statement 和权限。 |
| `ddl-table-column-constraint-conversion` | P0 | high | sql-database-conversion | 转换表、列、主外键、检查、唯一、默认、注释和存储属性。 |
| `decimal-money-float-precision-map` | P0 | medium | sql-database-conversion | 保持 Numeric、Money、浮点、舍入、溢出和聚合精度。 |
| `distributed-tidb-oceanbase-compatibility` | P1 | high | sql-database-conversion | 处理 TiDB、OceanBase 等分布式数据库的兼容模式、一致性、分片和事务差异。 |
| `domestic-database-dialect-adaptation` | P1 | high | sql-database-conversion | 为国产数据库建立 Oracle、MySQL、PostgreSQL 兼容模式与专有扩展的转换规则。 |
| `dual-write-consistency-and-outbox` | P0 | critical | sql-database-conversion | 设计双写、Outbox、幂等、补偿、对账和不一致修复。 |
| `dynamic-sql-bind-identifier-safety` | P0 | critical | sql-database-conversion | 转换动态 SQL、Bind、Identifier 拼接、权限上下文并阻止注入。 |
| `exception-error-code-diagnostic-map` | P0 | medium | sql-database-conversion | 映射 SQLSTATE、厂商错误码、Warning、Exception Handler 和客户端诊断。 |
| `function-operator-expression-rewrite` | P0 | high | sql-database-conversion | 重写内置函数、运算符、隐式转换、分析函数、正则和条件表达式。 |
| `index-partition-cluster-storage-conversion` | P0 | high | sql-database-conversion | 转换索引、分区、Cluster、Tablespace、压缩、分布键和物理布局。 |
| `json-xml-array-spatial-fulltext-conversion` | P1 | high | sql-database-conversion | 转换 JSON、XML、Array、Spatial、Fulltext、Vector 与专有类型。 |
| `merge-upsert-returning-output-conversion` | P0 | high | sql-database-conversion | 保持 MERGE、UPSERT、RETURNING、OUTPUT、并发竞争和受影响行语义。 |
| `mysql-mariadb-routine-event-migration` | P1 | high | sql-database-conversion | 迁移 MySQL/MariaDB Routine、Trigger、Event、Delimiter 和 SQL Mode 行为。 |
| `null-empty-string-boolean-semantics` | P0 | high | sql-database-conversion | 保持 Null、空字符串、Boolean、三值逻辑、比较和唯一约束行为。 |
| `online-schema-change-orchestration` | P0 | high | sql-database-conversion | 组织 Expand-Contract、影子表、在线索引和兼容窗口，避免阻塞发布。 |
| `oracle-plsql-package-migration` | P0 | high | sql-database-conversion | 迁移 Oracle PL/SQL Package、Procedure、Function、Cursor、Exception 和自治事务。 |
| `orm-query-native-sql-impact-analysis` | P0 | high | sql-database-conversion | 分析 ORM Mapping、Generated SQL、Native Query、Migration 脚本和客户端驱动影响。 |
| `postgres-plpgsql-routine-modernization` | P1 | high | sql-database-conversion | 现代化 PL/pgSQL Routine、Extension、Trigger、Security Definer 与执行权限。 |
| `query-plan-cardinality-index-advisor` | P0 | high | sql-database-conversion | 比较执行计划、基数估计、统计、索引、并行度和退化风险。 |
| `referential-integrity-ordering` | P0 | high | sql-database-conversion | 按外键、循环依赖、触发器和业务约束安排迁移、禁用与重建顺序。 |
| `result-set-order-null-precision-differential` | P0 | high | sql-database-conversion | 比较结果集顺序、Null、精度、Collation、时区、错误和副作用。 |
| `routine-side-effect-differential` | P0 | high | sql-database-conversion | 比较 Routine 对表、序列、临时对象、消息、事务和错误状态的副作用。 |
| `schema-migration-versioning-generation` | P0 | high | sql-database-conversion | 生成幂等、分阶段、可回滚的 Schema Migration 与版本锁。 |
| `security-role-grant-row-policy-migration` | P0 | critical | sql-database-conversion | 迁移 User、Role、Grant、Schema 权限、Row Policy、Masking 和审计。 |
| `sequence-job-scheduler-externalization` | P1 | high | sql-database-conversion | 迁移数据库 Job、Scheduler、Queue 和定时逻辑到目标数据库或外部编排器。 |
| `sql-parser-error-recovery-extension` | P0 | high | sql-database-conversion | 对厂商扩展、混合脚本、模板 SQL 和不完整源码执行容错解析并保留不确定性。 |
| `sqlserver-tsql-routine-migration` | P0 | high | sql-database-conversion | 迁移 T-SQL Procedure、Function、Trigger、Table Variable、TRY/CATCH 和动态 SQL。 |
| `sybase-transactsql-migration` | P1 | high | sql-database-conversion | 迁移 Sybase ASE Transact-SQL、Identity、TempDB、Procedure 和锁语义。 |
| `temp-table-table-variable-session-state` | P0 | high | sql-database-conversion | 迁移临时表、表变量、全局临时表、Session 状态和生命周期。 |
| `teradata-bteq-macro-procedure-migration` | P1 | high | sql-database-conversion | 迁移 Teradata BTEQ、Macro、Procedure、Volatile Table、QUALIFY 和分布语义。 |
| `timestamp-timezone-interval-calendar-map` | P0 | medium | sql-database-conversion | 保持 Timestamp、Timezone、Interval、DST、Calendar 和默认时间函数。 |
| `transaction-savepoint-isolation-lock-map` | P0 | critical | sql-database-conversion | 保持事务、Savepoint、Isolation、锁升级、死锁、超时和自动提交。 |
| `trigger-generated-column-default-conversion` | P0 | high | sql-database-conversion | 迁移 Trigger、Generated Column、Computed Column、Default 与审计字段。 |
| `type-domain-enum-identity-sequence-map` | P0 | critical | sql-database-conversion | 转换类型、Domain、Enum、Identity、Sequence、Auto Increment 与默认值。 |
| `view-materialized-view-synonym-conversion` | P0 | high | sql-database-conversion | 转换 View、Materialized View、Synonym、依赖刷新和权限。 |
| `warehouse-snowflake-bigquery-redshift` | P1 | high | sql-database-conversion | 在 Snowflake、BigQuery、Redshift 间迁移仓库 SQL、存储过程、任务和成本模型。 |
| `workload-replay-concurrency-lock-test` | P0 | high | sql-database-conversion | 回放真实工作负载，验证并发、锁、死锁、连接池、吞吐与尾延迟。 |
| `zero-downtime-cutover-and-fallback` | P0 | critical | sql-database-conversion | 编排冻结、追平、验证、切换、观测、回退和数据修复的零停机流程。 |

## Project Generation & Product Engineering / 全项目生成

原子 Skill：**44**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `acceptance-criteria-and-traceability` | P0 | high | project-generation | 把业务需求映射到 API、数据、模块、测试、证据和验收项。 |
| `ambiguity-assumption-decision-log` | P0 | high | project-generation | 识别歧义和缺失信息，记录可验证假设、默认决策、替代方案和退出条件。 |
| `api-doc-adr-runbook-generation` | P0 | high | project-generation | 生成 API 文档、ADR、运行手册、故障处理和支持材料。 |
| `architecture-diagram-mindmap-ppt-generation` | P1 | medium | project-generation | 生成 C4、UML、数据流、部署图、思维导图和项目介绍演示文稿。 |
| `architecture-style-selection` | P0 | high | project-generation | 在模块化单体、微服务、事件驱动、Serverless、Edge 与混合架构中做证据化选择。 |
| `bounded-context-module-decomposition` | P0 | high | project-generation | 生成领域边界、模块职责、依赖规则、数据所有权和团队接口。 |
| `ci-cd-iac-environment-generation` | P0 | high | project-generation | 生成 CI/CD、容器、Kubernetes、IaC、环境晋升和回滚配置。 |
| `config-secret-feature-flag-foundation` | P0 | critical | project-generation | 生成分环境配置、秘密、Feature Flag、动态配置和安全默认值。 |
| `cost-capacity-eta-estimation` | P0 | high | project-generation | 估算项目生成的模型、工具、构建、云资源、机器 Wall-clock 和容量。 |
| `data-privacy-retention-foundation` | P0 | high | project-generation | 生成数据分类、用途限制、脱敏、保留、删除、导出和租户边界。 |
| `database-schema-migration-seed-generation` | P0 | high | project-generation | 联合生成 Schema、约束、Migration、Seed、索引和数据访问层。 |
| `dependency-license-sbom-generation` | P0 | high | project-generation | 生成依赖锁、许可证报告、SBOM、漏洞扫描和升级策略。 |
| `dotnet-fullstack-project-generation` | P1 | high | project-generation | 生成 ASP.NET Core、数据访问、前端、测试、部署和观测完整项目。 |
| `error-idempotency-resilience-foundation` | P0 | high | project-generation | 生成统一错误、幂等、超时、重试、熔断、隔离和降级机制。 |
| `event-driven-workflow-scaffold` | P1 | high | project-generation | 生成事件 Schema、Broker、Outbox、Saga、重试、幂等和可回放流程。 |
| `event-schema-outbox-consumer-generation` | P0 | high | project-generation | 生成事件 Schema、Outbox、Producer、Consumer、幂等和兼容测试。 |
| `fastapi-python-project-generation` | P1 | high | project-generation | 生成 FastAPI、数据层、异步任务、测试、容器和可观测性项目。 |
| `flutter-multiplatform-project-generation` | P1 | high | project-generation | 生成 Flutter 多端应用、平台通道、离线同步、测试和发布配置。 |
| `frontend-design-system-app-generation` | P0 | high | project-generation | 从页面、流程和设计系统生成前端组件、状态、路由、表单与测试。 |
| `go-service-platform-generation` | P1 | high | project-generation | 生成 Go 服务、配置、数据库、消息、测试、部署和性能基线。 |
| `identity-access-policy-generation` | P0 | critical | project-generation | 生成认证、授权、角色、策略、SSO、服务身份和最小权限。 |
| `laravel-php-project-generation` | P2 | high | project-generation | 生成 Laravel、数据库、队列、认证、测试和部署完整项目。 |
| `local-dev-devcontainer-bootstrap` | P0 | high | project-generation | 生成本地一键启动、Dev Container、依赖服务、测试数据和调试配置。 |
| `microservice-platform-scaffold` | P0 | high | project-generation | 生成服务、网关、注册发现、配置、可观测性、部署和治理底座。 |
| `mobile-miniapp-client-generation` | P1 | high | project-generation | 生成 Flutter、原生移动端或多平台小程序客户端及平台适配层。 |
| `modular-monolith-scaffold` | P0 | high | project-generation | 生成强模块边界、内部事件、迁移路径和可独立测试的模块化单体。 |
| `multi-tenant-saas-foundation` | P0 | high | project-generation | 生成租户隔离、组织项目层级、权限、配额、计费、审计和数据生命周期。 |
| `nestjs-node-project-generation` | P1 | high | project-generation | 生成 NestJS、TypeScript、数据库、队列、测试和部署完整项目。 |
| `nfr-slo-risk-budget-generation` | P0 | high | project-generation | 生成性能、可用性、安全、隐私、成本、容量、RPO/RTO 和风险预算。 |
| `notification-search-file-workflow-modules` | P1 | high | project-generation | 生成通知、搜索、文件、工作流、任务和后台作业等通用模块。 |
| `observability-health-audit-foundation` | P0 | high | project-generation | 生成 Trace、Metric、Log、健康检查、审计和业务事件。 |
| `payment-order-subscription-foundation` | P1 | critical | project-generation | 生成订单、支付、退款、订阅、账单、对账、幂等和审计基础能力。 |
| `performance-security-chaos-test-generation` | P1 | critical | project-generation | 生成性能、安全、故障注入、长稳和恢复测试。 |
| `production-readiness-certification` | P0 | critical | project-generation | 执行构建、测试、安全、性能、运维、备份、恢复和 E0-E5 上线门。 |
| `project-template-product-line-management` | P1 | high | project-generation | 管理模板、Feature Model、变体、升级、补丁和客户定制分支。 |
| `requirement-ingestion-and-scope-contract` | P0 | high | project-generation | 把文本、原型、文档、现有系统和访谈转化为范围、角色、流程、约束与排除项。 |
| `requirement-to-production-golden-route` | P0 | critical | project-generation | 认证从需求到项目、测试、部署、运营和交付证据的可重复 Golden Route。 |
| `rest-graphql-grpc-api-generation` | P0 | high | project-generation | 生成 REST、GraphQL、gRPC 契约、服务实现、验证、错误和客户端。 |
| `rust-service-platform-generation` | P1 | high | project-generation | 生成 Rust 服务、类型契约、异步、数据库、测试和安全部署项目。 |
| `sample-data-demo-and-tenant-fixtures` | P1 | high | project-generation | 生成脱敏样例、演示场景、租户 Fixture 和可重置演示环境。 |
| `sdk-cli-codegen-and-samples` | P1 | high | project-generation | 生成多语言 SDK、CLI、代码生成器、示例和版本兼容策略。 |
| `serverless-edge-application-scaffold` | P1 | high | project-generation | 生成函数、触发器、状态、限制、冷启动和本地仿真支持。 |
| `springboot-fullstack-project-generation` | P0 | high | project-generation | 生成 Spring Boot 后端、数据库、前端、测试、部署和观测完整项目。 |
| `unit-integration-contract-e2e-generation` | P0 | high | project-generation | 生成单元、集成、契约、端到端测试和可重复测试环境。 |

## Frontend, Mobile & Mini-App Modernization / 前端与多端转换

原子 Skill：**44**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `alipay-miniapp-platform-adapter` | P0 | medium | frontend-mobile-miniapp | 适配支付宝小程序组件、API、授权、支付、生活号和平台限制。 |
| `android-build-permission-lifecycle` | P1 | critical | frontend-mobile-miniapp | 迁移 Gradle、Manifest、权限、后台限制、进程恢复和多版本设备行为。 |
| `android-java-kotlin-compose-migration` | P1 | high | frontend-mobile-miniapp | 迁移 Android Java/XML 到 Kotlin/Compose，保持状态、生命周期和导航。 |
| `angularjs-angular-migration` | P1 | high | frontend-mobile-miniapp | 迁移 AngularJS Module、Scope、Directive、DI、Route 到现代 Angular。 |
| `app-store-signing-release-automation` | P0 | critical | frontend-mobile-miniapp | 生成签名、Provision、构建变体、商店制品、隐私清单和发布流水线。 |
| `component-props-event-slot-mapping` | P0 | medium | frontend-mobile-miniapp | 在框架间映射组件、Props、Event、Slot、Children、Ref 和生命周期。 |
| `css-scss-less-cssmodule-migration` | P0 | high | frontend-mobile-miniapp | 迁移 CSS、SCSS、Less、CSS Module、Scope、变量、Mixin 和选择器优先级。 |
| `design-token-theme-component-library` | P0 | high | frontend-mobile-miniapp | 提取设计 Token、主题、组件变体、密度和品牌定制能力。 |
| `device-matrix-ui-performance-certification` | P0 | high | frontend-mobile-miniapp | 在设备、系统、分辨率、网络和性能矩阵上执行自动认证。 |
| `douyin-miniapp-platform-adapter` | P0 | medium | frontend-mobile-miniapp | 适配抖音小程序组件、API、登录、支付、内容与平台审核要求。 |
| `flutter-platform-channel-plugin-migration` | P1 | high | frontend-mobile-miniapp | 迁移 Platform Channel、Plugin、Method/Event Channel 和原生能力。 |
| `form-validation-error-accessibility` | P0 | high | frontend-mobile-miniapp | 迁移表单、校验、异步错误、焦点、ARIA 和提交幂等行为。 |
| `frontend-application-inventory` | P0 | medium | frontend-mobile-miniapp | 识别框架、构建、组件、状态、路由、样式、平台 API、浏览器与设备支持矩阵。 |
| `frontend-mobile-miniapp-golden-route` | P0 | high | frontend-mobile-miniapp | 认证 Web、移动端与四类小程序转换的可重复、多端 Golden Route。 |
| `frontend-performance-bundle-vitals` | P0 | high | frontend-mobile-miniapp | 优化 Bundle、加载、渲染、图片、缓存、Core Web Vitals 和长任务。 |
| `frontend-security-xss-csp-csrf` | P0 | critical | frontend-mobile-miniapp | 保持输出编码、CSP、CSRF、Origin、存储和第三方脚本安全。 |
| `i18n-l10n-rtl-timezone-currency` | P0 | high | frontend-mobile-miniapp | 迁移国际化、本地化、RTL、时区、数字、货币、复数和字体。 |
| `ios-objectivec-swift-migration` | P1 | high | frontend-mobile-miniapp | 迁移 Objective-C 到 Swift，保持 Runtime、ARC、KVC/KVO 和互操作。 |
| `ios-uikit-swiftui-migration` | P1 | high | frontend-mobile-miniapp | 迁移 UIKit 到 SwiftUI，保持导航、状态、生命周期和系统组件。 |
| `jquery-dom-to-component-framework` | P1 | high | frontend-mobile-miniapp | 把 jQuery DOM 操作、事件和插件迁移为组件化状态驱动实现。 |
| `miniapp-auth-payment-share-location` | P0 | critical | frontend-mobile-miniapp | 映射授权、登录、支付、分享、位置、隐私弹窗和用户拒绝路径。 |
| `miniapp-camera-media-bluetooth-device` | P1 | high | frontend-mobile-miniapp | 映射相机、媒体、文件、蓝牙、设备、扫码和权限降级。 |
| `miniapp-common-semantic-ir` | P0 | high | frontend-mobile-miniapp | 统一表示小程序组件、页面、生命周期、路由、事件、数据绑定和平台能力。 |
| `miniapp-lifecycle-routing-subpackage` | P0 | high | frontend-mobile-miniapp | 保持 App/Page/Component 生命周期、路由栈、分包、预加载和包体限制。 |
| `miniapp-storage-network-cloud-function` | P0 | high | frontend-mobile-miniapp | 迁移存储、网络、上传、Socket、云函数、环境和错误码。 |
| `mobile-offline-sync-push-deeplink` | P0 | high | frontend-mobile-miniapp | 保持离线数据、同步冲突、推送、Deep Link、后台任务和会话。 |
| `network-cache-retry-offline-auth` | P0 | high | frontend-mobile-miniapp | 保持请求、缓存、取消、重试、离线、Token 刷新和权限错误处理。 |
| `pwa-service-worker-offline-cache` | P1 | high | frontend-mobile-miniapp | 迁移 Service Worker、Cache、安装、更新、离线和后台同步。 |
| `react-class-hooks-migration` | P0 | high | frontend-mobile-miniapp | 把 Class Component 迁移为 Hooks，保持生命周期、Ref、Context 和错误边界。 |
| `react-state-server-component-modernization` | P1 | high | frontend-mobile-miniapp | 重构客户端状态、数据获取、Server Component 和 Hydration 边界。 |
| `reactnative-flutter-semantic-migration` | P1 | high | frontend-mobile-miniapp | 在 React Native 与 Flutter 间迁移组件、状态、导航和原生桥。 |
| `responsive-layout-and-browser-compat` | P0 | high | frontend-mobile-miniapp | 保持响应式断点、布局、输入设备、浏览器兼容和降级策略。 |
| `routing-navigation-guard-deeplink` | P0 | high | frontend-mobile-miniapp | 迁移路由、导航守卫、嵌套路由、Deep Link、返回栈和参数。 |
| `ssr-ssg-hydration-edge-rendering` | P1 | high | frontend-mobile-miniapp | 迁移 SSR、SSG、ISR、Hydration、Streaming 和 Edge Runtime 行为。 |
| `state-store-reactivity-equivalence` | P0 | high | frontend-mobile-miniapp | 保持 Redux、Vuex、Pinia、MobX、Context、响应式和持久化状态语义。 |
| `typescript-strictness-and-type-recovery` | P0 | high | frontend-mobile-miniapp | 恢复动态前端类型、启用严格模式并修复 Null、事件、API 与组件契约。 |
| `unit-component-e2e-test-migration` | P0 | high | frontend-mobile-miniapp | 迁移单元、组件、浏览器自动化、Mock、Fixture 和视觉测试。 |
| `visual-interaction-snapshot-differential` | P0 | high | frontend-mobile-miniapp | 比较截图、DOM/Accessibility Tree、交互、动画、焦点和状态转换。 |
| `vue-options-composition-api-migration` | P0 | high | frontend-mobile-miniapp | 把 Options API 迁移为 Composition API，并保持依赖、Watch、Provide/Inject 和类型。 |
| `vue2-vue3-semantic-migration` | P0 | high | frontend-mobile-miniapp | 迁移 Vue 2 到 Vue 3 的实例、响应式、生命周期、插件、Slot 和兼容行为。 |
| `web-accessibility-wcag-regression` | P0 | high | frontend-mobile-miniapp | 验证键盘、屏幕阅读器、语义、对比度、焦点和动态内容可访问性。 |
| `webpack-rollup-vite-build-modernization` | P0 | high | frontend-mobile-miniapp | 迁移 Bundler、Loader、Plugin、Chunk、环境变量和开发服务器行为。 |
| `wechat-miniapp-platform-adapter` | P0 | medium | frontend-mobile-miniapp | 适配微信小程序组件、API、登录、支付、分享、云能力和审核限制。 |
| `xiaohongshu-miniapp-adapter` | P0 | medium | frontend-mobile-miniapp | 适配小红书小程序组件、API、授权、内容、交易和平台限制。 |

## Repository Refactoring & Technical Debt / 整库重构

原子 Skill：**32**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-compatible-incremental-refactor` | P0 | high | repository-refactoring | 通过 Facade、Adapter、双实现和 Feature Flag 保持外部兼容的渐进重构。 |
| `api-surface-minimization` | P0 | high | repository-refactoring | 缩小公共 API、可见性、反射入口和跨模块耦合，同时保持兼容窗口。 |
| `architecture-modularization-roadmap` | P0 | medium | repository-refactoring | 生成按价值、风险、依赖和团队边界排序的模块化重构路线与检查点。 |
| `async-nonblocking-backpressure-refactor` | P1 | high | repository-refactoring | 把阻塞路径重构为受控异步、取消、背压和资源预算模型。 |
| `behavior-preserving-refactor-proof` | P0 | high | repository-refactoring | 组合编译、测试、差分、属性、变异和不变量证据证明行为保持。 |
| `bounded-context-extraction` | P1 | high | repository-refactoring | 从实体、流程、Schema、术语和变更历史中提取领域边界与反腐层。 |
| `code-smell-and-hotspot-ranking` | P0 | high | repository-refactoring | 结合复杂度、变更频率、缺陷、调用关键度和运行热点排序重构价值与风险。 |
| `concurrency-race-lock-refactor` | P0 | high | repository-refactoring | 修复竞态、死锁、锁顺序、共享状态、非原子操作和可见性问题。 |
| `configuration-secret-refactor` | P0 | critical | repository-refactoring | 消除硬编码配置与秘密，建立类型化配置、外部化、轮换和环境隔离。 |
| `data-class-domain-model-enrichment` | P1 | critical | repository-refactoring | 把贫血数据结构重构为带不变量、值对象、领域服务和明确生命周期的模型。 |
| `dead-code-feature-flag-cleanup` | P0 | high | repository-refactoring | 识别不可达、未使用、过期 Flag、废弃 API 和历史兼容代码并安全删除。 |
| `dependency-cycle-breaker` | P0 | high | repository-refactoring | 定位模块、包、类型和运行时循环依赖，生成接口、事件或分层解耦方案。 |
| `duplicate-clone-semantic-consolidation` | P1 | high | repository-refactoring | 检测文本与语义克隆，抽取共享实现并验证调用、性能和异常行为。 |
| `error-handling-result-contract-refactor` | P0 | high | repository-refactoring | 统一异常、错误码、Result、重试、日志和用户可见错误的契约。 |
| `god-class-long-method-decomposition` | P0 | high | repository-refactoring | 按职责、数据依赖、副作用和测试缝隙拆解 God Class 与长方法。 |
| `layered-architecture-conformance-refactor` | P0 | high | repository-refactoring | 修复跨层调用、反向依赖、共享数据库和隐藏耦合等架构违规。 |
| `legacy-library-dependency-upgrade` | P0 | high | repository-refactoring | 升级废弃库、框架、运行时和插件，处理 API、行为、许可证与安全变化。 |
| `logging-observability-context-refactor` | P0 | high | repository-refactoring | 统一结构化日志、Trace、Metric、Correlation 和审计上下文。 |
| `modular-monolith-to-services` | P1 | high | repository-refactoring | 按业务能力、数据所有权和运行负载提取服务并避免分布式单体。 |
| `monolith-to-modular-monolith` | P0 | high | repository-refactoring | 把大单体重构为强边界模块化单体，为独立部署保留演进路径。 |
| `naming-type-contract-improvement` | P1 | high | repository-refactoring | 改进命名、类型、Nullability、单位、边界和 Schema，使隐含约束显式化。 |
| `null-safety-and-defensive-boundary` | P0 | critical | repository-refactoring | 建立空安全、输入验证、防御边界和失败快原则，并消除无效默认值。 |
| `package-module-boundary-refactor` | P0 | high | repository-refactoring | 重构包、模块、程序集、Crate、Package 与可见性，建立稳定边界。 |
| `performance-allocation-query-refactor` | P1 | high | repository-refactoring | 优化热点算法、对象分配、N+1、查询、缓存和批量处理并防止语义变化。 |
| `refactor-rollback-and-bisect` | P0 | critical | repository-refactoring | 为每个重构波次建立回滚、二分定位、证据保留和数据兼容策略。 |
| `repository-refactoring-golden-route` | P0 | high | repository-refactoring | 在多语言大型仓库上认证可重复、低回归、可审阅的整库重构 Golden Route。 |
| `repository-technical-debt-baseline` | P0 | high | repository-refactoring | 建立架构、复杂度、依赖、缺陷、性能、安全、测试和维护成本的技术债基线。 |
| `resource-lifecycle-leak-refactor` | P0 | high | repository-refactoring | 修复文件、Socket、连接、线程、订阅、Listener 和 Native 资源泄漏。 |
| `reviewable-patch-series-generation` | P0 | high | repository-refactoring | 把大重构拆成可独立构建、审阅、回滚和合并的补丁序列。 |
| `security-hardening-refactor` | P0 | critical | repository-refactoring | 在不改变业务结果的前提下收紧权限、输入、序列化、加密和秘密边界。 |
| `testability-dependency-injection-refactor` | P0 | high | repository-refactoring | 引入测试缝隙、接口、依赖注入、时钟和随机源控制，提升可验证性。 |
| `transaction-boundary-consistency-refactor` | P0 | critical | repository-refactoring | 重构事务边界、传播、补偿、Outbox、幂等和跨服务一致性。 |

## API, Event & Integration Modernization / 接口与集成现代化

原子 Skill：**32**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-event-integration-golden-route` | P0 | high | api-event-integration | 认证协议、消费者、交付语义和渐进切换的集成现代化 Golden Route。 |
| `api-gateway-route-policy-migration` | P0 | high | api-event-integration | 迁移路由、重写、认证、限流、WAF、缓存、灰度和观测策略。 |
| `asyncapi-event-contract-generation` | P0 | high | api-event-integration | 生成 AsyncAPI、Channel、Message、Header、Correlation 和消费者契约。 |
| `auth-oauth-oidc-mtls-api-security` | P0 | critical | api-event-integration | 迁移 API Key、OAuth2、OIDC、JWT、mTLS、签名和服务身份。 |
| `bulkhead-load-shed-fallback` | P0 | high | api-event-integration | 建立资源隔离、负载卸载、降级、Fallback 和级联故障阻断。 |
| `cdc-event-stream-integration` | P0 | high | api-event-integration | 把 CDC、数据库日志和业务事件整合为有序、可追溯的数据流。 |
| `consumer-driven-compatibility` | P0 | high | api-event-integration | 收集并执行消费者契约，阻止 Provider 变更破坏真实调用方。 |
| `dead-letter-replay-poison-message` | P0 | high | api-event-integration | 设计 DLQ、隔离、重放、毒消息诊断、顺序恢复和审计。 |
| `delivery-semantics-exactly-once-analysis` | P0 | high | api-event-integration | 分析 At-most-once、At-least-once、Exactly-once 的真实边界与成本。 |
| `distributed-trace-correlation` | P0 | high | api-event-integration | 贯通 HTTP、RPC、消息、批处理和数据库的 Trace、Baggage 与业务 ID。 |
| `edi-file-sftp-batch-integration` | P1 | high | api-event-integration | 现代化 EDI、CSV、固定宽度、SFTP、批量交换、重传和文件对账。 |
| `event-ordering-partition-key` | P0 | high | api-event-integration | 保持事件顺序、Partition Key、并行消费、重分区和热点控制。 |
| `event-version-upcaster-downcaster` | P1 | high | api-event-integration | 生成事件 Upcaster、Downcaster、默认值、弃用和历史重放兼容层。 |
| `graphql-schema-resolver-migration` | P1 | high | api-event-integration | 迁移 GraphQL Schema、Resolver、N+1、Subscription、授权和弃用策略。 |
| `grpc-protobuf-service-migration` | P0 | high | api-event-integration | 迁移 gRPC、Proto、字段编号、Streaming、Deadline、Metadata 和错误状态。 |
| `idempotency-key-deduplication` | P0 | critical | api-event-integration | 建立请求幂等键、去重窗口、结果缓存、冲突和重复副作用处理。 |
| `incremental-cutover-dual-publish` | P0 | critical | api-event-integration | 通过 Adapter、双发布、镜像消费者、流量分层和回退完成渐进切换。 |
| `integration-landscape-inventory` | P0 | medium | api-event-integration | 盘点 API、RPC、事件、文件、ESB、消费者、认证、SLA、数据契约和依赖拓扑。 |
| `integration-performance-load-replay` | P0 | high | api-event-integration | 回放真实流量与消息，验证吞吐、尾延迟、积压和恢复速度。 |
| `integration-security-chaos-test` | P0 | critical | api-event-integration | 测试认证失败、重放、伪造、网络分区、依赖超时和 Broker 故障。 |
| `message-broker-kafka-rabbit-pulsar-map` | P1 | medium | api-event-integration | 在 Kafka、RabbitMQ、Pulsar 等 Broker 间映射 Topic、Queue、确认和事务。 |
| `openapi-contract-normalization` | P0 | high | api-event-integration | 规范 OpenAPI、参数、响应、错误、分页、版本、示例和代码生成兼容性。 |
| `outbox-inbox-transactional-messaging` | P0 | critical | api-event-integration | 实现 Outbox、Inbox、事务消息、幂等消费、重放和对账。 |
| `protobuf-avro-jsonschema-evolution` | P0 | high | api-event-integration | 管理 Proto、Avro、JSON Schema 的向前、向后与完全兼容演进。 |
| `rate-limit-quota-backpressure-policy` | P0 | high | api-event-integration | 保持配额、Burst、优先级、背压、429、重试提示和公平性。 |
| `rest-versioning-compatibility-migration` | P0 | high | api-event-integration | 迁移 REST 路由、媒体类型、版本、状态码、Header 和兼容窗口。 |
| `retry-timeout-circuit-breaker` | P0 | high | api-event-integration | 统一超时预算、重试条件、Jitter、熔断、恢复探测和幂等约束。 |
| `saga-orchestration-choreography` | P0 | high | api-event-integration | 设计 Saga 编排或协同、补偿、超时、人工介入和状态追踪。 |
| `schema-registry-compatibility` | P0 | high | api-event-integration | 管理 Schema Registry、兼容级别、Subject、版本、发布门和回滚。 |
| `service-virtualization-contract-test` | P0 | high | api-event-integration | 为不可用或昂贵依赖生成虚拟服务、故障场景和契约验证。 |
| `soap-wsdl-to-rest-grpc` | P1 | high | api-event-integration | 将 SOAP/WSDL、XSD、WS-Security、Fault 和事务语义迁移到 REST 或 gRPC。 |
| `websocket-sse-realtime-migration` | P1 | high | api-event-integration | 迁移 WebSocket、SSE、心跳、重连、顺序、背压和会话恢复。 |

## Data Engineering, Lakehouse & Analytics / 大数据与湖仓

原子 Skill：**40**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `airflow-dag-modernization` | P0 | high | data-engineering | 迁移 Airflow DAG、Operator、Sensor、XCom、Schedule、Backfill 和执行隔离。 |
| `batch-stream-unified-semantic-ir` | P0 | high | data-engineering | 统一表示 Source、Transform、State、Window、Sink、Checkpoint 与回填逻辑。 |
| `beam-portable-pipeline-generation` | P1 | high | data-engineering | 生成 Apache Beam 可移植 Pipeline、Runner Profile、Window 和 State。 |
| `cdc-ingestion-pipeline-generation` | P0 | high | data-engineering | 生成 CDC 连接器、水位、快照、增量、去重、Schema 演进和恢复流程。 |
| `dagster-asset-orchestration` | P1 | high | data-engineering | 生成 Dagster Asset、Partition、IO Manager、Sensor、资源和数据契约。 |
| `data-contract-and-ownership` | P0 | high | data-engineering | 定义 Schema、语义、质量、SLA、Owner、保留、隐私和兼容责任。 |
| `data-lineage-catalog-integration` | P0 | medium | data-engineering | 发布字段级血缘、Owner、术语、质量、用途和影响到数据目录。 |
| `data-pipeline-chaos-recovery` | P0 | high | data-engineering | 注入 Source、Broker、Executor、Object Store、Catalog 和网络故障验证恢复。 |
| `data-platform-security-governance` | P0 | critical | data-engineering | 执行最小权限、行列策略、审计、加密、密钥和租户隔离。 |
| `data-platform-source-inventory` | P0 | medium | data-engineering | 盘点数据库、日志、文件、API、消息、批处理、作业、表、指标和消费方。 |
| `data-product-production-certification` | P0 | critical | data-engineering | 对数据契约、质量、血缘、SLA、隐私、恢复和成本签发数据产品证据。 |
| `data-quality-rule-generation` | P0 | high | data-engineering | 从 Schema、统计、业务规则和历史缺陷生成完整性、一致性与及时性规则。 |
| `data-reconciliation-observability` | P0 | high | data-engineering | 生成行数、聚合、Checksum、分布、异常和 SLA 的持续对账与观测。 |
| `data-serving-olap-clickhouse` | P1 | high | data-engineering | 生成 OLAP、ClickHouse、物化视图、实时摄取、聚合和服务层。 |
| `dbt-model-test-documentation` | P0 | critical | data-engineering | 生成和迁移 dbt Model、Source、Test、Macro、Snapshot、Doc 与 Semantic Layer。 |
| `event-time-processing-correctness` | P0 | high | data-engineering | 验证 Event Time、Processing Time、Watermark、Window 和时区语义。 |
| `exactly-once-checkpoint-recovery` | P0 | high | data-engineering | 验证 State、Checkpoint、Source Offset、Sink Commit 和故障恢复一致性。 |
| `feature-store-training-serving-parity` | P1 | critical | data-engineering | 保持离线/在线 Feature、时间旅行、Point-in-time Correctness 和服务一致性。 |
| `flink-state-window-watermark-migration` | P0 | high | data-engineering | 迁移 Flink State、Window、Watermark、Timer、Checkpoint 和 Savepoint。 |
| `hadoop-mapreduce-spark-migration` | P1 | medium | data-engineering | 把 Hadoop MapReduce 作业迁移到 Spark 或批流统一引擎并保持结果。 |
| `hive-metastore-table-modernization` | P0 | high | data-engineering | 迁移 Hive Table、Partition、SerDe、Metastore、ACID 和统计信息。 |
| `kafka-topic-partition-retention-design` | P0 | high | data-engineering | 设计 Topic、Partition、Key、Retention、Compaction、配额和消费者组。 |
| `lakehouse-analytics-golden-route` | P0 | high | data-engineering | 认证批流、CDC、湖仓、编排、质量和分析平台的商业 Golden Route。 |
| `lakehouse-iceberg-delta-hudi-selection` | P0 | high | data-engineering | 按更新、流批、并发、生态、治理和成本选择 Iceberg、Delta 或 Hudi。 |
| `lakehouse-table-format-migration` | P0 | high | data-engineering | 迁移 Snapshot、Manifest、Log、Partition Evolution、Compaction 与 Time Travel。 |
| `late-data-reprocessing-backfill` | P0 | high | data-engineering | 处理迟到、乱序、重算、回填、幂等、覆盖和结果版本。 |
| `master-reference-data-management` | P1 | high | data-engineering | 生成主数据匹配、合并、Survivorship、版本和参考数据同步策略。 |
| `ml-data-drift-quality-gates` | P1 | high | data-engineering | 监控训练与服务数据漂移、缺失、延迟、标签和质量门。 |
| `multi-region-data-residency` | P0 | high | data-engineering | 按地域、租户、法规和延迟约束安排复制、处理、删除与访问。 |
| `object-storage-layout-compaction` | P0 | high | data-engineering | 优化对象存储路径、文件大小、分区、排序、压缩、小文件和生命周期。 |
| `pii-classification-tokenization` | P0 | high | data-engineering | 识别敏感字段并执行 Tokenization、Masking、访问策略和用途限制。 |
| `query-engine-cost-performance` | P0 | high | data-engineering | 优化扫描、分区裁剪、统计、缓存、并发、队列和云查询成本。 |
| `retention-deletion-legal-hold` | P0 | high | data-engineering | 在湖仓、缓存、备份和派生数据中执行保留、删除与 Legal Hold。 |
| `schema-evolution-compatibility` | P0 | high | data-engineering | 管理字段增加、删除、重命名、类型变化、默认值和历史读写兼容。 |
| `semantic-metric-layer-generation` | P0 | high | data-engineering | 生成一致的 Metric、维度、口径、时间粒度、权限和 BI 接口。 |
| `skew-hotkey-partition-optimization` | P0 | critical | data-engineering | 检测数据倾斜与 Hot Key，生成盐化、重分区、预聚合和容量策略。 |
| `spark-job-dataset-rdd-modernization` | P0 | high | data-engineering | 现代化 Spark RDD、DataFrame、Dataset、UDF、Shuffle、缓存和作业提交。 |
| `streaming-join-state-sizing` | P0 | high | data-engineering | 评估 Stream Join、State TTL、倾斜、内存、Checkpoint 和结果完整性。 |
| `trino-presto-federated-query` | P1 | high | data-engineering | 生成 Trino/Presto Catalog、联邦查询、Pushdown、权限和成本控制。 |
| `workflow-sla-retry-backfill` | P0 | high | data-engineering | 统一作业 SLA、重试、超时、补数、依赖、优先级和人工恢复。 |

## Cloud Native, DevOps & Platform Engineering / 云原生工程

原子 Skill：**38**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `application-cloud-readiness-assessment` | P0 | high | cloud-devops-platform | 评估状态、依赖、存储、网络、进程、许可、性能和云迁移阻塞项。 |
| `artifact-registry-signing-provenance` | P0 | high | cloud-devops-platform | 管理镜像、包、模型、SBOM、签名、来源证明和保留策略。 |
| `backup-restore-disaster-recovery` | P0 | high | cloud-devops-platform | 生成应用、数据库、对象、配置、密钥和集群备份恢复流程。 |
| `capacity-cost-carbon-optimization` | P1 | high | cloud-devops-platform | 优化资源、Spot、预留、存储层级、网络和能源成本，保持 SLO。 |
| `ci-pipeline-build-test-scan` | P0 | high | cloud-devops-platform | 生成缓存、矩阵构建、测试、扫描、签名、制品和发布流水线。 |
| `cloud-account-project-landing-zone` | P0 | high | cloud-devops-platform | 生成账户、项目、网络、日志、身份、预算、密钥和基线 Landing Zone。 |
| `cloud-native-production-golden-route` | P0 | critical | cloud-devops-platform | 认证容器、Kubernetes、IaC、CI/CD、灾备和私有部署 Golden Route。 |
| `compose-local-stack-generation` | P0 | high | cloud-devops-platform | 生成本地依赖、网络、Volume、健康检查、测试数据和一键启动 Compose。 |
| `configmap-secret-external-secret` | P0 | critical | cloud-devops-platform | 管理配置、Secret、外部 Secret、轮换、版本和工作负载重载。 |
| `dockerfile-multistage-hardening` | P0 | high | cloud-devops-platform | 生成多阶段、最小镜像、非 root、锁定依赖、缓存友好和可扫描的 Dockerfile。 |
| `environment-drift-detection` | P0 | high | cloud-devops-platform | 比较声明与实际环境、依赖、配置、权限和版本，阻止不可解释漂移。 |
| `ephemeral-preview-environment` | P1 | high | cloud-devops-platform | 按 PR 创建隔离、限额、可清理的预览环境和数据 Fixture。 |
| `gitops-argo-flux-promotion` | P0 | high | cloud-devops-platform | 生成 GitOps Repo、环境晋升、漂移检测、同步波次和审批。 |
| `helm-chart-lifecycle` | P0 | high | cloud-devops-platform | 生成 Helm Chart、Values Schema、Hook、升级、回滚、依赖和版本策略。 |
| `hpa-vpa-keda-autoscaling` | P1 | high | cloud-devops-platform | 生成 HPA、VPA、KEDA、稳定窗口、队列指标和扩缩容保护。 |
| `ingress-gateway-tls-routing` | P0 | high | cloud-devops-platform | 生成 Ingress/Gateway、证书、域名、路径、Header、限流和 WAF 集成。 |
| `kubernetes-workload-manifest-generation` | P0 | high | cloud-devops-platform | 生成 Deployment、StatefulSet、Job、Service、Config、Secret 和 RBAC。 |
| `kustomize-overlay-management` | P1 | high | cloud-devops-platform | 生成 Base、Overlay、Patch、环境差异和配置验证。 |
| `liveness-readiness-startup-probes` | P0 | high | cloud-devops-platform | 生成语义正确的启动、存活、就绪和依赖健康探针。 |
| `managed-database-cache-queue-migration` | P1 | high | cloud-devops-platform | 迁移托管数据库、缓存、队列、连接、备份、监控和切换。 |
| `multi-cloud-abstraction-exit-strategy` | P1 | high | cloud-devops-platform | 定义可移植接口、数据出口、替代服务、锁定风险和迁移演练。 |
| `multi-region-active-active-failover` | P1 | high | cloud-devops-platform | 设计多区域路由、数据一致性、故障转移、Split-brain 防护和回切。 |
| `network-policy-zero-trust` | P0 | high | cloud-devops-platform | 生成默认拒绝、服务身份、命名空间、出口、DNS 和微分段策略。 |
| `object-storage-cdn-static-delivery` | P1 | high | cloud-devops-platform | 生成对象存储、CDN、缓存、签名 URL、生命周期和静态站点。 |
| `observability-log-metric-trace-stack` | P0 | high | cloud-devops-platform | 部署日志、Metric、Trace、Profile、告警、看板和数据保留策略。 |
| `oncall-runbook-auto-remediation` | P1 | high | cloud-devops-platform | 从告警生成诊断、止损、自动修复、审批和复盘链接。 |
| `operator-crd-controller-generation` | P1 | high | cloud-devops-platform | 生成 CRD、Controller、Reconcile、Finalizer、Status、升级和幂等逻辑。 |
| `pdb-topology-spread-affinity` | P0 | high | cloud-devops-platform | 生成 PDB、Topology Spread、Affinity、Anti-affinity 和故障域策略。 |
| `platform-engineering-selfservice-template` | P1 | high | cloud-devops-platform | 生成受治理的服务模板、Golden Path、开发门户和自服务动作。 |
| `pod-security-admission-policy` | P0 | critical | cloud-devops-platform | 实施 Pod Security、Seccomp、Capability、只读文件系统和镜像策略。 |
| `policy-as-code-infrastructure` | P0 | high | cloud-devops-platform | 对 IaC、集群、镜像、网络、成本和地域执行可测试策略。 |
| `private-cloud-airgap-deployment` | P0 | high | cloud-devops-platform | 生成私有云、离线镜像仓、模型与依赖包、许可证、更新和审计流程。 |
| `pulumi-cloudformation-conversion` | P1 | high | cloud-devops-platform | 在 Pulumi、CloudFormation 与 Terraform 间转换资源、依赖和生命周期。 |
| `resource-request-limit-rightsizing` | P0 | high | cloud-devops-platform | 基于负载与历史生成 CPU、内存、Ephemeral Storage 请求和限制。 |
| `rolling-bluegreen-canary-deployment` | P0 | high | cloud-devops-platform | 生成滚动、蓝绿、金丝雀、分析模板、自动暂停和回滚。 |
| `serverless-function-event-migration` | P1 | high | cloud-devops-platform | 迁移函数、事件、状态、超时、并发、冷启动、重试和本地仿真。 |
| `service-mesh-traffic-policy` | P1 | high | cloud-devops-platform | 配置 mTLS、路由、重试、熔断、可观测性和渐进流量策略。 |
| `terraform-iac-generation` | P0 | high | cloud-devops-platform | 生成模块化 Terraform、State、Provider Lock、Plan 门和 Drift 检测。 |

## Autonomous Test & Quality Assurance Factory / 自动测试认证工厂

原子 Skill：**44**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `accessibility-localization-test` | P0 | high | test-quality-certification | 验证 Accessibility Tree、键盘、读屏、RTL、时区、货币和多语言。 |
| `api-contract-test-generation` | P0 | high | test-quality-certification | 根据 OpenAPI、GraphQL、Proto 和实际流量生成 Provider 契约测试。 |
| `automatic-test-repair` | P1 | high | test-quality-certification | 仅在产品契约未变时修复失效测试，禁止弱化断言或隐藏缺陷。 |
| `chaos-fault-network-storage-test` | P0 | high | test-quality-certification | 注入进程、网络、磁盘、时钟、依赖、区域和凭据故障。 |
| `compiler-framework-database-matrix` | P0 | high | test-quality-certification | 覆盖编译器、框架、驱动、数据库和协议版本兼容矩阵。 |
| `concurrency-race-linearizability-test` | P0 | high | test-quality-certification | 检测竞态、死锁、丢更新、顺序和线性化违规。 |
| `consumer-driven-contract-test` | P0 | high | test-quality-certification | 收集消费者假设并生成可阻断不兼容发布的契约测试。 |
| `coverage-branch-path-dataflow` | P0 | high | test-quality-certification | 融合行、分支、路径、数据流、调用、需求和风险覆盖，而非单一覆盖率。 |
| `database-schema-data-test` | P0 | high | test-quality-certification | 测试 Schema、约束、数据质量、迁移、回填、权限和回滚。 |
| `differential-runtime-test` | P0 | high | test-quality-certification | 用同一输入比较旧新实现、不同语言、不同数据库或不同模型结果。 |
| `e0-e5-business-line-certification` | P0 | high | test-quality-certification | 按业务线执行 E0-E5 的功能、行为、性能、安全、恢复和长期稳定门。 |
| `end-to-end-business-journey-test` | P0 | high | test-quality-certification | 生成跨前端、API、消息、数据库和第三方的业务旅程测试。 |
| `environment-matrix-os-arch-runtime` | P0 | high | test-quality-certification | 覆盖 OS、CPU 架构、运行时、Locale、文件系统和网络差异。 |
| `evidence-bundle-test-report` | P0 | high | test-quality-certification | 输出可追溯、可重放、带环境与版本的测试和未通过证据。 |
| `failed-test-root-cause-clustering` | P1 | high | test-quality-certification | 聚类失败签名，区分产品缺陷、测试缺陷、环境缺陷和数据缺陷。 |
| `fixture-service-virtualization` | P0 | high | test-quality-certification | 生成稳定 Fixture、Mock Server、模拟设备、故障脚本和录制回放。 |
| `flaky-test-detection-quarantine` | P0 | high | test-quality-certification | 统计识别 Flaky、污染、顺序依赖和环境不稳定，并隔离而非忽略。 |
| `fuzz-parser-api-file-protocol` | P0 | high | test-quality-certification | 对 Parser、API、文件、归档、协议和序列化执行结构化 Fuzz。 |
| `golden-master-approval-test` | P1 | high | test-quality-certification | 对难以显式断言的报表、文件、UI 和批处理输出建立受控 Golden Master。 |
| `independent-verifier-execution` | P0 | high | test-quality-certification | 在与生成 Agent 隔离的环境和权限下执行验证，阻止自证循环。 |
| `integration-test-environment-generation` | P0 | high | test-quality-certification | 生成数据库、消息、缓存、外部服务、容器和迁移的一体化测试环境。 |
| `legacy-characterization-test` | P0 | high | test-quality-certification | 在修改前捕获遗留系统可观察行为、错误、性能和副作用作为基线。 |
| `message-event-ordering-test` | P0 | high | test-quality-certification | 测试顺序、重复、丢失、重放、幂等、Schema 演进和 DLQ。 |
| `metamorphic-relation-test` | P0 | high | test-quality-certification | 在缺少精确 Oracle 时通过输入变换与关系断言验证结果。 |
| `mobile-device-platform-test` | P0 | high | test-quality-certification | 在系统、设备、权限、网络、后台和升级矩阵上测试移动端与小程序。 |
| `mutation-score-and-survivor-analysis` | P0 | high | test-quality-certification | 执行 Mutation Testing，分析存活变异并补齐真正有效的断言。 |
| `oracle-generation-and-calibration` | P0 | high | test-quality-certification | 从规范、旧实现、独立实现、约束和专家样本生成并校准 Oracle。 |
| `performance-load-stress-spike-test` | P0 | high | test-quality-certification | 生成负载、压力、峰值、容量和降级测试并对比基线。 |
| `privacy-data-leakage-test` | P0 | high | test-quality-certification | 检测日志、Trace、缓存、错误、导出、训练和跨租户数据泄漏。 |
| `property-based-invariant-test` | P0 | high | test-quality-certification | 从类型、Schema、业务规则和协议生成属性测试与最小反例。 |
| `qa-factory-golden-route` | P0 | high | test-quality-certification | 认证自动生成、执行、修复、复测与证据聚合的 QA Factory Golden Route。 |
| `regression-escape-feedback-loop` | P1 | high | test-quality-certification | 把生产漏检缺陷反向生成测试、Skill、防护和训练数据。 |
| `repository-test-inventory-and-gap` | P0 | medium | test-quality-certification | 盘点测试层级、覆盖、Fixture、环境、Flaky、缺陷历史和关键路径缺口。 |
| `requirement-to-test-traceability` | P0 | high | test-quality-certification | 把需求、规则、风险、代码、Schema、测试和证据连接为双向 Traceability Matrix。 |
| `routine-trigger-side-effect-test` | P0 | high | test-quality-certification | 测试 Procedure、Function、Trigger、Job 的结果、副作用、事务和错误。 |
| `security-abuse-misuse-test` | P0 | critical | test-quality-certification | 根据威胁模型生成攻击、滥用、越权和恶意输入测试。 |
| `soak-leak-degradation-test` | P0 | high | test-quality-certification | 长期运行检测内存、句柄、连接、积压、漂移和性能衰减。 |
| `test-data-synthetic-mask-subset` | P0 | high | test-quality-certification | 生成合成、脱敏、子集、边界和关系完整的测试数据。 |
| `test-impact-selection-parallelization` | P0 | high | test-quality-certification | 按语义影响、安全风险和历史失败选择并并行执行最小充分测试。 |
| `test-quality-score-and-stop-rule` | P0 | high | test-quality-certification | 综合风险、变异、覆盖、缺陷发现和不确定性决定是否停止或补测。 |
| `time-randomness-determinism-test` | P0 | high | test-quality-certification | 控制时钟、随机、UUID、调度和网络，发现不可重复测试与行为。 |
| `ui-component-interaction-test` | P0 | high | test-quality-certification | 生成组件、状态、表单、路由、权限、键盘和交互测试。 |
| `unit-test-generation-and-isolation` | P0 | high | test-quality-certification | 生成确定性单元测试、依赖隔离、边界、错误和不变量断言。 |
| `visual-regression-test` | P0 | high | test-quality-certification | 对截图、布局、字体、主题、动画和响应式进行容差可解释的视觉差分。 |

## Security, Privacy, Compliance & Supply Chain / 安全合规

原子 Skill：**40**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `application-threat-model-generation` | P0 | critical | security-compliance | 从架构、数据流、身份、工具和部署生成资产、攻击者、威胁与缓解措施。 |
| `attack-surface-and-trust-boundary` | P0 | high | security-compliance | 识别外部入口、内部边界、跨租户、控制面、数据面和供应链攻击面。 |
| `authorization-policy-equivalence` | P0 | critical | security-compliance | 证明角色、属性、资源、行列权限和方法安全在转换后未被扩大。 |
| `code-signing-provenance-attestation` | P0 | high | security-compliance | 为源码、构建、制品、模型、Skill 和证据生成签名与来源证明。 |
| `compliance-control-mapping-evidence` | P0 | medium | security-compliance | 把控制目标映射到策略、实现、测试、Owner、证据、例外和复审。 |
| `container-image-hardening-scan` | P0 | high | security-compliance | 扫描基础镜像、包、用户、Capability、文件权限、秘密和运行配置。 |
| `cryptography-algorithm-key-migration` | P0 | critical | security-compliance | 迁移算法、模式、密钥长度、KDF、证书、轮换和历史数据解密。 |
| `dast-api-web-security-testing` | P0 | critical | security-compliance | 对运行应用执行认证、注入、会话、权限、业务逻辑和 API 安全测试。 |
| `dependency-sca-vulnerability-reachability` | P0 | high | security-compliance | 结合 SBOM、调用图、配置和运行路径判断依赖漏洞真实可达性。 |
| `encryption-at-rest-in-transit` | P0 | critical | security-compliance | 验证传输、存储、备份、队列、缓存和租户数据的加密与证书配置。 |
| `file-upload-archive-parser-safety` | P0 | critical | security-compliance | 防御恶意文件、Zip Slip、解压炸弹、Polyglot、MIME 欺骗和 Parser 漏洞。 |
| `iac-policy-security-validation` | P0 | critical | security-compliance | 在 Plan 阶段阻止公开存储、宽权限、未加密、无日志和不合规地域。 |
| `iast-runtime-taint-validation` | P1 | high | security-compliance | 在测试运行中验证实际污点路径、Sanitizer、Sink 和漏洞可利用性。 |
| `identity-authentication-modernization` | P0 | critical | security-compliance | 现代化密码、MFA、SSO、OIDC、服务身份、设备身份和恢复流程。 |
| `incident-response-forensics-bundle` | P0 | high | security-compliance | 生成时间线、证据保全、影响范围、凭据轮换、客户通知和复盘包。 |
| `key-management-tenant-separation` | P0 | critical | security-compliance | 实施租户级密钥、Envelope Encryption、轮换、撤销和访问审计。 |
| `kubernetes-cloud-posture-scan` | P0 | high | security-compliance | 检查 RBAC、网络、工作负载、存储、日志、公开资源和云权限姿态。 |
| `license-obligation-and-policy` | P0 | high | security-compliance | 识别许可证、Notice、Copyleft、模型条款、数据权利和再分发义务。 |
| `malicious-repository-build-sandbox` | P0 | high | security-compliance | 把仓库脚本、构建插件、测试、代码生成和安装 Hook 视为不可信执行。 |
| `memory-rag-dataset-poisoning-defense` | P0 | high | security-compliance | 检测记忆、知识库、训练集和评测集中的污染、后门和低置信内容。 |
| `model-adapter-supply-chain-defense` | P0 | critical | security-compliance | 验证模型、Tokenizer、Adapter、量化、转换和加载组件的签名与租户绑定。 |
| `model-extraction-inversion-membership` | P1 | critical | security-compliance | 评估模型窃取、训练数据反演、成员推断、提示泄漏和速率攻击。 |
| `package-typosquat-dependency-confusion` | P0 | high | security-compliance | 检测拼写劫持、依赖混淆、恶意更新、来源变化和锁文件绕过。 |
| `pii-sensitive-data-dlp` | P0 | high | security-compliance | 识别、标记、脱敏、阻断和审计代码、日志、文档、数据与模型输出中的敏感信息。 |
| `privacy-purpose-consent-enforcement` | P0 | high | security-compliance | 在采集、检索、Trace、训练、导出、删除和共享阶段执行用途与同意。 |
| `prompt-injection-tool-abuse-defense` | P0 | high | security-compliance | 隔离仓库、文档、检索和工具结果中的指令，阻止权限提升与数据外传。 |
| `redteam-adversarial-campaign` | P1 | high | security-compliance | 对 Agent、代码转换、数据、模型、工具和多租户控制实施持续红队。 |
| `sast-semantic-vulnerability-analysis` | P0 | high | security-compliance | 结合数据流、调用、权限和配置执行可达性 SAST，减少无效告警。 |
| `sbom-mbom-aibom-generation` | P0 | high | security-compliance | 生成软件、模型、数据、Adapter、Skill、工具和镜像的统一物料清单。 |
| `secret-discovery-rotation-broker` | P0 | critical | security-compliance | 发现硬编码和泄漏秘密，接入短期凭据 Broker、轮换、审计和撤销。 |
| `secure-delete-crypto-erasure` | P0 | critical | security-compliance | 对主存储、缓存、索引、备份、日志、Adapter 和工作区执行可证明删除。 |
| `security-production-certification` | P0 | critical | security-compliance | 聚合应用、平台、数据、AI 和供应链证据，阻止带未接受关键风险的发布。 |
| `security-waiver-expiry-risk` | P0 | critical | security-compliance | 管理安全例外、补偿控制、责任人、到期、复审和自动阻断。 |
| `session-cookie-token-hardening` | P0 | high | security-compliance | 加固 Session、Cookie、JWT、Refresh、撤销、固定攻击和跨站策略。 |
| `sql-injection-query-safety` | P0 | critical | security-compliance | 检测拼接 SQL、动态标识符、二阶注入、ORM 绕过和权限上下文。 |
| `ssrf-rce-path-deserialization-defense` | P0 | high | security-compliance | 检测 SSRF、命令执行、路径穿越、模板注入和不安全反序列化。 |
| `tamper-evident-audit-evidence` | P0 | high | security-compliance | 通过哈希链、签名、不可变存储和时间戳保护审计与认证证据。 |
| `tenant-isolation-security-test` | P0 | critical | security-compliance | 测试身份、查询、缓存、对象存储、向量、模型 Adapter 和 Trace 的租户隔离。 |
| `vulnerability-remediation-verification` | P0 | high | security-compliance | 验证补丁真正切断可利用路径且未引入兼容、性能或权限回归。 |
| `xss-csrf-csp-browser-security` | P0 | critical | security-compliance | 检测 XSS、CSRF、CSP、Clickjacking、Origin、第三方脚本和存储风险。 |

## Performance, Reliability & Cost Engineering / 性能可靠性与成本

原子 Skill：**32**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `architecture-cost-quality-pareto` | P1 | high | performance-reliability-finops | 比较架构、模型、验证和部署方案的质量、延迟、风险和成本前沿。 |
| `backup-restore-rpo-rto` | P0 | high | performance-reliability-finops | 测量备份、恢复、PITR、RPO、RTO、完整性和运行手册可执行性。 |
| `cache-strategy-hit-consistency` | P0 | high | performance-reliability-finops | 设计本地、分布式、HTTP、查询和语义缓存的命中、失效与一致性。 |
| `capacity-margin-forecast` | P1 | high | performance-reliability-finops | 预测任务量、资源、队列、成本、收入、毛利和扩容时间点。 |
| `capacity-model-and-load-shape` | P0 | critical | performance-reliability-finops | 建立容量、队列、服务时间、资源饱和、Burst 和季节性模型。 |
| `chaos-resilience-game-day` | P0 | high | performance-reliability-finops | 组织进程、节点、区域、网络、依赖、时钟和权限故障演练。 |
| `cloud-resource-rightsizing` | P1 | high | performance-reliability-finops | 优化实例、容器、存储、数据库、网络、Spot 与预留资源。 |
| `cpu-profile-hotpath-optimization` | P0 | medium | performance-reliability-finops | 结合 Sampling、Tracing、Hardware Counter 和调用图定位 CPU 热点并验证收益。 |
| `data-pipeline-compute-storage-cost` | P1 | high | performance-reliability-finops | 优化扫描、Shuffle、State、文件布局、保留、重算和跨区传输成本。 |
| `database-query-lock-pool-tuning` | P0 | high | performance-reliability-finops | 优化 SQL、索引、锁、事务、连接池、批处理和数据库资源。 |
| `disaster-recovery-region-evacuation` | P1 | high | performance-reliability-finops | 演练区域疏散、DNS/流量切换、数据恢复、密钥和供应链依赖。 |
| `distributed-trace-critical-path` | P0 | high | performance-reliability-finops | 从跨服务 Trace、数据库和消息链路恢复端到端关键路径。 |
| `error-budget-release-policy` | P0 | critical | performance-reliability-finops | 把错误预算、回归风险、业务窗口和证据绑定发布速度与自动阻断。 |
| `frontend-bundle-render-vitals` | P0 | high | performance-reliability-finops | 优化 Bundle、关键资源、渲染、Hydration、图片、缓存和 Web Vitals。 |
| `gc-runtime-jit-aot-tuning` | P1 | high | performance-reliability-finops | 调优 GC、JIT、AOT、Runtime Flag、Warmup、Tiered Compilation 和启动。 |
| `ha-replication-failover` | P0 | high | performance-reliability-finops | 验证副本、Leader 选举、Quorum、故障转移、数据一致性和回切。 |
| `idempotency-replay-recovery` | P0 | high | performance-reliability-finops | 验证重复请求、任务重放、恢复和补偿不会产生重复副作用。 |
| `io-filesystem-network-profile` | P0 | medium | performance-reliability-finops | 分析磁盘、文件系统、对象存储、Socket、DNS、TLS 和网络往返瓶颈。 |
| `memory-heap-leak-allocation` | P0 | high | performance-reliability-finops | 分析 Heap、Allocation、GC、Native Memory、泄漏、缓存和对象生命周期。 |
| `mobile-startup-battery-network` | P1 | high | performance-reliability-finops | 优化移动端冷启动、内存、电量、网络、后台和包体积。 |
| `model-token-gpu-inference-cost` | P0 | critical | performance-reliability-finops | 优化模型路由、上下文、缓存、Batch、量化、Adapter 和 GPU 利用率。 |
| `performance-regression-bisect` | P0 | high | performance-reliability-finops | 在提交、依赖、配置、数据和环境之间自动二分定位性能退化。 |
| `performance-release-gate` | P0 | critical | performance-reliability-finops | 以可重复负载和统计置信阻止性能、容量或成本显著退化的发布。 |
| `performance-reliability-golden-route` | P0 | high | performance-reliability-finops | 认证从基线、优化、压测、故障演练到成本门的可重复 Golden Route。 |
| `queueing-concurrency-admission-control` | P0 | high | performance-reliability-finops | 设计并发、队列、公平调度、Admission、优先级和过载保护。 |
| `rate-limit-load-shed-graceful-degrade` | P0 | high | performance-reliability-finops | 生成限流、Load Shed、降级、Fallback 和恢复策略并验证用户影响。 |
| `reliability-evidence-and-slo-report` | P0 | high | performance-reliability-finops | 输出 SLI、SLO、错误预算、故障、恢复、容量和未决风险证据。 |
| `serialization-compression-payload` | P1 | high | performance-reliability-finops | 优化序列化格式、字段、压缩、Copy、Chunk 和网络 Payload。 |
| `streaming-state-backpressure-tuning` | P0 | high | performance-reliability-finops | 优化流处理 State、Checkpoint、Watermark、Backpressure、Shuffle 和并行度。 |
| `thread-pool-event-loop-coroutine` | P0 | high | performance-reliability-finops | 优化线程池、Event Loop、Coroutine、阻塞检测、上下文切换和背压。 |
| `timeout-retry-circuit-budget` | P0 | high | performance-reliability-finops | 按端到端 Deadline 分配超时、重试、熔断与放大预算。 |
| `workload-model-and-slo-baseline` | P0 | critical | performance-reliability-finops | 定义用户、请求、数据、并发、峰值、依赖、SLO、错误预算和成本基线。 |

## Architecture Intelligence, Documentation & Online IDE / 架构智能与代码工作台

原子 Skill：**32**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `api-doc-data-dictionary-generation` | P0 | high | architecture-documentation-ide | 生成版本化 API 文档、事件目录、数据字典、示例和兼容说明。 |
| `api-event-integration-map` | P0 | medium | architecture-documentation-ide | 展示 API、RPC、事件、Schema、生产者、消费者、网关和兼容版本。 |
| `architecture-adr-decision-workbench` | P0 | high | architecture-documentation-ide | 创建、关联、评审和失效 ADR，并连接代码、证据与替代方案。 |
| `architecture-intelligence-golden-route` | P0 | high | architecture-documentation-ide | 认证仓库阅读、架构恢复、在线审阅、调试和文档生成 Golden Route。 |
| `architecture-recovery-and-c4` | P0 | high | architecture-documentation-ide | 从代码、配置、部署和运行证据生成 C4 Context、Container、Component 与 Code 视图。 |
| `architecture-rule-violation-explorer` | P0 | high | architecture-documentation-ide | 展示跨层、循环、共享数据、依赖、权限和部署边界违规及修复建议。 |
| `business-process-bpmn-recovery` | P1 | high | architecture-documentation-ide | 从路由、状态机、数据库、事件和文档恢复 BPMN 或业务流程图。 |
| `call-sequence-control-flow-diagram` | P0 | medium | architecture-documentation-ide | 从入口到数据库、消息和外部服务生成调用、时序与控制流图。 |
| `change-impact-blast-radius-view` | P0 | high | architecture-documentation-ide | 根据语义图展示变更影响的调用方、数据、测试、消费者和部署对象。 |
| `code-explanation-and-question-answer` | P0 | high | architecture-documentation-ide | 基于可引用源码、图、测试和运行证据回答架构与实现问题。 |
| `data-flow-lineage-erd` | P0 | high | architecture-documentation-ide | 生成 ERD、字段级数据流、血缘、敏感性、质量和所有权视图。 |
| `deployment-network-topology-map` | P0 | medium | architecture-documentation-ide | 展示服务、容器、节点、区域、网络、端口、证书、数据库和依赖。 |
| `developer-onboarding-learning-path` | P1 | medium | architecture-documentation-ide | 按角色和任务生成可验证的仓库学习路径、练习和知识入口。 |
| `documentation-drift-verification` | P0 | medium | architecture-documentation-ide | 持续比较文档、图、API、Schema、配置和代码，标记过期与冲突。 |
| `domain-context-capability-map` | P1 | medium | architecture-documentation-ide | 恢复领域、Bounded Context、业务能力、实体、流程和上下游关系。 |
| `evidence-test-proof-risk-ui` | P0 | high | architecture-documentation-ide | 聚合测试、差分、证明、安全、性能、置信、失败和人工审批证据。 |
| `intermediate-revision-diff-viewer` | P0 | high | architecture-documentation-ide | 展示每个转换波次的源码、AST、IR、目标代码、测试和差异原因。 |
| `merge-conflict-semantic-assistant` | P0 | high | architecture-documentation-ide | 在 UI 中解释语义冲突、消费者影响、可选合并和验证结果。 |
| `mindmap-report-presentation-generation` | P1 | medium | architecture-documentation-ide | 生成项目思维导图、评估报告、迁移汇报和客户演示文稿。 |
| `module-dependency-layer-diagram` | P0 | medium | architecture-documentation-ide | 可视化模块、包、程序集、依赖方向、循环和架构规则违规。 |
| `online-code-editor-patch-review` | P0 | high | architecture-documentation-ide | 提供语义补全、Patch Stack、评论、建议、审批和按证据审阅能力。 |
| `remote-debug-breakpoint-session` | P1 | high | architecture-documentation-ide | 在隔离环境中提供断点、变量、线程、请求、容器和远程调试会话。 |
| `repository-onboarding-map` | P0 | medium | architecture-documentation-ide | 生成仓库入口、模块、构建、运行、测试、数据、部署和责任人的快速上手地图。 |
| `runbook-operations-support-doc` | P0 | high | architecture-documentation-ide | 生成部署、监控、告警、故障、备份、恢复、升级和支持 Runbook。 |
| `security-trust-threat-diagram` | P0 | critical | architecture-documentation-ide | 展示资产、身份、信任边界、数据流、攻击面、控制和未决风险。 |
| `semantic-search-code-navigation` | P0 | high | architecture-documentation-ide | 支持按符号、调用、数据流、事务、安全、需求和运行路径搜索导航。 |
| `source-ir-target-traceability-view` | P0 | high | architecture-documentation-ide | 可视化 Source Symbol、Semantic IR、Target Symbol、规则、证据和未决映射。 |
| `sql-explain-profile-workbench` | P1 | medium | architecture-documentation-ide | 提供 SQL、执行计划、统计、锁、索引、负载和跨数据库比较工作台。 |
| `symbol-call-dataflow-explorer` | P0 | high | architecture-documentation-ide | 交互探索定义、引用、调用、控制、数据、异常和污点传播。 |
| `task-plan-progress-critical-path-ui` | P0 | high | architecture-documentation-ide | 展示任务 DAG、当前节点、依赖、阻塞、检查点、成本和机器 ETA。 |
| `time-travel-task-replay` | P1 | high | architecture-documentation-ide | 按仓库、环境、模型、Skill、知识和工具快照重放任务与中间状态。 |
| `trace-log-metric-source-correlation` | P0 | high | architecture-documentation-ide | 把 Trace、Log、Metric、Profile、异常和 SQL 精确映射回源码与版本。 |

## AI Agent, RAG & ML Engineering / AI 工具项目生成与迁移

原子 Skill：**46**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `a2a-agent-discovery-messaging` | P1 | high | ai-agent-rag-ml | 生成 Agent-to-Agent 身份、发现、能力描述、消息、任务状态和信任策略。 |
| `adapter-lora-private-finetuning` | P1 | critical | ai-agent-rag-ml | 生成租户隔离 LoRA/Adapter 数据、训练、评测、签名、加载和撤回流程。 |
| `agent-memory-working-episodic-semantic` | P0 | high | ai-agent-rag-ml | 实现工作、情节、语义、程序和租户记忆的写入门、压缩、遗忘和回放。 |
| `agent-pause-resume-cancel` | P0 | high | ai-agent-rag-ml | 实现可持久化暂停、恢复、取消、人工审批和不可逆工具阻断。 |
| `agent-planner-executor-orchestration` | P0 | high | ai-agent-rag-ml | 生成 Planner、Executor、Verifier、Repairer、停止条件和任务状态机。 |
| `agent-rag-evaluation-harness` | P0 | high | ai-agent-rag-ml | 生成任务集、检索、工具、轨迹、结果、安全、成本和回归评测。 |
| `agent-rag-ml-golden-route` | P0 | high | ai-agent-rag-ml | 认证 AI Agent、RAG、私有训练、Serving 与安全运营的商业 Golden Route。 |
| `agui-streaming-human-interaction` | P1 | high | ai-agent-rag-ml | 生成 Agent UI 流式事件、进度、审批、表单、取消、恢复和证据展示。 |
| `ai-framework-cross-migration` | P1 | high | ai-agent-rag-ml | 在 Agent/RAG 框架间迁移 State、Tool、Memory、Checkpoint、Trace 与部署契约。 |
| `ai-project-requirement-and-risk-contract` | P0 | high | ai-agent-rag-ml | 定义任务、用户、数据、工具、副作用、质量、延迟、成本、隐私和人工接管契约。 |
| `ai-system-e0-e5-certification` | P0 | high | ai-agent-rag-ml | 认证数据权利、检索、工具、模型、Agent、部署、人工监督和长期漂移。 |
| `autogen-crewai-project-generation` | P1 | high | ai-agent-rag-ml | 生成 AutoGen 或 CrewAI 的角色、任务、Tool、Memory、流程和评测项目。 |
| `code-agent-repository-harness` | P0 | high | ai-agent-rag-ml | 生成仓库读取、Patch、Shell、构建、测试、恢复、证据和权限受控的编码 Agent Harness。 |
| `dataset-curation-sft-dpo-rlvr` | P1 | high | ai-agent-rag-ml | 生成数据分层、SFT、偏好对、可验证奖励、泄漏防护和训练血缘。 |
| `dify-project-generation` | P1 | high | ai-agent-rag-ml | 生成 Dify 应用、Workflow、知识库、Tool、变量、环境、评测与部署配置。 |
| `durable-agent-workflow-temporal` | P0 | high | ai-agent-rag-ml | 把长任务编排为持久 Workflow、Activity、Retry、Signal、Checkpoint 和补偿。 |
| `embedding-model-index-migration` | P0 | critical | ai-agent-rag-ml | 管理 Embedding、维度、归一化、索引重建、双索引和在线迁移。 |
| `feature-store-training-serving` | P1 | critical | ai-agent-rag-ml | 生成 Feature 定义、离线/在线同步、时间正确性、服务和监控。 |
| `graph-rag-knowledge-graph` | P1 | high | ai-agent-rag-ml | 生成实体、关系、社区、路径、证据图和图检索规划。 |
| `hallucination-uncertainty-abstention` | P0 | high | ai-agent-rag-ml | 校准事实、代码、工具和证据不确定性，触发回读、验证、拒绝或人工升级。 |
| `hybrid-search-reranker` | P0 | high | ai-agent-rag-ml | 融合全文、向量、符号、图和任务专用 Reranker，并构造困难负样本。 |
| `langchain-project-generation` | P1 | high | ai-agent-rag-ml | 生成 LangChain 模型、Prompt、Retriever、Tool、Agent、Callback、Eval 与部署项目。 |
| `langgraph-project-generation` | P0 | high | ai-agent-rag-ml | 生成 LangGraph State、Node、Edge、Checkpoint、Interrupt、Subgraph 和持久执行项目。 |
| `llm-observability-tracing-cost` | P0 | high | ai-agent-rag-ml | 记录模型、Prompt 版本、Token、缓存、延迟、工具、质量和成本但默认不泄露内容。 |
| `mcp-server-client-integration` | P0 | high | ai-agent-rag-ml | 生成 MCP Server、Client、Resource、Prompt、Tool、权限、生命周期和审计集成。 |
| `mlflow-model-registry-pipeline` | P1 | critical | ai-agent-rag-ml | 生成实验、Artifact、Model Registry、Stage、审批、发布和回滚流水线。 |
| `model-drift-shadow-canary-rollback` | P0 | critical | ai-agent-rag-ml | 监控输入、输出、质量、成本和安全漂移并执行影子、金丝雀和整体回滚。 |
| `model-provider-abstraction-gateway` | P0 | critical | ai-agent-rag-ml | 统一多模型 Provider、能力、上下文、工具、结构化输出、计费、错误和回退。 |
| `model-routing-cost-latency-quality` | P0 | critical | ai-agent-rag-ml | 按能力、风险、租户、延迟、成本、上下文和可用性选择模型组合。 |
| `model-serving-vllm-kserve` | P1 | critical | ai-agent-rag-ml | 生成高吞吐模型服务、Batch、量化、Adapter、健康、扩缩容和金丝雀部署。 |
| `multi-agent-role-topology` | P1 | high | ai-agent-rag-ml | 设计 Supervisor、Specialist、Debate、Blackboard、隔离上下文和冲突仲裁。 |
| `openai-agents-sdk-project` | P0 | high | ai-agent-rag-ml | 生成基于 OpenAI Agents SDK 的 Agent、Tool、Handoff、Guardrail、Trace 与评测项目。 |
| `pi-harness-openclaw-integration` | P1 | high | ai-agent-rag-ml | 生成 Pi、Harness 或 OpenClaw 类编码 Agent 的仓库、工具、权限和执行集成。 |
| `private-offline-ai-deployment` | P0 | critical | ai-agent-rag-ml | 生成私有、离线、国产或混合模型部署，包含模型包、知识、Adapter、许可证和更新。 |
| `prompt-injection-jailbreak-defense` | P0 | high | ai-agent-rag-ml | 防御直接与间接注入、越权工具、数据外传、角色混淆和持久污染。 |
| `prompt-kv-semantic-cache` | P0 | high | ai-agent-rag-ml | 实现 Prompt、Prefix/KV、检索、工具结果和语义缓存的安全失效。 |
| `prompt-template-version-test` | P0 | high | ai-agent-rag-ml | 版本化 Prompt、System Policy、Few-shot、变量、差分评测和回滚。 |
| `rag-chunking-structure-semantic` | P0 | high | ai-agent-rag-ml | 按文档结构、代码符号、调用、数据流和版本生成可引用语义分片。 |
| `rag-freshness-conflict-security` | P0 | critical | ai-agent-rag-ml | 处理知识时效、冲突、注入、不可信内容和敏感上下文泄漏。 |
| `rag-source-ingestion-pipeline` | P0 | high | ai-agent-rag-ml | 生成文档、代码、数据库、API、日志和多模态知识的增量摄取与血缘。 |
| `retrieval-citation-grounding` | P0 | high | ai-agent-rag-ml | 让关键结论绑定来源、版本、位置和权限，并检测引用不支持。 |
| `spring-ai-project-generation` | P0 | high | ai-agent-rag-ml | 生成 Spring AI Model、Prompt、Advisor、Vector Store、Tool、RAG、测试和观测项目。 |
| `structured-output-schema-constrained` | P0 | high | ai-agent-rag-ml | 生成 JSON Schema、Grammar、类型化解析、修复和拒绝非法结构输出。 |
| `tool-function-schema-generation` | P0 | high | ai-agent-rag-ml | 从 API、SDK、服务和权限生成 Tool Schema、参数验证、幂等和副作用声明。 |
| `tool-permission-approval-sandbox` | P0 | critical | ai-agent-rag-ml | 实现默认拒绝、参数级权限、环境所有权、审批、沙箱和短期凭据。 |
| `vector-database-adapter` | P0 | medium | ai-agent-rag-ml | 适配向量数据库的 Namespace、Filter、Hybrid、备份、租户隔离和成本。 |

## Legacy & Mainframe Modernization / 主机与遗留平台现代化

原子 Skill：**40**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `aspnet-webforms-core-migration` | P0 | high | legacy-mainframe-modernization | 迁移 WebForms Page Lifecycle、ViewState、PostBack、Control 和事件到 ASP.NET Core。 |
| `batch-online-transaction-equivalence` | P0 | critical | legacy-mainframe-modernization | 验证批处理与联机事务的共享数据、Cutoff、顺序、重试和结算语义。 |
| `binary-copybook-screen-report-ingestion` | P0 | high | legacy-mainframe-modernization | 摄取 Load Module、Copybook、BMS/Screen、报表模板和缺失源码的结构证据。 |
| `cics-transaction-screen-migration` | P0 | critical | legacy-mainframe-modernization | 迁移 CICS Transaction、COMMAREA、BMS、Pseudo-conversation、Syncpoint 和错误。 |
| `cl-command-job-migration` | P1 | high | legacy-mainframe-modernization | 迁移 IBM i CL Command、Job、Library List、Message Queue 和对象权限。 |
| `classic-asp-com-web-migration` | P1 | high | legacy-mainframe-modernization | 迁移 Classic ASP、Session、COM Component、ADO、Include 和页面脚本。 |
| `cobol-batch-file-io-conversion` | P0 | high | legacy-mainframe-modernization | 迁移 Sequential、Indexed、Relative 文件、Sort/Merge、Checkpoint 和批量错误。 |
| `cobol-copybook-data-model-migration` | P0 | critical | legacy-mainframe-modernization | 迁移 Copybook、REDEFINES、OCCURS、COMP、Packed Decimal 和记录布局。 |
| `cobol-program-semantic-ir` | P0 | high | legacy-mainframe-modernization | 解析 Division、Section、Paragraph、PERFORM、GO TO、Condition Name 和文件操作。 |
| `coldfusion-web-migration` | P2 | high | legacy-mainframe-modernization | 迁移 ColdFusion Template、Tag、Query、Session、Component 和调度。 |
| `com-dcom-activex-modernization` | P1 | high | legacy-mainframe-modernization | 替换 COM、DCOM、ActiveX、Registry、Apartment、Marshal 和部署依赖。 |
| `corba-idl-service-modernization` | P1 | high | legacy-mainframe-modernization | 迁移 CORBA IDL、ORB、Naming、Exception、Object Lifecycle 和协议桥。 |
| `data-cutover-cdc-reconciliation` | P0 | critical | legacy-mainframe-modernization | 组织全量、CDC、追平、对账、冻结、回退和历史归档。 |
| `db2-mainframe-sql-routine-migration` | P0 | high | legacy-mainframe-modernization | 迁移 DB2 Package、Bind、Cursor、SQLCODE、Stored Procedure 和数据访问。 |
| `delphi-vcl-database-migration` | P1 | high | legacy-mainframe-modernization | 迁移 Delphi VCL、Component、Event、Dataset、COM 和 Native 资源。 |
| `dotnet-framework-core-migration` | P0 | high | legacy-mainframe-modernization | 迁移 .NET Framework、AppDomain、配置、程序集、API 和依赖到现代 .NET。 |
| `dual-run-shadow-output-compare` | P0 | high | legacy-mainframe-modernization | 并行运行旧新系统并比较报表、文件、数据库、消息和用户流程。 |
| `foxpro-data-form-report-migration` | P1 | high | legacy-mainframe-modernization | 迁移 FoxPro DBF、Index、Form、Report、Macro 和并发访问。 |
| `ims-db-dc-hierarchy-migration` | P1 | high | legacy-mainframe-modernization | 迁移 IMS DB Hierarchy、PCB、SSA、DL/I、IMS DC 消息和事务语义。 |
| `informix-4gl-app-modernization` | P1 | high | legacy-mainframe-modernization | 迁移 Informix 4GL、Form、Report、Database、Cursor 和事务逻辑。 |
| `jcl-job-step-scheduler-migration` | P0 | high | legacy-mainframe-modernization | 迁移 JCL Job、Step、PROC、DD、Condition、Restart、Dataset 和调度依赖。 |
| `job-restart-checkpoint-semantics` | P0 | high | legacy-mainframe-modernization | 保持作业 Restart、Checkpoint、Dataset Generation、幂等和部分提交。 |
| `legacy-emulation-characterization` | P0 | high | legacy-mainframe-modernization | 在仿真器或隔离环境中捕获遗留输入输出、错误、性能和副作用。 |
| `legacy-estate-inventory-and-dependency` | P0 | medium | legacy-mainframe-modernization | 盘点程序、作业、屏幕、报表、文件、数据库、接口、调度、容量和业务关键度。 |
| `legacy-modernization-golden-route` | P0 | high | legacy-mainframe-modernization | 认证主机、客户端服务器和专有平台渐进现代化的商业 Golden Route。 |
| `legacy-performance-capacity-baseline` | P0 | high | legacy-mainframe-modernization | 建立 MIPS、CPU、批窗口、IO、事务吞吐、延迟和许可成本基线。 |
| `legacy-risk-compliance-evidence` | P0 | high | legacy-mainframe-modernization | 生成业务规则、数据、控制、审批、审计和迁移风险证据。 |
| `mainframe-encoding-ebcdic-unicode` | P0 | high | legacy-mainframe-modernization | 保持 EBCDIC、Code Page、DBCS、排序、填充和 Unicode 转换。 |
| `oracle-forms-reports-migration` | P0 | high | legacy-mainframe-modernization | 迁移 Oracle Forms、Trigger、Block、Canvas、PL/SQL 和 Reports 输出。 |
| `packed-decimal-numeric-equivalence` | P0 | high | legacy-mainframe-modernization | 保持 Packed/Zoned Decimal、Sign、Scale、Overflow 和舍入行为。 |
| `pli-program-conversion` | P1 | high | legacy-mainframe-modernization | 迁移 PL/I 数据、Condition、Storage、Procedure、IO 和并发语义。 |
| `powerbuilder-datawindow-migration` | P0 | high | legacy-mainframe-modernization | 迁移 PowerBuilder Window、DataWindow、Event、Transaction Object 和脚本。 |
| `proprietary-esb-bpm-modernization` | P1 | high | legacy-mainframe-modernization | 迁移厂商 ESB/BPM 流程、Adapter、映射、补偿和人工任务。 |
| `rpg-as400-program-migration` | P1 | high | legacy-mainframe-modernization | 迁移 RPG Fixed/Free Form、Record Format、Indicator、Data Area 和作业语义。 |
| `sap-abap-code-data-interface-migration` | P1 | high | legacy-mainframe-modernization | 迁移 ABAP Report、Function、Class、BAPI、IDoc、Table 和授权检查。 |
| `strangler-api-and-event-facade` | P0 | high | legacy-mainframe-modernization | 通过 API、事件、Screen Facade 和数据同步渐进替换遗留能力。 |
| `terminal-screen-web-ui-modernization` | P0 | high | legacy-mainframe-modernization | 把 3270/5250/终端 Screen 流程迁移为 Web/API 并保持导航和字段规则。 |
| `vb6-form-com-ado-migration` | P0 | high | legacy-mainframe-modernization | 迁移 VB6 Form、Event、COM、ActiveX、ADO、Variant、Error 和部署。 |
| `vsam-file-index-migration` | P1 | high | legacy-mainframe-modernization | 迁移 VSAM KSDS/ESDS/RRDS、Key、Alternate Index、锁和恢复。 |
| `wcf-remoting-grpc-rest-migration` | P0 | high | legacy-mainframe-modernization | 迁移 WCF、.NET Remoting、Binding、Contract、Fault 和安全到 gRPC/REST。 |

## Industrial IoT, Edge & Robotics / 工业边缘与机器人

原子 Skill：**32**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `can-bus-signal-dbc-mapping` | P1 | medium | industrial-iot-robotics | 解析 CAN/CAN-FD、DBC、Signal、Endian、Scaling、周期、错误和总线负载。 |
| `cloud-edge-orchestration` | P1 | high | industrial-iot-robotics | 编排模型、应用、配置、数据、资源和策略在云边设备间的部署。 |
| `device-driver-hardware-abstraction` | P0 | high | industrial-iot-robotics | 建立 Driver、HAL、模拟器、版本、Capability 和故障隔离边界。 |
| `device-shadow-digital-twin` | P0 | high | industrial-iot-robotics | 生成 Desired/Reported State、Twin Model、Command、Event、版本和一致性。 |
| `edge-offline-store-forward` | P0 | high | industrial-iot-robotics | 实现断网缓存、Store-and-forward、顺序、去重、追平和冲突处理。 |
| `ethercat-profinet-industrial-ethernet` | P1 | high | industrial-iot-robotics | 映射 EtherCAT、PROFINET 等实时工业以太网设备、周期和诊断。 |
| `fault-injection-diagnostics` | P0 | high | industrial-iot-robotics | 注入传感器、执行器、网络、时钟、电源和软件故障并验证诊断覆盖。 |
| `field-rollout-canary-rollback` | P0 | critical | industrial-iot-robotics | 按设备组、工厂、地域和风险执行现场金丝雀、观察、回滚和隔离。 |
| `fleet-device-identity-certificate` | P0 | critical | industrial-iot-robotics | 管理设备身份、证书、Provision、轮换、吊销、所有权和租户隔离。 |
| `functional-safety-evidence-pack` | P0 | critical | industrial-iot-robotics | 组织 Hazard、Requirement、Design、Test、Trace、变更和残余风险证据。 |
| `historian-time-series-migration` | P0 | high | industrial-iot-robotics | 迁移 Historian、时间序列、压缩、插值、质量码、补数和保留。 |
| `industrial-cybersecurity-segmentation` | P0 | critical | industrial-iot-robotics | 设计区域与通道、白名单、跳板、协议网关、补丁和远程维护安全。 |
| `industrial-iot-robotics-golden-route` | P0 | high | industrial-iot-robotics | 认证工业协议、边缘、ROS、数字孪生、SIL/HIL 与现场发布 Golden Route。 |
| `industrial-observability-trace` | P0 | high | industrial-iot-robotics | 关联设备、协议、控制命令、任务、日志、Metric、Trace 和物理事件。 |
| `industrial-system-asset-inventory` | P0 | medium | industrial-iot-robotics | 盘点 PLC、设备、机器人、网关、SCADA、协议、网络、固件、证书和安全等级。 |
| `mission-workflow-state-machine` | P0 | high | industrial-iot-robotics | 生成任务、状态机、暂停、恢复、抢占、取消、补偿和人工接管。 |
| `modbus-register-semantic-mapping` | P0 | medium | industrial-iot-robotics | 映射 Modbus Coil、Register、Address、Endian、Scaling、Polling 和异常码。 |
| `mqtt-topic-qos-retain-session` | P0 | high | industrial-iot-robotics | 设计 MQTT Topic、QoS、Retain、Session、Will、ACL、Offline Queue 和重连。 |
| `opcua-node-model-client-server` | P0 | critical | industrial-iot-robotics | 生成或迁移 OPC UA NodeSet、Namespace、Browse、Subscription、Method 和安全通道。 |
| `ota-firmware-config-update` | P0 | critical | industrial-iot-robotics | 实现签名固件、配置、分批 OTA、断点、回滚、防降级和设备兼容。 |
| `plc-iec61131-interface-integration` | P1 | high | industrial-iot-robotics | 连接 IEC 61131-3 程序、变量、Function Block、周期和上位机接口。 |
| `predictive-maintenance-data-pipeline` | P1 | high | industrial-iot-robotics | 生成设备特征、标签、异常、剩余寿命、模型服务和反馈闭环。 |
| `protocol-topology-tag-model-recovery` | P0 | critical | industrial-iot-robotics | 恢复设备、Tag、Address、Unit、Sampling、Command、Alarm 和通信拓扑。 |
| `realtime-deadline-jitter-analysis` | P0 | high | industrial-iot-robotics | 分析周期、Deadline、Jitter、优先级反转、资源争用和最坏执行时间。 |
| `robot-upper-computer-architecture` | P0 | high | industrial-iot-robotics | 生成机器人上位机设备管理、任务、状态、告警、遥测、权限和 UI 架构。 |
| `ros1-ros2-node-topic-service-migration` | P0 | high | industrial-iot-robotics | 迁移 ROS1 Node、Topic、Service、Parameter、Launch 和 TF 到 ROS2。 |
| `ros2-action-lifecycle-qos` | P0 | high | industrial-iot-robotics | 设计 ROS2 Action、Lifecycle、QoS、Executor、Composition 和故障恢复。 |
| `safety-interlock-failsafe-state` | P0 | critical | industrial-iot-robotics | 实现 Interlock、Emergency Stop、Fail-safe、Degraded Mode 和恢复许可。 |
| `scada-hmi-tag-alarm-migration` | P0 | high | industrial-iot-robotics | 迁移 SCADA/HMI Tag、画面、Alarm、Ack、Trend、权限和操作审计。 |
| `sensor-calibration-unit-time-sync` | P0 | high | industrial-iot-robotics | 管理标定、单位、坐标系、精度、漂移、时间同步和数据质量码。 |
| `simulation-sil-hil-environment` | P0 | high | industrial-iot-robotics | 生成仿真、Software-in-loop、Hardware-in-loop、虚拟设备和可重复场景。 |
| `telemetry-command-control-channel` | P0 | high | industrial-iot-robotics | 分离遥测与控制，设计认证、优先级、Ack、超时、审计和安全状态。 |

## Language & Build Runtime Adapters / 语言运行时适配矩阵

原子 Skill：**36**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `abap-language-adapter` | P1 | medium | language-runtime-adapters | 适配 ABAP Dictionary、Report、Class、BAPI、IDoc、Transport 和测试。 |
| `bundler-ruby-build-adapter` | P1 | medium | language-runtime-adapters | 适配 Gem、Bundler、Native Extension、Ruby 版本和测试运行。 |
| `c-language-adapter` | P0 | medium | language-runtime-adapters | 适配 C 预处理、Pointer、Struct、ABI、Make/CMake、Sanitizer 和调试。 |
| `cargo-rustup-build-adapter` | P0 | medium | language-runtime-adapters | 适配 Cargo、Workspace、Feature、Build Script、Rustup、Target 和缓存。 |
| `cmake-bazel-meson-ninja-adapter` | P0 | medium | language-runtime-adapters | 适配 CMake、Bazel、Meson、Ninja 的目标图、Toolchain 和增量构建。 |
| `cobol-language-adapter` | P1 | medium | language-runtime-adapters | 适配 COBOL 数据布局、控制流、文件、CICS/DB2、Compiler 和仿真。 |
| `composer-php-build-adapter` | P1 | medium | language-runtime-adapters | 适配 Composer、Packagist、Extension、Autoload、Script 和部署构建。 |
| `cpp-language-adapter` | P0 | medium | language-runtime-adapters | 适配 C++ Template、RAII、Exception、Module、ABI、构建、测试和分析。 |
| `csharp-dotnet-language-adapter` | P0 | medium | language-runtime-adapters | 适配 C# 类型、LINQ、Task、Attribute、Assembly、.NET Runtime、构建和测试。 |
| `dart-flutter-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Dart 类型、Future、Isolate、Package、Flutter Widget、Build 和测试。 |
| `dotnet-msbuild-nuget-adapter` | P0 | medium | language-runtime-adapters | 适配 MSBuild、Solution、Project、NuGet、Target Framework、RID 和发布。 |
| `fsharp-dotnet-language-adapter` | P1 | medium | language-runtime-adapters | 适配 F# Discriminated Union、Computation Expression、Module 和 .NET 互操作。 |
| `go-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Go Interface、Goroutine、Channel、Context、Module、Build Tag 和测试。 |
| `go-modules-workspace-adapter` | P0 | medium | language-runtime-adapters | 适配 Go Modules、Workspace、Proxy、Vendor、Build Tag 和跨平台构建。 |
| `groovy-jvm-language-adapter` | P1 | medium | language-runtime-adapters | 适配 Groovy 动态分派、Closure、MetaClass、AST Transform、Gradle 与测试。 |
| `java-jvm-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Java 源码、字节码、模块、注解、反射、JVM、调试、构建和测试。 |
| `javascript-language-adapter` | P0 | medium | language-runtime-adapters | 适配 JavaScript 动态对象、Prototype、Promise、Module、Bundler 和测试。 |
| `kotlin-jvm-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Kotlin 空安全、扩展、协程、DSL、Metadata、JVM 互操作和构建。 |
| `language-adapter-conformance-matrix` | P0 | medium | language-runtime-adapters | 对语言版本、OS、CPU、编译器、构建、调试、测试和 Semantic IR 执行矩阵认证。 |
| `lua-language-adapter` | P2 | medium | language-runtime-adapters | 适配 Lua Table、Metatable、Coroutine、C API、Module 和嵌入式运行时。 |
| `make-autotools-build-adapter` | P1 | medium | language-runtime-adapters | 适配 Make、Autoconf、Automake、Configure、交叉编译和系统依赖。 |
| `matlab-language-adapter` | P2 | medium | language-runtime-adapters | 适配 MATLAB Array、Script、Function、Toolbox、Codegen 和数值测试。 |
| `maven-gradle-ant-build-adapter` | P0 | medium | language-runtime-adapters | 适配 Maven、Gradle、Ant 的模块、依赖、Plugin、Profile、缓存和离线构建。 |
| `npm-pnpm-yarn-bun-adapter` | P0 | medium | language-runtime-adapters | 适配 Node 包管理、Workspace、Lock、Script、Registry、Bundler 和缓存。 |
| `objectivec-language-adapter` | P1 | medium | language-runtime-adapters | 适配 Objective-C Runtime、Message、Category、KVC/KVO、ARC 和 Xcode。 |
| `php-language-adapter` | P1 | medium | language-runtime-adapters | 适配 PHP 动态类型、Composer、Extension、Request Lifecycle、框架和测试。 |
| `python-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Python 动态类型、Typing、Decorator、Async、Packaging、Virtualenv 和测试。 |
| `python-uv-poetry-pip-adapter` | P0 | medium | language-runtime-adapters | 适配 uv、Poetry、pip、Wheel、Lock、Index、Environment 和构建。 |
| `r-language-adapter` | P2 | medium | language-runtime-adapters | 适配 R Vector、Data Frame、Package、Formula、Native Extension 和测试。 |
| `ruby-language-adapter` | P1 | medium | language-runtime-adapters | 适配 Ruby 动态分派、Meta-programming、Gem、Bundler、Rails 和测试。 |
| `rust-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Rust Ownership、Lifetime、Trait、Macro、Async、Cargo、Unsafe 和测试。 |
| `scala-jvm-language-adapter` | P1 | medium | language-runtime-adapters | 适配 Scala 类型、Trait、Implicit/Given、Macro、Future、SBT 和 JVM 互操作。 |
| `sql-procedural-language-adapter` | P0 | medium | language-runtime-adapters | 适配 SQL、PL/SQL、T-SQL、PL/pgSQL、SQL PL 与数据库执行环境。 |
| `swift-language-adapter` | P0 | medium | language-runtime-adapters | 适配 Swift Protocol、Optional、Concurrency、ARC、Package、Xcode 和测试。 |
| `swiftpm-cocoapods-xcode-adapter` | P0 | medium | language-runtime-adapters | 适配 SwiftPM、CocoaPods、Xcode Project、Scheme、Signing 和测试。 |
| `typescript-language-adapter` | P0 | medium | language-runtime-adapters | 适配 TypeScript 类型、Declaration、Decorator、Module、Build 和前后端运行时。 |

## Database Engine Adapters / 数据库引擎适配矩阵

原子 Skill：**24**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `bigquery-database-adapter` | P1 | medium | database-engine-adapters | 适配 BigQuery Standard SQL、Partition、Cluster、Slot、权限、成本和导入导出。 |
| `cassandra-scylladb-adapter` | P1 | medium | database-engine-adapters | 适配 Cassandra/Scylla CQL、Partition、Consistency、Compaction、Repair 和容量。 |
| `clickhouse-database-adapter` | P1 | medium | database-engine-adapters | 适配 ClickHouse Engine、MergeTree、Partition、Materialized View、集群和查询。 |
| `dameng-database-adapter` | P1 | medium | database-engine-adapters | 适配达梦数据库方言、兼容模式、Routine、权限、备份和驱动。 |
| `database-adapter-certification-matrix` | P0 | medium | database-engine-adapters | 对引擎版本、驱动、事务、SQL、Routine、复制、备份和性能执行矩阵认证。 |
| `database-driver-orm-compatibility` | P0 | high | database-engine-adapters | 验证 JDBC、ADO.NET、ODBC、Native Driver、ORM 方言、连接池和错误映射。 |
| `db2-database-adapter` | P1 | medium | database-engine-adapters | 适配 DB2 LUW/z、SQL PL、Package、Tablespace、HADR、权限和驱动。 |
| `dynamodb-document-adapter` | P1 | medium | database-engine-adapters | 适配 DynamoDB Key、Index、Condition、Transaction、Stream、容量和全局表。 |
| `elasticsearch-opensearch-adapter` | P1 | medium | database-engine-adapters | 适配 Elasticsearch/OpenSearch Mapping、Analyzer、Query、Index Lifecycle 和集群。 |
| `kingbase-database-adapter` | P1 | medium | database-engine-adapters | 适配人大金仓数据库方言、兼容模式、Routine、权限、备份和驱动。 |
| `mongodb-database-adapter` | P1 | medium | database-engine-adapters | 适配 MongoDB Document、Index、Transaction、Aggregation、Change Stream 和分片。 |
| `mysql-mariadb-database-adapter` | P0 | medium | database-engine-adapters | 适配 MySQL/MariaDB SQL Mode、InnoDB、GTID、Routine、权限和复制。 |
| `neo4j-graph-adapter` | P1 | medium | database-engine-adapters | 适配 Neo4j Property Graph、Cypher、Index、Constraint、Transaction 和备份。 |
| `oceanbase-database-adapter` | P1 | medium | database-engine-adapters | 适配 OceanBase MySQL/Oracle 模式、租户、分区、事务、备份和迁移。 |
| `oracle-database-adapter` | P0 | medium | database-engine-adapters | 适配 Oracle SQL、PL/SQL、Package、RAC、Data Guard、权限、备份和驱动。 |
| `postgresql-database-adapter` | P0 | medium | database-engine-adapters | 适配 PostgreSQL SQL、PL/pgSQL、Extension、Logical Replication、RLS 和运维。 |
| `redis-keyvalue-adapter` | P0 | medium | database-engine-adapters | 适配 Redis 数据结构、TTL、Lua、Transaction、Cluster、Persistence 和权限。 |
| `redshift-database-adapter` | P1 | medium | database-engine-adapters | 适配 Redshift Distribution、Sort Key、Spectrum、WLM、权限和运维。 |
| `snowflake-database-adapter` | P1 | medium | database-engine-adapters | 适配 Snowflake Warehouse、Task、Stream、Time Travel、Sharing、成本和权限。 |
| `sqlite-database-adapter` | P1 | medium | database-engine-adapters | 适配 SQLite 类型亲和、事务、WAL、并发、扩展和嵌入式备份。 |
| `sqlserver-database-adapter` | P0 | medium | database-engine-adapters | 适配 SQL Server T-SQL、Agent、Always On、权限、备份、驱动和执行计划。 |
| `sybase-ase-database-adapter` | P1 | medium | database-engine-adapters | 适配 Sybase ASE、Transact-SQL、TempDB、Replication、锁和备份。 |
| `teradata-database-adapter` | P1 | medium | database-engine-adapters | 适配 Teradata 分布、AMP、BTEQ、Macro、统计、Workload 和权限。 |
| `tidb-database-adapter` | P1 | medium | database-engine-adapters | 适配 TiDB MySQL 兼容、分布事务、Placement、TiFlash、CDC 和运维。 |

## Framework & Runtime Adapters / 框架平台适配矩阵

原子 Skill：**36**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `airflow-dagster-adapter` | P1 | medium | framework-runtime-adapters | 适配 Airflow/Dagster 作业、资产、调度、Backfill、Retry 和观测。 |
| `android-compose-adapter` | P1 | medium | framework-runtime-adapters | 适配 Android View/Compose、Lifecycle、Navigation、Permission、Gradle 和测试。 |
| `angular-adapter` | P1 | medium | framework-runtime-adapters | 适配 Angular Component、Signal、DI、Router、Form、RxJS 和构建。 |
| `dbt-adapter` | P1 | medium | framework-runtime-adapters | 适配 dbt Model、Macro、Test、Snapshot、Documentation 和 Warehouse Profile。 |
| `dify-agent-platform-adapter` | P1 | medium | framework-runtime-adapters | 适配 Dify 应用、Workflow、Knowledge、Tool、Variable、API 和部署。 |
| `django-adapter` | P1 | medium | framework-runtime-adapters | 适配 Django Model、View、Template、Middleware、Admin、Migration 和测试。 |
| `dotnet-aspnetcore-adapter` | P0 | medium | framework-runtime-adapters | 适配 ASP.NET Core、DI、Middleware、MVC、Minimal API、EF Core 和 Hosting。 |
| `dotnet-framework-webforms-adapter` | P1 | medium | framework-runtime-adapters | 适配 .NET Framework、WebForms、WCF、Remoting、AppDomain 和配置。 |
| `electron-tauri-adapter` | P1 | medium | framework-runtime-adapters | 适配 Electron/Tauri 主进程、渲染进程、IPC、Native、安全和打包。 |
| `express-nestjs-adapter` | P0 | medium | framework-runtime-adapters | 适配 Express/NestJS Route、Middleware、DI、Decorator、Validation 和模块。 |
| `flask-fastapi-adapter` | P1 | medium | framework-runtime-adapters | 适配 Flask/FastAPI Route、Dependency、Pydantic、Async、Middleware 和部署。 |
| `flutter-adapter` | P0 | medium | framework-runtime-adapters | 适配 Flutter Widget、State、Navigation、Plugin、Platform Channel 和多端构建。 |
| `framework-adapter-certification-matrix` | P0 | medium | framework-runtime-adapters | 对框架版本、运行时、构建、配置、插件、测试和目标转换执行矩阵认证。 |
| `graphql-adapter` | P1 | medium | framework-runtime-adapters | 适配 GraphQL Schema、Resolver、DataLoader、Subscription、Auth 和代码生成。 |
| `grpc-adapter` | P0 | medium | framework-runtime-adapters | 适配 gRPC、Proto、Streaming、Interceptor、Deadline、Error 和代码生成。 |
| `hibernate-jpa-adapter` | P0 | medium | framework-runtime-adapters | 适配 Hibernate/JPA Entity、Mapping、Query、Transaction、Cache 和生命周期。 |
| `ios-swiftui-adapter` | P1 | medium | framework-runtime-adapters | 适配 UIKit/SwiftUI、Lifecycle、Navigation、Combine、Package、Signing 和测试。 |
| `jakartaee-javaee-adapter` | P0 | medium | framework-runtime-adapters | 适配 Java EE/Jakarta EE、Servlet、EJB、JPA、JAX-RS、JAX-WS、CDI 和容器。 |
| `jsf-adapter` | P1 | medium | framework-runtime-adapters | 适配 JSF Component、Managed Bean、Facelets、Navigation、State 和生命周期。 |
| `kafka-pulsar-rabbit-adapter` | P0 | medium | framework-runtime-adapters | 适配 Kafka、Pulsar、RabbitMQ 的生产、消费、事务、重试、顺序和监控。 |
| `kubernetes-helm-adapter` | P0 | medium | framework-runtime-adapters | 适配 Kubernetes Resource、Helm Chart、Kustomize、Operator 和发布。 |
| `langchain-langgraph-adapter` | P0 | medium | framework-runtime-adapters | 适配 LangChain/LangGraph Model、Tool、State、Memory、Checkpoint 和 Trace。 |
| `laravel-symfony-adapter` | P1 | medium | framework-runtime-adapters | 适配 Laravel/Symfony DI、Route、ORM、Queue、Middleware、Console 和测试。 |
| `mybatis-adapter` | P0 | medium | framework-runtime-adapters | 适配 MyBatis/iBATIS Mapper、XML、Dynamic SQL、Plugin、Cache 和事务。 |
| `nextjs-react-adapter` | P0 | medium | framework-runtime-adapters | 适配 Next.js App Router、React Server/Client Component、Data Fetching 和部署。 |
| `qt-cpp-adapter` | P1 | medium | framework-runtime-adapters | 适配 Qt Object、Signal/Slot、Widget/QML、Resource、Build 和跨平台部署。 |
| `rails-adapter` | P1 | medium | framework-runtime-adapters | 适配 Rails Model、Controller、Route、Migration、Job、Callback 和测试。 |
| `react-native-adapter` | P1 | medium | framework-runtime-adapters | 适配 React Native Component、Bridge、Navigation、Native Module 和构建。 |
| `servlet-jsp-adapter` | P0 | medium | framework-runtime-adapters | 适配 Servlet、Filter、Listener、JSP、JSTL、Taglib、EL 和容器描述符。 |
| `spark-flink-beam-adapter` | P1 | medium | framework-runtime-adapters | 适配 Spark、Flink、Beam 的批流、State、Window、Checkpoint 和部署。 |
| `spring-ai-adapter` | P0 | medium | framework-runtime-adapters | 适配 Spring AI Model、Advisor、Tool、Vector Store、RAG、Observability 和测试。 |
| `spring-framework-adapter` | P0 | medium | framework-runtime-adapters | 适配 Spring Core、Boot、MVC、WebFlux、Security、Data、Batch、Integration 和 Actuator。 |
| `struts1-adapter` | P0 | medium | framework-runtime-adapters | 适配 Struts 1 Config、Action、Form、Forward、Validator、Tiles 和插件。 |
| `struts2-adapter` | P0 | medium | framework-runtime-adapters | 适配 Struts 2 Action、Interceptor、ValueStack、OGNL、Result 和 Convention。 |
| `terraform-pulumi-adapter` | P0 | medium | framework-runtime-adapters | 适配 Terraform/Pulumi Resource、State、Module、Provider、Plan 和 Drift。 |
| `vue-nuxt-adapter` | P0 | medium | framework-runtime-adapters | 适配 Vue、Nuxt、Composition、SSR、Route、State、Plugin 和构建。 |

## Cloud & Deployment Platform Adapters / 云平台适配矩阵

原子 Skill：**16**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `alibaba-cloud-adapter` | P1 | medium | cloud-platform-adapters | 适配阿里云身份、VPC、计算、OSS、数据库、消息、函数、监控和成本。 |
| `aws-cloud-adapter` | P1 | medium | cloud-platform-adapters | 适配 AWS 身份、网络、计算、存储、数据库、消息、Serverless、监控和成本。 |
| `azure-cloud-adapter` | P1 | medium | cloud-platform-adapters | 适配 Azure 身份、网络、计算、存储、数据库、消息、Functions、监控和成本。 |
| `baremetal-edge-adapter` | P0 | medium | cloud-platform-adapters | 适配裸机、PXE、镜像、驱动、边缘节点、离线、远程运维和资源限制。 |
| `cloud-platform-exit-portability` | P0 | high | cloud-platform-adapters | 生成数据、配置、身份、服务替代、出口带宽、回迁和多云切换证据。 |
| `gcp-cloud-adapter` | P1 | medium | cloud-platform-adapters | 适配 GCP 身份、网络、计算、存储、数据库、消息、Cloud Run、监控和成本。 |
| `huawei-cloud-adapter` | P1 | medium | cloud-platform-adapters | 适配华为云身份、VPC、计算、OBS、数据库、消息、函数、监控和成本。 |
| `identity-kms-secret-adapter` | P0 | critical | cloud-platform-adapters | 统一 IAM、KMS、Secret、证书、工作负载身份、轮换和审计。 |
| `kubernetes-platform-adapter` | P0 | medium | cloud-platform-adapters | 适配托管或私有 Kubernetes 的版本、网络、存储、身份、扩缩和升级。 |
| `managed-database-adapter` | P0 | medium | cloud-platform-adapters | 统一托管关系、文档、缓存数据库的连接、备份、监控、扩缩和切换。 |
| `managed-messaging-adapter` | P0 | medium | cloud-platform-adapters | 统一托管 Queue、Stream、Pub/Sub 的顺序、确认、重试、DLQ 和权限。 |
| `object-storage-adapter` | P0 | medium | cloud-platform-adapters | 统一对象存储 API、Consistency、Multipart、Lifecycle、Encryption 和签名访问。 |
| `private-openstack-adapter` | P0 | medium | cloud-platform-adapters | 适配 OpenStack Identity、Compute、Network、Storage、Image、Heat 和私有运维。 |
| `serverless-platform-adapter` | P1 | medium | cloud-platform-adapters | 适配函数运行时、事件、状态、并发、超时、冷启动、权限和本地仿真。 |
| `tencent-cloud-adapter` | P1 | medium | cloud-platform-adapters | 适配腾讯云身份、VPC、计算、COS、数据库、消息、函数、监控和成本。 |
| `vmware-platform-adapter` | P1 | medium | cloud-platform-adapters | 适配 VMware 虚拟化、网络、存储、模板、快照、Kubernetes 和迁移。 |

## Golden Route & Customer Delivery / 商业项目交付

原子 Skill：**24**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `baseline-build-test-evidence` | P0 | high | customer-delivery | 在任何修改前固化构建、测试、运行、性能、安全和缺陷基线。 |
| `canary-wave-cutover` | P0 | critical | customer-delivery | 按租户、模块、路由、流量、设备或数据分区执行金丝雀与波次切换。 |
| `commercial-golden-route-certifier` | P0 | high | customer-delivery | 对业务线 Golden Route 的重复性、可交付性、可计费性、SLA 和证据执行认证。 |
| `customer-acceptance-contract` | P0 | high | customer-delivery | 把需求、覆盖、测试、性能、安全、数据、部署和未决项写入机器可验收契约。 |
| `customer-data-export-deletion` | P0 | high | customer-delivery | 完成客户数据、知识、Adapter、Trace、缓存的导出、删除、撤销与证明。 |
| `customer-policy-knowledge-pack` | P0 | high | customer-delivery | 封装客户编码、架构、安全、数据、测试、部署、审批和知识规则。 |
| `defect-triage-and-remediation-sla` | P0 | high | customer-delivery | 按严重度、原因、责任、修复、复测、客户沟通和 SLA 管理缺陷。 |
| `delivery-dashboard-eta-cost-risk` | P0 | high | customer-delivery | 展示机器 Wall-clock ETA、进度、成本、质量、风险、阻塞和验收状态。 |
| `discovery-workshop-and-scope-freeze` | P0 | high | customer-delivery | 沉淀业务目标、范围、排除项、假设、责任、环境、数据和验收边界。 |
| `evidence-room-and-audit-export` | P0 | high | customer-delivery | 建立可搜索、脱敏、带血缘和签名的客户证据室与审计导出。 |
| `golden-dataset-and-eval-freeze` | P0 | high | customer-delivery | 冻结客户代表性用例、回归集、数据边界、泄漏防护和版本。 |
| `handover-training-runbook` | P0 | critical | customer-delivery | 交付架构、代码、部署、监控、故障、恢复、升级、知识和培训材料。 |
| `migration-factory-capacity-plan` | P0 | high | customer-delivery | 规划并发仓库、Agent、构建、测试、专家、队列、预算和交付节拍。 |
| `opportunity-repository-qualification` | P0 | high | customer-delivery | 评估仓库规模、技术栈、数据、权利、测试、构建、风险与可自动化比例。 |
| `pilot-slice-selection` | P0 | high | customer-delivery | 选择代表性、可隔离、可验证且能揭示关键风险的试点切片。 |
| `proof-of-value-execution` | P0 | high | customer-delivery | 执行小规模端到端迁移，量化质量、速度、成本、人工负担和剩余风险。 |
| `reference-architecture-case-study` | P1 | high | customer-delivery | 在客户许可范围内形成脱敏参考架构、案例和可重复实施模式。 |
| `repository-size-and-price-estimation` | P0 | high | customer-delivery | 按 LOC、符号、模块、动态性、依赖、验证、迁移窗口和风险估算机器时间与价格。 |
| `reusable-domain-pack-extraction` | P1 | high | customer-delivery | 从项目中提取不含客户秘密的知识、规则、Skill、测试和 Golden Route 增量。 |
| `roi-time-cost-quality-report` | P1 | high | customer-delivery | 量化人工与机器时间、缺陷、维护、性能、云成本、收入和投资回报。 |
| `rollback-business-continuity` | P0 | critical | customer-delivery | 验证代码、数据、配置、流量、凭据和运营流程的回退与连续性。 |
| `shadow-dual-run-plan` | P0 | high | customer-delivery | 设计影子、双运行、流量复制、结果对账、隐私和生产影响控制。 |
| `target-architecture-and-wave-plan` | P0 | high | customer-delivery | 生成目标架构、依赖顺序、迁移波次、兼容窗口、切流和回退计划。 |
| `warranty-lts-support-transition` | P0 | high | customer-delivery | 定义保修、LTS、补丁、升级、停服、升级窗口和支持责任。 |

## Product Commercialization & Marketplace / 产品商业化

原子 Skill：**16**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `capability-package-and-edition-design` | P0 | high | product-commercialization | 把模型、Skill、并发、上下文、认证、保留和支持组合为清晰产品版本。 |
| `commercial-product-readiness-gate` | P0 | high | product-commercialization | 验证产品、合同、计费、支持、SLA、隐私、审计、回滚和客户体验后才开放销售。 |
| `customer-portal-usage-evidence` | P0 | high | product-commercialization | 向客户展示用量、余额、任务、证据、质量、成本、发票和数据设置。 |
| `entitlement-license-feature-gating` | P0 | high | product-commercialization | 按租户、合同、地区、版本、私有部署和试用控制能力与资源。 |
| `fraud-abuse-credit-risk-control` | P0 | critical | product-commercialization | 检测账号滥用、信用套取、恶意仓库、资源攻击、退款欺诈和异常用量。 |
| `marketplace-skill-packaging-signing` | P1 | high | product-commercialization | 包装、签名、扫描、定价、版本化和发布内部、伙伴或客户 Skill Pack。 |
| `model-skill-tool-cost-metering` | P0 | critical | product-commercialization | 计量 Token、GPU、工具、构建、测试、存储、网络、专家与第三方费用。 |
| `partner-certification-revenue-share` | P1 | high | product-commercialization | 管理伙伴资格、交付质量、责任、结算、分成、撤销和客户证据。 |
| `prepaid-reservation-settlement-refund` | P0 | high | product-commercialization | 实现预付余额、任务预留、实际结算、释放、超额、退款和幂等对账。 |
| `private-deployment-license-control` | P0 | high | product-commercialization | 支持离线许可证、容量、模型与 Skill 授权、审计、续期和防误停。 |
| `repository-complexity-quote-engine` | P0 | high | product-commercialization | 依据规模、语言、框架、测试、数据、风险、SLA 和迁移方式自动报价。 |
| `roadmap-demand-value-prioritization` | P1 | medium | product-commercialization | 结合需求、失败、收入、毛利、战略、风险和复用价值排序路线。 |
| `sla-service-credit-automation` | P0 | critical | product-commercialization | 根据可用性、完成、恢复、质量和证据自动计算 SLA 补偿。 |
| `trial-sandbox-data-isolation` | P0 | high | product-commercialization | 为试用提供样例或授权数据、严格配额、隔离、过期清理和防滥用。 |
| `unit-economics-margin-optimization` | P0 | high | product-commercialization | 按模型、Skill、业务线、租户和项目优化质量、成本、价格与毛利。 |
| `usage-credit-subscription-project-price` | P0 | critical | product-commercialization | 支持 Usage Credit、订阅、按项目、按仓库规模、成功费和混合定价。 |

## Regulated Industry Assurance / 受监管行业认证

原子 Skill：**20**。

| Skill | Priority | Risk | Business line | Description |
|---|---:|---:|---|---|
| `audit-trail-data-integrity` | P0 | high | regulated-industry-assurance | 确保审计轨迹完整、准确、及时、不可篡改、可解释并与业务记录关联。 |
| `bias-fairness-impact-assessment` | P1 | high | regulated-industry-assurance | 按适用场景检查代表性、性能差异、代理变量、误用和缓解，不作无依据公平承诺。 |
| `change-control-capa-workflow` | P0 | high | regulated-industry-assurance | 管理变更请求、影响、审批、实施、偏差、根因、纠正预防和有效性检查。 |
| `control-objective-requirement-mapping` | P0 | medium | regulated-industry-assurance | 把法律、标准、合同和内部控制映射到需求、设计、实现、测试和证据。 |
| `data-retention-legal-hold-evidence` | P0 | high | regulated-industry-assurance | 在主系统、备份、日志、模型、知识和导出中执行保留、冻结和可证明删除。 |
| `electronic-record-signature-integrity` | P0 | high | regulated-industry-assurance | 保护电子记录、签名、身份、时间、含义、版本、不可抵赖和长期可读性。 |
| `explainability-human-oversight` | P0 | high | regulated-industry-assurance | 定义解释对象、证据、人工复核、申诉、接管、拒绝和自动化偏差防护。 |
| `model-risk-management-file` | P0 | critical | regulated-industry-assurance | 维护模型用途、限制、数据、验证、漂移、变更、Owner、挑战与退役档案。 |
| `periodic-review-recertification` | P0 | high | regulated-industry-assurance | 按时间、变更、漂移、事件、法规和供应商变化触发定期复审与再认证。 |
| `privacy-impact-assessment` | P0 | high | regulated-industry-assurance | 评估目的、必要性、数据主体、共享、自动决策、保留、跨境和缓解措施。 |
| `regulated-industry-golden-route` | P0 | critical | regulated-industry-assurance | 认证高保障场景从范围、验证、审批、运行监控到再认证的商业 Golden Route。 |
| `regulated-release-approval` | P0 | critical | regulated-industry-assurance | 在验证、偏差、风险、电子签名、职责分离和发布包满足后批准上线。 |
| `regulated-workload-classification` | P0 | critical | regulated-industry-assurance | 按数据、决策、影响、行业、地域、客户和自动化程度分类监管与保障范围。 |
| `regulator-customer-evidence-package` | P0 | high | regulated-industry-assurance | 按权限导出控制、验证、追踪、变更、事件、签名和残余风险证据。 |
| `requirement-design-test-trace-matrix` | P0 | high | regulated-industry-assurance | 建立用户需求、系统需求、设计、代码、风险、测试、缺陷和发布的双向追踪。 |
| `safety-case-hazard-risk-analysis` | P0 | critical | regulated-industry-assurance | 构建 Hazard、Claim、Argument、Evidence、残余风险和运行限制的安全案例。 |
| `segregation-of-duties-enforcement` | P0 | high | regulated-industry-assurance | 分离开发、训练、验证、批准、部署、审计和例外权限，防止自批自证。 |
| `software-validation-master-plan` | P0 | high | regulated-industry-assurance | 定义验证范围、方法、环境、角色、文档、偏差、接受标准和再验证触发器。 |
| `supplier-thirdparty-assurance` | P0 | high | regulated-industry-assurance | 评估模型、云、开源、外包、工具和数据供应商的风险、控制、证据和退出。 |
| `validation-environment-qualification` | P0 | high | regulated-industry-assurance | 确认硬件、OS、数据库、模型、工具、测试数据和配置满足验证用途。 |


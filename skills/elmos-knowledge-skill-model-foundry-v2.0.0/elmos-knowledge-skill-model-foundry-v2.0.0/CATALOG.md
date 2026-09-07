# Elmos Skills Catalog v2.0.0

共 458 个原子 Skill，17 个 Meta-Skill。启动时只暴露 Meta-Skill。

## 00-foundation-contracts

**Kernel：** K0 Cross-Kernel Contracts

建立所有知识、技能、数据、模型、证据与发布物共同遵循的身份、类型、权限、版本和兼容契约。

| Priority | Skill | Description |
|---|---|---|
| P0 | `capability-taxonomy-governance` | 统一定义能力域、Skill 粒度、风险等级、成熟度、依赖和所有权，防止能力重复与边界漂移。 |
| P0 | `artifact-identity-and-hashing` | 为知识对象、数据集、模型、Adapter、Skill、工具镜像和证据生成不可歧义的内容身份与哈希。 |
| P0 | `typed-skill-contract` | 定义 Skill 的输入、输出、前置条件、后置条件、工具权限、失败语义和副作用契约。 |
| P0 | `evidence-contract` | 定义每项能力必须产生的编译、测试、差分、证明、安全和人工审批证据。 |
| P0 | `policy-contract` | 把数据、权限、训练、部署和合规规则表达成可执行、可测试、可审计的策略契约。 |
| P0 | `tenancy-scope-contract` | 明确平台、组织、租户、项目、仓库、分支、任务和用户各级数据与能力作用域。 |
| P0 | `data-usage-consent-contract` | 约束数据可否检索、记录、标注、训练、跨租户聚合、导出、删除和保留。 |
| P0 | `release-bundle-contract` | 把模型、Adapter、Skill 集、知识快照、工具链、策略和评测基线绑定为不可变发布单元。 |
| P0 | `compatibility-matrix-manager` | 管理语言、框架、数据库、模型、硬件、驱动、工具和 Skill 的版本兼容矩阵。 |
| P1 | `capability-dependency-graph` | 建立能力依赖图并计算循环依赖、爆炸半径、升级影响和最小发布闭包。 |
| P1 | `extension-sdk-and-codegen` | 提供新增知识连接器、Skill、验证器、训练器和部署适配器的 SDK 与脚手架。 |
| P1 | `contract-migration-manager` | 在契约 Schema 升级时完成向前兼容、双写、迁移验证和安全回滚。 |
| P1 | `architecture-decision-record` | 把关键架构选择、假设、替代方案和退出条件沉淀为可检索 ADR。 |
| P0 | `package-conformance-validator` | 对整个 Skills Package 执行结构、命名、权限、证据和依赖一致性校验。 |

## 01-knowledge-ingestion-governance

**Kernel：** K1 Knowledge Fabric

把代码、文档、运行数据和组织经验安全、增量、可追溯地转换为统一知识对象。

| Priority | Skill | Description |
|---|---|---|
| P0 | `knowledge-source-connector-registry` | 注册并治理 Git、对象存储、Wiki、Issue、PR、CI、数据库和日志等知识源连接器。 |
| P0 | `repository-incremental-ingestion` | 按提交、分支和文件增量摄取仓库，保留删除、重命名、子模块和生成代码语义。 |
| P0 | `document-structure-ingestion` | 解析 Markdown、HTML、Word、PDF、TXT 与表格，恢复标题、章节、表格、引用和附件关系。 |
| P0 | `api-contract-ingestion` | 摄取 OpenAPI、AsyncAPI、GraphQL、Proto、IDL 和事件 Schema，生成版本化 API 知识对象。 |
| P0 | `database-metadata-ingestion` | 摄取 Schema、Routine、触发器、索引、约束、统计信息和执行计划。 |
| P1 | `issue-pr-review-ingestion` | 沉淀 Issue、PR、代码审查意见、提交理由与最终修复之间的因果和语义关系。 |
| P1 | `runtime-trace-ingestion` | 接入 Trace、Metric、Log、Profile、SQL 与消息链路，并与静态代码实体关联。 |
| P1 | `incident-runbook-ingestion` | 将故障报告、复盘、Runbook、变更记录和恢复步骤转换为可执行知识。 |
| P1 | `multimodal-artifact-ingestion` | 解析架构图、流程图、UI 截图、日志截图、音视频说明和代码演示。 |
| P0 | `archive-and-folder-ingestion` | 安全处理文件夹、zip、tar.gz、嵌套归档、超大文件和损坏归档。 |
| P0 | `artifact-normalization` | 将不同格式统一为 Artifact IR，保留原始字节、字符位置、页码和源映射。 |
| P1 | `structure-recovery-and-ocr-fallback` | 优先结构化解析，在必要时受控启用 OCR，并记录置信度和人工复核点。 |
| P0 | `incremental-change-capture` | 通过内容哈希和变更事件只重算受影响知识分片、图关系和向量。 |
| P0 | `source-freshness-and-expiry` | 跟踪知识有效期、版本适用范围、失效日期、最后验证时间和刷新 SLA。 |
| P0 | `provenance-and-lineage-capture` | 记录来源 URI、提交、作者、解析器、转换步骤、父子对象和派生链。 |
| P0 | `license-and-rights-classification` | 识别许可证、客户合同限制、训练许可、再分发权限和归属义务。 |
| P0 | `sensitive-data-and-secret-detection` | 发现凭据、密钥、个人信息、商业秘密、受监管数据和高敏代码。 |
| P0 | `ingestion-quarantine-gate` | 对来源不明、许可不清、解析失败、污染或恶意内容执行隔离与复核。 |
| P1 | `connector-health-and-backfill` | 监控同步延迟、缺页、断点、权限变化，并安全完成补采与校验。 |
| P1 | `data-residency-aware-routing` | 按租户、地域和法规要求选择存储、索引、处理和训练区域。 |

## 02-repository-semantic-intelligence

**Kernel：** K2 Repository Semantic Compiler

把仓库从文件集合提升为可查询、可变换、可证明的多层语义图和 Semantic IR。

| Priority | Skill | Description |
|---|---|---|
| P0 | `multi-language-ast-extraction` | 为支持语言构建带源映射、错误恢复和版本信息的统一 AST。 |
| P0 | `symbol-and-reference-graph` | 解析定义、引用、重载、泛型、反射、动态调用和跨模块符号关系。 |
| P0 | `call-graph-construction` | 组合静态、动态和配置证据构建调用图，并显式表达不确定边。 |
| P0 | `control-flow-graph` | 恢复分支、循环、异常、协程、回调和异步控制流。 |
| P0 | `data-flow-and-taint-graph` | 跟踪变量、字段、对象、请求、数据库和消息中的数据流与污点传播。 |
| P1 | `program-dependency-graph` | 融合控制依赖与数据依赖，支持影响分析、切片和最小变更计算。 |
| P0 | `type-and-contract-graph` | 表达类型、泛型、继承、接口、Nullability、约束和结构类型关系。 |
| P0 | `build-and-dependency-graph` | 解析构建模块、依赖、插件、Profile、代码生成和包解析结果。 |
| P0 | `configuration-semantics-graph` | 关联配置键、环境变量、Feature Flag、Bean、资源和运行行为。 |
| P0 | `api-and-event-contract-graph` | 建立 API、RPC、事件、Schema、消费者和生产者的契约依赖图。 |
| P0 | `database-schema-and-query-graph` | 关联表、列、约束、Routine、ORM 映射、SQL 与业务调用。 |
| P0 | `transaction-boundary-graph` | 识别事务传播、隔离级别、锁、补偿、幂等和跨服务一致性边界。 |
| P0 | `security-policy-graph` | 关联身份、角色、权限、路由、数据对象、过滤器和安全配置。 |
| P1 | `deployment-topology-graph` | 恢复服务、容器、端口、队列、数据库、网络策略和区域拓扑。 |
| P1 | `test-to-code-evidence-graph` | 连接测试、覆盖、变异、需求、缺陷、代码实体和认证证据。 |
| P1 | `issue-code-rationale-graph` | 关联需求、Issue、讨论、代码变更、回滚和设计理由。 |
| P1 | `runtime-static-correlation` | 把生产 Trace、SQL、异常和性能热点映射回静态语义实体。 |
| P1 | `architecture-recovery` | 从代码、构建、部署和运行证据恢复模块边界、层次、领域和依赖违规。 |
| P1 | `domain-ontology-induction` | 从命名、Schema、文档和流程中归纳领域实体、关系、规则和术语。 |
| P0 | `cross-source-entity-resolution` | 合并文档、代码、数据库、Issue 和运行数据中的同一实体并保留别名。 |
| P0 | `temporal-version-semantic-graph` | 支持双时态知识、版本区间、分支差异和历史语义查询。 |
| P0 | `semantic-diff-and-impact-analysis` | 比较两个版本的 API、行为、数据、依赖和风险变化，而非仅文本差异。 |
| P1 | `knowledge-contradiction-detection` | 发现文档、代码、测试、配置与运行事实之间的冲突并定位证据。 |
| P0 | `semantic-ir-reconciliation` | 将多解析器、多语言和多来源结果收敛为可追溯、带置信度的统一 Semantic IR。 |

## 03-retrieval-context-engineering

**Kernel：** K3 Retrieval and Context Kernel

为具体任务构造最小、正确、可信、版本匹配且抗注入的仓库级上下文。

| Priority | Skill | Description |
|---|---|---|
| P0 | `hybrid-code-knowledge-retrieval` | 融合关键词、向量、符号、类型和图关系检索代码与知识。 |
| P0 | `symbol-aware-retrieval` | 围绕定义、引用、实现、测试、配置和调用方检索完整符号上下文。 |
| P0 | `graph-path-retrieval` | 按调用、数据流、事务、安全或部署路径检索跨文件证据链。 |
| P1 | `execution-path-retrieval` | 使用运行 Trace 与失败路径优先选取真实执行相关上下文。 |
| P0 | `version-aware-retrieval` | 根据语言、框架、数据库、分支和发布日期过滤不兼容知识。 |
| P0 | `tenant-policy-aware-retrieval` | 在检索前执行租户、项目、角色、地域和敏感级别权限裁剪。 |
| P1 | `query-decomposition-and-rewrite` | 将复合工程任务拆为符号、行为、依赖、测试和风险检索子查询。 |
| P1 | `multi-hop-evidence-retrieval` | 通过多跳图搜索补齐需求到实现、实现到测试、错误到修复的链路。 |
| P0 | `task-specific-reranking` | 按任务类型训练并应用代码、文档、错误和 Skill 专用重排器。 |
| P1 | `retrieval-hard-negative-mining` | 从高相似但错误版本、错误框架和同名符号中构造困难负样本。 |
| P0 | `context-budget-optimizer` | 在 Token、延迟和成本约束下最大化有用证据覆盖和相互依赖完整性。 |
| P0 | `hierarchical-context-packing` | 按架构摘要、文件摘要、符号和必要源码分层组织上下文。 |
| P1 | `lost-in-middle-mitigation` | 通过分段、重排、重复锚点和检索式回读降低长上下文中间信息丢失。 |
| P0 | `delta-context-construction` | 只注入自上次检查点以来的语义变化，减少长任务重复上下文。 |
| P1 | `evidence-preserving-compression` | 压缩代码和文档时保留类型、约束、异常、边界和引用位置。 |
| P0 | `citation-and-source-binding` | 让每个关键事实、建议和变换都绑定来源对象、版本和位置。 |
| P0 | `stale-and-conflict-arbitration` | 识别过期或冲突上下文，按权威度、时间和运行证据裁决。 |
| P1 | `semantic-context-cache` | 缓存任务语义包并根据依赖图和知识变更进行精确失效。 |
| P0 | `retrieval-injection-defense` | 隔离不可信内容、标记指令性文本并阻止知识内容升级为系统权限。 |
| P0 | `retrieval-evaluation-and-replay` | 离线重放检索过程并计算 Recall、MRR、引用准确率和有用上下文比。 |

## 04-memory-experience-flywheel

**Kernel：** K4 Memory and Experience Kernel

把长任务状态、成功经验、失败模式和人工修订沉淀为可重放、可选择性遗忘的经验资产。

| Priority | Skill | Description |
|---|---|---|
| P0 | `working-memory-manager` | 维护当前任务假设、计划、约束、待办、已验证事实和风险，不混入长期记忆。 |
| P0 | `episodic-memory-store` | 保存一次任务的输入、环境、步骤、失败、修复、结果和证据。 |
| P0 | `semantic-memory-distiller` | 从多次经历中提炼稳定事实、规则和模式，并保留来源覆盖范围。 |
| P0 | `procedural-memory-store` | 保存可执行步骤、工具参数、前置条件和回滚方式，为 Skill Mining 提供材料。 |
| P0 | `durable-task-checkpoint-memory` | 在暂停、断电、网络中断和进程迁移后恢复任务状态与副作用边界。 |
| P1 | `long-horizon-memory-compaction` | 分层压缩长任务历史，保留决策、未决风险、工具结果哈希和恢复锚点。 |
| P0 | `experience-episode-capture` | 形成标准 Episode，绑定仓库快照、知识、Skill、模型、环境和最终验收。 |
| P1 | `trajectory-segmentation` | 把长轨迹切分为规划、定位、修改、验证、修复和发布等可学习片段。 |
| P0 | `tool-event-normalization` | 统一不同模型和 Agent 框架的工具请求、结果、错误和权限决策格式。 |
| P0 | `failure-signature-extraction` | 从编译、测试、运行、安全和性能失败中生成稳定、可聚类的签名。 |
| P1 | `repair-pattern-extraction` | 学习失败签名到补丁策略、验证步骤和适用条件的映射。 |
| P1 | `human-edit-diff-analysis` | 区分人工对模型结果的修错、偏好调整、补需求和无关格式修改。 |
| P1 | `outcome-attribution-and-credit` | 把最终成功或失败归因到检索、Skill、计划、工具、模型和验证步骤。 |
| P2 | `counterfactual-trajectory-replay` | 替换关键决策或上下文重放轨迹，估计某项改动的真实贡献。 |
| P1 | `experience-clustering-and-dedupe` | 按任务、语言、框架、失败和修复模式聚类并去除近重复经历。 |
| P0 | `experience-value-scoring` | 按正确性、稀缺性、泛化性、证据完整度和训练权利评估经验价值。 |
| P0 | `memory-retention-and-forgetting` | 根据用途、合同、风险和访问频率执行保留、降级、归档和删除。 |
| P0 | `memory-poisoning-defense` | 检测恶意、错误或低置信记忆，阻止其进入规划、检索与训练。 |
| P1 | `cross-task-experience-transfer` | 在满足边界条件时把经验迁移到相似仓库，并校准不确定性。 |
| P0 | `tenant-memory-isolation-and-replay` | 确保经验不可跨租户泄漏，且在固定环境中可以确定性重放验证。 |

## 05-skill-foundry-runtime

**Kernel：** K5 Skill Foundry and Runtime

把隐性工程方法转化为可发现、可组合、可执行、可评测、可签名和可撤销的证明携带型 Skill。

| Priority | Skill | Description |
|---|---|---|
| P0 | `skill-authoring-workbench` | 从需求和领域方法创建兼容 SKILL.md 的强类型 Skill，并生成模板、契约和评测。 |
| P1 | `runbook-to-skill-compiler` | 把人工 Runbook 转换为带条件、分支、工具、证据和异常处理的工作流。 |
| P1 | `trajectory-to-skill-miner` | 从多次成功且已验证轨迹中抽取稳定步骤、参数和适用边界。 |
| P1 | `commit-history-to-skill-miner` | 从重复提交、修复和评审意见中发现可自动化工程模式。 |
| P1 | `incident-to-recovery-skill-miner` | 从故障与恢复记录生成诊断、止损、修复和复盘 Skill。 |
| P1 | `anti-pattern-and-guardrail-miner` | 把重复错误、绕过行为和风险操作沉淀为禁止规则与防护 Skill。 |
| P1 | `skill-boundary-discovery` | 判断能力应拆为原子 Skill、复合 Skill、知识规则还是模型能力。 |
| P0 | `skill-decomposition-and-composition` | 拆解过大 Skill，组合原子 Skill，并验证数据、权限和失败语义兼容。 |
| P0 | `skill-dependency-resolver` | 解析 Skill、工具、模型、环境和 Schema 依赖，生成可重复执行闭包。 |
| P0 | `skill-activation-router` | 根据用户意图、仓库事实、风险和能力置信度选择应加载的 Skill。 |
| P1 | `skill-description-optimizer` | 使用应触发与不应触发样本优化 description，控制漏触发和误触发。 |
| P0 | `hierarchical-skill-registry` | 提供平台、组织、租户、项目和仓库级 Skill 注册、搜索和优先级覆盖。 |
| P0 | `skill-version-and-compatibility` | 管理 SemVer、兼容范围、依赖锁定、升级迁移和回滚版本。 |
| P0 | `skill-sandbox-executor` | 在受限环境中执行脚本与工具，施加文件、网络、CPU、内存和时间限制。 |
| P0 | `deterministic-script-packager` | 把高精度步骤固化为幂等、可测试、稳定接口的脚本资源。 |
| P0 | `progressive-skill-disclosure` | 只暴露 Meta-Skill 目录，激活后再加载原子 Skill 和必要资源。 |
| P1 | `skill-context-pinning` | 在长任务压缩和子 Agent 委派中保护已激活 Skill 的关键契约。 |
| P0 | `skill-replay-and-snapshot` | 在固定仓库、镜像、模型和知识快照中重放 Skill 执行。 |
| P0 | `skill-trigger-evaluation` | 评估应触发、不应触发、模糊意图、错别字和多意图场景。 |
| P0 | `skill-process-evaluation` | 检查是否遵守规定步骤、工具、审批、验证和最小副作用约束。 |
| P0 | `skill-output-evaluation` | 检查最终代码、文档、补丁、报告和证据是否满足契约。 |
| P1 | `skill-efficiency-evaluation` | 衡量 Token、工具次数、重试、Wall-clock、缓存和成本效率。 |
| P1 | `skill-robustness-evaluation` | 覆盖边界输入、版本变化、工具失败、并发、恢复和恶意内容。 |
| P0 | `proof-carrying-skill` | 要求 Skill 输出可机器验证的证明义务、测试结果、未决风险和回滚信息。 |
| P0 | `skill-signing-and-release` | 对 Skill 内容、依赖、脚本、策略和评测结果签名后发布。 |
| P0 | `skill-deprecation-and-revocation` | 在缺陷、安全事件或依赖失效时阻止新调用并迁移现有任务。 |
| P1 | `skill-telemetry-and-cost-profile` | 持续记录触发、成功、失败、成本、模型组合和客户价值。 |
| P1 | `cross-agent-skill-portability` | 验证 Skill 在 Codex、Claude Code、兼容 Agent 和 Elmos Runtime 的可移植性。 |
| P0 | `skill-transaction-and-rollback` | 为有副作用 Skill 建立幂等键、补偿事务、检查点和回滚演练。 |

## 06-dataset-foundry

**Kernel：** K6 Dataset Foundry

把经验和知识转化为合法、可追溯、无泄漏、可验证且适配不同训练目标的数据产品。

| Priority | Skill | Description |
|---|---|---|
| P0 | `dataset-contract-and-schema` | 定义任务、上下文、轨迹、补丁、证据、奖励、权限和血缘的标准训练样本结构。 |
| P0 | `bronze-dataset-intake` | 保存原始轨迹和产物但禁止训练，确保可追溯和可重新处理。 |
| P0 | `silver-promotion-gate` | 要求基础编译、测试、来源和权限检查通过后进入可限制使用的数据层。 |
| P0 | `gold-certified-promotion` | 要求独立验证、完整证据、专家接受或跨仓库复现后进入高可信训练层。 |
| P0 | `dataset-quarantine-management` | 隔离许可证不明、PII、密钥、污染、注入、低质量和结果不确定样本。 |
| P0 | `dataset-lineage-and-provenance` | 记录每个样本来自哪些对象、任务、模型、Skill、人工修改和转换步骤。 |
| P0 | `training-rights-enforcement` | 在数据读取、混合、训练、导出和发布阶段持续执行许可与合同限制。 |
| P0 | `secret-pii-and-sensitive-redaction` | 对代码、日志、Prompt、工具结果和补丁执行可验证脱敏并保留替换映射权限。 |
| P0 | `cross-tenant-data-separation` | 通过物理或逻辑分区、密钥和查询策略阻止跨租户训练泄漏。 |
| P0 | `semantic-and-ast-deduplication` | 使用文本、AST、图和行为指纹去除复制、近重复和模板污染。 |
| P0 | `benchmark-contamination-detection` | 检测公开基准、测试答案、下游评测仓库和相似变体进入训练数据。 |
| P0 | `repo-org-time-split-builder` | 按仓库、组织、时间、家族和 Fork 分组切分，避免相似提交跨训练与测试。 |
| P1 | `task-canonicalization-and-normalization` | 统一需求、错误、环境、期望结果和验收条件，减少标签噪声。 |
| P0 | `sft-dataset-builder` | 构建包含任务、上下文、计划、工具、补丁和验证结果的监督微调数据。 |
| P1 | `preference-pair-builder` | 从人工接受、回滚、修复差异和验证证据生成 chosen/rejected 样本对。 |
| P1 | `process-supervision-dataset` | 构造步骤级正确性、工具选择、检查点和错误恢复标签。 |
| P1 | `tool-trajectory-dataset` | 标准化多轮工具调用、参数、环境反馈和终止状态用于 Agent 训练。 |
| P0 | `retriever-reranker-dataset` | 从真实有用证据、误检和困难负例构建检索与重排数据。 |
| P0 | `router-and-risk-dataset` | 构建任务分类、Skill/模型选择、复杂度、风险和人工审批标签。 |
| P0 | `verifier-and-proof-dataset` | 构建补丁正确性、测试充分性、行为等价和证据缺口训练数据。 |
| P1 | `rlvr-environment-dataset` | 把仓库、任务、镜像、测试、奖励和终止条件封装为可复现 RL 环境。 |
| P1 | `verified-synthetic-data-factory` | 仅保留通过解析、执行、差分、变异或证明验证的合成数据。 |
| P1 | `mutation-counterexample-data` | 从正确实现生成故障、边界、对抗和反例，训练修复与验证能力。 |
| P1 | `hard-negative-data-mining` | 挖掘看似合理但版本、类型、事务、安全或行为错误的负例。 |
| P1 | `curriculum-and-mixture-optimizer` | 按难度、语言、业务线和失败模式优化训练顺序与数据混合比例。 |
| P0 | `label-quality-and-adjudication` | 测量标注一致性、证据覆盖和审阅偏差，并执行专家仲裁。 |
| P1 | `active-learning-sample-selection` | 按不确定性、业务价值、失败频率和信息增益选择人工标注样本。 |
| P0 | `dataset-version-card-and-signing` | 冻结版本、生成 Dataset Card、质量报告、权利摘要和数字签名。 |
| P0 | `dataset-revocation-unlearning-index` | 记录样本到 Checkpoint/Adapter 的影响范围，支持撤回、删除和选择性重训。 |
| P0 | `eval-freeze-and-leakage-firewall` | 冻结评测集并在数据流水线、检索、Prompt 和训练阶段阻断泄漏。 |

## 07-private-model-foundry

**Kernel：** K7 Private Model Foundry

构建可替换基座、多专家 Adapter、可复现训练、可签名发布和可选择性撤销的私有模型体系。

| Priority | Skill | Description |
|---|---|---|
| P0 | `base-model-selection-and-license` | 根据代码能力、上下文、工具使用、许可证、硬件和私有部署需求选择基座。 |
| P1 | `tokenizer-domain-audit` | 分析代码、DSL、标识符、SQL、中文和多语言 Token 效率与分词缺陷。 |
| P2 | `tokenizer-adaptation-and-migration` | 受控扩展词表并处理 Embedding 初始化、兼容、Checkpoint 迁移和回归。 |
| P2 | `domain-continued-pretraining` | 对稳定、授权、规模足够的领域语料执行 CPT，并监测能力迁移和遗忘。 |
| P0 | `supervised-finetuning-orchestrator` | 执行 SFT 数据验证、模板锁定、分布式训练、Checkpoint 与离线评测。 |
| P0 | `lora-qlora-adapter-training` | 以低秩 Adapter 训练业务线和租户能力，控制 Rank、目标层和量化误差。 |
| P0 | `adapter-lifecycle-manager` | 管理 Adapter 训练、依赖、缓存、权限、升级、回滚、撤销和租户归属。 |
| P1 | `adapter-composition-and-conflict` | 评估多 Adapter 组合、路由、加权、合并和能力冲突。 |
| P1 | `preference-optimization-orchestrator` | 支持 DPO、KTO、ORPO、SimPO 等策略并依据数据与目标选择。 |
| P1 | `outcome-reward-model-training` | 训练基于最终结果和证据的奖励模型，并校准跨任务泛化。 |
| P1 | `process-reward-model-training` | 对计划、工具选择、检查点、验证和恢复步骤进行过程级评分。 |
| P0 | `router-model-training` | 训练任务、Skill、模型、风险、成本和人工审批路由模型。 |
| P0 | `code-embedding-model-training` | 训练面向符号、错误、API、SQL 和跨语言语义的 Embedding 模型。 |
| P0 | `code-reranker-model-training` | 训练针对仓库检索、版本约束和证据相关性的重排器。 |
| P1 | `repository-planner-model-training` | 训练仓库理解、任务拆解、影响范围、检查点和执行 DAG 能力。 |
| P1 | `semantic-transformer-model-training` | 训练基于 Semantic IR 的代码生成、迁移、重构和跨语言变换能力。 |
| P1 | `execution-guided-repair-model` | 训练利用编译、测试、日志和差分反馈进行最小修复的模型。 |
| P0 | `verifier-model-training` | 训练补丁风险、行为等价、测试缺口、幻觉 API 和上线可接受性判断。 |
| P1 | `proof-critic-model-training` | 训练不变量、证明义务、反例和 Evidence Contract 完整性审查。 |
| P1 | `multi-teacher-distillation` | 从多个强模型和工具验证结果蒸馏稳定能力，减少单一教师偏差。 |
| P1 | `on-policy-self-distillation` | 从模型自身经验证的成功与失败轨迹中进行受控自蒸馏。 |
| P1 | `quantization-and-accuracy-guard` | 执行量化、校准和硬件适配，同时用业务评测阻止精度暗降。 |
| P2 | `speculative-draft-model-training` | 训练低成本草稿模型并验证其与目标模型的接受率和端到端收益。 |
| P0 | `uncertainty-calibration-abstention` | 校准置信度、风险阈值和拒答/升级机制，避免错误自动化。 |
| P1 | `continual-learning-with-replay` | 通过回放、正则化和领域采样持续学习，同时保持旧能力。 |
| P0 | `catastrophic-forgetting-detection` | 在每次训练后按语言、业务线、工具、长任务和安全集检测遗忘。 |
| P1 | `selective-model-unlearning` | 针对撤回数据、租户退出或风险样本执行选择性遗忘并验证残留。 |
| P2 | `federated-tenant-adapter-learning` | 在不集中原始数据的前提下聚合租户 Adapter 更新并防止反推。 |
| P2 | `differential-private-training` | 对确有必要的敏感训练应用差分隐私并量化效用损失。 |
| P1 | `hyperparameter-and-mixture-search` | 在预算约束下优化学习率、Rank、数据混合、长度和训练策略。 |
| P0 | `distributed-training-checkpointing` | 支持 DDP/FSDP/ZeRO、并行保存、拓扑变化恢复和训练断点续跑。 |
| P0 | `training-reproducibility-and-registry` | 记录代码、数据、容器、随机种子、依赖、硬件、指标与模型血缘。 |
| P0 | `model-card-signing-and-mlbom` | 生成模型卡、限制、数据摘要、依赖 BOM、签名和供应链证明。 |
| P1 | `training-cost-energy-estimator` | 预测并核算 GPU 时、Token、存储、网络、能耗和单能力边际成本。 |

## 08-agentic-training-rl

**Kernel：** K7 Private Model Foundry / Agent Learning

训练模型在真实仓库环境中进行长程规划、受控工具使用、验证、恢复和成本约束决策。

| Priority | Skill | Description |
|---|---|---|
| P0 | `repository-training-environment` | 把仓库、构建工具、依赖、服务、数据和测试封装为可重置训练环境。 |
| P0 | `sandbox-image-and-fixture-builder` | 构建固定工具链镜像、种子数据、外部服务模拟和网络策略。 |
| P0 | `environment-reset-and-cleanroom` | 确保每次 Rollout 从已知状态开始，并检测跨任务状态和答案泄漏。 |
| P1 | `tool-use-supervised-training` | 训练何时读取、搜索、编辑、编译、测试、查询和请求审批。 |
| P1 | `tool-selection-and-argument-policy` | 分别优化工具选择与参数生成，并以 Schema 和权限进行动作约束。 |
| P1 | `planner-executor-policy-training` | 训练计划模型与执行模型分工、重规划条件和证据交接。 |
| P2 | `hierarchical-and-subagent-planning` | 训练任务分层、子 Agent 委派、结果汇总、冲突处理和预算分配。 |
| P0 | `environment-aware-action-masking` | 根据权限、状态、风险和依赖动态屏蔽非法或无效动作。 |
| P1 | `automated-process-supervision` | 利用规则、验证器和搜索生成步骤级正负反馈。 |
| P0 | `multi-objective-reward-contract` | 组合功能、等价、安全、证据、维护性、最小改动、时间和成本奖励。 |
| P1 | `dense-partial-credit-reward` | 使用测试子集、覆盖、编译进度和不变量满足度提供稠密奖励。 |
| P0 | `reward-hacking-and-shortcut-detection` | 识别删除测试、硬编码答案、扩大权限、绕过验证和污染环境等投机行为。 |
| P1 | `grader-ensemble-and-disagreement` | 融合确定性检查、多个 Verifier 和人工标签，并利用分歧发现薄弱样本。 |
| P1 | `rlvr-code-agent-training` | 使用可执行测试、差分和证明信号进行可验证奖励强化学习。 |
| P2 | `rl-algorithm-abstraction` | 支持 GRPO、RLOO、PPO、离线 RL 等算法并保持环境与奖励接口稳定。 |
| P1 | `best-of-n-verifier-selection` | 生成多条候选轨迹，通过独立验证器选择或融合最可靠方案。 |
| P2 | `test-time-search-and-tree-exploration` | 受预算控制地执行分支搜索、回溯和候选修复。 |
| P2 | `self-play-task-and-test-generation` | 让任务生成器、Coder 和 Tester 协同产生更难且可验证的课程。 |
| P1 | `automatic-curriculum-scheduler` | 按成功率、失败模式、仓库规模和能力依赖动态提升难度。 |
| P1 | `task-mutation-and-adversarial-env` | 变异需求、依赖、配置、数据和故障，训练鲁棒性和泛化。 |
| P1 | `failure-recovery-policy-training` | 训练诊断、回退、缩小范围、修复环境和替代路径选择。 |
| P0 | `pause-resume-cancel-idempotency-training` | 让 Agent 在中断和重复请求下保持状态一致、无重复副作用。 |
| P1 | `cost-aware-agent-policy` | 把 Token、工具、GPU 和 Wall-clock 预算纳入动作价值与终止决策。 |
| P0 | `safety-constrained-agent-learning` | 把工具权限、审批、数据边界和禁止动作作为不可被奖励抵消的硬约束。 |
| P1 | `offline-trajectory-policy-learning` | 从已验证历史轨迹学习，避免直接在生产环境探索。 |
| P2 | `shadow-online-learning` | 在影子环境收集新分布经验，完成离线认证后再更新生产策略。 |
| P0 | `terminal-state-independent-verification` | 由独立执行器验证最终仓库状态，禁止模型自报成功作为奖励。 |
| P0 | `environment-and-answer-leakage-audit` | 检测测试答案、未来提交、缓存、共享工作区和网络造成的评测泄漏。 |

## 09-evaluation-proof-certification

**Kernel：** K8 Formal Assurance and Evidence

以确定性检查、差分、变异、形式化验证、红队和生产观测形成 E0-E5 可审计认证。

| Priority | Skill | Description |
|---|---|---|
| P0 | `evaluation-contract-and-scorecard` | 在实现前定义必须通过的结果、过程、风格、效率、安全和证据指标。 |
| P0 | `deterministic-grader-framework` | 优先使用 Schema、编译、测试、静态分析、差分和策略规则评分。 |
| P1 | `rubric-grader-and-calibration` | 对难以确定性判断的质量维度使用标尺评分并定期校准偏差。 |
| P1 | `multi-grader-consensus` | 对高风险结论使用多模型、规则和人工共识，保留分歧。 |
| P0 | `benchmark-and-baseline-registry` | 管理内部、外部、冻结、实时和客户基准及其可比条件。 |
| P0 | `model-skill-ablation-analysis` | 分离模型、Skill、检索、工具和训练改动对结果的贡献。 |
| P0 | `skill-activation-quality-metrics` | 测量触发 Precision、Recall、误触发成本和关键漏触发。 |
| P0 | `knowledge-retrieval-quality-metrics` | 测量 Recall@K、MRR、引用准确率、版本正确率和有用上下文比例。 |
| P0 | `compile-test-and-runtime-verification` | 执行构建、单测、集成、端到端、契约、部署和真实运行检查。 |
| P0 | `semantic-behavior-equivalence` | 基于输入输出、状态、异常、副作用、顺序和性能边界验证行为等价。 |
| P0 | `differential-testing` | 对源系统与目标系统、旧版本与新版本执行同输入差分。 |
| P1 | `metamorphic-testing` | 在缺少标准答案时利用输入变换与不变量验证输出关系。 |
| P0 | `mutation-testing-and-test-adequacy` | 通过注入缺陷评估测试是否真能阻止错误实现通过。 |
| P1 | `property-based-and-fuzz-testing` | 从类型、约束和协议生成边界、随机与恶意输入。 |
| P0 | `api-abi-and-schema-compatibility` | 验证 API、ABI、消息、序列化、数据库 Schema 和迁移兼容性。 |
| P0 | `transaction-and-data-equivalence` | 验证事务边界、隔离、锁、回滚、幂等和最终数据一致性。 |
| P0 | `concurrency-correctness-testing` | 检测竞态、死锁、丢失更新、顺序性、可见性和资源泄漏。 |
| P0 | `performance-regression-certification` | 在可比环境中验证吞吐、延迟、内存、SQL、启动和资源成本。 |
| P0 | `security-regression-certification` | 验证权限不扩大、输入处理、依赖、秘密、注入和供应链安全。 |
| P1 | `formal-invariant-synthesis` | 从契约、代码、测试和领域规则生成候选不变量并由人或工具确认。 |
| P1 | `proof-obligation-generator` | 按变换类型生成覆盖路由、类型、事务、安全和数据的证明义务。 |
| P1 | `smt-and-model-checking-adapter` | 把可表达约束交给 SMT、模型检查器或符号执行工具。 |
| P2 | `theorem-prover-integration` | 为关键算法和转换规则生成 Lean/Coq/Isabelle 等证明接口与证据。 |
| P1 | `counterexample-guided-repair` | 把验证器产生的最小反例反馈给修复模型并限制修改范围。 |
| P0 | `evidence-aggregation-and-completeness` | 聚合所有检查、日志、哈希、审批和未决风险，验证 Evidence Contract。 |
| P0 | `false-positive-test-detection` | 识别测试本身错误、环境偶然通过、污染和实现硬编码。 |
| P1 | `human-acceptance-and-edit-distance` | 量化专家接受率、人工改动原因、复核时间和信任边界。 |
| P0 | `uncertainty-and-abstention-evaluation` | 评估置信度校准、拒绝率、升级质量和高风险漏报。 |
| P1 | `distribution-shift-robustness` | 覆盖新框架、新版本、新仓库家族、长尾错误和超大仓库。 |
| P0 | `prompt-injection-and-data-leakage-eval` | 测试直接/间接注入、工具越权、记忆污染、训练数据和跨租户泄漏。 |
| P0 | `cost-latency-and-soak-evaluation` | 评估长任务 Wall-clock、Token、工具成本、并发、稳定性和资源泄漏。 |
| P0 | `shadow-canary-production-evaluation` | 在影子和金丝雀流量中对比质量、成本、失败和回滚信号。 |
| P0 | `e0-e5-certification-engine` | 把来源、单测、集成、影子、金丝雀和长期运行证据映射为 E0-E5。 |
| P0 | `release-regression-bisect` | 在模型、Skill、知识、工具和策略组合中自动定位回归来源。 |
| P1 | `live-benchmark-refresh` | 持续引入时间上晚于训练集的新任务，并保持隔离与可重复性。 |
| P0 | `production-promotion-gate` | 只有所有硬门通过、风险接受和回滚演练完成后才允许生产发布。 |

## 10-serving-routing-inference

**Kernel：** K8 Serving and Runtime Control

提供多模型、多 Adapter、多租户、长任务和高可靠推理的路由、资源调度、灰度与回滚。

| Priority | Skill | Description |
|---|---|---|
| P0 | `model-inference-gateway` | 统一鉴权、路由、配额、内容策略、观测和供应商兼容接口。 |
| P0 | `model-provider-abstraction` | 隔离 OpenAI、Anthropic、开源模型、私有服务和未来推理引擎差异。 |
| P0 | `multi-model-skill-aware-router` | 根据任务、Skill、语言、风险、上下文和历史表现选择模型组合。 |
| P0 | `complexity-risk-cost-latency-routing` | 在质量、风险、成本和延迟的 Pareto 约束下动态路由。 |
| P0 | `tenant-adapter-resolver` | 只解析当前租户授权且与基座、任务和版本兼容的 Adapter。 |
| P0 | `secure-adapter-cache-and-loading` | 验证签名、来源、租户和哈希后加载 Adapter，并隔离缓存。 |
| P0 | `structured-output-enforcement` | 使用 JSON Schema、语法约束和修复策略保证输出可被程序消费。 |
| P0 | `tool-call-schema-and-policy-check` | 在执行前验证工具名、参数、权限、审批和幂等键。 |
| P0 | `context-window-and-compaction-manager` | 管理上下文预算、压缩、恢复锚点和 Skill/证据保护。 |
| P1 | `prefix-kv-cache-and-isolation` | 利用 Prefix/KV Cache 降低成本，同时防止租户和权限上下文串用。 |
| P1 | `continuous-batching-and-speculation` | 优化批处理、Prefill、Decode 和投机解码，并用质量门保护。 |
| P0 | `admission-control-and-priority` | 按并发上限、账户余额、任务优先级、GPU 和截止时间控制入场。 |
| P0 | `fallback-retry-circuit-breaker` | 区分可重试、不可重试和副作用操作，执行退避、降级与熔断。 |
| P0 | `deadline-timeout-propagation` | 把任务和节点截止时间贯穿模型、工具、队列和子 Agent。 |
| P0 | `streaming-and-durable-long-task` | 支持流式反馈、异步节点、检查点、暂停、恢复、取消和断电恢复。 |
| P0 | `shadow-canary-ab-and-rollback` | 执行影子、流量拆分、自动门控和发布组合整体回滚。 |
| P0 | `gpu-scheduling-and-autoscaling` | 根据模型、上下文、Adapter、显存、队列和 SLA 调度 GPU。 |
| P1 | `capacity-and-warm-pool-planning` | 预测峰值、冷启动和 Adapter 热度，维护合理 Warm Pool。 |
| P0 | `usage-metering-and-slo` | 记录 Token、缓存、GPU、工具、延迟、错误和可用性并计算 SLA。 |
| P0 | `airgapped-and-private-serving` | 支持离线镜像、私有 Registry、无外网依赖、更新包和本地审计。 |
| P1 | `edge-and-resource-constrained-serving` | 对小模型、量化、CPU/NPU 和边缘设备进行适配与能力降级。 |
| P0 | `model-at-rest-and-in-use-protection` | 保护模型、Adapter、KV Cache、Prompt 和中间产物的存储与传输。 |
| P0 | `health-warmup-and-readiness` | 验证权重、Tokenizer、Adapter、依赖、显存和基准请求后才进入流量。 |
| P0 | `model-version-pinning-determinism` | 将请求绑定到明确发布组合并提供可复现实验模式。 |
| P1 | `inference-graph-orchestration` | 支持 Router、Sequence、Ensemble、Verifier 和 Fallback 的推理图。 |
| P0 | `serving-compatibility-gateway` | 在 API、Tokenizer、模板、工具 Schema 和 Adapter 变更时执行兼容转换。 |
| P1 | `quality-aware-cache-reuse` | 仅在任务语义、权限、版本和证据相容时复用响应或中间结果。 |
| P0 | `serving-incident-rollback` | 在泄漏、回归、成本异常或模型失效时自动隔离并恢复已知良好组合。 |

## 11-security-privacy-compliance

**Kernel：** Cross-Cutting Trust Plane

把零信任、最小权限、数据治理、供应链和区域合规作为知识、Skill、训练和推理的硬边界。

| Priority | Skill | Description |
|---|---|---|
| P0 | `zero-trust-user-workload-identity` | 对用户、Agent、服务、工具、训练作业和部署实例实施可验证身份。 |
| P0 | `least-privilege-tool-authorization` | 按任务、Environment、Attachment 和 Skill 精确授予工具与参数权限。 |
| P0 | `environment-owned-authority` | 权限归属于实际执行环境而非 Thread 全局状态，恢复后仍保持原始边界。 |
| P0 | `workspace-attachment-ownership-fencing` | 为远程 Executor、Workspace、挂载和产物建立所有权与 Fencing Token。 |
| P0 | `policy-as-code-enforcement` | 在 CI、运行时、训练和部署阶段统一执行可测试策略。 |
| P0 | `human-approval-and-breakglass` | 对高风险操作执行审批、双人复核、时限授权和事后审计。 |
| P0 | `sandbox-filesystem-network-isolation` | 限制文件路径、系统调用、进程、设备、网络出口、DNS 和凭据。 |
| P0 | `secret-broker-kms-and-key-isolation` | 不向模型暴露长期密钥，按租户和任务签发短期凭据并轮换。 |
| P1 | `confidential-workload-attestation` | 在需要时验证训练和推理环境、镜像和硬件可信状态。 |
| P0 | `direct-indirect-prompt-injection-defense` | 区分数据与指令，标记来源、降低权限并验证高风险操作意图。 |
| P0 | `tool-and-mcp-supply-chain-trust` | 校验第三方 Tool/MCP 的来源、权限、更新、依赖和返回内容。 |
| P0 | `memory-knowledge-poisoning-detection` | 识别恶意知识、持久化指令、错误高置信记录和跨任务污染。 |
| P0 | `training-data-poisoning-and-backdoor-scan` | 检测异常模式、触发器、标签投毒、来源集中和行为后门。 |
| P1 | `model-extraction-membership-audit` | 评估模型抽取、成员推断和训练数据记忆风险。 |
| P0 | `training-data-exfiltration-defense` | 阻止 Prompt、日志、Trace、Adapter 和输出泄露训练或客户数据。 |
| P0 | `generated-code-secret-license-scan` | 对生成代码、配置、依赖和文档执行秘密、许可证与版权检查。 |
| P0 | `dependency-vulnerability-and-sbom` | 生成 SBOM、扫描漏洞、评估可利用性并绑定修复证据。 |
| P0 | `ai-ml-bom-and-model-provenance` | 记录模型、数据集、训练方法、框架、Adapter 和部署依赖。 |
| P0 | `artifact-signing-and-verification` | 对 Skill、模型、Adapter、数据集、镜像和证据签名并在使用前验证。 |
| P0 | `tamper-evident-audit-log` | 记录不可抵赖的身份、决策、工具、数据、训练、发布和审批事件。 |
| P0 | `data-residency-retention-deletion` | 按地域、合同、用途和保留期控制数据位置、归档和删除。 |
| P0 | `consent-purpose-and-secondary-use` | 验证收集目的、训练用途、跨租户聚合和二次使用是否获得授权。 |
| P0 | `personal-data-rights-operations` | 支持访问、更正、导出、删除、限制处理和影响范围定位。 |
| P0 | `cross-border-transfer-control` | 对跨境数据、模型更新、日志和支持访问执行规则与审批。 |
| P1 | `legal-hold-and-evidence-preservation` | 在争议或调查期间冻结相关版本、日志、数据和证据链。 |
| P0 | `tenant-key-and-cache-isolation` | 确保对象、向量、缓存、Adapter、Checkpoint 和备份按租户隔离。 |
| P1 | `privacy-preserving-federated-learning` | 为联邦 Adapter 学习增加安全聚合、更新裁剪和异常客户端检测。 |
| P0 | `security-incident-response-and-forensics` | 检测、隔离、回滚、保全证据、通知和复盘 AI/Agent 安全事件。 |
| P0 | `agentic-redteam-automation` | 覆盖目标劫持、工具滥用、权限滥用、记忆污染、级联失败和 Rogue Agent。 |
| P0 | `nist-ai-rmf-control-profile` | 将 Govern、Map、Measure、Manage 映射到 Elmos 控制与证据。 |
| P0 | `iso42001-ai-management-profile` | 建立 AI 管理体系所需的职责、风险、数据、监控和持续改进证据。 |
| P1 | `eu-ai-act-readiness-profile` | 按产品角色和风险场景维护透明度、文档、监控和事件响应准备度。 |
| P0 | `china-ai-data-compliance-profile` | 维护中国网络、数据、个人信息、生成式 AI 备案/登记和标识要求映射。 |
| P1 | `soc2-iso27001-evidence-profile` | 复用身份、变更、访问、备份、监控和事件证据支持企业审计。 |
| P0 | `security-disaster-recovery` | 验证密钥、Registry、模型、知识、任务状态和审计系统的恢复能力。 |
| P1 | `policy-simulation-and-impact` | 在发布策略前模拟允许/拒绝变化、误伤率和权限爆炸半径。 |

## 12-observability-lineage-finops

**Kernel：** Cross-Cutting Observability and Economics Plane

统一追踪知识、检索、Skill、模型、工具、训练、证据、成本和业务价值，并支持重放和根因分析。

| Priority | Skill | Description |
|---|---|---|
| P0 | `genai-opentelemetry-instrumentation` | 为模型、Agent、Tool、MCP、检索和记忆输出统一 Trace、Metric 和 Event。 |
| P0 | `elmos-trace-semantic-schema` | 定义 Task、Turn、Environment、Skill、Knowledge、Model、Evidence 和 Cost 属性。 |
| P0 | `model-invocation-observability` | 记录模型版本、参数、Token、缓存、TTFT、Prefill、Decode、重试和结果。 |
| P0 | `skill-activation-and-workflow-trace` | 记录 Skill 候选、选择理由、版本、节点、审批、失败和回滚。 |
| P0 | `tool-call-and-side-effect-trace` | 记录工具输入、结果、权限、幂等键、资源、环境和副作用。 |
| P0 | `retrieval-and-context-trace` | 记录查询、候选、分数、过滤、引用、上下文预算和缓存命中。 |
| P1 | `memory-and-experience-trace` | 记录读写、压缩、遗忘、迁移、价值评分和污染决策。 |
| P0 | `training-run-and-checkpoint-trace` | 记录数据版本、代码、镜像、硬件、超参、Checkpoint、失败和恢复。 |
| P0 | `openlineage-compatible-emission` | 以 Dataset、Job、Run 和 Facet 表达数据与模型流水线血缘。 |
| P0 | `logs-metrics-traces-correlation` | 使用统一 ID 关联任务、模型、工具、仓库、部署和客户问题。 |
| P0 | `sensitive-content-capture-policy` | 默认不采集 Prompt、代码和工具内容，按明确授权进行过滤、截断或加密采集。 |
| P0 | `token-gpu-storage-network-accounting` | 核算输入输出 Token、缓存、GPU 秒、存储、网络和第三方工具费用。 |
| P0 | `task-tenant-project-cost-attribution` | 把成本精确归属到任务、用户、项目、业务线、模型和 Skill。 |
| P0 | `wall-clock-eta-and-progress-model` | 基于仓库规模、历史节点、队列和失败概率预测机器执行 ETA 与进度。 |
| P1 | `failure-probability-and-risk-forecast` | 预测任务节点失败、超预算、需人工和无法认证的概率。 |
| P0 | `quality-slo-and-business-dashboard` | 统一展示正确性、认证、延迟、可用性、成本、收入和毛利。 |
| P1 | `quality-cost-pareto-analysis` | 比较模型、Skill、缓存和验证策略的质量—成本—时间前沿。 |
| P1 | `cache-retrieval-skill-effectiveness` | 评估缓存命中质量、检索贡献、Skill 增益和无效激活。 |
| P0 | `model-data-knowledge-drift` | 监控输入、输出、失败、知识时效、数据分布和能力指标漂移。 |
| P1 | `adapter-reward-evaluator-drift` | 监控租户 Adapter、奖励函数和模型裁判随时间的偏移。 |
| P0 | `anomaly-detection-and-root-cause` | 关联发布、流量、数据、依赖、模型和环境变化定位异常。 |
| P0 | `task-and-training-run-replay` | 从 Trace、快照和发布组合重放任务或训练运行。 |
| P0 | `chargeback-showback-and-billing-feed` | 向计费系统输出可对账的用量、折扣、退款和成本明细。 |
| P0 | `budget-guard-and-auto-throttle` | 在账户、任务、模型和 GPU 预算接近阈值时降级、暂停或审批。 |
| P1 | `cost-capacity-and-margin-forecast` | 预测成本、容量、队列、收入、毛利和扩容需求。 |
| P0 | `audit-and-customer-evidence-export` | 导出脱敏 Trace、证据、SLO、数据血缘和认证报告。 |
| P1 | `observability-schema-versioning` | 管理遥测 Schema 演进、采集端兼容和历史查询迁移。 |
| P0 | `telemetry-loss-and-integrity-monitor` | 检测丢失、重复、乱序、篡改和采样偏差，避免错误运营结论。 |

## 13-commercial-multitenant-platform

**Kernel：** Commercial Control Plane

把知识、Skill 和模型能力产品化为可计量、可授权、可私有部署、可验收和可支持的多租户服务。

| Priority | Skill | Description |
|---|---|---|
| P0 | `tenant-org-project-repo-hierarchy` | 管理组织、租户、工作区、项目、仓库、分支、环境和成员关系。 |
| P0 | `feature-entitlement-and-license` | 按套餐、合同、地区、私有部署和试用授予模型、Skill、并发和认证能力。 |
| P0 | `quota-concurrency-and-fairness` | 执行每账户并发、队列、公平调度、优先级和资源上限。 |
| P0 | `credit-wallet-and-reservation` | 在长任务开始前预留余额，按实际用量结算、释放和处理超额。 |
| P0 | `subscription-and-project-pricing` | 支持订阅、Usage Credit、按项目、按仓库规模和混合计费。 |
| P0 | `usage-billing-reconciliation` | 对模型、GPU、工具和退款事件去重、汇总并与供应商账单对账。 |
| P0 | `invoice-and-cost-evidence` | 生成可审计的账单明细、成本归因、税务字段和客户异议证据。 |
| P0 | `sla-slo-and-service-credit` | 把可用性、完成时间、恢复、数据丢失和质量承诺绑定补偿规则。 |
| P0 | `customer-acceptance-report` | 输出需求覆盖、测试、证据、未决风险、环境和交付物清单。 |
| P0 | `support-diagnostic-bundle` | 在不泄露客户秘密的前提下导出版本、Trace、错误、依赖和健康信息。 |
| P0 | `private-airgap-deployment-packager` | 生成镜像、模型、Skill、知识、许可证、更新、备份和 Runbook 离线包。 |
| P1 | `tenant-knowledge-pack-lifecycle` | 支持客户知识包的导入、更新、验证、冻结、导出和删除。 |
| P1 | `tenant-adapter-commercial-lifecycle` | 管理租户 Adapter 的训练授权、成本、部署、升级、归属和退出。 |
| P0 | `data-sharing-optin-and-reward` | 让客户选择是否贡献匿名经验，并记录回报、范围和撤回。 |
| P0 | `tenant-export-delete-and-offboarding` | 完整导出客户资产、吊销访问、删除数据并提供完成证明。 |
| P1 | `tenant-region-migration` | 在保持身份、加密、血缘和停机目标下迁移区域或私有环境。 |
| P0 | `feature-flag-and-safe-release` | 按租户、业务线、风险和版本逐步开放能力并快速关闭。 |
| P1 | `skill-pack-marketplace-governance` | 管理内部、合作伙伴和客户 Skill 包的签名、定价、权限和责任。 |
| P1 | `partner-and-professional-services-handoff` | 把项目规则、知识、Skill、验收和运营责任标准化交接。 |
| P0 | `admin-audit-and-policy-console` | 提供租户、权限、用量、模型、Skill、知识、风险和审计统一控制台。 |
| P1 | `customer-specific-policy-pack` | 把客户编码规范、安全、数据和上线要求封装为版本化策略包。 |
| P0 | `commercial-margin-and-unit-economics` | 计算单任务、单租户、业务线和模型组合的收入、成本与毛利。 |
| P1 | `customer-success-quality-signals` | 识别采用、失败、复核负担、节省时间和续费风险，但不越权采集内容。 |
| P0 | `supportability-and-lts-policy` | 定义长期支持版本、补丁、升级路径、停服通知和安全修复承诺。 |

## 14-human-governance-operations

**Kernel：** Human Assurance Plane

建立专家复核、责任分配、例外管理、反馈质量和人机协同的可审计治理机制。

| Priority | Skill | Description |
|---|---|---|
| P0 | `expert-review-routing` | 按语言、框架、数据库、安全、业务和风险把问题分配给合适专家。 |
| P0 | `risk-based-human-approval-gates` | 根据副作用、客户级别、证据缺口和不确定性决定人工门。 |
| P0 | `annotation-and-comparison-workbench` | 支持轨迹、补丁、证据、偏好对和失败类型的高效标注。 |
| P0 | `reviewer-calibration-and-gold-check` | 通过标准样本、盲测和一致性指标校准审阅质量。 |
| P0 | `disagreement-adjudication` | 对模型、规则和专家分歧执行二审、仲裁和决策依据沉淀。 |
| P0 | `human-feedback-capture-and-lineage` | 记录反馈来源、范围、版本、意图、置信度和后续使用。 |
| P1 | `human-edit-causal-attribution` | 判断人工修改是修错、补需求、偏好、环境差异还是格式调整。 |
| P0 | `evidence-explanation-ui` | 以代码位置、差分、测试、反例、风险和来源展示结论。 |
| P0 | `decision-trace-and-accountability` | 记录谁在何时基于什么证据批准、拒绝、豁免或回滚。 |
| P0 | `raci-and-asset-ownership` | 为知识、Skill、数据集、模型、策略、发布和事件明确 RACI。 |
| P1 | `change-advisory-and-model-risk-board` | 对高风险模型、训练和生产变更执行跨职能评审。 |
| P0 | `waiver-exception-and-expiry` | 允许受控例外，但必须包含理由、补偿控制、期限和复审。 |
| P0 | `knowledge-data-model-stewardship` | 建立知识 Steward、数据 Owner、模型 Owner 和 Skill Maintainer 制度。 |
| P0 | `incident-command-and-communications` | 明确事件指挥、技术处置、客户沟通、法律和复盘职责。 |
| P1 | `redteam-blueteam-learning-loop` | 将攻击发现、修复、验证和新测试纳入持续改进。 |
| P0 | `audit-readiness-package` | 按审计目标组织政策、证据、抽样、变更、访问和事件材料。 |
| P0 | `training-consent-operations` | 让租户和数据 Owner 管理训练授权、范围、期限和撤回。 |
| P0 | `feedback-manipulation-defense` | 检测恶意评分、刷样本、利益冲突和低质量反馈进入训练。 |
| P1 | `human-overreliance-and-automation-bias` | 通过界面、抽检和培训降低对模型分数和自动证据的盲从。 |
| P0 | `escalation-sla-reversibility-transparency` | 定义升级时限、人工接管、撤销路径和对用户透明的信息。 |

## 15-domain-engineering-packs

**Kernel：** Domain Packs over K1-K8

把 Elmos 四条核心业务线及前端平台转换的深层语义、验证和训练资产封装为领域 Skill。

| Priority | Skill | Description |
|---|---|---|
| P0 | `spring-legacy-inventory-and-version-graph` | 识别 Struts、Servlet、Spring、JSP、依赖、容器、Java 版本和混合技术栈。 |
| P0 | `spring-route-request-binding-migration` | 迁移路由、HTTP 方法、参数绑定、上传、编码、Locale 和响应语义。 |
| P0 | `spring-session-state-migration` | 保持 Session、Cookie、Flash、并发访问、失效和序列化行为。 |
| P0 | `spring-filter-interceptor-listener-migration` | 迁移 Filter、Interceptor、Listener、生命周期和执行顺序。 |
| P0 | `spring-view-template-migration` | 迁移 JSP、Taglib、Tiles、Freemarker 和视图解析及前后端契约。 |
| P0 | `spring-validation-exception-migration` | 迁移校验、错误码、消息、异常映射、状态码和事务回滚规则。 |
| P0 | `spring-transaction-persistence-migration` | 迁移 JDBC、Hibernate、MyBatis、事务传播、锁和 Lazy 语义。 |
| P0 | `spring-security-equivalence` | 保持认证、授权、CSRF、Session Fixation、密码和方法级安全。 |
| P1 | `spring-messaging-batch-scheduling-migration` | 迁移消息、定时、批处理、重试、幂等和死信行为。 |
| P0 | `spring-build-dependency-boot4-modernization` | 升级构建、依赖、Jakarta 命名空间、容器和 Spring Boot 4 配置。 |
| P0 | `spring-shadow-differential-golden-route` | 通过影子流量、差分、回滚和真实大型仓库形成可付费 Golden Route。 |
| P0 | `cross-language-semantic-ir-compiler` | 把源语言解析为统一语义并按目标语言约束重新生成。 |
| P0 | `cross-language-type-and-nullability-mapping` | 处理数值、泛型、集合、Null、枚举、时间和领域值类型。 |
| P0 | `cross-language-control-error-equivalence` | 保持控制流、异常、资源释放、取消和错误传播。 |
| P0 | `cross-language-concurrency-memory-model` | 映射线程、协程、Actor、锁、原子性、所有权和内存可见性。 |
| P0 | `cross-language-framework-data-access` | 映射 Web、DI、ORM、缓存、消息、事务和配置框架。 |
| P0 | `cross-language-api-serialization-contract` | 保持 API、RPC、Schema、序列化、精度和兼容性。 |
| P1 | `cross-language-build-ffi-native-integration` | 迁移依赖、构建、C ABI、Native 库、平台能力和发布。 |
| P0 | `cross-language-repository-equivalence` | 通过可执行测试、差分、性能和语义覆盖认证整库转换。 |
| P0 | `sql-dialect-parser-and-semantic-ir` | 解析多数据库 SQL、PL/SQL、T-SQL、PL/pgSQL 和扩展语法。 |
| P0 | `sql-type-function-operator-mapping` | 映射类型、隐式转换、函数、运算符、Collation、时区和 Null。 |
| P0 | `sql-ddl-dml-constraint-conversion` | 转换表、索引、约束、分区、序列、Identity、MERGE 和 Upsert。 |
| P0 | `sql-routine-control-dynamic-conversion` | 转换过程、函数、包、游标、控制流、动态 SQL 和临时对象。 |
| P0 | `sql-transaction-isolation-exception` | 保持事务、保存点、隔离、锁、异常和错误码语义。 |
| P1 | `sql-json-spatial-fulltext-special-types` | 转换 JSON、数组、空间、全文、XML 和厂商专有类型。 |
| P0 | `sql-schema-data-result-differential` | 比较 Schema、数据、结果集、顺序、精度、副作用和错误。 |
| P0 | `sql-plan-performance-certification` | 比较执行计划、索引、统计、锁和性能，阻止语义正确但不可用的转换。 |
| P0 | `project-requirement-to-architecture` | 从需求生成边界、模块、ADR、数据流、部署和非功能约束。 |
| P0 | `project-schema-api-module-generation` | 联合生成数据库、API、事件、模块、代码和契约测试。 |
| P0 | `project-security-observability-foundation` | 默认生成身份、权限、审计、秘密、Trace、Metric 和健康检查。 |
| P0 | `project-test-deploy-doc-certification` | 生成测试、CI/CD、IaC、Runbook、架构文档和生产认证材料。 |
| P0 | `frontend-component-state-semantic-ir` | 抽取组件、Props、状态、响应式、生命周期、样式和可复用逻辑。 |
| P0 | `frontend-navigation-form-network-auth` | 迁移路由、表单、校验、请求、缓存、认证和权限。 |
| P0 | `frontend-platform-api-and-miniapp-targets` | 适配微信、支付宝、抖音、小红书小程序及平台权限和限制。 |
| P0 | `frontend-visual-accessibility-differential` | 执行截图、交互、布局、主题、响应式和无障碍差分。 |
| P0 | `automated-test-gap-generation-repair` | 分析测试缺口，生成并执行功能、性能、UI、压力、安全和变异测试。 |
| P0 | `domain-proof-and-certification-pack` | 为每条业务线维护专用不变量、反例、证据模板和 E0-E5 门。 |

## 16-self-evolution-release-engineering

**Kernel：** Learning Flywheel and Release Kernel

在严格证据、隔离和人工治理下发现能力缺口，协同演进知识、Skill、数据与模型并安全发布。

| Priority | Skill | Description |
|---|---|---|
| P1 | `capability-gap-and-unknown-mining` | 从失败、人工接管、低置信、客户需求和未覆盖证据中发现能力缺口。 |
| P1 | `failure-cluster-to-roadmap` | 把高频或高损失败聚类转为 Skill、知识、数据、模型或工具路线项。 |
| P2 | `skill-gene-mutation-and-composition` | 在沙箱中变异触发、步骤、工具和验证组合，寻找更优 Skill。 |
| P1 | `automatic-eval-and-counterexample-generation` | 为新缺陷自动生成回归、边界、对抗和反例测试。 |
| P1 | `self-correction-with-independent-verifier` | 允许自动修复，但由独立验证器和发布门决定是否接受。 |
| P2 | `model-skill-knowledge-coevolution` | 评估问题应通过知识、Skill、模型或工具解决，避免盲目训练。 |
| P1 | `knowledge-to-skill-distillation` | 把稳定知识规则转为可执行 Skill，同时保留引用和版本条件。 |
| P2 | `skill-to-weight-distillation` | 将高频、稳定、跨仓库 Skill 轨迹蒸馏进模型并保留原 Skill 作为校验。 |
| P2 | `weight-to-skill-extraction` | 从模型稳定行为中提取可解释、可测试的显式 Skill。 |
| P1 | `rag-skill-weight-placement-decision` | 按变化频率、精确性、权限、成本和泛化性决定能力落点。 |
| P1 | `capability-calibration-and-boundary` | 持续更新模型和 Skill 擅长、薄弱、拒绝和人工升级边界。 |
| P2 | `automatic-curriculum-and-benchmark-builder` | 从真实失败生成分层课程和无泄漏的新基准。 |
| P1 | `external-research-and-standard-watch` | 跟踪模型、Agent、训练、标准、法规和关键依赖变化。 |
| P1 | `external-change-impact-analysis` | 判断新版本对知识、Skill、模型、评测、部署和客户承诺的影响。 |
| P1 | `deprecation-and-obsolescence-detection` | 发现旧文档、旧 API、失效 Skill、弱模型和不再安全的依赖。 |
| P2 | `experiment-proposal-and-causal-analysis` | 自动提出消融与对照实验，估计改动的因果收益而非相关性。 |
| P2 | `bandit-budget-allocation` | 在有限 GPU、Token 和专家时间下分配实验与数据标注预算。 |
| P1 | `active-data-and-transfer-planner` | 选择最有信息增益的数据并判断跨语言、跨框架迁移机会。 |
| P2 | `lifelong-learning-and-forgetting-control` | 联合管理持续学习、回放、遗忘、数据撤回和能力稳定性。 |
| P1 | `model-collapse-synthetic-ratio-monitor` | 监控合成数据占比、分布收缩、错误放大和多样性丢失。 |
| P1 | `reward-overoptimization-alignment-tax` | 检测奖励模型过拟合、长度偏差、投机和对基础能力的损害。 |
| P1 | `frontier-teacher-distillation-governance` | 选择教师、验证授权、过滤错误并记录教师版本和贡献。 |
| P1 | `quality-cost-time-pareto-promotion` | 只提升在质量、风险、成本和 Wall-clock 上有明确收益的组合。 |
| P0 | `immutable-release-candidate-assembly` | 组装模型、Adapter、Skill、知识快照、策略、工具镜像和评测证据。 |
| P0 | `p0-p5-and-e0-e5-release-gates` | 执行构建、部署、数据、模型、Skill、影子、金丝雀和长期认证门。 |
| P0 | `release-shadow-canary-auto-rollback` | 根据硬门和实时 SLO 自动暂停、回滚或扩大流量。 |
| P0 | `chaos-soak-backup-restore-certification` | 验证长稳、故障注入、备份、恢复、跨区和依赖失效。 |
| P0 | `recertification-trigger-engine` | 在模型、数据、知识、Skill、工具、法规或环境变化时触发相应复认证。 |
| P0 | `golden-route-production-certifier` | 对 Spring、SQL、跨语言和项目生成 Golden Route 形成可重复商业认证。 |
| P1 | `autonomous-improvement-safety-budget` | 限定自动演进的权限、预算、环境、数据和最大影响范围。 |

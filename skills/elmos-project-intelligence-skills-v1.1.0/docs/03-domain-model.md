# 领域模型

## 1. Project Context

| 实体 | 说明 | 关键字段 |
|---|---|---|
| Tenant | 企业或个人隔离域 | id, plan, residency, policy |
| Project | 一个可理解的软件项目 | id, tenant_id, name, classification |
| SystemWorkspace | 多仓库组成的完整系统 | id, project_ids, topology |
| Repository | Git/上传来源 | provider, remote_ref, credential_ref |
| Revision | 不可变代码版本 | commit_sha/content_hash, branch, manifest |
| SourceBlob | 内容寻址对象 | hash, size, mime, encryption_key_ref |
| ProjectFingerprint | 技术栈和复杂度 | languages, frameworks, build_units, risks |

## 2. Analysis Context

| 实体 | 说明 |
|---|---|
| AnalysisRun | 一次固定输入和工具版本的分析 |
| AnalysisStage | ingest/parse/graph/flow/artifact 等阶段 |
| CodeIRShard | 文件或构建单元的标准化 IR |
| ParseDiagnostic | 解析失败、不支持和低置信度 |
| Symbol | 类型、函数、字段、模块等代码符号 |
| GraphNode/GraphEdge | 统一图谱节点和关系 |
| ProjectionView | C4、Flow、Data、API 等投影视图 |
| RuntimeObservation | 特定环境和时间窗口的运行证据 |

## 3. Evidence Context

| 实体 | 说明 |
|---|---|
| Evidence | 文件行、AST、配置、Schema、测试、Trace、日志 |
| Claim | 文档或图表中的可判断结论 |
| ClaimEvidence | Claim 与 Evidence 的支持/反驳关系 |
| Inference | 使用规则/模型从证据得出的推断 |
| Recommendation | 与当前事实分离的改进建议 |
| ConfidencePolicy | 置信度计算和阈值 |
| EvidenceBundle | 可离线核验的证据集合 |

## 4. Knowledge Context

| 实体 | 说明 |
|---|---|
| ArchitectureModel | 系统、容器、组件、模块、部署、安全视角 |
| Capability | 业务域、能力、功能、子功能 |
| FeatureTrace | 功能到页面/API/代码/数据/测试 |
| Flow | 业务或技术流程 |
| FlowStep/FlowEdge | 步骤、分支、并行、异常、补偿 |
| DataAsset | DB/表/字段/缓存/文件/索引 |
| DataLineage | 字段或资产的来源、转换和去向 |
| ApiContract | API/Schema/Auth/Error/Version |
| EventContract | Topic/Producer/Consumer/Retry/DLQ |
| ArchitectureRule | 架构约束 |
| Violation/Drift/Risk | 违规、漂移、风险和处置 |

## 5. Artifact Context

| 实体 | 说明 |
|---|---|
| Artifact | Diagram/Document/Presentation/Report/Explanation |
| ArtifactVersion | 固定 revision 和 generator 的不可变版本 |
| ArtifactBlock | 文档段落、图节点、Slide 页面/元素 |
| EvidenceBinding | ArtifactBlock 到 Claim/Evidence |
| HumanOverride | 人工内容或语义覆盖 |
| ArtifactLock | 内容、语义、布局、整页或整章锁定 |
| MergeConflict | 新旧生成与人工内容冲突 |
| Review/Approval | 草稿、评审、批准、认证 |
| Export | PPTX/DOCX/PDF/SVG/ZIP 等输出 |

## 6. Execution Context

| 实体 | 说明 |
|---|---|
| Job | 用户可见长任务 |
| WorkflowRun | durable workflow 实例 |
| Checkpoint | 可恢复阶段状态 |
| IdempotencyRecord | 外部副作用防重 |
| CacheEntry | 内容寻址缓存 |
| Estimate | 机器 ETA、Token、计算、存储、人审 |
| UsageEvent | 商业计量 |
| AuditEvent | 谁在何时对什么做了什么 |

## 7. 关键不变量

1. `Revision` 不可变。
2. `ArtifactVersion` 不可变；更新产生新版本。
3. `Confirmed Claim` 必须至少有一个可用 Evidence。
4. 人工 override 不改变原始分析事实。
5. `Certified` Artifact 不允许引用 stale Evidence。
6. Job 恢复必须验证输入 manifest 和权限。
7. 外部副作用必须有唯一 idempotency key。
8. Graph/Search 投影可重建，但 Evidence/Audit 不可随意丢弃。

# Skill Catalog

Package version: `1.0.0` · generated/as-of: `2026-08-19` · canonical count: **50**

| # | Skill | 触发边界 | 直接依赖 |
|---:|---|---|---|
| 01 | [`elmos-multimodal-input-orchestrator`](../skills/elmos-multimodal-input-orchestrator/SKILL.md)<br>统一多模态输入总控 | 为 Elmos 实现统一多模态输入总控；当任务涉及音频、图片、PDF、Word、Markdown、TXT、文件夹或压缩包接入、解析编排与下游交接时使用。 | `elmos-unified-multimodal-content-ir`, `elmos-source-anchor-and-provenance`, `elmos-durable-processing-and-recovery` |
| 02 | [`elmos-secure-resumable-upload`](../skills/elmos-secure-resumable-upload/SKILL.md)<br>安全断点续传 | 实现 Elmos 安全、幂等、可恢复的文件与大对象上传；当任务涉及分片上传、断点续传、预签名 URL、校验和或客户端重连时使用。 | — |
| 03 | [`elmos-file-type-detection-and-validation`](../skills/elmos-file-type-detection-and-validation/SKILL.md)<br>文件类型识别与验证 | 实现扩展名、MIME、文件魔数和内容特征联合识别；当任务涉及文件格式验证、伪装文件阻止或解析器选择时使用。 | — |
| 04 | [`elmos-malware-quarantine-and-sandbox`](../skills/elmos-malware-quarantine-and-sandbox/SKILL.md)<br>恶意文件隔离与解析沙箱 | 实现上传内容恶意扫描、隔离区和解析沙箱；当任务涉及病毒、Office 宏、PDF 脚本、解析器漏洞或不可信文件执行边界时使用。 | `elmos-file-type-detection-and-validation` |
| 05 | [`elmos-audio-asr-and-diarization`](../skills/elmos-audio-asr-and-diarization/SKILL.md)<br>音频识别与说话人分离 | 实现音频预处理、ASR、语言检测、时间戳和说话人分离；当用户上传录音、会议音频或口述需求时使用。 | `elmos-provider-routing-and-fallback`, `elmos-source-anchor-and-provenance` |
| 06 | [`elmos-image-ocr-and-preprocessing`](../skills/elmos-image-ocr-and-preprocessing/SKILL.md)<br>图片 OCR 与预处理 | 实现图片旋转、校正、增强、切片和 OCR；当任务涉及扫描件、截图、照片、手写文字或图像文本提取时使用。 | `elmos-provider-routing-and-fallback`, `elmos-source-anchor-and-provenance` |
| 07 | [`elmos-visual-ui-understanding`](../skills/elmos-visual-ui-understanding/SKILL.md)<br>UI 截图理解 | 把 Web、移动端或桌面端截图解析为页面结构、组件、状态和交互意图；当任务涉及截图生成前端、UI 复刻或视觉验收时使用。 | `elmos-image-ocr-and-preprocessing`, `elmos-source-anchor-and-provenance` |
| 08 | [`elmos-diagram-and-architecture-understanding`](../skills/elmos-diagram-and-architecture-understanding/SKILL.md)<br>图表与架构图理解 | 解析流程图、架构图、数据流图、UML、ER 图和手绘图；当任务涉及从图中恢复系统节点、关系、边界或数据流时使用。 | `elmos-image-ocr-and-preprocessing`, `elmos-source-anchor-and-provenance` |
| 09 | [`elmos-pdf-layout-table-parser`](../skills/elmos-pdf-layout-table-parser/SKILL.md)<br>PDF 版面与表格解析 | 解析原生、扫描和图文混合 PDF 的文字、表格、图片、目录与版面；当任务涉及 PDF 需求文档或报告接入时使用。 | `elmos-image-ocr-and-preprocessing`, `elmos-source-anchor-and-provenance` |
| 10 | [`elmos-word-document-parser`](../skills/elmos-word-document-parser/SKILL.md)<br>Word 文档解析 | 解析 DOCX/DOC 的标题、表格、图片、批注、修订、脚注和链接；当任务涉及 Word 需求、UAT 报告或版本差异时使用。 | `elmos-malware-quarantine-and-sandbox`, `elmos-source-anchor-and-provenance` |
| 11 | [`elmos-markdown-text-log-parser`](../skills/elmos-markdown-text-log-parser/SKILL.md)<br>Markdown、TXT 与日志解析 | 解析 Markdown/MDX、TXT、配置和日志文件；当任务涉及代码块、行号、日志堆栈、编码识别或超大文本流处理时使用。 | `elmos-source-anchor-and-provenance` |
| 12 | [`elmos-unified-multimodal-content-ir`](../skills/elmos-unified-multimodal-content-ir/SKILL.md)<br>统一多模态内容 IR | 设计并实现 Elmos 的统一多模态内容中间表示；当多个解析器需要共享内容块、关系、质量和来源结构时使用。 | — |
| 13 | [`elmos-source-anchor-and-provenance`](../skills/elmos-source-anchor-and-provenance/SKILL.md)<br>来源锚点与证据链 | 为所有提取、推断、需求和生成结果建立原始来源定位；当任务要求页码、坐标、时间戳、行号、代码范围或证据追溯时使用。 | `elmos-unified-multimodal-content-ir` |
| 14 | [`elmos-multimodal-requirement-extraction`](../skills/elmos-multimodal-requirement-extraction/SKILL.md)<br>多模态需求提取 | 从文档、音频、图片、图表和项目包中提取功能需求、非功能需求、约束与验收条件；当任务涉及需求理解或项目生成前置分析时使用。 | `elmos-source-anchor-and-provenance`, `elmos-multi-asset-content-fusion` |
| 15 | [`elmos-multi-asset-content-fusion`](../skills/elmos-multi-asset-content-fusion/SKILL.md)<br>多资产内容融合 | 将一次提交中的多个文件、图片、音频和项目目录融合为统一项目上下文；当任务涉及跨文件关联、去重或资料角色识别时使用。 | `elmos-unified-multimodal-content-ir`, `elmos-source-anchor-and-provenance` |
| 16 | [`elmos-document-version-and-conflict-detection`](../skills/elmos-document-version-and-conflict-detection/SKILL.md)<br>文档版本与冲突检测 | 识别输入资料的版本、覆盖关系和需求冲突；当 PDF、Word、录音、截图或项目包对同一事项表述不一致时使用。 | `elmos-multi-asset-content-fusion`, `elmos-source-anchor-and-provenance` |
| 17 | [`elmos-human-review-and-correction`](../skills/elmos-human-review-and-correction/SKILL.md)<br>人工审阅与纠错 | 为 OCR、ASR、文档解析、图表识别、需求提取和冲突提供人工复核闭环；当系统结果低置信度或用户需要修正时使用。 | `elmos-source-anchor-and-provenance` |
| 18 | [`elmos-prompt-injection-defense`](../skills/elmos-prompt-injection-defense/SKILL.md)<br>多模态提示注入防护 | 防止 PDF、Word、图片、音频、代码和网页内容中的指令控制 Agent 或扩大权限；当用户输入会进入 LLM 上下文或触发工具时使用。 | `elmos-source-anchor-and-provenance`, `elmos-downstream-agent-integration` |
| 19 | [`elmos-provider-routing-and-fallback`](../skills/elmos-provider-routing-and-fallback/SKILL.md)<br>解析与模型供应商路由 | 为 ASR、OCR、视觉、嵌入和 LLM 提供可替换供应商路由、熔断和降级；当任务涉及模型选择、成本、隐私约束或 provider 故障时使用。 | — |
| 20 | [`elmos-storage-index-and-retrieval`](../skills/elmos-storage-index-and-retrieval/SKILL.md)<br>存储、索引与检索 | 设计原始资产、内容 IR、全文、向量、符号和图关系的分层存储与检索；当任务涉及项目知识库、搜索或按需装载上下文时使用。 | `elmos-unified-multimodal-content-ir`, `elmos-source-anchor-and-provenance` |
| 21 | [`elmos-durable-processing-and-recovery`](../skills/elmos-durable-processing-and-recovery/SKILL.md)<br>持久任务执行与恢复 | 实现长时间解析和索引任务的检查点、恢复、取消与幂等副作用；当客户端断线、服务重启或 worker 崩溃后仍需继续时使用。 | — |
| 22 | [`elmos-processing-cost-and-eta-estimation`](../skills/elmos-processing-cost-and-eta-estimation/SKILL.md)<br>处理成本与机器 ETA | 估算并追踪 Elmos 自身处理任务的机器墙钟时间、资源成本和模型成本；当页面需要进度、预计完成时间或任务核算时使用。 | `elmos-durable-processing-and-recovery`, `elmos-multimodal-observability` |
| 23 | [`elmos-multimodal-observability`](../skills/elmos-multimodal-observability/SKILL.md)<br>多模态可观测性 | 为上传、扫描、解析、融合、索引、上下文和下游调用建立统一 Trace、Metrics、Logs；当任务涉及排障、SLO、成本或审计时使用。 | — |
| 24 | [`elmos-multimodal-evaluation-framework`](../skills/elmos-multimodal-evaluation-framework/SKILL.md)<br>多模态评测框架 | 为 OCR、ASR、版面、UI、图表、需求提取、检索和上下文保持建立可重复评测；当需要验证质量、回归或 provider 更换时使用。 | — |
| 25 | [`elmos-multimodal-input-workbench-ui`](../skills/elmos-multimodal-input-workbench-ui/SKILL.md)<br>多模态输入工作台 UI | 实现拖拽、录音、文件夹和压缩包上传、预览、进度、纠错和冲突审阅界面；当任务涉及 Elmos 多模态前端体验时使用。 | `elmos-ingestion-api-and-sdk`, `elmos-human-review-and-correction` |
| 26 | [`elmos-ingestion-api-and-sdk`](../skills/elmos-ingestion-api-and-sdk/SKILL.md)<br>接入 API 与 SDK | 设计多模态输入、上传、解析、查询、纠错和任务提交的版本化 API、SDK；当外部客户端、CLI 或服务需要接入 Elmos 时使用。 | `elmos-multimodal-input-orchestrator`, `elmos-secure-resumable-upload` |
| 27 | [`elmos-data-retention-and-governance`](../skills/elmos-data-retention-and-governance/SKILL.md)<br>数据保留与治理 | 实现多租户输入资产、派生内容、索引、修正和审计数据的分类、保留、导出与彻底删除；当任务涉及隐私、合规或生命周期管理时使用。 | `elmos-storage-index-and-retrieval` |
| 28 | [`elmos-downstream-agent-integration`](../skills/elmos-downstream-agent-integration/SKILL.md)<br>下游 Agent 集成 | 把统一输入包安全交给需求分析、代码生成、转换、测试、修复和文档 Agent；当任务涉及多模态结果进入执行型 Agent 时使用。 | `elmos-prompt-injection-defense`, `elmos-context-budget-manager`, `elmos-source-anchor-and-provenance` |
| 29 | [`elmos-codex-context-capacity-parity`](../skills/elmos-codex-context-capacity-parity/SKILL.md)<br>Codex 同级上下文容量 | 让 Elmos 活跃上下文容量与当前 Codex 同级并动态适配；当任务涉及 1.05M 级窗口、模型切换或容量兼容时使用。 | `elmos-model-capability-discovery`, `elmos-context-budget-manager` |
| 30 | [`elmos-context-budget-manager`](../skills/elmos-context-budget-manager/SKILL.md)<br>上下文预算管理器 | 为每次模型调用分配系统、策略、技能、对话、文档、代码、工具结果和输出预算；当任务涉及长上下文装载和超限控制时使用。 | `elmos-model-capability-discovery`, `elmos-multimodal-token-accounting` |
| 31 | [`elmos-multimodal-token-accounting`](../skills/elmos-multimodal-token-accounting/SKILL.md)<br>多模态 Token 计量 | 当 Elmos 需要估算文本、代码、OCR、音频转录、图像、工具定义与工具结果对模型上下文和费用的占用时使用。 | `elmos-context-budget-manager`, `elmos-model-capability-discovery` |
| 32 | [`elmos-long-context-packing-and-ranking`](../skills/elmos-long-context-packing-and-ranking/SKILL.md)<br>长上下文装箱与排序 | 当任务候选证据超过活动上下文，必须在不丢失关键约束的前提下选择、排序、去重和装载内容时使用。 | `elmos-context-budget-manager`, `elmos-multimodal-token-accounting`, `elmos-source-anchor-and-provenance`, `elmos-repository-context-map` |
| 33 | [`elmos-context-pressure-monitor`](../skills/elmos-context-pressure-monitor/SKILL.md)<br>上下文压力监控 | 当长任务需要持续监视上下文窗口、预防溢出并按 NORMAL/ELEVATED/HIGH/CRITICAL 状态采取动作时使用。 | `elmos-context-budget-manager`, `elmos-multimodal-token-accounting`, `elmos-structured-context-compaction` |
| 34 | [`elmos-structured-context-compaction`](../skills/elmos-structured-context-compaction/SKILL.md)<br>结构化上下文压缩 | 当 Elmos 长任务上下文接近容量、需要移出旧历史但必须继续可靠执行时使用。 | `elmos-context-pressure-monitor`, `elmos-source-anchor-and-provenance`, `elmos-context-integrity-and-loss-detection` |
| 35 | [`elmos-context-checkpoint-and-recovery`](../skills/elmos-context-checkpoint-and-recovery/SKILL.md)<br>上下文检查点与恢复 | 当任务要跨会话、客户端断线、进程重启、模型故障或上下文阶段边界继续执行时使用。 | `elmos-durable-processing-and-recovery`, `elmos-structured-context-compaction`, `elmos-context-integrity-and-loss-detection` |
| 36 | [`elmos-context-rehydration`](../skills/elmos-context-rehydration/SKILL.md)<br>上下文重新水化 | 当当前任务需要之前已压缩、驱逐或仅索引保存的需求、代码、图表、录音、测试或决策时使用。 | `elmos-source-anchor-and-provenance`, `elmos-storage-index-and-retrieval`, `elmos-long-context-packing-and-ranking`, `elmos-context-checkpoint-and-recovery` |
| 37 | [`elmos-project-memory-and-retrieval`](../skills/elmos-project-memory-and-retrieval/SKILL.md)<br>项目长期记忆与检索 | 当项目资料、代码、决策、任务历史和测试证据总量长期超过活动上下文，需要跨任务保存和检索时使用。 | `elmos-storage-index-and-retrieval`, `elmos-source-anchor-and-provenance`, `elmos-data-retention-and-governance` |
| 38 | [`elmos-repository-context-map`](../skills/elmos-repository-context-map/SKILL.md)<br>仓库上下文地图 | 当 Elmos 需要在大型代码仓库中决定应加载哪些模块、文件、符号、配置和测试到活动上下文时使用。 | `elmos-source-anchor-and-provenance`, `elmos-storage-index-and-retrieval` |
| 39 | [`elmos-model-capability-discovery`](../skills/elmos-model-capability-discovery/SKILL.md)<br>模型能力发现与注册 | 当 Elmos 接入、切换或升级模型，需要确定上下文窗口、最大输出、模态、工具、结构化输出、价格和区域能力时使用。 | — |
| 40 | [`elmos-context-integrity-and-loss-detection`](../skills/elmos-context-integrity-and-loss-detection/SKILL.md)<br>上下文完整性与丢失检测 | 当上下文被装载、压缩、驱逐、切换模型、恢复任务或重新水化时，需要证明关键事实没有静默丢失或篡改时使用。 | `elmos-source-anchor-and-provenance`, `elmos-context-checkpoint-and-recovery` |
| 41 | [`elmos-folder-tree-input`](../skills/elmos-folder-tree-input/SKILL.md)<br>文件夹树输入 | 当用户通过浏览器、桌面端、CLI 或 SDK 提交一个或多个本地文件夹，并要求保留完整相对目录结构时使用。 | `elmos-multimodal-input-orchestrator`, `elmos-secure-resumable-upload`, `elmos-project-package-manifest` |
| 42 | [`elmos-resumable-multi-file-folder-upload`](../skills/elmos-resumable-multi-file-folder-upload/SKILL.md)<br>多文件夹断点续传 | 当大型文件夹含数千至数十万个文件，上传需要文件级/分片级并发、去重、暂停、恢复和失败隔离时使用。 | `elmos-secure-resumable-upload`, `elmos-folder-tree-input` |
| 43 | [`elmos-project-package-manifest`](../skills/elmos-project-package-manifest/SKILL.md)<br>项目包清单 | 当文件夹或归档需要形成不可变、可比较、可签名的项目包目录树和版本事实来源时使用。 | `elmos-file-type-detection-and-validation`, `elmos-source-anchor-and-provenance` |
| 44 | [`elmos-secure-zip-tar-extraction`](../skills/elmos-secure-zip-tar-extraction/SKILL.md)<br>安全 ZIP/TAR 解压 | 当用户上传 ZIP、TAR、TAR.GZ、TGZ 或 GZIP，需要检查、解密并在隔离环境中安全展开时使用。 | `elmos-malware-quarantine-and-sandbox`, `elmos-archive-bomb-and-path-traversal-defense`, `elmos-project-package-manifest` |
| 45 | [`elmos-archive-bomb-and-path-traversal-defense`](../skills/elmos-archive-bomb-and-path-traversal-defense/SKILL.md)<br>归档炸弹与路径穿越防御 | 当系统检查或展开任何归档、嵌套压缩包、链接或特殊条目，需要防止 Zip Slip、压缩炸弹和资源耗尽时使用。 | `elmos-file-type-detection-and-validation`, `elmos-malware-quarantine-and-sandbox` |
| 46 | [`elmos-project-root-language-framework-detection`](../skills/elmos-project-root-language-framework-detection/SKILL.md)<br>项目根、语言与框架识别 | 当文件夹或归档解包后需要自动判断真实项目根、monorepo/多项目结构、编程语言、框架、构建系统和入口点时使用。 | `elmos-project-package-manifest`, `elmos-ignore-generated-vendored-file-classification` |
| 47 | [`elmos-ignore-generated-vendored-file-classification`](../skills/elmos-ignore-generated-vendored-file-classification/SKILL.md)<br>忽略、生成与第三方文件分类 | 当项目包包含 node_modules、vendor、build、缓存、二进制、生成代码、日志或敏感文件，需要决定解析深度和上下文优先级时使用。 | `elmos-project-package-manifest`, `elmos-data-retention-and-governance` |
| 48 | [`elmos-repository-map-and-symbol-indexing`](../skills/elmos-repository-map-and-symbol-indexing/SKILL.md)<br>仓库地图与符号索引 | 当安全接入的项目包需要建立模块、包、类、接口、函数、API、数据库、消息、测试、配置和依赖图时使用。 | `elmos-project-root-language-framework-detection`, `elmos-ignore-generated-vendored-file-classification`, `elmos-repository-context-map` |
| 49 | [`elmos-project-package-version-and-incremental-update`](../skills/elmos-project-package-version-and-incremental-update/SKILL.md)<br>项目包版本与增量更新 | 当用户上传新版本文件夹/压缩包、部分文件或重新同步仓库，需要识别新增、修改、删除、重命名并增量更新索引时使用。 | `elmos-project-package-manifest`, `elmos-repository-map-and-symbol-indexing`, `elmos-project-memory-and-retrieval` |
| 50 | [`elmos-project-package-preview-and-review-ui`](../skills/elmos-project-package-preview-and-review-ui/SKILL.md)<br>项目包预览与审查界面 | 当用户上传文件夹或归档，需要在提交任务前查看目录树、解压风险、项目识别、忽略规则、敏感文件和索引状态时使用。 | `elmos-multimodal-input-workbench-ui`, `elmos-project-package-manifest`, `elmos-project-root-language-framework-detection`, `elmos-ignore-generated-vendored-file-classification` |

## 使用方法

每个 Skill 目录包含：

```text
<skill-name>/
├── SKILL.md
└── references/
    └── contract.yaml
```

`SKILL.md` 面向编码 Agent，包含触发条件、实施流程、强制规则、交付清单和验收门槛；`contract.yaml` 供编排器、评测和自动检查读取。

## 依赖原则

- 依赖表示实现时必须同时遵守的契约，不表示每次对话都要把依赖全文装入模型。
- 包级安全、来源、幂等、租户和完成定义适用于全部 Skills。
- 循环依赖应由共享数据契约或编排层拆开；`scripts/validate_package.py` 会检查未知依赖。
- 同一需求可触发多个 Skill，执行计划需明确主 Skill、辅助 Skill、数据所有者和验收负责人。
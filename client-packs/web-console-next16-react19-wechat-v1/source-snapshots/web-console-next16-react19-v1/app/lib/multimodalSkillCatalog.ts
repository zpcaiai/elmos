export const multimodalSkillCatalog = [
  ["elmos-multimodal-input-orchestrator", "统一多模态输入总控", "intake"],
  ["elmos-secure-resumable-upload", "安全断点续传", "intake"],
  ["elmos-file-type-detection-and-validation", "文件类型识别与验证", "security"],
  ["elmos-malware-quarantine-and-sandbox", "恶意文件隔离与解析沙箱", "security"],
  ["elmos-audio-asr-and-diarization", "音频识别与说话人分离", "parser"],
  ["elmos-image-ocr-and-preprocessing", "图片 OCR 与预处理", "parser"],
  ["elmos-visual-ui-understanding", "UI 截图理解", "parser"],
  ["elmos-diagram-and-architecture-understanding", "图表与架构图理解", "parser"],
  ["elmos-pdf-layout-table-parser", "PDF 版面与表格解析", "parser"],
  ["elmos-word-document-parser", "Word 文档解析", "parser"],
  ["elmos-markdown-text-log-parser", "Markdown、TXT 与日志解析", "parser"],
  ["elmos-unified-multimodal-content-ir", "统一多模态内容 IR", "content"],
  ["elmos-source-anchor-and-provenance", "来源锚点与证据链", "content"],
  ["elmos-multimodal-requirement-extraction", "多模态需求提取", "content"],
  ["elmos-multi-asset-content-fusion", "多资产内容融合", "content"],
  ["elmos-document-version-and-conflict-detection", "文档版本与冲突检测", "content"],
  ["elmos-human-review-and-correction", "人工审阅与纠错", "review"],
  ["elmos-prompt-injection-defense", "多模态提示注入防护", "security"],
  ["elmos-provider-routing-and-fallback", "解析与模型供应商路由", "platform"],
  ["elmos-storage-index-and-retrieval", "存储、索引与检索", "platform"],
  ["elmos-durable-processing-and-recovery", "持久任务执行与恢复", "platform"],
  ["elmos-processing-cost-and-eta-estimation", "处理成本与机器 ETA", "platform"],
  ["elmos-multimodal-observability", "多模态可观测性", "platform"],
  ["elmos-multimodal-evaluation-framework", "多模态评测框架", "platform"],
  ["elmos-multimodal-input-workbench-ui", "多模态输入工作台 UI", "surface"],
  ["elmos-ingestion-api-and-sdk", "接入 API 与 SDK", "surface"],
  ["elmos-data-retention-and-governance", "数据保留与治理", "governance"],
  ["elmos-downstream-agent-integration", "下游 Agent 集成", "surface"],
  ["elmos-codex-context-capacity-parity", "Codex 同级上下文容量", "context"],
  ["elmos-context-budget-manager", "上下文预算管理器", "context"],
  ["elmos-multimodal-token-accounting", "多模态 Token 计量", "context"],
  ["elmos-long-context-packing-and-ranking", "长上下文装箱与排序", "context"],
  ["elmos-context-pressure-monitor", "上下文压力监控", "context"],
  ["elmos-structured-context-compaction", "结构化上下文压缩", "context"],
  ["elmos-context-checkpoint-and-recovery", "上下文检查点与恢复", "context"],
  ["elmos-context-rehydration", "上下文重新水化", "context"],
  ["elmos-project-memory-and-retrieval", "项目长期记忆与检索", "context"],
  ["elmos-repository-context-map", "仓库上下文地图", "repository"],
  ["elmos-model-capability-discovery", "模型能力发现与注册", "context"],
  ["elmos-context-integrity-and-loss-detection", "上下文完整性与丢失检测", "context"],
  ["elmos-folder-tree-input", "文件夹树输入", "package"],
  ["elmos-resumable-multi-file-folder-upload", "多文件夹断点续传", "package"],
  ["elmos-project-package-manifest", "项目包清单", "package"],
  ["elmos-secure-zip-tar-extraction", "安全 ZIP/TAR 解压", "package"],
  ["elmos-archive-bomb-and-path-traversal-defense", "归档炸弹与路径穿越防御", "security"],
  ["elmos-project-root-language-framework-detection", "项目根、语言与框架识别", "repository"],
  ["elmos-ignore-generated-vendored-file-classification", "忽略、生成与第三方文件分类", "repository"],
  ["elmos-repository-map-and-symbol-indexing", "仓库地图与符号索引", "repository"],
  ["elmos-project-package-version-and-incremental-update", "项目包版本与增量更新", "repository"],
  ["elmos-project-package-preview-and-review-ui", "项目包预览与审查界面", "surface"],
] as const;

export type MultimodalSkillName = (typeof multimodalSkillCatalog)[number][0];
export type MultimodalSkillGroup = (typeof multimodalSkillCatalog)[number][2];

export const multimodalSkillNames = new Set<string>(
  multimodalSkillCatalog.map(([name]) => name),
);

export type MultimodalIntakePermission =
  | "intake:read"
  | "intake:write"
  | "intake:review"
  | "intake:admin";

// This is an intentionally closed mirror of the engine's v1 operation
// registry. A catalog entry without an exact operation pair is not an
// extension point and is rejected before authentication or child execution.
const operationsBySkill = {
  "elmos-archive-bomb-and-path-traversal-defense": ["inspect"],
  "elmos-audio-asr-and-diarization": ["parse", "process_asset"],
  "elmos-codex-context-capacity-parity": ["check"],
  "elmos-context-budget-manager": ["calculate"],
  "elmos-context-checkpoint-and-recovery": ["create", "diff", "list", "restore", "rollback"],
  "elmos-context-integrity-and-loss-detection": ["verify"],
  "elmos-context-pressure-monitor": ["monitor"],
  "elmos-context-rehydration": ["rehydrate"],
  "elmos-data-retention-and-governance": ["delete", "delete_status", "evaluate", "export", "provider_access"],
  "elmos-diagram-and-architecture-understanding": ["parse", "process_asset", "understand"],
  "elmos-document-version-and-conflict-detection": ["detect_conflicts"],
  "elmos-downstream-agent-integration": ["build_context", "get_context", "get_grant", "link_result", "list_result_links", "revoke_grant"],
  "elmos-durable-processing-and-recovery": ["get_task_state", "list_outbox", "mark_outbox_published", "process_durable_transition", "transition"],
  "elmos-file-type-detection-and-validation": ["inspect", "process_asset"],
  "elmos-folder-tree-input": ["append", "begin", "finalize", "page", "status"],
  "elmos-human-review-and-correction": [
    "approve", "claim", "correct", "current_correction", "edit", "enqueue",
    "enqueue_execute", "enqueue_prepare", "get", "list", "propagation_claim",
    "propagation_complete", "propagation_dispatch", "propagation_reconcile",
    "propagation_status", "reject", "reopen", "reservation_status", "revert",
    "source_get", "source_list", "source_register",
  ],
  "elmos-ignore-generated-vendored-file-classification": ["rebuild", "rollback", "status"],
  "elmos-image-ocr-and-preprocessing": ["parse", "process_asset"],
  "elmos-ingestion-api-and-sdk": ["build_contract", "capabilities", "describe", "health"],
  "elmos-long-context-packing-and-ranking": ["pack"],
  "elmos-malware-quarantine-and-sandbox": ["inspect", "process_asset"],
  "elmos-markdown-text-log-parser": ["parse", "process_asset"],
  "elmos-model-capability-discovery": ["discover", "history", "rollback"],
  "elmos-multi-asset-content-fusion": ["fuse"],
  "elmos-multimodal-evaluation-framework": ["catalog", "evaluate", "get_run", "verify"],
  "elmos-multimodal-input-orchestrator": ["bootstrap_project", "cancel_job", "create_session", "get_session", "process_session", "resume_job"],
  "elmos-multimodal-input-workbench-ui": ["build_preview", "capabilities", "describe", "health"],
  "elmos-multimodal-observability": ["observe"],
  "elmos-multimodal-requirement-extraction": ["extract"],
  "elmos-multimodal-token-accounting": ["account"],
  "elmos-pdf-layout-table-parser": ["parse", "process_asset"],
  "elmos-processing-cost-and-eta-estimation": ["estimate"],
  "elmos-project-memory-and-retrieval": ["delete", "query", "rebuild_status", "repair", "write"],
  "elmos-project-package-manifest": ["diff", "finalize", "page"],
  "elmos-project-package-preview-and-review-ui": ["override", "page", "undo"],
  "elmos-project-package-version-and-incremental-update": ["diff"],
  "elmos-project-root-language-framework-detection": ["rebuild", "rollback", "status"],
  "elmos-prompt-injection-defense": ["evaluate"],
  "elmos-provider-routing-and-fallback": ["route"],
  "elmos-repository-context-map": ["rebuild", "rollback", "status"],
  "elmos-repository-map-and-symbol-indexing": ["rebuild", "rollback", "status"],
  "elmos-resumable-multi-file-folder-upload": ["confirm_part", "negotiate", "status"],
  "elmos-secure-resumable-upload": ["abort", "commit", "start", "status", "upload_part"],
  "elmos-secure-zip-tar-extraction": ["expand_nested", "extract", "publish"],
  "elmos-source-anchor-and-provenance": ["anchor"],
  "elmos-storage-index-and-retrieval": ["delete", "query", "rebuild_status", "repair", "upsert"],
  "elmos-structured-context-compaction": ["compact"],
  "elmos-unified-multimodal-content-ir": ["normalize"],
  "elmos-visual-ui-understanding": ["parse", "process_asset", "understand"],
  "elmos-word-document-parser": ["parse", "process_asset"],
} as const satisfies Record<MultimodalSkillName, readonly string[]>;

const readOnlyOperationPairs = new Set<string>([
  "elmos-archive-bomb-and-path-traversal-defense\0inspect",
  "elmos-codex-context-capacity-parity\0check",
  "elmos-context-budget-manager\0calculate",
  "elmos-context-checkpoint-and-recovery\0diff",
  "elmos-context-checkpoint-and-recovery\0list",
  "elmos-context-integrity-and-loss-detection\0verify",
  "elmos-context-pressure-monitor\0monitor",
  "elmos-data-retention-and-governance\0delete_status",
  "elmos-data-retention-and-governance\0evaluate",
  "elmos-data-retention-and-governance\0provider_access",
  "elmos-downstream-agent-integration\0get_context",
  "elmos-downstream-agent-integration\0get_grant",
  "elmos-downstream-agent-integration\0list_result_links",
  "elmos-durable-processing-and-recovery\0get_task_state",
  "elmos-durable-processing-and-recovery\0list_outbox",
  "elmos-file-type-detection-and-validation\0inspect",
  "elmos-folder-tree-input\0page",
  "elmos-folder-tree-input\0status",
  "elmos-ingestion-api-and-sdk\0build_contract",
  "elmos-ingestion-api-and-sdk\0capabilities",
  "elmos-ingestion-api-and-sdk\0describe",
  "elmos-ingestion-api-and-sdk\0health",
  "elmos-malware-quarantine-and-sandbox\0inspect",
  "elmos-model-capability-discovery\0history",
  "elmos-multimodal-evaluation-framework\0catalog",
  "elmos-multimodal-evaluation-framework\0get_run",
  "elmos-multimodal-evaluation-framework\0verify",
  "elmos-multimodal-input-orchestrator\0get_session",
  "elmos-multimodal-input-workbench-ui\0build_preview",
  "elmos-multimodal-input-workbench-ui\0capabilities",
  "elmos-multimodal-input-workbench-ui\0describe",
  "elmos-multimodal-input-workbench-ui\0health",
  "elmos-processing-cost-and-eta-estimation\0estimate",
  "elmos-project-memory-and-retrieval\0query",
  "elmos-project-memory-and-retrieval\0rebuild_status",
  "elmos-project-package-manifest\0diff",
  "elmos-project-package-manifest\0page",
  "elmos-project-package-preview-and-review-ui\0page",
  "elmos-project-package-version-and-incremental-update\0diff",
  "elmos-project-root-language-framework-detection\0status",
  "elmos-prompt-injection-defense\0evaluate",
  "elmos-provider-routing-and-fallback\0route",
  "elmos-repository-context-map\0status",
  "elmos-repository-map-and-symbol-indexing\0status",
  "elmos-resumable-multi-file-folder-upload\0status",
  "elmos-secure-resumable-upload\0status",
  "elmos-storage-index-and-retrieval\0query",
  "elmos-storage-index-and-retrieval\0rebuild_status",
]);

const operationPermissions = new Map<string, MultimodalIntakePermission>();
for (const [skill, operations] of Object.entries(operationsBySkill)) {
  for (const operation of operations) {
    const key = `${skill}\0${operation}`;
    const permission: MultimodalIntakePermission = skill === "elmos-human-review-and-correction"
      ? "intake:review"
      : key === "elmos-multimodal-input-orchestrator\0bootstrap_project"
        ? "intake:admin"
        : readOnlyOperationPairs.has(key)
          ? "intake:read"
          : "intake:write";
    operationPermissions.set(key, permission);
  }
}

export const multimodalOperationCount = operationPermissions.size;

export function multimodalPermissionForOperation(
  skill: string,
  operation: string,
): MultimodalIntakePermission | undefined {
  return operationPermissions.get(`${skill}\0${operation}`);
}

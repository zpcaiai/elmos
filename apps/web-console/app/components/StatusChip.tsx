const statusLabels: Record<string, string> = {
  READY: "契约就绪",
  ENFORCED: "已强制",
  BLOCKED: "已阻断",
  NOT_RUN: "未运行",
  NOT_CERTIFIED: "未认证",
  NOT_CONFIGURED: "未配置",
  CONFIGURATION_REQUIRED: "待配置",
  EXPERIMENTAL: "实验性",
  LIMITED: "受限支持",
  RECOMMENDED: "推荐",
  OPTIONAL: "可选",
  CONDITIONAL: "条件选择",
  REVIEW: "待审阅",
  DRAFT: "草稿",
  SUPPORTED: "已支持",
  CERTIFIED: "已认证",
  PASSED: "已通过",
  FAILED: "已失败",
  LIVE_API: "实时 API",
  REPOSITORY_CONTRACT: "仓库契约",
  CONTRACT_READY: "契约就绪",
  INSTALLED: "已安装",
  ADAPTER_DECLARED: "适配器已声明",
};

export function StatusChip({ status, compact = false }: { status: string; compact?: boolean }) {
  const normalized = status.toUpperCase();
  return <span className={`status-chip status-${normalized.toLowerCase().replaceAll("_", "-")} ${compact ? "status-compact" : ""}`}><i />{statusLabels[normalized] ?? status}</span>;
}

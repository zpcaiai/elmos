const statusLabels: Record<string, string> = {
  READY: "契约就绪",
  ENFORCED: "已强制",
  BLOCKED: "已阻断",
  NOT_RUN: "未运行",
  NOT_CERTIFIED: "未认证",
  NOT_CONFIGURED: "未配置",
  EXPERIMENTAL: "实验性",
  REVIEW: "待审阅",
  DRAFT: "草稿",
  LIVE_API: "实时 API",
  REPOSITORY_CONTRACT: "仓库契约",
};

export function StatusChip({ status, compact = false }: { status: string; compact?: boolean }) {
  const normalized = status.toUpperCase();
  return <span className={`status-chip status-${normalized.toLowerCase().replaceAll("_", "-")} ${compact ? "status-compact" : ""}`}><i />{statusLabels[normalized] ?? status}</span>;
}

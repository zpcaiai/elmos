// Top-level helpers and constants
try { function isStoredDraft(value) {
    if (!value || typeof value !== "object")
        return false;
    const draft = value;
    return typeof draft.id === "string"
        && typeof draft.name === "string"
        && typeof draft.source === "string"
        && typeof draft.target === "string"
        && typeof draft.scope === "string"
        && (draft.capabilityId === null || typeof draft.capabilityId === "string")
        && typeof draft.createdAt === "string";
} } catch(e) {}
try { const extensions = [
    { name: "ChinaDB Commercial Migration", publisher: "ELMOS First-party", type: "SQL 转换增强", description: "13 个国产目标身份已登记；仅在显式兼容模式下进行有限 SQL 发射，不代表厂商原生适配，实库执行与认证保持 NOT_RUN。", version: "1.0.0", compatibility: "Batch 31 · COMPATIBILITY_MODE", status: "EXPERIMENTAL", icon: "database" },
    { name: "Language Adapter SDK", publisher: "ELMOS First-party", type: "语言适配器", description: "对接解析器、PSP、类型语义和发射器，并保留未知语义。", version: "0.1.0", compatibility: "Platform 0.1", status: "EXPERIMENTAL", icon: "code" },
    { name: "Evidence Collector SDK", publisher: "ELMOS First-party", type: "证据采集器", description: "采集原生证据并与归一化记录分离，保留首个失败。", version: "0.1.0", compatibility: "Platform 0.1", status: "REVIEW", icon: "file" },
    { name: "Runner Job SDK", publisher: "ELMOS First-party", type: "Runner 扩展", description: "声明最小能力、网络和文件权限；默认拒绝宿主访问。", version: "0.1.0", compatibility: "Platform 0.1", status: "DRAFT", icon: "server" },
    { name: "Policy Extension SDK", publisher: "ELMOS First-party", type: "策略扩展", description: "扩展类型化策略判断，不能绕过核心授权或自行批准。", version: "0.1.0", compatibility: "Platform 0.1", status: "DRAFT", icon: "shield" },
]; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    items: {
      type: null,
      value: null,
    },
    query: {
      type: null,
      value: null,
    },
    setQuery: {
      type: null,
      value: null,
    },
  },
  data: {
  },
  lifetimes: {
    attached() {
    },
    detached() {
    },
  },
  methods: {
  },
});

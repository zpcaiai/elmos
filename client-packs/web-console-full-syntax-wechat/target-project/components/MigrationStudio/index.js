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
  },
  data: {
    view: "routes",
    query: "",
    statusFilter: "ALL",
    selected: "M36",
    capabilities: "fallbackCapabilities",
    source: "REPOSITORY_CONTRACT",
    note: "正在读取能力契约…",
    dialogOpen: false,
    drafts: [],
    draftsReady: false,
    draftCapability: null,
    feedback: "",
    dialogReturnFocus: {"current":null},
    dialogPanel: {"current":null},
    draftNameInput: {"current":null},
    visibleCapabilities: null,
  },
  lifetimes: {
    attached() {
      const setView = (val) => { this.setData({ view: typeof val === "function" ? val(this.data.view) : val }); };
      const setQuery = (val) => { this.setData({ query: typeof val === "function" ? val(this.data.query) : val }); };
      const setStatusFilter = (val) => { this.setData({ statusFilter: typeof val === "function" ? val(this.data.statusFilter) : val }); };
      const setSelected = (val) => { this.setData({ selected: typeof val === "function" ? val(this.data.selected) : val }); };
      const setCapabilities = (val) => { this.setData({ capabilities: typeof val === "function" ? val(this.data.capabilities) : val }); };
      const setSource = (val) => { this.setData({ source: typeof val === "function" ? val(this.data.source) : val }); };
      const setNote = (val) => { this.setData({ note: typeof val === "function" ? val(this.data.note) : val }); };
      const setDialogOpen = (val) => { this.setData({ dialogOpen: typeof val === "function" ? val(this.data.dialogOpen) : val }); };
      const setDrafts = (val) => { this.setData({ drafts: typeof val === "function" ? val(this.data.drafts) : val }); };
      const setDraftsReady = (val) => { this.setData({ draftsReady: typeof val === "function" ? val(this.data.draftsReady) : val }); };
      const setDraftCapability = (val) => { this.setData({ draftCapability: typeof val === "function" ? val(this.data.draftCapability) : val }); };
      const setFeedback = (val) => { this.setData({ feedback: typeof val === "function" ? val(this.data.feedback) : val }); };
      const dialogReturnFocus = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const dialogPanel = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const draftNameInput = { current: { focus: () => {}, scrollIntoView: () => {} } };
      // Lifecycle effect effect_0
      (async () => {
        try {
          fetch("/api/capabilities/migration")
        .then((response) => response.ok ? response.json() : Promise.reject())
        .then((payload) => {
        setCapabilities(payload.capabilities);
        setSource(payload.source);
        setNote(payload.note ?? "能力契约已载入。");
    })
        .catch(() => setNote("能力 API 不可用；继续显示仓库契约，外部执行保持 NOT_RUN。"));
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          try {
        const stored = JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]");
        if (Array.isArray(stored))
            setDrafts(stored.filter(isStoredDraft).slice(0, 50));
    }
    catch {
        try {
            window.localStorage.removeItem(DRAFT_STORAGE_KEY);
        }
        catch { /* Storage may be disabled by policy. */ }
        setFeedback("本地草稿存储不可用；迁移能力目录仍可浏览，但刷新后不会恢复草稿。");
    }
    finally {
        setDraftsReady(true);
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_2
      (async () => {
        try {
          if (!draftsReady)
        return;
    try {
        window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts));
    }
    catch {
        setFeedback("浏览器未允许保存本地草稿；请勿依赖当前草稿跨刷新恢复。");
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_3
      (async () => {
        try {
          if (!dialogOpen)
        return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => draftNameInput.current?.focus());
    function handleEscape(event) {
        if (event.key === "Escape")
            closeDialog();
        if (event.key !== "Tab")
            return;
        const focusable = Array.from(dialogPanel.current?.querySelectorAll("button, input, select, [href], [tabindex]:not([tabindex='-1'])") ?? []).filter((element) => !element.hasAttribute("disabled"));
        if (focusable.length === 0)
            return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        }
        else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }
    window.addEventListener("keydown", handleEscape);
    return () => {
        document.body.style.overflow = previousOverflow;
        window.removeEventListener("keydown", handleEscape);
    };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_4
      (async () => {
        try {
          if (!feedback)
        return;
    const timer = window.setTimeout(() => setFeedback(""), 4200);
    return () => window.clearTimeout(timer);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    openDialog(capabilityId) {
      const dialogReturnFocus = this.data.dialogReturnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const dialogPanel = this.data.dialogPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const draftNameInput = this.data.draftNameInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        dialogReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDraftCapability(capabilityId ?? null);
    setDialogOpen(true);
      } catch (err) {
        console.warn("openDialog execution warning:", err);
      }
    },
    closeDialog() {
      const dialogReturnFocus = this.data.dialogReturnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const dialogPanel = this.data.dialogPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const draftNameInput = this.data.draftNameInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setDialogOpen(false);
    requestAnimationFrame(() => dialogReturnFocus.current?.focus());
      } catch (err) {
        console.warn("closeDialog execution warning:", err);
      }
    },
    clearFilters() {
      const dialogReturnFocus = this.data.dialogReturnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const dialogPanel = this.data.dialogPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const draftNameInput = this.data.draftNameInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setQuery("");
    setStatusFilter("ALL");
      } catch (err) {
        console.warn("clearFilters execution warning:", err);
      }
    },
    createDraft(event) {
      const dialogReturnFocus = this.data.dialogReturnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const dialogPanel = this.data.dialogPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const draftNameInput = this.data.draftNameInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim() || "未命名评估";
    setDrafts((current) => [{
            id: crypto.randomUUID(),
            name,
            source: String(form.get("source") ?? "Unknown"),
            target: String(form.get("target") ?? "Unknown"),
            scope: String(form.get("scope") ?? "单仓评估"),
            capabilityId: draftCapability,
            createdAt: new Date().toISOString(),
        }, ...current]);
    setFeedback(`“${name}”已持久保存到此浏览器，不会触发外部执行。`);
    closeDialog();
    event.currentTarget.reset();
      } catch (err) {
        console.warn("createDraft execution warning:", err);
      }
    },
    removeDraft(id) {
      const dialogReturnFocus = this.data.dialogReturnFocus || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const dialogPanel = this.data.dialogPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const draftNameInput = this.data.draftNameInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const removed = drafts.find((draft) => draft.id === id);
    setDrafts((current) => current.filter((draft) => draft.id !== id));
    if (removed)
        setFeedback(`“${removed.name}”已从此浏览器删除。`);
      } catch (err) {
        console.warn("removeDraft execution warning:", err);
      }
    },
  },
});

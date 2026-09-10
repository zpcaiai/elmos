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
    dialogReturnFocus: null,
    dialogPanel: null,
    draftNameInput: null,
  },
  lifetimes: {
    attached() {
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
      })();
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
      })();
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
      })();
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
      })();
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
      })();
    },
    detached() {
    },
  },
  methods: {
    openDialog(capabilityId) {
      try {
        dialogReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDraftCapability(capabilityId ?? null);
    setDialogOpen(true);
      } catch (err) {
        console.warn("openDialog execution warning:", err);
      }
    },
    closeDialog() {
      try {
        setDialogOpen(false);
    requestAnimationFrame(() => dialogReturnFocus.current?.focus());
      } catch (err) {
        console.warn("closeDialog execution warning:", err);
      }
    },
    clearFilters() {
      try {
        setQuery("");
    setStatusFilter("ALL");
      } catch (err) {
        console.warn("clearFilters execution warning:", err);
      }
    },
    createDraft(event) {
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

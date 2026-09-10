Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    children: {
      type: null,
      value: null,
    },
  },
  data: {
    mobileOpen: false,
    commandOpen: false,
    commandQuery: "",
    commandActive: 0,
    showBackToTop: false,
    telemetryEnabled: true,
    profileOpen: false,
    commandPanel: null,
    commandInput: null,
    returnFocus: null,
    visibleCommands: [],
  },
  lifetimes: {
    attached() {
      const setMobileOpen = (val) => { this.setData({ mobileOpen: typeof val === "function" ? val(this.data.mobileOpen) : val }); };
      const setCommandOpen = (val) => { this.setData({ commandOpen: typeof val === "function" ? val(this.data.commandOpen) : val }); };
      const setCommandQuery = (val) => { this.setData({ commandQuery: typeof val === "function" ? val(this.data.commandQuery) : val }); };
      const setCommandActive = (val) => { this.setData({ commandActive: typeof val === "function" ? val(this.data.commandActive) : val }); };
      const setShowBackToTop = (val) => { this.setData({ showBackToTop: typeof val === "function" ? val(this.data.showBackToTop) : val }); };
      const setTelemetryEnabled = (val) => { this.setData({ telemetryEnabled: typeof val === "function" ? val(this.data.telemetryEnabled) : val }); };
      const setProfileOpen = (val) => { this.setData({ profileOpen: typeof val === "function" ? val(this.data.profileOpen) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          const skipLink = document.querySelector(".skip-link");
    if (skipLink) {
        skipLink.textContent = english ? "Skip to main content" : "跳到主要内容";
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          function handleShortcut(event) {
        if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
            event.preventDefault();
            if (commandOpen)
                closeCommand();
            else
                openCommand();
        }
        if (event.key === "Escape" && commandOpen)
            closeCommand();
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_2
      (async () => {
        try {
          if (!commandOpen)
        return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => commandInput.current?.focus());
    return () => { document.body.style.overflow = previousOverflow; };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_3
      (async () => {
        try {
          function updateBackToTop() {
        setShowBackToTop(window.scrollY > 640);
    }
    updateBackToTop();
    window.addEventListener("scroll", updateBackToTop, { passive: true });
    return () => window.removeEventListener("scroll", updateBackToTop);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_4
      (async () => {
        try {
          try {
        setTelemetryEnabled(localStorage.getItem("elmos:telemetry-enabled:v1") !== "off");
    }
    catch {
        setTelemetryEnabled(true);
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    openCommand(trigger) {
      try {
        returnFocus.current = trigger
        ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setCommandActive(0);
    setCommandOpen(true);
      } catch (err) {
        console.warn("openCommand execution warning:", err);
      }
    },
    closeCommand() {
      try {
        setCommandOpen(false);
    setCommandQuery("");
    setCommandActive(0);
    requestAnimationFrame(() => returnFocus.current?.focus());
      } catch (err) {
        console.warn("closeCommand execution warning:", err);
      }
    },
    handleCommandKey(event) {
      try {
        if (event.key === "ArrowDown") {
        event.preventDefault();
        if (visibleCommands.length === 0)
            return;
        setCommandActive((index) => Math.min(index + 1, visibleCommands.length - 1));
    }
    if (event.key === "ArrowUp") {
        event.preventDefault();
        if (visibleCommands.length === 0)
            return;
        setCommandActive((index) => Math.max(index - 1, 0));
    }
    if (event.key === "Enter" && visibleCommands[commandActive]) {
        event.preventDefault();
        const target = visibleCommands[commandActive].href;
        closeCommand();
        router.push(target);
    }
      } catch (err) {
        console.warn("handleCommandKey execution warning:", err);
      }
    },
    containDialogFocus(event) {
      try {
        if (event.key !== "Tab" || !commandPanel.current)
        return;
    const focusable = Array.from(commandPanel.current.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])")).filter((element) => element.getClientRects().length > 0);
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
      } catch (err) {
        console.warn("containDialogFocus execution warning:", err);
      }
    },
    reloadPage() {
      try {
        if (window.confirm("重新载入会清除本页尚未保存的输入。是否继续？")) {
        window.location.reload();
    }
      } catch (err) {
        console.warn("reloadPage execution warning:", err);
      }
    },
    scrollToTop() {
      try {
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      } catch (err) {
        console.warn("scrollToTop execution warning:", err);
      }
    },
    toggleTelemetry() {
      try {
        const enabled = !telemetryEnabled;
    setTelemetryEnabled(enabled);
    window.dispatchEvent(new CustomEvent("elmos:telemetry-preference", { detail: { enabled } }));
      } catch (err) {
        console.warn("toggleTelemetry execution warning:", err);
      }
    },
    closeSidebar() {
      try {
        setMobileOpen(false);
    setProfileOpen(false);
      } catch (err) {
        console.warn("closeSidebar execution warning:", err);
      }
    },
    toggleTopProfileMenu() {
      try {
        const nextOpen = !profileOpen;
    setProfileOpen(nextOpen);
    if (nextOpen && window.matchMedia("(max-width: 900px)").matches) {
        setMobileOpen(true);
    }
      } catch (err) {
        console.warn("toggleTopProfileMenu execution warning:", err);
      }
    },
    async logout() {
      try {
        await account.logout();
    closeSidebar();
      } catch (err) {
        console.warn("logout execution warning:", err);
      }
    },
  },
});

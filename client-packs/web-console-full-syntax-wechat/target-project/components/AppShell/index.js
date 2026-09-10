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
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      try {
        const skipLink = document.querySelector<HTMLAnchorElement>(".skip-link");
    if (skipLink) {
      skipLink.textContent = english ? "Skip to main content" : "跳到主要内容";
    }
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_2
      try {
        function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        if (commandOpen) closeCommand();
        else openCommand();
      }
      if (event.key === "Escape" && commandOpen) closeCommand();
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_4
      try {
        if (!commandOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => commandInput.current?.focus());
    return () => { document.body.style.overflow = previousOverflow; };
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_6
      try {
        function updateBackToTop() {
      setShowBackToTop(window.scrollY > 640);
    }
    updateBackToTop();
    window.addEventListener("scroll", updateBackToTop, { passive: true });
    return () => window.removeEventListener("scroll", updateBackToTop);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_8
      try {
        try {
      setTelemetryEnabled(localStorage.getItem("elmos:telemetry-enabled:v1") !== "off");
    } catch {
      setTelemetryEnabled(true);
    }
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    handleShortcut(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        if (commandOpen)
            closeCommand();
        else
            openCommand();
    }
    if (event.key === "Escape" && commandOpen)
        closeCommand();
    },
    updateBackToTop() {
      setShowBackToTop(window.scrollY > 640);
    },
    openCommand(trigger) {
      returnFocus.current = trigger
        ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setCommandActive(0);
    setCommandOpen(true);
    },
    closeCommand() {
      setCommandOpen(false);
    setCommandQuery("");
    setCommandActive(0);
    requestAnimationFrame(() => returnFocus.current?.focus());
    },
    handleCommandKey(event) {
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
    },
    containDialogFocus(event) {
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
    },
    reloadPage() {
      if (window.confirm("重新载入会清除本页尚未保存的输入。是否继续？")) {
        window.location.reload();
    }
    },
    scrollToTop() {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    },
    toggleTelemetry() {
      const enabled = !telemetryEnabled;
    setTelemetryEnabled(enabled);
    window.dispatchEvent(new CustomEvent("elmos:telemetry-preference", { detail: { enabled } }));
    },
    closeSidebar() {
      setMobileOpen(false);
    setProfileOpen(false);
    },
    toggleTopProfileMenu() {
      const nextOpen = !profileOpen;
    setProfileOpen(nextOpen);
    if (nextOpen && window.matchMedia("(max-width: 900px)").matches) {
        setMobileOpen(true);
    }
    },
    logout() {
      await account.logout();
    closeSidebar();
    },
  },
});

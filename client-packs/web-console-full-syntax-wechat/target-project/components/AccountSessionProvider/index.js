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
    status: "loading",
    principal: null,
    expiresAt: null,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      (async () => {
        try {
          void refresh();
    const channel = typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel(channelName);
    const update = () => void refresh();
    channel?.addEventListener("message", update);
    window.addEventListener("storage", update);
    return () => {
        channel?.removeEventListener("message", update);
        channel?.close();
        window.removeEventListener("storage", update);
    };
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_1
      (async () => {
        try {
          if (!expiresAt || status !== "authenticated")
        return;
    const expiry = Date.parse(expiresAt);
    const delay = Math.max(15_000, Math.min(5 * 60_000, expiry - Date.now() - 2 * 60_000));
    const timer = window.setTimeout(async () => {
        const response = await fetch("/api/auth/refresh", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
        });
        if (response.ok) {
            await refresh();
        }
        else {
            setPrincipal(null);
            setExpiresAt(null);
            setStatus("anonymous");
        }
    }, delay);
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
  },
});

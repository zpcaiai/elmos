// Top-level helpers and constants
try { var channelName = "elmos-account-session-v1"; } catch(e) {}
try { var readSession = async function readSession() {
    const response = await fetch("/api/auth/session", {
        credentials: "same-origin",
        cache: "no-store",
    });
    const payload = await response.json();
    return payload;
} } catch(e) {}
try { var useAccountSession = function useAccountSession() {
    const value = useContext(AccountSessionContext);
    if (!value)
        throw new Error("AccountSessionProvider is required");
    return value;
} } catch(e) {}

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
    value: null,
  },
  lifetimes: {
    attached() {
      const setStatus = (val) => { this.setData({ status: typeof val === "function" ? val(this.data.status) : val }); };
      const setPrincipal = (val) => { this.setData({ principal: typeof val === "function" ? val(this.data.principal) : val }); };
      const setExpiresAt = (val) => { this.setData({ expiresAt: typeof val === "function" ? val(this.data.expiresAt) : val }); };
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
      })().catch(() => {});
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
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
  },
});

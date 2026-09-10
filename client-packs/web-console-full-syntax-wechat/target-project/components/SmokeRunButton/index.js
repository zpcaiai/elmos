Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    projectRef: {
      type: null,
      value: null,
    },
  },
  data: {
    capability: null,
    pack: null,
    session: null,
    evidence: null,
    entry: "",
    error: null,
    busy: false,
    remaining: 0,
    extendOpen: false,
    extendSeconds: 300,
    extendReason: "",
    extendActor: "",
    expiresAtRef: null,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      (async () => {
        try {
          let cancelled = false;
    (async () => {
        try {
            const [capabilityResponse, packResponse] = await Promise.all([
                fetch("/api/smoke/capability", { cache: "no-store" }),
                fetch(`/api/smoke/pack?projectRef=${encodeURIComponent(projectRef)}`, { cache: "no-store" }),
            ]);
            const nextCapability = await readJson(capabilityResponse);
            const nextPack = await readJson(packResponse);
            if (cancelled)
                return;
            setCapability(nextCapability);
            setPack(nextPack);
            setEntry(nextPack.defaultEntry ?? nextPack.entries.find((item) => item.status === "available")?.entry ?? "");
        }
        catch (loadError) {
            if (!cancelled)
                setError(loadError instanceof Error ? loadError.message : "SMOKE_LOAD_FAILED");
        }
    })();
    return () => { cancelled = true; };
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_1
      (async () => {
        try {
          if (!session || !LIVE_STATES.has(session.state))
        return;
    const timer = window.setInterval(async () => {
        try {
            const next = await readJson(await fetch(`/api/smoke/sessions/${session.sessionId}`, { cache: "no-store" }));
            applySession(next);
        }
        catch {
            /* transient poll failure: the local countdown keeps running */
        }
    }, 3_000);
    return () => window.clearInterval(timer);
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_2
      (async () => {
        try {
          if (!session || !LIVE_STATES.has(session.state))
        return;
    const timer = window.setInterval(() => {
        const expiresAt = expiresAtRef.current;
        setRemaining(expiresAt ? Math.max(0, Math.round(expiresAt * 1_000 - Date.now()) / 1_000) : 0);
    }, 1_000);
    return () => window.clearInterval(timer);
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

// Top-level helpers and constants
try { var clock = function clock(seconds) {
    const safe = Math.max(0, Math.floor(seconds));
    return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
} } catch(e) {}
try { var readJson = async function readJson(response) {
    const payload = (await response.json());
    if (!response.ok || payload.status === "BLOCKED") {
        throw new Error(payload.reason ?? `HTTP_${response.status}`);
    }
    return payload;
} } catch(e) {}

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
    expiresAtRef: {"current":null},
    selectedEntry: null,
  },
  lifetimes: {
    attached() {
      const setCapability = (val) => { this.setData({ capability: typeof val === "function" ? val(this.data.capability) : val }); };
      const setPack = (val) => { this.setData({ pack: typeof val === "function" ? val(this.data.pack) : val }); };
      const setSession = (val) => { this.setData({ session: typeof val === "function" ? val(this.data.session) : val }); };
      const setEvidence = (val) => { this.setData({ evidence: typeof val === "function" ? val(this.data.evidence) : val }); };
      const setEntry = (val) => { this.setData({ entry: typeof val === "function" ? val(this.data.entry) : val }); };
      const setError = (val) => { this.setData({ error: typeof val === "function" ? val(this.data.error) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setRemaining = (val) => { this.setData({ remaining: typeof val === "function" ? val(this.data.remaining) : val }); };
      const setExtendOpen = (val) => { this.setData({ extendOpen: typeof val === "function" ? val(this.data.extendOpen) : val }); };
      const setExtendSeconds = (val) => { this.setData({ extendSeconds: typeof val === "function" ? val(this.data.extendSeconds) : val }); };
      const setExtendReason = (val) => { this.setData({ extendReason: typeof val === "function" ? val(this.data.extendReason) : val }); };
      const setExtendActor = (val) => { this.setData({ extendActor: typeof val === "function" ? val(this.data.extendActor) : val }); };
      const expiresAtRef = { current: { focus: () => {}, scrollIntoView: () => {} } };
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
      })().catch(() => {});
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
      })().catch(() => {});
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
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
  },
});

// Top-level helpers and constants
try { var initialRisk = {
    security: "low",
    dataMigration: "low",
    concurrency: "low",
    publicContract: "low",
    blastRadius: "low",
    longHorizon: false,
}; } catch(e) {}
try { var riskOptions = ["none", "low", "medium", "high", "critical"]; } catch(e) {}
try { var readableReason = function readableReason(reason) {
    return reason.replaceAll("_", " ").replaceAll(":", " · ");
} } catch(e) {}
try { var statusTone = function statusTone(status) {
    if (status === "BLOCKED" || status === "NOT_CONFIGURED")
        return "blocked";
    if (status.startsWith("READY"))
        return "ready";
    return "pending";
} } catch(e) {}
try { var responseJson = async function responseJson(response) {
    const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
    if (mediaType !== "application/json")
        throw new Error("REPOSITORY_RESPONSE_MEDIA_TYPE_INVALID");
    return response.json();
} } catch(e) {}
try { var failureMessage = function failureMessage(value, fallback) {
    if (typeof value !== "object" || value === null || Array.isArray(value))
        return fallback;
    const message = value.message;
    return typeof message === "string" && message.trim() ? message : fallback;
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    catalog: null,
    catalogError: null,
    loading: true,
    mode: "smart",
    selectedModel: null,
    fallbackEnabled: false,
    optimizationProfile: "cost_performance",
    verificationPolicy: "system_required_verifiers",
    risk: {"security":"low","dataMigration":"low","concurrency":"low","publicContract":"low","blastRadius":"low","longHorizon":false},
    result: null,
    preflightError: null,
    submitting: false,
    selectedDescriptor: null,
  },
  lifetimes: {
    attached() {
      const setCatalog = (val) => { this.setData({ catalog: typeof val === "function" ? val(this.data.catalog) : val }); };
      const setCatalogError = (val) => { this.setData({ catalogError: typeof val === "function" ? val(this.data.catalogError) : val }); };
      const setLoading = (val) => { this.setData({ loading: typeof val === "function" ? val(this.data.loading) : val }); };
      const setMode = (val) => { this.setData({ mode: typeof val === "function" ? val(this.data.mode) : val }); };
      const setSelectedModel = (val) => { this.setData({ selectedModel: typeof val === "function" ? val(this.data.selectedModel) : val }); };
      const setFallbackEnabled = (val) => { this.setData({ fallbackEnabled: typeof val === "function" ? val(this.data.fallbackEnabled) : val }); };
      const setOptimizationProfile = (val) => { this.setData({ optimizationProfile: typeof val === "function" ? val(this.data.optimizationProfile) : val }); };
      const setVerificationPolicy = (val) => { this.setData({ verificationPolicy: typeof val === "function" ? val(this.data.verificationPolicy) : val }); };
      const setRisk = (val) => { this.setData({ risk: typeof val === "function" ? val(this.data.risk) : val }); };
      const setResult = (val) => { this.setData({ result: typeof val === "function" ? val(this.data.result) : val }); };
      const setPreflightError = (val) => { this.setData({ preflightError: typeof val === "function" ? val(this.data.preflightError) : val }); };
      const setSubmitting = (val) => { this.setData({ submitting: typeof val === "function" ? val(this.data.submitting) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          const controller = new AbortController();
    async function loadCatalog() {
        setLoading(true);
        setCatalogError(null);
        try {
            const response = await fetch("/api/repository-orchestrator/models", {
                method: "GET",
                headers: { Accept: "application/json" },
                cache: "no-store",
                signal: controller.signal,
            });
            const raw = await responseJson(response);
            if (!response.ok)
                throw new Error(failureMessage(raw, "模型目录当前不可用。"));
            const parsed = parseRepositoryModelCatalog(raw);
            setCatalog(parsed);
            setMode(parsed.defaultMode);
            setOptimizationProfile(parsed.optimizationProfiles[0]);
            setVerificationPolicy(parsed.verificationPolicies[0]);
        }
        catch (error) {
            if (controller.signal.aborted)
                return;
            setCatalogError(error instanceof Error ? error.message : "模型目录当前不可用。");
        }
        finally {
            if (!controller.signal.aborted)
                setLoading(false);
        }
    }
    void loadCatalog();
    return () => controller.abort();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    updateRisk(field, value) {
      try {
        setRisk((current) => ({ ...current, [field]: value }));
    setResult(null);
      } catch (err) {
        console.warn("updateRisk execution warning:", err);
      }
    },
    async submitPreflight() {
      try {
        if (!catalog || !canPreflight)
        return;
    const request = {
        schemaVersion: "1.0",
        catalogVersion: catalog.catalogVersion,
        selectionVersion: catalog.selectionVersion,
        mode,
        selectedModel: mode === "manual" ? selectedModel : null,
        optimizationProfile,
        fallbackPolicy: mode === "manual"
            ? fallbackEnabled ? "smart_within_allowlist" : "strict"
            : null,
        verificationPolicy,
        risk,
    };
    setSubmitting(true);
    setPreflightError(null);
    setResult(null);
    try {
        const response = await fetch("/api/repository-orchestrator/preflight", {
            method: "POST",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify(request),
            cache: "no-store",
        });
        const raw = await responseJson(response);
        if (!response.ok && response.status !== 400) {
            throw new Error(failureMessage(raw, "仓库编排预检当前不可用。"));
        }
        setResult(parseRepositoryPreflightResult(raw));
    }
    catch (error) {
        setPreflightError(error instanceof Error ? error.message : "仓库编排预检当前不可用。");
    }
    finally {
        setSubmitting(false);
    }
      } catch (err) {
        console.warn("submitPreflight execution warning:", err);
      }
    },
  },
});

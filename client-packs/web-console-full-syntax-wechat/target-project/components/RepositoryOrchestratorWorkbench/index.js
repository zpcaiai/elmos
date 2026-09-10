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
    risk: "initialRisk",
    result: null,
    preflightError: null,
    submitting: false,
  },
  lifetimes: {
    attached() {
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
      })();
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

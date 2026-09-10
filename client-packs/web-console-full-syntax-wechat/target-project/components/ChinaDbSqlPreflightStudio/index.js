Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    capabilities: null,
    fields: "initialFields",
    parameters: [],
    result: null,
    loadingCapabilities: true,
    busy: false,
    error: "",
    errorSummary: null,
    resultPanel: null,
    activeAssessment: null,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      (async () => {
        try {
          const controller = new AbortController();
    async function loadCapabilities() {
        try {
            const response = await fetch("/api/capabilities/database-sql", {
                cache: "no-store",
                signal: controller.signal,
            });
            const payload = await responseJson(response);
            if (!response.ok)
                throw apiError(payload, "CHINADB_SQL_CAPABILITIES_UNAVAILABLE");
            const parsed = parseChinaDbSqlCapabilities(payload);
            setCapabilities(parsed);
            setFields((current) => ({
                ...current,
                targetId: parsed.targets.some((target) => target.id === current.targetId)
                    ? current.targetId
                    : parsed.targets[0].id,
            }));
        }
        catch (loadError) {
            if (controller.signal.aborted)
                return;
            setError(errorMessage(loadError));
            requestAnimationFrame(() => errorSummary.current?.focus());
        }
        finally {
            if (!controller.signal.aborted)
                setLoadingCapabilities(false);
        }
    }
    void loadCapabilities();
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
    updateField(key, value) {
      try {
        if (key === "targetId" && typeof value === "string" && targetPresets[value]) {
        setFields((current) => ({
            ...current,
            targetId: value,
            ...targetPresets[value],
        }));
    }
    else {
        setFields((current) => ({ ...current, [key]: value }));
    }
    setResult(null);
      } catch (err) {
        console.warn("updateField execution warning:", err);
      }
    },
    addParameter() {
      try {
        if (parameters.length >= chinaDbSqlParameterLimit)
        return;
    setParameters((current) => [...current, { name: "", logicalType: "", nullable: false }]);
    setResult(null);
      } catch (err) {
        console.warn("addParameter execution warning:", err);
      }
    },
    updateParameter(index, patch) {
      try {
        setParameters((current) => current.map((parameter, parameterIndex) => (parameterIndex === index ? { ...parameter, ...patch } : parameter)));
    setResult(null);
      } catch (err) {
        console.warn("updateParameter execution warning:", err);
      }
    },
    removeParameter(index) {
      try {
        setParameters((current) => current.filter((_, parameterIndex) => parameterIndex !== index));
    setResult(null);
      } catch (err) {
        console.warn("removeParameter execution warning:", err);
      }
    },
    async submit(event) {
      try {
        event.preventDefault();
    if (!capabilities || busy)
        return;
    setBusy(true);
    setError("");
    setResult(null);
    const controller = new AbortController();
    activeAssessment.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
    }, 17_000);
    try {
        const request = parseChinaDbSqlPreflightRequest({
            schemaVersion: "1.0",
            ...fields,
            capabilitySnapshotDigest: capabilities.capabilitySnapshotDigest,
            parameters,
        });
        bindChinaDbSqlRequestToCapabilities(request, capabilities);
        const response = await fetch("/api/database-sql/preflight", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request),
            cache: "no-store",
            signal: controller.signal,
        });
        const payload = await responseJson(response);
        if (!response.ok)
            throw apiError(payload, "CHINADB_SQL_PREFLIGHT_REJECTED");
        const sourceDigest = await sha256Text(request.sql);
        const parsed = parseChinaDbSqlPreflightResult(payload, request, capabilities, sourceDigest);
        setResult(parsed);
        requestAnimationFrame(() => resultPanel.current?.focus());
    }
    catch (submitError) {
        setError(timedOut ? "预检请求超时，请稍后重试。" : errorMessage(submitError));
        requestAnimationFrame(() => errorSummary.current?.focus());
    }
    finally {
        window.clearTimeout(timeout);
        if (activeAssessment.current === controller)
            activeAssessment.current = null;
        setBusy(false);
    }
      } catch (err) {
        console.warn("submit execution warning:", err);
      }
    },
    cancelAssessment() {
      try {
        activeAssessment.current?.abort();
      } catch (err) {
        console.warn("cancelAssessment execution warning:", err);
      }
    },
  },
});

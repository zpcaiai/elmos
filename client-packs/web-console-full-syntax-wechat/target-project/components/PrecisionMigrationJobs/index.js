Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    skill: "pm-b02-repository-modernization-assessment",
    mode: "assess",
    workspacePath: "",
    runnerToken: "",
    tenantId: "local-tenant",
    actorId: "local-operator",
    job: null,
    busy: false,
    error: "",
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      (async () => {
        try {
          if (!job || terminal.has(job.status))
        return;
    const timer = window.setInterval(() => void load(job.job_id).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "JOB_STATUS_FAILED");
    }), 1_500);
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
    async submit() {
      try {
        setBusy(true);
    setError("");
    try {
        const response = await fetch("/api/precision-migration/jobs", {
            method: "POST",
            headers: { "content-type": "application/json", ...localAuthHeaders() },
            body: JSON.stringify({
                request_id: crypto.randomUUID(),
                skill: skill.trim(),
                mode,
                inputs: {
                    assets: [],
                    parameters: workspacePath.trim() ? { workspace_path: workspacePath.trim() } : {},
                },
                policy: {
                    unresolved_differences: "block",
                    allow_test_weakening: false,
                    require_provenance: true,
                    risk_level: "medium",
                },
                evidence: [],
                semantic_losses: [],
                approvals: [],
            }),
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.reason ?? "JOB_SUBMIT_FAILED");
        setJob(payload);
    }
    catch (reason) {
        setError(reason instanceof Error ? reason.message : "JOB_SUBMIT_FAILED");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("submit execution warning:", err);
      }
    },
    async action(kind) {
      try {
        if (!job)
        return;
    setBusy(true);
    setError("");
    try {
        const response = await fetch(`/api/precision-migration/jobs/${encodeURIComponent(job.job_id)}`, {
            method: kind === "cancel" ? "DELETE" : "POST",
            headers: { ...(kind === "retry" ? { "content-type": "application/json" } : {}), ...localAuthHeaders() },
            body: kind === "retry" ? JSON.stringify({ action: "retry" }) : undefined,
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.reason ?? `JOB_${kind.toUpperCase()}_FAILED`);
        setJob(payload);
    }
    catch (reason) {
        setError(reason instanceof Error ? reason.message : `JOB_${kind.toUpperCase()}_FAILED`);
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("action execution warning:", err);
      }
    },
    async download(artifact) {
      try {
        if (!job)
        return;
    const name = artifactName(artifact);
    if (!name)
        return;
    setError("");
    try {
        const response = await fetch(`/api/precision-migration/jobs/${encodeURIComponent(job.job_id)}/artifacts/${encodeURIComponent(name)}`, {
            headers: localAuthHeaders(),
        });
        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.reason ?? "ARTIFACT_DOWNLOAD_FAILED");
        }
        const url = URL.createObjectURL(await response.blob());
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = name;
        anchor.click();
        URL.revokeObjectURL(url);
    }
    catch (reason) {
        setError(reason instanceof Error ? reason.message : "ARTIFACT_DOWNLOAD_FAILED");
    }
      } catch (err) {
        console.warn("download execution warning:", err);
      }
    },
  },
});

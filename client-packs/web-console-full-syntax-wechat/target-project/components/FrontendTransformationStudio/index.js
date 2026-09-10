Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    batch: "ALL",
    query: "",
    source: "Vue 3",
    target: "React",
    selectedSkillId: "FRT-1305",
    workspaceId: "workspace-frt-console",
    projectId: "project-frt-console",
    environmentId: "development",
    releaseId: "local-review",
    policyVersion: "frt-policy-1.0.0",
    risk: "R4",
    tenantId: "",
    actorId: "",
    runnerToken: "",
    sourceFiles: {},
    inputJson: "{}",
    run: null,
    audit: [],
    operationError: "",
    busy: false,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      try {
        setInputJson(initialContractInput(selectedSkill));
    setOperationError("");
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_1
      try {
        if (!run || !["QUEUED", "RUNNING"].includes(run.state)) return;
    const timer = window.setInterval(() => void refreshRun(run.runId), 1_500);
    return () => window.clearInterval(timer);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    requestHeaders(json) {
      return {
        ...(json ? { "content-type": "application/json" } : {}),
        ...(tenantId && actorId && runnerToken ? {
            authorization: `Bearer ${runnerToken}`,
            "x-elmos-tenant": tenantId,
            "x-elmos-actor": actorId,
        } : {}),
    };
    },
    scopedRunUrl(path) {
      const query = new URLSearchParams({ workspaceId, projectId, environmentId, releaseId });
    return `${path}?${query.toString()}`;
    },
    sourceDigest(input) {
      const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalInput(input)));
    return `sha256:${Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, "0")).join("")}`;
    },
    chooseRepositoryFiles(files) {
      if (!files)
        return;
    setOperationError("");
    const selected = [...files];
    if (!selected.length || selected.length > 512 || selected.some(file => file.size > 1_000_000)) {
        setOperationError("请选择 1–512 个文本文件，单文件不得超过 1 MB。");
        return;
    }
    const loaded = {};
    for (const file of selected)
        loaded[file.webkitRelativePath || file.name] = await file.text();
    setSourceFiles(loaded);
    },
    refreshRun(runId) {
      if (!runId)
        return;
    // A transient disconnect on one read surface must not discard the other
    // successful response or leave the mutation controls permanently busy.
    // The polling loop will retry either resource independently.
    const options = {
        headers: requestHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(8_000),
    };
    const [runResult, auditResult] = await Promise.allSettled([
        fetch(scopedRunUrl(`/api/frt/runs/${runId}`), options),
        fetch(scopedRunUrl(`/api/frt/runs/${runId}/audit`), options),
    ]);
    if (runResult.status === "fulfilled" && runResult.value.ok) {
        setRun(await runResult.value.json());
    }
    if (auditResult.status === "fulfilled" && auditResult.value.ok) {
        setAudit((await auditResult.value.json()).audit);
    }
    },
    startRun(action) {
      if (!selectedSkill)
        return;
    setBusy(true);
    setOperationError("");
    try {
        if (action === "VERIFY" && (!run || run.skillId !== selectedSkill.id
            || ["QUEUED", "RUNNING"].includes(run.state))) {
            throw new Error("VERIFY 需要当前功能在同一资源作用域内已有终态 Run。");
        }
        let parsedInput;
        try {
            parsedInput = JSON.parse(inputJson);
        }
        catch {
            throw new Error("功能输入必须是有效 JSON。");
        }
        if (!parsedInput || typeof parsedInput !== "object" || Array.isArray(parsedInput)) {
            throw new Error("功能输入必须是 JSON object。");
        }
        const typedInput = { ...parsedInput };
        if (acceptsFiles && Object.keys(sourceFiles).length)
            typedInput.files = sourceFiles;
        const allowed = new Set([
            ...selectedSkill.executionContract.inputContract.required,
            ...selectedSkill.executionContract.inputContract.optional,
        ]);
        const unknown = Object.keys(typedInput).filter(key => !allowed.has(key));
        if (unknown.length)
            throw new Error(`未声明的输入字段：${unknown.join(", ")}`);
        if (["ANALYZE", "EXECUTE"].includes(action)) {
            const missing = selectedSkill.executionContract.inputContract.required
                .filter(key => !Object.hasOwn(typedInput, key));
            if (missing.length)
                throw new Error(`缺少必需输入：${missing.join(", ")}`);
        }
        const submittedInput = action === "VERIFY" ? {} : typedInput;
        const response = await fetch("/api/frt/runs", {
            method: "POST",
            headers: requestHeaders(true),
            body: JSON.stringify({
                skillId: selectedSkill.id,
                action,
                idempotencyKey: `console-${crypto.randomUUID()}`,
                workspaceId,
                projectId,
                environmentId,
                releaseId,
                sourceSnapshotDigest: action === "VERIFY" ? run.sourceSnapshotDigest : await sourceDigest(submittedInput),
                policyVersion,
                risk,
                ...(action === "VERIFY" ? {
                    verificationSubject: { runId: run.runId, resultDigest: run.resultDigest },
                } : {}),
                ...(action === "VERIFY" || Object.keys(submittedInput).length === 0 ? {} : { input: submittedInput }),
            }),
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.reason ?? payload.errorCode ?? "FRT_RUN_REJECTED");
        setRun(payload);
        setAudit(Array.isArray(payload.audit) ? payload.audit : []);
        void refreshRun(payload.runId);
    }
    catch (error) {
        setOperationError(error instanceof Error ? error.message : "FRT_RUN_REJECTED");
    }
    finally {
        setBusy(false);
    }
    },
    transition(operation) {
      if (!run)
        return;
    setBusy(true);
    setOperationError("");
    try {
        const response = await fetch(scopedRunUrl(`/api/frt/runs/${run.runId}/${operation}`), {
            method: "POST",
            headers: requestHeaders(true),
            body: JSON.stringify({ expectedVersion: run.version }),
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.reason ?? payload.errorCode ?? "FRT_TRANSITION_REJECTED");
        setRun(payload);
        if (Array.isArray(payload.audit))
            setAudit(payload.audit);
        void refreshRun(payload.runId);
    }
    catch (error) {
        setOperationError(error instanceof Error ? error.message : "FRT_TRANSITION_REJECTED");
    }
    finally {
        setBusy(false);
    }
    },
    downloadArtifacts() {
      if (!run)
        return;
    triggerBrowserDownload(new Blob([JSON.stringify(run.artifacts, null, 2)], { type: "application/json" }), `${run.runId}-artifacts.json`);
    },
    chooseSource(value) {
      setSource(value);
    if (value === target) {
        setTarget(frtCatalog.technologyStacks.find((candidate) => candidate !== value) ?? "React");
    }
    },
    chooseTarget(value) {
      setTarget(value);
    if (value === source) {
        setSource(frtCatalog.technologyStacks.find((candidate) => candidate !== value) ?? "Vue 3");
    }
    },
    openRouteSkill() {
      if (!selectedRoute)
        return;
    setBatch(selectedRoute.batch);
    setQuery(selectedRoute.skillId);
    setSelectedSkillId(selectedRoute.skillId);
    document.getElementById("frt-skill-catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  },
});

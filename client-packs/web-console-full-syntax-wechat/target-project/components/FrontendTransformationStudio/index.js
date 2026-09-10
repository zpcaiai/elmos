// Top-level helpers and constants
try { var deliveryStages = [
    { range: "G01–G04", title: "发现与类型化", detail: "仓库、框架、依赖、UI Interaction IR 与六类源适配器" },
    { range: "G05–G12", title: "规划与生成内核", detail: "差距决策、目标架构、生成、组件、状态、边界与平台能力" },
    { range: "G13–G17", title: "30 条有向路线", detail: "Vue 2、Vue 3、React、小程序、ArkUI 与 Flutter 两两转换" },
    { range: "G18–G20", title: "组合、证明与产品化", detail: "Pack 组合、Proof Obligation、Runtime、API、CLI 与 Console" },
    { range: "G21–G26", title: "产品与体验闭环", detail: "需求、业务、数据、管理端、可用性、无障碍与回归资格" },
    { range: "G27–G30", title: "生产就绪外部门禁", detail: "性能、韧性、安全与 SRE；需要授权的真实环境证据" },
]; } catch(e) {}
try { var lower = function lower(value) {
    return value.toLocaleLowerCase("zh-CN");
} } catch(e) {}
try { var contractExamples = {
    invariants: [{ id: "tenant-scope", satisfied: true }],
    inventory: { workspaceKind: "monorepo", packages: [], routes: [], components: [] },
    target: { stack: "React", version: "19.2.7", language: "TypeScript" },
    targetProfile: { stack: "React", version: "19.2.7" },
    uiIr: { title: "Application", modules: ["app"] },
    astNodes: [{ id: "app", name: "App", kind: "component" }],
    components: [{ id: "app", props: [], events: [], slots: [], hooks: [] }],
    states: [{ id: "draft" }, { id: "ready" }],
    transitions: [{ id: "publish", from: "draft", to: "ready", sideEffect: false }],
    routes: [{ id: "home", path: "/" }],
    uiNodes: [{ id: "page-title", interactive: false }],
    requiredCapabilities: ["storage"],
    platformCapabilities: { web: ["storage"] },
    corpus: [{ id: "case-1", sourceDigest: `sha256:${"1".repeat(64)}`, expectedIrDigest: `sha256:${"2".repeat(64)}` }],
    packs: [{ id: "core", priority: 100, provides: ["ui"], requires: [] }],
    properties: [{ id: "state-valid", expression: "state != null", kind: "invariant", assumptions: [] }],
    resources: [{ id: "skill-registry", type: "registry", tenantBound: true, version: "1.0.0" }],
    requirements: [{ id: "REQ-1" }],
    capabilities: [{ id: "runs.read" }],
    roles: [{ id: "operator", permissions: ["runs.read"] }],
    operations: [{ id: "list-runs", roleId: "operator", permission: "runs.read", auditEvent: "runs.listed" }],
    workload: { concurrency: 10, durationSeconds: 60 },
    budgets: { p95LatencyMs: 500, maximumErrorRate: 0.01 },
    scenarios: [{ id: "dependency-loss", rollback: "restore service", blastRadius: "isolated-test-tenant" }],
    recoveryObjectives: { maximumRtoSeconds: 300, maximumRpoSeconds: 60 },
    assets: [{ id: "frontend-api", classification: "confidential" }],
    findings: [],
    slos: [{ serviceId: "frontend", target: 0.999 }],
    runbooks: [{ id: "frontend-errors", serviceId: "frontend" }],
}; } catch(e) {}
try { var initialContractInput = function initialContractInput(skill) {
    if (!skill)
        return "{}";
    const entries = skill.executionContract.inputContract.required
        .filter(key => key !== "files")
        .map(key => [key, contractExamples[key] ?? {}]);
    return JSON.stringify(Object.fromEntries(entries), null, 2);
} } catch(e) {}
try { var canonicalInput = function canonicalInput(value) {
    if (Array.isArray(value))
        return `[${value.map(canonicalInput).join(",")}]`;
    if (value && typeof value === "object") {
        return `{${Object.entries(value)
            .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
            .map(([key, item]) => `${JSON.stringify(key)}:${canonicalInput(item)}`)
            .join(",")}}`;
    }
    return JSON.stringify(value);
} } catch(e) {}

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
    filteredSkills: [],
  },
  lifetimes: {
    attached() {
      const setBatch = (val) => { this.setData({ batch: typeof val === "function" ? val(this.data.batch) : val }); };
      const setQuery = (val) => { this.setData({ query: typeof val === "function" ? val(this.data.query) : val }); };
      const setSource = (val) => { this.setData({ source: typeof val === "function" ? val(this.data.source) : val }); };
      const setTarget = (val) => { this.setData({ target: typeof val === "function" ? val(this.data.target) : val }); };
      const setSelectedSkillId = (val) => { this.setData({ selectedSkillId: typeof val === "function" ? val(this.data.selectedSkillId) : val }); };
      const setWorkspaceId = (val) => { this.setData({ workspaceId: typeof val === "function" ? val(this.data.workspaceId) : val }); };
      const setProjectId = (val) => { this.setData({ projectId: typeof val === "function" ? val(this.data.projectId) : val }); };
      const setEnvironmentId = (val) => { this.setData({ environmentId: typeof val === "function" ? val(this.data.environmentId) : val }); };
      const setReleaseId = (val) => { this.setData({ releaseId: typeof val === "function" ? val(this.data.releaseId) : val }); };
      const setPolicyVersion = (val) => { this.setData({ policyVersion: typeof val === "function" ? val(this.data.policyVersion) : val }); };
      const setRisk = (val) => { this.setData({ risk: typeof val === "function" ? val(this.data.risk) : val }); };
      const setTenantId = (val) => { this.setData({ tenantId: typeof val === "function" ? val(this.data.tenantId) : val }); };
      const setActorId = (val) => { this.setData({ actorId: typeof val === "function" ? val(this.data.actorId) : val }); };
      const setRunnerToken = (val) => { this.setData({ runnerToken: typeof val === "function" ? val(this.data.runnerToken) : val }); };
      const setSourceFiles = (val) => { this.setData({ sourceFiles: typeof val === "function" ? val(this.data.sourceFiles) : val }); };
      const setInputJson = (val) => { this.setData({ inputJson: typeof val === "function" ? val(this.data.inputJson) : val }); };
      const setRun = (val) => { this.setData({ run: typeof val === "function" ? val(this.data.run) : val }); };
      const setAudit = (val) => { this.setData({ audit: typeof val === "function" ? val(this.data.audit) : val }); };
      const setOperationError = (val) => { this.setData({ operationError: typeof val === "function" ? val(this.data.operationError) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          setInputJson(initialContractInput(selectedSkill));
    setOperationError("");
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          if (!run || !["QUEUED", "RUNNING"].includes(run.state))
        return;
    const timer = window.setInterval(() => void refreshRun(run.runId), 1_500);
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
    requestHeaders(json) {
      try {
        return {
        ...(json ? { "content-type": "application/json" } : {}),
        ...(tenantId && actorId && runnerToken ? {
            authorization: `Bearer ${runnerToken}`,
            "x-elmos-tenant": tenantId,
            "x-elmos-actor": actorId,
        } : {}),
    };
      } catch (err) {
        console.warn("requestHeaders execution warning:", err);
      }
    },
    scopedRunUrl(path) {
      try {
        const query = new URLSearchParams({ workspaceId, projectId, environmentId, releaseId });
    return `${path}?${query.toString()}`;
      } catch (err) {
        console.warn("scopedRunUrl execution warning:", err);
      }
    },
    async sourceDigest(input) {
      try {
        const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalInput(input)));
    return `sha256:${Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, "0")).join("")}`;
      } catch (err) {
        console.warn("sourceDigest execution warning:", err);
      }
    },
    async chooseRepositoryFiles(files) {
      try {
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
      } catch (err) {
        console.warn("chooseRepositoryFiles execution warning:", err);
      }
    },
    async refreshRun(runId) {
      try {
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
      } catch (err) {
        console.warn("refreshRun execution warning:", err);
      }
    },
    async startRun(action) {
      try {
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
      } catch (err) {
        console.warn("startRun execution warning:", err);
      }
    },
    async transition(operation) {
      try {
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
      } catch (err) {
        console.warn("transition execution warning:", err);
      }
    },
    downloadArtifacts() {
      try {
        if (!run)
        return;
    triggerBrowserDownload(new Blob([JSON.stringify(run.artifacts, null, 2)], { type: "application/json" }), `${run.runId}-artifacts.json`);
      } catch (err) {
        console.warn("downloadArtifacts execution warning:", err);
      }
    },
    chooseSource(value) {
      try {
        setSource(value);
    if (value === target) {
        setTarget(frtCatalog.technologyStacks.find((candidate) => candidate !== value) ?? "React");
    }
      } catch (err) {
        console.warn("chooseSource execution warning:", err);
      }
    },
    chooseTarget(value) {
      try {
        setTarget(value);
    if (value === source) {
        setSource(frtCatalog.technologyStacks.find((candidate) => candidate !== value) ?? "Vue 3");
    }
      } catch (err) {
        console.warn("chooseTarget execution warning:", err);
      }
    },
    openRouteSkill() {
      try {
        if (!selectedRoute)
        return;
    setBatch(selectedRoute.batch);
    setQuery(selectedRoute.skillId);
    setSelectedSkillId(selectedRoute.skillId);
    document.getElementById("frt-skill-catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) {
        console.warn("openRouteSkill execution warning:", err);
      }
    },
  },
});

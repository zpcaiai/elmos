// Top-level helpers and constants
try { var plannedAssets = [
    { icon: "workflow", title: "需求与资产图", detail: "PSIR、Blueprint 与来源追踪" },
    { icon: "code", title: "CRUD 与健康检查", detail: "多实体接口与 OpenAPI" },
    { icon: "test", title: "测试与构建", detail: "单元测试、CI 与 Makefile" },
    { icon: "box", title: "容器配置", detail: "非 root Dockerfile" },
    { icon: "cloud", title: "运行清单", detail: "Kubernetes 探针与资源" },
    { icon: "file", title: "证据与归档", detail: "逐目标结果与可交付 ZIP" },
]; } catch(e) {}
try { var generationTargetIds = new Set(generationTargets.map((target) => target.id)); } catch(e) {}
try { var repositoryWorkspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i; } catch(e) {}
try { var browserArtifactTicket = function browserArtifactTicket(value) {
    if (!value || typeof value !== "object")
        throw new Error("ARTIFACT_TICKET_INVALID");
    const ticket = value;
    if (typeof ticket.downloadUrl !== "string"
        || ticket.downloadUrl.length === 0
        || ticket.downloadUrl.length > 4096
        || typeof ticket.filename !== "string"
        || ticket.filename.length === 0
        || ticket.filename.length > 180
        || typeof ticket.contentSha256 !== "string"
        || !/^[0-9a-f]{64}$/.test(ticket.contentSha256)
        || !Number.isSafeInteger(ticket.byteSize)
        || (ticket.byteSize ?? 0) <= 0
        || (ticket.byteSize ?? 0) > MAX_BROWSER_ARTIFACT_BYTES
        || !Number.isSafeInteger(ticket.expiresInSeconds)
        || (ticket.expiresInSeconds ?? 0) <= 0
        || (ticket.expiresInSeconds ?? 0) > 600) {
        throw new Error("ARTIFACT_TICKET_INVALID");
    }
    let url;
    try {
        url = new URL(ticket.downloadUrl);
    }
    catch {
        throw new Error("ARTIFACT_TICKET_INVALID");
    }
    const localDevelopment = url.protocol === "http:"
        && ["127.0.0.1", "localhost"].includes(url.hostname)
        && ["127.0.0.1", "localhost"].includes(window.location.hostname);
    if ((url.protocol !== "https:" && !localDevelopment)
        || url.username
        || url.password
        || url.hash) {
        throw new Error("ARTIFACT_TICKET_URL_NOT_ALLOWED");
    }
    return ticket;
} } catch(e) {}
try { var readBoundedArtifact = async function readBoundedArtifact(response, expectedBytes) {
    if (!Number.isSafeInteger(expectedBytes)
        || expectedBytes <= 0
        || expectedBytes > MAX_BROWSER_ARTIFACT_BYTES) {
        throw new Error("ARTIFACT_LENGTH_INVALID");
    }
    const declared = response.headers.get("content-length");
    if (declared !== null && Number(declared) !== expectedBytes) {
        await response.body?.cancel().catch(() => undefined);
        throw new Error("ARTIFACT_LENGTH_MISMATCH");
    }
    if (!response.body)
        throw new Error("ARTIFACT_BODY_MISSING");
    const data = new Uint8Array(expectedBytes);
    const reader = response.body.getReader();
    let offset = 0;
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done)
                break;
            if (offset + value.byteLength > expectedBytes) {
                await reader.cancel().catch(() => undefined);
                throw new Error("ARTIFACT_LENGTH_MISMATCH");
            }
            data.set(value, offset);
            offset += value.byteLength;
        }
    }
    finally {
        reader.releaseLock();
    }
    if (offset !== expectedBytes)
        throw new Error("ARTIFACT_LENGTH_MISMATCH");
    return data.buffer;
} } catch(e) {}
try { var isStoredSourceReference = function isStoredSourceReference(value) {
    if (!value || typeof value !== "object")
        return false;
    const source = value;
    return typeof source.id === "string"
        && /^SRC-\d{3}$/.test(source.id)
        && typeof source.label === "string"
        && source.label.length <= 180
        && typeof source.sha256 === "string"
        && /^[a-f0-9]{64}$/.test(source.sha256)
        && typeof source.byteCount === "number"
        && typeof source.extractedCharacters === "number"
        && typeof source.includedCharacters === "number"
        && typeof source.truncated === "boolean"
        && Array.isArray(source.warnings);
} } catch(e) {}
try { var isStoredGenerationDraft = function isStoredGenerationDraft(value) {
    if (!value || typeof value !== "object")
        return false;
    const draft = value;
    return typeof draft.id === "string" && draft.id.length <= 100
        && typeof draft.createdAt === "string" && !Number.isNaN(Date.parse(draft.createdAt))
        && typeof draft.name === "string" && draft.name.length <= 64
        && typeof draft.namespace === "string" && draft.namespace.length <= 200
        && typeof draft.description === "string" && draft.description.length <= 32_000
        && typeof draft.entity === "string" && draft.entity.length <= 64
        && typeof draft.reviewer === "string" && draft.reviewer.length <= 200
        && ["in-memory", "postgresql"].includes(draft.persistence ?? "in-memory")
        && ["none", "jwt", "oidc"].includes(draft.authMode ?? "none")
        && Array.isArray(draft.targets) && draft.targets.length > 0
        && draft.targets.every((target) => typeof target === "string" && generationTargetIds.has(target))
        && (draft.sources === undefined
            || (Array.isArray(draft.sources)
                && draft.sources.length > 0
                && draft.sources.every(isStoredSourceReference)
                && typeof draft.sourceBundleSha256 === "string"
                && /^[a-f0-9]{64}$/.test(draft.sourceBundleSha256)));
} } catch(e) {}
try { var shellQuote = function shellQuote(value) {
    return `'${value.replaceAll("'", "'\\''")}'`;
} } catch(e) {}
try { var runnerReasonMessage = function runnerReasonMessage(reason) {
    if (!reason)
        return "";
    if (reason.includes("ROOTLESS_CONTAINER_ENGINE_REQUIRED")) {
        return "当前容器引擎不是 rootless；生产一键本地部署运行保持关闭，请配置 rootless Podman/Docker。";
    }
    if (reason.includes("TOOLCHAIN_IMAGES_NOT_AVAILABLE_OFFLINE")) {
        return "精确工具链镜像尚未缓存，且构建网络为 none；请预加载 digest 镜像或审批受限构建网络。";
    }
    if (reason.includes("BUILD_NETWORK_NOT_APPROVED") || reason.includes("APPROVED_BUILD_NETWORK_MISSING")) {
        return "构建网络缺少 ELMOS 审批标签；运行器已拒绝未授权的网络出口。";
    }
    if (reason.includes("LOCAL_RUNNER_NOT_ENABLED")) {
        return "本地 Runner 未启用；仍可审阅并导出 Intent，执行入口保持关闭。";
    }
    return reason;
} } catch(e) {}
try { var buildWorkflowCommands = function buildWorkflowCommands(draft) {
    const workspace = `generated/${draft.name}`;
    return [
        {
            id: "analyze",
            label: "1 · 分析 Intent",
            command: "uv run elmos-project-synthesis analyze --intent project-intent.json --output synthesis-request.json",
        },
        {
            id: "approve",
            label: "2 · 审阅并批准",
            command: `uv run elmos-project-synthesis approve --request synthesis-request.json --actor ${shellQuote(draft.reviewer)} --output approved-request.json`,
        },
        {
            id: "generate",
            label: "3 · 生成工作区",
            command: `uv run elmos-project-synthesis generate --request approved-request.json --output ${shellQuote(workspace)}`,
        },
        {
            id: "verify",
            label: "4 · 真实构建验证",
            command: `uv run elmos-project-synthesis verify --workspace ${shellQuote(workspace)} --evidence verification.json`,
        },
        {
            id: "runtime",
            label: "5 · 生成运行计划",
            command: `uv run elmos-project-synthesis runtime-plan --workspace ${shellQuote(workspace)}`,
        },
    ];
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    name: "order-service",
    namespace: "io.elmos.orders",
    description: "提供订单创建、查询与状态管理的服务",
    entity: "order",
    reviewer: "user:reviewer",
    targets: ["java","python"],
    persistence: "in-memory",
    authMode: "none",
    sourceUrl: "",
    sourceSkills: "",
    repositoryWorkspaceId: "",
    repositoryPaths: "",
    sourceFiles: [],
    sourceBundle: null,
    sourceBusy: false,
    draft: null,
    savedDrafts: [],
    draftsReady: false,
    capability: null,
    capabilityError: "",
    runnerReadiness: null,
    tenantId: "local-dev",
    runnerToken: "",
    analysis: null,
    approved: false,
    job: null,
    recoveryJobId: "",
    runnerBusy: false,
    runtimeLanguage: "java",
    runtimePreviewPayload: null,
    githubOwner: "",
    githubRepositoryName: "order-service",
    githubToken: "",
    githubConfirmed: false,
    githubBusy: false,
    githubIdempotencyKey: "() => crypto.randomUUID()",
    feedback: "",
    targetError: "",
    feedbackTimer: {"current":null},
    sourceFileInput: {"current":null},
    jobRequestEpoch: {"current":null},
    artifactGroups: null,
    runtimeRemainingSeconds: null,
    selectedProfiles: null,
  },
  lifetimes: {
    attached() {
      const setName = (val) => { this.setData({ name: typeof val === "function" ? val(this.data.name) : val }); };
      const setNamespace = (val) => { this.setData({ namespace: typeof val === "function" ? val(this.data.namespace) : val }); };
      const setDescription = (val) => { this.setData({ description: typeof val === "function" ? val(this.data.description) : val }); };
      const setEntity = (val) => { this.setData({ entity: typeof val === "function" ? val(this.data.entity) : val }); };
      const setReviewer = (val) => { this.setData({ reviewer: typeof val === "function" ? val(this.data.reviewer) : val }); };
      const setTargets = (val) => { this.setData({ targets: typeof val === "function" ? val(this.data.targets) : val }); };
      const setPersistence = (val) => { this.setData({ persistence: typeof val === "function" ? val(this.data.persistence) : val }); };
      const setAuthMode = (val) => { this.setData({ authMode: typeof val === "function" ? val(this.data.authMode) : val }); };
      const setSourceUrl = (val) => { this.setData({ sourceUrl: typeof val === "function" ? val(this.data.sourceUrl) : val }); };
      const setSourceSkills = (val) => { this.setData({ sourceSkills: typeof val === "function" ? val(this.data.sourceSkills) : val }); };
      const setRepositoryWorkspaceId = (val) => { this.setData({ repositoryWorkspaceId: typeof val === "function" ? val(this.data.repositoryWorkspaceId) : val }); };
      const setRepositoryPaths = (val) => { this.setData({ repositoryPaths: typeof val === "function" ? val(this.data.repositoryPaths) : val }); };
      const setSourceFiles = (val) => { this.setData({ sourceFiles: typeof val === "function" ? val(this.data.sourceFiles) : val }); };
      const setSourceBundle = (val) => { this.setData({ sourceBundle: typeof val === "function" ? val(this.data.sourceBundle) : val }); };
      const setSourceBusy = (val) => { this.setData({ sourceBusy: typeof val === "function" ? val(this.data.sourceBusy) : val }); };
      const setDraft = (val) => { this.setData({ draft: typeof val === "function" ? val(this.data.draft) : val }); };
      const setSavedDrafts = (val) => { this.setData({ savedDrafts: typeof val === "function" ? val(this.data.savedDrafts) : val }); };
      const setDraftsReady = (val) => { this.setData({ draftsReady: typeof val === "function" ? val(this.data.draftsReady) : val }); };
      const setCapability = (val) => { this.setData({ capability: typeof val === "function" ? val(this.data.capability) : val }); };
      const setCapabilityError = (val) => { this.setData({ capabilityError: typeof val === "function" ? val(this.data.capabilityError) : val }); };
      const setRunnerReadiness = (val) => { this.setData({ runnerReadiness: typeof val === "function" ? val(this.data.runnerReadiness) : val }); };
      const setTenantId = (val) => { this.setData({ tenantId: typeof val === "function" ? val(this.data.tenantId) : val }); };
      const setRunnerToken = (val) => { this.setData({ runnerToken: typeof val === "function" ? val(this.data.runnerToken) : val }); };
      const setAnalysis = (val) => { this.setData({ analysis: typeof val === "function" ? val(this.data.analysis) : val }); };
      const setApproved = (val) => { this.setData({ approved: typeof val === "function" ? val(this.data.approved) : val }); };
      const setJob = (val) => { this.setData({ job: typeof val === "function" ? val(this.data.job) : val }); };
      const setRecoveryJobId = (val) => { this.setData({ recoveryJobId: typeof val === "function" ? val(this.data.recoveryJobId) : val }); };
      const setRunnerBusy = (val) => { this.setData({ runnerBusy: typeof val === "function" ? val(this.data.runnerBusy) : val }); };
      const setRuntimeLanguage = (val) => { this.setData({ runtimeLanguage: typeof val === "function" ? val(this.data.runtimeLanguage) : val }); };
      const setRuntimePreviewPayload = (val) => { this.setData({ runtimePreviewPayload: typeof val === "function" ? val(this.data.runtimePreviewPayload) : val }); };
      const setGithubOwner = (val) => { this.setData({ githubOwner: typeof val === "function" ? val(this.data.githubOwner) : val }); };
      const setGithubRepositoryName = (val) => { this.setData({ githubRepositoryName: typeof val === "function" ? val(this.data.githubRepositoryName) : val }); };
      const setGithubToken = (val) => { this.setData({ githubToken: typeof val === "function" ? val(this.data.githubToken) : val }); };
      const setGithubConfirmed = (val) => { this.setData({ githubConfirmed: typeof val === "function" ? val(this.data.githubConfirmed) : val }); };
      const setGithubBusy = (val) => { this.setData({ githubBusy: typeof val === "function" ? val(this.data.githubBusy) : val }); };
      const setGithubIdempotencyKey = (val) => { this.setData({ githubIdempotencyKey: typeof val === "function" ? val(this.data.githubIdempotencyKey) : val }); };
      const setFeedback = (val) => { this.setData({ feedback: typeof val === "function" ? val(this.data.feedback) : val }); };
      const setTargetError = (val) => { this.setData({ targetError: typeof val === "function" ? val(this.data.targetError) : val }); };
      const feedbackTimer = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = { current: { focus: () => {}, scrollIntoView: () => {} } };
      // Lifecycle effect effect_0
      (async () => {
        try {
          if (!accountRunner || !account.principal)
        return;
    setTenantId(account.principal.organizationId);
    setReviewer(account.principal.actorId);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          const controller = new AbortController();
    fetch("/api/capabilities/generation", { cache: "no-store", signal: controller.signal })
        .then((response) => response.ok ? response.json() : Promise.reject(new Error("capability unavailable")))
        .then((payload) => {
        setCapability(payload);
        setCapabilityError("");
    })
        .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
            setCapability(null);
            setCapabilityError("无法读取项目生成能力契约；执行入口保持关闭，请检查 Web Console 服务端日志。");
        }
    });
    return () => controller.abort();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_2
      (async () => {
        try {
          const fromRepository = new URLSearchParams(window.location.search)
        .get("repositoryWorkspaceId")?.trim() ?? "";
    if (repositoryWorkspaceIdPattern.test(fromRepository)) {
        setRepositoryWorkspaceId(fromRepository);
        setDescription("");
        setFeedback("已接收代码仓库工作区；输入同一身份绑定的 Runner 令牌后即可导入快照。");
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_3
      (async () => {
        try {
          const controller = new AbortController();
    fetch("/api/health?probe=readiness", { cache: "no-store", signal: controller.signal })
        .then(async (response) => {
        const payload = await response.json();
        if (!payload.localRunner)
            throw new Error("runner readiness unavailable");
        return payload.localRunner;
    })
        .then(setRunnerReadiness)
        .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
            setRunnerReadiness({
                status: "BLOCKED",
                isolation: "NOT_CONFIGURED",
                storage: "BLOCKED",
                reason: "LOCAL_RUNNER_READINESS_UNAVAILABLE",
            });
        }
    });
    return () => controller.abort();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_4
      (async () => {
        try {
          try {
        const stored = JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]");
        if (Array.isArray(stored)) {
            setSavedDrafts(stored
                .filter(isStoredGenerationDraft)
                .map((item) => ({
                ...item,
                persistence: item.persistence ?? "in-memory",
                authMode: item.authMode ?? "none",
            }))
                .slice(0, 50));
        }
    }
    catch {
        try {
            window.localStorage.removeItem(DRAFT_STORAGE_KEY);
        }
        catch { /* Storage may be disabled by policy. */ }
        setFeedback("本地草稿存储不可用；当前页面仍可准备一次性交接，但刷新后不会恢复。");
    }
    finally {
        setDraftsReady(true);
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_5
      (async () => {
        try {
          if (!draftsReady)
        return;
    try {
        window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(savedDrafts));
    }
    catch {
        announce("浏览器未允许保存本地草稿；请在离开页面前复制已锁定的交接命令。");
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_6
      (async () => {
        try {
          if (feedbackTimer.current !== null)
    window.clearTimeout(feedbackTimer.current);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_7
      (async () => {
        try {
          if (!job?.artifactSha256)
        return;
    setGithubRepositoryName(draft?.name ?? name);
    setGithubToken("");
    setGithubConfirmed(false);
    setGithubIdempotencyKey(crypto.randomUUID());
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_8
      (async () => {
        try {
          if (!job || !runnerCredentialReady)
        return;
    const active = !["COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED"].includes(job.status)
        || ["STARTING", "RUNNING"].includes(job.runtime.status);
    if (!active)
        return;
    let cancelled = false;
    let timer;
    const controller = new AbortController();
    const poll = async () => {
        const requestEpoch = jobRequestEpoch.current;
        try {
            const next = await runnerRequest(`/api/generation/jobs/${job.id}`, { signal: controller.signal });
            if (!cancelled && jobRequestEpoch.current === requestEpoch)
                setJob(next);
        }
        catch {
            // Polling is best-effort; the next serialized attempt reconciles state.
        }
        finally {
            if (!cancelled)
                timer = window.setTimeout(() => void poll(), 1_200);
        }
    };
    timer = window.setTimeout(() => void poll(), 1_200);
    return () => {
        cancelled = true;
        controller.abort();
        if (timer !== undefined)
            window.clearTimeout(timer);
    };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_9
      (async () => {
        try {
          if (job?.runtime.status !== "RUNNING")
    setRuntimePreviewPayload(null);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    announce(message) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (feedbackTimer.current !== null)
        window.clearTimeout(feedbackTimer.current);
    setFeedback(message);
    feedbackTimer.current = window.setTimeout(() => {
        setFeedback("");
        feedbackTimer.current = null;
    }, 4800);
      } catch (err) {
        console.warn("announce execution warning:", err);
      }
    },
    invalidateDraft() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setDraft(null);
    setAnalysis(null);
    setApproved(false);
      } catch (err) {
        console.warn("invalidateDraft execution warning:", err);
      }
    },
    updateDescription(value) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setDescription(value);
    if (sourceBundle && value !== sourceBundle.combinedText) {
        setSourceBundle(null);
    }
    invalidateDraft();
      } catch (err) {
        console.warn("updateDescription execution warning:", err);
      }
    },
    async ingestSources() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!runnerCredentialReady) {
        announce("解析文件、能力模块或在线 HTML 前，请先登录具备生成权限的账户或输入本地短期令牌。");
        return;
    }
    if (!description.trim()
        && sourceFiles.length === 0
        && !sourceUrl.trim()
        && !sourceSkills.trim()
        && !repositoryWorkspaceId.trim()) {
        announce("请至少填写简述、选择文件、填写在线 HTML 地址、仓库工作区或指定能力模块。");
        return;
    }
    if (repositoryWorkspaceId.trim()
        && !repositoryWorkspaceIdPattern.test(repositoryWorkspaceId.trim())) {
        announce("仓库工作区 ID 必须是有效 UUID。");
        return;
    }
    const form = new FormData();
    if (description.trim())
        form.set("description", description.trim());
    if (sourceUrl.trim())
        form.set("url", sourceUrl.trim());
    if (sourceSkills.trim())
        form.set("skills", sourceSkills.trim());
    if (repositoryWorkspaceId.trim()) {
        form.set("repositoryWorkspaceId", repositoryWorkspaceId.trim());
        if (repositoryPaths.trim())
            form.set("repositoryPaths", repositoryPaths.trim());
    }
    sourceFiles.forEach((file) => form.append("files", file, file.name));
    setSourceBusy(true);
    try {
        const response = await fetch("/api/generation/sources", {
            method: "POST",
            cache: "no-store",
            headers: accountRunner ? undefined : {
                "Authorization": `Bearer ${runnerToken}`,
                "X-ELMOS-Tenant": tenantId.trim(),
                "X-ELMOS-Actor": reviewer.trim(),
            },
            body: form,
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.reason ?? `HTTP_${response.status}`);
        setSourceBundle(payload);
        setDescription(payload.combinedText);
        invalidateDraft();
        announce(`已提取并绑定 ${payload.sources.length} 个来源；请审阅合并后的项目说明再锁定计划。`);
    }
    catch (error) {
        setSourceBundle(null);
        announce(`来源解析被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        setSourceBusy(false);
    }
      } catch (err) {
        console.warn("ingestSources execution warning:", err);
      }
    },
    productionCapable(id) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        // targets with PostgreSQL-backed integration evidence declare profiles.
    return (availableTargets.find((profile) => profile.id === id)?.productionProfiles.length ?? 0) > 0;
      } catch (err) {
        console.warn("productionCapable execution warning:", err);
      }
    },
    toggleTarget(id) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (persistence === "postgresql") {
        if (!productionCapable(id)) {
            setTargetError("该目标尚未产出 PostgreSQL + JWT/OIDC 集成证据，生产配置保持阻断。");
            return;
        }
        // The production profile is generated and verified one target at a
        // time, so selection replaces rather than accumulates.
        setTargets([id]);
        setTargetError("");
        invalidateDraft();
        return;
    }
    setTargets((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    setTargetError("");
    invalidateDraft();
      } catch (err) {
        console.warn("toggleTarget execution warning:", err);
      }
    },
    createDraft(event) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        event.preventDefault();
    if (targets.length === 0) {
        setTargetError("请至少选择一个目标技术栈。");
        return;
    }
    if (persistence === "postgresql"
        && (targets.length !== 1 || !productionCapable(targets[0]) || authMode === "none")) {
        setTargetError("生产配置要求单个已验证目标加 JWT 或 OIDC；其他组合保持阻断。");
        return;
    }
    if (persistence === "in-memory" && authMode !== "none") {
        setTargetError("内存 Starter 只允许 auth=none；请选择 PostgreSQL 生产配置或恢复为无认证 Starter。");
        return;
    }
    const nextDraft = {
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        name: name.trim(),
        namespace: namespace.trim(),
        description: description.trim(),
        entity: entity.trim(),
        reviewer: reviewer.trim(),
        targets,
        persistence,
        authMode,
        ...(sourceBundle ? {
            sources: sourceBundle.sources,
            sourceBundleSha256: sourceBundle.bundleSha256,
        } : {}),
    };
    setDraft(nextDraft);
    setAnalysis(null);
    setApproved(false);
    setSavedDrafts((current) => [nextDraft, ...current].slice(0, 50));
    announce(`“${nextDraft.name}”的五阶段生成交接已保存到此浏览器；仍未执行任何代码生成。`);
      } catch (err) {
        console.warn("createDraft execution warning:", err);
      }
    },
    restoreDraft(saved) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setName(saved.name);
    setNamespace(saved.namespace);
    setDescription(saved.description);
    setEntity(saved.entity);
    setReviewer(saved.reviewer);
    setTargets(saved.targets);
    setPersistence(saved.persistence ?? "in-memory");
    setAuthMode(saved.authMode ?? "none");
    setSourceBundle(saved.sources && saved.sourceBundleSha256 ? {
        status: "READY_FOR_REVIEW",
        schemaVersion: "1.0.0",
        bundleSha256: saved.sourceBundleSha256,
        combinedText: saved.description,
        sources: saved.sources,
        warnings: [...new Set(saved.sources.flatMap((source) => source.warnings))],
        extractedAt: saved.createdAt,
    } : null);
    setSourceFiles([]);
    setSourceUrl("");
    setSourceSkills("");
    setTargetError("");
    setDraft(saved);
    setAnalysis(null);
    setApproved(false);
    announce(`已恢复“${saved.name}”并重新锁定其受控命令。`);
      } catch (err) {
        console.warn("restoreDraft execution warning:", err);
      }
    },
    removeDraft(id) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const removed = savedDrafts.find((item) => item.id === id);
    setSavedDrafts((current) => current.filter((item) => item.id !== id));
    if (draft?.id === id) {
        setDraft(null);
        setAnalysis(null);
        setApproved(false);
    }
    if (removed)
        announce(`“${removed.name}”已从此浏览器删除。`);
      } catch (err) {
        console.warn("removeDraft execution warning:", err);
      }
    },
    async copyText(value, successMessage) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!draft) {
        announce("请先提交并锁定当前计划预览，再复制受控命令。");
        return;
    }
    try {
        await navigator.clipboard.writeText(value);
        announce(successMessage);
    }
    catch {
        announce("浏览器未允许访问剪贴板，请手动选择并复制命令。");
    }
      } catch (err) {
        console.warn("copyText execution warning:", err);
      }
    },
    async runnerRequest(url, init, identityOverride) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const isExistingJobRequest = Boolean(job && url.includes(`/jobs/${job.id}`));
    const actor = identityOverride?.actor
        ?? (isExistingJobRequest ? job.actor : draft?.reviewer ?? reviewer);
    const requestTenantId = identityOverride?.tenantId
        ?? (isExistingJobRequest ? job.tenantId : tenantId);
    const response = await fetch(url, {
        ...init,
        cache: "no-store",
        headers: {
            "Content-Type": "application/json",
            ...(!accountRunner ? {
                "Authorization": `Bearer ${runnerToken}`,
                "X-ELMOS-Tenant": requestTenantId,
                "X-ELMOS-Actor": actor,
            } : {}),
            ...init?.headers,
        },
    });
    const payload = await response.json();
    if (!response.ok)
        throw new Error(payload.reason ?? `HTTP_${response.status}`);
    return payload;
      } catch (err) {
        console.warn("runnerRequest execution warning:", err);
      }
    },
    async recoverJob() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const exactJobId = recoveryJobId.trim().toLowerCase();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(exactJobId)) {
        announce("请输入完整、有效的任务 UUID。");
        return;
    }
    if (!runnerCredentialReady) {
        announce("恢复任务需要企业账户会话或本地短期 Runner 令牌。");
        return;
    }
    setRunnerBusy(true);
    try {
        const next = await runnerRequest(`/api/generation/jobs/${exactJobId}`, undefined, { tenantId: tenantId.trim(), actor: reviewer.trim() });
        setJob(next);
        setRecoveryJobId(next.id);
        setRuntimeLanguage(next.runtime.language ?? next.runtime.plans[0]?.language ?? "java");
        announce(`已按租户与操作者身份恢复任务 ${next.id.slice(0, 8)}；令牌仍只保存在页面内存。`);
    }
    catch (error) {
        announce(`任务恢复被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        setRunnerBusy(false);
    }
      } catch (err) {
        console.warn("recoverJob execution warning:", err);
      }
    },
    async analyzeDraft() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!draft) {
        announce("请先锁定当前项目意图。");
        return;
    }
    if (!runnerCredentialReady) {
        announce("请先登录具备生成权限的账户或输入本地短期 Runner 令牌。");
        return;
    }
    setRunnerBusy(true);
    setApproved(false);
    try {
        const result = await runnerRequest("/api/generation/analyze", {
            method: "POST",
            body: JSON.stringify({
                name: draft.name,
                namespace: draft.namespace,
                description: draft.description,
                entity: draft.entity,
                targets: draft.targets,
                persistence: draft.persistence,
                authMode: draft.authMode,
                ...(draft.sources ? { sources: draft.sources } : {}),
                ...(draft.sourceBundleSha256
                    ? { sourceBundleSha256: draft.sourceBundleSha256 }
                    : {}),
            }),
        });
        setAnalysis(result);
        announce(result.request.open_questions.length > 0
            ? `需求已整理，但仍有 ${result.request.open_questions.length} 个开放问题，暂不能批准执行。`
            : `需求已整理为 ${result.request.entities.length} 个实体、${result.request.requirements.length} 项需求，请审阅后批准。`);
    }
    catch (error) {
        setAnalysis(null);
        announce(`需求分析被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        setRunnerBusy(false);
    }
      } catch (err) {
        console.warn("analyzeDraft execution warning:", err);
      }
    },
    async executeJob() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!draft || !analysis || analysis.request.open_questions.length > 0 || !approved) {
        announce("请先完成需求分析、处理开放问题并批准当前锁定计划。");
        return;
    }
    if (incompatibleProductionTargets.length > 0) {
        announce(`当前生产请求有 ${analysis.request.entities.length} 个实体；`
            + `${incompatibleProductionTargets.map((target) => target.language).join("、")} 的生产 Profile 当前仍只接受单实体。`);
        return;
    }
    if (!runnerCredentialReady) {
        announce("请先登录具备生成权限的账户或输入本地短期 Runner 令牌。");
        return;
    }
    setRunnerBusy(true);
    try {
        const next = await runnerRequest("/api/generation/jobs", {
            method: "POST",
            body: JSON.stringify({
                name: draft.name,
                namespace: draft.namespace,
                description: draft.description,
                entity: draft.entity,
                reviewer: draft.reviewer,
                targets: draft.targets,
                persistence: draft.persistence,
                authMode: draft.authMode,
                approved: true,
                analysisDigest: analysis.requestDigest,
                ...(draft.sources ? { sources: draft.sources } : {}),
                ...(draft.sourceBundleSha256
                    ? { sourceBundleSha256: draft.sourceBundleSha256 }
                    : {}),
            }),
        });
        setJob(next);
        setRuntimeLanguage(draft.targets[0]);
        announce(`受控任务 ${next.id.slice(0, 8)} 已进入执行队列。`);
    }
    catch (error) {
        announce(`执行被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        setRunnerBusy(false);
    }
      } catch (err) {
        console.warn("executeJob execution warning:", err);
      }
    },
    async postJobAction(action) {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!job)
        return;
    if (!runnerCredentialReady) {
        announce("任务操作需要企业账户会话或本地短期 Runner 令牌。");
        return;
    }
    jobRequestEpoch.current += 1;
    setRunnerBusy(true);
    try {
        const next = await runnerRequest(`/api/generation/jobs/${job.id}/${action}`, {
            method: "POST",
            body: action === "run" ? JSON.stringify({ language: runtimeLanguage }) : "{}",
        });
        setJob(next);
        setRuntimePreviewPayload(null);
        announce(action === "cancel"
            ? "任务已请求取消。"
            : action === "run"
                ? "浏览器预览已启动；健康确认后可查看，服务端将在 10 分钟租约到期时强制清理。"
                : "浏览器预览进程已停止。");
    }
    catch (error) {
        announce(`操作被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        jobRequestEpoch.current += 1;
        setRunnerBusy(false);
    }
      } catch (err) {
        console.warn("postJobAction execution warning:", err);
      }
    },
    async downloadArtifact() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!job?.artifactReady || !job.artifactSize || !job.artifactSha256)
        return;
    if (!runnerCredentialReady) {
        announce("归档下载需要企业账户会话或本地短期 Runner 令牌。");
        return;
    }
    try {
        const response = await fetch(`/api/generation/jobs/${job.id}/artifact`, {
            cache: "no-store",
            headers: accountRunner ? undefined : {
                "Authorization": `Bearer ${runnerToken}`,
                "X-ELMOS-Tenant": job.tenantId,
                "X-ELMOS-Actor": job.actor,
            },
        });
        if (!response.ok) {
            const payload = await response.json();
            throw new Error(payload.reason ?? `HTTP_${response.status}`);
        }
        let expectedDigest = response.headers.get("x-content-sha256");
        let artifactBytes;
        if (response.headers.get("content-type")?.startsWith("application/json")) {
            const ticket = browserArtifactTicket(await response.json());
            if (ticket.byteSize !== job.artifactSize
                || ticket.contentSha256 !== job.artifactSha256) {
                throw new Error("ARTIFACT_TICKET_IDENTITY_MISMATCH");
            }
            const objectResponse = await fetch(ticket.downloadUrl, { cache: "no-store" });
            if (!objectResponse.ok)
                throw new Error(`OBJECT_STORAGE_HTTP_${objectResponse.status}`);
            artifactBytes = await readBoundedArtifact(objectResponse, ticket.byteSize);
            expectedDigest = ticket.contentSha256;
        }
        else {
            artifactBytes = await readBoundedArtifact(response, job.artifactSize);
        }
        const actualDigest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", artifactBytes))].map((value) => value.toString(16).padStart(2, "0")).join("");
        if (!expectedDigest
            || expectedDigest !== actualDigest
            || expectedDigest !== job.artifactSha256) {
            throw new Error("ARTIFACT_INTEGRITY_MISMATCH");
        }
        triggerBrowserDownload(new Blob([artifactBytes], { type: "application/zip" }), `${draft?.name ?? "generated-project"}.zip`);
        announce(job.status === "COMPLETED"
            ? "归档摘要已复算并下载；本次目标构建与启动探针均通过。"
            : "归档摘要已复算并下载；其中仍含 PARTIAL / NOT_RUN 证据，请先查看任务结果。");
    }
    catch (error) {
        announce(`归档下载失败：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
      } catch (err) {
        console.warn("downloadArtifact execution warning:", err);
      }
    },
    async openRuntimePreview() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!job || job.runtime.status !== "RUNNING")
        return;
    setRunnerBusy(true);
    try {
        const previewResult = await runnerRequest(`/api/generation/jobs/${job.id}/preview`);
        setRuntimePreviewPayload(previewResult);
        announce(`已在浏览器读取 ${previewResult.service} 的真实运行健康响应。`);
    }
    catch (error) {
        setRuntimePreviewPayload(null);
        announce(`浏览器预览失败：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        setRunnerBusy(false);
    }
      } catch (err) {
        console.warn("openRuntimePreview execution warning:", err);
      }
    },
    async publishGitHub() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!job?.artifactReady || !job.artifactSha256)
        return;
    if (accountRunner && !accountCanPublish) {
        announce("当前企业账户缺少 repository:push 权限；未创建 GitHub 仓库。");
        return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(githubRepositoryName.trim())
        || githubRepositoryName.trim().toLowerCase().endsWith(".git")
        || githubToken.trim().length < 20
        || /\s/.test(githubToken.trim())
        || !githubConfirmed) {
        announce("请填写有效仓库名与短期 GitHub 凭证，并确认仅创建新的私有仓库。");
        return;
    }
    if (!window.confirm(`将在 GitHub 创建私有仓库 ${githubOwner.trim() ? `${githubOwner.trim()}/` : "当前账户/"}${githubRepositoryName.trim()} 并上传完整生成代码。继续？`)) {
        return;
    }
    const token = githubToken.trim();
    const requestBody = JSON.stringify({
        repositoryName: githubRepositoryName.trim(),
        ...(githubOwner.trim() ? { owner: githubOwner.trim() } : {}),
        description: `Generated by ELMOS from ${job.artifactSha256}`,
        token,
        artifactSha256: job.artifactSha256,
        idempotencyKey: githubIdempotencyKey,
        confirmed: true,
    });
    setGithubToken("");
    setGithubConfirmed(false);
    setGithubBusy(true);
    try {
        const next = await runnerRequest(`/api/generation/jobs/${job.id}/github`, {
            method: "POST",
            body: requestBody,
        });
        setJob(next);
        announce(`GitHub 私有仓库 ${next.githubPublication?.repositoryFullName ?? githubRepositoryName} 已按 main 提交回读验证。`);
    }
    catch (error) {
        try {
            setJob(await runnerRequest(`/api/generation/jobs/${job.id}`));
        }
        catch {
            // The original publication error remains the useful user-facing result.
        }
        announce(`GitHub 上传被阻断：${error instanceof Error ? error.message : "UNKNOWN_ERROR"}`);
    }
    finally {
        setGithubBusy(false);
    }
      } catch (err) {
        console.warn("publishGitHub execution warning:", err);
      }
    },
    downloadIntent() {
      const feedbackTimer = this.data.feedbackTimer || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const sourceFileInput = this.data.sourceFileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const jobRequestEpoch = this.data.jobRequestEpoch || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!draft) {
        announce("请先提交并锁定项目意图，再导出结构化 Intent。");
        return;
    }
    const intent = {
        schema_version: "1.1.0",
        name: draft.name,
        namespace: draft.namespace,
        description: draft.description,
        entity: draft.entity,
        languages: draft.targets,
        project_kind: "api",
        persistence: draft.persistence,
        auth_mode: draft.authMode,
        business_rules: [],
        permissions: [],
        ...(draft.sources ? { requirement_sources: draft.sources } : {}),
        ...(draft.sourceBundleSha256
            ? { source_bundle_sha256: draft.sourceBundleSha256 }
            : {}),
        ui_handoff: {
            created_at: draft.createdAt,
            reviewer: draft.reviewer,
            execution_status: "NOT_RUN",
            certification_status: "NOT_CERTIFIED",
        },
    };
    triggerBrowserDownload(new Blob([JSON.stringify(intent, null, 2)], { type: "application/json" }), "project-intent.json");
    announce("project-intent.json 已导出；请在受控终端从 Analyze 阶段开始。");
      } catch (err) {
        console.warn("downloadIntent execution warning:", err);
      }
    },
  },
});

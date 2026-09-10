// Top-level helpers and constants
try { const latestRunStorageKey = "elmos.spring.latest-run-id"; } catch(e) {}
try { function buildStageCards(capability, target) {
    const verifiedRoutes = capability?.routes?.filter((route) => route.evidenceStatus === "PASSED_LOCAL").length ?? (capability ? 1 : 0);
    const source = capability
        ? `${capability.routes?.length ?? 1} 条声明路线；${verifiedRoutes} 个精确点有本地工程证据`
        : "契约未读取的路线目录";
    const targetLabel = target
        ? `Spring Boot ${target.springBoot} / Java ${target.java}`
        : "目标 Spring Boot / Java";
    const rewrite = capability
        ? `固定 Rewrite Spring ${capability.openRewrite.rewriteSpring} 与插件 ${capability.openRewrite.mavenPlugin}。`
        : "固定 OpenRewrite 版本由 Engine 能力契约声明；契约未读取时不展示版本号。";
    return [
        { stages: ["IMPORT_GIT"], title: "导入 Git 仓库", detail: "仅允许批准的 HTTPS Git host，拒绝 URL 凭证。" },
        { stages: ["LOCK_SNAPSHOT"], title: "锁定 Commit / Snapshot", detail: "解析 40 位 Commit，并生成确定性内容摘要。" },
        { stages: ["FINGERPRINT"], title: "精确版本识别", detail: `按 Spring family、精确版本、JDK 与构建工具从 ${source} 中选择，不做模糊匹配。` },
        { stages: ["SOURCE_BASELINE"], title: "源工程基线", detail: "在一次性副本中使用检测到且已配置的精确源 JDK 执行完整构建与测试。" },
        { stages: ["EXTRACT_FCM"], title: "提取 FCM", detail: "在转换前固化能力、来源映射、默认值与未知项。" },
        { stages: ["OPENREWRITE"], title: "OpenRewrite 实际转换", detail: rewrite },
        { stages: ["BUILD_AND_TEST", "DETERMINISTIC_REPAIR"], title: "编译 / 测试 / 修复", detail: `${targetLabel} 真实测试；失败时最多一次确定性修复。` },
        { stages: ["PACKAGE_ARTIFACT"], title: "候选项目打包", detail: "生成内容寻址 ZIP，尚不自动开放下载。" },
        { stages: ["INDEPENDENT_VALIDATION"], title: "独立验证", detail: "另一验证器从 ZIP 新目录解包并执行 mvn verify。" },
        { stages: ["READY"], title: "下载新项目", detail: "只有独立 PASS 后才开放下载。" },
        { stages: ["START_APPLICATION", "HEALTH_CHECK"], title: "一键隔离启动", detail: `${targetLabel} 启动、回环健康检查，未配置 Rootless 时拒绝。` },
        { stages: ["STOP_APPLICATION"], title: "日志 / 停止 / 重试", detail: "实时脱敏日志、优雅停止与新的可追溯尝试。" },
    ];
} } catch(e) {}
try { function routeSourceFamilyLabel(route) {
    if (route.sourceFrameworkFamily === "spring-mvc")
        return "Spring Framework MVC";
    if (route.sourceFrameworkFamily === "spring-framework")
        return "Spring Framework";
    return "Spring Boot";
} } catch(e) {}
try { function routeSourceConstraintLabel(route) {
    if (route.exactSourceVersion)
        return `exact ${route.exactSourceVersion}`;
    if (route.sourceConstraint?.startsWith("exact:")) {
        return `exact ${route.sourceConstraint.slice("exact:".length)}`;
    }
    return route.sourceConstraint
        ?? `[${route.sourceBootMinInclusive}, ${route.sourceBootMaxExclusive})`;
} } catch(e) {}
try { function routeEvidenceLabel(route) {
    const sourceFamily = routeSourceFamilyLabel(route);
    return route.evidenceStatus === "PASSED_LOCAL"
        ? `PASSED_LOCAL @ ${sourceFamily} ${route.verifiedSourceSpringBoot} / Java ${route.verifiedSourceJava}`
        : `${route.evidenceStatus} · ${sourceFamily}`;
} } catch(e) {}
try { function routeLaunchStatus(route) {
    if (route.launchStatus)
        return route.launchStatus;
    return route.evidenceStatus === "NOT_IMPLEMENTED" ? "INVENTORY_ONLY" : "EXPERIMENTAL";
} } catch(e) {}
try { function fingerprintSourceLabel(fingerprint) {
    const version = fingerprint.sourceFrameworkVersion?.trim()
        || fingerprint.springBootVersion.trim()
        || "UNKNOWN";
    return fingerprint.sourceFrameworkFamily === "spring-mvc"
        ? `Spring Framework MVC ${version}`
        : fingerprint.sourceFrameworkFamily === "spring-framework"
            ? `Spring Framework ${version}`
            : `Spring Boot ${version}`;
} } catch(e) {}
try { const orderedStages = [
    "IMPORT_GIT", "LOCK_SNAPSHOT", "FINGERPRINT", "SOURCE_BASELINE", "EXTRACT_FCM",
    "OPENREWRITE", "BUILD_AND_TEST", "DETERMINISTIC_REPAIR", "PACKAGE_ARTIFACT",
    "INDEPENDENT_VALIDATION", "READY", "START_APPLICATION", "HEALTH_CHECK", "STOP_APPLICATION",
]; } catch(e) {}
try { function randomKey(prefix) {
    return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`}`;
} } catch(e) {}
try { function shortDigest(value) {
    return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "等待生成";
} } catch(e) {}
try { function formatBytes(value) {
    if (!value)
        return "等待生成";
    return value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;
} } catch(e) {}
try { async function api(url, init, credentials) {
    const response = await fetch(url, {
        cache: "no-store",
        ...init,
        headers: {
            ...init?.headers,
            ...(credentials ? {
                authorization: `Bearer ${credentials.token}`,
                "x-elmos-tenant": credentials.tenantId,
                "x-elmos-actor": credentials.actorId,
            } : {}),
        },
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(`${error.errorCode ?? `HTTP_${response.status}`}: ${error.message ?? "请求失败"}`);
    }
    return response.json();
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    sourceMode: "PUBLIC_GIT",
    repositoryUrl: "",
    requestedRef: "main",
    expectedCommitSha: "",
    snapshotId: "",
    materializedRelativePath: "",
    repositoryWorkspaceId: "",
    githubRepositories: [],
    githubRepositoryId: "",
    githubCatalogStatus: "NOT_CONFIGURED",
    startAfterVerification: false,
    allowExperimentalRoutes: false,
    capability: null,
    targetSpringBoot: "",
    targetJava: "",
    capabilityError: "",
    run: null,
    logs: null,
    showLogs: false,
    busy: false,
    feedback: "",
    feedbackKind: "success",
    tenantId: "",
    actorId: "",
    proxyToken: "",
    recoveryRunId: "",
    targetOptions: null,
    selectedTarget: null,
    runTarget: null,
    credentials: null,
    stageCards: null,
    currentMessage: null,
    selectableTargetKeys: null,
    displayedTargetOptions: null,
  },
  lifetimes: {
    attached() {
      const setSourceMode = (val) => { this.setData({ sourceMode: typeof val === "function" ? val(this.data.sourceMode) : val }); };
      const setRepositoryUrl = (val) => { this.setData({ repositoryUrl: typeof val === "function" ? val(this.data.repositoryUrl) : val }); };
      const setRequestedRef = (val) => { this.setData({ requestedRef: typeof val === "function" ? val(this.data.requestedRef) : val }); };
      const setExpectedCommitSha = (val) => { this.setData({ expectedCommitSha: typeof val === "function" ? val(this.data.expectedCommitSha) : val }); };
      const setSnapshotId = (val) => { this.setData({ snapshotId: typeof val === "function" ? val(this.data.snapshotId) : val }); };
      const setMaterializedRelativePath = (val) => { this.setData({ materializedRelativePath: typeof val === "function" ? val(this.data.materializedRelativePath) : val }); };
      const setRepositoryWorkspaceId = (val) => { this.setData({ repositoryWorkspaceId: typeof val === "function" ? val(this.data.repositoryWorkspaceId) : val }); };
      const setGithubRepositories = (val) => { this.setData({ githubRepositories: typeof val === "function" ? val(this.data.githubRepositories) : val }); };
      const setGithubRepositoryId = (val) => { this.setData({ githubRepositoryId: typeof val === "function" ? val(this.data.githubRepositoryId) : val }); };
      const setGithubCatalogStatus = (val) => { this.setData({ githubCatalogStatus: typeof val === "function" ? val(this.data.githubCatalogStatus) : val }); };
      const setStartAfterVerification = (val) => { this.setData({ startAfterVerification: typeof val === "function" ? val(this.data.startAfterVerification) : val }); };
      const setAllowExperimentalRoutes = (val) => { this.setData({ allowExperimentalRoutes: typeof val === "function" ? val(this.data.allowExperimentalRoutes) : val }); };
      const setCapability = (val) => { this.setData({ capability: typeof val === "function" ? val(this.data.capability) : val }); };
      const setTargetSpringBoot = (val) => { this.setData({ targetSpringBoot: typeof val === "function" ? val(this.data.targetSpringBoot) : val }); };
      const setTargetJava = (val) => { this.setData({ targetJava: typeof val === "function" ? val(this.data.targetJava) : val }); };
      const setCapabilityError = (val) => { this.setData({ capabilityError: typeof val === "function" ? val(this.data.capabilityError) : val }); };
      const setRun = (val) => { this.setData({ run: typeof val === "function" ? val(this.data.run) : val }); };
      const setLogs = (val) => { this.setData({ logs: typeof val === "function" ? val(this.data.logs) : val }); };
      const setShowLogs = (val) => { this.setData({ showLogs: typeof val === "function" ? val(this.data.showLogs) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setFeedback = (val) => { this.setData({ feedback: typeof val === "function" ? val(this.data.feedback) : val }); };
      const setFeedbackKind = (val) => { this.setData({ feedbackKind: typeof val === "function" ? val(this.data.feedbackKind) : val }); };
      const setTenantId = (val) => { this.setData({ tenantId: typeof val === "function" ? val(this.data.tenantId) : val }); };
      const setActorId = (val) => { this.setData({ actorId: typeof val === "function" ? val(this.data.actorId) : val }); };
      const setProxyToken = (val) => { this.setData({ proxyToken: typeof val === "function" ? val(this.data.proxyToken) : val }); };
      const setRecoveryRunId = (val) => { this.setData({ recoveryRunId: typeof val === "function" ? val(this.data.recoveryRunId) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          if (!accountRunner || !account.principal)
        return;
    setTenantId(account.principal.organizationId);
    setActorId(account.principal.actorId);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          api("/api/spring-upgrades/capabilities")
        .then((value) => {
        setCapability(value);
        setTargetSpringBoot((current) => current || value.targetTuple.springBoot);
        setTargetJava((current) => current || value.targetTuple.java);
        setCapabilityError("");
    })
        .catch((error) => {
        setCapability(null);
        setCapabilityError(error.message);
        notify(error.message, "error");
    });
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_2
      (async () => {
        try {
          refreshGithubCatalog()
        .catch(() => {
        setGithubCatalogStatus("NOT_CONFIGURED");
        setGithubRepositories([]);
    });
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_3
      (async () => {
        try {
          const runId = window.sessionStorage.getItem(latestRunStorageKey);
    if (runId && /^[0-9a-f-]{36}$/i.test(runId))
        setRecoveryRunId(runId);
    const parameters = new URLSearchParams(window.location.search);
    const workspaceId = parameters.get("repositoryWorkspaceId")?.trim().toLowerCase() ?? "";
    const commit = parameters.get("expectedCommitSha")?.trim().toLowerCase() ?? "";
    const ref = parameters.get("requestedRef")?.trim() ?? "";
    if (/^[0-9a-f-]{36}$/.test(workspaceId) && /^[0-9a-f]{40}$/.test(commit)) {
        setRepositoryWorkspaceId(workspaceId);
        setExpectedCommitSha(commit);
        if (ref)
            setRequestedRef(ref);
        setSourceMode("REPOSITORY_WORKSPACE");
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_4
      (async () => {
        try {
          if (!run || !["QUEUED", "RUNNING"].includes(run.status) && run.runtimeStatus !== "STARTING")
        return;
    const timer = window.setInterval(() => {
        refresh(run.runId).catch((error) => notify(error.message, "error"));
    }, 1_500);
    return () => window.clearInterval(timer);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_5
      (async () => {
        try {
          if (!feedback || feedbackKind === "error")
        return;
    const timer = window.setTimeout(() => setFeedback(""), 6_000);
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
    async submit(event) {
      try {
        event.preventDefault();
    if (busy || migrationActive || !selectedTargetSupported)
        return;
    setBusy(true);
    setFeedback("");
    try {
        const next = await api("/api/spring-upgrades", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                sourceMode,
                repositoryUrl: sourceMode === "PUBLIC_GIT" ? repositoryUrl.trim() : null,
                repositoryId: sourceMode === "GITHUB_APP" ? githubRepositoryId : null,
                repositoryWorkspaceId: sourceMode === "REPOSITORY_WORKSPACE"
                    ? repositoryWorkspaceId.trim()
                    : null,
                requestedRef: sourceMode === "MATERIALIZED_SNAPSHOT"
                    ? "snapshot"
                    : requestedRef.trim(),
                expectedCommitSha: sourceMode === "GITHUB_APP"
                    ? null
                    : expectedCommitSha.trim() || null,
                snapshotId: sourceMode === "MATERIALIZED_SNAPSHOT"
                    ? snapshotId.trim()
                    : null,
                materializedRelativePath: sourceMode === "MATERIALIZED_SNAPSHOT" ? materializedRelativePath.trim() : null,
                startAfterVerification,
                allowExperimentalRoutes,
                targetSpringBoot,
                targetJava,
                idempotencyKey: randomKey("spring-upgrade"),
            }),
        }, credentials);
        applyRun(next);
        setLogs(null);
        notify("迁移已排队；页面会持续读取真实阶段和证据状态。");
    }
    catch (error) {
        notify(error instanceof Error ? error.message : "提交失败", "error");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("submit execution warning:", err);
      }
    },
    async connectGithubApp() {
      try {
        setBusy(true);
    setFeedback("");
    try {
        const result = await api("/api/github-installation", {
            method: "POST",
        }, credentials);
        const target = new URL(result.installationUrl);
        if (target.protocol !== "https:" || target.hostname !== "github.com") {
            throw new Error("GITHUB_APP_INSTALL_URL_INVALID: 安装地址未通过安全校验");
        }
        window.location.assign(target.toString());
    }
    catch (error) {
        notify(error.message, "error");
        setBusy(false);
    }
      } catch (err) {
        console.warn("connectGithubApp execution warning:", err);
      }
    },
    async lifecycle(path, body) {
      try {
        if (!run)
        return;
    setBusy(true);
    try {
        const next = await api(`/api/spring-upgrades/${run.runId}/${path}`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body ?? {}),
        }, credentials);
        applyRun(next);
        notify("操作已受理，状态将自动刷新。");
    }
    catch (error) {
        notify(error instanceof Error ? error.message : "操作失败", "error");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("lifecycle execution warning:", err);
      }
    },
    async toggleLogs() {
      try {
        if (!run)
        return;
    const next = !showLogs;
    setShowLogs(next);
    if (next) {
        try {
            setLogs(await api(`/api/spring-upgrades/${run.runId}/logs`, undefined, credentials));
        }
        catch (error) {
            notify(error instanceof Error ? error.message : "日志不可用", "error");
        }
    }
      } catch (err) {
        console.warn("toggleLogs execution warning:", err);
      }
    },
    async downloadArtifact() {
      try {
        if (!run?.downloadAvailable || !run.artifactSha256 || !run.artifactSize)
        return;
    setBusy(true);
    try {
        const response = await fetch(`/api/spring-upgrades/${run.runId}/artifact`, {
            cache: "no-store",
            headers: accountRunner ? undefined : {
                authorization: `Bearer ${proxyToken}`,
                "x-elmos-tenant": tenantId.trim(),
                "x-elmos-actor": actorId.trim(),
            },
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(`${error.errorCode ?? `HTTP_${response.status}`}: ${error.message ?? "归档不可用"}`);
        }
        const responseDigest = response.headers.get("x-content-sha256");
        const declaredLength = Number(response.headers.get("content-length"));
        const blob = await response.blob();
        const actualDigest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))].map((value) => value.toString(16).padStart(2, "0")).join("");
        if (responseDigest !== run.artifactSha256
            || actualDigest !== run.artifactSha256
            || blob.size !== run.artifactSize
            || !Number.isSafeInteger(declaredLength)
            || declaredLength !== blob.size) {
            throw new Error("ARTIFACT_INTEGRITY_MISMATCH: 下载字节与独立验证证据不一致");
        }
        triggerBrowserDownload(blob, artifactFileName);
        notify("ZIP 的长度和 SHA-256 已在浏览器复算并与独立验证证据一致。");
    }
    catch (error) {
        notify(error instanceof Error ? error.message : "归档下载失败", "error");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("downloadArtifact execution warning:", err);
      }
    },
    async recoverRun() {
      try {
        if (!/^[0-9a-f-]{36}$/i.test(recoveryRunId) || !credentialsReady)
        return;
    setBusy(true);
    try {
        await refresh(recoveryRunId.toLowerCase(), false);
        notify("已按 Run UUID 与当前租户身份恢复持久迁移运行。");
    }
    catch (error) {
        notify(error instanceof Error ? error.message : "SPRING_UPGRADE_RUN_NOT_FOUND", "error");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("recoverRun execution warning:", err);
      }
    },
  },
});

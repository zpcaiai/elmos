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
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      try {
        if (!accountRunner || !account.principal) return;
    setTenantId(account.principal.organizationId);
    setActorId(account.principal.actorId);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_1
      try {
        api<Capability>("/api/spring-upgrades/capabilities")
      .then((value) => {
        setCapability(value);
        setTargetSpringBoot((current) => current || value.targetTuple.springBoot);
        setTargetJava((current) => current || value.targetTuple.java);
        setCapabilityError("");
      })
      .catch((error: Error) => {
        setCapability(null);
        setCapabilityError(error.message);
        notify(error.message, "error");
      });
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_2
      try {
        refreshGithubCatalog()
      .catch(() => {
        setGithubCatalogStatus("NOT_CONFIGURED");
        setGithubRepositories([]);
      });
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_3
      try {
        const runId = window.sessionStorage.getItem(latestRunStorageKey);
    if (runId && /^[0-9a-f-]{36}$/i.test(runId)) setRecoveryRunId(runId);
    const parameters = new URLSearchParams(window.location.search);
    const workspaceId = parameters.get("repositoryWorkspaceId")?.trim().toLowerCase() ?? "";
    const commit = parameters.get("expectedCommitSha")?.trim().toLowerCase() ?? "";
    const ref = parameters.get("requestedRef")?.trim() ?? "";
    if (/^[0-9a-f-]{36}$/.test(workspaceId) && /^[0-9a-f]{40}$/.test(commit)) {
      setRepositoryWorkspaceId(workspaceId);
      setExpectedCommitSha(commit);
      if (ref) setRequestedRef(ref);
      setSourceMode("REPOSITORY_WORKSPACE");
    }
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_4
      try {
        if (!run || !["QUEUED", "RUNNING"].includes(run.status) && run.runtimeStatus !== "STARTING") return;
    const timer = window.setInterval(() => {
      refresh(run.runId).catch((error: Error) => notify(error.message, "error"));
    }, 1_500);
    return () => window.clearInterval(timer);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_5
      try {
        if (!feedback || feedbackKind === "error") return;
    const timer = window.setTimeout(() => setFeedback(""), 6_000);
    return () => window.clearTimeout(timer);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    submit(event) {
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
    },
    connectGithubApp() {
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
    },
    lifecycle(path, body) {
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
    },
    toggleLogs() {
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
    },
    downloadArtifact() {
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
    },
    recoverRun() {
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
    },
  },
});

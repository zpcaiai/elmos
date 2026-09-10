Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    sourceLanguage: "java",
    targetLanguage: "python",
    repositoryRef: "local:customer-repository",
    scope: "repository",
    handoff: null,
    repositoryPlan: null,
    discovery: null,
    workUnitFilter: "",
    workUnitPage: 0,
    capability: null,
    capabilityError: "",
    importing: false,
    feedback: "",
    tenantId: "",
    actorId: "",
    runnerToken: "",
    workspaceId: "",
    repositoryWorkspaceId: "",
    casesBundleId: "",
    recoveryJobId: "",
    runnerHealth: null,
    job: null,
    jobBusy: false,
  },
  lifetimes: {
    attached() {
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
      })();
      // Lifecycle effect effect_1
      (async () => {
        try {
          const value = new URLSearchParams(window.location.search)
        .get("repositoryWorkspaceId")?.trim().toLowerCase() ?? "";
    if (/^[0-9a-f-]{36}$/.test(value))
        setRepositoryWorkspaceId(value);
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_2
      (async () => {
        try {
          const controller = new AbortController();
    fetch("/api/capabilities/translation", { cache: "no-store", signal: controller.signal })
        .then(async (response) => {
        const payload = await response.json().catch(() => null);
        if (!response.ok || !payload || !("routes" in payload)) {
            const detail = payload && "errorCode" in payload && payload.errorCode
                ? `${payload.errorCode}：${payload.message ?? ""}`
                : `HTTP_${response.status}`;
            throw new Error(detail);
        }
        setCapability(payload);
        setCapabilityError("");
    })
        .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError")
            return;
        setCapability(null);
        setCapabilityError(`路线能力契约不可读取（${error instanceof Error ? error.message : "UNKNOWN"}）；`
            + "所有路线状态保持 NOT_RUN，页面不会展示未读取到的通过结论。");
    });
    try {
        const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
        if (isStoredHandoff(stored))
            setHandoff(stored);
    }
    catch {
        try {
            window.localStorage.removeItem(STORAGE_KEY);
        }
        catch { /* Storage may be denied. */ }
    }
    return () => controller.abort();
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_3
      (async () => {
        try {
          fetch("/api/translation/health", { cache: "no-store" })
        .then(async (response) => {
        const payload = await response.json();
        setRunnerHealth(payload);
    })
        .catch(() => setRunnerHealth({
        status: "BLOCKED",
        isolation: "NOT_CONFIGURED",
        sourceStorage: "BLOCKED",
        activeJobs: 0,
        reason: "TRANSLATION_RUNNER_HEALTH_UNAVAILABLE",
    }));
    const latest = window.sessionStorage.getItem(JOB_STORAGE_KEY);
    if (latest && /^[0-9a-f-]{36}$/.test(latest))
        setRecoveryJobId(latest);
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_4
      (async () => {
        try {
          if (!job || !["QUEUED", "PRECHECK", "RUNNING"].includes(job.status))
        return;
    const timer = window.setInterval(() => {
        void runnerRequest(`/api/translation/jobs/${job.id}`)
            .then(setJob)
            .catch((error) => setFeedback(`任务刷新失败：${error.message}`));
    }, 1_500);
    return () => window.clearInterval(timer);
        } catch (err) {
          // Handled mount effect
        }
      })();
      // Lifecycle effect effect_5
      (async () => {
        try {
          if (!feedback)
        return;
    const timer = window.setTimeout(() => setFeedback(""), 5_200);
    return () => window.clearTimeout(timer);
        } catch (err) {
          // Handled mount effect
        }
      })();
    },
    detached() {
    },
  },
  methods: {
    resetDerivedState() {
      try {
        setHandoff(null);
    setRepositoryPlan(null);
    setDiscovery(null);
    setWorkUnitFilter("");
    setWorkUnitPage(0);
      } catch (err) {
        console.warn("resetDerivedState execution warning:", err);
      }
    },
    chooseSource(id) {
      try {
        setSourceLanguage(id);
    if (id === targetLanguage) {
        const replacement = languages.find((language) => language.id !== id);
        if (replacement)
            setTargetLanguage(replacement.id);
    }
    resetDerivedState();
      } catch (err) {
        console.warn("chooseSource execution warning:", err);
      }
    },
    chooseTarget(id) {
      try {
        if (id === sourceLanguage)
        return;
    setTargetLanguage(id);
    resetDerivedState();
      } catch (err) {
        console.warn("chooseTarget execution warning:", err);
      }
    },
    saveHandoff() {
      try {
        if (!selectedRoute) {
        setFeedback("当前源/目标组合在仓库路线契约中不存在，无法生成交接。");
        return;
    }
    if (!isSafeRepositoryRef(repositoryRef.trim())) {
        setFeedback("仓库引用仅接受不含凭证、查询参数或本机路径的 local: 标识或 HTTPS 地址。");
        return;
    }
    if (!selectedRouteExecutable) {
        setFeedback(`路线 ${selectedRoute.id} 的本地受限 Profile 状态为 ${selectedRoute.localExecution}，不生成交接。`);
        return;
    }
    if (scope === "repository"
        && (!repositoryPlan
            || repositoryPlan.repository_ref !== repositoryRef.trim()
            || repositoryPlan.route_id !== selectedRoute.id
            || repositoryPlan.source_language !== sourceLanguage
            || repositoryPlan.target_language !== targetLanguage)) {
        setFeedback("整个仓库必须先导入与当前仓库引用、源语言和目标语言完全匹配的只读清单 JSON。");
        return;
    }
    const next = {
        schemaVersion: "1.1.0",
        repositoryRef: repositoryRef.trim(),
        routeId: selectedRoute.id,
        scope,
        inventorySnapshotSha256: scope === "repository" ? repositoryPlan?.snapshot_sha256 : undefined,
        workUnitCount: scope === "repository" ? repositoryPlan?.work_units.length : undefined,
        requestedStatus: "EXPERIMENTAL_EVALUATION",
        executionStatus: "NOT_RUN",
        certificationStatus: "NOT_CERTIFIED",
        blockers: selectedRoute.blockers,
        createdAt: new Date().toISOString(),
    };
    setHandoff(next);
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        setFeedback(scope === "repository"
            ? `整库路线交接已绑定 ${repositoryPlan?.work_units.length ?? 0} 个工作单元；转换执行仍为 NOT_RUN。`
            : "定向路线交接已保存；未执行转换。");
    }
    catch {
        setFeedback("浏览器未允许保存；当前交接仍可导出。");
    }
      } catch (err) {
        console.warn("saveHandoff execution warning:", err);
      }
    },
    async importInventory(event) {
      try {
        const file = event.target.files?.[0];
    event.target.value = "";
    if (!file)
        return;
    if (!selectedRoute) {
        setFeedback("当前源/目标组合不在仓库路线契约中，拒绝导入清单。");
        return;
    }
    if (file.size > 8 * 1024 * 1024) {
        setFeedback("仓库清单超过 8 MB 上限，请缩小评估范围。");
        return;
    }
    setImporting(true);
    try {
        const plan = JSON.parse(await file.text());
        // The browser never decides acceptance. The server re-reads the route
        // contract and re-validates every field before the plan is bound here.
        const response = await fetch("/api/translation/repository-plan", {
            method: "POST",
            cache: "no-store",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                repositoryRef: repositoryRef.trim(),
                routeId: selectedRoute.id,
                sourceLanguage,
                targetLanguage,
                plan,
            }),
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok || !payload || payload.status !== "ACCEPTED") {
            const code = payload && payload.status === "BLOCKED" ? payload.errorCode : `HTTP_${response.status}`;
            const detail = payload && payload.status === "BLOCKED" ? payload.message : "服务端拒绝了该清单。";
            throw new Error(`${code}：${detail}`);
        }
        setRepositoryPlan(payload.plan);
        setHandoff(null);
        setDiscovery(null);
        setWorkUnitFilter("");
        setWorkUnitPage(0);
        setFeedback(`服务端已校验只读清单：${payload.plan.source_file_count} 个源文件拆为 `
            + `${payload.plan.work_units.length} 个待发现工作单元，执行状态仍为 NOT_RUN。`);
    }
    catch (error) {
        setRepositoryPlan(null);
        setFeedback(`仓库清单导入失败：${error instanceof Error ? error.message : "REPOSITORY_PLAN_INVALID"}`);
    }
    finally {
        setImporting(false);
    }
      } catch (err) {
        console.warn("importInventory execution warning:", err);
      }
    },
    async importDiscovery(event) {
      try {
        const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedRoute || !repositoryPlan)
        return;
    if (file.size > 8 * 1024 * 1024) {
        setFeedback("发现报告超过 8 MB 上限，请缩小评估范围。");
        return;
    }
    setImporting(true);
    try {
        const report = JSON.parse(await file.text());
        const response = await fetch("/api/translation/discovery-report", {
            method: "POST",
            cache: "no-store",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                repositoryRef: repositoryRef.trim(),
                routeId: selectedRoute.id,
                snapshotSha256: repositoryPlan.snapshot_sha256,
                sourceLanguage,
                targetLanguage,
                report,
            }),
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok || !payload || payload.status !== "ACCEPTED") {
            const code = payload && payload.status === "BLOCKED" ? payload.errorCode : `HTTP_${response.status}`;
            const detail = payload && payload.status === "BLOCKED" ? payload.message : "服务端拒绝了该发现报告。";
            throw new Error(`${code}：${detail}`);
        }
        setDiscovery(payload.report);
        setWorkUnitPage(0);
        setFeedback(`服务端已校验发现报告：${payload.report.discovered_count} 个单元完成判定，`
            + `${payload.report.ready_count} 个 READY；转换执行仍为 NOT_RUN。`);
    }
    catch (error) {
        setDiscovery(null);
        setFeedback(`发现报告导入失败：${error instanceof Error ? error.message : "DISCOVERY_INVALID"}`);
    }
    finally {
        setImporting(false);
    }
      } catch (err) {
        console.warn("importDiscovery execution warning:", err);
      }
    },
    async copyText(value, message) {
      try {
        try {
        await navigator.clipboard.writeText(value);
        setFeedback(message);
    }
    catch {
        setFeedback("浏览器未允许访问剪贴板，请手动复制。");
    }
      } catch (err) {
        console.warn("copyText execution warning:", err);
      }
    },
    async runnerRequest(url, init) {
      try {
        const response = await fetch(url, {
        cache: "no-store",
        ...init,
        headers: {
            ...(init?.body ? { "content-type": "application/json" } : {}),
            ...(!accountRunner ? {
                authorization: `Bearer ${runnerToken}`,
                "x-elmos-tenant": tenantId,
                "x-elmos-actor": actorId,
            } : {}),
            ...init?.headers,
        },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
        const reason = payload && typeof payload === "object" && "reason" in payload
            ? payload.reason
            : payload && typeof payload === "object" && "errorCode" in payload
                ? payload.errorCode
                : `HTTP_${response.status}`;
        throw new Error(reason || `HTTP_${response.status}`);
    }
    return payload;
      } catch (err) {
        console.warn("runnerRequest execution warning:", err);
      }
    },
    async startRepositoryPipeline() {
      try {
        if (!selectedRouteExecutable) {
        setFeedback("当前路线没有本地 Profile 通过证据，受控执行保持关闭。");
        return;
    }
    if (accountRunner && !repositoryWorkspaceId.trim()) {
        setFeedback("企业账户执行必须选择已授权的仓库工作区；不接受全局预物化源码 ID。");
        return;
    }
    setJobBusy(true);
    try {
        const next = await runnerRequest("/api/translation/jobs", {
            method: "POST",
            body: JSON.stringify({
                workspaceId: repositoryWorkspaceId.trim() ? undefined : workspaceId.trim(),
                repositoryWorkspaceId: repositoryWorkspaceId.trim() || undefined,
                casesBundleId: casesBundleId.trim(),
                sourceLanguage,
                targetLanguage,
            }),
        });
        setJob(next);
        setRecoveryJobId(next.id);
        window.sessionStorage.setItem(JOB_STORAGE_KEY, next.id);
        setFeedback("整库预检已进入持久队列；此时尚未接受转换或计费。预检通过后页面才会显示真实编译、回放、装配与构建状态。");
    }
    catch (error) {
        const reason = error instanceof Error ? error.message : "TRANSLATION_RUNNER_ERROR";
        setFeedback(`整库执行被阻断：${translationRunnerFailureMessage(reason)}`);
    }
    finally {
        setJobBusy(false);
    }
      } catch (err) {
        console.warn("startRepositoryPipeline execution warning:", err);
      }
    },
    async recoverRepositoryPipeline() {
      try {
        setJobBusy(true);
    try {
        const next = await runnerRequest(`/api/translation/jobs/${recoveryJobId.trim()}`);
        setJob(next);
        window.sessionStorage.setItem(JOB_STORAGE_KEY, next.id);
        setFeedback("已按任务 UUID 与当前租户身份恢复持久任务。");
    }
    catch (error) {
        setFeedback(`任务恢复失败：${error instanceof Error ? error.message : "TRANSLATION_JOB_NOT_FOUND"}`);
    }
    finally {
        setJobBusy(false);
    }
      } catch (err) {
        console.warn("recoverRepositoryPipeline execution warning:", err);
      }
    },
    async cancelRepositoryPipeline() {
      try {
        if (!job)
        return;
    setJobBusy(true);
    try {
        setJob(await runnerRequest(`/api/translation/jobs/${job.id}/cancel`, {
            method: "POST",
        }));
        setFeedback("任务已取消；已经写入的检查点保留为审计事实。");
    }
    catch (error) {
        setFeedback(`取消失败：${error instanceof Error ? error.message : "TRANSLATION_CANCEL_FAILED"}`);
    }
    finally {
        setJobBusy(false);
    }
      } catch (err) {
        console.warn("cancelRepositoryPipeline execution warning:", err);
      }
    },
    async downloadRepositoryArtifact() {
      try {
        if (!job?.artifactReady || !job.artifactSha256 || !job.artifactSize)
        return;
    setJobBusy(true);
    try {
        const response = await fetch(`/api/translation/jobs/${job.id}/artifact`, {
            cache: "no-store",
            headers: accountRunner ? undefined : {
                authorization: `Bearer ${runnerToken}`,
                "x-elmos-tenant": tenantId,
                "x-elmos-actor": actorId,
            },
        });
        if (!response.ok) {
            const payload = await response.json().catch(() => null);
            throw new Error(payload?.reason ?? `HTTP_${response.status}`);
        }
        const blob = await verifiedDownloadBlob(response, job.artifactSize, job.artifactSha256, MAX_TRANSLATION_ARTIFACT_BYTES, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
        triggerBrowserDownload(blob, `${job.sourceLanguage}-to-${job.targetLanguage}-${job.status.toLowerCase()}.zip`);
        setFeedback(`已复算 ZIP 摘要并下载；结果状态 ${job.status}，外部验证仍为 NOT_RUN。`);
    }
    catch (error) {
        setFeedback(`归档下载失败：${error instanceof Error ? error.message : "TRANSLATION_DOWNLOAD_FAILED"}`);
    }
    finally {
        setJobBusy(false);
    }
      } catch (err) {
        console.warn("downloadRepositoryArtifact execution warning:", err);
      }
    },
    async downloadConversionReport(format) {
      try {
        const descriptor = format === "markdown"
        ? job?.reportMarkdown
        : format === "json" ? job?.reportJson : job?.reportBundle;
    if (!job?.reportReady || !descriptor)
        return;
    setJobBusy(true);
    try {
        const response = await fetch(`/api/translation/jobs/${job.id}/report?format=${format}`, {
            cache: "no-store",
            headers: accountRunner ? undefined : {
                authorization: `Bearer ${runnerToken}`,
                "x-elmos-tenant": tenantId,
                "x-elmos-actor": actorId,
            },
        });
        if (!response.ok) {
            const payload = await response.json().catch(() => null);
            throw new Error(payload?.reason ?? `HTTP_${response.status}`);
        }
        const blob = await verifiedDownloadBlob(response, descriptor.bytes, descriptor.sha256, format === "bundle" ? MAX_REPORT_BUNDLE_BYTES : MAX_REPORT_BYTES, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
        triggerBrowserDownload(blob, descriptor.path);
        setFeedback(`已在浏览器复算 ${format === "bundle" ? "完整 ZIP" : format === "markdown" ? "Markdown" : "JSON"} 报告摘要并下载；`
            + "报告状态不代表独立验证或认证。");
    }
    catch (error) {
        setFeedback(`转换报告下载失败：${error instanceof Error ? error.message : "TRANSLATION_REPORT_DOWNLOAD_FAILED"}`);
    }
    finally {
        setJobBusy(false);
    }
      } catch (err) {
        console.warn("downloadConversionReport execution warning:", err);
      }
    },
    exportHandoff() {
      try {
        if (!handoff || !selectedRoute) {
        setFeedback("请先保存当前路线交接。");
        return;
    }
    if (handoff.scope === "repository" && !repositoryPlan) {
        setFeedback("为避免持久化客户文件路径，整库清单不会写入浏览器存储；刷新后请重新导入清单再导出。");
        return;
    }
    const payload = {
        ...handoff,
        route: selectedRoute,
        sourceProfile,
        targetProfile,
        contractPath: capability?.contractPath ?? "UNREAD",
        semanticProfile: capability?.semanticProfile ?? "UNKNOWN",
        commands: [routeCommand, ...validationCommands],
        repositoryPlan: handoff.scope === "repository" ? repositoryPlan : undefined,
    };
    triggerBrowserDownload(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }), `${handoff.routeId}-handoff.json`);
    setFeedback("路线交接已导出，所有执行与认证状态保持 NOT_RUN / NOT_CERTIFIED。");
      } catch (err) {
        console.warn("exportHandoff execution warning:", err);
      }
    },
    exportWorkUnits() {
      try {
        if (!repositoryPlan)
        return;
    const header = "source_path,source_sha256,source_bytes,status,execution_status,unsupported_until_discovered\n";
    const rows = repositoryPlan.work_units.map((unit) => [
        unit.source_path,
        unit.source_sha256,
        String(unit.source_bytes),
        unit.status,
        unit.execution_status,
        unit.unsupported_until_discovered.join(" | "),
    ].map((cell) => `"${cell.replaceAll('"', '""')}"`).join(",")).join("\n");
    triggerBrowserDownload(new Blob([header + rows + "\n"], { type: "text/csv" }), `${repositoryPlan.route_id}-work-units.csv`);
    setFeedback("工作单元清单已导出为 CSV；每个单元的执行状态仍为 NOT_RUN。");
      } catch (err) {
        console.warn("exportWorkUnits execution warning:", err);
      }
    },
  },
});

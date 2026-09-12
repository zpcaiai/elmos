// Top-level helpers and constants
try { var lines = [
    ["ALL", "全部业务线"],
    ["SPRING_MODERNIZATION", "Spring 老项目翻新"],
    ["LANGUAGE_TRANSLATION", "全库跨语言转换"],
    ["PROJECT_SYNTHESIS", "多语言项目生成"],
    ["REPOSITORY_WORKSPACE", "代码仓库工作区"],
    ["MIGRATION_GOVERNANCE", "迁移能力与验证"],
    ["DATABASE_DATA", "数据库与数据平台"],
    ["DATABASE_DATA_SQL", "国产数据库 SQL 转换"],
    ["CLIENT_MODERNIZATION", "客户端现代化"],
    ["CLOUD_INFRASTRUCTURE", "云与基础设施"],
    ["SECURITY_COMPLIANCE", "安全与合规"],
    ["DELIVERY_GOVERNANCE", "交付治理"],
    ["COMMERCIALIZATION", "商业化控制面"],
    ["PRICING_USAGE", "套餐与用量"],
    ["SKILLS_QUALIFICATION", "功能能力与验证"],
    ["ENTERPRISE_MODERNIZATION", "企业现代化"],
    ["MAINFRAME_MODERNIZATION", "主机现代化"],
    ["SYSTEM_INTEGRATION", "系统集成"],
    ["PRODUCT_OVERVIEW", "产品总览"],
    ["ADMIN_OPERATIONS", "管理端"],
]; } catch(e) {}
try { var lineLabels = Object.fromEntries(lines); } catch(e) {}
try { var roleRank = { VIEWER: 1, OPERATOR: 2, APPROVER: 3 }; } catch(e) {}
try { var jobBusinessLines = [
    ["ALL", "全部作业类型"],
    ["GENERATION", "项目生成"],
    ["TRANSLATION", "跨语言转换"],
    ["SPRING_UPGRADE", "Spring 升级"],
    ["REPOSITORY_WORKSPACE", "仓库工作区"],
    ["MODERNIZATION_PROOF", "现代化证明"],
]; } catch(e) {}
try { var jobStatuses = [
    ["ALL", "全部状态"],
    ["QUEUED", "排队"],
    ["CLAIMED", "已租约"],
    ["RUNNING", "运行中"],
    ["SUCCEEDED", "成功"],
    ["PARTIAL", "部分完成"],
    ["FAILED", "失败"],
    ["CANCELLED", "已取消"],
    ["LOST", "租约丢失"],
]; } catch(e) {}
try { var knownJobBusinessLines = new Set(jobBusinessLines.slice(1).map(([value]) => value)); } catch(e) {}
try { var knownJobStatuses = new Set(jobStatuses.slice(1).map(([value]) => value)); } catch(e) {}
try { var terminalJobStatuses = new Set([
    "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST",
]); } catch(e) {}
try { var runnerFleetStatuses = [
    ["ALL", "全部 Runner 状态"],
    ["REGISTERED", "已注册 / 待验证"],
    ["READY", "可调度"],
    ["DRAINING", "排空中"],
    ["QUARANTINED", "已隔离"],
    ["LOST", "已失联"],
    ["RETIRED", "已退役"],
]; } catch(e) {}
try { var knownRunnerFleetStatuses = new Set(runnerFleetStatuses.slice(1).map(([value]) => value)); } catch(e) {}
try { var csvCell = function csvCell(value) {
    if (value === null || value === undefined)
        return '""';
    return `"${String(value).replace(/"/g, '""')}"`;
} } catch(e) {}
try { var downloadCsv = function downloadCsv(rows, days) {
    const header = EXPORT_COLUMNS.join(",");
    const body = rows
        .map((row) => EXPORT_COLUMNS.map((column) => csvCell(row[column])).join(","))
        .join("\r\n");
    // The BOM keeps Excel from mangling non-ASCII targets on open.
    const blob = new Blob([`﻿${header}\r\n${body}\r\n`], {
        type: "text/csv;charset=utf-8",
    });
    triggerBrowserDownload(blob, `elmos-audit-${days}d-${new Date().toISOString().slice(0, 10)}.csv`);
} } catch(e) {}
try { var adminSections = [
    ["USERS", "用户与租户"],
    ["TASKS", "任务队列"],
    ["REPOSITORIES", "仓库"],
    ["AUDIT", "审计"],
    ["ALERTS", "告警与事件"],
    ["USAGE", "用量与性能"],
    ["FINANCE", "财务对账"],
    ["CONFIG", "配置与门禁"],
]; } catch(e) {}
try { var formatTime = function formatTime(value) {
    return new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    }).format(new Date(value));
} } catch(e) {}
try { var displayTarget = function displayTarget(value) {
    return value.length > 54 ? `${value.slice(0, 51)}…` : value;
} } catch(e) {}
try { var isReconciliationCase = function isReconciliationCase(value) {
    if (typeof value !== "object" || value === null || Array.isArray(value))
        return false;
    const item = value;
    return typeof item.reconciliationCaseId === "string" && item.reconciliationCaseId.length <= 96
        && typeof item.provider === "string" && item.provider.length <= 32
        && typeof item.providerObjectRef === "string" && item.providerObjectRef.length <= 255
        && typeof item.expectedState === "string" && item.expectedState.length <= 64
        && typeof item.observedState === "string" && item.observedState.length <= 64
        && typeof item.status === "string" && ["OPEN", "RESOLVED", "REJECTED"].includes(item.status)
        && typeof item.reasonCode === "string" && item.reasonCode.length <= 96
        && typeof item.openedAt === "string" && Number.isFinite(Date.parse(item.openedAt))
        && (item.resolvedAt === null || (typeof item.resolvedAt === "string" && Number.isFinite(Date.parse(item.resolvedAt))))
        && (item.resolverActorId === null || (typeof item.resolverActorId === "string" && item.resolverActorId.length <= 128))
        && (item.resolutionRef === null || (typeof item.resolutionRef === "string" && item.resolutionRef.length <= 255));
} } catch(e) {}
try { var isNullableTime = function isNullableTime(value) {
    return value === null || (typeof value === "string" && Number.isFinite(Date.parse(value)));
} } catch(e) {}
try { var isOperationsJob = function isOperationsJob(value) {
    if (typeof value !== "object" || value === null || Array.isArray(value))
        return false;
    const item = value;
    return typeof item.jobId === "string"
        && typeof item.organizationId === "string"
        && typeof item.actorId === "string"
        && typeof item.businessLine === "string"
        && knownJobBusinessLines.has(item.businessLine)
        && typeof item.jobKind === "string"
        && typeof item.status === "string"
        && knownJobStatuses.has(item.status)
        && typeof item.stage === "string"
        && typeof item.progress === "number"
        && Number.isFinite(item.progress)
        && item.progress >= 0
        && item.progress <= 100
        && typeof item.resultStatus === "string"
        && (item.failureCode === null || typeof item.failureCode === "string")
        && Number.isInteger(item.attempt)
        && Number.isInteger(item.maxAttempts)
        && typeof item.createdAt === "string"
        && Number.isFinite(Date.parse(item.createdAt))
        && isNullableTime(item.startedAt)
        && isNullableTime(item.finishedAt)
        && typeof item.cancelRequested === "boolean"
        && Number.isInteger(item.stateVersion);
} } catch(e) {}
try { var isRunnerFleetNode = function isRunnerFleetNode(value) {
    if (typeof value !== "object" || value === null || Array.isArray(value))
        return false;
    const node = value;
    return typeof node.runnerNodeId === "string"
        && typeof node.runnerPoolId === "string"
        && typeof node.agentVersion === "string"
        && typeof node.fleetStatus === "string"
        && knownRunnerFleetStatuses.has(node.fleetStatus)
        && Array.isArray(node.capabilities)
        && node.capabilities.length <= 64
        && node.capabilities.every((capability) => typeof capability === "string")
        && Number.isInteger(node.maxConcurrency)
        && typeof node.attestationVerified === "boolean"
        && isNullableTime(node.attestationVerifiedAt)
        && typeof node.imageAllowlistVersion === "string"
        && isNullableTime(node.lastHeartbeatAt)
        && isNullableTime(node.drainRequestedAt)
        && typeof node.createdAt === "string"
        && Number.isFinite(Date.parse(node.createdAt))
        && typeof node.updatedAt === "string"
        && Number.isFinite(Date.parse(node.updatedAt));
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    hours: "24",
    businessLine: "ALL",
    result: "ALL",
    state: "LOCKED",
    view: null,
    error: "",
    notice: "",
    busyAction: "",
    exportDays: "7",
    exportBusy: false,
    exportError: "",
    exportNotice: "",
    replayRunId: "",
    replayBusy: false,
    replayError: "",
    replay: null,
    quota: null,
    quotaBusy: false,
    quotaError: "",
    quotaNotice: "",
    quotaTokenLimit: "",
    quotaCreditLimit: "",
    quotaReason: "",
    operationsJobs: [],
    operationsJobsLoaded: false,
    operationsJobsBusy: false,
    operationsJobsError: "",
    operationsJobsNotice: "",
    operationsJobBusinessLine: "ALL",
    operationsJobStatus: "ALL",
    operationsJobCancelBusy: "",
    runnerFleet: [],
    runnerFleetLoaded: false,
    runnerFleetBusy: false,
    runnerFleetStatus: "ALL",
    runnerFleetActionBusy: "",
    runnerFleetError: "",
    runnerFleetNotice: "",
    adminSection: "USERS",
    systemReadiness: null,
    systemReadinessBusy: false,
    systemReadinessError: "",
    financialStatus: "OPEN",
    financialCases: [],
    financialLoaded: false,
    financialLoadBusy: false,
    financialBusyAction: "",
    financialError: "",
    financialNotice: "",
    financialUnknown: "",
    financialResolutionRefs: {},
    financialIdempotencyKeys: {"current":null},
    periodLabel: null,
    taskEvents: null,
    repositoryEvents: null,
  },
  lifetimes: {
    attached() {
      const setHours = (val) => { this.setData({ hours: typeof val === "function" ? val(this.data.hours) : val }); };
      const setBusinessLine = (val) => { this.setData({ businessLine: typeof val === "function" ? val(this.data.businessLine) : val }); };
      const setResult = (val) => { this.setData({ result: typeof val === "function" ? val(this.data.result) : val }); };
      const setState = (val) => { this.setData({ state: typeof val === "function" ? val(this.data.state) : val }); };
      const setView = (val) => { this.setData({ view: typeof val === "function" ? val(this.data.view) : val }); };
      const setError = (val) => { this.setData({ error: typeof val === "function" ? val(this.data.error) : val }); };
      const setNotice = (val) => { this.setData({ notice: typeof val === "function" ? val(this.data.notice) : val }); };
      const setBusyAction = (val) => { this.setData({ busyAction: typeof val === "function" ? val(this.data.busyAction) : val }); };
      const setExportDays = (val) => { this.setData({ exportDays: typeof val === "function" ? val(this.data.exportDays) : val }); };
      const setExportBusy = (val) => { this.setData({ exportBusy: typeof val === "function" ? val(this.data.exportBusy) : val }); };
      const setExportError = (val) => { this.setData({ exportError: typeof val === "function" ? val(this.data.exportError) : val }); };
      const setExportNotice = (val) => { this.setData({ exportNotice: typeof val === "function" ? val(this.data.exportNotice) : val }); };
      const setReplayRunId = (val) => { this.setData({ replayRunId: typeof val === "function" ? val(this.data.replayRunId) : val }); };
      const setReplayBusy = (val) => { this.setData({ replayBusy: typeof val === "function" ? val(this.data.replayBusy) : val }); };
      const setReplayError = (val) => { this.setData({ replayError: typeof val === "function" ? val(this.data.replayError) : val }); };
      const setReplay = (val) => { this.setData({ replay: typeof val === "function" ? val(this.data.replay) : val }); };
      const setQuota = (val) => { this.setData({ quota: typeof val === "function" ? val(this.data.quota) : val }); };
      const setQuotaBusy = (val) => { this.setData({ quotaBusy: typeof val === "function" ? val(this.data.quotaBusy) : val }); };
      const setQuotaError = (val) => { this.setData({ quotaError: typeof val === "function" ? val(this.data.quotaError) : val }); };
      const setQuotaNotice = (val) => { this.setData({ quotaNotice: typeof val === "function" ? val(this.data.quotaNotice) : val }); };
      const setQuotaTokenLimit = (val) => { this.setData({ quotaTokenLimit: typeof val === "function" ? val(this.data.quotaTokenLimit) : val }); };
      const setQuotaCreditLimit = (val) => { this.setData({ quotaCreditLimit: typeof val === "function" ? val(this.data.quotaCreditLimit) : val }); };
      const setQuotaReason = (val) => { this.setData({ quotaReason: typeof val === "function" ? val(this.data.quotaReason) : val }); };
      const setOperationsJobs = (val) => { this.setData({ operationsJobs: typeof val === "function" ? val(this.data.operationsJobs) : val }); };
      const setOperationsJobsLoaded = (val) => { this.setData({ operationsJobsLoaded: typeof val === "function" ? val(this.data.operationsJobsLoaded) : val }); };
      const setOperationsJobsBusy = (val) => { this.setData({ operationsJobsBusy: typeof val === "function" ? val(this.data.operationsJobsBusy) : val }); };
      const setOperationsJobsError = (val) => { this.setData({ operationsJobsError: typeof val === "function" ? val(this.data.operationsJobsError) : val }); };
      const setOperationsJobsNotice = (val) => { this.setData({ operationsJobsNotice: typeof val === "function" ? val(this.data.operationsJobsNotice) : val }); };
      const setOperationsJobBusinessLine = (val) => { this.setData({ operationsJobBusinessLine: typeof val === "function" ? val(this.data.operationsJobBusinessLine) : val }); };
      const setOperationsJobStatus = (val) => { this.setData({ operationsJobStatus: typeof val === "function" ? val(this.data.operationsJobStatus) : val }); };
      const setOperationsJobCancelBusy = (val) => { this.setData({ operationsJobCancelBusy: typeof val === "function" ? val(this.data.operationsJobCancelBusy) : val }); };
      const setRunnerFleet = (val) => { this.setData({ runnerFleet: typeof val === "function" ? val(this.data.runnerFleet) : val }); };
      const setRunnerFleetLoaded = (val) => { this.setData({ runnerFleetLoaded: typeof val === "function" ? val(this.data.runnerFleetLoaded) : val }); };
      const setRunnerFleetBusy = (val) => { this.setData({ runnerFleetBusy: typeof val === "function" ? val(this.data.runnerFleetBusy) : val }); };
      const setRunnerFleetStatus = (val) => { this.setData({ runnerFleetStatus: typeof val === "function" ? val(this.data.runnerFleetStatus) : val }); };
      const setRunnerFleetActionBusy = (val) => { this.setData({ runnerFleetActionBusy: typeof val === "function" ? val(this.data.runnerFleetActionBusy) : val }); };
      const setRunnerFleetError = (val) => { this.setData({ runnerFleetError: typeof val === "function" ? val(this.data.runnerFleetError) : val }); };
      const setRunnerFleetNotice = (val) => { this.setData({ runnerFleetNotice: typeof val === "function" ? val(this.data.runnerFleetNotice) : val }); };
      const setAdminSection = (val) => { this.setData({ adminSection: typeof val === "function" ? val(this.data.adminSection) : val }); };
      const setSystemReadiness = (val) => { this.setData({ systemReadiness: typeof val === "function" ? val(this.data.systemReadiness) : val }); };
      const setSystemReadinessBusy = (val) => { this.setData({ systemReadinessBusy: typeof val === "function" ? val(this.data.systemReadinessBusy) : val }); };
      const setSystemReadinessError = (val) => { this.setData({ systemReadinessError: typeof val === "function" ? val(this.data.systemReadinessError) : val }); };
      const setFinancialStatus = (val) => { this.setData({ financialStatus: typeof val === "function" ? val(this.data.financialStatus) : val }); };
      const setFinancialCases = (val) => { this.setData({ financialCases: typeof val === "function" ? val(this.data.financialCases) : val }); };
      const setFinancialLoaded = (val) => { this.setData({ financialLoaded: typeof val === "function" ? val(this.data.financialLoaded) : val }); };
      const setFinancialLoadBusy = (val) => { this.setData({ financialLoadBusy: typeof val === "function" ? val(this.data.financialLoadBusy) : val }); };
      const setFinancialBusyAction = (val) => { this.setData({ financialBusyAction: typeof val === "function" ? val(this.data.financialBusyAction) : val }); };
      const setFinancialError = (val) => { this.setData({ financialError: typeof val === "function" ? val(this.data.financialError) : val }); };
      const setFinancialNotice = (val) => { this.setData({ financialNotice: typeof val === "function" ? val(this.data.financialNotice) : val }); };
      const setFinancialUnknown = (val) => { this.setData({ financialUnknown: typeof val === "function" ? val(this.data.financialUnknown) : val }); };
      const setFinancialResolutionRefs = (val) => { this.setData({ financialResolutionRefs: typeof val === "function" ? val(this.data.financialResolutionRefs) : val }); };
      const financialIdempotencyKeys = { current: { focus: () => {}, scrollIntoView: () => {} } };
      // Lifecycle effect effect_0
      (async () => {
        try {
          if (adminSection === "CONFIG" && state === "READY" && !systemReadiness) {
        void loadSystemReadiness();
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          setOperationsJobs([]);
    setOperationsJobsLoaded(false);
    setOperationsJobsError("");
    setOperationsJobsNotice("");
    setOperationsJobCancelBusy("");
    setRunnerFleet([]);
    setRunnerFleetLoaded(false);
    setRunnerFleetError("");
    setRunnerFleetNotice("");
    setRunnerFleetActionBusy("");
    setFinancialCases([]);
    setFinancialLoaded(false);
    setFinancialError("");
    setFinancialNotice("");
    setFinancialUnknown("");
    setFinancialResolutionRefs({});
    financialIdempotencyKeys.current.clear();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    async loadSystemReadiness() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setSystemReadinessBusy(true);
    setSystemReadinessError("");
    try {
        const response = await fetch("/api/health?probe=readiness", {
            cache: "no-store",
            credentials: "same-origin",
        });
        const payload = await response.json();
        if (!response.ok && payload.status !== "BLOCKED") {
            throw new Error(payload.message || "系统依赖状态读取失败。");
        }
        setSystemReadiness(payload);
    }
    catch (readinessFailure) {
        setSystemReadiness(null);
        setSystemReadinessError(readinessFailure instanceof Error ? readinessFailure.message : "系统依赖状态读取失败。");
    }
    finally {
        setSystemReadinessBusy(false);
    }
      } catch (err) {
        console.warn("loadSystemReadiness execution warning:", err);
      }
    },
    async downloadAuditExport() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated" || !account.principal?.isPlatformAdmin) {
        setExportError("请先通过独立管理员入口登录已验证的管理员账户。");
        return;
    }
    setExportBusy(true);
    setExportError("");
    setExportNotice("");
    const rows = [];
    let cursor = null;
    let truncated = false;
    try {
        for (let page = 0;; page++) {
            if (page >= MAX_EXPORT_PAGES) {
                truncated = true;
                break;
            }
            const query = new URLSearchParams({
                days: exportDays,
                businessLine,
                result,
                limit: "200",
            });
            if (cursor) {
                query.set("afterOccurredAt", cursor.at);
                query.set("afterEventId", cursor.id);
            }
            const response = await fetch(`/api/admin/audit-export?${query}`, {
                credentials: "same-origin",
                cache: "no-store",
            });
            const payload = await response.json();
            if (!response.ok)
                throw new Error(payload.message || "审计导出读取失败。");
            rows.push(...payload.rows);
            if (!payload.hasMore || !payload.nextOccurredAt || !payload.nextEventId)
                break;
            cursor = { at: payload.nextOccurredAt, id: payload.nextEventId };
        }
        if (rows.length === 0) {
            setExportNotice("所选窗口内没有审计记录。");
            return;
        }
        downloadCsv(rows, exportDays);
        setExportNotice(truncated
            ? `已导出前 ${rows.length} 行后停止：窗口过大，请缩短天数或收窄业务线后重新导出。`
            : `已导出 ${rows.length} 行。`);
    }
    catch (downloadError) {
        setExportError(downloadError instanceof Error ? downloadError.message : "审计导出读取失败。");
    }
    finally {
        setExportBusy(false);
    }
      } catch (err) {
        console.warn("downloadAuditExport execution warning:", err);
      }
    },
    async loadReplay() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const runId = replayRunId.trim();
    if (!runId) {
        setReplayError("请输入迁移运行 ID。");
        return;
    }
    if (account.status !== "authenticated" || !account.principal?.isPlatformAdmin) {
        setReplayError("请先通过独立管理员入口登录已验证的管理员账户。");
        return;
    }
    setReplayBusy(true);
    setReplayError("");
    setReplay(null);
    try {
        const response = await fetch(`/api/admin/run-replay/${encodeURIComponent(runId)}`, {
            credentials: "same-origin",
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(response.status === 404
                ? "本租户下没有这个运行 ID。"
                : payload.message || "运行历史读取失败。");
        }
        setReplay(payload);
    }
    catch (replayFailure) {
        setReplayError(replayFailure instanceof Error ? replayFailure.message : "运行历史读取失败。");
    }
    finally {
        setReplayBusy(false);
    }
      } catch (err) {
        console.warn("loadReplay execution warning:", err);
      }
    },
    async loadQuota() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated" || !account.principal?.isPlatformAdmin) {
        setQuotaError("请先通过独立管理员入口登录已验证的管理员账户。");
        return;
    }
    setQuotaBusy(true);
    setQuotaError("");
    setQuotaNotice("");
    try {
        const response = await fetch("/api/admin/tenant-quota", {
            credentials: "same-origin",
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.message || "配额读取失败。");
        setQuota(payload);
        setQuotaTokenLimit(payload.tokenLimit);
        setQuotaCreditLimit(payload.creditLimit);
    }
    catch (quotaFailure) {
        setQuota(null);
        setQuotaError(quotaFailure instanceof Error ? quotaFailure.message : "配额读取失败。");
    }
    finally {
        setQuotaBusy(false);
    }
      } catch (err) {
        console.warn("loadQuota execution warning:", err);
      }
    },
    async submitQuotaAdjustment(event) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        event.preventDefault();
    if (!quota)
        return;
    setQuotaBusy(true);
    setQuotaError("");
    setQuotaNotice("");
    try {
        const response = await fetch("/api/admin/tenant-quota", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            credentials: "same-origin",
            cache: "no-store",
            body: JSON.stringify({
                quotaAllocationId: quota.quotaAllocationId,
                tokenLimit: quotaTokenLimit.trim(),
                creditLimit: quotaCreditLimit.trim(),
                expectedVersion: quota.allocationVersion,
                reasonCode: quotaReason.trim().toUpperCase(),
            }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(response.status === 409
                ? "配额已被其他管理员改动，请重新读取后再调整。"
                : payload.message || "配额调整失败。");
        }
        setQuota(payload);
        setQuotaTokenLimit(payload.tokenLimit);
        setQuotaCreditLimit(payload.creditLimit);
        setQuotaReason("");
        setQuotaNotice(`已调整，当前版本 ${payload.allocationVersion}。`);
    }
    catch (adjustFailure) {
        setQuotaError(adjustFailure instanceof Error ? adjustFailure.message : "配额调整失败。");
    }
    finally {
        setQuotaBusy(false);
    }
      } catch (err) {
        console.warn("submitQuotaAdjustment execution warning:", err);
      }
    },
    async loadOperationsJobs() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated" || !account.principal?.isPlatformAdmin) {
        setOperationsJobsError("请先通过独立管理员入口登录已验证的管理员账户。");
        return;
    }
    setOperationsJobsBusy(true);
    setOperationsJobsError("");
    setOperationsJobsNotice("");
    setOperationsJobs([]);
    setOperationsJobsLoaded(false);
    try {
        const query = new URLSearchParams({ limit: "100" });
        if (operationsJobBusinessLine !== "ALL") {
            query.set("businessLine", operationsJobBusinessLine);
        }
        if (operationsJobStatus !== "ALL")
            query.set("status", operationsJobStatus);
        const response = await fetch(`/api/admin/jobs?${query}`, {
            credentials: "same-origin",
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.message || "持久作业列表读取失败。");
        if (payload.schemaVersion !== "1.0.0"
            || !Array.isArray(payload.items)
            || payload.items.length > 100
            || !payload.items.every(isOperationsJob)
            || typeof payload.limit !== "number"
            || typeof payload.scanned !== "number"
            || typeof payload.scanTruncated !== "boolean") {
            throw new Error("控制面返回了不受支持的持久作业数据。");
        }
        setOperationsJobs(payload.items);
        setOperationsJobsLoaded(true);
        if (payload.scanTruncated) {
            setOperationsJobsNotice(`已扫描 ${payload.scanned} 条后达到服务端上限；请收窄状态或业务线。`);
        }
    }
    catch (jobsFailure) {
        setOperationsJobsError(jobsFailure instanceof Error ? jobsFailure.message : "持久作业列表读取失败。");
    }
    finally {
        setOperationsJobsBusy(false);
    }
      } catch (err) {
        console.warn("loadOperationsJobs execution warning:", err);
      }
    },
    async cancelOperationsJob(job) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!can("OPERATOR")) {
        setOperationsJobsError("取消作业需要 OPERATOR 或更高权限。");
        return;
    }
    setOperationsJobCancelBusy(job.jobId);
    setOperationsJobsError("");
    setOperationsJobsNotice("");
    let response;
    try {
        response = await fetch(`/api/admin/jobs/${encodeURIComponent(job.jobId)}/cancel`, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
        });
    }
    catch {
        setOperationsJobsError("取消请求结果未知，系统未自动重试。请先重新读取作业状态，再决定是否人工重放。");
        setOperationsJobCancelBusy("");
        return;
    }
    let payload = {};
    try {
        payload = await response.json();
    }
    catch {
        // A confirmed non-2xx response can still be surfaced without inventing a body.
    }
    if (!response.ok) {
        setOperationsJobsError(response.status === 409
            ? "该作业已进入终态，无法再取消；请重新读取列表。"
            : payload.message || payload.errorCode || "作业取消被拒绝。");
        setOperationsJobCancelBusy("");
        return;
    }
    if (payload.schemaVersion !== "1.0.0"
        || payload.jobId !== job.jobId
        || payload.cancelRequested !== true
        || typeof payload.status !== "string"
        || !knownJobStatuses.has(payload.status)
        || typeof payload.idempotentReplay !== "boolean") {
        setOperationsJobsError("取消请求已返回，但结果无法确认。系统未自动重试，请重新读取作业。");
        setOperationsJobCancelBusy("");
        return;
    }
    setOperationsJobs((current) => current.map((candidate) => (candidate.jobId === job.jobId
        ? { ...candidate, status: payload.status, cancelRequested: true }
        : candidate)));
    setOperationsJobsNotice(payload.idempotentReplay
        ? "该作业之前已请求取消；本次为幂等确认。"
        : "取消请求已被持久队列接受。");
    setOperationsJobCancelBusy("");
      } catch (err) {
        console.warn("cancelOperationsJob execution warning:", err);
      }
    },
    async loadRunnerFleet() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated" || !account.principal?.isPlatformAdmin) {
        setRunnerFleetError("请先通过独立管理员入口登录已验证的管理员账户。");
        return;
    }
    setRunnerFleetBusy(true);
    setRunnerFleetError("");
    setRunnerFleetNotice("");
    setRunnerFleet([]);
    setRunnerFleetLoaded(false);
    try {
        const query = new URLSearchParams({ limit: "100" });
        if (runnerFleetStatus !== "ALL")
            query.set("status", runnerFleetStatus);
        const response = await fetch(`/api/admin/runners?${query}`, {
            credentials: "same-origin",
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.message || "Runner Fleet 读取失败。");
        if (payload.schemaVersion !== "1.0.0"
            || !Array.isArray(payload.items)
            || payload.items.length > 100
            || !payload.items.every(isRunnerFleetNode)
            || payload.returned !== payload.items.length
            || typeof payload.truncated !== "boolean") {
            throw new Error("控制面返回了不受支持的 Runner Fleet 数据。");
        }
        setRunnerFleet(payload.items);
        setRunnerFleetLoaded(true);
        if (payload.truncated) {
            setRunnerFleetNotice("列表已达 100 个节点上限；请按状态收窄结果。");
        }
    }
    catch (fleetFailure) {
        setRunnerFleetError(fleetFailure instanceof Error ? fleetFailure.message : "Runner Fleet 读取失败。");
    }
    finally {
        setRunnerFleetBusy(false);
    }
      } catch (err) {
        console.warn("loadRunnerFleet execution warning:", err);
      }
    },
    async mutateRunnerFleetNode(node, action) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated") {
        setRunnerFleetError("Runner 证明和排空只接受已验证的管理员企业 OIDC 会话。");
        return;
    }
    const requiredRole = action === "drain" ? "OPERATOR" : "APPROVER";
    if (!can(requiredRole)) {
        setRunnerFleetError(`该 Runner 操作需要 ${requiredRole} 权限。`);
        return;
    }
    const actionId = `${node.runnerNodeId}:${action}`;
    setRunnerFleetActionBusy(actionId);
    setRunnerFleetError("");
    setRunnerFleetNotice("");
    let response;
    try {
        response = await fetch(`/api/admin/runners/${encodeURIComponent(node.runnerNodeId)}/${action}`, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
        });
    }
    catch {
        setRunnerFleetError("Runner 操作结果未知，系统未自动重试。请先重新读取 Fleet 状态。");
        setRunnerFleetActionBusy("");
        return;
    }
    let payload = {};
    try {
        payload = await response.json();
    }
    catch {
        // Preserve the authoritative HTTP outcome without inventing a response body.
    }
    const expectedStatus = action === "drain" ? "DRAINING" : "READY";
    if (!response.ok) {
        setRunnerFleetError(payload.message || payload.errorCode || payload.code || "Runner 管理操作被拒绝。");
        setRunnerFleetActionBusy("");
        return;
    }
    if (payload.runnerNodeId !== node.runnerNodeId || payload.status !== expectedStatus) {
        setRunnerFleetError("Runner 操作已返回，但结果无法确认。系统未自动重试，请重新读取 Fleet。");
        setRunnerFleetActionBusy("");
        return;
    }
    setRunnerFleetActionBusy("");
    await loadRunnerFleet();
    setRunnerFleetNotice(action === "drain" ? "Runner 排空请求已确认。" : "Runner attestation 已经独立验证并进入 READY。");
      } catch (err) {
        console.warn("mutateRunnerFleetNode execution warning:", err);
      }
    },
    async loadFinancialReconciliation() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated") {
        setFinancialCases([]);
        setFinancialLoaded(false);
        setFinancialError("财务对账只接受已验证的管理员企业 OIDC 会话。");
        return;
    }
    setFinancialLoadBusy(true);
    setFinancialError("");
    setFinancialNotice("");
    setFinancialUnknown("");
    try {
        const query = new URLSearchParams({ status: financialStatus, limit: "100" });
        const response = await fetch(`/api/admin/billing/reconciliation?${query}`, {
            credentials: "same-origin",
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.message || "财务对账列表读取失败。");
        if (payload.schemaVersion !== "1.0.0"
            || !Array.isArray(payload.items)
            || payload.items.length > 200
            || !payload.items.every(isReconciliationCase)) {
            throw new Error("商业服务返回了不受支持的财务对账数据。");
        }
        setFinancialCases(payload.items);
        setFinancialLoaded(true);
    }
    catch (loadFailure) {
        setFinancialCases([]);
        setFinancialLoaded(false);
        setFinancialError(loadFailure instanceof Error ? loadFailure.message : "财务对账列表读取失败。");
    }
    finally {
        setFinancialLoadBusy(false);
    }
      } catch (err) {
        console.warn("loadFinancialReconciliation execution warning:", err);
      }
    },
    stableFinancialIdempotencyKey(reconciliationCaseId, resolutionStatus, resolutionRef) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const tuple = JSON.stringify([reconciliationCaseId, resolutionStatus, resolutionRef]);
    const existing = financialIdempotencyKeys.current.get(tuple);
    if (existing)
        return { tuple, key: existing };
    const key = `finance-${resolutionStatus.toLowerCase()}-${crypto.randomUUID()}`;
    financialIdempotencyKeys.current.set(tuple, key);
    return { tuple, key };
      } catch (err) {
        console.warn("stableFinancialIdempotencyKey execution warning:", err);
      }
    },
    async resolveFinancialReconciliation(item, resolutionStatus) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated") {
        setFinancialError("财务对账只接受企业 OIDC 会话。");
        return;
    }
    if (!account.principal?.permissions.includes("admin:approve")) {
        setFinancialError("当前企业账户缺少 admin:approve，不能结案财务对账。");
        return;
    }
    const resolutionRef = (financialResolutionRefs[item.reconciliationCaseId] ?? "").trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._:/-]{7,254}$/.test(resolutionRef)) {
        setFinancialError("处理依据必须是 8 到 255 字符的稳定外部证据代号。");
        return;
    }
    const attempt = stableFinancialIdempotencyKey(item.reconciliationCaseId, resolutionStatus, resolutionRef);
    const actionId = `${item.reconciliationCaseId}:${resolutionStatus}`;
    setFinancialBusyAction(actionId);
    setFinancialError("");
    setFinancialNotice("");
    setFinancialUnknown("");
    let response;
    try {
        response = await fetch("/api/admin/billing/reconciliation", {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": attempt.key,
            },
            body: JSON.stringify({
                reconciliationCaseId: item.reconciliationCaseId,
                resolutionStatus,
                resolutionRef,
            }),
        });
    }
    catch {
        setFinancialUnknown("本次结案结果未知，系统未自动重试。请先重新读取案件状态；若人工确认需要重放，当前页面会对相同案件、状态和依据复用原 Idempotency-Key。");
        setFinancialBusyAction("");
        return;
    }
    let payload = null;
    try {
        payload = await response.json();
    }
    catch {
        payload = null;
    }
    if (response.status >= 500
        || payload?.status === "UNKNOWN"
        || payload?.operationMayHaveCompleted === true
        || (response.ok && payload?.status !== resolutionStatus)) {
        setFinancialUnknown("本次结案结果未知，系统未自动重试。请先重新读取案件状态；若人工确认需要重放，当前页面会对相同案件、状态和依据复用原 Idempotency-Key。");
        setFinancialBusyAction("");
        return;
    }
    if (!response.ok) {
        setFinancialError(typeof payload?.message === "string" ? payload.message : "财务对账结案被拒绝。");
        setFinancialBusyAction("");
        return;
    }
    financialIdempotencyKeys.current.delete(attempt.tuple);
    // The resolve endpoint confirms only the terminal status, not the database
    // timestamp or resolver fields. Remove the case from this OPEN result set
    // instead of inventing those evidence-bearing values in the browser.
    setFinancialCases((current) => current.filter((candidate) => candidate.reconciliationCaseId !== item.reconciliationCaseId));
    setFinancialNotice(resolutionStatus === "RESOLVED" ? "上游已确认案件为 RESOLVED。" : "上游已确认案件为 REJECTED。");
    setFinancialBusyAction("");
      } catch (err) {
        console.warn("resolveFinancialReconciliation execution warning:", err);
      }
    },
    async loadData() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (account.status !== "authenticated" || !account.principal?.isPlatformAdmin) {
        setState("ERROR");
        setError("请先通过独立管理员入口登录已验证的管理员账户。");
        return;
    }
    setState("LOADING");
    setError("");
    try {
        const query = new URLSearchParams({ hours, businessLine, result, limit: "60" });
        const response = await fetch(`/api/admin/operations?${query}`, {
            credentials: "same-origin",
            cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.message || "管理端数据读取失败。");
        setView(payload);
        setState("READY");
    }
    catch (loadError) {
        setView(null);
        setState("ERROR");
        setError(loadError instanceof Error ? loadError.message : "管理端数据读取失败。");
    }
      } catch (err) {
        console.warn("loadData execution warning:", err);
      }
    },
    async load(event) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        event?.preventDefault();
    await loadData();
      } catch (err) {
        console.warn("load execution warning:", err);
      }
    },
    async mutate(action, body) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setBusyAction(action);
    setError("");
    setNotice("");
    try {
        const response = await fetch("/api/admin/operations", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            credentials: "same-origin",
            body: JSON.stringify({ action, ...body }),
        });
        const payload = await response.json();
        if (!response.ok)
            throw new Error(payload.message || "管理操作执行失败。");
        setNotice(`操作已完成：${payload.status ?? payload.decision ?? action}`);
        await loadData();
    }
    catch (actionError) {
        setState("READY");
        setError(actionError instanceof Error ? actionError.message : "管理操作执行失败。");
    }
    finally {
        setBusyAction("");
    }
      } catch (err) {
        console.warn("mutate execution warning:", err);
      }
    },
    lock() {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setView(null);
    setOperationsJobs([]);
    setOperationsJobsLoaded(false);
    setOperationsJobsError("");
    setOperationsJobsNotice("");
    setOperationsJobCancelBusy("");
    setRunnerFleet([]);
    setRunnerFleetLoaded(false);
    setRunnerFleetError("");
    setRunnerFleetNotice("");
    setRunnerFleetActionBusy("");
    setFinancialCases([]);
    setFinancialLoaded(false);
    setFinancialResolutionRefs({});
    setFinancialError("");
    setFinancialNotice("");
    setFinancialUnknown("");
    financialIdempotencyKeys.current.clear();
    setError("");
    setNotice("");
    setState("LOCKED");
      } catch (err) {
        console.warn("lock execution warning:", err);
      }
    },
    can(required) {
      const financialIdempotencyKeys = this.data.financialIdempotencyKeys || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        return Boolean(view && roleRank[view.role] >= roleRank[required]);
      } catch (err) {
        console.warn("can execution warning:", err);
      }
    },
  },
});

// Top-level helpers and constants
try { const lines = [
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
try { const lineLabels = Object.fromEntries(lines); } catch(e) {}
try { const roleRank = { VIEWER: 1, OPERATOR: 2, APPROVER: 3 }; } catch(e) {}
try { const jobBusinessLines = [
    ["ALL", "全部作业类型"],
    ["GENERATION", "项目生成"],
    ["TRANSLATION", "跨语言转换"],
    ["SPRING_UPGRADE", "Spring 升级"],
    ["REPOSITORY_WORKSPACE", "仓库工作区"],
    ["MODERNIZATION_PROOF", "现代化证明"],
]; } catch(e) {}
try { const jobStatuses = [
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
try { const knownJobBusinessLines = new Set(jobBusinessLines.slice(1).map(([value]) => value)); } catch(e) {}
try { const knownJobStatuses = new Set(jobStatuses.slice(1).map(([value]) => value)); } catch(e) {}
try { const terminalJobStatuses = new Set([
    "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST",
]); } catch(e) {}
try { const runnerFleetStatuses = [
    ["ALL", "全部 Runner 状态"],
    ["REGISTERED", "已注册 / 待验证"],
    ["READY", "可调度"],
    ["DRAINING", "排空中"],
    ["QUARANTINED", "已隔离"],
    ["LOST", "已失联"],
    ["RETIRED", "已退役"],
]; } catch(e) {}
try { const knownRunnerFleetStatuses = new Set(runnerFleetStatuses.slice(1).map(([value]) => value)); } catch(e) {}
try { function csvCell(value) {
    if (value === null || value === undefined)
        return '""';
    return `"${String(value).replace(/"/g, '""')}"`;
} } catch(e) {}
try { function downloadCsv(rows, days) {
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
try { const adminSections = [
    ["USERS", "用户与租户"],
    ["TASKS", "任务队列"],
    ["REPOSITORIES", "仓库"],
    ["AUDIT", "审计"],
    ["ALERTS", "告警与事件"],
    ["USAGE", "用量与性能"],
    ["FINANCE", "财务对账"],
    ["CONFIG", "配置与门禁"],
]; } catch(e) {}
try { function formatTime(value) {
    return new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    }).format(new Date(value));
} } catch(e) {}
try { function displayTarget(value) {
    return value.length > 54 ? `${value.slice(0, 51)}…` : value;
} } catch(e) {}
try { function isReconciliationCase(value) {
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
try { function isNullableTime(value) {
    return value === null || (typeof value === "string" && Number.isFinite(Date.parse(value)));
} } catch(e) {}
try { function isOperationsJob(value) {
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
try { function isRunnerFleetNode(value) {
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
    incident: {
      type: null,
      value: null,
    },
    businessLineLabel: {
      type: null,
      value: null,
    },
    disabled: {
      type: null,
      value: null,
    },
  },
  data: {
  },
  lifetimes: {
    attached() {
    },
    detached() {
    },
  },
  methods: {
    onAssign(e) {
      this.triggerEvent("assign", e.detail);
    },
    onResolve(e) {
      this.triggerEvent("resolve", e.detail);
    },
  },
});

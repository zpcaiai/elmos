const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "OperationsAdmin",
  "title": "% · P95",
  "role": "table",
  "source": {
    "file": "app/admin/OperationsAdmin.tsx",
    "componentName": "OperationsAdmin",
    "sha256": "sha256:887dfc4ed913566b13192fb8ca4b4a86b6487f501806b3bc31b77183259f390f",
    "range": {
      "start": 9911,
      "end": 89288
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "token",
      "type": "inferred"
    },
    {
      "name": "hours",
      "type": "inferred"
    },
    {
      "name": "businessLine",
      "type": "inferred"
    },
    {
      "name": "result",
      "type": "inferred"
    },
    {
      "name": "state",
      "type": "LoadState"
    },
    {
      "name": "view",
      "type": "OperationsConsoleView | null"
    },
    {
      "name": "error",
      "type": "inferred"
    },
    {
      "name": "notice",
      "type": "inferred"
    },
    {
      "name": "busyAction",
      "type": "inferred"
    },
    {
      "name": "exportDays",
      "type": "inferred"
    },
    {
      "name": "exportBusy",
      "type": "inferred"
    },
    {
      "name": "exportError",
      "type": "inferred"
    },
    {
      "name": "exportNotice",
      "type": "inferred"
    },
    {
      "name": "replayRunId",
      "type": "inferred"
    },
    {
      "name": "replayBusy",
      "type": "inferred"
    },
    {
      "name": "replayError",
      "type": "inferred"
    },
    {
      "name": "replay",
      "type": "RunReplayTimeline | null"
    },
    {
      "name": "quota",
      "type": "TenantQuotaView | null"
    },
    {
      "name": "quotaBusy",
      "type": "inferred"
    },
    {
      "name": "quotaError",
      "type": "inferred"
    },
    {
      "name": "quotaNotice",
      "type": "inferred"
    },
    {
      "name": "quotaTokenLimit",
      "type": "inferred"
    },
    {
      "name": "quotaCreditLimit",
      "type": "inferred"
    },
    {
      "name": "quotaReason",
      "type": "inferred"
    },
    {
      "name": "operationsJobs",
      "type": "OperationsJobView[]"
    },
    {
      "name": "operationsJobsLoaded",
      "type": "inferred"
    },
    {
      "name": "operationsJobsBusy",
      "type": "inferred"
    },
    {
      "name": "operationsJobsError",
      "type": "inferred"
    },
    {
      "name": "operationsJobsNotice",
      "type": "inferred"
    },
    {
      "name": "operationsJobBusinessLine",
      "type": "OperationsJobBusinessLine | \"ALL\""
    },
    {
      "name": "operationsJobStatus",
      "type": "OperationsJobStatus | \"ALL\""
    },
    {
      "name": "operationsJobCancelBusy",
      "type": "inferred"
    },
    {
      "name": "runnerFleet",
      "type": "RunnerFleetNodeView[]"
    },
    {
      "name": "runnerFleetLoaded",
      "type": "inferred"
    },
    {
      "name": "runnerFleetBusy",
      "type": "inferred"
    },
    {
      "name": "runnerFleetStatus",
      "type": "RunnerFleetStatus | \"ALL\""
    },
    {
      "name": "runnerFleetActionBusy",
      "type": "inferred"
    },
    {
      "name": "runnerFleetError",
      "type": "inferred"
    },
    {
      "name": "runnerFleetNotice",
      "type": "inferred"
    },
    {
      "name": "adminSection",
      "type": "AdminSection"
    },
    {
      "name": "systemReadiness",
      "type": "SystemReadiness | null"
    },
    {
      "name": "systemReadinessBusy",
      "type": "inferred"
    },
    {
      "name": "systemReadinessError",
      "type": "inferred"
    },
    {
      "name": "financialStatus",
      "type": "ReconciliationStatus"
    },
    {
      "name": "financialCases",
      "type": "ReconciliationCase[]"
    },
    {
      "name": "financialLoaded",
      "type": "inferred"
    },
    {
      "name": "financialLoadBusy",
      "type": "inferred"
    },
    {
      "name": "financialBusyAction",
      "type": "inferred"
    },
    {
      "name": "financialError",
      "type": "inferred"
    },
    {
      "name": "financialNotice",
      "type": "inferred"
    },
    {
      "name": "financialUnknown",
      "type": "inferred"
    },
    {
      "name": "financialResolutionRefs",
      "type": "Record<string, string>"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useRef",
    "useMemo",
    "useEffect"
  ],
  "resources": [
    "UNKNOWN"
  ],
  "apiPaths": [
    "/api/admin/billing/reconciliation",
    "/api/admin/operations",
    "/api/admin/tenant-quota",
    "/api/health?probe=readiness"
  ],
  "labels": [
    "% · P95",
    "/ 预算",
    "/api/admin/billing/reconciliation",
    "/api/admin/operations",
    "/api/admin/tenant-quota",
    "/api/health?probe=readiness",
    "/repositories",
    "1.0.0",
    "100",
    "168",
    "200",
    "24",
    "30",
    "366",
    "60",
    "720",
    "90",
    "ACKNOWLEDGED",
    "ACKNOWLEDGE_ALERT",
    "ALERTS",
    "ALL",
    "API 与页面性能",
    "APPROVER",
    "APPROVE_REMEDIATION"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-scroll-row-table-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "OperationsAdmin:source-blocker"
  ],
  "irDigest": "sha256:93a85942b0a0df4adb422fc1ecc902f767146210fc3a99ca5197bc90ffd2d8f4"
}));

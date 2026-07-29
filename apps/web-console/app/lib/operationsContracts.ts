export type OperationResult = "SUCCESS" | "FAILURE" | "CANCELLED";

export type UserActivityEvent = {
  eventId: string;
  sessionId: string;
  eventKind: string;
  action: string;
  businessLine: string;
  route: string;
  target: string;
  occurredAt: string;
  durationMs?: number;
  result: OperationResult;
  errorCode?: string;
  metricName?: string;
  metricValue?: number;
  metadata?: Record<string, string>;
};

export type BusinessLineActivitySummary = {
  businessLine: string;
  eventCount: number;
  sessionCount: number;
  failureCount: number;
  failureRate: number;
  p95DurationMs: number | null;
};

export type UserActivitySummary = {
  from: string;
  to: string;
  totalEvents: number;
  activeSessions: number;
  failedEvents: number;
  failureRate: number;
  p95DurationMs: number | null;
  businessLines: BusinessLineActivitySummary[];
  topErrors: Array<{ errorCode: string; count: number; lastSeenAt: string }>;
  recentEvents: Array<{
    eventId: string;
    sessionId: string;
    eventKind: string;
    action: string;
    businessLine: string;
    route: string;
    target: string;
    occurredAt: string;
    durationMs: number | null;
    result: OperationResult;
    errorCode: string | null;
    metricName: string | null;
    metricValue: number | null;
  }>;
  persistence: "POSTGRES_DUAL_STORE";
  externalEvidence: "NOT_RUN";
};

export type OperationsSloPolicy = {
  policyId: string;
  businessLine: string;
  latencyP95BudgetMs: number;
  failureRateBudgetBps: number;
  minimumEventCount: number;
  evaluationWindowMinutes: number;
  ownerActorId: string;
  runbookUrl: string;
  enabled: boolean;
  version: number;
};

export type OperationsAlert = {
  alertId: string;
  businessLine: string;
  signal: "FAILURE_RATE_BPS" | "LATENCY_P95_MS";
  severity: "P0" | "P1" | "P2";
  status: "OPEN" | "ACKNOWLEDGED" | "SILENCED" | "RESOLVED";
  observedValue: number;
  thresholdValue: number;
  occurrenceCount: number;
  ownerActorId: string;
  runbookUrl: string;
  firstSeenAt: string;
  lastSeenAt: string;
  silenceUntil: string | null;
  version: number;
};

export type OperationsIncident = {
  incidentId: string;
  alertId: string;
  businessLine: string;
  severity: "P0" | "P1" | "P2";
  status: "OPEN" | "ACKNOWLEDGED" | "MITIGATED" | "RESOLVED";
  summaryCode: string;
  ownerActorId: string;
  openedAt: string;
  resolutionCode: string | null;
  version: number;
};

export type OperationsRemediation = {
  proposalId: string;
  incidentId: string;
  recipeId: string;
  remediationKind: "PERFORMANCE" | "BUG_FIX";
  riskLevel: "LOW" | "MEDIUM" | "HIGH";
  status:
    | "PROPOSED"
    | "APPROVED"
    | "REJECTED"
    | "READY_FOR_SCM"
    | "EXECUTED"
    | "VERIFIED"
    | "VERIFICATION_FAILED"
    | "ROLLED_BACK";
  titleCode: string;
  preconditionDigest: string;
  artifactDigest: string | null;
  patchPreview: string;
  expectedDiagnosticDelta: string;
  requiredTests: string;
  rollbackPlan: string;
  createdAt: string;
  decidedBy: string | null;
  version: number;
};

export type OperationsControl = {
  policies: OperationsSloPolicy[];
  alerts: OperationsAlert[];
  incidents: OperationsIncident[];
  remediations: OperationsRemediation[];
  retentionRuns: Array<{
    retentionRunId: string;
    actorId: string;
    retentionDays: number;
    cutoffAt: string;
    deletedEventCount: number;
    aggregateEvidence: string;
    occurredAt: string;
  }>;
  pendingNotifications: number;
  automationMode: "DETECT_DIAGNOSE_PROPOSE_AUTOMATIC";
  sourceMutationMode: "APPROVAL_AND_EXTERNAL_SCM_REQUIRED";
  notificationDeliveryEvidence: "NOT_RUN";
  productionDeploymentEvidence: "NOT_RUN";
};

export type OperationsConsoleView = {
  activity: UserActivitySummary;
  control: OperationsControl;
  role: "VIEWER" | "OPERATOR" | "APPROVER";
  actorId: string;
};

/** One exported audit row. `source` names which store it came from. */
export type AuditExportRow = {
  eventId: string;
  source: "AUDIT" | "TELEMETRY";
  sessionId?: string;
  eventKind: string;
  action: string;
  businessLine: string;
  route: string;
  target: string;
  occurredAt: string;
  durationMs?: number;
  result: OperationResult;
  errorCode?: string;
};

/**
 * One keyset page of the audit export.
 *
 * `nextOccurredAt` and `nextEventId` are both present exactly when `hasMore`
 * is true; they form a single cursor and must be sent together.
 */
export type AuditExportPage = {
  from: string;
  to: string;
  rows: AuditExportRow[];
  hasMore: boolean;
  nextOccurredAt?: string;
  nextEventId?: string;
};

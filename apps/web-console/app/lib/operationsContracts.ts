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

/**
 * A tenant's allowance, as an operator sees it.
 *
 * Every amount is a decimal string, not a number: these are `BigDecimal` on the
 * server, and a limit that lost precision by round-tripping through a JavaScript
 * float would be a billing defect with no visible symptom.
 *
 * `minimumTokenLimit` and `minimumCreditLimit` are consumed + reserved. A
 * decrease below them is refused, because a reservation is a promise already
 * made to the tenant. They are carried in the view so the UI can say so before
 * the operator submits, rather than after.
 */
export type TenantQuotaView = {
  organizationId: string;
  quotaAllocationId: string;
  subscriptionId: string;
  planId: string;
  planDisplayName: string;
  periodStartsAt: string;
  periodEndsAt: string;
  tokenLimit: string;
  creditLimit: string;
  consumedTokens: string;
  consumedCredits: string;
  reservedTokens: string;
  reservedCredits: string;
  minimumTokenLimit: string;
  minimumCreditLimit: string;
  allocationVersion: number;
};

export type OperationsJobBusinessLine =
  | "GENERATION"
  | "TRANSLATION"
  | "SPRING_UPGRADE"
  | "REPOSITORY_WORKSPACE"
  | "MODERNIZATION_PROOF";

export type OperationsJobStatus =
  | "QUEUED"
  | "CLAIMED"
  | "RUNNING"
  | "SUCCEEDED"
  | "PARTIAL"
  | "FAILED"
  | "CANCELLED"
  | "LOST";

export type OperationsJobResultStatus =
  | "NOT_RUN"
  | "PASSED"
  | "PARTIAL"
  | "FAILED"
  | "BLOCKED";

export type OperationsJobView = {
  jobId: string;
  organizationId: string;
  actorId: string;
  businessLine: OperationsJobBusinessLine;
  jobKind: string;
  status: OperationsJobStatus;
  stage: string;
  progress: number;
  resultStatus: OperationsJobResultStatus;
  failureCode: string | null;
  attempt: number;
  maxAttempts: number;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  cancelRequested: boolean;
  stateVersion: number;
};

export type OperationsJobListView = {
  schemaVersion: "1.0.0";
  items: OperationsJobView[];
  limit: number;
  scanned: number;
  scanTruncated: boolean;
  businessLine: OperationsJobBusinessLine | null;
  status: OperationsJobStatus | null;
};

export type OperationsJobCancellationView = {
  schemaVersion: "1.0.0";
  jobId: string;
  status: OperationsJobStatus;
  cancelRequested: true;
  idempotentReplay: boolean;
};

export type RunnerFleetStatus =
  | "REGISTERED"
  | "READY"
  | "DRAINING"
  | "QUARANTINED"
  | "LOST"
  | "RETIRED";

/**
 * Secret-free runner projection exposed to tenant administrators.
 *
 * Credential identifiers, enrollment/node tokens, token hashes, raw
 * attestation payloads, and verifier identities are intentionally absent.
 */
export type RunnerFleetNodeView = {
  runnerNodeId: string;
  runnerPoolId: string;
  agentVersion: string;
  fleetStatus: RunnerFleetStatus;
  capabilities: string[];
  maxConcurrency: number;
  attestationVerified: boolean;
  attestationVerifiedAt: string | null;
  imageAllowlistVersion: string;
  lastHeartbeatAt: string | null;
  drainRequestedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type RunnerFleetListView = {
  schemaVersion: "1.0.0";
  items: RunnerFleetNodeView[];
  limit: number;
  returned: number;
  truncated: boolean;
  status: RunnerFleetStatus | null;
};

export type RunnerFleetMutationView = {
  runnerNodeId: string;
  status: "DRAINING" | "READY";
};

/**
 * One section of a run replay.
 *
 * `truncated` is not decoration. The store reads one row past its cap and sets
 * this rather than quietly returning a short list, so anything rendering a
 * section must say so when it is true -- a replay that looks complete but is
 * missing the attempt where the run failed is worse than one that admits it.
 */
export type ReplaySection<T> = {
  rows: T[];
  truncated: boolean;
};

/** One attempt at one step. Attempts are not collapsed: a run that succeeded on its third try is a different story from one that succeeded on its first. */
export type ReplayStepAttempt = {
  stepRunId: string;
  stepId: string;
  attempt: number;
  executorType: string;
  state: string;
  startedAt?: string;
  finishedAt?: string;
  failureCode?: string;
};

export type ReplayEvidenceRef = {
  evidenceId: string;
  stepRunId?: string;
  evidenceType: string;
  producerType: string;
  producerName: string;
  producerVersion: string;
  status: string;
  summary: string;
  artifactRef: string;
  contentHash: string;
  createdAt?: string;
};

export type ReplayAuditEntry = {
  auditId: string;
  actorType: string;
  actorId: string;
  action: string;
  resourceType: string;
  occurredAt?: string;
  policyDecision: string;
  result: string;
  requestId: string;
};

/** The reconstructed history of one migration run. Read-only by construction: there is no write endpoint behind it. */
export type RunReplayTimeline = {
  migrationRunId: string;
  organizationId: string;
  snapshotId: string;
  migrationPlanId: string;
  planVersion: number;
  state: string;
  steps: ReplaySection<ReplayStepAttempt>;
  evidence: ReplaySection<ReplayEvidenceRef>;
  audit: ReplaySection<ReplayAuditEntry>;
};

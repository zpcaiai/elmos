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
  persistence: "POSTGRES_APPEND_ONLY";
  externalEvidence: "NOT_RUN";
};

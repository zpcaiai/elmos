export type SmokeExecutionLocation = "HOSTED_RUNNER" | "LOCAL_WORKSTATION";

export type SmokeEntry = "script" | "compose" | "make" | "zero-dep";

export type SmokeLocationStatus = "AVAILABLE" | "NOT_CONFIGURED" | "BLOCKED";

export type SmokeSessionState =
  | "STARTING"
  | "RUNNING"
  | "READY"
  | "HOLDING"
  | "COMPLETED"
  | "EXPIRED"
  | "FAILED"
  | "NOT_RUN";

export type SmokeCheckStatus = "PASS" | "FAIL" | "NOT_RUN";

export type SmokeCapabilityLocation = {
  location: SmokeExecutionLocation;
  status: SmokeLocationStatus;
  reason?: string;
};

export type SmokeCapabilityResponse = {
  freeQuotaSeconds: number;
  graceSeconds: number;
  autoRenew: false;
  extendPolicy: "EXPLICIT_ONLY";
  locations: SmokeCapabilityLocation[];
  preferredLocation: SmokeExecutionLocation | null;
  checkedAt: string;
};

export type SmokeEntryAvailability = {
  entry: SmokeEntry;
  status: "available" | "unavailable";
  command?: string;
  reason?: string;
  semanticWarning?: string;
};

export type SmokePackSummary = {
  projectRef: string;
  languages: string[];
  frameworks: string[];
  datastores: string[];
  entries: SmokeEntryAvailability[];
  defaultEntry: SmokeEntry | null;
  unknownCount: number;
};

export type SmokeCheckResult = {
  id: string;
  status: SmokeCheckStatus;
  detail: string;
  required: boolean;
};

export type SmokeTeardownReport = {
  reason: string;
  stoppedAt?: string;
  processes: { pid: number; graceful?: boolean; killed?: boolean; exitCode?: number | null }[];
  compose: { composeFile: string; status: string; reason?: string }[];
  removedPaths: { path: string; removed: string }[];
  complete: boolean;
};

export type SmokeSession = {
  sessionId: string;
  projectRef: string;
  entry: SmokeEntry;
  location: SmokeExecutionLocation;
  state: SmokeSessionState;
  url: string | null;
  createdAt: string;
  updatedAt: string;
  freeQuotaSeconds: number;
  ttlSeconds: number;
  billableSeconds: number;
  remainingSeconds: number;
  expiresAtEpoch: number | null;
  checks: SmokeCheckResult[];
  notes: string[];
  extensions: { grantedAt: string; seconds: number; reason: string; actor: string; beyondFreeQuota: boolean }[];
  teardown: SmokeTeardownReport | null;
  gateStatus: "runnable" | "limited" | "blocked" | "NOT_RUN";
  gateFailures: string[];
  gateLimitations: string[];
  evidenceAvailable: boolean;
  blockedReason?: string;
};

export type SmokeEvidenceBundle = {
  sessionId: string;
  result: unknown | null;
  gate: unknown | null;
  lease: unknown | null;
  logs: { name: string; bytes: number; tail: string }[];
  retainedAfterExpiry: true;
};

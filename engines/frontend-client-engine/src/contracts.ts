export type JobStatus = "ACCEPTED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export type FrontendErrorCode =
  | "FRONTEND_WORKSPACE_NOT_FOUND"
  | "FRONTEND_PACKAGE_MANAGER_UNRESOLVED"
  | "FRONTEND_INSTALL_FAILED"
  | "FRONTEND_BUILD_FAILED"
  | "FRONTEND_DEV_SERVER_FAILED"
  | "FRONTEND_ROUTE_DISCOVERY_FAILED"
  | "BROWSER_LAUNCH_FAILED"
  | "DESKTOP_RUNNER_REQUIRED"
  | "MOBILE_RUNNER_REQUIRED"
  | "VISUAL_ENVIRONMENT_UNSTABLE"
  | "ACCESSIBILITY_PROFILE_MISSING"
  | "FRONTEND_PLAN_BLOCKED"
  | "FRONTEND_PROJECT_GENERATION_REJECTED"
  | "RUNNER_NOT_CONFIGURED"
  | "IDEMPOTENCY_CONFLICT"
  | "JOB_NOT_FOUND"
  | "JOB_TERMINAL";

export interface EngineProblem {
  readonly errorCode: FrontendErrorCode;
  readonly message: string;
  readonly retryable: boolean;
}

export interface EngineJobRequest {
  readonly organizationId: string;
  readonly snapshotId: string;
  readonly idempotencyKey: string;
  readonly workspaceRef: string;
  readonly input?: Readonly<Record<string, unknown>>;
}

export interface ExecuteStepRequest extends EngineJobRequest {
  readonly planId: string;
  readonly stepId: string;
  readonly runnerProfile: string;
}

export interface JobResponse {
  readonly schemaVersion: "1.0";
  readonly jobId: string;
  readonly status: JobStatus;
  readonly evidenceRefs: readonly string[];
  readonly result: Readonly<Record<string, unknown>>;
  readonly error?: EngineProblem;
}

export interface Capabilities {
  readonly schemaVersion: "1.0";
  readonly engine: "ELMOS_FRONTEND_CLIENT";
  readonly engineVersion: "1.2.0";
  readonly languages: readonly string[];
  readonly webFrameworks: readonly string[];
  readonly desktopFrameworks: readonly string[];
  readonly mobileFrameworks: readonly string[];
  readonly runnerProfiles: Readonly<Record<string, "NOT_CONFIGURED">>;
  readonly staticAnalysis: "READY";
  readonly customerCodeExecution: "RUNNER_REQUIRED_FAIL_CLOSED";
  readonly jobStatePersistence: "EPHEMERAL_PROCESS_LOCAL";
  readonly durableStateAuthority: "ELMOS_CONTROL_PLANE";
  readonly restartRecovery: "NOT_SUPPORTED_BY_WORKER";
  readonly uiProjectGeneration: "STATIC_PROJECT_AND_CONFIGURATION_READY";
  readonly directedUiRouteCount: 72;
  readonly frtPlatform: "G01_G30_DURABLE_RUNTIME_READY_EXTERNAL_GATES_NOT_RUN";
  readonly frtRunPersistence: "FILESYSTEM_ATOMIC_TENANT_SCOPED";
  readonly frtRestartRecovery: "RUNNING_FAILS_CLOSED_QUEUED_RETAINED";
  readonly frtBatchCount: 30;
  readonly frtSkillCount: 472;
  readonly frtDirectedRouteCount: 30;
}

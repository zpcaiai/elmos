export type FrtAction = "PLAN" | "ANALYZE" | "EXECUTE" | "VERIFY";

export type FrtRunState = "QUEUED" | "RUNNING" | "SUCCEEDED" | "BLOCKED" | "FAILED" | "CANCELLED";

export type FrtEvidenceState = "PASSED" | "FAILED" | "INCONCLUSIVE" | "NOT_RUN";

export interface FrtExecutionScope {
  readonly organizationId: string;
  readonly tenantId: string;
  readonly workspaceId: string;
  readonly projectId: string;
  readonly accountId: string;
  readonly environmentId: string;
  readonly releaseId: string;
}

export interface FrtExecutionContext extends FrtExecutionScope {
  readonly sourceSnapshotDigest: string;
  readonly policyVersion: string;
  readonly requestedBy: string;
  readonly risk: "R0" | "R1" | "R2" | "R3" | "R4" | "R5";
}

export interface FrtPrerequisiteCertificate {
  readonly batch: string;
  readonly state: "ACTIVE" | "STALE" | "REVOKED" | "RETEST_REQUIRED";
  readonly scope: FrtExecutionScope;
  readonly artifactDigest: string;
  readonly evidenceRefs: readonly string[];
  readonly authority: string;
  readonly keyId: string;
  readonly issuedAt: string;
  readonly expiresAt: string;
  readonly signature: string;
}

export interface FrtEvidenceReference {
  readonly role: string;
  readonly uri: string;
  readonly digest: string;
  readonly state: FrtEvidenceState;
  readonly executor: string;
  readonly verifier: string;
  readonly synthetic: boolean;
  readonly byteCount: number;
  readonly authority: string;
  readonly keyId: string;
  readonly issuedAt: string;
  readonly expiresAt: string;
  readonly signature: string;
}

export interface FrtSkillRunRequest {
  readonly schemaVersion: "1.0";
  readonly skillId: string;
  readonly action: FrtAction;
  readonly idempotencyKey: string;
  readonly expectedVersion: number;
  readonly context: FrtExecutionContext;
  readonly prerequisiteCertificates: readonly FrtPrerequisiteCertificate[];
  readonly evidence: readonly FrtEvidenceReference[];
  readonly input?: Readonly<Record<string, unknown>>;
}

export interface FrtFinding {
  readonly code: string;
  readonly severity: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  readonly message: string;
  readonly owner: string;
  readonly blocking: boolean;
}

/**
 * A time-bounded right to execute one claimed run. A lease is the only thing that
 * makes a RUNNING run legitimate: once it expires the run is reclaimed, so a runner
 * that dies silently can never leave a run stuck in RUNNING forever.
 */
export interface FrtRunLease {
  readonly runnerId: string;
  readonly claimedAt: string;
  readonly expiresAt: string;
  readonly heartbeatCount: number;
}

export type FrtRunnerExitStatus = "COMPLETED" | "FAILED";

export interface FrtRunnerArtifactReference {
  readonly name: string;
  readonly uri: string;
  readonly digest: string;
  readonly byteCount: number;
}

/**
 * A runner's signed report of what it actually executed outside this control plane.
 * The attestation is verified against the RUNNER trust purpose before any field is
 * trusted; an unverified completion can never mark customer code or a production
 * operation as executed.
 */
export interface FrtRunnerCompletion {
  readonly schemaVersion: "1.0";
  readonly runnerId: string;
  readonly exitStatus: FrtRunnerExitStatus;
  readonly startedAt: string;
  readonly finishedAt: string;
  readonly customerCodeExecuted: boolean;
  readonly productionOperationExecuted: boolean;
  readonly artifacts: readonly FrtRunnerArtifactReference[];
  readonly evidence: readonly FrtEvidenceReference[];
  readonly authority: string;
  readonly keyId: string;
  readonly issuedAt: string;
  readonly expiresAt: string;
  readonly signature: string;
}

export interface FrtCertificateFragment {
  readonly batch: string;
  readonly family: string;
  readonly eligibleForBatchGate: boolean;
  readonly certification: "NOT_CERTIFIED";
  readonly externalAuthorityRequired: true;
  readonly evidenceRefs: readonly string[];
}

export interface FrtSkillRunResult {
  readonly schemaVersion: "1.0";
  readonly runId: string;
  readonly version: number;
  readonly skillId: string;
  readonly skillName: string;
  readonly batch: string;
  readonly action: FrtAction;
  readonly state: FrtRunState;
  readonly outcome:
    | "PLAN_READY"
    | "STATIC_ANALYSIS_COMPLETE"
    | "PROPOSAL_READY_FOR_RUNNER"
    | "READY_FOR_BATCH_GATE"
    | "BLOCKED_BY_PREREQUISITE"
    | "BLOCKED_BY_EVIDENCE"
    | "BLOCKED_BY_UNSUPPORTED_SEMANTICS"
    | "BLOCKED_BY_RUNNER_RECOVERY"
    | "RUNNER_EXECUTION_RECORDED"
    | "RUNNER_EXECUTION_FAILED"
    | "BLOCKED_BY_RUNNER_ATTESTATION"
    | "BLOCKED_BY_RUNNER_EVIDENCE"
    | "BLOCKED_BY_LEASE_EXPIRED"
    | "REQUEST_REJECTED"
    | "CANCELLED";
  readonly inputDigest: string;
  readonly resultDigest: string;
  readonly requiredEvidenceRoles: readonly string[];
  readonly obligations: readonly string[];
  readonly findings: readonly FrtFinding[];
  readonly evidence: readonly FrtEvidenceReference[];
  readonly artifacts: Readonly<Record<string, unknown>>;
  /** Non-null only while the run is RUNNING under a live runner lease. */
  readonly lease: FrtRunLease | null;
  readonly certificateFragment: FrtCertificateFragment;
  /**
   * Stays false until a trust-store-verified runner attestation reports that the
   * runner really executed customer code. This control plane never sets it itself.
   */
  readonly customerCodeExecuted: boolean;
  /**
   * Stays false until a trust-store-verified runner attestation reports a real
   * production operation. This control plane never sets it itself.
   */
  readonly productionOperationExecuted: boolean;
}

export interface FrtBatchPlanRequest {
  readonly schemaVersion: "1.0";
  readonly batch: string;
  readonly idempotencyKey: string;
  readonly expectedVersion: number;
  readonly context: FrtExecutionContext;
  readonly prerequisiteCertificates: readonly FrtPrerequisiteCertificate[];
}

export interface FrtRunTransitionRequest {
  readonly schemaVersion: "1.0";
  readonly expectedVersion: number;
}

export interface FrtRunCompletionRequest {
  readonly schemaVersion: "1.0";
  readonly expectedVersion: number;
  readonly completion: FrtRunnerCompletion;
}

export interface FrtBatchPlan {
  readonly schemaVersion: "1.0";
  readonly planId: string;
  readonly batch: string;
  readonly dependsOn: string | null;
  readonly state: "READY" | "BLOCKED";
  readonly skillIds: readonly string[];
  readonly stages: readonly {
    readonly skillId: string;
    readonly dependsOn: readonly string[];
    readonly action: "PLAN";
  }[];
  readonly findings: readonly FrtFinding[];
  readonly productionCertification: "NOT_CERTIFIED";
}

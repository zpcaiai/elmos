import { createHash } from "node:crypto";

import { buildUiSemanticGraph, discoverWorkspace } from "./analyzer.js";
import { frtCatalog } from "./frt-catalog.generated.js";
import { frtHandlerRegistry } from "./frt-handler-registry.generated.js";
import {
  validateFrtBatchPlanRequest,
  validateFrtRunnerCompletion,
  validateFrtSkillRunRequest,
} from "./frt-contract-validation.js";
import {
  frtSecurityFromEnvironment,
  prerequisiteCertificatePayload,
  runnerCompletionPayload,
  validateResolvedEvidence,
  type FrtSecurityContext,
} from "./frt-security.js";
import {
  frtRunStoreFromEnvironment,
  type FrtAuditEvent,
  type FrtRunStore,
} from "./frt-run-store.js";
import type {
  FrtBatchPlan,
  FrtBatchPlanRequest,
  FrtCertificateFragment,
  FrtEvidenceReference,
  FrtExecutionContext,
  FrtExecutionScope,
  FrtFinding,
  FrtPrerequisiteCertificate,
  FrtRunLease,
  FrtRunnerCompletion,
  FrtSkillRunRequest,
  FrtSkillRunResult,
} from "./frt-types.js";
import { planFrontendMigration } from "./planner.js";
import type { TargetProfile, WorkspaceInventory } from "./domain.js";
import {
  convertDirectionalRoute,
  type FrtRouteTypedGap,
  type FrtRouteStack,
} from "./directional-route.js";
import { convertVue3ToReact } from "./vue3-react-route.js";
import {
  frtArtifactStoreFromEnvironment,
  type FrtArtifactStore,
} from "./frt-artifact-store.js";
import { executeFrtSemanticHandler } from "./frt-semantic-handlers.js";

type FrtSkill = (typeof frtCatalog.skills)[number];
type FrtBatch = (typeof frtCatalog.batches)[number];
type FrtHandlerDescriptor = (typeof frtHandlerRegistry)[number];

const sha256 = /^sha256:[a-f0-9]{64}$/;
const safeId = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$/;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value)).digest("hex")}`;
}

function requireSafeText(value: unknown, name: string): asserts value is string {
  if (typeof value !== "string" || !safeId.test(value)) throw new Error(`${name} is invalid`);
}

function validateScope(scope: FrtExecutionScope): void {
  requireSafeText(scope.organizationId, "organizationId");
  requireSafeText(scope.tenantId, "tenantId");
  requireSafeText(scope.workspaceId, "workspaceId");
  requireSafeText(scope.projectId, "projectId");
  requireSafeText(scope.accountId, "accountId");
  requireSafeText(scope.environmentId, "environmentId");
  requireSafeText(scope.releaseId, "releaseId");
}

function sameScope(left: FrtExecutionScope, right: FrtExecutionScope): boolean {
  return left.organizationId === right.organizationId
    && left.tenantId === right.tenantId
    && left.workspaceId === right.workspaceId
    && left.projectId === right.projectId
    && left.accountId === right.accountId
    && left.environmentId === right.environmentId
    && left.releaseId === right.releaseId;
}

function finding(
  code: string,
  severity: FrtFinding["severity"],
  message: string,
  owner: string,
  blocking: boolean,
): FrtFinding {
  return { code, severity, message, owner, blocking };
}

function skillByKey(key: string): FrtSkill | undefined {
  const normalized = key.trim().toLocaleLowerCase("en-US");
  return frtCatalog.skills.find(skill =>
    skill.id.toLocaleLowerCase("en-US") === normalized
      || skill.name.toLocaleLowerCase("en-US") === normalized,
  );
}

function batchByKey(key: string): FrtBatch | undefined {
  const normalized = key.trim().toLocaleUpperCase("en-US");
  return frtCatalog.batches.find(batch => batch.id === normalized);
}

function handlerBySkillId(skillId: string): FrtHandlerDescriptor {
  const handler = frtHandlerRegistry.find(item => item.skillId === skillId);
  if (!handler) throw new Error(`No registered semantic handler exists for ${skillId}`);
  return handler;
}

function validateContext(context: FrtExecutionContext): void {
  validateScope(context);
  if (!sha256.test(context.sourceSnapshotDigest)) throw new Error("sourceSnapshotDigest is invalid");
  requireSafeText(context.policyVersion, "policyVersion");
  requireSafeText(context.requestedBy, "requestedBy");
  if (!["R0", "R1", "R2", "R3", "R4", "R5"].includes(context.risk)) {
    throw new Error("risk is invalid");
  }
}

function prerequisiteFindings(
  skill: FrtSkill,
  context: FrtExecutionContext,
  certificates: readonly FrtPrerequisiteCertificate[],
  security: FrtSecurityContext,
): FrtFinding[] {
  if (skill.requiresCertificate === null) return [];
  const certificate = certificates.find(item => item.batch === skill.requiresCertificate);
  if (!certificate) {
    return [finding(
      "FRT_PREREQUISITE_CERTIFICATE_MISSING",
      "CRITICAL",
      `${skill.id} requires an active ${skill.requiresCertificate} certificate for the exact scope.`,
      "batch-orchestrator",
      true,
    )];
  }
  const findings: FrtFinding[] = [];
  if (certificate.state !== "ACTIVE") {
    findings.push(finding(
      "FRT_PREREQUISITE_CERTIFICATE_INACTIVE",
      "CRITICAL",
      `${certificate.batch} certificate state is ${certificate.state}.`,
      "certificate-authority",
      true,
    ));
  }
  if (!sameScope(context, certificate.scope)) {
    findings.push(finding(
      "FRT_PREREQUISITE_SCOPE_MISMATCH",
      "CRITICAL",
      `${certificate.batch} certificate does not cover the requested tenant, workspace, project, environment, release, and account scope.`,
      "certificate-authority",
      true,
    ));
  }
  let certificateVerified = true;
  try {
    security.trustStore.verify(
      "CERTIFICATE",
      certificate.authority,
      certificate.keyId,
      certificate.issuedAt,
      certificate.expiresAt,
      prerequisiteCertificatePayload(certificate),
      certificate.signature,
      security.now(),
    );
  } catch {
    certificateVerified = false;
  }
  if (security.trustStore.isRecordRevoked(certificate.artifactDigest)) {
    findings.push(finding(
      "FRT_PREREQUISITE_RECORD_REVOKED",
      "CRITICAL",
      `${certificate.batch} certificate record ${certificate.artifactDigest} has been revoked.`,
      "certificate-authority",
      true,
    ));
  }
  if (!certificateVerified || certificate.evidenceRefs.length === 0
      || !sha256.test(certificate.artifactDigest)) {
    findings.push(finding(
      "FRT_PREREQUISITE_UNVERIFIED",
      "CRITICAL",
      `${certificate.batch} certificate lacks a trusted signature, evidence, or a content digest.`,
      "control-plane",
      true,
    ));
  }
  return findings;
}

function requiredEvidenceRoles(skill: FrtSkill): readonly string[] {
  const batch = Number.parseInt(skill.batch.slice(1), 10);
  const base = ["CONTRACT_VALIDATION", "SOURCE_LINEAGE", "INDEPENDENT_VERIFICATION"];
  if (batch <= 3) return [...base, "SCHEMA_VALIDATION", "NEGATIVE_TEST"];
  if (batch <= 7) return [...base, "SOURCE_BUILD", "TARGET_BUILD", "TYPECHECK", "NEGATIVE_TEST"];
  if (batch <= 12) return [...base, "SOURCE_RUNTIME", "TARGET_RUNTIME", "JOURNEY", "ACCESSIBILITY"];
  if (batch <= 17) return [...base, "SOURCE_BUILD", "TARGET_BUILD", "BROWSER_OR_DEVICE_JOURNEY", "HOLDOUT_CORPUS"];
  if (batch === 18) return [...base, "PACK_SIGNATURE", "PACK_CONFORMANCE", "CONFLICT_RESOLUTION"];
  if (batch === 19) return [...base, "PROOF_KERNEL", "COUNTEREXAMPLE_REPLAY", "HOLDOUT_CORPUS"];
  if (batch === 20) return [...base, "DURABLE_RUNTIME", "TENANT_ISOLATION", "SECURITY_TEST", "OPERATOR_JOURNEY"];
  if (batch <= 26) return [...base, "USER_JOURNEY", "ADMIN_JOURNEY", "HOLDOUT_CORPUS", "REPRESENTATIVE_JOURNEY"];
  if (batch === 27) return [...base, "PERFORMANCE_RUN", "CONCURRENCY_RUN", "CAPACITY_RUN", "DEGRADATION_TEST"];
  if (batch === 28) return [...base, "CHAOS_RUN", "FAILOVER_RUN", "RESTORE_RUN", "DR_EXERCISE"];
  if (batch === 29) return [...base, "PENETRATION_TEST", "PRIVACY_REVIEW", "SUPPLY_CHAIN_ATTESTATION", "INCIDENT_DRILL"];
  return [...base, "PRODUCTION_OBSERVATION", "CANARY_OBSERVATION", "ROLLBACK_DRILL", "ON_CALL_REVIEW", "CUSTOMER_OUTCOME"];
}

function skillObligations(skill: FrtSkill): readonly string[] {
  const obligations = new Set<string>([
    "PRESERVE_SOURCE_READ_ONLY",
    "ENFORCE_EXACT_TENANT_AND_RESOURCE_SCOPE",
    "BIND_INPUT_OUTPUT_AND_EVIDENCE_DIGESTS",
    "KEEP_UNKNOWN_AND_UNSUPPORTED_SEMANTICS_EXPLICIT",
    "REQUIRE_INDEPENDENT_GATE_FOR_CERTIFICATION",
  ]);
  const batch = Number.parseInt(skill.batch.slice(1), 10);
  if (batch >= 3 && batch <= 19) obligations.add("TRANSFORM_THROUGH_TYPED_SEMANTIC_IR");
  if (batch >= 4 && batch <= 17) obligations.add("USE_EXACT_DIRECTIONAL_SOURCE_AND_TARGET_PROFILES");
  if (skill.route !== null) {
    obligations.add(`ROUTE_${skill.route.source.toLocaleUpperCase("en-US").replaceAll(" ", "_")}_TO_${skill.route.target.toLocaleUpperCase("en-US").replaceAll(" ", "_")}`);
    obligations.add("RUN_REAL_SOURCE_AND_TARGET_APPLICATIONS");
  }
  if (batch >= 19) obligations.add("MODELS_MAY_PROPOSE_BUT_MAY_NOT_CERTIFY");
  if (batch >= 21) obligations.add("REQUIRE_REPRESENTATIVE_BUSINESS_AND_ADMIN_JOURNEYS");
  if (batch >= 27) obligations.add("REQUIRE_AUTHORIZED_EXTERNAL_OR_PRODUCTION_EQUIVALENT_EXECUTION");
  if (batch >= 29) obligations.add("ZERO_TOLERANCE_FOR_CRITICAL_SECURITY_OR_PRIVACY_FINDINGS");
  if (batch === 30) obligations.add("PRODUCTION_AUTHORITY_REMAINS_EXTERNAL");
  return [...obligations];
}

function validateEvidence(
  requiredRoles: readonly string[],
  evidence: readonly FrtEvidenceReference[],
  security: FrtSecurityContext,
): FrtFinding[] {
  const findings: FrtFinding[] = [];
  const duplicateRoles = evidence
    .map(item => item.role)
    .filter((role, index, roles) => roles.indexOf(role) !== index);
  for (const role of new Set(duplicateRoles)) {
    findings.push(finding(
      "FRT_EVIDENCE_ROLE_DUPLICATED",
      "CRITICAL",
      `${role} evidence was supplied more than once.`,
      "evidence-owner",
      true,
    ));
  }
  const byRole = new Map(evidence.map(item => [item.role, item]));
  for (const role of requiredRoles) {
    const item = byRole.get(role);
    if (!item || item.state === "NOT_RUN") {
      findings.push(finding(
        "FRT_EVIDENCE_NOT_RUN",
        "ERROR",
        `${role} evidence is NOT_RUN.`,
        "evidence-owner",
        true,
      ));
      continue;
    }
    if (item.state !== "PASSED") {
      findings.push(finding(
        "FRT_EVIDENCE_NON_PASSING",
        item.state === "FAILED" ? "CRITICAL" : "ERROR",
        `${role} evidence state is ${item.state}.`,
        "evidence-owner",
        true,
      ));
    }
    if (!sha256.test(item.digest) || !item.uri.trim()) {
      findings.push(finding(
        "FRT_EVIDENCE_INTEGRITY_INVALID",
        "CRITICAL",
        `${role} evidence lacks an immutable digest or URI.`,
        "evidence-owner",
        true,
      ));
    }
    if (item.synthetic) {
      findings.push(finding(
        "FRT_SYNTHETIC_EVIDENCE_NON_AUTHORITATIVE",
        "ERROR",
        `${role} evidence is synthetic and cannot support a real gate.`,
        "evidence-owner",
        true,
      ));
    }
    if (!item.executor.trim() || !item.verifier.trim() || item.executor === item.verifier) {
      findings.push(finding(
        "FRT_INDEPENDENT_VERIFIER_MISSING",
        "CRITICAL",
        `${role} requires distinct accountable executor and verifier identities.`,
        "evidence-owner",
        true,
      ));
    }
    try {
      validateResolvedEvidence(item, security);
    } catch {
      findings.push(finding(
        "FRT_EVIDENCE_ATTESTATION_INVALID",
        "CRITICAL",
        `${role} evidence could not be resolved and verified against a trusted content-addressed attestation.`,
        "evidence-owner",
        true,
      ));
    }
  }
  return findings;
}

function runnerArtifactFindings(completion: FrtRunnerCompletion): FrtFinding[] {
  const findings: FrtFinding[] = [];
  const names = completion.artifacts.map(item => item.name);
  for (const name of new Set(names.filter((item, index) => names.indexOf(item) !== index))) {
    findings.push(finding(
      "FRT_RUNNER_ARTIFACT_NAME_DUPLICATED",
      "ERROR",
      `The runner reported more than one artifact named ${name}.`,
      "runner-owner",
      true,
    ));
  }
  for (const artifact of completion.artifacts) {
    if (!sha256.test(artifact.digest) || !artifact.uri.trim() || artifact.byteCount <= 0) {
      findings.push(finding(
        "FRT_RUNNER_ARTIFACT_INTEGRITY_INVALID",
        "CRITICAL",
        `Artifact ${artifact.name} lacks an immutable digest, a URI or a non-empty byte count.`,
        "runner-owner",
        true,
      ));
    }
  }
  return findings;
}

function runnerEvidenceFindings(
  completion: FrtRunnerCompletion,
  security: FrtSecurityContext,
): FrtFinding[] {
  const findings: FrtFinding[] = [];
  const roles = completion.evidence.map(item => item.role);
  for (const role of new Set(roles.filter((item, index) => roles.indexOf(item) !== index))) {
    findings.push(finding(
      "FRT_EVIDENCE_ROLE_DUPLICATED",
      "CRITICAL",
      `${role} evidence was reported more than once by the runner.`,
      "runner-owner",
      true,
    ));
  }
  for (const item of completion.evidence) {
    if (item.executor !== completion.runnerId) {
      findings.push(finding(
        "FRT_RUNNER_EVIDENCE_EXECUTOR_MISMATCH",
        "CRITICAL",
        `${item.role} evidence names ${item.executor} as executor but was reported by runner ${completion.runnerId}.`,
        "runner-owner",
        true,
      ));
    }
    if (item.verifier === item.executor || item.verifier === completion.runnerId) {
      findings.push(finding(
        "FRT_INDEPENDENT_VERIFIER_MISSING",
        "CRITICAL",
        `${item.role} evidence cannot be verified by the runner that produced it.`,
        "runner-owner",
        true,
      ));
    }
    // Names are cheap to fake; keys are not. The trust store already forbids one key from
    // both executing and attesting, and this is the second, per-record line of defence.
    if (item.keyId === completion.keyId) {
      findings.push(finding(
        "FRT_EVIDENCE_KEY_NOT_INDEPENDENT",
        "CRITICAL",
        `${item.role} evidence is signed with the same key that attested the runner's own execution.`,
        "runner-owner",
        true,
      ));
    }
    if (security.trustStore.isRecordRevoked(item.digest)) {
      findings.push(finding(
        "FRT_EVIDENCE_RECORD_REVOKED",
        "CRITICAL",
        `${item.role} evidence record ${item.digest} has been revoked.`,
        "evidence-owner",
        true,
      ));
    }
    if (item.synthetic) {
      findings.push(finding(
        "FRT_SYNTHETIC_EVIDENCE_NON_AUTHORITATIVE",
        "ERROR",
        `${item.role} evidence is synthetic and cannot support a real gate.`,
        "runner-owner",
        true,
      ));
    }
    try {
      validateResolvedEvidence(item, security);
    } catch {
      findings.push(finding(
        "FRT_EVIDENCE_ATTESTATION_INVALID",
        "CRITICAL",
        `${item.role} evidence could not be resolved and verified against a trusted content-addressed attestation.`,
        "runner-owner",
        true,
      ));
    }
  }
  return findings;
}

/**
 * The artifact store keys objects by digest and only accepts a flat, slash-free name, so a
 * generated path becomes a safe store name here while the caller-visible reference keeps the
 * original relative path.
 */
function artifactNameFor(relativePath: string): string {
  const sanitized = relativePath.replace(/[^A-Za-z0-9._-]/g, "-").replace(/^[^A-Za-z0-9]+/, "");
  return (sanitized || "artifact").slice(0, 128);
}

/**
 * Writes a generated target workspace into the artifact store. Nothing is materialised when
 * the store is unconfigured; the caller surfaces that as a non-blocking finding rather than
 * pretending the bytes landed somewhere.
 */
function materializeRoute(
  skillId: string,
  generatedFiles: Readonly<Record<string, string>>,
  store: FrtArtifactStore,
): Readonly<Record<string, unknown>> | undefined {
  if (!store.configured) return undefined;
  const paths = Object.keys(generatedFiles).sort();
  const files = paths.map(path => {
    const reference = store.put(
      artifactNameFor(`${skillId}-${path}`),
      Buffer.from(generatedFiles[path]!, "utf8"),
    );
    // Keep the caller-visible name as the path inside the generated workspace.
    return { ...reference, name: path };
  });
  const bundle = store.put(
    artifactNameFor(`${skillId}-target-workspace`),
    Buffer.from(canonical(Object.fromEntries(paths.map(path => [path, generatedFiles[path]!]))), "utf8"),
  );
  return { bundle, files };
}

function routeMaterialization(
  skillId: string,
  migration: { readonly status: string; readonly generatedFiles: Readonly<Record<string, string>> },
  store: FrtArtifactStore,
): Readonly<Record<string, unknown>> {
  if (migration.status !== "GENERATED") return {};
  const materialized = materializeRoute(skillId, migration.generatedFiles, store);
  if (materialized) return { materializedArtifacts: materialized };
  return {
    materializationFindings: [finding(
      "FRT_ARTIFACT_STORE_NOT_CONFIGURED",
      "WARNING",
      "No artifact store is configured, so the generated target workspace was not persisted; set ELMOS_FRT_ARTIFACT_ROOT to retain it.",
      "platform-owner",
      false,
    )],
  };
}

function asSourceFiles(input: Readonly<Record<string, unknown>> | undefined): Readonly<Record<string, string>> {
  const value = input?.files;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("input.files is required for analysis");
  }
  const files: Record<string, string> = {};
  for (const [path, content] of Object.entries(value as Record<string, unknown>)) {
    if (typeof content !== "string") throw new Error("source files must contain text only");
    files[path] = content;
  }
  return files;
}

function analysisArtifacts(
  skill: FrtSkill,
  request: FrtSkillRunRequest,
  store: FrtArtifactStore,
): Readonly<Record<string, unknown>> {
  const handler = handlerBySkillId(skill.id);
  if (["estate_discovery", "semantic_ir", "typed_contract"].includes(handler.handlerKind)) {
    const files = asSourceFiles(request.input);
    const inventory = discoverWorkspace(request.context.sourceSnapshotDigest, files);
    const graph = buildUiSemanticGraph(request.context.projectId, files);
    return {
      handler,
      inventory,
      graph,
      sourceExecuted: false,
      staticAnalysis: "PASSED",
    };
  }
  if (handler.handlerKind === "migration_planning") {
    if (!request.input?.inventory || !request.input?.target) {
      throw new Error("input.inventory and input.target are required for migration planning");
    }
    const inventory = request.input.inventory as WorkspaceInventory;
    const target = request.input.target as TargetProfile;
    const currentVersions = (request.input.currentVersions ?? {}) as Readonly<Record<string, string>>;
    return { handler, migrationPlan: planFrontendMigration(inventory, target, currentVersions) };
  }
  if (handler.handlerKind === "directional_route") {
    const route = frtCatalog.routes.find(item => item.skillId === skill.id);
    if (!route) throw new Error(`The route descriptor for ${skill.id} is missing`);
    const files = request.input?.files && typeof request.input.files === "object"
      && !Array.isArray(request.input.files) ? asSourceFiles(request.input) : {};
    if (skill.id === "FRT-1305" && files["frt-ui-ir.json"] === undefined) {
      const migration = convertVue3ToReact(
        files,
      );
      return {
        handler,
        route,
        routeMigration: migration,
        typedGaps: migration.typedGaps,
        routeRuntime: migration.status === "GENERATED"
          ? "VUE3_REACT_VERTICAL_SLICE_GENERATED"
          : "BLOCKED_BY_TYPED_GAPS",
        ...routeMaterialization(skill.id, migration, store),
      };
    }
    const migration = convertDirectionalRoute(
      route.source as FrtRouteStack,
      route.target as FrtRouteStack,
      files,
    );
    return {
      handler,
      route,
      routeMigration: migration,
      typedGaps: migration.typedGaps,
      routeRuntime: migration.status === "GENERATED"
        ? "TYPED_UI_IR_DIRECTIONAL_ROUTE_GENERATED"
        : "BLOCKED_BY_TYPED_GAPS",
      ...routeMaterialization(skill.id, migration, store),
    };
  }
  return executeFrtSemanticHandler({
    skill,
    handler,
    action: request.action,
    ...(request.input === undefined ? {} : { input: request.input }),
    routes: frtCatalog.routes,
    requiredEvidenceRoles: requiredEvidenceRoles(skill),
    obligations: skillObligations(skill),
  });
}

function certificateFragment(
  skill: FrtSkill,
  eligibleForBatchGate: boolean,
  evidence: readonly FrtEvidenceReference[],
): FrtCertificateFragment {
  return {
    batch: skill.batch,
    family: skill.certificateFamily,
    eligibleForBatchGate,
    certification: "NOT_CERTIFIED",
    externalAuthorityRequired: true,
    evidenceRefs: evidence.filter(item => item.state === "PASSED").map(item => item.uri).sort(),
  };
}

function requestFinding(error: unknown): FrtFinding {
  return finding(
    "FRT_REQUEST_REJECTED",
    "ERROR",
    error instanceof Error ? error.message : "The FRT request was rejected.",
    "request-owner",
    true,
  );
}

/**
 * Lease bounds per docs/frt-g01-g30/RUNNER_CONTRACT.md section 3 and
 * schemas/frt-g01-g30/run-lease.schema.json: default 900s, hard range [30, 86400].
 */
const defaultLeaseSeconds = 900;
const minimumLeaseSeconds = 30;
const maximumLeaseSeconds = 86_400;

function leaseSeconds(requested?: number): number {
  const configured = Number.parseInt(process.env.ELMOS_FRT_LEASE_SECONDS ?? "", 10);
  const candidate = requested ?? (Number.isInteger(configured) ? configured : defaultLeaseSeconds);
  if (!Number.isInteger(candidate)) throw new Error("leaseSeconds must be an integer");
  if (candidate < minimumLeaseSeconds || candidate > maximumLeaseSeconds) {
    throw new Error(`leaseSeconds must be within [${minimumLeaseSeconds}, ${maximumLeaseSeconds}]`);
  }
  return candidate;
}

function issueLease(runnerId: string, now: Date, seconds: number, heartbeatCount = 0): FrtRunLease {
  return {
    runnerId,
    claimedAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + seconds * 1000).toISOString(),
    heartbeatCount,
  };
}

function leaseExpired(lease: FrtRunLease, now: Date): boolean {
  const expires = Date.parse(lease.expiresAt);
  return !Number.isFinite(expires) || expires <= now.getTime();
}

export class FrtRuntime {
  readonly #security: FrtSecurityContext;
  readonly #store: FrtRunStore;
  readonly #artifacts: FrtArtifactStore;

  constructor(options: {
    readonly security?: FrtSecurityContext;
    readonly store?: FrtRunStore;
    readonly artifacts?: FrtArtifactStore;
  } = {}) {
    this.#security = options.security ?? frtSecurityFromEnvironment();
    this.#store = options.store ?? frtRunStoreFromEnvironment();
    this.#artifacts = options.artifacts ?? frtArtifactStoreFromEnvironment();
    this.#recoverInterruptedRuns();
  }

  #transitionResult(
    existing: FrtSkillRunResult,
    patch: Partial<Pick<
      FrtSkillRunResult,
      | "state"
      | "outcome"
      | "findings"
      | "evidence"
      | "artifacts"
      | "certificateFragment"
      | "customerCodeExecuted"
      | "productionOperationExecuted"
      | "lease"
    >>,
  ): FrtSkillRunResult {
    const { resultDigest: _resultDigest, ...prior } = existing;
    const unsigned = {
      ...prior,
      ...patch,
      version: existing.version + 1,
    };
    return { ...unsigned, resultDigest: digest(unsigned) };
  }

  /**
   * Reclaims RUNNING runs whose lease has expired. A RUNNING run whose lease is still
   * live is left alone, so restarting one control-plane instance does not kill a runner
   * that is executing healthily against another. Reclaiming can only ever produce
   * BLOCKED; an expired lease is never revived and never becomes success.
   */
  sweepExpiredLeases(): number {
    const now = this.#security.now();
    let reclaimed = 0;
    for (const stored of this.#store.recoverableRuns()) {
      const previous = stored.result;
      if (previous.state !== "RUNNING") continue;
      const lease = previous.lease;
      if (lease && !leaseExpired(lease, now)) continue;
      const result = this.#transitionResult(previous, {
        state: "BLOCKED",
        outcome: lease ? "BLOCKED_BY_LEASE_EXPIRED" : "BLOCKED_BY_RUNNER_RECOVERY",
        lease: null,
        findings: [
          ...previous.findings,
          lease
            ? finding(
              "FRT_RUN_LEASE_EXPIRED",
              "CRITICAL",
              `The lease held by ${lease.runnerId} expired at ${lease.expiresAt}; the run must be retried rather than resumed.`,
              "runner-owner",
              true,
            )
            : finding(
              "FRT_RUNNER_PROCESS_LOST_AFTER_RESTART",
              "CRITICAL",
              "The durable run was RUNNING without a lease when its process disappeared; automatic success is forbidden and an operator retry is required.",
              "runner-owner",
              true,
            ),
        ],
      });
      this.#store.saveRun(stored, result, {
        actor: "frt-lease-controller",
        event: lease ? "RUN_LEASE_EXPIRED" : "RUN_RECOVERY_BLOCKED",
        expectedStoredVersion: previous.version,
        now,
      });
      reclaimed += 1;
    }
    return reclaimed;
  }

  #recoverInterruptedRuns(): void {
    this.sweepExpiredLeases();
  }

  /**
   * Extends the lease on a claimed run. Holder only, never after expiry. Each renewal
   * bumps the run version, so a runner must carry the version returned here into its
   * next call.
   */
  heartbeat(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
    expectedVersion: number,
    actor: string,
    requestedLeaseSeconds?: number,
  ): FrtSkillRunResult | undefined {
    requireSafeText(actor, "actor");
    const seconds = leaseSeconds(requestedLeaseSeconds);
    const existing = this.getRun(scope, runId);
    if (!existing) return undefined;
    if (existing.version !== expectedVersion) throw new Error("run version conflict");
    if (existing.state !== "RUNNING") throw new Error("only a running run can be renewed");
    const lease = existing.lease;
    if (!lease) throw new Error("run has no active lease");
    if (lease.runnerId !== actor) throw new Error("only the lease holder can renew the lease");
    const now = this.#security.now();
    if (leaseExpired(lease, now)) throw new Error("run lease has expired");
    const renewed = this.#transitionResult(existing, {
      lease: issueLease(lease.runnerId, now, seconds, lease.heartbeatCount + 1),
    });
    this.#store.saveRun(scope, renewed, {
      actor,
      event: "RUN_HEARTBEAT",
      expectedStoredVersion: expectedVersion,
      now,
    });
    return renewed;
  }

  catalog(batch?: string, query?: string): Readonly<Record<string, unknown>> {
    const normalizedBatch = batch?.trim().toLocaleUpperCase("en-US");
    const needle = query?.trim().toLocaleLowerCase("en-US");
    const skills = frtCatalog.skills.filter(skill =>
      (!normalizedBatch || skill.batch === normalizedBatch)
      && (!needle || `${skill.id} ${skill.name} ${skill.title} ${skill.description}`.toLocaleLowerCase("en-US").includes(needle)),
    );
    return {
      schemaVersion: frtCatalog.schemaVersion,
      package: frtCatalog.package,
      packageVersion: frtCatalog.packageVersion,
      packageManifestSha256: frtCatalog.packageManifestSha256,
      sourceTreeSha256: frtCatalog.sourceTreeSha256,
      batchCount: frtCatalog.batchCount,
      skillCount: frtCatalog.skillCount,
      directedRouteCount: frtCatalog.directedRouteCount,
      returnedSkillCount: skills.length,
      batches: frtCatalog.batches,
      skills,
      evidenceBoundary: frtCatalog.evidenceBoundary,
    };
  }

  routes(): typeof frtCatalog.routes {
    return frtCatalog.routes;
  }

  skill(key: string): FrtSkill | undefined {
    return skillByKey(key);
  }

  planBatch(request: FrtBatchPlanRequest): FrtBatchPlan {
    request = validateFrtBatchPlanRequest(request);
    validateContext(request.context);
    requireSafeText(request.idempotencyKey, "idempotencyKey");
    if (!Number.isInteger(request.expectedVersion) || request.expectedVersion < 0) {
      throw new Error("expectedVersion must be a non-negative integer");
    }
    const batch = batchByKey(request.batch);
    if (!batch) throw new Error("batch is unknown");
    const firstSkill = frtCatalog.skills.find(skill => skill.batch === batch.id);
    if (!firstSkill) throw new Error("batch has no Skills");
    const findings = prerequisiteFindings(
      firstSkill,
      request.context,
      request.prerequisiteCertificates,
      this.#security,
    );
    const skillIds = frtCatalog.skills.filter(skill => skill.batch === batch.id).map(skill => skill.id);
    const planId = createHash("sha256")
      .update(canonical({ batch: batch.id, context: request.context, expectedVersion: request.expectedVersion }))
      .digest("hex")
      .slice(0, 24);
    return {
      schemaVersion: "1.0",
      planId,
      batch: batch.id,
      dependsOn: batch.dependsOn,
      state: findings.some(item => item.blocking) ? "BLOCKED" : "READY",
      skillIds,
      stages: skillIds.map((skillId, index) => ({
        skillId,
        dependsOn: index === 0 ? [] : [skillIds[index - 1]!],
        action: "PLAN",
      })),
      findings,
      productionCertification: "NOT_CERTIFIED",
    };
  }

  run(request: FrtSkillRunRequest): FrtSkillRunResult {
    let skill: FrtSkill | undefined;
    let runId = createHash("sha256").update(canonical(request)).digest("hex").slice(0, 24);
    try {
      request = validateFrtSkillRunRequest(request);
      validateContext(request.context);
      requireSafeText(request.idempotencyKey, "idempotencyKey");
      if (!Number.isInteger(request.expectedVersion) || request.expectedVersion < 0) {
        throw new Error("expectedVersion must be a non-negative integer");
      }
      skill = skillByKey(request.skillId);
      if (!skill) throw new Error("skillId is unknown");
      const idempotencyScope = `${request.context.organizationId}:${request.context.tenantId}:${skill.id}:${request.action}:${request.idempotencyKey}`;
      const fingerprint = digest(request);
      const existing = this.#store.getIdempotency(idempotencyScope);
      if (existing) {
        const prior = this.#store.getRun(request.context, existing.runId)?.result;
        if (existing.fingerprint === fingerprint && prior) return prior;
        throw new Error("idempotency key was reused with different input");
      }
      if (request.expectedVersion !== 0) {
        throw new Error("expectedVersion must be 0 for a new run");
      }
      runId = createHash("sha256").update(idempotencyScope).digest("hex").slice(0, 24);
      const prerequisites = prerequisiteFindings(
        skill,
        request.context,
        request.prerequisiteCertificates,
        this.#security,
      );
      const roles = requiredEvidenceRoles(skill);
      const obligations = skillObligations(skill);
      const handler = handlerBySkillId(skill.id);
      const inputDigest = digest(request);
      let state: FrtSkillRunResult["state"] = "SUCCEEDED";
      let outcome: FrtSkillRunResult["outcome"] = "PLAN_READY";
      let artifacts: Readonly<Record<string, unknown>> = {
        executionPlan: {
          skillId: skill.id,
          batch: skill.batch,
          action: request.action,
          sourceSnapshotDigest: request.context.sourceSnapshotDigest,
          requiredEvidenceRoles: roles,
          obligations,
          handlerKind: handler.handlerKind,
          surfaceManifestPaths: handler.surfaceManifestPaths,
        },
      };
      let findings = prerequisites;
      if (prerequisites.some(item => item.blocking)) {
        state = "BLOCKED";
        outcome = "BLOCKED_BY_PREREQUISITE";
      } else if (request.action === "ANALYZE") {
        artifacts = analysisArtifacts(skill, request, this.#artifacts);
        const handlerFindings = (artifacts.handlerFindings ?? []) as readonly FrtFinding[];
        findings = [...findings, ...handlerFindings];
        if (handlerFindings.some(item => item.blocking)) {
          state = "BLOCKED";
          outcome = "BLOCKED_BY_INPUT_CONTRACT";
        } else {
          outcome = "STATIC_ANALYSIS_COMPLETE";
        }
      } else if (request.action === "EXECUTE") {
        artifacts = analysisArtifacts(skill, request, this.#artifacts);
        const handlerFindings = (artifacts.handlerFindings ?? []) as readonly FrtFinding[];
        findings = [
          ...findings,
          ...handlerFindings,
          ...((artifacts.materializationFindings ?? []) as readonly FrtFinding[]),
        ];
        const typedGaps = (artifacts.typedGaps ?? []) as readonly FrtRouteTypedGap[];
        if (handlerFindings.some(item => item.blocking)) {
          state = "BLOCKED";
          outcome = "BLOCKED_BY_INPUT_CONTRACT";
        } else if (typedGaps.some(item => item.blocking)) {
          state = "BLOCKED";
          outcome = "BLOCKED_BY_UNSUPPORTED_SEMANTICS";
          findings = [
            ...findings,
            ...typedGaps.map(item => finding(
              item.code,
              item.severity,
              item.message,
              "route-owner",
              item.blocking,
            )),
          ];
        } else {
          state = "QUEUED";
          outcome = "PROPOSAL_READY_FOR_RUNNER";
          findings = [
            ...findings,
            finding(
              "FRT_EXTERNAL_RUNNER_REQUIRED",
              "WARNING",
              "The deterministic proposal is ready; customer code, provider, device, proof, and production execution remain outside this durable runtime.",
              "runner-owner",
              false,
            ),
          ];
        }
      } else if (request.action === "VERIFY") {
        const evidenceFindings = validateEvidence(roles, request.evidence, this.#security);
        findings = [...findings, ...evidenceFindings];
        if (evidenceFindings.some(item => item.blocking)) {
          state = "BLOCKED";
          outcome = "BLOCKED_BY_EVIDENCE";
        } else {
          outcome = "READY_FOR_BATCH_GATE";
          artifacts = {
            verificationSummary: {
              passedEvidenceRoles: roles,
              independentEvidence: true,
              certificationAuthorityInvoked: false,
            },
          };
        }
      }
      const eligible = outcome === "READY_FOR_BATCH_GATE";
      const unsigned = {
        schemaVersion: "1.0" as const,
        runId,
        version: request.expectedVersion + 1,
        skillId: skill.id,
        skillName: skill.name,
        batch: skill.batch,
        action: request.action,
        state,
        outcome,
        inputDigest,
        requiredEvidenceRoles: roles,
        obligations,
        findings,
        evidence: request.evidence,
        artifacts,
        certificateFragment: certificateFragment(skill, eligible, request.evidence),
        lease: null,
        customerCodeExecuted: false as const,
        productionOperationExecuted: false as const,
      };
      const result: FrtSkillRunResult = { ...unsigned, resultDigest: digest(unsigned) };
      this.#store.saveRun(request.context, result, {
        actor: request.context.requestedBy,
        event: "RUN_CREATED",
        expectedStoredVersion: null,
        now: this.#security.now(),
      });
      this.#store.saveIdempotency(idempotencyScope, {
        schemaVersion: "1.0",
        fingerprint,
        runId,
      });
      return result;
    } catch (error) {
      const fallbackSkill = skill ?? frtCatalog.skills[0];
      const findings = [requestFinding(error)];
      const unsigned = {
        schemaVersion: "1.0" as const,
        runId,
        version: Number.isInteger(request.expectedVersion) ? request.expectedVersion : 0,
        skillId: skill?.id ?? request.skillId,
        skillName: skill?.name ?? "unknown",
        batch: skill?.batch ?? "UNKNOWN",
        action: request.action,
        state: "FAILED" as const,
        outcome: "REQUEST_REJECTED" as const,
        inputDigest: digest(request),
        requiredEvidenceRoles: skill ? requiredEvidenceRoles(skill) : [],
        obligations: skill ? skillObligations(skill) : [],
        findings,
        evidence: request.evidence ?? [],
        artifacts: {},
        certificateFragment: certificateFragment(fallbackSkill, false, request.evidence ?? []),
        lease: null,
        customerCodeExecuted: false as const,
        productionOperationExecuted: false as const,
      };
      return { ...unsigned, resultDigest: digest(unsigned) };
    }
  }

  getRun(scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">, runId: string): FrtSkillRunResult | undefined {
    requireSafeText(scope.organizationId, "organizationId");
    requireSafeText(scope.tenantId, "tenantId");
    requireSafeText(runId, "runId");
    return this.#store.getRun(scope, runId)?.result;
  }

  audit(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
  ): readonly FrtAuditEvent[] | undefined {
    return this.#store.getRun(scope, runId)?.audit;
  }

  claim(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
    expectedVersion: number,
    actor: string,
    requestedLeaseSeconds?: number,
  ): FrtSkillRunResult | undefined {
    requireSafeText(actor, "actor");
    const seconds = leaseSeconds(requestedLeaseSeconds);
    const existing = this.getRun(scope, runId);
    if (!existing) return undefined;
    if (existing.version !== expectedVersion) throw new Error("run version conflict");
    if (existing.state !== "QUEUED") throw new Error("only a queued run can be claimed");
    const claimed = this.#transitionResult(existing, {
      state: "RUNNING",
      lease: issueLease(actor, this.#security.now(), seconds),
    });
    this.#store.saveRun(scope, claimed, {
      actor,
      event: "RUN_CLAIMED",
      expectedStoredVersion: expectedVersion,
      now: this.#security.now(),
    });
    return claimed;
  }

  cancel(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
    expectedVersion: number,
    actor: string,
  ): FrtSkillRunResult | undefined {
    const existing = this.getRun(scope, runId);
    if (!existing) return undefined;
    if (existing.version !== expectedVersion) throw new Error("run version conflict");
    if (!["QUEUED", "RUNNING"].includes(existing.state)) throw new Error("run is terminal");
    const cancelled = this.#transitionResult(existing, {
      state: "CANCELLED",
      outcome: "CANCELLED",
      lease: null,
    });
    this.#store.saveRun(scope, cancelled, {
      actor,
      event: "RUN_CANCELLED",
      expectedStoredVersion: expectedVersion,
      now: this.#security.now(),
    });
    return cancelled;
  }

  /**
   * Records what an external runner actually executed for a claimed EXECUTE run and
   * moves the run out of RUNNING. Completion is a report, never a certification: the
   * batch gate stays ineligible and the certificate family stays NOT_CERTIFIED, so a
   * separate VERIFY run with independently verified evidence remains mandatory.
   */
  complete(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
    expectedVersion: number,
    actor: string,
    completion: FrtRunnerCompletion,
  ): FrtSkillRunResult | undefined {
    requireSafeText(actor, "actor");
    const existing = this.getRun(scope, runId);
    if (!existing) return undefined;
    if (existing.version !== expectedVersion) throw new Error("run version conflict");
    if (existing.state !== "RUNNING") throw new Error("only a claimed run can be completed");
    if (existing.action !== "EXECUTE") throw new Error("only an EXECUTE run can be completed");
    // Only the lease holder may complete, and never on an expired lease: a runner that
    // stalled past its lease must let the control plane reclaim the run and be retried,
    // otherwise a hung-then-revived runner silently regains authority.
    if (!existing.lease) throw new Error("run has no active lease");
    if (existing.lease.runnerId !== actor) throw new Error("only the lease holder can complete the run");
    if (leaseExpired(existing.lease, this.#security.now())) throw new Error("run lease has expired");
    const report = validateFrtRunnerCompletion(completion);
    if (report.runnerId !== actor) throw new Error("runner identity must match the completing actor");

    const findings: FrtFinding[] = existing.findings.filter(
      item => item.code !== "FRT_EXTERNAL_RUNNER_REQUIRED",
    );
    let attested = true;
    try {
      this.#security.trustStore.verify(
        "RUNNER",
        report.authority,
        report.keyId,
        report.issuedAt,
        report.expiresAt,
        runnerCompletionPayload(report),
        report.signature,
        this.#security.now(),
      );
    } catch {
      attested = false;
    }
    const completionRecordId = digest(runnerCompletionPayload(report));
    if (attested && this.#security.trustStore.isRecordRevoked(completionRecordId)) {
      findings.push(finding(
        "FRT_RUNNER_COMPLETION_RECORD_REVOKED",
        "CRITICAL",
        `The runner completion record ${completionRecordId} has been revoked.`,
        "runner-owner",
        true,
      ));
    }
    if (!attested) {
      findings.push(finding(
        "FRT_RUNNER_ATTESTATION_INVALID",
        "CRITICAL",
        "The runner completion lacks a trusted, unexpired RUNNER attestation; the reported execution is not authoritative.",
        "runner-owner",
        true,
      ));
    } else {
      findings.push(...runnerArtifactFindings(report));
      findings.push(...runnerEvidenceFindings(report, this.#security));
    }

    const blocked = findings.some(item => item.blocking);
    const state: FrtSkillRunResult["state"] = blocked
      ? "BLOCKED"
      : report.exitStatus === "FAILED" ? "FAILED" : "SUCCEEDED";
    const outcome: FrtSkillRunResult["outcome"] = !attested
      ? "BLOCKED_BY_RUNNER_ATTESTATION"
      : blocked ? "BLOCKED_BY_RUNNER_EVIDENCE"
        : report.exitStatus === "FAILED" ? "RUNNER_EXECUTION_FAILED"
          : "RUNNER_EXECUTION_RECORDED";
    const evidence = attested ? [...existing.evidence, ...report.evidence] : existing.evidence;
    const completed = this.#transitionResult(existing, {
      state,
      outcome,
      findings,
      evidence,
      artifacts: {
        ...existing.artifacts,
        runnerCompletion: {
          runnerId: report.runnerId,
          exitStatus: report.exitStatus,
          startedAt: report.startedAt,
          finishedAt: report.finishedAt,
          attested,
          artifacts: report.artifacts,
          completionDigest: completionRecordId,
        },
      },
      certificateFragment: {
        ...existing.certificateFragment,
        // Recording an execution never makes a run gate-eligible; only a VERIFY run
        // with complete, independently verified evidence can do that.
        eligibleForBatchGate: false,
        evidenceRefs: evidence
          .filter(item => item.state === "PASSED")
          .map(item => item.uri)
          .sort(),
      },
      customerCodeExecuted: attested && report.customerCodeExecuted,
      productionOperationExecuted: attested && report.productionOperationExecuted,
      lease: null,
    });
    this.#store.saveRun(scope, completed, {
      actor,
      event: "RUN_COMPLETED",
      expectedStoredVersion: expectedVersion,
      now: this.#security.now(),
    });
    return completed;
  }

  retry(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
    expectedVersion: number,
    actor: string,
  ): FrtSkillRunResult | undefined {
    const existing = this.getRun(scope, runId);
    if (!existing) return undefined;
    if (existing.version !== expectedVersion) throw new Error("run version conflict");
    if (existing.action !== "EXECUTE" || !["BLOCKED", "FAILED", "CANCELLED"].includes(existing.state)) {
      throw new Error("only a terminal EXECUTE run can be retried");
    }
    const retried = this.#transitionResult(existing, {
      state: "QUEUED",
      outcome: "PROPOSAL_READY_FOR_RUNNER",
      lease: null,
      findings: existing.findings.filter(
        item => item.code !== "FRT_RUNNER_PROCESS_LOST_AFTER_RESTART",
      ),
    });
    this.#store.saveRun(scope, retried, {
      actor,
      event: "RUN_RETRIED",
      expectedStoredVersion: expectedVersion,
      now: this.#security.now(),
    });
    return retried;
  }
}

export const frtRuntime = new FrtRuntime();

/**
 * Evidence ledger for component translation.
 *
 * This is intentionally an evidence contract, not a status override.  A
 * ledger starts with all real-environment channels as NOT_RUN.  A caller may
 * attach a real artifact only when it has a digest and execution identity;
 * independent verification additionally requires a distinct verifier.
 */
import * as crypto from "crypto";
import type { CrossPlatformComponentIR } from "./cross-platform-ir";
import { EXECUTABLE_FRAMEWORKS, Framework } from "./models";

export type EvidenceChannel = "SOURCE_BUILD" | "TARGET_BUILD" | "BROWSER" | "DEVICE" | "PLATFORM" | "INDEPENDENT_VERIFICATION";
export type EvidenceStatus = "PASSED" | "FAILED" | "NOT_RUN" | "NOT_APPLICABLE";

export interface EvidenceRecord {
  id: string;
  channel: EvidenceChannel;
  status: EvidenceStatus;
  framework: Framework;
  environment: string;
  command: string | null;
  artifactPath: string | null;
  artifactDigest: string | null;
  executor: string | null;
  verifier: string | null;
  independent: boolean;
  observedAt: string | null;
  notes: string[];
}

export interface ComponentEvidenceLedger {
  schemaVersion: "1.0";
  kind: "elmos.component-translation-evidence";
  componentId: string;
  irDigest: string;
  sourceFramework: Framework;
  targetFramework: Framework;
  claim: "ENGINEERING_ONLY" | "READY_FOR_EXTERNAL_GATE" | "NOT_CERTIFIED";
  records: EvidenceRecord[];
  unresolved: string[];
}

export interface EvidenceObservation {
  status: "PASSED" | "FAILED";
  artifactPath: string;
  artifactContents: string;
  executor: string;
  verifier?: string;
  independent?: boolean;
  observedAt?: string;
  notes?: string[];
}

function record(id: string, channel: EvidenceChannel, framework: Framework, environment: string, status: EvidenceStatus, notes: string[] = []): EvidenceRecord {
  return { id, channel, status, framework, environment, command: null, artifactPath: null, artifactDigest: null, executor: null, verifier: null, independent: false, observedAt: null, notes };
}

export function createEvidenceLedger(ir: CrossPlatformComponentIR, targetFramework: Framework): ComponentEvidenceLedger {
  const target = ir.targetAdapters[targetFramework];
  const sourceRuntime = EXECUTABLE_FRAMEWORKS.has(ir.source.framework);
  const targetRuntime = target.runtimeEvidence === "AVAILABLE_HERE";
  const records: EvidenceRecord[] = [
    record("source-build", "SOURCE_BUILD", ir.source.framework, "declared-source-toolchain", "NOT_RUN"),
    record("target-build", "TARGET_BUILD", targetFramework, "declared-target-toolchain", "NOT_RUN"),
    record("browser", "BROWSER", targetFramework, "declared-browser-matrix", target.requiredRuntime === "BROWSER" ? "NOT_RUN" : "NOT_APPLICABLE"),
    record("device", "DEVICE", targetFramework, "declared-device-matrix", ["ANDROID", "IOS", "HARMONYOS", "FLUTTER", "WECHAT_DEVTOOLS"].includes(target.requiredRuntime) ? "NOT_RUN" : "NOT_APPLICABLE"),
    record("platform", "PLATFORM", targetFramework, "declared-platform-runtime", targetRuntime ? "NOT_RUN" : "NOT_RUN", sourceRuntime && targetRuntime ? [] : ["real source/target runtime is not available in the current engine process"]),
    record("independent", "INDEPENDENT_VERIFICATION", targetFramework, "independent-verifier", "NOT_RUN"),
  ];
  return {
    schemaVersion: "1.0",
    kind: "elmos.component-translation-evidence",
    componentId: ir.componentId,
    irDigest: ir.irDigest,
    sourceFramework: ir.source.framework,
    targetFramework,
    claim: "NOT_CERTIFIED",
    records,
    unresolved: ["source-build", "target-build", "browser-or-device", "platform-runtime", "independent-verification"],
  };
}

export function validateEvidenceLedger(ledger: ComponentEvidenceLedger): string[] {
  const errors: string[] = [];
  const ids = new Set<string>();
  for (const item of ledger.records) {
    if (ids.has(item.id)) errors.push(`duplicate evidence record ${item.id}`);
    ids.add(item.id);
    if (item.status === "PASSED") {
      if (!item.artifactPath || !/^sha256:[a-f0-9]{64}$/.test(item.artifactDigest ?? "")) errors.push(`${item.id}: PASSED requires a digest-bound artifact`);
      if (!item.executor) errors.push(`${item.id}: PASSED requires an executor identity`);
    }
    if (item.status === "FAILED" && item.artifactPath !== null) {
      if (!/^sha256:[a-f0-9]{64}$/.test(item.artifactDigest ?? "")) errors.push(`${item.id}: FAILED evidence with an artifact requires its digest`);
      if (!item.executor) errors.push(`${item.id}: FAILED evidence with an artifact requires an executor identity`);
    }
    if (item.channel === "INDEPENDENT_VERIFICATION" && item.status === "PASSED") {
      if (!item.independent) errors.push("independent verification cannot pass with independent=false");
      if (!item.verifier || item.verifier === item.executor) errors.push("independent verification requires a verifier distinct from the producer");
    }
    if ((item.status === "NOT_RUN" || item.status === "NOT_APPLICABLE") && (item.artifactPath !== null || item.artifactDigest !== null || item.executor !== null)) {
      errors.push(`${item.id}: ${item.status} evidence cannot carry an execution artifact or executor`);
    }
  }
  if (ledger.claim === "READY_FOR_EXTERNAL_GATE" || ledger.claim === "ENGINEERING_ONLY") {
    errors.push("this component evidence ledger may not manufacture a release or certification claim");
  }
  return errors;
}

function unresolvedFor(ledger: ComponentEvidenceLedger): string[] {
  const status = new Map(ledger.records.map((item) => [item.id, item.status]));
  const unresolved: string[] = [];
  if (status.get("source-build") !== "PASSED") unresolved.push("source-build");
  if (status.get("target-build") !== "PASSED") unresolved.push("target-build");
  const browserApplicable = status.get("browser") !== "NOT_APPLICABLE";
  const deviceApplicable = status.get("device") !== "NOT_APPLICABLE";
  const browserPassed = status.get("browser") === "PASSED";
  const devicePassed = status.get("device") === "PASSED";
  if ((browserApplicable || deviceApplicable) && !browserPassed && !devicePassed) unresolved.push("browser-or-device");
  if (status.get("platform") !== "PASSED") unresolved.push("platform-runtime");
  if (status.get("independent") !== "PASSED") unresolved.push("independent-verification");
  return unresolved;
}

/**
 * Bind an observation produced by a real runner to one ledger record.
 * The runner supplies the artifact bytes; this function computes the digest
 * itself so callers cannot claim that an arbitrary digest matches a file.
 * It deliberately does not promote `claim`: even a fully populated local
 * ledger still needs the separate Batch 32 gate and independent evidence.
 */
export function bindEvidenceObservation(
  ledger: ComponentEvidenceLedger,
  recordId: string,
  observation: EvidenceObservation,
): ComponentEvidenceLedger {
  if (!observation.artifactPath.trim()) throw new Error("EVIDENCE_ARTIFACT_PATH_REQUIRED");
  if (!observation.executor.trim()) throw new Error("EVIDENCE_EXECUTOR_REQUIRED");
  if (observation.status === "PASSED" && recordId === "independent") {
    if (!observation.independent || !observation.verifier?.trim() || observation.verifier === observation.executor) {
      throw new Error("EVIDENCE_INDEPENDENT_VERIFIER_REQUIRED");
    }
  }
  const found = ledger.records.some((item) => item.id === recordId);
  if (!found) throw new Error(`EVIDENCE_RECORD_NOT_FOUND: ${recordId}`);
  const artifactDigest = digestEvidenceArtifact(observation.artifactContents);
  const records = ledger.records.map((item) => item.id === recordId ? {
    ...item,
    status: observation.status,
    artifactPath: observation.artifactPath,
    artifactDigest,
    executor: observation.executor,
    verifier: observation.verifier ?? null,
    independent: observation.independent ?? false,
    observedAt: observation.observedAt ?? new Date().toISOString(),
    notes: observation.notes ?? item.notes,
  } : { ...item, notes: [...item.notes] });
  const updated: ComponentEvidenceLedger = { ...ledger, records, unresolved: [] };
  updated.unresolved = unresolvedFor(updated);
  const errors = validateEvidenceLedger(updated);
  if (errors.length > 0) throw new Error(`EVIDENCE_LEDGER_INVALID: ${errors.join("; ")}`);
  return updated;
}

export function digestEvidenceArtifact(contents: string): string {
  return `sha256:${crypto.createHash("sha256").update(contents, "utf8").digest("hex")}`;
}

import type { KeyObject } from "node:crypto";

import type { FrtArtifactStore } from "./frt-artifact-store.js";
import { evidenceReferencePayload, signFrtPayload } from "./frt-security.js";
import type { FrtEvidenceReference, FrtEvidenceState } from "./frt-types.js";

/**
 * Evidence production, split so that the party who produced a result can never be the
 * party who attests to it.
 *
 * A runner turns its own output (build log, test report, screenshot) into an unsigned
 * candidate: it can say what it ran and what came out, but it holds no evidence key
 * and therefore cannot make the result authoritative. An independent verifier — a
 * different identity holding a different EVIDENCE signing key — signs the candidate
 * into an FrtEvidenceReference. The runtime rejects any evidence whose verifier or
 * signing key is the runner's own.
 */
export interface FrtEvidenceCandidate {
  readonly schemaVersion: "1.0";
  readonly role: string;
  readonly uri: string;
  readonly digest: string;
  readonly state: FrtEvidenceState;
  readonly executor: string;
  readonly synthetic: boolean;
  readonly byteCount: number;
}

export interface FrtVerifierIdentity {
  readonly verifier: string;
  readonly authority: string;
  readonly keyId: string;
  readonly issuedAt: string;
  readonly expiresAt: string;
  readonly privateKey: string | KeyObject;
}

export interface FrtRunnerEvidenceOutput {
  readonly role: string;
  readonly state: FrtEvidenceState;
  readonly bytes: Buffer;
  readonly artifactName?: string;
  readonly synthetic?: boolean;
}

export class FrtEvidenceError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "FrtEvidenceError";
    this.code = code;
  }
}

/**
 * Materialises runner output into the artifact store and describes it as an unsigned
 * candidate. `state` must be the honest result — NOT_RUN and INCONCLUSIVE are valid
 * candidates and are rejected later by the gate, which is the point.
 */
export function evidenceCandidateFromBytes(
  options: {
    readonly role: string;
    readonly executor: string;
    readonly state: FrtEvidenceState;
    readonly bytes: Buffer;
    readonly store: FrtArtifactStore;
    readonly artifactName?: string;
    readonly synthetic?: boolean;
  },
): FrtEvidenceCandidate {
  if (!options.role.trim()) throw new FrtEvidenceError("FRT_EVIDENCE_ROLE_REQUIRED");
  if (!options.executor.trim()) throw new FrtEvidenceError("FRT_EVIDENCE_EXECUTOR_REQUIRED");
  const name = options.artifactName
    ?? `evidence-${options.role.toLocaleLowerCase("en-US").replaceAll(/[^a-z0-9]+/g, "-")}`;
  const stored = options.store.put(name, options.bytes);
  return {
    schemaVersion: "1.0",
    role: options.role,
    uri: stored.uri,
    digest: stored.digest,
    state: options.state,
    executor: options.executor,
    synthetic: options.synthetic ?? false,
    byteCount: stored.byteCount,
  };
}

/**
 * Converts a runner's complete output bundle into immutable unsigned candidates in one
 * deterministic operation. Duplicate roles are rejected because a gate role must bind
 * one unambiguous byte stream. This is collection, not attestation: candidates still
 * require an independent verifier before the runtime will trust them.
 */
export function collectRunnerEvidenceCandidates(options: {
  readonly executor: string;
  readonly outputs: readonly FrtRunnerEvidenceOutput[];
  readonly store: FrtArtifactStore;
}): readonly FrtEvidenceCandidate[] {
  if (!options.executor.trim()) throw new FrtEvidenceError("FRT_EVIDENCE_EXECUTOR_REQUIRED");
  if (options.outputs.length === 0) throw new FrtEvidenceError("FRT_EVIDENCE_OUTPUTS_REQUIRED");
  const roles = options.outputs.map(item => item.role);
  if (new Set(roles).size !== roles.length) {
    throw new FrtEvidenceError("FRT_EVIDENCE_ROLE_DUPLICATED");
  }
  return options.outputs.map(output => evidenceCandidateFromBytes({
    role: output.role,
    executor: options.executor,
    state: output.state,
    bytes: output.bytes,
    store: options.store,
    ...(output.artifactName === undefined ? {} : { artifactName: output.artifactName }),
    ...(output.synthetic === undefined ? {} : { synthetic: output.synthetic }),
  }));
}

/**
 * Signs a candidate as an independent verifier. Refuses when the verifier is the same
 * identity that produced the result, so producer/verifier separation cannot be lost by
 * a caller passing the runner's own identity.
 */
export function signEvidenceAsVerifier(
  candidate: FrtEvidenceCandidate,
  identity: FrtVerifierIdentity,
): FrtEvidenceReference {
  if (!identity.verifier.trim()) throw new FrtEvidenceError("FRT_EVIDENCE_VERIFIER_REQUIRED");
  if (identity.verifier === candidate.executor) {
    throw new FrtEvidenceError("FRT_INDEPENDENT_VERIFIER_MISSING");
  }
  const unsigned = {
    role: candidate.role,
    uri: candidate.uri,
    digest: candidate.digest,
    state: candidate.state,
    executor: candidate.executor,
    verifier: identity.verifier,
    synthetic: candidate.synthetic,
    byteCount: candidate.byteCount,
    authority: identity.authority,
    keyId: identity.keyId,
    issuedAt: identity.issuedAt,
    expiresAt: identity.expiresAt,
  };
  return {
    ...unsigned,
    signature: signFrtPayload(
      identity.privateKey,
      evidenceReferencePayload({ ...unsigned, signature: "pending" }),
    ),
  };
}

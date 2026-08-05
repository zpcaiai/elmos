import {
  createHash,
  createPrivateKey,
  createPublicKey,
  sign,
  verify,
  type KeyObject,
} from "node:crypto";
import {
  readFileSync,
  realpathSync,
  statSync,
} from "node:fs";
import { delimiter, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import type {
  FrtEvidenceReference,
  FrtExecutionScope,
  FrtPrerequisiteCertificate,
  FrtRunnerCompletion,
} from "./frt-types.js";

export type FrtTrustPurpose = "IDENTITY" | "CERTIFICATE" | "EVIDENCE" | "RUNNER";

/**
 * Role vocabulary shared with scripts/precision_migration/trust.py so the whole platform
 * describes signing authority the same way. `execution-attester` is FRT's addition:
 * precision migration has no runner that attests to its own execution.
 */
export type FrtTrustRole =
  | "identity-issuer"
  | "evidence-authorizer"
  | "gate-evidence-authorizer"
  | "execution-attester";

const rolePurposes: Readonly<Record<FrtTrustRole, FrtTrustPurpose>> = {
  "identity-issuer": "IDENTITY",
  "evidence-authorizer": "EVIDENCE",
  "gate-evidence-authorizer": "CERTIFICATE",
  "execution-attester": "RUNNER",
};

/** Roles that attest to a result. A key that executes must never also attest. */
const attestingPurposes: readonly FrtTrustPurpose[] = ["EVIDENCE", "CERTIFICATE"];

export interface FrtTrustKey {
  readonly keyId: string;
  readonly authority: string;
  readonly publicKeyPem: string;
  /** Internal purposes. Unioned with whatever `roles` resolves to. */
  readonly purposes: readonly FrtTrustPurpose[];
  /** Optional role names; each resolves to exactly one purpose. */
  readonly roles?: readonly FrtTrustRole[];
  readonly activeFrom: string;
  readonly expiresAt: string;
  readonly revoked: boolean;
}

export interface FrtTrustStoreDocument {
  readonly schemaVersion: "1.0";
  readonly keys: readonly FrtTrustKey[];
  /**
   * Record-level revocation, same meaning as `revoked_record_ids` in
   * scripts/precision_migration/trust.py. Evidence is keyed by its own digest, a runner
   * completion by its payload digest, a certificate by its artifactDigest. One bad record
   * can be voided precisely without revoking the key that signed everything else.
   */
  readonly revokedRecordIds?: readonly string[];
}

export interface FrtIdentityClaims {
  readonly schemaVersion: "1.0";
  readonly subject: string;
  readonly permissions: readonly ("frt:plan" | "frt:run" | "frt:read" | "frt:evidence")[];
  readonly scope: FrtExecutionScope;
  readonly issuedAt: string;
  readonly expiresAt: string;
  readonly nonce: string;
}

export interface FrtIdentityEnvelope {
  readonly schemaVersion: "1.0";
  readonly authority: string;
  readonly keyId: string;
  readonly claims: FrtIdentityClaims;
}

export interface FrtEvidenceContent {
  readonly bytes: Buffer;
  readonly canonicalUri: string;
}

export interface FrtEvidenceResolver {
  resolve(uri: string): FrtEvidenceContent;
}

export interface FrtSecurityContext {
  readonly trustStore: FrtTrustStore;
  readonly evidenceResolver: FrtEvidenceResolver;
  readonly now: () => Date;
}

const safeId = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$/;
const sha256 = /^sha256:[a-f0-9]{64}$/;
const base64url = /^[A-Za-z0-9_-]+$/;
const permissions = new Set(["frt:plan", "frt:run", "frt:read", "frt:evidence"]);

export class FrtSecurityError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "FrtSecurityError";
    this.code = code;
  }
}

/**
 * Canonical JSON shared with `scripts/precision_migration/trust.py`.
 *
 * Both sides must emit identical bytes or a signature minted by one cannot be verified
 * by the other, which is what lets them share a single trust store. The contract is:
 * object keys sorted ascending, no insignificant whitespace, and raw UTF-8 rather than
 * `\uXXXX` escapes (Python needs `ensure_ascii=False` for that last part).
 *
 * The comparison below is deliberately `<` and not `localeCompare`. Locale collation is
 * not code-point order: it reorders the signed key sets under cs, sk, lv, lt, az, uz, cy
 * and the Spanish traditional collation, so a signature minted on one host would fail to
 * verify on another. Do not reintroduce it.
 *
 * Known and accepted limit: JS relational operators compare UTF-16 code units while
 * Python `sort_keys` compares code points. The two disagree only for keys containing
 * supplementary-plane characters (U+10000 and above), which sort before U+E000..U+FFFF
 * here but after them in Python. Every key in every signed payload is a schema-constrained
 * ASCII identifier, so this cannot be reached today; widening a key pattern beyond ASCII
 * would require replacing this comparator with an explicit code-point comparison on both
 * sides at once.
 */
export function canonicalFrtJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalFrtJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalFrtJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function timestamp(value: string, code: string): number {
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) throw new FrtSecurityError(code);
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw new FrtSecurityError(code);
  return parsed;
}

function activeWindow(issuedAt: string, expiresAt: string, now: Date, prefix: string): void {
  const issued = timestamp(issuedAt, `${prefix}_ISSUED_AT_INVALID`);
  const expires = timestamp(expiresAt, `${prefix}_EXPIRES_AT_INVALID`);
  if (issued > now.getTime() + 60_000) throw new FrtSecurityError(`${prefix}_NOT_YET_VALID`);
  if (expires <= now.getTime()) throw new FrtSecurityError(`${prefix}_EXPIRED`);
  if (expires <= issued) throw new FrtSecurityError(`${prefix}_WINDOW_INVALID`);
}

function confined(root: string, candidate: string): string {
  const rootPath = realpathSync(resolve(root));
  const candidatePath = realpathSync(resolve(candidate));
  const pathFromRoot = relative(rootPath, candidatePath);
  if (pathFromRoot.startsWith("..") || isAbsolute(pathFromRoot)) {
    throw new FrtSecurityError("FRT_EVIDENCE_PATH_OUTSIDE_APPROVED_ROOT");
  }
  return candidatePath;
}

export class DenyAllFrtEvidenceResolver implements FrtEvidenceResolver {
  resolve(): FrtEvidenceContent {
    throw new FrtSecurityError("FRT_EVIDENCE_RESOLVER_NOT_CONFIGURED");
  }
}

export class ConfinedFileFrtEvidenceResolver implements FrtEvidenceResolver {
  readonly #roots: readonly string[];

  constructor(roots: readonly string[]) {
    this.#roots = roots.map(root => realpathSync(resolve(root)));
    if (!this.#roots.length) throw new FrtSecurityError("FRT_EVIDENCE_ROOT_REQUIRED");
  }

  resolve(uri: string): FrtEvidenceContent {
    let path: string;
    try {
      const parsed = new URL(uri);
      if (parsed.protocol !== "file:") throw new FrtSecurityError("FRT_EVIDENCE_URI_SCHEME_UNSUPPORTED");
      path = fileURLToPath(parsed);
    } catch (error) {
      if (error instanceof FrtSecurityError) throw error;
      throw new FrtSecurityError("FRT_EVIDENCE_URI_INVALID");
    }
    const approved = this.#roots.find(root => {
      try {
        confined(root, path);
        return true;
      } catch {
        return false;
      }
    });
    if (!approved) throw new FrtSecurityError("FRT_EVIDENCE_PATH_OUTSIDE_APPROVED_ROOT");
    const canonicalPath = confined(approved, path);
    const stats = statSync(canonicalPath);
    if (!stats.isFile()) throw new FrtSecurityError("FRT_EVIDENCE_NOT_A_FILE");
    return { bytes: readFileSync(canonicalPath), canonicalUri: pathToFileURL(canonicalPath).href };
  }
}

export class FrtTrustStore {
  readonly #keys: ReadonlyMap<string, FrtTrustKey>;
  readonly #purposes: ReadonlyMap<string, readonly FrtTrustPurpose[]>;
  readonly #revokedRecordIds: ReadonlySet<string>;

  constructor(document: FrtTrustStoreDocument) {
    if (document.schemaVersion !== "1.0" || !Array.isArray(document.keys)) {
      throw new FrtSecurityError("FRT_TRUST_STORE_INVALID");
    }
    const keys = new Map<string, FrtTrustKey>();
    const purposes = new Map<string, readonly FrtTrustPurpose[]>();
    for (const key of document.keys) {
      if (!safeId.test(key.keyId) || !safeId.test(key.authority) || keys.has(key.keyId)) {
        throw new FrtSecurityError("FRT_TRUST_KEY_INVALID");
      }
      const declaredRoles: readonly FrtTrustRole[] = key.roles ?? [];
      if (!declaredRoles.every((role: FrtTrustRole) => Object.hasOwn(rolePurposes, role))) {
        throw new FrtSecurityError("FRT_TRUST_KEY_ROLE_UNKNOWN");
      }
      const resolved = [...new Set<FrtTrustPurpose>([
        ...key.purposes,
        ...declaredRoles.map((role: FrtTrustRole) => rolePurposes[role]),
      ])];
      // Structural invariant: a key that attests to its own execution can never also sign
      // evidence or gate certificates. Enforcing it here means every call path inherits
      // "the executor cannot vouch for itself" without repeating the check, and a deployment
      // holding an all-powerful key fails at load instead of at audit time.
      if (resolved.includes("RUNNER") && resolved.some(item => attestingPurposes.includes(item))) {
        throw new FrtSecurityError("FRT_TRUST_KEY_ROLE_CONFLICT");
      }
      createPublicKey(key.publicKeyPem);
      keys.set(key.keyId, key);
      purposes.set(key.keyId, resolved);
    }
    this.#keys = keys;
    this.#purposes = purposes;
    const revoked = document.revokedRecordIds ?? [];
    if (!Array.isArray(revoked) || revoked.some(item => typeof item !== "string" || !item.length)) {
      throw new FrtSecurityError("FRT_TRUST_STORE_INVALID");
    }
    this.#revokedRecordIds = new Set(revoked);
  }

  /** True when a specific signed record has been voided without revoking its signing key. */
  isRecordRevoked(recordId: string): boolean {
    return this.#revokedRecordIds.has(recordId);
  }

  verify(
    purpose: FrtTrustPurpose,
    authority: string,
    keyId: string,
    issuedAt: string,
    expiresAt: string,
    payload: unknown,
    signature: string,
    now: Date,
  ): void {
    const key = this.#keys.get(keyId);
    if (!key || key.revoked || key.authority !== authority
        || !(this.#purposes.get(keyId) ?? []).includes(purpose)) {
      throw new FrtSecurityError(`FRT_${purpose}_TRUST_KEY_REJECTED`);
    }
    activeWindow(key.activeFrom, key.expiresAt, now, "FRT_TRUST_KEY");
    activeWindow(issuedAt, expiresAt, now, `FRT_${purpose}`);
    if (!base64url.test(signature)) {
      throw new FrtSecurityError(`FRT_${purpose}_SIGNATURE_INVALID`);
    }
    const signatureBytes = Buffer.from(signature, "base64url");
    if (!signatureBytes.length || !verify(
      null,
      Buffer.from(canonicalFrtJson(payload)),
      createPublicKey(key.publicKeyPem),
      signatureBytes,
    )) {
      throw new FrtSecurityError(`FRT_${purpose}_SIGNATURE_INVALID`);
    }
  }
}

export function prerequisiteCertificatePayload(
  certificate: FrtPrerequisiteCertificate,
): Readonly<Record<string, unknown>> {
  const { signature: _signature, ...payload } = certificate;
  return payload;
}

export function evidenceReferencePayload(
  evidence: FrtEvidenceReference,
): Readonly<Record<string, unknown>> {
  const { signature: _signature, ...payload } = evidence;
  return payload;
}

export function runnerCompletionPayload(
  completion: FrtRunnerCompletion,
): Readonly<Record<string, unknown>> {
  const { signature: _signature, ...payload } = completion;
  return payload;
}

export function signFrtPayload(privateKey: string | KeyObject, payload: unknown): string {
  const key = typeof privateKey === "string" ? createPrivateKey(privateKey) : privateKey;
  return sign(null, Buffer.from(canonicalFrtJson(payload)), key).toString("base64url");
}

export function encodeFrtIdentityToken(
  envelope: FrtIdentityEnvelope,
  privateKey: string | KeyObject,
): string {
  const encoded = Buffer.from(canonicalFrtJson(envelope)).toString("base64url");
  return `${encoded}.${signFrtPayload(privateKey, envelope)}`;
}

export function verifyFrtIdentityToken(
  token: string,
  trustStore: FrtTrustStore,
  now: Date,
): FrtIdentityClaims {
  const [encoded, signature, extra] = token.split(".");
  if (!encoded || !signature || extra || !base64url.test(encoded) || !base64url.test(signature)) {
    throw new FrtSecurityError("FRT_IDENTITY_TOKEN_INVALID");
  }
  let envelope: FrtIdentityEnvelope;
  try {
    envelope = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8")) as FrtIdentityEnvelope;
  } catch {
    throw new FrtSecurityError("FRT_IDENTITY_TOKEN_INVALID");
  }
  if (envelope.schemaVersion !== "1.0" || envelope.claims?.schemaVersion !== "1.0") {
    throw new FrtSecurityError("FRT_IDENTITY_TOKEN_INVALID");
  }
  const claims = envelope.claims;
  const scope = claims.scope;
  if (!safeId.test(envelope.authority) || !safeId.test(envelope.keyId)
      || !safeId.test(claims.subject) || !safeId.test(claims.nonce)
      || !scope || !Object.values(scope).every(value => typeof value === "string" && safeId.test(value))
      || !Array.isArray(claims.permissions) || claims.permissions.length === 0
      || new Set(claims.permissions).size !== claims.permissions.length
      || !claims.permissions.every(permission => permissions.has(permission))) {
    throw new FrtSecurityError("FRT_IDENTITY_TOKEN_INVALID");
  }
  trustStore.verify(
    "IDENTITY",
    envelope.authority,
    envelope.keyId,
    envelope.claims.issuedAt,
    envelope.claims.expiresAt,
    envelope,
    signature,
    now,
  );
  return claims;
}

export function digestFrtEvidence(bytes: Buffer): string {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function trustStoreFromEnvironment(): FrtTrustStore {
  const path = process.env.ELMOS_FRT_TRUST_STORE_PATH?.trim();
  if (!path) return new FrtTrustStore({ schemaVersion: "1.0", keys: [] });
  return new FrtTrustStore(JSON.parse(readFileSync(path, "utf8")) as FrtTrustStoreDocument);
}

function evidenceResolverFromEnvironment(): FrtEvidenceResolver {
  const roots = (process.env.ELMOS_FRT_EVIDENCE_ROOTS ?? "")
    .split(delimiter)
    .map(item => item.trim())
    .filter(Boolean);
  return roots.length ? new ConfinedFileFrtEvidenceResolver(roots) : new DenyAllFrtEvidenceResolver();
}

export function frtSecurityFromEnvironment(): FrtSecurityContext {
  return {
    trustStore: trustStoreFromEnvironment(),
    evidenceResolver: evidenceResolverFromEnvironment(),
    now: () => new Date(),
  };
}

export function validateResolvedEvidence(
  reference: FrtEvidenceReference,
  security: FrtSecurityContext,
): void {
  security.trustStore.verify(
    "EVIDENCE",
    reference.authority,
    reference.keyId,
    reference.issuedAt,
    reference.expiresAt,
    evidenceReferencePayload(reference),
    reference.signature,
    security.now(),
  );
  const content = security.evidenceResolver.resolve(reference.uri);
  if (content.bytes.byteLength !== reference.byteCount) {
    throw new FrtSecurityError("FRT_EVIDENCE_BYTE_COUNT_MISMATCH");
  }
  if (!sha256.test(reference.digest) || digestFrtEvidence(content.bytes) !== reference.digest) {
    throw new FrtSecurityError("FRT_EVIDENCE_DIGEST_MISMATCH");
  }
}

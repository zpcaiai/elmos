import { generateKeyPairSync, sign, verify, type KeyObject } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

export const HOSTED_JOB_TOKEN_TYPE = "ELMOS-JOB";
export const HOSTED_JOB_TOKEN_ISSUER = "elmos-job-dispatcher";
export const HOSTED_JOB_TOKEN_AUDIENCE = "elmos-runner-agent";
const MAX_LIFETIME_SECONDS = 15 * 60;
const IMAGE = /^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?\/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$/;
const IDENTITY = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$/;
const JTI = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,199}$/;
const SCOPES = new Set(["generate", "build", "probe", "preview", "archive"]);

export class HostedJobTokenError extends Error {
  readonly code: string;
  constructor(code: string) {
    super(code);
    this.name = "HostedJobTokenError";
    this.code = code;
  }
}

export type HostedJobTokenClaims = {
  jti: string;
  tenant: string;
  actor: string;
  job: string;
  scope: string[];
  image: string;
  limits: {
    cpu_millis: number;
    memory_mib: number;
    pids: number;
    wallclock_seconds: number;
  };
  iat: number;
  exp: number;
};

function encode(value: object): string {
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

function decodeObject(value: string): Record<string, unknown> {
  try {
    const decoded: unknown = JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
    if (!decoded || typeof decoded !== "object" || Array.isArray(decoded)) {
      throw new Error("not an object");
    }
    return decoded as Record<string, unknown>;
  } catch {
    throw new HostedJobTokenError("JOB_TOKEN_MALFORMED");
  }
}

function validInteger(value: unknown, minimum: number, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
}

function validateClaims(claims: HostedJobTokenClaims, now?: number): void {
  if (!validInteger(claims.iat, 0) || !validInteger(claims.exp, 0)
      || claims.exp <= claims.iat || claims.exp - claims.iat > MAX_LIFETIME_SECONDS) {
    throw new HostedJobTokenError("JOB_TOKEN_LIFETIME_INVALID");
  }
  if (now !== undefined) {
    if (claims.exp <= now) throw new HostedJobTokenError("JOB_TOKEN_EXPIRED");
    if (claims.iat > now + 30) throw new HostedJobTokenError("JOB_TOKEN_NOT_YET_VALID");
  }
  if (!IMAGE.test(claims.image)) {
    throw new HostedJobTokenError("JOB_TOKEN_IMAGE_NOT_DIGEST_PINNED");
  }
  if (!IDENTITY.test(claims.tenant) || !IDENTITY.test(claims.actor)
      || !IDENTITY.test(claims.job) || !JTI.test(claims.jti)) {
    throw new HostedJobTokenError("JOB_TOKEN_IDENTITY_INVALID");
  }
  if (!Array.isArray(claims.scope) || claims.scope.length === 0
      || claims.scope.some((scope) => typeof scope !== "string" || !SCOPES.has(scope))) {
    throw new HostedJobTokenError("JOB_TOKEN_SCOPE_INVALID");
  }
  const limits = claims.limits;
  if (!limits || typeof limits !== "object"
      || !validInteger(limits.cpu_millis, 100)
      || !validInteger(limits.memory_mib, 64)
      || !validInteger(limits.pids, 8)
      || !validInteger(limits.wallclock_seconds, 1, MAX_LIFETIME_SECONDS)) {
    throw new HostedJobTokenError("JOB_TOKEN_LIMITS_INVALID");
  }
}

export function rejectLocalRunnerInProduction(environment: NodeJS.ProcessEnv = process.env): void {
  const hosted = environment.ELMOS_HOSTED_RUNNER_ENABLED === "true"
    || environment.ELMOS_ENVIRONMENT === "production";
  if (!hosted) {
    return;
  }
  if (environment.ELMOS_LOCAL_RUNNER_AUTH_TOKEN || environment.ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE) {
    throw new HostedJobTokenError("LOCAL_RUNNER_TOKEN_FORBIDDEN_IN_PRODUCTION");
  }
  if (environment.ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID) {
    throw new HostedJobTokenError("TRUSTED_SINGLE_TENANT_FORBIDDEN_IN_PRODUCTION");
  }
  if (environment.ELMOS_HOSTED_RUNNER_ENABLED !== "true") {
    throw new HostedJobTokenError("HOSTED_RUNNER_REQUIRED_IN_PRODUCTION");
  }
}

export function issueHostedJobToken(
  claims: HostedJobTokenClaims,
  privateKey: KeyObject,
  keyId: string,
): string {
  validateClaims(claims);
  const header = encode({ alg: "EdDSA", typ: HOSTED_JOB_TOKEN_TYPE, kid: keyId });
  const payload = encode({
    ...claims,
    iss: HOSTED_JOB_TOKEN_ISSUER,
    aud: HOSTED_JOB_TOKEN_AUDIENCE,
    v: 1,
  });
  const message = `${header}.${payload}`;
  const signature = sign(null, Buffer.from(message, "utf8"), privateKey).toString("base64url");
  return `${message}.${signature}`;
}

export function verifyHostedJobToken(
  token: string,
  publicKey: KeyObject,
  keyId: string,
  requiredScope: string,
  seenJti: Set<string>,
  now = Math.floor(Date.now() / 1000),
  expectedTenant?: string,
  expectedJob?: string,
): HostedJobTokenClaims {
  const parts = token.split(".");
  if (parts.length !== 3) throw new HostedJobTokenError("JOB_TOKEN_MALFORMED");
  const header = decodeObject(parts[0]);
  if (header.alg !== "EdDSA" || header.typ !== HOSTED_JOB_TOKEN_TYPE || header.kid !== keyId) {
    throw new HostedJobTokenError("JOB_TOKEN_HEADER_INVALID");
  }
  let ok = false;
  try {
    ok = verify(
      null,
      Buffer.from(`${parts[0]}.${parts[1]}`, "utf8"),
      publicKey,
      Buffer.from(parts[2], "base64url"),
    );
  } catch {
    throw new HostedJobTokenError("JOB_TOKEN_SIGNATURE_INVALID");
  }
  if (!ok) throw new HostedJobTokenError("JOB_TOKEN_SIGNATURE_INVALID");
  const payload = decodeObject(parts[1]) as HostedJobTokenClaims & {
    iss?: string;
    aud?: string;
    v?: number;
  };
  if (payload.iss !== HOSTED_JOB_TOKEN_ISSUER || payload.aud !== HOSTED_JOB_TOKEN_AUDIENCE || payload.v !== 1) {
    throw new HostedJobTokenError("JOB_TOKEN_CLAIMS_INVALID");
  }
  validateClaims(payload, now);
  if (!payload.scope.includes(requiredScope)) throw new HostedJobTokenError("JOB_TOKEN_SCOPE_DENIED");
  if (expectedTenant !== undefined && payload.tenant !== expectedTenant) {
    throw new HostedJobTokenError("JOB_TOKEN_TENANT_MISMATCH");
  }
  if (expectedJob !== undefined && payload.job !== expectedJob) {
    throw new HostedJobTokenError("JOB_TOKEN_JOB_MISMATCH");
  }
  if (seenJti.has(payload.jti)) throw new HostedJobTokenError("JOB_TOKEN_REPLAYED");
  seenJti.add(payload.jti);
  return payload;
}

export function writeEd25519KeyPair(directory: string): { privateKeyPem: string; publicKeyPem: string } {
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const privateKeyPem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
  const publicKeyPem = publicKey.export({ type: "spki", format: "pem" }).toString();
  writeFileSync(path.join(directory, "job-token.ed25519.private.pem"), privateKeyPem, { mode: 0o600 });
  writeFileSync(path.join(directory, "job-token.ed25519.public.pem"), publicKeyPem, { mode: 0o644 });
  return { privateKeyPem, publicKeyPem };
}

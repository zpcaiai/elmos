import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import {
  closeSync,
  constants as fsConstants,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import path from "node:path";

const TOKEN_TYPE = "ELMOS-RUNNER-SVC";
const TOKEN_ALGORITHM = "HS256";
const TOKEN_ISSUER = "elmos-local-runner-controller";
const TOKEN_AUDIENCE = "elmos-generation-runner";
const MAX_TOKEN_LIFETIME_SECONDS = 300;
const CLOCK_SKEW_SECONDS = 5;
const MAX_KEY_BYTES = 4_096;
const identityPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$/;
const keyIdPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/;
const jtiPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,199}$/;

type Environment = Record<string, string | undefined>;

export class LocalRunnerCredentialError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = "LocalRunnerCredentialError";
    this.code = code;
    this.status = status;
  }
}

type Header = { alg: string; typ: string; kid: string };
type Claims = {
  v: number;
  iss: string;
  aud: string;
  tenant_id: string;
  actor_id: string;
  permission: string;
  method: string;
  path: string;
  iat: number;
  nbf: number;
  exp: number;
  jti: string;
};

function exactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const observed = Object.keys(value).sort();
  return observed.length === expected.length
    && observed.every((key, index) => key === [...expected].sort()[index]);
}

function parseSegment(segment: string): Record<string, unknown> {
  if (!/^[A-Za-z0-9_-]+$/.test(segment) || segment.length > 8_192) {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_MALFORMED", 401);
  }
  try {
    const value = JSON.parse(Buffer.from(segment, "base64url").toString("utf8")) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("object required");
    return value as Record<string, unknown>;
  } catch {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_MALFORMED", 401);
  }
}

function safeEqual(left: Buffer, right: Buffer): boolean {
  return left.length === right.length && timingSafeEqual(left, right);
}

function signingKey(environment: Environment): { key: Buffer; keyId: string } {
  const configuredPath = environment.ELMOS_LOCAL_RUNNER_AUTH_SIGNING_KEY_FILE?.trim() ?? "";
  const keyId = environment.ELMOS_LOCAL_RUNNER_AUTH_KEY_ID?.trim() ?? "";
  if (!path.isAbsolute(configuredPath) || !keyIdPattern.test(keyId)) {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_CONFIG_INVALID", 503);
  }
  try {
    const info = lstatSync(configuredPath);
    if (
      info.isSymbolicLink()
      || !info.isFile()
      || info.size < 32
      || info.size > MAX_KEY_BYTES
      || (info.mode & 0o077) !== 0
      || (typeof process.getuid === "function" && info.uid !== process.getuid())
    ) throw new Error("unsafe signing key");
    const key = Buffer.from(
      readFileSync(/* turbopackIgnore: true */ configuredPath, "utf8").trim(),
      "utf8",
    );
    if (key.length < 32 || key.length > MAX_KEY_BYTES) throw new Error("invalid signing key length");
    return { key, keyId };
  } catch {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_CONFIG_INVALID", 503);
  }
}

function durableReplayCheck(environment: Environment, issuer: string, jti: string, exp: number, now: number): void {
  const configuredRoot = environment.ELMOS_LOCAL_RUNNER_ROOT?.trim() ?? "";
  if (!path.isAbsolute(configuredRoot)) {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_CREDENTIAL_REPLAY_STORE_INVALID", 503);
  }
  try {
    const rootInfo = lstatSync(configuredRoot);
    if (
      rootInfo.isSymbolicLink()
      || !rootInfo.isDirectory()
      || (rootInfo.mode & 0o077) !== 0
      || (typeof process.getuid === "function" && rootInfo.uid !== process.getuid())
      || realpathSync(/* turbopackIgnore: true */ configuredRoot) !== configuredRoot
    ) throw new Error("unsafe replay root");
    const replayRoot = path.join(configuredRoot, "credential-replay");
    try {
      mkdirSync(replayRoot, { recursive: false, mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }
    const replayInfo = lstatSync(replayRoot);
    if (
      replayInfo.isSymbolicLink()
      || !replayInfo.isDirectory()
      || (replayInfo.mode & 0o077) !== 0
      || (typeof process.getuid === "function" && replayInfo.uid !== process.getuid())
    ) throw new Error("unsafe replay directory");
    const entries = readdirSync(replayRoot);
    if (entries.length > 10_000) {
      throw new LocalRunnerCredentialError("LOCAL_RUNNER_CREDENTIAL_REPLAY_STORE_FULL", 503);
    }
    for (const entry of entries) {
      const match = /^(\d{10})-[a-f0-9]{64}$/.exec(entry);
      if (!match) throw new Error("invalid replay entry");
      if (Number(match[1]) > now) continue;
      const expired = path.join(replayRoot, entry);
      const info = lstatSync(expired);
      if (info.isSymbolicLink() || !info.isFile() || (info.mode & 0o077) !== 0) {
        throw new Error("unsafe replay entry");
      }
      unlinkSync(expired);
    }
    const digest = createHash("sha256").update(`${issuer}\0${jti}`, "utf8").digest("hex");
    const replayPath = path.join(replayRoot, `${String(exp).padStart(10, "0")}-${digest}`);
    let descriptor: number | undefined;
    try {
      descriptor = openSync(
        replayPath,
        fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
        0o600,
      );
      writeSync(descriptor, `${digest}\n`, undefined, "utf8");
      fsyncSync(descriptor);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "EEXIST") {
        throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_REPLAYED", 401);
      }
      throw error;
    } finally {
      if (descriptor !== undefined) closeSync(descriptor);
    }
  } catch (error) {
    if (error instanceof LocalRunnerCredentialError) throw error;
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_CREDENTIAL_REPLAY_STORE_INVALID", 503);
  }
}

export function verifyLocalRunnerServiceCredential(input: {
  authorization: string;
  tenantHeader: string;
  actorHeader: string;
  permission: string;
  method: string;
  path: string;
  environment?: Environment;
  now?: Date;
}): { tenantId: string; actor: string } {
  const match = /^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/.exec(input.authorization);
  if (!match) throw new LocalRunnerCredentialError("AUTHENTICATION_REQUIRED", 401);
  const [encodedHeader, encodedClaims, encodedSignature] = match[1].split(".");
  const header = parseSegment(encodedHeader) as Header;
  const claims = parseSegment(encodedClaims) as Claims;
  if (!exactKeys(header as unknown as Record<string, unknown>, ["alg", "typ", "kid"])
    || header.alg !== TOKEN_ALGORITHM
    || header.typ !== TOKEN_TYPE) {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_HEADER_INVALID", 401);
  }
  const { key, keyId } = signingKey(input.environment ?? process.env);
  if (header.kid !== keyId) {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_KEY_ID_INVALID", 401);
  }
  let providedSignature: Buffer;
  try {
    providedSignature = Buffer.from(encodedSignature, "base64url");
    if (providedSignature.toString("base64url") !== encodedSignature) {
      throw new Error("non-canonical base64url signature");
    }
  } catch {
    throw new LocalRunnerCredentialError("AUTHENTICATION_REQUIRED", 401);
  }
  const expectedSignature = createHmac("sha256", key)
    .update(`${encodedHeader}.${encodedClaims}`, "utf8")
    .digest();
  if (!safeEqual(providedSignature, expectedSignature)) {
    throw new LocalRunnerCredentialError("AUTHENTICATION_REQUIRED", 401);
  }
  const expectedClaimKeys = [
    "v", "iss", "aud", "tenant_id", "actor_id", "permission", "method", "path",
    "iat", "nbf", "exp", "jti",
  ] as const;
  const now = Math.floor((input.now ?? new Date()).getTime() / 1000);
  if (
    !exactKeys(claims as unknown as Record<string, unknown>, expectedClaimKeys)
    || claims.v !== 1
    || claims.iss !== TOKEN_ISSUER
    || claims.aud !== TOKEN_AUDIENCE
    || !identityPattern.test(claims.tenant_id)
    || !identityPattern.test(claims.actor_id)
    || claims.permission !== input.permission
    || claims.method !== input.method.toUpperCase()
    || claims.path !== input.path
    || !Number.isSafeInteger(claims.iat)
    || !Number.isSafeInteger(claims.nbf)
    || !Number.isSafeInteger(claims.exp)
    || !jtiPattern.test(claims.jti)
    || claims.iat > now + CLOCK_SKEW_SECONDS
    || claims.iat < now - MAX_TOKEN_LIFETIME_SECONDS
    || claims.nbf > now + CLOCK_SKEW_SECONDS
    || claims.nbf < claims.iat - CLOCK_SKEW_SECONDS
    || claims.exp <= now
    || claims.exp <= claims.iat
    || claims.exp - claims.iat > MAX_TOKEN_LIFETIME_SECONDS
  ) {
    throw new LocalRunnerCredentialError("LOCAL_RUNNER_SERVICE_CREDENTIAL_CLAIMS_INVALID", 401);
  }
  if (input.tenantHeader !== claims.tenant_id) {
    throw new LocalRunnerCredentialError("TENANT_ID_NOT_BOUND_TO_CREDENTIAL", 403);
  }
  if (input.actorHeader !== claims.actor_id) {
    throw new LocalRunnerCredentialError("ACTOR_ID_NOT_BOUND_TO_CREDENTIAL", 403);
  }
  durableReplayCheck(input.environment ?? process.env, claims.iss, claims.jti, claims.exp, now);
  return { tenantId: claims.tenant_id, actor: claims.actor_id };
}

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";
import { chmod, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  LocalRunnerCredentialError,
  verifyLocalRunnerServiceCredential,
} from "./localRunnerServiceCredential.ts";

const root = await realpath(await mkdtemp(path.join(os.tmpdir(), "elmos-runner-credential-")));
const keyFile = path.join(root, "key");
const key = "test-only-signing-key-that-is-long-enough-0123456789";
await writeFile(keyFile, key, { mode: 0o600 });
await chmod(keyFile, 0o600);
const environment = {
  ELMOS_LOCAL_RUNNER_AUTH_SIGNING_KEY_FILE: keyFile,
  ELMOS_LOCAL_RUNNER_AUTH_KEY_ID: "runner-key-20260904",
  ELMOS_LOCAL_RUNNER_ROOT: root,
};
const now = new Date("2026-09-04T12:00:00Z");

function token(overrides = {}, overrideHeader = {}) {
  const header = { alg: "HS256", typ: "ELMOS-RUNNER-SVC", kid: "runner-key-20260904", ...overrideHeader };
  const claims = {
    v: 1,
    iss: "elmos-local-runner-controller",
    aud: "elmos-generation-runner",
    tenant_id: "tenant:one",
    actor_id: "service:controller",
    permission: "generation:execute",
    method: "POST",
    path: "/api/generation/jobs",
    iat: 1788523200,
    nbf: 1788523200,
    exp: 1788523320,
    jti: `request-${Math.random().toString(36).slice(2)}-0123456789`,
    ...overrides,
  };
  const encodedHeader = Buffer.from(JSON.stringify(header)).toString("base64url");
  const encodedClaims = Buffer.from(JSON.stringify(claims)).toString("base64url");
  const signature = createHmac("sha256", key)
    .update(`${encodedHeader}.${encodedClaims}`)
    .digest("base64url");
  return `${encodedHeader}.${encodedClaims}.${signature}`;
}

function verify(value) {
  return verifyAt(value, now);
}

function verifyAt(value, observedAt) {
  return verifyLocalRunnerServiceCredential({
    authorization: `Bearer ${value}`,
    tenantHeader: "tenant:one",
    actorHeader: "service:controller",
    permission: "generation:execute",
    method: "POST",
    path: "/api/generation/jobs",
    environment,
    now: observedAt,
  });
}

try {
  assert.deepEqual(verify(token()), { tenantId: "tenant:one", actor: "service:controller" });

  const replayed = token();
  verify(replayed);
  assert.throws(() => verify(replayed), (error) => (
    error instanceof LocalRunnerCredentialError
    && error.code === "LOCAL_RUNNER_SERVICE_CREDENTIAL_REPLAYED"
  ));

  assert.throws(() => verify(token({ aud: "other-runner" })), /LOCAL_RUNNER_SERVICE_CREDENTIAL_CLAIMS_INVALID/);
  assert.throws(() => verify(token({ exp: 1788526800 })), /LOCAL_RUNNER_SERVICE_CREDENTIAL_CLAIMS_INVALID/);
  assert.throws(() => verify(token({ tenant_id: "tenant:two" })), /TENANT_ID_NOT_BOUND_TO_CREDENTIAL/);
  assert.throws(() => verify(token({ permission: "repository:push" })), /LOCAL_RUNNER_SERVICE_CREDENTIAL_CLAIMS_INVALID/);
  assert.throws(() => verify(token({ path: "/api/generation/jobs/other" })), /LOCAL_RUNNER_SERVICE_CREDENTIAL_CLAIMS_INVALID/);
  const signed = token();
  const segments = signed.split(".");
  const tamperedSignature = `${segments[2][0] === "A" ? "B" : "A"}${segments[2].slice(1)}`;
  const tampered = `${segments[0]}.${segments[1]}.${tamperedSignature}`;
  assert.throws(() => verify(tampered), /AUTHENTICATION_REQUIRED/);

  const canonical = token();
  const canonicalSegments = canonical.split(".");
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  const lastIndex = alphabet.indexOf(canonicalSegments[2].at(-1));
  assert.notEqual(lastIndex, -1);
  const nonCanonicalLast = alphabet[(lastIndex & 0b111100) | 0b000001];
  assert.notEqual(nonCanonicalLast, canonicalSegments[2].at(-1));
  const nonCanonical = `${canonicalSegments[0]}.${canonicalSegments[1]}.${canonicalSegments[2].slice(0, -1)}${nonCanonicalLast}`;
  assert.deepEqual(Buffer.from(canonicalSegments[2], "base64url"), Buffer.from(`${canonicalSegments[2].slice(0, -1)}${nonCanonicalLast}`, "base64url"));
  assert.throws(() => verify(nonCanonical), /AUTHENTICATION_REQUIRED/);

  const issuer = path.resolve(
    path.dirname(new URL(import.meta.url).pathname),
    "../../../../../deploy/local-runner/issue_service_credential.py",
  );
  const issued = execFileSync("python3", [
    issuer,
    "--key-file", keyFile,
    "--key-id", "runner-key-20260904",
    "--tenant", "tenant:one",
    "--actor", "service:controller",
    "--permission", "generation:execute",
    "--method", "POST",
    "--path", "/api/generation/jobs",
    "--ttl-seconds", "60",
  ], { encoding: "utf8" }).trim();
  assert.deepEqual(verifyAt(issued, new Date()), {
    tenantId: "tenant:one",
    actor: "service:controller",
  });
  console.log("local Runner service credential verification: PASS");
} finally {
  await rm(root, { recursive: true, force: true });
}

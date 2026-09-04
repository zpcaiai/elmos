import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";
import {
  chmodSync,
  mkdtempSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  authenticateSpringEngineRequest,
  signSpringEngineRequest,
} from "./springEngineAuth.ts";

const secret = Buffer.from("0123456789abcdef0123456789abcdef", "utf8");
const timestamp = 1_788_542_400;
const nonce = "123e4567-e89b-42d3-a456-426614174000";
const requestPath = "/engine/v1/spring-upgrades/capabilities";
const organizationId = "tenant:alpha";
const actorId = "user:alice";
const body = "";
const bodySha256 = createHash("sha256").update(body).digest("hex");
const canonical = [
  String(timestamp),
  nonce,
  "GET",
  requestPath,
  organizationId,
  actorId,
  bodySha256,
].join("\n");

const signed = signSpringEngineRequest({
  method: "get",
  requestPath,
  organizationId,
  actorId,
  body,
  secret,
  timestamp,
  nonce,
});
assert.deepEqual(signed, {
  timestamp: String(timestamp),
  nonce,
  bodySha256,
  signature: createHmac("sha256", secret).update(canonical).digest("hex"),
});

const runId = "123e4567-e89b-42d3-a456-426614174000";
for (const allowedPath of [
  "/engine/v1/spring-upgrades",
  `/engine/v1/spring-upgrades/${runId}`,
  `/engine/v1/spring-upgrades/${runId}/logs`,
  `/engine/v1/spring-upgrades/${runId}/artifact`,
  `/engine/v1/spring-upgrades/${runId}/retry`,
  `/engine/v1/spring-upgrades/${runId}/cancel`,
  `/engine/v1/spring-upgrades/${runId}/runtime/start`,
  `/engine/v1/spring-upgrades/${runId}/runtime/stop`,
]) {
  assert.doesNotThrow(() => signSpringEngineRequest({
    method: "POST",
    requestPath: allowedPath,
    organizationId,
    actorId,
    body: "{}",
    secret,
    timestamp,
    nonce,
  }));
}

for (const [expected, overrides] of [
  ["SPRING_ENGINE_METHOD_REJECTED", { method: "DELETE" }],
  ["SPRING_ENGINE_PATH_REJECTED", { requestPath: `${requestPath}?admin=true` }],
  ["SPRING_ENGINE_PATH_REJECTED", { requestPath: "/engine/v1/spring-upgrades/../admin" }],
  ["SPRING_ENGINE_ORGANIZATION_REJECTED", { organizationId: "tenant alpha" }],
  ["SPRING_ENGINE_ACTOR_REJECTED", { actorId: "x" }],
  ["SPRING_ENGINE_TIMESTAMP_REJECTED", { timestamp: 0 }],
  ["SPRING_ENGINE_NONCE_REJECTED", { nonce: "00000000-0000-0000-0000-000000000000" }],
  ["SPRING_ENGINE_SECRET_REJECTED", { secret: Buffer.from("too-short") }],
]) {
  assert.throws(
    () => signSpringEngineRequest({
      method: "GET",
      requestPath,
      organizationId,
      actorId,
      body,
      secret,
      timestamp,
      nonce,
      ...overrides,
    }),
    (error) => error instanceof Error && error.message === expected,
  );
}

const priorEnabled = process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED;
const priorSecretFile = process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE;
const temporaryRoot = mkdtempSync(
  path.join(realpathSync(os.tmpdir()), "elmos-spring-auth-"),
);
const secretFile = path.join(temporaryRoot, "engine-auth.key");
try {
  delete process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE;
  process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED = "false";
  const unsigned = authenticateSpringEngineRequest("GET", requestPath, {
    "X-ELMOS-Organization-ID": organizationId,
    "X-ELMOS-Actor-ID": actorId,
  });
  assert.equal(unsigned.get("X-ELMOS-Engine-Signature"), null);

  process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED = "true";
  assert.throws(
    () => authenticateSpringEngineRequest("GET", requestPath, unsigned),
    (error) => error instanceof Error
      && error.message === "SPRING_ENGINE_AUTH_SECRET_FILE_REQUIRED",
  );

  writeFileSync(secretFile, secret, { mode: 0o600 });
  chmodSync(secretFile, 0o600);
  process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE = secretFile;
  const authenticated = authenticateSpringEngineRequest("POST", requestPath, {
    "X-ELMOS-Organization-ID": organizationId,
    "X-ELMOS-Actor-ID": actorId,
    "X-ELMOS-Engine-Signature": "attacker-controlled",
  }, "{}");
  assert.match(authenticated.get("X-ELMOS-Engine-Timestamp") ?? "", /^[0-9]+$/);
  assert.match(
    authenticated.get("X-ELMOS-Engine-Nonce") ?? "",
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.equal(
    authenticated.get("X-ELMOS-Engine-Body-SHA256"),
    createHash("sha256").update("{}").digest("hex"),
  );
  assert.match(authenticated.get("X-ELMOS-Engine-Signature") ?? "", /^[0-9a-f]{64}$/);
  assert.notEqual(authenticated.get("X-ELMOS-Engine-Signature"), "attacker-controlled");

  chmodSync(secretFile, 0o644);
  assert.throws(
    () => authenticateSpringEngineRequest("GET", requestPath, unsigned),
    (error) => error instanceof Error
      && error.message === "SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED",
  );
} finally {
  if (priorEnabled === undefined) delete process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED;
  else process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED = priorEnabled;
  if (priorSecretFile === undefined) delete process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE;
  else process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE = priorSecretFile;
  rmSync(temporaryRoot, { recursive: true, force: true });
}

console.log("spring engine request authentication: deterministic and negative checks passed");

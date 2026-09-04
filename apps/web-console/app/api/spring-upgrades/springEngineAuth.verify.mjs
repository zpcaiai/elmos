import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";
import {
  chmodSync,
  linkSync,
  mkdtempSync,
  realpathSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  authenticateSpringEngineRequest,
  signSpringEngineRequest,
} from "./springEngineAuth.ts";

const secret = Buffer.from("spring-engine-bff-test-secret-00000000000000", "utf8");
const input = {
  method: "POST",
  requestPath: "/engine/v1/spring-upgrades",
  organizationId: "org-production-a",
  actorId: "user:operator-a",
  body: "{\"organizationId\":\"org-production-a\"}",
  secret,
  timestamp: 1_788_508_800,
  nonce: "123e4567-e89b-42d3-a456-426614174000",
};
const signed = signSpringEngineRequest(input);
const canonical = [
  "ELMOS-SPRING-ENGINE-HMAC-V1", "ENGINE",
  String(input.timestamp), input.nonce, input.method, input.requestPath,
  input.organizationId, input.actorId,
  createHash("sha256").update(input.body).digest("hex"),
].join("\n");
assert.equal(
  signed.signature,
  createHmac("sha256", secret).update(canonical).digest("hex"),
);
assert.equal(signed.bodySha256, createHash("sha256").update(input.body).digest("hex"));
assert.throws(
  () => signSpringEngineRequest({ ...input, requestPath: "https://attacker.test/" }),
  /SPRING_ENGINE_PATH_REJECTED/,
);
assert.throws(
  () => signSpringEngineRequest({
    ...input,
    requestPath: "/engine/v1/spring-upgrades/run/../artifact",
  }),
  /SPRING_ENGINE_PATH_REJECTED/,
);
assert.throws(
  () => signSpringEngineRequest({ ...input, organizationId: "../other" }),
  /SPRING_ENGINE_ORGANIZATION_REJECTED/,
);

const directory = realpathSync(
  mkdtempSync(path.join(tmpdir(), "elmos-spring-engine-auth-")),
);
const secretFile = path.join(directory, "secret");
const previousEnabled = process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED;
const previousSecret = process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE;
try {
  writeFileSync(secretFile, secret, { mode: 0o600, flag: "wx" });
  process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED = "true";
  process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE = secretFile;
  const headers = authenticateSpringEngineRequest(
    "POST",
    input.requestPath,
    {
      "X-ELMOS-Organization-ID": input.organizationId,
      "X-ELMOS-Actor-ID": input.actorId,
    },
    input.body,
  );
  assert.match(headers.get("X-ELMOS-Engine-Timestamp") ?? "", /^[0-9]+$/);
  assert.match(
    headers.get("X-ELMOS-Engine-Nonce") ?? "",
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.equal(headers.get("X-ELMOS-Engine-Body-SHA256"), signed.bodySha256);
  assert.match(headers.get("X-ELMOS-Engine-Signature") ?? "", /^[0-9a-f]{64}$/);

  chmodSync(secretFile, 0o644);
  assert.throws(
    () => authenticateSpringEngineRequest(
      "POST", input.requestPath,
      { "X-ELMOS-Organization-ID": input.organizationId, "X-ELMOS-Actor-ID": input.actorId },
      input.body,
    ),
    /SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED/,
  );

  chmodSync(secretFile, 0o600);
  const hardlink = path.join(directory, "secret-hardlink");
  linkSync(secretFile, hardlink);
  assert.throws(
    () => authenticateSpringEngineRequest(
      "POST", input.requestPath,
      { "X-ELMOS-Organization-ID": input.organizationId, "X-ELMOS-Actor-ID": input.actorId },
      input.body,
    ),
    /SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED/,
  );
  unlinkSync(hardlink);

  chmodSync(secretFile, 0o000);
  assert.throws(
    () => authenticateSpringEngineRequest(
      "POST", input.requestPath,
      { "X-ELMOS-Organization-ID": input.organizationId, "X-ELMOS-Actor-ID": input.actorId },
      input.body,
    ),
    /SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED/,
  );

  chmodSync(secretFile, 0o600);
  for (const whitespace of ["\u0085", "\u2003", "\ufeff"]) {
    writeFileSync(secretFile, Buffer.concat([secret, Buffer.from(whitespace, "utf8")]));
    assert.throws(
      () => authenticateSpringEngineRequest(
        "POST", input.requestPath,
        { "X-ELMOS-Organization-ID": input.organizationId, "X-ELMOS-Actor-ID": input.actorId },
        input.body,
      ),
      /SPRING_ENGINE_AUTH_SECRET_FILE_REJECTED/,
    );
  }

  process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED = "false";
  const unsigned = authenticateSpringEngineRequest(
    "POST", input.requestPath,
    { "X-ELMOS-Organization-ID": input.organizationId, "X-ELMOS-Actor-ID": input.actorId },
    input.body,
  );
  assert.equal(unsigned.has("X-ELMOS-Engine-Signature"), false);
} finally {
  if (previousEnabled === undefined) delete process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED;
  else process.env.ELMOS_SPRING_ENGINE_AUTH_ENABLED = previousEnabled;
  if (previousSecret === undefined) delete process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE;
  else process.env.ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE = previousSecret;
  rmSync(directory, { recursive: true, force: true });
}

console.log("spring engine BFF request authentication: PASS");

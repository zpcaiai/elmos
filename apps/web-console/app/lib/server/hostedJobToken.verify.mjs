import assert from "node:assert/strict";
import { createPrivateKey, createPublicKey, generateKeyPairSync } from "node:crypto";
import {
  HostedJobTokenError,
  issueHostedJobToken,
  rejectLocalRunnerInProduction,
  verifyHostedJobToken,
} from "./hostedJobToken.ts";

const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const now = 1_700_000_000;
const image = "ghcr.io/elmos/generation-runner@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const claims = {
  jti: "jti-0123456789abcdef",
  tenant: "tenant-alpha",
  actor: "actor-one",
  job: "job-0123456789abcdef",
  scope: ["generate", "build"],
  image,
  limits: { cpu_millis: 1000, memory_mib: 512, pids: 64, wallclock_seconds: 600 },
  iat: now,
  exp: now + 600,
};

const token = issueHostedJobToken(claims, privateKey, "dispatcher-1");
const seen = new Set();
const verified = verifyHostedJobToken(token, publicKey, "dispatcher-1", "generate", seen, now + 1);
assert.equal(verified.tenant, "tenant-alpha");
assert.throws(
  () => verifyHostedJobToken(token, publicKey, "dispatcher-1", "generate", seen, now + 2),
  (error) => error instanceof HostedJobTokenError && error.code === "JOB_TOKEN_REPLAYED",
);
assert.throws(
  () => issueHostedJobToken({ ...claims, image: "busybox:latest" }, privateKey, "dispatcher-1"),
  (error) => error instanceof HostedJobTokenError && error.code === "JOB_TOKEN_IMAGE_NOT_DIGEST_PINNED",
);
assert.throws(
  () => rejectLocalRunnerInProduction({
    ELMOS_ENVIRONMENT: "production",
    ELMOS_HOSTED_RUNNER_ENABLED: "true",
    ELMOS_LOCAL_RUNNER_AUTH_TOKEN: "x".repeat(32),
  }),
  (error) => error instanceof HostedJobTokenError && error.code === "LOCAL_RUNNER_TOKEN_FORBIDDEN_IN_PRODUCTION",
);
assert.ok(createPrivateKey(privateKey.export({ type: "pkcs8", format: "pem" })));
assert.ok(createPublicKey(publicKey.export({ type: "spki", format: "pem" })));
console.log("hosted job token verify passed");

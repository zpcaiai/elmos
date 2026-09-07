import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalizeMiniappConversionRequest,
  MiniappContractValidationError,
  normalizeMiniappRelativePath,
  validateMiniappConversionRequest,
} from "../src/miniapp-contract-validation.js";
import {
  MINIAPP_EVIDENCE_STATES,
  MINIAPP_PLATFORMS,
  MINIAPP_SOURCE_LABELS,
  type MiniappConversionRequest,
} from "../src/miniapp-types.js";

const digestA = `sha256:${"a".repeat(64)}`;
const digestB = `sha256:${"b".repeat(64)}`;

function validRequest(): Record<string, unknown> {
  return {
    schemaVersion: "1.0",
    requestId: "conv-miniapp-001",
    tenantId: "tenant-demo",
    source: {
      root: "apps/client",
      revision: "0123456789abcdef",
      snapshotDigest: digestA,
      sourceLabel: "react",
      frameworkVersion: "19.2.7",
      languageVersion: "5.9.2",
      runtimeVersion: "24.3.0",
      buildToolVersion: "7.1.3",
    },
    targets: [
      { platform: "xiaohongshu", platformVersion: "1.2.0", toolchainVersion: "2.4.1" },
      { platform: "wechat", platformVersion: "3.9.1", toolchainVersion: "1.06.2504010" },
    ],
    policy: {
      priority: "balanced",
      webviewFallback: "deny",
      fullPageCanvasFallback: "deny",
      unsupportedPolicy: "block",
      limits: { maxFileCount: 500, maxFileBytes: 1048576, maxTotalBytes: 8388608 },
      secretReferences: [
        { name: "wechat-secret", reference: "vault://tenant-demo/wechat/app-secret" },
        { name: "alipay-key", reference: "kms://tenant-demo/alipay/signing-key" },
      ],
    },
    evidence: [
      {
        role: "source-snapshot",
        uri: "artifact://run/source-snapshot",
        digest: digestB,
        state: "PASSED",
        executor: "inventory-worker",
        verifier: "evidence-worker",
        synthetic: false,
        byteCount: 1234,
      },
    ],
  };
}

test("the contract exposes exactly four target platforms and ten source labels", () => {
  assert.deepEqual(MINIAPP_PLATFORMS, ["wechat", "alipay", "douyin", "xiaohongshu"]);
  assert.deepEqual(MINIAPP_SOURCE_LABELS, [
    "vue2", "vue3", "react", "flutter", "h5", "typescript", "javascript", "taro", "uni-app", "native-miniapp",
  ]);
  assert.deepEqual(MINIAPP_EVIDENCE_STATES, ["PASSED", "FAILED", "INCONCLUSIVE", "NOT_RUN"]);
});

test("strict conversion requests retain exact tuples and normalize order deterministically", () => {
  const parsed = validateMiniappConversionRequest(validRequest());
  assert.deepEqual(parsed.targets.map(target => target.platform), ["wechat", "xiaohongshu"]);
  assert.deepEqual(parsed.policy.secretReferences.map(reference => reference.name), ["alipay-key", "wechat-secret"]);
  assert.equal(parsed.source.frameworkVersion, "19.2.7");
  assert.equal(parsed.source.snapshotDigest, digestA);

  const reordered = validRequest();
  reordered.targets = [...(reordered.targets as unknown[])].reverse();
  const policy = reordered.policy as Record<string, unknown>;
  policy.secretReferences = [...(policy.secretReferences as unknown[])].reverse();
  assert.equal(
    canonicalizeMiniappConversionRequest(parsed),
    canonicalizeMiniappConversionRequest(validateMiniappConversionRequest(reordered)),
  );
});

test("every evidence state is explicit and survives validation", () => {
  for (const state of MINIAPP_EVIDENCE_STATES) {
    const request = validRequest();
    const evidence = (request.evidence as Array<Record<string, unknown>>)[0]!;
    evidence.state = state;
    assert.equal(validateMiniappConversionRequest(request).evidence[0]!.state, state);
  }
});

test("additional properties fail closed at every request level", () => {
  const rootExtra = validRequest();
  rootExtra.unexpected = true;
  assert.throws(() => validateMiniappConversionRequest(rootExtra), (error: unknown) =>
    error instanceof MiniappContractValidationError && error.path === "request.unexpected");

  const nestedExtra = validRequest();
  (nestedExtra.source as Record<string, unknown>).mutableBranch = "main";
  assert.throws(() => validateMiniappConversionRequest(nestedExtra), (error: unknown) =>
    error instanceof MiniappContractValidationError && error.path === "request.source.mutableBranch");

  const evidenceExtra = validRequest();
  (evidenceExtra.evidence as Array<Record<string, unknown>>)[0]!.claim = "certified";
  assert.throws(() => validateMiniappConversionRequest(evidenceExtra), (error: unknown) =>
    error instanceof MiniappContractValidationError && error.path === "request.evidence[0].claim");
});

test("mutable versions, malformed digests, duplicate targets, and raw secrets are rejected", () => {
  const mutableVersion = validRequest();
  (mutableVersion.source as Record<string, unknown>).frameworkVersion = "^19.0.0";
  assert.throws(() => validateMiniappConversionRequest(mutableVersion), /frameworkVersion: has an invalid format/u);

  const latestVersion = validRequest();
  ((latestVersion.targets as Array<Record<string, unknown>>)[0]!).toolchainVersion = "latest";
  assert.throws(() => validateMiniappConversionRequest(latestVersion), /toolchainVersion: has an invalid format/u);

  const badDigest = validRequest();
  (badDigest.source as Record<string, unknown>).snapshotDigest = "abc";
  assert.throws(() => validateMiniappConversionRequest(badDigest), /snapshotDigest: has an invalid format/u);

  const duplicate = validRequest();
  duplicate.targets = [
    { platform: "wechat", platformVersion: "3.9.1", toolchainVersion: "1.2.3" },
    { platform: "wechat", platformVersion: "3.9.2", toolchainVersion: "1.2.4" },
  ];
  assert.throws(() => validateMiniappConversionRequest(duplicate), /duplicate platform wechat/u);

  const rawSecret = validRequest();
  const policy = rawSecret.policy as Record<string, unknown>;
  policy.secretReferences = [{ name: "wechat-secret", reference: "actual-secret-value" }];
  assert.throws(() => validateMiniappConversionRequest(rawSecret), /secretReferences\[0\]\.reference: has an invalid format/u);
});

test("relative source roots reject traversal, absolute forms, and encoded traversal", () => {
  assert.equal(normalizeMiniappRelativePath("apps/client", "path"), "apps/client");
  assert.equal(normalizeMiniappRelativePath(".", "path"), ".");
  for (const path of ["../client", "apps/../client", "/private/client", "C:/client", "apps\\client", "%2e%2e/client"]) {
    assert.throws(() => normalizeMiniappRelativePath(path, "path"), MiniappContractValidationError, path);
  }
});

test("canonicalization validates its typed input instead of trusting a cast", () => {
  const request = validateMiniappConversionRequest(validRequest());
  const tampered = { ...request, rogue: true } as MiniappConversionRequest;
  assert.throws(() => canonicalizeMiniappConversionRequest(tampered), /request\.rogue: is not allowed/u);
});

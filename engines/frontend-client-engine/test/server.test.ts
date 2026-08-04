import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { createFrontendClientServer } from "../src/server.js";
import {
  DenyAllFrtEvidenceResolver,
  FrtTrustStore,
  encodeFrtIdentityToken,
} from "../src/frt-security.js";
import type { FrtExecutionScope } from "../src/frt-types.js";
import { FileFrtRunStore } from "../src/frt-run-store.js";

const frtScope = {
  organizationId: "org-http-frt",
  tenantId: "tenant-http-frt",
  workspaceId: "workspace-http-frt",
  projectId: "project-http-frt",
  accountId: "account-http-frt",
  environmentId: "environment-http-frt",
  releaseId: "release-http-frt",
} as const;
const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const authority = "http-test-authority";
const keyId = "http-test-key";
const now = new Date("2026-08-01T00:00:00Z");
const security = {
  trustStore: new FrtTrustStore({
    schemaVersion: "1.0",
    keys: [{
      keyId,
      authority,
      publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
      purposes: ["IDENTITY"],
      activeFrom: "2026-01-01T00:00:00Z",
      expiresAt: "2027-01-01T00:00:00Z",
      revoked: false,
    }],
  }),
  evidenceResolver: new DenyAllFrtEvidenceResolver(),
  now: () => now,
};

function identityToken(options: {
  readonly scope?: FrtExecutionScope;
  readonly permissions?: readonly ("frt:plan" | "frt:run" | "frt:read" | "frt:evidence")[];
  readonly expiresAt?: string;
} = {}): string {
  return encodeFrtIdentityToken({
    schemaVersion: "1.0",
    authority,
    keyId,
    claims: {
      schemaVersion: "1.0",
      subject: "operator-http-frt",
      permissions: options.permissions ?? ["frt:plan", "frt:run", "frt:read", "frt:evidence"],
      scope: options.scope ?? frtScope,
      issuedAt: "2026-07-31T00:00:00Z",
      expiresAt: options.expiresAt ?? "2026-08-02T00:00:00Z",
      nonce: `nonce-${options.scope?.tenantId ?? "default"}-${options.permissions?.join("-") ?? "all"}`,
    },
  }, privateKey);
}

const frtAuthorization = { authorization: `Bearer ${identityToken()}` };
const serverRunStoreRoot = mkdtempSync(join(tmpdir(), "elmos-frt-http-runs-"));
const server = createFrontendClientServer({
  frtSecurity: security,
  frtRunStore: new FileFrtRunStore(serverRunStoreRoot),
});

let baseUrl = "";

before(async () => {
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  rmSync(serverRunStoreRoot, { recursive: true, force: true });
});

test("HTTP capabilities disclose every unconfigured Runner profile", async () => {
  const response = await fetch(`${baseUrl}/engine/v1/capabilities`);
  const body = await response.json() as { engine: string; runnerProfiles: Record<string, string>; customerCodeExecution: string; jobStatePersistence: string; durableStateAuthority: string };
  assert.equal(response.status, 200);
  assert.equal(body.engine, "ELMOS_FRONTEND_CLIENT");
  assert.ok(Object.values(body.runnerProfiles).every(value => value === "NOT_CONFIGURED"));
  assert.equal(body.customerCodeExecution, "RUNNER_REQUIRED_FAIL_CLOSED");
  assert.equal(body.jobStatePersistence, "EPHEMERAL_PROCESS_LOCAL");
  assert.equal(body.durableStateAuthority, "ELMOS_CONTROL_PLANE");
});

test("HTTP UI project capabilities expose exact profiles and fail-closed routes", async () => {
  const response = await fetch(`${baseUrl}/engine/v1/ui-projects/capabilities`);
  const body = await response.json() as {
    directedRouteCount: number;
    exactTargetProfiles: Array<{ id: string; frameworkVersion: string }>;
    directedRoutes: Array<{ semanticConversionEvidence: string; certification: string }>;
    runtimeEvidence: string;
  };
  assert.equal(response.status, 200);
  assert.equal(body.exactTargetProfiles.length, 9);
  assert.equal(body.directedRouteCount, 72);
  assert.ok(body.directedRoutes.every(route => route.semanticConversionEvidence === "NOT_RUN"));
  assert.ok(body.directedRoutes.every(route => route.certification === "NOT_CERTIFIED"));
  assert.equal(body.runtimeEvidence, "NOT_RUN");
});

test("HTTP execute-step accepts the job transport but returns terminal fail-closed state", async () => {
  const response = await fetch(`${baseUrl}/engine/v1/execute-step`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ organizationId: "org-http", snapshotId: "snap", idempotencyKey: "exec",
      workspaceRef: "app", planId: "plan", stepId: "route", runnerProfile: "MODERN_WEB" })
  });
  const body = await response.json() as { status: string; evidenceRefs: string[]; result: Record<string, boolean> };
  assert.equal(response.status, 202);
  assert.equal(body.status, "FAILED");
  assert.deepEqual(body.evidenceRefs, []);
  assert.equal(body.result.customerCodeExecuted, false);
});

test("HTTP idempotency conflict and tenant-scoped job visibility use 409 and 404", async () => {
  const request = { organizationId: "org-http", snapshotId: "snap", idempotencyKey: "scan",
    workspaceRef: "app", input: { files: { "package.json": "{}", "package-lock.json": "{}" } } };
  const first = await fetch(`${baseUrl}/engine/v1/scan`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
  const firstBody = await first.json() as { jobId: string };
  const visible = await fetch(`${baseUrl}/engine/v1/jobs/${firstBody.jobId}?organizationId=org-http`);
  assert.equal(visible.status, 200);
  const conflict = await fetch(`${baseUrl}/engine/v1/scan`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...request, snapshotId: "changed" }) });
  assert.equal(conflict.status, 409);
  assert.equal((await conflict.json() as { errorCode: string }).errorCode, "IDEMPOTENCY_CONFLICT");
  const hidden = await fetch(`${baseUrl}/engine/v1/jobs/${firstBody.jobId}?organizationId=org-other`);
  assert.equal(hidden.status, 404);
  assert.equal((await hidden.json() as { errorCode: string }).errorCode, "JOB_NOT_FOUND");
});

test("HTTP contract errors do not disclose parser or payload details", async () => {
  const response = await fetch(`${baseUrl}/engine/v1/scan`, {
    method: "POST", headers: { "content-type": "application/json" }, body: "{private-customer-path"
  });
  const payload = await response.json() as { errorCode: string; message: string };
  assert.equal(response.status, 400);
  assert.equal(payload.errorCode, "FRONTEND_REQUEST_REJECTED");
  assert.equal(payload.message, "The frontend engine request was rejected by its contract.");
  assert.doesNotMatch(payload.message, /private-customer-path|JSON|position/i);
});

test("HTTP FRT catalog and route endpoints expose all implemented Skill contracts", async () => {
  const catalogResponse = await fetch(`${baseUrl}/engine/v1/frt/catalog?batch=G13`);
  const catalog = await catalogResponse.json() as {
    batchCount: number;
    skillCount: number;
    directedRouteCount: number;
    returnedSkillCount: number;
    evidenceBoundary: { production: string; certification: string };
  };
  assert.equal(catalogResponse.status, 200);
  assert.equal(catalog.batchCount, 30);
  assert.equal(catalog.skillCount, 472);
  assert.equal(catalog.directedRouteCount, 30);
  assert.equal(catalog.returnedSkillCount, 11);
  assert.equal(catalog.evidenceBoundary.production, "NOT_RUN");
  assert.equal(catalog.evidenceBoundary.certification, "NOT_CERTIFIED");

  const routesResponse = await fetch(`${baseUrl}/engine/v1/frt/routes`);
  const routes = await routesResponse.json() as { directedRouteCount: number; routes: unknown[] };
  assert.equal(routesResponse.status, 200);
  assert.equal(routes.directedRouteCount, 30);
  assert.equal(routes.routes.length, 30);
});

test("HTTP FRT Skill run fails closed when its prerequisite certificate is missing", async () => {
  const response = await fetch(`${baseUrl}/engine/v1/frt/skills/frt-1305-vue-3-to-react-route-pack/runs`, {
    method: "POST",
    headers: { "content-type": "application/json", ...frtAuthorization },
    body: JSON.stringify({
      schemaVersion: "1.0",
      skillId: "FRT-1305",
      action: "PLAN",
      idempotencyKey: "http-frt-missing-certificate",
      expectedVersion: 0,
      context: {
        ...frtScope,
        sourceSnapshotDigest: `sha256:${"a".repeat(64)}`,
        policyVersion: "frt-policy-1.0.0",
        requestedBy: "operator-http-frt",
        risk: "R4",
      },
      prerequisiteCertificates: [],
      evidence: [],
    }),
  });
  const result = await response.json() as { state: string; outcome: string; certificateFragment: { certification: string } };
  assert.equal(response.status, 202);
  assert.equal(result.state, "BLOCKED");
  assert.equal(result.outcome, "BLOCKED_BY_PREREQUISITE");
  assert.equal(result.certificateFragment.certification, "NOT_CERTIFIED");
});

test("HTTP FRT contract rejects unknown actions and extra fields before dispatch", async () => {
  const validRequest = {
    schemaVersion: "1.0",
    skillId: "FRT-0100",
    action: "PLAN",
    idempotencyKey: "http-frt-contract-negative",
    expectedVersion: 0,
    context: {
      ...frtScope,
      sourceSnapshotDigest: `sha256:${"a".repeat(64)}`,
      policyVersion: "frt-policy-1.0.0",
      requestedBy: "operator-http-frt",
      risk: "R4",
    },
    prerequisiteCertificates: [],
    evidence: [],
  };
  for (const body of [
    { ...validRequest, action: "INVALID_ACTION" },
    { ...validRequest, unexpectedCustomerField: "must-not-be-accepted" },
  ]) {
    const response = await fetch(`${baseUrl}/engine/v1/frt/skills/FRT-0100/runs`, {
      method: "POST",
      headers: { "content-type": "application/json", ...frtAuthorization },
      body: JSON.stringify(body),
    });
    const payload = await response.json() as { errorCode: string; message: string };
    assert.equal(response.status, 400);
    assert.equal(payload.errorCode, "FRONTEND_REQUEST_REJECTED");
    assert.equal(payload.message, "The frontend engine request was rejected by its contract.");
    assert.doesNotMatch(payload.message, /INVALID_ACTION|unexpectedCustomerField/);
  }
});

test("HTTP FRT mutations require a trusted identity, permission, and exact body scope", async () => {
  const validRequest = {
    schemaVersion: "1.0",
    skillId: "FRT-0100",
    action: "PLAN",
    idempotencyKey: "http-frt-auth-negative",
    expectedVersion: 0,
    context: {
      ...frtScope,
      sourceSnapshotDigest: `sha256:${"b".repeat(64)}`,
      policyVersion: "frt-policy-1.0.0",
      requestedBy: "operator-http-frt",
      risk: "R4",
    },
    prerequisiteCertificates: [],
    evidence: [],
  };
  const cases = [
    {
      headers: { "content-type": "application/json" },
      body: validRequest,
      status: 401,
      code: "FRT_AUTHENTICATION_REQUIRED",
    },
    {
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${identityToken({ expiresAt: "2026-07-31T12:00:00Z" })}`,
      },
      body: validRequest,
      status: 401,
      code: "FRT_IDENTITY_EXPIRED",
    },
    {
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${identityToken({ permissions: ["frt:read"] })}`,
      },
      body: validRequest,
      status: 403,
      code: "FRT_PERMISSION_DENIED",
    },
    {
      headers: { "content-type": "application/json", ...frtAuthorization },
      body: { ...validRequest, context: { ...validRequest.context, tenantId: "tenant-attacker" } },
      status: 403,
      code: "FRT_SCOPE_MISMATCH",
    },
  ];
  for (const item of cases) {
    const response = await fetch(`${baseUrl}/engine/v1/frt/skills/FRT-0100/runs`, {
      method: "POST",
      headers: item.headers,
      body: JSON.stringify(item.body),
    });
    assert.equal(response.status, item.status);
    assert.equal((await response.json() as { errorCode: string }).errorCode, item.code);
  }
});

test("HTTP FRT reads derive tenant scope from identity and ignore spoofed query scope", async () => {
  const response = await fetch(`${baseUrl}/engine/v1/frt/skills/FRT-0100/runs`, {
    method: "POST",
    headers: { "content-type": "application/json", ...frtAuthorization },
    body: JSON.stringify({
      schemaVersion: "1.0",
      skillId: "FRT-0100",
      action: "PLAN",
      idempotencyKey: "http-frt-scope-read",
      expectedVersion: 0,
      context: {
        ...frtScope,
        sourceSnapshotDigest: `sha256:${"c".repeat(64)}`,
        policyVersion: "frt-policy-1.0.0",
        requestedBy: "operator-http-frt",
        risk: "R4",
      },
      prerequisiteCertificates: [],
      evidence: [],
    }),
  });
  assert.equal(response.status, 202);
  const result = await response.json() as { runId: string };

  const spoofedQuery = await fetch(
    `${baseUrl}/engine/v1/frt/runs/${result.runId}?organizationId=attacker&tenantId=attacker`,
    { headers: frtAuthorization },
  );
  assert.equal(spoofedQuery.status, 200);

  const crossTenantToken = identityToken({ scope: { ...frtScope, tenantId: "tenant-other" } });
  const hidden = await fetch(`${baseUrl}/engine/v1/frt/runs/${result.runId}`, {
    headers: { authorization: `Bearer ${crossTenantToken}` },
  });
  assert.equal(hidden.status, 404);
  assert.equal((await hidden.json() as { errorCode: string }).errorCode, "FRT_RUN_NOT_FOUND");
});

test("HTTP FRT durable lifecycle exposes optimistic claim, cancel, retry, and audit", async () => {
  const createdResponse = await fetch(`${baseUrl}/engine/v1/frt/skills/FRT-0100/runs`, {
    method: "POST",
    headers: { "content-type": "application/json", ...frtAuthorization },
    body: JSON.stringify({
      schemaVersion: "1.0",
      skillId: "FRT-0100",
      action: "EXECUTE",
      idempotencyKey: "http-frt-durable-lifecycle",
      expectedVersion: 0,
      context: {
        ...frtScope,
        sourceSnapshotDigest: `sha256:${"d".repeat(64)}`,
        policyVersion: "frt-policy-1.0.0",
        requestedBy: "operator-http-frt",
        risk: "R4",
      },
      prerequisiteCertificates: [],
      evidence: [],
    }),
  });
  const created = await createdResponse.json() as { runId: string; state: string; version: number };
  assert.equal(createdResponse.status, 202);
  assert.equal(created.state, "QUEUED");

  const transition = async (operation: "claim" | "cancel" | "retry", expectedVersion: number) => {
    const response = await fetch(`${baseUrl}/engine/v1/frt/runs/${created.runId}/${operation}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...frtAuthorization },
      body: JSON.stringify({ schemaVersion: "1.0", expectedVersion }),
    });
    return { response, body: await response.json() as { state?: string; version?: number; errorCode?: string } };
  };
  const claimed = await transition("claim", created.version);
  assert.equal(claimed.response.status, 200);
  assert.equal(claimed.body.state, "RUNNING");
  const stale = await transition("cancel", created.version);
  assert.equal(stale.response.status, 409);
  assert.equal(stale.body.errorCode, "FRT_RUN_TRANSITION_REJECTED");
  const cancelled = await transition("cancel", claimed.body.version!);
  assert.equal(cancelled.body.state, "CANCELLED");
  const retried = await transition("retry", cancelled.body.version!);
  assert.equal(retried.body.state, "QUEUED");

  const auditResponse = await fetch(`${baseUrl}/engine/v1/frt/runs/${created.runId}/audit`, {
    headers: frtAuthorization,
  });
  const audit = await auditResponse.json() as { audit: Array<{ event: string }> };
  assert.equal(auditResponse.status, 200);
  assert.deepEqual(
    audit.audit.map(item => item.event),
    ["RUN_CREATED", "RUN_CLAIMED", "RUN_CANCELLED", "RUN_RETRIED"],
  );
});

import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";

import { server } from "../src/server.js";

let baseUrl = "";

before(async () => {
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
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

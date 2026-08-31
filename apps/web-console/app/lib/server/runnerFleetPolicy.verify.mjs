import assert from "node:assert/strict";
import {
  relayRunnerFleetMutationResponse,
  relayRunnerFleetResponse,
  RunnerFleetPolicyError,
  runnerFleetListQuery,
  runnerFleetRequiredRole,
  runnerFleetStatuses,
  validateRunnerFleetMutationRequest,
} from "./runnerFleetPolicy.ts";

let checks = 0;

assert.equal(runnerFleetRequiredRole, "VIEWER");
checks += 1;

function acceptedQuery(raw, expected) {
  assert.deepEqual(
    [...runnerFleetListQuery(new URLSearchParams(raw)).entries()],
    [...new URLSearchParams(expected).entries()],
  );
  checks += 1;
}

function rejected(action, status, errorCode) {
  assert.throws(action, (error) => {
    assert.ok(error instanceof RunnerFleetPolicyError);
    assert.equal(error.status, status);
    assert.equal(error.errorCode, errorCode);
    return true;
  });
  checks += 1;
}

async function asyncRejected(action, status, errorCode) {
  await assert.rejects(action, (error) => {
    assert.ok(error instanceof RunnerFleetPolicyError);
    assert.equal(error.status, status);
    assert.equal(error.errorCode, errorCode);
    return true;
  });
  checks += 1;
}

acceptedQuery("", "limit=50");
acceptedQuery("limit=1", "limit=1");
acceptedQuery("limit=100&status=READY", "limit=100&status=READY");
for (const status of runnerFleetStatuses) {
  acceptedQuery(`status=${status}`, `limit=50&status=${status}`);
}

for (const query of [
  "limit=",
  "limit=0",
  "limit=101",
  "limit=01",
  "limit=1.0",
  "limit=%2B1",
  "limit=1&limit=2",
  "status=",
  "status=ready",
  "status=%20READY",
  "status=READY%20",
  "status=UNKNOWN",
  "status=READY&status=LOST",
  "pool=pool-1",
  "offset=0",
]) {
  rejected(
    () => runnerFleetListQuery(new URLSearchParams(query)),
    400,
    "ADMIN_RUNNER_FLEET_QUERY_INVALID",
  );
}

const validNode = {
  runnerNodeId: "runner-1",
  runnerPoolId: "pool-1",
  agentVersion: "1.2.3",
  fleetStatus: "READY",
  capabilities: ["generation:multi"],
  maxConcurrency: 2,
  attestationVerified: true,
  attestationVerifiedAt: "2026-08-09T01:00:00Z",
  imageAllowlistVersion: "allowlist-v1",
  lastHeartbeatAt: "2026-08-09T01:09:55.123456Z",
  drainRequestedAt: null,
  createdAt: "2026-08-09T00:00:00Z",
  updatedAt: "2026-08-09T01:09:55Z",
};
const validResponse = {
  schemaVersion: "1.0.0",
  items: [validNode],
  limit: 50,
  returned: 1,
  truncated: false,
  status: "READY",
};

const relayed = await relayRunnerFleetResponse(Response.json(validResponse));
assert.equal(relayed.status, 200);
assert.equal(relayed.headers.get("cache-control"), "private, no-store, max-age=0");
assert.equal(relayed.headers.get("vary"), "Cookie, Authorization");
assert.deepEqual(await relayed.json(), validResponse);
checks += 4;

for (const invalidResponse of [
  { ...validResponse, schemaVersion: "2.0.0" },
  { ...validResponse, returned: 2 },
  { ...validResponse, items: [{ ...validNode, fleetStatus: "LOST" }] },
  { ...validResponse, items: [{ ...validNode, attestationVerifiedAt: null }] },
  ...[
    "organizationId",
    "enrollmentCredentialId",
    "enrollmentToken",
    "nodeToken",
    "tokenSha256",
    "attestationPayload",
    "verifierActorId",
  ].map((field) => ({
    ...validResponse,
    items: [{ ...validNode, [field]: "must-not-leak" }],
  })),
]) {
  await assert.rejects(
    () => relayRunnerFleetResponse(Response.json(invalidResponse)),
    (error) => {
      assert.ok(error instanceof RunnerFleetPolicyError);
      assert.equal(error.status, 502);
      assert.equal(error.errorCode, "ADMIN_RUNNER_FLEET_RESPONSE_INVALID");
      return true;
    },
  );
  checks += 1;
}

const failurePayload = '{"errorCode":"OPERATIONS_RUNNER_FLEET_FORBIDDEN","retryable":false}';
const relayedFailure = await relayRunnerFleetResponse(new Response(failurePayload, {
  status: 403,
  headers: { "content-type": "application/json; charset=utf-8" },
}));
assert.equal(relayedFailure.status, 403);
assert.equal(await relayedFailure.text(), failurePayload);
assert.equal(relayedFailure.headers.get("cache-control"), "private, no-store, max-age=0");
assert.equal(relayedFailure.headers.get("vary"), "Cookie, Authorization");
checks += 4;

const oidcAccessToken = `oidc-${"a".repeat(64)}`;
const operator = {
  role: "OPERATOR",
  authentication: "OIDC_SESSION",
  accessToken: oidcAccessToken,
};
const approver = {
  role: "APPROVER",
  authentication: "OIDC_SESSION",
  accessToken: oidcAccessToken,
};
const unsupportedCredential = {
  role: "APPROVER",
  authentication: "UNSUPPORTED_CREDENTIAL",
};
const consoleOrigin = "https://console.example.test";

function mutationRequest(path, { origin = consoleOrigin, fetchSite, body } = {}) {
  const headers = {};
  if (origin !== null) headers.origin = origin;
  if (fetchSite !== undefined) headers["sec-fetch-site"] = fetchSite;
  return new Request(`${consoleOrigin}${path}`, {
    method: "POST",
    headers,
    ...(body === undefined ? {} : { body }),
  });
}

for (const profile of [
  { path: "/api/admin/runners/runner-1/drain", principal: operator, role: "OPERATOR" },
  {
    path: "/api/admin/runners/runner-1/attestation/verify",
    principal: approver,
    role: "APPROVER",
  },
]) {
  assert.equal(
    await validateRunnerFleetMutationRequest(
      mutationRequest(profile.path, { fetchSite: "same-origin" }),
      "runner-1",
      profile.principal,
      profile.role,
    ),
    "runner-1",
  );
  checks += 1;

  for (const invalidOrigin of [null, "https://attacker.example", `${consoleOrigin}:444`]) {
    await asyncRejected(
      () => validateRunnerFleetMutationRequest(
        mutationRequest(profile.path, { origin: invalidOrigin, fetchSite: "same-origin" }),
        "runner-1",
        profile.principal,
        profile.role,
      ),
      403,
      "RUNNER_FLEET_SAME_ORIGIN_REQUIRED",
    );
  }
  await asyncRejected(
    () => validateRunnerFleetMutationRequest(
      mutationRequest(profile.path, { fetchSite: "cross-site" }),
      "runner-1",
      profile.principal,
      profile.role,
    ),
    403,
    "RUNNER_FLEET_SAME_ORIGIN_REQUIRED",
  );
  await asyncRejected(
    () => validateRunnerFleetMutationRequest(
      mutationRequest(`${profile.path}?force=true`),
      "runner-1",
      profile.principal,
      profile.role,
    ),
    400,
    "ADMIN_RUNNER_FLEET_MUTATION_QUERY_INVALID",
  );
  await asyncRejected(
    () => validateRunnerFleetMutationRequest(
      mutationRequest(profile.path, { body: "{}" }),
      "runner-1",
      profile.principal,
      profile.role,
    ),
    400,
    "ADMIN_RUNNER_FLEET_MUTATION_BODY_INVALID",
  );
  await asyncRejected(
    () => validateRunnerFleetMutationRequest(
      mutationRequest(profile.path),
      "Runner/../other",
      profile.principal,
      profile.role,
    ),
    400,
    "ADMIN_RUNNER_FLEET_NODE_ID_INVALID",
  );
  await asyncRejected(
    () => validateRunnerFleetMutationRequest(
      mutationRequest(profile.path),
      "runner-1",
      unsupportedCredential,
      profile.role,
    ),
    403,
    "RUNNER_FLEET_OIDC_SESSION_REQUIRED",
  );
}

await asyncRejected(
  () => validateRunnerFleetMutationRequest(
    mutationRequest("/api/admin/runners/runner-1/attestation/verify"),
    "runner-1",
    operator,
    "APPROVER",
  ),
  403,
  "RUNNER_FLEET_ADMIN_ROLE_INSUFFICIENT",
);

for (const mutation of [
  { status: "DRAINING", httpStatus: 202 },
  { status: "READY", httpStatus: 200 },
]) {
  const mutationResponse = await relayRunnerFleetMutationResponse(
    Response.json(
      { status: mutation.status, runnerNodeId: "runner-1" },
      { status: mutation.httpStatus },
    ),
    mutation.status,
    "runner-1",
  );
  assert.equal(mutationResponse.status, mutation.httpStatus);
  assert.equal(mutationResponse.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.equal(mutationResponse.headers.get("vary"), "Cookie, Authorization");
  assert.deepEqual(await mutationResponse.json(), {
    status: mutation.status,
    runnerNodeId: "runner-1",
  });
  checks += 4;
}

for (const invalidMutation of [
  { status: "READY", runnerNodeId: "runner-other" },
  { status: "DRAINING", runnerNodeId: "runner-1", enrollmentToken: "must-not-leak" },
]) {
  await asyncRejected(
    () => relayRunnerFleetMutationResponse(
      Response.json(invalidMutation),
      "READY",
      "runner-1",
    ),
    502,
    "ADMIN_RUNNER_FLEET_RESPONSE_INVALID",
  );
}

console.log(`runner fleet BFF policy: ${checks} checks passed`);

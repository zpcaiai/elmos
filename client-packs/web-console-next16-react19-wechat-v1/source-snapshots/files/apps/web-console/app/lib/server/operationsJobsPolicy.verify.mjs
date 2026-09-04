import assert from "node:assert/strict";
import {
  assertEmptyOperationsJobQuery,
  OperationsJobsPolicyError,
  operationsJobBusinessLines,
  operationsJobId,
  operationsJobListQuery,
  operationsJobStatuses,
  operationsJobsRequiredRoles,
  relayOperationsJobResponse,
} from "./operationsJobsPolicy.ts";

let checks = 0;

assert.deepEqual(operationsJobsRequiredRoles, { list: "VIEWER", cancel: "OPERATOR" });
checks += 1;

function acceptedQuery(raw, expected) {
  assert.deepEqual(
    [...operationsJobListQuery(new URLSearchParams(raw)).entries()],
    [...new URLSearchParams(expected).entries()],
  );
  checks += 1;
}

function rejected(action, errorCode) {
  assert.throws(action, (error) => {
    assert.ok(error instanceof OperationsJobsPolicyError);
    assert.equal(error.errorCode, errorCode);
    return true;
  });
  checks += 1;
}

acceptedQuery("", "limit=50");
acceptedQuery(
  "limit=100&businessLine=MODERNIZATION_PROOF&status=RUNNING",
  "limit=100&businessLine=MODERNIZATION_PROOF&status=RUNNING",
);
for (const businessLine of operationsJobBusinessLines) {
  acceptedQuery(`businessLine=${businessLine}`, `limit=50&businessLine=${businessLine}`);
}
for (const status of operationsJobStatuses) {
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
  "businessLine=",
  "businessLine=generation",
  "businessLine=UNKNOWN",
  "businessLine=GENERATION&businessLine=TRANSLATION",
  "status=",
  "status=running",
  "status=UNKNOWN",
  "status=RUNNING&status=FAILED",
  "offset=0",
]) {
  rejected(
    () => operationsJobListQuery(new URLSearchParams(query)),
    "ADMIN_JOBS_QUERY_INVALID",
  );
}

for (const jobId of ["job-1", "job.one:two_three", `a${"b".repeat(127)}`]) {
  assert.equal(operationsJobId(jobId), jobId);
  checks += 1;
}
for (const jobId of [
  undefined,
  null,
  1,
  "",
  "-job",
  "job/1",
  "job 1",
  "作业-1",
  `a${"b".repeat(128)}`,
]) {
  rejected(() => operationsJobId(jobId), "ADMIN_JOB_ID_INVALID");
}

assert.doesNotThrow(() => assertEmptyOperationsJobQuery(new URLSearchParams()));
checks += 1;
rejected(
  () => assertEmptyOperationsJobQuery(new URLSearchParams("force=true")),
  "ADMIN_JOBS_QUERY_INVALID",
);

for (const [status, payload] of [
  [200, '{"idempotentReplay":true}'],
  [202, '{"idempotentReplay":false}'],
  [409, '{"errorCode":"ELMOS_EXECUTION_JOB_TERMINAL"}'],
]) {
  const relayed = await relayOperationsJobResponse(new Response(payload, {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  }));
  assert.equal(relayed.status, status);
  assert.equal(await relayed.text(), payload);
  assert.equal(relayed.headers.get("cache-control"), "no-store, private");
  assert.equal(relayed.headers.get("vary"), "Authorization");
  checks += 1;
}

console.log(`operations jobs BFF policy: ${checks} checks passed`);

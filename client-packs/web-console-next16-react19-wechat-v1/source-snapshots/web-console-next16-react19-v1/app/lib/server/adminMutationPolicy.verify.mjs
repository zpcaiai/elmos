import assert from "node:assert/strict";
import {
  AdminMutationPolicyError,
  assertEmptyAdminMutationBody,
  assertAdminMutationOrigin,
  readBoundedAdminJsonObject,
} from "./adminMutationPolicy.ts";

let checks = 0;

function request(origin, fetchSite) {
  const headers = {};
  if (origin !== undefined) headers.origin = origin;
  if (fetchSite !== undefined) headers["sec-fetch-site"] = fetchSite;
  return new Request("https://console.example.test/api/admin/operations", {
    method: "POST",
    headers,
  });
}

for (const uncredentialed of [
  request(undefined, undefined),
  request("https://attacker.example", "cross-site"),
]) {
  assert.doesNotThrow(() => assertAdminMutationOrigin(uncredentialed, false));
  checks += 1;
}

for (const sameOrigin of [
  request("https://console.example.test", undefined),
  request("https://console.example.test", "same-origin"),
]) {
  assert.doesNotThrow(() => assertAdminMutationOrigin(sameOrigin, true));
  checks += 1;
}

for (const rejected of [
  request(undefined, undefined),
  request("null", "cross-site"),
  request("https://attacker.example", "cross-site"),
  request("https://console.example.test:444", "same-origin"),
  request("https://console.example.test", "same-site"),
  request("https://console.example.test", "none"),
]) {
  assert.throws(
    () => assertAdminMutationOrigin(rejected, true),
    (error) => {
      assert.ok(error instanceof AdminMutationPolicyError);
      assert.equal(error.status, 403);
      assert.equal(error.errorCode, "ADMIN_MUTATION_SAME_ORIGIN_REQUIRED");
      return true;
    },
  );
  checks += 1;
}

const jsonRequest = (body, headers = {}) => new Request(
  "https://console.example.test/api/admin/operations",
  {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body,
  },
);

assert.deepEqual(await readBoundedAdminJsonObject(jsonRequest('{"action":"EVALUATE"}')), {
  action: "EVALUATE",
});
checks += 1;

for (const [candidate, status, errorCode] of [
  [new Request("https://console.example.test/api/admin/operations", { method: "POST" }), 415, "ADMIN_MUTATION_CONTENT_TYPE_INVALID"],
  [jsonRequest("[]"), 400, "ADMIN_MUTATION_BODY_INVALID"],
  [jsonRequest("{"), 400, "ADMIN_MUTATION_BODY_INVALID"],
  [jsonRequest(`{"value":"${"x".repeat(32)}"}`), 413, "ADMIN_MUTATION_BODY_TOO_LARGE"],
]) {
  await assert.rejects(
    readBoundedAdminJsonObject(candidate, 16),
    (error) => {
      assert.ok(error instanceof AdminMutationPolicyError);
      assert.equal(error.status, status);
      assert.equal(error.errorCode, errorCode);
      return true;
    },
  );
  checks += 1;
}

await assertEmptyAdminMutationBody(new Request(
  "https://console.example.test/api/admin/jobs/job-1/cancel",
  { method: "POST" },
));
checks += 1;
await assert.rejects(
  assertEmptyAdminMutationBody(new Request(
    "https://console.example.test/api/admin/jobs/job-1/cancel",
    { method: "POST", body: "{}" },
  )),
  (error) => {
    assert.ok(error instanceof AdminMutationPolicyError);
    assert.equal(error.status, 400);
    assert.equal(error.errorCode, "ADMIN_MUTATION_BODY_INVALID");
    return true;
  },
);
checks += 1;

console.log(`admin cookie mutation policy: ${checks} checks passed`);

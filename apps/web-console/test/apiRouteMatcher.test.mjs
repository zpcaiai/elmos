import assert from "node:assert/strict";
import test from "node:test";
import { compileRoutes, matchRoute } from "../app/api/_routeMatcher.ts";

const routes = compileRoutes([
  { template: "jobs/[jobId]", value: "job" },
  { template: "jobs/gc", value: "gc" },
  { template: "files/[...path]", value: "files" },
  { template: "account/[[...path]]", value: "account" },
]);

test("static routes win over dynamic siblings", () => {
  assert.deepEqual(matchRoute(["jobs", "gc"], routes), { value: "gc", params: {} });
  assert.deepEqual(matchRoute(["jobs", "job-7"], routes), {
    value: "job",
    params: { jobId: "job-7" },
  });
});

test("catch-all routes preserve array and optional parameter semantics", () => {
  assert.deepEqual(matchRoute(["files", "a", "b"], routes), {
    value: "files",
    params: { path: ["a", "b"] },
  });
  assert.equal(matchRoute(["files"], routes), null);
  assert.deepEqual(matchRoute(["account"], routes), {
    value: "account",
    params: { path: undefined },
  });
});

test("unknown routes do not fall through to another handler", () => {
  assert.equal(matchRoute(["unknown"], routes), null);
});

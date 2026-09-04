import assert from "node:assert/strict";
import test from "node:test";

import {
  executionQueueMode,
  hostedExecutionRequired,
  localFilesystemExecutionAllowed,
} from "../app/lib/server/executionQueuePolicy.ts";

test("production always selects hosted execution even when the opt-in flag is absent or false", () => {
  for (const value of [undefined, "false", "FALSE", "0"]) {
    const environment = { NODE_ENV: "production", ELMOS_HOSTED_EXECUTION_ENABLED: value };
    assert.equal(executionQueueMode(environment), "HOSTED");
    assert.equal(hostedExecutionRequired(environment), true);
    assert.equal(localFilesystemExecutionAllowed(environment), false);
  }
});

test("development remains backward compatible and only exact true opts into hosted execution", () => {
  assert.equal(executionQueueMode({ NODE_ENV: "development" }), "LOCAL_DEVELOPMENT");
  assert.equal(executionQueueMode({
    NODE_ENV: "test",
    ELMOS_HOSTED_EXECUTION_ENABLED: "false",
  }), "LOCAL_DEVELOPMENT");
  assert.equal(executionQueueMode({
    NODE_ENV: "development",
    ELMOS_HOSTED_EXECUTION_ENABLED: "true",
  }), "HOSTED");
});

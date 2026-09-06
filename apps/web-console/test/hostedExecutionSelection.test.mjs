import assert from "node:assert/strict";
import test from "node:test";
import { hostedExecutionEnabled, getHostedGenerationJob } from "../app/lib/server/hostedExecutionClient.ts";

test("actual hosted client cannot downgrade production to the filesystem queue", async (context) => {
  const names = ["NODE_ENV", "ELMOS_HOSTED_EXECUTION_ENABLED", "ELMOS_CONTROL_PLANE_BASE_URL"];
  const saved = Object.fromEntries(names.map((name) => [name, process.env[name]]));
  context.after(() => {
    for (const name of names) {
      if (saved[name] === undefined) delete process.env[name];
      else process.env[name] = saved[name];
    }
  });
  process.env.NODE_ENV = "production";
  delete process.env.ELMOS_CONTROL_PLANE_BASE_URL;
  for (const flag of [undefined, "false", "true"]) {
    if (flag === undefined) delete process.env.ELMOS_HOSTED_EXECUTION_ENABLED;
    else process.env.ELMOS_HOSTED_EXECUTION_ENABLED = flag;
    assert.equal(hostedExecutionEnabled(), true);
  }
  await assert.rejects(getHostedGenerationJob({ tenantId: "tenant-a", actor: "actor-a",
    accessToken: "test-only" }, "job-a"), { message: "CONTROL_PLANE_NOT_CONFIGURED" });
  process.env.NODE_ENV = "development";
  process.env.ELMOS_HOSTED_EXECUTION_ENABLED = "false";
  assert.equal(hostedExecutionEnabled(), false);
});

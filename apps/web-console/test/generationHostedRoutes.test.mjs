import assert from "node:assert/strict";
import test from "node:test";

// Route handlers are imported directly: in hosted mode the fail-closed
// branch runs before authentication and before any runner configuration,
// so a plain Request is enough to prove the boundary.
import { GET as previewRoute } from "../app/api/generation/jobs/[jobId]/preview/_route.ts";
import { POST as runRoute } from "../app/api/generation/jobs/[jobId]/run/_route.ts";
import { POST as stopRoute } from "../app/api/generation/jobs/[jobId]/stop/_route.ts";
import { POST as githubRoute } from "../app/api/generation/jobs/[jobId]/github/_route.ts";

const ENV_NAMES = [
  "NODE_ENV",
  "ELMOS_HOSTED_EXECUTION_ENABLED",
  "ELMOS_LOCAL_RUNNER_ENABLED",
  "ELMOS_LOCAL_RUNNER_AUTH_TOKEN",
  "ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE",
  "ELMOS_LOCAL_RUNNER_TENANT_ID",
  "ELMOS_LOCAL_RUNNER_ACTOR_ID",
  "ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT",
  "ELMOS_LOCAL_GITHUB_PUBLISH_ENABLED",
];

const HOSTED_TOKEN = "hosted-route-test-token-0123456789";

async function hostedEnvironment(context) {
  const saved = Object.fromEntries(ENV_NAMES.map((name) => [name, process.env[name]]));
  context.after(() => {
    for (const name of ENV_NAMES) {
      if (saved[name] === undefined) delete process.env[name];
      else process.env[name] = saved[name];
    }
  });
  process.env.NODE_ENV = "development";
  process.env.ELMOS_HOSTED_EXECUTION_ENABLED = "true";
  process.env.ELMOS_LOCAL_RUNNER_ENABLED = "true";
  process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN = HOSTED_TOKEN;
  delete process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE;
  process.env.ELMOS_LOCAL_RUNNER_TENANT_ID = "tenant-hosted-routes";
  process.env.ELMOS_LOCAL_RUNNER_ACTOR_ID = "actor-hosted-routes";
  process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT = new Date(
    Date.now() + 60 * 60_000,
  ).toISOString();
  process.env.ELMOS_LOCAL_GITHUB_PUBLISH_ENABLED = "true";
}

function jobRoute(href, init) {
  return [new Request(href, init), { params: Promise.resolve({ jobId: "job-hosted-routes" }) }];
}

function authorizedInit(init = {}) {
  return {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${HOSTED_TOKEN}`,
      "x-elmos-tenant": "tenant-hosted-routes",
      "x-elmos-actor": "actor-hosted-routes",
      ...(init.headers ?? {}),
    },
  };
}

test("hosted runtime start is refused before authentication", async (context) => {
  await hostedEnvironment(context);
  const [request, routeContext] = jobRoute(
    "http://localhost/api/generation/jobs/job-hosted-routes/run",
    { method: "POST", body: JSON.stringify({ language: "python" }) },
  );
  const response = await runRoute(request, routeContext);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).reason, "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE");
});

test("hosted runtime stop is refused before authentication", async (context) => {
  await hostedEnvironment(context);
  const [request, routeContext] = jobRoute(
    "http://localhost/api/generation/jobs/job-hosted-routes/stop",
    { method: "POST", body: "{}" },
  );
  const response = await stopRoute(request, routeContext);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).reason, "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE");
});

test("hosted runtime preview is refused before authentication", async (context) => {
  await hostedEnvironment(context);
  const [request, routeContext] = jobRoute(
    "http://localhost/api/generation/jobs/job-hosted-routes/preview",
  );
  const response = await previewRoute(request, routeContext);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).reason, "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE");
});

test("hosted GitHub publish reports explicit NOT_RUN for authorized callers", async (context) => {
  await hostedEnvironment(context);
  const [request, routeContext] = jobRoute(
    "http://localhost/api/generation/jobs/job-hosted-routes/github",
    {
      method: "POST",
      body: JSON.stringify({ repoName: "generated-project", token: "ghp-not-a-real-token-000000" }),
      ...authorizedInit(),
    },
  );
  const response = await githubRoute(request, routeContext);
  assert.equal(response.status, 501);
  assert.equal((await response.json()).reason, "GITHUB_PUBLISH_HOSTED_EXECUTION_NOT_RUN");
});

test("hosted GitHub publish still demands authentication first", async (context) => {
  await hostedEnvironment(context);
  const [request, routeContext] = jobRoute(
    "http://localhost/api/generation/jobs/job-hosted-routes/github",
    {
      method: "POST",
      body: JSON.stringify({ repoName: "generated-project", token: "ghp-not-a-real-token-000000" }),
    },
  );
  const response = await githubRoute(request, routeContext);
  assert.equal(response.status, 401);
});

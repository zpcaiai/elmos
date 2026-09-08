import { expect, test } from "@playwright/test";

// Hosted-mode fail-closed journeys. These run only when the Playwright web
// server itself is started with ELMOS_HOSTED_EXECUTION_ENABLED=true (dev mode
// permits the hosted queue only through that explicit opt-in), which is what
// the CI step "Verify generation hosted fail-closed journeys" does:
//
//   ELMOS_HOSTED_EXECUTION_ENABLED=true ELMOS_E2E_HOSTED_MODE=true \
//     pnpm --dir apps/web-console exec playwright test \
//     --project=chromium e2e/generation-hosted-failclosed.spec.ts
//
// The unit suites (test/generationHostedClient.test.mjs,
// test/generationHostedRoutes.test.mjs) cover the same boundary in-process;
// these journeys prove it against a real dev server.
test.skip(
  process.env.ELMOS_E2E_HOSTED_MODE !== "true",
  "hosted fail-closed journeys require the web server to be started with ELMOS_HOSTED_EXECUTION_ENABLED=true",
);

const runnerHeaders = {
  "Content-Type": "application/json",
  "Authorization": "Bearer elmos-e2e-local-token-32-characters",
  "X-ELMOS-Tenant": "local-e2e",
  "X-ELMOS-Actor": "user:e2e",
};

test.describe.configure({ mode: "serial", timeout: 120_000 });

test("hosted 模式下本地运行、停止与浏览器预览在鉴权前显式不可用", async ({ request }) => {
  const jobId = "00000000-0000-4000-8000-000000000000";
  for (const [path, method] of [
    [`/api/generation/jobs/${jobId}/run`, "POST"],
    [`/api/generation/jobs/${jobId}/stop`, "POST"],
    [`/api/generation/jobs/${jobId}/preview`, "GET"],
  ] as const) {
    // No credentials at all: the hosted boundary refuses before auth, so the
    // response can never leak whether a job id exists.
    const anonymous = method === "POST"
      ? await request.post(path, { data: { language: "python" }, timeout: 30_000 })
      : await request.get(path, { timeout: 30_000 });
    expect(anonymous.status()).toBe(409);
    expect(await anonymous.json()).toMatchObject({
      status: "BLOCKED",
      reason: "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE",
    });

    const authorized = method === "POST"
      ? await request.post(path, { headers: runnerHeaders, data: { language: "python" }, timeout: 30_000 })
      : await request.get(path, { headers: runnerHeaders, timeout: 30_000 });
    expect(authorized.status()).toBe(409);
    expect(await authorized.json()).toMatchObject({
      status: "BLOCKED",
      reason: "HOSTED_RUNTIME_PREVIEW_NOT_AVAILABLE",
    });
  }
});

test("hosted 模式下任务入队走托管客户端并在缺少分析评审处失败", async ({ request }) => {
  // Without credentials the hosted admission still demands authentication
  // first; the hosted branch is only reached by an authorized caller.
  const anonymous = await request.post("/api/generation/jobs", {
    data: {},
    timeout: 30_000,
  });
  expect(anonymous.status()).toBe(401);
  expect(await anonymous.json()).toMatchObject({
    status: "BLOCKED",
    reason: "AUTHENTICATION_REQUIRED",
  });

  // With credentials the request enters createHostedGenerationJob, whose
  // single-use analysis-review rule fails closed long before any control
  // plane call could be attempted for this fabricated digest.
  const authorized = await request.post("/api/generation/jobs", {
    headers: runnerHeaders,
    data: {
      name: "hosted-failclosed",
      namespace: "elmos.e2e",
      description: "hosted 边界旅程专用请求，不应产生任何执行。",
      entity: "work_order",
      targets: ["python"],
      persistence: "in-memory",
      authMode: "none",
      reviewer: "user:e2e",
      approved: true,
      analysisDigest: "f".repeat(64),
    },
    timeout: 30_000,
  });
  expect(authorized.status()).toBe(409);
  const payload = await authorized.json();
  expect(payload).toMatchObject({ status: "BLOCKED" });
  expect(["ANALYSIS_REVIEW_NOT_FOUND", "APPROVED_ANALYSIS_REQUIRED"]).toContain(payload.reason);
});

test("hosted 模式下 GitHub 发布在未启用本地发布时拒绝", async ({ request }) => {
  const response = await request.post(
    "/api/generation/jobs/00000000-0000-4000-8000-000000000000/github",
    {
      headers: runnerHeaders,
      data: { repoName: "hosted-failclosed", token: "ghp-not-a-real-token-000000" },
      timeout: 30_000,
    },
  );
  // With ELMOS_LOCAL_GITHUB_PUBLISH_ENABLED unset the route stops at the
  // local-publish gate; when the CI step enables it, the hosted branch
  // answers with its explicit NOT_RUN code instead. Both are fail-closed.
  expect([403, 501]).toContain(response.status());
  const payload = await response.json();
  expect(payload).toMatchObject({ status: "BLOCKED" });
  expect([
    "LOCAL_GITHUB_PUBLISH_NOT_ENABLED",
    "GITHUB_PUBLISH_HOSTED_EXECUTION_NOT_RUN",
  ]).toContain(payload.reason);
});

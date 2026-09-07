import { expect, test } from "@playwright/test";

const tenantId = "tenant-operations-a";
const actorId = "operations-approver-1";
const jobId = "job-live-1";
const runnerNodeId = "runner-live-1";

const accountSession = {
  authenticated: true,
  configured: true,
  expiresAt: "2026-08-09T12:00:00Z",
  principal: {
    actorId,
    displayName: "Operations Approver",
    email: "operations-approver@example.test",
    organizationId: tenantId,
    roles: ["APPROVER"],
    permissions: ["admin:read", "admin:operate", "admin:approve"],
    memberships: [{
      organizationId: tenantId,
      roles: ["APPROVER"],
      permissions: ["admin:read", "admin:operate", "admin:approve"],
    }],
  },
};

const operationsView = {
  role: "APPROVER",
  actorId,
  activity: {
    from: "2026-08-08T10:00:00Z",
    to: "2026-08-09T10:00:00Z",
    totalEvents: 0,
    activeSessions: 0,
    failedEvents: 0,
    failureRate: 0,
    p95DurationMs: 0,
    businessLines: [],
    topErrors: [],
    recentEvents: [],
    persistence: "POSTGRES_DUAL_STORE",
    externalEvidence: "NOT_RUN",
  },
  control: {
    policies: [],
    alerts: [],
    incidents: [],
    remediations: [],
    retentionRuns: [],
    pendingNotifications: 0,
    automationMode: "DETECT_DIAGNOSE_PROPOSE_AUTOMATIC",
    sourceMutationMode: "APPROVAL_AND_EXTERNAL_SCM_REQUIRED",
    notificationDeliveryEvidence: "NOT_RUN",
    productionDeploymentEvidence: "NOT_RUN",
  },
};

test("admin closes the durable job and Runner Fleet operation loop", async ({ page }) => {
  let jobCancelled = false;
  let runnerStatus: "REGISTERED" | "READY" | "DRAINING" = "REGISTERED";
  let cancelCalls = 0;
  let attestationCalls = 0;
  let drainCalls = 0;

  await page.route("**/api/auth/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(accountSession),
    });
  });
  await page.route("**/api/telemetry/events", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/admin/operations?**", async (route) => {
    expect(route.request().headers().authorization).toBeUndefined();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(operationsView),
    });
  });
  await page.route(`**/api/admin/jobs/${jobId}/cancel`, async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers().authorization).toBeUndefined();
    cancelCalls += 1;
    jobCancelled = true;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        schemaVersion: "1.0.0",
        jobId,
        status: "RUNNING",
        cancelRequested: true,
        idempotentReplay: false,
      }),
    });
  });
  await page.route("**/api/admin/jobs?**", async (route) => {
    expect(route.request().method()).toBe("GET");
    expect(route.request().headers().authorization).toBeUndefined();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schemaVersion: "1.0.0",
        items: [{
          jobId,
          organizationId: tenantId,
          actorId,
          businessLine: "GENERATION",
          jobKind: "PROJECT_GENERATION",
          status: "RUNNING",
          stage: "EXECUTE",
          progress: 42,
          resultStatus: "NOT_RUN",
          failureCode: null,
          attempt: 1,
          maxAttempts: 3,
          createdAt: "2026-08-09T08:00:00Z",
          startedAt: "2026-08-09T08:01:00Z",
          finishedAt: null,
          cancelRequested: jobCancelled,
          stateVersion: jobCancelled ? 3 : 2,
        }],
        limit: 100,
        scanned: 1,
        scanTruncated: false,
        businessLine: null,
        status: null,
      }),
    });
  });
  await page.route(`**/api/admin/runners/${runnerNodeId}/attestation/verify`, async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers().authorization).toBeUndefined();
    attestationCalls += 1;
    runnerStatus = "READY";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ runnerNodeId, status: "READY" }),
    });
  });
  await page.route(`**/api/admin/runners/${runnerNodeId}/drain`, async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers().authorization).toBeUndefined();
    drainCalls += 1;
    runnerStatus = "DRAINING";
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ runnerNodeId, status: "DRAINING" }),
    });
  });
  await page.route("**/api/admin/runners?**", async (route) => {
    expect(route.request().method()).toBe("GET");
    expect(route.request().headers().authorization).toBeUndefined();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schemaVersion: "1.0.0",
        items: [{
          runnerNodeId,
          runnerPoolId: "pool-commercial-a",
          agentVersion: "1.0.0",
          fleetStatus: runnerStatus,
          capabilities: ["JAVA_21", "NODE_22"],
          maxConcurrency: 4,
          attestationVerified: runnerStatus !== "REGISTERED",
          attestationVerifiedAt: runnerStatus === "REGISTERED" ? null : "2026-08-09T08:10:00Z",
          imageAllowlistVersion: "2026-08-09",
          lastHeartbeatAt: "2026-08-09T08:12:00Z",
          drainRequestedAt: runnerStatus === "DRAINING" ? "2026-08-09T08:13:00Z" : null,
          createdAt: "2026-08-09T08:00:00Z",
          updatedAt: "2026-08-09T08:13:00Z",
        }],
        limit: 100,
        returned: 1,
        truncated: false,
        status: null,
      }),
    });
  });

  await page.goto("/admin");
  await expect(page.getByLabel("短期管理令牌")).toBeDisabled();
  await page.getByRole("button", { name: "读取数据" }).click();
  await page.getByRole("button", { name: "任务队列" }).click();

  const durableJobs = page.getByRole("region", { name: "持久作业队列" });
  await durableJobs.getByRole("button", { name: "读取作业" }).click();
  await expect(durableJobs.getByText(jobId, { exact: true })).toBeVisible();
  await durableJobs.getByRole("button", { name: "请求取消" }).click();
  await expect(durableJobs.getByText("取消请求已被持久队列接受。", { exact: true })).toBeVisible();
  expect(cancelCalls).toBe(1);

  const fleet = page.getByRole("region", { name: "Runner Fleet" });
  await fleet.getByRole("button", { name: "读取 Fleet" }).click();
  await expect(fleet.getByText("REGISTERED", { exact: true })).toBeVisible();
  await fleet.getByRole("button", { name: "确认独立证明" }).click();
  await expect(fleet.getByText("READY", { exact: true })).toBeVisible();
  await expect(fleet.getByText(/Runner attestation 已经独立验证并进入 READY/)).toBeVisible();
  expect(attestationCalls).toBe(1);

  await fleet.getByRole("button", { name: "排空节点" }).click();
  await expect(fleet.getByText("DRAINING", { exact: true })).toBeVisible();
  await expect(fleet.getByText("Runner 排空请求已确认。", { exact: true })).toBeVisible();
  expect(drainCalls).toBe(1);
});

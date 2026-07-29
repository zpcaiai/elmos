import { expect, test } from "@playwright/test";

const consoleView = {
  role: "APPROVER",
  actorId: "operator-1",
  activity: {
    from: "2026-07-27T10:00:00Z",
    to: "2026-07-28T10:00:00Z",
    totalEvents: 128,
    activeSessions: 14,
    failedEvents: 4,
    failureRate: 3.13,
    p95DurationMs: 480,
    businessLines: [
    {
      businessLine: "PROJECT_SYNTHESIS",
      eventCount: 72,
      sessionCount: 8,
      failureCount: 2,
      failureRate: 2.78,
      p95DurationMs: 420,
    },
    {
      businessLine: "SPRING_MODERNIZATION",
      eventCount: 56,
      sessionCount: 6,
      failureCount: 2,
      failureRate: 3.57,
      p95DurationMs: 610,
    },
    ],
    topErrors: [
      { errorCode: "HTTP_409", count: 3, lastSeenAt: "2026-07-28T09:58:00Z" },
    ],
    recentEvents: [
    {
      eventId: "event-1",
      sessionId: "session-1",
      eventKind: "API_REQUEST",
      action: "API_POST",
      businessLine: "PROJECT_SYNTHESIS",
      route: "/api/generation/jobs",
      target: "/api/generation/jobs",
      occurredAt: "2026-07-28T09:59:00Z",
      durationMs: 390,
      result: "SUCCESS",
      errorCode: null,
      metricName: null,
      metricValue: null,
    },
    ],
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

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
});

test("admin stays locked until an operator supplies a short-lived token", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "运营管理端" })).toBeVisible();
  await expect(page.getByText("管理数据默认锁定")).toBeVisible();
  await expect(page.getByText("外部生产证据", { exact: false })).toHaveCount(0);
});

test("admin renders tenant-scoped performance and error signals", async ({ page }) => {
  await page.route("**/api/admin/operations?**", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer admin-observability-token-32");
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(consoleView) });
  });
  await page.goto("/admin");
  await page.getByLabel("短期管理令牌").fill("admin-observability-token-32");
  await page.getByRole("button", { name: "读取数据" }).click();

  await expect(page.getByRole("navigation", { name: "管理端功能" })).toBeVisible();
  await expect(page.getByRole("button", { name: "用户与租户" })).toHaveAttribute(
    "aria-current", "page",
  );
  await expect(page.getByText(/外部 IdP 全量用户目录同步尚未执行/)).toBeVisible();

  await page.getByRole("button", { name: "用量与性能" }).click();
  await expect(page.getByText("128", { exact: true })).toBeVisible();
  await expect(page.getByText("3.13%", { exact: true })).toBeVisible();
  await expect(page.getByText("480 ms", { exact: true })).toBeVisible();
  await expect(page.getByText("HTTP_409", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "审计" }).click();
  await expect(page.getByText("POSTGRES_DUAL_STORE", { exact: false })).toBeVisible();
  await expect(page.locator("small").filter({ hasText: "外部生产证据 NOT_RUN" })).toBeVisible();

  await page.getByRole("button", { name: "配置与门禁" }).click();
  await expect(page.getByRole("button", { name: "立即评估全部 SLO" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "执行 30 天保留" })).toBeEnabled();
});

test("collector batches semantic actions without input values or URL queries", async ({ page }) => {
  const captured: Array<Record<string, unknown>> = [];
  await page.unroute("**/api/telemetry/events");
  await page.route("**/api/telemetry/events", async (route) => {
    const body = route.request().postDataJSON() as { events: Array<Record<string, unknown>> };
    captured.push(...body.events);
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/?secret=must-not-be-logged");
  await page.getByRole("button", { name: "打开全局搜索" }).click();
  await page.evaluate(async () => {
    await fetch("/api/generation/jobs/1d39f590-6191-4ae9-8c79-f6273d2860ad?token=must-not-be-logged");
  });

  await expect.poll(() => captured.some((event) => event.actionKey === "click"), { timeout: 6_000 }).toBe(true);
  expect(JSON.stringify(captured)).not.toContain("must-not-be-logged");
  expect(JSON.stringify(captured)).not.toContain("1d39f590-6191-4ae9-8c79-f6273d2860ad");
  expect(captured.every((event) => !Object.hasOwn(event, "value"))).toBe(true);
});

test("telemetry ingress rejects cross-origin and non-allowlisted fields before storage", async ({ request, baseURL }) => {
  const event = {
    schemaVersion: "1.0.0",
    eventName: "interaction",
    businessLine: "overview",
    route: "/",
    actionKey: "click.primary",
    targetKind: "button",
    outcome: "succeeded",
    durationBucket: "lt_100ms",
    viewportClass: "desktop",
    sessionId: "78c4b04f-1d39-4f50-8fd8-8dcb65787d99",
    occurredAt: new Date().toISOString(),
    durationMs: 42,
    errorCode: null,
  };
  const crossOrigin = await request.post("/api/telemetry/events", {
    headers: { Origin: "https://attacker.invalid" },
    data: { events: [event] },
  });
  expect(crossOrigin.status()).toBe(403);

  const extraField = await request.post("/api/telemetry/events", {
    headers: { Origin: baseURL ?? "" },
    data: { events: [{ ...event, inputValue: "must-never-be-accepted" }] },
  });
  expect(extraField.status()).toBe(400);
  await expect(extraField.json()).resolves.toMatchObject({ reason: "EVENT_FIELDS_NOT_ALLOWLISTED" });
});

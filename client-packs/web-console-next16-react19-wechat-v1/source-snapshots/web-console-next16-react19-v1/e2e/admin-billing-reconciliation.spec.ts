import { expect, test } from "@playwright/test";

const accountSession = {
  authenticated: true,
  configured: true,
  expiresAt: "2026-08-09T12:00:00Z",
  principal: {
    actorId: "finance-approver-1",
    displayName: "Finance Approver",
    email: "approver@example.test",
    organizationId: "tenant-finance-a",
    roles: ["APPROVER"],
    permissions: ["admin:read", "admin:operate", "admin:approve"],
    memberships: [{
      organizationId: "tenant-finance-a",
      roles: ["APPROVER"],
      permissions: ["admin:read", "admin:operate", "admin:approve"],
    }],
  },
};

const operationsView = {
  role: "APPROVER",
  actorId: "finance-approver-1",
  activity: {
    from: "2026-08-08T10:00:00Z",
    to: "2026-08-09T10:00:00Z",
    totalEvents: 1,
    activeSessions: 1,
    failedEvents: 0,
    failureRate: 0,
    p95DurationMs: 10,
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

function reconciliation(status: "OPEN" | "REJECTED") {
  return {
    reconciliationCaseId: status === "OPEN" ? "recon-case-open-1" : "recon-case-rejected-1",
    provider: "STRIPE",
    providerObjectRef: status === "OPEN" ? "invoice-open-1" : "invoice-rejected-1",
    expectedState: "PAID",
    observedState: "UNKNOWN",
    status,
    reasonCode: "PROVIDER_STATE_MISMATCH",
    openedAt: "2026-08-09T08:30:00Z",
    resolvedAt: status === "OPEN" ? null : "2026-08-09T09:30:00Z",
    resolverActorId: status === "OPEN" ? null : "finance-approver-2",
    resolutionRef: status === "OPEN" ? null : "bank-statement:2026-08-09/previous",
  };
}

test("finance admin lists filtered cases and never auto-retries an unknown write", async ({ page }) => {
  const requestedStatuses: string[] = [];
  const mutationKeys: string[] = [];
  const mutationBodies: unknown[] = [];

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
  await page.route("**/api/admin/billing/reconciliation**", async (route) => {
    const request = route.request();
    expect(request.headers().authorization).toBeUndefined();
    if (request.method() === "GET") {
      const status = new URL(request.url()).searchParams.get("status") ?? "";
      requestedStatuses.push(status);
      const item = status === "REJECTED" ? reconciliation("REJECTED") : reconciliation("OPEN");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ schemaVersion: "1.0.0", items: [item] }),
      });
      return;
    }
    mutationKeys.push(request.headers()["idempotency-key"] ?? "");
    mutationBodies.push(request.postDataJSON());
    if (mutationKeys.length === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          status: "UNKNOWN",
          code: "BILLING_RECONCILIATION_RESULT_UNKNOWN",
          retryable: false,
          operationMayHaveCompleted: true,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "RESOLVED" }),
    });
  });

  await page.goto("/admin");
  await expect(page.getByLabel("短期管理令牌")).toBeDisabled();
  await page.getByRole("button", { name: "读取数据" }).click();
  await page.getByRole("button", { name: "财务对账" }).click();

  await page.getByRole("button", { name: "读取对账" }).click();
  await expect(page.getByText("recon-case-open-1", { exact: true })).toBeVisible();

  await page.getByLabel("财务对账状态").selectOption("REJECTED");
  await page.getByRole("button", { name: "读取对账" }).click();
  await expect(page.getByText("recon-case-rejected-1", { exact: true })).toBeVisible();

  await page.getByLabel("财务对账状态").selectOption("OPEN");
  await page.getByRole("button", { name: "读取对账" }).click();
  await page.getByLabel("处理依据 recon-case-open-1").fill("bank-statement:2026-08-09/42");
  await expect(page.getByRole("button", { name: "驳回案件" })).toBeVisible();
  await page.getByRole("button", { name: "标记已解决" }).click();

  await expect(page.getByText(/本次结案结果未知，系统未自动重试/)).toBeVisible();
  await page.waitForTimeout(500);
  expect(mutationKeys).toHaveLength(1);

  await page.getByRole("button", { name: "标记已解决" }).click();
  await expect(page.getByText("上游已确认案件为 RESOLVED。", { exact: true })).toBeVisible();
  expect(mutationKeys).toHaveLength(2);
  expect(mutationKeys[0]).toBe(mutationKeys[1]);
  expect(mutationKeys[0]).toMatch(/^finance-resolved-[0-9a-f-]{36}$/);
  expect(mutationBodies[0]).toEqual(mutationBodies[1]);
  expect(mutationBodies[0]).toEqual({
    reconciliationCaseId: "recon-case-open-1",
    resolutionStatus: "RESOLVED",
    resolutionRef: "bank-statement:2026-08-09/42",
  });
  expect(requestedStatuses).toEqual(["OPEN", "REJECTED", "OPEN"]);
});

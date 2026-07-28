import { appendFile, mkdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

const tenantId = "local-e2e";
const actorId = "user:e2e";
const planId = "elmos-pro-monthly";
const token = "elmos-e2e-local-token-32-characters";
const headers = {
  "Authorization": `Bearer ${token}`,
  "X-ELMOS-Tenant": tenantId,
  "X-ELMOS-Actor": actorId,
};

function event(
  eventId: string,
  meterId: "model-token-v1" | "platform-credit-v1",
  quantity: number,
  reconciliationStatus: "RECONCILED" | "PENDING" = "RECONCILED",
) {
  const timestamp = new Date().toISOString();
  return {
    schemaVersion: "1.0.0",
    eventId,
    idempotencyKey: `idem-${eventId}`,
    tenantId,
    actorId,
    planId,
    meterId,
    quantity,
    occurredAt: timestamp,
    recordedAt: timestamp,
    reconciliationStatus,
  };
}

test.describe.serial("实时账户用量", () => {
  let ledgerPath = "";

  test.beforeAll(async () => {
    const runnerRoot = process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT;
    if (!runnerRoot) throw new Error("ELMOS_E2E_EFFECTIVE_RUNNER_ROOT_REQUIRED");
    const usageRoot = path.join(runnerRoot, "tenants", tenantId, "usage");
    ledgerPath = path.join(usageRoot, "ledger.jsonl");
    await mkdir(usageRoot, { recursive: true });
    await writeFile(
      ledgerPath,
      [
        event("usage-token-001", "model-token-v1", 5_000_000),
        event("usage-credit-001", "platform-credit-v1", 150),
        event("usage-token-pending-001", "model-token-v1", 1_000_000, "PENDING"),
      ].map((value) => JSON.stringify(value)).join("\n") + "\n",
      "utf8",
    );
  });

  test("用量 API 要求精确身份并只聚合已对账事件", async ({ request }) => {
    const unauthorized = await request.get("/api/usage/current");
    expect(unauthorized.status()).toBe(401);
    await expect(unauthorized.json()).resolves.toMatchObject({
      code: "USAGE_AUTHENTICATION_REQUIRED",
      retryable: false,
    });

    const crossTenant = await request.get("/api/usage/current", {
      headers: { ...headers, "X-ELMOS-Tenant": "other-tenant" },
    });
    expect(crossTenant.status()).toBe(403);
    await expect(crossTenant.json()).resolves.toMatchObject({
      code: "USAGE_SUBJECT_MISMATCH",
      retryable: false,
    });

    const response = await request.get("/api/usage/current", { headers });
    const responseText = await response.text();
    expect(response.ok(), responseText).toBe(true);
    expect(response.headers()["cache-control"]).toContain("no-store");
    expect(response.headers()["x-elmos-usage-snapshot-version"]).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.parse(responseText)).toMatchObject({
      status: "PARTIAL",
      plan: { planId },
      tokens: {
        consumed: 5_000_000,
        limit: 20_000_000,
        remaining: 15_000_000,
        usageBps: 2_500,
      },
      credits: {
        consumed: 150,
        limit: 600,
        remaining: 450,
        usageBps: 2_500,
      },
      reconciledEventCount: 2,
      unreconciledEventCount: 1,
    });

    const unavailablePath = `${ledgerPath}.unavailable`;
    await rename(ledgerPath, unavailablePath);
    try {
      const unavailable = await request.get("/api/usage/current", { headers });
      expect(unavailable.status()).toBe(503);
      await expect(unavailable.json()).resolves.toMatchObject({
        code: "USAGE_LEDGER_NOT_CONFIGURED",
        status: "NOT_CONFIGURED",
      });
    } finally {
      await rename(unavailablePath, ledgerPath);
    }
  });

  test("套餐页实时更新 token 消耗量与进度", async ({ page }) => {
    await page.goto("/pricing");
    await page.getByLabel("用量租户标识").fill(tenantId);
    await page.getByLabel("用量用户标识").fill(actorId);
    await page.getByLabel("用量短期访问令牌").fill(token);
    await page.getByRole("button", { name: "连接实时用量" }).click();

    await expect(page.getByText("已连接实时用量")).toBeVisible();
    await expect(page.getByText("当前有 1 条未对账事件")).toBeVisible();
    await expect(
      page.getByRole("progressbar", { name: "模型 Token消耗进度" }),
    ).toHaveAttribute("aria-valuetext", /5,000,000.*25\.00%/);
    await expect(
      page.getByRole("progressbar", { name: "平台 Credits消耗进度" }),
    ).toHaveAttribute("aria-valuetext", /150.*25\.00%/);

    await appendFile(
      ledgerPath,
      `${JSON.stringify(event("usage-token-002", "model-token-v1", 1_000_000))}\n`,
      "utf8",
    );

    await expect(
      page.getByRole("progressbar", { name: "模型 Token消耗进度" }),
    ).toHaveAttribute("aria-valuetext", /6,000,000.*30\.00%/, { timeout: 12_000 });
  });
});

import { expect, test } from "@playwright/test";
import { installAdministratorSession } from "./helpers/admin-session";

test("人民币套餐页展示精确 token 与 credit 额度", async ({ page }) => {
  await installAdministratorSession(page);
  await page.goto("/pricing");

  await expect(page.getByRole("heading", { name: "先验证价值，再为持续交付付费。" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "免费体验" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "专业月付" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "专业年付" })).toBeVisible();
  await expect(page.getByText("¥129.00", { exact: true })).toBeVisible();
  await expect(page.getByText("¥1,290.00", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "按需购买，不必先订阅" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "500 Credits" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "单项目生成一次" })).toBeVisible();
  await expect(page.getByText("¥99.00", { exact: true })).toBeVisible();
  await expect(page.getByText("¥39.00", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "等待开放" })).toHaveCount(4);
  await expect(page.getByLabel("专业月付用量额度")).toContainText("20,000,000");
  await expect(page.getByLabel("专业月付用量额度")).toContainText("600");
  await expect(page.getByLabel("专业年付用量额度")).toContainText("25,000,000");
  await expect(page.getByLabel("专业年付用量额度")).toContainText("750");
  await expect(page.getByText(/支付、税务与开票均为/)).toContainText("NOT_CONFIGURED");
});

test("套餐 API 与页面共享同一目录版本并保持支付关闭", async ({ request }) => {
  const response = await request.get("/api/pricing");
  expect(response.ok()).toBe(true);
  expect(response.headers()["x-elmos-catalog-version"]).toBe("2026-09-08.1");

  const catalog = await response.json();
  expect(catalog.currency).toBe("CNY");
  expect(catalog.status).toBe("DRAFT");
  expect(catalog.paymentStatus).toBe("NOT_CONFIGURED");
  expect(catalog.costValidationStatus).toBe("NOT_RUN");
  expect(catalog.authoritativeSource).toBe(
    "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
  );
  expect(catalog.overagePolicy).toBe("HARD_STOP_NO_AUTOMATIC_CHARGE");
  expect(catalog.plans).toHaveLength(3);
  expect(catalog.creditPacks).toEqual([expect.objectContaining({
    sku: "elmos-credit-500",
    priceFen: 9_900,
    credits: 500,
    expiryDays: 365,
  })]);
  expect(catalog.oneTimeProducts).toEqual([expect.objectContaining({
    sku: "elmos-project-generation-once",
    priceFen: 3_900,
    operationKey: "verified-generation-or-migration",
    maxRunnerMinutes: 20,
  })]);
  expect(catalog.plans[1]).toMatchObject({
    planId: "elmos-pro-monthly",
    priceFen: 12_900,
    tokens: 20_000_000,
    credits: 600,
  });
  expect(catalog.plans[2]).toMatchObject({
    planId: "elmos-pro-annual",
    priceFen: 129_000,
    tokens: 25_000_000,
    credits: 750,
    annualTokens: 300_000_000,
    annualCredits: 9_000,
  });
});

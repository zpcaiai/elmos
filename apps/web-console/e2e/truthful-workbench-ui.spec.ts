import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

test("playground exposes one shell and never converts a static preview into proof evidence", async ({
  page,
}) => {
  await page.goto("/playground");

  await expect(page.locator(".app-shell")).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.getByText("Static workbench preview · NOT_RUN")).toBeVisible();
  await expect(page.locator("main")).not.toContainText(
    /SAT_PROVED|SLSA Level 3 certified|PR Review Verdict: PASS/i,
  );

  await page.getByRole("button", { name: "检查真实执行条件" }).click();
  await expect(page.locator("main").getByRole("status")).toContainText("BLOCKED");
  await expect(page.locator("main").getByRole("status")).toContainText("NOT_CERTIFIED");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("governance labels illustrative mutation output without claiming a runner execution", async ({
  page,
}) => {
  await page.goto("/governance");

  await expect(page.getByText(/Runner execution NOT_RUN/)).toBeVisible();
  await expect(page.getByLabel("待测业务逻辑示例")).toBeVisible();
  await page.getByRole("button", { name: /生成变异结果示例/ }).click();
  await expect(page.getByText("75.0%")).toBeVisible();
  await expect(page.getByText("SAMPLE_ONLY", { exact: true })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("执行变异测试 (elmos qa mutate)");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("observability remains truthful, accessible and contained at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/observability");

  await expect(page.getByText("SAMPLE DATA · NOT_RUN")).toBeVisible();
  await page.getByRole("button", { name: "Prometheus 指标示例" }).click();
  await expect(page.getByText("Scrape Status: NOT_RUN")).toBeVisible();
  await page.getByRole("button", { name: "SLSA 凭证结构示例" }).click();
  await expect(page.getByText("Verification: NOT_RUN")).toBeVisible();
  await expect(page.locator("main")).not.toContainText("Ed25519 Verified");

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("smoke page does not nest main landmarks", async ({ page }) => {
  await page.goto("/smoke");
  await expect(page.locator("main")).toHaveCount(1);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("desktop account menu keeps secure logout inside the viewport and usable", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/login");
  await page.getByLabel("邮箱").fill("test@example.test");
  await page.getByLabel("密码").fill("test");
  await page.getByRole("button", { name: "使用邮箱登录" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.getByRole("button", { name: "打开账户菜单" }).click();
  const logout = page.getByRole("button", { name: "安全退出" });
  await expect(logout).toBeVisible();
  const box = await logout.boundingBox();
  expect(box).not.toBeNull();
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(768);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  await logout.click();
  await expect(page).toHaveURL(/\/login/);
  const session = await page.evaluate(async () =>
    (await fetch("/api/auth/session", { credentials: "same-origin" })).json());
  expect(session).toMatchObject({ authenticated: false, principal: null });
});

test("mobile top avatar opens the account menu inside the navigation drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByLabel("邮箱").fill("test@example.test");
  await page.getByLabel("密码").fill("test");
  await page.getByRole("button", { name: "使用邮箱登录" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.getByRole("button", { name: "打开账户菜单" }).click();
  await expect(page.locator(".sidebar")).toHaveClass(/sidebar-open/);
  const logout = page.getByRole("button", { name: "安全退出" });
  await expect(logout).toBeVisible();
  await expect.poll(async () => (await logout.boundingBox())?.x ?? -1).toBeGreaterThanOrEqual(0);
  const box = await logout.boundingBox();
  expect(box).not.toBeNull();
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(844);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

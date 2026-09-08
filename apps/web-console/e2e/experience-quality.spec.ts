import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

test("help, shell locale and theme preferences stay accessible and persistent", async ({ page }) => {
  await page.goto("/help");

  await expect(page.getByRole("heading", { name: "帮助与就绪状态" })).toBeVisible();
  await expect(page.getByText("GitHub / Gitee 现场执行 NOT_RUN")).toBeVisible();

  await page.getByRole("button", { name: "使用深色主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: "将导航和帮助切换为英文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Help and readiness" })).toBeVisible();
  await expect(page.locator(".skip-link")).toHaveText("Skip to main content");
  await expect(page.locator('button[aria-label="Reload current page (clears unsaved input)"]')).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Open global search" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open repository workspace" })).toHaveCount(0);
  await expect(
    page.getByLabel("Operate and diagnose")
      .getByRole("link", { name: "Administrator sign in" }),
  ).toHaveAttribute("href", "/admin/login");

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("authenticated account menu label follows English navigation mode", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("账号 / 邮箱").fill("test");
  await page.getByLabel("密码").fill("test");
  await page.getByRole("button", { name: "使用测试账号登录" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "打开账户菜单" })).toBeVisible();

  await page.getByRole("button", { name: "将导航和帮助切换为英文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("button", { name: "Open account menu" })).toBeVisible();
  await expect(page.getByRole("button", { name: "打开账户菜单" })).toHaveCount(0);
});

test("skip link moves keyboard focus to main content", async ({ page }) => {
  await page.goto("/help");
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("help remains usable at 200 percent zoom and mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/help");
  await page.addStyleTag({ content: "html { font-size: 200% !important; }" });
  await expect(page.getByRole("heading", { name: "帮助与就绪状态" })).toBeVisible();
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const administratorLogin = page.getByRole("link", { name: "前往管理员登录" });
  await expect(administratorLogin).toBeVisible();
  await expect(administratorLogin).toHaveAttribute(
    "href", "/admin/login",
  );
});

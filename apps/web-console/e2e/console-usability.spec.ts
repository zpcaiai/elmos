import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { installAdministratorSession } from "./helpers/admin-session";

/** Surfaces a signed-in customer reaches from /login. */
const userRoutes = [
  "/",
  "/spring",
  "/translation",
  "/generation",
  "/migration",
  "/pricing",
  "/capabilities",
] as const;

/** Surfaces that only a platform administrator reaches from /admin/login. */
const operationsRoutes = ["/commercialization"] as const;

for (const route of [...userRoutes, ...operationsRoutes]) {
  test(`${route} 在桌面与移动端保持清晰、无横向溢出并通过自动可访问性检查`, async ({
    page,
  }) => {
    if ((operationsRoutes as readonly string[]).includes(route)) {
      await installAdministratorSession(page);
    }
    await page.goto(route);
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content, `${route} 不应产生横向滚动`).toBeLessThanOrEqual(
      dimensions.viewport,
    );

    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(
      accessibility.violations,
      `${route} 不应存在自动可访问性违规`,
    ).toEqual([]);
  });
}

test("全局搜索支持键盘焦点约束、语义化结果和显式关闭", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "打开全局搜索" });
  await trigger.click();

  const dialog = page.getByRole("dialog", { name: "全局搜索" });
  const search = dialog.getByRole("combobox", { name: "搜索页面、能力或批次" });
  const results = dialog.getByRole("option");
  await expect(dialog).toBeVisible();
  await expect(search).toBeFocused();
  await expect(search).toHaveAttribute("aria-expanded", "true");
  await expect(dialog.getByRole("button", { name: "关闭全局搜索" })).toBeVisible();
  await expect(results.first()).toHaveAttribute("aria-selected", "true");

  await results.last().focus();
  await page.keyboard.press("Tab");
  await expect(search).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(results.last()).toBeFocused();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("长页面提供可触达的返回顶部操作", async ({ page }) => {
  await page.goto("/generation");
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));

  const backToTop = page.getByRole("button", { name: "返回页面顶部" });
  await expect(backToTop).toBeVisible();
  await backToTop.click();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(10);
});

test("重新载入前明确提醒未保存输入风险", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name.startsWith("mobile-"), "移动顶栏不显示重新载入操作");
  await page.goto("/");

  let warning = "";
  page.once("dialog", async (dialog) => {
    warning = dialog.message();
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "重新载入当前页面（会清除未保存输入）" }).click();
  await expect.poll(() => warning).toContain("尚未保存的输入");
});

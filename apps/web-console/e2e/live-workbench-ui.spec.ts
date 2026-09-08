import { expect, test } from "@playwright/test";
import { installAdministratorSession } from "./helpers/admin-session";

test("live workbench sends anonymous visitors to the administrator entry", async ({ page }) => {
  await page.goto("/workbench");
  await expect(page).toHaveURL(/\/admin\/login\?returnTo=%2Fworkbench$/);
  await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();
});

test("administrator workbench renders the fixed-window fail-closed controls", async ({ page }) => {
  await installAdministratorSession(page);
  await page.goto("/workbench");

  await expect(page.getByRole("heading", { name: "Live Workbench" })).toBeVisible();
  await expect(page.getByText(/固定 10 分钟计时/)).toBeVisible();
  await expect(page.getByRole("button", { name: "创建隔离会话" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /续期|延长/ })).toHaveCount(0);

  await page.getByLabel("交付物 ID").fill("delivery-e2e");
  await page.getByLabel("仓库 ID").fill("repository-e2e");
  await page.getByLabel("不可变快照 SHA-256").fill("not-a-digest");
  await page.getByRole("button", { name: "创建隔离会话" }).click();
  await expect(page.getByText(
    "请求被安全门禁阻断：SNAPSHOT_SHA256_REQUIRED",
    { exact: true },
  )).toBeVisible();
});

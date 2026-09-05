import { expect, test } from "@playwright/test";

const administratorEmail = "zpchoney@gmail.com";

test("anonymous administrator entries perform a document navigation", async ({ page }) => {
  await page.goto("/");

  const topAdminLogin = page.locator("header").getByRole("link", {
    name: "管理员入口",
    exact: true,
  });
  await expect(topAdminLogin).toHaveAttribute("href", "/admin/login");
  await topAdminLogin.click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();

  await page.goto("/");
  const sidebarAdminLogin = page.locator("aside").getByRole("link", {
    name: /管理员登录入口/,
  });
  await expect(sidebarAdminLogin).toHaveAttribute("href", "/admin/login");
  await sidebarAdminLogin.click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();
});

test("administrator login is visibly separate from user login", async ({ page }) => {
  await page.goto("/admin/login");

  await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();
  await expect(page.getByText("管理员专用 · ADMIN ONLY", { exact: true })).toBeVisible();
  await expect(page.getByText(administratorEmail, { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("管理员身份提供商未配置");
  await expect(page.getByLabel("管理员邮箱")).toHaveCount(0);
  await expect(page.getByLabel("密码")).toHaveCount(0);
  await expect(page.getByText(/每次管理员成功登录后/)).toBeVisible();
  await expect(page.getByRole("link", { name: "返回用户登录" })).toHaveAttribute("href", "/login");
  await expect(page.locator(".admin-auth-card")).toBeVisible();

  await page.getByRole("link", { name: "返回用户登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "用户登录" })).toBeVisible();
  await expect(page.locator(".user-auth-card")).toBeVisible();
});

test("administrator login reports rejected and unavailable security states", async ({ page }) => {
  await page.goto("/admin/login?error=ADMIN_EMAIL_REQUIRED");
  await expect(page.locator(".auth-error[role='alert']")).toContainText("不是获准的管理员账户");

  await page.goto("/admin/login?error=ADMIN_LOGIN_ENTRY_REQUIRED");
  await expect(page.locator(".auth-error[role='alert']")).toContainText("管理员账户必须从当前专用入口登录");

  await page.goto("/admin/login?error=ADMIN_LOGIN_NOTIFICATION_UNAVAILABLE");
  await expect(page.locator(".auth-error[role='alert']")).toContainText("本次未建立管理员会话");
});

test("admin navigation and commands require the server-issued admin session", async ({ page }) => {
  await page.route("**/api/auth/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        configured: true,
        expiresAt: "2099-08-31T12:00:00Z",
        principal: {
          actorId: "admin-zpchoney",
          displayName: "ELMOS Administrator",
          email: administratorEmail,
          emailVerified: true,
          isPlatformAdmin: true,
          organizationId: "elmos-platform",
          roles: ["APPROVER"],
          permissions: ["workspace:view", "admin:read", "admin:operate", "admin:approve"],
          memberships: [{
            organizationId: "elmos-platform",
            roles: ["APPROVER"],
            permissions: ["workspace:view", "admin:read", "admin:operate", "admin:approve"],
          }],
        },
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /运营管理端/ })).toBeVisible();
  await expect(page.getByText("管理员会话", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "打开账户菜单" }).click();
  await expect(page.getByText("管理员会话", { exact: true })).toBeVisible();
  const mobileNavigationOverlay = page.getByRole("button", { name: "关闭导航遮罩" });
  if ((page.viewportSize()?.width ?? 0) <= 900) {
    await expect(mobileNavigationOverlay).toBeVisible();
    await mobileNavigationOverlay.click();
    await expect(mobileNavigationOverlay).toBeHidden();
  }

  await page.getByRole("button", { name: "打开全局搜索" }).click();
  await expect(page.getByRole("option", { name: /查看操作日志与性能/ })).toBeVisible();
});

test("ordinary users cannot discover admin navigation or admin commands", async ({ page }) => {
  await page.route("**/api/auth/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        configured: true,
        expiresAt: "2099-08-31T12:00:00Z",
        principal: {
          actorId: "user-1",
          displayName: "ELMOS User",
          email: "user@example.test",
          emailVerified: true,
          isPlatformAdmin: false,
          organizationId: "tenant-user",
          roles: ["DEVELOPER"],
          permissions: ["workspace:view"],
          memberships: [{
            organizationId: "tenant-user",
            roles: ["DEVELOPER"],
            permissions: ["workspace:view"],
          }],
        },
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: "打开账户菜单" })).toBeVisible();
  await expect(page.getByRole("link", { name: /运营管理端/ })).toHaveCount(0);
  await page.getByRole("button", { name: "打开全局搜索" }).click();
  await expect(page.getByRole("option", { name: /查看操作日志与性能/ })).toHaveCount(0);
});

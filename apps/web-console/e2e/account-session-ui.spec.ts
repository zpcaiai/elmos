import { expect, test } from "@playwright/test";

test("account session discovery represents anonymous state without a console-level 401", async ({
  request,
  page,
}) => {
  const session = await request.get("/api/auth/session");
  expect(session.status()).toBe(200);
  await expect(session.json()).resolves.toMatchObject({
    authenticated: false,
    configured: true,
    principal: null,
  });

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "用户登录" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "使用邮箱登录" })).toBeVisible();
  await expect(page.getByLabel("邮箱")).toHaveAttribute("name", "email");
  await expect(page.locator('input[name="loginMode"]')).toHaveValue("USER");
  await expect(page.getByRole("button", { name: "使用邮箱登录" })).toBeVisible();
  await expect(page.getByRole("link", { name: "进入管理员登录" })).toHaveAttribute(
    "href",
    "/admin/login",
  );
  await expect(page.getByText(/服务端 API 均会拒绝操作/)).toBeVisible();
});

test("user login directs the platform administrator to the dedicated entry", async ({ page }) => {
  await page.goto("/login?error=ADMIN_LOGIN_ENTRY_REQUIRED");

  await expect(page.getByRole("alert")).toContainText("管理员账户必须从独立的管理员入口登录");
  await expect(page.getByRole("link", { name: "进入管理员登录" })).toHaveAttribute(
    "href",
    "/admin/login",
  );
});

test("local test account establishes a development-only session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("邮箱").fill("test@example.test");
  await page.getByLabel("密码").fill("test");
  await page.getByRole("button", { name: "使用邮箱登录" }).click();
  await expect(page).toHaveURL(/\/$/);

  const session = await page.evaluate(async () => {
    const response = await fetch("/api/auth/session", { credentials: "same-origin" });
    return response.json();
  });
  expect(session).toMatchObject({
    authenticated: true,
    configured: true,
    principal: {
      actorId: "local:test",
      email: "test@example.test",
      emailVerified: false,
      isPlatformAdmin: false,
      organizationId: "local-e2e",
      roles: ["DEVELOPER"],
    },
  });
});

test("local registration creates an account and starts a session", async ({ page }) => {
  const username = `e2e-${Date.now()}`;
  const email = `${username}@example.test`;
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "注册 ELMOS 账户" })).toBeVisible();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("显示名称").fill("E2E User");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill("correct-horse-battery");
  await page.getByLabel("确认密码").fill("correct-horse-battery");
  await page.getByRole("button", { name: "创建账户" }).click();
  await expect(page).toHaveURL(/\/$/);

  const session = await page.evaluate(async () => {
    const response = await fetch("/api/auth/session", { credentials: "same-origin" });
    return response.json();
  });
  expect(session).toMatchObject({
    authenticated: true,
    configured: true,
    principal: {
      actorId: `local:${username}`,
      displayName: "E2E User",
      email,
      emailVerified: false,
      isPlatformAdmin: false,
      roles: ["DEVELOPER"],
    },
  });
});

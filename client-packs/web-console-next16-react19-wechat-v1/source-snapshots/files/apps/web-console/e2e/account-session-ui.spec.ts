import { expect, test } from "@playwright/test";

test("account session discovery represents anonymous state without a console-level 401", async ({
  request,
  page,
}) => {
  const session = await request.get("/api/auth/session");
  expect(session.status()).toBe(200);
  await expect(session.json()).resolves.toMatchObject({
    authenticated: false,
    configured: false,
    principal: null,
  });

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录 ELMOS 控制中心" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "本地测试账号" })).toBeVisible();
  await expect(page.getByRole("button", { name: "使用本地测试账号登录" })).toBeVisible();
  await expect(page.getByText(/服务端 API 均会拒绝操作/)).toBeVisible();
});

test("local test account establishes a development-only session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("test");
  await page.getByLabel("密码").fill("test");
  await page.getByRole("button", { name: "使用本地测试账号登录" }).click();
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
      organizationId: "local-e2e",
      roles: ["DEVELOPER"],
    },
  });
});

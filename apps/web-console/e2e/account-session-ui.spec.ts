import { expect, test } from "@playwright/test";

test("account session fails closed when OIDC is not configured", async ({ request, page }) => {
  const session = await request.get("/api/auth/session");
  expect(session.status()).toBe(401);
  await expect(session.json()).resolves.toMatchObject({
    authenticated: false,
    configured: false,
    principal: null,
  });

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录 ELMOS 控制中心" })).toBeVisible();
  await expect(page.getByText("身份提供商未配置", { exact: true })).toBeVisible();
  await expect(page.getByText(/服务端 API 均会拒绝操作/)).toBeVisible();
});

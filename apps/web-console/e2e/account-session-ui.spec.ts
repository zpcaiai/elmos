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
  await expect(page.getByText("身份提供商未配置", { exact: true })).toBeVisible();
  await expect(page.getByText(/服务端 API 均会拒绝操作/)).toBeVisible();
});

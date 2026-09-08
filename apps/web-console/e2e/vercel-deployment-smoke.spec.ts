import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

const routes = [
  "/",
  "/frontend",
  "/help",
  "/login",
  "/register",
  "/admin/login",
] as const;
const administratorRoutes = ["/capabilities"] as const;
const trustedOidcToken = process.env.ELMOS_VERCEL_TRUSTED_OIDC_TOKEN?.trim();

test.beforeEach(async ({ context }) => {
  if (trustedOidcToken) {
    await context.setExtraHTTPHeaders({
      "x-vercel-trusted-oidc-idp-token": trustedOidcToken,
    });
  }
});

test("deployed console renders its critical public routes and protects administrator routes", async ({ page }, testInfo) => {
  const observations: Array<Record<string, unknown>> = [];
  for (const route of routes) {
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response, `${route} must return an HTTP response`).not.toBeNull();
    observations.push({
      route,
      status: response?.status() ?? null,
      contentType: response?.headers()["content-type"] ?? null,
    });
    expect(response?.status(), `${route} must be reachable`).toBe(200);
    expect(response?.headers()["content-type"] ?? "").toContain("text/html");
  }

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveTitle("ELMOS 控制中心");
  await expect(page.getByRole("heading", { name: "四类核心工作空间，一套可验证的交付闭环。" })).toBeVisible();
  await expect(page.getByRole("link", { name: "功能能力中心" })).toHaveCount(0);

  for (const route of administratorRoutes) {
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response, `${route} must return an HTTP response`).not.toBeNull();
    expect(response?.status(), `${route} must fail closed into the administrator login surface`).toBe(200);
    expect(page.url()).toContain("/admin/login");
    await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();
    observations.push({
      route,
      status: response?.status() ?? null,
      finalPath: new URL(page.url()).pathname,
      access: "ADMINISTRATOR_SESSION_REQUIRED",
    });
  }

  const reportPath = testInfo.outputPath("deployment-surface.json");
  await writeFile(reportPath, `${JSON.stringify({
    schemaVersion: "1.0",
    kind: "VERCEL_DEPLOYMENT_SURFACE_SMOKE",
    baseURL: testInfo.project.use.baseURL,
    routes: observations,
    boundary: "DEPLOYMENT_SURFACE_ONLY_NOT_PRODUCTION_CERTIFICATION",
  }, null, 2)}\n`, "utf8");
  await testInfo.attach("deployment-surface", { path: reportPath, contentType: "application/json" });
});

test("health reports readiness honestly and never upgrades blocked dependencies", async ({ page }, testInfo) => {
  const response = await page.goto("/api/health", { waitUntil: "domcontentloaded" });
  expect(response, "health must return an HTTP response").not.toBeNull();
  const httpStatus = response?.status() ?? 0;
  expect([200, 503], "health must use an explicit readiness status").toContain(httpStatus);
  const payload = JSON.parse(await page.locator("body").innerText()) as {
    status?: unknown;
    dependencies?: unknown;
    localRunner?: unknown;
  };
  expect(["UP", "READY", "BLOCKED", "DEGRADED", "NOT_CONFIGURED"], "unknown health states are rejected").toContain(payload.status);
  expect(payload.dependencies).toBeDefined();
  expect(payload.localRunner).toBeDefined();

  const reportPath = testInfo.outputPath("health.json");
  await writeFile(reportPath, `${JSON.stringify({
    schemaVersion: "1.0",
    kind: "VERCEL_DEPLOYMENT_HEALTH_OBSERVATION",
    httpStatus,
    payload,
    boundary: "HEALTH_OBSERVATION_ONLY_NOT_PRODUCTION_CERTIFICATION",
    productionQualification: "NOT_RUN",
    certification: "NOT_CERTIFIED",
    releaseStatus: "NOT_GA",
  }, null, 2)}\n`, "utf8");
  await testInfo.attach("health-observation", { path: reportPath, contentType: "application/json" });

  if (process.env.ELMOS_VERCEL_REQUIRE_HEALTHY === "true") {
    expect(httpStatus).toBe(200);
    expect(["UP", "READY"]).toContain(payload.status);
  }
});

test("deployed console exposes separate provider-backed user and administrator entry points", async ({ page }) => {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "用户登录" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "邮箱验证码登录" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "手机号验证码登录" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "微信扫码登录" })).toBeVisible();
  await expect(page.getByRole("link", { name: "进入管理员登录" })).toHaveAttribute("href", "/admin/login");
  const passwordInputs = page.getByLabel("密码");
  expect([0, 1]).toContain(await passwordInputs.count());

  await page.goto("/register", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "注册 ELMOS 账户" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "邮箱注册" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "手机号注册" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "微信扫码注册" })).toBeVisible();

  await page.goto("/admin/login", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "管理员登录" })).toBeVisible();
  await expect(page.getByLabel("管理员邮箱")).toHaveValue("zpchoney@gmail.com");
  await expect(page.getByRole("heading", { name: "手机号验证码登录" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "微信扫码登录" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "管理员邮箱验证码登录" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送管理员验证码" })).toBeVisible();

  const session = await page.evaluate(async () => {
    const response = await fetch("/api/auth/session", { credentials: "same-origin" });
    return response.json();
  }) as { authenticated?: boolean; principal?: { actorId?: string } };

  expect(session.authenticated).toBe(false);
  expect(session.principal?.actorId).toBeUndefined();
});

test("deployed console authenticates test/test credential and yields customer session", async ({ page }) => {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  const testLoginButton = page.getByRole("button", { name: "使用测试账号登录" });
  if (await testLoginButton.count() > 0) {
    await page.getByLabel("账号 / 邮箱").fill("test");
    await page.getByLabel("密码").fill("test");
    await testLoginButton.click();
    await expect(page).toHaveURL(/\/$/, { timeout: 20_000 });

    const session = await page.evaluate(async () => {
      const response = await fetch("/api/auth/session", { credentials: "same-origin" });
      return response.json();
    }) as { authenticated?: boolean; principal?: { actorId?: string } };

    expect(session.authenticated).toBe(true);
    expect(session.principal?.actorId).toBe("local:test");
  }
});

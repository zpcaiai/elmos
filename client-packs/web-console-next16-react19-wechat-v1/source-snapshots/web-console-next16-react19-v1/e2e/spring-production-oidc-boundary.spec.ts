import { expect, test, type Page } from "@playwright/test";

const productionOidcEnabled = process.env.ELMOS_E2E_WEB_SERVER_MODE === "production"
  && process.env.ELMOS_E2E_PRODUCTION_OIDC === "true";
const syntheticRunId = "123e4567-e89b-42d3-a456-426614174000";

test.describe("Spring production OIDC authorization boundary", () => {
  test.skip(!productionOidcEnabled, "Requires the explicit isolated production OIDC harness.");

  test.beforeEach(async ({ page }) => {
    await page.route("**/api/telemetry/events", (route) =>
      route.fulfill({ status: 204, body: "" }));
  });

  async function login(page: Page, identity: string) {
    await page.goto("/login?returnTo=/spring");
    await page.getByRole("link", { name: "使用企业账户登录" }).click();
    await expect(page.getByText("LOCAL ISOLATED OIDC", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "选择合成测试身份" })).toBeVisible();
    await page.getByRole("button", { name: identity }).click();
    await expect(page).toHaveURL(/\/spring$/);
    await expect(page.getByRole("heading", { name: "Java / Spring 老项目一键迁移" })).toBeVisible();
  }

  async function beginLogin(page: Page) {
    await page.goto("/login?returnTo=/spring");
    await page.getByRole("link", { name: "使用企业账户登录" }).click();
    await expect(page.getByText("LOCAL ISOLATED OIDC", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "选择合成测试身份" })).toBeVisible();
  }

  async function expectNoAccountCookies(page: Page) {
    const names = (await page.context().cookies()).map(({ name }) => name);
    for (const name of [
      "__Host-elmos_authorization_flow",
      "__Host-elmos_session",
      "__Host-elmos_access_token",
      "__Host-elmos_refresh_token",
      "__Host-elmos_tenant",
    ]) {
      expect(names).not.toContain(name);
    }
  }

  async function realSpringRead(page: Page) {
    return page.evaluate(async (runId) => {
      const response = await fetch(`/api/spring-upgrades/${runId}`, {
        cache: "no-store",
        credentials: "same-origin",
      });
      return { status: response.status, body: await response.json() };
    }, syntheticRunId);
  }

  async function realSpringCapabilities(page: Page) {
    return page.evaluate(async () => {
      const response = await fetch("/api/spring-upgrades/capabilities", {
        cache: "no-store",
        credentials: "same-origin",
      });
      return { status: response.status, body: await response.json() };
    });
  }

  test("developer claim establishes an HttpOnly session and reaches the real Java Spring engine", async ({
    page,
  }) => {
    await login(page, "以 Spring E2E 开发者登录");
    await expect(page.getByText("企业 OIDC · spring:execute", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "隔离 Runner 未配置" })).toBeDisabled();
    const capabilities = await realSpringCapabilities(page);
    expect(capabilities).toMatchObject({
      status: 200,
      body: {
        packKey: "spring-boot-2-7-18-to-3-5-3",
        transformerConfigured: false,
        independentVerifierConfigured: false,
        runtimeRunnerConfigured: false,
      },
    });
    expect(capabilities.body.routes.length).toBeGreaterThan(0);
    expect(capabilities.body.routes.filter(
      (route: { evidenceStatus: string }) => route.evidenceStatus === "PASSED_LOCAL",
    )).toHaveLength(4);
    await expect(page.getByText(`${capabilities.body.routes.length} 条`, { exact: true })).toBeVisible();
    await expect(realSpringRead(page)).resolves.toMatchObject({
      status: 404,
      body: { errorCode: "SPRING_UPGRADE_RUN_NOT_FOUND", retryable: false },
    });
  });

  test("an anonymous browser is rejected by the Spring API before the engine is contacted", async ({ page }) => {
    await page.goto("/login?returnTo=/spring");
    await expect(realSpringRead(page)).resolves.toMatchObject({
      status: 401,
      body: { errorCode: "ACCOUNT_SESSION_REQUIRED", retryable: false },
    });
    await expectNoAccountCookies(page);
  });

  test("viewer may render the protected shell but the Spring server API denies execution permission", async ({
    page,
  }) => {
    await login(page, "以只读 Viewer 登录");
    await expect(page.getByText("企业 OIDC · spring:execute", { exact: true })).toHaveCount(0);
    await expect(realSpringRead(page)).resolves.toMatchObject({
      status: 403,
      body: { errorCode: "ACCOUNT_PERMISSION_REQUIRED", retryable: false },
    });
  });

  test("a developer from another tenant is rejected before the Java engine is contacted", async ({
    page,
  }) => {
    await login(page, "以其他租户开发者登录");
    await expect(realSpringRead(page)).resolves.toMatchObject({
      status: 403,
      body: { errorCode: "TENANT_ID_NOT_BOUND_TO_ENGINE", retryable: false },
    });
  });

  test("tampered state is rejected and clears the authorization flow without a session", async ({ page }) => {
    await beginLogin(page);
    await page.getByRole("button", { name: "负例：返回不匹配 state" }).click();
    await expect(page).toHaveURL(/\/login\?error=OIDC_STATE_INVALID$/);
    await expect(page.locator(".auth-error")).toContainText("登录 state 已过期或不匹配");
    await expectNoAccountCookies(page);
  });

  test("a signed token with the wrong nonce is rejected without a session", async ({ page }) => {
    await beginLogin(page);
    await page.getByRole("button", { name: "负例：返回 nonce 不匹配令牌" }).click();
    await expect(page).toHaveURL(/\/login\?error=OIDC_NONCE_INVALID$/);
    await expect(page.locator(".auth-error")).toContainText("登录 nonce 校验失败");
    await expectNoAccountCookies(page);
  });

  test("a PKCE verifier mismatch is rejected by the token endpoint without a session", async ({ page }) => {
    await beginLogin(page);
    await page.getByRole("button", { name: "负例：拒绝 PKCE verifier" }).click();
    await expect(page).toHaveURL(/\/login\?error=OIDC_TOKEN_EXCHANGE_REJECTED$/);
    await expect(page.locator(".auth-error")).toContainText("身份提供商拒绝令牌交换");
    await expectNoAccountCookies(page);
  });

  test("logout revokes the access token, clears every account cookie, and protects Spring again", async ({
    page,
  }) => {
    await login(page, "以 Spring E2E 开发者登录");
    const result = await page.evaluate(async () => {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: "{}",
      });
      return { status: response.status, body: await response.json() };
    });
    expect(result).toEqual({
      status: 200,
      body: { loggedOut: true, revocationConfirmed: true, endSessionUrl: null },
    });
    await expectNoAccountCookies(page);
    await page.goto("/spring");
    await expect(page).toHaveURL(/\/login\?returnTo=%2Fspring$/);
  });
});

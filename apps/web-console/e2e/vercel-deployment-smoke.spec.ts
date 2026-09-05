import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

const routes = ["/", "/frontend", "/capabilities", "/help"] as const;
const trustedOidcToken = process.env.ELMOS_VERCEL_TRUSTED_OIDC_TOKEN?.trim();

test.beforeEach(async ({ context }) => {
  if (trustedOidcToken) {
    await context.setExtraHTTPHeaders({
      "x-vercel-trusted-oidc-idp-token": trustedOidcToken,
    });
  }
});

test("deployed console renders its critical public routes", async ({ page }, testInfo) => {
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
  await expect(page.getByRole("link", { name: "功能能力中心" })).toBeVisible();

  const compatibilityResponse = await page.goto("/capabilities/", {
    waitUntil: "domcontentloaded",
  });
  expect(compatibilityResponse?.status()).toBe(200);
  expect(compatibilityResponse?.headers()["content-type"] ?? "").toContain("text/html");
  expect(new URL(page.url()).pathname).toBe("/capabilities");
  await expect(page.getByRole("heading", { name: "功能能力中心" })).toBeVisible();

  const generationCapability = await page.request.get("/api/capabilities/generation");
  expect(generationCapability.status()).toBe(200);
  expect(generationCapability.headers()["content-type"] ?? "").toContain("application/json");
  const generationPayload = await generationCapability.json() as {
    generationStatus?: unknown;
    operationalReadiness?: {
      externalRuntimeAcceptance?: unknown;
      productionCertification?: unknown;
      productionSubstrate?: { boundary?: unknown };
    };
  };
  expect(["READY", "DEGRADED", "BLOCKED", "NOT_CONFIGURED"]).toContain(
    generationPayload.generationStatus,
  );
  expect(generationPayload.operationalReadiness?.externalRuntimeAcceptance).toBe("NOT_RUN");
  expect(generationPayload.operationalReadiness?.productionCertification).toBe("NOT_CERTIFIED");
  expect(generationPayload.operationalReadiness?.productionSubstrate?.boundary).toBe(
    "CONFIGURATION_PRESENCE_ONLY",
  );

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
  const liveness = await page.request.get("/api/health?probe=liveness");
  expect(liveness.status()).toBe(200);
  expect((await liveness.json() as { status?: unknown }).status).toBe("UP");

  const response = await page.request.get("/api/health?probe=readiness");
  const httpStatus = response.status();
  expect([200, 503]).toContain(httpStatus);
  const payload = await response.json() as {
    status?: unknown;
    dependencies?: unknown;
    localRunner?: unknown;
    generation?: { status?: unknown };
    deployment?: { provider?: unknown; commitSha?: unknown; identityStatus?: unknown };
  };
  expect(["UP", "BLOCKED", "DEGRADED"]).toContain(payload.status);
  expect(payload.dependencies).toBeDefined();
  expect(payload.localRunner).toBeDefined();
  expect(["READY", "DEGRADED", "BLOCKED", "NOT_CONFIGURED"]).toContain(
    payload.generation?.status,
  );
  expect(payload.deployment).toEqual({
    provider: "VERCEL",
    commitSha: process.env.ELMOS_VERCEL_EXPECTED_COMMIT_SHA?.trim().toLowerCase(),
    identityStatus: "SHA_BOUND",
  });

  const reportPath = testInfo.outputPath("health.json");
  await writeFile(reportPath, `${JSON.stringify({
    schemaVersion: "1.0",
    kind: "VERCEL_DEPLOYMENT_HEALTH_OBSERVATION",
    httpStatus,
    payload,
    boundary: "CURRENT_SHA_DEPLOYMENT_SURFACE_NOT_PRODUCTION_READINESS_OR_CERTIFICATION",
    productionQualification: "NOT_RUN",
    certification: "NOT_CERTIFIED",
    releaseStatus: "NOT_GA",
  }, null, 2)}\n`, "utf8");
  await testInfo.attach("health-observation", { path: reportPath, contentType: "application/json" });

});

test("deployed console authenticates test/test credential and yields session", async ({ page }) => {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.getByLabel("邮箱").fill("test@example.test");
  await page.getByLabel("密码").fill("test");
  await page.getByRole("button", { name: "使用邮箱登录" }).click();
  await expect(page).toHaveURL(/\/$/, { timeout: 20_000 });

  const session = await page.evaluate(async () => {
    const response = await fetch("/api/auth/session", { credentials: "same-origin" });
    return response.json();
  }) as { authenticated?: boolean; principal?: { actorId?: string } };

  expect(session.authenticated).toBe(true);
  expect(session.principal?.actorId).toBe("local:test");
});

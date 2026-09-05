import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";
import { expect, test, type Page, type Route } from "@playwright/test";

const runId = "123e4567-e89b-42d3-a456-426614174000";
const commit = "a".repeat(40);
const artifactBody = Buffer.from("PK\u0003\u0004ELMOS-E2E");
const artifactSha = createHash("sha256").update(artifactBody).digest("hex");
const snapshotSha = "c".repeat(64);
const productionOidcEnabled = process.env.ELMOS_E2E_WEB_SERVER_MODE === "production"
  && process.env.ELMOS_E2E_PRODUCTION_OIDC === "true";

async function establishProductionOidcSession(page: Page) {
  await page.goto("/login?returnTo=/");
  await expect(page.getByText("身份提供商未配置", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "使用企业账户登录" }).click();
  await expect(page.getByRole("heading", { name: "选择合成测试身份" })).toBeVisible();
  await page.getByRole("button", { name: "以 Spring E2E 开发者登录" }).click();
  await expect(page).toHaveURL(/\/$/);

  const session = await page.evaluate(async () => {
    const response = await fetch("/api/auth/session", { cache: "no-store" });
    return { status: response.status, body: await response.json() };
  });
  expect(session).toMatchObject({
    status: 200,
    body: {
      authenticated: true,
      configured: true,
      principal: {
        actorId: "user:spring-production-e2e",
        organizationId: "spring-production-e2e",
        roles: ["DEVELOPER"],
      },
    },
  });
  expect(session.body.principal.permissions).toContain("spring:execute");
  const cookies = await page.context().cookies();
  for (const name of ["__Host-elmos_session", "__Host-elmos_access_token"]) {
    expect(cookies).toContainEqual(expect.objectContaining({
      name,
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    }));
  }
  expect(cookies.map(({ name }) => name)).not.toContain("__Host-elmos_authorization_flow");
  expect(await page.evaluate(() => document.cookie)).not.toContain("__Host-elmos_");
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
  // The seven Spring UI journeys use browser-level business API fixtures. Keep
  // the authenticated GitHub catalog in that same explicit mock boundary; the
  // separate production OIDC boundary suite does not install this route.
  await page.route("**/api/github-repositories", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "cache-control": "no-store" },
      body: JSON.stringify({
        status: "NOT_CONFIGURED",
        repositories: [],
        message: "GitHub App is outside this Spring UI fixture.",
      }),
    }));
  // This suite exercises the explicit short-lived Spring Runner lease. Keep
  // the account-session probe deterministic and cover its fail-closed 401
  // contract separately in account-session-ui.spec.ts.
  if (productionOidcEnabled) {
    await establishProductionOidcSession(page);
  } else {
    await page.route("**/api/auth/session", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          authenticated: false,
          configured: false,
          principal: null,
          expiresAt: null,
        }),
      }));
  }
});

const capabilities = {
  packKey: "spring-boot-2-7-18-to-3-5-3",
  sourceTuple: { springBoot: "2.7.18", java: "17", build: "Maven 3.9.11" },
  targetTuple: { springBoot: "3.5.3", java: "21", build: "Maven 3.9.11" },
  openRewrite: { rewriteSpring: "6.35.0", mavenPlugin: "6.44.0" },
  routes: [
    {
      routeId: "boot-2.0-2.6-maven-to-boot-3.5.3-java-21",
      packKey: "spring-boot-2-0-2-6-to-3-5-3",
      label: "Spring Boot 2.0–2.6 / Java 8, 11, 17 / Maven",
      sourceFrameworkFamily: "spring-boot",
      buildTool: "maven",
      sourceBootMinInclusive: "2.0.0",
      sourceBootMaxExclusive: "2.7.0",
      sourceJavaVersions: ["11", "17", "8"],
      targetSpringBoot: "3.5.3",
      targetJava: "21",
      recipeId: "io.elmos.openrewrite.SpringBoot2_0To2_6ToBoot3_5_3Java21",
      evidenceStatus: "NOT_RUN",
      verifiedSourceSpringBoot: "",
      verifiedSourceJava: "",
    },
    {
      routeId: "boot-2.7-maven-to-boot-3.2.12-java-17",
      packKey: "spring-boot-2-7-to-3-2-12",
      label: "Spring Boot 2.7.x / Java 8, 11, 17 / Maven → Boot 3.2.12 / Java 17",
      sourceFrameworkFamily: "spring-boot",
      buildTool: "maven",
      sourceBootMinInclusive: "2.7.0",
      sourceBootMaxExclusive: "2.8.0",
      sourceJavaVersions: ["11", "17", "8"],
      targetSpringBoot: "3.2.12",
      targetJava: "17",
      recipeId: "io.elmos.openrewrite.SpringBoot2_7ToBoot3_2_12Java17",
      evidenceStatus: "NOT_RUN",
      verifiedSourceSpringBoot: "",
      verifiedSourceJava: "",
    },
    {
      routeId: "boot-2.7-maven-to-boot-3.5.3-java-21",
      packKey: "spring-boot-2-7-18-to-3-5-3",
      label: "Spring Boot 2.7.x / Java 8, 11, 17 / Maven",
      sourceFrameworkFamily: "spring-boot",
      buildTool: "maven",
      sourceBootMinInclusive: "2.7.0",
      sourceBootMaxExclusive: "2.8.0",
      sourceJavaVersions: ["11", "17", "8"],
      targetSpringBoot: "3.5.3",
      targetJava: "21",
      recipeId: "io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21",
      launchStatus: "DESIGN_PARTNER",
      evidenceStatus: "PASSED_LOCAL",
      verifiedSourceSpringBoot: "2.7.18",
      verifiedSourceJava: "17",
    },
    {
      routeId: "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21",
      packKey: "spring-framework-5-3-mvc-to-spring-boot-3-5-3",
      label: "Spring Framework 5.3.39 MVC / Java 11 / Maven → Boot 3.5.3 / Java 21",
      sourceFrameworkFamily: "spring-mvc",
      buildTool: "maven",
      sourceBootMinInclusive: "5.3.39",
      sourceBootMaxExclusive: "5.3.40",
      exactSourceVersion: "5.3.39",
      sourceConstraint: "exact:5.3.39",
      sourceVersionMatch: "EXACT",
      sourceJavaVersions: ["11"],
      targetSpringBoot: "3.5.3",
      targetJava: "21",
      recipeId: "io.elmos.openrewrite.SpringFramework5_3MvcToSpringBoot3_5_3Java21",
      evidenceStatus: "PASSED_LOCAL",
      verifiedSourceSpringBoot: "5.3.39",
      verifiedSourceJava: "11",
    },
    {
      routeId: "boot-1.5-3.5.15-maven-to-boot-3.5.16-java-21",
      packKey: "spring-boot-1-5-3-5-15-to-3-5-16-inventory-only",
      label: "Spring Boot 1.5–3.5.15 / Java 8, 11, 17, 21 / Maven → Boot 3.5.16 / Java 21",
      sourceFrameworkFamily: "spring-boot",
      buildTool: "maven",
      sourceBootMinInclusive: "1.5.0",
      sourceBootMaxExclusive: "3.5.16",
      sourceJavaVersions: ["8", "11", "17", "21"],
      targetSpringBoot: "3.5.16",
      targetJava: "21",
      recipeId: "",
      evidenceStatus: "NOT_IMPLEMENTED",
      verifiedSourceSpringBoot: "",
      verifiedSourceJava: "",
      notes: "Inventory gap; no executable recipe is available.",
    },
    {
      routeId: "boot-1.5-maven-to-boot-4.1.0-java-21",
      packKey: "spring-to-boot-4-1-0",
      label: "Spring Boot 1.5.x / Java 8 / Maven → Boot 4.1.0 / Java 21",
      sourceFrameworkFamily: "spring-boot",
      buildTool: "maven",
      sourceBootMinInclusive: "1.5.0",
      sourceBootMaxExclusive: "2.0.0",
      sourceJavaVersions: ["8"],
      targetSpringBoot: "4.1.0",
      targetJava: "21",
      recipeId: "io.elmos.openrewrite.SpringBoot1_5ToBoot4_1_0Java21",
      evidenceStatus: "NOT_RUN",
      verifiedSourceSpringBoot: "",
      verifiedSourceJava: "",
    },
  ],
  operatorExperimentalRoutesEnabled: true,
  experimentalRoutesRequireOptIn: true,
  transformerConfigured: true,
  transformerReason: "Rootless private Runner is configured.",
  runtimeRunnerConfigured: true,
  runtimeRunnerReason: "Per-run rootless Runtime is configured.",
  independentVerifierConfigured: true,
  independentVerifierReason: "Separate read-only verifier is configured.",
  downloadRequiresIndependentPass: true,
  runtimeRequiresIndependentPass: true,
};

const completedStages = [
  "IMPORT_GIT",
  "LOCK_SNAPSHOT",
  "FINGERPRINT",
  "SOURCE_BASELINE",
  "EXTRACT_FCM",
  "OPENREWRITE",
  "BUILD_AND_TEST",
  "PACKAGE_ARTIFACT",
  "INDEPENDENT_VALIDATION",
  "READY",
] as const;

function events() {
  return completedStages.map((stage, index) => ({
    sequence: index + 1,
    stage,
    status: "PASS",
    message: `${stage} 已产生摘要绑定证据`,
    observedAt: new Date(Date.UTC(2026, 6, 26, 10, 0, index)).toISOString(),
  }));
}

function completedRun(overrides: Record<string, unknown> = {}) {
  return {
    runId,
    retryOfRunId: null,
    status: "SUCCEEDED",
    stage: "READY",
    runtimeStatus: "NOT_STARTED",
    attempt: 1,
    repositoryUrl: "https://github.com/example/legacy-orders.git",
    requestedRef: "main",
    resolvedCommitSha: commit,
    snapshotId: "snapshot-customer-route",
    snapshotDigest: snapshotSha,
    exactTuple: {
      sourceSpringBoot: "2.7.18",
      sourceFrameworkFamily: "spring-boot",
      sourceFrameworkVersion: "2.7.18",
      sourceJava: "17",
      sourceBuildTool: "maven-3.9.11",
      targetSpringBoot: "3.5.3",
      targetJava: "21",
      targetBuildTool: "maven-3.9.11",
      rewriteSpring: "6.35.0",
      rewriteMavenPlugin: "6.44.0",
    },
    fingerprint: {
      springBootVersion: "2.7.18",
      javaVersion: "17",
      buildTool: "maven",
      modules: [],
      activeCapabilities: ["actuator", "web"],
      unknowns: [],
    },
    fcmArtifact: "evidence/framework-contract-model.json",
    downloadAvailable: true,
    artifactSha256: artifactSha,
    artifactSize: artifactBody.byteLength,
    healthPath: null,
    runtimePort: null,
    failureCode: null,
    failureMessage: null,
    independentValidation: {
      status: "PASS",
      verifierId: "verifier-a",
      artifactSha256: artifactSha,
      evidencePath: "evidence/independent-validation.json",
      decidedAt: "2026-07-26T10:01:00Z",
    },
    events: events(),
    ...overrides,
  };
}

function runWithTarget(
  targetSpringBoot: string,
  targetJava: string,
  overrides: Record<string, unknown> = {},
) {
  const base = completedRun();
  return {
    ...base,
    exactTuple: {
      ...base.exactTuple,
      targetSpringBoot,
      targetJava,
    },
    ...overrides,
  };
}

function activeRun(targetSpringBoot: string, targetJava: string) {
  return runWithTarget(targetSpringBoot, targetJava, {
    status: "RUNNING",
    stage: "BUILD_AND_TEST",
    runtimeStatus: "NOT_STARTED",
    downloadAvailable: false,
    artifactSha256: null,
    artifactSize: null,
    independentValidation: null,
    events: [
      ...events().slice(0, 6),
      {
        sequence: 7,
        stage: "BUILD_AND_TEST",
        status: "RUNNING",
        message: "正在使用不可变目标执行真实构建",
        observedAt: "2026-07-26T10:00:07Z",
      },
    ],
  });
}

function completedMvcRun() {
  const base = completedRun();
  return {
    ...base,
    exactTuple: {
      ...base.exactTuple,
      sourceSpringBoot: null,
      sourceFrameworkFamily: "spring-mvc",
      sourceFrameworkVersion: "5.3.39",
      sourceJava: "11",
    },
    fingerprint: {
      ...base.fingerprint,
      springBootVersion: "UNKNOWN",
      sourceFrameworkFamily: "spring-mvc",
      sourceFrameworkVersion: "5.3.39",
      javaVersion: "11",
      activeCapabilities: ["spring-mvc", "servlet"],
    },
  };
}

async function fulfillJson(route: Route, value: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "cache-control": "no-store" },
    body: JSON.stringify(value),
  });
}

async function fillSpringCredentials(page: Page) {
  if (productionOidcEnabled) {
    await expect(page.getByText("企业 OIDC · spring:execute", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Spring 租户标识")).toHaveValue("spring-production-e2e");
    await expect(page.getByLabel("Spring 执行者标识")).toHaveValue("user:spring-production-e2e");
    await expect(page.getByLabel("Spring 租户标识")).toHaveAttribute("readonly", "");
    await expect(page.getByLabel("Spring 执行者标识")).toHaveAttribute("readonly", "");
    await expect(page.getByLabel("Spring 代理短期令牌")).toHaveCount(0);
    return;
  }
  await page.getByLabel("Spring 租户标识").fill("spring-e2e");
  await page.getByLabel("Spring 执行者标识").fill("user:spring-e2e");
  await page.getByLabel("Spring 代理短期令牌").fill("spring-e2e-short-lived-token-32-characters");
}

async function configureJourneyApi(page: Page) {
  let state = completedRun();
  let postedBody: Record<string, unknown> | undefined;

  await page.route("**/api/spring-upgrades/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/capabilities")) return fulfillJson(route, capabilities);
    if (path.endsWith("/logs")) {
      return fulfillJson(route, {
        runId,
        lines: [
          "snapshot locked sha256:" + snapshotSha,
          "OpenRewrite actual recipe completed",
          "Independent verifier PASS: verifier-a",
        ],
        truncated: false,
      });
    }
    if (path.endsWith("/artifact")) {
      return route.fulfill({
        status: 200,
        headers: {
          "content-type": "application/zip",
          "content-disposition": 'attachment; filename="migrated-spring-boot-3.5.3.zip"',
          "content-length": String(artifactBody.byteLength),
          "x-content-sha256": artifactSha,
        },
        body: artifactBody,
      });
    }
    if (path.endsWith("/runtime/start")) {
      state = completedRun({
        stage: "HEALTH_CHECK",
        runtimeStatus: "HEALTHY",
        runtimePort: 18081,
        healthPath: "/actuator/health",
        events: [
          ...events(),
          {
            sequence: 11,
            stage: "START_APPLICATION",
            status: "PASS",
            message: "隔离 Runner 已启动",
            observedAt: "2026-07-26T10:02:00Z",
          },
          {
            sequence: 12,
            stage: "HEALTH_CHECK",
            status: "PASS",
            message: "健康检查通过",
            observedAt: "2026-07-26T10:02:10Z",
          },
        ],
      });
      return fulfillJson(route, state);
    }
    if (path.endsWith("/runtime/stop")) {
      state = completedRun({
        stage: "STOP_APPLICATION",
        runtimeStatus: "STOPPED",
        events: [
          ...events(),
          {
            sequence: 11,
            stage: "STOP_APPLICATION",
            status: "PASS",
            message: "运行实例已优雅停止",
            observedAt: "2026-07-26T10:03:00Z",
          },
        ],
      });
      return fulfillJson(route, state);
    }
    return fulfillJson(route, state);
  });

  await page.route("**/api/spring-upgrades", async (route) => {
    postedBody = route.request().postDataJSON() as Record<string, unknown>;
    return fulfillJson(route, completedRun());
  });

  return {
    postedBody: () => postedBody,
  };
}

test("Spring 真实旅程 UI 可完成导入、证据查看、下载、启动、健康检查与停止", async ({
  page,
}) => {
  const api = await configureJourneyApi(page);
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/spring");
  await expect(page.getByText("Runner 与独立验证器已配置，可以提交精确路线。")).toBeVisible();
  await fillSpringCredentials(page);

  // The catalog is rendered from the engine contract, and only the tuple that
  // carries recorded evidence may display PASSED_LOCAL.
  const catalog = page.getByRole("table", { name: "Spring 遗留版本路线目录" });
  await expect(catalog.getByRole("cell", { name: "Spring Boot [2.0.0, 2.7.0)" })).toBeVisible();
  await expect(catalog.getByRole("cell", { name: "Spring Boot [2.7.0, 2.8.0)" }).first()).toBeVisible();
  await expect(catalog.getByRole("cell", { name: "Spring Framework MVC exact 5.3.39" })).toBeVisible();
  await expect(
    catalog.getByRole("cell", { name: "PASSED_LOCAL @ Spring Framework MVC 5.3.39 / Java 11" }),
  ).toBeVisible();
  await expect(catalog.getByRole("cell", { name: "NOT_IMPLEMENTED · Spring Boot" })).toHaveCount(1);
  await expect(page.getByText("NOT_IMPLEMENTED 仅记录 inventory gap", { exact: false })).toBeVisible();
  await expect(
    catalog.getByRole("cell", { name: "PASSED_LOCAL @ Spring Boot 2.7.18 / Java 17" }),
  ).toBeVisible();
  const targetSelector = page.getByLabel("Spring 目标精确版本");
  await expect(targetSelector.locator('option[value="3.5.16|21"]')).toHaveCount(0);
  await expect(targetSelector.locator('option[value="4.1.0|21"]')).toHaveCount(0);
  await page.getByLabel("允许实验性升级路线").check();
  await expect(targetSelector.locator('option[value="4.1.0|21"]')).toHaveCount(1);

  await page.getByLabel("Git 仓库 URL").fill("https://github.com/example/legacy-orders.git");
  await page.getByLabel("Branch / Tag").fill("main");
  await page.getByLabel("预期 Commit（可选）").fill(commit);
  await page.getByLabel("验证通过后自动一键启动").check();
  await page.getByRole("button", { name: "开始真实迁移" }).click();

  await expect(page.getByText("Spring Boot 2.7.18 · Java 17 · maven")).toBeVisible();
  await expect(page.getByText("PASS", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "下载新项目 ZIP" })).toBeVisible();
  expect(api.postedBody()).toMatchObject({
    sourceMode: "PUBLIC_GIT",
    repositoryUrl: "https://github.com/example/legacy-orders.git",
    requestedRef: "main",
    expectedCommitSha: commit,
    startAfterVerification: true,
    targetSpringBoot: "3.5.3",
    targetJava: "21",
  });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载新项目 ZIP" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("migrated-spring-boot-3.5.3.zip");
  await expect(page.getByText("ZIP 的长度和 SHA-256 已在浏览器复算并与独立验证证据一致。")).toBeVisible();

  await page.getByRole("button", { name: "一键启动" }).click();
  await expect(page.getByText("127.0.0.1:18081/actuator/health")).toBeVisible();
  await expect(page.getByText("健康检查通过").first()).toBeVisible();

  await page.getByRole("button", { name: "查看日志" }).click();
  await expect(page.getByText("Independent verifier PASS: verifier-a")).toBeVisible();

  await page.getByRole("button", { name: "停止", exact: true }).click();
  await expect(page.getByText("运行实例已优雅停止").first()).toBeVisible();
  await expect(page.getByText("STOPPED", { exact: true }).first()).toBeVisible();

  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("Spring 迁移失败保持可见且不伪造 Run、Artifact 或验证通过", async ({ page }) => {
  await page.route("**/api/spring-upgrades/capabilities", (route) =>
    fulfillJson(route, capabilities));
  await page.route("**/api/spring-upgrades", (route) =>
    fulfillJson(route, {
      errorCode: "UNSUPPORTED_SOURCE_TUPLE",
      message: "仅支持精确 Spring Boot 2.7.18 / Java 17 路线。",
      retryable: false,
    }, 422));

  await page.goto("/spring");
  await fillSpringCredentials(page);
  await page.getByLabel("Git 仓库 URL").fill("https://github.com/example/not-supported.git");
  await page.getByLabel("Branch / Tag").fill("main");
  await page.getByRole("button", { name: "开始真实迁移" }).click();

  await expect(page.getByText(
    "UNSUPPORTED_SOURCE_TUPLE: 仅支持精确 Spring Boot 2.7.18 / Java 17 路线。",
  )).toBeVisible();
  await expect(page.getByText("尚未创建")).toBeVisible();
  await expect(page.getByText("NOT_RUN", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "下载新项目 ZIP" })).toHaveCount(0);
});

test("Rootless Runtime 未证明时禁用自动启动并持续展示安全阻断原因", async ({ page }) => {
  await page.route("**/api/spring-upgrades/capabilities", (route) =>
    fulfillJson(route, {
      ...capabilities,
      runtimeRunnerConfigured: false,
      runtimeRunnerReason: "未发现受证明的 Rootless Docker socket；禁止降级到宿主机进程。",
    }));
  await page.route("**/api/github-repositories", (route) =>
    fulfillJson(route, { status: "NOT_CONFIGURED", repositories: [] }));

  await page.goto("/spring");

  await expect(page.getByText("BLOCKED · 不降级执行")).toBeVisible();
  await expect(page.getByText("未发现受证明的 Rootless Docker socket；禁止降级到宿主机进程。").first())
    .toBeVisible();
  await expect(page.getByLabel("验证通过后自动一键启动")).toBeDisabled();
  await expect(page.getByRole("button", { name: "一键启动" })).toBeDisabled();
});

test("GitHub App 私有仓库入口只跳转经过校验的 GitHub HTTPS 安装地址", async ({ page }) => {
  await page.route("**/api/spring-upgrades/capabilities", (route) =>
    fulfillJson(route, capabilities));
  await page.route("**/api/github-repositories", (route) =>
    fulfillJson(route, { status: "NOT_CONFIGURED", repositories: [] }));
  await page.route("**/api/github-installation", (route) =>
    fulfillJson(route, {
      status: "AWAITING_GITHUB_INSTALLATION",
      installationUrl: "https://github.com/apps/elmos/installations/new?state=signed-state",
      expiresAt: "2026-07-26T10:10:00Z",
    }));
  await page.route("https://github.com/apps/elmos/installations/new?state=signed-state", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<html><title>GitHub App installation</title><body>GitHub 安装页</body></html>",
    }));

  await page.goto("/spring");
  await page.getByLabel("输入方式").selectOption("GITHUB_APP");
  await expect(page.getByText("最长 1 小时的短期 Token", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "安装 / 更新 GitHub App" }).click();

  await expect(page).toHaveURL(
    "https://github.com/apps/elmos/installations/new?state=signed-state",
  );
});

test("页面刷新后使用会话内 Run ID 与显式租户身份恢复最近运行", async ({ page }) => {
  const recovered = runWithTarget("3.2.12", "17");
  let releaseCapability = () => {};
  const capabilityGate = new Promise<void>((resolve) => {
    releaseCapability = resolve;
  });
  await page.addInitScript(({ key, value }) => {
    window.sessionStorage.setItem(key, value);
  }, { key: "elmos.spring.latest-run-id", value: runId });
  await page.route("**/api/spring-upgrades/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) {
      await capabilityGate;
      return fulfillJson(route, capabilities);
    }
    return fulfillJson(route, recovered);
  });
  await page.route("**/api/github-repositories", (route) =>
    fulfillJson(route, { status: "NOT_CONFIGURED", repositories: [] }));

  await page.goto("/spring");
  await fillSpringCredentials(page);
  await expect(page.getByLabel("恢复 Run UUID")).toHaveValue(runId);
  await page.getByRole("button", { name: "恢复运行" }).click();
  await expect(page.getByText("已按 Run UUID 与当前租户身份恢复持久迁移运行。")).toBeVisible();
  await expect(page.getByText(`${runId.slice(0, 8)} · #1`)).toBeVisible();
  await expect(page.getByLabel("Spring 目标精确版本")).toHaveValue("3.2.12|17");
  releaseCapability();
  const targetSelector = page.getByLabel("Spring 目标精确版本");
  await expect(targetSelector).toBeEnabled();
  await expect(targetSelector.locator('option[value="3.5.3|21"]')).toHaveCount(1);
  await expect(targetSelector).toHaveValue("3.2.12|17");
  const metrics = page.getByLabel("精确迁移路线");
  await expect(metrics.getByText("Boot 3.2.12", { exact: true })).toBeVisible();
  await expect(metrics.getByText("Java 17 · 当前 Run 不可变目标", { exact: true })).toBeVisible();
  await expect(page.getByText(
    "Spring Boot 3.2.12 / Java 17 真实测试；失败时最多一次确定性修复。",
  )).toBeVisible();
  await expect(page.getByRole("button", { name: "下载新项目 ZIP" })).toBeVisible();
});

test("恢复活动迁移后锁定不可变目标并禁止重复提交", async ({ page }) => {
  await page.route("**/api/spring-upgrades/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) return fulfillJson(route, capabilities);
    return fulfillJson(route, activeRun("3.2.12", "17"));
  });
  await page.route("**/api/github-repositories", (route) =>
    fulfillJson(route, { status: "NOT_CONFIGURED", repositories: [] }));

  await page.goto("/spring");
  await fillSpringCredentials(page);
  await page.getByLabel("恢复 Run UUID").fill(runId);
  await page.getByRole("button", { name: "恢复运行" }).click();

  await expect(page.getByLabel("Spring 目标精确版本")).toHaveValue("3.2.12|17");
  await expect(page.getByLabel("Spring 目标精确版本")).toBeDisabled();
  await expect(page.getByRole("button", { name: "迁移运行中" })).toBeDisabled();
  await expect(page.getByLabel("精确迁移路线").getByText(
    "Java 17 · 当前 Run 不可变目标",
    { exact: true },
  )).toBeVisible();
});

test("MVC Run 检测结果按源 family 展示精确 Spring Framework 版本", async ({ page }) => {
  await page.route("**/api/spring-upgrades/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) return fulfillJson(route, capabilities);
    return fulfillJson(route, completedMvcRun());
  });
  await page.route("**/api/github-repositories", (route) =>
    fulfillJson(route, { status: "NOT_CONFIGURED", repositories: [] }));

  await page.goto("/spring");
  await fillSpringCredentials(page);
  await page.getByLabel("恢复 Run UUID").fill(runId);
  await page.getByRole("button", { name: "恢复运行" }).click();

  await expect(page.getByText(
    "Spring Framework MVC 5.3.39 · Java 11 · maven",
    { exact: true },
  )).toBeVisible();
  await expect(page.getByText("Spring Boot UNKNOWN", { exact: false })).toHaveCount(0);
});

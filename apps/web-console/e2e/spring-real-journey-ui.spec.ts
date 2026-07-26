import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";
import { expect, test, type Page, type Route } from "@playwright/test";

const runId = "123e4567-e89b-42d3-a456-426614174000";
const commit = "a".repeat(40);
const artifactBody = Buffer.from("PK\u0003\u0004ELMOS-E2E");
const artifactSha = createHash("sha256").update(artifactBody).digest("hex");
const snapshotSha = "c".repeat(64);

const capabilities = {
  packKey: "spring-boot-2-7-18-to-3-5-3",
  sourceTuple: { springBoot: "2.7.18", java: "17", build: "Maven 3.9.11" },
  targetTuple: { springBoot: "3.5.3", java: "21", build: "Maven 3.9.11" },
  openRewrite: { rewriteSpring: "6.35.0", mavenPlugin: "6.44.0" },
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

async function fulfillJson(route: Route, value: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "cache-control": "no-store" },
    body: JSON.stringify(value),
  });
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
  await page.getByLabel("Git 仓库 URL").fill("https://github.com/example/legacy-orders.git");
  await page.getByLabel("Branch / Tag").fill("main");
  await page.getByLabel("预期 Commit（可选）").fill(commit);
  await page.getByLabel("验证通过后自动一键启动").check();
  await page.getByRole("button", { name: "开始真实迁移" }).click();

  await expect(page.getByText("2.7.18 · Java 17 · maven")).toBeVisible();
  await expect(page.getByText("PASS", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "下载新项目 ZIP" })).toBeVisible();
  expect(api.postedBody()).toMatchObject({
    sourceMode: "PUBLIC_GIT",
    repositoryUrl: "https://github.com/example/legacy-orders.git",
    requestedRef: "main",
    expectedCommitSha: commit,
    startAfterVerification: true,
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

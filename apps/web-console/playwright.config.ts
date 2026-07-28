import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import path from "node:path";

process.env.NO_PROXY = "127.0.0.1,localhost";
process.env.no_proxy = "127.0.0.1,localhost";
delete process.env.NO_COLOR;

const repositoryRoot = path.resolve(__dirname, "../..");
const translationSourceRoot = path.resolve(__dirname, "e2e/fixtures/translation-sources");
const translationCasesRoot = path.resolve(__dirname, "e2e/fixtures/translation-cases");
const runnerToken = "elmos-e2e-local-token-32-characters";
const uvPath = process.env.ELMOS_UV_PATH ?? "/opt/homebrew/bin/uv";
const webPort = Number.parseInt(process.env.ELMOS_E2E_PORT ?? "3200", 10);
const webServerMode = process.env.ELMOS_E2E_WEB_SERVER_MODE ?? "development";
const webServerBundler = process.env.ELMOS_E2E_WEB_BUNDLER ?? "turbopack";
if (!["development", "production"].includes(webServerMode)) {
  throw new Error("ELMOS_E2E_WEB_SERVER_MODE_INVALID");
}
if (!["turbopack", "webpack"].includes(webServerBundler)) {
  throw new Error("ELMOS_E2E_WEB_BUNDLER_INVALID");
}
const configuredRunnerRoot = process.env.ELMOS_E2E_RUNNER_ROOT;
const runnerRoot = configuredRunnerRoot
  ?? path.join(tmpdir(), `elmos-web-console-e2e-${webPort}`);
const outputDir = process.env.ELMOS_E2E_OUTPUT_DIR ?? "./test-results/playwright";
const reportDir = process.env.ELMOS_E2E_REPORT_DIR ?? "./test-results/playwright-report";
const nextDistDir = `.next-e2e-${webPort}`;
const baseURL = `http://127.0.0.1:${webPort}`;
const webServerEnvironment = { ...process.env };
delete webServerEnvironment.FORCE_COLOR;
delete webServerEnvironment.NO_COLOR;
process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT = runnerRoot;
process.env.ELMOS_E2E_AUTO_RUNNER_ROOT = configuredRunnerRoot ? "false" : "true";
process.env.ELMOS_E2E_EFFECTIVE_DIST_DIR = path.resolve(__dirname, nextDistDir);

export default defineConfig({
  testDir: "./e2e",
  outputDir,
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: true,
  workers: 2,
  forbidOnly: true,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { outputFolder: reportDir, open: "never" }]],
  use: {
    baseURL,
    locale: "zh-CN",
    colorScheme: "light",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: {
    command: webServerMode === "production"
      ? `pnpm build && pnpm start --hostname 127.0.0.1 --port ${webPort}`
      : `pnpm dev --hostname 127.0.0.1 --port ${webPort}${webServerBundler === "webpack" ? " --webpack" : ""}`,
    url: `${baseURL}/api/capabilities/generation`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...webServerEnvironment,
      ELMOS_LOCAL_RUNNER_ENABLED: "true",
      ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
      ELMOS_REPOSITORY_ROOT: repositoryRoot,
      ELMOS_TRANSLATION_SOURCE_ROOT: translationSourceRoot,
      ELMOS_TRANSLATION_CASES_ROOT: translationCasesRoot,
      ELMOS_UV_PATH: uvPath,
      ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
      ELMOS_LOCAL_RUNNER_AUTH_TOKEN: runnerToken,
      ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT: new Date(
        Date.now() + 60 * 60_000,
      ).toISOString(),
      ELMOS_LOCAL_RUNNER_TENANT_ID: "local-e2e",
      ELMOS_LOCAL_RUNNER_ACTOR_ID: "user:e2e",
      ELMOS_NEXT_DIST_DIR: nextDistDir,
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile-chromium",
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: "mobile-webkit",
      use: {
        ...devices["iPhone 15"],
        viewport: { width: 393, height: 852 },
      },
    },
  ],
});

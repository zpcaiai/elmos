import { defineConfig, devices } from "@playwright/test";
import { generateKeyPairSync } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import path from "node:path";

process.env.NO_PROXY = "127.0.0.1,localhost";
process.env.no_proxy = "127.0.0.1,localhost";
delete process.env.NO_COLOR;

const repositoryRoot = path.resolve(__dirname, "../..");
const translationSourceRoot = path.resolve(__dirname, "e2e/fixtures/translation-sources");
const translationCasesRoot = path.resolve(__dirname, "e2e/fixtures/translation-cases");
const runnerToken = "elmos-e2e-local-token-32-characters";

function resolveExecutableOnPath(name: string): string | null {
  for (const directory of (process.env.PATH ?? "").split(path.delimiter)) {
    if (!directory) continue;
    const candidate = path.resolve(directory, name);
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

const configuredUvPath = process.env.ELMOS_UV_PATH?.trim();
const uvPath = configuredUvPath
  ? path.resolve(configuredUvPath)
  : resolveExecutableOnPath(process.platform === "win32" ? "uv.exe" : "uv");
if (!uvPath || !existsSync(uvPath)) {
  throw new Error("ELMOS_UV_PATH_REQUIRED");
}
const webPort = Number.parseInt(process.env.ELMOS_E2E_PORT ?? "3200", 10);
const githubPort = Number.parseInt(
  process.env.ELMOS_E2E_GITHUB_PORT ?? String(webPort + 99),
  10,
);
const webServerMode = process.env.ELMOS_E2E_WEB_SERVER_MODE ?? "development";
const webServerTimeout = webServerMode === "production" ? 300_000 : 120_000;
const webServerBundler = process.env.ELMOS_E2E_WEB_BUNDLER ?? "turbopack";
const chromiumChannel = process.env.ELMOS_E2E_CHROMIUM_CHANNEL?.trim();
const fullRuntimeLease = process.env.ELMOS_E2E_FULL_RUNTIME_TTL === "true";
if (!["development", "production"].includes(webServerMode)) {
  throw new Error("ELMOS_E2E_WEB_SERVER_MODE_INVALID");
}
if (!["turbopack", "webpack"].includes(webServerBundler)) {
  throw new Error("ELMOS_E2E_WEB_BUNDLER_INVALID");
}
const configuredRunnerRoot = process.env.ELMOS_E2E_RUNNER_ROOT;
const runnerRoot = configuredRunnerRoot
  ?? path.join(tmpdir(), `elmos-web-console-e2e-${webPort}`);
const enginePort = webPort + 1_000;
const auditPort = webPort + 2_000;
const auditFixtureKey = "elmos-frt-local-audit-fixture-key";
const auditFixtureTenant = "frt-local-qualification";
const auditFixtureActor = "playwright-qualification";
const engineRoot = path.resolve(repositoryRoot, "engines/frontend-client-engine");
const frtSecurityRoot = path.join(runnerRoot, "frt-security");
const frtEvidenceRoot = path.join(runnerRoot, "frt-evidence");
const frtRunStoreRoot = path.join(runnerRoot, "frt-runs");
const frtPrivateKeyPath = path.join(frtSecurityRoot, "identity-private.pem");
const frtTrustStorePath = path.join(frtSecurityRoot, "trust-store.json");
mkdirSync(frtSecurityRoot, { recursive: true, mode: 0o700 });
mkdirSync(frtEvidenceRoot, { recursive: true, mode: 0o700 });
if (!existsSync(frtPrivateKeyPath) || !existsSync(frtTrustStorePath)) {
  const { privateKey: frtPrivateKey, publicKey: frtPublicKey } = generateKeyPairSync("ed25519");
  writeFileSync(frtPrivateKeyPath, frtPrivateKey.export({ type: "pkcs8", format: "pem" }), { mode: 0o600 });
  chmodSync(frtPrivateKeyPath, 0o600);
  writeFileSync(frtTrustStorePath, `${JSON.stringify({
    schemaVersion: "1.0",
    keys: [{
      keyId: "frt-e2e-identity-key",
      authority: "frt-e2e-web-console",
      publicKeyPem: frtPublicKey.export({ type: "spki", format: "pem" }).toString(),
      purposes: ["IDENTITY"],
      activeFrom: new Date(Date.now() - 60 * 60_000).toISOString(),
      expiresAt: new Date(Date.now() + 2 * 60 * 60_000).toISOString(),
      revoked: false,
    }],
  }, null, 2)}\n`, { mode: 0o600 });
}
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
  webServer: [
    ...(webServerMode === "production" ? [{
      command: `node ${path.join(repositoryRoot, "scripts/frt/local_audit_fixture_server.mjs")}`,
      url: `http://127.0.0.1:${auditPort}/health`,
      reuseExistingServer: false,
      timeout: webServerTimeout,
      env: {
        ...webServerEnvironment,
        ELMOS_FRT_AUDIT_FIXTURE_HOST: "127.0.0.1",
        ELMOS_FRT_AUDIT_FIXTURE_PORT: String(auditPort),
        ELMOS_FRT_AUDIT_FIXTURE_KEY: auditFixtureKey,
        ELMOS_FRT_AUDIT_FIXTURE_TENANT: auditFixtureTenant,
        ELMOS_FRT_AUDIT_FIXTURE_ACTOR: auditFixtureActor,
      },
    }] : []),
    {
      command: `pnpm --dir ${engineRoot} run build && node ${path.join(engineRoot, "dist/src/server.js")}`,
      url: `http://127.0.0.1:${enginePort}/health`,
      reuseExistingServer: false,
      timeout: webServerTimeout,
      env: {
        ...webServerEnvironment,
        ELMOS_FRONTEND_PORT: String(enginePort),
        ELMOS_FRONTEND_HOST: "127.0.0.1",
        ELMOS_FRT_TRUST_STORE_PATH: frtTrustStorePath,
        ELMOS_FRT_EVIDENCE_ROOTS: frtEvidenceRoot,
        ELMOS_FRT_RUN_STORE_ROOT: frtRunStoreRoot,
      },
    },
    {
      command: "node e2e/github-api-mock.mjs",
      url: `http://127.0.0.1:${githubPort}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        ...webServerEnvironment,
        ELMOS_E2E_GITHUB_PORT: String(githubPort),
      },
    },
    {
      command: webServerMode === "production"
        ? `pnpm build && pnpm start --hostname 127.0.0.1 --port ${webPort}`
        : `pnpm dev --hostname 127.0.0.1 --port ${webPort}${webServerBundler === "webpack" ? " --webpack" : ""}`,
      url: `${baseURL}/api/capabilities/generation`,
      reuseExistingServer: false,
      timeout: webServerTimeout,
      env: {
        ...webServerEnvironment,
        ELMOS_LOCAL_RUNNER_ENABLED: "true",
        ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
        ELMOS_REPOSITORY_ROOT: repositoryRoot,
        ELMOS_TRANSLATION_SOURCE_ROOT: translationSourceRoot,
        ELMOS_TRANSLATION_CASES_ROOT: translationCasesRoot,
        ELMOS_UV_PATH: uvPath,
        ELMOS_PROJECT_SYNTHESIS_UV_CACHE: process.env.ELMOS_PROJECT_SYNTHESIS_UV_CACHE
          ?? path.join(homedir(), ".cache", "uv"),
        ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
        ELMOS_LOCAL_RUNNER_AUTH_TOKEN: runnerToken,
        ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT: new Date(
          Date.now() + 60 * 60_000,
        ).toISOString(),
        ELMOS_LOCAL_RUNNER_TENANT_ID: "local-e2e",
        ELMOS_LOCAL_RUNNER_ACTOR_ID: "user:e2e",
        ELMOS_PRECISION_MIGRATION_JOB_ROOT: path.join(runnerRoot, "precision-migration-jobs"),
        ELMOS_PRECISION_EVIDENCE_ROOTS: repositoryRoot,
        ELMOS_FRONTEND_ENGINE_URL: `http://127.0.0.1:${enginePort}`,
        ELMOS_FRT_IDENTITY_PRIVATE_KEY_PATH: frtPrivateKeyPath,
        ELMOS_FRT_IDENTITY_AUTHORITY: "frt-e2e-web-console",
        ELMOS_FRT_IDENTITY_KEY_ID: "frt-e2e-identity-key",
        ELMOS_NEXT_DIST_DIR: nextDistDir,
        ...(webServerMode === "production" ? {
          ELMOS_CONTROL_PLANE_BASE_URL: `http://127.0.0.1:${auditPort}`,
          ELMOS_OPERATIONS_API_KEY: auditFixtureKey,
          ELMOS_OPERATIONS_TENANT_ID: auditFixtureTenant,
          ELMOS_OPERATIONS_ACTOR_ID: auditFixtureActor,
          ELMOS_OPERATIONS_API_KEY_EXPIRES_AT: new Date(
            Date.now() + 60 * 60_000,
          ).toISOString(),
        } : {}),
        ELMOS_LOCAL_GITHUB_PUBLISH_ENABLED: "true",
        ELMOS_GENERATION_GITHUB_API_BASE: `http://127.0.0.1:${githubPort}`,
        ELMOS_GENERATION_GITHUB_ALLOW_HTTP_LOCALHOST: "true",
        ELMOS_ALLOW_TEST_RUNTIME_TTL: fullRuntimeLease ? "false" : "true",
        ELMOS_TEST_RUNTIME_TTL_MS: fullRuntimeLease ? "600000" : "12000",
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(chromiumChannel ? { channel: chromiumChannel } : {}),
        viewport: { width: 1440, height: 900 },
      },
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
        ...(chromiumChannel ? { channel: chromiumChannel } : {}),
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

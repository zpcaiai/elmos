import { defineConfig, devices } from "@playwright/test";
import { execFileSync } from "node:child_process";
import {
  createHash,
  createPrivateKey,
  generateKeyPairSync,
  X509Certificate,
} from "node:crypto";
import {
  chmodSync,
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import path from "node:path";

process.env.NO_PROXY = "127.0.0.1,localhost";
process.env.no_proxy = "127.0.0.1,localhost";
delete process.env.NO_COLOR;

const repositoryRoot = path.resolve(__dirname, "../..");
const translationSourceFixtureRoot = path.resolve(__dirname, "e2e/fixtures/translation-sources");
const translationCasesFixtureRoot = path.resolve(__dirname, "e2e/fixtures/translation-cases");
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
  ? realpathSync(path.resolve(configuredUvPath))
  : resolveExecutableOnPath(process.platform === "win32" ? "uv.exe" : "uv");
if (!uvPath || !existsSync(uvPath)) {
  throw new Error("ELMOS_UV_PATH_REQUIRED");
}
const canonicalUvPath = realpathSync(uvPath);
const webPort = Number.parseInt(process.env.ELMOS_E2E_PORT ?? "3200", 10);
const canonicalTemporaryRoot = realpathSync(tmpdir());
const translationFixtureRoot = path.join(
  canonicalTemporaryRoot,
  `elmos-web-console-e2e-translation-fixtures-${webPort}`,
);
const translationSourceRoot = path.join(translationFixtureRoot, "sources");
const translationCasesRoot = path.join(translationFixtureRoot, "cases");
rmSync(translationFixtureRoot, { recursive: true, force: true });
mkdirSync(translationFixtureRoot, { recursive: true, mode: 0o700 });
cpSync(translationSourceFixtureRoot, translationSourceRoot, { recursive: true });
cpSync(translationCasesFixtureRoot, translationCasesRoot, { recursive: true });
const shardedTranslationSource = path.join(translationSourceRoot, "sharded-python");
const shardedTranslationCases = path.join(translationCasesRoot, "sharded-python-empty");
mkdirSync(shardedTranslationSource, { recursive: true, mode: 0o700 });
mkdirSync(shardedTranslationCases, { recursive: true, mode: 0o700 });
writeFileSync(
  path.join(shardedTranslationSource, "many_functions.py"),
  `${Array.from({ length: 2_001 }, (_, index) => {
    const name = `function_${String(index + 1).padStart(5, "0")}`;
    return `def ${name}(value: int) -> int:\n    return value\n`;
  }).join("\n")}\n`,
  { mode: 0o600 },
);
writeFileSync(
  path.join(shardedTranslationCases, "README.md"),
  "This empty case bundle forces a bounded two-shard diagnostic report.\n",
  { mode: 0o600 },
);
const githubPort = Number.parseInt(
  process.env.ELMOS_E2E_GITHUB_PORT ?? String(webPort + 99),
  10,
);
const webServerMode = process.env.ELMOS_E2E_WEB_SERVER_MODE ?? "development";
const productionOidcEnabled = webServerMode === "production"
  && process.env.ELMOS_E2E_PRODUCTION_OIDC === "true";
// Cold Webpack/Turbopack compilation on a clean CI runner can exceed two minutes.
// Keep a bounded timeout, but give both modes the same production-sized budget so
// infrastructure startup is not misreported as a browser assertion failure.
const webServerTimeout = 300_000;
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
  ?? path.join(canonicalTemporaryRoot, `elmos-web-console-e2e-${webPort}`);
const enginePort = webPort + 1_000;
const auditPort = webPort + 2_000;
const oidcPort = webPort + 3_000;
const nextUpstreamPort = productionOidcEnabled ? webPort + 4_000 : webPort;
const springEnginePort = webPort + 5_000;
const productionHarnessHealthPort = webPort + 6_000;
const auditFixtureKey = "elmos-frt-local-audit-fixture-key";
const auditFixtureTenant = "frt-local-qualification";
const auditFixtureActor = "playwright-qualification";
const engineRoot = path.resolve(repositoryRoot, "engines/frontend-client-engine");
const engineServer = path.join(engineRoot, "dist/src/server.js");
const skipEngineBuild = process.env.ELMOS_E2E_ENGINE_SKIP_BUILD === "true";
if (skipEngineBuild && !existsSync(engineServer)) {
  throw new Error("ELMOS_E2E_ENGINE_BUILD_REQUIRED");
}
const frtSecurityRoot = path.join(runnerRoot, "frt-security");
const frtEvidenceRoot = path.join(runnerRoot, "frt-evidence");
const frtRunStoreRoot = path.join(runnerRoot, "frt-runs");
const smokeProjectsRoot = path.join(runnerRoot, "smoke-projects");
const smokeRuntimeStateRoot = path.join(runnerRoot, "smoke-runtime-state");
mkdirSync(smokeProjectsRoot, { recursive: true, mode: 0o700 });
mkdirSync(smokeRuntimeStateRoot, { recursive: true, mode: 0o700 });
process.env.ELMOS_E2E_SMOKE_PROJECTS_ROOT = smokeProjectsRoot;
const productionOidcRoot = path.join(runnerRoot, "production-oidc");
const productionCaKeyPath = path.join(productionOidcRoot, "local-ca-key.pem");
const productionCaCertificatePath = path.join(productionOidcRoot, "local-ca-certificate.pem");
const productionTlsKeyPath = path.join(productionOidcRoot, "localhost-key.pem");
const productionTlsCertificatePath = path.join(productionOidcRoot, "localhost-certificate.pem");
const productionTlsRequestPath = path.join(productionOidcRoot, "localhost.csr");
const productionTlsExtensionsPath = path.join(productionOidcRoot, "localhost-extensions.cnf");
const productionNodeCaPreflight = path.join(__dirname, "e2e/fixtures/production-node-ca-preflight.cjs");
const productionOidcClientId = "elmos-web-console-e2e";
const productionOidcClientSecret = "elmos-production-e2e-client-secret-32";
const productionOidcOrigin = `https://localhost:${oidcPort}`;
const configuredSpringEngineJar = process.env.ELMOS_E2E_SPRING_ENGINE_JAR?.trim();
const springEngineJar = configuredSpringEngineJar
  ? path.resolve(configuredSpringEngineJar)
  : path.join(repositoryRoot, "apps/java-engine-worker/target/elmos-java-engine-worker-0.1.0-SNAPSHOT-exec.jar");
const configuredJavaPath = process.env.ELMOS_E2E_JAVA_PATH?.trim();
const javaPath = configuredJavaPath
  ? path.resolve(configuredJavaPath)
  : resolveExecutableOnPath(process.platform === "win32" ? "java.exe" : "java");
let productionTlsSpkiSha256: string | null = null;
if (productionOidcEnabled) {
  const opensslPath = resolveExecutableOnPath(process.platform === "win32" ? "openssl.exe" : "openssl");
  if (!opensslPath) throw new Error("ELMOS_E2E_PRODUCTION_OIDC_OPENSSL_REQUIRED");
  if (!javaPath || !existsSync(javaPath)) throw new Error("ELMOS_E2E_JAVA_PATH_REQUIRED");
  if (!existsSync(springEngineJar)) throw new Error("ELMOS_E2E_REAL_SPRING_ENGINE_JAR_REQUIRED");
  mkdirSync(productionOidcRoot, { recursive: true, mode: 0o700 });
  try {
    const completeIdentity = [
      productionCaKeyPath,
      productionCaCertificatePath,
      productionTlsKeyPath,
      productionTlsCertificatePath,
    ].every(existsSync);
    // The Playwright coordinator and its test workers can evaluate this config
    // more than once. Reissuing the leaf here would leave the already-launched
    // Chrome pinned to the previous key, so one runner root owns one immutable
    // TLS identity for its whole lifetime.
    if (!completeIdentity) {
      execFileSync(opensslPath, [
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", productionCaKeyPath,
        "-out", productionCaCertificatePath,
        "-days", "1",
        "-sha256",
        "-subj", "/CN=ELMOS isolated production E2E CA",
        "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
      ], { stdio: "pipe" });
      execFileSync(opensslPath, [
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", productionTlsKeyPath,
        "-out", productionTlsRequestPath,
        "-sha256",
        "-subj", "/CN=ELMOS isolated production E2E",
      ], { stdio: "pipe" });
      writeFileSync(productionTlsExtensionsPath, [
        "subjectAltName=IP:127.0.0.1,DNS:localhost",
        "basicConstraints=critical,CA:FALSE",
        "keyUsage=critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage=serverAuth",
        "subjectKeyIdentifier=hash",
        "authorityKeyIdentifier=keyid,issuer",
        "",
      ].join("\n"), { mode: 0o600 });
      execFileSync(opensslPath, [
        "x509", "-req",
        "-in", productionTlsRequestPath,
        "-CA", productionCaCertificatePath,
        "-CAkey", productionCaKeyPath,
        "-CAcreateserial",
        "-out", productionTlsCertificatePath,
        "-days", "1",
        "-sha256",
        "-extfile", productionTlsExtensionsPath,
      ], { stdio: "pipe" });
    }
    chmodSync(productionCaKeyPath, 0o600);
    chmodSync(productionCaCertificatePath, 0o600);
    chmodSync(productionTlsKeyPath, 0o600);
    chmodSync(productionTlsCertificatePath, 0o600);
    const caCertificate = new X509Certificate(readFileSync(productionCaCertificatePath));
    const certificate = new X509Certificate(readFileSync(productionTlsCertificatePath));
    const leafKey = createPrivateKey(readFileSync(productionTlsKeyPath));
    const now = Date.now();
    if (
      !certificate.checkPrivateKey(leafKey)
      || !certificate.verify(caCertificate.publicKey)
      || certificate.checkIP("127.0.0.1") !== "127.0.0.1"
      || certificate.checkHost("localhost") !== "localhost"
      || Date.parse(certificate.validFrom) > now
      || Date.parse(certificate.validTo) <= now
    ) {
      throw new Error("ELMOS_E2E_PRODUCTION_OIDC_TLS_IDENTITY_INVALID");
    }
    productionTlsSpkiSha256 = createHash("sha256")
      .update(certificate.publicKey.export({ type: "spki", format: "der" }))
      .digest("base64");
    if (!/^[A-Za-z0-9+/]{43}=$/.test(productionTlsSpkiSha256)) {
      throw new Error("ELMOS_E2E_PRODUCTION_OIDC_SPKI_PIN_INVALID");
    }
  } catch (error) {
    throw new Error("ELMOS_E2E_PRODUCTION_OIDC_TLS_PREFLIGHT_FAILED", { cause: error });
  }
}
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
const baseURL = productionOidcEnabled
  ? `https://127.0.0.1:${webPort}`
  : `http://127.0.0.1:${webPort}`;
const nextServerBaseURL = `http://127.0.0.1:${nextUpstreamPort}`;
const webServerEnvironment = { ...process.env };
delete webServerEnvironment.FORCE_COLOR;
delete webServerEnvironment.NO_COLOR;
process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT = runnerRoot;
process.env.ELMOS_E2E_AUTO_RUNNER_ROOT = configuredRunnerRoot ? "false" : "true";
process.env.ELMOS_E2E_EFFECTIVE_TRANSLATION_FIXTURE_ROOT = translationFixtureRoot;
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
    ...(productionOidcEnabled ? [{
      command: "node e2e/fixtures/production-oidc-harness.mjs",
      url: `http://127.0.0.1:${productionHarnessHealthPort}/health`,
      reuseExistingServer: false,
      timeout: webServerTimeout,
      env: {
        ...webServerEnvironment,
        ELMOS_E2E_OIDC_PORT: String(oidcPort),
        ELMOS_E2E_TLS_PROXY_PORT: String(webPort),
        ELMOS_E2E_NEXT_UPSTREAM_PORT: String(nextUpstreamPort),
        ELMOS_E2E_AUDIT_UPSTREAM_PORT: String(auditPort),
        ELMOS_E2E_HARNESS_HEALTH_PORT: String(productionHarnessHealthPort),
        ELMOS_E2E_OIDC_CLIENT_ID: productionOidcClientId,
        ELMOS_E2E_OIDC_CLIENT_SECRET: productionOidcClientSecret,
        ELMOS_E2E_OIDC_REDIRECT_URI: `${baseURL}/api/auth/callback`,
        ELMOS_E2E_OIDC_ISSUER: productionOidcOrigin,
        ELMOS_E2E_OIDC_LISTEN_HOST: "::1",
        ELMOS_E2E_TLS_KEY_PATH: productionTlsKeyPath,
        ELMOS_E2E_TLS_CERT_PATH: productionTlsCertificatePath,
      },
    }] : []),
    ...(productionOidcEnabled ? [{
      command: `"${javaPath}" -jar "${springEngineJar}"`,
      url: `http://127.0.0.1:${springEnginePort}/actuator/health`,
      reuseExistingServer: false,
      timeout: webServerTimeout,
      env: {
        ...webServerEnvironment,
        ELMOS_ENGINE_PORT: String(springEnginePort),
        ELMOS_SPRING_UPGRADE_ENABLED: "false",
        ELMOS_SPRING_UPGRADE_WORKSPACE_ROOT: path.join(runnerRoot, "spring-engine-workspace"),
      },
    }] : []),
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
      command: skipEngineBuild
        ? `node ${engineServer}`
        : `pnpm --dir ${engineRoot} run build && node ${engineServer}`,
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
        ? `pnpm build && pnpm start --hostname 127.0.0.1 --port ${nextUpstreamPort}`
        : `pnpm dev --hostname 127.0.0.1 --port ${webPort}${webServerBundler === "webpack" ? " --webpack" : ""}`,
      url: `${nextServerBaseURL}/api/capabilities/generation`,
      reuseExistingServer: false,
      timeout: webServerTimeout,
      env: {
        ...webServerEnvironment,
        ELMOS_LOCAL_RUNNER_ENABLED: "true",
        ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
        ELMOS_REPOSITORY_ROOT: repositoryRoot,
        ELMOS_TRANSLATION_SOURCE_ROOT: translationSourceRoot,
        ELMOS_TRANSLATION_CASES_ROOT: translationCasesRoot,
        ELMOS_UV_PATH: canonicalUvPath,
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
        ELMOS_SMOKE_PROJECTS_ROOT: smokeProjectsRoot,
        ELMOS_RUNTIME_STATE_DIR: smokeRuntimeStateRoot,
        // 冒烟 fixture 只用标准库；e2e 不依赖网络安装依赖。
        ELMOS_SMOKE_SKIP_INSTALL: "true",
        ELMOS_SMOKE_MAX_ACTIVE_SESSIONS: "2",
        ...(webServerMode === "production" ? {
          ELMOS_CONTROL_PLANE_BASE_URL: productionOidcEnabled
            ? productionOidcOrigin
            : `http://127.0.0.1:${auditPort}`,
          ELMOS_OPERATIONS_API_KEY: auditFixtureKey,
          ELMOS_OPERATIONS_TENANT_ID: auditFixtureTenant,
          ELMOS_OPERATIONS_ACTOR_ID: auditFixtureActor,
          ELMOS_OPERATIONS_API_KEY_EXPIRES_AT: new Date(
            Date.now() + 60 * 60_000,
          ).toISOString(),
          ...(productionOidcEnabled ? {
            ELMOS_PUBLIC_ORIGIN: baseURL,
            ELMOS_SESSION_SECRET: "elmos-production-e2e-session-secret-at-least-32-characters",
            ELMOS_OIDC_ISSUER_URI: productionOidcOrigin,
            ELMOS_OIDC_AUTHORIZATION_ENDPOINT: `${productionOidcOrigin}/authorize`,
            ELMOS_OIDC_TOKEN_ENDPOINT: `${productionOidcOrigin}/token`,
            ELMOS_OIDC_JWKS_URI: `${productionOidcOrigin}/.well-known/jwks.json`,
            ELMOS_OIDC_REVOCATION_ENDPOINT: `${productionOidcOrigin}/revoke`,
            ELMOS_OIDC_CLIENT_ID: productionOidcClientId,
            ELMOS_OIDC_CLIENT_SECRET: productionOidcClientSecret,
            ELMOS_OIDC_REDIRECT_URI: `${baseURL}/api/auth/callback`,
            ELMOS_OIDC_AUDIENCE: "elmos-spring-production-e2e",
            ELMOS_OIDC_SCOPES: "openid profile email",
            NODE_EXTRA_CA_CERTS: productionCaCertificatePath,
            SSL_CERT_FILE: productionCaCertificatePath,
            NODE_OPTIONS: `${webServerEnvironment.NODE_OPTIONS ?? ""} --use-openssl-ca --require=${productionNodeCaPreflight}`.trim(),
            ELMOS_SPRING_PROXY_ENABLED: "true",
            ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID: "spring-production-e2e",
            JAVA_ENGINE_BASE_URL: `http://127.0.0.1:${springEnginePort}`,
          } : {}),
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
        ...(productionTlsSpkiSha256 ? {
          launchOptions: {
            args: [`--ignore-certificate-errors-spki-list=${productionTlsSpkiSha256}`],
          },
        } : {}),
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
        ...(productionTlsSpkiSha256 ? {
          launchOptions: {
            args: [`--ignore-certificate-errors-spki-list=${productionTlsSpkiSha256}`],
          },
        } : {}),
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

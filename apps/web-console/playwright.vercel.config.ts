import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";

const configuredBaseURL = process.env.ELMOS_E2E_BASE_URL?.trim();
const configuredChromiumExecutable = process.env.ELMOS_E2E_CHROMIUM_EXECUTABLE?.trim();
if (!configuredBaseURL) {
  throw new Error("ELMOS_E2E_BASE_URL_REQUIRED");
}

let baseURL: string;
try {
  const parsed = new URL(configuredBaseURL);
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error("unsupported protocol");
  }
  if (parsed.username || parsed.password || parsed.hash) {
    throw new Error("credentials and fragments are forbidden");
  }
  parsed.search = "";
  parsed.pathname = parsed.pathname.replace(/\/+$/, "") || "/";
  baseURL = parsed.toString().replace(/\/$/, "");
} catch (error) {
  throw new Error("ELMOS_E2E_BASE_URL_INVALID", { cause: error });
}
if (configuredChromiumExecutable && !existsSync(configuredChromiumExecutable)) {
  throw new Error("ELMOS_E2E_CHROMIUM_EXECUTABLE_NOT_FOUND");
}

export default defineConfig({
  testDir: "./e2e",
  testMatch: /vercel-deployment-smoke\.spec\.ts/,
  outputDir: "./test-results/vercel-deployment-smoke",
  reporter: [
    ["list"],
    ["json", { outputFile: "./test-results/vercel-deployment-smoke/results.json" }],
    ["html", { outputFolder: "./test-results/vercel-deployment-smoke-report", open: "never" }],
  ],
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    locale: "zh-CN",
    colorScheme: "light",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ...(process.env.https_proxy || process.env.http_proxy
      ? { proxy: { server: (process.env.https_proxy || process.env.http_proxy)! } }
      : {}),
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(configuredChromiumExecutable ? { launchOptions: { executablePath: configuredChromiumExecutable } } : {}),
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});

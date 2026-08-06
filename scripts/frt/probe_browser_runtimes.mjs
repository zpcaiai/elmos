#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { createReadStream, existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptRoot, "../..");
const webRoot = path.join(repositoryRoot, "apps/web-console");
const requireFromWeb = createRequire(path.join(webRoot, "package.json"));
const { firefox, webkit } = requireFromWeb("@playwright/test");
const launch = process.argv.includes("--launch");

async function sha256File(filePath) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) digest.update(chunk);
  return `sha256:${digest.digest("hex")}`;
}

async function probe(name, browserType) {
  const executablePath = browserType.executablePath();
  const executablePresent = existsSync(executablePath);
  const result = {
    name,
    executable_present: executablePresent,
    executable_sha256: executablePresent ? await sha256File(executablePath) : null,
    launch_attempted: launch && executablePresent,
    launch_available: false,
    detected_version: null,
    reason: executablePresent ? (launch ? null : "LAUNCH_NOT_REQUESTED") : "PLAYWRIGHT_RUNTIME_NOT_INSTALLED",
  };
  if (!launch || !executablePresent) return result;
  try {
    const browser = await browserType.launch({ headless: true, timeout: 30_000 });
    result.detected_version = browser.version();
    result.launch_available = true;
    result.reason = null;
    await browser.close();
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    result.reason = "BROWSER_LAUNCH_FAILED";
    result.launch_error_sha256 = `sha256:${createHash("sha256").update(detail).digest("hex")}`;
  }
  return result;
}

const packageJson = JSON.parse(readFileSync(path.join(webRoot, "package.json"), "utf8"));
const output = {
  schema_version: 1,
  kind: "FRT_PLAYWRIGHT_RUNTIME_PREFLIGHT",
  playwright_version: packageJson.devDependencies?.["@playwright/test"] ?? null,
  runtimes: {
    firefox: await probe("firefox", firefox),
    webkit: await probe("webkit", webkit),
  },
  boundaries: {
    downloads_attempted: false,
    browser_journeys_executed: false,
    external_state: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  },
};

process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);

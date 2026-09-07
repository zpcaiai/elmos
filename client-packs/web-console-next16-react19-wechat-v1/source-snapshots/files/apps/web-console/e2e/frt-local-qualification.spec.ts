import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

interface NavigationSample {
  readonly domContentLoadedMs: number;
  readonly loadMs: number;
  readonly firstContentfulPaintMs: number | null;
  readonly transferBytes: number;
  readonly resourceCount: number;
  readonly horizontalOverflowPixels: number;
}

function percentile(values: readonly number[], quantile: number): number {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * quantile) - 1)] ?? Infinity;
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
});

test("FRT production rendering meets the governed local performance budget", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const samples: NavigationSample[] = [];
  for (let index = 0; index < 5; index += 1) {
    await page.goto(`/frontend?qualification_sample=${index}`, { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "前端仓库转换工厂" })).toBeVisible();
    samples.push(await page.evaluate(() => {
      const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
      const paints = performance.getEntriesByType("paint") as PerformanceEntry[];
      const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
      return {
        domContentLoadedMs: Math.round(navigation.domContentLoadedEventEnd),
        loadMs: Math.round(navigation.loadEventEnd),
        firstContentfulPaintMs: paints.find((entry) => entry.name === "first-contentful-paint")?.startTime == null
          ? null
          : Math.round(paints.find((entry) => entry.name === "first-contentful-paint")!.startTime),
        transferBytes: resources.reduce((total, entry) => total + entry.transferSize, 0),
        resourceCount: resources.length,
        horizontalOverflowPixels: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
      };
    }));
  }

  const fcpSamples = samples.flatMap((sample) => sample.firstContentfulPaintMs == null
    ? []
    : [sample.firstContentfulPaintMs]);
  const budget = {
    p95DomContentLoadedMs: 5_000,
    p95LoadMs: 8_000,
    p95FirstContentfulPaintMs: 5_000,
    maximumHorizontalOverflowPixels: 0,
    maximumConsoleErrors: 0,
  } as const;
  const result = {
    schemaVersion: "1.0",
    kind: "FRT_LOCAL_BROWSER_PERFORMANCE",
    browserProject: testInfo.project.name,
    webServerMode: process.env.ELMOS_E2E_WEB_SERVER_MODE ?? "development",
    sampleCount: samples.length,
    samples,
    summary: {
      p95DomContentLoadedMs: percentile(samples.map((sample) => sample.domContentLoadedMs), 0.95),
      p95LoadMs: percentile(samples.map((sample) => sample.loadMs), 0.95),
      p95FirstContentfulPaintMs: fcpSamples.length ? percentile(fcpSamples, 0.95) : null,
      maximumHorizontalOverflowPixels: Math.max(...samples.map((sample) => sample.horizontalOverflowPixels)),
      consoleErrors,
    },
    budget,
    boundary: "LOCAL_ENGINEERING_EVIDENCE_NOT_PRODUCTION_CAPACITY_CERTIFICATION",
  };
  const evidencePath = testInfo.outputPath("performance-evidence.json");
  writeFileSync(evidencePath, `${JSON.stringify(result, null, 2)}\n`);
  await testInfo.attach("performance-evidence", {
    path: evidencePath,
    contentType: "application/json",
  });
  expect(result.summary.p95DomContentLoadedMs).toBeLessThanOrEqual(budget.p95DomContentLoadedMs);
  expect(result.summary.p95LoadMs).toBeLessThanOrEqual(budget.p95LoadMs);
  if (result.summary.p95FirstContentfulPaintMs !== null) {
    expect(result.summary.p95FirstContentfulPaintMs).toBeLessThanOrEqual(budget.p95FirstContentfulPaintMs);
  }
  expect(result.summary.maximumHorizontalOverflowPixels).toBe(budget.maximumHorizontalOverflowPixels);
  expect(consoleErrors).toHaveLength(budget.maximumConsoleErrors);
});

test("FRT visual output is captured as an unapproved content-addressed candidate", async ({ page }, testInfo) => {
  await page.goto("/frontend", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "前端仓库转换工厂" })).toBeVisible();
  const screenshotPath = testInfo.outputPath("frt-frontend-visual-candidate.png");
  await page.screenshot({
    path: screenshotPath,
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
  const screenshot = readFileSync(screenshotPath);
  const manifest = {
    schemaVersion: "1.0",
    kind: "FRT_VISUAL_BASELINE_CANDIDATE",
    browserProject: testInfo.project.name,
    viewport: testInfo.project.use.viewport ?? null,
    locale: testInfo.project.use.locale ?? null,
    colorScheme: "light",
    reducedMotion: "reduce",
    sourcePath: "/frontend",
    screenshotSha256: `sha256:${createHash("sha256").update(screenshot).digest("hex")}`,
    screenshotByteCount: screenshot.byteLength,
    approvalState: "CANDIDATE_AWAITING_INDEPENDENT_APPROVAL",
    approver: null,
    approvalEvidence: null,
  };
  const manifestPath = testInfo.outputPath("visual-candidate-manifest.json");
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  await testInfo.attach("visual-candidate", { path: screenshotPath, contentType: "image/png" });
  await testInfo.attach("visual-candidate-manifest", { path: manifestPath, contentType: "application/json" });
  expect(screenshot.byteLength).toBeGreaterThan(10_000);
  expect(manifest.approvalState).toBe("CANDIDATE_AWAITING_INDEPENDENT_APPROVAL");
});

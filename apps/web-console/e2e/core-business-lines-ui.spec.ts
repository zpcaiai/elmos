import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { unzipSync } from "fflate";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

for (const businessLine of [
  {
    path: "/spring",
    heading: "Java / Spring 老项目一键迁移",
    readyText: "完整真实旅程",
  },
  {
    path: "/translation",
    heading: "全库跨语言转换",
    readyText: "选择源语言与目标语言",
  },
] as const) {
  test(`${businessLine.heading} 在桌面与移动视口可操作且通过自动可访问性检查`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });

    await page.goto(businessLine.path);
    await expect(page.getByRole("heading", { name: businessLine.heading })).toBeVisible();
    await expect(page.getByText(businessLine.readyText, { exact: true })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}

test("跨语言整库范围只保存发现与拆分交接，不伪造执行结果", async ({ page }) => {
  await page.goto("/translation");
  await page.getByLabel("仓库引用").fill("local:e2e-customer-repository");
  await page.getByLabel("评估范围").selectOption("repository");
  await page.getByRole("button", { name: "保存路线交接" }).click();
  await expect(page.getByText("整个仓库必须先导入与当前仓库引用", { exact: false })).toBeVisible();

  const digest = "a".repeat(64);
  await page.getByLabel("导入仓库清单 JSON").setInputFiles({
    name: "repository-route-plan.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({
      schema_version: "1.0.0",
      kind: "elmos.repository-route-plan",
      status: "PLANNED",
      repository_ref: "local:e2e-customer-repository",
      snapshot_sha256: digest,
      snapshot_consistency: "STABLE_READ_ONLY_SCAN",
      route_id: "java-to-python",
      source_language: "java",
      target_language: "python",
      file_count: 1,
      source_file_count: 1,
      source_bytes: 128,
      language_counts: { java: 1, csharp: 0, go: 0, rust: 0, python: 0, typescript: 0 },
      ignored_symlink_count: 0,
      work_units: [{
        id: "WU-00001",
        route_id: "java-to-python",
        source_path: "src/main/java/example/Order.java",
        source_sha256: digest,
        source_bytes: 128,
        status: "DISCOVERY_REQUIRED",
        execution_status: "NOT_RUN",
        required_inputs: ["function_name", "behavior_cases_json"],
        declared_profile: "typed-pure-function-v1",
        unsupported_until_discovered: ["object_graph", "database"],
      }],
      execution_status: "NOT_RUN",
      external_verification_status: "NOT_RUN",
      certification_status: "NOT_CERTIFIED",
      limitations: ["Repository-wide success is not inferred."],
    })),
  });
  await expect(page.getByText("服务端已校验只读清单：1 个源文件拆为 1 个待发现工作单元", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "整库工作单元" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "src/main/java/example/Order.java" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "DISCOVERY_REQUIRED · NOT_RUN" })).toBeVisible();
  await page.getByRole("button", { name: "保存路线交接" }).click();
  await expect(page.getByText("整库路线交接已绑定 1 个工作单元；转换执行仍为 NOT_RUN。")).toBeVisible();
  await expect(page.getByText("清单只读取受支持源文件", { exact: false })).toBeVisible();
});

test("发现报告的接受判定发生在服务端，READY 判定必须带分析器事实", async ({ request }) => {
  const digest = "c".repeat(64);
  const snapshot = "d".repeat(64);
  const baseReport = {
    schema_version: "1.0.0",
    kind: "elmos.repository-discovery-report",
    status: "DISCOVERED",
    repository_ref: "local:e2e-customer-repository",
    snapshot_sha256: snapshot,
    route_id: "java-to-python",
    source_language: "java",
    target_language: "python",
    profile: "typed-pure-function-v1",
    work_unit_count: 2,
    discovered_count: 2,
    ready_count: 1,
    execution_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
    results: [
      {
        id: "WU-00001",
        source_path: "src/main/java/example/Pricing.java",
        declared_sha256: digest,
        verdict: "READY",
        profile: "typed-pure-function-v1",
        execution_status: "NOT_RUN",
        function_name: "calculate",
        parameter_count: 2,
        return_type: "number",
        analyzer: "JDK Compiler Tree API",
        rejected_candidates: [],
      },
      {
        id: "WU-00002",
        source_path: "src/main/java/example/Storage.java",
        declared_sha256: digest,
        verdict: "UNSUPPORTED",
        profile: "typed-pure-function-v1",
        execution_status: "NOT_RUN",
        reason: "No candidate declaration stayed inside the bounded profile.",
        rejected_candidates: [{ candidate: "read", reason: "JAVA_UNSUPPORTED_STATEMENT:Try" }],
      },
    ],
  };
  const post = (report: unknown, snapshotSha256 = snapshot) =>
    request.post("/api/translation/discovery-report", {
      data: {
        repositoryRef: "local:e2e-customer-repository",
        routeId: "java-to-python",
        snapshotSha256,
        sourceLanguage: "java",
        targetLanguage: "python",
        report,
      },
    });

  const accepted = await post(baseReport);
  expect(accepted.ok()).toBe(true);
  const acceptedBody = await accepted.json();
  expect(acceptedBody.status).toBe("ACCEPTED");
  expect(acceptedBody.report.ready_count).toBe(1);
  expect(acceptedBody.report.verdict_counts).toEqual({ READY: 1, UNSUPPORTED: 1 });

  for (const [mutation, expectedCode] of [
    [{ execution_status: "PASSED" }, "DISCOVERY_EXECUTION_CLAIMED"],
    [{ certification_status: "CERTIFIED" }, "DISCOVERY_CERTIFICATION_CLAIMED"],
    [{ ready_count: 2 }, "DISCOVERY_READY_COUNT_DRIFT"],
    [{ route_id: "java-to-java" }, "DISCOVERY_ROUTE_UNKNOWN"],
    [
      { results: [{ ...baseReport.results[0], analyzer: undefined }, baseReport.results[1]] },
      "DISCOVERY_READY_WITHOUT_ANALYZER",
    ],
    [
      { results: [{ ...baseReport.results[0], function_name: "" }, baseReport.results[1]] },
      "DISCOVERY_READY_WITHOUT_FUNCTION",
    ],
    [
      { results: [{ ...baseReport.results[0], source_path: "../../etc/passwd" }, baseReport.results[1]] },
      "DISCOVERY_PATH_ESCAPES_REPOSITORY",
    ],
  ] as const) {
    const rejected = await post({ ...baseReport, ...mutation });
    expect(rejected.ok()).toBe(false);
    const body = await rejected.json();
    expect(body.status).toBe("BLOCKED");
    expect(body.errorCode).toBe(expectedCode);
  }

  // A report produced from a different tree must not bind to this plan.
  const wrongSnapshot = await post(baseReport, "e".repeat(64));
  expect((await wrongSnapshot.json()).errorCode).toBe("DISCOVERY_SNAPSHOT_MISMATCH");
});

test("整库清单的接受判定发生在服务端，被篡改的客户端请求同样失败关闭", async ({ request }) => {
  const digest = "b".repeat(64);
  const basePlan = {
    schema_version: "1.0.0",
    kind: "elmos.repository-route-plan",
    status: "PLANNED",
    repository_ref: "local:e2e-customer-repository",
    snapshot_sha256: digest,
    snapshot_consistency: "STABLE_READ_ONLY_SCAN",
    route_id: "java-to-python",
    source_language: "java",
    target_language: "python",
    file_count: 1,
    source_file_count: 1,
    source_bytes: 128,
    language_counts: { java: 1, csharp: 0, go: 0, rust: 0, python: 0, typescript: 0 },
    ignored_symlink_count: 0,
    work_units: [{
      id: "WU-00001",
      route_id: "java-to-python",
      source_path: "src/main/java/example/Order.java",
      source_sha256: digest,
      source_bytes: 128,
      status: "DISCOVERY_REQUIRED",
      execution_status: "NOT_RUN",
      required_inputs: ["function_name", "behavior_cases_json"],
      declared_profile: "typed-pure-function-v1",
      unsupported_until_discovered: ["object_graph"],
    }],
    execution_status: "NOT_RUN",
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
    limitations: ["Repository-wide success is not inferred."],
  };
  const post = (plan: unknown) => request.post("/api/translation/repository-plan", {
    data: {
      repositoryRef: "local:e2e-customer-repository",
      routeId: "java-to-python",
      sourceLanguage: "java",
      targetLanguage: "python",
      plan,
    },
  });

  const accepted = await post(basePlan);
  expect(accepted.ok()).toBe(true);
  expect((await accepted.json()).status).toBe("ACCEPTED");

  for (const [mutation, expectedCode] of [
    [{ execution_status: "PASSED" }, "PLAN_EXECUTION_CLAIMED"],
    [{ certification_status: "CERTIFIED" }, "PLAN_CERTIFICATION_CLAIMED"],
    [{ route_id: "java-to-java" }, "PLAN_ROUTE_UNKNOWN"],
    [{ source_file_count: 2 }, "PLAN_SOURCE_FILE_COUNT_INVALID"],
    [{ limitations: [] }, "PLAN_LIMITATIONS_INVALID"],
    [
      { work_units: [{ ...basePlan.work_units[0], source_path: "../../etc/passwd" }] },
      "WORK_UNIT_PATH_ESCAPES_REPOSITORY",
    ],
  ] as const) {
    const rejected = await post({ ...basePlan, ...mutation });
    expect(rejected.ok()).toBe(false);
    const body = await rejected.json();
    expect(body.status).toBe("BLOCKED");
    expect(body.errorCode).toBe(expectedCode);
  }
});

test("跨语言整库受控任务完成真实回放、构建、恢复和摘要校验下载", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "有副作用的代表整库旅程只执行一次");
  test.setTimeout(300_000);

  await page.goto("/translation");
  await expect(page.getByText(
    "单个转换任务硬上限为 10,000 个已报告功能义务行（最多 5 个内容寻址分片，每片 2,000）。非 Python 路线可能仍有 inventory 未知范围，不能把行数当作项目真实功能总数。超过上限会在接受转换、计费、原生编译与代码生成前失败关闭；请先按仓库、模块或授权工作区拆分为多个任务。",
    { exact: true },
  )).toBeVisible();
  await page.getByLabel("跨语言租户标识").fill("local-e2e");
  await page.getByLabel("跨语言执行者标识").fill("user:e2e");
  await page.getByLabel("跨语言 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
  await page.getByLabel("受控源码工作区 ID").fill("pure-python");
  await page.getByLabel("独立行为用例包 ID").fill("pure-python-holdout");
  await page.getByRole("button", { name: /python 到 typescript/i }).click();
  await page.getByRole("button", { name: "启动整库转换" }).click();

  await expect(page.getByText("COMPLETE", { exact: true }).last()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("PASSED", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("1/1 = 100.00%", { exact: true })).toBeVisible();
  await expect(page.getByText("完整 · MEASURED", { exact: true })).toBeVisible();
  const jobId = await page.getByText(/[0-9a-f]{8}-[0-9a-f-]{27}/).last().textContent();
  expect(jobId).toMatch(/^[0-9a-f-]{36}$/);

  await page.reload();
  await page.getByLabel("跨语言租户标识").fill("local-e2e");
  await page.getByLabel("跨语言执行者标识").fill("user:e2e");
  await page.getByLabel("跨语言 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
  await expect(page.getByLabel("恢复任务 UUID")).toHaveValue(jobId ?? "");
  await page.getByRole("button", { name: "恢复任务" }).click();
  await expect(page.getByText("COMPLETE", { exact: true }).last()).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载摘要校验归档" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("python-to-typescript-complete.zip");

  const reportDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载转换报告" }).click();
  const reportDownload = await reportDownloadPromise;
  expect(reportDownload.suggestedFilename()).toBe("FUNCTION_CONVERSION_REPORT.md");
  const downloadedReportPath = await reportDownload.path();
  if (!downloadedReportPath) throw new Error("Playwright did not expose the conversion report path");
  const markdown = await readFile(downloadedReportPath, "utf8");
  expect(markdown).toContain("## 转换总览");
  expect(markdown).toContain("1/1 = 100.00%");
  expect(markdown).toContain("## 逐功能转换结果");

  const denied = await page.request.get(`/api/translation/jobs/${jobId}/report`, {
    headers: {
      authorization: "Bearer elmos-e2e-local-token-32-characters",
      "x-elmos-tenant": "other-e2e-tenant",
      "x-elmos-actor": "user:e2e",
    },
  });
  expect(denied.status()).toBe(403);

  const runnerRoot = process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT;
  if (!runnerRoot) throw new Error("ELMOS_E2E_EFFECTIVE_RUNNER_ROOT_REQUIRED");
  const storedReport = path.join(
    runnerRoot,
    "tenants",
    "local-e2e",
    "translation-jobs",
    jobId ?? "",
    "pipeline",
    "FUNCTION_CONVERSION_REPORT.md",
  );
  const originalReport = await readFile(storedReport);
  try {
    await writeFile(storedReport, Buffer.concat([originalReport, Buffer.from("\ntampered\n")]));
    const tampered = await page.request.get(`/api/translation/jobs/${jobId}/report`, {
      headers: {
        authorization: "Bearer elmos-e2e-local-token-32-characters",
        "x-elmos-tenant": "local-e2e",
        "x-elmos-actor": "user:e2e",
      },
    });
    expect(tampered.status()).toBe(409);
    expect((await tampered.json()).reason).toBe("TRANSLATION_REPORT_INTEGRITY_MISMATCH");
  } finally {
    await writeFile(storedReport, originalReport);
  }

  await page.getByLabel("受控源码工作区 ID").fill("pure-python");
  await page.getByLabel("独立行为用例包 ID").fill("pure-python-empty");
  await page.getByRole("button", { name: /python 到 typescript/i }).click();
  await page.getByRole("button", { name: "启动整库转换" }).click();
  await expect(page.getByText("blocked · 100%", { exact: true })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("0/1 = 0.00%", { exact: true })).toBeVisible();
  const failedFunction = page.locator("details").filter({ hasText: "SKIPPED_NO_CASES" });
  await expect(failedFunction).toBeVisible();
  await failedFunction.locator("summary").click();
  await expect(failedFunction).toContainText(
    "No independent behavior-case corpus was supplied for this unit.",
  );
  await expect(failedFunction).toContainText(
    "独立行为用例 JSON，覆盖正常、边界和反例后重新运行转换。",
  );
  await expect(page.getByRole("button", { name: "下载摘要校验归档" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "下载转换报告" })).toBeEnabled();

  const blockedReportPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载转换报告" }).click();
  const blockedReport = await blockedReportPromise;
  const blockedReportPath = await blockedReport.path();
  if (!blockedReportPath) throw new Error("Playwright did not expose the blocked report path");
  const blockedMarkdown = await readFile(blockedReportPath, "utf8");
  expect(blockedMarkdown).toContain("0/1 = 0.00%");
  expect(blockedMarkdown).toContain("原代码块：");
  expect(blockedMarkdown).toContain("目标代码块：");
  expect(blockedMarkdown).toContain("NOT_GENERATED");

  await page.getByLabel("受控源码工作区 ID").fill("sharded-python");
  await page.getByLabel("独立行为用例包 ID").fill("sharded-python-empty");
  await page.getByRole("button", { name: /python 到 typescript/i }).click();
  await page.getByRole("button", { name: "启动整库转换" }).click();
  // The preceding job is also BLOCKED. Wait on this job's unique metric first so a stale
  // terminal status cannot satisfy the assertion while the new request is still polling.
  await expect(page.getByText("0/2001 = 0.00%", { exact: true })).toBeVisible({ timeout: 240_000 });
  await expect(page.getByText("blocked · 100%", { exact: true })).toBeVisible();
  const bundleButton = page.getByRole("button", { name: "下载完整转换报告包" });
  await expect(bundleButton).toBeEnabled();
  const bundleDownloadPromise = page.waitForEvent("download");
  await bundleButton.click();
  const bundleDownload = await bundleDownloadPromise;
  expect(bundleDownload.suggestedFilename()).toBe("FUNCTION_CONVERSION_REPORT_BUNDLE.zip");
  const bundleDownloadPath = await bundleDownload.path();
  if (!bundleDownloadPath) throw new Error("Playwright did not expose the conversion report bundle path");
  const bundleEntries = unzipSync(await readFile(bundleDownloadPath));
  expect(Object.keys(bundleEntries).sort()).toEqual([
    "FUNCTION_CONVERSION_REPORT.md",
    "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json",
    "functional-conversion-report-shards/report-00001.json",
    "functional-conversion-report-shards/report-00001.md",
    "functional-conversion-report-shards/report-00002.json",
    "functional-conversion-report-shards/report-00002.md",
    "functional-conversion-report.json",
  ].sort());
  const bundleManifest = JSON.parse(
    Buffer.from(bundleEntries["FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json"]).toString("utf8"),
  );
  expect(bundleManifest.kind).toBe("elmos.project-language-conversion-report-bundle-manifest");
  expect(bundleManifest.file_count).toBe(6);

  const runnerHeaders = {
    authorization: "Bearer elmos-e2e-local-token-32-characters",
    "x-elmos-tenant": "local-e2e",
    "x-elmos-actor": "user:e2e",
  };
  const racingCreate = await page.request.post("/api/translation/jobs", {
    headers: runnerHeaders,
    data: {
      workspaceId: "pure-python",
      casesBundleId: "pure-python-holdout",
      sourceLanguage: "python",
      targetLanguage: "typescript",
    },
  });
  expect(racingCreate.status()).toBe(202);
  const racingJob = await racingCreate.json() as { id: string };
  const racingCancel = await page.request.post(
    `/api/translation/jobs/${racingJob.id}/cancel`,
    { headers: runnerHeaders },
  );
  expect(racingCancel.status()).toBe(200);
  expect((await racingCancel.json()).status).toBe("CANCELLED");
  await page.waitForTimeout(2_500);
  const durableCancellation = await page.request.get(
    `/api/translation/jobs/${racingJob.id}`,
    { headers: runnerHeaders },
  );
  expect(durableCancellation.status()).toBe(200);
  const durableCancellationJob = await durableCancellation.json();
  expect(durableCancellationJob.status).toBe("CANCELLED");
  expect(durableCancellationJob.reportReady).toBe(false);
  expect(durableCancellationJob.artifactReady).toBe(false);
});

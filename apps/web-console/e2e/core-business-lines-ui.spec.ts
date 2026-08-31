import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

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

test("跨语言整库入口在路线证据未通过时保持关闭", async ({ page }) => {
  await page.goto("/translation");
  await page.getByLabel("仓库引用").fill("local:e2e-customer-repository");
  await page.getByLabel("评估范围").selectOption("repository");
  await expect(page.getByRole("button", { name: "保存路线交接" })).toBeDisabled();
  await expect(page.getByLabel("导入仓库清单 JSON")).toBeDisabled();
  await expect(page.getByText(
    "当前路线的本地受限 Profile 未通过，导入入口保持关闭。",
    { exact: true },
  )).toBeVisible();
});

test("发现报告在权威路线本地 Profile 未通过时由服务端拒绝", async ({ request }) => {
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
    language_lifecycle: "ACTIVE",
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

  const blocked = await post(baseReport);
  expect(blocked.status()).toBe(422);
  expect(await blocked.json()).toMatchObject({
    status: "BLOCKED",
    errorCode: "DISCOVERY_ROUTE_LOCAL_PROFILE_NOT_PASSED",
  });

  for (const [mutation, expectedCode] of [
    [{ execution_status: "PASSED" }, "DISCOVERY_EXECUTION_CLAIMED"],
    [{ certification_status: "CERTIFIED" }, "DISCOVERY_CERTIFICATION_CLAIMED"],
    [{ ready_count: 2 }, "DISCOVERY_ROUTE_LOCAL_PROFILE_NOT_PASSED"],
    [{ route_id: "java-to-java" }, "DISCOVERY_ROUTE_UNKNOWN"],
    [
      { results: [{ ...baseReport.results[0], analyzer: undefined }, baseReport.results[1]] },
      "DISCOVERY_ROUTE_LOCAL_PROFILE_NOT_PASSED",
    ],
    [
      { results: [{ ...baseReport.results[0], function_name: "" }, baseReport.results[1]] },
      "DISCOVERY_ROUTE_LOCAL_PROFILE_NOT_PASSED",
    ],
    [
      { results: [{ ...baseReport.results[0], source_path: "../../etc/passwd" }, baseReport.results[1]] },
      "DISCOVERY_ROUTE_LOCAL_PROFILE_NOT_PASSED",
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

test("整库清单在权威路线本地 Profile 未通过时由服务端拒绝", async ({ request }) => {
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
    language_lifecycle: "ACTIVE",
    file_count: 1,
    source_file_count: 1,
    source_bytes: 128,
    repository_scale: "small",
    repository_limits: {
      maximum_source_files: 5000,
      maximum_source_bytes: 67108864,
      maximum_bytes_per_file: 2097152,
    },
    language_counts: {
      java: 1,
      python: 0,
      csharp: 0,
      typescript: 0,
      go: 0,
      rust: 0,
      cpp: 0,
      objc: 0,
      swift: 0,
      php: 0,
      kotlin: 0,
      react: 0,
      flutter: 0,
      javascript: 0,
    },
    deprecated_excluded_files: [],
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

  const blocked = await post(basePlan);
  expect(blocked.status()).toBe(422);
  expect(await blocked.json()).toMatchObject({
    status: "BLOCKED",
    errorCode: "PLAN_ROUTE_LOCAL_PROFILE_NOT_PASSED",
  });

  for (const [mutation, expectedCode] of [
    [{ execution_status: "PASSED" }, "PLAN_EXECUTION_CLAIMED"],
    [{ certification_status: "CERTIFIED" }, "PLAN_CERTIFICATION_CLAIMED"],
    [{ route_id: "java-to-java" }, "PLAN_ROUTE_UNKNOWN"],
    [{ source_file_count: 2 }, "PLAN_ROUTE_LOCAL_PROFILE_NOT_PASSED"],
    [{ limitations: [] }, "PLAN_ROUTE_LOCAL_PROFILE_NOT_PASSED"],
    [
      { work_units: [{ ...basePlan.work_units[0], source_path: "../../etc/passwd" }] },
      "PLAN_ROUTE_LOCAL_PROFILE_NOT_PASSED",
    ],
  ] as const) {
    const rejected = await post({ ...basePlan, ...mutation });
    expect(rejected.ok()).toBe(false);
    const body = await rejected.json();
    expect(body.status).toBe("BLOCKED");
    expect(body.errorCode).toBe(expectedCode);
  }
});

test("跨语言整库 Runner 在路线证据未通过时拒绝创建任务", async ({ page }) => {
  await page.goto("/translation");
  await page.getByLabel("跨语言租户标识").fill("local-e2e");
  await page.getByLabel("跨语言执行者标识").fill("user:e2e");
  await page.getByLabel("跨语言 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
  await page.getByLabel("受控源码工作区 ID").fill("pure-python");
  await page.getByLabel("独立行为用例包 ID").fill("pure-python-holdout");
  await page.getByRole("button", { name: /python 到 typescript/i }).click();
  await expect(page.getByRole("button", { name: "启动整库转换" })).toBeDisabled();

  const create = await page.request.post("/api/translation/jobs", {
    headers: {
      authorization: "Bearer elmos-e2e-local-token-32-characters",
      "x-elmos-tenant": "local-e2e",
      "x-elmos-actor": "user:e2e",
    },
    data: {
      workspaceId: "pure-python",
      casesBundleId: "pure-python-holdout",
      sourceLanguage: "python",
      targetLanguage: "typescript",
    },
  });
  expect(create.status()).toBe(409);
  expect(await create.json()).toEqual({
    status: "BLOCKED",
    reason: "TRANSLATION_ROUTE_NOT_LOCALLY_EXECUTABLE",
  });
});

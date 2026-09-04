import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash, randomUUID } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { request as nodeHttpRequest } from "node:http";
import path from "node:path";

const runnerHeaders = {
  "Content-Type": "application/json",
  "Authorization": "Bearer elmos-e2e-local-token-32-characters",
  "X-ELMOS-Tenant": "local-e2e",
  "X-ELMOS-Actor": "user:e2e",
};
const runnerPipelineOutcomeTimeoutMs = 21 * 60_000;

test.describe.configure({ mode: "serial", timeout: 25 * 60_000 });

async function chunkedJsonRequest(
  url: string,
  authorization: string,
  byteLength: number,
): Promise<Response> {
  const target = new URL(url);
  return new Promise((resolve, reject) => {
    const request = nodeHttpRequest({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": authorization,
        "X-ELMOS-Tenant": runnerHeaders["X-ELMOS-Tenant"],
        "X-ELMOS-Actor": runnerHeaders["X-ELMOS-Actor"],
      },
    }, (response) => {
      const chunks: Buffer[] = [];
      response.on("data", (chunk: Buffer) => chunks.push(Buffer.from(chunk)));
      response.once("end", () => resolve(new Response(Buffer.concat(chunks), {
        status: response.statusCode ?? 500,
        headers: {
          "Content-Type": String(response.headers["content-type"] ?? "application/json"),
        },
      })));
    });
    request.once("error", reject);
    request.setTimeout(10_000, () => request.destroy(new Error("chunked request timed out")));
    for (let offset = 0; offset < byteLength; offset += 1_024) {
      request.write(Buffer.alloc(Math.min(1_024, byteLength - offset), 0x78));
    }
    request.end();
  });
}

test("在线 HTML 读取拒绝回环与私网目标", async ({ request }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "SSRF 负例只执行一次");
  const response = await request.post("/api/generation/sources", {
    headers: {
      "Authorization": runnerHeaders.Authorization,
      "X-ELMOS-Tenant": runnerHeaders["X-ELMOS-Tenant"],
      "X-ELMOS-Actor": runnerHeaders["X-ELMOS-Actor"],
    },
    multipart: {
      url: "https://127.0.0.1/internal-requirements",
    },
  });

  expect(response.status()).toBe(400);
  expect(await response.json()).toMatchObject({
    status: "BLOCKED",
    reason: "SOURCE_URL_PRIVATE_ADDRESS_BLOCKED",
  });
});

test("GitHub 发布先鉴权再有界读取无 Content-Length 请求", async ({}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "请求流安全边界只执行一次");
  const baseUrl = String(testInfo.project.use.baseURL ?? "");
  const target = `${baseUrl}/api/generation/jobs/${randomUUID()}/github`;
  const githubPort = Number.parseInt(
    process.env.ELMOS_E2E_GITHUB_PORT
      ?? String(Number.parseInt(process.env.ELMOS_E2E_PORT ?? "3200", 10) + 99),
    10,
  );
  const metricsUrl = `http://127.0.0.1:${githubPort}/__test/metrics`;
  const metrics = async () => {
    const response = await fetch(metricsUrl, {
      headers: { Authorization: "Bearer github-e2e-fine-grained-token-32-characters" },
    });
    return await response.json() as { provider_requests: number };
  };
  const requestsBefore = (await metrics()).provider_requests;

  // Next.js compiles dynamic development routes on first access. Warm this
  // exact route with a bounded, rejected request so the streaming assertions
  // below measure authentication/body handling rather than cold compilation.
  const warmup = await fetch(target, {
    method: "POST",
    headers: {
      ...runnerHeaders,
      "Authorization": "Bearer invalid-runner-token",
    },
    body: "null",
  });
  expect(warmup.status).toBe(401);
  expect(await warmup.json()).toMatchObject({ reason: "AUTHENTICATION_REQUIRED" });

  const denied = await chunkedJsonRequest(target, "Bearer invalid-runner-token", 16 * 1024);
  expect(denied.status).toBe(401);
  expect(await denied.json()).toMatchObject({ reason: "AUTHENTICATION_REQUIRED" });

  const oversized = await chunkedJsonRequest(
    target,
    runnerHeaders.Authorization,
    16 * 1024,
  );
  expect(oversized.status).toBe(413);
  expect(await oversized.json()).toMatchObject({ reason: "REQUEST_TOO_LARGE" });

  const invalidShape = await fetch(target, {
    method: "POST",
    headers: runnerHeaders,
    body: "null",
  });
  expect(invalidShape.status).toBe(400);
  expect(await invalidShape.json()).toMatchObject({ reason: "GITHUB_PUBLISH_REQUEST_INVALID" });
  expect((await metrics()).provider_requests).toBe(requestsBefore);
});

test("hosted GitHub 发布在读取正文或调用 provider 前显式 NOT_RUN", async ({}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium"
      || process.env.ELMOS_HOSTED_EXECUTION_ENABLED !== "true",
    "仅在 hosted fail-closed 专项运行",
  );
  const baseUrl = String(testInfo.project.use.baseURL ?? "");
  const githubPort = Number.parseInt(
    process.env.ELMOS_E2E_GITHUB_PORT
      ?? String(Number.parseInt(process.env.ELMOS_E2E_PORT ?? "3200", 10) + 99),
    10,
  );
  const metricsUrl = `http://127.0.0.1:${githubPort}/__test/metrics`;
  const metrics = async () => {
    const response = await fetch(metricsUrl, {
      headers: { Authorization: "Bearer github-e2e-fine-grained-token-32-characters" },
    });
    return await response.json() as { provider_requests: number };
  };
  const requestsBefore = (await metrics()).provider_requests;
  const response = await chunkedJsonRequest(
    `${baseUrl}/api/generation/jobs/${randomUUID()}/github`,
    runnerHeaders.Authorization,
    16 * 1024,
  );
  expect(response.status).toBe(501);
  expect(await response.json()).toMatchObject({
    status: "BLOCKED",
    reason: "GITHUB_PUBLISH_HOSTED_EXECUTION_NOT_RUN",
  });
  expect((await metrics()).provider_requests).toBe(requestsBefore);
});

test("凭证不能切换租户，审阅摘要不能批准被修改的 Intent", async ({
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "安全边界的代表请求只执行一次");

  const switchedTenant = await request.post("/api/generation/analyze", {
    headers: { ...runnerHeaders, "X-ELMOS-Tenant": "other-e2e" },
    data: {
      name: "secure-service",
      namespace: "io.elmos.secure",
      description: "生成一个受控的内存 API",
      entity: "record",
      targets: ["python"],
      persistence: "in-memory",
      authMode: "none",
    },
  });
  expect(switchedTenant.status()).toBe(403);
  expect(await switchedTenant.json()).toMatchObject({
    reason: "TENANT_ID_NOT_BOUND_TO_CREDENTIAL",
  });

  const intent = {
    name: "secure-service",
    namespace: "io.elmos.secure",
    description: "生成一个受控的内存 API",
    entity: "record",
    targets: ["python"],
    persistence: "in-memory",
    authMode: "none",
  };
  const [analyzed, concurrentAnalysis] = await Promise.all([
    request.post("/api/generation/analyze", {
      headers: runnerHeaders,
      data: intent,
    }),
    request.post("/api/generation/analyze", {
      headers: runnerHeaders,
      data: {
        ...intent,
        name: "concurrent-service",
        namespace: "io.elmos.concurrent",
      },
    }),
  ]);
  if (!analyzed.ok()) {
    throw new Error(`primary analysis failed: ${await analyzed.text()}`);
  }
  if (!concurrentAnalysis.ok()) {
    throw new Error(`concurrent analysis failed: ${await concurrentAnalysis.text()}`);
  }
  const analysis = await analyzed.json() as { requestDigest: string };

  const modifiedIntent = await request.post("/api/generation/jobs", {
    headers: runnerHeaders,
    data: {
      ...intent,
      description: "审阅后被修改的内容",
      reviewer: "user:e2e",
      approved: true,
      analysisDigest: analysis.requestDigest,
    },
  });
  expect(modifiedIntent.status()).toBe(409);
  expect(await modifiedIntent.json()).toMatchObject({
    reason: "ANALYSIS_REVIEW_MISMATCH",
  });
});

test("服务端接受 PostgreSQL 生产配置下的多实体 Go 请求", async ({
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "生产能力边界的代表请求只执行一次");
  const intent = {
    name: "inventory-service",
    namespace: "io.elmos.inventory",
    description: "实体: product, inventory; product字段: name:string:required; "
      + "inventory字段: quantity:integer:required; "
      + "权限: admin:create/read/update/delete:product",
    entity: "product",
    targets: ["go"],
    persistence: "postgresql",
    authMode: "jwt",
  };
  const analyzed = await request.post("/api/generation/analyze", {
    headers: runnerHeaders,
    data: intent,
  });
  expect(analyzed.ok()).toBe(true);
  const analysis = await analyzed.json() as { requestDigest: string };
  const execution = await request.post("/api/generation/jobs", {
    headers: runnerHeaders,
    data: {
      ...intent,
      reviewer: "user:e2e",
      approved: true,
      analysisDigest: analysis.requestDigest,
    },
  });
  expect(execution.ok(), await execution.text()).toBe(true);
  const accepted = await execution.json() as { id: string };
  const cancelled = await request.post(`/api/generation/jobs/${accepted.id}/cancel`, {
    headers: runnerHeaders,
  });
  expect(cancelled.ok(), await cancelled.text()).toBe(true);
  expect(await cancelled.json()).toMatchObject({
    id: accepted.id,
    status: "CANCELLED",
    reason: "CANCELLED_BY_AUTHORIZED_ACTOR",
  });
});

test("需求分析、完整代码下载、浏览器限时运行与 GitHub 私有仓库发布闭环", async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "有副作用的代表旅程只执行一次");

  await page.goto("/generation");
  await page.getByLabel("审批者标识").fill("user:e2e");
  await page.getByLabel("租户标识").fill("local-e2e");
  await page.getByLabel("本地 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
  await page.getByLabel("核心实体").fill("product");
  await page.getByLabel("项目说明").fill(
    "实体: product, inventory; "
    + "product字段: name:string:required, price:number:required; "
    + "inventory字段: product_id:string:required, quantity:integer:required; "
    + "关系: inventory.product_id -> product.id; "
    + "规则: inventory.quantity must be non-negative; "
    + "权限: admin:create/read/update/delete:inventory; "
    + "权限: viewer:read:product",
  );
  const javaTarget = page.locator("label.target-card").filter({ hasText: "Java 21" })
    .locator('input[type="checkbox"]');
  await expect(javaTarget).toBeChecked();
  await javaTarget.focus();
  await javaTarget.press("Space");
  await expect(javaTarget).not.toBeChecked();

  await page.getByRole("button", { name: "锁定生成计划" }).click();
  const analyzeButton = page.getByRole("button", { name: "分析并整理需求" });
  await expect(analyzeButton).toBeEnabled({ timeout: 120_000 });
  const analysisResponsePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/generation/analyze"
  ), { timeout: 75_000 });
  await analyzeButton.click();
  const analysisResponse = await analysisResponsePromise;
  if (!analysisResponse.ok()) {
    throw new Error(`generation analysis failed: ${await analysisResponse.text()}`);
  }
  await expect(page.getByText("实体与字段 · 2")).toBeVisible();
  await expect(page.getByText("inventory.product_id many-to-one product.id")).toBeVisible();
  await expect(page.getByText("BR-001 · inventory.quantity must be non-negative")).toBeVisible();
  await expect(page.getByText("admin · allow create · inventory")).toBeVisible();
  await expect(page.getByText("viewer · allow read · product")).toBeVisible();
  await expect(page.getByText("开放问题 · 0")).toBeVisible();

  await page.getByRole("checkbox", { name: /我已审阅结构化需求/ }).check();
  const acceptedJobResponse = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && new URL(response.url()).pathname === "/api/generation/jobs"
  ));
  await page.getByRole("button", { name: "一键生成、验证并归档" }).click();
  const acceptedJob = await (await acceptedJobResponse).json() as { id: string };
  const generationOutcome = await Promise.race([
    page.getByText("生成文件树").waitFor({
      state: "visible",
      timeout: runnerPipelineOutcomeTimeoutMs,
    })
      .then(() => "READY"),
    page.getByText("BLOCKED", { exact: true }).last().waitFor({
      state: "visible",
      timeout: runnerPipelineOutcomeTimeoutMs,
    })
      .then(() => "BLOCKED"),
  ]);
  if (generationOutcome === "BLOCKED") {
    const reason = await page.getByRole("alert").last().textContent();
    const logs = await page.getByLabel("任务日志").textContent();
    throw new Error(
      `GENERATION_BLOCKED:${reason ?? "UNKNOWN"}\n${logs ?? "NO_JOB_LOGS"}`,
    );
  }
  expect(generationOutcome).toBe("READY");
  await expect(page.getByText("python/", { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "一键下载完整代码库" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("order-service.zip");
  const downloadedPath = await download.path();
  if (!downloadedPath) throw new Error("Playwright did not expose the downloaded archive path");
  const downloadedBytes = await readFile(downloadedPath);
  const downloadedDigest = createHash("sha256").update(downloadedBytes).digest("hex");
  const artifactResponse = await request.get(
    `/api/generation/jobs/${acceptedJob.id}/artifact`,
    { headers: runnerHeaders },
  );
  if (!artifactResponse.ok()) {
    throw new Error(`artifact download failed: ${await artifactResponse.text()}`);
  }
  const artifactBytes = await artifactResponse.body();
  const artifactHeaders = artifactResponse.headers();
  const expectedDigest = artifactHeaders["x-content-sha256"];
  expect(expectedDigest).toMatch(/^[0-9a-f]{64}$/);
  expect(downloadedDigest).toBe(expectedDigest);
  expect(createHash("sha256").update(artifactBytes).digest("hex")).toBe(expectedDigest);
  expect(Number(artifactHeaders["content-length"])).toBe(artifactBytes.length);
  const completedJobResponse = await request.get(`/api/generation/jobs/${acceptedJob.id}`, {
    headers: runnerHeaders,
  });
  expect(completedJobResponse.ok()).toBe(true);
  expect((await completedJobResponse.json() as { artifactSha256?: string }).artifactSha256).toBe(
    expectedDigest,
  );

  const fullRuntimeLease = process.env.ELMOS_E2E_FULL_RUNTIME_TTL === "true";
  await page.getByRole("button", { name: "一键运行 10 分钟" }).click();
  await expect(page.getByText("RUNNING", { exact: true })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByLabel("任务日志")).toContainText("Runtime health probe passed on 127.0.0.1:");
  await expect(page.getByText(
    fullRuntimeLease ? /^(?:10:00|09:[0-5][0-9])$/ : /^00:(?:0[1-9]|1[0-2])$/,
  )).toBeVisible();
  await page.getByRole("button", { name: "浏览器查看运行结果" }).click();
  await expect(page.getByLabel("浏览器运行结果")).toContainText('"status": "UP"');
  await expect(page.getByLabel("浏览器运行结果")).toContainText('"service": "order-service"');
  await expect(page.getByText("STOPPED", { exact: true })).toBeVisible({
    timeout: fullRuntimeLease ? 630_000 : 20_000,
  });
  await expect(page.getByLabel("任务日志")).toContainText("Ten-minute browser runtime lease expired");

  if (process.env.ELMOS_E2E_WEB_SERVER_MODE !== "production") {
    await page.getByLabel("GitHub 短期凭证").fill("github-invalid-fine-grained-token-000000");
    await page.getByRole("checkbox", { name: /我确认创建新的 GitHub 私有仓库/ }).check();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "一键上传 GitHub" }).click();
    await expect(page.getByText("GitHub 上传被阻断：GITHUB_CREDENTIAL_REJECTED")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByLabel("GitHub 短期凭证")).toHaveValue("");

    await page.getByLabel("GitHub 短期凭证").fill("github-e2e-fine-grained-token-32-characters");
    await page.getByRole("checkbox", { name: /我确认创建新的 GitHub 私有仓库/ }).check();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "一键上传 GitHub" }).click();
    const publication = page.getByRole("region", { name: "一键上传 GitHub 私有仓库" });
    await expect(publication.getByText("PUBLISHED", { exact: true })).toBeVisible({ timeout: 45_000 });
    await expect(publication.getByText("elmos-e2e/order-service", { exact: true })).toBeVisible();
    await expect(publication.getByText(/main · [0-9a-f]{12} · \d+ 个文件/)).toBeVisible();
    await expect(publication.getByRole("link", { name: "在 GitHub 查看" })).toHaveAttribute(
      "href",
      "https://github.example.invalid/elmos-e2e/order-service",
    );
    await expect(page.getByLabel("GitHub 短期凭证")).toHaveValue("");
    expect(await page.evaluate(() => Object.values(localStorage).join("\n"))).not.toContain(
      "github-e2e-fine-grained-token-32-characters",
    );
    expect(await page.evaluate(() => Object.values(sessionStorage).join("\n"))).not.toContain(
      "github-e2e-fine-grained-token-32-characters",
    );
  }
});

test("GitHub 创建身份无法确认时持久阻断并禁止无脑重试或不安全清理", async ({
  request,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium"
      || process.env.ELMOS_E2E_WEB_SERVER_MODE === "production",
    "GitHub 故障注入只在本地隔离 mock 执行一次",
  );

  const intent = {
    name: "reconcile-unknown-service",
    namespace: "io.elmos.reconcile",
    description: "生成一个用于验证 GitHub 创建结果安全对账的内存 API",
    entity: "record",
    targets: ["python"],
    persistence: "in-memory",
    authMode: "none",
  };
  const analyzed = await request.post("/api/generation/analyze", {
    headers: runnerHeaders,
    data: intent,
  });
  if (!analyzed.ok()) throw new Error(`reconciliation analysis failed: ${await analyzed.text()}`);
  const analysis = await analyzed.json() as { requestDigest: string };
  const execution = await request.post("/api/generation/jobs", {
    headers: runnerHeaders,
    data: {
      ...intent,
      reviewer: "user:e2e",
      approved: true,
      analysisDigest: analysis.requestDigest,
    },
  });
  if (!execution.ok()) throw new Error(`reconciliation generation failed: ${await execution.text()}`);
  const accepted = await execution.json() as { id: string };
  let completed: {
    status: string;
    reason?: string;
    artifactSha256?: string;
    githubPublication?: { status: string; reason?: string; repositoryFullName?: string };
  } | undefined;
  await expect.poll(async () => {
    const status = await request.get(`/api/generation/jobs/${accepted.id}`, {
      headers: runnerHeaders,
    });
    if (!status.ok()) return `HTTP_${status.status()}`;
    completed = await status.json() as typeof completed;
    return completed?.status === "BLOCKED"
      ? `BLOCKED:${completed.reason ?? "UNKNOWN"}`
      : completed?.status;
  }, {
    timeout: runnerPipelineOutcomeTimeoutMs,
    intervals: [1_000, 2_000, 5_000],
  }).toBe("COMPLETED");
  expect(completed?.artifactSha256).toMatch(/^[0-9a-f]{64}$/);

  const artifactSha256 = completed?.artifactSha256 as string;
  const githubToken = "github-e2e-fine-grained-token-32-characters";
  const githubPort = Number.parseInt(
    process.env.ELMOS_E2E_GITHUB_PORT
      ?? String(Number.parseInt(process.env.ELMOS_E2E_PORT ?? "3200", 10) + 99),
    10,
  );
  const githubState = async (fullName: string) => request.get(
    `http://127.0.0.1:${githubPort}/__test/state?full_name=${encodeURIComponent(fullName)}`,
    { headers: { Authorization: `Bearer ${githubToken}` } },
  );
  const githubMetrics = async () => {
    const response = await request.get(`http://127.0.0.1:${githubPort}/__test/metrics`, {
      headers: { Authorization: `Bearer ${githubToken}` },
    });
    return await response.json() as { provider_requests: number };
  };
  const runnerRoot = process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT;
  if (!runnerRoot) throw new Error("ELMOS_E2E_EFFECTIVE_RUNNER_ROOT missing");
  const persistedJobPath = path.join(
    runnerRoot,
    "tenants",
    runnerHeaders["X-ELMOS-Tenant"],
    "jobs",
    accepted.id,
    "job.json",
  );
  const clearTestPublication = async () => {
    const resetJob = JSON.parse(
      await readFile(persistedJobPath, "utf-8"),
    ) as Record<string, unknown>;
    delete resetJob.githubPublication;
    await writeFile(persistedJobPath, `${JSON.stringify(resetJob, null, 2)}\n`, "utf-8");
  };

  for (const negative of [
    {
      repositoryName: "blob-corrupt-service",
      reason: "GITHUB_BLOB_CONTENT_VERIFICATION_FAILED_MANUAL_CLEANUP_REQUIRED",
    },
    {
      repositoryName: "blob-oversized-service",
      reason: "GITHUB_API_RESPONSE_TOO_LARGE_MANUAL_CLEANUP_REQUIRED",
    },
    {
      repositoryName: "json-oversized-service",
      reason: "GITHUB_API_RESPONSE_TOO_LARGE_MANUAL_CLEANUP_REQUIRED",
    },
    {
      repositoryName: "json-declared-oversized-service",
      reason: "GITHUB_API_RESPONSE_TOO_LARGE_MANUAL_CLEANUP_REQUIRED",
    },
  ]) {
    const response = await request.post(`/api/generation/jobs/${accepted.id}/github`, {
      headers: runnerHeaders,
      data: {
        repositoryName: negative.repositoryName,
        token: githubToken,
        artifactSha256,
        idempotencyKey: randomUUID(),
        confirmed: true,
      },
    });
    const responseBody = await response.json();
    expect(response.status(), JSON.stringify(responseBody)).toBe(502);
    expect(responseBody).toMatchObject({
      status: "BLOCKED",
      reason: negative.reason,
    });
    expect(await (await githubState(`elmos-e2e/${negative.repositoryName}`)).json()).toMatchObject({
      exists: true,
      creation_attempts: 1,
      deletion_attempts: 0,
    });
    const persistedNegative = await request.get(`/api/generation/jobs/${accepted.id}`, {
      headers: runnerHeaders,
    });
    expect(await persistedNegative.json()).toMatchObject({
      githubPublication: {
        status: "BLOCKED",
        reason: negative.reason,
        repositoryFullName: `elmos-e2e/${negative.repositoryName}`,
      },
    });
    await clearTestPublication();
  }

  const spoofedUrlPublication = await request.post(
    `/api/generation/jobs/${accepted.id}/github`,
    {
      headers: runnerHeaders,
      data: {
        repositoryName: "html-url-spoof-service",
        token: githubToken,
        artifactSha256,
        idempotencyKey: randomUUID(),
        confirmed: true,
      },
    },
  );
  expect(spoofedUrlPublication.status()).toBe(502);
  expect(await spoofedUrlPublication.json()).toMatchObject({
    status: "BLOCKED",
    reason: "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED",
  });
  expect(await (await githubState("elmos-e2e/html-url-spoof-service")).json()).toMatchObject({
    exists: true,
    creation_attempts: 1,
    deletion_attempts: 0,
  });
  await clearTestPublication();

  const capacityIntent = {
    ...intent,
    name: "capacity-control-service",
    namespace: "io.elmos.capacity",
    description: "生成一个用于验证 GitHub 发布内存并发门禁的内存 API",
  };
  const capacityAnalyzed = await request.post("/api/generation/analyze", {
    headers: runnerHeaders,
    data: capacityIntent,
  });
  if (!capacityAnalyzed.ok()) {
    throw new Error(`capacity analysis failed: ${await capacityAnalyzed.text()}`);
  }
  const capacityAnalysis = await capacityAnalyzed.json() as { requestDigest: string };
  const capacityExecution = await request.post("/api/generation/jobs", {
    headers: runnerHeaders,
    data: {
      ...capacityIntent,
      reviewer: "user:e2e",
      approved: true,
      analysisDigest: capacityAnalysis.requestDigest,
    },
  });
  if (!capacityExecution.ok()) {
    throw new Error(`capacity generation failed: ${await capacityExecution.text()}`);
  }
  const capacityAccepted = await capacityExecution.json() as { id: string };
  let capacityArtifactSha256 = "";
  await expect.poll(async () => {
    const status = await request.get(`/api/generation/jobs/${capacityAccepted.id}`, {
      headers: runnerHeaders,
    });
    if (!status.ok()) return `HTTP_${status.status()}`;
    const job = await status.json() as {
      status: string;
      reason?: string;
      artifactSha256?: string;
    };
    capacityArtifactSha256 = job.artifactSha256 ?? "";
    return job.status === "BLOCKED" ? `BLOCKED:${job.reason ?? "UNKNOWN"}` : job.status;
  }, {
    timeout: runnerPipelineOutcomeTimeoutMs,
    intervals: [1_000, 2_000, 5_000],
  }).toBe("COMPLETED");
  expect(capacityArtifactSha256).toMatch(/^[0-9a-f]{64}$/);

  const slowRepositoryName = "slow-publish-service";
  const slowPublication = request.post(`/api/generation/jobs/${accepted.id}/github`, {
    headers: runnerHeaders,
    data: {
      repositoryName: slowRepositoryName,
      token: githubToken,
      artifactSha256,
      idempotencyKey: randomUUID(),
      confirmed: true,
    },
  });
  await expect.poll(async () => {
    const state = await githubState(`elmos-e2e/${slowRepositoryName}`);
    return (await state.json() as { creation_attempts?: number }).creation_attempts ?? 0;
  }, { timeout: 10_000, intervals: [100, 250, 500] }).toBe(1);
  const rejectedForCapacity = await request.post(
    `/api/generation/jobs/${capacityAccepted.id}/github`,
    {
      headers: runnerHeaders,
      data: {
        repositoryName: "capacity-rejected-service",
        token: githubToken,
        artifactSha256: capacityArtifactSha256,
        idempotencyKey: randomUUID(),
        confirmed: true,
      },
    },
  );
  expect(rejectedForCapacity.status()).toBe(429);
  expect(await rejectedForCapacity.json()).toMatchObject({
    status: "BLOCKED",
    reason: "GITHUB_TENANT_PUBLICATION_CAPACITY_EXCEEDED",
  });
  expect(await (await githubState("elmos-e2e/capacity-rejected-service")).json()).toMatchObject({
    exists: false,
    creation_attempts: 0,
    deletion_attempts: 0,
  });
  const slowPublicationResponse = await slowPublication;
  expect(slowPublicationResponse.status()).toBe(200);
  expect(await slowPublicationResponse.json()).toMatchObject({
    githubPublication: {
      status: "PUBLISHED",
      repositoryFullName: `elmos-e2e/${slowRepositoryName}`,
      artifactSha256,
    },
  });
  await clearTestPublication();

  const recoveredRepository = "recovered-marker-service";
  const recoveredIdempotencyKey = randomUUID();
  const recoveredDescription = `ELMOS-Publication-ID:${recoveredIdempotencyKey} | Artifact-SHA256:${artifactSha256}`;
  const seed = await request.post(
    `http://127.0.0.1:${githubPort}/__test/seed-recovery-repository`,
    {
      headers: { Authorization: `Bearer ${githubToken}` },
      data: {
        full_name: `elmos-e2e/${recoveredRepository}`,
        description: recoveredDescription,
      },
    },
  );
  expect(seed.status()).toBe(201);
  const creatingJob = JSON.parse(await readFile(persistedJobPath, "utf-8")) as Record<string, unknown>;
  creatingJob.githubPublication = {
    status: "CREATING",
    repositoryFullName: `elmos-e2e/${recoveredRepository}`,
    artifactSha256,
    idempotencyKey: recoveredIdempotencyKey,
    updatedAt: new Date().toISOString(),
  };
  await writeFile(persistedJobPath, `${JSON.stringify(creatingJob, null, 2)}\n`, "utf-8");
  const providerRequestsBeforeRecovery = (await githubMetrics()).provider_requests;
  const recoveredAttempt = await request.post(`/api/generation/jobs/${accepted.id}/github`, {
    headers: runnerHeaders,
    data: {
      repositoryName: recoveredRepository,
      token: githubToken,
      artifactSha256,
      idempotencyKey: recoveredIdempotencyKey,
      confirmed: true,
    },
  });
  expect(recoveredAttempt.status()).toBe(409);
  expect(await recoveredAttempt.json()).toMatchObject({
    status: "BLOCKED",
    reason: "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED",
  });
  expect(await (await githubState(`elmos-e2e/${recoveredRepository}`)).json()).toMatchObject({
    exists: true,
    creation_attempts: 0,
    deletion_attempts: 0,
  });
  expect((await githubMetrics()).provider_requests).toBe(providerRequestsBeforeRecovery);

  await clearTestPublication();

  const idempotencyKey = randomUUID();
  const publicationRequest = {
    repositoryName: "reconcile-unknown-service",
    token: githubToken,
    artifactSha256,
    idempotencyKey,
    confirmed: true,
  };
  const firstPublication = await request.post(
    `/api/generation/jobs/${accepted.id}/github`,
    { headers: runnerHeaders, data: publicationRequest },
  );
  expect(firstPublication.status()).toBe(502);
  expect(await firstPublication.json()).toMatchObject({
    status: "BLOCKED",
    reason: "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED",
  });

  const persisted = await request.get(`/api/generation/jobs/${accepted.id}`, {
    headers: runnerHeaders,
  });
  expect(persisted.ok()).toBe(true);
  expect(await persisted.json()).toMatchObject({
    githubPublication: {
      status: "BLOCKED",
      reason: "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED",
      repositoryFullName: "elmos-e2e/reconcile-unknown-service",
    },
  });

  const stateUrl = `http://127.0.0.1:${githubPort}/__test/state?full_name=${encodeURIComponent("elmos-e2e/reconcile-unknown-service")}`;
  const stateAfterUnknown = await request.get(stateUrl, {
    headers: { Authorization: "Bearer github-e2e-fine-grained-token-32-characters" },
  });
  expect(await stateAfterUnknown.json()).toMatchObject({
    exists: true,
    creation_attempts: 1,
    deletion_attempts: 0,
  });

  const providerRequestsBeforeRetry = (await githubMetrics()).provider_requests;
  const retry = await request.post(`/api/generation/jobs/${accepted.id}/github`, {
    headers: runnerHeaders,
    data: publicationRequest,
  });
  expect(retry.status()).toBe(409);
  expect(await retry.json()).toMatchObject({
    status: "BLOCKED",
    reason: "GITHUB_PUBLICATION_RECONCILIATION_REQUIRED",
  });
  const stateAfterRetry = await request.get(stateUrl, {
    headers: { Authorization: "Bearer github-e2e-fine-grained-token-32-characters" },
  });
  expect(await stateAfterRetry.json()).toMatchObject({
    exists: true,
    creation_attempts: 1,
    deletion_attempts: 0,
  });
  expect((await githubMetrics()).provider_requests).toBe(providerRequestsBeforeRetry);
});

for (const authMode of ["jwt", "oidc"] as const) {
  test(`Python PostgreSQL ${authMode.toUpperCase()} 企业配置可生成、验证并一键本地部署运行`, async ({
    page,
    request,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "企业配置的真实有副作用旅程只执行一次");
    const analysisWarmup = await request.post("/api/generation/analyze", {
      headers: {
        ...runnerHeaders,
        Authorization: "Bearer invalid-runner-token-token-token",
      },
      data: {},
      timeout: 180_000,
    });
    expect(analysisWarmup.status()).toBe(401);
    expect(await analysisWarmup.json()).toMatchObject({
      status: "BLOCKED",
      reason: "AUTHENTICATION_REQUIRED",
    });
    const admissionWarmup = await request.post("/api/generation/jobs", {
      headers: {
        ...runnerHeaders,
        Authorization: "Bearer invalid-runner-token-token-token",
      },
      data: {},
      timeout: 180_000,
    });
    expect(admissionWarmup.status()).toBe(401);
    expect(await admissionWarmup.json()).toMatchObject({
      status: "BLOCKED",
      reason: "AUTHENTICATION_REQUIRED",
    });
    await page.goto("/generation");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();
    await page.getByLabel("审批者标识").fill("user:e2e");
    await page.getByLabel("租户标识").fill("local-e2e");
    await page.getByLabel("本地 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
    await page.getByLabel("核心实体").fill("order");
    await page.getByLabel("项目说明").fill(
      "实体: customer, order; "
      + "customer字段: name:string:required; "
      + "order字段: customer_id:string:required, total:number:required; "
      + "关系: order.customer_id -> customer.id; "
      + "规则: order.total must be non-negative; "
      + "权限: admin:create/read/update/delete:customer; "
      + "权限: admin:create/read/update/delete:order",
    );
    await page.getByLabel("数据配置").selectOption("postgresql");
    await page.getByLabel("认证配置").selectOption(authMode);
    await expect(page.getByLabel("认证配置")).toHaveValue(authMode);

    await page.getByRole("button", { name: "锁定生成计划" }).click();
    const analyzeButton = page.getByRole("button", { name: "分析并整理需求" });
    await expect(analyzeButton).toBeEnabled({ timeout: 120_000 });
    const analysisResponsePromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/generation/analyze"
    ), { timeout: 75_000 });
    await analyzeButton.click();
    const analysisResponse = await analysisResponsePromise;
    if (!analysisResponse.ok()) {
      throw new Error(`generation analysis failed: ${await analysisResponse.text()}`);
    }
    await expect(page.getByText("实体与字段 · 2")).toBeVisible();
    await expect(page.getByText("order.customer_id many-to-one customer.id")).toBeVisible();
    await expect(page.getByText("开放问题 · 0")).toBeVisible();

    await page.getByRole("checkbox", { name: /我已审阅结构化需求/ }).check();
    const acceptedJobResponsePromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/generation/jobs"
    ), { timeout: 180_000 });
    await page.getByRole("button", { name: "一键生成、验证并归档" }).click();
    const acceptedJobResponse = await acceptedJobResponsePromise;
    if (!acceptedJobResponse.ok()) {
      throw new Error(`generation job admission failed: ${await acceptedJobResponse.text()}`);
    }
    const acceptedJob = await acceptedJobResponse.json() as { id: string };
    const generationOutcome = await Promise.race([
      page.getByText("生成文件树").waitFor({
        state: "visible",
        timeout: runnerPipelineOutcomeTimeoutMs,
      })
        .then(() => "READY"),
      page.getByText("BLOCKED", { exact: true }).last()
        .waitFor({ state: "visible", timeout: runnerPipelineOutcomeTimeoutMs })
        .then(() => "BLOCKED"),
    ]);
    if (generationOutcome === "BLOCKED") {
      const reason = await page.getByRole("alert").last().textContent();
      const logs = await page.getByLabel("任务日志").textContent();
      throw new Error(
        `GENERATION_BLOCKED:${reason ?? "UNKNOWN"}\n${logs ?? "NO_JOB_LOGS"}`,
      );
    }
    expect(generationOutcome).toBe("READY");
    await expect(page.getByText("database/", { exact: true })).toBeVisible();
    await expect(page.getByText("security/", { exact: true })).toBeVisible();
    await expect(page.getByText("PASSED", { exact: true }).first()).toBeVisible({
      timeout: 600_000,
    });

    const runtimeWarmup = await request.post(
      `/api/generation/jobs/${acceptedJob.id}/run`,
      {
        headers: {
          ...runnerHeaders,
          Authorization: "Bearer invalid-runner-token-token-token",
        },
        data: { language: "python" },
        timeout: 180_000,
      },
    );
    expect(runtimeWarmup.status()).toBe(401);
    expect(await runtimeWarmup.json()).toMatchObject({
      status: "BLOCKED",
      reason: "AUTHENTICATION_REQUIRED",
    });
    const stopWarmup = await request.post(
      `/api/generation/jobs/${acceptedJob.id}/stop`,
      {
        headers: {
          ...runnerHeaders,
          Authorization: "Bearer invalid-runner-token-token-token",
        },
        timeout: 180_000,
      },
    );
    expect(stopWarmup.status()).toBe(401);
    expect(await stopWarmup.json()).toMatchObject({
      status: "BLOCKED",
      reason: "AUTHENTICATION_REQUIRED",
    });
    const runtimeStartResponsePromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname === `/api/generation/jobs/${acceptedJob.id}/run`
    ), { timeout: 200_000 });
    await page.getByRole("button", { name: "一键运行 10 分钟" }).click();
    const runtimeStartResponse = await runtimeStartResponsePromise;
    if (!runtimeStartResponse.ok()) {
      throw new Error(`generation runtime start failed: ${await runtimeStartResponse.text()}`);
    }
    expect(await runtimeStartResponse.json()).toMatchObject({
      runtime: { status: "RUNNING", language: "python" },
    });
    await expect(page.getByText("RUNNING", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("任务日志")).toContainText("Runtime health probe passed on 127.0.0.1:");
    const runtimeStopResponsePromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname === `/api/generation/jobs/${acceptedJob.id}/stop`
    ), { timeout: 120_000 });
    await page.getByRole("button", { name: "停止" }).click();
    const runtimeStopResponse = await runtimeStopResponsePromise;
    if (!runtimeStopResponse.ok()) {
      throw new Error(`generation runtime stop failed: ${await runtimeStopResponse.text()}`);
    }
    expect(await runtimeStopResponse.json()).toMatchObject({
      runtime: {
        status: "STOPPED",
        reason: "STOPPED_BY_AUTHORIZED_ACTOR",
      },
    });
    await expect(page.getByText("STOPPED", { exact: true })).toBeVisible({ timeout: 30_000 });
    // The enterprise journey leaves a polling page and several long-lived API
    // connections behind. Close both fixtures explicitly so Playwright does
    // not spend its five-minute worker shutdown budget draining idle sockets.
    await page.close();
    await request.dispose();
  });
}

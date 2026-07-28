import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const runnerHeaders = {
  "Content-Type": "application/json",
  "Authorization": "Bearer elmos-e2e-local-token-32-characters",
  "X-ELMOS-Tenant": "local-e2e",
  "X-ELMOS-Actor": "user:e2e",
};

test.describe.configure({ mode: "serial" });

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

test("服务端在消费审阅摘要前阻断单实体目标的多实体生产请求", async ({
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
  expect(execution.status()).toBe(409);
  expect(await execution.json()).toMatchObject({
    reason: "PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY",
  });
});

test("需求分析、生成验证、文件树、归档与健康确认的一键运行闭环", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "有副作用的代表旅程只执行一次");
  test.setTimeout(360_000);

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
  await javaTarget.uncheck();

  await page.getByRole("button", { name: "锁定生成计划" }).click();
  await page.getByRole("button", { name: "分析并整理需求" }).click();
  await expect(page.getByText("实体与字段 · 2")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("inventory.product_id many-to-one product.id")).toBeVisible();
  await expect(page.getByText("BR-001 · inventory.quantity must be non-negative")).toBeVisible();
  await expect(page.getByText("admin · allow create · inventory")).toBeVisible();
  await expect(page.getByText("viewer · allow read · product")).toBeVisible();
  await expect(page.getByText("开放问题 · 0")).toBeVisible();

  await page.getByRole("checkbox", { name: /我已审阅结构化需求/ }).check();
  await page.getByRole("button", { name: "一键生成、验证并归档" }).click();
  const generationOutcome = await Promise.race([
    page.getByText("生成文件树").waitFor({ state: "visible", timeout: 260_000 })
      .then(() => "READY"),
    page.getByText("BLOCKED", { exact: true }).last().waitFor({ state: "visible", timeout: 260_000 })
      .then(() => "BLOCKED"),
  ]);
  expect(generationOutcome).toBe("READY");
  await expect(page.getByText("python/", { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载归档" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("order-service.zip");

  await page.getByRole("button", { name: "一键运行" }).click();
  await expect(page.getByText("RUNNING", { exact: true })).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "停止" }).click();
  await expect(page.getByText("STOPPED", { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(1_500);
  await expect(page.getByText("STOPPED", { exact: true })).toBeVisible();
});

test("Python PostgreSQL JWT/OIDC 企业配置均可生成、验证并一键运行", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "企业配置的真实有副作用旅程只执行一次");
  test.setTimeout(1_200_000);

  for (const authMode of ["jwt", "oidc"] as const) {
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
    await page.getByRole("button", { name: "分析并整理需求" }).click();
    await expect(page.getByText("实体与字段 · 2")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("order.customer_id many-to-one customer.id")).toBeVisible();
    await expect(page.getByText("开放问题 · 0")).toBeVisible();

    await page.getByRole("checkbox", { name: /我已审阅结构化需求/ }).check();
    await page.getByRole("button", { name: "一键生成、验证并归档" }).click();
    const generationOutcome = await Promise.race([
      page.getByText("生成文件树").waitFor({ state: "visible", timeout: 600_000 })
        .then(() => "READY"),
      page.getByText("BLOCKED", { exact: true }).last()
        .waitFor({ state: "visible", timeout: 600_000 })
        .then(() => "BLOCKED"),
    ]);
    expect(generationOutcome).toBe("READY");
    await expect(page.getByText("database/", { exact: true })).toBeVisible();
    await expect(page.getByText("security/", { exact: true })).toBeVisible();
    await expect(page.getByText("PASSED", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "一键运行" }).click();
    await expect(page.getByText("RUNNING", { exact: true })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "停止" }).click();
    await expect(page.getByText("STOPPED", { exact: true })).toBeVisible({ timeout: 20_000 });
  }
});

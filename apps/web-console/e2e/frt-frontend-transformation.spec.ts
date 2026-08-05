import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

test("FRT 前端转换工厂在桌面与移动端可浏览、规划且无自动可访问性违规", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/frontend");
  await expect(page.getByRole("heading", { name: "前端仓库转换工厂" })).toBeVisible();
  await expect(page.getByText("472", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("30 / 30 路线已注册", { exact: true })).toBeVisible();

  await page.getByLabel("源技术栈").selectOption("React");
  await page.getByLabel("目标技术栈").selectOption("Flutter");
  await expect(page.getByRole("heading", { name: "React → Flutter" })).toBeVisible();
  await expect(page.getByText(/FRT-1605/).first()).toBeVisible();
  await expect(page.getByText("NOT_CERTIFIED", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "查看 Route Skill" }).click();
  await expect(page.getByRole("button", { name: /FRT-1605/ })).toBeVisible();

  await page.locator('nav[aria-label="按 Batch 筛选 Skill"] button').first().click();
  await page.getByPlaceholder("搜索 ID、名称或能力…").fill("FRT-3001");
  await expect(page.getByRole("button", { name: /FRT-3001/ })).toBeVisible();
  await expect(page.getByText("Production Readiness Checklist Compiler", { exact: true })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("FRT 目录 API 保留完整计数并限制单次结果规模", async ({ request }, testInfo) => {
  test.skip(testInfo.project.name === "mobile-chromium", "API 合同由桌面项目执行一次");
  const response = await request.get("/api/frt/catalog?batch=G13&limit=5");
  expect(response.ok()).toBe(true);
  const body = await response.json();
  expect(body.batchCount).toBe(30);
  expect(body.skillCount).toBe(472);
  expect(body.directedRouteCount).toBe(30);
  expect(body.matchedSkillCount).toBe(11);
  expect(body.skills).toHaveLength(5);
  expect(body.evidenceBoundary.production).toBe("NOT_RUN");
  expect(body.evidenceBoundary.certification).toBe("NOT_CERTIFIED");
});

test("FRT Web BFF 拒绝未认证请求和伪造的跨租户身份", async ({ request }, testInfo) => {
  test.skip(testInfo.project.name === "mobile-chromium", "身份边界由桌面项目执行一次");
  const data = {
    skillId: "FRT-0100",
    action: "PLAN",
    idempotencyKey: "browser-negative-identity",
    workspaceId: "workspace-e2e",
    projectId: "project-e2e",
    environmentId: "development",
    releaseId: "release-e2e",
    sourceSnapshotDigest: `sha256:${"0".repeat(64)}`,
    policyVersion: "policy-e2e",
    risk: "R0",
  };
  const unauthenticated = await request.post("/api/frt/runs", { data });
  expect(unauthenticated.status()).toBe(401);
  expect(await unauthenticated.json()).toEqual({
    status: "BLOCKED",
    reason: "AUTHENTICATION_REQUIRED",
  });

  const spoofedTenant = await request.post("/api/frt/runs", {
    data,
    headers: {
      authorization: "Bearer elmos-e2e-local-token-32-characters",
      "x-elmos-tenant": "attacker-tenant",
      "x-elmos-actor": "user:e2e",
    },
  });
  expect(spoofedTenant.status()).toBe(403);
  expect(await spoofedTenant.json()).toEqual({
    status: "BLOCKED",
    reason: "TENANT_ID_NOT_BOUND_TO_CREDENTIAL",
  });
});

test("FRT 操作台通过真实 Engine 完成仓库、执行、进度、产物、Finding 与审计闭环", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "持久化 Engine 生命周期由桌面 Chromium 串行执行一次");
  await page.goto("/frontend");
  await page.getByPlaceholder("搜索 ID、名称或能力…").fill("FRT-0100");
  await page.getByRole("button", { name: /FRT-0100/ }).click();
  await page.getByText("本地开发身份租约").click();
  await page.getByLabel("FRT 本地租户标识").fill("local-e2e");
  await page.getByLabel("FRT 本地执行者标识").fill("user:e2e");
  await page.getByLabel("FRT 本地 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
  await page.getByLabel("选择 FRT 仓库文件").setInputFiles({
    name: "package.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({ name: "frt-e2e-source", private: true })),
  });
  await expect(page.getByText("1 个文件已绑定")).toBeVisible();
  await page.getByRole("button", { name: "EXECUTE", exact: true }).click();

  await expect(page.locator('strong[data-run-state="QUEUED"]')).toBeVisible();
  await expect(page.getByText("FRT_EXTERNAL_RUNNER_REQUIRED")).toBeVisible();
  await expect(page.locator("pre")).toContainText('"handlerKind": "governance"');
  await expect(page.getByText("RUN_CREATED", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Runner 领取" }).click();
  await expect(page.locator('strong[data-run-state="RUNNING"]')).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.locator('strong[data-run-state="CANCELLED"]')).toBeVisible();
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator('strong[data-run-state="QUEUED"]')).toBeVisible();
  await expect(page.getByText("RUN_CLAIMED", { exact: true })).toBeVisible();
  await expect(page.getByText("RUN_CANCELLED", { exact: true })).toBeVisible();
  await expect(page.getByText("RUN_RETRIED", { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("FRT 关键路径支持键盘操作并随全局语言切换提供英文界面", async ({ page }) => {
  await page.goto("/frontend");
  await page.getByRole("button", { name: "将导航和帮助切换为英文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Frontend repository transformation factory" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose an exact directed transformation route" })).toBeVisible();
  await expect(page.getByLabel("Source stack")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Repository → plan → execute → evidence loop" })).toBeVisible();

  const search = page.getByPlaceholder("搜索 ID、名称或能力…");
  await search.focus();
  await page.keyboard.type("FRT-1305");
  const skill = page.getByRole("button", { name: /FRT-1305/ });
  await skill.focus();
  await page.keyboard.press("Enter");
  await expect(skill).toHaveAttribute("aria-pressed", "true");
  const plan = page.getByRole("button", { name: "PLAN", exact: true });
  await plan.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("alert").filter({ hasText: "请先选择仓库中的文本文件" }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

import { expect, test } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync, symlinkSync } from "node:fs";
import path from "node:path";

import { installAdministratorSession } from "./helpers/admin-session";

/**
 * Batch 46 一键运行按钮。
 *
 * 上半部分是真实的 API 契约旅程：真的 scaffold 一个冒烟包、真的把服务跑起来、
 * 真的续期与回收，断言证据由冒烟包自己写下。下半部分按仓库既有 UI 约定用
 * page.route 打桩，验证倒计时、到期禁用、续期表单、回收报告与证据展示。
 */

// /smoke is a platform operations surface and requires an administrator session.
test.beforeEach(async ({ page }) => {
  await installAdministratorSession(page);
});

const runnerHeaders = {
  "Content-Type": "application/json",
  "Authorization": "Bearer elmos-e2e-local-token-32-characters",
  "X-ELMOS-Tenant": "local-e2e",
  "X-ELMOS-Actor": "user:e2e",
};

const repositoryRoot = path.resolve(__dirname, "../../..");
const scaffold = path.join(repositoryRoot, "scripts/batch46/scaffold_smoke_pack.py");
const fixtureSource = path.resolve(__dirname, "fixtures/smoke-projects/demo-service");
const projectRef = "demo-service";

function python(): string | null {
  for (const candidate of [process.env.ELMOS_SMOKE_PYTHON, "python3", "python"]) {
    if (!candidate) continue;
    const probe = spawnSync(candidate, ["-c", "import sys; print(sys.version_info[0])"], { encoding: "utf-8" });
    if (probe.status === 0 && probe.stdout.trim() === "3") return candidate;
  }
  return null;
}

/**
 * dev-server 在 Turbopack 缓存失效时会自我重启，此时连接层会 socket hang up。
 * 那不代表端点有问题，所以只对连接失败重试；任何 HTTP 状态码都原样交给断言。
 */
async function postTolerantOfRestart(
  request: import("@playwright/test").APIRequestContext,
  url: string,
  data: unknown,
) {
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await request.post(url, { headers: runnerHeaders, data });
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
  }
  throw lastError;
}

function projectsRoot(): string {
  const configured = process.env.ELMOS_E2E_SMOKE_PROJECTS_ROOT;
  if (!configured) throw new Error("ELMOS_E2E_SMOKE_PROJECTS_ROOT_MISSING");
  return configured;
}

test.describe("Batch 46 一键运行 · 真实会话", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeAll(() => {
    const interpreter = python();
    if (!interpreter) return;
    const target = path.join(projectsRoot(), projectRef);
    rmSync(target, { recursive: true, force: true });
    mkdirSync(path.dirname(target), { recursive: true });
    cpSync(fixtureSource, target, { recursive: true });
    const built = spawnSync(interpreter, [scaffold, target, "--write"], { encoding: "utf-8" });
    expect(built.status, built.stderr).toBe(0);
    expect(existsSync(path.join(target, "smoke", "runner-manifest.json"))).toBe(true);
  });

  test.afterAll(() => {
    rmSync(path.join(projectsRoot(), "escaped-project"), { force: true });
    const interpreter = python();
    if (!interpreter) return;
    const target = path.join(projectsRoot(), projectRef);
    const lease = path.join(target, "smoke", "tools", "smoke_lease.py");
    if (!existsSync(lease)) return;
    // 绕开 web 服务直接回收：即便 dev-server 崩了，租约也不该留下活着的服务。
    spawnSync(interpreter, [lease, "stop", "--project", target, "--reason", "e2e-cleanup"], {
      encoding: "utf-8",
    });
  });

  test("能力接口如实报告执行位置与不可续期的免费额度", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "契约请求只执行一次");
    const response = await request.get("/api/smoke/capability", {
      headers: runnerHeaders,
      // A clean Next development server can reset one idempotent GET while it
      // compiles the API route after the preceding long-running build journeys.
      // Retry only transport-level resets; HTTP failures remain observable.
      maxRetries: 2,
    });
    expect(response.status()).toBe(200);
    const capability = await response.json();
    expect(capability).toMatchObject({
      freeQuotaSeconds: 600,
      autoRenew: false,
      extendPolicy: "EXPLICIT_ONLY",
      preferredLocation: "LOCAL_WORKSTATION",
    });
    const hosted = capability.locations.find((item: { location: string }) => item.location === "HOSTED_RUNNER");
    // 未配置的执行位置必须带理由，不能表现成可用。
    expect(hosted.status).toBe("NOT_CONFIGURED");
    expect(hosted.reason).toBeTruthy();
  });

  test("冒烟包摘要按入口给出可用性与理由", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "契约请求只执行一次");
    test.skip(python() === null, "需要 python3 才能构建冒烟包");

    const response = await request.get(`/api/smoke/pack?projectRef=${projectRef}`, { headers: runnerHeaders });
    expect(response.status()).toBe(200);
    const pack = await response.json();
    expect(pack.languages).toContain("python");
    expect(pack.datastores).toContain("postgres");

    const byEntry = Object.fromEntries(
      pack.entries.map((item: { entry: string }) => [item.entry, item]),
    );
    expect(byEntry["zero-dep"].status).toBe("available");
    expect(byEntry["zero-dep"].semanticWarning).toContain("substitute");
    expect(byEntry.script.status).toBe("available");
  });

  test("未知项目引用与越界路径被拒绝", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "负例只执行一次");

    const traversal = await request.get("/api/smoke/pack?projectRef=../../etc", { headers: runnerHeaders });
    expect(traversal.status()).toBe(400);
    expect(await traversal.json()).toMatchObject({ status: "BLOCKED", reason: "SMOKE_PROJECT_REF_INVALID" });

    const missing = await request.get("/api/smoke/pack?projectRef=does-not-exist", { headers: runnerHeaders });
    expect(missing.status()).toBe(404);
    expect(await missing.json()).toMatchObject({ status: "BLOCKED", reason: "SMOKE_PACK_NOT_FOUND" });

    if (process.platform !== "win32") {
      const escaped = path.join(projectsRoot(), "escaped-project");
      rmSync(escaped, { force: true });
      symlinkSync(repositoryRoot, escaped, "dir");
      const symlinkEscape = await request.get("/api/smoke/pack?projectRef=escaped-project", {
        headers: runnerHeaders,
      });
      expect(symlinkEscape.status()).toBe(400);
      expect(await symlinkEscape.json()).toMatchObject({
        status: "BLOCKED",
        reason: "SMOKE_PATH_CONFINEMENT_FAILED",
      });
    }
  });

  test("凭证不能切换租户", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "安全边界只执行一次");
    const response = await request.post("/api/smoke/sessions", {
      headers: { ...runnerHeaders, "X-ELMOS-Tenant": "other-e2e" },
      data: { projectRef, entry: "zero-dep" },
    });
    expect(response.status()).toBe(403);
  });

  test("会话写接口拒绝畸形或超限 JSON", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "请求边界只执行一次");
    const malformed = await request.post("/api/smoke/sessions", {
      headers: runnerHeaders,
      data: Buffer.from("{not-json", "utf-8"),
    });
    expect(malformed.status()).toBe(400);
    expect(await malformed.json()).toMatchObject({ status: "BLOCKED", reason: "INVALID_JSON" });

    const oversized = await request.post("/api/smoke/sessions", {
      headers: runnerHeaders,
      data: { projectRef, padding: "x".repeat(5_000) },
    });
    expect(oversized.status()).toBe(413);
    expect(await oversized.json()).toMatchObject({ status: "BLOCKED", reason: "REQUEST_TOO_LARGE" });
  });

  test("一键运行：起服务、跑断言、显式续期、停止回收、门禁给结论", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "有副作用的代表旅程只执行一次");
    test.skip(python() === null, "需要 python3 才能真实运行");
    test.setTimeout(180_000);

    const created = await request.post("/api/smoke/sessions", {
      headers: runnerHeaders,
      data: { projectRef, entry: "zero-dep", ttlSeconds: 120 },
    });
    expect(created.status()).toBe(202);
    const session = await created.json();
    expect(session.location).toBe("LOCAL_WORKSTATION");
    expect(session.freeQuotaSeconds).toBe(600);

    const sessionUrl = `/api/smoke/sessions/${session.sessionId}`;
    const readSession = async () => (await request.get(sessionUrl, { headers: runnerHeaders })).json();

    // 服务起来，断言通过，倒计时在跑。
    await expect.poll(async () => {
      const current = await readSession();
      const readiness = current.checks.find((check: { id: string }) => check.id === "http-readiness");
      return readiness?.status ?? "PENDING";
    }, { timeout: 90_000, intervals: [1_000] }).toBe("PASS");

    const live = await readSession();
    expect(["READY", "HOLDING"]).toContain(live.state);
    expect(live.url).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
    expect(live.remainingSeconds).toBeGreaterThan(0);
    expect(live.remainingSeconds).toBeLessThanOrEqual(120);
    expect(live.checks.find((check: { id: string }) => check.id === "seed-visible").status).toBe("PASS");
    // 零依赖入口必须带着语义警告，不能悄悄换引擎。
    expect(live.notes.join(" ")).toContain("substitute");

    // 续期必须显式且可归因。
    const withoutReason = await request.post(`${sessionUrl}/extend`, {
      headers: runnerHeaders,
      data: { seconds: 60 },
    });
    expect(withoutReason.status()).toBe(400);
    expect(await withoutReason.json()).toMatchObject({ status: "BLOCKED", reason: "SMOKE_REASON_REQUIRED" });

    const tooShort = await request.post(`${sessionUrl}/extend`, {
      headers: runnerHeaders,
      data: { seconds: 5, reason: "太短的续期应当被拒" },
    });
    expect(tooShort.status()).toBe(400);

    const extended = await request.post(`${sessionUrl}/extend`, {
      headers: runnerHeaders,
      data: { seconds: 60, reason: "e2e 验证续期会被运行中的看门狗采纳", actor: "user:e2e" },
    });
    expect(extended.status()).toBe(200);
    const afterExtension = await extended.json();
    expect(afterExtension.ttlSeconds).toBe(180);
    expect(afterExtension.extensions.at(-1)).toMatchObject({
      seconds: 60,
      actor: "user:e2e",
      beyondFreeQuota: false,
    });

    // 停止即回收：服务停掉，容器与临时数据清掉，证据留下。
    const stopped = await postTolerantOfRestart(request, `${sessionUrl}/stop`, { reason: "e2e-teardown" });
    expect(stopped.status()).toBe(200);

    // 门禁在运行结束后由运行器自动执行，等它出结论再断言，避免与回收竞态。
    await expect.poll(async () => (await readSession()).gateStatus,
      { timeout: 60_000, intervals: [1_000] }).not.toBe("NOT_RUN");

    const finished = await readSession();
    expect(finished.teardown?.complete).toBe(true);
    expect(["COMPLETED", "EXPIRED", "FAILED"]).toContain(finished.state);
    expect(finished.remainingSeconds).toBe(0);
    expect(finished.teardown.processes.every((item: { killed: boolean }) => !item.killed)).toBe(true);
    // 零依赖入口跑出来的结论只能是 limited，不能是 runnable。
    expect(finished.gateStatus).toBe("limited");
    expect(finished.gateFailures).toEqual([]);
    expect(finished.gateLimitations.join(" ")).toContain("zero-dependency");

    const evidence = await (await request.get(`${sessionUrl}/evidence`, { headers: runnerHeaders })).json();
    expect(evidence.retainedAfterExpiry).toBe(true);
    expect(evidence.result.overall).toBe("PASS");
    expect(evidence.lease.teardown_complete).toBe(true);
    expect(evidence.logs.length).toBeGreaterThan(0);

    // Rerun the same project. The first session's bytes must be snapshotted
    // before the shared project runtime is cleared, and an old session handle
    // must never be able to stop the new lease.
    const rerunResponse = await request.post("/api/smoke/sessions", {
      headers: runnerHeaders,
      data: { projectRef, entry: "zero-dep", ttlSeconds: 60 },
    });
    expect(rerunResponse.status()).toBe(202);
    const rerun = await rerunResponse.json();
    const rerunUrl = `/api/smoke/sessions/${rerun.sessionId}`;
    await expect.poll(async () => {
      const current = await (await request.get(rerunUrl, { headers: runnerHeaders })).json();
      const readiness = current.checks.find((check: { id: string }) => check.id === "http-readiness")?.status;
      return readiness === "PASS" ? current.state : "PENDING";
    }, { timeout: 90_000, intervals: [1_000] }).toBe("HOLDING");

    const oldStop = await request.post(`${sessionUrl}/stop`, {
      headers: runnerHeaders,
      data: { reason: "old-session-must-be-idempotent" },
    });
    expect(oldStop.status()).toBe(200);
    const stillRunning = await (await request.get(rerunUrl, { headers: runnerHeaders })).json();
    expect(["READY", "HOLDING"]).toContain(stillRunning.state);

    const retained = await (await request.get(`${sessionUrl}/evidence`, { headers: runnerHeaders })).json();
    expect(retained.result.result_digest).toBe(evidence.result.result_digest);
    expect(retained.lease.lease_id).toBe(evidence.lease.lease_id);

    const rerunStopped = await request.post(`${rerunUrl}/stop`, {
      headers: runnerHeaders,
      data: { reason: "e2e-rerun-teardown" },
    });
    expect(rerunStopped.status()).toBe(200);
  });
});

/* ------------------------------------------------------------------ UI ---- */

type StubSession = Record<string, unknown>;

function stubSession(overrides: StubSession = {}): StubSession {
  return {
    sessionId: "11111111-2222-4333-8444-555555555555",
    projectRef,
    entry: "zero-dep",
    location: "LOCAL_WORKSTATION",
    state: "HOLDING",
    url: "http://127.0.0.1:5000",
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:05.000Z",
    freeQuotaSeconds: 600,
    ttlSeconds: 600,
    billableSeconds: 0,
    remainingSeconds: 597,
    expiresAtEpoch: Date.now() / 1_000 + 597,
    checks: [
      { id: "process-started", status: "PASS", detail: "pid 4242 is live", required: true },
      { id: "http-readiness", status: "PASS", detail: "/health -> 200", required: true },
      { id: "http-functional", status: "NOT_RUN", detail: "未声明可用端点", required: false },
    ],
    notes: ["an embedded substitute is not the production engine"],
    extensions: [],
    teardown: null,
    gateStatus: "NOT_RUN",
    gateFailures: [],
    gateLimitations: [],
    evidenceAvailable: false,
    ...overrides,
  };
}

async function stubSmokeApi(page: import("@playwright/test").Page, session: StubSession) {
  await page.route("**/api/telemetry/events", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/api/smoke/capability", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      freeQuotaSeconds: 600,
      graceSeconds: 30,
      autoRenew: false,
      extendPolicy: "EXPLICIT_ONLY",
      locations: [
        { location: "HOSTED_RUNNER", status: "NOT_CONFIGURED", reason: "沙箱未配置" },
        { location: "LOCAL_WORKSTATION", status: "AVAILABLE" },
      ],
      preferredLocation: "LOCAL_WORKSTATION",
      checkedAt: "2026-01-01T00:00:00.000Z",
    }),
  }));
  await page.route("**/api/smoke/pack*", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      projectRef,
      languages: ["python"],
      frameworks: ["flask"],
      datastores: ["postgres"],
      entries: [
        { entry: "script", status: "available", command: "./run-smoke.sh" },
        { entry: "compose", status: "unavailable", reason: "docker 未安装" },
        { entry: "make", status: "available" },
        {
          entry: "zero-dep",
          status: "available",
          semanticWarning: "内嵌替代不是声明的引擎，结论只作冒烟证据",
        },
      ],
      defaultEntry: "zero-dep",
      unknownCount: 0,
    }),
  }));
  await page.route("**/api/smoke/sessions", (route) => route.fulfill({
    status: 202,
    contentType: "application/json",
    body: JSON.stringify(session),
  }));
  await page.route(/\/api\/smoke\/sessions\/[0-9a-f-]{36}$/, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(session),
  }));
}

async function loadPanel(page: import("@playwright/test").Page) {
  await page.goto("/smoke");
  await page.getByRole("textbox").fill(projectRef);
  await page.getByRole("button", { name: "载入冒烟包" }).click();
  await expect(page.getByRole("heading", { name: "一键运行冒烟测试" })).toBeVisible();
}

test.describe("Batch 46 一键运行 · 界面", () => {
  test("运行中显示倒计时、服务地址与逐条断言", async ({ page }) => {
    await stubSmokeApi(page, stubSession());
    await loadPanel(page);

    await page.getByRole("button", { name: /一键运行（免费 10 分钟）/ }).click();

    await expect(page.getByText(/^0[89]:\d\d$/)).toBeVisible();
    await expect(page.getByRole("link", { name: "http://127.0.0.1:5000" })).toBeVisible();
    await expect(page.getByText("pid 4242 is live")).toBeVisible();
    // NOT_RUN 必须照实显示，不能被折算成通过。
    await expect(page.getByText("未声明可用端点")).toBeVisible();
    await expect(page.getByText(/an embedded substitute is not the production engine/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "立即停止并回收" })).toBeEnabled();
  });

  test("续期必须填写理由，未填写时无法提交", async ({ page }) => {
    await stubSmokeApi(page, stubSession());
    await loadPanel(page);
    await page.getByRole("button", { name: /一键运行（免费 10 分钟）/ }).click();
    await page.getByRole("button", { name: "续期", exact: true }).click();

    await expect(page.getByText(/续期不会自动发生/)).toBeVisible();
    const confirm = page.getByRole("button", { name: /确认续期/ });
    await expect(confirm).toBeDisabled();
    await page.getByPlaceholder("例如：复现 POST /orders 的 500").fill("复现登录 500");
    await expect(confirm).toBeEnabled();
  });

  test("额度到期后按钮变为重新运行，并展示回收报告、门禁结论与保留的证据", async ({ page }) => {
    await stubSmokeApi(page, stubSession({
      state: "EXPIRED",
      remainingSeconds: 0,
      expiresAtEpoch: Date.now() / 1_000 - 5,
      url: null,
      billableSeconds: 300,
      ttlSeconds: 900,
      extensions: [{
        grantedAt: "2026-01-01T00:05:00.000Z",
        seconds: 300,
        reason: "复现登录 500",
        actor: "user:e2e",
        beyondFreeQuota: true,
      }],
      teardown: {
        reason: "expired",
        stoppedAt: "2026-01-01T00:10:00.000Z",
        processes: [{ pid: 4242, graceful: true, killed: false, exitCode: 0 }],
        compose: [],
        removedPaths: [{ path: "/tmp/smoke.sqlite", removed: "file" }],
        complete: true,
      },
      gateStatus: "limited",
      gateLimitations: ["executed through the zero-dependency entry"],
      evidenceAvailable: true,
    }));
    await loadPanel(page);
    await page.getByRole("button", { name: /一键运行（免费 10 分钟）/ }).click();

    await expect(page.getByRole("button", { name: /重新运行（新的免费额度）/ })).toBeEnabled();
    await expect(page.getByRole("button", { name: "立即停止并回收" })).toHaveCount(0);
    await expect(page.getByText("回收报告（额度到期）")).toBeVisible();
    await expect(page.getByText(/全部在宽限期内优雅退出/)).toBeVisible();
    await expect(page.getByText(/回收结论：无残留/)).toBeVisible();
    await expect(page.getByText(/超出免费额度/).first()).toBeVisible();
    await expect(page.getByText(/executed through the zero-dependency entry/).first()).toBeVisible();
    await expect(page.getByText(/服务已回收，证据与日志仍然保留/)).toBeVisible();
  });

  test("没有可用执行位置时按钮禁用并说明原因", async ({ page }) => {
    await page.route("**/api/telemetry/events", (route) => route.fulfill({ status: 204, body: "" }));
    await page.route("**/api/smoke/capability", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        freeQuotaSeconds: 600,
        graceSeconds: 30,
        autoRenew: false,
        extendPolicy: "EXPLICIT_ONLY",
        locations: [
          { location: "HOSTED_RUNNER", status: "NOT_CONFIGURED", reason: "沙箱未配置" },
          { location: "LOCAL_WORKSTATION", status: "NOT_CONFIGURED", reason: "本机运行未启用" },
        ],
        preferredLocation: null,
        checkedAt: "2026-01-01T00:00:00.000Z",
      }),
    }));
    await page.route("**/api/smoke/pack*", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        projectRef,
        languages: ["python"],
        frameworks: [],
        datastores: [],
        entries: [
          { entry: "script", status: "available", command: "./run-smoke.sh" },
          { entry: "compose", status: "unavailable", reason: "无 Dockerfile" },
          { entry: "make", status: "available" },
          { entry: "zero-dep", status: "available" },
        ],
        defaultEntry: "script",
        unknownCount: 0,
      }),
    }));

    await loadPanel(page);
    await expect(page.getByRole("button", { name: /一键运行（免费 10 分钟）/ })).toBeDisabled();
    await expect(page.getByText(/当前没有可用的执行位置/)).toBeVisible();
    await expect(page.getByText(/本机运行未启用/)).toBeVisible();
  });
});

import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import path from "node:path";

const repositoryRoot = path.resolve(__dirname, "../../..");
const runnerHeaders = {
  "Content-Type": "application/json",
  "Authorization": "Bearer elmos-e2e-local-token-32-characters",
  "X-ELMOS-Tenant": "local-e2e",
  "X-ELMOS-Actor": "user:e2e",
};
const terminal = new Set(["SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"]);

function assessmentRequest(commandMarker?: string) {
  return {
    request_id: crypto.randomUUID(),
    skill: "pm-b02-repository-modernization-assessment",
    mode: "assess",
    inputs: {
      assets: [],
      parameters: {
        workspace_path: path.join(repositoryRoot, "scripts/precision_migration"),
        ...(commandMarker ? { command: `touch ${commandMarker}` } : {}),
      },
    },
    policy: {
      unresolved_differences: "block",
      allow_test_weakening: false,
      require_provenance: true,
      risk_level: "medium",
    },
    evidence: [],
    semantic_losses: [],
    approvals: [],
  };
}

test.describe.configure({ mode: "serial" });

test("租户隔离 API 完成真实只读评估并提供内容寻址产物", async ({ request }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "持久化 API 旅程只执行一次");
  const runnerRoot = process.env.ELMOS_E2E_EFFECTIVE_RUNNER_ROOT;
  expect(runnerRoot).toBeTruthy();
  const commandMarker = path.join(runnerRoot!, "request-command-must-not-run");

  const weakened = assessmentRequest() as ReturnType<typeof assessmentRequest>;
  weakened.policy.allow_test_weakening = true;
  const rejected = await request.post("/api/precision-migration/jobs", {
    headers: runnerHeaders,
    data: weakened,
  });
  expect(rejected.status()).toBe(400);
  expect(await rejected.json()).toMatchObject({ reason: "policy.allow_test_weakening must be false" });

  const created = await request.post("/api/precision-migration/jobs", {
    headers: runnerHeaders,
    data: assessmentRequest(commandMarker),
  });
  expect(created.status()).toBe(202);
  const submission = await created.json() as { job_id: string; status: string };
  expect(submission.job_id).toMatch(/^pmj-[0-9a-f]{32}$/);

  let completed: {
    status: string;
    progress: number;
    artifacts?: Array<{ uri: string; digest: string; size_bytes: number }>;
    result?: { execution_state?: string };
  } | undefined;
  await expect.poll(async () => {
    const response = await request.get(`/api/precision-migration/jobs/${submission.job_id}`, {
      headers: runnerHeaders,
    });
    expect(response.ok()).toBe(true);
    completed = await response.json();
    return terminal.has(completed!.status) ? completed!.status : "PENDING";
  }, { timeout: 45_000 }).toBe("SUCCEEDED");

  expect(completed).toMatchObject({
    status: "SUCCEEDED",
    progress: 100,
    result: { execution_state: "LOCAL_EXECUTED" },
  });
  expect(completed!.artifacts).toHaveLength(1);
  expect(completed!.artifacts![0].digest).toMatch(/^sha256:[0-9a-f]{64}$/);
  expect(completed!.artifacts![0].size_bytes).toBeGreaterThan(100);
  expect(existsSync(commandMarker)).toBe(false);

  const artifact = await request.get(
    `/api/precision-migration/jobs/${submission.job_id}/artifacts/repository-assessment.json`,
    { headers: runnerHeaders },
  );
  expect(artifact.ok()).toBe(true);
  expect(artifact.headers()["content-type"]).toContain("application/json");
  expect(await artifact.json()).toMatchObject({
    skill: "pm-b02-repository-modernization-assessment",
    truncated: false,
  });

  const tenantDigest = createHash("sha256").update("local-e2e").digest("hex");
  const storedArtifact = path.join(
    runnerRoot!, "precision-migration-jobs", "tenants", tenantDigest, "jobs",
    submission.job_id, "artifacts", "repository-assessment.json",
  );
  await writeFile(storedArtifact, "{}\n", "utf-8");
  const tampered = await request.get(
    `/api/precision-migration/jobs/${submission.job_id}/artifacts/repository-assessment.json`,
    { headers: runnerHeaders },
  );
  expect(tampered.status()).toBe(409);
  expect(await tampered.json()).toMatchObject({ reason: "ARTIFACT_INTEGRITY_MISMATCH" });

  const switchedTenant = await request.get(`/api/precision-migration/jobs/${submission.job_id}`, {
    headers: { ...runnerHeaders, "X-ELMOS-Tenant": "other-e2e" },
  });
  expect(switchedTenant.status()).toBe(403);
  expect(await switchedTenant.json()).toMatchObject({ reason: "TENANT_ID_NOT_BOUND_TO_CREDENTIAL" });
});

test("Skills 页面可提交、轮询、重试并下载精密迁移作业", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "浏览器代表旅程只执行一次");
  await page.goto("/skills");
  const card = page.getByRole("region", { name: "精密迁移作业" });
  await card.getByText("本地开发认证（生产环境使用企业会话）").click();
  await card.getByLabel("本地租户").fill("local-e2e");
  await card.getByLabel("本地 Actor").fill("user:e2e");
  await card.getByLabel("本地短期 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
  await card.getByLabel("只读工作区路径").fill(path.join(repositoryRoot, "scripts/precision_migration"));
  await card.getByRole("button", { name: "提交作业" }).click();

  await expect(card.getByText("SUCCEEDED", { exact: true })).toBeVisible({ timeout: 45_000 });
  await expect(card.getByText("LOCAL_EXECUTED", { exact: true })).toBeVisible();
  await expect(card.getByText(/pmj-[0-9a-f]{32}/)).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await card.getByRole("button", { name: /repository-assessment.json/ }).click();
  expect((await downloadPromise).suggestedFilename()).toBe("repository-assessment.json");

  await card.getByRole("button", { name: "重试" }).click();
  await expect(card.getByText("SUCCEEDED", { exact: true })).toBeVisible({ timeout: 45_000 });
  await expect(card.getByText("重试来源")).toBeVisible();
});

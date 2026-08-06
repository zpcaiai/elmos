import { expect, test } from "@playwright/test";

const digest = `sha256:${"a".repeat(64)}`;

test("submits one idempotent proof mutation and polls to a fail-closed result", async ({ page }) => {
  let createCalls = 0;
  let jobReads = 0;

  await page.route("**/api/modernization-proof/contracts", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      id: "B108-S16",
      batch: 108,
      name: "customer-ready-modernization-certificate",
      dependencies: ["B108-S13", "B108-S15"],
      canonicalSha256: digest,
      executionClass: "INDEPENDENT_GATE",
      evidenceSlots: ["modernization-certificate.json", "claim-evaluation.json"],
    }]),
  }));
  await page.route("**/api/modernization-proof/subject-digest", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ organizationId: "local-e2e", subjectDigest: digest, canonicalizationVersion: 1 }),
  }));
  await page.route("**/api/modernization-proof/jobs", async (route) => {
    createCalls += 1;
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ jobId: "job-proof-1" }) });
  });
  await page.route("**/api/modernization-proof/jobs/job-proof-1", async (route) => {
    jobReads += 1;
    const running = jobReads === 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        jobId: "job-proof-1",
        organizationId: "local-e2e",
        actorId: "user:e2e",
        businessLine: "MODERNIZATION_PROOF",
        jobKind: "batch105-108-proof-loop",
        status: running ? "RUNNING" : "FAILED",
        stage: running ? "evaluate-contracts" : "blocked",
        progress: running ? 55 : 100,
        resultStatus: running ? "NOT_RUN" : "BLOCKED",
        createdAt: "2026-08-05T12:00:00Z",
        cancelRequested: false,
        artifacts: running ? [] : [{
          role: "EVIDENCE_PACK",
          filename: "evidence/proof-loop-result.json",
          contentSha256: digest,
          byteSize: 4096,
        }],
      }),
    });
  });

  await page.goto("/proof-loop");
  await expect(page.getByRole("heading", { name: "现代化生产证据闭环" })).toBeVisible();
  await page.getByLabel("项目 ID").fill("project-e2e");
  await page.getByLabel("仓库 ID").fill("repository-e2e");
  await page.getByLabel("策略摘要").fill(digest);
  await page.getByRole("button", { name: "提交证据闭环" }).click();

  await expect(page.getByText("job-proof-1")).toBeVisible();
  await expect(page.getByText("FAILED", { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("EVIDENCE_PACK")).toBeVisible();
  await expect(page.getByText(digest)).toBeVisible();
  expect(createCalls).toBe(1);
  expect(jobReads).toBeGreaterThanOrEqual(2);
});

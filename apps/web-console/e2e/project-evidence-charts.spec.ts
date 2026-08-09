import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { GenerationJob, TranslationJob } from "../app/lib/contracts";

const generationJobId = "123e4567-e89b-42d3-a456-426614174101";
const translationJobId = "123e4567-e89b-42d3-a456-426614174102";
const maliciousLabel = '<img src=x onerror="window.__evidencePwned=1">';

function generationJob(): GenerationJob {
  return {
    id: generationJobId,
    tenantId: "tenant-evidence",
    actor: "user:evidence-reviewer",
    createdAt: "2026-08-10T01:00:00Z",
    updatedAt: "2026-08-10T01:05:00Z",
    status: "COMPLETED",
    stage: "complete",
    progress: 100,
    resultStatus: "PASSED",
    artifactReady: false,
    artifacts: [],
    logs: [],
    runtime: {
      status: "STOPPED",
      plans: [],
      updatedAt: "2026-08-10T01:05:00Z",
    },
    insights: {
      schema_version: "1.0.0",
      kind: "elmos.project-generation-insights",
      stage: "VERIFIED",
      project: {
        id: "PRJ-EVIDENCE",
        name: "evidence-service",
        request_sha256: "a".repeat(64),
        approved_payload_sha256: "b".repeat(64),
      },
      claim_ceiling: "LOCAL_ENGINEERING_EVIDENCE",
      project_structure: {
        schema_version: "1.0.0",
        graph_kind: "elmos.project-structure",
        project: {
          id: "PRJ-EVIDENCE",
          name: "evidence-service",
          repository_mode: "polyglot-monorepo",
          approved_payload_sha256: "b".repeat(64),
        },
        nodes: [
          { id: "repository", kind: "repository", path: ".", label: "evidence-service", ownership: "managed", file_count: 18, status: "REPRESENTED" },
          { id: "app:java", kind: "application", path: "java", label: maliciousLabel, ownership: "managed", file_count: 9, status: "REPRESENTED", language: "java", framework: "Spring Boot 3.5.3", runtime: "21" },
          { id: "app:python", kind: "application", path: "python", label: "Python API", ownership: "managed", file_count: 9, status: "REPRESENTED", language: "python", framework: "FastAPI 0.116.1", runtime: "3.12" },
        ],
        edges: [
          { from: "repository", to: "app:java", type: "contains" },
          { from: "repository", to: "app:python", type: "contains" },
        ],
        coverage: {
          scope: "managed-generated-artifacts",
          managed_file_count: 18,
          classified_file_count: 18,
          declared_application_count: 2,
          represented_application_count: 2,
          unclassified_paths: [],
          status: "PASSED",
        },
      },
      declared_dependencies: {
        schema_version: "1.0.0",
        graph_kind: "elmos.declared-dependency-graph",
        project_id: "PRJ-EVIDENCE",
        nodes: [
          { id: "app:java", kind: "application", coordinate: "java", version_source: "project-blueprint" },
          { id: "runtime:java:21", kind: "runtime", coordinate: "java@21", version_source: "project-blueprint" },
          { id: "app:python", kind: "application", coordinate: "python", version_source: "project-blueprint" },
          { id: "runtime:python:3.12", kind: "runtime", coordinate: "python@3.12", version_source: "project-blueprint" },
        ],
        edges: [
          { from: "app:java", to: "runtime:java:21", type: "requires", scope: "runtime", evidence_status: "DECLARED" },
          { from: "app:python", to: "runtime:python:3.12", type: "requires", scope: "runtime", evidence_status: "DECLARED" },
        ],
        resolution: { status: "NOT_RUN", resolved_graph_refs: [] },
        complete: false,
        issues: ["NATIVE_TRANSITIVE_RESOLUTION_NOT_RUN"],
      },
      structure: {
        graph_kind: "project-synthesis-insight-graph",
        nodes: [
          { id: "approved", label: "Approved request", kind: "baseline", path: "requirements/approved-request.json", status: "PASSED" },
          { id: "psir", label: "Typed PSIR", kind: "semantic-ir", path: "requirements/psir.json", status: "PASSED" },
        ],
        edges: [{ from: "approved", to: "psir", relation: "normalizes" }],
        node_count: 2,
        edge_count: 1,
        target_count: 2,
      },
      semantic: {
        relation: "APPROVED_REQUIREMENTS_TO_GENERATED_TARGETS",
        mapping_status: "PASSED",
        equivalence_status: "NOT_RUN",
        subjects: [{
          id: "requirements",
          label: "批准需求",
          source_count: 2,
          mapped_count: 2,
          mapping_status: "PASSED",
          semantic_equivalence_status: "NOT_RUN",
          evidence_strength: "HASH_BOUND_TRACEABILITY",
        }],
        source_subject_count: 2,
        mapped_subject_count: 2,
        limitations: ["哈希绑定映射不是直接语义等价证明。"],
      },
      behavior: {
        profile: "native-build-test-startup-v1",
        status: "PASSED",
        targets: [
          {
            language: "java",
            status: "PASSED",
            exact_toolchain_status: "PASSED",
            build_analysis: { total: 1, status_counts: { PASSED: 1, FAILED: 0, NOT_RUN: 0, UNKNOWN: 0, NOT_APPLICABLE: 0 } },
            startup_status: "PASSED",
          },
          {
            language: "python",
            status: "PASSED",
            exact_toolchain_status: "PASSED",
            build_analysis: { total: 1, status_counts: { PASSED: 1, FAILED: 0, NOT_RUN: 0, UNKNOWN: 0, NOT_APPLICABLE: 0 } },
            startup_status: "PASSED",
          },
        ],
        cross_target_matrix: [
          { source: "java", target: "java", semantic_status: "NOT_APPLICABLE", behavior_status: "NOT_APPLICABLE", reason: "SAME_TARGET" },
          { source: "java", target: "python", semantic_status: "NOT_RUN", behavior_status: "NOT_RUN", reason: "DIRECT_PAIRWISE_SOURCE_TARGET_COMPARISON_NOT_EXECUTED" },
          { source: "python", target: "java", semantic_status: "NOT_RUN", behavior_status: "NOT_RUN", reason: "DIRECT_PAIRWISE_SOURCE_TARGET_COMPARISON_NOT_EXECUTED" },
          { source: "python", target: "python", semantic_status: "NOT_APPLICABLE", behavior_status: "NOT_APPLICABLE", reason: "SAME_TARGET" },
        ],
        limitations: ["单目标原生验证通过不代表跨目标行为等价。"],
      },
      coverage: [
        { id: "project-structure", label: "项目结构", status: "PASSED", passed: 1, total: 1 },
        { id: "requirements-traceability", label: "需求映射", status: "PASSED", passed: 1, total: 1 },
        { id: "native-target-verification", label: "原生目标验证", status: "PASSED", passed: 2, total: 2 },
        { id: "direct-semantic-equivalence", label: "直接语义等价", status: "NOT_RUN", passed: 0, total: 2 },
        { id: "direct-behavior-equivalence", label: "直接行为等价", status: "NOT_RUN", passed: 0, total: 2 },
      ],
      verification_status: "PASSED",
      external_verification_status: "NOT_RUN",
      certification_status: "NOT_CERTIFIED",
    },
  };
}

function translationJob(): TranslationJob {
  return {
    id: translationJobId,
    tenantId: "tenant-evidence",
    actor: "user:evidence-reviewer",
    createdAt: "2026-08-10T02:00:00Z",
    updatedAt: "2026-08-10T02:05:00Z",
    repositoryRef: "local:evidence-repository",
    workspaceId: "evidence-repository",
    casesBundleId: "evidence-holdout",
    sourceLanguage: "java",
    targetLanguage: "python",
    repositoryExecutionStatus: "PASSED",
    repositoryProfile: "typed-pure-function-v1",
    repositoryEvidenceRef: "routes/java-to-python/evidence.json",
    repositoryEvidenceSha256: "c".repeat(64),
    repositoryEvidenceBytes: 128,
    status: "PARTIAL",
    stage: "complete",
    progress: 100,
    executor: "HOST_DEVELOPMENT",
    recoveryAttempts: 0,
    artifactReady: false,
    workUnitCount: 2,
    includedUnitCount: 1,
    semanticCoverage: {
      profile: "compiler-semantic-symbol-coverage-v1",
      sourceLanguage: "java",
      status: "LIMITED",
      complete: false,
      inventoryStatus: "PASSED",
      subjectCount: 3,
      statusCounts: { BLOCKED: 0, FAILED: 0, NOT_RUN: 1, PASSED: 2, UNKNOWN: 0 },
    },
    behaviorCoverage: {
      profile: "typed-pure-function-v1",
      status: "NOT_RUN",
      complete: false,
      workUnitCount: 2,
      accountedWorkUnitCount: 2,
      attemptedWorkUnitCount: 1,
      unresolvedWorkUnitCount: 1,
      behaviorCaseCount: 4,
      behaviorCaseCountScope: "PASSED_WORK_UNITS_ONLY",
      statusCounts: { FAILED: 0, NOT_RUN: 1, PASSED: 1, UNKNOWN: 0 },
      evidenceStrength: "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON",
      independentVerificationStatus: "NOT_RUN",
      externalVerificationStatus: "NOT_RUN",
    },
    independentVerificationStatus: "NOT_RUN",
    externalVerificationStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    logs: [],
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) => route.fulfill({ status: 204, body: "" }));
});

test("生成结果以可访问结构图、精确分母和 NOT_RUN NxN 矩阵呈现", async ({ page }, testInfo) => {
  test.skip(!["chromium", "mobile-chromium"].includes(testInfo.project.name), "代表性桌面与移动视口");
  const job = generationJob();
  await page.route(`**/api/generation/jobs/${generationJobId}`, (route) => route.fulfill({ status: 200, json: job }));

  await page.goto("/generation");
  await page.getByLabel("租户标识").fill(job.tenantId);
  await page.getByLabel("审批者标识").fill(job.actor);
  await page.getByLabel("本地 Runner 令牌").fill("short-lived-evidence-runner-token");
  await page.getByLabel("恢复任务 ID").fill(generationJobId);
  const recover = page.getByRole("button", { name: "恢复任务" });
  await expect(recover).toBeEnabled();
  await recover.click();

  await expect(page.getByRole("heading", { name: "项目结构与等价证据" })).toBeVisible();
  await expect(page.getByText("完整项目结构", { exact: true })).toBeVisible();
  await expect(page.getByText("声明依赖图", { exact: true })).toBeVisible();
  await expect(page.locator(".evidence-graph-node strong").filter({ hasText: maliciousLabel })).toBeVisible();
  await expect(page.locator(".project-evidence-charts img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as typeof window & { __evidencePwned?: number }).__evidencePwned)).toBeUndefined();

  const directBehavior = page.getByRole("progressbar", { name: "直接行为等价", exact: true });
  await expect(directBehavior).toHaveAttribute("aria-valuenow", "0");
  await expect(directBehavior).toHaveAttribute("aria-valuemax", "2");
  await expect(directBehavior).toHaveAttribute("aria-valuetext", /未运行 2/);
  const behaviorMatrix = page.getByRole("region", { name: "直接行为等价矩阵，可横向滚动" });
  await behaviorMatrix.focus();
  await expect(behaviorMatrix).toBeFocused();
  await expect(page.getByLabel(/Java 到 Python，直接行为等价未运行/)).toBeVisible();

  expect((await new AxeBuilder({ page }).include(".project-evidence-charts").analyze()).violations).toEqual([]);
  const widths = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
  expect(widths.content).toBeLessThanOrEqual(widths.viewport);
});

test("转换结果分别呈现语义主题和行为工作单元覆盖", async ({ page }, testInfo) => {
  test.skip(!["chromium", "mobile-chromium"].includes(testInfo.project.name), "代表性桌面与移动视口");
  const job = translationJob();
  await page.route(`**/api/translation/jobs/${translationJobId}`, (route) => route.fulfill({ status: 200, json: job }));

  await page.goto("/translation");
  await page.getByLabel("跨语言租户标识").fill(job.tenantId);
  await page.getByLabel("跨语言执行者标识").fill(job.actor);
  await page.getByLabel("跨语言 Runner 令牌").fill("short-lived-translation-token");
  await page.getByLabel("恢复任务 UUID").fill(translationJobId);
  await page.getByRole("button", { name: "恢复任务" }).click();

  await expect(page.getByRole("heading", { name: "转换语义与行为覆盖" })).toBeVisible();
  const semantic = page.getByRole("progressbar", { name: "编译器语义主题" });
  await expect(semantic).toHaveAttribute("aria-valuenow", "2");
  await expect(semantic).toHaveAttribute("aria-valuemax", "3");
  await expect(semantic).toHaveAttribute("aria-valuetext", /未运行 1/);
  const behavior = page.getByRole("progressbar", { name: "工作单元行为回放" });
  await expect(behavior).toHaveAttribute("aria-valuenow", "1");
  await expect(behavior).toHaveAttribute("aria-valuemax", "2");
  await expect(page.getByText("1 / 2", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("PASSED_WORK_UNITS_ONLY", { exact: false })).toBeVisible();

  expect((await new AxeBuilder({ page }).include(".translation-evidence-charts").analyze()).violations).toEqual([]);
  const widths = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
  expect(widths.content).toBeLessThanOrEqual(widths.viewport);
});

test("缺失生成 insights 时所有图表保持 NOT_RUN", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "缺失数据兼容只需执行一次");
  const job = generationJob();
  delete job.insights;
  await page.route(`**/api/generation/jobs/${generationJobId}`, (route) => route.fulfill({ status: 200, json: job }));

  await page.goto("/generation");
  await page.getByLabel("租户标识").fill(job.tenantId);
  await page.getByLabel("审批者标识").fill(job.actor);
  await page.getByLabel("本地 Runner 令牌").fill("short-lived-evidence-runner-token");
  await page.getByLabel("恢复任务 ID").fill(generationJobId);
  await page.getByRole("button", { name: "恢复任务" }).click();

  await expect(page.getByText("项目洞察尚未生成", { exact: true })).toBeVisible();
  await expect(page.getByText("结构、依赖、语义映射和行为等价均保持 NOT_RUN。", { exact: true })).toBeVisible();
  await expect(page.locator(".project-evidence-charts [role=progressbar]")).toHaveCount(0);
});

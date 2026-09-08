import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  cancelHostedGenerationJob,
  createHostedGenerationJob,
  getHostedGenerationJob,
  hostedArtifactTicket,
} from "../app/lib/server/hostedExecutionClient.ts";

// Mirrors canonicalJson/sha256Json in generationRunner.ts: the stored review
// digest must be recomputed exactly the way the server does it.
function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function sha256Json(value) {
  return createHash("sha256").update(canonicalJson(value)).digest("hex");
}

const TENANT = "tenant-hosted";
const ACTOR = "actor-hosted";
const ACCESS_TOKEN = "control-plane-access-token";

const synthesisRequest = {
  status: "REVIEW_REQUIRED",
  entities: [{ singular: "work_order", plural: "work_orders", fields: [] }],
  requirements: [],
  open_questions: [],
};

const intentShape = (overrides = {}) => ({
  name: "work-order-service",
  namespace: "elmos.test",
  description: "维修工单创建、查询和健康检查服务。",
  entity: "work_order",
  targets: ["python"],
  persistence: "in-memory",
  authMode: "none",
  ...overrides,
});

function createRequest(analysisDigest) {
  return { ...intentShape(), reviewer: ACTOR, approved: true, analysisDigest };
}

const ENV_NAMES = [
  "NODE_ENV",
  "ELMOS_LOCAL_RUNNER_ENABLED",
  "ELMOS_LOCAL_RUNNER_ROOT",
  "ELMOS_REPOSITORY_ROOT",
  "ELMOS_UV_PATH",
  "ELMOS_LOCAL_RUNNER_EXECUTOR",
  "ELMOS_CONTROL_PLANE_BASE_URL",
  "ELMOS_GENERATION_ARTIFACT_DOWNLOAD_ALLOWED_HOSTS",
];

async function sandbox(context, { controlPlaneBaseUrl = "https://control-plane.test" } = {}) {
  const saved = Object.fromEntries(ENV_NAMES.map((name) => [name, process.env[name]]));
  context.after(() => {
    for (const name of ENV_NAMES) {
      if (saved[name] === undefined) delete process.env[name];
      else process.env[name] = saved[name];
    }
    globalThis.fetch = savedFetch;
  });

  const root = await mkdtemp(path.join(tmpdir(), "elmos-hosted-client-"));
  context.after(() => rm(root, { recursive: true, force: true }));

  process.env.NODE_ENV = "development";
  process.env.ELMOS_LOCAL_RUNNER_ENABLED = "true";
  process.env.ELMOS_LOCAL_RUNNER_ROOT = root;
  process.env.ELMOS_REPOSITORY_ROOT = path.resolve(import.meta.dirname, "../../..");
  process.env.ELMOS_UV_PATH = process.execPath;
  process.env.ELMOS_LOCAL_RUNNER_EXECUTOR = "HOST_DEVELOPMENT";
  process.env.ELMOS_CONTROL_PLANE_BASE_URL = controlPlaneBaseUrl;
  process.env.ELMOS_GENERATION_ARTIFACT_DOWNLOAD_ALLOWED_HOSTS = "artifacts.test";
  return root;
}

async function storeReview(root, { expired = false, consumed = false } = {}) {
  const analysisDigest = sha256Json(synthesisRequest);
  const review = {
    tenantId: TENANT,
    actor: ACTOR,
    createdAt: new Date(Date.now() - 60_000).toISOString(),
    expiresAt: new Date(expired ? Date.now() - 1_000 : Date.now() + 30 * 60_000).toISOString(),
    intent: intentShape(),
    requestDigest: analysisDigest,
    request: synthesisRequest,
  };
  const reviewDir = path.join(
    root, "tenants", TENANT, consumed ? "analysis-reviews-consumed" : "analysis-reviews",
  );
  await mkdir(reviewDir, { recursive: true, mode: 0o700 });
  const file = path.join(
    reviewDir,
    `${createHash("sha256").update(ACTOR).digest("hex")}-${analysisDigest}.json`,
  );
  const { writeFile } = await import("node:fs/promises");
  await writeFile(file, JSON.stringify(review), { encoding: "utf-8", mode: 0o600 });
  return { file, analysisDigest, review };
}

const savedFetch = globalThis.fetch;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function controlPlaneJob(overrides = {}) {
  return {
    jobId: "job-hosted-1",
    organizationId: TENANT,
    actorId: ACTOR,
    status: "SUCCEEDED",
    stage: "complete",
    progress: 100,
    resultStatus: "PASSED",
    createdAt: "2026-09-07T00:00:00.000Z",
    startedAt: "2026-09-07T00:01:00.000Z",
    finishedAt: "2026-09-07T00:10:00.000Z",
    cancelRequested: false,
    artifacts: [{
      role: "PROJECT_ARCHIVE",
      filename: "generated-project.zip",
      contentSha256: "a".repeat(64),
      byteSize: 2048,
    }],
    ...overrides,
  };
}

test("hosted create rejects before touching the control plane without approval", async (context) => {
  await sandbox(context);
  let fetched = false;
  globalThis.fetch = async () => {
    fetched = true;
    throw new Error("must not be called");
  };
  const authorized = { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN };
  await assert.rejects(
    createHostedGenerationJob(authorized, { ...createRequest("b".repeat(64)), approved: false }),
    { message: "APPROVED_ANALYSIS_REQUIRED" },
  );
  await assert.rejects(
    createHostedGenerationJob(authorized, { ...createRequest("not-a-digest"), approved: true }),
    { message: "APPROVED_ANALYSIS_REQUIRED" },
  );
  assert.equal(fetched, false);
});

test("hosted create ships the synthesis request and consumes the analysis once", async (context) => {
  const root = await sandbox(context);
  const { file, analysisDigest } = await storeReview(root);

  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), method: init?.method, body: init?.body });
    if (String(url).endsWith("/api/v1/execution/jobs") && init?.method === "POST") {
      return jsonResponse({ jobId: "job-hosted-1", status: "QUEUED" }, 202);
    }
    return jsonResponse(controlPlaneJob({ status: "QUEUED", stage: "queued", progress: 0, artifacts: undefined }));
  };

  const job = await createHostedGenerationJob(
    { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN },
    createRequest(analysisDigest),
  );

  assert.equal(job.status, "QUEUED");
  assert.equal(job.stage, "queued");
  const enqueue = JSON.parse(calls.find((call) => call.method === "POST").body);
  assert.equal(enqueue.businessLine, "GENERATION");
  assert.equal(enqueue.jobKind, "project-synthesis");
  assert.equal(enqueue.payload.actor, ACTOR);
  assert.equal(enqueue.payload.tenantId, TENANT);
  assert.deepEqual(enqueue.payload.synthesisRequest, synthesisRequest);
  assert.equal(enqueue.payload.intent.approval_context.analysis_digest, analysisDigest);
  assert.equal(enqueue.payload.intent.languages[0], "python");

  // The review funds exactly one hosted job and its consumption is recorded.
  const { access } = await import("node:fs/promises");
  await assert.rejects(access(file), { code: "ENOENT" });
  const consumedDir = path.join(root, "tenants", TENANT, "analysis-reviews-consumed");
  const consumed = await readdir(consumedDir);
  assert.ok(consumed.includes(`${createHash("sha256").update(ACTOR).digest("hex")}-${analysisDigest}.json`));
  const consumptionLog = await readFile(path.join(consumedDir, "hosted-consumption.log"), "utf-8");
  assert.ok(consumptionLog.includes("job-hosted-1"));
  assert.ok(consumptionLog.includes(analysisDigest));
});

test("hosted create keeps the analysis when the control plane fail-closes", async (context) => {
  const root = await sandbox(context);
  const { file, analysisDigest } = await storeReview(root);

  globalThis.fetch = async () => jsonResponse(
    { status: "CONFIGURATION_REQUIRED", code: "ELMOS_RUNNER_IMAGE_NOT_CONFIGURED" }, 503,
  );
  await assert.rejects(
    createHostedGenerationJob(
      { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN },
      createRequest(analysisDigest),
    ),
    { message: "ELMOS_RUNNER_IMAGE_NOT_CONFIGURED" },
  );
  // Not consumed: a retry after the configuration gap is closed must succeed
  // with the same idempotency key instead of demanding a new analysis.
  assert.equal(await readFile(file, "utf-8").then(() => true, () => false), true);
});

test("hosted create fails closed on an expired or already consumed analysis", async (context) => {
  const root = await sandbox(context);
  const expired = await storeReview(root, { expired: true });
  globalThis.fetch = async () => jsonResponse({ jobId: "job-x" }, 202);
  await assert.rejects(
    createHostedGenerationJob(
      { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN },
      createRequest(expired.analysisDigest),
    ),
    { message: "ANALYSIS_REVIEW_EXPIRED" },
  );
  // Both fixtures derive from the same synthesis request, so remove the
  // expired copy before staging the consumed one.
  await rm(expired.file);

  const consumed = await storeReview(root, { consumed: true });
  await assert.rejects(
    createHostedGenerationJob(
      { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN },
      createRequest(consumed.analysisDigest),
    ),
    { message: "ANALYSIS_REVIEW_NOT_FOUND" },
  );
});

test("hosted create requires the access token for control-plane calls", async (context) => {
  const root = await sandbox(context);
  const { analysisDigest } = await storeReview(root);
  globalThis.fetch = async () => jsonResponse({ jobId: "job-x" }, 202);
  await assert.rejects(
    createHostedGenerationJob({ tenantId: TENANT, actor: ACTOR }, createRequest(analysisDigest)),
    { message: "ACCOUNT_ACCESS_TOKEN_REQUIRED" },
  );
});

test("hosted job view maps control-plane states onto generation states", async (context) => {
  await sandbox(context);
  const cases = [
    [{ status: "QUEUED", stage: "queued", progress: 0 }, "QUEUED", "queued"],
    [{ status: "CLAIMED", stage: "pipeline", progress: 10 }, "GENERATING", "pipeline"],
    [{ status: "RUNNING", stage: "generating", progress: 40 }, "GENERATING", "pipeline"],
    [{ status: "SUCCEEDED" }, "COMPLETED", "complete"],
    [{ status: "PARTIAL" }, "PARTIAL", "complete"],
    [{ status: "CANCELLED" }, "CANCELLED", "cancelled"],
    [{ status: "FAILED", failureCode: "WORKLOAD_EXIT_1", artifacts: undefined }, "BLOCKED", "blocked"],
    [{ status: "LOST", failureCode: "LEASE_LOST", artifacts: undefined }, "BLOCKED", "blocked"],
  ];
  for (const [overrides, expectedStatus, expectedStage] of cases) {
    globalThis.fetch = async () => jsonResponse(controlPlaneJob(overrides));
    const job = await getHostedGenerationJob(
      { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN }, "job-hosted-1",
    );
    assert.equal(job.status, expectedStatus, JSON.stringify(overrides));
    assert.equal(job.stage, expectedStage, JSON.stringify(overrides));
    if (expectedStatus === "BLOCKED") assert.equal(job.reason, overrides.failureCode);
  }
});

test("hosted job view exposes the archive identity from the artifact list", async (context) => {
  await sandbox(context);
  globalThis.fetch = async () => jsonResponse(controlPlaneJob());
  const job = await getHostedGenerationJob(
    { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN }, "job-hosted-1",
  );
  assert.equal(job.artifactReady, true);
  assert.equal(job.artifactSha256, "a".repeat(64));
  assert.equal(job.artifactSize, 2048);
  assert.deepEqual(job.artifacts, [{
    path: "generated-project.zip",
    sha256: "a".repeat(64),
    ownership: "managed",
  }]);
});

test("hosted cancel issues the control-plane delete", async (context) => {
  await sandbox(context);
  const methods = [];
  globalThis.fetch = async (url, init) => {
    methods.push({ url: String(url), method: init?.method });
    return jsonResponse(init?.method === "DELETE"
      ? { status: "CANCEL_REQUESTED" }
      : controlPlaneJob({ status: "CANCELLED", stage: "cancelled", artifacts: undefined }));
  };
  const job = await cancelHostedGenerationJob(
    { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN }, "job-hosted-1",
  );
  assert.equal(job.status, "CANCELLED");
  assert.deepEqual(methods.map((call) => call.method), ["DELETE", "GET"]);
  assert.ok(methods[0].url.endsWith("/api/v1/execution/jobs/job-hosted-1"));
});

test("hosted artifact tickets fail closed on policy violations", async (context) => {
  await sandbox(context);
  const authorized = { tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN };
  const ticketBody = (overrides = {}) => ({
    downloadUrl: "https://artifacts.test/download/generated-project.zip",
    filename: "generated-project.zip",
    contentSha256: "a".repeat(64),
    byteSize: 2048,
    expiresInSeconds: 300,
    ...overrides,
  });

  const serve = (jobOverrides, ticketOverrides) => {
    globalThis.fetch = async (url, init) => {
      if (init?.method === "POST") return jsonResponse(ticketBody(ticketOverrides));
      return jsonResponse(controlPlaneJob(jobOverrides));
    };
  };

  serve({ artifacts: undefined });
  await assert.rejects(
    hostedArtifactTicket(authorized, "job-hosted-1"),
    { message: "ARTIFACT_NOT_READY" },
  );

  serve({}, {});
  const ticket = await hostedArtifactTicket(authorized, "job-hosted-1");
  assert.equal(ticket.filename, "generated-project.zip");
  assert.equal(ticket.contentSha256, "a".repeat(64));

  serve({}, { downloadUrl: "https://evil.test/download" });
  await assert.rejects(
    hostedArtifactTicket(authorized, "job-hosted-1"),
    { message: "HOSTED_ARTIFACT_TICKET_URL_NOT_ALLOWED" },
  );

  serve({}, { expiresInSeconds: 601 });
  await assert.rejects(
    hostedArtifactTicket(authorized, "job-hosted-1"),
    { message: "HOSTED_ARTIFACT_TICKET_INVALID" },
  );

  serve({}, { byteSize: 2049 });
  await assert.rejects(
    hostedArtifactTicket(authorized, "job-hosted-1"),
    { message: "HOSTED_ARTIFACT_TICKET_IDENTITY_MISMATCH" },
  );

  serve({}, { contentSha256: "0".repeat(64) });
  await assert.rejects(
    hostedArtifactTicket(authorized, "job-hosted-1"),
    { message: "HOSTED_ARTIFACT_TICKET_IDENTITY_MISMATCH" },
  );

  serve({}, { filename: "../escape.zip" });
  await assert.rejects(
    hostedArtifactTicket(authorized, "job-hosted-1"),
    { message: "HOSTED_ARTIFACT_TICKET_INVALID" },
  );
});

test("hosted control-plane errors surface their server code", async (context) => {
  await sandbox(context);
  globalThis.fetch = async () => jsonResponse({ code: "ELMOS_JOB_NOT_FOUND" }, 404);
  await assert.rejects(
    getHostedGenerationJob({ tenantId: TENANT, actor: ACTOR, accessToken: ACCESS_TOKEN }, "missing"),
    { message: "ELMOS_JOB_NOT_FOUND" },
  );
});

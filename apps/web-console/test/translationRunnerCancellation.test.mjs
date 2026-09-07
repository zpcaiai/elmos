import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmod,
  mkdtemp,
  mkdir,
  readFile,
  realpath,
  rename,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test, { after } from "node:test";
import { zipSync } from "fflate";

import { DurableJobLease } from "../app/lib/server/durableJobLease.ts";
import {
  readBoundedTranslationRequest,
  rejectDuplicateTopLevelJsonFields,
} from "../app/lib/server/translationRequestBody.ts";
import {
  MAX_TRANSLATION_ARTIFACT_BYTES,
  cancelTranslationJob,
  createTranslationJob,
  getTranslationJob,
  translationCasesBase,
  translationArtifact,
  translationRunnerHealth,
} from "../app/lib/server/translationRunner.ts";
import {
  createTranslationRouteAdmissionFixture,
  TEST_ROUTE_JOB_ADMISSION,
} from "./translationRouteAdmissionFixture.mjs";

const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
const admittedRepository = await createTranslationRouteAdmissionFixture(repositoryRoot);
const admittedRepositoryRoot = admittedRepository.root;
after(async () => admittedRepository.cleanup());

test("route admission fixture rejects duplicate fields and path identities before writes", async () => {
  const fakeRepository = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-route-admission-negative-")),
  );
  const inventoryPath = path.join(fakeRepository, "routes", "inventory.json");
  try {
    await mkdir(path.dirname(inventoryPath), { recursive: true });
    await writeFile(inventoryPath, '{"routes":[],"routes":[]}\n');
    await assert.rejects(
      createTranslationRouteAdmissionFixture(fakeRepository),
      (error) => error?.message === "DUPLICATE_JSON_FIELD",
    );

    const inventory = JSON.parse(
      await readFile(path.join(repositoryRoot, "routes", "inventory.json"), "utf8"),
    );
    inventory.routes[0].route_key = "../escape";
    await writeFile(inventoryPath, `${JSON.stringify(inventory)}\n`);
    await assert.rejects(
      createTranslationRouteAdmissionFixture(fakeRepository),
      (error) => error?.message === "TEST_ROUTE_INVENTORY_IDENTITY_INVALID:../escape",
    );
    await assert.rejects(
      readFile(path.join(fakeRepository, "escape", "route.json")),
      (error) => error?.code === "ENOENT",
    );
  } finally {
    await rm(fakeRepository, { recursive: true, force: true });
  }
});

function codeArtifactFixture({ tamperPayloadDigest = false } = {}) {
  const payload = Buffer.from("export function migrated(value) { return value + 1; }\n");
  const summary = {
    definitionId: "verified-functional-obligation-success-rate/v1",
    numerator: 1,
    denominator: 1,
    successRateBasisPoints: 10_000,
    measurementStatus: "MEASURED",
    denominatorComplete: true,
    projectSuccessRateDisplay: "100.00%",
    codeArtifactReady: true,
    casesManifestSha256: "c".repeat(64),
  };
  const manifest = Buffer.from(`${JSON.stringify({
    schema_version: "1.0.0",
    kind: "elmos.repository-migration-artifact-manifest",
    status: "COMPLETE",
    repository_ref: "workspace@artifact-snapshot",
    snapshot_sha256: "b".repeat(64),
    route_id: "python-to-typescript",
    profile: "typed-pure-function-v1",
    functional_conversion: {
      definition_id: summary.definitionId,
      numerator: summary.numerator,
      denominator: summary.denominator,
      success_rate_basis_points: summary.successRateBasisPoints,
      measurement_status: summary.measurementStatus,
      denominator_complete: summary.denominatorComplete,
      project_success_rate_display: summary.projectSuccessRateDisplay,
      code_artifact_ready: true,
      cases_manifest_sha256: summary.casesManifestSha256,
    },
    files: [{
      path: "converted.ts",
      bytes: payload.byteLength,
      sha256: tamperPayloadDigest
        ? "d".repeat(64)
        : createHash("sha256").update(payload).digest("hex"),
    }],
    external_verification_status: "NOT_RUN",
    certification_status: "NOT_CERTIFIED",
  })}\n`);
  return {
    archive: Buffer.from(zipSync({
      "artifact-manifest.json": manifest,
      "converted.ts": payload,
    }, { level: 9 })),
    summary,
  };
}

async function waitUntil(operation, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await operation();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw lastError ?? new Error("TEST_WAIT_TIMEOUT");
}

const rootlessFixtureReadinessTimeoutMs = 30_000;

async function createFakeContainerEngine(binRoot) {
  const executable = path.join(binRoot, "docker");
  await mkdir(binRoot, { recursive: true });
  const source = [
    "#!/usr/bin/env node",
    "import { createHash } from 'node:crypto';",
    "import { appendFile, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';",
    "import path from 'node:path';",
    "const args = process.argv.slice(2);",
    "const state = process.env.FAKE_TRANSLATION_ENGINE_STATE;",
    "const containers = path.join(state, 'containers');",
    "await mkdir(containers, { recursive: true });",
    "await appendFile(path.join(state, 'operations.log'), JSON.stringify(args) + '\\n');",
    "const option = (name) => { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : undefined; };",
    "const command = args[0];",
    "if (command === 'run') {",
    "  const name = option('--name');",
    "  const cidFile = option('--cidfile');",
    "  const labels = {};",
    "  for (let index = 0; index < args.length; index += 1) {",
    "    if (args[index] !== '--label') continue;",
    "    const [key, ...value] = String(args[index + 1]).split('=');",
    "    labels[key] = value.join('=');",
    "  }",
    "  const id = createHash('sha256').update(name).digest('hex');",
    "  await mkdir(path.dirname(cidFile), { recursive: true });",
    "  await writeFile(cidFile, id + '\\n');",
    "  await writeFile(path.join(containers, name + '.json'), JSON.stringify({ Id: id, Name: '/' + name, Config: { Labels: labels } }));",
    "  process.on('SIGTERM', () => process.exit(143));",
    "  process.on('SIGINT', () => process.exit(130));",
    "  await writeFile(path.join(state, 'active.json'), JSON.stringify({ name, id, cidFile, labels }));",
    "  setInterval(() => undefined, 60_000);",
    "} else if (command === 'inspect') {",
    "  const name = args.at(-1);",
    "  try { process.stdout.write(await readFile(path.join(containers, name + '.json'), 'utf8')); }",
    "  catch { process.exitCode = 1; }",
    "} else if (command === 'ps') {",
    "  const entries = (await readdir(containers)).filter((entry) => entry.endsWith('.json'));",
    "  for (const entry of entries) {",
    "    const document = JSON.parse(await readFile(path.join(containers, entry), 'utf8'));",
    "    process.stdout.write(String(document.Id) + '\\n');",
    "  }",
    "} else if (command === 'stop' || command === 'kill') {",
    "  process.exitCode = 0;",
    "} else if (command === 'rm') {",
    "  const name = args.at(-1);",
    "  if (process.env.FAKE_TRANSLATION_ENGINE_REFUSE_REMOVE !== 'true') await rm(path.join(containers, name + '.json'), { force: true });",
    "} else {",
    "  process.exitCode = 2;",
    "}",
    "",
  ].join("\n");
  await writeFile(executable, source, { mode: 0o700 });
  await chmod(executable, 0o700);
  return executable;
}

async function waitForWorkerClose(worker, timeoutMs) {
  if (worker.exitCode !== null || worker.signalCode !== null) return true;
  return new Promise((resolve) => {
    const onClose = () => {
      clearTimeout(timer);
      resolve(true);
    };
    const timer = setTimeout(() => {
      worker.off("close", onClose);
      resolve(false);
    }, timeoutMs);
    worker.once("close", onClose);
  });
}

async function stopWorker(worker) {
  if (worker.exitCode !== null || worker.signalCode !== null) return;
  worker.kill("SIGTERM");
  if (await waitForWorkerClose(worker, 2_000)) return;
  worker.kill("SIGKILL");
  await waitForWorkerClose(worker, 2_000);
}

async function stopFixtureRuntime(jobPath) {
  let processGroupId;
  try {
    const job = JSON.parse(await readFile(jobPath, "utf8"));
    processGroupId = job.runtimeReceipt?.processGroupId;
  } catch {
    return;
  }
  if (!Number.isSafeInteger(processGroupId) || processGroupId <= 1 || processGroupId === process.pid) {
    return;
  }
  try {
    process.kill(-processGroupId, "SIGKILL");
  } catch (error) {
    if (error?.code !== "ESRCH") throw error;
  }
  await waitUntil(() => {
    try {
      process.kill(-processGroupId, 0);
      return undefined;
    } catch (error) {
      if (error?.code === "ESRCH") return true;
      throw error;
    }
  }, 2_000).catch(() => undefined);
}

async function rootlessTwoInstanceFixture({ refuseRemove = false } = {}) {
  const sandbox = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-two-instance-")),
  );
  const runnerRoot = path.join(sandbox, "runner");
  const sourceRoot = path.join(sandbox, "sources");
  const casesRoot = path.join(sandbox, "cases");
  const engineState = path.join(sandbox, "engine-state");
  const workspaceId = "two-instance-source";
  const casesBundleId = "two-instance-cases";
  const tenantId = `tenant-two-instance-${refuseRemove ? "blocked" : "success"}`;
  const jobIdFile = path.join(sandbox, "job-id.txt");
  const engine = await createFakeContainerEngine(path.join(sandbox, "bin"));
  await Promise.all([
    mkdir(path.join(sourceRoot, workspaceId), { recursive: true }),
    mkdir(path.join(casesRoot, casesBundleId), { recursive: true }),
    mkdir(engineState, { recursive: true }),
  ]);
  const environment = {
    ...process.env,
    NODE_ENV: "development",
    ELMOS_LOCAL_RUNNER_ENABLED: "true",
    ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
    ELMOS_REPOSITORY_ROOT: admittedRepositoryRoot,
    ELMOS_TRANSLATION_SOURCE_ROOT: sourceRoot,
    ELMOS_TRANSLATION_CASES_ROOT: casesRoot,
    ELMOS_UV_PATH: process.execPath,
    ELMOS_LOCAL_RUNNER_EXECUTOR: "ROOTLESS_CONTAINER",
    ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE: engine,
    ELMOS_TRANSLATION_RUNNER_IMAGE: `example.invalid/elmos-translation@sha256:${"1".repeat(64)}`,
    ELMOS_TEST_TENANT_ID: tenantId,
    ELMOS_TEST_WORKSPACE_ID: workspaceId,
    ELMOS_TEST_CASES_BUNDLE_ID: casesBundleId,
    ELMOS_TEST_JOB_ID_FILE: jobIdFile,
    FAKE_TRANSLATION_ENGINE_STATE: engineState,
    FAKE_TRANSLATION_ENGINE_REFUSE_REMOVE: refuseRemove ? "true" : "false",
  };
  let stderr = "";
  const worker = spawn(process.execPath, [
    "--loader",
    path.join(import.meta.dirname, "ts-extension-loader.mjs"),
    path.join(import.meta.dirname, "translationCancellationWorker.mjs"),
  ], {
    cwd: path.dirname(import.meta.dirname),
    env: environment,
    stdio: ["ignore", "ignore", "pipe"],
  });
  worker.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
  let jobPath;
  try {
    const jobId = await waitUntil(async () => {
      if (worker.exitCode !== null) throw new Error(`worker exited ${worker.exitCode}: ${stderr}`);
      const candidate = (await readFile(jobIdFile, "utf8")).trim();
      return candidate || undefined;
    }, rootlessFixtureReadinessTimeoutMs);
    jobPath = path.join(
      runnerRoot,
      "tenants",
      tenantId,
      "translation-jobs",
      jobId,
      "job.json",
    );
    const running = await waitUntil(async () => {
      if (worker.exitCode !== null) throw new Error(`worker exited ${worker.exitCode}: ${stderr}`);
      const candidate = JSON.parse(await readFile(jobPath, "utf8"));
      return candidate.runtimeReceipt?.state === "RUNNING" ? candidate : undefined;
    }, rootlessFixtureReadinessTimeoutMs);
    await waitUntil(async () => {
      if (worker.exitCode !== null) throw new Error(`worker exited ${worker.exitCode}: ${stderr}`);
      return readFile(path.join(engineState, "active.json"), "utf8");
    }, rootlessFixtureReadinessTimeoutMs);
    return {
      sandbox,
      runnerRoot,
      sourceRoot,
      casesRoot,
      engineState,
      engine,
      tenantId,
      jobId,
      jobPath,
      running,
      worker,
      environment,
    };
  } catch (error) {
    await stopWorker(worker);
    if (jobPath) await stopFixtureRuntime(jobPath);
    await rm(sandbox, { recursive: true, force: true });
    throw error;
  }
}

const rootlessEnvironmentNames = [
  "NODE_ENV",
  "ELMOS_LOCAL_RUNNER_ENABLED",
  "ELMOS_LOCAL_RUNNER_ROOT",
  "ELMOS_REPOSITORY_ROOT",
  "ELMOS_TRANSLATION_SOURCE_ROOT",
  "ELMOS_TRANSLATION_CASES_ROOT",
  "ELMOS_UV_PATH",
  "ELMOS_LOCAL_RUNNER_EXECUTOR",
  "ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE",
  "ELMOS_TRANSLATION_RUNNER_IMAGE",
  "FAKE_TRANSLATION_ENGINE_STATE",
  "FAKE_TRANSLATION_ENGINE_REFUSE_REMOVE",
];

function installRootlessEnvironment(environment) {
  const previous = Object.fromEntries(
    rootlessEnvironmentNames.map((name) => [name, process.env[name]]),
  );
  for (const name of rootlessEnvironmentNames) process.env[name] = environment[name];
  return () => {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  };
}

test("cancellation during lease acquisition cannot be overwritten by the stale execution generation", async () => {
  const sandbox = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-cancel-race-")),
  );
  const runnerRoot = path.join(sandbox, "runner");
  const sourceRoot = path.join(sandbox, "sources");
  const casesRoot = path.join(sandbox, "cases");
  const workspaceId = "cancel-source";
  const casesBundleId = "cancel-cases";
  const environment = {
    ELMOS_LOCAL_RUNNER_ENABLED: process.env.ELMOS_LOCAL_RUNNER_ENABLED,
    ELMOS_LOCAL_RUNNER_ROOT: process.env.ELMOS_LOCAL_RUNNER_ROOT,
    ELMOS_REPOSITORY_ROOT: process.env.ELMOS_REPOSITORY_ROOT,
    ELMOS_TRANSLATION_SOURCE_ROOT: process.env.ELMOS_TRANSLATION_SOURCE_ROOT,
    ELMOS_TRANSLATION_CASES_ROOT: process.env.ELMOS_TRANSLATION_CASES_ROOT,
    ELMOS_UV_PATH: process.env.ELMOS_UV_PATH,
    ELMOS_LOCAL_RUNNER_EXECUTOR: process.env.ELMOS_LOCAL_RUNNER_EXECUTOR,
    NODE_ENV: process.env.NODE_ENV,
  };
  const originalAcquire = DurableJobLease.acquire;
  let acquisitionEntered;
  const entered = new Promise((resolve) => {
    acquisitionEntered = resolve;
  });
  let resumeAcquisition;
  const acquisitionPaused = new Promise((resolve) => {
    resumeAcquisition = resolve;
  });
  let releasedOutcome;

  try {
    await Promise.all([
      mkdir(path.join(sourceRoot, workspaceId), { recursive: true }),
      mkdir(path.join(casesRoot, casesBundleId), { recursive: true }),
    ]);
    Object.assign(process.env, {
      ELMOS_LOCAL_RUNNER_ENABLED: "true",
      ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
      ELMOS_REPOSITORY_ROOT: admittedRepositoryRoot,
      ELMOS_TRANSLATION_SOURCE_ROOT: sourceRoot,
      ELMOS_TRANSLATION_CASES_ROOT: casesRoot,
      ELMOS_UV_PATH: process.execPath,
      ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
    });
    DurableJobLease.acquire = async () => {
      acquisitionEntered();
      await acquisitionPaused;
      return {
        heartbeatIntervalMs: 60_000,
        heartbeat: async () => undefined,
        release: async (outcome) => {
          releasedOutcome = outcome;
        },
      };
    };

    const context = { tenantId: "tenant-cancel-race", actor: "user:cancel-race" };
    const job = await createTranslationJob(context, {
      workspaceId,
      casesBundleId,
      sourceLanguage: "python",
      targetLanguage: "typescript",
    });
    await entered;
    const cancelled = await cancelTranslationJob(context, job.id);
    assert.equal(cancelled.status, "CANCELLED");
    resumeAcquisition();

    await assert.doesNotReject(async () => {
      for (let attempt = 0; attempt < 100 && releasedOutcome === undefined; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
      assert.equal(releasedOutcome, "CANCELLED");
    });
    const durable = await getTranslationJob(context, job.id);
    assert.equal(durable.status, "CANCELLED");
    assert.equal(durable.stage, "cancelled");
    assert.equal(durable.reportReady, false);
    assert.equal(durable.artifactReady, false);
    const stored = JSON.parse(await readFile(path.join(
      runnerRoot,
      "tenants",
      context.tenantId,
      "translation-jobs",
      job.id,
      "job.json",
    ), "utf8"));
    assert.equal(stored.status, "CANCELLED");
    assert.equal(stored.stage, "cancelled");
  } finally {
    DurableJobLease.acquire = originalAcquire;
    for (const [name, value] of Object.entries(environment)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    resumeAcquisition?.();
    await rm(sandbox, { recursive: true, force: true });
  }
});

test("a second instance observes the durable lease and verifies exact rootless cleanup before cancellation", async () => {
  const fixture = await rootlessTwoInstanceFixture();
  const restore = installRootlessEnvironment(fixture.environment);
  const context = { tenantId: fixture.tenantId, actor: "user:second-instance" };
  try {
    const observed = await getTranslationJob(context, fixture.jobId);
    assert.equal(observed.recoveryAttempts, 0);
    assert.notEqual(observed.stage, "restart-recovery");
    assert.equal(observed.executionId, fixture.running.executionId);

    const cancelled = await cancelTranslationJob(context, fixture.jobId);
    assert.equal(cancelled.status, "CANCELLED");
    assert.equal(cancelled.reason, "CANCELLED_BY_AUTHORIZED_ACTOR");
    assert.equal(cancelled.cancelRequestedBy, context.actor);
    assert.ok(Number.isFinite(Date.parse(cancelled.cancelRequestedAt)));
    assert.match(cancelled.executionId, /^[0-9a-f-]{36}$/);
    assert.equal(cancelled.runtimeReceipt.state, "CLEANUP_VERIFIED");
    assert.equal(cancelled.runtimeReceipt.executionId, cancelled.executionId);
    assert.equal(cancelled.runtimeReceipt.labels.jobId, fixture.jobId);
    assert.equal(cancelled.runtimeReceipt.labels.executionId, cancelled.executionId);
    assert.equal(cancelled.runtimeReceipt.labels.phase, "preflight");
    assert.equal(
      cancelled.runtimeReceipt.containerName,
      `elmos-tr-${fixture.jobId}-${cancelled.executionId.replaceAll("-", "")}-preflight`,
    );
    assert.match(cancelled.runtimeReceipt.containerId, /^[0-9a-f]{64}$/);
    assert.ok(Number.isFinite(Date.parse(cancelled.runtimeReceipt.cleanupVerifiedAt)));
    await assert.rejects(readFile(path.join(
      fixture.runnerRoot,
      "tenants",
      fixture.tenantId,
      "translation-jobs",
      fixture.jobId,
      ...cancelled.runtimeReceipt.cidFile.split("/"),
    )));

    const operations = (await readFile(
      path.join(fixture.engineState, "operations.log"),
      "utf8",
    )).trim().split("\n").map((line) => JSON.parse(line));
    const run = operations.find((operation) => operation[0] === "run");
    assert.deepEqual(
      run.slice(run.indexOf("--name"), run.indexOf("--name") + 2),
      ["--name", cancelled.runtimeReceipt.containerName],
    );
    assert.ok(run.includes(`io.elmos.translation.job-id=${fixture.jobId}`));
    assert.ok(run.includes(`io.elmos.translation.execution-id=${cancelled.executionId}`));
    assert.ok(run.includes("io.elmos.translation.phase=preflight"));
    assert.ok(operations.some((operation) => operation[0] === "inspect"));
    assert.ok(operations.some((operation) => operation[0] === "stop"));
    assert.ok(operations.some((operation) => operation[0] === "rm"));
    assert.ok(operations.some((operation) => operation[0] === "ps"));

    const stored = await waitUntil(async () => {
      const candidate = JSON.parse(await readFile(fixture.jobPath, "utf8"));
      return candidate.status === "CANCELLED" ? candidate : undefined;
    });
    assert.equal(stored.executionId, cancelled.executionId);
    await new Promise((resolve) => setTimeout(resolve, 250));
    assert.equal(JSON.parse(await readFile(fixture.jobPath, "utf8")).status, "CANCELLED");
    const tenantDigest = createHash("sha256").update(fixture.tenantId).digest("hex");
    const releaseReceipt = await waitUntil(async () => JSON.parse(await readFile(path.join(
      fixture.runnerRoot,
      ".durable-queue",
      "receipts",
      "translation",
      tenantDigest,
      `${fixture.jobId}.json`,
    ), "utf8")));
    assert.equal(releaseReceipt.outcome, "CANCELLED");
  } finally {
    restore();
    await stopWorker(fixture.worker);
    await stopFixtureRuntime(fixture.jobPath);
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test("unverified rootless removal blocks cancellation and a later exact cleanup retry reconciles it", async () => {
  const fixture = await rootlessTwoInstanceFixture({ refuseRemove: true });
  const restore = installRootlessEnvironment(fixture.environment);
  const context = { tenantId: fixture.tenantId, actor: "user:cleanup-retry" };
  try {
    const blocked = await cancelTranslationJob(context, fixture.jobId);
    assert.equal(blocked.status, "BLOCKED");
    assert.equal(blocked.stage, "blocked");
    assert.equal(blocked.reason, "CANCEL_CLEANUP_UNVERIFIED");
    assert.equal(blocked.runtimeReceipt.state, "CLEANUP_UNVERIFIED");
    assert.equal(blocked.reportReady, false);
    assert.equal(blocked.artifactReady, false);

    process.env.FAKE_TRANSLATION_ENGINE_REFUSE_REMOVE = "false";
    const reconciled = await cancelTranslationJob(context, fixture.jobId);
    assert.equal(reconciled.status, "CANCELLED");
    assert.equal(reconciled.runtimeReceipt.state, "CLEANUP_VERIFIED");
    assert.equal(reconciled.reason, "CANCELLED_BY_AUTHORIZED_ACTOR");
    await new Promise((resolve) => setTimeout(resolve, 250));
    assert.equal(JSON.parse(await readFile(fixture.jobPath, "utf8")).status, "CANCELLED");
  } finally {
    restore();
    await stopWorker(fixture.worker);
    await stopFixtureRuntime(fixture.jobPath);
    await rm(fixture.sandbox, { recursive: true, force: true });
  }
});

test("production rejects global workspace IDs and binds case bundles to the authenticated tenant", async () => {
  const previousNodeEnvironment = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  try {
    await assert.rejects(
      createTranslationJob(
        { tenantId: "tenant-isolation-a", actor: "user:isolation" },
        {
          workspaceId: "guessed-global-workspace",
          casesBundleId: "guessed-global-cases",
          sourceLanguage: "python",
          targetLanguage: "typescript",
        },
      ),
      (error) => error?.message === "TRANSLATION_DIRECT_WORKSPACE_FORBIDDEN",
    );
    const runner = { casesRoot: "/srv/elmos/translation-cases" };
    assert.equal(
      translationCasesBase(runner, { tenantId: "tenant-isolation-a" }),
      "/srv/elmos/translation-cases/tenant-isolation-a",
    );
    assert.equal(
      translationCasesBase(runner, { tenantId: "tenant-isolation-b" }),
      "/srv/elmos/translation-cases/tenant-isolation-b",
    );
    assert.notEqual(
      translationCasesBase(runner, { tenantId: "tenant-isolation-a" }),
      translationCasesBase(runner, { tenantId: "tenant-isolation-b" }),
    );
  } finally {
    if (previousNodeEnvironment === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = previousNodeEnvironment;
  }
});

test("canonical storage checks reject an overlap hidden behind an ancestor symlink", async () => {
  const sandbox = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-path-alias-")),
  );
  const runnerRoot = path.join(sandbox, "runner");
  const casesRoot = path.join(sandbox, "cases");
  const aliasParent = path.join(sandbox, "alias-parent");
  const environment = {
    ELMOS_LOCAL_RUNNER_ENABLED: process.env.ELMOS_LOCAL_RUNNER_ENABLED,
    ELMOS_LOCAL_RUNNER_ROOT: process.env.ELMOS_LOCAL_RUNNER_ROOT,
    ELMOS_REPOSITORY_ROOT: process.env.ELMOS_REPOSITORY_ROOT,
    ELMOS_TRANSLATION_SOURCE_ROOT: process.env.ELMOS_TRANSLATION_SOURCE_ROOT,
    ELMOS_TRANSLATION_CASES_ROOT: process.env.ELMOS_TRANSLATION_CASES_ROOT,
    ELMOS_UV_PATH: process.env.ELMOS_UV_PATH,
    ELMOS_LOCAL_RUNNER_EXECUTOR: process.env.ELMOS_LOCAL_RUNNER_EXECUTOR,
  };
  try {
    await mkdir(casesRoot, { recursive: true });
    await symlink(path.dirname(repositoryRoot), aliasParent, "dir");
    Object.assign(process.env, {
      ELMOS_LOCAL_RUNNER_ENABLED: "true",
      ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
      ELMOS_REPOSITORY_ROOT: repositoryRoot,
      ELMOS_TRANSLATION_SOURCE_ROOT: path.join(aliasParent, path.basename(repositoryRoot)),
      ELMOS_TRANSLATION_CASES_ROOT: casesRoot,
      ELMOS_UV_PATH: process.execPath,
      ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
    });

    const health = await translationRunnerHealth();
    assert.equal(health.status, "BLOCKED");
    assert.equal(health.reason, "TRANSLATION_RUNNER_ROOT_UNSAFE");
  } finally {
    for (const [name, value] of Object.entries(environment)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    await rm(sandbox, { recursive: true, force: true });
  }
});

test("persisted artifact descriptors above the 256 MiB commercial bound fail before file I/O", async () => {
  const sandbox = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-artifact-bound-")),
  );
  const runnerRoot = path.join(sandbox, "runner");
  const sourceRoot = path.join(sandbox, "sources");
  const casesRoot = path.join(sandbox, "cases");
  const context = { tenantId: "tenant-artifact-bound", actor: "user:artifact-bound" };
  const jobId = "11111111-1111-4111-8111-111111111111";
  const environment = {
    ELMOS_LOCAL_RUNNER_ENABLED: process.env.ELMOS_LOCAL_RUNNER_ENABLED,
    ELMOS_LOCAL_RUNNER_ROOT: process.env.ELMOS_LOCAL_RUNNER_ROOT,
    ELMOS_REPOSITORY_ROOT: process.env.ELMOS_REPOSITORY_ROOT,
    ELMOS_TRANSLATION_SOURCE_ROOT: process.env.ELMOS_TRANSLATION_SOURCE_ROOT,
    ELMOS_TRANSLATION_CASES_ROOT: process.env.ELMOS_TRANSLATION_CASES_ROOT,
    ELMOS_UV_PATH: process.env.ELMOS_UV_PATH,
    ELMOS_LOCAL_RUNNER_EXECUTOR: process.env.ELMOS_LOCAL_RUNNER_EXECUTOR,
  };
  try {
    await Promise.all([
      mkdir(sourceRoot, { recursive: true }),
      mkdir(casesRoot, { recursive: true }),
      mkdir(path.join(
        runnerRoot,
        "tenants",
        context.tenantId,
        "translation-jobs",
        jobId,
      ), { recursive: true }),
    ]);
    Object.assign(process.env, {
      ELMOS_LOCAL_RUNNER_ENABLED: "true",
      ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
      ELMOS_REPOSITORY_ROOT: admittedRepositoryRoot,
      ELMOS_TRANSLATION_SOURCE_ROOT: sourceRoot,
      ELMOS_TRANSLATION_CASES_ROOT: casesRoot,
      ELMOS_UV_PATH: process.execPath,
      ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
    });
    await writeFile(path.join(
      runnerRoot,
      "tenants",
      context.tenantId,
      "translation-jobs",
      jobId,
      "job.json",
    ), JSON.stringify({
      id: jobId,
      tenantId: context.tenantId,
      ...TEST_ROUTE_JOB_ADMISSION,
      artifactReady: true,
      artifactSha256: "a".repeat(64),
      artifactSize: MAX_TRANSLATION_ARTIFACT_BYTES + 1,
    }));
    await assert.rejects(
      translationArtifact(context, jobId),
      (error) => error?.message === "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
    );
  } finally {
    for (const [name, value] of Object.entries(environment)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    await rm(sandbox, { recursive: true, force: true });
  }
});

test("artifact download keeps the verified open file when the pathname is replaced", async () => {
  const sandbox = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-artifact-open-fd-")),
  );
  const runnerRoot = path.join(sandbox, "runner");
  const sourceRoot = path.join(sandbox, "sources");
  const casesRoot = path.join(sandbox, "cases");
  const context = { tenantId: "tenant-artifact-open-fd", actor: "user:artifact-open-fd" };
  const jobId = "22222222-2222-4222-8222-222222222222";
  const jobRoot = path.join(
    runnerRoot,
    "tenants",
    context.tenantId,
    "translation-jobs",
    jobId,
  );
  const pipeline = path.join(jobRoot, "pipeline");
  const archivePath = path.join(pipeline, "repository-migration-artifact.zip");
  const fixture = codeArtifactFixture();
  const original = fixture.archive;
  const replacement = Buffer.from("unverified replacement bytes");
  const environment = {
    ELMOS_LOCAL_RUNNER_ENABLED: process.env.ELMOS_LOCAL_RUNNER_ENABLED,
    ELMOS_LOCAL_RUNNER_ROOT: process.env.ELMOS_LOCAL_RUNNER_ROOT,
    ELMOS_REPOSITORY_ROOT: process.env.ELMOS_REPOSITORY_ROOT,
    ELMOS_TRANSLATION_SOURCE_ROOT: process.env.ELMOS_TRANSLATION_SOURCE_ROOT,
    ELMOS_TRANSLATION_CASES_ROOT: process.env.ELMOS_TRANSLATION_CASES_ROOT,
    ELMOS_UV_PATH: process.env.ELMOS_UV_PATH,
    ELMOS_LOCAL_RUNNER_EXECUTOR: process.env.ELMOS_LOCAL_RUNNER_EXECUTOR,
  };
  let artifact;
  try {
    await Promise.all([
      mkdir(sourceRoot, { recursive: true }),
      mkdir(casesRoot, { recursive: true }),
      mkdir(pipeline, { recursive: true }),
    ]);
    Object.assign(process.env, {
      ELMOS_LOCAL_RUNNER_ENABLED: "true",
      ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
      ELMOS_REPOSITORY_ROOT: admittedRepositoryRoot,
      ELMOS_TRANSLATION_SOURCE_ROOT: sourceRoot,
      ELMOS_TRANSLATION_CASES_ROOT: casesRoot,
      ELMOS_UV_PATH: process.execPath,
      ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
    });
    await writeFile(archivePath, original);
    const jobRecord = {
      id: jobId,
      tenantId: context.tenantId,
      ...TEST_ROUTE_JOB_ADMISSION,
      repositoryRef: "workspace@artifact-snapshot",
      status: "COMPLETE",
      artifactReady: true,
      artifactSha256: createHash("sha256").update(original).digest("hex"),
      artifactSize: original.byteLength,
      snapshotSha256: "b".repeat(64),
      conversionSummary: fixture.summary,
    };
    await writeFile(path.join(jobRoot, "job.json"), JSON.stringify(jobRecord));

    artifact = await translationArtifact(context, jobId);
    await rename(archivePath, `${archivePath}.replaced`);
    await writeFile(archivePath, replacement);
    const observed = Buffer.alloc(original.byteLength);
    const { bytesRead } = await artifact.handle.read(observed, 0, observed.length, 0);
    assert.equal(bytesRead, original.byteLength);
    assert.deepEqual(observed, original);
    assert.notDeepEqual(observed, replacement);
  } finally {
    await artifact?.handle.close().catch(() => undefined);
    for (const [name, value] of Object.entries(environment)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    await rm(sandbox, { recursive: true, force: true });
  }
});

test("non-ZIP bytes and a self-consistent archive with a false manifest digest are rejected", async () => {
  const sandbox = await realpath(
    await mkdtemp(path.join(tmpdir(), "elmos-translation-artifact-invalid-zip-")),
  );
  const runnerRoot = path.join(sandbox, "runner");
  const sourceRoot = path.join(sandbox, "sources");
  const casesRoot = path.join(sandbox, "cases");
  const context = { tenantId: "tenant-artifact-invalid", actor: "user:artifact-invalid" };
  const jobId = "33333333-3333-4333-8333-333333333333";
  const jobRoot = path.join(runnerRoot, "tenants", context.tenantId, "translation-jobs", jobId);
  const pipeline = path.join(jobRoot, "pipeline");
  const archive = Buffer.from("not a ZIP, despite a self-consistent outer digest");
  const fixture = codeArtifactFixture();
  const environment = {
    ELMOS_LOCAL_RUNNER_ENABLED: process.env.ELMOS_LOCAL_RUNNER_ENABLED,
    ELMOS_LOCAL_RUNNER_ROOT: process.env.ELMOS_LOCAL_RUNNER_ROOT,
    ELMOS_REPOSITORY_ROOT: process.env.ELMOS_REPOSITORY_ROOT,
    ELMOS_TRANSLATION_SOURCE_ROOT: process.env.ELMOS_TRANSLATION_SOURCE_ROOT,
    ELMOS_TRANSLATION_CASES_ROOT: process.env.ELMOS_TRANSLATION_CASES_ROOT,
    ELMOS_UV_PATH: process.env.ELMOS_UV_PATH,
    ELMOS_LOCAL_RUNNER_EXECUTOR: process.env.ELMOS_LOCAL_RUNNER_EXECUTOR,
  };
  try {
    await Promise.all([
      mkdir(sourceRoot, { recursive: true }),
      mkdir(casesRoot, { recursive: true }),
      mkdir(pipeline, { recursive: true }),
    ]);
    Object.assign(process.env, {
      ELMOS_LOCAL_RUNNER_ENABLED: "true",
      ELMOS_LOCAL_RUNNER_ROOT: runnerRoot,
      ELMOS_REPOSITORY_ROOT: admittedRepositoryRoot,
      ELMOS_TRANSLATION_SOURCE_ROOT: sourceRoot,
      ELMOS_TRANSLATION_CASES_ROOT: casesRoot,
      ELMOS_UV_PATH: process.execPath,
      ELMOS_LOCAL_RUNNER_EXECUTOR: "HOST_DEVELOPMENT",
    });
    await writeFile(path.join(pipeline, "repository-migration-artifact.zip"), archive);
    const jobRecord = {
      id: jobId,
      tenantId: context.tenantId,
      ...TEST_ROUTE_JOB_ADMISSION,
      repositoryRef: "workspace@artifact-snapshot",
      status: "COMPLETE",
      artifactReady: true,
      artifactSha256: createHash("sha256").update(archive).digest("hex"),
      artifactSize: archive.byteLength,
      snapshotSha256: "b".repeat(64),
      conversionSummary: fixture.summary,
    };
    await writeFile(path.join(jobRoot, "job.json"), JSON.stringify(jobRecord));
    await assert.rejects(
      translationArtifact(context, jobId),
      (error) => error?.message === "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
    );
    const tamperedManifestFixture = codeArtifactFixture({ tamperPayloadDigest: true });
    await writeFile(
      path.join(pipeline, "repository-migration-artifact.zip"),
      tamperedManifestFixture.archive,
    );
    await writeFile(path.join(jobRoot, "job.json"), JSON.stringify({
      ...jobRecord,
      artifactSha256: createHash("sha256").update(tamperedManifestFixture.archive).digest("hex"),
      artifactSize: tamperedManifestFixture.archive.byteLength,
    }));
    await assert.rejects(
      translationArtifact(context, jobId),
      (error) => error?.message === "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
    );
  } finally {
    for (const [name, value] of Object.entries(environment)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    await rm(sandbox, { recursive: true, force: true });
  }
});

test("chunked translation requests are cancelled at 8 KiB and duplicate fields fail closed", async () => {
  let cancelled = false;
  const oversized = new Request("http://localhost/api/translation/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array(4_096));
        controller.enqueue(new Uint8Array(4_097));
      },
      cancel() {
        cancelled = true;
      },
    }),
    duplex: "half",
  });
  await assert.rejects(
    readBoundedTranslationRequest(oversized),
    (error) => error?.status === 413 && error?.message === "REQUEST_TOO_LARGE",
  );
  assert.equal(cancelled, true);
  assert.throws(
    () => rejectDuplicateTopLevelJsonFields(
      '{"workspaceId":"allowed","workspaceId":"overridden"}',
    ),
    (error) => error?.status === 400
      && error?.message === "TRANSLATION_REQUEST_DUPLICATE_FIELD",
  );
});

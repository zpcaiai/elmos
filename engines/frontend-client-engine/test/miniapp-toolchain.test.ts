import assert from "node:assert/strict";
import test from "node:test";

import { runMiniappConversion } from "../src/miniapp-skill-runtime.js";
import {
  executeMiniappOfficialToolchain,
  planMiniappOfficialToolchain,
  type MiniappToolchainBroker,
  type MiniappToolchainPermit,
} from "../src/miniapp-toolchain.js";
import { conversionInput } from "./miniapp-test-fixture.js";

test("official toolchain planning binds exact supported stages and blocks unknown tuples", () => {
  const input = conversionInput(undefined, "vue3", ["wechat", "alipay", "douyin", "xiaohongshu"]);
  const run = runMiniappConversion(input);
  const plans = planMiniappOfficialToolchain(run.request, run.generatedProjects);
  assert.equal(plans.length, 20);
  assert.equal(plans.find(plan => plan.platform === "wechat" && plan.stage === "build")?.state, "NOT_RUN");
  assert.equal(plans.find(plan => plan.platform === "wechat" && plan.stage === "build")?.adapterAction, "getCompiledResult");
  assert.equal(plans.find(plan => plan.platform === "wechat" && plan.stage === "preview")?.adapterAction, "preview");
  assert.equal(plans.find(plan => plan.platform === "wechat" && plan.stage === "upload")?.adapterAction, "upload");
  assert.equal(plans.find(plan => plan.platform === "alipay" && plan.stage === "preview")?.driver, "minidev");
  assert.equal(plans.find(plan => plan.platform === "douyin" && plan.stage === "build")?.state, "BLOCKED");
  assert.equal(plans.find(plan => plan.platform === "xiaohongshu" && plan.stage === "release")?.state, "BLOCKED");
  assert.deepEqual(run.delivery.officialToolchainPlans, plans);
});

test("official execution stays NOT_RUN without authority and validates content-bound receipts", async () => {
  const run = runMiniappConversion(conversionInput(undefined, "vue3", ["wechat"]));
  const plan = run.delivery.officialToolchainPlans.find(candidate => candidate.stage === "build");
  assert.ok(plan);
  assert.equal((await executeMiniappOfficialToolchain(run.request, plan, undefined, undefined)).state, "NOT_RUN");

  const permit: MiniappToolchainPermit = {
    schemaVersion: "1.0",
    requestId: run.request.requestId,
    tenantId: run.request.tenantId,
    platform: plan.platform,
    stage: plan.stage,
    projectDigest: plan.projectDigest,
    idempotencyKey: plan.idempotencyKey,
    credentialReference: "secretref://tenant/wechat-ci",
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
  };
  const broker: MiniappToolchainBroker = {
    async execute(exactPlan) {
      return {
        schemaVersion: "1.0",
        platform: exactPlan.platform,
        stage: exactPlan.stage,
        state: "PASSED",
        idempotencyKey: exactPlan.idempotencyKey,
        projectDigest: exactPlan.projectDigest,
        artifactDigest: `sha256:${"a".repeat(64)}`,
        executor: "wechat-ci-runner",
        verifier: "independent-build-verifier",
        startedAt: new Date().toISOString(),
        completedAt: new Date().toISOString(),
        rawReceiptDigest: `sha256:${"b".repeat(64)}`,
      };
    },
  };
  assert.equal((await executeMiniappOfficialToolchain(run.request, plan, permit, broker)).state, "PASSED_EXTERNAL");

  await assert.rejects(
    executeMiniappOfficialToolchain(
      run.request,
      plan,
      { ...permit, tenantId: "other-tenant" },
      broker,
    ),
    /invalid, expired or cross-scope/u,
  );
});

test("preview and side-effecting stages require explicit approval", async () => {
  const run = runMiniappConversion(conversionInput(undefined, "vue3", ["wechat"]));
  const preview = run.delivery.officialToolchainPlans.find(candidate => candidate.stage === "preview");
  assert.ok(preview);
  const permit: MiniappToolchainPermit = {
    schemaVersion: "1.0",
    requestId: run.request.requestId,
    tenantId: run.request.tenantId,
    platform: preview.platform,
    stage: preview.stage,
    projectDigest: preview.projectDigest,
    idempotencyKey: preview.idempotencyKey,
    credentialReference: "secretref://tenant/wechat-ci",
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
  };
  const broker: MiniappToolchainBroker = {
    async execute() {
      throw new Error("must not execute without approval");
    },
  };
  await assert.rejects(
    executeMiniappOfficialToolchain(run.request, preview, permit, broker),
    /requires explicit approval/u,
  );
});

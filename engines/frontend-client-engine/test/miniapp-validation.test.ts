import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  canonicalizeMiniappDeterministicJson,
  digestMiniappValidationBytes,
  digestMiniappValidationPayload,
  evaluateMiniappLocalValidation,
  MINIAPP_LOCAL_VALIDATION_HARD_LIMITS,
  type MiniappLocalValidationContext,
  type MiniappValidationTraceEvent,
} from "../src/miniapp-validation.js";
import { materializeMiniappDeclaredOutputs } from "../src/miniapp-output-contracts.js";
import { runMiniappConversion } from "../src/miniapp-skill-runtime.js";
import { conversionInput } from "./miniapp-test-fixture.js";

const sourceTrace = [{
  sequence: 0,
  type: "route",
  value: "/",
  metadata: { runtimeTimestamp: 100, stable: "yes" },
}] as const;

const targetTrace = [{
  sequence: 0,
  type: "route",
  value: "/",
  metadata: { runtimeTimestamp: 200, stable: "yes" },
}] as const;

test("canonical evidence identity uses exact Unicode code-unit ordering without locale collation", () => {
  const decomposed = "e\u0301";
  const composed = "\u00e9";
  const first = {
    [composed]: 4,
    "\u00e4": 3,
    z: 2,
    [decomposed]: 1,
  };
  const reordered = {
    [decomposed]: 1,
    z: 2,
    "\u00e4": 3,
    [composed]: 4,
  };
  const expectedCanonical = `{"${decomposed}":1,"z":2,"ä":3,"${composed}":4}`;
  const expectedDigest = `sha256:${createHash("sha256").update(expectedCanonical, "utf8").digest("hex")}`;

  assert.equal(canonicalizeMiniappDeterministicJson(first), expectedCanonical);
  assert.equal(canonicalizeMiniappDeterministicJson(reordered), expectedCanonical);
  assert.equal(digestMiniappValidationPayload(first), expectedDigest);
  assert.equal(digestMiniappValidationPayload(reordered), expectedDigest);
  assert.notEqual(
    digestMiniappValidationPayload({ [decomposed]: true }),
    digestMiniappValidationPayload({ [composed]: true }),
    "NFC and NFD keys must remain distinct byte identities",
  );
});

function localCandidate(
  projectDigest: string,
  target: readonly MiniappValidationTraceEvent[] = targetTrace,
  source: readonly MiniappValidationTraceEvent[] = sourceTrace,
): unknown {
  const pixels = Uint8Array.from([10, 20, 30, 255, 40, 50, 60, 255]);
  const expectedFlows = [{ flowId: "route-home", platform: "wechat" }] as const;
  const testPlan = {
    testPlanId: "critical-route-plan-v1",
    criticalFlowPassRate: 1,
    expectedFlows,
  } as const;
  return {
    schemaVersion: "1.0",
    differential: {
      normalizerVersion: "local-v1",
      ignoredMetadataKeys: ["runtimeTimestamp"],
      testPlan: {
        ...testPlan,
        digest: digestMiniappValidationPayload(testPlan),
      },
      flows: [{
        flowId: "route-home",
        platform: "wechat",
        sourceTrace: source,
        targetTrace: target,
        sourceTraceDigest: digestMiniappValidationPayload(source),
        targetTraceDigest: digestMiniappValidationPayload(target),
        targetProjectDigest: projectDigest,
        sourceExecutor: "source-runner",
        targetExecutor: "target-runner",
        verifier: "independent-local-verifier",
      }],
    },
    visual: {
      comparisons: [{
        comparisonId: "home-default",
        platform: "wechat",
        width: 2,
        height: 1,
        sourceRgbaBase64: Buffer.from(pixels).toString("base64"),
        targetRgbaBase64: Buffer.from(pixels).toString("base64"),
        sourceDigest: digestMiniappValidationBytes(pixels),
        targetDigest: digestMiniappValidationBytes(pixels),
        targetProjectDigest: projectDigest,
        masks: [],
        sourceExecutor: "source-visual-runner",
        targetExecutor: "target-visual-runner",
        verifier: "independent-visual-verifier",
      }],
    },
  };
}

test("byte-bound local comparisons execute without manufacturing official runtime, device, or release evidence", () => {
  const input = conversionInput(undefined, "vue3", ["wechat"]);
  const initial = runMiniappConversion(input);
  const projectDigest = initial.evidenceGraph.find(node => node.id === "project-wechat")?.digest;
  assert.ok(projectDigest);

  const run = runMiniappConversion({ ...input, localValidation: localCandidate(projectDigest) });
  assert.equal(run.localValidation.differential.state, "PASSED_LOCAL");
  assert.equal(run.localValidation.visual.state, "PASSED_LOCAL");
  assert.equal(run.localValidation.evidenceBoundary.localCandidate, "SELF_ATTESTED");
  assert.equal(run.localValidation.evidenceBoundary.officialSourceRuntime, "NOT_RUN");
  assert.equal(run.localValidation.evidenceBoundary.officialTargetRuntime, "NOT_RUN");
  assert.equal(run.localValidation.evidenceBoundary.officialDeviceVisual, "NOT_RUN");
  assert.equal(run.localValidation.evidenceBoundary.release, "NOT_RUN");
  assert.equal(run.localValidation.visual.rawCaptureReplay, "BLOCKED_RAW_CAPTURE_NOT_MATERIALIZED");
  assert.equal(run.differential.sourceRuntimeCapture, "NOT_RUN");
  assert.equal(run.visual.sourceScreenshots, "NOT_RUN");
  assert.equal(run.delivery.state, "NOT_RUN");
  assert.equal(run.certification, "NOT_CERTIFIED");
  assert.equal(run.gates.find(gate => gate.gate === "G5")?.state, "NOT_RUN");
  assert.equal(run.gates.find(gate => gate.gate === "G6")?.state, "NOT_RUN");
  const localEvidence = run.evidenceGraph.find(node => node.id === "local-validation-candidate");
  assert.equal(localEvidence?.synthetic, true);
  for (const gate of run.gates.filter(candidate => ["G0", "G1", "G2", "G3", "G4", "G8"].includes(candidate.gate))) {
    assert.equal(gate.evidenceDigests.includes(localEvidence!.digest), false);
  }
  assert.ok(run.taskRecords
    .filter(record => ["MAPP-031", "MAPP-032", "MAPP-033", "MAPP-034"].includes(record.taskId))
    .every(record => record.state === "EXECUTED_LOCAL_EXTERNAL_PENDING"));

  const outputs = materializeMiniappDeclaredOutputs(run);
  assert.ok(outputs
    .filter(output => output.ownerSkill === "miniapp-differential-testing")
    .every(output => output.state === "PASSED_LOCAL"));
  const visualOutputs = outputs.filter(output => output.ownerSkill === "miniapp-visual-regression-testing");
  assert.equal(visualOutputs.find(output => output.declaredPattern === "screenshots/**")?.state, "NOT_RUN");
  assert.ok(visualOutputs
    .filter(output => output.declaredPattern !== "screenshots/**")
    .every(output => output.state === "PASSED_LOCAL"));
  const ciStates = new Map(outputs
    .filter(output => output.ownerSkill === "miniapp-ci-build-release")
    .map(output => [output.declaredPattern, output.state]));
  assert.equal(ciStates.get("ci pipelines"), "NOT_RUN");
  assert.equal(ciStates.get("build manifests"), "NOT_RUN");
  assert.equal(ciStates.get("upload receipts"), "NOT_RUN");
  assert.equal(ciStates.get("release records"), "NOT_RUN");
});

test("tampered trace and pixel digests fail closed before a comparison result exists", () => {
  const context: MiniappLocalValidationContext = {
    targets: [{
      platform: "wechat",
      toolchainVersion: "1.06.2504010",
      projectDigest: `sha256:${"a".repeat(64)}`,
    }],
    requestedSimilarity: 0.95,
    criticalFlowPassRate: 1,
    maximumRepairIterations: 3,
    repairFindings: [],
  };
  const tamperedTrace = localCandidate(context.targets[0]!.projectDigest) as {
    differential: { flows: Array<{ sourceTraceDigest: string }> };
  };
  tamperedTrace.differential.flows[0]!.sourceTraceDigest = `sha256:${"b".repeat(64)}`;
  assert.throws(
    () => evaluateMiniappLocalValidation(tamperedTrace, context),
    /sourceTraceDigest mismatch/,
  );

  const tamperedPixels = localCandidate(context.targets[0]!.projectDigest) as {
    visual: { comparisons: Array<{ targetDigest: string }> };
  };
  tamperedPixels.visual.comparisons[0]!.targetDigest = `sha256:${"c".repeat(64)}`;
  assert.throws(
    () => evaluateMiniappLocalValidation(tamperedPixels, context),
    /targetDigest mismatch/,
  );
});

test("aggregate local-validation byte and node budgets protect structured API callers", () => {
  const finding = "wechat:C:MINIAPP_STYLE_MAPPING_REQUIRED";
  const context: MiniappLocalValidationContext = {
    targets: [{
      platform: "wechat",
      toolchainVersion: "1.06.2504010",
      projectDigest: `sha256:${"a".repeat(64)}`,
    }],
    requestedSimilarity: 0.95,
    criticalFlowPassRate: 1,
    maximumRepairIterations: 3,
    repairFindings: [{ finding, owner: "mapping", approvalRequired: false }],
  };
  const candidateWithPatchValue = (value: unknown) => ({
    schemaVersion: "1.0",
    repair: {
      priorPatchDigests: [],
      proposals: [{
        finding,
        owner: "mapping",
        patch: [{ op: "replace", path: "/mappings/bounded", value }],
        patchDigest: `sha256:${"b".repeat(64)}`,
        targetedTests: ["mapping-contract"],
        affectedGates: ["G3"],
        risk: "low",
      }],
    },
  });

  assert.throws(
    () => evaluateMiniappLocalValidation(
      candidateWithPatchValue("x".repeat(MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxCanonicalBytes)),
      context,
    ),
    /aggregate localValidation canonical byte budget/,
  );

  const fullArrays = Math.floor(MINIAPP_LOCAL_VALIDATION_HARD_LIMITS.maxJsonNodes / 4096) + 1;
  const tooManyNodes = Array.from(
    { length: fullArrays },
    () => Array<null>(4096).fill(null),
  );
  assert.throws(
    () => evaluateMiniappLocalValidation(candidateWithPatchValue(tooManyNodes), context),
    /aggregate localValidation JSON node budget/,
  );
});

test("local-validation snapshots reject accessors and Proxies without invoking user traps", () => {
  const context: MiniappLocalValidationContext = {
    targets: [{
      platform: "wechat",
      toolchainVersion: "1.06.2504010",
      projectDigest: `sha256:${"a".repeat(64)}`,
    }],
    requestedSimilarity: 0.95,
    criticalFlowPassRate: 1,
    maximumRepairIterations: 3,
    repairFindings: [],
  };
  let accessorCalls = 0;
  const accessorCandidate: Record<string, unknown> = { schemaVersion: "1.0" };
  Object.defineProperty(accessorCandidate, "repair", {
    enumerable: true,
    get() {
      accessorCalls += 1;
      return { priorPatchDigests: [], proposals: [] };
    },
  });
  assert.throws(
    () => evaluateMiniappLocalValidation(accessorCandidate, context),
    /accessors are forbidden/,
  );
  assert.equal(accessorCalls, 0);

  let proxyTrapCalls = 0;
  const proxyCandidate = new Proxy({ schemaVersion: "1.0" }, {
    getPrototypeOf(target) {
      proxyTrapCalls += 1;
      return Reflect.getPrototypeOf(target);
    },
    ownKeys(target) {
      proxyTrapCalls += 1;
      return Reflect.ownKeys(target);
    },
    getOwnPropertyDescriptor(target, property) {
      proxyTrapCalls += 1;
      return Reflect.getOwnPropertyDescriptor(target, property);
    },
  });
  assert.throws(
    () => evaluateMiniappLocalValidation(proxyCandidate, context),
    /must not be a Proxy/,
  );
  assert.equal(proxyTrapCalls, 0);
});

test("repair-only plans remain blocked evidence until reproduction and gate validation execute", () => {
  const files = [{
    path: "package.json",
    content: JSON.stringify({ dependencies: { react: "19.2.0" } }),
  }, {
    path: "package-lock.json",
    content: JSON.stringify({
      lockfileVersion: 3,
      packages: {
        "": { dependencies: { react: "19.2.0" } },
        "node_modules/react": { version: "19.2.0" },
      },
    }),
  }, {
    path: "src/App.tsx",
    content: "export function App(){ return <main><input autoFocus /></main>; }",
  }] as const;
  const input = conversionInput(files, "react", ["wechat"]);
  const initial = runMiniappConversion(input);
  const finding = initial.repair.candidates.find((candidate) => !candidate.approvalRequired);
  assert.ok(finding, "fixture must produce a deterministic repair candidate");
  const root = finding.owner === "mapping"
    ? "mappings"
    : finding.owner === "adapter"
      ? "adapters"
      : finding.owner === "generated-code"
        ? "generators"
        : "ir";
  const patch = [{ op: "replace", path: `/${root}/reviewed`, value: true }] as const;
  const run = runMiniappConversion({
    ...input,
    localValidation: {
      schemaVersion: "1.0",
      repair: {
        priorPatchDigests: [],
        proposals: [{
          finding: finding.finding,
          owner: finding.owner,
          patch,
          patchDigest: digestMiniappValidationPayload(patch),
          targetedTests: ["repair-reproduction"],
          affectedGates: ["G3"],
          risk: "low",
        }],
      },
    },
  });
  assert.equal(run.localValidation.differential.state, "NOT_RUN");
  assert.equal(run.localValidation.visual.state, "NOT_RUN");
  assert.equal(run.localValidation.repair.state, "PLAN_READY");
  assert.equal(run.localValidation.repair.executionEvidence, "NOT_RUN");
  const candidateEvidence = run.evidenceGraph.find((node) => node.id === "local-validation-candidate");
  assert.ok(candidateEvidence);
  assert.equal(candidateEvidence.synthetic, true);
  assert.equal(candidateEvidence.state, "BLOCKED");

  const repairOutputs = materializeMiniappDeclaredOutputs(run).filter(
    (artifact) => artifact.ownerSkill === "miniapp-auto-repair-loop",
  );
  assert.equal(repairOutputs.find((artifact) => artifact.declaredPattern === "repair-action.json")?.state, "BLOCKED");
  assert.equal(repairOutputs.find((artifact) => artifact.declaredPattern === "repair-history.json")?.state, "BLOCKED");
  assert.equal(repairOutputs.find((artifact) => artifact.declaredPattern === "patches/**")?.state, "NOT_RUN");
  assert.equal(repairOutputs.find((artifact) => artifact.declaredPattern === "post-repair-validation.json")?.state, "NOT_RUN");
  const action = repairOutputs.find((artifact) => artifact.declaredPattern === "repair-action.json");
  assert.ok(action);
  const actionBody = JSON.parse(action.content) as { validation: { reproduction: string } };
  assert.equal(actionBody.validation.reproduction, "blocked");
});

test("functional differences invalidate a matching local visual candidate", () => {
  const input = conversionInput(undefined, "vue3", ["wechat"]);
  const initial = runMiniappConversion(input);
  const projectDigest = initial.evidenceGraph.find(node => node.id === "project-wechat")?.digest;
  assert.ok(projectDigest);
  const changedTarget = [{
    sequence: 0,
    type: "route",
    value: "/different",
    metadata: { runtimeTimestamp: 200, stable: "yes" },
  }] as const;
  const run = runMiniappConversion({ ...input, localValidation: localCandidate(projectDigest, changedTarget) });
  assert.equal(run.localValidation.differential.state, "FAILED_LOCAL");
  assert.equal(run.localValidation.visual.comparisons[0]?.similarity, 1);
  assert.equal(run.localValidation.visual.comparisons[0]?.verdict, "blocked");
  assert.equal(run.localValidation.visual.state, "BLOCKED");
  assert.equal(run.gates.find(gate => gate.gate === "G6")?.state, "NOT_RUN");
});

test("critical-flow plans block missing flows and preserve absent-versus-null event values", () => {
  const input = conversionInput(undefined, "vue3", ["wechat"]);
  const initial = runMiniappConversion(input);
  const projectDigest = initial.evidenceGraph.find(node => node.id === "project-wechat")?.digest;
  assert.ok(projectDigest);

  const absentValue = [{ sequence: 0, type: "route", metadata: {} }] as const;
  const explicitNull = [{ sequence: 0, type: "route", value: null, metadata: {} }] as const;
  const presenceRun = runMiniappConversion({
    ...input,
    localValidation: localCandidate(projectDigest, explicitNull, absentValue),
  });
  assert.equal(presenceRun.localValidation.differential.state, "FAILED_LOCAL");
  assert.ok(presenceRun.localValidation.differential.comparisons[0]?.diffs.some(
    diff => diff.kind === "event-value" && diff.message === "event value presence differs",
  ));

  const incomplete = localCandidate(projectDigest) as {
    differential: {
      testPlan: {
        testPlanId: string;
        criticalFlowPassRate: number;
        expectedFlows: Array<{ flowId: string; platform: "wechat" }>;
        digest: string;
      };
    };
  };
  const expectedFlows = [
    { flowId: "route-home", platform: "wechat" as const },
    { flowId: "route-settings", platform: "wechat" as const },
  ];
  incomplete.differential.testPlan.expectedFlows = expectedFlows;
  incomplete.differential.testPlan.digest = digestMiniappValidationPayload({
    testPlanId: incomplete.differential.testPlan.testPlanId,
    criticalFlowPassRate: incomplete.differential.testPlan.criticalFlowPassRate,
    expectedFlows,
  });
  const incompleteRun = runMiniappConversion({ ...input, localValidation: incomplete });
  assert.equal(incompleteRun.localValidation.differential.state, "BLOCKED");
  assert.ok(incompleteRun.localValidation.differential.findings.includes(
    "wechat:route-settings:LOCAL_EXPECTED_FLOW_MISSING",
  ));
});

test("repair planning is bounded, digest-bound, duplicate-aware, and never applies a patch", () => {
  const projectDigest = `sha256:${"a".repeat(64)}`;
  const finding = "wechat:C:MINIAPP_STYLE_MAPPING_REQUIRED";
  const patch = [{ op: "replace", path: "/mappings/todo/color", value: "#111827" }] as const;
  const patchDigest = digestMiniappValidationPayload(patch);
  const context: MiniappLocalValidationContext = {
    targets: [{ platform: "wechat", toolchainVersion: "1.06.2504010", projectDigest }],
    requestedSimilarity: 0.95,
    criticalFlowPassRate: 1,
    maximumRepairIterations: 9,
    repairFindings: [{ finding, owner: "mapping", approvalRequired: false }],
  };
  const planned = evaluateMiniappLocalValidation({
    schemaVersion: "1.0",
    repair: {
      priorPatchDigests: [],
      proposals: [{
        finding,
        owner: "mapping",
        patch,
        patchDigest,
        targetedTests: ["mapping-contract"],
        affectedGates: ["G3", "G6"],
        risk: "medium",
      }],
    },
  }, context);
  assert.equal(planned.repair.state, "PLAN_READY");
  assert.equal(planned.repair.maximumIterations, 3);
  assert.equal(planned.repair.appliedIterations, 0);
  assert.equal(planned.repair.executionEvidence, "NOT_RUN");
  assert.equal(planned.repair.rollback, "NO_MUTATION_PERFORMED");

  const duplicate = evaluateMiniappLocalValidation({
    schemaVersion: "1.0",
    repair: {
      priorPatchDigests: [patchDigest],
      proposals: [{
        finding,
        owner: "mapping",
        patch,
        patchDigest,
        targetedTests: ["mapping-contract"],
        affectedGates: ["G3"],
        risk: "low",
      }],
    },
  }, context);
  assert.equal(duplicate.repair.state, "BLOCKED");
  assert.match(duplicate.repair.actions[0]?.stopReason ?? "", /DUPLICATE_PATCH_FINGERPRINT/);
  assert.equal(duplicate.evidenceBoundary.release, "NOT_RUN");

  const escapedPatch = [{ op: "replace", path: "/mappings/~1escape", value: "x" }] as const;
  assert.throws(() => evaluateMiniappLocalValidation({
    schemaVersion: "1.0",
    repair: {
      priorPatchDigests: [],
      proposals: [{
        finding,
        owner: "mapping",
        patch: escapedPatch,
        patchDigest: digestMiniappValidationPayload(escapedPatch),
        targetedTests: ["mapping-contract"],
        affectedGates: ["G3"],
        risk: "low",
      }],
    },
  }, context), /outside repairable roots/);
});

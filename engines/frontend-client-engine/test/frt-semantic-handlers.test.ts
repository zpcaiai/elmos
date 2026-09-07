import test from "node:test";
import assert from "node:assert/strict";

import { frtCatalog } from "../src/frt-catalog.generated.js";
import { frtHandlerRegistry } from "../src/frt-handler-registry.generated.js";
import {
  delegatedFrtSemanticHandlerKinds,
  executeFrtSemanticHandler,
  implementedFrtHandlerKinds,
  type DelegatedFrtSemanticHandlerKind,
  type FrtSemanticHandlerContext,
} from "../src/frt-semantic-handlers.js";

const routes = [
  {
    routeId: "Vue 3 -> React",
    skillId: "FRT-1305",
    batch: "G13",
    source: "Vue 3",
    target: "React",
    certification: "NOT_CERTIFIED",
  },
] as const;

const fixtures: Readonly<Record<DelegatedFrtSemanticHandlerKind, Readonly<Record<string, unknown>>>> = {
  governance: {
    invariants: [{ id: "tenant-scope", satisfied: true }],
  },
  source_generation: {
    targetProfile: { stack: "React", version: "19.2.7" },
    uiIr: { title: "Counter", modules: ["app"] },
  },
  build_toolchain: {
    astNodes: [{ id: "counter", name: "Counter", kind: "component" }],
  },
  test_automation: {
    components: [{ id: "counter", props: ["value"], events: ["increment"], slots: [], hooks: [] }],
  },
  delivery_pipeline: {
    states: [{ id: "count", owner: "counter", persistence: "memory" }],
  },
  design_system: {
    routes: [{ id: "home", path: "/" }],
  },
  mobile_client: {
    uiNodes: [{ id: "title", interactive: false }],
    designTokens: { accent: "#b34838" },
    locales: ["en-US"],
  },
  cross_platform: {
    requiredCapabilities: ["storage"],
    platformCapabilities: { ios: ["storage"] },
  },
  route_orchestration: {
    routeIds: ["Vue 3 -> React"],
    corpus: [{ id: "case-1", sourceDigest: `sha256:${"1".repeat(64)}`, expectedIrDigest: `sha256:${"2".repeat(64)}` }],
  },
  compatibility: {
    packs: [{ id: "core", priority: 100, provides: ["ui"], requires: [] }],
  },
  advanced_verification: {
    properties: [{ id: "count-non-negative", expression: "count >= 0", kind: "invariant", assumptions: [] }],
  },
  runtime_operations: {
    resources: [{ id: "skill-registry", type: "registry", tenantBound: true, version: "1.0.0" }],
  },
  product_workflow: {
    requirements: [{ id: "REQ-1" }],
    initialState: "draft",
    states: [{ id: "draft" }, { id: "done" }],
    transitions: [{ id: "finish", from: "draft", to: "done", sideEffect: false }],
    artifacts: [{ id: "component", requirementIds: ["REQ-1"] }],
    journeys: [{ id: "journey", requirementIds: ["REQ-1"] }],
  },
  administration: {
    capabilities: [{ id: "orders.read" }],
    roles: [{ id: "operator", permissions: ["orders.read"] }],
    operations: [{ id: "list-orders", roleId: "operator", permission: "orders.read", auditEvent: "orders.listed" }],
  },
  performance_capacity: {
    workload: { concurrency: 10, durationSeconds: 60 },
    budgets: { p95LatencyMs: 500, maximumErrorRate: 0.01 },
    samples: [{ latencyMs: 100, success: true }, { latencyMs: 200, success: true }],
  },
  resilience_dr: {
    scenarios: [{ id: "database-loss", rollback: "restore snapshot", blastRadius: "isolated-test-tenant" }],
    recoveryObjectives: { maximumRtoSeconds: 300, maximumRpoSeconds: 60 },
  },
  security_privacy: {
    assets: [{ id: "checkout-api", classification: "confidential" }],
    findings: [],
    dataFlows: [{ id: "checkout", personalData: false }],
    sbomComponents: [{ name: "react", version: "19.2.7" }],
  },
  production_readiness: {
    slos: [{ serviceId: "frontend", target: 0.999 }],
    runbooks: [{ id: "frontend-errors", serviceId: "frontend" }],
  },
};

function context(
  handlerKind: DelegatedFrtSemanticHandlerKind,
  input: Readonly<Record<string, unknown>> = fixtures[handlerKind],
): FrtSemanticHandlerContext {
  const skill = frtCatalog.skills.find(item => item.handlerKind === handlerKind);
  assert.ok(skill, `catalog must contain ${handlerKind}`);
  return {
    skill,
    handler: { handlerKind, surfaceManifestPaths: {} },
    contract: skill.executionContract,
    action: "ANALYZE",
    input,
    routes,
    requiredEvidenceRoles: ["CONTRACT_VALIDATION", "INDEPENDENT_VERIFICATION"],
    obligations: ["KEEP_UNKNOWN_AND_UNSUPPORTED_SEMANTICS_EXPLICIT"],
  };
}

test("the generated FRT registry has a concrete implementation for every one of its 23 handler kinds", () => {
  const registered = [...new Set(frtHandlerRegistry.map(item => item.handlerKind))].sort();
  assert.deepEqual(registered, [...implementedFrtHandlerKinds].sort());
  assert.equal(registered.length, 23);
});

test("all 18 formerly fallback handler kinds execute distinct typed domain artifacts", () => {
  const artifactKinds = new Set<string>();
  for (const handlerKind of delegatedFrtSemanticHandlerKinds) {
    const result = executeFrtSemanticHandler(context(handlerKind));
    assert.equal(result.handlerImplementation, "frt-semantic-handlers/v1", handlerKind);
    assert.equal((result.inputContract as { state: string }).state, "SATISFIED", handlerKind);
    const handlerFindings = result.handlerFindings as { blocking: boolean }[];
    assert.equal(handlerFindings.some(item => item.blocking), false, handlerKind);
    const artifact = result.semanticArtifact as { kind: string };
    assert.ok(artifact.kind, handlerKind);
    artifactKinds.add(artifact.kind);
    assert.equal((result.executionBoundary as { externalExecution: string }).externalExecution, "NOT_RUN");
    assert.equal((result.executionBoundary as { certification: string }).certification, "NOT_CERTIFIED");
    assert.equal("semanticAnalysis" in result, false, `${handlerKind} must not use the old metadata echo fallback`);
  }
  assert.equal(artifactKinds.size, delegatedFrtSemanticHandlerKinds.length);
});

test("generated web skeletons escape source-controlled titles and use valid static Vue attributes", () => {
  const vue = executeFrtSemanticHandler(context("source_generation", {
    targetProfile: { stack: "Vue 3", version: "3.5.29" },
    uiIr: { title: '<Admin & "Ops">' },
  }));
  const files = (vue.semanticArtifact as { generatedFiles: Record<string, string> }).generatedFiles;
  assert.match(files["src/App.vue"]!, /aria-label="&lt;Admin &amp; &quot;Ops&quot;&gt;"/);
  assert.doesNotMatch(files["src/App.vue"]!, /:aria-label/);

  const react = executeFrtSemanticHandler(context("source_generation", {
    targetProfile: { stack: "React", version: "19.2.7" },
    uiIr: { title: 'Admin "Ops"' },
  }));
  const reactFiles = (react.semanticArtifact as { generatedFiles: Record<string, string> }).generatedFiles;
  assert.match(reactFiles["src/App.tsx"]!, /aria-label=\{"Admin \\"Ops\\""\}/);
});

test("typed handlers fail closed on absent required input instead of emitting success-shaped metadata", () => {
  for (const handlerKind of delegatedFrtSemanticHandlerKinds) {
    const result = executeFrtSemanticHandler(context(handlerKind, {}));
    const contract = result.inputContract as { state: string; missing: string[] };
    assert.equal(contract.state, "INPUT_REQUIRED", handlerKind);
    assert.ok(contract.missing.length > 0, handlerKind);
    assert.ok((result.handlerFindings as { blocking: boolean }[]).some(item => item.blocking), handlerKind);
  }
});

test("domain algorithms surface governance, performance, workflow, and security failures", () => {
  const governance = executeFrtSemanticHandler(context("governance", {
    invariants: [{ id: "tenant-scope", satisfied: false }],
  }));
  assert.equal((governance.semanticArtifact as { releaseDecision: string }).releaseDecision, "BLOCKED");

  const performance = executeFrtSemanticHandler(context("performance_capacity", {
    workload: { concurrency: 2 },
    budgets: { p95LatencyMs: 50 },
    samples: [{ latencyMs: 100, success: true }],
  }));
  assert.deepEqual((performance.semanticArtifact as { budgetViolations: string[] }).budgetViolations, ["p95LatencyMs"]);

  const workflow = executeFrtSemanticHandler(context("product_workflow", {
    requirements: [{ id: "REQ-1" }],
    initialState: "draft",
    states: [{ id: "draft" }, { id: "orphan" }],
    transitions: [],
  }));
  assert.deepEqual((workflow.semanticArtifact as { stateMachine: { unreachable: string[] } }).stateMachine.unreachable, ["orphan"]);

  const security = executeFrtSemanticHandler(context("security_privacy", {
    assets: [{ id: "api", classification: "confidential" }],
    findings: [{ id: "SEC-1", severity: "CRITICAL" }],
  }));
  assert.equal((security.semanticArtifact as { zeroToleranceFindingCount: number }).zeroToleranceFindingCount, 1);
  assert.ok((security.handlerFindings as { code: string }[]).some(item => item.code === "FRT_SECURITY_ZERO_TOLERANCE_FINDING"));
});

test("unknown handler kinds are rejected and cannot fall through permissively", () => {
  assert.throws(
    () => executeFrtSemanticHandler({
      ...context("governance"),
      handler: { handlerKind: "unknown", surfaceManifestPaths: {} },
    }),
    /No concrete FRT semantic handler is implemented/,
  );
});

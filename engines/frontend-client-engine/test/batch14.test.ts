import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  FrontendClientEngine,
  advanceFrontendState,
  assessAngularJsWatch,
  assessBffResponsibilities,
  assessDesktopWebReplacement,
  assessDomOwnership,
  assessElectronSecurity,
  assessServiceWorkerRelease,
  assessVueCompat,
  buildUiSemanticGraph,
  classifyReactClass,
  discoverWorkspace,
  evaluateAccessibility,
  evaluateClientCompatibility,
  evaluateClientCutover,
  evaluateVisualDifference,
  jqueryUpgradePath,
  mapDesignComponent,
  planFrontendMigration,
  validateDeepLinks,
  validateOfflineReplay,
  type TargetProfile,
  type VisualEnvironment,
  type WorkspaceInventory
} from "../src/index.js";

const environment: VisualEnvironment = {
  imageDigest: "sha256:browser", browserVersion: "chromium-140", operatingSystem: "linux",
  fontHash: "sha256:fonts", viewport: "1440x900", locale: "zh-CN", timezone: "Asia/Shanghai",
  fixtureHash: "sha256:fixture"
};

function inventory(frameworks: WorkspaceInventory["frameworks"]): WorkspaceInventory {
  return { snapshotId: "snap-1", packageManager: "PNPM", lockfiles: ["pnpm-lock.yaml"], frameworks,
    buildTools: ["VITE"], platforms: ["WEB"], entryPoints: ["src/main.ts"], findings: [] };
}

const target: TargetProfile = {
  mode: "BEHAVIOR_PRESERVING_MODERNIZATION", targetFramework: "ANGULAR", targetVersion: "20.0.0",
  browserProfileRef: "browser-1", accessibilityTarget: "WCAG_2_2_AA"
};

test("scenario 1 reports AngularJS EOL and inventory evidence", () => {
  const result = discoverWorkspace("snap-1", { "package.json": '{"dependencies":{"angular":"1.8.3"}}', "package-lock.json": "{}", "app.js": "angular.module('legacy', [])" });
  assert.ok(result.findings.some(value => value.code === "ANGULARJS_EOL"));
  assert.deepEqual(result.frameworks, ["ANGULARJS"]);
});

test("scenario 2 does not mechanically lower interdependent watches", () => {
  assert.equal(assessAngularJsWatch("$scope.$watch('a', fn); $scope.$watch('b', fn); $scope.$broadcast('x')"), "BEHAVIOR_TEST_REQUIRED");
});

test("scenario 3 expands Angular upgrades one major at a time", () => {
  const plan = planFrontendMigration(inventory(["ANGULAR"]), target, { ANGULAR: "17.3.0" });
  assert.deepEqual(plan.steps.filter(value => value.type.startsWith("ANGULAR_MAJOR_UPGRADE")).map(value => value.type),
    ["ANGULAR_MAJOR_UPGRADE_18", "ANGULAR_MAJOR_UPGRADE_19", "ANGULAR_MAJOR_UPGRADE_20"]);
});

test("scenario 4 makes Vue compatibility temporary and removable", () => {
  const plan = planFrontendMigration(inventory(["VUE2"]), { ...target, targetFramework: "VUE", targetVersion: "3.5.0" });
  assert.ok(plan.steps.some(value => value.type === "ENABLE_VUE_COMPAT"));
  assert.ok(plan.steps.some(value => value.type === "REMOVE_VUE_COMPAT"));
});

test("scenario 5 blocks private Vue VNode assumptions", () => {
  assert.equal(assessVueCompat("return vnode.componentOptions.Ctor"), "INELIGIBLE");
});

test("scenario 6 classifies DOM measurement separately from ordinary effects", () => {
  assert.equal(classifyReactClass("componentDidMount(){ this.el.getBoundingClientRect(); }"), "FUNCTION_WITH_LAYOUT_EFFECT");
});

test("scenario 7 preserves class error boundaries", () => {
  assert.equal(classifyReactClass("componentDidCatch(error) { report(error); }"), "KEEP_ERROR_BOUNDARY_CLASS");
});

test("scenario 8 detects mixed React and jQuery DOM ownership", () => {
  assert.equal(assessDomOwnership("createRoot(root).render(app); $('#root').html(markup);"), "CONFLICT");
});

test("scenario 9 stages jQuery 1 to 4 migration and removes Migrate", () => {
  assert.deepEqual(jqueryUpgradePath(1, 4), ["MIGRATE_1", "JQUERY_3", "MIGRATE_3", "JQUERY_4", "MIGRATE_4", "REMOVE_MIGRATE"]);
});

test("scenario 10 treats font drift as an unstable visual environment", () => {
  assert.equal(evaluateVisualDifference(environment, { ...environment, fontHash: "sha256:other" }, 0.8, 0.01, false), "UNSTABLE_BASELINE");
});

test("scenario 11 compares an approved design change against target authority", () => {
  assert.equal(evaluateVisualDifference(environment, environment, 0.25, 0.01, true), "EXPECTED_APPROVED_CHANGE");
});

test("scenario 12 automated accessibility success cannot claim full pass", () => {
  assert.equal(evaluateAccessibility({ automatedViolations: 0, automatedIncomplete: 0 }), "NEEDS_REVIEW");
});

test("scenario 13 a focus regression fails independently of visual equality", () => {
  assert.equal(evaluateAccessibility({ automatedViolations: 0, automatedIncomplete: 0, keyboardPassed: true, focusPassed: false }), "VIOLATION");
});

test("scenario 14 unsafe Electron IPC is critical input to the security gate", () => {
  const findings = assessElectronSecurity("new BrowserWindow({webPreferences:{nodeIntegration:true}}); ipcMain.on('exec-command', (_, command) => exec(command));");
  assert.ok(findings.includes("ELECTRON_NODE_INTEGRATION"));
  assert.ok(findings.includes("ELECTRON_IPC_UNVALIDATED"));
});

test("scenario 15 desktop device dependencies block full web replacement", () => {
  assert.equal(assessDesktopWebReplacement(["SERIAL_PORT", "PRINTER", "SMART_CARD"]), "DEVICE_CAPABILITY_BLOCKER");
});

test("scenario 16 active old mobile versions block backend field removal", () => {
  assert.equal(evaluateClientCompatibility({ activeClientVersions: ["5.1", "6.0"], supportedClientVersions: ["6.0"], removedFields: ["legacyPrice"], adapterAvailable: false }), "BLOCKED");
});

test("scenario 17 offline duplicate replay requires idempotency", () => {
  assert.equal(validateOfflineReplay(["order-1", "order-1"], false), "DUPLICATE_RISK");
  assert.equal(validateOfflineReplay(["order-1", "order-1"], true), "PASS");
});

test("scenario 18 deep-link removal requires redirect coverage", () => {
  assert.deepEqual(validateDeepLinks(["/campaign", "/orders/1"], ["/orders/1"], {}), ["/campaign"]);
});

test("scenario 19 service-worker release retains old chunks or reload strategy", () => {
  assert.equal(assessServiceWorkerRelease(["old-a.js"], [], false), "CHUNK_404_RISK");
});

test("scenario 20 BFF cannot become the pricing domain owner", () => {
  assert.equal(assessBffResponsibilities(["AGGREGATION", "PRICE_CALCULATION"]), "BFF_BUSINESS_LOGIC_LEAK");
});

test("scenario 21 coordinated cutover requires every client and backend", () => {
  assert.equal(evaluateClientCutover({ requestedStage: "CANARY", currentStage: "INTERNAL", webPassed: true,
    desktopPassed: true, androidPassed: true, iosPassed: false, bffPassed: true, backendPassed: true,
    usageEvidenceRefs: ["ev-usage"] }), "HOLD");
});

test("scenario 22 no-equivalent design component requires human design", () => {
  assert.equal(mapDesignComponent("NO_EQUIVALENT"), "HUMAN_DESIGN_REQUIRED");
});

test("static scan emits immutable evidence without executing customer code", () => {
  const engine = new FrontendClientEngine();
  const response = engine.scan({ organizationId: "org-1", snapshotId: "snap-1", idempotencyKey: "scan-1", workspaceRef: "app-1",
    input: { files: { "package.json": '{"dependencies":{"react":"19.2.7"}}', "pnpm-lock.yaml": "lockfileVersion: '9.0'", "src/App.tsx": "export function App(){ return <div/> }" } } });
  assert.equal(response.status, "SUCCEEDED");
  assert.equal(response.result.customerCodeExecuted, false);
  assert.equal(response.evidenceRefs.length, 1);
});

test("changed-input idempotency reuse conflicts", () => {
  const engine = new FrontendClientEngine();
  const base = { organizationId: "org-1", snapshotId: "snap-1", idempotencyKey: "same", workspaceRef: "app-1" };
  engine.scan({ ...base, input: { files: { "package.json": "{}", "package-lock.json": "{}" } } });
  const conflict = engine.scan({ ...base, input: { files: { "package.json": '{"name":"changed"}', "package-lock.json": "{}" } } });
  assert.equal(conflict.error?.errorCode, "IDEMPOTENCY_CONFLICT");
  assert.equal(conflict.evidenceRefs.length, 0);
});

test("customer transformation fails closed without an approved runner", () => {
  const engine = new FrontendClientEngine();
  const response = engine.executeStep({ organizationId: "org-1", snapshotId: "snap-1", idempotencyKey: "exec-1", workspaceRef: "app-1", planId: "plan-1", stepId: "route-1", runnerProfile: "MODERN_WEB" });
  assert.equal(response.status, "FAILED");
  assert.equal(response.error?.errorCode, "RUNNER_NOT_CONFIGURED");
  assert.deepEqual(response.evidenceRefs, []);
});

test("validation is inconclusive without manual evidence when required", () => {
  const engine = new FrontendClientEngine();
  const response = engine.validate({ organizationId: "org-1", snapshotId: "snap-1", idempotencyKey: "validate-1", workspaceRef: "app-1", input: { baselineEvidenceRefs: ["ev-base"], targetEvidenceRefs: ["ev-target"], requiresManual: true } });
  assert.equal(response.status, "FAILED");
  assert.equal(response.evidenceRefs.length, 0);
});

test("frontend lifecycle advances exactly one state and rejects skipped gates", () => {
  assert.equal(advanceFrontendState("DISCOVERY", "BASELINE_CAPTURING"), "BASELINE_CAPTURING");
  assert.throws(() => advanceFrontendState("DISCOVERY", "TARGET_PLANNING"), /exactly one stage/);
});

test("UX redesign planning is evidence-producing but policy-blocked without named approval", () => {
  const engine = new FrontendClientEngine();
  const response = engine.plan({ organizationId: "org-1", snapshotId: "snap-1", idempotencyKey: "plan-ux",
    workspaceRef: "app-1", input: { inventory: inventory(["REACT"]), target: { ...target, mode: "UX_REDESIGN" } } });
  assert.equal(response.status, "FAILED");
  assert.equal(response.error?.errorCode, "FRONTEND_PLAN_BLOCKED");
  assert.equal(response.evidenceRefs.length, 1);
  assert.equal(response.result.customerCodeExecuted, false);
});

test("UI graph separates routes, components, permissions and dynamic uncertainty", () => {
  const graph = buildUiSemanticGraph("app-1", { "src/Admin.tsx": "function Admin(){ return <div/> }; const route={path:'/admin', permission:'ADMIN', component: selectedComponent};" });
  assert.equal(graph.routes[0]?.path, "/admin");
  assert.deepEqual(graph.routes[0]?.requiredPermissions, ["ADMIN"]);
  assert.ok(graph.findings.some(value => value.code === "DYNAMIC_UI_DEPENDENCY"));
});

test("six Batch 14 schema fixtures are versioned and satisfy declared required fields", () => {
  const engineRoot = process.cwd();
  const repositoryRoot = resolve(engineRoot, "../..");
  const matrix = JSON.parse(readFileSync(resolve(engineRoot, "test-fixtures/fixture-matrix.json"), "utf8")) as {
    fixtures: Array<{ schema: string; instance: string }>;
  };
  assert.equal(matrix.fixtures.length, 6);
  for (const item of matrix.fixtures) {
    const schema = JSON.parse(readFileSync(resolve(repositoryRoot, item.schema), "utf8")) as {
      $schema: string; required: string[];
    };
    const instance = JSON.parse(readFileSync(resolve(engineRoot, "test-fixtures", item.instance), "utf8")) as Record<string, unknown>;
    assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema");
    for (const property of schema.required) assert.ok(property in instance, `${item.instance} missing ${property}`);
  }
});

test("acceptance fixture declares all 22 scenarios exactly once", () => {
  const fixture = JSON.parse(readFileSync(resolve(process.cwd(), "test-fixtures/batch14-acceptance-scenarios.json"), "utf8")) as {
    scenarios: Array<{ id: number }>;
  };
  assert.deepEqual(fixture.scenarios.map(value => value.id), Array.from({ length: 22 }, (_, index) => index + 1));
});

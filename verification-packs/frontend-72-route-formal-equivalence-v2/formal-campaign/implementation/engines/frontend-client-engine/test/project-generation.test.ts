import test from "node:test";
import assert from "node:assert/strict";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

import { discoverWorkspace } from "../src/analyzer.js";
import { FrontendClientEngine } from "../src/engine.js";
import {
  generateUiProject,
  uiProjectGenerationCapabilities,
  validateUiProjectGenerationRequest,
} from "../src/project-generation.js";
import {
  uiConversionRoutes,
  uiTargetProfiles,
} from "../src/project-profiles.js";
import type {
  UiFrameworkId,
  UiIrNode,
  UiProjectGenerationRequest,
} from "../src/project-types.js";

function node(id: string, references: readonly string[] = []): UiIrNode {
  return { id, name: id, kind: "contract", references, sourceRefs: [`source/${id}.txt:1`] };
}

function request(targetFramework: UiFrameworkId = "react"): UiProjectGenerationRequest {
  const source = targetFramework === "vue2"
    ? { framework: "react" as const, version: "19.2.8", platform: "WEB" as const }
    : { framework: "vue2" as const, version: "2.7.16", platform: "WEB" as const };
  return {
    schemaVersion: "1.0",
    projectName: `generated-${targetFramework.replaceAll("-", "")}`,
    applicationId: "generated.application",
    title: "生成工作台",
    source,
    targetFramework,
    packageName: "generated_application",
    bundleId: "io.elmos.generatedapplication",
    uiIr: {
      schemaVersion: "1.0",
      sourceSnapshotDigest: `sha256:${"a".repeat(64)}`,
      routes: [{
        ...node("route.home", ["component.home"]),
        path: "/",
        componentId: "component.home",
        requiresAuth: false,
        deepLink: true,
      }],
      views: [node("view.home", ["component.home"])],
      components: [{
        ...node("component.home", ["state.home"]),
        text: "从统一 UI IR 生成的首页。",
        accessibilityRole: "main",
      }],
      states: [node("state.home")],
      actions: [node("action.open")],
      effects: [node("effect.load")],
      forms: [node("form.search")],
      bindings: [node("binding.search", ["form.search"])],
      permissions: [node("permission.public")],
      resources: [node("resource.api")],
      designTokens: [node("token.brand")],
      accessibility: [node("a11y.main", ["component.home"])],
      nativeBoundaries: [],
      unknowns: [],
    },
  };
}

test("nine exact target profiles create a complete 72-route directed matrix", () => {
  const profiles = uiTargetProfiles();
  const routes = uiConversionRoutes();
  assert.equal(profiles.length, 9);
  assert.equal(routes.length, profiles.length * (profiles.length - 1));
  assert.equal(new Set(routes.map(route => route.routeId)).size, routes.length);
  assert.ok(routes.every(route => route.source !== route.target));
  assert.ok(routes.every(route => route.semanticConversionEvidence === "NOT_RUN"));
  assert.ok(routes.every(route => route.runtimeEvidence === "NOT_RUN"));
  assert.ok(routes.every(route => route.certification === "NOT_CERTIFIED"));
});

test("every core target generates deterministic project and configuration files", () => {
  for (const profile of uiTargetProfiles()) {
    const first = generateUiProject(request(profile.id));
    const second = generateUiProject(request(profile.id));
    assert.equal(first.contentDigest, second.contentDigest, profile.id);
    assert.deepEqual(first.files, second.files, profile.id);
    for (const file of profile.requiredProjectFiles) {
      assert.ok(file in first.files, `${profile.id} omitted ${file}`);
    }
    assert.ok("elmos.ui-migration.json" in first.files);
    assert.ok("ui-ir/model.json" in first.files);
    assert.ok("target-profile/profile.json" in first.files);
    assert.ok(".github/workflows/generated-ui-quality.yml" in first.files);
    assert.equal(first.verification.targetBuild, "NOT_RUN");
    assert.equal(first.verification.certification, "NOT_CERTIFIED");
    assert.doesNotMatch(profile.frameworkVersion, /latest|\*|\^|~|[xX]$/);
  }
});

test("Flutter widget test uses the unique bounded route contract without an unused app import", () => {
  const files = generateUiProject(request("flutter")).files;
  const widgetTest = files["test/widget_test.dart"]!;
  assert.doesNotMatch(widgetTest, /\/main\.dart';/);
  assert.match(widgetTest, /\/elmos_bounded_navigation\.dart';/);
  assert.match(widgetTest, /elmosBoundedRoutes\.map\(\(raw\) => elmosRoute\(raw\)\.path\)/);
  assert.match(
    files["lib/elmos_bounded_navigation.dart"]!,
    /elmosBoundedRoutes = elmosBoundedNavigation\['routes'\]! as List<Object\?>;/,
  );
});

test("generation validates direction, routes, source versions, and UI IR references", () => {
  assert.throws(
    () => validateUiProjectGenerationRequest({ ...request(), targetFramework: "vue2" }),
    /must differ/,
  );
  assert.throws(
    () => validateUiProjectGenerationRequest({ ...request(), source: { framework: "vue2", version: "latest", platform: "WEB" } }),
    /source.version is invalid/,
  );
  assert.throws(
    () => validateUiProjectGenerationRequest({ ...request(), source: { framework: "vue2", version: "2.7.15", platform: "WEB" } }),
    /source.version must equal 2.7.16/,
  );
  assert.throws(
    () => validateUiProjectGenerationRequest({ ...request(), source: { framework: "vue2", version: "2.7.16", platform: "IOS" } }),
    /source.platform is not supported by vue2/,
  );
  const unsafe = request();
  assert.throws(
    () => validateUiProjectGenerationRequest({
      ...unsafe,
      uiIr: {
        ...unsafe.uiIr,
        routes: [{ ...unsafe.uiIr.routes[0]!, path: "/../private" }],
      },
    }),
    /escapes its navigation scope/,
  );
  assert.throws(
    () => validateUiProjectGenerationRequest({
      ...unsafe,
      uiIr: {
        ...unsafe.uiIr,
        actions: [{ ...unsafe.uiIr.actions[0]!, references: ["missing.node"] }],
      },
    }),
    /unresolved/,
  );
});

test("capabilities distinguish static project generation from runtime evidence", () => {
  const capabilities = uiProjectGenerationCapabilities();
  assert.equal(capabilities.directedRouteCount, 72);
  assert.equal(capabilities.generation, "STATIC_PROJECT_AND_CONFIGURATION_READY");
  assert.equal(capabilities.runtimeEvidence, "NOT_RUN");
  assert.equal(capabilities.certification, "NOT_CERTIFIED");
  assert.ok(Array.isArray(capabilities.recommendedExtensions));
});

test("engine returns content-addressed project output without executing customer code", () => {
  const engine = new FrontendClientEngine();
  const response = engine.generateProject({
    organizationId: "org-generation",
    snapshotId: "snapshot-generation",
    idempotencyKey: "generate-react",
    workspaceRef: "workspace-generation",
    input: { project: request("react") },
  });
  assert.equal(response.status, "SUCCEEDED");
  assert.equal(response.result.customerCodeExecuted, false);
  assert.equal(response.evidenceRefs.length, 1);
  assert.match(response.evidenceRefs[0] ?? "", /^artifact:\/\/frontend-project\/[a-f0-9]{64}$/);

  const rejected = engine.generateProject({
    organizationId: "org-generation",
    snapshotId: "snapshot-generation",
    idempotencyKey: "generate-invalid",
    workspaceRef: "workspace-generation",
    input: { project: { ...request("react"), targetFramework: "vue2" } },
  });
  assert.equal(rejected.error?.errorCode, "FRONTEND_PROJECT_GENERATION_REJECTED");
  assert.doesNotMatch(rejected.error?.message ?? "", /generated-|-react|customer/i);
});

test("workspace discovery recognizes Svelte, React Native, Flutter, and Harmony ArkUI", () => {
  assert.deepEqual(
    discoverWorkspace("svelte", {
      "package.json": '{"dependencies":{"svelte":"5.56.8"}}',
      "package-lock.json": "{}",
      "src/App.svelte": "<main />",
    }).frameworks,
    ["SVELTE"],
  );
  assert.ok(discoverWorkspace("rn", {
    "package.json": '{"dependencies":{"react":"19.2.3","react-native":"0.86.0"}}',
    "package-lock.json": "{}",
    "App.tsx": 'import { View } from "react-native"; export function App(){ return <View/>; }',
  }).frameworks.includes("REACT_NATIVE"));
  assert.ok(discoverWorkspace("flutter", {
    "pubspec.yaml": "dependencies:\n  flutter:\n    sdk: flutter\n",
    "pubspec.lock": "",
    "lib/main.dart": "class App extends StatelessWidget {}",
  }).frameworks.includes("FLUTTER"));
  const harmony = discoverWorkspace("harmony", {
    "oh-package.json5": "{}",
    "oh-package-lock.json5": "{}",
    "entry/src/main/ets/pages/Index.ets": "@Entry @Component struct Index {}",
  });
  assert.ok(harmony.frameworks.includes("HARMONY_ARKUI"));
  assert.ok(harmony.platforms.includes("HARMONYOS"));
});

test("CLI materializes a create-only project and refuses non-empty output", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-ui-project-"));
  try {
    const input = join(root, "request.json");
    const output = join(root, "output");
    writeFileSync(input, JSON.stringify(request("react")), "utf8");
    const cli = resolve(process.cwd(), "dist/src/project-cli.js");
    const first = spawnSync(process.execPath, [cli, input, output], { encoding: "utf8" });
    assert.equal(first.status, 0, first.stderr);
    const report = JSON.parse(readFileSync(join(output, "materialization-report.json"), "utf8")) as {
      lockfile: string;
      targetBuild: string;
      certification: string;
    };
    assert.equal(report.lockfile, "NOT_RUN");
    assert.equal(report.targetBuild, "NOT_RUN");
    assert.equal(report.certification, "NOT_CERTIFIED");
    const repositoryRoot = resolve(process.cwd(), "../..");
    const validator = spawnSync(
      "python3",
      [
        resolve(repositoryRoot, "scripts/batch32/validate_ui_ir.py"),
        join(output, "ui-ir/model.json"),
      ],
      { encoding: "utf8" },
    );
    assert.equal(validator.status, 0, validator.stderr);
    assert.match(validator.stdout, /OK:/);
    const second = spawnSync(process.execPath, [cli, input, output], { encoding: "utf8" });
    assert.notEqual(second.status, 0);
    assert.match(second.stderr, /absent or empty/);
    const hostExecutionAttempt = join(root, "host-execution-attempt");
    const forbidden = spawnSync(
      process.execPath,
      [cli, input, hostExecutionAttempt, "--resolve-lockfile"],
      { encoding: "utf8" },
    );
    assert.notEqual(forbidden.status, 0);
    assert.match(forbidden.stderr, /usage: project-cli/);
    assert.equal(existsSync(hostExecutionAttempt), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

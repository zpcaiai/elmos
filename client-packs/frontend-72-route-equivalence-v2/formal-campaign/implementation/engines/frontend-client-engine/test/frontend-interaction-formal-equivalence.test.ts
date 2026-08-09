import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  boundedInteractionScenarios,
  canonicalBoundedFrontendInteractionModel,
  interactionBlockIds,
  interactionInfluenceMatrix,
  interactionScenarioIds,
  interactionSourceSpec,
  navigationCompatibilitySource,
  observeBoundedFrontendInteraction,
} from "../src/bounded-interaction-source.js";
import {
  boundedFrontendBlockObserverContracts,
  boundedFrontendRuntimeActualKeys,
  boundedInteractionConsumerPaths,
  boundedInteractionFixtureRequest,
  boundedInteractionSourceFixtureBytes,
  generateBoundedInteractionProject,
  projectBoundedFrontendRuntimeObservation,
  reduceBoundedFrontendRuntime,
  validateUiProjectGenerationRequestV2,
} from "../src/bounded-interaction-project.js";
import {
  buildInteractionSmt2,
  buildInteractionVacuitySmt2,
  interactionLeafCounterexamples,
  materializeFrontendInteractionCampaign,
  mutateInteractionModelAtPointer,
  referenceObserveBoundedInteraction,
  reliftBoundedInteractionProject,
  verifyFrontendInteractionCampaign,
} from "../src/frontend-interaction-formal-equivalence.js";
import { runFrontendSolver } from "../src/frontend-formal-equivalence.js";
import { uiConversionRoutes, uiTargetProfiles } from "../src/project-profiles.js";
import type { UiFrameworkId, UiProjectGenerationRequestV2 } from "../src/project-types.js";

function jsonClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function writeCanonicalJson(path: string, value: unknown): string {
  const bytes = `${JSON.stringify(value, null, 2)}\n`;
  writeFileSync(path, bytes, "utf8");
  return sha256Bytes(bytes);
}

function sha256Bytes(bytes: string): string {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function mutateRequest(
  request: UiProjectGenerationRequestV2,
  mutation: (draft: Record<string, unknown>) => void,
): UiProjectGenerationRequestV2 {
  const draft = jsonClone(request) as unknown as Record<string, unknown>;
  mutation(draft);
  return draft as unknown as UiProjectGenerationRequestV2;
}

test("v2 typed request validates every exact block, role graph, tuple, and source reference", () => {
  const request = boundedInteractionFixtureRequest("react");
  assert.equal(validateUiProjectGenerationRequestV2(request), request);
  const sourceLines = boundedInteractionSourceFixtureBytes(request).split("\n");
  for (const node of [
    ...request.uiIr.routes, ...request.uiIr.views, ...request.uiIr.components,
    request.uiIr.componentTemplate, request.uiIr.stateManagement, request.uiIr.actionEvent,
    request.uiIr.effectLifecycle, request.uiIr.formBindingValidation, request.uiIr.apiNetwork,
    request.uiIr.identityPermission, request.uiIr.renderingHydration, request.uiIr.accessibilityFocus,
    request.uiIr.i18nThemeResponsive, request.uiIr.nativePlatform,
  ]) {
    const line = Number(node.sourceRefs[0]!.split(":").at(-1));
    assert.match(sourceLines[line - 1]!, new RegExp(`"id": "${node.id.replaceAll(".", "\\.")}"`));
  }
  const ir = (draft: Record<string, unknown>) => draft.uiIr as Record<string, unknown>;
  const blockMutations: readonly [string, string, unknown][] = [
    ["componentTemplate", "templateKind", "STATIC"], ["stateManagement", "maximum", 3],
    ["actionEvent", "keyboardSubmit", "Space"], ["effectLifecycle", "cleanupEffect", "NONE"],
    ["formBindingValidation", "minimumLength", 0], ["apiNetwork", "retry", "ALWAYS"],
    ["identityPermission", "tenantIsolation", "NONE"], ["renderingHydration", "duplicateEffectsAllowed", true],
    ["accessibilityFocus", "liveRegion", "off"], ["i18nThemeResponsive", "compactBreakpoint", 0],
    ["nativePlatform", "capability", "NONE"],
  ];
  for (const [block, field, value] of blockMutations) {
    assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
      (ir(draft)[block] as Record<string, unknown>)[field] = value;
    })), /literal contract drifted|profile drifted/, block);
    assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
      (ir(draft)[block] as Record<string, unknown>).extra = true;
    })), /exact keys|shape drifted/, `${block}:extra`);
    assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
      delete (ir(draft)[block] as Record<string, unknown>)[field];
    })), /exact keys|shape drifted/, `${block}:missing`);
  }
  assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
    (ir(draft).componentTemplate as Record<string, unknown>).extra = true;
  })), /exact keys|shape drifted/);
  assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
    delete (ir(draft).apiNetwork as Record<string, unknown>).method;
  })), /exact keys|shape drifted/);
  assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
    (ir(draft).stateManagement as Record<string, unknown>).references = ["block.action"];
  })), /role dependency graph drifted/);
  assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
    (ir(draft).nativePlatform as Record<string, unknown>).sourceRefs = ["../escape.ts:1"];
  })), /sourceRef is unsafe/);
  assert.throws(() => validateUiProjectGenerationRequestV2(mutateRequest(request, draft => {
    const routes = ir(draft).routes as Record<string, unknown>[]; routes[0]!.extra = "forbidden";
  })), /shape drifted/);
});

test("all nine v2 generated projects re-lift the sole source contract and direct navigation identity", () => {
  const digests = new Set<string>();
  for (const profile of uiTargetProfiles()) {
    const request = boundedInteractionFixtureRequest(profile.id);
    const project = generateBoundedInteractionProject(request);
    const relift = reliftBoundedInteractionProject(profile.id, project.files);
    const canonical = canonicalBoundedFrontendInteractionModel(request);
    assert.deepEqual(relift.model, canonical, profile.id);
    assert.equal(relift.consumer_binding.strict_generated_grammar, true, profile.id);
    assert.equal(relift.consumer_binding.navigation_identity_projection, true, profile.id);
    assert.equal(Object.keys(relift.block_digests).length, 12, profile.id);
    assert.ok(Object.keys(relift.spans).every(pointer => pointer === "" || pointer.startsWith("/")), profile.id);
    assert.equal(project.files[interactionSourceSpec(profile.id).compatibilityPath], navigationCompatibilitySource(profile.id));
    digests.add(relift.model_digest);
  }
  assert.equal(digests.size, 1);
  assert.equal(uiConversionRoutes().length, 72);
});

test("strict v2 relift rejects dead/static/unused consumer, duplicate contract, and copied routes for all profiles", () => {
  for (const profile of uiTargetProfiles()) {
    const project = generateBoundedInteractionProject(boundedInteractionFixtureRequest(profile.id));
    const consumerPath = boundedInteractionConsumerPaths(profile.id).at(-1)!;
    assert.throws(() => reliftBoundedInteractionProject(profile.id, {
      ...project.files, [consumerPath]: `${project.files[consumerPath]}\nconst ELMOS_UNUSED = "state effect form auth api hydration a11y i18n native";\n`,
    }), /consumer grammar drifted/, `${profile.id} accepted unused consumer bytes`);
    const spec = interactionSourceSpec(profile.id);
    assert.throws(() => reliftBoundedInteractionProject(profile.id, {
      ...project.files, [spec.compatibilityPath]: `${project.files[spec.compatibilityPath]}\n// dead compatibility decoy\n`,
    }), /direct identity projection/, `${profile.id} accepted compatibility drift`);
    const duplicatePath = profile.id === "flutter" ? "lib/duplicate.dart" : profile.id === "harmony-arkui" ? "entry/src/main/ets/duplicate.ets" : "src/duplicate.ts";
    assert.throws(() => reliftBoundedInteractionProject(profile.id, {
      ...project.files, [duplicatePath]: profile.id === "flutter" ? "final elmosFrontendInteraction = {};\n" : "const ELMOS_FRONTEND_INTERACTION = {};\n",
    }), /duplicate bounded interaction contract literal/, `${profile.id} accepted a second contract`);
  }
});

test("generated framework consumers reject circular observers and expose reachable local runtime bindings", () => {
  const frameworkTokens: Readonly<Record<UiFrameworkId, readonly string[]>> = {
    react: ["useState", "useEffect", "<ElmosInteractionPanel />", "REACT_COMPONENT_ACTUAL_EVENTS"],
    vue2: ["beforeDestroy", "this.$set", "<ElmosInteractionPanel />", "VUE2_COMPONENT_ACTUAL_EVENTS"],
    vue3: ["onBeforeUnmount", "rows.value", "<ElmosInteractionPanel />", "VUE3_COMPONENT_ACTUAL_EVENTS"],
    jquery: [".on('click.elmos'", ".data('elmosScenario'", "JQUERY_EVENTS_AND_DATA"],
    angular: ["signal<", "ngOnDestroy", "<elmos-interaction />", "ANGULAR_COMPONENT_ACTUAL_EVENTS"],
    svelte: ["onDestroy", "rows = { ...rows", "<ElmosInteractionPanel />", "SVELTE_COMPONENT_ACTUAL_EVENTS"],
    "react-native": ["useState", "accessibilityLabel={`scenario:", "REACT_NATIVE_COMPONENT_ACTUAL_EVENTS"],
    flutter: ["StatefulWidget", "elmosNativeObserverDeclarations", "ValueKey<String>('block:$id:${declaration['block_id']}')"],
    "harmony-arkui": ["@State interactionDeclarations", "elmosArkObserverDeclarations", "BLOCK_SPECIFIC_RUNTIME_OBSERVED"],
  };
  for (const profile of uiTargetProfiles()) {
    const project = generateBoundedInteractionProject(boundedInteractionFixtureRequest(profile.id));
    const source = boundedInteractionConsumerPaths(profile.id).map(path => project.files[path] ?? "").join("\n");
    assert.doesNotMatch(source, /elmosObserveInteraction|ELMOS_INTERACTION_OBSERVATIONS|observeBoundedFrontendInteraction|elmosReduceRuntime|elmosProjectRuntimeObservation/, profile.id);
    assert.match(source, /block-specific-runtime-observation-v1|declaration-only observer contract/i, `${profile.id}:observer-protocol`);
    assert.match(source, /BLOCK_SPECIFIC_RUNTIME_OBSERVED/, `${profile.id}:runtime-source`);
    for (const token of frameworkTokens[profile.id]) assert.ok(source.includes(token), `${profile.id}:${token}`);
    const consumerPath = boundedInteractionConsumerPaths(profile.id).at(-1)!;
    assert.throws(() => reliftBoundedInteractionProject(profile.id, {
      ...project.files,
      [consumerPath]: `${project.files[consumerPath]}\n// circular decoy only: elmosObserveInteraction(ELMOS_INTERACTION_SCENARIOS[0])\n`,
    }), /consumer grammar drifted/, `${profile.id}:circular-decoy`);
  }
});

test("all six web consumers execute native invalid and configured keyboard-submit paths", () => {
  const contracts: Readonly<Record<"react" | "vue2" | "vue3" | "jquery" | "angular" | "svelte", Readonly<{ path: string; invalid: string; input: string; submitType: string; pending: string }>>> = {
    react: { path: "src/ElmosInteractionPanel.tsx", invalid: "onInvalid={invalidForm}", input: "onInput={syncValidity}", submitType: "type={isSubmitScenario(scenario) ? 'submit' : 'button'}", pending: "if (isSubmitScenario(scenario)) pending.current = scenario" },
    vue2: { path: "src/ElmosInteractionPanel.vue", invalid: "addEventListener('invalid', this.invalidForm)", input: "addEventListener('input', this.syncValidity)", submitType: `:type="isSubmitScenario(scenario) ? 'submit' : 'button'"`, pending: "if (this.isSubmitScenario(scenario)) this.pending = scenario" },
    vue3: { path: "src/ElmosInteractionPanel.vue", invalid: '@invalid="invalidForm"', input: '@input="syncValidity"', submitType: `:type="isSubmitScenario(scenario) ? 'submit' : 'button'"`, pending: "if (isSubmitScenario(scenario)) pending.value = scenario" },
    jquery: { path: "src/elmos-interaction-consumer.ts", invalid: "addEventListener('invalid', invalidForm, true)", input: "form.on('input.elmos', '#elmos-query', syncValidity)", submitType: "type: isSubmitScenario(scenario) ? 'submit' : 'button'", pending: "if (isSubmitScenario(scenario)) pending = scenario" },
    angular: { path: "src/elmos-interaction.component.ts", invalid: '(invalid)="invalidForm($event)"', input: '(input)="syncValidity($event)"', submitType: `[type]="isSubmitScenario(scenario) ? 'submit' : 'button'"`, pending: "if (this.isSubmitScenario(scenario)) this.pending = scenario" },
    svelte: { path: "src/ElmosInteractionPanel.svelte", invalid: "oninvalid={invalidForm}", input: "oninput={syncValidity}", submitType: 'type={isSubmitScenario(scenario) ? "submit" : "button"}', pending: "if (isSubmitScenario(scenario)) pending = scenario" },
  };
  for (const [profile, contract] of Object.entries(contracts) as [keyof typeof contracts, (typeof contracts)[keyof typeof contracts]][]) {
    const project = generateBoundedInteractionProject(boundedInteractionFixtureRequest(profile));
    const consumer = project.files[contract.path]!;
    const runtimePath = profile === "vue2" ? "src/elmos-interaction-runtime.js" : "src/elmos-interaction-runtime.ts";
    const runtime = project.files[runtimePath]!;
    assert.ok(consumer.includes(contract.invalid), `${profile}:native-invalid-handler`);
    assert.ok(consumer.includes(contract.input), `${profile}:input-validity-sync`);
    assert.ok(consumer.includes("scenario.input.event === 'SUBMIT' || scenario.input.keyboardKey ==="), `${profile}:configured-keyboard-submit-predicate`);
    assert.ok(consumer.includes(contract.submitType), `${profile}:native-submit-control`);
    assert.ok(consumer.includes(contract.pending), `${profile}:pending-scenario-preserved`);
    assert.match(consumer, /data-elmos-invalid-event/);
    assert.doesNotMatch(consumer, /noValidate|novalidate|formNoValidate|dispatchEvent\(new Event\(['"]invalid['"]/);
    assert.match(runtime, /queryElement\.validity\.valid/, `${profile}:side-effect-free-validity-read`);
    assert.doesNotMatch(runtime, /queryElement\.checkValidity\(\)/, `${profile}:programmatic-invalid-event`);
    assert.throws(() => reliftBoundedInteractionProject(profile, {
      ...project.files,
      [contract.path]: consumer.replace(contract.invalid, contract.invalid.replace("invalidForm", "disconnectedInvalidForm")),
    }), /consumer grammar drifted/, `${profile}:disconnected-native-invalid-handler`);
    assert.throws(() => reliftBoundedInteractionProject(profile, {
      ...project.files,
      [runtimePath]: runtime.replace("queryElement.validity.valid", "queryElement.checkValidity()"),
    }), /consumer grammar drifted/, `${profile}:programmatic-invalid-event`);
    assert.throws(() => reliftBoundedInteractionProject(profile, {
      ...project.files,
      [contract.path]: consumer.replace("scenario.input.keyboardKey ===", "scenario.input.keyboardKey !=="),
    }), /consumer grammar drifted/, `${profile}:keyboard-submit-predicate-drift`);
    assert.throws(() => reliftBoundedInteractionProject(profile, {
      ...project.files,
      [contract.path]: consumer.replace(contract.submitType, contract.submitType.replace("isSubmitScenario", "isSubmitEventOnly")),
    }), /consumer grammar drifted/, `${profile}:disconnected-native-submit-control`);
  }
});

test("Vue2 route-owned boolean data attributes preserve explicit false strings", () => {
  const project = generateBoundedInteractionProject(boundedInteractionFixtureRequest("vue2"));
  const pagePath = "src/views/GeneratedPage.vue";
  const page = project.files[pagePath]!;
  const app = project.files["src/App.vue"]!;
  for (const token of [
    `:data-elmos-requires-auth="page && page.requiresAuth ? 'true' : 'false'"`,
    `:data-elmos-deep-link="page && page.deepLink ? 'true' : 'false'"`,
    `:data-requires-auth="page && page.requiresAuth ? 'true' : 'false'"`,
    `:data-deep-link="page && page.deepLink ? 'true' : 'false'"`,
  ]) assert.ok(page.includes(token), `GeneratedPage:${token}`);
  for (const token of [
    `:data-requires-auth="route.requiresAuth ? 'true' : 'false'"`,
    `:data-deep-link="route.deepLink ? 'true' : 'false'"`,
  ]) assert.ok(app.includes(token), `App:${token}`);
  assert.doesNotMatch(page, /:data-(?:elmos-)?requires-auth="page && page\.requiresAuth"/);
  assert.doesNotMatch(app, /:data-requires-auth="route\.requiresAuth"/);
  assert.throws(() => reliftBoundedInteractionProject("vue2", {
    ...project.files,
    [pagePath]: page.replace(
      `:data-requires-auth="page && page.requiresAuth ? 'true' : 'false'"`,
      ':data-requires-auth="page && page.requiresAuth"',
    ),
  }), /consumer grammar drifted/, "Vue2 accepted a boolean false attribute that the DOM removes");
});

test("independent runtime reducer and strict channel projection cover exact 18 by 12 observations", () => {
  const model = canonicalBoundedFrontendInteractionModel(boundedInteractionFixtureRequest("react"));
  for (const scenario of boundedInteractionScenarios(model)) {
    const runtime = reduceBoundedFrontendRuntime(model, scenario);
    assert.deepEqual(runtime, observeBoundedFrontendInteraction(model, scenario), scenario.scenarioId);
    for (const channel of ["browser", "android", "ios", "harmonyos"] as const) {
      const projected = projectBoundedFrontendRuntimeObservation(runtime, channel);
      assert.deepEqual(Object.keys(projected), interactionBlockIds, `${scenario.scenarioId}:${channel}:blocks`);
      for (const blockId of interactionBlockIds) {
        assert.deepEqual(Object.keys(projected[blockId]!).sort(), [...boundedFrontendRuntimeActualKeys[blockId]].sort(), `${scenario.scenarioId}:${channel}:${blockId}`);
      }
      if (channel === "browser") assert.deepEqual(projected["native-platform"], {
        boundary: runtime.blocks["native-platform"].boundary,
        lifecycle: runtime.blocks["native-platform"].lifecycle,
        attempted: false,
        permission: runtime.blocks["native-platform"].permission,
        available: false,
        outcome: "NOT_ATTEMPTED",
        recovery: runtime.blocks["native-platform"].recovery,
      });
    }
  }
  const nativeScenario = boundedInteractionScenarios(model).find(value => value.scenarioId === "NATIVE_FOREGROUND_PERMISSION_GRANTED_OPEN");
  assert.ok(nativeScenario);
  assert.equal(projectBoundedFrontendRuntimeObservation(reduceBoundedFrontendRuntime(model, nativeScenario), "android")["native-platform"]?.attempted, true);
});

test("block-specific observer declarations and generated runtime dataflow fail closed", () => {
  const project = generateBoundedInteractionProject(boundedInteractionFixtureRequest("react"));
  const runtimePath = "src/elmos-interaction-runtime.ts";
  const runtime = project.files[runtimePath]!;
  assert.doesNotMatch(runtime, /elmosReduceRuntime|elmosProjectRuntimeObservation/);
  assert.deepEqual(Object.keys(boundedFrontendBlockObserverContracts), interactionBlockIds);
  assert.deepEqual(interactionBlockIds.filter(blockId => boundedFrontendBlockObserverContracts[blockId].browser_status === "PASSED"), [
    "route-navigation-deeplink-404", "component-template-view", "state-management", "action-event",
    "form-binding-validation", "accessibility-focus", "i18n-theme-responsive",
  ]);
  assert.deepEqual(interactionBlockIds.filter(blockId => boundedFrontendBlockObserverContracts[blockId].browser_status === "NOT_RUN"), [
    "effect-lifecycle", "api-network", "identity-permission", "rendering-hydration", "native-platform",
  ]);
  assert.match(boundedFrontendBlockObserverContracts["api-network"].browser_reason, /timeout, retry, tenant cache, and unmount cancellation/);
  assert.deepEqual(interactionBlockIds.filter(blockId => boundedFrontendBlockObserverContracts[blockId].native_status === "NOT_RUN"), ["api-network"]);
  assert.match(boundedFrontendBlockObserverContracts["api-network"].native_reason, /timeout, retry, tenant cache, and unmount cancellation/);
  const consumerPath = "src/ElmosInteractionPanel.tsx";
  const consumer = project.files[consumerPath]!;
  const appPath = "src/App.tsx";
  const app = project.files[appPath]!;
  const mutations: readonly [string, string, string, string][] = [
    [runtimePath, "history.pushState({}, '', selected.path)", "void selected.path", "disconnected-router"],
    [runtimePath, "counterAfter", "counterDisconnected", "disconnected-state-dataflow"],
    [consumerPath, 'data-elmos-ready="true"', 'data-elmos-ready="false"', "false-ready-flag"],
    [consumerPath, "</form>", '<article data-scenario-id="EXTRA_SCENARIO"></article></form>', "extra-scenario"],
    [consumerPath, "data-elmos-state-measurement", "data-elmos-static-state", "static-measurement"],
    [appPath, "data-elmos-route-id={route.id}", 'data-elmos-route-id="STATIC"', "static-rendered-route"],
  ];
  for (const [path, token, replacement, name] of mutations) {
    const source = project.files[path]!;
    assert.ok(source.includes(token), `${name}:fixture token`);
    assert.throws(() => reliftBoundedInteractionProject("react", { ...project.files, [path]: source.replace(token, replacement) }), /consumer grammar drifted/, name);
  }
  const flutter = generateBoundedInteractionProject(boundedInteractionFixtureRequest("flutter"));
  assert.ok(flutter.files["web/index.html"]); assert.ok(flutter.files["platform-scaffold-contract.json"]); assert.ok(flutter.files["integration_test/bounded_interaction_test.dart"]?.includes("for (final blockId in elmosRuntimeBlockIds)"));
  assert.doesNotMatch(flutter.files["platform-scaffold-contract.json"]!, /"materialization_status": "PASSED"/);
  assert.match(flutter.files["lib/elmos_interaction_consumer.dart"]!, /runtimeChannel != 'browser'/);
  assert.match(flutter.files["lib/elmos_interaction_consumer.dart"]!, /:sequence:\$\{sequences\[id\]/);
  assert.match(flutter.files["lib/elmos_interaction_consumer.dart"]!, /SingleChildScrollView/);
  assert.match(flutter.files["lib/main.dart"]!, /Material\(child: ElmosInteractionPanel/);
  assert.match(flutter.files["integration_test/bounded_interaction_test.dart"]!, /block_declarations/);
  assert.match(flutter.files["integration_test/bounded_interaction_test.dart"]!, /keys, isNot\(contains\('actual'\)\)/);
  assert.match(flutter.files["test_driver/integration_test.dart"]!, /BLOCK_SPECIFIC_RUNTIME_OBSERVED/);
  assert.match(flutter.files["test_driver/integration_test.dart"]!, /tracePath\.tmp\.\$pid/);
  const dartConsumer = "lib/elmos_interaction_consumer.dart";
  assert.doesNotMatch(flutter.files[dartConsumer]!, /elmosReduceRuntime|elmosProjectRuntimeObservation/);
  assert.throws(() => reliftBoundedInteractionProject("flutter", { ...flutter.files, [dartConsumer]: flutter.files[dartConsumer]!.replace("BLOCK_SPECIFIC_RUNTIME_OBSERVED", "SELF_REPORTED_REDUCER_JSON") }), /consumer grammar drifted/);
  assert.match(flutter.files["lib/elmos_interaction_runtime.dart"]!, /nativeStatus == 'PASSED'/);
  assert.match(flutter.files["lib/elmos_interaction_runtime.dart"]!, /single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation/);
  assert.doesNotMatch(flutter.files[dartConsumer]!, /if \(apiObserved\) 'api-network'/);
  const reactNative = generateBoundedInteractionProject(boundedInteractionFixtureRequest("react-native"));
  assert.match(reactNative.files["src/elmos-interaction-runtime.ts"]!, /spec\.native_status === 'PASSED'/);
  assert.match(reactNative.files["src/elmos-interaction-runtime.ts"]!, /single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation/);
  assert.doesNotMatch(reactNative.files["src/elmos-interaction-consumer.tsx"]!, /observedBlocks = \[[^\]]*'api-network'/);
  assert.doesNotMatch(reactNative.files["src/elmos-interaction-consumer.tsx"]!, /dataSet=/);
  assert.match(reactNative.files["src/elmos-interaction-consumer.tsx"]!, /accessibilityLabel=\{`declaration:/);
  const nativeScaffold = JSON.parse(reactNative.files["platform-scaffold-contract.json"]!) as Record<string, unknown>;
  assert.equal(nativeScaffold.kind, "expo-react-native-platform-scaffold-materialization-contract");
  assert.equal(nativeScaffold.materialization_status, "NOT_RUN");
  assert.equal(nativeScaffold.android_runtime_status, "NOT_RUN");
  assert.equal(nativeScaffold.ios_runtime_status, "NOT_RUN");
  assert.deepEqual(nativeScaffold.required_captured_outputs, ["package-lock.json", "android", "ios"]);
  const ark = generateBoundedInteractionProject(boundedInteractionFixtureRequest("harmony-arkui"));
  assert.match(ark.files["entry/src/main/ets/elmos-interaction-runtime.ets"]!, /spec\.native_status === 'PASSED'/);
  assert.match(ark.files["entry/src/main/ets/elmos-interaction-runtime.ets"]!, /single native adapter call does not prove timeout, retry, tenant cache, and unmount cancellation/);
});

test("18 finite scenarios cover every non-echo leaf and the separate reference reducer agrees", () => {
  const model = canonicalBoundedFrontendInteractionModel(boundedInteractionFixtureRequest("react"));
  const scenarios = boundedInteractionScenarios(model);
  assert.equal(scenarios.length, 18);
  assert.deepEqual(scenarios.map(value => value.scenarioId), interactionScenarioIds);
  for (const scenario of scenarios) {
    assert.deepEqual(referenceObserveBoundedInteraction(model, scenario), observeBoundedFrontendInteraction(model, scenario), scenario.scenarioId);
  }
  const byId = Object.fromEntries(scenarios.map(scenario => [scenario.scenarioId, observeBoundedFrontendInteraction(model, scenario)]));
  assert.equal(byId.TENANT_ISOLATION_MISMATCH_DENIED?.blocks["identity-permission"].authorized, false);
  assert.equal(byId.API_NETWORK_ERROR?.blocks["api-network"].outcome, "ERROR");
  assert.equal(byId.HYDRATE_MISMATCH_ERROR?.blocks["rendering-hydration"].status, "RENDER_ERROR");
  assert.equal(byId.NATIVE_FOREGROUND_PERMISSION_GRANTED_OPEN?.blocks["native-platform"].outcome, "OPENED");
  assert.equal(byId.LOCALE_EN_US_WIDE_721?.blocks["i18n-theme-responsive"].columns, 2);
  assert.equal(byId.BREAKPOINT_720_COMPACT?.blocks["i18n-theme-responsive"].columns, 1);
  assert.equal(byId.UNSUPPORTED_THEME_FALLBACK?.blocks["i18n-theme-responsive"].theme, "LIGHT");
  const witnesses = interactionLeafCounterexamples(model);
  assert.ok(witnesses.length > 80);
  assert.ok(witnesses.every(witness => witness.semantic_mutant_detected));
  assert.deepEqual(witnesses.filter(witness => witness.influence_class !== "DECLARATION_ECHO" && !witness.behavior_mutant_detected), []);
  assert.deepEqual(witnesses.filter(witness => witness.influence_class === "DECLARATION_ECHO" && witness.scenario_id !== null), []);
  assert.ok(interactionBlockIds.every(block => Object.keys(interactionInfluenceMatrix[block]).length > 0));
});

test("symbolic obligations are UNSAT when equal, vacuity is SAT, and each block refutes source/target/reference mutants", () => {
  const model = canonicalBoundedFrontendInteractionModel(boundedInteractionFixtureRequest("react"));
  assert.equal(runFrontendSolver(buildInteractionVacuitySmt2()).outcome, "SAT");
  assert.equal(runFrontendSolver(buildInteractionSmt2(model, model, model, model)).outcome, "UNSAT");
  const witnesses = interactionLeafCounterexamples(model);
  for (const blockId of interactionBlockIds) {
    const witness = witnesses.find(value => value.block_id === blockId && value.influence_class !== "DECLARATION_ECHO" && value.behavior_mutant_detected);
    assert.ok(witness, blockId);
    const mutant = mutateInteractionModelAtPointer(model, witness.pointer);
    assert.equal(runFrontendSolver(buildInteractionSmt2(model, mutant, model, model)).outcome, "SAT", `${blockId}:source`);
    assert.equal(runFrontendSolver(buildInteractionSmt2(model, model, mutant, model)).outcome, "SAT", `${blockId}:target`);
    assert.equal(runFrontendSolver(buildInteractionSmt2(model, model, model, mutant)).outcome, "SAT", `${blockId}:reference`);
  }
});

test("v2 campaign closes exact 9/72/12 with three-way mutations and verifies byte links fail closed", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-interaction-formal-test-"));
  try {
    const campaign = materializeFrontendInteractionCampaign(root);
    assert.equal(campaign.profile_count, 9); assert.equal(campaign.route_count, 72); assert.equal(campaign.block_count, 12);
    assert.deepEqual(campaign.counts, { PROVED_UNDER_ASSUMPTIONS: 72, REFUTED: 0, NOT_PROVED: 0 });
    const runtimeProfiles = campaign.profiles as { profile_id: UiFrameworkId; runtime_driver_contract: Record<string, unknown> }[];
    for (const profile of runtimeProfiles) {
      const driver = profile.runtime_driver_contract;
      assert.equal(driver.runtime_status, "NOT_RUN"); assert.equal(driver.independent_runtime_oracle, "NOT_RUN"); assert.equal(driver.certification, "NOT_CERTIFIED");
      assert.equal(driver.observer_protocol, "block-specific-runtime-observation-v1");
      assert.equal(driver.actual_source, "BLOCK_SPECIFIC_RUNTIME_OBSERVED");
      assert.equal(driver.self_reported_reducer_json_allowed, false);
      assert.equal(driver.legacy_runtime_observed_allowed, false);
      assert.deepEqual(driver.native_required_not_run_blocks, ["api-network"]);
      assert.equal(driver.native_route_without_real_device_channel_status, "NOT_RUN");
      assert.deepEqual(Object.keys(driver.block_observer_contracts as Record<string, unknown>), interactionBlockIds);
      assert.deepEqual(driver.block_observer_contracts, boundedFrontendBlockObserverContracts);
      assert.match(String(driver.channel_projection_contract_digest), /^sha256:[0-9a-f]{64}$/);
      const projection = driver.channel_projection_contract as { channels: Record<string, { scenarios: { scenario_id: string; blocks: Record<string, Record<string, unknown>> }[] }> };
      for (const [channel, value] of Object.entries(projection.channels)) {
        assert.equal(value.scenarios.length, 18, `${profile.profile_id}:${channel}`);
        assert.ok(value.scenarios.every(row => Object.keys(row.blocks).length === 12));
        if (channel === "browser") assert.ok(value.scenarios.every(row => row.blocks["native-platform"]?.attempted === false && row.blocks["native-platform"]?.outcome === "NOT_ATTEMPTED"));
      }
    }
    assert.deepEqual(verifyFrontendInteractionCampaign(root), []);
    const mutationPath = join(root, "mutation-campaign.json");
    const mutationOriginal = readFileSync(mutationPath, "utf8");
    const mutation = JSON.parse(mutationOriginal) as {
      mutations: { block_id: string; pointer: string; scenario_id: string; counterexample_replay: Record<string, unknown>; variants: Record<string, unknown>[] }[];
    };
    assert.equal(mutation.mutations.length, 12);
    assert.ok(mutation.mutations.every(row => row.variants.length === 3));
    assert.ok(mutation.mutations.every(row => assert.deepEqual(row.variants.map(variant => variant.variant), ["SOURCE_ONLY", "TARGET_ONLY", "REFERENCE_ONLY"]) === undefined));
    const firstMutationFormal = JSON.parse(readFileSync(join(root, String(mutation.mutations[0]!.variants[0]!.formal_input_path)), "utf8")) as Record<string, unknown>;
    assert.match(String(firstMutationFormal.canonical_block_digest), /^sha256:[0-9a-f]{64}$/);
    assert.match(String(firstMutationFormal.mutant_block_digest), /^sha256:[0-9a-f]{64}$/);
    assert.notEqual(firstMutationFormal.canonical_block_digest, firstMutationFormal.mutant_block_digest);

    const solverRoot = join(root, "solver-overrides"); mkdirSync(solverRoot);
    const recordedSolverPath = join(root, String(mutation.mutations[0]!.variants[0]!.solver_result_path));
    const recordedSolver = JSON.parse(readFileSync(recordedSolverPath, "utf8")) as Record<string, unknown>;
    const relocatedSolver = join(solverRoot, "z3"); copyFileSync(String(recordedSolver.solver_binary_realpath), relocatedSolver); chmodSync(relocatedSolver, 0o755);
    const cli = join(process.cwd(), "dist", "src", "frontend-interaction-formal-cli.js");
    const verified = spawnSync(process.execPath, [cli, "--verify", root, "--proof-profile", "bounded-frontend-interaction-v1", "--solver", relocatedSolver, "--json"], { encoding: "utf8" });
    assert.equal(verified.status, 0, verified.stderr); assert.match(verified.stdout, /"valid":true/);
    for (const args of [
      ["--verify", root],
      ["--verify", root, "--proof-profile", "bounded-navigation-v1"],
      ["--verify", root, "--proof-profile", "unknown-v9"],
    ]) assert.equal(spawnSync(process.execPath, [cli, ...args], { encoding: "utf8" }).status, 1);
    const wrongDigestSolver = join(solverRoot, "wrong", "z3"); mkdirSync(join(solverRoot, "wrong"));
    writeFileSync(wrongDigestSolver, "#!/bin/sh\nprintf 'Z3 version 4.16.0 - 64 bit\\n'\n", "utf8"); chmodSync(wrongDigestSolver, 0o755);
    assert.ok(verifyFrontendInteractionCampaign(root, { solver: { command: wrongDigestSolver } }).some(error => /locked solver identity/.test(error)));
    assert.equal(spawnSync(process.execPath, [cli, "--verify", root, "--proof-profile", "bounded-frontend-interaction-v1", "--solver", wrongDigestSolver, "--json"], { encoding: "utf8" }).status, 2);

    const campaignPath = join(root, "frontend-interaction-formal-campaign.json");
    const original = readFileSync(campaignPath, "utf8");
    const parsed = JSON.parse(original) as {
      mutation_campaign: Record<string, unknown>;
      profiles: { runtime_driver_contract: { block_observer_contracts: Record<string, Record<string, unknown>> } }[];
      routes: Record<string, unknown>[];
      block_counts: Record<string, Record<string, number>>;
    };

    const observerContractDrift = jsonClone(parsed);
    observerContractDrift.profiles[0]!.runtime_driver_contract.block_observer_contracts["api-network"]!.browser_status = "PASSED";
    observerContractDrift.profiles[0]!.runtime_driver_contract.block_observer_contracts["api-network"]!.browser_reason = "self reported reducer result";
    writeCanonicalJson(campaignPath, observerContractDrift);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /runtime driver\/projection contract drifted/.test(error)));
    writeFileSync(campaignPath, original, "utf8");

    const recordedSolverOriginal = readFileSync(recordedSolverPath, "utf8");
    const assertRecordedSolverTamperRejected = (field: string, value: unknown): void => {
      const solverDrift = JSON.parse(recordedSolverOriginal) as Record<string, unknown>; solverDrift[field] = value;
      const solverDriftDigest = writeCanonicalJson(recordedSolverPath, solverDrift);
      const mutationDrift = jsonClone(mutation); mutationDrift.mutations[0]!.variants[0]!.solver_result_digest = solverDriftDigest;
      const mutationDriftDigest = writeCanonicalJson(mutationPath, mutationDrift);
      const campaignDrift = jsonClone(parsed); campaignDrift.mutation_campaign.digest = mutationDriftDigest;
      writeCanonicalJson(campaignPath, campaignDrift);
      assert.ok(verifyFrontendInteractionCampaign(root, { solver: { command: relocatedSolver } }).some(error => /identity\/options\/output diverged/.test(error)));
      writeFileSync(recordedSolverPath, recordedSolverOriginal, "utf8");
      writeFileSync(mutationPath, mutationOriginal, "utf8");
      writeFileSync(campaignPath, original, "utf8");
    };
    assertRecordedSolverTamperRejected("solver_version", "Z3 version 0.0.0 - 64 bit");
    assertRecordedSolverTamperRejected("stdout", "unsat\n");

    const firstVariant = mutation.mutations[0]!.variants[0]!;
    const mutationFormalPath = join(root, String(firstVariant.formal_input_path));
    const mutationSmtPath = join(root, String(firstVariant.smt2_path));
    const mutationFormalOriginal = readFileSync(mutationFormalPath, "utf8");
    const mutationSmtOriginal = readFileSync(mutationSmtPath, "utf8");
    const linkedFormalDrift = JSON.parse(mutationFormalOriginal) as Record<string, unknown>;
    linkedFormalDrift.oracle_provenance = "FORGED_INDEPENDENT";
    const linkedFormalDigest = writeCanonicalJson(mutationFormalPath, linkedFormalDrift);
    const linkedSmtDrift = mutationSmtOriginal.replace(String(firstVariant.formal_input_digest), linkedFormalDigest);
    assert.notEqual(linkedSmtDrift, mutationSmtOriginal);
    writeFileSync(mutationSmtPath, linkedSmtDrift, "utf8"); const linkedSmtDigest = sha256Bytes(linkedSmtDrift);
    const linkedSolverDrift = JSON.parse(recordedSolverOriginal) as Record<string, unknown>;
    linkedSolverDrift.formal_input_digest = linkedFormalDigest;
    linkedSolverDrift.solver_input_digest = linkedSmtDigest;
    linkedSolverDrift.smt2_digest = linkedSmtDigest;
    const linkedSolverDigest = writeCanonicalJson(recordedSolverPath, linkedSolverDrift);
    const linkedMutationDrift = jsonClone(mutation);
    linkedMutationDrift.mutations[0]!.variants[0]!.formal_input_digest = linkedFormalDigest;
    linkedMutationDrift.mutations[0]!.variants[0]!.smt2_digest = linkedSmtDigest;
    linkedMutationDrift.mutations[0]!.variants[0]!.solver_result_digest = linkedSolverDigest;
    const linkedMutationDigest = writeCanonicalJson(mutationPath, linkedMutationDrift);
    const linkedCampaignDrift = jsonClone(parsed); linkedCampaignDrift.mutation_campaign.digest = linkedMutationDigest;
    writeCanonicalJson(campaignPath, linkedCampaignDrift);
    assert.ok(verifyFrontendInteractionCampaign(root, { solver: { command: relocatedSolver } }).some(error => /formal input reconstruction drifted/.test(error)));
    writeFileSync(mutationFormalPath, mutationFormalOriginal, "utf8"); writeFileSync(mutationSmtPath, mutationSmtOriginal, "utf8");
    writeFileSync(recordedSolverPath, recordedSolverOriginal, "utf8"); writeFileSync(mutationPath, mutationOriginal, "utf8"); writeFileSync(campaignPath, original, "utf8");

    const duplicateVariantMutation = jsonClone(mutation);
    duplicateVariantMutation.mutations[0]!.variants[2] = jsonClone(duplicateVariantMutation.mutations[0]!.variants[0]!);
    const duplicateVariantDigest = writeCanonicalJson(mutationPath, duplicateVariantMutation);
    const duplicateVariantCampaign = jsonClone(parsed); duplicateVariantCampaign.mutation_campaign.digest = duplicateVariantDigest;
    writeCanonicalJson(campaignPath, duplicateVariantCampaign);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /variant identity is duplicated/.test(error)));
    writeFileSync(mutationPath, mutationOriginal, "utf8"); writeFileSync(campaignPath, original, "utf8");

    const crossBlockMutation = jsonClone(mutation);
    crossBlockMutation.mutations[0]!.pointer = crossBlockMutation.mutations[1]!.pointer;
    crossBlockMutation.mutations[0]!.scenario_id = crossBlockMutation.mutations[1]!.scenario_id;
    crossBlockMutation.mutations[0]!.counterexample_replay = jsonClone(crossBlockMutation.mutations[1]!.counterexample_replay);
    const crossBlockDigest = writeCanonicalJson(mutationPath, crossBlockMutation);
    const crossBlockCampaign = jsonClone(parsed); crossBlockCampaign.mutation_campaign.digest = crossBlockDigest;
    writeCanonicalJson(campaignPath, crossBlockCampaign);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /pointer\/witness\/symbol drifted/.test(error)));
    writeFileSync(mutationPath, mutationOriginal, "utf8"); writeFileSync(campaignPath, original, "utf8");

    const firstRoute = parsed.routes[0]!;
    const blockPath = join(root, String(firstRoute.block_results_path)); const blockOriginal = readFileSync(blockPath, "utf8");
    const layeredPath = join(root, String(firstRoute.evidence_path)); const layeredOriginal = readFileSync(layeredPath, "utf8");
    const blockPair = JSON.parse(blockOriginal) as { blocks: Record<string, unknown>[] };
    blockPair.blocks[0]!.formal_status = "NOT_PROVED"; blockPair.blocks[0]!.status = "NOT_PROVED";
    const blockPairDigest = writeCanonicalJson(blockPath, blockPair);
    const blockPairLayered = JSON.parse(layeredOriginal) as { links: Record<string, unknown> };
    blockPairLayered.links.block_results_digest = blockPairDigest;
    const blockPairLayeredDigest = writeCanonicalJson(layeredPath, blockPairLayered);
    const blockPairCampaign = jsonClone(parsed); const blockPairRoute = blockPairCampaign.routes[0]!;
    blockPairRoute.block_results_digest = blockPairDigest; blockPairRoute.evidence_digest = blockPairLayeredDigest;
    const firstBlockId = interactionBlockIds[0];
    blockPairCampaign.block_counts[firstBlockId]!.PROVED_UNDER_ASSUMPTIONS = 71;
    blockPairCampaign.block_counts[firstBlockId]!.NOT_PROVED = 1;
    writeCanonicalJson(campaignPath, blockPairCampaign);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /block results reconstruction drifted/.test(error)));
    writeFileSync(blockPath, blockOriginal, "utf8"); writeFileSync(layeredPath, layeredOriginal, "utf8"); writeFileSync(campaignPath, original, "utf8");

    const blockCountsCampaign = jsonClone(parsed);
    blockCountsCampaign.block_counts[firstBlockId]!.PROVED_UNDER_ASSUMPTIONS = 71;
    blockCountsCampaign.block_counts[firstBlockId]!.NOT_PROVED = 1;
    writeCanonicalJson(campaignPath, blockCountsCampaign);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /block counts drifted/.test(error)));
    writeFileSync(campaignPath, original, "utf8");

    const crossChannelRouteIndex = parsed.routes.findIndex(route => route.source_profile === "angular" && route.target_profile === "harmony-arkui");
    assert.notEqual(crossChannelRouteIndex, -1);
    const crossChannelRoute = parsed.routes[crossChannelRouteIndex]!;
    const compositionPath = join(root, String(crossChannelRoute.composition_path)); const compositionOriginal = readFileSync(compositionPath, "utf8");
    const crossChannelLayeredPath = join(root, String(crossChannelRoute.evidence_path)); const crossChannelLayeredOriginal = readFileSync(crossChannelLayeredPath, "utf8");
    const compositionDrift = JSON.parse(compositionOriginal) as Record<string, unknown>;
    compositionDrift.cross_channel_equivalence = { harmonyos: "NOT_RUN" };
    const compositionDriftDigest = writeCanonicalJson(compositionPath, compositionDrift);
    const compositionLayered = JSON.parse(crossChannelLayeredOriginal) as { links: Record<string, unknown> };
    compositionLayered.links.composition_digest = compositionDriftDigest;
    const compositionLayeredDigest = writeCanonicalJson(crossChannelLayeredPath, compositionLayered);
    const compositionCampaign = jsonClone(parsed); compositionCampaign.routes[crossChannelRouteIndex]!.composition_digest = compositionDriftDigest;
    compositionCampaign.routes[crossChannelRouteIndex]!.evidence_digest = compositionLayeredDigest;
    writeCanonicalJson(campaignPath, compositionCampaign);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /composition reconstruction drifted/.test(error)));
    writeFileSync(compositionPath, compositionOriginal, "utf8"); writeFileSync(crossChannelLayeredPath, crossChannelLayeredOriginal, "utf8"); writeFileSync(campaignPath, original, "utf8");

    const layeredDrift = JSON.parse(layeredOriginal) as { layers: Record<string, unknown> };
    layeredDrift.layers.framework_native_build = "PASSED";
    const layeredDriftDigest = writeCanonicalJson(layeredPath, layeredDrift);
    const layeredCampaign = jsonClone(parsed); layeredCampaign.routes[0]!.evidence_digest = layeredDriftDigest;
    writeCanonicalJson(campaignPath, layeredCampaign);
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /layered result reconstruction drifted/.test(error)));
    writeFileSync(layeredPath, layeredOriginal, "utf8"); writeFileSync(campaignPath, original, "utf8");

    parsed.routes[1] = { ...parsed.routes[0] };
    writeFileSync(campaignPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /duplicated|closure/.test(error)));
    writeFileSync(campaignPath, original, "utf8");

    const formalPath = join(root, "routes", "angular--to--flutter", "formal-input.json");
    writeFileSync(formalPath, `${readFileSync(formalPath, "utf8")} `, "utf8");
    assert.ok(verifyFrontendInteractionCampaign(root).some(error => /formal bytes digest drifted/.test(error)));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("framework tuple remains exact for every v2 request", () => {
  for (const profile of uiTargetProfiles()) {
    const request = boundedInteractionFixtureRequest(profile.id);
    assert.throws(() => validateUiProjectGenerationRequestV2({ ...request, source: { ...request.source, version: "0.0.0" } }), /source.version must equal/);
    const wrongPlatform = request.source.platform === "HARMONYOS" ? "WEB" : "HARMONYOS";
    assert.throws(() => validateUiProjectGenerationRequestV2({ ...request, source: { ...request.source, platform: wrongPlatform } }), /source.platform is not supported/);
  }
});

test("external block IDs stay hyphenated and map exactly once", () => {
  assert.equal(new Set(interactionBlockIds).size, 12);
  assert.ok(interactionBlockIds.every(block => block.includes("-") || block === "api-network"));
  const profiles = new Set<UiFrameworkId>(uiTargetProfiles().map(profile => profile.id));
  assert.equal(profiles.size, 9);
});

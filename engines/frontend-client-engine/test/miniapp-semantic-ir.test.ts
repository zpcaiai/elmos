import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { inventoryMiniappSource } from "../src/miniapp-inventory.js";
import {
  analyzeMiniappSource,
  buildMiniappSemanticIr,
  canonicalizeMiniappSemanticIr,
  validateMiniappSemanticIr,
} from "../src/miniapp-semantic-ir.js";
import { computeMiniappSourceFileSetDigest } from "../src/miniapp-skill-runtime.js";
import { miniappRequest, vueTodoFiles } from "./miniapp-test-fixture.js";

function analyzeFixture() {
  const request = miniappRequest();
  const inventory = inventoryMiniappSource({
    schemaVersion: "1.0",
    inventoryId: "inv-vue-todo",
    sourceRevision: request.source.revision,
    sourceSnapshotDigest: request.source.snapshotDigest,
    sourceLabelHint: request.source.sourceLabel,
    limits: request.policy.limits,
    files: vueTodoFiles,
  });
  const sources = Object.fromEntries(vueTodoFiles.map(file => [file.path, String(file.content)]));
  const analysis = analyzeMiniappSource(request, inventory, sources);
  return { request, inventory, analysis, ir: buildMiniappSemanticIr(request, inventory, analysis) };
}

test("Vue SFC and TypeScript compiler APIs produce traced deterministic semantic IR", () => {
  const first = analyzeFixture();
  const second = analyzeFixture();
  assert.equal(first.inventory.fileSetDigest, computeMiniappSourceFileSetDigest(vueTodoFiles));
  assert.equal(first.inventory.selectedSourceLabel, "vue3");
  assert.match(first.analysis.parser, /typescript-compiler-api|vue-compiler-sfc/);
  assert.equal(first.analysis.coverage, 1);
  assert.ok(first.analysis.components.length >= 4);
  assert.ok(first.analysis.routes.some(route => route.path === "/"));
  assert.equal(first.analysis.findings.some(finding => finding.code === "MINIAPP_ROUTE_DECLARATION_UNBOUND"), false);
  assert.equal(first.analysis.findings.some(finding => finding.code === "MINIAPP_ROUTE_OPTION_UNRESOLVED"), false);
  const namedRouteFiles = vueTodoFiles.map(file => file.path === "src/router.ts" ? {
    ...file,
    content: String(file.content).replace('routes: [{ path: "/", component: "App" }]', 'routes: [{ path: "/", name: "home", component: "App" }]'),
  } : file);
  const namedRouteRequest = miniappRequest(namedRouteFiles);
  const namedRouteInventory = inventoryMiniappSource({
    schemaVersion: "1.0",
    inventoryId: "inv-vue-named-route",
    sourceRevision: namedRouteRequest.source.revision,
    sourceSnapshotDigest: namedRouteRequest.source.snapshotDigest,
    sourceLabelHint: namedRouteRequest.source.sourceLabel,
    limits: namedRouteRequest.policy.limits,
    files: namedRouteFiles,
  });
  const namedRouteSources = Object.fromEntries(namedRouteFiles.map(file => [file.path, String(file.content)]));
  const namedRouteAnalysis = analyzeMiniappSource(namedRouteRequest, namedRouteInventory, namedRouteSources);
  assert.equal(namedRouteAnalysis.routes.find(route => route.path === "/")?.name, "home");
  assert.equal(namedRouteAnalysis.findings.some(finding => finding.code === "MINIAPP_ROUTE_OPTION_UNRESOLVED"), false);
  assert.ok(first.analysis.states.some(state => state.name === "title"));
  assert.ok(first.analysis.states.some(state => state.name === "items" && state.scope === "application"));
  assert.deepEqual(first.analysis.interactions.map(interaction => ({
    kind: interaction.kind,
    draft: interaction.draftState,
    draftId: interaction.draftStateId,
    collection: interaction.collectionState,
    collectionId: interaction.collectionStateId,
    ignoreBlank: interaction.ignoreBlank,
    clearAfterSubmit: interaction.clearAfterSubmit,
  })), [{
    kind: "trimmed-text-append-list",
    draft: "title",
    draftId: first.analysis.states.find(state => state.name === "title")!.id,
    collection: "items",
    collectionId: first.analysis.states.find(state => state.name === "items")!.id,
    ignoreBlank: true,
    clearAfterSubmit: true,
  }]);
  for (const dependency of ["vue", "vue-router", "pinia"]) {
    assert.ok((first.analysis.dependencyUsage[dependency] ?? []).length > 0, `${dependency} must have import-bound usage evidence`);
  }
  assert.equal(first.analysis.deterministicDigest, second.analysis.deterministicDigest);
  assert.equal(first.ir.deterministicDigest, second.ir.deterministicDigest);
  assert.equal(canonicalizeMiniappSemanticIr(first.ir), canonicalizeMiniappSemanticIr(second.ir));
  assert.equal(first.ir.coverage.tracedNodes, 1);
  assert.ok(first.ir.nodes.every(node => node.sourceRefs.length > 0 && node.obligations.includes("NO_SILENT_DROP")));
  const sourceDigests = new Map(vueTodoFiles.map(file => [
    file.path,
    `sha256:${createHash("sha256").update(file.content).digest("hex")}`,
  ]));
  for (const ref of first.ir.nodes.flatMap(node => node.sourceRefs)) {
    assert.equal(ref.sha256, sourceDigests.get(ref.path), `trace must bind real source bytes: ${ref.path}`);
  }

  const chainedFiles = [
    ...vueTodoFiles.map(file => file.path === "src/router.ts" ? {
      ...file,
      content: String(file.content).replace("export default createRouter", "export const router = createRouter"),
    } : file),
    {
      path: "src/main.ts",
      content: `import { createApp } from "vue"; import { createPinia } from "pinia"; import App from "./App.vue"; import { router } from "./router"; createApp(App).use(createPinia()).use(router).mount("#app");`,
    },
  ];
  const chainedRequest = miniappRequest(chainedFiles);
  const chainedInventory = inventoryMiniappSource({
    schemaVersion: "1.0",
    inventoryId: "inv-vue-chained-bootstrap",
    sourceRevision: chainedRequest.source.revision,
    sourceSnapshotDigest: chainedRequest.source.snapshotDigest,
    sourceLabelHint: chainedRequest.source.sourceLabel,
    limits: chainedRequest.policy.limits,
    files: chainedFiles,
  });
  const chainedSources = Object.fromEntries(chainedFiles.map(file => [file.path, String(file.content)]));
  const chainedAnalysis = analyzeMiniappSource(chainedRequest, chainedInventory, chainedSources);
  const frameworkEffects = chainedAnalysis.effects.filter(effect => effect.name.startsWith("vue.") || effect.name === "pinia.create");
  assert.ok(frameworkEffects.some(effect => effect.name === "vue.app.use.pinia"));
  assert.ok(frameworkEffects.some(effect => effect.name === "vue.app.use.router"));
  assert.ok(frameworkEffects.some(effect => effect.name === "vue.app.mount"));
  assert.equal(
    chainedAnalysis.findings.some(finding => finding.code === "MINIAPP_CALL_SEMANTICS_UNRESOLVED"),
    false,
  );
  validateMiniappSemanticIr(first.ir);
});

test("semantic IR validation rejects dangling references and untraced nodes", () => {
  const { ir } = analyzeFixture();
  const first = ir.nodes[0]!;
  assert.throws(() => validateMiniappSemanticIr({
    ...ir,
    nodes: [{ ...first, references: ["missing.node"] }, ...ir.nodes.slice(1)],
  }), /reference is not closed/);
  assert.throws(() => validateMiniappSemanticIr({
    ...ir,
    nodes: [{ ...first, sourceRefs: [] }, ...ir.nodes.slice(1)],
  }), /no source trace/);

  const { deterministicDigest: _digest, ...unsigned } = ir;
  assert.match(_digest, /^sha256:[a-f0-9]{64}$/u);
  assert.throws(() => validateMiniappSemanticIr({
    ...unsigned,
    traceIndex: { ...unsigned.traceIndex, [first.id]: [] },
  }), /trace index does not match node source trace/);
  assert.throws(() => validateMiniappSemanticIr({
    ...unsigned,
    traceIndex: { ...unsigned.traceIndex, "rogue.node": first.sourceRefs },
  }), /trace index is not an exact IR node index/);
  assert.throws(() => validateMiniappSemanticIr({
    ...unsigned,
    nodes: [{ ...first, semanticRole: `${first.semanticRole}-tampered` }, ...unsigned.nodes.slice(1)],
  }), /exactly reconstruct the typed semantic collections/);
  const component = unsigned.components[0]!;
  assert.throws(() => validateMiniappSemanticIr({
    ...unsigned,
    components: [{ ...component, sourceRefs: [] }, ...unsigned.components.slice(1)],
  }), /exactly reconstruct the typed semantic collections/);
  assert.throws(() => validateMiniappSemanticIr({
    ...unsigned,
    components: unsigned.components.slice(1),
  }), /component collection is not exactly indexed/);
  assert.throws(() => validateMiniappSemanticIr({
    ...unsigned,
    application: { ...unsigned.application, routeIds: [] },
  }), /application route index is not closed/);
  assert.throws(() => validateMiniappSemanticIr({
    ...ir,
    application: { ...ir.application, title: "tampered" },
  }), /deterministic digest does not match its content/);
});

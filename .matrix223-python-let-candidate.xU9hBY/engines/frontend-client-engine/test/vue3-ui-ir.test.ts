import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { frtCatalog } from "../src/frt-catalog.generated.js";
import {
  convertDirectionalRoute,
  createDirectionalRouteFixture,
  frtSourceDerivedStacks,
  type FrtRouteStack,
} from "../src/directional-route.js";
import { frtTypedGapCodes, frtTypedGapDefinition } from "../src/frt-typed-gap-catalog.js";
import { deriveVue3PortableUiIr } from "../src/vue3-ui-ir.js";
import type { FrtRouteTypedGap } from "../src/frt-route-ir.js";

const vue3Routes = frtCatalog.routes.filter(route => route.source === "Vue 3");

function withoutDeclaredIr(files: Readonly<Record<string, string>>): Record<string, string> {
  const copy = { ...files };
  delete copy["frt-ui-ir.json"];
  return copy;
}

function replaceSfc(files: Readonly<Record<string, string>>, sfc: string): Record<string, string> {
  return { ...withoutDeclaredIr(files), "src/App.vue": sfc };
}

function derive(files: Readonly<Record<string, string>>) {
  const gaps: FrtRouteTypedGap[] = [];
  const ir = deriveVue3PortableUiIr(files, gaps);
  return { ir, gaps };
}

const vue3Fixture = createDirectionalRouteFixture("Vue 3");
const declaredVue3Ir = JSON.parse(vue3Fixture["frt-ui-ir.json"]!) as {
  view: { title: string; initialCount: number; incrementBy: number; buttonLabel: string };
  style: { accentColor: string };
  accessibility: { mainLabel: string; buttonLabel: string; liveRegion: string };
  source: { version: string };
  sourceSnapshotDigest: string;
};

test("every Vue 3 route derives its typed UI IR from source when nothing is declared", () => {
  assert.equal(vue3Routes.length, 5);
  for (const route of vue3Routes) {
    const migration = convertDirectionalRoute(
      "Vue 3",
      route.target as FrtRouteStack,
      withoutDeclaredIr(vue3Fixture),
    );
    assert.deepEqual(migration.typedGaps, [], route.routeId);
    assert.equal(migration.status, "GENERATED", route.routeId);
    assert.equal(migration.irProvenance, "SOURCE_DERIVED", route.routeId);
    // The derived snapshot digest is the same content addressing a declared IR
    // would have had to carry, so "derived" costs no provenance.
    assert.equal(migration.sourceSnapshotDigest, declaredVue3Ir.sourceSnapshotDigest, route.routeId);
    assert.ok(Object.keys(migration.generatedFiles).length >= 2, route.routeId);
    assert.equal(migration.certification, "NOT_CERTIFIED", route.routeId);
  }
});

test("the IR derived from the Vue 3 fixture is exactly what the fixture declares", () => {
  const { ir, gaps } = derive(withoutDeclaredIr(vue3Fixture));
  assert.deepEqual(gaps, []);
  assert.ok(ir);
  assert.deepEqual(ir.view, declaredVue3Ir.view);
  assert.deepEqual(ir.style, declaredVue3Ir.style);
  assert.deepEqual(ir.accessibility, declaredVue3Ir.accessibility);
  assert.equal(ir.source.version, declaredVue3Ir.source.version);
  assert.equal(ir.sourceSnapshotDigest, declaredVue3Ir.sourceSnapshotDigest);
});

test("a declared Vue 3 IR may not assert anything the source does not say", () => {
  const divergences: readonly (readonly [string, (ir: Record<string, unknown>) => void])[] = [
    ["view.title", ir => { (ir.view as Record<string, unknown>).title = "Not what the source says"; }],
    ["view.initialCount", ir => { (ir.view as Record<string, unknown>).initialCount = 41; }],
    ["view.incrementBy", ir => { (ir.view as Record<string, unknown>).incrementBy = 7; }],
    ["view.buttonLabel", ir => { (ir.view as Record<string, unknown>).buttonLabel = "Fabricated"; }],
    ["style.accentColor", ir => { (ir.style as Record<string, unknown>).accentColor = "#FF0000"; }],
    ["accessibility.mainLabel", ir => { (ir.accessibility as Record<string, unknown>).mainLabel = "Invented label"; }],
    ["accessibility.buttonLabel", ir => {
      (ir.accessibility as Record<string, unknown>).buttonLabel = "Invented action name";
    }],
  ];
  for (const [field, tamper] of divergences) {
    const declared = JSON.parse(vue3Fixture["frt-ui-ir.json"]!) as Record<string, unknown>;
    tamper(declared);
    const migration = convertDirectionalRoute("Vue 3", "React", {
      ...vue3Fixture,
      "frt-ui-ir.json": `${JSON.stringify(declared, null, 2)}\n`,
    });
    assert.equal(migration.status, "BLOCKED", field);
    assert.equal(migration.irProvenance, "NONE", field);
    assert.deepEqual(migration.generatedFiles, {}, field);
    const divergence = migration.typedGaps.find(
      item => item.code === "FRT_DECLARED_IR_DIVERGES_FROM_SOURCE" && item.message.startsWith(`${field}:`),
    );
    assert.ok(divergence, `${field} divergence must be reported explicitly, not as a generic invalidity`);
    assert.equal(divergence.blocking, true, field);
  }
});

test("an honest declared Vue 3 IR is accepted, and says it was cross-checked", () => {
  const migration = convertDirectionalRoute("Vue 3", "Flutter", vue3Fixture);
  assert.deepEqual(migration.typedGaps, []);
  assert.equal(migration.status, "GENERATED");
  assert.equal(migration.irProvenance, "DECLARED_CROSS_CHECKED");
});

test("an accessibility contract absent from the Vue 3 source is never invented", () => {
  const cases: readonly (readonly [string, string])[] = [
    ["main", '<template><main><h1>{{ title }}</h1><button aria-label="Increment counter" @click="increment">Increment</button><p aria-live="polite">{{ count }}</p></main></template>'],
    ["button", '<template><main aria-label="Counter application"><h1>{{ title }}</h1><button @click="increment">Increment</button><p aria-live="polite">{{ count }}</p></main></template>'],
    ["live region", '<template><main aria-label="Counter application"><h1>{{ title }}</h1><button aria-label="Increment counter" @click="increment">Increment</button><p>{{ count }}</p></main></template>'],
  ];
  const script = '<script setup lang="ts">import { ref } from "vue"; const title = "Counter"; const count = ref(0); function increment() { count.value += 1; }</script><style scoped>button { color: #0057B8; }</style>\n';
  for (const [what, template] of cases) {
    const { ir, gaps } = derive(replaceSfc(vue3Fixture, `${template}${script}`));
    assert.equal(ir, undefined, what);
    assert.ok(
      gaps.some(item => item.code === "FRT_VUE3_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE" && item.blocking),
      `a missing ${what} accessible name must block rather than be defaulted`,
    );
  }
});

test("an aria-live mode this IR cannot carry is reported instead of downgraded", () => {
  const sfc = '<template><main aria-label="Counter application"><h1>{{ title }}</h1><button aria-label="Increment counter" @click="increment">Increment</button><p aria-live="assertive">{{ count }}</p></main></template><script setup lang="ts">import { ref } from "vue"; const title = "Counter"; const count = ref(0); function increment() { count.value += 1; }</script><style scoped>button { color: #0057B8; }</style>\n';
  const { ir, gaps } = derive(replaceSfc(vue3Fixture, sfc));
  assert.equal(ir, undefined);
  assert.ok(gaps.some(item => item.code === "FRT_VUE3_LIVE_REGION_UNSUPPORTED"));
});

test("Vue 3 semantics outside the derivable slice surface as specific typed gaps", () => {
  const head = '<template><main aria-label="Counter application"><h1>{{ title }}</h1>';
  const action = '<button aria-label="Increment counter" @click="increment">Increment</button>';
  const tail = '<p aria-live="polite">{{ count }}</p></main></template>';
  const style = '<style scoped>button { color: #0057B8; }</style>\n';
  const baseScript = 'import { ref } from "vue"; const title = "Counter"; const count = ref(0);';

  const cases: readonly (readonly [string, string])[] = [
    ["FRT_VUE3_IMPORT_UNSUPPORTED",
      `${head}${action}${tail}<script setup lang="ts">import { computed } from "vue"; ${baseScript} function increment() { count.value += 1; }</script>${style}`],
    ["FRT_VUE3_BINDING_UNSUPPORTED",
      `${head}${action}${tail}<script setup lang="ts">${baseScript} const total = count.value * 2; function increment() { count.value += 1; }</script>${style}`],
    ["FRT_VUE3_HANDLER_STATEMENT_UNSUPPORTED",
      `${head}${action}${tail}<script setup lang="ts">${baseScript} function increment() { count.value = count.value * 2; }</script>${style}`],
    ["FRT_VUE3_TEMPLATE_ATTRIBUTE_UNSUPPORTED",
      `${head}<button aria-label="Increment counter" v-if="title" @click="increment">Increment</button>${tail}<script setup lang="ts">${baseScript} function increment() { count.value += 1; }</script>${style}`],
    ["FRT_VUE3_TEMPLATE_SHAPE_UNSUPPORTED",
      `${head}${action}${tail.replace("</main>", "<footer>extra</footer></main>")}<script setup lang="ts">${baseScript} function increment() { count.value += 1; }</script>${style}`],
    ["FRT_VUE3_ROUTE_ROOT_UNSUPPORTED",
      `<template><section aria-label="Counter application"><h1>{{ title }}</h1>${action}<p aria-live="polite">{{ count }}</p></section></template><script setup lang="ts">${baseScript} function increment() { count.value += 1; }</script>${style}`],
    ["FRT_VUE3_ACCENT_COLOR_NOT_DERIVABLE",
      `${head}${action}${tail}<script setup lang="ts">${baseScript} function increment() { count.value += 1; }</script><style scoped>button { color: #0057B8; } h1 { font-weight: 700; }</style>\n`],
    ["FRT_VUE3_COUNTER_ACTION_NOT_DERIVABLE",
      `${head}<button aria-label="Increment counter" @click="missing">Increment</button>${tail}<script setup lang="ts">${baseScript} function increment() { count.value += 1; }</script>${style}`],
    ["FRT_VUE3_COUNTER_STATE_NOT_DERIVABLE",
      `${head}${action}<p aria-live="polite">{{ title }}</p></main></template><script setup lang="ts">${baseScript} function increment() { count.value += 1; }</script>${style}`],
  ];

  for (const [code, sfc] of cases) {
    const { ir, gaps } = derive(replaceSfc(vue3Fixture, sfc));
    assert.equal(ir, undefined, code);
    assert.ok(gaps.some(item => item.code === code), `${code} was not reported; gaps: ${gaps.map(g => g.code).join(", ")}`);
  }
});

test("a Vue 3 target emitted from any source re-derives to the same interaction contract", () => {
  for (const stack of ["Vue 2", "React", "WeChat Mini Program", "ArkUI", "Flutter"] as const) {
    const migration = convertDirectionalRoute(stack, "Vue 3", createDirectionalRouteFixture(stack));
    assert.equal(migration.status, "GENERATED", stack);
    const { ir, gaps } = derive(migration.generatedFiles);
    assert.deepEqual(gaps, [], stack);
    assert.ok(ir, stack);
    // Round trip: what the emitter wrote is exactly what the extractor reads
    // back, so the Vue 3 emitter cannot quietly drop a contract field.
    assert.deepEqual(ir.view, declaredVue3Ir.view, stack);
    assert.deepEqual(ir.style, declaredVue3Ir.style, stack);
    assert.deepEqual(ir.accessibility, declaredVue3Ir.accessibility, stack);
  }
});

test("only stacks with a real extractor claim source-derived provenance", () => {
  assert.deepEqual([...frtSourceDerivedStacks].sort(), [
    "ArkUI", "Flutter", "React", "Vue 2", "Vue 3", "WeChat Mini Program",
  ]);
  let declared = 0;
  for (const route of frtCatalog.routes) {
    const migration = convertDirectionalRoute(
      route.source as FrtRouteStack,
      route.target as FrtRouteStack,
      createDirectionalRouteFixture(route.source as FrtRouteStack),
    );
    if (frtSourceDerivedStacks.has(route.source as FrtRouteStack)) {
      assert.equal(migration.irProvenance, "DECLARED_CROSS_CHECKED", route.routeId);
      continue;
    }
    assert.equal(migration.irProvenance, "DECLARED", route.routeId);
    declared += 1;
  }
  assert.equal(declared, 0);
});

test("every typed gap code the route layer can emit is registered in the catalogue", () => {
  const sources = [
    "frt-route-ir.ts",
    "directional-route.ts",
    "vue3-ui-ir.ts",
    "react-ui-ir.ts",
    "additional-ui-ir.ts",
    "vue3-react-route.ts",
  ];
  const emitted = new Set<string>();
  for (const name of sources) {
    const text = readFileSync(new URL(`../../src/${name}`, import.meta.url), "utf8");
    for (const match of text.matchAll(/"(FRT_[A-Z0-9_]+)"/g)) emitted.add(match[1]!);
  }
  assert.ok(emitted.size > 0);
  assert.deepEqual([...emitted].sort(), [...frtTypedGapCodes]);
  for (const code of frtTypedGapCodes) {
    const definition = frtTypedGapDefinition(code);
    assert.ok(definition.summary.length > 0, code);
    assert.ok(definition.remediation.length > 0, code);
  }
  assert.throws(() => frtTypedGapDefinition("FRT_NOT_REGISTERED"), /not registered/);
});

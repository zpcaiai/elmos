import assert from "node:assert/strict";
import test from "node:test";

import { frtCatalog } from "../src/frt-catalog.generated.js";
import { convertDirectionalRoute, createDirectionalRouteFixture, type FrtRouteStack } from "../src/directional-route.js";
import { deriveReactPortableUiIr } from "../src/react-ui-ir.js";
import type { FrtRouteTypedGap } from "../src/frt-route-ir.js";

const reactRoutes = frtCatalog.routes.filter(route => route.source === "React");
const reactFixture = createDirectionalRouteFixture("React");

const declaredReactIr = JSON.parse(reactFixture["frt-ui-ir.json"]!) as {
  view: { title: string; initialCount: number; incrementBy: number; buttonLabel: string };
  style: { accentColor: string };
  accessibility: { mainLabel: string; buttonLabel: string; liveRegion: string };
  source: { version: string };
  sourceSnapshotDigest: string;
};

function withoutDeclaredIr(files: Readonly<Record<string, string>>): Record<string, string> {
  const copy = { ...files };
  delete copy["frt-ui-ir.json"];
  return copy;
}

function replaceModule(files: Readonly<Record<string, string>>, module: string): Record<string, string> {
  return { ...withoutDeclaredIr(files), "src/App.tsx": module };
}

function derive(files: Readonly<Record<string, string>>) {
  const gaps: FrtRouteTypedGap[] = [];
  const ir = deriveReactPortableUiIr(files, gaps);
  return { ir, gaps };
}

const head = 'import { useState } from "react";\nimport "./App.css";\nexport function App() {\n  const [count, setCount] = useState(0);\n  return ';
const main = '<main aria-label="Counter application">';
const heading = "<h1>Counter</h1>";
const action = '<button aria-label="Increment counter" onClick={() => setCount(value => value + 1)}>Increment</button>';
const live = '<p aria-live="polite">{count}</p>';
const tail = "</main>;\n}\n";

function module(body: string): string {
  return `${head}${body}${tail}`;
}

test("every React route derives its typed UI IR from source when nothing is declared", () => {
  assert.equal(reactRoutes.length, 5);
  for (const route of reactRoutes) {
    const migration = convertDirectionalRoute(
      "React",
      route.target as FrtRouteStack,
      withoutDeclaredIr(reactFixture),
    );
    assert.deepEqual(migration.typedGaps, [], route.routeId);
    assert.equal(migration.status, "GENERATED", route.routeId);
    assert.equal(migration.irProvenance, "SOURCE_DERIVED", route.routeId);
    assert.equal(migration.sourceSnapshotDigest, declaredReactIr.sourceSnapshotDigest, route.routeId);
    assert.equal(migration.certification, "NOT_CERTIFIED", route.routeId);
  }
});

test("the IR derived from the React fixture is exactly what the fixture declares", () => {
  const { ir, gaps } = derive(withoutDeclaredIr(reactFixture));
  assert.deepEqual(gaps, []);
  assert.ok(ir);
  assert.deepEqual(ir.view, declaredReactIr.view);
  assert.deepEqual(ir.style, declaredReactIr.style);
  assert.deepEqual(ir.accessibility, declaredReactIr.accessibility);
  assert.equal(ir.source.version, declaredReactIr.source.version);
  assert.equal(ir.sourceSnapshotDigest, declaredReactIr.sourceSnapshotDigest);
});

test("a declared React IR may not assert anything the source does not say", () => {
  const divergences: readonly (readonly [string, (ir: Record<string, unknown>) => void])[] = [
    ["view.title", ir => { (ir.view as Record<string, unknown>).title = "Not what the source says"; }],
    ["view.initialCount", ir => { (ir.view as Record<string, unknown>).initialCount = 41; }],
    ["view.incrementBy", ir => { (ir.view as Record<string, unknown>).incrementBy = 7; }],
    ["view.buttonLabel", ir => { (ir.view as Record<string, unknown>).buttonLabel = "Fabricated"; }],
    ["style.accentColor", ir => { (ir.style as Record<string, unknown>).accentColor = "#FF0000"; }],
    ["accessibility.mainLabel", ir => { (ir.accessibility as Record<string, unknown>).mainLabel = "Invented"; }],
    ["accessibility.buttonLabel", ir => {
      (ir.accessibility as Record<string, unknown>).buttonLabel = "Invented action name";
    }],
  ];
  for (const [field, tamper] of divergences) {
    const declared = JSON.parse(reactFixture["frt-ui-ir.json"]!) as Record<string, unknown>;
    tamper(declared);
    const migration = convertDirectionalRoute("React", "Vue 3", {
      ...reactFixture,
      "frt-ui-ir.json": `${JSON.stringify(declared, null, 2)}\n`,
    });
    assert.equal(migration.status, "BLOCKED", field);
    assert.deepEqual(migration.generatedFiles, {}, field);
    const divergence = migration.typedGaps.find(
      item => item.code === "FRT_DECLARED_IR_DIVERGES_FROM_SOURCE" && item.message.startsWith(`${field}:`),
    );
    assert.ok(divergence, `${field} divergence must be reported explicitly, not as a generic invalidity`);
  }
});

test("an accessibility contract absent from the React source is never invented", () => {
  const cases: readonly (readonly [string, string])[] = [
    ["main", module(`<main>${heading}${action}${live}`)],
    ["button", module(`${main}${heading}<button onClick={() => setCount(value => value + 1)}>Increment</button>${live}`)],
    ["live region", module(`${main}${heading}${action}<p>{count}</p>`)],
  ];
  for (const [what, source] of cases) {
    const { ir, gaps } = derive(replaceModule(reactFixture, source));
    assert.equal(ir, undefined, what);
    assert.ok(
      gaps.some(item => item.code === "FRT_REACT_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE" && item.blocking),
      `a missing ${what} accessible name must block rather than be defaulted`,
    );
  }
});

test("React semantics outside the derivable slice surface as specific typed gaps", () => {
  const body = `${main}${heading}${action}${live}`;
  const cases: readonly (readonly [string, Record<string, string>])[] = [
    ["FRT_REACT_IMPORT_UNSUPPORTED", replaceModule(reactFixture,
      module(body).replace('import { useState } from "react";', 'import { useState, useEffect } from "react";'))],
    ["FRT_REACT_BINDING_UNSUPPORTED", replaceModule(reactFixture,
      module(body).replace("const [count, setCount] = useState(0);", "const [count, setCount] = useState(0);\n  const doubled = count * 2;"))],
    ["FRT_REACT_COUNTER_ACTION_NOT_DERIVABLE", replaceModule(reactFixture,
      module(`${main}${heading}<button aria-label="Increment counter" onClick={() => setCount(value => value * 2)}>Increment</button>${live}`))],
    ["FRT_REACT_COUNTER_STATE_NOT_DERIVABLE", replaceModule(reactFixture,
      module(`${main}${heading}${action}<p aria-live="polite">{"literal"}</p>`))],
    ["FRT_REACT_TEMPLATE_ATTRIBUTE_UNSUPPORTED", replaceModule(reactFixture,
      module(`${main}${heading}${action.replace("<button ", '<button className="cta" ')}${live}`))],
    ["FRT_REACT_TEMPLATE_SHAPE_UNSUPPORTED", replaceModule(reactFixture,
      module(`${main}${heading}${action}${live}<footer>extra</footer>`))],
    ["FRT_REACT_ROUTE_ROOT_UNSUPPORTED", replaceModule(reactFixture,
      module(`<section aria-label="Counter application">${heading}${action}${live}`).replace("</main>;", "</section>;"))],
    ["FRT_REACT_LIVE_REGION_UNSUPPORTED", replaceModule(reactFixture,
      module(`${main}${heading}${action}<p aria-live="assertive">{count}</p>`))],
    ["FRT_REACT_ACCENT_COLOR_NOT_DERIVABLE",
      { ...replaceModule(reactFixture, module(body)), "src/App.css": "button { color: #0057B8; } h1 { font-weight: 700; }\n" }],
    ["FRT_REACT_STYLESHEET_NOT_IMPORTED", replaceModule(reactFixture,
      module(body).replace('import "./App.css";\n', ""))],
    ["FRT_REACT_SOURCE_VERSION_NOT_EXACT",
      { ...replaceModule(reactFixture, module(body)), "package.json": '{\n  "dependencies": {\n    "react": "^19.2.7"\n  }\n}\n' }],
  ];

  for (const [code, files] of cases) {
    const { ir, gaps } = derive(files);
    assert.equal(ir, undefined, code);
    assert.ok(gaps.some(item => item.code === code), `${code} was not reported; gaps: ${gaps.map(g => g.code).join(", ")}`);
  }
});

test("a React target emitted from any source re-derives to the same interaction contract", () => {
  for (const stack of ["Vue 2", "Vue 3", "WeChat Mini Program", "ArkUI", "Flutter"] as const) {
    const migration = convertDirectionalRoute(stack, "React", createDirectionalRouteFixture(stack));
    assert.equal(migration.status, "GENERATED", stack);
    const { ir, gaps } = derive(migration.generatedFiles);
    assert.deepEqual(gaps, [], stack);
    assert.ok(ir, stack);
    assert.deepEqual(ir.view, declaredReactIr.view, stack);
    assert.deepEqual(ir.style, declaredReactIr.style, stack);
    assert.deepEqual(ir.accessibility, declaredReactIr.accessibility, stack);
  }
});

test("React and Vue 3 round-trip through each other without losing the contract", () => {
  const toReact = convertDirectionalRoute("Vue 3", "React", createDirectionalRouteFixture("Vue 3"));
  assert.equal(toReact.status, "GENERATED");
  const backToVue = convertDirectionalRoute("React", "Vue 3", toReact.generatedFiles);
  // The emitted React project carries no declared IR, so the return trip can
  // only work if the React extractor really reads it back out of the bytes.
  assert.deepEqual(backToVue.typedGaps, []);
  assert.equal(backToVue.status, "GENERATED");
  assert.equal(backToVue.irProvenance, "SOURCE_DERIVED");
  assert.match(backToVue.generatedFiles["src/App.vue"]!, /aria-label="Counter application"/);
  assert.match(backToVue.generatedFiles["src/App.vue"]!, /count\.value \+= 1/);
});

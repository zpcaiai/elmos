import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveArkUiPortableUiIr,
  deriveFlutterPortableUiIr,
  deriveMiniProgramPortableUiIr,
  deriveVue2PortableUiIr,
} from "../src/additional-ui-ir.js";
import { frtCatalog } from "../src/frt-catalog.generated.js";
import {
  convertDirectionalRoute,
  createDirectionalRouteFixture,
  type FrtRouteStack,
} from "../src/directional-route.js";
import type { FrtRouteTypedGap, PortableUiIr } from "../src/frt-route-ir.js";

const stacks = ["Vue 2", "WeChat Mini Program", "ArkUI", "Flutter"] as const;

function withoutDeclaredIr(files: Readonly<Record<string, string>>): Record<string, string> {
  const copy = { ...files };
  delete copy["frt-ui-ir.json"];
  return copy;
}

function derive(stack: typeof stacks[number], files: Readonly<Record<string, string>>) {
  const gaps: FrtRouteTypedGap[] = [];
  const ir = stack === "Vue 2" ? deriveVue2PortableUiIr(files, gaps)
    : stack === "WeChat Mini Program" ? deriveMiniProgramPortableUiIr(files, gaps)
      : stack === "ArkUI" ? deriveArkUiPortableUiIr(files, gaps)
        : deriveFlutterPortableUiIr(files, gaps);
  return { ir, gaps };
}

function declared(stack: typeof stacks[number]): PortableUiIr {
  return JSON.parse(createDirectionalRouteFixture(stack)["frt-ui-ir.json"]!) as PortableUiIr;
}

test("all twenty outgoing routes from the four added stacks derive IR from source", () => {
  for (const stack of stacks) {
    const routes = frtCatalog.routes.filter(route => route.source === stack);
    assert.equal(routes.length, 5, stack);
    const fixture = withoutDeclaredIr(createDirectionalRouteFixture(stack));
    for (const route of routes) {
      const migration = convertDirectionalRoute(stack, route.target as FrtRouteStack, fixture);
      assert.deepEqual(migration.typedGaps, [], route.routeId);
      assert.equal(migration.status, "GENERATED", route.routeId);
      assert.equal(migration.irProvenance, "SOURCE_DERIVED", route.routeId);
      assert.equal(migration.sourceSnapshotDigest, declared(stack).sourceSnapshotDigest, route.routeId);
      assert.equal(migration.certification, "NOT_CERTIFIED", route.routeId);
    }
  }
});

test("each added extractor derives exactly the contract declared by its fixture", () => {
  for (const stack of stacks) {
    const expected = declared(stack);
    const { ir, gaps } = derive(stack, withoutDeclaredIr(createDirectionalRouteFixture(stack)));
    assert.deepEqual(gaps, [], stack);
    assert.ok(ir, stack);
    assert.deepEqual(ir.view, expected.view, stack);
    assert.deepEqual(ir.style, expected.style, stack);
    assert.deepEqual(ir.accessibility, expected.accessibility, stack);
    assert.deepEqual(ir.source, expected.source, stack);
    assert.equal(ir.sourceSnapshotDigest, expected.sourceSnapshotDigest, stack);
  }
});

test("declared IR divergence is blocked for every added source stack", () => {
  for (const stack of stacks) {
    const fixture = createDirectionalRouteFixture(stack);
    const declaration = JSON.parse(fixture["frt-ui-ir.json"]!) as PortableUiIr;
    const tampered = { ...declaration, view: { ...declaration.view, incrementBy: 9 } };
    const migration = convertDirectionalRoute(stack, "React", {
      ...fixture,
      "frt-ui-ir.json": `${JSON.stringify(tampered, null, 2)}\n`,
    });
    assert.equal(migration.status, "BLOCKED", stack);
    assert.equal(migration.irProvenance, "NONE", stack);
    assert.deepEqual(migration.generatedFiles, {}, stack);
    assert.ok(migration.typedGaps.some(gap => gap.code === "FRT_DECLARED_IR_DIVERGES_FROM_SOURCE"
      && gap.message.startsWith("view.incrementBy:")), stack);
  }
});

test("accessibility declarations absent from each added stack are never invented", () => {
  const mutations: Record<typeof stacks[number], (files: Record<string, string>) => void> = {
    "Vue 2": files => { files["src/App.vue"] = files["src/App.vue"]!.replace(' aria-label="Counter application"', ""); },
    "WeChat Mini Program": files => {
      files["pages/index/index.wxml"] = files["pages/index/index.wxml"]!.replace(' aria-label="Counter application"', "");
    },
    ArkUI: files => {
      files["entry/src/main/ets/pages/Index.ets"] = files["entry/src/main/ets/pages/Index.ets"]!
        .replace('.accessibilityText("Counter application")', "");
    },
    Flutter: files => { files["lib/main.dart"] = files["lib/main.dart"]!.replace('label: "Counter application", ', ""); },
  };
  const expected: Record<typeof stacks[number], string> = {
    "Vue 2": "FRT_VUE2_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE",
    "WeChat Mini Program": "FRT_MINIPROGRAM_WXML_SEMANTIC_UNSUPPORTED",
    ArkUI: "FRT_ARKUI_CONTRACT_NOT_DERIVABLE",
    Flutter: "FRT_FLUTTER_CONTRACT_NOT_DERIVABLE",
  };
  for (const stack of stacks) {
    const files = withoutDeclaredIr(createDirectionalRouteFixture(stack));
    mutations[stack](files);
    const { ir, gaps } = derive(stack, files);
    assert.equal(ir, undefined, stack);
    assert.ok(gaps.some(gap => gap.code === expected[stack] && gap.blocking),
      `${stack}: ${gaps.map(gap => gap.code).join(", ")}`);
  }
});

test("unmodeled source semantics surface as stack-specific typed gaps", () => {
  const mutations: Record<typeof stacks[number], (files: Record<string, string>) => void> = {
    "Vue 2": files => { files["src/App.vue"] = files["src/App.vue"]!.replace("<main ", '<main v-if="count >= 0" '); },
    "WeChat Mini Program": files => {
      files["pages/index/index.wxml"] = files["pages/index/index.wxml"]!.replace("<view ", '<view hidden="{{false}}" ');
    },
    ArkUI: files => { files["entry/src/main/ets/pages/Index.ets"] += "const hidden = 1;\n"; },
    Flutter: files => { files["lib/main.dart"] += "void hidden() {}\n"; },
  };
  const expected: Record<typeof stacks[number], string> = {
    "Vue 2": "FRT_VUE2_TEMPLATE_SEMANTIC_UNSUPPORTED",
    "WeChat Mini Program": "FRT_MINIPROGRAM_WXML_SEMANTIC_UNSUPPORTED",
    ArkUI: "FRT_ARKUI_SEMANTIC_UNSUPPORTED",
    Flutter: "FRT_FLUTTER_SEMANTIC_UNSUPPORTED",
  };
  for (const stack of stacks) {
    const files = withoutDeclaredIr(createDirectionalRouteFixture(stack));
    mutations[stack](files);
    const { ir, gaps } = derive(stack, files);
    assert.equal(ir, undefined, stack);
    assert.ok(gaps.some(gap => gap.code === expected[stack]),
      `${stack}: ${gaps.map(gap => gap.code).join(", ")}`);
  }
});

test("each added target emitter round-trips through its source extractor", () => {
  for (const target of stacks) {
    const migration = convertDirectionalRoute("React", target, createDirectionalRouteFixture("React"));
    assert.equal(migration.status, "GENERATED", target);
    const { ir, gaps } = derive(target, migration.generatedFiles);
    assert.deepEqual(gaps, [], target);
    assert.ok(ir, target);
    const expected = declared(target);
    assert.deepEqual(ir.view, expected.view, target);
    assert.deepEqual(ir.style, expected.style, target);
    assert.deepEqual(ir.accessibility, expected.accessibility, target);
  }
});

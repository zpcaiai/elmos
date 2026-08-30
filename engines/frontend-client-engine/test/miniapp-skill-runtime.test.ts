import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  MINIAPP_SKILL_CATALOG,
  computeMiniappSourceFileSetDigest,
  executeMiniappSkill,
  handleMiniappSkillRequest,
  runMiniappConversion,
  runMiniappSkillJson,
  type MiniappConversionRun,
} from "../src/miniapp-skill-runtime.js";
import {
  MINIAPP_DECLARED_OUTPUT_CATALOG,
  materializeMiniappDeclaredOutputs,
  materializeMiniappGeneratedProjectArtifacts,
  materializeMiniappGeneratedProjectBasePath,
} from "../src/miniapp-output-contracts.js";
import { validateMiniappConversionRequest } from "../src/miniapp-contract-validation.js";
import {
  validateMiniappSemanticIr,
  type MiniappSemanticIr,
} from "../src/miniapp-semantic-ir.js";
import { conversionInput, vueTodoFiles } from "./miniapp-test-fixture.js";

function exactReactFiles(source: string) {
  return [
    {
      path: "package.json",
      content: JSON.stringify({
        engines: { node: "24.3.0" },
        dependencies: { react: "19.2.0" },
        devDependencies: { typescript: "5.9.2", vite: "6.0.0" },
      }),
    },
    {
      path: "package-lock.json",
      content: JSON.stringify({
        lockfileVersion: 3,
        packages: {
          "": { dependencies: { react: "19.2.0" }, devDependencies: { typescript: "5.9.2", vite: "6.0.0" } },
          "node_modules/react": { version: "19.2.0" },
          "node_modules/typescript": { version: "5.9.2" },
          "node_modules/vite": { version: "6.0.0" },
        },
      }),
    },
    { path: "src/App.tsx", content: source },
  ] as const;
}

const sourceMatrix = {
  vue2: [
    { path: "package.json", content: JSON.stringify({ dependencies: { vue: "2.7.16" } }) },
    { path: "src/App.vue", content: '<template><main>Vue 2</main></template><script>import Vue from "vue"; export default {}</script>' },
  ],
  vue3: undefined,
  react: [
    { path: "package.json", content: JSON.stringify({ dependencies: { react: "19.2.0" } }) },
    { path: "src/App.tsx", content: 'import React from "react"; export function App(){ return <main>React</main>; }' },
  ],
  flutter: [
    { path: "pubspec.yaml", content: "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n" },
    { path: "lib/main.dart", content: 'void main() => runApp(const Text("Flutter"));' },
  ],
  h5: [{ path: "index.html", content: "<main><button>H5</button></main>" }],
  typescript: [
    { path: "tsconfig.json", content: "{}" },
    { path: "index.ts", content: "export function App(){ return 1; }" },
  ],
  javascript: Array.from({ length: 5 }, (_, index) => ({
    path: index === 0 ? "index.js" : `src/module-${index}.js`,
    content: index === 0 ? "export function App(){ return 1; }" : `export const value${index} = ${index};`,
  })),
  taro: [
    { path: "package.json", content: JSON.stringify({ dependencies: { "@tarojs/taro": "4.1.0", react: "19.2.0" } }) },
    { path: "src/app.tsx", content: 'import Taro from "@tarojs/taro"; import React from "react"; export function App(){ return <View />; }' },
  ],
  "uni-app": [
    { path: "package.json", content: JSON.stringify({ dependencies: { "@dcloudio/uni-app": "3.0.0", vue: "3.5.39" } }) },
    { path: "pages.json", content: JSON.stringify({ pages: [{ path: "pages/index/index" }] }) },
    { path: "pages/index/index.vue", content: "<template><view>Uni</view></template><script setup>import { ref } from 'vue'; const n=ref(0); uni.request({url:'/'});</script>" },
  ],
  "native-miniapp": [
    { path: "app.json", content: JSON.stringify({ pages: ["pages/index/index"] }) },
    { path: "pages/index/index.wxml", content: "<view><button>Native</button></view>" },
    { path: "pages/index/index.js", content: "Page({ data: { ready: true } });" },
  ],
} as const;

test("catalog owns exactly 22 Skills and MAPP-001 through MAPP-040 once", () => {
  assert.equal(MINIAPP_SKILL_CATALOG.length, 22);
  const tasks = MINIAPP_SKILL_CATALOG.flatMap(skill => skill.taskIds);
  assert.equal(tasks.length, 40);
  assert.equal(new Set(tasks).size, 40);
  assert.deepEqual([...tasks].sort(), Array.from({ length: 40 }, (_, index) => `MAPP-${String(index + 1).padStart(3, "0")}`));
});

test("all ten declared source labels reach a static candidate or an explicit blocker without source execution", () => {
  for (const [sourceLabel, declaredFiles] of Object.entries(sourceMatrix)) {
    const input = declaredFiles === undefined
      ? conversionInput(undefined, "vue3", ["wechat"])
      : conversionInput(declaredFiles, sourceLabel as Parameters<typeof conversionInput>[1], ["wechat"]);
    const run = runMiniappConversion(input);
    assert.equal(run.inventory.selectedSourceLabel, sourceLabel);
    assert.equal(run.analysis.sourceLabel, sourceLabel);
    assert.equal(run.generatedProjects.length, 1);
    assert.equal(run.generatedProjects[0]!.platform, "wechat");
    assert.equal(run.generatedProjects[0]!.staticValidation, "PASSED");
    assert.equal(run.generatedProjects[0]!.officialBuild, "NOT_RUN");
    assert.equal(run.certification, "NOT_CERTIFIED");
    if (run.generatedProjects[0]!.status === "GENERATED") {
      assert.ok(run.plan.findings.every(finding => !finding.blocking));
    } else {
      assert.ok(run.plan.findings.some(finding => finding.blocking));
      assert.equal(run.localEngineering, "BLOCKED");
    }
  }
});

test("unsupported control flow, route identity and binary assets fail closed instead of producing silent candidates", () => {
  const controlFlow = runMiniappConversion(conversionInput(exactReactFiles(`
    import React from "react";
    export const Conditional = () => authorized ? <main>A</main> : <main>B</main>;
    export function Logical(){ return authorized && <main>Secret</main>; }
    export const AsyncView = async () => <main>Async</main>;
    export function Fatal(){ throw "fatal"; return <main>Unreachable</main>; }
    export function Mutating(){ globalFlag = false; return <main>Mutation</main>; }
    export class Legacy extends React.Component { render(){ return <main>Visible</main>; } }
  `), "react", ["wechat"]));
  const controlCodes = new Set(controlFlow.plan.findings.map(finding => finding.code));
  assert.ok(controlCodes.has("MINIAPP_COMPONENT_CONTROL_FLOW_UNRESOLVED"));
  assert.ok(controlCodes.has("MINIAPP_COMPONENT_STATEMENTS_UNRESOLVED"));
  assert.ok(controlCodes.has("MINIAPP_ASYNC_COMPONENT_UNSUPPORTED"));
  assert.ok(controlCodes.has("MINIAPP_REACT_CLASS_COMPONENT_UNSUPPORTED"));
  assert.equal(controlFlow.gates.find(gate => gate.gate === "G3")?.state, "BLOCKED");
  assert.equal(controlFlow.localEngineering, "BLOCKED");

  const aliasRouteFiles = vueTodoFiles.map(file => file.path === "src/router.ts" ? {
    ...file,
    content: `import { createRouter } from "vue-router"; export default createRouter({ history: null, routes: [{ path: "/", component: () => import("@/App.vue") }] });`,
  } : file);
  const aliasRoute = runMiniappConversion(conversionInput(aliasRouteFiles, "vue3", ["wechat"]));
  assert.ok(aliasRoute.plan.findings.some(finding => finding.code === "MINIAPP_ROUTE_COMPONENT_UNRESOLVED" && finding.blocking));

  const bareRouteFiles = vueTodoFiles.map(file => file.path === "src/router.ts" ? {
    ...file,
    content: `import { createRouter } from "vue-router"; export default createRouter({ history: null, routes: [{ path: "/", component: () => import("src/App.vue") }] });`,
  } : file);
  const bareRoute = runMiniappConversion(conversionInput(bareRouteFiles, "vue3", ["wechat"]));
  assert.ok(bareRoute.plan.findings.some(finding => finding.code === "MINIAPP_ROUTE_COMPONENT_UNRESOLVED" && finding.blocking));

  const reservedRouteFiles = vueTodoFiles.map(file => file.path === "src/router.ts" ? {
    ...file,
    content: String(file.content).replace('path: "/"', 'path: "/CON"'),
  } : file);
  const reservedRoute = runMiniappConversion(conversionInput(reservedRouteFiles, "vue3", ["wechat"]));
  assert.ok(reservedRoute.plan.findings.some(finding =>
    finding.code === "MINIAPP_ROUTE_PATH_NOT_LOSSLESS" && finding.blocking));
  assert.equal(reservedRoute.generatedProjects[0]?.status, "GENERATED_WITH_BLOCKERS");

  const duplicateStemFiles = [
    ...vueTodoFiles.filter(file => file.path !== "src/App.vue" && file.path !== "src/router.ts"),
    { path: "src/views/Home.vue", content: "<template><main>Current</main></template>" },
    { path: "src/legacy/Home.vue", content: "<template><main>Legacy</main></template>" },
    { path: "src/router.ts", content: `import { createRouter } from "vue-router"; export default createRouter({ history: null, routes: [{ path: "/", component: "Home" }] });` },
  ];
  const duplicateStem = runMiniappConversion(conversionInput(duplicateStemFiles, "vue3", ["wechat"]));
  assert.ok(duplicateStem.plan.findings.some(finding => finding.code === "MINIAPP_ROUTE_COMPONENT_UNRESOLVED" && finding.blocking));

  const duplicateSubmitFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(
      '<button :disabled="!title.trim()" @click="submit">Add</button>',
      '<button :disabled="!title.trim()" @click="submit">Add A</button><button :disabled="!title.trim()" @click="submit">Add B</button>',
    ),
  } : file);
  const duplicateSubmit = runMiniappConversion(conversionInput(duplicateSubmitFiles, "vue3", ["wechat"]));
  assert.ok(duplicateSubmit.plan.findings.some(finding => finding.code === "MINIAPP_INTERACTION_COMPONENT_AMBIGUOUS" && finding.blocking));
  assert.equal(duplicateSubmit.gates.find(gate => gate.gate === "G3")?.state, "BLOCKED");

  const reorderedSubmitFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(
      'function submit(){ todos.add(title.value); title.value = ""; }',
      'function submit(){ title.value = ""; todos.add(title.value); }',
    ),
  } : file);
  const reorderedSubmit = runMiniappConversion(conversionInput(reorderedSubmitFiles, "vue3", ["wechat"]));
  assert.ok(reorderedSubmit.plan.findings.some(finding => finding.code === "MINIAPP_ACTION_BEHAVIOR_UNRESOLVED" && finding.blocking));

  const wrongStatePathFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace("todos.add(title.value)", "todos.add(other.title.value)"),
  } : file);
  const wrongStatePath = runMiniappConversion(conversionInput(wrongStatePathFiles, "vue3", ["wechat"]));
  assert.ok(wrongStatePath.plan.findings.some(finding => finding.code === "MINIAPP_ACTION_BEHAVIOR_UNRESOLVED" && finding.blocking));

  const duplicateAppendFiles = vueTodoFiles.map(file => file.path === "src/store.ts" ? {
    ...file,
    content: String(file.content).replace("this.items.push(value);", "this.items.push(value); this.items.push(value);"),
  } : file);
  const duplicateAppend = runMiniappConversion(conversionInput(duplicateAppendFiles, "vue3", ["wechat"]));
  assert.ok(duplicateAppend.plan.findings.some(finding => finding.code === "MINIAPP_ACTION_BEHAVIOR_UNRESOLVED" && finding.blocking));

  const auditAppendFiles = [
    ...vueTodoFiles.map(file => file.path === "src/store.ts" ? {
      ...file,
      content: `import { audit } from "./audit"; ${String(file.content).replace("this.items.push(value);", "this.items.push(value); audit.track(value);")}`,
    } : file),
    { path: "src/audit.ts", content: "export const audit = { track(_value: string) {} };" },
  ];
  const auditAppend = runMiniappConversion(conversionInput(auditAppendFiles, "vue3", ["wechat"]));
  assert.ok(auditAppend.plan.findings.some(finding => finding.code === "MINIAPP_ACTION_BEHAVIOR_UNRESOLVED" && finding.blocking));

  const todoPage = (storeName: string): string => `<script setup lang="ts">import { ref } from "vue"; import { useTodoStore } from "./${storeName}"; const title = ref(""); const todos = useTodoStore(); function submit(){ todos.add(title.value); title.value = ""; }</script>
<template><main><input v-model="title" required/><button :disabled="!title.trim()" @click="submit">Add</button><ul><li v-for="(item, index) in todos.items" :key="item + '-' + index">{{ item }}</li></ul></main></template>`;
  const duplicateStateKeyFiles = [
    ...vueTodoFiles.filter(file => file.path === "package.json" || file.path === "package-lock.json"),
    { path: "src/PageA.vue", content: todoPage("storeA") },
    { path: "src/PageB.vue", content: todoPage("storeB") },
    { path: "src/storeA.ts", content: `import { defineStore } from "pinia"; export const useTodoStore = defineStore("a", { state: () => ({ items: [] as string[] }), actions: { add(text: string) { const value = text.trim(); if (value) this.items.push(value); } } });` },
    { path: "src/storeB.ts", content: `import { defineStore } from "pinia"; export const useTodoStore = defineStore("b", { state: () => ({ items: [] as string[] }), actions: { add(text: string) { const value = text.trim(); if (value) this.items.push(value); } } });` },
    { path: "src/router.ts", content: `import { createRouter } from "vue-router"; export default createRouter({ history: null, routes: [{ path: "/a", component: () => import("./PageA.vue") }, { path: "/b", component: () => import("./PageB.vue") }] });` },
  ];
  const duplicateStateKey = runMiniappConversion(conversionInput(duplicateStateKeyFiles, "vue3", ["wechat"]));
  assert.ok(duplicateStateKey.plan.findings.some(finding => finding.code === "MINIAPP_INTERACTION_STATE_KEY_COLLISION" && finding.blocking));

  const ambiguousShellFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace('<div class="form-body">', '<RouterView/><RouterView/><div class="form-body">'),
  } : file);
  const ambiguousShell = runMiniappConversion(conversionInput(ambiguousShellFiles, "vue3", ["wechat"]));
  assert.ok(ambiguousShell.plan.findings.some(finding => finding.code === "MINIAPP_APPLICATION_SHELL_AMBIGUOUS" && finding.blocking));

  for (const [needle, replacement] of [
    ['@click="submit"', '@click.stop="submit"'],
    ['v-model="title"', 'v-model.trim="title"'],
    ['required/>', 'required pattern="[0-9]+"/>'],
    ['aria-label="Todo list"', 'aria-label="Todo list" aria-label="Other"'],
    ['<span aria-label="Todo list">Todos</span>', "<table><tr><td>Todos</td></tr></table><iframe></iframe><br/><hr/>"],
    ['<span aria-label="Todo list">Todos</span>', "<header><label>Todos</label></header>"],
    ["<style>", "<style module>"],
  ] as const) {
    const files = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
      ...file,
      content: String(file.content).replace(needle, replacement),
    } : file);
    const run = runMiniappConversion(conversionInput(files, "vue3", ["wechat"]));
    assert.ok(run.plan.findings.some(finding => finding.blocking), `${needle} must fail closed`);
    assert.equal(run.gates.find(gate => gate.gate === "G3")?.state, "BLOCKED", needle);
  }

  const boundedScopedSemanticFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content)
      .replace(
        '<span aria-label="Todo list">Todos</span>',
        '<main><h1>Todos</h1><nav><ul><li>One</li></ul></nav></main>',
      )
      .replace("<style>", "<style scoped>"),
  } : file);
  const boundedScopedSemantic = runMiniappConversion(conversionInput(boundedScopedSemanticFiles, "vue3", ["wechat"]));
  assert.ok(!boundedScopedSemantic.plan.findings.some(finding => [
    "MINIAPP_HTML_IMPLICIT_SEMANTICS_NOT_LOWERED",
    "MINIAPP_SCOPED_STYLE_NOT_LOWERED",
    "MINIAPP_EXTERNAL_STYLE_SOURCE_UNRESOLVED",
  ].includes(finding.code)));
  assert.equal(boundedScopedSemantic.generatedProjects[0]?.status, "GENERATED");
  const scopedTemplate = Object.entries(boundedScopedSemantic.generatedProjects[0]!.files)
    .find(([path]) => path.endsWith(".wxml"))?.[1] ?? "";
  const scopeClass = boundedScopedSemantic.semanticIr.components
    .flatMap(component => component.styleScopeClasses ?? [])[0];
  assert.match(scopeClass ?? "", /^elmos-scope-[a-f0-9]{12}$/u);
  assert.match(scopedTemplate, new RegExp(`class="[^"]*${scopeClass}`, "u"));
  assert.match(scopedTemplate, /aria-role="main"/u);
  assert.match(scopedTemplate, /aria-role="heading" aria-level="1"/u);
  assert.match(scopedTemplate, /aria-role="navigation"/u);
  assert.doesNotMatch(scopedTemplate, /<navigator\b[^>]*aria-role="navigation"/u);
  assert.match(scopedTemplate, /<view\b[^>]*aria-role="navigation"/u);
  assert.match(scopedTemplate, /aria-role="list"/u);
  assert.match(scopedTemplate, /aria-role="listitem"/u);
  const scopedStyles = Object.entries(boundedScopedSemantic.generatedProjects[0]!.files)
    .filter(([path]) => path.endsWith(".wxss"))
    .map(([, content]) => content)
    .join("\n");
  assert.match(scopedStyles, new RegExp(`\\.page\\.${scopeClass}\\s*\\{`, "u"));

  const forgedAccessibility = structuredClone(boundedScopedSemantic.semanticIr) as MiniappSemanticIr;
  const heading = forgedAccessibility.components.find(component => component.implicitAccessibility?.role === "heading");
  assert.ok(heading);
  (heading as unknown as { implicitAccessibility: { provenance: string; role: string; level: number; officialRuntimeVerification: string } }).implicitAccessibility = {
    provenance: "html-implicit",
    role: "main",
    level: 1,
    officialRuntimeVerification: "NOT_RUN",
  };
  assert.throws(() => validateMiniappSemanticIr(forgedAccessibility), /implicit accessibility/u);

  const forgedScopeClass = structuredClone(boundedScopedSemantic.semanticIr) as MiniappSemanticIr;
  const scopedComponent = forgedScopeClass.components.find(component => (component.styleScopeClasses?.length ?? 0) > 0);
  assert.ok(scopedComponent);
  (scopedComponent as unknown as { styleScopeClasses: string[] }).styleScopeClasses = ["elmos-scope-000000000000"];
  assert.throws(() => validateMiniappSemanticIr(forgedScopeClass), /scoped-style class/u);

  const inconsistentScopeOwnership = structuredClone(boundedScopedSemantic.semanticIr) as MiniappSemanticIr;
  const ownedComponent = inconsistentScopeOwnership.components.find(component => (component.styleScopeClasses?.length ?? 0) > 0);
  assert.ok(ownedComponent);
  (ownedComponent as unknown as { styleScopeClasses: string[] }).styleScopeClasses = [];
  assert.throws(() => validateMiniappSemanticIr(inconsistentScopeOwnership), /consistently owned/u);

  const deepScopedFiles = boundedScopedSemanticFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(".page {", ":deep(.page) {"),
  } : file);
  const deepScoped = runMiniappConversion(conversionInput(deepScopedFiles, "vue3", ["wechat"]));
  assert.ok(deepScoped.plan.findings.some(finding => finding.code === "MINIAPP_CSS_SELECTOR_UNRESOLVED" && finding.blocking));

  const externalScopedStyleFiles = [
    ...boundedScopedSemanticFiles.map(file => file.path === "src/App.vue" ? {
      ...file,
      content: String(file.content).replace(/<style scoped>[\s\S]*<\/style>/u, '<style scoped src="./external.css"></style>'),
    } : file),
    { path: "src/external.css", content: ".page { color: #111827; }" },
  ];
  const externalScopedStyle = runMiniappConversion(conversionInput(externalScopedStyleFiles, "vue3", ["wechat"]));
  assert.ok(externalScopedStyle.plan.findings.some(finding =>
    finding.code === "MINIAPP_EXTERNAL_STYLE_SOURCE_UNRESOLVED"
    && finding.classification === "D"
    && finding.blocking));
  assert.equal(externalScopedStyle.gates.find(gate => gate.gate === "G3")?.state, "BLOCKED");

  const buildPluginFiles = vueTodoFiles.map(file => {
    if (file.path === "package.json") {
      const manifest = JSON.parse(String(file.content)) as { devDependencies: Record<string, string> };
      manifest.devDependencies["@vitejs/plugin-vue"] = "5.2.1";
      return { ...file, content: JSON.stringify(manifest) };
    }
    if (file.path === "package-lock.json") {
      const lock = JSON.parse(String(file.content)) as { packages: Record<string, Record<string, unknown>> };
      (lock.packages[""]!.devDependencies as Record<string, string>)["@vitejs/plugin-vue"] = "5.2.1";
      lock.packages["node_modules/@vitejs/plugin-vue"] = { version: "5.2.1" };
      return { ...file, content: JSON.stringify(lock) };
    }
    return file;
  });
  const manifestOnlyBuildPlugin = runMiniappConversion(conversionInput(buildPluginFiles, "vue3", ["wechat"]));
  assert.equal(manifestOnlyBuildPlugin.plan.dependencies.find(item => item.dependency === "@vitejs/plugin-vue")?.action, "blocked");
  assert.ok(manifestOnlyBuildPlugin.plan.findings.some(finding =>
    finding.code === "MINIAPP_SOURCE_BUILD_CONFIG_MISSING_OR_INVALID" && finding.blocking));

  const buildPluginWithConfig = [
    ...buildPluginFiles,
    {
      path: "vite.config.ts",
      content: 'import { defineConfig } from "vite"; import vue from "@vitejs/plugin-vue"; export default defineConfig({ plugins: [vue()] });',
    },
  ];
  const buildPlugin = runMiniappConversion(conversionInput(buildPluginWithConfig, "vue3", ["wechat"]));
  const pluginDecision = buildPlugin.plan.dependencies.find(item => item.dependency === "@vitejs/plugin-vue");
  assert.equal(pluginDecision?.action, "rewrite");
  assert.equal(pluginDecision?.replacement, "semantic-ir-native-generation");
  assert.ok(pluginDecision?.usageEvidence.some(item => item.includes("locked-5.2.1")));
  assert.ok(pluginDecision?.usageEvidence.some(item => /^vite\.config\.ts:config-sha256:[a-f0-9]{64}$/u.test(item)));
  assert.ok(!buildPlugin.plan.findings.some(finding => finding.code === "MINIAPP_DEPENDENCY_ADAPTER_NOT_WIRED"
    && finding.message.startsWith("@vitejs/plugin-vue:")));
  assert.ok(!buildPlugin.plan.findings.some(finding => finding.code === "MINIAPP_SOURCE_BUILD_CONFIG_MISSING_OR_INVALID"));

  for (const invalidConfig of [
    'import { defineConfig } from "vite"; import vue from "@vitejs/plugin-vue"; export default defineConfig({ plugins: [] });',
    'import { defineConfig } from "vite"; import vue from "@vitejs/plugin-vue"; export default defineConfig({ plugins: [enabled ? vue() : null] });',
    'import { defineConfig } from "vite"; import vue from "@vitejs/plugin-vue"; export default defineConfig({ plugins: [vue(), vue()] });',
    'import { defineConfig } from "vite"; import vue from "@vitejs/plugin-vue"; const plugins = [vue()]; export default defineConfig({ plugins });',
  ]) {
    const invalidBuildPlugin = runMiniappConversion(conversionInput([
      ...buildPluginFiles,
      { path: "vite.config.ts", content: invalidConfig },
    ], "vue3", ["wechat"]));
    assert.ok(invalidBuildPlugin.inventory.findings.some(finding =>
      finding.code === "MINIAPP_CONFIG_PARSE_ERROR" && finding.paths.includes("vite.config.ts")));
    assert.equal(invalidBuildPlugin.plan.dependencies.find(item => item.dependency === "@vitejs/plugin-vue")?.action, "blocked");
    assert.ok(invalidBuildPlugin.plan.findings.some(finding =>
      finding.code === "MINIAPP_SOURCE_BUILD_CONFIG_MISSING_OR_INVALID" && finding.blocking));
  }
  const formFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content)
      .replace('<div class="form-body">', "<form>")
      .replace("</div></div></div></template>", "</div></form></div></template>"),
  } : file);
  const formRun = runMiniappConversion(conversionInput(formFiles, "vue3", ["wechat"]));
  assert.ok(formRun.plan.findings.some(finding => finding.code === "MINIAPP_SOURCE_CONTROL_TAG_UNSUPPORTED" && finding.blocking));

  const entityFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace('<span aria-label="Todo list">Todos</span>', '<span aria-label="Entity text">Tom &amp; Jerry &#38; &#x4a; &copy; &reg</span>'),
  } : file);
  const entityRun = runMiniappConversion(conversionInput(entityFiles, "vue3", ["wechat"]));
  const entityTemplate = Object.entries(entityRun.generatedProjects[0]!.files).find(([path]) => path.endsWith(".wxml"))?.[1] ?? "";
  assert.match(entityTemplate, /Tom &amp; Jerry &amp; J/u);
  assert.match(entityTemplate, /©/u);
  assert.match(entityTemplate, /®/u);
  assert.doesNotMatch(entityTemplate, /&amp;amp;/u);

  const unknownEntityFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace("Todos</span>", "&unsupportedEntity;</span>"),
  } : file);
  const unknownEntity = runMiniappConversion(conversionInput(unknownEntityFiles, "vue3", ["wechat"]));
  assert.ok(unknownEntity.plan.findings.some(finding => finding.code === "MINIAPP_TEMPLATE_PARSE_FAILED" && finding.blocking));

  for (const invalidCss of [
    ".page { color: ; }",
    ".page { color }",
    ".page { : red; }",
    ".page[ { color: red; }",
    ".page { width: calc(1px + ); }",
    ".page { width: calc(); }",
    ".page { color: rgb(255,,0); }",
    ".page { color: red !garbage; }",
    "@property --tone { syntax: '<color>'; } .page { color: red; }",
  ]) {
    const files = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
      ...file,
      content: String(file.content).replace(".page { padding: 16px; color: #111827; }", invalidCss),
    } : file);
    const run = runMiniappConversion(conversionInput(files, "vue3", ["wechat"]));
    assert.ok(run.plan.findings.some(finding => [
      "MINIAPP_CSS_AT_RULE_REQUIRES_AST",
      "MINIAPP_CSS_DECLARATION_UNRESOLVED",
      "MINIAPP_CSS_SELECTOR_UNRESOLVED",
      "MINIAPP_CSS_VALUE_UNRESOLVED",
    ].includes(finding.code) && finding.blocking), invalidCss);
  }

  const reportOnlyStyleFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(".page { padding: 16px; color: #111827; }", ".page { width: 100vw; }"),
  } : file);
  const reportOnlyStyleInput = conversionInput(reportOnlyStyleFiles, "vue3", ["wechat"]);
  const reportOnlyStyleRequest = validateMiniappConversionRequest(reportOnlyStyleInput.request);
  const reportOnlyStyle = runMiniappConversion({
    ...reportOnlyStyleInput,
    request: {
      ...reportOnlyStyleRequest,
      policy: {
        ...reportOnlyStyleRequest.policy,
        unsupportedPolicy: "report-and-continue-noncritical",
      },
    },
  });
  assert.ok(reportOnlyStyle.plan.findings.some(finding =>
    finding.code === "MINIAPP_STYLE_REDESIGN_REQUIRED" && finding.blocking));
  assert.equal(reportOnlyStyle.generatedProjects[0]?.status, "GENERATED_WITH_BLOCKERS");

  const tagSelectorFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(
      ".page { padding: 16px; color: #111827; }",
      "div.page { padding: 16px; color: #111827; }",
    ),
  } : file);
  const tagSelector = runMiniappConversion(conversionInput(tagSelectorFiles, "vue3", ["wechat"]));
  assert.ok(tagSelector.plan.styles[0]?.rules.some(rule => rule.selector === "view.page" && rule.classification === "A"));
  const tagSelectorStyles = Object.entries(tagSelector.generatedProjects[0]!.files)
    .filter(([path]) => path.endsWith(".wxss"))
    .map(([, content]) => content)
    .join("\n");
  assert.match(tagSelectorStyles, /view\.page\s*\{/u);
  assert.doesNotMatch(tagSelectorStyles, /(?:^|\n)div\.page\s*\{/u);

  const unsupportedCssCapabilityFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(
      ".page { padding: 16px; color: #111827; }",
      ".page { display: grid; color: #111827; }",
    ),
  } : file);
  const unsupportedCssCapability = runMiniappConversion(conversionInput(unsupportedCssCapabilityFiles, "vue3", ["wechat"]));
  assert.ok(unsupportedCssCapability.plan.findings.some(finding =>
    finding.code === "MINIAPP_STYLE_REDESIGN_REQUIRED"
    && finding.message.includes("display-mode-not-portable")
    && finding.blocking));

  const staticDisabledFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replace(
      ':disabled="!title.trim()"',
      'disabled="disabled"',
    ),
  } : file);
  const staticDisabled = runMiniappConversion(conversionInput(staticDisabledFiles, "vue3", ["wechat"]));
  assert.ok(staticDisabled.plan.findings.every(finding =>
    finding.code !== "MINIAPP_SOURCE_ATTRIBUTE_UNSUPPORTED" || !finding.message.includes("disabled")));
  const staticDisabledTemplate = Object.entries(staticDisabled.generatedProjects[0]!.files)
    .find(([path]) => path.endsWith(".wxml"))?.[1] ?? "";
  assert.match(staticDisabledTemplate, /disabled="true"/u);
  assert.doesNotMatch(staticDisabledTemplate, /disabled="\{\{!canSubmit/u);

  const assetRun = runMiniappConversion(conversionInput([
    ...vueTodoFiles,
    { path: "assets/logo.png", content: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 1, 2, 3]) },
    { path: "assets/payload.bin", content: new Uint8Array([0, 1, 2, 3]) },
  ], "vue3", ["wechat"]));
  assert.deepEqual(assetRun.plan.findings
    .filter(finding => finding.code === "MINIAPP_ASSET_NOT_MATERIALIZED")
    .map(finding => finding.message.split(" ", 1)[0]), ["assets/logo.png", "assets/payload.bin"]);
  assert.equal(assetRun.generatedProjects[0]?.status, "GENERATED_WITH_BLOCKERS");

  const unsupportedSourceRun = runMiniappConversion(conversionInput([
    ...vueTodoFiles,
    { path: "src/Widget.svelte", content: "<script>let value = 1;</script><button>{value}</button>" },
    { path: "src/page.astro", content: "---\nconst title = 'x';\n---\n<h1>{title}</h1>" },
    { path: "src/view.mdx", content: "# Hidden source semantics" },
    { path: "src/template.pug", content: "button Hidden" },
    { path: "src/view.hbs", content: "<button>{{hidden}}</button>" },
    { path: "src/runtime.dat", content: "opaque runtime text" },
  ], "vue3", ["wechat"]));
  assert.ok(unsupportedSourceRun.inventory.findings.some(finding => finding.code === "MINIAPP_SOURCE_FILE_UNSUPPORTED" && finding.blocking));
  assert.ok(unsupportedSourceRun.inventory.findings.some(finding => finding.code === "MINIAPP_SOURCE_FILE_UNCLASSIFIED" && finding.blocking));
  assert.equal(unsupportedSourceRun.gates.find(gate => gate.gate === "G1")?.state, "BLOCKED");
  assert.equal(unsupportedSourceRun.localEngineering, "BLOCKED");

  for (const source of [
    'const cfg = { appSecret: ["raw-secret-123456"] }; export function App(){ return <div>Secret</div>; }',
    'const accessToken = "vault://tenant/token" + suffix; export function App(){ return <div>Secret</div>; }',
    'export function App(){ return <div authorization={sessionValue}>Secret</div>; }',
    'globalThis.appSecret = ["raw-session-secret"]; export function App(){ return <div>Secret</div>; }',
    'class Holder { appSecret = ["raw-session-secret"]; } export function App(){ return <div>Secret</div>; }',
    'localStorage.setItem("accessToken", tokenValue); export function App(){ return <div>Secret</div>; }',
  ]) {
    const secretExpression = runMiniappConversion(conversionInput(exactReactFiles(source), "react", ["wechat"]));
    assert.ok(secretExpression.plan.findings.some(finding => finding.code === "MINIAPP_SOURCE_SECRET_REFERENCE_REQUIRED" && finding.blocking));
  }

  const computedSecretKey = runMiniappConversion(conversionInput(exactReactFiles(
    'const secretKey = "appSecret"; const config = { [secretKey]: "raw-secret-123456" }; void config; export function App(){ return <div>Secret</div>; }',
  ), "react", ["wechat"]));
  assert.ok(computedSecretKey.plan.findings.some(finding =>
    finding.code === "MINIAPP_COMPUTED_PROPERTY_SEMANTICS_UNRESOLVED" && finding.blocking));

  const sensitivePlatformCapability = runMiniappConversion(conversionInput(exactReactFiles(
    'export function App(){ wx.chooseMedia({ count: 1 }); return <div>Media</div>; }',
  ), "react", ["wechat"]));
  const mediaDecision = sensitivePlatformCapability.plan.capabilities.find(decision =>
    decision.capabilityName === "platform.chooseMedia");
  assert.equal(mediaDecision?.classification, "D");
  assert.deepEqual(mediaDecision?.permission, ["media-selection"]);
  assert.ok(sensitivePlatformCapability.plan.findings.some(finding =>
    finding.code === "MINIAPP_CAPABILITY_D" && finding.blocking));

  for (const source of [
    'export function App(){ return <div><input required /></div>; }',
    'export function App(){ return <div><input autoFocus /></div>; }',
  ]) {
    const formConstraint = runMiniappConversion(conversionInput(exactReactFiles(source), "react", ["wechat"]));
    assert.ok(formConstraint.plan.findings.some(finding => finding.code === "MINIAPP_SOURCE_ATTRIBUTE_UNSUPPORTED" && finding.blocking));
  }

  const duplicateJsxAttribute = runMiniappConversion(conversionInput(exactReactFiles(
    'export function App(){ return <div aria-label="First" aria-label="Second">Duplicate</div>; }',
  ), "react", ["wechat"]));
  assert.ok(duplicateJsxAttribute.plan.findings.some(finding =>
    ["MINIAPP_JSX_DUPLICATE_ATTRIBUTE", "MINIAPP_SOURCE_PARSE_FAILED"].includes(finding.code)
    && finding.blocking));

  const dangerousStateFiles = vueTodoFiles.map(file => file.path === "src/App.vue" ? {
    ...file,
    content: String(file.content).replaceAll("title", "__proto__"),
  } : file);
  const dangerousState = runMiniappConversion(conversionInput(dangerousStateFiles, "vue3", ["wechat"]));
  assert.ok(dangerousState.plan.findings.some(finding => finding.code === "MINIAPP_INTERACTION_STATE_KEY_UNSAFE" && finding.blocking));
});

test("full runtime is deterministic, resumable and keeps external gates fail closed", () => {
  const input = conversionInput(undefined, undefined, ["wechat"]);
  const first = runMiniappConversion(input);
  const second = runMiniappConversion(input);
  assert.equal(first.deterministicDigest, second.deterministicDigest);
  assert.equal(first.checkpoint.checkpointDigest, second.checkpoint.checkpointDigest);
  assert.equal(first.taskRecords.length, 40);
  assert.equal(first.localEngineering, "PASSED");
  assert.equal(first.readiness, "NOT_READY");
  assert.equal(first.certification, "NOT_CERTIFIED");
  assert.deepEqual(first.gates.slice(0, 4).map(gate => gate.state), ["PASSED", "PASSED", "PASSED", "PASSED"]);
  assert.ok(first.gates.slice(4).every(gate => gate.state === "NOT_RUN"));
  assert.ok(first.evidenceGraph.length >= 7);
  assert.ok(first.evidenceGraph.every(node => /^sha256:[a-f0-9]{64}$/.test(node.digest) && node.byteCount > 0));
  const adapter = first.generatedProjects[0]?.files["adapters/platform.js"] ?? "";
  assert.match(adapter, /platform: "wechat"/u);
  assert.doesNotMatch(adapter, /\b(?:request|navigateTo|getStorage|setStorage):/u,
    "a source with no platform capabilities must not receive ambient adapter authority");
  const resumed = runMiniappConversion({ ...input, resumeFrom: first.checkpoint });
  assert.equal(resumed.resumed, true);
  assert.equal(resumed.inputDigest, first.inputDigest);
  assert.equal(resumed.checkpoint.checkpointDigest, first.checkpoint.checkpointDigest);
});

test("every installed Skill has a callable distinct handler result", () => {
  const input = conversionInput(undefined, undefined, ["wechat"]);
  const results = MINIAPP_SKILL_CATALOG.map(skill => executeMiniappSkill(skill.name, input));
  assert.equal(results.length, 22);
  assert.equal(new Set(results.map(result => result.skill)).size, 22);
  assert.ok(results.every(result => result.runId && result.inputDigest && result.certification === "NOT_CERTIFIED"));
  for (const result of results) {
    const contract = MINIAPP_DECLARED_OUTPUT_CATALOG.find(skill => skill.ownerSkill === result.skill);
    assert.ok(contract);
    assert.deepEqual(
      result.declaredOutputs.map(artifact => artifact.declaredPattern).sort(),
      [...contract.requiredOutputs].sort(),
    );
    assert.ok(result.declaredOutputs.every(artifact =>
      artifact.ownerSkill === result.skill
      && /^sha256:[a-f0-9]{64}$/.test(artifact.digest)
      && artifact.bytes === Buffer.byteLength(artifact.content, "utf8")
    ));
  }
  assert.equal(executeMiniappSkill("react-to-miniapp-analyzer", input).state, "NOT_APPLICABLE");
  assert.equal(executeMiniappSkill("wechat-miniapp-codegen", input).state, "EXECUTED");
  assert.equal(executeMiniappSkill("miniapp-third-party-dependency-migrator", input).state, "NOT_RUN");
  for (const skill of ["miniapp-differential-testing", "miniapp-visual-regression-testing", "miniapp-auto-repair-loop", "miniapp-ci-build-release"] as const) {
    const result = executeMiniappSkill(skill, input);
    assert.equal(result.state, "NOT_RUN");
    assert.ok(result.taskRecords.every(record => record.state === "NOT_RUN_EXTERNAL"));
  }
});

test("handler and JSON port reject extra keys, bad snapshots and unknown Skills", () => {
  const conversion = conversionInput();
  assert.throws(() => handleMiniappSkillRequest({ schemaVersion: "1.0", action: "run-all", conversion, extra: true }), /not allowed/);
  assert.throws(() => handleMiniappSkillRequest({ schemaVersion: "1.0", action: "run-skill", conversion, skill: "unknown" }), /installed miniapp Skill/);
  assert.throws(() => runMiniappConversion({
    ...conversion,
    request: { ...(conversion.request as object), source: { ...(conversion.request as { source: object }).source, snapshotDigest: `sha256:${"0".repeat(64)}` } },
  }), /snapshot digest mismatch/);
  assert.throws(() => runMiniappSkillJson("{"), /valid JSON/);
  assert.throws(() => computeMiniappSourceFileSetDigest([{ path: "../escape.ts", content: "x" }]), /relative|normalized/);
  assert.throws(() => computeMiniappSourceFileSetDigest([{ path: "index.ts", content: "x", extra: true } as never]), /not allowed/);
  assert.throws(() => computeMiniappSourceFileSetDigest([
    { path: "index.ts", content: "x" },
    { path: "index.ts", content: "y" },
  ]), /duplicates/);
  const parsed = JSON.parse(runMiniappSkillJson(JSON.stringify({ schemaVersion: "1.0", action: "run-skill", skill: "miniapp-semantic-ir", conversion }))) as { skill: string };
  assert.equal(parsed.skill, "miniapp-semantic-ir");
});

test("CLI catalog and atomic native project materialization are executable", () => {
  const catalog = spawnSync(process.execPath, ["dist/src/miniapp-cli.js", "catalog"], { encoding: "utf8" });
  assert.equal(catalog.status, 0, catalog.stderr);
  assert.equal((JSON.parse(catalog.stdout) as { skills: unknown[] }).skills.length, 22);
  const unsafeDigest = spawnSync(process.execPath, ["dist/src/miniapp-cli.js", "digest"], {
    input: JSON.stringify({ files: [{ path: "../escape.ts", content: "x" }] }),
    encoding: "utf8",
  });
  assert.notEqual(unsafeDigest.status, 0);
  assert.match(unsafeDigest.stderr, /relative|normalized/);
  const invalidUtf8Pipe = spawnSync(process.execPath, ["dist/src/miniapp-cli.js", "run"], {
    input: Buffer.from([0xff]),
    encoding: "utf8",
  });
  assert.notEqual(invalidUtf8Pipe.status, 0);
  assert.match(invalidUtf8Pipe.stderr, /input must be valid UTF-8/u);

  const temporary = mkdtempSync(join(tmpdir(), "elmos-miniapp-cli-"));
  const target = join(temporary, "generated");
  try {
    const catalogOutput = join(temporary, "catalog-output.json");
    const catalogToFile = spawnSync(
      process.execPath,
      ["dist/src/miniapp-cli.js", "catalog", "--output", catalogOutput],
      { encoding: "utf8" },
    );
    assert.equal(catalogToFile.status, 0, catalogToFile.stderr);
    const catalogFileContent = readFileSync(catalogOutput, "utf8");
    assert.equal((JSON.parse(catalogFileContent) as { skills: unknown[] }).skills.length, 22);
    const catalogOverwrite = spawnSync(
      process.execPath,
      ["dist/src/miniapp-cli.js", "catalog", "--output", catalogOutput],
      { encoding: "utf8" },
    );
    assert.notEqual(catalogOverwrite.status, 0);
    assert.match(catalogOverwrite.stderr, /must not already exist/u);
    assert.equal(readFileSync(catalogOutput, "utf8"), catalogFileContent);

    const invalidUtf8File = join(temporary, "invalid-utf8.json");
    writeFileSync(invalidUtf8File, Buffer.from([0x7b, 0xff, 0x7d]));
    const invalidUtf8Input = spawnSync(
      process.execPath,
      ["dist/src/miniapp-cli.js", "run", "--input", invalidUtf8File],
      { encoding: "utf8" },
    );
    assert.notEqual(invalidUtf8Input.status, 0);
    assert.match(invalidUtf8Input.stderr, /input must be valid UTF-8/u);
    const request = JSON.stringify({ schemaVersion: "1.0", action: "run-all", conversion: conversionInput() });
    const nestedOutput = spawnSync(
      process.execPath,
      [
        "dist/src/miniapp-cli.js",
        "run",
        "--output",
        join(target, "unindexed-result.json"),
        "--materialize",
        target,
      ],
      { input: request, encoding: "utf8" },
    );
    assert.notEqual(nestedOutput.status, 0);
    assert.match(nestedOutput.stderr, /cannot be combined/u);
    assert.equal(existsSync(target), false);

    const ancestorOutput = spawnSync(
      process.execPath,
      [
        "dist/src/miniapp-cli.js",
        "run",
        "--output",
        target,
        "--materialize",
        join(target, "nested"),
      ],
      { input: request, encoding: "utf8" },
    );
    assert.notEqual(ancestorOutput.status, 0);
    assert.match(ancestorOutput.stderr, /cannot be combined/u);
    assert.equal(existsSync(target), false);

    const result = spawnSync(process.execPath, ["dist/src/miniapp-cli.js", "run", "--materialize", target], {
      input: request,
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
    });
    assert.equal(result.status, 0, result.stderr);
    const run = JSON.parse(result.stdout) as MiniappConversionRun;
    assert.equal(existsSync(join(target, "local-run-summary.json")), false);
    const migrationEvidence = JSON.parse(readFileSync(join(
      target,
      "runs",
      run.runId,
      "declared-outputs",
      "miniapp-migration-evidence-reporter",
      "migration-evidence.json",
    ), "utf8")) as { release_status: string };
    assert.equal(migrationEvidence.release_status, "not-ready");
    const generated = materializeMiniappGeneratedProjectArtifacts(run);
    assert.deepEqual(
      [...new Set(generated.map(artifact => artifact.platform))],
      ["wechat", "alipay"],
    );
    for (const artifact of generated) {
      assert.equal(
        readFileSync(join(target, artifact.materializedPath), "utf8"),
        artifact.content,
      );
      assert.equal(
        existsSync(join(target, artifact.platform, artifact.sourcePath)),
        false,
      );
    }
    for (const platform of ["wechat", "alipay"]) {
      assert.ok(generated.some(artifact =>
        artifact.platform === platform && artifact.sourcePath === "app.json"));
    }
    const declared = materializeMiniappDeclaredOutputs(run);
    for (const platform of ["douyin", "xiaohongshu"] as const) {
      assert.equal(generated.some(artifact => artifact.platform === platform), false);
      const wildcard = declared.find(artifact =>
        artifact.declaredPattern === `platforms/${platform}/**`);
      assert.ok(wildcard);
      assert.equal(wildcard.state, "BLOCKED");
      assert.ok(wildcard.materializedPath.endsWith("/blocked-surrogate-index.json"));
      assert.equal(
        readFileSync(join(target, wildcard.materializedPath), "utf8"),
        wildcard.content,
      );
      assert.deepEqual(
        (JSON.parse(wildcard.content) as { readonly files: readonly unknown[] }).files,
        [],
      );
      assert.equal(
        existsSync(join(
          target,
          materializeMiniappGeneratedProjectBasePath(run, platform),
          "app.json",
        )),
        false,
      );
    }
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});

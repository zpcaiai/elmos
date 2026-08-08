import { compileTemplate, parse as parseVueSfc } from "@vue/compiler-sfc";
import ts from "typescript";

import {
  assertDeclaredIrMatchesSource,
  canonical,
  frtRouteStackSet,
  frtRouteStacks,
  gap,
  sha256,
  type FrtRouteStack,
  type FrtRouteTypedGap,
  type PortableUiIr,
  type SourceReference,
} from "./frt-route-ir.js";
import { deriveReactPortableUiIr } from "./react-ui-ir.js";
import { deriveVue3PortableUiIr } from "./vue3-ui-ir.js";
import {
  deriveArkUiPortableUiIr,
  deriveFlutterPortableUiIr,
  deriveMiniProgramPortableUiIr,
  deriveVue2PortableUiIr,
} from "./additional-ui-ir.js";
import { attachRunnableTarget } from "./frt-runnable-target.js";

export {
  frtRouteStacks,
  type FrtRouteStack,
  type FrtRouteTypedGap,
  type PortableUiIr,
  type SourceReference,
};

/**
 * Source stacks with a real extractor, i.e. stacks whose IR is read out of the
 * source bytes rather than taken on trust from a declaration.
 *
 * A stack joins this set only when its extractor exists and its typed gaps are
 * registered in the catalogue. Every stack not listed here still runs on a
 * declared IR, and the result says so through `irProvenance` instead of
 * implying more rigour than the route actually has.
 */
export const frtSourceDerivedStacks: ReadonlySet<FrtRouteStack> =
  new Set<FrtRouteStack>(frtRouteStacks);

/**
 * Where the IR that drove this conversion came from.
 *
 * - `SOURCE_DERIVED` — extracted from the source bytes; nothing was declared.
 * - `DECLARED_CROSS_CHECKED` — declared, and every field it asserts was checked
 *   against the same source and agreed.
 * - `DECLARED` — declared and schema-validated, but this source stack has no
 *   extractor yet, so the declaration was not cross-checked.
 * - `NONE` — no IR survived validation; the route is blocked.
 */
export type FrtIrProvenance =
  | "SOURCE_DERIVED"
  | "DECLARED_CROSS_CHECKED"
  | "DECLARED"
  | "NONE";

export interface DirectionalRouteResult {
  readonly route: string;
  readonly source: FrtRouteStack;
  readonly target: FrtRouteStack;
  readonly status: "GENERATED" | "BLOCKED";
  readonly sourceFiles: readonly string[];
  readonly sourceSnapshotDigest?: string;
  readonly generatedFiles: Readonly<Record<string, string>>;
  readonly mappings: readonly string[];
  readonly typedGaps: readonly FrtRouteTypedGap[];
  readonly irProvenance: FrtIrProvenance;
  readonly sourceValidation: "PASSED" | "BLOCKED";
  readonly targetValidation: "PASSED" | "BLOCKED";
  readonly sourceBuild: "NOT_RUN";
  readonly targetBuild: "NOT_RUN";
  readonly browserJourney: "NOT_RUN";
  readonly certification: "NOT_CERTIFIED";
}

const digestPattern = /^sha256:[a-f0-9]{64}$/;
const exactVersion = /^(?:[0-9]+\.)+[0-9]+(?:\([0-9]+\))?$/;
const safePath = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9._@/-]{1,512}$/;
const safeColor = /^#[0-9A-Fa-f]{6}$/;
function exactObject(
  value: unknown,
  keys: readonly string[],
  name: string,
): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length
      || keys.some(key => !Object.hasOwn(record, key))) {
    throw new Error(`${name} fields are not exact`);
  }
  return record;
}

function boundedText(value: unknown, name: string, maximum = 160): string {
  if (typeof value !== "string" || value.length < 1 || value.length > maximum
      || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error(`${name} is invalid`);
  }
  return value;
}

function integer(value: unknown, name: string, minimum: number, maximum: number): number {
  if (!Number.isInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new Error(`${name} is invalid`);
  }
  return value as number;
}

function emptyArray(value: unknown, name: string): readonly [] {
  if (!Array.isArray(value) || value.length !== 0) throw new Error(`${name} must be empty`);
  return [];
}

function parsePortableUiIr(
  files: Readonly<Record<string, string>>,
  expectedSource: FrtRouteStack,
): PortableUiIr {
  const raw = files["frt-ui-ir.json"];
  if (raw === undefined) throw new Error("frt-ui-ir.json is required");
  const root = exactObject(JSON.parse(raw), [
    "schemaVersion",
    "source",
    "sourceSnapshotDigest",
    "sourceRefs",
    "route",
    "view",
    "style",
    "accessibility",
    "capabilities",
  ], "route IR");
  if (root.schemaVersion !== "1.0") throw new Error("route IR schemaVersion is unsupported");
  const source = exactObject(root.source, ["stack", "version"], "route IR source");
  if (source.stack !== expectedSource || !frtRouteStackSet.has(String(source.stack))) {
    throw new Error("route IR source stack does not match the selected route");
  }
  if (typeof source.version !== "string" || !exactVersion.test(source.version)) {
    throw new Error("route IR source version is not exact");
  }
  if (typeof root.sourceSnapshotDigest !== "string" || !digestPattern.test(root.sourceSnapshotDigest)) {
    throw new Error("route IR sourceSnapshotDigest is invalid");
  }
  if (!Array.isArray(root.sourceRefs) || root.sourceRefs.length < 1 || root.sourceRefs.length > 32) {
    throw new Error("route IR sourceRefs are invalid");
  }
  const seen = new Set<string>();
  const sourceRefs = root.sourceRefs.map((entry, index) => {
    const reference = exactObject(entry, ["path", "sha256"], `sourceRefs[${index}]`);
    if (typeof reference.path !== "string" || !safePath.test(reference.path)
        || reference.path === "frt-ui-ir.json" || seen.has(reference.path)) {
      throw new Error(`sourceRefs[${index}].path is invalid`);
    }
    if (typeof reference.sha256 !== "string" || !digestPattern.test(reference.sha256)) {
      throw new Error(`sourceRefs[${index}].sha256 is invalid`);
    }
    const content = files[reference.path];
    if (content === undefined || sha256(content) !== reference.sha256) {
      throw new Error(`sourceRefs[${index}] does not match source bytes`);
    }
    seen.add(reference.path);
    return { path: reference.path, sha256: reference.sha256 };
  }).sort((left, right) => left.path.localeCompare(right.path));
  if (sha256(canonical(sourceRefs)) !== root.sourceSnapshotDigest) {
    throw new Error("route IR source snapshot digest does not match its references");
  }
  const route = exactObject(root.route, ["path", "requiresAuth", "deepLink"], "route IR route");
  if (route.path !== "/" || route.requiresAuth !== false || route.deepLink !== true) {
    throw new Error("this route slice supports one public deep-linked root route");
  }
  const view = exactObject(root.view, [
    "title", "initialCount", "incrementBy", "buttonLabel",
  ], "route IR view");
  const style = exactObject(root.style, ["accentColor"], "route IR style");
  if (typeof style.accentColor !== "string" || !safeColor.test(style.accentColor)) {
    throw new Error("route IR accentColor is invalid");
  }
  const accessibility = exactObject(root.accessibility, [
    "mainLabel", "buttonLabel", "liveRegion",
  ], "route IR accessibility");
  if (accessibility.liveRegion !== "polite") throw new Error("route IR liveRegion is unsupported");
  const capabilities = exactObject(root.capabilities, [
    "permissions", "native", "network",
  ], "route IR capabilities");
  return {
    schemaVersion: "1.0",
    source: { stack: source.stack as FrtRouteStack, version: source.version },
    sourceSnapshotDigest: root.sourceSnapshotDigest,
    sourceRefs,
    route: { path: "/", requiresAuth: false, deepLink: true },
    view: {
      title: boundedText(view.title, "route IR title"),
      initialCount: integer(view.initialCount, "route IR initialCount", -1_000_000, 1_000_000),
      incrementBy: integer(view.incrementBy, "route IR incrementBy", -1_000, 1_000),
      buttonLabel: boundedText(view.buttonLabel, "route IR buttonLabel"),
    },
    style: { accentColor: style.accentColor },
    accessibility: {
      mainLabel: boundedText(accessibility.mainLabel, "route IR mainLabel"),
      buttonLabel: boundedText(accessibility.buttonLabel, "route IR accessibility.buttonLabel"),
      liveRegion: "polite",
    },
    capabilities: {
      permissions: emptyArray(capabilities.permissions, "route IR permissions"),
      native: emptyArray(capabilities.native, "route IR native capabilities"),
      network: emptyArray(capabilities.network, "route IR network capabilities"),
    },
  };
}

function sourceText(files: Readonly<Record<string, string>>, refs: readonly SourceReference[], extension: string): string {
  const reference = refs.find(item => item.path.endsWith(extension));
  if (!reference) throw new Error(`source snapshot is missing ${extension}`);
  return files[reference.path]!;
}

function balancedTokens(source: string): string[] {
  const tokens: string[] = [];
  const pairs: Record<string, string> = { "(": ")", "[": "]", "{": "}" };
  const stack: string[] = [];
  let index = 0;
  while (index < source.length) {
    const char = source[index]!;
    if (/\s/.test(char)) { index += 1; continue; }
    if (char === "/" && source[index + 1] === "/") {
      index += 2;
      while (index < source.length && source[index] !== "\n") index += 1;
      continue;
    }
    if (char === "/" && source[index + 1] === "*") {
      const end = source.indexOf("*/", index + 2);
      if (end < 0) throw new Error("source contains an unterminated comment");
      index = end + 2;
      continue;
    }
    if (["\"", "'", "`"].includes(char)) {
      const quote = char;
      let value = quote;
      index += 1;
      let closed = false;
      while (index < source.length) {
        const item = source[index]!;
        value += item;
        index += 1;
        if (item === "\\" && index < source.length) {
          value += source[index]!;
          index += 1;
        } else if (item === quote) {
          closed = true;
          break;
        }
      }
      if (!closed) throw new Error("source contains an unterminated string");
      tokens.push(value);
      continue;
    }
    if (/[A-Za-z_$@]/.test(char)) {
      let value = char;
      index += 1;
      while (index < source.length && /[A-Za-z0-9_$]/.test(source[index]!)) {
        value += source[index]!;
        index += 1;
      }
      tokens.push(value);
      continue;
    }
    if (Object.hasOwn(pairs, char)) stack.push(pairs[char]!);
    else if ([")", "]", "}"].includes(char) && stack.pop() !== char) {
      throw new Error("source delimiters are unbalanced");
    }
    tokens.push(char);
    index += 1;
  }
  if (stack.length) throw new Error("source delimiters are unbalanced");
  return tokens;
}

function requireTokens(tokens: readonly string[], required: readonly string[], stack: FrtRouteStack): void {
  for (const token of required) {
    if (!tokens.includes(token)) throw new Error(`${stack} source is missing ${token}`);
  }
}

function validateWxml(source: string): void {
  const stack: string[] = [];
  let cursor = 0;
  while (cursor < source.length) {
    const start = source.indexOf("<", cursor);
    if (start < 0) break;
    const end = source.indexOf(">", start + 1);
    if (end < 0) throw new Error("WXML tag is unterminated");
    const raw = source.slice(start + 1, end).trim();
    if (!raw.startsWith("!") && !raw.startsWith("?")) {
      const closing = raw.startsWith("/");
      const selfClosing = raw.endsWith("/");
      const name = raw.replace(/^\//, "").split(/[\s/]/, 1)[0] ?? "";
      if (!/^[a-z][a-z0-9-]*$/.test(name)) throw new Error("WXML tag name is invalid");
      if (closing) {
        if (stack.pop() !== name) throw new Error("WXML tags are unbalanced");
      } else if (!selfClosing) stack.push(name);
    }
    cursor = end + 1;
  }
  if (stack.length) throw new Error("WXML tags are unbalanced");
}

function validateSourceShape(
  stack: FrtRouteStack,
  files: Readonly<Record<string, string>>,
  ir: PortableUiIr,
): void {
  const refs = ir.sourceRefs;
  if (stack === "Vue 2" || stack === "Vue 3") {
    const packageManifest = JSON.parse(sourceText(files, refs, "package.json")) as { dependencies?: Record<string, string> };
    if (packageManifest.dependencies?.vue !== ir.source.version) throw new Error(`${stack} package version does not match the route IR`);
    const parsed = parseVueSfc(sourceText(files, refs, ".vue"), { filename: "App.vue" });
    if (parsed.errors.length || !parsed.descriptor.template) throw new Error(`${stack} SFC is invalid`);
    if (stack === "Vue 2" && !parsed.descriptor.script) throw new Error("Vue 2 Options API script is required");
    if (stack === "Vue 3" && !parsed.descriptor.scriptSetup) throw new Error("Vue 3 script setup is required");
    return;
  }
  if (stack === "React") {
    const packageManifest = JSON.parse(sourceText(files, refs, "package.json")) as { dependencies?: Record<string, string> };
    if (packageManifest.dependencies?.react !== ir.source.version) throw new Error("React package version does not match the route IR");
    const source = sourceText(files, refs, ".tsx");
    const parsed = ts.createSourceFile("App.tsx", source, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TSX);
    const diagnostics = (parsed as ts.SourceFile & { readonly parseDiagnostics?: readonly unknown[] }).parseDiagnostics ?? [];
    if (diagnostics.length || !parsed.statements.some(statement => ts.isFunctionDeclaration(statement))) {
      throw new Error("React TSX source is invalid");
    }
    return;
  }
  if (stack === "WeChat Mini Program") {
    const project = JSON.parse(sourceText(files, refs, "project.config.json")) as { libVersion?: string };
    if (project.libVersion !== ir.source.version) throw new Error("Mini Program base-library version does not match the route IR");
    validateWxml(sourceText(files, refs, ".wxml"));
    const program = ts.createSourceFile("index.js", sourceText(files, refs, ".js"), ts.ScriptTarget.ESNext, true, ts.ScriptKind.JS);
    const hasPage = program.statements.some(statement => ts.isExpressionStatement(statement)
      && ts.isCallExpression(statement.expression)
      && ts.isIdentifier(statement.expression.expression)
      && statement.expression.expression.text === "Page");
    if (!hasPage) throw new Error("Mini Program Page registration is required");
    return;
  }
  if (stack === "ArkUI") {
    const profile = JSON.parse(sourceText(files, refs, "build-profile.json5")) as { apiVersion?: number };
    if (`6.0.0(${String(profile.apiVersion ?? "")})` !== ir.source.version) throw new Error("ArkUI API version does not match the route IR");
    requireTokens(balancedTokens(sourceText(files, refs, ".ets")), ["@Entry", "@Component", "struct", "@State", "build"], stack);
    return;
  }
  if (!sourceText(files, refs, "pubspec.yaml").includes("sdk: flutter")) throw new Error("Flutter SDK dependency is required");
  requireTokens(balancedTokens(sourceText(files, refs, ".dart")), ["class", "StatefulWidget", "State", "Widget", "build"], stack);
}

function json(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function xml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}

function dartString(value: string): string {
  return JSON.stringify(value.replaceAll("$", "\\$"));
}

function routeMetadata(ir: PortableUiIr, target: FrtRouteStack): string {
  return json({
    schemaVersion: "1.0",
    source: ir.source,
    sourceSnapshotDigest: ir.sourceSnapshotDigest,
    target: { stack: target },
    scope: "single-public-counter-route-v1",
    certification: "NOT_CERTIFIED",
  });
}

function emitReact(ir: PortableUiIr): Record<string, string> {
  return {
    "package.json": json({ name: "frt-react-route", private: true, version: "1.0.0", type: "module", scripts: { build: "tsc --noEmit" }, dependencies: { react: "19.2.7", "react-dom": "19.2.7" }, devDependencies: { typescript: "5.9.2", "@types/react": "19.1.10", "@types/react-dom": "19.1.7" } }),
    "tsconfig.json": json({ compilerOptions: { target: "ES2022", module: "ESNext", moduleResolution: "Bundler", jsx: "react-jsx", strict: true, noEmit: true, lib: ["ES2022", "DOM"] }, include: ["src"] }),
    "src/App.tsx": [
      'import { useState } from "react";',
      'import "./App.css";',
      `const title = ${JSON.stringify(ir.view.title)};`,
      `const buttonLabel = ${JSON.stringify(ir.view.buttonLabel)};`,
      "export default function App() {",
      `  const [count, setCount] = useState(${ir.view.initialCount});`,
      `  return <main aria-label=${JSON.stringify(ir.accessibility.mainLabel)}><h1>{title}</h1>`,
      `    <button aria-label=${JSON.stringify(ir.accessibility.buttonLabel)} onClick={() => setCount(previous => previous + ${ir.view.incrementBy})}>{buttonLabel}</button>`,
      '    <p aria-live="polite">{count}</p></main>;',
      "}",
      "",
    ].join("\n"),
    "src/App.css": `button { color: ${ir.style.accentColor}; }\n`,
  };
}

function emitVue3(ir: PortableUiIr): Record<string, string> {
  return {
    "package.json": json({ name: "frt-vue3-route", private: true, version: "1.0.0", type: "module", dependencies: { vue: "3.5.39" } }),
    "src/App.vue": [
      '<script setup lang="ts">',
      'import { ref } from "vue";',
      `const title = ${JSON.stringify(ir.view.title)};`,
      `const buttonLabel = ${JSON.stringify(ir.view.buttonLabel)};`,
      `const count = ref(${ir.view.initialCount});`,
      `function increment() { count.value += ${ir.view.incrementBy}; }`,
      "</script>",
      `<template><main aria-label=${JSON.stringify(ir.accessibility.mainLabel)}><h1>{{ title }}</h1>`,
      `  <button aria-label=${JSON.stringify(ir.accessibility.buttonLabel)} @click="increment">{{ buttonLabel }}</button>`,
      '  <p aria-live="polite">{{ count }}</p></main></template>',
      `<style scoped>button { color: ${ir.style.accentColor}; }</style>`,
      "",
    ].join("\n"),
  };
}

function emitVue2(ir: PortableUiIr): Record<string, string> {
  return {
    "package.json": json({ name: "frt-vue2-route", private: true, version: "1.0.0", type: "module", dependencies: { vue: "2.7.16" } }),
    "src/App.vue": [
      "<script>",
      "export default {",
      `  data: () => ({ title: ${JSON.stringify(ir.view.title)}, buttonLabel: ${JSON.stringify(ir.view.buttonLabel)}, count: ${ir.view.initialCount} }),`,
      `  methods: { increment() { this.count += ${ir.view.incrementBy}; } },`,
      "};",
      "</script>",
      `<template><main aria-label=${JSON.stringify(ir.accessibility.mainLabel)}><h1>{{ title }}</h1>`,
      `  <button aria-label=${JSON.stringify(ir.accessibility.buttonLabel)} @click="increment">{{ buttonLabel }}</button>`,
      '  <p aria-live="polite">{{ count }}</p></main></template>',
      `<style scoped>button { color: ${ir.style.accentColor}; }</style>`,
      "",
    ].join("\n"),
  };
}

function emitMiniProgram(ir: PortableUiIr): Record<string, string> {
  return {
    "app.json": json({ pages: ["pages/index/index"], window: { navigationBarTitleText: ir.view.title } }),
    "project.config.json": json({ appid: "touristappid", projectname: "frt-mini-program-route", compileType: "miniprogram", libVersion: "3.10.3" }),
    "pages/index/index.json": json({ navigationBarTitleText: ir.view.title }),
    "pages/index/index.wxml": [
      `<view role="main" aria-label="${xml(ir.accessibility.mainLabel)}">`,
      `  <text>${xml(ir.view.title)}</text>`,
      `  <button aria-label="${xml(ir.accessibility.buttonLabel)}" bindtap="increment">{{buttonLabel}}</button>`,
      '  <text aria-live="polite">{{count}}</text>',
      "</view>",
      "",
    ].join("\n"),
    "pages/index/index.wxss": `button { color: ${ir.style.accentColor}; }\n`,
    "pages/index/index.js": [
      "Page({",
      `  data: { count: ${ir.view.initialCount}, buttonLabel: ${JSON.stringify(ir.view.buttonLabel)} },`,
      `  increment() { this.setData({ count: this.data.count + ${ir.view.incrementBy} }); },`,
      "});",
      "",
    ].join("\n"),
  };
}

function emitArkUi(ir: PortableUiIr): Record<string, string> {
  return {
    "build-profile.json5": json({ apiVersion: 20, app: { products: [{ name: "default" }] }, modules: [{ name: "entry", srcPath: "./entry", targets: [{ name: "default" }] }] }),
    "hvigor-config.json5": json({ modelVersion: "5.0.5", dependencies: {} }),
    "oh-package.json5": json({
      modelVersion: "5.0.5",
      name: "frt_arkui_route",
      version: "1.0.0",
      description: "Content-addressed FRT counter route",
      dependencies: {},
      devDependencies: { "@ohos/hvigor-ohos-plugin": "5.0.5" },
    }),
    "hvigorfile.ts": [
      "import { appTasks } from '@ohos/hvigor-ohos-plugin';",
      "export default { system: appTasks, plugins: [] };",
      "",
    ].join("\n"),
    "AppScope/app.json5": json({ app: { bundleName: "io.elmos.frtroute", vendor: "elmos", versionCode: 1000000, versionName: "1.0.0" } }),
    "entry/oh-package.json5": json({ name: "entry", version: "1.0.0", description: "FRT route entry", main: "", author: "", license: "", dependencies: {} }),
    "entry/hvigorfile.ts": [
      "import { hapTasks } from '@ohos/hvigor-ohos-plugin';",
      "export default { system: hapTasks, plugins: [] };",
      "",
    ].join("\n"),
    "entry/src/main/module.json5": json({ module: { name: "entry", type: "entry", srcEntry: "./ets/pages/Index.ets", deviceTypes: ["phone", "tablet"], pages: "$profile:main_pages" } }),
    "entry/src/main/resources/base/profile/main_pages.json": json({ src: ["pages/Index"] }),
    "entry/src/main/ets/pages/Index.ets": [
      "@Entry",
      "@Component",
      "struct Index {",
      `  @State count: number = ${ir.view.initialCount};`,
      "  build() {",
      "    Column() {",
      `      Text(${JSON.stringify(ir.view.title)}).accessibilityText(${JSON.stringify(ir.accessibility.mainLabel)})`,
      `      Button(${JSON.stringify(ir.view.buttonLabel)}).accessibilityText(${JSON.stringify(ir.accessibility.buttonLabel)}).onClick(() => { this.count += ${ir.view.incrementBy}; })`,
      "      Text(this.count.toString()).accessibilityLevel('yes')",
      `    }.fontColor('${ir.style.accentColor}')`,
      "  }",
      "}",
      "",
    ].join("\n"),
  };
}

function emitFlutter(ir: PortableUiIr): Record<string, string> {
  return {
    ".fvmrc": json({ flutter: "3.44.1" }),
    "pubspec.yaml": [
      "name: frt_flutter_route",
      "description: Content-addressed FRT counter route",
      "publish_to: none",
      "version: 1.0.0+1",
      "environment:",
      "  sdk: '>=3.12.0 <4.0.0'",
      "dependencies:",
      "  flutter:",
      "    sdk: flutter",
      "dev_dependencies:",
      "  flutter_test:",
      "    sdk: flutter",
      "",
    ].join("\n"),
    "analysis_options.yaml": "analyzer:\n  language:\n    strict-casts: true\n    strict-inference: true\n  errors:\n    avoid_print: error\n",
    "lib/main.dart": [
      "import 'package:flutter/material.dart';",
      "void main() => runApp(const CounterApp());",
      "class CounterApp extends StatelessWidget {",
      "  const CounterApp({super.key});",
      "  @override Widget build(BuildContext context) => const MaterialApp(home: CounterPage());",
      "}",
      "class CounterPage extends StatefulWidget {",
      "  const CounterPage({super.key});",
      "  @override State<CounterPage> createState() => _CounterPageState();",
      "}",
      "class _CounterPageState extends State<CounterPage> {",
      `  int count = ${ir.view.initialCount};`,
      `  void increment() => setState(() => count += ${ir.view.incrementBy});`,
      "  @override Widget build(BuildContext context) => Scaffold(body: SafeArea(child: Semantics(",
      `    label: ${dartString(ir.accessibility.mainLabel)}, container: true, child: Column(children: [`,
      `      Text(${dartString(ir.view.title)}),`,
      `      Semantics(button: true, label: ${dartString(ir.accessibility.buttonLabel)}, child: ExcludeSemantics(child: ElevatedButton(`,
      `        style: ElevatedButton.styleFrom(foregroundColor: const Color(0xFF${ir.style.accentColor.slice(1).toUpperCase()})),`,
      `        onPressed: increment, child: Text(${dartString(ir.view.buttonLabel)}),`,
      "      ))),",
      "      Semantics(liveRegion: true, child: Text('$count', key: const Key('count'))),",
      "    ]),",
      "  )));",
      "}",
      "",
    ].join("\n"),
    "test/widget_test.dart": [
      "import 'package:flutter/material.dart';",
      "import 'package:flutter_test/flutter_test.dart';",
      "import 'package:frt_flutter_route/main.dart';",
      "void main() {",
      "  testWidgets('counter route preserves the interaction contract', (tester) async {",
      "    final semantics = tester.ensureSemantics();",
      "    await tester.pumpWidget(const CounterApp());",
      "    expect(find.byType(SafeArea), findsOneWidget);",
      `    expect(find.byWidgetPredicate((widget) => widget is Semantics && widget.properties.label == ${dartString(ir.accessibility.mainLabel)}), findsOneWidget);`,
      `    expect(find.byWidgetPredicate((widget) => widget is Semantics && widget.properties.label == ${dartString(ir.accessibility.buttonLabel)}), findsOneWidget);`,
      `    expect(find.text(${dartString(String(ir.view.initialCount))}), findsOneWidget);`,
      `    await tester.tap(find.text(${dartString(ir.view.buttonLabel)}));`,
      "    await tester.pump();",
      `    expect(find.text(${dartString(String(ir.view.initialCount + ir.view.incrementBy))}), findsOneWidget);`,
      "    semantics.dispose();",
      "  });",
      "}",
      "",
    ].join("\n"),
  };
}

function emitTarget(ir: PortableUiIr, target: FrtRouteStack): Record<string, string> {
  const files = target === "React" ? emitReact(ir)
    : target === "Vue 3" ? emitVue3(ir)
      : target === "Vue 2" ? emitVue2(ir)
        : target === "WeChat Mini Program" ? emitMiniProgram(ir)
          : target === "ArkUI" ? emitArkUi(ir)
            : emitFlutter(ir);
  return {
    ...attachRunnableTarget(files, ir, target),
    "frt-route.json": routeMetadata(ir, target),
  };
}

function validateGeneratedTarget(target: FrtRouteStack, files: Readonly<Record<string, string>>): void {
  if (target === "React") {
    const parsed = ts.createSourceFile("App.tsx", files["src/App.tsx"] ?? "", ts.ScriptTarget.ESNext, true, ts.ScriptKind.TSX);
    const diagnostics = (parsed as ts.SourceFile & { readonly parseDiagnostics?: readonly unknown[] }).parseDiagnostics ?? [];
    if (diagnostics.length) throw new Error("generated React target is syntactically invalid");
  } else if (target === "Vue 2" || target === "Vue 3") {
    const parsed = parseVueSfc(files["src/App.vue"] ?? "", { filename: "App.vue" });
    if (parsed.errors.length || !parsed.descriptor.template) throw new Error(`generated ${target} target is invalid`);
    if (target === "Vue 3") {
      const compiled = compileTemplate({
        source: parsed.descriptor.template.content,
        filename: "App.vue",
        id: "frt-directional-route",
      });
      if (compiled.errors.length) throw new Error(`generated Vue 3 template compiler errors: ${compiled.errors.join("; ")}`);
    }
  } else if (target === "WeChat Mini Program") {
    validateWxml(files["pages/index/index.wxml"] ?? "");
    JSON.parse(files["app.json"] ?? "");
    JSON.parse(files["project.config.json"] ?? "");
    balancedTokens(files["pages/index/index.js"] ?? "");
  } else if (target === "ArkUI") {
    requireTokens(balancedTokens(files["entry/src/main/ets/pages/Index.ets"] ?? ""), ["@Entry", "@Component", "struct", "@State", "build"], target);
  } else {
    requireTokens(balancedTokens(files["lib/main.dart"] ?? ""), ["class", "StatefulWidget", "State", "Widget", "build"], target);
  }
  JSON.parse(files["frt-route.json"] ?? "");
}

/**
 * Dispatch to the extractor for a source stack that has one.
 *
 * Registered here rather than inline so that adding a stack to
 * `frtSourceDerivedStacks` without writing its extractor fails to compile.
 */
function deriveSourceIr(
  source: FrtRouteStack,
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  if (source === "Vue 3") return deriveVue3PortableUiIr(files, gaps);
  if (source === "React") return deriveReactPortableUiIr(files, gaps);
  if (source === "Vue 2") return deriveVue2PortableUiIr(files, gaps);
  if (source === "WeChat Mini Program") return deriveMiniProgramPortableUiIr(files, gaps);
  if (source === "ArkUI") return deriveArkUiPortableUiIr(files, gaps);
  return deriveFlutterPortableUiIr(files, gaps);
}

function sourcePathOf(ir: PortableUiIr): string {
  return ir.sourceRefs.find(item => /\.(?:vue|tsx|wxml|ets|dart)$/.test(item.path))?.path ?? "<source>";
}

export function convertDirectionalRoute(
  source: FrtRouteStack,
  target: FrtRouteStack,
  files: Readonly<Record<string, string>>,
): DirectionalRouteResult {
  const gaps: FrtRouteTypedGap[] = [];
  if (!frtRouteStackSet.has(source) || !frtRouteStackSet.has(target) || source === target) {
    gap(gaps, "FRT_ROUTE_DIRECTION_INVALID", "<route>", "A known non-self source and target route is required.");
  }
  let ir: PortableUiIr | undefined;
  let irProvenance: FrtIrProvenance = "NONE";
  const extractable = frtSourceDerivedStacks.has(source);

  if (files["frt-ui-ir.json"] === undefined) {
    // Nothing declared: the IR has to come out of the source bytes, or not at all.
    if (extractable) {
      const derived = deriveSourceIr(source, files, gaps);
      if (derived && !gaps.some(item => item.blocking)) {
        ir = derived;
        irProvenance = "SOURCE_DERIVED";
      }
    } else {
      gap(gaps, "FRT_TYPED_UI_IR_OR_SOURCE_INVALID", "frt-ui-ir.json",
        `No ${source} source extractor exists yet, so this route still requires a declared `
        + "frt-ui-ir.json; it is not derived from source.");
    }
  } else {
    let declared: PortableUiIr | undefined;
    try {
      declared = parsePortableUiIr(files, source);
      validateSourceShape(source, files, declared);
    } catch (error) {
      gap(gaps, "FRT_TYPED_UI_IR_OR_SOURCE_INVALID", "frt-ui-ir.json",
        error instanceof Error ? error.message : "Typed route input is invalid.");
    }
    if (declared) {
      if (extractable) {
        // A declaration is only as good as the source behind it: derive the same
        // IR and make every disagreement explicit, field by field.
        const derived = deriveSourceIr(source, files, gaps);
        if (derived) assertDeclaredIrMatchesSource(declared, derived, sourcePathOf(derived), gaps);
        if (!gaps.some(item => item.blocking)) {
          ir = declared;
          irProvenance = "DECLARED_CROSS_CHECKED";
        }
      } else if (!gaps.some(item => item.blocking)) {
        ir = declared;
        irProvenance = "DECLARED";
      }
    }
  }
  let generatedFiles: Readonly<Record<string, string>> = {};
  if (ir && !gaps.some(item => item.blocking)) {
    try {
      generatedFiles = emitTarget(ir, target);
      validateGeneratedTarget(target, generatedFiles);
    } catch (error) {
      gap(gaps, "FRT_TARGET_EMISSION_INVALID", "<generated-target>", error instanceof Error ? error.message : "Target emission is invalid.");
      generatedFiles = {};
    }
  }
  const blocked = gaps.some(item => item.blocking);
  return {
    route: `${source} -> ${target}`,
    source,
    target,
    status: blocked ? "BLOCKED" : "GENERATED",
    sourceFiles: ir?.sourceRefs.map(item => item.path) ?? [],
    ...(ir ? { sourceSnapshotDigest: ir.sourceSnapshotDigest } : {}),
    generatedFiles,
    mappings: blocked ? [] : [
      `${source} syntax shape + content-addressed source references -> typed UI Interaction IR`,
      `typed root route -> ${target} navigation root`,
      `typed counter state/action -> ${target} native state update`,
      `typed accessibility contract -> ${target} semantic attributes`,
      `typed design token -> ${target} native styling`,
    ],
    typedGaps: gaps,
    irProvenance: blocked ? "NONE" : irProvenance,
    sourceValidation: blocked ? "BLOCKED" : "PASSED",
    targetValidation: blocked ? "BLOCKED" : "PASSED",
    sourceBuild: "NOT_RUN",
    targetBuild: "NOT_RUN",
    browserJourney: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
}

function arkSourceFixture(): string {
  return [
    "@Entry",
    "@Component",
    "struct Index {",
    "  @State count: number = 0;",
    "  build() {",
    "    Column() {",
    '      Text("Counter").accessibilityText("Counter application")',
    '      Button("Increment").accessibilityText("Increment counter").onClick(() => { this.count += 1; })',
    "      Text(this.count.toString()).accessibilityLevel('yes')",
    "    }.fontColor('#0057B8')",
    "  }",
    "}",
    "",
  ].join("\n");
}

function flutterSourceFixture(): string {
  return [
    "import 'package:flutter/material.dart';",
    "void main() => runApp(const CounterApp());",
    "class CounterApp extends StatelessWidget {",
    "  const CounterApp({super.key});",
    "  @override Widget build(BuildContext context) => const MaterialApp(home: CounterPage());",
    "}",
    "class CounterPage extends StatefulWidget {",
    "  const CounterPage({super.key});",
    "  @override State<CounterPage> createState() => _CounterPageState();",
    "}",
    "class _CounterPageState extends State<CounterPage> {",
    "  int count = 0;",
    "  void increment() => setState(() => count += 1);",
    "  @override Widget build(BuildContext context) => Scaffold(body: SafeArea(child: Semantics(",
    '    label: "Counter application", container: true, child: Column(children: [',
    '      Text("Counter"),',
    '      Semantics(button: true, label: "Increment counter", child: ExcludeSemantics(child: ElevatedButton(',
    "        style: ElevatedButton.styleFrom(foregroundColor: const Color(0xFF0057B8)),",
    '        onPressed: increment, child: Text("Increment"),',
    "      ))),",
    "      Semantics(liveRegion: true, child: Text('$count', key: const Key('count'))),",
    "    ]),",
    "  )));",
    "}",
    "",
  ].join("\n");
}

export function createDirectionalRouteFixture(stack: FrtRouteStack): Readonly<Record<string, string>> {
  const native = stack === "Vue 2" ? {
    "package.json": json({ dependencies: { vue: "2.7.16" } }),
    "src/App.vue": '<template><main aria-label="Counter application"><h1>{{ title }}</h1><button aria-label="Increment counter" @click="increment">{{ buttonLabel }}</button><p aria-live="polite">{{ count }}</p></main></template><script>export default { data: () => ({ title: "Counter", buttonLabel: "Increment", count: 0 }), methods: { increment() { this.count += 1; } } };</script><style scoped>button { color: #0057B8; }</style>\n',
  } : stack === "Vue 3" ? {
    "package.json": json({ dependencies: { vue: "3.5.39" } }),
    "src/App.vue": '<template><main aria-label="Counter application"><h1>{{ title }}</h1><button aria-label="Increment counter" @click="increment">Increment</button><p aria-live="polite">{{ count }}</p></main></template><script setup lang="ts">import { ref } from "vue"; const title = "Counter"; const count = ref(0); function increment() { count.value += 1; }</script><style scoped>button { color: #0057B8; }</style>\n',
  } : stack === "React" ? {
    "package.json": json({ dependencies: { react: "19.2.7" } }),
    "src/App.tsx": 'import { useState } from "react";\nimport "./App.css";\nexport function App() {\n  const [count, setCount] = useState(0);\n  return <main aria-label="Counter application"><h1>Counter</h1><button aria-label="Increment counter" onClick={() => setCount(value => value + 1)}>Increment</button><p aria-live="polite">{count}</p></main>;\n}\n',
    "src/App.css": "button { color: #0057B8; }",
  } : stack === "WeChat Mini Program" ? {
    "project.config.json": json({ appid: "touristappid", projectname: "frt-source", compileType: "miniprogram", libVersion: "3.10.3" }),
    "pages/index/index.wxml": '<view role="main" aria-label="Counter application"><text>Counter</text><button aria-label="Increment counter" bindtap="increment">{{buttonLabel}}</button><text aria-live="polite">{{count}}</text></view>\n',
    "pages/index/index.js": 'Page({ data: { count: 0, buttonLabel: "Increment" }, increment() { this.setData({ count: this.data.count + 1 }); } });\n',
    "pages/index/index.wxss": "button { color: #0057B8; }\n",
  } : stack === "ArkUI" ? {
    "build-profile.json5": json({ apiVersion: 20 }),
    "entry/src/main/ets/pages/Index.ets": arkSourceFixture(),
  } : {
    ".fvmrc": json({ flutter: "3.44.1" }),
    "pubspec.yaml": "name: frt_source\nenvironment:\n  sdk: '>=3.12.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n",
    "lib/main.dart": flutterSourceFixture(),
  };
  const sourceRefs = Object.entries(native).map(([path, content]) => ({ path, sha256: sha256(content) }))
    .sort((left, right) => left.path.localeCompare(right.path));
  const versions: Record<FrtRouteStack, string> = {
    "Vue 2": "2.7.16",
    "Vue 3": "3.5.39",
    React: "19.2.7",
    "WeChat Mini Program": "3.10.3",
    ArkUI: "6.0.0(20)",
    Flutter: "3.44.1",
  };
  return {
    ...native,
    "frt-ui-ir.json": json({
      schemaVersion: "1.0",
      source: { stack, version: versions[stack] },
      sourceSnapshotDigest: sha256(canonical(sourceRefs)),
      sourceRefs,
      route: { path: "/", requiresAuth: false, deepLink: true },
      view: { title: "Counter", initialCount: 0, incrementBy: 1, buttonLabel: "Increment" },
      style: { accentColor: "#0057B8" },
      accessibility: { mainLabel: "Counter application", buttonLabel: "Increment counter", liveRegion: "polite" },
      capabilities: { permissions: [], native: [], network: [] },
    }),
  };
}

/**
 * Real cross-framework EXECUTION comparison.
 *
 * Syntax validation only proves a compiler accepted the emitted source. It
 * does not prove the translation preserved behavior -- and the two defects
 * this engine has already found (Vue's `count.value = ...` inside a
 * template, and the WeChat mini program's synchronous `setData` breaking
 * React's closure semantics) both compiled perfectly cleanly.
 *
 * This module closes that gap for the frameworks whose real server
 * renderer is a plain npm package: the source component and the translated
 * component are both actually RENDERED with the same prop values, and
 * their normalized DOM output is compared. A mismatch is reported as
 * FAILED -- never rounded up to a pass.
 *
 * Frameworks needing an external runtime (Angular's platform-server
 * bootstrap, React Native's Metro/simulator, WeChat devtools, HarmonyOS
 * DevEco, the Flutter/Dart SDK) are honestly reported as
 * EXECUTION_NOT_AVAILABLE by `validator.ts` rather than silently skipped.
 */
import { execFileSync } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as ts from "typescript";
import { ComponentDef, DataPropDef, Framework, ListPropDef, Literal, PrimitiveType } from "./models";

export interface ExecutionCase {
  /** Prop values to render with. Keys must be declared props; list props
   * receive a real sample array so list rendering is actually exercised. */
  props: Record<string, unknown>;
}

export interface ExecutionOutcome {
  status: "PASSED" | "FAILED";
  diagnostics: string[];
}

/**
 * Normalizes rendered HTML so that framework-specific but semantically
 * irrelevant differences do not produce false mismatches:
 *  - React emits no marker comments; Vue emits `<!--[-->`/`<!--]-->`
 *    fragment anchors and `<!--v-if-->` placeholders; Svelte emits
 *    `<!--[-->`/`<!--]-->` too.
 *  - Attribute order and insignificant whitespace differ between renderers.
 *
 * Everything that actually affects what a user sees -- tag structure,
 * text content, and attribute *values* -- is preserved and compared.
 */
export function normalizeHtml(html: string): string {
  let out = html.replace(/<!--[\s\S]*?-->/g, "");
  // Framework hydration markers are bookkeeping for the client runtime,
  // not content: Vue 2's server renderer stamps `data-server-rendered` on
  // the root, and Svelte/Vue 3 use comment anchors (already stripped
  // above). None of them change what a user sees, so comparing them would
  // report a false divergence on every single render.
  out = out.replace(/\s+data-server-rendered="[^"]*"/g, "");
  out = out.replace(/\s+/g, " ");
  // Sort attributes within each tag so ordering differences are ignored.
  out = out.replace(/<([a-zA-Z][\w-]*)((?:\s+[^\s=>]+(?:="[^"]*")?)*)\s*(\/?)>/g, (_m, tag, attrs: string, selfClose) => {
    const parts = (attrs.match(/[^\s=]+(?:="[^"]*")?/g) ?? [])
      .map((a) => a.trim())
      .filter((a) => a.length > 0)
      .sort();
    return `<${tag}${parts.length ? " " + parts.join(" ") : ""}${selfClose}>`;
  });
  return out.replace(/>\s+</g, "><").trim();
}

function defaultFor(prop: DataPropDef): string | number | boolean {
  if (prop.defaultValue !== undefined) return literalValue(prop.defaultValue);
  return prop.propType === "string" ? "sample" : prop.propType === "number" ? 1 : true;
}

function primitiveSample(type: PrimitiveType, seed: number): string | number | boolean {
  if (type === "string") return `item-${seed}`;
  if (type === "number") return seed;
  return seed % 2 === 0;
}

/**
 * Builds real sample rows for a list prop.
 *
 * Without this the execution leg would render every list as empty and
 * "prove" that two frameworks agree on rendering nothing -- the emptiest
 * possible false pass. Rows are deterministic so a mismatch is
 * reproducible, and there are two of them so ordering differences show up.
 */
function listSample(prop: ListPropDef, count = 2): unknown[] {
  return Array.from({ length: count }, (_unused, index) => {
    const seed = index + 1;
    if (prop.element.kind === "primitive") return primitiveSample(prop.element.primitive, seed);
    const row: Record<string, string | number | boolean> = {};
    for (const [field, type] of Object.entries(prop.element.fields)) {
      row[field] = field === prop.keyField && type === "number" ? seed : primitiveSample(type, seed);
    }
    return row;
  });
}

function literalValue(literal: Literal): string | number | boolean {
  return literal.value;
}

/** Builds a deterministic set of prop values covering the component's
 * declared props, so callers need not hand-write cases for every test. */
export function defaultExecutionCases(component: ComponentDef): ExecutionCase[] {
  const base: Record<string, unknown> = {};
  for (const prop of component.props) {
    if (prop.kind === "data") base[prop.name] = defaultFor(prop);
    else if (prop.kind === "list") base[prop.name] = listSample(prop);
  }
  const variant: Record<string, unknown> = { ...base };
  for (const prop of component.props) {
    if (prop.kind === "list") {
      // A different row count catches emitters that hard-code an arity or
      // drop the loop entirely.
      variant[prop.name] = listSample(prop, 3);
      continue;
    }
    if (prop.kind !== "data") continue;
    if (prop.propType === "number") variant[prop.name] = 7;
    else if (prop.propType === "boolean") variant[prop.name] = !base[prop.name];
    else variant[prop.name] = "other";
  }
  return [{ props: base }, { props: variant }];
}

/**
 * Scratch directory for the transpiled modules that actually get
 * `require`d during a render.
 *
 * It deliberately lives under the working directory rather than in the OS
 * temp dir: Node resolves bare specifiers like `react` and `vue` by walking
 * *up* from the requiring file, so a module written to `/tmp` cannot see
 * this package's `node_modules` and every render fails with
 * "Cannot find module 'react'". Anchoring the scratch dir inside the
 * project keeps that resolution path intact. `ELMOS_CDE_SCRATCH` overrides
 * it for callers with a read-only working directory.
 */
/** ESM dynamic import needs a file:// URL, not a bare path. */
function pathToFileUrl(file: string): string {
  return new URL(`file://${path.resolve(file)}`).href;
}

function tempDir(): string {
  const base = process.env["ELMOS_CDE_SCRATCH"] ?? path.join(process.cwd(), ".cde-scratch");
  fs.mkdirSync(base, { recursive: true });
  return fs.mkdtempSync(path.join(base, "run-"));
}

function transpileTsx(source: string): string {
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.React,
      esModuleInterop: true,
    },
  }).outputText;
  // `jsx: "react"` compiles JSX to `React.createElement(...)`, so `React`
  // must be in scope. A stateful component only imports `useState` (the
  // idiomatic modern form) and needs the factory binding injected; a
  // stateless one already emits `import * as React from "react"`, which
  // transpiles to its own `React` const -- injecting a second one is a
  // duplicate-declaration SyntaxError. Only inject when it is absent.
  const alreadyBound = /\b(const|var|let)\s+React\b/.test(output);
  return alreadyBound ? output : `const React = require("react");\n${output}`;
}

async function renderReact(source: string, props: Record<string, unknown>): Promise<string> {
  const dir = tempDir();
  try {
    const js = transpileTsx(source);
    const file = path.join(dir, "Component.js");
    fs.writeFileSync(file, js, "utf8");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const React = require("react");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { renderToStaticMarkup } = require("react-dom/server");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require(file);
    const Component = mod.default ?? mod;
    return renderToStaticMarkup(React.createElement(Component, props));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

async function renderVue3(source: string, props: Record<string, unknown>): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const sfc = require("@vue/compiler-sfc");
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { createSSRApp } = require("vue");
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { renderToString } = require("@vue/server-renderer");

  const { descriptor } = sfc.parse(source, { filename: "Component.vue" });
  const id = "cde";
  const script = sfc.compileScript(descriptor, { id, inlineTemplate: true, templateOptions: { ssr: true } });
  const dir = tempDir();
  try {
    const js = ts.transpileModule(script.content, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    }).outputText;
    const file = path.join(dir, "Component.js");
    fs.writeFileSync(file, js, "utf8");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require(file);
    const Component = mod.default ?? mod;
    const app = createSSRApp(Component, props);
    return await renderToString(app);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Renders a Vue 2 SFC with the real `vue-server-renderer`.
 *
 * `vue-template-compiler` and `vue-server-renderer` both refuse to load
 * from their package entry point when vue@3 is installed alongside them (a
 * hard version-mismatch guard). `build.js` is the same published compiler
 * without that guard, and `vue2` is this package's aliased vue@2 install,
 * so the real Vue 2 runtime is used -- not a stand-in.
 */
async function renderVue2(source: string, props: Record<string, unknown>): Promise<string> {
  /* eslint-disable @typescript-eslint/no-var-requires */
  const compiler = require("vue-template-compiler/build");
  const Vue2 = require("vue2");
  const { createRenderer } = require("vue-server-renderer/build.prod");
  /* eslint-enable @typescript-eslint/no-var-requires */

  const descriptor = compiler.parseComponent(source);
  if (!descriptor.template || !descriptor.script) throw new Error("Vue 2 SFC needs both <template> and <script>");

  const compiled = compiler.compileToFunctions(descriptor.template.content);
  const dir = tempDir();
  try {
    const js = ts.transpileModule(descriptor.script.content, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    }).outputText;
    const file = path.join(dir, "Options.js");
    fs.writeFileSync(file, js, "utf8");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require(file);
    const options = mod.default ?? mod;

    const Component = Vue2.extend({
      ...options,
      render: compiled.render,
      staticRenderFns: compiled.staticRenderFns,
    });
    const app = new Component({ propsData: props });
    return await createRenderer().renderToString(app);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Renders a Svelte 5 component with the real `svelte/compiler` +
 * `svelte/server`. The compiler emits an ES module, so it is written to
 * disk and loaded with a dynamic `import()`; a cache-busting query keeps
 * repeated renders from reusing a stale module.
 */
/**
 * The Svelte SSR renderer, run in a short-lived Node subprocess.
 *
 * Both halves of this are ESM-only: `svelte/server` publishes no CommonJS
 * condition, and the compiler's server output is itself an ES module. Node
 * 22 can `require()` an ES module, so an in-process `require` appears to
 * work -- and then breaks inside a CommonJS test runner, whose VM sandbox
 * also refuses dynamic `import()` without `--experimental-vm-modules`.
 * Rather than push that constraint onto every caller, the render happens
 * under native ESM in its own process. It is the real Svelte renderer, not
 * a stand-in -- exactly the arrangement `parsers/angular.ts` uses for
 * `@angular/compiler`.
 */
const SVELTE_RENDER_SCRIPT = `
import { render } from "svelte/server";
const [, , modulePath, propsJson] = process.argv;
const mod = await import(modulePath);
const result = render(mod.default, { props: JSON.parse(propsJson) });
process.stdout.write(String(result.body ?? result.html ?? ""));
`;

async function renderSvelte(source: string, props: Record<string, unknown>): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const compiler = require("svelte/compiler");
  const compiled = compiler.compile(source, { generate: "server", filename: "Component.svelte" });
  const dir = tempDir();
  try {
    const componentFile = path.join(dir, "Component.server.mjs");
    fs.writeFileSync(componentFile, compiled.js.code, "utf8");
    const runnerFile = path.join(dir, "render.mjs");
    fs.writeFileSync(runnerFile, SVELTE_RENDER_SCRIPT, "utf8");
    return execFileSync(
      process.execPath,
      [runnerFile, pathToFileUrl(componentFile), JSON.stringify(props)],
      { encoding: "utf8", cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"], timeout: 60_000 },
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

export type Renderable = { framework: Framework; source: string };

async function render(target: Renderable, props: Record<string, unknown>): Promise<string> {
  if (target.framework === "react" || target.framework === "typescript") return renderReact(target.source, props);
  if (target.framework === "vue3") return renderVue3(target.source, props);
  if (target.framework === "vue2") return renderVue2(target.source, props);
  if (target.framework === "svelte") return renderSvelte(target.source, props);
  throw new Error(`EXECUTION_NOT_AVAILABLE for framework ${target.framework}`);
}

/**
 * Renders both components against every case and compares normalized
 * output. Any difference -- or any render throwing -- is a FAILED result
 * carrying the actual diverging markup, not a soft warning.
 */
export async function compareRendered(
  source: Renderable,
  target: Renderable,
  cases: ExecutionCase[],
): Promise<ExecutionOutcome> {
  const diagnostics: string[] = [];
  for (const [index, testCase] of cases.entries()) {
    let sourceHtml: string;
    let targetHtml: string;
    try {
      sourceHtml = normalizeHtml(await render(source, testCase.props));
    } catch (error) {
      diagnostics.push(`case ${index}: ${source.framework} render threw: ${(error as Error).message}`);
      continue;
    }
    try {
      targetHtml = normalizeHtml(await render(target, testCase.props));
    } catch (error) {
      diagnostics.push(`case ${index}: ${target.framework} render threw: ${(error as Error).message}`);
      continue;
    }
    if (sourceHtml !== targetHtml) {
      diagnostics.push(
        `case ${index} props=${JSON.stringify(testCase.props)}: rendered output differs\n` +
        `  ${source.framework}: ${sourceHtml}\n` +
        `  ${target.framework}: ${targetHtml}`,
      );
    }
  }
  return { status: diagnostics.length === 0 ? "PASSED" : "FAILED", diagnostics };
}

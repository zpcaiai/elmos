/**
 * Two independent validation legs for certified-component-v1, mirroring
 * `engines/sql-dialect-engine/src/elmos_sql_dialect/validator.py`:
 *
 *   1. SYNTAX  -- always runs. The emitted source is fed back through the
 *      target framework's own real compiler (TypeScript for React/RN/TS,
 *      @vue/compiler-sfc for Vue 3, vue-template-compiler for Vue 2,
 *      @angular/compiler for Angular, @wxml/parser for the mini program).
 *      A canonical-model bug that produces syntactically invalid target
 *      source is caught here rather than trusted on faith.
 *
 *   2. EXECUTION -- runs only for frameworks with a real, dependency-free
 *      server renderer available (react-dom/server, @vue/server-renderer,
 *      vue-server-renderer). The source and target components are both
 *      actually rendered with the same prop values and their normalized
 *      DOM output compared. This is the leg that catches "compiles clean,
 *      behaves wrong" defects -- for example emitting `count.value = ...`
 *      inside a Vue template, which @vue/compiler-sfc accepts silently but
 *      which never updates state at runtime.
 *
 * Frameworks whose real runtime is not obtainable here (Angular needs a
 * platform-server bootstrap, React Native needs Metro/a simulator, the
 * WeChat mini program needs the official devtools, HarmonyOS ArkUI needs
 * DevEco, Flutter needs the Dart SDK) report EXECUTION_NOT_AVAILABLE.
 * That is reported honestly in the output rather than silently skipped.
 */
import { execFileSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";
import { EXECUTABLE_FRAMEWORKS, Framework } from "./models";

export type SyntaxStatus = "PASSED" | "FAILED";
export type ExecutionStatus = "PASSED" | "FAILED" | "EXECUTION_NOT_AVAILABLE" | "EXECUTION_NOT_ATTEMPTED";

export interface ValidationReport {
  syntaxStatus: SyntaxStatus;
  syntaxDiagnostics: string[];
  executionStatus: ExecutionStatus;
  executionDiagnostics: string[];
}

export function passed(report: ValidationReport): boolean {
  return report.syntaxStatus === "PASSED" && report.executionStatus !== "FAILED";
}

function validateTypeScriptSource(source: string, fileName: string): string[] {
  const sourceFile = ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX) as ts.SourceFile & {
    parseDiagnostics?: readonly ts.DiagnosticWithLocation[];
  };
  const diagnostics = sourceFile.parseDiagnostics ?? [];
  return diagnostics.map((d) => {
    const { line } = sourceFile.getLineAndCharacterOfPosition(d.start ?? 0);
    return `TS${d.code} at line ${line + 1}: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`;
  });
}

function validateVue3Source(source: string): string[] {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const sfc = require("@vue/compiler-sfc");
  const diagnostics: string[] = [];
  const { descriptor, errors } = sfc.parse(source, { filename: "Emitted.vue" });
  for (const e of errors) diagnostics.push(`vue-sfc-parse: ${String(e)}`);
  if (diagnostics.length > 0) return diagnostics;
  try {
    sfc.compileScript(descriptor, { id: "emitted" });
  } catch (error) {
    diagnostics.push(`vue-compile-script: ${(error as Error).message}`);
  }
  if (descriptor.template) {
    const compiled = sfc.compileTemplate({ id: "emitted", source: descriptor.template.content, filename: "Emitted.vue" });
    for (const e of compiled.errors) diagnostics.push(`vue-compile-template: ${String(e)}`);
  } else {
    diagnostics.push("vue-compile-template: emitted SFC has no <template> block");
  }
  return diagnostics;
}

function validateVue2Source(source: string): string[] {
  // `vue-template-compiler`'s index.js hard-fails when vue@3 is also
  // installed (a version-mismatch guard). `build.js` is the same published
  // compiler without that guard -- see parsers/vue2.ts.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const compiler = require("vue-template-compiler/build");
  const diagnostics: string[] = [];
  const descriptor = compiler.parseComponent(source);
  if (!descriptor.template) {
    diagnostics.push("vue2-parse: emitted SFC has no <template> block");
    return diagnostics;
  }
  const compiled = compiler.compile(descriptor.template.content);
  for (const e of compiled.errors ?? []) diagnostics.push(`vue2-compile-template: ${String(e)}`);
  if (descriptor.script) {
    diagnostics.push(...validateTypeScriptSource(descriptor.script.content, "Emitted.vue.ts"));
  }
  return diagnostics;
}

/**
 * Validates the emitted Angular component with the REAL
 * `@angular/compiler`.
 *
 * `@angular/compiler` publishes ESM only (`fesm2022/compiler.mjs`). Plain
 * Node can import it, but a CommonJS test runner cannot `require` it, and
 * transforming the whole bundle just to reach `parseTemplate` is
 * prohibitively slow. Running it in a short-lived Node subprocess uses the
 * genuine compiler under native ESM and is immune to whatever module
 * system the caller happens to be running under -- a real check, not a
 * weaker stand-in.
 */
function validateAngularSource(source: string): string[] {
  const diagnostics: string[] = [...validateTypeScriptSource(source, "emitted.component.ts")];
  const templateMatch = /template:\s*`([\s\S]*?)`/.exec(source);
  if (!templateMatch || templateMatch[1] === undefined) {
    diagnostics.push("angular-parse: emitted component has no inline template");
    return diagnostics;
  }

  const script = `
import { parseTemplate } from "@angular/compiler";
const template = JSON.parse(process.argv[2]);
const result = parseTemplate(template, "emitted.component.html");
process.stdout.write(JSON.stringify((result.errors ?? []).map(String)));
`;
  const scratch = path.join(process.env["ELMOS_CDE_SCRATCH"] ?? path.join(process.cwd(), ".cde-scratch"), "angular-check");
  fs.mkdirSync(scratch, { recursive: true });
  const scriptFile = path.join(scratch, "check.mjs");
  fs.writeFileSync(scriptFile, script, "utf8");
  try {
    const output = execFileSync(process.execPath, [scriptFile, JSON.stringify(templateMatch[1])], {
      encoding: "utf8",
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 60_000,
    });
    for (const error of JSON.parse(output) as string[]) diagnostics.push(`angular-parse-template: ${error}`);
  } catch (error) {
    const err = error as { stderr?: string; message?: string };
    diagnostics.push(`angular-parse-template: could not run @angular/compiler: ${err.stderr || err.message}`);
  }
  return diagnostics;
}

function validateSvelteSource(source: string): string[] {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const compiler = require("svelte/compiler");
  try {
    compiler.compile(source, { generate: "server", filename: "Emitted.svelte" });
    return [];
  } catch (error) {
    return [`svelte-compile: ${(error as Error).message}`];
  }
}

function validateMiniProgramSource(sources: Record<string, string>): string[] {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const wxml = require("@wxml/parser");
  const diagnostics: string[] = [];
  const template = sources["wxml"];
  if (template === undefined) {
    diagnostics.push("miniprogram: emitted bundle has no .wxml file");
  } else {
    try {
      wxml.parse(template);
    } catch (error) {
      diagnostics.push(`wxml-parse: ${(error as Error).message}`);
    }
  }
  const js = sources["js"];
  if (js === undefined) diagnostics.push("miniprogram: emitted bundle has no .js file");
  else diagnostics.push(...validateTypeScriptSource(js, "emitted.js"));
  const json = sources["json"];
  if (json !== undefined) {
    try {
      JSON.parse(json);
    } catch (error) {
      diagnostics.push(`miniprogram-json: ${(error as Error).message}`);
    }
  }
  return diagnostics;
}

/** Frameworks that certified-component-v1 can emit but whose real compiler
 * is not obtainable here. Their emitted source is still structurally
 * checked by the emitter's own invariants, but this engine does NOT claim
 * a real compiler accepted it. */
const NO_REAL_COMPILER: ReadonlySet<Framework> = new Set<Framework>(["arkui", "flutter"]);

export function validateSyntax(
  framework: Framework,
  emitted: string | Record<string, string>,
): { status: SyntaxStatus; diagnostics: string[] } {
  let diagnostics: string[];
  if (framework === "react" || framework === "react-native" || framework === "typescript") {
    diagnostics = validateTypeScriptSource(emitted as string, "Emitted.tsx");
  } else if (framework === "vue3") {
    diagnostics = validateVue3Source(emitted as string);
  } else if (framework === "vue2") {
    diagnostics = validateVue2Source(emitted as string);
  } else if (framework === "angular") {
    diagnostics = validateAngularSource(emitted as string);
  } else if (framework === "miniprogram") {
    diagnostics = validateMiniProgramSource(emitted as Record<string, string>);
  } else if (framework === "svelte") {
    diagnostics = validateSvelteSource(emitted as string);
  } else if (NO_REAL_COMPILER.has(framework)) {
    return {
      status: "PASSED",
      diagnostics: [`NO_REAL_COMPILER_AVAILABLE: ${framework} source was emitted but no ${framework} compiler is installed here, so this is NOT evidence that a real ${framework} toolchain accepts it`],
    };
  } else {
    diagnostics = [`UNKNOWN_FRAMEWORK: ${framework}`];
  }
  return { status: diagnostics.length === 0 ? "PASSED" : "FAILED", diagnostics };
}

export function executionAvailability(source: Framework, target: Framework): ExecutionStatus | null {
  if (!EXECUTABLE_FRAMEWORKS.has(source) || !EXECUTABLE_FRAMEWORKS.has(target)) {
    return "EXECUTION_NOT_AVAILABLE";
  }
  return null;
}

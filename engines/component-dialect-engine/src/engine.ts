/**
 * Top-level orchestration: parse -> canonical model -> emit -> validate.
 *
 * This is the one place that decides PASSED vs BLOCKED. Every other module
 * raises DialectError/RouteError on anything outside certified-component-v1;
 * here that becomes a structured, evidence-carrying report instead of an
 * uncaught exception -- the same convention as
 * `engines/sql-dialect-engine`'s `translate_ddl` and
 * `engines/polyglot-route-engine`'s RouteError -> BLOCKED mapping.
 */
import {
  ALL_FRAMEWORKS, ComponentDef, DialectError, EXECUTABLE_FRAMEWORKS, Framework,
  isParseable, RouteError,
} from "./models";
import { parseReactComponent, parseReactComponents, parseReactComponentResults, ReactParserOptions } from "./parsers/react";
import { parseVue3Component } from "./parsers/vue3";
import { parseVue2Component } from "./parsers/vue2";
import { parseSvelteComponent } from "./parsers/svelte";
import { parseAngularComponent } from "./parsers/angular";
import { parseMiniProgramComponent, MiniProgramSource } from "./parsers/miniprogram";
import { emitReact } from "./emitters/react";
import { emitVue3 } from "./emitters/vue3";
import { emitVue2 } from "./emitters/vue2";
import { emitAngular } from "./emitters/angular";
import { emitSvelte } from "./emitters/svelte";
import { emitMiniProgram } from "./emitters/miniprogram";
import { emitReactNative } from "./emitters/react-native";
import { emitArkUI } from "./emitters/arkui";
import { emitFlutter } from "./emitters/flutter";
import { ExecutionStatus, validateSyntax } from "./validator";
import { compareRendered, defaultExecutionCases } from "./execution";

export type TranslationStatus = "PASSED" | "FAILED" | "BLOCKED";

export interface TranslationReport {
  schemaVersion: "1.0";
  kind: "elmos.component-dialect-translation";
  status: TranslationStatus;
  profile: "certified-component-v1";
  sourceFramework: Framework;
  targetFramework: Framework;
  reasonCode: string | null;
  reason: string | null;
  /** Single-file targets set `emitted`; the WeChat mini program sets
   * `emittedFiles` (wxml/js/json/wxss). Exactly one is non-null. */
  emitted: string | null;
  emittedFiles: Record<string, string> | null;
  /** Constructs with no equivalent on the target that were dropped. Always
   * surfaced, never silently discarded. */
  notes: string[];
  validation: {
    syntaxStatus: "PASSED" | "FAILED";
    syntaxDiagnostics: string[];
    executionStatus: ExecutionStatus;
    executionDiagnostics: string[];
  } | null;
}

export function resolveFramework(value: string): Framework {
  if ((ALL_FRAMEWORKS as readonly string[]).includes(value)) return value as Framework;
  throw new RouteError(`UNSUPPORTED_FRAMEWORK: ${JSON.stringify(value)} is not one of ${ALL_FRAMEWORKS.join(", ")}`);
}

export function parseComponent(source: string | MiniProgramSource, framework: Framework, fileName: string, reactOptions: ReactParserOptions = {}): ComponentDef {
  if (!isParseable(framework)) {
    throw new RouteError(
      `FRAMEWORK_NOT_PARSEABLE: ${framework} can only be a translation TARGET in certified-component-v1. ` +
      `ArkUI's struct syntax has no standalone parser and Flutter needs the Dart SDK; neither is available, ` +
      `so this engine refuses to guess at their source rather than shipping an unverifiable regex parser.`,
    );
  }
  switch (framework) {
    case "react":
    case "typescript":
    case "react-native":
      return parseReactComponent(source as string, fileName, reactOptions);
    case "vue3":
      return parseVue3Component(source as string, fileName);
    case "vue2":
      return parseVue2Component(source as string, fileName);
    case "svelte":
      return parseSvelteComponent(source as string, fileName);
    case "angular":
      return parseAngularComponent(source as string, fileName);
    case "miniprogram":
      // A mini program component is a multi-file bundle, so the caller
      // passes { wxml, js } rather than a single source string.
      return parseMiniProgramComponent(source as unknown as MiniProgramSource, fileName);
    default:
      throw new RouteError(`PARSER_NOT_IMPLEMENTED: ${framework} is declared parseable but its parser is not wired up yet`);
  }
}

interface Emission {
  emitted: string | null;
  emittedFiles: Record<string, string> | null;
  notes: string[];
}

export function emitComponent(component: ComponentDef, framework: Framework): Emission {
  switch (framework) {
    case "react":
    case "typescript":
      return { emitted: emitReact(component), emittedFiles: null, notes: [] };
    case "vue3":
      return { emitted: emitVue3(component), emittedFiles: null, notes: [] };
    case "vue2":
      return {
        emitted: emitVue2(component),
        emittedFiles: null,
        // Vue 2's Options API cannot express an emit payload type, so this
        // information is genuinely lost in the target format. Reported so
        // nobody assumes a later Vue2 -> X translation still has it.
        notes: component.props.some((p) => p.kind === "callback" && p.paramType !== undefined)
          ? ["Vue 2 has no typed emit declaration; callback payload types are not representable and will not survive a translation back out of Vue 2"]
          : [],
      };
    case "angular":
      return { emitted: emitAngular(component), emittedFiles: null, notes: [] };
    case "svelte":
      return { emitted: emitSvelte(component), emittedFiles: null, notes: [] };
    case "react-native": {
      const result = emitReactNative(component);
      return { emitted: result.source, emittedFiles: null, notes: result.notes };
    }
    case "miniprogram": {
      const notes = ["WeChat mini program styling is emitted as generated WXSS classes; the source project's own CSS was NOT translated"];
      // A WeChat `properties` entry has no "required" concept -- every
      // property carries a default value -- so a required prop is emitted
      // with a synthesized empty default and cannot be recovered as
      // required on the way back out.
      if (component.props.some((p) => p.kind === "data" && p.required)) {
        notes.push("WeChat properties cannot express a required prop; required props are emitted with a synthesized default value and will read back as optional");
      }
      // `triggerEvent` detail is untyped, so a callback payload type is
      // lost the same way it is in Vue 2.
      if (component.props.some((p) => p.kind === "callback" && p.paramType !== undefined)) {
        notes.push("WeChat triggerEvent carries an untyped detail object; callback payload types are not representable and will not survive a translation back out of the mini program");
      }
      return { emitted: null, emittedFiles: emitMiniProgram(component), notes };
    }
    case "arkui":
      return {
        emitted: emitArkUI(component),
        emittedFiles: null,
        notes: ["no ArkTS compiler is installed here, so this output has NOT been verified by a real HarmonyOS toolchain"],
      };
    case "flutter":
      return {
        emitted: emitFlutter(component),
        emittedFiles: null,
        notes: ["no Dart SDK is installed here, so this output has NOT been verified by a real Flutter toolchain"],
      };
    default:
      throw new RouteError(`EMITTER_NOT_IMPLEMENTED: no certified-component-v1 emitter for ${framework} yet`);
  }
}

function blocked(source: Framework, target: Framework, code: string, reason: string): TranslationReport {
  return {
    schemaVersion: "1.0",
    kind: "elmos.component-dialect-translation",
    status: "BLOCKED",
    profile: "certified-component-v1",
    sourceFramework: source,
    targetFramework: target,
    reasonCode: code,
    reason,
    emitted: null,
    emittedFiles: null,
    notes: [],
    validation: null,
  };
}

export interface TranslateOptions {
  fileName?: string;
  /** Skip the SSR execution comparison even when both frameworks support
   * it. Off by default: the execution leg is the evidence that matters. */
  skipExecution?: boolean;
  reactOptions?: ReactParserOptions;
}

/**
 * Parse every component in a file.
 *
 * Only React-family sources genuinely carry more than one component per
 * file. A Vue/Svelte single-file component is one component by definition,
 * an Angular file is one @Component, and a WeChat component is one
 * directory -- so for those this is exactly the single-component path
 * rather than a limitation being papered over.
 */
export function parseComponents(source: string | MiniProgramSource, framework: Framework, fileName: string, reactOptions: ReactParserOptions = {}): ComponentDef[] {
  if (framework === "react" || framework === "typescript" || framework === "react-native") {
    return parseReactComponents(source as string, fileName, reactOptions);
  }
  return [parseComponent(source, framework, fileName)];
}

/**
 * Per-component parse results for any source framework, isolating failures.
 *
 * Shared by `translateFile` and by the coverage pre-check so the measured
 * number and the achieved number are produced by the same code path -- a
 * scan that counted differently from the pipeline would be worse than no
 * scan at all.
 */
export function parseComponentResults(
  source: string | MiniProgramSource,
  framework: Framework,
  fileName: string,
  reactOptions: ReactParserOptions = {},
): { name: string | null; component: ComponentDef | null; error: DialectError | null }[] {
  if (framework === "react" || framework === "typescript" || framework === "react-native") {
    return parseReactComponentResults(source as string, fileName, reactOptions);
  }
  try {
    const component = parseComponent(source, framework, fileName, reactOptions);
    return [{ name: component.name, component, error: null }];
  } catch (error) {
    if (error instanceof DialectError) return [{ name: null, component: null, error }];
    throw error;
  }
}

/**
 * Translate every component in a file, in declaration order.
 *
 * Each is reported independently: one component being outside the subset
 * must not blank out the ones beside it that are inside it.
 */
export async function translateFile(
  source: string | MiniProgramSource,
  sourceFramework: string,
  targetFramework: string,
  options: TranslateOptions = {},
): Promise<{ name: string | null; report: TranslationReport }[]> {
  const from = resolveFramework(sourceFramework);
  const to = resolveFramework(targetFramework);
  if (from === to) {
    throw new RouteError("SOURCE_AND_TARGET_MUST_DIFFER: translating a framework to itself is not a supported route");
  }

  // React-family files can declare several components, and one being
  // outside the subset must cost exactly itself -- not the components
  // declared beside it.
  if (from === "react" || from === "typescript" || from === "react-native") {
    let results: ReturnType<typeof parseReactComponentResults>;
    try {
      results = parseReactComponentResults(source as string, options.fileName ?? "Component", options.reactOptions);
    } catch (error) {
      if (error instanceof DialectError) return [{ name: null, report: blocked(from, to, error.code, error.reason) }];
      throw error;
    }
    const out: { name: string | null; report: TranslationReport }[] = [];
    for (const result of results) {
      out.push(result.component !== null
        ? { name: result.component.name, report: await translateParsed(result.component, from, to, options) }
        : { name: result.name, report: blocked(from, to, result.error?.code ?? "UNKNOWN", result.error?.reason ?? "") });
    }
    return out;
  }

  // Every other source format is one component per file by definition.
  let components: ComponentDef[];
  try {
    components = parseComponents(source, from, options.fileName ?? "Component", options.reactOptions);
  } catch (error) {
    if (error instanceof DialectError) return [{ name: null, report: blocked(from, to, error.code, error.reason) }];
    throw error;
  }
  const out: { name: string | null; report: TranslationReport }[] = [];
  for (const component of components) {
    out.push({ name: component.name, report: await translateParsed(component, from, to, options) });
  }
  return out;
}

export async function translateComponent(
  source: string | MiniProgramSource,
  sourceFramework: string,
  targetFramework: string,
  options: TranslateOptions = {},
): Promise<TranslationReport> {
  const from = resolveFramework(sourceFramework);
  const to = resolveFramework(targetFramework);
  if (from === to) {
    throw new RouteError("SOURCE_AND_TARGET_MUST_DIFFER: translating a framework to itself is not a supported route");
  }

  let component: ComponentDef;
  try {
    component = parseComponent(source, from, options.fileName ?? "Component");
  } catch (error) {
    if (error instanceof DialectError) return blocked(from, to, error.code, error.reason);
    throw error;
  }
  return translateParsed(component, from, to, options);
}

/** Emit + validate an already-parsed component. Shared by the single- and
 * multi-component entry points so both legs of validation are identical. */
async function translateParsed(
  component: ComponentDef,
  from: Framework,
  to: Framework,
  options: TranslateOptions,
): Promise<TranslationReport> {
  let emission: Emission;
  try {
    emission = emitComponent(component, to);
  } catch (error) {
    if (error instanceof DialectError) return blocked(from, to, error.code, error.reason);
    throw error;
  }

  const syntax = validateSyntax(to, emission.emittedFiles ?? (emission.emitted as string));

  let executionStatus: ExecutionStatus = "EXECUTION_NOT_AVAILABLE";
  let executionDiagnostics: string[] = [];
  if (options.skipExecution) {
    executionStatus = "EXECUTION_NOT_ATTEMPTED";
  } else if (EXECUTABLE_FRAMEWORKS.has(from) && EXECUTABLE_FRAMEWORKS.has(to) && syntax.status === "PASSED") {
    const sourceEmission = emitComponent(component, from);
    const result = await compareRendered(
      { framework: from, source: sourceEmission.emitted as string },
      { framework: to, source: emission.emitted as string },
      defaultExecutionCases(component),
    );
    executionStatus = result.status;
    executionDiagnostics = result.diagnostics;
  }

  const status: TranslationStatus =
    syntax.status === "FAILED" || executionStatus === "FAILED" ? "FAILED" : "PASSED";

  return {
    schemaVersion: "1.0",
    kind: "elmos.component-dialect-translation",
    status,
    profile: "certified-component-v1",
    sourceFramework: from,
    targetFramework: to,
    reasonCode: status === "PASSED" ? null : "CERTIFIED_COMPONENT_TARGET_VALIDATION_FAILED",
    reason: status === "PASSED" ? null : [...syntax.diagnostics, ...executionDiagnostics].join("; "),
    emitted: emission.emitted,
    emittedFiles: emission.emittedFiles,
    notes: emission.notes,
    validation: {
      syntaxStatus: syntax.status,
      syntaxDiagnostics: syntax.diagnostics,
      executionStatus,
      executionDiagnostics,
    },
  };
}

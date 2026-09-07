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
import { buildCrossPlatformIR, CrossPlatformComponentIR } from "./cross-platform-ir";
import { emitFromTargetAdapter } from "./target-adapters";
import { ComponentEvidenceLedger, createEvidenceLedger } from "./evidence";
import { parseReactComponent, parseReactComponents, parseReactComponentResults, ReactParserOptions } from "./parsers/react";
import { parseVue3Component } from "./parsers/vue3";
import { parseVue2Component } from "./parsers/vue2";
import { parseSvelteComponent } from "./parsers/svelte";
import { parseAngularComponent } from "./parsers/angular";
import { parseMiniProgramComponent, MiniProgramSource } from "./parsers/miniprogram";
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
  /** Typed, framework-neutral semantic contract consumed by the target
   * adapter. Null means the source failed before a canonical component could
   * be constructed. */
  semanticIR: CrossPlatformComponentIR | null;
  targetAdapterId: string | null;
  /** A fail-closed ledger of the evidence still needed for this exact
   * source/target tuple. It starts NOT_RUN and cannot be promoted by JSON
   * editing alone. */
  evidence: ComponentEvidenceLedger | null;
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
      `ArkUI's struct syntax has no standalone parser and Flutter source parsing is owned by the external Dart toolchain; ` +
      `this engine refuses to guess at their source rather than shipping an unverifiable regex parser.`,
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

export function emitComponent(
  component: ComponentDef,
  framework: Framework,
  sourceFramework: Framework = "typescript",
  sourceFile = `${component.name}.source`,
): { emitted: string | null; emittedFiles: Record<string, string> | null; notes: string[] } {
  const ir = buildCrossPlatformIR(component, sourceFramework, sourceFile);
  return emitFromTargetAdapter(ir, framework);
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
    semanticIR: null,
    targetAdapterId: null,
    evidence: null,
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
  const semanticIR = buildCrossPlatformIR(component, from, options.fileName ?? `${component.name}.source`);
  let emission: { emitted: string | null; emittedFiles: Record<string, string> | null; notes: string[] };
  try {
    emission = emitFromTargetAdapter(semanticIR, to);
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
    const sourceEmission = emitFromTargetAdapter(semanticIR, from);
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
    semanticIR,
    targetAdapterId: semanticIR.targetAdapters[to]?.adapterId ?? null,
    evidence: createEvidenceLedger(semanticIR, to),
    validation: {
      syntaxStatus: syntax.status,
      syntaxDiagnostics: syntax.diagnostics,
      executionStatus,
      executionDiagnostics,
    },
  };
}

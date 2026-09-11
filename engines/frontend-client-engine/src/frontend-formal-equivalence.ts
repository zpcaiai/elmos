import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  accessSync,
  constants as fsConstants,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, relative, resolve, sep } from "node:path";

import ts from "typescript";

import {
  navigationSourceSpec,
  type BoundedNavigationSemanticModel,
} from "./bounded-navigation-source.js";
import { generateUiProject, validateUiProjectGenerationRequest } from "./project-generation.js";
import { uiConversionRoutes, uiTargetProfile, uiTargetProfiles } from "./project-profiles.js";
import { renderTargetProject, type ProjectTemplateContext } from "./project-templates.js";
import type {
  GeneratedUiProject,
  UiFrameworkId,
  UiIrNode,
  UiProjectGenerationRequest,
} from "./project-types.js";

export type FrontendFormalStatus = "PROVED_UNDER_ASSUMPTIONS" | "REFUTED" | "NOT_PROVED";

export interface SourceByteSpan {
  readonly path: string;
  readonly start_byte: number;
  readonly end_byte: number;
  readonly content_hash: string;
  readonly subtree_hash: string;
}

export interface ReliftedBoundedNavigation {
  readonly schema_version: "1.0";
  readonly proof_profile: "bounded-navigation-v1";
  readonly profile_id: UiFrameworkId;
  readonly parser: "TYPESCRIPT_AST" | "DART_BOUNDED_BASE64";
  readonly source_path: string;
  readonly source_hash: string;
  readonly model: BoundedNavigationSemanticModel;
  readonly model_digest: string;
  readonly spans: Readonly<Record<string, SourceByteSpan>>;
  readonly consumer_binding: {
    readonly route_table_is_unique: true;
    readonly navigation_consumer: true;
    readonly render_consumer: true;
    readonly accessibility_consumer: true;
    readonly fallback_consumer: true;
    readonly consumed_route_fields: readonly ["id", "path", "title", "text", "requiresAuth", "deepLink"];
  };
}

export interface BehaviorObservation {
  readonly trace_id: string;
  readonly operation: "INITIAL_RENDER" | "SELECT_DECLARED_PATH" | "SELECT_UNKNOWN_PATH";
  readonly input_path: string | null;
  readonly resolution: "DECLARED" | "FIRST_DECLARED_FALLBACK";
  readonly route: {
    readonly id: string;
    readonly path: string;
    readonly title: string;
    readonly text: string;
    readonly requiresAuth: boolean;
    readonly deepLink: boolean;
  };
  readonly render: {
    readonly navigationLabel: string;
    readonly mainRole: string;
    readonly headingLevel: number;
  };
}

export interface FrontendSolverOptions {
  readonly command?: string;
  readonly args?: readonly string[];
  readonly timeout_ms?: number;
}

export interface FrontendSolverResult {
  readonly schema_version: "1.0";
  readonly solver: string;
  readonly solver_binary_realpath: string | null;
  readonly solver_binary_sha256: string | null;
  readonly solver_version: string;
  readonly identity_status: "VERIFIED" | "REJECTED";
  readonly invocation: readonly string[];
  readonly options: { readonly args: readonly string[]; readonly timeout_ms: number };
  readonly environment: { readonly platform: string; readonly arch: string; readonly node_version: string };
  readonly exit_code: number | null;
  readonly stdout: string;
  readonly stderr: string;
  readonly outcome: "UNSAT" | "SAT" | "UNKNOWN" | "MISSING" | "ERROR";
  readonly proof_status: FrontendFormalStatus;
  readonly unconditional_proof: false;
}

export interface FrontendFormalCampaignOptions {
  readonly solver?: FrontendSolverOptions;
  readonly tamper?: {
    readonly profile_id: UiFrameworkId;
    readonly path: string;
    readonly find: string;
    readonly replace: string;
  };
}

const proofAssumptions = [
  "The proof covers only the canonical bounded-navigation-v1 IR and ELMOS-emitted profile projects, not arbitrary customer source.",
  "TypeScript AST plus strict bounded Vue/Svelte template, ArkUI shell, and Dart/base64 parsers faithfully re-lift the generated grammar; native compiler AST evidence remains NOT_RUN where unavailable.",
  "Route requiresAuth and deepLink values are observable metadata; identity enforcement and native deep-link dispatch are outside this bounded proof.",
  "Framework, compiler, router, browser, device, and runtime soundness are assumptions until independent real toolchain and journey evidence passes.",
  "SHA-256 is used for artifact identity and drift detection, not as the semantic equivalence proof rule.",
] as const;

const unsupportedSemanticBlocks = [
  "state",
  "action",
  "effect",
  "form",
  "binding",
  "permission-enforcement",
  "resource",
  "design-token",
  "native-boundary",
  "component-state-action",
] as const;
const lockedZ3Version = "Z3 version 4.16.0 - 64 bit";
const lockedZ3BinaryDigest = "sha256:537a502af2f4013a8e887beebe525a0dae84918a61ff545991e36dfda07ed6d7";
const lockedZ3BinaryDigests = new Set<string>([
  lockedZ3BinaryDigest,
  "sha256:edae32f9e37ea4b5bb35310d72f0e352d0dc07626cac4e9e30bc1ea9a5bc8efb",
]);

const codePointCompare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => codePointCompare(left, right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function frontendFormalDigest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value), "utf8").digest("hex")}`;
}

function bytesDigest(value: string | Buffer): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function json(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function artifactBytes(value: unknown): string {
  return typeof value === "string" ? value : json(value);
}

function artifactDigest(value: unknown): string {
  return bytesDigest(artifactBytes(value));
}

function pointerEscape(value: string): string {
  return value.replaceAll("~", "~0").replaceAll("/", "~1");
}

function byteOffset(text: string, characterOffset: number): number {
  return Buffer.byteLength(text.slice(0, characterOffset), "utf8");
}

function unwrapExpression(node: ts.Expression): ts.Expression {
  let current = node;
  while (
    ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isParenthesizedExpression(current)
    || ts.isSatisfiesExpression(current)
  ) current = current.expression;
  return current;
}

function propertyName(node: ts.PropertyName, source: ts.SourceFile): string {
  if (ts.isIdentifier(node) || ts.isPrivateIdentifier(node)) return node.text;
  if (ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text;
  throw new Error(`computed property is outside bounded navigation grammar at ${source.fileName}`);
}

function parseLiteral(
  node: ts.Expression,
  source: ts.SourceFile,
  sourcePath: string,
  pointer: string,
  spans: Record<string, SourceByteSpan>,
): unknown {
  const expression = unwrapExpression(node);
  const start = expression.getStart(source);
  const end = expression.getEnd();
  const raw = source.text.slice(start, end);
  const record = (value: unknown): unknown => {
    spans[pointer] = {
      path: sourcePath,
      start_byte: byteOffset(source.text, start),
      end_byte: byteOffset(source.text, end),
      content_hash: bytesDigest(raw),
      subtree_hash: frontendFormalDigest(value),
    };
    return value;
  };
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) return record(expression.text);
  if (ts.isNumericLiteral(expression)) return record(Number(expression.text));
  if (expression.kind === ts.SyntaxKind.TrueKeyword) return record(true);
  if (expression.kind === ts.SyntaxKind.FalseKeyword) return record(false);
  if (expression.kind === ts.SyntaxKind.NullKeyword) return record(null);
  if (ts.isArrayLiteralExpression(expression)) {
    const items = expression.elements.map((element, index) => {
      if (ts.isSpreadElement(element)) throw new Error("spread is outside bounded navigation grammar");
      return parseLiteral(element, source, sourcePath, `${pointer}/${index}`, spans);
    });
    return record(items);
  }
  if (ts.isObjectLiteralExpression(expression)) {
    const result: Record<string, unknown> = {};
    for (const member of expression.properties) {
      if (!ts.isPropertyAssignment(member)) throw new Error("non-property member is outside bounded navigation grammar");
      const key = propertyName(member.name, source);
      if (Object.hasOwn(result, key)) throw new Error(`duplicate bounded navigation property: ${key}`);
      result[key] = parseLiteral(member.initializer, source, sourcePath, `${pointer}/${pointerEscape(key)}`, spans);
    }
    return record(result);
  }
  throw new Error(`unsupported bounded navigation literal: ${ts.SyntaxKind[expression.kind]}`);
}

function assertString(value: unknown, name: string): asserts value is string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${name} must be a non-empty string`);
}

function validateBoundedModel(value: unknown): BoundedNavigationSemanticModel {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("bounded navigation model must be an object");
  const model = value as Record<string, unknown>;
  const exactRoot = ["fallback", "navigation", "profile", "projectTitle", "render", "routes", "schemaVersion"];
  if (Object.keys(model).sort().join("|") !== exactRoot.join("|")) throw new Error("bounded navigation root shape drifted");
  if (model.schemaVersion !== "1.0" || model.profile !== "bounded-navigation-v1") throw new Error("bounded navigation identity drifted");
  assertString(model.projectTitle, "projectTitle");
  const navigation = model.navigation as Record<string, unknown>;
  const render = model.render as Record<string, unknown>;
  const fallback = model.fallback as Record<string, unknown>;
  if (!navigation || Object.keys(navigation).join("|") !== "label" || navigation.label !== "主要导航") throw new Error("navigation contract drifted");
  if (!render || Object.keys(render).sort().join("|") !== "headingLevel|mainRole" || render.mainRole !== "main" || render.headingLevel !== 1) throw new Error("render contract drifted");
  if (!fallback || Object.keys(fallback).join("|") !== "strategy" || fallback.strategy !== "FIRST_DECLARED_ROUTE") throw new Error("fallback contract drifted");
  if (!Array.isArray(model.routes) || model.routes.length === 0) throw new Error("bounded navigation routes are required");
  const ids = new Set<string>();
  const paths = new Set<string>();
  for (const [index, raw] of model.routes.entries()) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error(`route ${index} must be an object`);
    const route = raw as Record<string, unknown>;
    const fields = ["deepLink", "id", "path", "requiresAuth", "text", "title"];
    if (Object.keys(route).sort().join("|") !== fields.join("|")) throw new Error(`route ${index} shape drifted`);
    for (const field of ["id", "path", "title", "text"] as const) assertString(route[field], `route ${index}.${field}`);
    if (typeof route.requiresAuth !== "boolean" || typeof route.deepLink !== "boolean") throw new Error(`route ${index} flags drifted`);
    if (ids.has(route.id as string) || paths.has(route.path as string)) throw new Error("bounded navigation route identity is duplicated");
    ids.add(route.id as string);
    paths.add(route.path as string);
  }
  return value as BoundedNavigationSemanticModel;
}

function tsRelift(profile: UiFrameworkId, sourcePath: string, text: string): {
  model: BoundedNavigationSemanticModel;
  spans: Readonly<Record<string, SourceByteSpan>>;
} {
  const kind = sourcePath.endsWith(".js") ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const source = ts.createSourceFile(sourcePath, text, ts.ScriptTarget.Latest, true, kind);
  const parseDiagnostics = (source as ts.SourceFile & { readonly parseDiagnostics?: readonly ts.Diagnostic[] }).parseDiagnostics ?? [];
  if (parseDiagnostics.length > 0) throw new Error(`navigation source parse failed for ${profile}`);
  let initializer: ts.Expression | undefined;
  source.forEachChild(node => {
    if (!ts.isVariableStatement(node)) return;
    for (const declaration of node.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name) && declaration.name.text === "ELMOS_BOUNDED_NAVIGATION") initializer = declaration.initializer;
    }
  });
  if (!initializer) throw new Error("ELMOS_BOUNDED_NAVIGATION declaration is missing");
  requireDirectRoutesIdentity(source, "ELMOS_ROUTES", "ELMOS_BOUNDED_NAVIGATION.routes");
  const spans: Record<string, SourceByteSpan> = {};
  const parsed = parseLiteral(initializer, source, sourcePath, "", spans);
  return { model: validateBoundedModel(parsed), spans };
}

function collectPointers(value: unknown, pointer = "", result: string[] = []): string[] {
  result.push(pointer);
  if (Array.isArray(value)) value.forEach((item, index) => collectPointers(item, `${pointer}/${index}`, result));
  else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      collectPointers((value as Record<string, unknown>)[key], `${pointer}/${pointerEscape(key)}`, result);
    }
  }
  return result;
}

function dartRelift(sourcePath: string, text: string): {
  model: BoundedNavigationSemanticModel;
  spans: Readonly<Record<string, SourceByteSpan>>;
} {
  const match = /const String elmosBoundedNavigationBase64 = "([A-Za-z0-9+/=]+)";/.exec(text);
  if (!match || match.index < 0 || match[1] === undefined) throw new Error("Dart bounded navigation payload is missing");
  const decoded = Buffer.from(match[1], "base64").toString("utf8");
  const model = validateBoundedModel(JSON.parse(decoded));
  if (Buffer.from(decoded, "utf8").toString("base64") !== match[1]) throw new Error("Dart bounded navigation payload is not canonical base64");
  if (!/^final List<Object\?> elmosBoundedRoutes = elmosBoundedNavigation\['routes'\]! as List<Object\?>;$/m.test(text)) {
    throw new Error("elmosBoundedRoutes must be the direct decoded route-list identity alias");
  }
  const groupStart = match.index + match[0].indexOf(match[1]);
  const groupEnd = groupStart + match[1].length;
  const region = text.slice(groupStart, groupEnd);
  const spans: Record<string, SourceByteSpan> = {};
  for (const pointer of collectPointers(model)) {
    spans[pointer] = {
      path: sourcePath,
      start_byte: byteOffset(text, groupStart),
      end_byte: byteOffset(text, groupEnd),
      content_hash: bytesDigest(region),
      subtree_hash: frontendFormalDigest(resolvePointer(model, pointer)),
    };
  }
  return { model, spans };
}

function resolvePointer(value: unknown, pointer: string): unknown {
  if (pointer === "") return value;
  if (!pointer.startsWith("/")) throw new Error(`invalid RFC6901 pointer: ${pointer}`);
  let current = value;
  for (const raw of pointer.slice(1).split("/")) {
    const key = raw.replaceAll("~1", "/").replaceAll("~0", "~");
    if (Array.isArray(current)) {
      if (!/^(?:0|[1-9][0-9]*)$/.test(key)) throw new Error(`invalid array pointer: ${pointer}`);
      current = current[Number(key)];
    } else if (current !== null && typeof current === "object" && Object.hasOwn(current, key)) {
      current = (current as Record<string, unknown>)[key];
    } else throw new Error(`unresolved RFC6901 pointer: ${pointer}`);
  }
  return current;
}

interface ConsumerAstFacts {
  readonly imports: ReadonlyMap<string, ReadonlySet<string>>;
  readonly identifiers: ReadonlySet<string>;
  readonly properties: ReadonlySet<string>;
  readonly elements: ReadonlySet<string>;
  readonly calls: ReadonlySet<string>;
  readonly strings: readonly string[];
  readonly jsx_attributes: ReadonlySet<string>;
  readonly jsx_tags: ReadonlySet<string>;
}

function consumerSource(path: string, text: string): ts.SourceFile {
  const kind = /\.tsx$/.test(path) ? ts.ScriptKind.TSX : /\.jsx?$/.test(path) ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind);
  const diagnostics = (source as ts.SourceFile & { readonly parseDiagnostics?: readonly ts.Diagnostic[] }).parseDiagnostics ?? [];
  if (diagnostics.length > 0) throw new Error(`consumer AST parse failed: ${path}`);
  return source;
}

function astFacts(source: ts.SourceFile, root: ts.Node = source): ConsumerAstFacts {
  const imports = new Map<string, Set<string>>();
  const identifiers = new Set<string>();
  const properties = new Set<string>();
  const elements = new Set<string>();
  const calls = new Set<string>();
  const strings: string[] = [];
  const jsxAttributes = new Set<string>();
  const jsxTags = new Set<string>();
  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const names = imports.get(node.moduleSpecifier.text) ?? new Set<string>();
      const clause = node.importClause;
      if (clause?.name) names.add(clause.name.text);
      if (clause?.namedBindings && ts.isNamedImports(clause.namedBindings)) {
        for (const element of clause.namedBindings.elements) names.add(element.name.text);
      }
      imports.set(node.moduleSpecifier.text, names);
    }
    if (ts.isIdentifier(node)) identifiers.add(node.text);
    if (ts.isPropertyAccessExpression(node)) properties.add(node.getText(source));
    if (ts.isElementAccessExpression(node)) elements.add(node.getText(source));
    if (ts.isCallExpression(node)) calls.add(node.expression.getText(source));
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) strings.push(node.text);
    if (ts.isJsxAttribute(node)) jsxAttributes.add(node.name.getText(source));
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) jsxTags.add(node.tagName.getText(source));
    node.forEachChild(visit);
  };
  visit(root);
  return { imports, identifiers, properties, elements, calls, strings, jsx_attributes: jsxAttributes, jsx_tags: jsxTags };
}

function requireImport(facts: ConsumerAstFacts, moduleName: string, names: readonly string[]): void {
  const imported = facts.imports.get(moduleName);
  if (!imported || names.some(name => !imported.has(name))) throw new Error(`consumer AST import binding drifted: ${moduleName}:${names.join(",")}`);
}

function requireFacts(
  facts: ConsumerAstFacts,
  required: {
    readonly properties?: readonly string[];
    readonly elements?: readonly string[];
    readonly calls?: readonly string[];
    readonly identifiers?: readonly string[];
    readonly jsx_attributes?: readonly string[];
    readonly jsx_tags?: readonly string[];
    readonly string_contains?: readonly string[];
  },
): void {
  for (const [name, actual, expected] of [
    ["property", facts.properties, required.properties ?? []],
    ["element", facts.elements, required.elements ?? []],
    ["call", facts.calls, required.calls ?? []],
    ["identifier", facts.identifiers, required.identifiers ?? []],
    ["JSX attribute", facts.jsx_attributes, required.jsx_attributes ?? []],
    ["JSX tag", facts.jsx_tags, required.jsx_tags ?? []],
  ] as const) {
    for (const item of expected) if (!actual.has(item)) throw new Error(`consumer AST ${name} binding drifted: ${item}`);
  }
  for (const value of required.string_contains ?? []) {
    if (!facts.strings.some(item => item.includes(value))) throw new Error(`consumer AST template/string binding drifted: ${value}`);
  }
}

function requireTopLevelExpression(
  source: ts.SourceFile,
  prefix: string,
  required: Parameters<typeof requireFacts>[1] = {},
): void {
  const statement = source.statements.find(candidate =>
    ts.isExpressionStatement(candidate) && candidate.expression.getText(source).startsWith(prefix));
  if (!statement || !ts.isExpressionStatement(statement)) throw new Error(`reachable top-level entry expression is missing: ${source.fileName}:${prefix}`);
  requireFacts(astFacts(source, statement.expression), required);
}

function requireDirectRoutesIdentity(source: ts.SourceFile, variableName: string, expectedText: string): void {
  const declarations = source.statements.flatMap(statement => ts.isVariableStatement(statement)
    ? [...statement.declarationList.declarations]
    : []).filter(declaration => ts.isIdentifier(declaration.name) && declaration.name.text === variableName);
  if (declarations.length !== 1 || !declarations[0]?.initializer || unwrapExpression(declarations[0].initializer).getText(source) !== expectedText) {
    throw new Error(`${variableName} must be the direct identity alias ${expectedText}`);
  }
}

function namedFunction(source: ts.SourceFile, name: string): ts.FunctionDeclaration {
  const declaration = source.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name?.text === name);
  if (!declaration || !ts.isFunctionDeclaration(declaration) || !declaration.body) throw new Error(`reachable consumer function is missing: ${name}`);
  return declaration;
}

function requireRouteAlias(files: Readonly<Record<string, string>>, path: string, moduleName: string): void {
  const text = files[path];
  if (text === undefined) throw new Error(`route alias source is missing: ${path}`);
  const source = consumerSource(path, text);
  const facts = astFacts(source);
  requireImport(facts, moduleName, ["ELMOS_ROUTES"]);
  requireDirectRoutesIdentity(source, "routes", "ELMOS_ROUTES");
}

function scriptBlock(path: string, text: string): ts.SourceFile {
  const matches = [...text.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
  if (matches.length !== 1 || matches[0]?.[1] === undefined) throw new Error(`bounded component requires exactly one script block: ${path}`);
  return consumerSource(`${path}.ts`, matches[0][1]);
}

function codeWithoutComments(text: string): string {
  return text
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/[^\r\n]*/g, "$1");
}

function requireCodeTokens(files: Readonly<Record<string, string>>, path: string, tokens: readonly string[]): void {
  const text = files[path];
  if (text === undefined) throw new Error(`consumer source is missing: ${path}`);
  const executable = codeWithoutComments(text);
  for (const token of tokens) if (!executable.includes(token)) throw new Error(`bounded consumer grammar drifted in ${path}: ${token}`);
}

function requireEntryReachability(profile: UiFrameworkId, files: Readonly<Record<string, string>>): void {
  const parse = (path: string): ts.SourceFile => {
    const text = files[path];
    if (text === undefined) throw new Error(`entry source is missing: ${path}`);
    return consumerSource(path, text);
  };
  switch (profile) {
    case "react": {
      const entry = parse("src/main.tsx");
      requireImport(astFacts(entry), "./App", ["App"]);
      requireTopLevelExpression(entry, "createRoot(root).render(", { jsx_tags: ["App", "BrowserRouter"] });
      break;
    }
    case "vue3": {
      const entry = parse("src/main.ts");
      requireImport(astFacts(entry), "./App.vue", ["App"]);
      requireImport(astFacts(entry), "./router", ["router"]);
      requireTopLevelExpression(entry, "createApp(App).use(createPinia()).use(router).mount(", { identifiers: ["App", "router"] });
      break;
    }
    case "vue2": {
      const entry = parse("src/main.js");
      requireImport(astFacts(entry), "./App.vue", ["App"]);
      requireImport(astFacts(entry), "./router", ["router"]);
      requireTopLevelExpression(entry, "new Vue({ router, render:", { identifiers: ["App", "router"], calls: ["create"] });
      break;
    }
    case "jquery": {
      const entry = parse("src/main.ts");
      requireImport(astFacts(entry), "./routes", ["routes"]);
      requireTopLevelExpression(entry, "$(\"body\").empty().append(shell)", { identifiers: ["shell"] });
      requireTopLevelExpression(entry, "render(window.location.pathname)", { calls: ["render"] });
      break;
    }
    case "svelte": {
      const entry = parse("src/main.ts");
      requireImport(astFacts(entry), "./App.svelte", ["App"]);
      requireTopLevelExpression(entry, "mount(App, { target })", { identifiers: ["App", "target"], calls: ["mount"] });
      break;
    }
    case "angular": {
      const entry = parse("src/main.ts");
      requireImport(astFacts(entry), "./app/app.component", ["AppComponent"]);
      requireImport(astFacts(entry), "./routes", ["routes"]);
      requireTopLevelExpression(entry, "bootstrapApplication(AppComponent, { providers: [provideRouter(routes)] })", {
        identifiers: ["AppComponent", "routes"], calls: ["bootstrapApplication", "provideRouter"],
      });
      break;
    }
    case "react-native": {
      const entry = parse("index.ts");
      requireImport(astFacts(entry), "./App", ["App"]);
      requireTopLevelExpression(entry, "registerRootComponent(App)", { identifiers: ["App"], calls: ["registerRootComponent"] });
      const app = parse("App.tsx");
      requireImport(astFacts(app), "./src/navigation", ["GeneratedNavigation"]);
      requireFacts(astFacts(app, namedFunction(app, "App")), { jsx_tags: ["GeneratedNavigation"] });
      break;
    }
    case "flutter": {
      const entry = codeWithoutComments(files["lib/main.dart"] ?? "");
      if (/\bif\s*\(\s*false\s*\)/.test(entry)
        || !/^import 'package:flutter\/material\.dart';\nimport 'elmos_bounded_navigation\.dart';/m.test(entry)
        || !/^void main\(\) => runApp\(const GeneratedApp\(\)\);$/m.test(entry)
        || !/class GeneratedApp extends StatelessWidget[\s\S]*?Widget build\(BuildContext context\) \{\n    return MaterialApp\(/.test(entry)
        || !/initialRoute: elmosFirstRoute\.path/.test(entry)
        || !/onUnknownRoute:[\s\S]*GeneratedPage\(route: elmosFirstRoute\)/.test(entry)) {
        throw new Error("Flutter main entry-to-navigation dataflow is not the strict generated grammar");
      }
      break;
    }
    case "harmony-arkui": {
      const ability = codeWithoutComments(files["entry/src/main/ets/entryability/EntryAbility.ets"] ?? "");
      const page = codeWithoutComments(files["entry/src/main/ets/pages/Index.ets"] ?? "");
      if (/\bif\s*\(\s*false\s*\)/.test(`${ability}\n${page}`)
        || !/onWindowStageCreate\(windowStage: window\.WindowStage\): void \{ windowStage\.loadContent\('pages\/Index'\); \}/.test(ability)
        || !/^import \{ ELMOS_ROUTES, elmosSelectBoundedRoute \} from '\.\.\/elmos-bounded-navigation';$/m.test(page)
        || !/@Entry\s+@Component\s+struct Index/.test(page)
        || !/build\(\) \{\s+Navigation\(\)/.test(page)) {
        throw new Error("ArkUI ability-to-page-to-navigation dataflow is not the strict generated grammar");
      }
      const pseudo = consumerSource("arkui-route-alias.ts", page.split("@Entry", 1)[0] ?? "");
      requireDirectRoutesIdentity(pseudo, "GENERATED_ROUTES", "ELMOS_ROUTES");
      break;
    }
  }
}

const generatedConsumerPaths: Readonly<Record<UiFrameworkId, readonly string[]>> = {
  angular: ["src/routes.ts", "src/app/generated-page.component.ts", "src/app/app.component.ts", "src/main.ts"],
  flutter: ["lib/main.dart"],
  "harmony-arkui": ["entry/src/main/ets/entryability/EntryAbility.ets", "entry/src/main/ets/pages/Index.ets"],
  jquery: ["src/routes.ts", "src/main.ts"],
  react: ["src/routes.ts", "src/App.tsx", "src/main.tsx"],
  "react-native": ["index.ts", "App.tsx", "src/navigation.tsx"],
  svelte: ["src/routes.ts", "src/App.svelte", "src/main.ts"],
  vue2: ["src/routes.js", "src/router.js", "src/views/GeneratedPage.vue", "src/App.vue", "src/main.js"],
  vue3: ["src/routes.ts", "src/router.ts", "src/views/GeneratedPage.vue", "src/App.vue", "src/main.ts"],
};

export function boundedNavigationGeneratedConsumerPaths(profile: UiFrameworkId): readonly string[] {
  return generatedConsumerPaths[profile];
}

function generatedProjectName(profile: UiFrameworkId, files: Readonly<Record<string, string>>): string {
  const manifest = files["package.json"];
  if (manifest === undefined) return `formal-${profile.replaceAll("-", "")}`;
  let parsed: unknown;
  try {
    parsed = JSON.parse(manifest);
  } catch {
    throw new Error(`${profile} package manifest is not valid JSON`);
  }
  const name = parsed && typeof parsed === "object" && !Array.isArray(parsed)
    ? (parsed as Record<string, unknown>).name
    : undefined;
  if (typeof name !== "string" || !/^[a-z][a-z0-9-]{1,47}$/.test(name)) {
    throw new Error(`${profile} generated project name is invalid`);
  }
  return name;
}

function expectedConsumerContext(
  profile: UiFrameworkId,
  model: BoundedNavigationSemanticModel,
  files: Readonly<Record<string, string>>,
): ProjectTemplateContext {
  const sourceProfile = uiTargetProfiles().find(candidate => candidate.id !== profile);
  if (!sourceProfile) throw new Error("source profile for consumer grammar is unavailable");
  const node = (id: string, name = id): UiIrNode => ({
    id,
    name,
    kind: "bounded-consumer-grammar",
    references: [],
    sourceRefs: [`generated-consumer/${id}:1`],
  });
  const components = model.routes.map((route, index) => ({
    ...node(`component.expected.${index}`, route.title),
    text: route.text,
    accessibilityRole: "main",
  }));
  const routes = model.routes.map((route, index) => ({
    ...node(route.id),
    path: route.path,
    componentId: components[index]!.id,
    requiresAuth: route.requiresAuth,
    deepLink: route.deepLink,
  }));
  const request: UiProjectGenerationRequest = {
    schemaVersion: "1.0",
    projectName: generatedProjectName(profile, files),
    applicationId: "elmos.generated.consumer",
    title: model.projectTitle,
    source: {
      framework: sourceProfile.id,
      version: sourceProfile.frameworkVersion,
      platform: sourceProfile.platforms[0]!,
    },
    targetFramework: profile,
    packageName: "elmos_generated_consumer",
    bundleId: "io.elmos.generatedconsumer",
    uiIr: {
      schemaVersion: "1.0",
      sourceSnapshotDigest: `sha256:${"0".repeat(64)}`,
      routes,
      views: [],
      components,
      states: [],
      actions: [],
      effects: [],
      forms: [],
      bindings: [],
      permissions: [],
      resources: [],
      designTokens: [],
      accessibility: [],
      nativeBoundaries: [],
      unknowns: [],
    },
  };
  return {
    request,
    profile: uiTargetProfile(profile),
    safeProjectName: request.projectName,
    routes: routes.map((route, index) => ({
      ...route,
      title: model.routes[index]!.title,
      text: model.routes[index]!.text,
    })),
  };
}

export function expectedBoundedNavigationConsumerFiles(
  profile: UiFrameworkId,
  model: BoundedNavigationSemanticModel,
  files: Readonly<Record<string, string>>,
): Readonly<Record<string, string>> {
  return renderTargetProject(expectedConsumerContext(profile, model, files));
}

function validateGeneratedConsumerGrammar(
  profile: UiFrameworkId,
  model: BoundedNavigationSemanticModel,
  files: Readonly<Record<string, string>>,
): void {
  const expected = expectedBoundedNavigationConsumerFiles(profile, model, files);
  for (const path of generatedConsumerPaths[profile]) {
    if (files[path] === undefined) throw new Error(`reachable generated consumer is missing: ${profile}:${path}`);
    if (expected[path] === undefined || files[path] !== expected[path]) {
      throw new Error(`reachable generated consumer grammar drifted: ${profile}:${path}`);
    }
  }
}

function rejectDuplicateRouteTables(
  files: Readonly<Record<string, string>>,
  contractPath: string,
): void {
  const routeKeys = new Set(["id", "path", "title", "text", "requiresAuth", "deepLink"]);
  for (const [path, text] of Object.entries(files)) {
    if (path === contractPath) continue;
    if (/\.(?:ts|tsx|js|jsx|ets)$/.test(path)) {
      const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, path.endsWith("x") ? ts.ScriptKind.TSX : path.endsWith(".js") ? ts.ScriptKind.JS : ts.ScriptKind.TS);
      const walk = (node: ts.Node): void => {
        if (ts.isObjectLiteralExpression(node)) {
          const literalFields = new Set<string>();
          for (const member of node.properties) {
            if (!ts.isPropertyAssignment(member)) continue;
            let key: string;
            try { key = propertyName(member.name, source); } catch { continue; }
            const value = unwrapExpression(member.initializer);
            if (ts.isStringLiteral(value) || value.kind === ts.SyntaxKind.TrueKeyword || value.kind === ts.SyntaxKind.FalseKeyword) literalFields.add(key);
          }
          if ([...routeKeys].every(key => literalFields.has(key))) throw new Error(`duplicate literal route table is forbidden: ${path}`);
        }
        node.forEachChild(walk);
      };
      walk(source);
    }
    if (path.endsWith(".dart") && /GeneratedRoute\s*\(\s*["']/.test(text)) throw new Error(`duplicate Dart route table is forbidden: ${path}`);
  }
}

function validateConsumerBinding(profile: UiFrameworkId, files: Readonly<Record<string, string>>, contractPath: string): void {
  rejectDuplicateRouteTables(files, contractPath);
  switch (profile) {
    case "react": {
      requireRouteAlias(files, "src/routes.ts", "./elmos-bounded-navigation");
      const source = consumerSource("src/App.tsx", files["src/App.tsx"]!);
      requireImport(astFacts(source), "./routes", ["routes"]);
      requireFacts(astFacts(source, namedFunction(source, "App")), {
        properties: ["route.id", "route.path", "route.title", "route.requiresAuth", "route.deepLink"],
        elements: ["routes[0]"], calls: ["routes.map"],
        jsx_attributes: ["aria-label", "data-requires-auth", "data-deep-link"], string_contains: ["*"],
      });
      requireFacts(astFacts(source, namedFunction(source, "GeneratedPage")), {
        properties: ["route.id", "route.path", "route.title", "route.text", "route.requiresAuth", "route.deepLink"],
        jsx_attributes: ["data-route-id", "data-route-path", "data-requires-auth", "data-deep-link"],
      });
      break;
    }
    case "vue3": {
      requireRouteAlias(files, "src/routes.ts", "./elmos-bounded-navigation");
      const router = consumerSource("src/router.ts", files["src/router.ts"]!);
      requireImport(astFacts(router), "./routes", ["routes"]);
      requireFacts(astFacts(router), { properties: ["route.path"], elements: ["routes[0]"], calls: ["routes.map"], string_contains: ["/:pathMatch(.*)*"] });
      const app = scriptBlock("src/App.vue", files["src/App.vue"]!);
      requireImport(astFacts(app), "./routes", ["routes"]);
      requireCodeTokens(files, "src/App.vue", ["route.id", "route.path", "route.title", "route.requiresAuth", "route.deepLink", "data-route-id", 'aria-label="主要导航"']);
      const page = scriptBlock("src/views/GeneratedPage.vue", files["src/views/GeneratedPage.vue"]!);
      requireFacts(astFacts(page), { calls: ["routes.find"], properties: ["route.path"], elements: ["routes[0]"] });
      requireCodeTokens(files, "src/views/GeneratedPage.vue", ["page?.id", "page?.path", "page?.requiresAuth", "page?.deepLink", "page?.title", "page?.text", "data-route-id", "data-route-path", "<main", "<h1>"]);
      break;
    }
    case "vue2": {
      requireRouteAlias(files, "src/routes.js", "./elmos-bounded-navigation");
      const router = consumerSource("src/router.js", files["src/router.js"]!);
      requireFacts(astFacts(router), { properties: ["route.path"], elements: ["routes[0]"], calls: ["routes.map"], string_contains: ["*"] });
      const app = scriptBlock("src/App.vue", files["src/App.vue"]!);
      requireImport(astFacts(app), "./routes", ["routes"]);
      requireCodeTokens(files, "src/App.vue", ["route.id", "route.path", "route.title", "route.requiresAuth", "route.deepLink", "data-route-id", 'aria-label="主要导航"']);
      const page = scriptBlock("src/views/GeneratedPage.vue", files["src/views/GeneratedPage.vue"]!);
      requireFacts(astFacts(page), { calls: ["routes.find"], properties: ["route.path"], elements: ["routes[0]"] });
      requireCodeTokens(files, "src/views/GeneratedPage.vue", ["page.id", "page.path", "page.requiresAuth", "page.deepLink", "page.title", "page.text", "data-route-id", "data-route-path", "<main", "<h1>"]);
      break;
    }
    case "jquery": {
      requireRouteAlias(files, "src/routes.ts", "./elmos-bounded-navigation");
      const source = consumerSource("src/main.ts", files["src/main.ts"]!);
      const render = astFacts(source, namedFunction(source, "render"));
      requireFacts(render, { calls: ["routes.find"], properties: ["candidate.path", "route.id", "route.path", "route.title", "route.text", "route.requiresAuth", "route.deepLink"], elements: ["routes[0]"], string_contains: ["data-route-id", "data-route-path"] });
      requireFacts(astFacts(source), { properties: ["route.id", "route.path", "route.title", "route.requiresAuth", "route.deepLink"], string_contains: ["主要导航"] });
      const called = source.statements.some(statement => ts.isExpressionStatement(statement) && ts.isCallExpression(statement.expression) && ts.isIdentifier(statement.expression.expression) && statement.expression.expression.text === "render");
      if (!called) throw new Error("jQuery render consumer is not reachable from the entry");
      break;
    }
    case "svelte": {
      requireRouteAlias(files, "src/routes.ts", "./elmos-bounded-navigation");
      const source = scriptBlock("src/App.svelte", files["src/App.svelte"]!);
      requireImport(astFacts(source), "./routes", ["routes"]);
      requireFacts(astFacts(source), { calls: ["routes.find"], properties: ["route.path"], elements: ["routes[0]"] });
      requireCodeTokens(files, "src/App.svelte", ["route.id", "route.path", "route.title", "route.requiresAuth", "route.deepLink", "page?.id", "page?.path", "page?.requiresAuth", "page?.deepLink", "page?.title", "page?.text", 'aria-label="主要导航"', "data-route-id", "data-route-path", "<main", "<h1>"]);
      break;
    }
    case "angular": {
      const routes = consumerSource("src/routes.ts", files["src/routes.ts"]!);
      requireImport(astFacts(routes), "./elmos-bounded-navigation", ["ELMOS_ROUTES"]);
      requireFacts(astFacts(routes), { calls: ["ELMOS_ROUTES.map", "route.path.replace", "ELMOS_ROUTES[0]?.path.replace"], elements: ["ELMOS_ROUTES[0]"], properties: ["route.path"], string_contains: ["**"] });
      const app = consumerSource("src/app/app.component.ts", files["src/app/app.component.ts"]!);
      requireImport(astFacts(app), "../elmos-bounded-navigation", ["ELMOS_ROUTES"]);
      requireFacts(astFacts(app), { identifiers: ["ELMOS_ROUTES"], string_contains: ["route.id", "route.path", "route.title", "route.requiresAuth", "route.deepLink", "data-route-id", "aria-label=\"主要导航\""] });
      const page = consumerSource("src/app/generated-page.component.ts", files["src/app/generated-page.component.ts"]!);
      requireFacts(astFacts(page), {
        elements: ['this.route.snapshot.data["id"]', 'this.route.snapshot.data["path"]', 'this.route.snapshot.data["title"]', 'this.route.snapshot.data["text"]', 'this.route.snapshot.data["requiresAuth"]', 'this.route.snapshot.data["deepLink"]'],
        string_contains: ["<main", "<h1>", "data-route-id", "data-route-path", "data-requires-auth", "data-deep-link"],
      });
      break;
    }
    case "react-native": {
      const source = consumerSource("src/navigation.tsx", files["src/navigation.tsx"]!);
      requireImport(astFacts(source), "./elmos-bounded-navigation", ["ELMOS_ROUTES", "elmosSelectBoundedRoute"]);
      requireFacts(astFacts(source), { calls: ["ELMOS_ROUTES.map"] });
      requireFacts(astFacts(source, namedFunction(source, "resolveGeneratedScreen")), { calls: ["elmosSelectBoundedRoute", "ELMOS_ROUTES.findIndex", "generatedScreenName"], identifiers: ["selected"] });
      requireFacts(astFacts(source, namedFunction(source, "GeneratedNavigation")), { calls: ["resolveGeneratedScreen", "ELMOS_ROUTES.map", "generatedScreenName"], properties: ["route.id", "route.path", "route.title", "route.text", "route.requiresAuth", "route.deepLink"], jsx_attributes: ["initialRouteName"] });
      requireFacts(astFacts(source, namedFunction(source, "GeneratedScreen")), { properties: ["route.params.id", "route.params.path", "route.params.requiresAuth", "route.params.deepLink", "route.params.title", "route.params.text"], jsx_attributes: ["accessibilityLabel"] });
      break;
    }
    case "flutter":
      requireCodeTokens(files, "lib/elmos_bounded_navigation.dart", ["elmosBoundedRoutes = elmosBoundedNavigation['routes']", "get id => this['id']", "get path => this['path']", "get title => this['title']", "get text => this['text']", "get requiresAuth => this['requiresAuth']", "get deepLink => this['deepLink']", "orElse: () => elmosBoundedRoutes.first"]);
      requireCodeTokens(files, "lib/main.dart", ["elmosFirstRoute.path", "for (final raw in elmosBoundedRoutes)", "elmosRoute(raw).path", "onUnknownRoute", "route.id", "route.path", "route.requiresAuth", "route.deepLink", "route.title", "route.text", "Semantics("]);
      break;
    case "harmony-arkui":
      requireCodeTokens(files, "entry/src/main/ets/pages/Index.ets", ["GENERATED_ROUTES: readonly GeneratedRoute[] = ELMOS_ROUTES", "elmosSelectBoundedRoute", "'/__unknown__'", "item.id", "item.path", "item.requiresAuth", "item.deepLink", "item.title", "this.currentRoute().title", "this.currentRoute().text", "accessibilityText"]);
      break;
  }
}

function validateContractConsumer(profile: UiFrameworkId, source: string): void {
  const tokens = profile === "flutter"
    ? ["elmosBoundedRoutes.first", "route.id", "route.path", "route.title", "route.text", "route.requiresAuth", "route.deepLink", "navigation['label']", "render['mainRole']", "render['headingLevel']"]
    : [".find(route => route.path === path)", "routes[0]", "route.id", "route.path", "route.title", "route.text", "route.requiresAuth", "route.deepLink", "navigation.label", "render.mainRole", "render.headingLevel"];
  if (profile === "flutter") {
    const executable = codeWithoutComments(source);
    for (const token of tokens) if (!executable.includes(token)) throw new Error(`bounded selector/observer dataflow drifted: ${token}`);
    return;
  }
  const parsed = consumerSource(navigationSourceSpec(profile).sourcePath, source);
  const select = astFacts(parsed, namedFunction(parsed, "elmosSelectBoundedRoute"));
  requireFacts(select, { calls: ["ELMOS_BOUNDED_NAVIGATION.routes.find"], properties: ["route.path"], elements: ["ELMOS_BOUNDED_NAVIGATION.routes[0]"] });
  const observe = astFacts(parsed, namedFunction(parsed, "elmosObserveBoundedRoute"));
  requireFacts(observe, { calls: ["elmosSelectBoundedRoute"], properties: ["route.id", "route.path", "route.title", "route.text", "route.requiresAuth", "route.deepLink", "ELMOS_BOUNDED_NAVIGATION.navigation.label", "ELMOS_BOUNDED_NAVIGATION.render.mainRole", "ELMOS_BOUNDED_NAVIGATION.render.headingLevel"] });
}

export function reliftBoundedNavigationProject(
  profile: UiFrameworkId,
  files: Readonly<Record<string, string>>,
): ReliftedBoundedNavigation {
  const spec = navigationSourceSpec(profile);
  const text = files[spec.sourcePath];
  if (text === undefined) throw new Error(`navigation source is missing: ${spec.sourcePath}`);
  const parsed = spec.parser === "TYPESCRIPT_AST"
    ? tsRelift(profile, spec.sourcePath, text)
    : dartRelift(spec.sourcePath, text);
  validateContractConsumer(profile, text);
  requireEntryReachability(profile, files);
  validateConsumerBinding(profile, files, spec.sourcePath);
  validateGeneratedConsumerGrammar(profile, parsed.model, files);
  return {
    schema_version: "1.0",
    proof_profile: "bounded-navigation-v1",
    profile_id: profile,
    parser: spec.parser,
    source_path: spec.sourcePath,
    source_hash: bytesDigest(text),
    model: parsed.model,
    model_digest: frontendFormalDigest(parsed.model),
    spans: parsed.spans,
    consumer_binding: {
      route_table_is_unique: true,
      navigation_consumer: true,
      render_consumer: true,
      accessibility_consumer: true,
      fallback_consumer: true,
      consumed_route_fields: ["id", "path", "title", "text", "requiresAuth", "deepLink"],
    },
  };
}

export function canonicalBoundedNavigationModel(request: UiProjectGenerationRequest): BoundedNavigationSemanticModel {
  const valid = validateUiProjectGenerationRequest(request);
  const components = new Map(valid.uiIr.components.map(component => [component.id, component]));
  return {
    schemaVersion: "1.0",
    profile: "bounded-navigation-v1",
    projectTitle: valid.title,
    navigation: { label: "主要导航" },
    render: { mainRole: "main", headingLevel: 1 },
    fallback: { strategy: "FIRST_DECLARED_ROUTE" },
    routes: valid.uiIr.routes.map(route => {
      const component = components.get(route.componentId);
      if (!component) throw new Error(`canonical route component is missing: ${route.componentId}`);
      return {
        id: route.id,
        path: route.path,
        title: component.name,
        text: component.text,
        requiresAuth: route.requiresAuth,
        deepLink: route.deepLink,
      };
    }),
  };
}

export function observeBoundedNavigationModel(model: BoundedNavigationSemanticModel, interpreter: string): readonly BehaviorObservation[] {
  const first = model.routes[0];
  if (!first) throw new Error("behavior domain requires a first route");
  const observation = (
    traceId: string,
    operation: BehaviorObservation["operation"],
    inputPath: string | null,
    selected: typeof first,
    resolution: BehaviorObservation["resolution"],
  ): BehaviorObservation => ({
    trace_id: `${interpreter}:${traceId}`,
    operation,
    input_path: inputPath,
    resolution,
    route: { ...selected },
    render: {
      navigationLabel: model.navigation.label,
      mainRole: model.render.mainRole,
      headingLevel: model.render.headingLevel,
    },
  });
  return [
    observation("initial", "INITIAL_RENDER", null, first, "FIRST_DECLARED_FALLBACK"),
    ...model.routes.map((route, index) => observation(`declared-${index}`, "SELECT_DECLARED_PATH", route.path, route, "DECLARED")),
    observation("unknown", "SELECT_UNKNOWN_PATH", "/__elmos_unknown_route__", first, "FIRST_DECLARED_FALLBACK"),
  ];
}

function behaviorComparable(observations: readonly BehaviorObservation[]): unknown {
  return observations.map(({ trace_id: _traceId, ...rest }) => rest);
}

function independentObserve(model: BoundedNavigationSemanticModel): readonly BehaviorObservation[] {
  const inputs: ReadonlyArray<{ operation: BehaviorObservation["operation"]; path: string | null }> = [
    { operation: "INITIAL_RENDER", path: null },
    ...model.routes.map(route => ({ operation: "SELECT_DECLARED_PATH" as const, path: route.path })),
    { operation: "SELECT_UNKNOWN_PATH", path: "/__elmos_unknown_route__" },
  ];
  const first = model.routes.at(0);
  if (!first) throw new Error("reference behavior requires a route");
  return inputs.map((input, index) => {
    const match = input.path === null ? undefined : model.routes.filter(route => route.path === input.path).at(0);
    const selected = match === undefined ? first : match;
    return {
      trace_id: `reference:${index}`,
      operation: input.operation,
      input_path: input.path,
      resolution: match === undefined ? "FIRST_DECLARED_FALLBACK" : "DECLARED",
      route: { ...selected },
      render: { navigationLabel: model.navigation.label, mainRole: model.render.mainRole, headingLevel: model.render.headingLevel },
    };
  });
}

function flatten(value: unknown, pointer = "", output: Record<string, string> = {}): Record<string, string> {
  if (Array.isArray(value)) {
    output[`${pointer}/#length`] = String(value.length);
    value.forEach((item, index) => flatten(item, `${pointer}/${index}`, output));
  } else if (value !== null && typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).sort();
    output[`${pointer}/#keys`] = keys.join("\u001f");
    for (const key of keys) flatten((value as Record<string, unknown>)[key], `${pointer}/${pointerEscape(key)}`, output);
  } else output[pointer] = canonical(value);
  return output;
}

function smtString(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

export function buildFrontendSmt2(
  canonicalModel: BoundedNavigationSemanticModel,
  sourceModel: BoundedNavigationSemanticModel,
  targetModel: BoundedNavigationSemanticModel,
  canonicalBehavior: readonly BehaviorObservation[],
  independentBehavior: readonly BehaviorObservation[],
  sourceBehavior: readonly BehaviorObservation[],
  targetBehavior: readonly BehaviorObservation[],
  formalInputDigest = "UNBOUND_FORMAL_INPUT",
): string {
  const datasets = [
    flatten({ semantic: canonicalModel, behavior: behaviorComparable(canonicalBehavior) }),
    flatten({ semantic: sourceModel, behavior: behaviorComparable(sourceBehavior) }),
    flatten({ semantic: targetModel, behavior: behaviorComparable(targetBehavior) }),
    flatten({ semantic: canonicalModel, behavior: behaviorComparable(independentBehavior) }),
  ];
  const pointers = [...new Set(datasets.flatMap(item => Object.keys(item)))].sort();
  const lines = [
    "; ELMOS bounded-navigation-v1 canonical/source/target/reference equivalence",
    `; formal-input-bytes-digest: ${formalInputDigest}`,
    "; Framework/compiler/runtime soundness is explicitly outside this bounded formula.",
    "(set-logic ALL)",
    "(declare-const event Int)",
    "(declare-const input_path String)",
    "(assert (or (= event 0) (= event 1)))",
  ];
  const disequalities: string[] = [];
  const semanticModels = [canonicalModel, sourceModel, targetModel, canonicalModel] as const;
  const prefixes = ["canonical", "source", "target", "reference"] as const;
  const literal = (value: string | boolean | number, sort: "String" | "Bool" | "Int"): string => {
    if (sort === "String") return smtString(String(value));
    if (sort === "Bool") return value ? "true" : "false";
    return String(value);
  };
  const selector = (
    model: BoundedNavigationSemanticModel,
    field: keyof BoundedNavigationSemanticModel["routes"][number],
    sort: "String" | "Bool",
  ): string => {
    const first = model.routes[0]!;
    let selected = literal(first[field], sort);
    for (const route of [...model.routes].reverse()) {
      selected = `(ite (= input_path ${smtString(route.path)}) ${literal(route[field], sort)} ${selected})`;
    }
    return `(ite (= event 0) ${literal(first[field], sort)} ${selected})`;
  };
  const symbolicFields: ReadonlyArray<readonly [string, keyof BoundedNavigationSemanticModel["routes"][number], "String" | "Bool"]> = [
    ["route_id", "id", "String"], ["path", "path", "String"], ["title", "title", "String"],
    ["text", "text", "String"], ["requires_auth", "requiresAuth", "Bool"], ["deep_link", "deepLink", "Bool"],
  ];
  for (const [name, field, sort] of symbolicFields) {
    for (const [index, prefix] of prefixes.entries()) {
      lines.push(`(define-fun ${prefix}_${name} ((event_arg Int) (path_arg String)) ${sort} ${selector(semanticModels[index]!, field, sort).replaceAll("event", "event_arg").replaceAll("input_path", "path_arg")})`);
    }
    disequalities.push(
      `(not (= (canonical_${name} event input_path) (source_${name} event input_path)))`,
      `(not (= (canonical_${name} event input_path) (target_${name} event input_path)))`,
      `(not (= (canonical_${name} event input_path) (reference_${name} event input_path)))`,
    );
  }
  const renderFields: ReadonlyArray<readonly [string, "String" | "Int", (model: BoundedNavigationSemanticModel) => string | number]> = [
    ["navigation_label", "String", model => model.navigation.label],
    ["main_role", "String", model => model.render.mainRole],
    ["heading_level", "Int", model => model.render.headingLevel],
  ];
  for (const [name, sort, get] of renderFields) {
    for (const [index, prefix] of prefixes.entries()) lines.push(`(define-fun ${prefix}_${name} () ${sort} ${literal(get(semanticModels[index]!), sort)})`);
    disequalities.push(
      `(not (= canonical_${name} source_${name}))`,
      `(not (= canonical_${name} target_${name}))`,
      `(not (= canonical_${name} reference_${name}))`,
    );
  }
  for (const [index, pointer] of pointers.entries()) {
    const names = ["canonical", "source", "target", "reference"].map(prefix => `${prefix}_${index}`);
    for (const [datasetIndex, name] of names.entries()) {
      lines.push(`(declare-const ${name} String)`);
      lines.push(`(assert (= ${name} ${smtString(datasets[datasetIndex]?.[pointer] ?? "__MISSING_POINTER__")}))`);
    }
    disequalities.push(`(distinct ${names[0]} ${names[1]})`, `(distinct ${names[0]} ${names[2]})`, `(distinct ${names[0]} ${names[3]})`);
  }
  lines.push(`(assert (or ${disequalities.join(" ")}))`, "(check-sat)", "(exit)", "");
  return lines.join("\n");
}

export function runFrontendSolver(smt2: string, options: FrontendSolverOptions = {}): FrontendSolverResult {
  const command = options.command ?? process.env.ELMOS_FRONTEND_Z3 ?? "z3";
  const timeout = options.timeout_ms ?? 10_000;
  const rejected = (
    outcome: "MISSING" | "ERROR",
    reason: string,
    realpath: string | null = null,
    binaryDigest: string | null = null,
    version = "UNKNOWN",
  ): FrontendSolverResult => ({
    schema_version: "1.0",
    solver: command,
    solver_binary_realpath: realpath,
    solver_binary_sha256: binaryDigest,
    solver_version: version,
    identity_status: "REJECTED",
    invocation: realpath === null ? [command, "-in"] : [realpath, "-in"],
    options: { args: ["-in"], timeout_ms: timeout },
    environment: { platform: process.platform, arch: process.arch, node_version: process.version },
    exit_code: null,
    stdout: "",
    stderr: reason,
    outcome,
    proof_status: "NOT_PROVED",
    unconditional_proof: false,
  });
  if ((options.args?.length ?? 0) > 0) return rejected("ERROR", "custom solver arguments are forbidden by the locked Z3 profile");
  let binaryPath: string | undefined;
  const candidates = command.includes("/")
    ? [resolve(command)]
    : (process.env.PATH ?? "").split(":").filter(Boolean).map(directory => join(directory, command));
  for (const candidate of candidates) {
    try {
      accessSync(candidate, fsConstants.X_OK);
      binaryPath = realpathSync(candidate);
      break;
    } catch { /* continue bounded PATH search */ }
  }
  if (binaryPath === undefined) return rejected("MISSING", "locked Z3 executable is missing");
  const binaryDigest = bytesDigest(readFileSync(binaryPath));
  if (basename(binaryPath) !== "z3") return rejected("ERROR", "solver executable identity is not Z3", binaryPath, binaryDigest);
  if (!lockedZ3BinaryDigests.has(binaryDigest)) return rejected("ERROR", "solver binary digest is not the locked Z3 4.16.0 artifact", binaryPath, binaryDigest);
  const versionResult = spawnSync(binaryPath, ["-version"], { encoding: "utf8", timeout: Math.min(timeout, 5_000) });
  const solverVersion = versionResult.status === 0 ? (versionResult.stdout ?? "").trim() : "UNKNOWN";
  if (solverVersion !== lockedZ3Version) {
    return rejected("ERROR", "solver version is not the locked Z3 4.16.0 tuple", binaryPath, binaryDigest, solverVersion);
  }
  const args = ["-in"] as const;
  const result = spawnSync(binaryPath, args, {
    encoding: "utf8",
    input: smt2,
    timeout,
    maxBuffer: 4 * 1024 * 1024,
  });
  const stdout = result.stdout ?? "";
  const stderr = result.stderr ?? "";
  let outcome: FrontendSolverResult["outcome"];
  if (result.error && (result.error as NodeJS.ErrnoException).code === "ENOENT") outcome = "MISSING";
  else if (result.error || result.status !== 0) outcome = "ERROR";
  else {
    outcome = stderr !== "" ? "ERROR"
      : stdout === "unsat\n" ? "UNSAT"
        : stdout === "sat\n" ? "SAT"
          : stdout === "unknown\n" ? "UNKNOWN"
            : "ERROR";
  }
  return {
    schema_version: "1.0",
    solver: binaryPath,
    solver_binary_realpath: binaryPath,
    solver_binary_sha256: binaryDigest,
    solver_version: solverVersion,
    identity_status: "VERIFIED",
    invocation: [binaryPath, ...args],
    options: { args, timeout_ms: timeout },
    environment: { platform: process.platform, arch: process.arch, node_version: process.version },
    exit_code: result.status,
    stdout,
    stderr,
    outcome,
    proof_status: outcome === "UNSAT" ? "PROVED_UNDER_ASSUMPTIONS" : outcome === "SAT" ? "REFUTED" : "NOT_PROVED",
    unconditional_proof: false,
  };
}

function fixtureNode(id: string, references: readonly string[] = []): UiIrNode {
  return { id, name: id, kind: "bounded-fixture", references, sourceRefs: [`fixture/${id}.tsx:1`] };
}

export function frontendFormalFixtureRequest(target: UiFrameworkId): UiProjectGenerationRequest {
  const sourceProfile = uiTargetProfiles().find(profile => profile.id !== target);
  if (!sourceProfile) throw new Error("source profile fixture is unavailable");
  return {
    schemaVersion: "1.0",
    projectName: `formal-${target.replaceAll("-", "")}`,
    applicationId: "elmos.formal.frontend",
    title: "ELMOS 有界导航验证",
    source: {
      framework: sourceProfile.id,
      version: sourceProfile.frameworkVersion,
      platform: sourceProfile.platforms[0]!,
    },
    targetFramework: target,
    packageName: "elmos_formal_frontend",
    bundleId: "io.elmos.formalfrontend",
    uiIr: {
      schemaVersion: "1.0",
      sourceSnapshotDigest: `sha256:${"b".repeat(64)}`,
      routes: [
        { ...fixtureNode("route.home", ["component.home"]), path: "/", componentId: "component.home", requiresAuth: false, deepLink: true },
        { ...fixtureNode("route.account", ["component.account"]), path: "/account", componentId: "component.account", requiresAuth: true, deepLink: true },
        { ...fixtureNode("route.help", ["component.help"]), path: "/help", componentId: "component.help", requiresAuth: false, deepLink: false },
      ],
      views: [fixtureNode("view.shell", ["component.home", "component.account", "component.help"])],
      components: [
        { ...fixtureNode("component.home", ["state.navigation"]), text: "首页内容", accessibilityRole: "main" },
        { ...fixtureNode("component.account", ["state.navigation"]), text: "账户内容", accessibilityRole: "main" },
        { ...fixtureNode("component.help", ["state.navigation"]), text: "帮助内容", accessibilityRole: "main" },
      ],
      states: [fixtureNode("state.navigation")],
      actions: [fixtureNode("action.select-route", ["state.navigation"])],
      effects: [fixtureNode("effect.history", ["action.select-route"])],
      forms: [fixtureNode("form.none")],
      bindings: [fixtureNode("binding.route", ["state.navigation"])],
      permissions: [fixtureNode("permission.route-metadata")],
      resources: [fixtureNode("resource.route-copy")],
      designTokens: [fixtureNode("token.navigation")],
      accessibility: [fixtureNode("a11y.navigation", ["view.shell"])],
      nativeBoundaries: [],
      unknowns: [],
    },
  };
}

interface ProfileBundle {
  readonly project: GeneratedUiProject;
  readonly relift: ReliftedBoundedNavigation;
  readonly canonical_model: BoundedNavigationSemanticModel;
  readonly project_digest: string;
}

function projectDigest(files: Readonly<Record<string, string>>): string {
  return frontendFormalDigest(Object.fromEntries(Object.entries(files).sort(([left], [right]) => codePointCompare(left, right))));
}

function makeProfileBundles(options: FrontendFormalCampaignOptions): ReadonlyMap<UiFrameworkId, ProfileBundle> {
  const result = new Map<UiFrameworkId, ProfileBundle>();
  for (const profile of uiTargetProfiles()) {
    const request = frontendFormalFixtureRequest(profile.id);
    const generated = generateUiProject(request);
    const files = { ...generated.files };
    if (options.tamper?.profile_id === profile.id) {
      const current = files[options.tamper.path];
      if (current === undefined || !current.includes(options.tamper.find)) throw new Error("requested tamper target was not found");
      files[options.tamper.path] = current.replace(options.tamper.find, options.tamper.replace);
    }
    const project = { ...generated, files };
    const relift = reliftBoundedNavigationProject(profile.id, project.files);
    result.set(profile.id, {
      project,
      relift,
      canonical_model: canonicalBoundedNavigationModel(request),
      project_digest: projectDigest(project.files),
    });
  }
  return result;
}

function assertSafeRelative(path: string): void {
  if (!path || path.startsWith("/") || path.includes("\\") || path.split("/").includes("..")) throw new Error(`unsafe generated path: ${path}`);
}

function materializeProject(root: string, files: Readonly<Record<string, string>>): void {
  for (const [path, content] of Object.entries(files)) {
    assertSafeRelative(path);
    const destination = join(root, ...path.split("/"));
    mkdirSync(dirname(destination), { recursive: true });
    writeFileSync(destination, content, "utf8");
  }
}

function writeArtifact(root: string, relativePath: string, value: unknown): string {
  const destination = join(root, ...relativePath.split("/"));
  mkdirSync(dirname(destination), { recursive: true });
  const content = artifactBytes(value);
  writeFileSync(destination, content, "utf8");
  return bytesDigest(content);
}

function routeChunks(source: ReliftedBoundedNavigation, target: ReliftedBoundedNavigation): readonly Record<string, unknown>[] {
  const pointers = collectPointers(source.model).sort();
  if (pointers.join("|") !== collectPointers(target.model).sort().join("|")) throw new Error("semantic pointer sets diverged");
  return pointers.map(pointer => ({
    pointer,
    pointer_standard: "RFC6901",
    source: source.spans[pointer],
    target: target.spans[pointer],
    canonical_subtree_hash: frontendFormalDigest(resolvePointer(source.model, pointer)),
    source_subtree_hash: source.spans[pointer]?.subtree_hash,
    target_subtree_hash: target.spans[pointer]?.subtree_hash,
    equivalent: source.spans[pointer]?.subtree_hash === target.spans[pointer]?.subtree_hash,
  }));
}

export function materializeFrontendFormalCampaign(
  outputDirectory: string,
  options: FrontendFormalCampaignOptions = {},
): Readonly<Record<string, unknown>> {
  const output = resolve(outputDirectory);
  if (existsSync(output) && readdirSync(output).length > 0) throw new Error("frontend formal output directory must be absent or empty");
  mkdirSync(output, { recursive: true });
  const bundles = makeProfileBundles(options);
  const profileRecords: Record<string, unknown>[] = [];
  for (const profile of uiTargetProfiles()) {
    const bundle = bundles.get(profile.id)!;
    const profileRoot = join(output, "profiles", profile.id);
    materializeProject(join(profileRoot, "project"), bundle.project.files);
    const files = Object.entries(bundle.project.files).sort(([left], [right]) => codePointCompare(left, right)).map(([path, content]) => ({
      path,
      sha256: bytesDigest(content),
      byte_count: Buffer.byteLength(content, "utf8"),
    }));
    const manifestBase = {
      schema_version: "1.0",
      kind: "frontend-formal-profile-project",
      profile_id: profile.id,
      framework_version: profile.frameworkVersion,
      platforms: profile.platforms,
      project_path: "project",
      project_digest: bundle.project_digest,
      digest_scope: "sorted UTF-8 project files keyed by POSIX relative path",
      file_count: files.length,
      files,
    };
    const manifest = { ...manifestBase, manifest_digest: frontendFormalDigest(manifestBase) };
    writeArtifact(output, `profiles/${profile.id}/manifest.json`, manifest);
    profileRecords.push({
      profile_id: profile.id,
      framework_version: profile.frameworkVersion,
      platforms: profile.platforms,
      project_path: `profiles/${profile.id}/project`,
      project_digest: bundle.project_digest,
      manifest_path: `profiles/${profile.id}/manifest.json`,
      manifest_digest: manifest.manifest_digest,
      navigation_source_path: bundle.relift.source_path,
      relift_model_digest: bundle.relift.model_digest,
      target_build: "NOT_RUN",
    });
  }

  const routeRecords: Record<string, unknown>[] = [];
  for (const route of uiConversionRoutes()) {
    const source = bundles.get(route.source)!;
    const target = bundles.get(route.target)!;
    const canonicalModel = source.canonical_model;
    const canonicalBehavior = observeBoundedNavigationModel(canonicalModel, "canonical");
    const independentBehavior = independentObserve(canonicalModel);
    const sourceBehavior = observeBoundedNavigationModel(source.relift.model, "source");
    const targetBehavior = observeBoundedNavigationModel(target.relift.model, "target");
    const semanticEqual = canonical(source.relift.model) === canonical(canonicalModel)
      && canonical(target.relift.model) === canonical(canonicalModel);
    const behaviorEqual = canonical(behaviorComparable(canonicalBehavior)) === canonical(behaviorComparable(independentBehavior))
      && canonical(behaviorComparable(canonicalBehavior)) === canonical(behaviorComparable(sourceBehavior))
      && canonical(behaviorComparable(canonicalBehavior)) === canonical(behaviorComparable(targetBehavior));
    const chunks = routeChunks(source.relift, target.relift);
    const chunkEqual = chunks.every(chunk => chunk.equivalent === true);
    const routeRoot = `routes/${route.routeId}`;
    const behavior = {
      schema_version: "1.0",
      domain: {
        id: "bounded-navigation-domain-v1",
        operations: ["INITIAL_RENDER", "SELECT_DECLARED_PATH", "SELECT_UNKNOWN_PATH"],
        unknown_path_policy: "FIRST_DECLARED_ROUTE",
        framework_native_runtime: "NOT_RUN",
      },
      canonical: { runtime_kind: "SPEC_INTERPRETER", observations: canonicalBehavior },
      independent: { runtime_kind: "BOUNDED_REFERENCE_INTERPRETER", observations: independentBehavior },
      source: { runtime_kind: "RELIFTED_EMITTED_SOURCE_INTERPRETER", observations: sourceBehavior },
      target: { runtime_kind: "RELIFTED_EMITTED_TARGET_INTERPRETER", observations: targetBehavior },
      equivalent: behaviorEqual,
      native_browser_or_device_evidence: "NOT_RUN",
    };
    const chunkArtifact = { schema_version: "1.0", route_id: route.routeId, chunks, equivalent: chunkEqual };
    const sourceModelArtifactDigest = artifactDigest(source.relift);
    const targetModelArtifactDigest = artifactDigest(target.relift);
    const formalInput = {
      schema_version: "1.0",
      kind: "frontend-bounded-navigation-formal-input",
      corpus_id: "frontend-bounded-navigation-corpus-v1",
      proof_profile: "bounded-navigation-v1",
      proof_scope: "canonical bounded navigation IR <-> emitted source re-lift <-> emitted target re-lift",
      route_id: route.routeId,
      tuple: {
        source_profile: route.source,
        source_framework_version: uiTargetProfile(route.source).frameworkVersion,
        target_profile: route.target,
        target_framework_version: uiTargetProfile(route.target).frameworkVersion,
      },
      source_project_digest: source.project_digest,
      target_project_digest: target.project_digest,
      canonical_model: canonicalModel,
      canonical_model_digest: frontendFormalDigest(canonicalModel),
      source_model_digest: source.relift.model_digest,
      target_model_digest: target.relift.model_digest,
      source_model_artifact_digest: sourceModelArtifactDigest,
      target_model_artifact_digest: targetModelArtifactDigest,
      semantic_equal: semanticEqual,
      behavior_digest: artifactDigest(behavior),
      behavior_equal: behaviorEqual,
      chunk_digest: artifactDigest(chunkArtifact),
      chunk_equal: chunkEqual,
      assumptions: proofAssumptions,
      semantic_blocks: {
        proved: ["route-id-path-title-text-auth-deeplink", "navigation-consumer", "render-a11y-consumer", "first-route-fallback"],
        externally_composable_not_run: ["certified-component-v1"],
        unsupported_not_proved: unsupportedSemanticBlocks,
      },
      arbitrary_customer_source: "NOT_PROVED",
      compiler_framework_runtime_soundness: "ASSUMED_NOT_PROVED",
    };
    const formalInputDigest = artifactDigest(formalInput);
    const smt2 = buildFrontendSmt2(canonicalModel, source.relift.model, target.relift.model, canonicalBehavior, independentBehavior, sourceBehavior, targetBehavior, formalInputDigest);
    const solver = runFrontendSolver(smt2, options.solver);
    const smt2Digest = bytesDigest(smt2);
    const status: FrontendFormalStatus = !semanticEqual || !behaviorEqual || !chunkEqual
      ? "REFUTED"
      : solver.proof_status;
    const solverResult = {
      ...solver,
      route_id: route.routeId,
      formal_input_digest: formalInputDigest,
      solver_input_digest: smt2Digest,
      smt2_digest: smt2Digest,
    };
    const solverResultDigest = artifactDigest(solverResult);
    const composition = {
      schema_version: "1.0",
      route_id: route.routeId,
      source_lifting: { profile_id: route.source, project_digest: source.project_digest, model_digest: source.relift.model_digest },
      target_lowering_relift: { profile_id: route.target, project_digest: target.project_digest, model_digest: target.relift.model_digest },
      canonical_model_digest: frontendFormalDigest(canonicalModel),
      semantic_equal: semanticEqual,
      chunk_equal: chunkEqual,
      behavior_equal: behaviorEqual,
      solver_outcome: solver.outcome,
      status,
    };
    const layered = {
      schema_version: "1.0",
      kind: "frontend-bounded-navigation-layered-result",
      route_id: route.routeId,
      proof_profile: "bounded-navigation-v1",
      links: {
        formal_input_path: `${routeRoot}/formal-input.json`,
        formal_input_digest: formalInputDigest,
        smt2_path: `${routeRoot}/proof.smt2`,
        smt2_digest: smt2Digest,
        solver_result_path: `${routeRoot}/solver-result.json`,
        solver_result_digest: solverResultDigest,
        source_model_path: `${routeRoot}/source-model.json`,
        source_model_digest: sourceModelArtifactDigest,
        target_model_path: `${routeRoot}/target-model.json`,
        target_model_digest: targetModelArtifactDigest,
        behavior_path: `${routeRoot}/behavior.json`,
        behavior_digest: artifactDigest(behavior),
        chunks_path: `${routeRoot}/chunks.json`,
        chunks_digest: artifactDigest(chunkArtifact),
        composition_path: `${routeRoot}/composition.json`,
        composition_digest: artifactDigest(composition),
      },
      layers: {
        emitted_source_relift: "PASSED",
        emitted_target_relift: "PASSED",
        semantic: semanticEqual ? "PASSED" : "FAILED",
        chunk: chunkEqual ? "PASSED" : "FAILED",
        behavior: behaviorEqual ? "PASSED" : "FAILED",
        smt_solver: solver.outcome,
        framework_native_build: "NOT_RUN",
        framework_native_runtime: "NOT_RUN",
        independent_external_verification: "NOT_RUN",
      },
      status,
      unconditional_proof: false,
      certification: "NOT_CERTIFIED",
      assumptions: proofAssumptions,
    };
    writeArtifact(output, `${routeRoot}/formal-input.json`, formalInput);
    writeArtifact(output, `${routeRoot}/proof.smt2`, smt2);
    writeArtifact(output, `${routeRoot}/solver-result.json`, solverResult);
    writeArtifact(output, `${routeRoot}/source-model.json`, source.relift);
    writeArtifact(output, `${routeRoot}/target-model.json`, target.relift);
    writeArtifact(output, `${routeRoot}/behavior.json`, behavior);
    writeArtifact(output, `${routeRoot}/chunks.json`, chunkArtifact);
    writeArtifact(output, `${routeRoot}/composition.json`, composition);
    writeArtifact(output, `${routeRoot}/layered-result.json`, layered);
    routeRecords.push({
      route_id: route.routeId,
      source_profile: route.source,
      target_profile: route.target,
      source_project_digest: source.project_digest,
      target_project_digest: target.project_digest,
      evidence_path: `${routeRoot}/layered-result.json`,
      formal_input_path: `${routeRoot}/formal-input.json`,
      formal_input_digest: formalInputDigest,
      solver_result_path: `${routeRoot}/solver-result.json`,
      layered_result: status,
      status,
    });
  }
  const counts = Object.fromEntries(["PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"].map(status => [status, routeRecords.filter(route => route.status === status).length]));
  const campaign = {
    schema_version: "1.0",
    kind: "frontend-formal-route-campaign",
    proof_profile: "bounded-navigation-v1",
    corpus_id: "frontend-bounded-navigation-corpus-v1",
    profile_count: profileRecords.length,
    route_count: routeRecords.length,
    profiles: profileRecords,
    source_liftings: profileRecords.map(profile => ({ profile_id: profile.profile_id, project_digest: profile.project_digest, relift_model_digest: profile.relift_model_digest, status: "PASSED" })),
    target_lowerings: profileRecords.map(profile => ({ profile_id: profile.profile_id, project_digest: profile.project_digest, emitted_project: "PASSED", relift: "PASSED" })),
    routes: routeRecords,
    counts,
    semantic_blocks: {
      proved: ["bounded-navigation-v1"],
      externally_composable_not_run: ["component-dialect-engine/certified-component-v1"],
      unsupported_not_proved: unsupportedSemanticBlocks,
    },
    assumptions: proofAssumptions,
    arbitrary_customer_source: "NOT_PROVED",
    unconditional_proof: false,
    native_build_and_runtime: "NOT_RUN",
    independent_external_verification: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
  writeArtifact(output, "frontend-formal-route-campaign.json", campaign);
  return campaign;
}

function filesBelow(root: string): readonly string[] {
  const output: string[] = [];
  const visit = (directory: string): void => {
    for (const name of readdirSync(directory).sort()) {
      const path = join(directory, name);
      const metadata = lstatSync(path);
      if (metadata.isSymbolicLink()) throw new Error(`symbolic links are forbidden in formal artifacts: ${path}`);
      if (metadata.isDirectory()) visit(path);
      else if (metadata.isFile()) output.push(relative(root, path).split(sep).join("/"));
      else throw new Error(`non-regular formal artifact is forbidden: ${path}`);
    }
  };
  visit(root);
  return output;
}

function safeCampaignFile(root: string, relativePath: unknown, name: string): string {
  if (typeof relativePath !== "string" || !relativePath || relativePath.includes("\\") || relativePath.startsWith("/")) {
    throw new Error(`${name} path is unsafe`);
  }
  const segments = relativePath.split("/");
  if (segments.some(segment => !segment || segment === "." || segment === "..")) throw new Error(`${name} path is unsafe`);
  const rootReal = realpathSync(root);
  const candidate = resolve(rootReal, ...segments);
  if (candidate !== rootReal && !candidate.startsWith(`${rootReal}${sep}`)) throw new Error(`${name} path escapes campaign root`);
  const metadata = lstatSync(candidate);
  if (metadata.isSymbolicLink() || !metadata.isFile()) throw new Error(`${name} must be a non-symlink regular file`);
  const actual = realpathSync(candidate);
  if (!actual.startsWith(`${rootReal}${sep}`)) throw new Error(`${name} resolves outside campaign root`);
  return actual;
}

function exactObjectKeys(value: Record<string, unknown>, expected: readonly string[], name: string): void {
  const actual = Object.keys(value).sort(codePointCompare);
  const wanted = [...expected].sort(codePointCompare);
  if (actual.join("|") !== wanted.join("|")) throw new Error(`${name} keys drifted`);
}

export function verifyFrontendFormalCampaign(outputDirectory: string): readonly string[] {
  const output = resolve(outputDirectory);
  const errors: string[] = [];
  try {
    const campaignPath = safeCampaignFile(output, "frontend-formal-route-campaign.json", "campaign");
    const campaign = JSON.parse(readFileSync(campaignPath, "utf8")) as Record<string, unknown>;
    exactObjectKeys(campaign, [
      "schema_version", "kind", "proof_profile", "corpus_id", "profile_count", "route_count", "profiles",
      "source_liftings", "target_lowerings", "routes", "counts", "semantic_blocks", "assumptions",
      "arbitrary_customer_source", "unconditional_proof", "native_build_and_runtime",
      "independent_external_verification", "certification",
    ], "campaign");
    if (campaign.schema_version !== "1.0" || campaign.kind !== "frontend-formal-route-campaign"
      || campaign.proof_profile !== "bounded-navigation-v1" || campaign.corpus_id !== "frontend-bounded-navigation-corpus-v1"
      || campaign.profile_count !== 9 || campaign.route_count !== 72 || campaign.unconditional_proof !== false
      || campaign.certification !== "NOT_CERTIFIED" || campaign.native_build_and_runtime !== "NOT_RUN"
      || campaign.independent_external_verification !== "NOT_RUN" || campaign.arbitrary_customer_source !== "NOT_PROVED"
      || canonical(campaign.assumptions) !== canonical(proofAssumptions)) errors.push("campaign identity or proof boundary drifted");
    const profiles = campaign.profiles;
    const verifiedProfiles = new Map<UiFrameworkId, {
      readonly project_digest: string;
      readonly files: Readonly<Record<string, string>>;
      readonly relift: ReliftedBoundedNavigation;
    }>();
    const seenProfileIds = new Set<UiFrameworkId>();
    if (!Array.isArray(profiles) || profiles.length !== 9) errors.push("campaign must bind nine profiles");
    else for (const raw of profiles) {
      const profile = raw as Record<string, unknown>;
      const id = profile.profile_id as UiFrameworkId;
      try {
        exactObjectKeys(profile, ["profile_id", "framework_version", "platforms", "project_path", "project_digest", "manifest_path", "manifest_digest", "navigation_source_path", "relift_model_digest", "target_build"], `profile ${id}`);
        if (!uiTargetProfiles().some(candidate => candidate.id === id) || seenProfileIds.has(id)) throw new Error("profile identity is unknown or duplicated");
        seenProfileIds.add(id);
        const exactProfile = uiTargetProfile(id);
        if (profile.framework_version !== exactProfile.frameworkVersion || canonical(profile.platforms) !== canonical(exactProfile.platforms)
          || profile.project_path !== `profiles/${id}/project` || profile.manifest_path !== `profiles/${id}/manifest.json`
          || profile.navigation_source_path !== navigationSourceSpec(id).sourcePath || profile.target_build !== "NOT_RUN") {
          throw new Error("exact profile tuple or canonical path drifted");
        }
        const manifestPath = safeCampaignFile(output, profile.manifest_path, `${id}.manifest`);
        const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Record<string, unknown>;
        exactObjectKeys(manifest, ["schema_version", "kind", "profile_id", "framework_version", "platforms", "project_path", "project_digest", "digest_scope", "file_count", "files", "manifest_digest"], `${id}.manifest`);
        const manifestDigest = manifest.manifest_digest;
        const { manifest_digest: _ignored, ...base } = manifest;
        if (frontendFormalDigest(base) !== manifestDigest || manifestDigest !== profile.manifest_digest
          || manifest.schema_version !== "1.0" || manifest.kind !== "frontend-formal-profile-project"
          || manifest.profile_id !== id || manifest.framework_version !== exactProfile.frameworkVersion
          || canonical(manifest.platforms) !== canonical(exactProfile.platforms) || manifest.project_path !== "project"
          || manifest.digest_scope !== "sorted UTF-8 project files keyed by POSIX relative path") throw new Error("manifest identity or digest drifted");
        const projectRoot = join(output, "profiles", id, "project");
        const projectMetadata = lstatSync(projectRoot);
        if (projectMetadata.isSymbolicLink() || !projectMetadata.isDirectory()) throw new Error("project root is not a real directory");
        const diskFiles = Object.fromEntries(filesBelow(projectRoot).map(path => [path, readFileSync(join(projectRoot, ...path.split("/")), "utf8")]));
        const computedProjectDigest = projectDigest(diskFiles);
        if (computedProjectDigest !== profile.project_digest || computedProjectDigest !== manifest.project_digest) throw new Error("project digest drifted");
        const expectedFileRows = Object.entries(diskFiles).sort(([left], [right]) => codePointCompare(left, right)).map(([path, content]) => ({
          path, sha256: bytesDigest(content), byte_count: Buffer.byteLength(content, "utf8"),
        }));
        if (manifest.file_count !== expectedFileRows.length || canonical(manifest.files) !== canonical(expectedFileRows)) throw new Error("manifest file inventory drifted");
        const relift = reliftBoundedNavigationProject(id, diskFiles);
        if (relift.model_digest !== profile.relift_model_digest) throw new Error("profile relift model digest drifted");
        verifiedProfiles.set(id, { project_digest: computedProjectDigest, files: diskFiles, relift });
      } catch (error) { errors.push(`${id}: ${error instanceof Error ? error.message : String(error)}`); }
    }
    const exactIds = new Set(uiTargetProfiles().map(profile => profile.id));
    if (seenProfileIds.size !== exactIds.size || [...exactIds].some(id => !seenProfileIds.has(id))) errors.push("campaign profile closure is incomplete");
    const routes = campaign.routes;
    const seenRouteIds = new Set<string>();
    const seenPairs = new Set<string>();
    const solverReplayCache = new Map<string, FrontendSolverResult>();
    if (!Array.isArray(routes) || routes.length !== 72) errors.push("campaign must bind 72 directed routes");
    else for (const raw of routes) {
      const route = raw as Record<string, unknown>;
      const routeId = String(route.route_id);
      try {
        exactObjectKeys(route, ["route_id", "source_profile", "target_profile", "source_project_digest", "target_project_digest", "evidence_path", "formal_input_path", "formal_input_digest", "solver_result_path", "layered_result", "status"], `route ${routeId}`);
        const sourceId = route.source_profile as UiFrameworkId;
        const targetId = route.target_profile as UiFrameworkId;
        const pair = `${sourceId}--to--${targetId}`;
        if (routeId !== pair || sourceId === targetId || seenRouteIds.has(routeId) || seenPairs.has(pair)) throw new Error("route identity is invalid or duplicated");
        seenRouteIds.add(routeId); seenPairs.add(pair);
        const source = verifiedProfiles.get(sourceId); const target = verifiedProfiles.get(targetId);
        if (!source || !target || route.source_project_digest !== source.project_digest || route.target_project_digest !== target.project_digest) throw new Error("route project binding drifted");
        const routeRoot = `routes/${routeId}`;
        if (route.evidence_path !== `${routeRoot}/layered-result.json` || route.formal_input_path !== `${routeRoot}/formal-input.json`
          || route.solver_result_path !== `${routeRoot}/solver-result.json`) throw new Error("route artifact path is non-canonical");
        const formalPath = safeCampaignFile(output, route.formal_input_path, `${routeId}.formal-input`);
        const formalBytes = readFileSync(formalPath, "utf8");
        const formal = JSON.parse(formalBytes) as Record<string, unknown>;
        exactObjectKeys(formal, ["schema_version", "kind", "corpus_id", "proof_profile", "proof_scope", "route_id", "tuple", "source_project_digest", "target_project_digest", "canonical_model", "canonical_model_digest", "source_model_digest", "target_model_digest", "source_model_artifact_digest", "target_model_artifact_digest", "semantic_equal", "behavior_digest", "behavior_equal", "chunk_digest", "chunk_equal", "assumptions", "semantic_blocks", "arbitrary_customer_source", "compiler_framework_runtime_soundness"], `${routeId}.formal-input`);
        if (bytesDigest(formalBytes) !== route.formal_input_digest || artifactBytes(formal) !== formalBytes) throw new Error("formal input bytes or digest drifted");
        const layeredPath = safeCampaignFile(output, route.evidence_path, `${routeId}.layered-result`);
        const layeredBytes = readFileSync(layeredPath, "utf8");
        const layered = JSON.parse(layeredBytes) as Record<string, unknown>;
        exactObjectKeys(layered, ["schema_version", "kind", "route_id", "proof_profile", "links", "layers", "status", "unconditional_proof", "certification", "assumptions"], `${routeId}.layered-result`);
        if (artifactBytes(layered) !== layeredBytes || layered.status !== route.status || route.layered_result !== route.status
          || layered.unconditional_proof !== false || layered.certification !== "NOT_CERTIFIED"
          || canonical(layered.assumptions) !== canonical(proofAssumptions)) throw new Error("layered result drifted");
        const links = layered.links as Record<string, unknown>;
        if (!links || typeof links !== "object") throw new Error("layered links are missing");
        exactObjectKeys(links, ["formal_input_path", "formal_input_digest", "smt2_path", "smt2_digest", "solver_result_path", "solver_result_digest", "source_model_path", "source_model_digest", "target_model_path", "target_model_digest", "behavior_path", "behavior_digest", "chunks_path", "chunks_digest", "composition_path", "composition_digest"], `${routeId}.layered-links`);
        const expectedPaths = {
          formal_input_path: `${routeRoot}/formal-input.json`, smt2_path: `${routeRoot}/proof.smt2`,
          solver_result_path: `${routeRoot}/solver-result.json`, source_model_path: `${routeRoot}/source-model.json`,
          target_model_path: `${routeRoot}/target-model.json`, behavior_path: `${routeRoot}/behavior.json`,
          chunks_path: `${routeRoot}/chunks.json`, composition_path: `${routeRoot}/composition.json`,
        } as const;
        for (const [key, value] of Object.entries(expectedPaths)) if (links[key] !== value) throw new Error(`${key} is non-canonical`);
        if (links.formal_input_digest !== route.formal_input_digest) throw new Error("layered formal digest drifted");
        const readLinkedJson = (pathKey: keyof typeof expectedPaths, digestKey: string): { bytes: string; value: Record<string, unknown> } => {
          const path = safeCampaignFile(output, links[pathKey], `${routeId}.${pathKey}`);
          const bytes = readFileSync(path, "utf8");
          const value = JSON.parse(bytes) as Record<string, unknown>;
          if (artifactBytes(value) !== bytes || bytesDigest(bytes) !== links[digestKey]) throw new Error(`${digestKey} bytes drifted`);
          return { bytes, value };
        };
        const sourceModelArtifact = readLinkedJson("source_model_path", "source_model_digest");
        const targetModelArtifact = readLinkedJson("target_model_path", "target_model_digest");
        const behaviorArtifact = readLinkedJson("behavior_path", "behavior_digest");
        const chunkArtifact = readLinkedJson("chunks_path", "chunks_digest");
        const compositionArtifact = readLinkedJson("composition_path", "composition_digest");
        const solverArtifact = readLinkedJson("solver_result_path", "solver_result_digest");
        if (canonical(sourceModelArtifact.value) !== canonical(source.relift) || canonical(targetModelArtifact.value) !== canonical(target.relift)) throw new Error("source/target re-lift artifact drifted");
        const canonicalModel = validateBoundedModel(formal.canonical_model);
        const canonicalDigest = frontendFormalDigest(canonicalModel);
        const semanticEqual = canonical(canonicalModel) === canonical(source.relift.model) && canonical(canonicalModel) === canonical(target.relift.model);
        if (formal.schema_version !== "1.0" || formal.kind !== "frontend-bounded-navigation-formal-input"
          || formal.proof_profile !== "bounded-navigation-v1" || formal.route_id !== routeId
          || formal.source_project_digest !== source.project_digest || formal.target_project_digest !== target.project_digest
          || formal.canonical_model_digest !== canonicalDigest || formal.source_model_digest !== source.relift.model_digest
          || formal.target_model_digest !== target.relift.model_digest || formal.source_model_artifact_digest !== links.source_model_digest
          || formal.target_model_artifact_digest !== links.target_model_digest || formal.semantic_equal !== semanticEqual
          || formal.arbitrary_customer_source !== "NOT_PROVED" || formal.compiler_framework_runtime_soundness !== "ASSUMED_NOT_PROVED"
          || canonical(formal.assumptions) !== canonical(proofAssumptions)) throw new Error("formal semantic/model binding drifted");
        const tuple = formal.tuple as Record<string, unknown>;
        if (!tuple || tuple.source_profile !== sourceId || tuple.target_profile !== targetId
          || tuple.source_framework_version !== uiTargetProfile(sourceId).frameworkVersion
          || tuple.target_framework_version !== uiTargetProfile(targetId).frameworkVersion) throw new Error("formal exact tuple drifted");
        const canonicalBehavior = observeBoundedNavigationModel(canonicalModel, "canonical");
        const independentBehavior = independentObserve(canonicalModel);
        const sourceBehavior = observeBoundedNavigationModel(source.relift.model, "source");
        const targetBehavior = observeBoundedNavigationModel(target.relift.model, "target");
        const behaviorEqual = canonical(behaviorComparable(canonicalBehavior)) === canonical(behaviorComparable(independentBehavior))
          && canonical(behaviorComparable(canonicalBehavior)) === canonical(behaviorComparable(sourceBehavior))
          && canonical(behaviorComparable(canonicalBehavior)) === canonical(behaviorComparable(targetBehavior));
        const expectedBehavior = {
          schema_version: "1.0",
          domain: { id: "bounded-navigation-domain-v1", operations: ["INITIAL_RENDER", "SELECT_DECLARED_PATH", "SELECT_UNKNOWN_PATH"], unknown_path_policy: "FIRST_DECLARED_ROUTE", framework_native_runtime: "NOT_RUN" },
          canonical: { runtime_kind: "SPEC_INTERPRETER", observations: canonicalBehavior },
          independent: { runtime_kind: "BOUNDED_REFERENCE_INTERPRETER", observations: independentBehavior },
          source: { runtime_kind: "RELIFTED_EMITTED_SOURCE_INTERPRETER", observations: sourceBehavior },
          target: { runtime_kind: "RELIFTED_EMITTED_TARGET_INTERPRETER", observations: targetBehavior },
          equivalent: behaviorEqual, native_browser_or_device_evidence: "NOT_RUN",
        };
        if (canonical(behaviorArtifact.value) !== canonical(expectedBehavior) || formal.behavior_digest !== links.behavior_digest
          || formal.behavior_equal !== behaviorEqual) throw new Error("behavior evidence drifted");
        const expectedChunkRows = routeChunks(source.relift, target.relift);
        const chunkEqual = expectedChunkRows.every(chunk => chunk.equivalent === true);
        const expectedChunks = { schema_version: "1.0", route_id: routeId, chunks: expectedChunkRows, equivalent: chunkEqual };
        if (canonical(chunkArtifact.value) !== canonical(expectedChunks) || formal.chunk_digest !== links.chunks_digest
          || formal.chunk_equal !== chunkEqual) throw new Error("chunk mapping/span/hash evidence drifted");
        const smtPath = safeCampaignFile(output, links.smt2_path, `${routeId}.smt2`);
        const smt2 = readFileSync(smtPath, "utf8");
        const expectedSmt2 = buildFrontendSmt2(canonicalModel, source.relift.model, target.relift.model, canonicalBehavior, independentBehavior, sourceBehavior, targetBehavior, String(route.formal_input_digest));
        if (smt2 !== expectedSmt2 || bytesDigest(smt2) !== links.smt2_digest) throw new Error("SMT2 bytes or symbolic encoding drifted");
        const solver = solverArtifact.value;
        exactObjectKeys(solver, ["schema_version", "solver", "solver_binary_realpath", "solver_binary_sha256", "solver_version", "identity_status", "invocation", "options", "environment", "exit_code", "stdout", "stderr", "outcome", "proof_status", "unconditional_proof", "route_id", "formal_input_digest", "solver_input_digest", "smt2_digest"], `${routeId}.solver-result`);
        const solverOutcome = solver.outcome;
        const proofStatus = solverOutcome === "UNSAT" ? "PROVED_UNDER_ASSUMPTIONS" : solverOutcome === "SAT" ? "REFUTED" : "NOT_PROVED";
        const expectedStatus: FrontendFormalStatus = !semanticEqual || !behaviorEqual || !chunkEqual ? "REFUTED" : proofStatus;
        if (route.status !== expectedStatus || solver.schema_version !== "1.0" || solver.route_id !== routeId
          || solver.proof_status !== proofStatus || solver.unconditional_proof !== false
          || solver.formal_input_digest !== route.formal_input_digest || solver.solver_input_digest !== links.smt2_digest
          || solver.smt2_digest !== links.smt2_digest) throw new Error("solver result/status linkage drifted");
        if (solver.identity_status === "VERIFIED") {
          const binaryPath = String(solver.solver_binary_realpath);
          if (solver.solver !== binaryPath || basename(binaryPath) !== "z3" || realpathSync(binaryPath) !== binaryPath
            || solver.solver_version !== lockedZ3Version || !lockedZ3BinaryDigests.has(String(solver.solver_binary_sha256))
            || solver.solver_binary_sha256 !== bytesDigest(readFileSync(binaryPath))
            || canonical(solver.invocation) !== canonical([binaryPath, "-in"]) || solver.exit_code !== 0
            || solver.stderr !== "" || !["unsat\n", "sat\n", "unknown\n"].includes(String(solver.stdout))) throw new Error("locked solver identity/execution drifted");
          const options = solver.options as Record<string, unknown>;
          if (!options || canonical(options.args) !== canonical(["-in"]) || typeof options.timeout_ms !== "number") throw new Error("solver options drifted");
          const environment = solver.environment as Record<string, unknown>;
          if (!environment || environment.platform !== process.platform || environment.arch !== process.arch || environment.node_version !== process.version) throw new Error("solver environment drifted");
          const replayKey = smt2.replace(/^; formal-input-bytes-digest: .*$/m, "; formal-input-bytes-digest: <bound-separately>");
          const replay = solverReplayCache.get(replayKey)
            ?? runFrontendSolver(smt2, { command: binaryPath, timeout_ms: options.timeout_ms as number });
          solverReplayCache.set(replayKey, replay);
          if (replay.identity_status !== "VERIFIED" || replay.outcome !== solverOutcome || replay.stdout !== solver.stdout
            || replay.exit_code !== solver.exit_code || replay.solver_binary_sha256 !== solver.solver_binary_sha256) throw new Error("solver replay diverged");
        } else if (route.status !== "NOT_PROVED" || solver.stdout !== "" || solver.exit_code !== null) throw new Error("unverified solver identity cannot support a proof result");
        const expectedComposition = {
          schema_version: "1.0", route_id: routeId,
          source_lifting: { profile_id: sourceId, project_digest: source.project_digest, model_digest: source.relift.model_digest },
          target_lowering_relift: { profile_id: targetId, project_digest: target.project_digest, model_digest: target.relift.model_digest },
          canonical_model_digest: canonicalDigest, semantic_equal: semanticEqual, chunk_equal: chunkEqual,
          behavior_equal: behaviorEqual, solver_outcome: solverOutcome, status: expectedStatus,
        };
        if (canonical(compositionArtifact.value) !== canonical(expectedComposition)) throw new Error("composition evidence drifted");
        const layers = layered.layers as Record<string, unknown>;
        if (layers) exactObjectKeys(layers, ["emitted_source_relift", "emitted_target_relift", "semantic", "chunk", "behavior", "smt_solver", "framework_native_build", "framework_native_runtime", "independent_external_verification"], `${routeId}.layers`);
        if (!layers || layers.emitted_source_relift !== "PASSED" || layers.emitted_target_relift !== "PASSED"
          || layers.semantic !== (semanticEqual ? "PASSED" : "FAILED") || layers.chunk !== (chunkEqual ? "PASSED" : "FAILED")
          || layers.behavior !== (behaviorEqual ? "PASSED" : "FAILED") || layers.smt_solver !== solverOutcome
          || layers.framework_native_build !== "NOT_RUN" || layers.framework_native_runtime !== "NOT_RUN"
          || layers.independent_external_verification !== "NOT_RUN") throw new Error("layered status evidence drifted");
      } catch (error) { errors.push(`${routeId}: ${error instanceof Error ? error.message : String(error)}`); }
    }
    const expectedPairs = new Set(uiConversionRoutes().map(route => route.routeId));
    if (seenRouteIds.size !== expectedPairs.size || [...expectedPairs].some(routeId => !seenRouteIds.has(routeId))) errors.push("campaign directed route closure is incomplete");
    const expectedSourceLiftings = [...verifiedProfiles.entries()].sort(([left], [right]) => codePointCompare(left, right)).map(([profile_id, profile]) => ({ profile_id, project_digest: profile.project_digest, relift_model_digest: profile.relift.model_digest, status: "PASSED" }));
    const expectedTargetLowerings = expectedSourceLiftings.map(({ profile_id, project_digest }) => ({ profile_id, project_digest, emitted_project: "PASSED", relift: "PASSED" }));
    if (canonical(campaign.source_liftings) !== canonical(expectedSourceLiftings) || canonical(campaign.target_lowerings) !== canonical(expectedTargetLowerings)) errors.push("campaign lifting/lowering closure drifted");
    if (Array.isArray(routes)) {
      const expectedCounts = Object.fromEntries(["PROVED_UNDER_ASSUMPTIONS", "REFUTED", "NOT_PROVED"].map(status => [status, routes.filter(route => (route as Record<string, unknown>).status === status).length]));
      if (canonical(campaign.counts) !== canonical(expectedCounts)) errors.push("campaign proof counts drifted");
    }
  } catch (error) { errors.push(error instanceof Error ? error.message : String(error)); }
  return errors;
}

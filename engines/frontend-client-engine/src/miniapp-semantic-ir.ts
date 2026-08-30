import { createHash } from "node:crypto";

import { compileTemplate, parse as parseVueSfc } from "@vue/compiler-sfc";
import ts from "typescript";

import type {
  MiniappConversionRequest,
  MiniappSourceInventory,
  MiniappSourceLabel,
} from "./miniapp-types.js";

export type MiniappCompatibilityClass = "A" | "B" | "C" | "D" | "E";

export interface MiniappSourceRef {
  readonly path: string;
  readonly sha256: string;
  readonly startLine: number;
  readonly startColumn: number;
  readonly endLine: number;
  readonly endColumn: number;
}

export interface MiniappSourceFinding {
  readonly code: string;
  readonly severity: "info" | "warning" | "error" | "critical";
  readonly message: string;
  readonly classification: MiniappCompatibilityClass;
  readonly blocking: boolean;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappAnalyzedComponent {
  readonly id: string;
  readonly name: string;
  readonly semanticRole: string;
  readonly sourceKind: "ast" | "template-ast" | "dart-token-model" | "native-template";
  readonly props: readonly string[];
  readonly events: readonly string[];
  readonly children: readonly string[];
  readonly accessibility: readonly string[];
  readonly sourceTag: string;
  readonly attributes: Readonly<Record<string, string>>;
  readonly textContent: string;
  readonly eventBindings: readonly MiniappEventBinding[];
  readonly modelBinding: string | null;
  readonly collectionBinding: MiniappCollectionBinding | null;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappEventBinding {
  readonly event: string;
  readonly handler: string;
  readonly modifiers: readonly string[];
}

export interface MiniappCollectionBinding {
  readonly collection: string;
  readonly itemAlias: string;
  readonly indexAlias: string | null;
  readonly keyExpression: string | null;
  readonly valueExpression: string;
}

export interface MiniappAnalyzedInteraction {
  readonly id: string;
  readonly kind: "trimmed-text-append-list";
  readonly draftState: string;
  readonly draftStateId: string;
  readonly collectionState: string;
  readonly collectionStateId: string;
  readonly inputComponentId: string;
  readonly submitComponentId: string;
  readonly listComponentId: string;
  readonly submitHandler: string;
  readonly submitActionId: string;
  readonly delegatedActionId: string;
  readonly ignoreBlank: true;
  readonly clearAfterSubmit: true;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappAnalyzedRoute {
  readonly id: string;
  readonly path: string;
  /** A static Vue Router name is preserved as source metadata for downstream evidence. */
  readonly name?: string;
  readonly component: string;
  readonly componentModule?: string | null;
  readonly parameters: readonly string[];
  readonly guards: readonly string[];
  readonly sourceRefs: readonly MiniappSourceRef[];
  /** The exact router instance that owns this route declaration, when bound. */
  readonly ownerInstanceId?: string;
}

export interface MiniappAnalyzedState {
  readonly id: string;
  readonly name: string;
  readonly scope: "component" | "page" | "application" | "persistent";
  readonly stateType: "scalar" | "collection" | "object" | "unknown";
  readonly reads: number;
  readonly writes: number;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappAnalyzedEffect {
  readonly id: string;
  readonly name: string;
  readonly trigger: string;
  readonly instanceId?: string;
  readonly relatedInstanceId?: string;
  readonly asynchronous: boolean;
  readonly cleanup: "present" | "absent" | "not-applicable" | "unknown";
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappAnalyzedForm {
  readonly id: string;
  readonly name: string;
  readonly fields: readonly string[];
  readonly binding: string;
  readonly validation: "declared" | "implicit" | "unknown";
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappAnalyzedStyle {
  readonly id: string;
  readonly selector: string;
  readonly declarations: Readonly<Record<string, string>>;
  readonly responsive: boolean;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappAnalyzedCapability {
  readonly id: string;
  readonly name: string;
  readonly category: string;
  readonly sensitive: boolean;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

export interface MiniappSourceAnalysis {
  readonly schemaVersion: "1.0";
  readonly analysisId: string;
  readonly sourceLabel: MiniappSourceLabel;
  readonly frameworkVersion: string;
  readonly parser: string;
  readonly parserEvidence: readonly string[];
  readonly components: readonly MiniappAnalyzedComponent[];
  readonly routes: readonly MiniappAnalyzedRoute[];
  readonly states: readonly MiniappAnalyzedState[];
  readonly effects: readonly MiniappAnalyzedEffect[];
  readonly forms: readonly MiniappAnalyzedForm[];
  readonly styles: readonly MiniappAnalyzedStyle[];
  readonly capabilities: readonly MiniappAnalyzedCapability[];
  readonly interactions: readonly MiniappAnalyzedInteraction[];
  readonly dependencies: readonly string[];
  readonly dependencyUsage: Readonly<Record<string, readonly MiniappSourceRef[]>>;
  readonly findings: readonly MiniappSourceFinding[];
  readonly parsedFiles: readonly string[];
  readonly failedFiles: readonly string[];
  readonly coverage: number;
  readonly deterministicDigest: string;
}

export interface MiniappUiIrNode {
  readonly id: string;
  readonly kind:
    | "component"
    | "route"
    | "state"
    | "effect"
    | "form"
    | "style"
    | "capability"
    | "interaction";
  readonly name: string;
  readonly semanticRole: string;
  readonly references: readonly string[];
  readonly sourceRefs: readonly MiniappSourceRef[];
  readonly obligations: readonly string[];
}

export interface MiniappSemanticIr {
  readonly schemaVersion: "2.0";
  readonly profile: "miniapp-ui-interaction-v1";
  readonly source: {
    readonly label: MiniappSourceLabel;
    readonly frameworkVersion: string;
    readonly snapshotDigest: string;
    readonly revision: string;
    readonly parser: string;
  };
  readonly application: {
    readonly id: string;
    readonly title: string;
    readonly routeIds: readonly string[];
    readonly componentIds: readonly string[];
    readonly defaultLocale: string;
    readonly theme: string;
  };
  readonly nodes: readonly MiniappUiIrNode[];
  readonly routes: readonly MiniappAnalyzedRoute[];
  readonly components: readonly MiniappAnalyzedComponent[];
  readonly states: readonly MiniappAnalyzedState[];
  readonly effects: readonly MiniappAnalyzedEffect[];
  readonly forms: readonly MiniappAnalyzedForm[];
  readonly styles: readonly MiniappAnalyzedStyle[];
  readonly capabilities: readonly MiniappAnalyzedCapability[];
  readonly interactions: readonly MiniappAnalyzedInteraction[];
  readonly dependencies: readonly string[];
  readonly dependencyUsage: Readonly<Record<string, readonly MiniappSourceRef[]>>;
  readonly unknowns: readonly MiniappSourceFinding[];
  readonly traceIndex: Readonly<Record<string, readonly MiniappSourceRef[]>>;
  readonly coverage: {
    readonly parsedSource: number;
    readonly tracedNodes: number;
    readonly unresolvedCritical: number;
  };
  readonly deterministicDigest: string;
}

type SourceFiles = Readonly<Record<string, string>>;

const sourceBuildConfigPaths = new Set([
  "vite.config.ts", "vite.config.js", "vite.config.mts", "vite.config.mjs",
  "webpack.config.ts", "webpack.config.js", "rollup.config.ts", "rollup.config.js",
]);

type FrameworkFactoryKind = "vue-app" | "pinia" | "router" | "router-history-web" | "router-history-hash" | "router-history-memory";
type FrameworkBinding = { readonly kind: FrameworkFactoryKind; readonly instanceId: string };

interface MutableAnalysis {
  components: MiniappAnalyzedComponent[];
  routes: MiniappAnalyzedRoute[];
  states: MiniappAnalyzedState[];
  effects: MiniappAnalyzedEffect[];
  forms: MiniappAnalyzedForm[];
  styles: MiniappAnalyzedStyle[];
  capabilities: MiniappAnalyzedCapability[];
  actionFacts: ActionFact[];
  stateInitialValues: Map<string, string>;
  dependencies: Set<string>;
  dependencyUsage: Map<string, MiniappSourceRef[]>;
  findings: MiniappSourceFinding[];
  parsedFiles: Set<string>;
  failedFiles: Set<string>;
  parserEvidence: Set<string>;
  nativeConfigFiles: Map<string, string>;
  nativeConfigInvalid: Set<string>;
  frameworkExports: Map<string, FrameworkBinding>;
}

interface MarkupTag {
  readonly name: string;
  readonly attributes: Readonly<Record<string, string>>;
  readonly line: number;
  readonly column: number;
  readonly textContent: string;
  readonly mixedContent: boolean;
  readonly parentIndex: number | null;
}

interface ActionFact {
  readonly id: string;
  readonly name: string;
  readonly parameters: readonly string[];
  readonly calls: readonly { readonly receiver: string; readonly method: string; readonly arguments: readonly string[]; readonly receiverModule: string | null }[];
  readonly assignments: readonly { readonly target: string; readonly value: string }[];
  readonly trims: readonly { readonly target: string; readonly source: string }[];
  readonly appends: readonly { readonly target: string; readonly value: string; readonly guardExpression: string | null }[];
  readonly exactTodoSubmit: {
    readonly receiver: string;
    readonly receiverModule: string | null;
    readonly method: string;
    readonly argument: string;
    readonly clearTarget: string;
  } | null;
  readonly exactTodoAppend: {
    readonly parameter: string;
    readonly trimmedLocal: string;
    readonly collectionTarget: string;
  } | null;
  readonly sourceRefs: readonly MiniappSourceRef[];
}

interface DartToken {
  readonly value: string;
  readonly line: number;
  readonly column: number;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Readonly<Record<string, unknown>>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right, "en-US"))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value)).digest("hex")}`;
}

function stableId(kind: string, path: string, name: string): string {
  return `${kind}.${createHash("sha256").update(`${kind}\u0000${path}\u0000${name}`).digest("hex").slice(0, 20)}`;
}

function textDigest(value: string): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function positionRef(path: string, source: string, start: number, end: number): MiniappSourceRef {
  const sourceFile = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const startPoint = sourceFile.getLineAndCharacterOfPosition(Math.max(0, Math.min(start, source.length)));
  const endPoint = sourceFile.getLineAndCharacterOfPosition(Math.max(0, Math.min(end, source.length)));
  return {
    path,
    sha256: textDigest(source),
    startLine: startPoint.line + 1,
    startColumn: startPoint.character + 1,
    endLine: endPoint.line + 1,
    endColumn: endPoint.character + 1,
  };
}

function lineRef(path: string, source: string, line: number, column = 1): MiniappSourceRef {
  const lines = source.split("\n");
  const safeLine = Math.max(1, Math.min(line, lines.length));
  const lineText = lines[safeLine - 1] ?? "";
  return {
    path,
    sha256: textDigest(source),
    startLine: safeLine,
    startColumn: Math.max(1, column),
    endLine: safeLine,
    endColumn: Math.max(1, lineText.length + 1),
  };
}

function finding(
  code: string,
  message: string,
  classification: MiniappCompatibilityClass,
  refs: readonly MiniappSourceRef[],
  severity: MiniappSourceFinding["severity"] = "warning",
  blocking = classification === "D" || classification === "E",
): MiniappSourceFinding {
  return { code, severity, message, classification, blocking, sourceRefs: refs };
}

function scriptKind(path: string): ts.ScriptKind {
  if (path.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (path.endsWith(".jsx")) return ts.ScriptKind.JSX;
  if (path.endsWith(".js")) return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

function propertyName(node: ts.PropertyName | undefined): string | undefined {
  if (!node) return undefined;
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text;
  return undefined;
}

function literalText(node: ts.Expression | undefined): string | undefined {
  if (!node) return undefined;
  if (ts.isStringLiteralLike(node) || ts.isNumericLiteral(node)) return node.text;
  return undefined;
}

const sourceSecretReference = /^(?:vault|secret|kms):\/\/[A-Za-z0-9][A-Za-z0-9._/@:-]{0,511}$/u;
const implicitHtmlSemanticTags = new Set([
  "article", "aside", "footer", "header", "h1", "h2", "h3", "h4", "h5", "h6",
  "label", "li", "main", "nav", "ol", "section", "ul",
]);

function sensitiveSourceKey(key: string): boolean {
  const normalized = key.normalize("NFKC").replace(/[^A-Za-z0-9]/gu, "").toLowerCase();
  return /(?:secret|token|password|passwd|credential|credentials|privatekey|apikey|accesskey|accesskeyid|authorization|cookie|session|sessionid|sessionkey)(?:value|material)?$/u.test(normalized);
}

function exactSecretReferenceInitializer(node: ts.Expression | undefined): boolean {
  return node !== undefined && ts.isStringLiteralLike(node) && sourceSecretReference.test(node.text);
}

function sensitiveAssignmentKey(node: ts.Expression): string | undefined {
  if (ts.isIdentifier(node)) return sensitiveSourceKey(node.text) ? node.text : undefined;
  if (ts.isPropertyAccessExpression(node)) {
    return sensitiveSourceKey(node.name.text) ? node.name.text : undefined;
  }
  if (ts.isElementAccessExpression(node) && node.argumentExpression && ts.isStringLiteralLike(node.argumentExpression)) {
    return sensitiveSourceKey(node.argumentExpression.text) ? node.argumentExpression.text : undefined;
  }
  return undefined;
}

function normalizeBindingExpression(value: string): string {
  const trimmed = value.trim();
  return trimmed.startsWith("{{") && trimmed.endsWith("}}") ? trimmed.slice(2, -2).trim() : trimmed;
}

function exactCollectionItemInterpolation(value: string, itemAlias: string): string {
  const match = /^\{\{\s*([A-Za-z_$][\w$]*)\s*\}\}$/u.exec(value.trim());
  return match?.[1] === itemAlias ? itemAlias : "";
}

function eventBindingsFromAttributes(attributes: Readonly<Record<string, string>>): readonly MiniappEventBinding[] {
  return Object.entries(attributes).flatMap(([name, rawHandler]) => {
    const vue = /^(?:@|v-on:)([A-Za-z][A-Za-z0-9-]*)(?:\.(.+))?$/u.exec(name);
    const react = /^on([A-Z][A-Za-z0-9]*)$/u.exec(name);
    const native = /^(bind|catch|on)([A-Za-z][A-Za-z0-9-]*)$/u.exec(name);
    if (!vue && !react && !native) return [];
    const event = vue?.[1]
      ?? react?.[1]?.replace(/^[A-Z]/u, value => value.toLowerCase())
      ?? native?.[2]?.toLowerCase()
      ?? "unknown";
    const modifiers = vue?.[2]?.split(".").filter(Boolean)
      ?? (native?.[1] === "catch" ? ["stop"] : []);
    return [{ event, handler: normalizeBindingExpression(rawHandler), modifiers }];
  }).sort((left, right) => `${left.event}:${left.handler}`.localeCompare(`${right.event}:${right.handler}`, "en-US"));
}

function collectionBindingFromAttributes(
  attributes: Readonly<Record<string, string>>,
  textContent: string,
): MiniappCollectionBinding | null {
  const vueFor = attributes["v-for"];
  if (vueFor) {
    const match = /^\s*(?:\(\s*([A-Za-z_$][\w$]*)\s*(?:,\s*([A-Za-z_$][\w$]*))?\s*\)|([A-Za-z_$][\w$]*))\s+(?:in|of)\s+(.+?)\s*$/u.exec(vueFor);
    if (!match) return null;
    const itemAlias = match[1] ?? match[3] ?? "item";
    return {
      collection: normalizeBindingExpression(match[4] ?? ""),
      itemAlias,
      indexAlias: match[2] ?? null,
      keyExpression: attributes[":key"] ?? attributes["v-bind:key"] ?? null,
      valueExpression: exactCollectionItemInterpolation(textContent, itemAlias),
    };
  }
  const directive = Object.entries(attributes).find(([name]) => /^(?:wx|a|tt|xhs):for$/u.test(name));
  if (!directive) return null;
  const namespace = directive[0].split(":", 1)[0] ?? "wx";
  const itemAlias = attributes[`${namespace}:for-item`] || "item";
  return {
    collection: normalizeBindingExpression(directive[1]),
    itemAlias,
    indexAlias: attributes[`${namespace}:for-index`] || "index",
    keyExpression: attributes[`${namespace}:key`] ?? null,
    valueExpression: exactCollectionItemInterpolation(textContent, itemAlias),
  };
}

function analyzedComponentBindings(
  sourceTag: string,
  attributes: Readonly<Record<string, string>>,
  textContent = "",
): Pick<MiniappAnalyzedComponent, "sourceTag" | "attributes" | "textContent" | "eventBindings" | "modelBinding" | "collectionBinding"> {
  const orderedAttributes = Object.fromEntries(Object.entries(attributes).sort(([left], [right]) => left.localeCompare(right, "en-US")));
  return {
    sourceTag,
    attributes: orderedAttributes,
    textContent: textContent.trim(),
    eventBindings: eventBindingsFromAttributes(orderedAttributes),
    modelBinding: orderedAttributes["v-model"]
      ?? orderedAttributes["v-model.trim"]
      ?? null,
    collectionBinding: collectionBindingFromAttributes(orderedAttributes, textContent),
  };
}

function addCapability(
  state: MutableAnalysis,
  path: string,
  source: string,
  name: string,
  category: string,
  node: ts.Node,
  sensitive = false,
  sourceRefOverride?: MiniappSourceRef,
): void {
  const key = sourceRefOverride
    ? `${name}:${path}:${sourceRefOverride.startLine}:${sourceRefOverride.startColumn}`
    : `${name}:${path}:${node.getStart()}`;
  if (state.capabilities.some(item => item.id === stableId("capability", path, key))) return;
  state.capabilities.push({
    id: stableId("capability", path, key),
    name,
    category,
    sensitive,
    sourceRefs: [sourceRefOverride ?? positionRef(path, source, node.getStart(), node.getEnd())],
  });
}

interface TypeScriptTraceContext {
  readonly source: string;
  readonly offset: number;
  readonly scriptKind: ts.ScriptKind;
  readonly recordParsedFile: boolean;
}

function analyzeTypeScript(
  path: string,
  source: string,
  state: MutableAnalysis,
  trace?: TypeScriptTraceContext,
): void {
  const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, trace?.scriptKind ?? scriptKind(path));
  const traceSource = trace?.source ?? source;
  const traceOffset = trace?.offset ?? 0;
  const sourceRef = (start: number, end: number): MiniappSourceRef =>
    positionRef(path, traceSource, traceOffset + start, traceOffset + end);
  const nodeRef = (node: ts.Node): MiniappSourceRef => sourceRef(node.getStart(), node.getEnd());
  const absoluteStart = (node: ts.Node): number => traceOffset + node.getStart();
  const diagnostics = (file as ts.SourceFile & { readonly parseDiagnostics?: readonly ts.Diagnostic[] }).parseDiagnostics ?? [];
  if (diagnostics.length > 0) {
    state.failedFiles.add(path);
    state.findings.push(finding(
      "MINIAPP_SOURCE_PARSE_FAILED",
      `TypeScript compiler reported ${diagnostics.length} parse diagnostic(s).`,
      "D",
      [sourceRef(0, Math.min(source.length, 1))],
      "error",
      true,
    ));
    return;
  }
  if (trace?.recordParsedFile !== false) state.parsedFiles.add(path);
  state.parserEvidence.add("typescript-compiler-api");

  const unwrapExpression = (expression: ts.Expression): ts.Expression => {
    let current = expression;
    while (ts.isParenthesizedExpression(current) || ts.isAsExpression(current) || ts.isTypeAssertionExpression(current)) {
      current = current.expression;
    }
    return current;
  };

  const imports = new Map<string, { readonly module: string; readonly imported: string }>();
  const storeInstances = new Map<string, string>();
  const routeOwnerInstances = new Map<ts.ObjectLiteralExpression, string>();
  const frameworkBindings = new Map<string, FrameworkBinding>();
  const frameworkBindingsByDeclaration = new Map<ts.VariableDeclaration, FrameworkBinding>();
  const invalidFrameworkBindings = new Set<string>();
  const shadowedNamesByFunction = new Map<ts.Node, Set<string>>();
  const collectImportsAndShadows = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const module = node.moduleSpecifier.text;
      const clause = node.importClause;
      if (clause?.name) imports.set(clause.name.text, { module, imported: "default" });
      if (clause?.namedBindings && ts.isNamespaceImport(clause.namedBindings)) {
        imports.set(clause.namedBindings.name.text, { module, imported: "*" });
      }
      for (const item of clause?.namedBindings && ts.isNamedImports(clause.namedBindings) ? clause.namedBindings.elements : []) {
        imports.set(item.name.text, { module, imported: item.propertyName?.text ?? item.name.text });
      }
    }
    if (ts.isFunctionLike(node)) {
      const names = new Set<string>(node.parameters.flatMap(parameter => {
        const name = parameter.name;
        return ts.isIdentifier(name) ? [name.text] : [];
      }));
      const collectLocal = (child: ts.Node): void => {
        if (child !== node && ts.isFunctionLike(child)) return;
        if (ts.isVariableDeclaration(child) && ts.isIdentifier(child.name)) names.add(child.name.text);
        if ((ts.isFunctionDeclaration(child) || ts.isClassDeclaration(child)) && child.name) names.add(child.name.text);
        ts.forEachChild(child, collectLocal);
      };
      const body = (node as ts.FunctionLikeDeclaration).body;
      collectLocal(body ?? node);
      shadowedNamesByFunction.set(node, names);
    }
    ts.forEachChild(node, collectImportsAndShadows);
  };
  collectImportsAndShadows(file);
  const frameworkKindForImport = (binding: { readonly module: string; readonly imported: string } | undefined): FrameworkFactoryKind | null => {
    if (binding?.module === "vue" && binding.imported === "createApp") return "vue-app";
    if (binding?.module === "pinia" && binding.imported === "createPinia") return "pinia";
    if (binding?.module === "vue-router" && binding.imported === "createRouter") return "router";
    if (binding?.module === "vue-router" && binding.imported === "createWebHistory") return "router-history-web";
    if (binding?.module === "vue-router" && binding.imported === "createWebHashHistory") return "router-history-hash";
    if (binding?.module === "vue-router" && binding.imported === "createMemoryHistory") return "router-history-memory";
    return null;
  };
  const frameworkFactoryKind = (call: ts.CallExpression): FrameworkFactoryKind | null => {
    const value = unwrapExpression(call.expression);
    const binding = ts.isIdentifier(value)
      ? imports.get(value.text)
      : ts.isPropertyAccessExpression(value) && ts.isIdentifier(value.expression)
        ? (() => {
          const namespace = imports.get(value.expression.text);
          return namespace?.imported === "*" ? { module: namespace.module, imported: value.name.text } : undefined;
        })()
        : undefined;
    if (ts.isIdentifier(value)) {
      for (const [fn, names] of shadowedNamesByFunction) {
        if (names.has(value.text) && fn !== file && value.getSourceFile() === file) {
          let current: ts.Node | undefined = value.parent;
          while (current && current !== fn) current = current.parent;
          if (current === fn) return null;
        }
      }
    }
    if (ts.isPropertyAccessExpression(value) && ts.isIdentifier(value.expression)) {
      for (const [fn, names] of shadowedNamesByFunction) {
        if (!names.has(value.expression.text)) continue;
        let current: ts.Node | undefined = value.expression.parent;
        while (current && current !== fn) current = current.parent;
        if (current === fn) return null;
      }
    }
    return frameworkKindForImport(binding);
  };
  const precollectFrameworkBindings = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer && ts.isCallExpression(node.initializer)) {
      const kind = frameworkFactoryKind(node.initializer);
      if (kind) {
        const binding = {
          kind,
          instanceId: stableId("framework-instance", path, `${kind}:${absoluteStart(node.initializer)}`),
        } as const;
        frameworkBindings.set(node.name.text, binding);
        frameworkBindingsByDeclaration.set(node, binding);
      }
    }
    ts.forEachChild(node, precollectFrameworkBindings);
  };
  precollectFrameworkBindings(file);
  const frameworkInstanceForExpression = (expression: ts.Expression): FrameworkBinding | null => {
    const value = unwrapExpression(expression);
    if (ts.isIdentifier(value)) {
      let current: ts.Node | undefined = value.parent;
      while (current) {
        if (ts.isFunctionLike(current)) {
          const functionScope = current;
          const names = shadowedNamesByFunction.get(functionScope);
          if (names?.has(value.text)) {
            let localBinding: FrameworkBinding | null = null;
            const findLocal = (child: ts.Node): void => {
              if (localBinding || (child !== functionScope && ts.isFunctionLike(child))) return;
              if (ts.isVariableDeclaration(child) && ts.isIdentifier(child.name)
                && child.name.text === value.text) {
                localBinding = frameworkBindingsByDeclaration.get(child) ?? null;
              }
              ts.forEachChild(child, findLocal);
            };
            const body = (functionScope as ts.FunctionLikeDeclaration).body;
            if (body) findLocal(body);
            return localBinding && !invalidFrameworkBindings.has(value.text) ? localBinding : null;
          }
        }
        current = current.parent;
      }
      const binding = frameworkBindings.get(value.text);
      if (binding && !invalidFrameworkBindings.has(value.text)) return binding;
      const importBinding = imports.get(value.text);
      if (importBinding?.module.startsWith(".")) {
        const candidates = [...state.frameworkExports.entries()].filter(([key]) => {
          const separator = key.lastIndexOf("#");
          if (separator < 0 || key.slice(separator + 1) !== importBinding.imported) return false;
          return moduleResolvesToSource(path, importBinding.module, key.slice(0, separator));
        });
        if (candidates.length === 1) return candidates[0]![1];
      }
      return null;
    }
    if (ts.isCallExpression(value) && ts.isPropertyAccessExpression(value.expression)) {
      const method = value.expression.name.text;
      const receiver = frameworkInstanceForExpression(value.expression.expression);
      // Vue's use() returns the same app instance, so preserve identity through
      // arbitrarily chained plugin installs before resolving mount(). Other
      // fluent APIs are intentionally not treated as app-preserving.
      if (method === "use" && receiver?.kind === "vue-app") return receiver;
    }
    if (ts.isCallExpression(value)) {
      const kind = frameworkFactoryKind(value);
      if (!kind) return null;
      return { kind, instanceId: stableId("framework-instance", path, `${kind}:${absoluteStart(value)}`) };
    }
    if (ts.isPropertyAccessExpression(value)) {
      const receiver = frameworkInstanceForExpression(value.expression);
      return receiver?.kind === "vue-app" ? receiver : null;
    }
    return null;
  };
  const recordFrameworkEffect = (
    name: string,
    trigger: string,
    node: ts.Node,
    instanceId: string,
    relatedInstanceId?: string,
  ): void => {
    const id = stableId("effect", path, `${name}:${absoluteStart(node)}`);
    if (state.effects.some(effect => effect.id === id)) return;
    state.effects.push({
      id,
      name,
      trigger,
      instanceId,
      ...(relatedInstanceId ? { relatedInstanceId } : {}),
      asynchronous: false,
      cleanup: name === "vue.app.unmount" ? "present" : "not-applicable",
      sourceRefs: [nodeRef(node)],
    });
  };
  const frameworkPluginForExpression = (expression: ts.Expression | undefined): FrameworkBinding | null => {
    if (!expression) return null;
    return frameworkInstanceForExpression(expression);
  };
  const stateByName = new Map<string, MiniappAnalyzedState>();
  const componentNames = new Set<string>();
  let anonymousComponent = 0;

  const recordState = (
    name: string,
    scope: MiniappAnalyzedState["scope"],
    node: ts.Node,
    stateType: MiniappAnalyzedState["stateType"],
    exactInitial?: string,
  ): void => {
    const existing = stateByName.get(name);
    const next: MiniappAnalyzedState = existing ?? {
      id: stableId("state", path, name),
      name,
      scope,
      stateType,
      reads: 0,
      writes: 0,
      sourceRefs: [nodeRef(node)],
    };
    stateByName.set(name, next);
    if (exactInitial !== undefined) state.stateInitialValues.set(next.id, exactInitial);
  };

  const exactInitial = (expression: ts.Expression | undefined): { readonly type: MiniappAnalyzedState["stateType"]; readonly value?: string } => {
    if (!expression) return { type: "unknown" };
    const value = unwrapExpression(expression);
    if (ts.isArrayLiteralExpression(value) && value.elements.length === 0) return { type: "collection", value: "[]" };
    if (ts.isObjectLiteralExpression(value) && value.properties.length === 0) return { type: "object", value: "{}" };
    if (ts.isStringLiteralLike(value) || ts.isNumericLiteral(value) || value.kind === ts.SyntaxKind.TrueKeyword || value.kind === ts.SyntaxKind.FalseKeyword || value.kind === ts.SyntaxKind.NullKeyword) {
      return { type: "scalar", value: value.getText(file) };
    }
    return { type: "unknown" };
  };
  const storeStateObject = (call: ts.CallExpression): ts.ObjectLiteralExpression | undefined => {
    const config = call.arguments[1];
    if (!config || !ts.isObjectLiteralExpression(config)) return undefined;
    const stateProperty = config.properties.find(item => propertyName(item.name) === "state");
    const initializer = stateProperty && ts.isPropertyAssignment(stateProperty) ? stateProperty.initializer
      : stateProperty && ts.isMethodDeclaration(stateProperty) ? stateProperty.body
        : undefined;
    if (!initializer) return undefined;
    if (ts.isArrowFunction(initializer) || ts.isFunctionExpression(initializer)) {
      if (!ts.isBlock(initializer.body)) {
        const body = unwrapExpression(initializer.body);
        return ts.isObjectLiteralExpression(body) ? body : undefined;
      }
      const returned = initializer.body.statements.find(ts.isReturnStatement)?.expression;
      if (returned) {
        const body = unwrapExpression(returned);
        return ts.isObjectLiteralExpression(body) ? body : undefined;
      }
    }
    if (ts.isBlock(initializer)) {
      const returned = initializer.statements.find(ts.isReturnStatement)?.expression;
      if (returned) {
        const body = unwrapExpression(returned);
        return ts.isObjectLiteralExpression(body) ? body : undefined;
      }
    }
    return undefined;
  };
  const directJsxOpening = (expression: ts.Expression): ts.JsxOpeningElement | ts.JsxSelfClosingElement | undefined => {
    const value = unwrapExpression(expression);
    return ts.isJsxElement(value)
      ? value.openingElement
      : ts.isJsxSelfClosingElement(value)
        ? value
        : undefined;
  };
  const returnedJsxRootIds = (body: ts.ConciseBody): readonly string[] => {
    const returned = ts.isBlock(body)
      ? body.statements.find(ts.isReturnStatement)?.expression
      : body;
    if (!returned) return [];
    const opening = directJsxOpening(returned);
    if (!opening) return [];
    const tag = opening.tagName.getText(file);
    const name = /^[a-z]/u.test(tag) ? `${tag}-${absoluteStart(opening)}` : tag;
    return [stableId("component", path, name)];
  };
  const unresolvedComponentControlFlow = (body: ts.ConciseBody): boolean => {
    const containsJsx = (root: ts.Node): boolean => {
      let present = false;
      const walk = (node: ts.Node): void => {
        if (present) return;
        if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node) || ts.isJsxFragment(node)) {
          present = true;
          return;
        }
        ts.forEachChild(node, walk);
      };
      walk(root);
      return present;
    };
    if (!ts.isBlock(body)) return directJsxOpening(body) === undefined && containsJsx(body);
    const returns: ts.ReturnStatement[] = [];
    let branch = false;
    const walk = (node: ts.Node): void => {
      if (node !== body && (ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node))) return;
      if (ts.isReturnStatement(node)) returns.push(node);
      if (ts.isIfStatement(node) || ts.isSwitchStatement(node) || ts.isConditionalExpression(node)
        || ts.isTryStatement(node) || ts.isForStatement(node) || ts.isForOfStatement(node)
        || ts.isForInStatement(node) || ts.isWhileStatement(node) || ts.isDoStatement(node)) branch = true;
      ts.forEachChild(node, walk);
    };
    walk(body);
    if (!containsJsx(body)) return false;
    return branch
      || returns.length !== 1
      || !returns[0]!.expression
      || directJsxOpening(returns[0]!.expression!) === undefined;
  };
  const unresolvedComponentStatements = (body: ts.ConciseBody): boolean => {
    if (!ts.isBlock(body)) return false;
    const modeledStateFactories = new Set(["useState", "useReducer", "createSignal"]);
    return body.statements.some(statement => {
      if (ts.isReturnStatement(statement)) return !statement.expression || directJsxOpening(statement.expression) === undefined;
      if (ts.isVariableStatement(statement)) {
        return statement.declarationList.declarations.some(declaration => {
          const initializer = declaration.initializer;
          return !initializer || !ts.isCallExpression(initializer)
            || !modeledStateFactories.has(initializer.expression.getText(file));
        });
      }
      return !ts.isEmptyStatement(statement);
    });
  };
  const asyncOrGenerator = (node: ts.FunctionDeclaration | ts.ArrowFunction): boolean =>
    node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.AsyncKeyword) === true
    || (ts.isFunctionDeclaration(node) && node.asteriskToken !== undefined);
  const directlyModeledCalls = new Set([
    "Page", "Component", "import", "fetch", "ref", "reactive", "computed", "useState", "useReducer", "createSignal",
    "defineStore", "createStore", "configureStore", "create", "createRouter", "createBrowserRouter", "useRoutes",
    "useEffect", "watch", "watchEffect", "onMounted", "onUnmounted", "onBeforeUnmount", "createApp",
  ]);

  const collectActionFact = (
    name: string,
    parameters: readonly ts.ParameterDeclaration[],
    body: ts.Block,
    owner: ts.Node,
  ): void => {
    const calls: Array<{ receiver: string; method: string; arguments: string[]; receiverModule: string | null }> = [];
    const assignments: Array<{ target: string; value: string }> = [];
    const trims: Array<{ target: string; source: string }> = [];
    const appends: Array<{ target: string; value: string; guardExpression: string | null }> = [];
    const guardExpression = (node: ts.Node): string | null => {
      let current: ts.Node | undefined = node.parent;
      while (current && current !== body) {
        if (ts.isIfStatement(current)) return current.expression.getText(file);
        current = current.parent;
      }
      return null;
    };
    const walk = (node: ts.Node): void => {
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
        const receiver = node.expression.expression.getText(file);
        const method = node.expression.name.text;
        const arguments_ = node.arguments.map(item => item.getText(file));
        const receiverRoot = receiver.split(".", 1)[0] ?? receiver;
        calls.push({ receiver, method, arguments: arguments_, receiverModule: storeInstances.get(receiverRoot) ?? null });
        if (method === "trim" && ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name)) {
          trims.push({ target: node.parent.name.text, source: receiver });
        }
        if (method === "push") {
          appends.push({ target: receiver, value: arguments_[0] ?? "", guardExpression: guardExpression(node) });
        }
      }
      if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
        assignments.push({ target: node.left.getText(file), value: node.right.getText(file) });
      }
      ts.forEachChild(node, walk);
    };
    walk(body);
    const exactTodoSubmit = (() => {
      if (body.statements.length !== 2) return null;
      const callStatement = body.statements[0];
      const clearStatement = body.statements[1];
      if (!callStatement || !clearStatement || !ts.isExpressionStatement(callStatement)
        || !ts.isCallExpression(callStatement.expression)
        || !ts.isPropertyAccessExpression(callStatement.expression.expression)
        || callStatement.expression.arguments.length !== 1
        || !ts.isExpressionStatement(clearStatement)
        || !ts.isBinaryExpression(clearStatement.expression)
        || clearStatement.expression.operatorToken.kind !== ts.SyntaxKind.EqualsToken
        || !/^(?:''|""|``)$/u.test(clearStatement.expression.right.getText(file))) return null;
      const receiver = callStatement.expression.expression.expression.getText(file);
      const receiverRoot = receiver.split(".", 1)[0] ?? receiver;
      return {
        receiver,
        receiverModule: storeInstances.get(receiverRoot) ?? null,
        method: callStatement.expression.expression.name.text,
        argument: callStatement.expression.arguments[0]!.getText(file),
        clearTarget: clearStatement.expression.left.getText(file),
      };
    })();
    const exactTodoAppend = (() => {
      if (body.statements.length !== 2 || parameters.length !== 1) return null;
      const declarationStatement = body.statements[0];
      const guardedStatement = body.statements[1];
      if (!declarationStatement || !guardedStatement || !ts.isVariableStatement(declarationStatement)
        || (declarationStatement.declarationList.flags & ts.NodeFlags.Const) === 0
        || declarationStatement.declarationList.declarations.length !== 1
        || !ts.isIfStatement(guardedStatement)
        || guardedStatement.elseStatement !== undefined) return null;
      const declaration = declarationStatement.declarationList.declarations[0];
      if (!declaration || !ts.isIdentifier(declaration.name) || !declaration.initializer
        || !ts.isCallExpression(declaration.initializer)
        || !ts.isPropertyAccessExpression(declaration.initializer.expression)
        || declaration.initializer.expression.name.text !== "trim"
        || declaration.initializer.arguments.length !== 0) return null;
      const parameter = parameters[0]!.name.getText(file);
      if (declaration.initializer.expression.expression.getText(file) !== parameter) return null;
      const trimmedLocal = declaration.name.text;
      const normalizedGuard = guardedStatement.expression.getText(file).replace(/[\s()]/gu, "");
      if (![trimmedLocal, `!!${trimmedLocal}`, `${trimmedLocal}.length`, `${trimmedLocal}.length>0`].includes(normalizedGuard)) return null;
      const guardedBody = ts.isBlock(guardedStatement.thenStatement)
        ? guardedStatement.thenStatement.statements
        : [guardedStatement.thenStatement];
      const appendStatement = guardedBody.length === 1 ? guardedBody[0] : undefined;
      if (!appendStatement || !ts.isExpressionStatement(appendStatement)
        || !ts.isCallExpression(appendStatement.expression)
        || !ts.isPropertyAccessExpression(appendStatement.expression.expression)
        || appendStatement.expression.expression.name.text !== "push"
        || appendStatement.expression.arguments.length !== 1
        || appendStatement.expression.arguments[0]!.getText(file) !== trimmedLocal) return null;
      return {
        parameter,
        trimmedLocal,
        collectionTarget: appendStatement.expression.expression.expression.getText(file),
      };
    })();
    state.actionFacts.push({
      id: stableId("action", path, `${name}:${absoluteStart(owner)}`),
      name,
      parameters: parameters.map(item => item.name.getText(file)),
      calls,
      assignments,
      trims,
      appends,
      exactTodoSubmit,
      exactTodoAppend,
      sourceRefs: [nodeRef(owner)],
    });
  };

  const validateRouterConfiguration = (
    call: ts.CallExpression,
    routerInstanceId: string,
  ): string | null => {
    const configuration = call.arguments.length === 1 ? unwrapExpression(call.arguments[0]!) : undefined;
    if (!configuration || !ts.isObjectLiteralExpression(configuration)) {
      state.findings.push(finding(
        "MINIAPP_ROUTER_CONFIGURATION_UNRESOLVED",
        "createRouter requires exactly one inline object-literal configuration for exact routes/history lowering.",
        "D",
        [nodeRef(call)],
        "error",
        true,
      ));
      return null;
    }
    const properties = configuration.properties;
    const historyProperties = properties.filter(property => propertyName(property.name) === "history");
    const routesProperties = properties.filter(property => propertyName(property.name) === "routes");
    const unknownOptions = properties.filter(property => {
      const name = ts.isSpreadAssignment(property) ? undefined : propertyName(property.name);
      return name !== "history" && name !== "routes";
    });
    if (unknownOptions.length > 0 || historyProperties.length !== 1 || routesProperties.length !== 1) {
      state.findings.push(finding(
        "MINIAPP_ROUTER_OPTION_UNRESOLVED",
        "Router configuration must contain exactly one history and routes property and no unmodeled options.",
        "D",
        [nodeRef(configuration)],
        "error",
        true,
      ));
    }
    const historyProperty = historyProperties[0];
    const historyInitializer = historyProperty && ts.isPropertyAssignment(historyProperty)
      ? unwrapExpression(historyProperty.initializer)
      : undefined;
    let historyInstanceId: string | null = null;
    let validRootHistory = false;
    if (historyInitializer && ts.isCallExpression(historyInitializer)) {
      const historyKind = frameworkFactoryKind(historyInitializer);
      const historyBinding = frameworkBindings.get(
        ts.isIdentifier(historyInitializer.expression) ? historyInitializer.expression.text : "",
      );
      if (historyKind === "router-history-web"
        && historyInitializer.arguments.length === 1
        && literalText(historyInitializer.arguments[0]) === "/") {
        historyInstanceId = historyBinding?.instanceId
          ?? stableId("framework-instance", path, `${historyKind}:${absoluteStart(historyInitializer)}`);
        validRootHistory = true;
      }
    }
    if (!validRootHistory) {
      state.findings.push(finding(
        "MINIAPP_ROUTER_HISTORY_BASE_UNRESOLVED",
        "Router history must be one trace-bound createWebHistory(\"/\") call; null, hash, memory, dynamic and referenced history are not equivalent to the native root page stack.",
        "D",
        [nodeRef(historyProperty ?? configuration)],
        "error",
        true,
      ));
    }
    const routesProperty = routesProperties[0];
    const routeInitializer = routesProperty && ts.isPropertyAssignment(routesProperty)
      ? unwrapExpression(routesProperty.initializer)
      : undefined;
    if (!routeInitializer || !ts.isArrayLiteralExpression(routeInitializer) || routeInitializer.elements.length === 0) {
      state.findings.push(finding(
        "MINIAPP_ROUTER_ROUTES_UNRESOLVED",
        "Router routes must be one non-empty inline array literal of explicit path/component objects.",
        "D",
        [nodeRef(routesProperty ?? configuration)],
        "error",
        true,
      ));
      return historyInstanceId;
    }
    for (const element of routeInitializer.elements) {
      const routeObject = unwrapExpression(element);
      if (!ts.isObjectLiteralExpression(routeObject)) {
        state.findings.push(finding(
          "MINIAPP_ROUTER_ROUTES_UNRESOLVED",
          "Spread, referenced and computed route entries require a resolved route graph before native page generation.",
          "D",
          [nodeRef(element)],
          "error",
          true,
        ));
        continue;
      }
      const names = routeObject.properties.map(property => ts.isSpreadAssignment(property) ? undefined : propertyName(property.name));
      const pathProperty = routeObject.properties.find(property => ts.isPropertyAssignment(property)
        && propertyName(property.name) === "path");
      const nameProperty = routeObject.properties.find(property => ts.isPropertyAssignment(property)
        && propertyName(property.name) === "name");
      const componentProperty = routeObject.properties.find(property => ts.isPropertyAssignment(property)
        && propertyName(property.name) === "component");
      const routePath = pathProperty && ts.isPropertyAssignment(pathProperty)
        ? literalText(pathProperty.initializer)
        : undefined;
      const routeName = nameProperty && ts.isPropertyAssignment(nameProperty)
        ? literalText(nameProperty.initializer)
        : undefined;
      const componentInitializer = componentProperty && ts.isPropertyAssignment(componentProperty)
        ? unwrapExpression(componentProperty.initializer)
        : undefined;
      const valid = names.length >= 2 && names.length <= 3
        && names.filter(name => name === "path").length === 1
        && names.filter(name => name === "component").length === 1
        && names.filter(name => name === "name").length <= 1
        && routeObject.properties.every(property => ts.isPropertyAssignment(property)
          && ["path", "component", "name"].includes(propertyName(property.name) ?? ""))
        && typeof routePath === "string"
        && routePath.startsWith("/")
        && (nameProperty === undefined || (typeof routeName === "string" && routeName.length > 0))
        && Boolean(componentInitializer)
        && componentInitializer?.kind !== ts.SyntaxKind.NullKeyword;
      if (!valid) {
        state.findings.push(finding(
          "MINIAPP_ROUTE_OPTION_UNRESOLVED",
          "Each route object must contain exactly path and component properties; aliases, guards, meta, props, children and spreads are not lowered.",
          "D",
          [nodeRef(routeObject)],
          "error",
          true,
        ));
        continue;
      }
      routeOwnerInstances.set(routeObject, routerInstanceId);
    }
    return historyInstanceId;
  };

  const visit = (node: ts.Node): void => {
    const recordSecretReferenceFinding = (key: string, owner: ts.Node, surface: string): void => {
      state.findings.push(finding(
        "MINIAPP_SOURCE_SECRET_REFERENCE_REQUIRED",
        `${key} ${surface} must be a single vault://, secret://, or kms:// reference; expression and embedded secret values are not consumed.`,
        "E",
        [nodeRef(owner)],
        "critical",
        true,
      ));
    };
    if ((ts.isPropertyAssignment(node)
      || ts.isPropertyDeclaration(node)
      || ts.isMethodDeclaration(node)
      || ts.isGetAccessorDeclaration(node)
      || ts.isSetAccessorDeclaration(node))
      && ts.isComputedPropertyName(node.name)) {
      state.findings.push(finding(
        "MINIAPP_COMPUTED_PROPERTY_SEMANTICS_UNRESOLVED",
        `${node.name.getText(file)} is a computed property name; its state, capability, permission and secret-flow meaning cannot be proven by the bounded analyzer.`,
        "C",
        [nodeRef(node)],
        "error",
        true,
      ));
    }
    if (ts.isPropertyAssignment(node)) {
      const key = propertyName(node.name);
      if (key && sensitiveSourceKey(key) && !exactSecretReferenceInitializer(node.initializer)) {
        recordSecretReferenceFinding(key, node, "property");
      }
    }
    if (ts.isPropertyDeclaration(node)) {
      const key = propertyName(node.name);
      if (key && sensitiveSourceKey(key) && !exactSecretReferenceInitializer(node.initializer)) {
        recordSecretReferenceFinding(key, node, "class property");
      }
    }
    if ((ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node))) {
      const key = propertyName(node.name);
      if (key && sensitiveSourceKey(key)) recordSecretReferenceFinding(key, node, "accessor");
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)
      && sensitiveSourceKey(node.name.text) && !exactSecretReferenceInitializer(node.initializer)) {
      recordSecretReferenceFinding(node.name.text, node, "binding");
    }
    if (ts.isBinaryExpression(node)) {
      const assignmentKind = node.operatorToken.kind;
      const assignment = assignmentKind >= ts.SyntaxKind.FirstAssignment
        && assignmentKind <= ts.SyntaxKind.LastAssignment;
      if (assignment && ts.isIdentifier(node.left) && frameworkBindings.has(node.left.text)) {
        invalidFrameworkBindings.add(node.left.text);
        state.findings.push(finding(
          "MINIAPP_FRAMEWORK_INSTANCE_REASSIGNED",
          `${node.left.text} reassigns a trace-bound framework instance; later operations cannot be attributed to one declaration.`,
          "C",
          [nodeRef(node)],
          "error",
          true,
        ));
      }
      if (assignment && (ts.isPropertyAccessExpression(node.left) || ts.isElementAccessExpression(node.left))) {
        const receiver = frameworkInstanceForExpression(node.left);
        if (receiver?.kind === "vue-app") {
          state.findings.push(finding(
            "MINIAPP_VUE_APP_PROPERTY_WRITE_UNRESOLVED",
            `${node.left.getText(file)} mutates the Vue application instance/configuration outside bounded bootstrap lowering.`,
            "D",
            [nodeRef(node)],
            "error",
            true,
          ));
        }
      }
      if (assignment
        && ts.isElementAccessExpression(node.left)
        && (!node.left.argumentExpression || !ts.isStringLiteralLike(node.left.argumentExpression))) {
        state.findings.push(finding(
          "MINIAPP_DYNAMIC_PROPERTY_ASSIGNMENT_UNRESOLVED",
          `${node.left.getText(file)} uses a dynamic assignment key whose state, capability, permission and secret-flow meaning is not represented.`,
          "C",
          [nodeRef(node)],
          "error",
          true,
        ));
      }
      const key = assignment ? sensitiveAssignmentKey(node.left) : undefined;
      if (key && (assignmentKind !== ts.SyntaxKind.EqualsToken || !exactSecretReferenceInitializer(node.right))) {
        recordSecretReferenceFinding(key, node, "assignment");
      }
    }
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      const method = node.expression.name.text;
      const keyArgument = node.arguments[0];
      const definePropertyKeyArgument = node.arguments[1];
      if (method === "defineProperty" && node.arguments.length >= 3
        && definePropertyKeyArgument && ts.isStringLiteralLike(definePropertyKeyArgument)) {
        const key = definePropertyKeyArgument.text;
        const descriptor = node.arguments[2];
        const valueProperty = descriptor && ts.isObjectLiteralExpression(descriptor)
          ? descriptor.properties.find(property => ts.isPropertyAssignment(property) && propertyName(property.name) === "value")
          : undefined;
        const value = valueProperty && ts.isPropertyAssignment(valueProperty) ? valueProperty.initializer : undefined;
        if (sensitiveSourceKey(key) && !exactSecretReferenceInitializer(value)) {
          recordSecretReferenceFinding(key, node, "defineProperty value");
        }
      }
      if (["set", "setItem"].includes(method) && node.arguments.length >= 2
        && keyArgument && ts.isStringLiteralLike(keyArgument)) {
        const key = keyArgument.text;
        if (sensitiveSourceKey(key) && !exactSecretReferenceInitializer(node.arguments[1])) {
          recordSecretReferenceFinding(key, node, `${method} value`);
        }
      }
    }
    if (ts.isJsxAttribute(node)) {
      const key = node.name.getText(file);
      const initializer = node.initializer;
      const safe = initializer !== undefined && ts.isStringLiteral(initializer) && sourceSecretReference.test(initializer.text);
      if (sensitiveSourceKey(key) && !safe) {
        state.findings.push(finding(
          "MINIAPP_SOURCE_SECRET_REFERENCE_REQUIRED",
          `${key} JSX input must be a single vault://, secret://, or kms:// reference.`,
          "E",
          [nodeRef(node)],
          "critical",
          true,
        ));
      }
    }
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      if (!node.moduleSpecifier.text.startsWith(".") && !node.moduleSpecifier.text.startsWith("/")) {
        state.dependencies.add(node.moduleSpecifier.text);
        const usage = state.dependencyUsage.get(node.moduleSpecifier.text) ?? [];
        usage.push(nodeRef(node));
        state.dependencyUsage.set(node.moduleSpecifier.text, usage);
      }
      const clause = node.importClause;
      if (clause?.name) imports.set(clause.name.text, { module: node.moduleSpecifier.text, imported: "default" });
      if (clause?.namedBindings && ts.isNamespaceImport(clause.namedBindings)) {
        imports.set(clause.namedBindings.name.text, { module: node.moduleSpecifier.text, imported: "*" });
      }
      for (const item of clause?.namedBindings && ts.isNamedImports(clause.namedBindings) ? clause.namedBindings.elements : []) {
        imports.set(item.name.text, { module: node.moduleSpecifier.text, imported: item.propertyName?.text ?? item.name.text });
      }
    }

    if (ts.isFunctionDeclaration(node) && node.name && node.body) {
      collectActionFact(node.name.text, node.parameters, node.body, node);
    } else if (ts.isMethodDeclaration(node) && node.body) {
      const name = propertyName(node.name);
      if (name) collectActionFact(name, node.parameters, node.body, node);
    }

    if ((ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node)) && node.name && /^[A-Z]/.test(node.name.text)) {
      componentNames.add(node.name.text);
      state.components.push({
        id: stableId("component", path, node.name.text),
        name: node.name.text,
        semanticRole: "view-component",
        sourceKind: "ast",
        props: ts.isFunctionDeclaration(node)
          ? node.parameters.map(item => item.name.getText(file)).sort()
          : [],
        events: [],
        children: ts.isFunctionDeclaration(node) && node.body ? returnedJsxRootIds(node.body) : [],
        accessibility: [],
        ...analyzedComponentBindings(node.name.text, {}),
        sourceRefs: [nodeRef(node)],
      });
      if (ts.isFunctionDeclaration(node) && node.body && unresolvedComponentControlFlow(node.body)) {
        state.findings.push(finding(
          "MINIAPP_COMPONENT_CONTROL_FLOW_UNRESOLVED",
          `${node.name.text} contains branching or multiple JSX returns that are not represented by the bounded component IR.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (ts.isFunctionDeclaration(node) && node.body && unresolvedComponentStatements(node.body)) {
        state.findings.push(finding(
          "MINIAPP_COMPONENT_STATEMENTS_UNRESOLVED",
          `${node.name.text} contains component statements outside the bounded state-declaration plus direct-JSX-return grammar.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (ts.isFunctionDeclaration(node) && asyncOrGenerator(node)) {
        state.findings.push(finding(
          "MINIAPP_ASYNC_COMPONENT_UNSUPPORTED",
          `${node.name.text} is async or generator-based; Promise, Suspense and yield semantics are not represented by the bounded component IR.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (ts.isClassDeclaration(node)) {
        state.findings.push(finding(
          "MINIAPP_REACT_CLASS_COMPONENT_UNSUPPORTED",
          `${node.name.text} is a React-style class component; render, state and lifecycle semantics are outside the bounded function-component analyzer.`,
          "C",
          [nodeRef(node)],
        ));
      }
    }

    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      if (ts.isArrowFunction(node.initializer) && /^[A-Z]/.test(node.name.text)) {
        componentNames.add(node.name.text);
        state.components.push({
          id: stableId("component", path, node.name.text),
          name: node.name.text,
          semanticRole: "view-component",
          sourceKind: "ast",
          props: node.initializer.parameters.map(item => item.name.getText(file)).sort(),
          events: [],
          children: returnedJsxRootIds(node.initializer.body),
          accessibility: [],
          ...analyzedComponentBindings(node.name.text, {}),
          sourceRefs: [nodeRef(node)],
        });
        if (unresolvedComponentControlFlow(node.initializer.body)) {
          state.findings.push(finding(
            "MINIAPP_COMPONENT_CONTROL_FLOW_UNRESOLVED",
            `${node.name.text} contains branching or multiple JSX returns that are not represented by the bounded component IR.`,
            "C",
            [nodeRef(node)],
          ));
        }
        if (unresolvedComponentStatements(node.initializer.body)) {
          state.findings.push(finding(
            "MINIAPP_COMPONENT_STATEMENTS_UNRESOLVED",
            `${node.name.text} contains component statements outside the bounded state-declaration plus direct-JSX-return grammar.`,
            "C",
            [nodeRef(node)],
          ));
        }
        if (asyncOrGenerator(node.initializer)) {
          state.findings.push(finding(
            "MINIAPP_ASYNC_COMPONENT_UNSUPPORTED",
            `${node.name.text} is async; Promise and Suspense semantics are not represented by the bounded component IR.`,
            "C",
            [nodeRef(node)],
          ));
        }
      }
      if (ts.isCallExpression(node.initializer)) {
        const callee = node.initializer.expression.getText(file);
        const importedFactory = imports.get(callee);
        if (importedFactory?.module.startsWith(".")) storeInstances.set(node.name.text, importedFactory.module);
        if (["ref", "reactive", "computed", "useState", "useReducer", "createSignal"].includes(callee)) {
          const initial = exactInitial(node.initializer.arguments[0]);
          recordState(node.name.text, "component", node, callee === "reactive" ? "object" : initial.type, initial.value);
        }
        if (callee === "defineStore") {
          const storeState = storeStateObject(node.initializer);
          for (const property of storeState?.properties ?? []) {
            if (!ts.isPropertyAssignment(property)) continue;
            const name = propertyName(property.name);
            if (!name) continue;
            const initial = exactInitial(property.initializer);
            recordState(name, "application", property, initial.type, initial.value);
          }
        } else if (["createStore", "configureStore", "create"].includes(callee)) {
          recordState(node.name.text, "application", node, "object");
        }
      }
    }

    if (
      ts.isVariableDeclaration(node)
      && ts.isArrayBindingPattern(node.name)
      && node.initializer
      && ts.isCallExpression(node.initializer)
    ) {
      const callee = node.initializer.expression.getText(file);
      if (callee === "useState" || callee === "useReducer") {
        const first = node.name.elements[0];
        const name = first && ts.isBindingElement(first)
          ? first.name.getText(file)
          : `state-${absoluteStart(node)}`;
        const initial = exactInitial(node.initializer.arguments[0]);
        recordState(name, "component", node, initial.type, initial.value);
      }
    }

    if (ts.isCallExpression(node)) {
      const callee = node.expression.getText(file);
      const frameworkKind = frameworkFactoryKind(node);
      if (frameworkKind === "vue-app") {
        const instanceId = frameworkBindings.get(
          ts.isIdentifier(node.expression) ? node.expression.text : "",
        )?.instanceId ?? stableId("framework-instance", path, `${frameworkKind}:${absoluteStart(node)}`);
        recordFrameworkEffect("vue.create-app", "application-bootstrap", node, instanceId);
        const rootExpression = node.arguments.length === 1 ? unwrapExpression(node.arguments[0]!) : undefined;
        const rootBinding = rootExpression && ts.isIdentifier(rootExpression)
          ? imports.get(rootExpression.text)
          : undefined;
        const rootIsTraceBound = Boolean(
          rootExpression
          && ts.isIdentifier(rootExpression)
          && (
            componentNames.has(rootExpression.text)
            || (rootBinding?.module.startsWith(".") && rootBinding.imported === "default")
          ),
        );
        if (node.arguments.length !== 1 || !rootExpression || !ts.isIdentifier(rootExpression) || !rootIsTraceBound) {
          state.findings.push(finding(
            node.arguments.length > 1 ? "MINIAPP_VUE_ROOT_PROPS_UNRESOLVED" : "MINIAPP_VUE_ROOT_COMPONENT_UNRESOLVED",
            "createApp requires exactly one imported or locally declared trace-bound root component; root props and unknown roots are not lowered.",
            "D",
            [nodeRef(node)],
            "error",
            true,
          ));
        }
      } else if (frameworkKind === "pinia") {
        const instanceId = frameworkBindings.get(
          ts.isIdentifier(node.expression) ? node.expression.text : "",
        )?.instanceId ?? stableId("framework-instance", path, `${frameworkKind}:${absoluteStart(node)}`);
        recordFrameworkEffect("pinia.create", "application-state-provider", node, instanceId);
        if (node.arguments.length !== 0) state.findings.push(finding(
          "MINIAPP_PINIA_FACTORY_ARGUMENTS_UNRESOLVED",
          "createPinia must not receive source-controlled arguments.",
          "D",
          [nodeRef(node)],
          "error",
          true,
        ));
      } else if (frameworkKind === "router") {
        state.parserEvidence.add("vue-router-ast");
        const routerInstanceId = frameworkBindings.get(
          ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name) ? node.parent.name.text : "",
        )?.instanceId ?? stableId("framework-instance", path, `${frameworkKind}:${absoluteStart(node)}`);
        const historyInstanceId = validateRouterConfiguration(node, routerInstanceId);
        recordFrameworkEffect("vue-router.create-router", "application-router", node, routerInstanceId, historyInstanceId ?? undefined);
      } else if (frameworkKind?.startsWith("router-history-")) {
        const instanceId = frameworkBindings.get(
          ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name) ? node.parent.name.text : "",
        )?.instanceId ?? stableId("framework-instance", path, `${frameworkKind}:${absoluteStart(node)}`);
        const exactRoot = frameworkKind === "router-history-web"
          && node.arguments.length === 1
          && literalText(node.arguments[0]) === "/";
        recordFrameworkEffect(
          exactRoot ? "vue-router.history.web-root" : "vue-router.history.unsupported",
          exactRoot ? "native-page-stack" : "source-router-history",
          node,
          instanceId,
        );
        if (!exactRoot) state.findings.push(finding(
          "MINIAPP_ROUTER_HISTORY_BASE_UNRESOLVED",
          "Only createWebHistory(\"/\") is equivalent to the native root page stack; hash, memory, null, dynamic and non-root bases are blocked.",
          "D",
          [nodeRef(node)],
          "error",
          true,
        ));
      }
      const frameworkPropertyCall = ts.isPropertyAccessExpression(node.expression) ? node.expression : undefined;
      if (frameworkPropertyCall) {
        const receiver = frameworkInstanceForExpression(frameworkPropertyCall.expression);
        if (receiver?.kind === "vue-app") {
          if (frameworkPropertyCall.name.text === "use" && node.arguments.length === 1) {
            const plugin = frameworkPluginForExpression(node.arguments[0]);
            if (plugin?.kind === "router" || plugin?.kind === "pinia") {
              recordFrameworkEffect(`vue.app.use.${plugin.kind}`, "application-plugin-install", node, receiver.instanceId, plugin.instanceId);
            } else {
              state.findings.push(finding(
                "MINIAPP_VUE_PLUGIN_INSTALL_UNRESOLVED",
                "app.use requires one trace-bound Pinia or Vue Router instance; arbitrary plugin hooks are not silently dropped.",
                "D",
                [nodeRef(node)],
                "error",
                true,
              ));
            }
          } else if (frameworkPropertyCall.name.text === "mount") {
            if (node.arguments.length === 1 && literalText(node.arguments[0])?.trim()) {
              recordFrameworkEffect("vue.app.mount", "native-application-entry", node, receiver.instanceId);
            } else state.findings.push(finding(
              "MINIAPP_VUE_MOUNT_TARGET_UNRESOLVED",
              "Vue mount requires exactly one non-empty selector string.",
              "D",
              [nodeRef(node)],
              "error",
              true,
            ));
          } else if (frameworkPropertyCall.name.text === "unmount") {
            recordFrameworkEffect("vue.app.unmount", "unsupported-application-lifecycle", node, receiver.instanceId);
            state.findings.push(finding(
              "MINIAPP_VUE_APP_UNMOUNT_UNRESOLVED",
              "Vue app unmount lifecycle is not represented by the native MiniApp application contract.",
              "D",
              [nodeRef(node)],
              "error",
              true,
            ));
          } else if (frameworkPropertyCall.name.text !== "use" || node.arguments.length !== 1) {
            state.findings.push(finding(
              "MINIAPP_VUE_APP_PROPERTY_WRITE_UNRESOLVED",
              `${callee} reads or mutates the Vue application instance outside bounded use/mount lowering.`,
              "D",
              [nodeRef(node)],
              "error",
              true,
            ));
          }
        }
      }
      if (callee === "Page" || callee === "Component") {
        state.findings.push(finding(
          "MINIAPP_NATIVE_PAGE_SEMANTICS_UNRESOLVED",
          `${callee} data, observers, lifecycles and setData transitions require a native-page lowering before cross-platform generation.`,
          "C",
          [nodeRef(node)],
          "error",
          true,
        ));
      }
      if (["useEffect", "watch", "watchEffect", "onMounted", "onUnmounted", "onBeforeUnmount"].includes(callee)) {
        const callback = node.arguments[0];
        const cleanup = callback && (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback))
          ? callback.body.getText(file).includes("return")
            ? "present" as const
            : "absent" as const
          : "unknown" as const;
        state.effects.push({
          id: stableId("effect", path, `${callee}:${absoluteStart(node)}`),
          name: callee,
          trigger: callee,
          asynchronous: callback?.getText(file).includes("async") === true || callback?.getText(file).includes("await") === true,
          cleanup,
          sourceRefs: [nodeRef(node)],
        });
        if (cleanup === "absent" && callback?.getText(file).includes("fetch")) {
          state.findings.push(finding(
            "MINIAPP_ASYNC_EFFECT_WITHOUT_CLEANUP",
            "An asynchronous effect has no observable cleanup/cancellation path.",
            "C",
            [nodeRef(node)],
          ));
        }
      }
      if (callee === "fetch" || callee.startsWith("axios.")) addCapability(state, path, source, "network.request", "network", node, false, nodeRef(node));
      if (/^(?:localStorage|sessionStorage)\./.test(callee)) addCapability(state, path, source, "storage.local", "storage", node, false, nodeRef(node));
      const [calleeRoot, ...calleePath] = callee.split(".");
      const importBinding = calleeRoot ? imports.get(calleeRoot) : undefined;
      const isTaroBinding = importBinding?.module === "@tarojs/taro" || importBinding?.module.startsWith("@tarojs/");
      const isUniBinding = importBinding?.module === "@dcloudio/uni-app" || importBinding?.module.startsWith("@dcloudio/");
      const directPlatformRoot = calleeRoot && ["wx", "my", "tt", "xhs", "Taro", "uni"].includes(calleeRoot);
      if (directPlatformRoot || isTaroBinding || isUniBinding) {
        const operation = calleePath.length > 0
          ? calleePath.join(".")
          : importBinding && importBinding.imported !== "default" ? importBinding.imported : "unknown";
        const sensitive = /(?:address|album|authorize|biometric|bluetooth|camera|clipboard|contact|health|invoice|location|login|media|microphone|motion|payment|pay|phone|record|scan|setting|user)/iu.test(operation);
        const canonicalCapability = /(?:^|\.)request$/iu.test(operation)
          ? "network.request"
          : /(?:^|\.)(?:getStorage|setStorage|removeStorage|clearStorage)$/u.test(operation)
            ? "storage.local"
            : /(?:^|\.)(?:navigateTo|redirectTo|reLaunch|switchTab|navigateBack)$/u.test(operation)
              ? "navigation.route"
              : `platform.${operation}`;
        const provider = directPlatformRoot ? calleeRoot : importBinding?.module ?? "unknown";
        addCapability(state, path, source, canonicalCapability, `platform-api:${provider}`, node, sensitive, nodeRef(node));
        const implicitDependency = calleeRoot === "uni" ? "@dcloudio/uni-app" : calleeRoot === "Taro" ? "@tarojs/taro" : undefined;
        if (implicitDependency && !importBinding) {
          const usage = state.dependencyUsage.get(implicitDependency) ?? [];
          usage.push(nodeRef(node));
          state.dependencyUsage.set(implicitDependency, usage);
        }
        state.parserEvidence.add("platform-api-import-binding");
      }
      if (/^(?:document|window|navigator)\./.test(callee)) {
        addCapability(state, path, source, `browser.${callee.split(".")[0]}`, "browser-only", node, false, nodeRef(node));
        state.findings.push(finding(
          "MINIAPP_BROWSER_ONLY_API",
          `${callee} requires redesign or a target adapter.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (callee === "createRouter" || callee === "createBrowserRouter" || callee === "useRoutes") {
        state.parserEvidence.add("router-ast");
      }
      if (/\.(?:beforeEach|beforeResolve|beforeEnter)$/u.test(callee)) {
        state.findings.push(finding(
          "MINIAPP_GLOBAL_ROUTE_GUARD_REQUIRES_AUTH_LOWERING",
          `${callee} must be lowered into an explicit target authorization and redirect contract.`,
          "D",
          [nodeRef(node)],
          "error",
          true,
        ));
      }
      const propertyCall = ts.isPropertyAccessExpression(node.expression) ? node.expression : undefined;
      const propertyMethod = propertyCall?.name.text;
      const propertyReceiverRoot = propertyCall?.expression.getText(file).split(".", 1)[0] ?? "";
      const modeledStoreCall = propertyMethod === "add" && storeInstances.has(propertyReceiverRoot);
      const frameworkReceiver = propertyCall ? frameworkInstanceForExpression(propertyCall.expression) : null;
      const knownFrameworkMethod = frameworkReceiver?.kind === "vue-app"
        && (propertyMethod === "use" || propertyMethod === "mount");
      const knownCall = directlyModeledCalls.has(callee)
        || frameworkKind !== null
        || knownFrameworkMethod
        || (importBinding?.module.startsWith(".") ?? false)
        || directPlatformRoot
        || isTaroBinding
        || isUniBinding
        || callee.startsWith("axios.")
        || /^(?:localStorage|sessionStorage|document|window|navigator)\./u.test(callee)
        || /\.(?:beforeEach|beforeResolve|beforeEnter)$/u.test(callee)
        || propertyMethod === "trim"
        || propertyMethod === "push"
        || modeledStoreCall;
      if (!knownCall) {
        state.findings.push(finding(
          "MINIAPP_CALL_SEMANTICS_UNRESOLVED",
          `${callee} is parsed but not consumed by a capability, state transition, router, lifecycle or bounded interaction model.`,
          "C",
          [nodeRef(node)],
        ));
      }
    }

    if (ts.isNewExpression(node)) {
      state.findings.push(finding(
        "MINIAPP_CONSTRUCTOR_SEMANTICS_UNRESOLVED",
        `${node.expression.getText(file)} construction is not represented by the bounded miniapp IR.`,
        "C",
        [nodeRef(node)],
      ));
    }

    if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) {
      const expression = ts.isPropertyAccessExpression(node) ? node.expression : node.expression;
      const root = expression.getText(file).split(".", 1)[0] ?? "";
      if (["document", "window", "navigator"].includes(root)) {
        addCapability(state, path, source, `browser.${root}`, "browser-only", node, false, nodeRef(node));
        state.findings.push(finding(
          "MINIAPP_BROWSER_ONLY_API",
          `${node.getText(file)} requires redesign or a target adapter.`,
          "C",
          [nodeRef(node)],
        ));
      }
    }

    if (ts.isPropertyAssignment(node) && propertyName(node.name) === "path") {
      const routePath = literalText(node.initializer);
      const parent = node.parent;
      const routeLike = parent.properties.some(item => ts.isPropertyAssignment(item)
        && ["component", "element", "children", "loader", "redirect"].includes(propertyName(item.name) ?? ""));
      const validatedRouteContainer = routeOwnerInstances.has(parent);
      if (routePath && routeLike && !validatedRouteContainer) {
        state.findings.push(finding(
          "MINIAPP_ROUTE_DECLARATION_UNBOUND",
          `Route-like object ${routePath} is not owned by a validated router route container and cannot be lowered as a native page.`,
          "D",
          [nodeRef(parent)],
          "error",
          true,
        ));
      }
      if (routePath && routeLike && !routePath.startsWith("/")) {
        state.findings.push(finding(
          "MINIAPP_NESTED_RELATIVE_ROUTE_UNRESOLVED",
          `Relative route ${routePath} requires parent-route composition and a nested outlet contract.`,
          "D",
          [nodeRef(parent)],
          "error",
          true,
        ));
      }
      if (routePath?.startsWith("/") && validatedRouteContainer) {
        const nameProperty = parent.properties.find(item => ts.isPropertyAssignment(item)
          && propertyName(item.name) === "name");
        const routeName = nameProperty && ts.isPropertyAssignment(nameProperty)
          ? literalText(nameProperty.initializer)
          : undefined;
        const componentProperty = parent.properties.find(item => ts.isPropertyAssignment(item)
          && ["component", "element"].includes(propertyName(item.name) ?? ""));
        const componentInitializer = componentProperty && ts.isPropertyAssignment(componentProperty)
          ? componentProperty.initializer
          : undefined;
        const componentText = componentInitializer?.getText(file) ?? "";
        const dynamicImport = /import\(["']([^"']+)["']\)/u.exec(componentText);
        const referencedIdentifier = /^<?([A-Za-z_$][\w$]*)/u.exec(componentText.replace(/^\(\)\s*=>\s*/u, ""))?.[1];
        const component = componentProperty && ts.isPropertyAssignment(componentProperty)
          ? literalText(componentProperty.initializer)
            ?? dynamicImport?.[1]?.split("/").at(-1)?.replace(/\.[A-Za-z0-9]+$/u, "")
            ?? referencedIdentifier
            ?? componentProperty.initializer.getText(file).replace(/[<>"']/g, "")
          : "UnknownRouteComponent";
        const componentModule = dynamicImport?.[1]
          ?? (referencedIdentifier ? imports.get(referencedIdentifier)?.module : undefined)
          ?? null;
        state.routes.push({
          id: stableId("route", path, `${routePath}:${absoluteStart(node)}`),
          path: routePath,
          ...(routeName !== undefined ? { name: routeName } : {}),
          component,
          componentModule,
          parameters: routePath.split("/").filter(part => part.startsWith(":")),
          guards: parent.properties
            .filter(item => ts.isPropertyAssignment(item) && (
              /guard|auth|beforeEnter|loader|redirect/i.test(propertyName(item.name) ?? "")
              || (propertyName(item.name) === "meta" && /requiresAuth|auth|permission/i.test(item.initializer.getText(file)))
            ))
            .map(item => propertyName(item.name) ?? "guard")
            .sort(),
          sourceRefs: [nodeRef(parent)],
          ...(routeOwnerInstances.has(parent)
            ? { ownerInstanceId: routeOwnerInstances.get(parent)! }
            : {}),
        });
      }
    }

    if (ts.isPropertyAssignment(node) && ["alias", "children", "components"].includes(propertyName(node.name) ?? "")) {
      const routeObject = node.parent;
      if (routeObject.properties.some(item => ts.isPropertyAssignment(item) && propertyName(item.name) === "path")) {
        state.findings.push(finding(
          "MINIAPP_ADVANCED_ROUTE_CONTRACT_UNRESOLVED",
          `Route option ${propertyName(node.name)} is not represented by the flat target page manifest.`,
          "D",
          [nodeRef(routeObject)],
          "error",
          true,
        ));
      }
    }

    if (ts.isPropertyAssignment(node) && propertyName(node.name) === "scrollBehavior") {
      state.findings.push(finding(
        "MINIAPP_ROUTER_SCROLL_BEHAVIOR_UNRESOLVED",
        "Router scrollBehavior requires a target page-stack and scroll-container implementation.",
        "C",
        [nodeRef(node)],
      ));
    }

    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(file);
      const attributeEntries = node.attributes.properties.filter(ts.isJsxAttribute).map(attribute => {
        const name = attribute.name.getText(file);
        const initializer = attribute.initializer;
        const value = initializer === undefined ? "true"
          : ts.isStringLiteral(initializer) ? initializer.text
            : ts.isJsxExpression(initializer) && initializer.expression
              ? ts.isStringLiteralLike(initializer.expression) || ts.isNumericLiteral(initializer.expression)
                ? initializer.expression.text
                : `{{${initializer.expression.getText(file)}}}`
              : initializer.getText(file);
        return [name, value] as const;
      });
      const attributeNames = new Set<string>();
      for (const [attributeName] of attributeEntries) {
        if (attributeNames.has(attributeName)) {
          state.findings.push(finding(
            "MINIAPP_JSX_DUPLICATE_ATTRIBUTE",
            `${tag} repeats JSX attribute ${attributeName}; overwrite order cannot be preserved by the bounded component IR.`,
            "C",
            [nodeRef(node)],
          ));
        }
        attributeNames.add(attributeName);
      }
      const attributes = Object.fromEntries(attributeEntries);
      const attrs = Object.keys(attributes);
      const events = attrs.filter(name => /^on[A-Z]/.test(name)).sort();
      const accessibility = attrs.filter(name => /^(?:aria-|role|tabIndex)/.test(name)).sort();
      const name = /^[a-z]/.test(tag) ? `${tag}-${absoluteStart(node)}` : tag;
      if (implicitHtmlSemanticTags.has(tag.toLowerCase())) {
        state.findings.push(finding(
          "MINIAPP_HTML_IMPLICIT_SEMANTICS_NOT_LOWERED",
          `${tag} carries implicit landmark, heading, label, or list accessibility semantics that are not represented by the target component profile.`,
          "C",
          [nodeRef(node)],
        ));
      }
      const jsxElement = ts.isJsxOpeningElement(node) && ts.isJsxElement(node.parent) ? node.parent : undefined;
      const textContent = jsxElement
        ? jsxElement.children.filter(ts.isJsxText).map(item => item.text).join(" ").replace(/\s+/gu, " ").trim()
        : "";
      const children = jsxElement
        ? jsxElement.children.flatMap(child => {
          const opening = ts.isJsxElement(child) ? child.openingElement : ts.isJsxSelfClosingElement(child) ? child : undefined;
          if (!opening) return [];
          const childTag = opening.tagName.getText(file);
          const childName = /^[a-z]/.test(childTag) ? `${childTag}-${absoluteStart(opening)}` : childTag;
          return [stableId("component", path, childName)];
        })
        : [];
      if (!state.components.some(item => item.id === stableId("component", path, name))) {
        state.components.push({
          id: stableId("component", path, name),
          name,
          semanticRole: semanticRole(tag),
          sourceKind: "ast",
          props: attrs.filter(item => !/^on[A-Z]/.test(item)).sort(),
          events,
          children,
          accessibility,
          ...analyzedComponentBindings(tag, attributes, textContent),
          sourceRefs: [nodeRef(node)],
        });
      }
      if (jsxElement?.children.some(child => ts.isJsxExpression(child) && child.expression
        && !ts.isStringLiteral(child.expression) && !ts.isNumericLiteral(child.expression))) {
        state.findings.push(finding(
          "MINIAPP_JSX_CHILD_EXPRESSION_UNRESOLVED",
          `${tag} has a dynamic JSX child expression that is not represented by the bounded interaction model.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (jsxElement && textContent && jsxElement.children.some(child => ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child))) {
        state.findings.push(finding(
          "MINIAPP_ORDERED_MIXED_CONTENT_UNRESOLVED",
          `${tag} interleaves direct JSX text and child elements; ordered content must be lowered before generation.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (node.attributes.properties.some(ts.isJsxSpreadAttribute)) {
        state.findings.push(finding(
          "MINIAPP_JSX_SPREAD_ATTRIBUTES_UNRESOLVED",
          `${tag} uses spread attributes that require typed value resolution before target generation.`,
          "C",
          [nodeRef(node)],
        ));
      }
      if (tag === "form" || ["input", "textarea", "select"].includes(tag)) {
        const formId = stableId("form", path, `form:${absoluteStart(node)}`);
        if (!state.forms.some(item => item.id === formId)) {
          state.forms.push({
            id: formId,
            name: tag,
            fields: attrs.filter(item => ["name", "value", "checked"].includes(item)).sort(),
            binding: events.includes("onChange") || events.includes("onInput") ? "controlled-event" : "implicit",
            validation: attrs.some(item => ["required", "pattern", "minLength", "maxLength"].includes(item)) ? "declared" : "implicit",
            sourceRefs: [nodeRef(node)],
          });
        }
      }
    }

    ts.forEachChild(node, visit);
  };
  visit(file);

  for (const [name, value] of stateByName) {
    const reads = source.split(name).length - 1;
    state.states.push({ ...value, reads, writes: Math.max(0, reads - 1) });
  }
  if (componentNames.size === 0 && /\.(?:tsx|jsx)$/.test(path)) {
    anonymousComponent += 1;
    state.findings.push(finding(
      "MINIAPP_COMPONENT_NOT_RECOVERED",
      `No named component was recovered from JSX source (${anonymousComponent}).`,
      "C",
      [sourceRef(0, Math.min(source.length, 1))],
    ));
  }
}

function semanticRole(tag: string): string {
  const normalized = tag.toLowerCase();
  if (["script", "style", "head", "title", "base", "meta", "link", "noscript"].includes(normalized)) return "non-render-metadata";
  if (["routerview", "router-view", "outlet"].includes(normalized)) return "route-outlet";
  if (["button"].includes(normalized)) return "button";
  if (["input", "textarea", "select", "picker"].includes(normalized)) return "form-control";
  if (["img", "image", "video"].includes(normalized)) return "media";
  if (["list", "scroll-view", "scrollview", "flatlist"].includes(normalized)) return "list";
  if (["nav", "navigator"].includes(normalized)) return "navigation";
  if (["text", "span", "p", "label", "h1", "h2", "h3", "h4", "h5", "h6"].includes(normalized)) return "text";
  if (["view", "block", "div", "main", "section", "article", "header", "footer", "ul", "ol", "li", "form"].includes(normalized)) return "container";
  return /^[A-Z]/.test(tag) ? "custom-component" : "unsupported-component";
}

function decodeMarkupEntities(value: string): string {
  const named: Readonly<Record<string, string>> = {
    amp: "&", apos: "'", copy: "©", gt: ">", hellip: "…", lt: "<", mdash: "—",
    nbsp: "\u00a0", ndash: "–", quot: "\"", reg: "®", trade: "™",
  };
  const decode = (match: string, decimal: string | undefined, hexadecimal: string | undefined, name: string | undefined): string => {
    if (name) {
      const decoded = named[name.toLowerCase()];
      if (decoded === undefined) throw new Error(`markup entity &${name}; is outside the bounded decoder`);
      return decoded;
    }
    const codePoint = Number.parseInt(decimal ?? hexadecimal ?? "", hexadecimal ? 16 : 10);
    if (!Number.isInteger(codePoint) || codePoint <= 0 || codePoint > 0x10ffff || (codePoint >= 0xd800 && codePoint <= 0xdfff)) {
      throw new Error(`markup numeric entity ${match} is invalid`);
    }
    return String.fromCodePoint(codePoint);
  };
  const terminated = value.replace(/&(?:#(\d+)|#x([a-f0-9]+)|([a-z]+));/giu, decode);
  const legacy = terminated.replace(
    /&(?:#(\d+)|#x([a-f0-9]+)|([a-z]+))(?![A-Za-z0-9=;])/giu,
    decode,
  );
  if (/&(?:#(?:x[a-f0-9]*)?|[A-Za-z][A-Za-z0-9]{1,31})(?![A-Za-z0-9;])/iu.test(legacy)) {
    throw new Error("markup contains an ambiguous unterminated entity outside the bounded decoder");
  }
  return legacy;
}

function parseMarkup(source: string): MarkupTag[] {
  const result: MarkupTag[] = [];
  const stack: number[] = [];
  const textSegments = new Map<number, string[]>();
  let index = 0;
  let line = 1;
  let column = 1;
  const advance = (char: string): void => {
    if (char === "\n") { line += 1; column = 1; } else column += 1;
  };
  while (index < source.length) {
    if (source[index] !== "<") {
      const start = index;
      while (index < source.length && source[index] !== "<") {
        advance(source[index] ?? "");
        index += 1;
      }
      const owner = stack.at(-1);
      if (owner !== undefined) {
        const segment = decodeMarkupEntities(source.slice(start, index)).replace(/\s+/gu, " ").trim();
        if (segment) textSegments.set(owner, [...(textSegments.get(owner) ?? []), segment]);
      }
      continue;
    }
    const tagLine = line;
    const tagColumn = column;
    let cursor = index + 1;
    if (source[cursor] === "/") {
      cursor += 1;
      while (cursor < source.length && /\s/u.test(source[cursor] ?? "")) cursor += 1;
      let closingName = "";
      while (cursor < source.length && /[A-Za-z0-9_.:-]/u.test(source[cursor] ?? "")) {
        closingName += source[cursor];
        cursor += 1;
      }
      while (cursor < source.length && /\s/u.test(source[cursor] ?? "")) cursor += 1;
      if (source[cursor] !== ">" || !closingName) throw new Error("markup contains an invalid closing tag");
      const openIndex = stack.at(-1);
      if (openIndex === undefined || result[openIndex]?.name.toLowerCase() !== closingName.toLowerCase()) {
        throw new Error(`markup closing tag ${closingName} does not match ${openIndex === undefined ? "an empty stack" : result[openIndex]?.name}`);
      }
      stack.pop();
      while (index <= cursor && index < source.length) { advance(source[index] ?? ""); index += 1; }
      continue;
    }
    if (["!", "?"].includes(source[cursor] ?? "")) {
      while (cursor < source.length && source[cursor] !== ">") cursor += 1;
      while (index <= cursor && index < source.length) { advance(source[index] ?? ""); index += 1; }
      continue;
    }
    let name = "";
    while (cursor < source.length && /[A-Za-z0-9_.:-]/.test(source[cursor] ?? "")) {
      name += source[cursor]; cursor += 1;
    }
    const attributes: Record<string, string> = {};
    let quote: string | undefined;
    let buffer = "";
    let attributeName = "";
    let readingValue = false;
    const commitAttribute = (value: string): void => {
      if (!attributeName) throw new Error("markup contains an attribute value without a name");
      if (Object.hasOwn(attributes, attributeName)) {
        throw new Error(`markup contains duplicate attribute ${attributeName}`);
      }
      attributes[attributeName] = value;
      attributeName = "";
      buffer = "";
      readingValue = false;
    };
    while (cursor < source.length) {
      const char = source[cursor] ?? "";
      if (quote) {
        if (char === quote) { commitAttribute(decodeMarkupEntities(buffer)); quote = undefined; }
        else buffer += char;
        cursor += 1;
        continue;
      }
      if (char === "\"" || char === "'") { quote = char; cursor += 1; continue; }
      if (char === ">") {
        if (attributeName) commitAttribute(readingValue ? decodeMarkupEntities(buffer) : "true");
        break;
      }
      if (/\s|\//.test(char)) {
        if (attributeName) commitAttribute(readingValue ? decodeMarkupEntities(buffer) : "true");
        cursor += 1;
        continue;
      }
      if (char === "=") { readingValue = true; cursor += 1; continue; }
      if (readingValue) buffer += char; else attributeName += char;
      cursor += 1;
    }
    if (!name || cursor >= source.length) throw new Error("markup contains an unterminated or invalid tag");
    const parentIndex = stack.at(-1) ?? null;
    const resultIndex = result.length;
    result.push({ name, attributes, line: tagLine, column: tagColumn, textContent: "", mixedContent: false, parentIndex });
    const rawTag = source.slice(index, cursor + 1);
    const selfClosing = /\/\s*>$/u.test(rawTag) || /^(?:input|img|image|br|hr|meta|link)$/iu.test(name);
    if (!selfClosing) stack.push(resultIndex);
    while (index <= cursor) { advance(source[index] ?? ""); index += 1; }
  }
  if (stack.length > 0) {
    const openIndex = stack.at(-1)!;
    throw new Error(`markup tag ${result[openIndex]?.name ?? "unknown"} is not closed`);
  }
  const parentsWithChildren = new Set(result.flatMap((tag, childIndex) => tag.parentIndex === null ? [] : [tag.parentIndex]));
  return result.map((tag, tagIndex) => ({
    ...tag,
    textContent: (textSegments.get(tagIndex) ?? []).join(" "),
    mixedContent: parentsWithChildren.has(tagIndex) && (textSegments.get(tagIndex)?.length ?? 0) > 0,
  }));
}

interface EmbeddedTraceContext {
  readonly source: string;
  readonly lineOffset: number;
  readonly recordParsedFile: boolean;
  readonly parserEvidence?: string;
}

function analyzeMarkup(
  path: string,
  source: string,
  sourceKind: MiniappAnalyzedComponent["sourceKind"],
  state: MutableAnalysis,
  trace?: EmbeddedTraceContext,
): void {
  const ref = (line: number, column = 1): MiniappSourceRef =>
    lineRef(path, trace?.source ?? source, (trace?.lineOffset ?? 0) + line, column);
  try {
    const tags = parseMarkup(source);
    const componentIds = tags.map(tag => stableId("component", path, `${tag.name}:${tag.line}:${tag.column}`));
    const children = new Map<number, string[]>();
    tags.forEach((tag, index) => {
      if (tag.parentIndex !== null) children.set(tag.parentIndex, [...(children.get(tag.parentIndex) ?? []), componentIds[index]!]);
    });
    for (const [tagIndex, tag] of tags.entries()) {
      const attrs = Object.keys(tag.attributes).sort();
      const events = attrs.filter(name => /^(?:@|v-on:|on|bind|catch)/.test(name));
      const accessibility = attrs.filter(name => /^(?:aria-|role|tabindex)/i.test(name));
      const analyzedComponent: MiniappAnalyzedComponent = {
        id: componentIds[tagIndex]!,
        name: `${tag.name}@${tag.line}:${tag.column}`,
        semanticRole: tag.attributes["v-for"] || Object.keys(tag.attributes).some(name => /^(?:wx|a|tt|xhs):for$/u.test(name))
          ? "list"
          : semanticRole(tag.name),
        sourceKind,
        props: attrs.filter(name => !events.includes(name)),
        events,
        children: children.get(tagIndex) ?? [],
        accessibility,
        ...analyzedComponentBindings(tag.name, tag.attributes, tag.textContent),
        sourceRefs: [ref(tag.line, tag.column)],
      };
      state.components.push(analyzedComponent);
      if (analyzedComponent.collectionBinding
        && analyzedComponent.collectionBinding.valueExpression !== analyzedComponent.collectionBinding.itemAlias) {
        state.findings.push(finding(
          "MINIAPP_LIST_ITEM_CONTENT_UNRESOLVED",
          `${tag.name} collection item content is not one exact direct {{${analyzedComponent.collectionBinding.itemAlias}}} interpolation; nested or mixed list semantics are not lowered by the bounded generator.`,
          "D",
          [ref(tag.line, tag.column)],
          "error",
          true,
        ));
      }
      if (implicitHtmlSemanticTags.has(tag.name.toLowerCase())) {
        state.findings.push(finding(
          "MINIAPP_HTML_IMPLICIT_SEMANTICS_NOT_LOWERED",
          `${tag.name} carries implicit landmark, heading, label, or list accessibility semantics that are not represented by the target component profile.`,
          "C",
          [ref(tag.line, tag.column)],
        ));
      }
      if (tag.mixedContent) {
        state.findings.push(finding(
          "MINIAPP_ORDERED_MIXED_CONTENT_UNRESOLVED",
          `${tag.name} interleaves direct text and child nodes; ordered content must be lowered before generation.`,
          "C",
          [ref(tag.line, tag.column)],
        ));
      }
      if (tag.name === "form" || ["input", "textarea", "picker", "select"].includes(tag.name)) {
        state.forms.push({
          id: stableId("form", path, `${tag.name}:${tag.line}:${tag.column}`),
          name: tag.attributes.name || tag.name,
          fields: attrs.filter(name => ["name", "value", "checked", "v-model"].includes(name)),
          binding: attrs.some(name => /model|input|change/.test(name)) ? "template-event-binding" : "implicit",
          validation: attrs.some(name => /required|pattern|min|max/.test(name)) ? "declared" : "implicit",
          sourceRefs: [ref(tag.line, tag.column)],
        });
      }
      if (tag.name === "web-view") {
        state.findings.push(finding(
          "MINIAPP_WEBVIEW_REQUIRES_APPROVAL",
          "A WebView cannot be used as an undeclared native-conversion fallback.",
          "D",
          [ref(tag.line, tag.column)],
          "error",
          true,
        ));
      }
      if (tag.name === "canvas") {
        const node = syntheticNode(path, source, tag.line);
        addCapability(state, path, source, "render.canvas", "rendering", node, false, ref(tag.line, tag.column));
      }
    }
    if (trace?.recordParsedFile !== false) state.parsedFiles.add(path);
    state.parserEvidence.add(trace?.parserEvidence
      ?? (sourceKind === "native-template" ? "native-template-parser" : "deterministic-markup-parser"));
  } catch (error) {
    state.failedFiles.add(path);
    state.findings.push(finding(
      "MINIAPP_TEMPLATE_PARSE_FAILED",
      error instanceof Error ? error.message : String(error),
      "D",
      [ref(1)],
      "error",
      true,
    ));
  }
}

function resolveLocalHtmlScriptPath(htmlPath: string, sourceAttribute: string): string | null {
  const withoutQuery = sourceAttribute.split(/[?#]/u, 1)[0] ?? "";
  if (!withoutQuery || /^(?:[A-Za-z][A-Za-z0-9+.-]*:|\/\/)/u.test(withoutQuery)) return null;
  const parts = (withoutQuery.startsWith("/") ? withoutQuery.slice(1) : `${htmlPath.slice(0, htmlPath.lastIndexOf("/") + 1)}${withoutQuery}`)
    .split("/");
  const normalized: string[] = [];
  for (const part of parts) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (normalized.length === 0) return null;
      normalized.pop();
    } else normalized.push(part);
  }
  return normalized.join("/") || null;
}

function analyzeHtmlScripts(path: string, source: string, state: MutableAnalysis, files: SourceFiles): void {
  const pattern = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/giu;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    const attributes = match[1] ?? "";
    const body = match[2] ?? "";
    const sourceAttribute = /\bsrc\s*=\s*["']([^"']+)["']/iu.exec(attributes)?.[1];
    if (sourceAttribute) {
      const localPath = resolveLocalHtmlScriptPath(path, sourceAttribute);
      if (localPath && Object.hasOwn(files, localPath) && /\btype\s*=\s*["']module["']/iu.test(attributes)) continue;
      state.findings.push(finding(
        "MINIAPP_H5_EXTERNAL_SCRIPT_LINK_REQUIRES_RESOLUTION",
        `HTML script source ${sourceAttribute} must be inventory-bound and analyzed before generation.`,
        "C",
        [positionRef(path, source, match.index, match.index + match[0].length)],
      ));
      continue;
    }
    if (!body.trim()) continue;
    const bodyOffset = match.index + match[0].indexOf(body);
    analyzeTypeScript(path, body, state, {
      source,
      offset: bodyOffset,
      scriptKind: /\btype\s*=\s*["'](?:module|text\/typescript)["']/iu.test(attributes)
        ? ts.ScriptKind.TS
        : ts.ScriptKind.JS,
      recordParsedFile: false,
    });
  }
}

function syntheticNode(path: string, source: string, line: number): ts.Node {
  const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true);
  const offset = source.split("\n").slice(0, Math.max(0, line - 1)).reduce((total, item) => total + item.length + 1, 0);
  const node = file.statements.find(item => item.getStart() >= offset) ?? file;
  return node;
}

function analyzeVue2(path: string, source: string, state: MutableAnalysis): void {
  const result = parseVueSfc(source, { filename: path });
  state.parserEvidence.add("@vue/compiler-sfc@3.5.39-vue2-compat");
  if (result.errors.length > 0) {
    state.failedFiles.add(path);
    state.findings.push(finding(
      "MINIAPP_VUE2_SFC_PARSE_FAILED",
      `Vue 2-compatible SFC parsing reported ${result.errors.length} error(s).`,
      "D",
      [lineRef(path, source, 1)],
      "error",
      true,
    ));
    return;
  }
  const descriptor = result.descriptor;
  if (descriptor.script) {
    analyzeTypeScript(path, descriptor.script.content, state, {
      source,
      offset: descriptor.script.loc.start.offset,
      scriptKind: descriptor.script.lang === "js" ? ts.ScriptKind.JS : ts.ScriptKind.TS,
      recordParsedFile: false,
    });
  }
  if (descriptor.template) {
    const compiled = compileTemplate({
      id: stableId("vue2-template", path, "template"),
      filename: path,
      source: descriptor.template.content,
    });
    if (compiled.errors.length > 0) {
      state.failedFiles.add(path);
      state.findings.push(finding(
        "MINIAPP_VUE2_TEMPLATE_COMPILE_FAILED",
        `Vue 2-compatible template compiler reported ${compiled.errors.length} error(s).`,
        "D",
        [lineRef(path, source, 1)],
        "error",
        true,
      ));
    } else {
      const lineOffset = Math.max(0, descriptor.template.loc.start.line - 1);
      analyzeMarkup(path, descriptor.template.content, "template-ast", state, {
        source,
        lineOffset,
        recordParsedFile: false,
        parserEvidence: "@vue/compiler-sfc-template@3.5.39-vue2-compat",
      });
    }
  }
  for (const block of descriptor.styles) {
    const lineOffset = Math.max(0, block.loc.start.line - 1);
    const scopedStyle = block as typeof block & { readonly scoped?: boolean; readonly module?: string | boolean };
    if (scopedStyle.scoped || scopedStyle.module) {
      state.findings.push(finding(
        "MINIAPP_SCOPED_STYLE_NOT_LOWERED",
        "Vue scoped/module style ownership requires deterministic scope selectors and matching template attributes before target emission.",
        "C",
        [lineRef(path, source, Math.max(1, lineOffset + 1))],
      ));
      continue;
    }
    if (block.lang && block.lang !== "css") {
      state.findings.push(finding(
        "MINIAPP_STYLE_PREPROCESSOR_NOT_RUN",
        `${block.lang} style semantics require the exact source preprocessor and are not parsed as CSS.`,
        "C",
        [lineRef(path, source, Math.max(1, lineOffset + 1))],
      ));
      continue;
    }
    analyzeCss(path, block.content, state, { source, lineOffset, recordParsedFile: false });
  }
  state.parsedFiles.add(path);
}

function analyzeVue(path: string, source: string, state: MutableAnalysis, sourceLabel: MiniappSourceLabel): void {
  if (sourceLabel === "vue2") {
    analyzeVue2(path, source, state);
    return;
  }
  const result = parseVueSfc(source, { filename: path });
  if (result.errors.length > 0) {
    state.failedFiles.add(path);
    state.findings.push(finding(
      "MINIAPP_VUE_SFC_PARSE_FAILED",
      `Vue SFC compiler reported ${result.errors.length} error(s).`,
      "D",
      [lineRef(path, source, 1)],
      "error",
      true,
    ));
    return;
  }
  state.parserEvidence.add("@vue/compiler-sfc");
  const descriptor = result.descriptor;
  const scriptBlocks = [descriptor.script, descriptor.scriptSetup].filter((item): item is NonNullable<typeof item> => item !== null);
  for (const block of scriptBlocks) {
    const language = block.lang?.toLowerCase();
    const kind = language === "tsx" ? ts.ScriptKind.TSX
      : language === "jsx" ? ts.ScriptKind.JSX
        : language === "js" ? ts.ScriptKind.JS
          : ts.ScriptKind.TS;
    analyzeTypeScript(path, block.content, state, {
      source,
      offset: block.loc.start.offset,
      scriptKind: kind,
      recordParsedFile: false,
    });
  }
  if (descriptor.template) {
    const compiled = compileTemplate({
      id: stableId("vue-template", path, "template"),
      filename: path,
      source: descriptor.template.content,
    });
    if (compiled.errors.length > 0) {
      state.failedFiles.add(path);
      state.findings.push(finding(
        "MINIAPP_VUE_TEMPLATE_COMPILE_FAILED",
        `Vue template compiler reported ${compiled.errors.length} error(s).`,
        "D",
        [lineRef(path, source, descriptor.template.loc.start.line)],
        "error",
        true,
      ));
    } else {
      analyzeMarkup(path, descriptor.template.content, "template-ast", state, {
        source,
        lineOffset: Math.max(0, descriptor.template.loc.start.line - 1),
        recordParsedFile: false,
        parserEvidence: "@vue/compiler-sfc-template@3.5.39",
      });
    }
  }
  for (const block of descriptor.styles) {
    if (block.scoped || block.module) {
      state.findings.push(finding(
        "MINIAPP_SCOPED_STYLE_NOT_LOWERED",
        "Vue scoped/module style ownership requires deterministic scope selectors and matching template attributes before target emission.",
        "C",
        [lineRef(path, source, Math.max(1, block.loc.start.line))],
      ));
      continue;
    }
    if (block.lang && block.lang !== "css") {
      state.findings.push(finding(
        "MINIAPP_STYLE_PREPROCESSOR_NOT_RUN",
        `${block.lang} style semantics require the exact source preprocessor and are not parsed as CSS.`,
        "C",
        [lineRef(path, source, Math.max(1, block.loc.start.line))],
      ));
      continue;
    }
    analyzeCss(path, block.content, state, {
      source,
      lineOffset: Math.max(0, block.loc.start.line - 1),
      recordParsedFile: false,
    });
  }
  state.parsedFiles.add(path);
}

function boundedCssSelector(value: string): boolean {
  const compound = /^(?:\*|[A-Za-z][A-Za-z0-9-]*)?(?:[.#][A-Za-z_][A-Za-z0-9_-]*)*$/u;
  return value.split(",").every(rawSelector => {
    const selector = rawSelector.trim();
    if (!selector || !/^[A-Za-z0-9_*#. +>~-]+$/u.test(selector)
      || /(?:^|[>+~])\s*(?:[>+~]|$)/u.test(selector)) return false;
    const parts = selector.split(/\s*(?:[>+~]|\s+)\s*/u).filter(Boolean);
    return parts.length > 0 && parts.every(part => compound.test(part) && part.length > 0);
  });
}

function boundedCssValue(value: string): boolean {
  if (!value || !/^[A-Za-z0-9#%.,\s_'"/()+*!-]+$/u.test(value)) return false;
  const withoutImportant = value.replace(/\s*!important\s*$/iu, "").trim();
  if (!withoutImportant || withoutImportant.includes("!")) return false;
  let depth = 0;
  let quote: "'" | "\"" | undefined;
  const functionStack: Array<{ name: string; contentStart: number }> = [];
  const supportedFunctions = new Set([
    "calc", "clamp", "env", "hsl", "hsla", "linear-gradient", "max", "min", "minmax",
    "radial-gradient", "repeat", "rgb", "rgba", "rotate", "scale", "translate", "translatex",
    "translatey", "url", "var",
  ]);
  for (let index = 0; index < withoutImportant.length; index += 1) {
    const char = withoutImportant[index]!;
    if (quote) {
      if (char === quote && withoutImportant[index - 1] !== "\\") quote = undefined;
      continue;
    }
    if (char === "'" || char === "\"") { quote = char; continue; }
    if (char === "(") {
      const prefix = withoutImportant.slice(0, index);
      const match = /([A-Za-z][A-Za-z0-9-]*)\s*$/u.exec(prefix);
      if (!match || !supportedFunctions.has(match[1]!.toLowerCase())) return false;
      depth += 1;
      functionStack.push({ name: match[1]!.toLowerCase(), contentStart: index + 1 });
    }
    else if (char === ")") {
      depth -= 1;
      if (depth < 0) return false;
      const current = functionStack.pop();
      if (!current) return false;
      const content = withoutImportant.slice(current.contentStart, index).trim();
      if (!content || /^,|,$|,\s*,/u.test(content)) return false;
    }
  }
  if (quote !== undefined || depth !== 0) return false;
  return !/(?:\(\s*[+*/]|[+\-*/]\s*\))/u.test(withoutImportant);
}

function analyzeCss(path: string, source: string, state: MutableAnalysis, trace?: EmbeddedTraceContext): void {
  const ref = (line: number): MiniappSourceRef =>
    lineRef(path, trace?.source ?? source, (trace?.lineOffset ?? 0) + line);
  let selector = "";
  let property = "";
  let value = "";
  let mode: "selector" | "property" | "value" = "selector";
  let quote: string | undefined;
  let comment = false;
  const declarations: Record<string, string> = {};
  let blockLine = 1;
  let line = 1;
  if (/@[A-Za-z_-][A-Za-z0-9_-]*/u.test(source)) {
    state.findings.push(finding(
      "MINIAPP_CSS_AT_RULE_REQUIRES_AST",
      "CSS imports and at-rules require a standards-compliant CSS AST and asset/module resolution before target lowering.",
      "C",
      [ref(1)],
    ));
  }
  if (/\{[^{}]*\{/su.test(source) || /(?:^|[;{])\s*&(?:[:.#\[]|\s)/mu.test(source)) {
    state.findings.push(finding(
      "MINIAPP_CSS_NESTING_REQUIRES_AST",
      "Nested selector syntax is outside the bounded flat-CSS parser and will not be emitted as a declaration.",
      "C",
      [ref(1)],
    ));
  }
  const flush = (): void => {
    const clean = selector.trim();
    if (!clean) return;
    if (!boundedCssSelector(clean)) {
      state.findings.push(finding(
        "MINIAPP_CSS_SELECTOR_UNRESOLVED",
        `CSS selector ${clean} is outside the bounded tag/class/id/combinator grammar.`,
        "C",
        [ref(blockLine)],
      ));
      selector = ""; property = ""; value = "";
      for (const key of Object.keys(declarations)) delete declarations[key];
      mode = "selector";
      return;
    }
    state.styles.push({
      id: stableId("style", path, `${clean}:${(trace?.lineOffset ?? 0) + blockLine}`),
      selector: clean,
      declarations: Object.fromEntries(Object.entries(declarations).sort(([a], [b]) => a.localeCompare(b, "en-US"))),
      responsive: clean.startsWith("@media") || source.includes("@media"),
      sourceRefs: [ref(blockLine)],
    });
    selector = ""; property = ""; value = "";
    for (const key of Object.keys(declarations)) delete declarations[key];
    mode = "selector";
  };
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index] ?? "";
    const next = source[index + 1] ?? "";
    if (char === "\n") line += 1;
    if (comment) { if (char === "*" && next === "/") { comment = false; index += 1; } continue; }
    if (!quote && char === "/" && next === "*") { comment = true; index += 1; continue; }
    if (quote) { if (char === quote && source[index - 1] !== "\\") quote = undefined; if (mode === "value") value += char; continue; }
    if (char === "\"" || char === "'") { quote = char; if (mode === "value") value += char; continue; }
    if (mode === "selector") {
      if (char === "{") { mode = "property"; blockLine = line; }
      else if (char === "}") {
        state.findings.push(finding("MINIAPP_CSS_DECLARATION_UNRESOLVED", "CSS contains a closing brace without an open declaration block.", "C", [ref(line)]));
        selector = "";
      }
      else selector += char;
    } else if (mode === "property") {
      if (char === ":") mode = "value";
      else if (char === ";") {
        if (property.trim()) state.findings.push(finding("MINIAPP_CSS_DECLARATION_UNRESOLVED", `CSS declaration ${property.trim()} is missing a colon and value.`, "C", [ref(line)]));
        property = "";
      }
      else if (char === "{") {
        state.findings.push(finding("MINIAPP_CSS_NESTING_REQUIRES_AST", "CSS contains a nested declaration block.", "C", [ref(line)]));
      }
      else if (char === "}") {
        if (property.trim()) state.findings.push(finding("MINIAPP_CSS_DECLARATION_UNRESOLVED", `CSS declaration ${property.trim()} is missing a colon and value.`, "C", [ref(line)]));
        flush();
      }
      else property += char;
    } else if (char === ";" || char === "}") {
      const key = property.trim();
      const cleanValue = value.trim();
      if (!key || !cleanValue) {
        state.findings.push(finding(
          "MINIAPP_CSS_DECLARATION_UNRESOLVED",
          `CSS declaration requires a non-empty property and value (property=${key || "missing"}, value=${cleanValue ? "present" : "missing"}).`,
          "C",
          [ref(line)],
        ));
      } else {
        if (!/^(?:--[A-Za-z0-9_-]+|-?[A-Za-z][A-Za-z0-9-]*)$/u.test(key)) {
          state.findings.push(finding(
            "MINIAPP_CSS_DECLARATION_UNRESOLVED",
            `CSS declaration name ${key} is not valid in the bounded flat-CSS grammar.`,
            "C",
            [ref(line)],
          ));
        } else if (!boundedCssValue(cleanValue)) {
          state.findings.push(finding(
            "MINIAPP_CSS_VALUE_UNRESOLVED",
            `CSS value for ${key} is outside the balanced bounded value grammar.`,
            "C",
            [ref(line)],
          ));
        } else {
          declarations[key] = cleanValue;
        }
      }
      property = ""; value = "";
      if (char === "}") flush(); else mode = "property";
    } else {
      if (char === "{") state.findings.push(finding("MINIAPP_CSS_NESTING_REQUIRES_AST", "CSS contains a nested value block.", "C", [ref(line)]));
      value += char;
    }
  }
  if (comment || quote || mode !== "selector" || selector.trim()) {
    state.findings.push(finding("MINIAPP_CSS_PARSE_INCOMPLETE", "CSS has an unclosed comment, string, or block.", "C", [ref(line)]));
  }
  if (trace?.recordParsedFile !== false) state.parsedFiles.add(path);
  state.parserEvidence.add("deterministic-css-parser");
}

function tokenizeDart(source: string): DartToken[] {
  const result: DartToken[] = [];
  let index = 0;
  let line = 1;
  let column = 1;
  const advance = (char: string): void => { if (char === "\n") { line += 1; column = 1; } else column += 1; };
  while (index < source.length) {
    const char = source[index] ?? "";
    const next = source[index + 1] ?? "";
    if (/\s/.test(char)) { advance(char); index += 1; continue; }
    if (char === "/" && next === "/") { while (index < source.length && source[index] !== "\n") { advance(source[index] ?? ""); index += 1; } continue; }
    if (char === "/" && next === "*") {
      advance(char); advance(next); index += 2;
      while (index < source.length && !(source[index] === "*" && source[index + 1] === "/")) { advance(source[index] ?? ""); index += 1; }
      if (index >= source.length) throw new Error("unterminated Dart comment");
      advance("*"); advance("/"); index += 2; continue;
    }
    const tokenLine = line; const tokenColumn = column;
    if (char === "\"" || char === "'") {
      const quote = char; let value = char; advance(char); index += 1; let closed = false;
      while (index < source.length) {
        const item = source[index] ?? ""; value += item; advance(item); index += 1;
        if (item === "\\" && index < source.length) { value += source[index] ?? ""; advance(source[index] ?? ""); index += 1; }
        else if (item === quote) { closed = true; break; }
      }
      if (!closed) throw new Error("unterminated Dart string");
      result.push({ value, line: tokenLine, column: tokenColumn }); continue;
    }
    if (/[A-Za-z_$]/.test(char)) {
      let value = char; advance(char); index += 1;
      while (index < source.length && /[A-Za-z0-9_$]/.test(source[index] ?? "")) { value += source[index]; advance(source[index] ?? ""); index += 1; }
      result.push({ value, line: tokenLine, column: tokenColumn }); continue;
    }
    result.push({ value: char, line: tokenLine, column: tokenColumn }); advance(char); index += 1;
  }
  return result;
}

function analyzeDart(path: string, source: string, state: MutableAnalysis): void {
  try {
    const tokens = tokenizeDart(source);
    state.parserEvidence.add("dart-token-model-v1");
    state.findings.push(finding(
      "MINIAPP_DART_NATIVE_ANALYZER_NOT_RUN",
      "A deterministic Dart token model ran, but native Dart analyzer/type-resolution evidence remains NOT_RUN.",
      "C",
      [lineRef(path, source, 1)],
      "warning",
      false,
    ));
    for (let index = 0; index < tokens.length; index += 1) {
      const token = tokens[index];
      if (!token) continue;
      if (token.value === "class" && tokens[index + 1] && tokens[index + 2]?.value === "extends") {
        const name = tokens[index + 1]!.value;
        const base = tokens[index + 3]?.value ?? "unknown";
        if (["StatelessWidget", "StatefulWidget"].includes(base)) {
          state.components.push({
            id: stableId("component", path, name), name, semanticRole: "view-component", sourceKind: "dart-token-model",
            props: [], events: [], children: [], accessibility: [], ...analyzedComponentBindings(name, {}),
            sourceRefs: [lineRef(path, source, token.line, token.column)],
          });
        }
      }
      if (["Navigator", "GoRouter", "MaterialApp"].includes(token.value)) {
        state.routes.push({
          id: stableId("route", path, `${token.value}:${token.line}:${token.column}`), path: "/", component: token.value,
          parameters: [], guards: [], sourceRefs: [lineRef(path, source, token.line, token.column)],
        });
      }
      if (["setState", "notifyListeners", "emit"].includes(token.value)) {
        state.states.push({
          id: stableId("state", path, `${token.value}:${token.line}:${token.column}`), name: token.value, scope: "component",
          stateType: "unknown", reads: 1, writes: 1, sourceRefs: [lineRef(path, source, token.line, token.column)],
        });
      }
      if (["initState", "dispose", "didChangeDependencies"].includes(token.value)) {
        state.effects.push({
          id: stableId("effect", path, `${token.value}:${token.line}:${token.column}`), name: token.value, trigger: token.value,
          asynchronous: false, cleanup: token.value === "dispose" ? "present" : "not-applicable",
          sourceRefs: [lineRef(path, source, token.line, token.column)],
        });
      }
      if (["MethodChannel", "EventChannel", "BasicMessageChannel"].includes(token.value)) {
        state.capabilities.push({
          id: stableId("capability", path, `${token.value}:${token.line}:${token.column}`), name: `flutter.${token.value}`,
          category: "platform-channel", sensitive: true, sourceRefs: [lineRef(path, source, token.line, token.column)],
        });
        state.findings.push(finding(
          "MINIAPP_FLUTTER_PLATFORM_CHANNEL_REQUIRES_DECISION",
          `${token.value} requires an explicit platform capability decision.`,
          "D",
          [lineRef(path, source, token.line, token.column)],
          "error",
          true,
        ));
      }
    }
    state.parsedFiles.add(path);
  } catch (error) {
    state.failedFiles.add(path);
    state.findings.push(finding(
      "MINIAPP_DART_TOKENIZATION_FAILED",
      error instanceof Error ? error.message : String(error),
      "D",
      [lineRef(path, source, 1)],
      "error",
      true,
    ));
  }
}

function analyzeNativeConfig(
  path: string,
  source: string,
  state: MutableAnalysis,
  sourceLabel: MiniappSourceLabel,
): void {
  const configName = path.split("/").at(-1) ?? path;
  const previous = state.nativeConfigFiles.get(configName);
  state.nativeConfigFiles.set(configName, path);
  const configRef = lineRef(path, source, 1);
  const invalid = (message: string): void => {
    state.nativeConfigInvalid.add(path);
    state.findings.push(finding(
      "MINIAPP_NATIVE_CONFIG_INVALID",
      message,
      "D",
      [configRef],
      "error",
      true,
    ));
  };
  try {
    const parsed = JSON.parse(source) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      invalid("configuration root must be an object");
    } else if (previous && previous !== path) {
      invalid(`${configName} is declared more than once (${previous}, ${path}); one authoritative configuration is required.`);
    } else {
      const record = parsed as Readonly<Record<string, unknown>>;
      const expectedSchema = sourceLabel === "uni-app" && configName === "pages.json"
        ? "uni-pages"
        : sourceLabel === "native-miniapp" && configName === "app.json"
          ? "native-app"
          : "unsupported";
      const unknownKeys = Object.keys(record).filter(key => key !== "pages");
      if (expectedSchema === "unsupported") {
        invalid(`${configName} is not a supported source configuration for ${sourceLabel}; only native-miniapp/app.json or uni-app/pages.json are accepted.`);
      } else if (unknownKeys.length > 0) {
        invalid(`${configName} contains unmodeled configuration key(s): ${unknownKeys.sort().join(", ")}.`);
      } else if (!Array.isArray(record.pages) || record.pages.length === 0) {
        invalid(`${configName}.pages must be a non-empty array.`);
      } else if (expectedSchema === "native-app") {
        const pageItems = record.pages.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
        if (pageItems.length !== record.pages.length) {
          invalid(`${configName}.pages entries must be non-empty strings.`);
        } else {
          for (const item of pageItems) {
            const routePath = item.startsWith("/") ? item : `/${item}`;
            state.routes.push({
              id: stableId("route", path, routePath), path: routePath, component: item, componentModule: item, parameters: [], guards: [],
              sourceRefs: [configRef],
            });
          }
        }
      } else {
        const pageItems = record.pages.filter((item): item is Record<string, unknown> =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item));
        const validPages = pageItems.length === record.pages.length
          && pageItems.every(item => Object.keys(item).length === 1
            && typeof item.path === "string"
            && item.path.trim().length > 0
            && !item.path.startsWith("/"));
        if (!validPages) {
          invalid(`${configName}.pages entries must be objects with exactly one non-empty relative path property.`);
        } else {
          for (const item of pageItems) {
            const routePath = `/${item.path as string}`;
            state.routes.push({
              id: stableId("route", path, routePath), path: routePath, component: item.path as string, componentModule: item.path as string, parameters: [], guards: [],
              sourceRefs: [configRef],
            });
          }
        }
      }
    }
    state.parsedFiles.add(path);
    state.parserEvidence.add("json-parser");
  } catch (error) {
    state.failedFiles.add(path);
    state.nativeConfigInvalid.add(path);
    state.findings.push(finding(
      "MINIAPP_NATIVE_CONFIG_INVALID",
      error instanceof Error ? error.message : String(error),
      "D",
      [configRef],
      "error",
      true,
    ));
  }
}

function readDependencies(files: SourceFiles): readonly string[] {
  const names = new Set<string>();
  const packageJson = files["package.json"];
  if (packageJson) {
    try {
      const parsed = JSON.parse(packageJson) as Readonly<Record<string, unknown>>;
      for (const key of ["dependencies", "devDependencies", "peerDependencies"] as const) {
        const section = parsed[key];
        if (section && typeof section === "object" && !Array.isArray(section)) Object.keys(section).forEach(name => names.add(name));
      }
    } catch { /* inventory already owns malformed package reporting */ }
  }
  const pubspec = files["pubspec.yaml"];
  if (pubspec) {
    let inDependencies = false;
    for (const line of pubspec.split("\n")) {
      if (/^dependencies:\s*$/.test(line)) { inDependencies = true; continue; }
      if (inDependencies && /^\S/.test(line) && !line.startsWith("#")) inDependencies = false;
      const match = inDependencies ? /^\s{2}([A-Za-z0-9_-]+):/.exec(line) : null;
      if (match?.[1]) names.add(match[1]);
    }
  }
  return [...names].sort((left, right) => left.localeCompare(right, "en-US"));
}

function deduplicate<T extends { readonly id: string }>(items: readonly T[]): readonly T[] {
  const byId = new Map<string, T>();
  for (const item of items) if (!byId.has(item.id)) byId.set(item.id, item);
  return [...byId.values()].sort((left, right) => left.id.localeCompare(right.id, "en-US"));
}

function semanticPathTail(value: string): string {
  return value.trim().replace(/^this\./u, "").replace(/\.value$/u, "").split(".").at(-1) ?? value;
}

function modeledStateExpression(value: string): string | null {
  const normalized = value.trim().replace(/^this\./u, "").replace(/\.value$/u, "");
  return /^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$/u.test(normalized) ? normalized : null;
}

export function miniappRuntimeStateKey(value: string): string | null {
  const normalized = modeledStateExpression(value);
  if (!normalized || normalized.includes(".")) return null;
  return ["__proto__", "constructor", "prototype"].includes(normalized) ? null : normalized;
}

function moduleResolvesToSource(callerPath: string, moduleSpecifier: string, targetPath: string): boolean {
  if (!moduleSpecifier.startsWith(".")) return false;
  const segments = callerPath.split("/").slice(0, -1);
  for (const part of moduleSpecifier.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (segments.length === 0) return false;
      segments.pop();
    } else {
      segments.push(part);
    }
  }
  const withoutSourceExtension = (value: string): string => value
    .replace(/\.(?:[cm]?[jt]sx?|vue)$/u, "")
    .replace(/\/index$/u, "");
  return withoutSourceExtension(segments.join("/")) === withoutSourceExtension(targetPath);
}

function collectFrameworkExports(files: SourceFiles, state: MutableAnalysis): void {
  for (const [path, source] of Object.entries(files)) {
    if (!/\.(?:[cm]?[jt]sx?)$/u.test(path)) continue;
    const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, scriptKind(path));
    const imports = new Map<string, { readonly module: string; readonly imported: string }>();
    const collectImports = (node: ts.Node): void => {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
        const module = node.moduleSpecifier.text;
        const clause = node.importClause;
        if (clause?.name) imports.set(clause.name.text, { module, imported: "default" });
        if (clause?.namedBindings && ts.isNamespaceImport(clause.namedBindings)) {
          imports.set(clause.namedBindings.name.text, { module, imported: "*" });
        }
        for (const item of clause?.namedBindings && ts.isNamedImports(clause.namedBindings)
          ? clause.namedBindings.elements : []) {
          imports.set(item.name.text, { module, imported: item.propertyName?.text ?? item.name.text });
        }
      }
      ts.forEachChild(node, collectImports);
    };
    collectImports(file);
    const factoryKind = (expression: ts.Expression): FrameworkFactoryKind | null => {
      let value = expression;
      while (ts.isParenthesizedExpression(value) || ts.isAsExpression(value) || ts.isTypeAssertionExpression(value)) {
        value = value.expression;
      }
      const binding = ts.isIdentifier(value)
        ? imports.get(value.text)
        : ts.isPropertyAccessExpression(value) && ts.isIdentifier(value.expression)
          ? (() => {
            const namespace = imports.get(value.expression.text);
            return namespace?.imported === "*" ? { module: namespace.module, imported: value.name.text } : undefined;
          })()
          : undefined;
      if (binding?.module === "vue" && binding.imported === "createApp") return "vue-app";
      if (binding?.module === "pinia" && binding.imported === "createPinia") return "pinia";
      if (binding?.module === "vue-router" && binding.imported === "createRouter") return "router";
      if (binding?.module === "vue-router" && binding.imported === "createWebHistory") return "router-history-web";
      if (binding?.module === "vue-router" && binding.imported === "createWebHashHistory") return "router-history-hash";
      if (binding?.module === "vue-router" && binding.imported === "createMemoryHistory") return "router-history-memory";
      return null;
    };
    const collectExports = (node: ts.Node): void => {
      if (ts.isVariableStatement(node)
        && node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)) {
        for (const declaration of node.declarationList.declarations) {
          if (!ts.isIdentifier(declaration.name) || !declaration.initializer || !ts.isCallExpression(declaration.initializer)) continue;
          const kind = factoryKind(declaration.initializer.expression);
          if (!kind) continue;
          const key = `${path}#${declaration.name.text}`;
          const binding = { kind, instanceId: stableId("framework-instance", path, `${kind}:${declaration.initializer.getStart()}`) };
          if (state.frameworkExports.has(key)) state.frameworkExports.delete(key);
          else state.frameworkExports.set(key, binding);
        }
      }
      ts.forEachChild(node, collectExports);
    };
    collectExports(file);
  }
}

function miniappRouteModulePath(routeSourcePath: string, moduleSpecifier: string): string | null {
  if (!moduleSpecifier) return null;
  const withoutSourceExtension = (value: string): string => value
    .replace(/\.(?:[cm]?[jt]sx?|vue|html|wxml|axml|ttml|xhsml)$/u, "")
    .replace(/\/index$/u, "");
  if (!moduleSpecifier.startsWith(".")) {
    if (moduleSpecifier === routeSourcePath) return withoutSourceExtension(routeSourcePath);
    if (routeSourcePath.endsWith(".json")
      && !moduleSpecifier.startsWith("/")
      && !moduleSpecifier.includes(":")
      && !moduleSpecifier.split("/").some(part => !part || part === "." || part === "..")) {
      return withoutSourceExtension(moduleSpecifier);
    }
    return null;
  }
  const segments = routeSourcePath.split("/").slice(0, -1);
  for (const part of moduleSpecifier.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (segments.length === 0) return null;
      segments.pop();
    } else {
      segments.push(part);
    }
  }
  return withoutSourceExtension(segments.join("/"));
}

export function resolveMiniappRouteComponentRoots(
  components: readonly MiniappAnalyzedComponent[],
  route: MiniappAnalyzedRoute,
): readonly MiniappAnalyzedComponent[] {
  const withoutSourceExtension = (value: string): string => value
    .replace(/\.(?:[cm]?[jt]sx?|vue|html|wxml|axml|ttml|xhsml)$/u, "")
    .replace(/\/index$/u, "");
  const routeSourcePath = route.sourceRefs[0]?.path ?? "";
  const resolvedModule = route.componentModule ? miniappRouteModulePath(routeSourcePath, route.componentModule) : null;
  if (route.componentModule && resolvedModule === null) return [];
  const normalizedName = route.component.replace(/[^A-Za-z0-9_$-]/gu, "").toLowerCase();
  const candidates = components.filter(component => component.sourceRefs.some(ref => {
    if (resolvedModule) return withoutSourceExtension(ref.path) === resolvedModule;
    const stem = (ref.path.split("/").at(-1) ?? ref.path).replace(/\.[^.]+$/u, "").toLowerCase();
    return component.name === route.component
      || component.sourceTag === route.component
      || (Boolean(normalizedName) && stem === normalizedName);
  }));
  const named = candidates.filter(component => component.name === route.component || component.sourceTag === route.component);
  if (named.length === 1) return named;
  if (named.length > 1) return [];
  const childIds = new Set(candidates.flatMap(component => component.children));
  const roots = candidates.filter(component => !childIds.has(component.id)
    && component.semanticRole !== "non-render-metadata"
    && component.semanticRole !== "route-outlet");
  return roots.length === 1 ? roots : [];
}

function reconstructInteractions(state: MutableAnalysis): readonly MiniappAnalyzedInteraction[] {
  const inputs = state.components.filter(component => component.semanticRole === "form-control" && component.modelBinding);
  const submits = state.components.filter(component => component.semanticRole === "button"
    && component.eventBindings.some(binding => binding.event === "click" || binding.event === "tap"));
  const lists = state.components.filter(component => component.collectionBinding);
  const interactions: MiniappAnalyzedInteraction[] = [];
  for (const input of inputs) {
    const inputPath = input.sourceRefs[0]?.path;
    if (!inputPath) continue;
    const draftState = semanticPathTail(input.modelBinding ?? "");
    const draftStates = state.states.filter(candidate => semanticPathTail(candidate.name) === draftState
      && candidate.sourceRefs.some(ref => ref.path === inputPath));
    if (draftStates.length !== 1) continue;
    const draftInitial = state.stateInitialValues.get(draftStates[0]!.id);
    if (draftInitial !== "''" && draftInitial !== '""' && draftInitial !== "``") continue;
    for (const submit of submits.filter(candidate => candidate.sourceRefs.some(ref => ref.path === inputPath))) {
      const binding = submit.eventBindings.find(item => item.event === "click" || item.event === "tap");
      const submitActions = binding ? state.actionFacts.filter(action => action.name === binding.handler
        && action.sourceRefs.some(ref => ref.path === inputPath)) : [];
      const submitAction = submitActions.length === 1 ? submitActions[0] : undefined;
      const submitGrammar = submitAction?.exactTodoSubmit;
      const modeledDraft = modeledStateExpression(input.modelBinding ?? "");
      if (!binding || !submitAction || !submitGrammar
        || modeledDraft === null
        || modeledDraft !== modeledStateExpression(draftStates[0]!.name)
        || modeledStateExpression(submitGrammar.clearTarget) !== modeledDraft
        || modeledStateExpression(submitGrammar.argument) !== modeledDraft) continue;
      const callerPath = submitAction.sourceRefs[0]?.path;
      const delegatedActions = submitGrammar.receiverModule && callerPath
        ? state.actionFacts.filter(action => action.name === submitGrammar.method
          && action.sourceRefs[0] !== undefined
          && moduleResolvesToSource(callerPath, submitGrammar.receiverModule!, action.sourceRefs[0].path))
        : [];
      const delegatedAction = delegatedActions.length === 1 ? delegatedActions[0] : undefined;
      const appendGrammar = delegatedAction?.exactTodoAppend;
      if (!delegatedAction || !appendGrammar) continue;
      const collectionState = semanticPathTail(appendGrammar.collectionTarget);
      const delegatedPath = delegatedAction.sourceRefs[0]?.path;
      const collectionStates = state.states.filter(candidate => semanticPathTail(candidate.name) === collectionState
        && delegatedPath !== undefined && candidate.sourceRefs.some(ref => ref.path === delegatedPath));
      if (collectionStates.length !== 1
        || modeledStateExpression(appendGrammar.collectionTarget) !== collectionState
        || state.stateInitialValues.get(collectionStates[0]!.id) !== "[]") continue;
      const matchingLists = lists.filter(candidate => candidate.sourceRefs.some(ref => ref.path === inputPath)
        && modeledStateExpression(candidate.collectionBinding?.collection ?? "")
          === `${modeledStateExpression(submitGrammar.receiver) ?? "<unresolved>"}.${collectionState}`);
      if (matchingLists.length !== 1) continue;
      const list = matchingLists[0]!;
      const sourceRefs = [...input.sourceRefs, ...submit.sourceRefs, ...list.sourceRefs, ...submitAction.sourceRefs, ...delegatedAction.sourceRefs]
        .filter((ref, index, refs) => refs.findIndex(candidate => `${candidate.path}:${candidate.startLine}:${candidate.startColumn}` === `${ref.path}:${ref.startLine}:${ref.startColumn}`) === index);
      interactions.push({
        id: stableId("interaction", input.sourceRefs[0]?.path ?? "<source>", `${input.id}:${submit.id}:${list.id}:${binding.handler}`),
        kind: "trimmed-text-append-list",
        draftState,
        draftStateId: draftStates[0]!.id,
        collectionState,
        collectionStateId: collectionStates[0]!.id,
        inputComponentId: input.id,
        submitComponentId: submit.id,
        listComponentId: list.id,
        submitHandler: binding.handler,
        submitActionId: submitAction.id,
        delegatedActionId: delegatedAction.id,
        ignoreBlank: true,
        clearAfterSubmit: true,
        sourceRefs,
      });
    }
  }
  const deduplicated = deduplicate(interactions);
  const ownersByComponent = new Map<string, MiniappAnalyzedInteraction[]>();
  for (const interaction of deduplicated) {
    for (const componentId of [interaction.inputComponentId, interaction.submitComponentId, interaction.listComponentId]) {
      const owners = ownersByComponent.get(componentId) ?? [];
      owners.push(interaction);
      ownersByComponent.set(componentId, owners);
    }
  }
  const ambiguousIds = new Set([...ownersByComponent.entries()]
    .filter(([, owners]) => owners.length > 1)
    .map(([componentId]) => componentId));
  if (ambiguousIds.size > 0) {
    const refs = state.components.filter(component => ambiguousIds.has(component.id)).flatMap(component => component.sourceRefs);
    state.findings.push(finding(
      "MINIAPP_INTERACTION_COMPONENT_AMBIGUOUS",
      `${ambiguousIds.size} component(s) participate in multiple reconstructed interactions; one-to-one executable ownership cannot be proved.`,
      "C",
      refs,
      "error",
      true,
    ));
  }
  const componentSafe = deduplicated.filter(interaction => ![
    interaction.inputComponentId, interaction.submitComponentId, interaction.listComponentId,
  ].some(componentId => ambiguousIds.has(componentId)));
  const unsafeStateInteractions = componentSafe.filter(interaction => miniappRuntimeStateKey(interaction.draftState) === null
    || miniappRuntimeStateKey(interaction.collectionState) === null);
  if (unsafeStateInteractions.length > 0) {
    state.findings.push(finding(
      "MINIAPP_INTERACTION_STATE_KEY_UNSAFE",
      "A reconstructed interaction uses a non-identifier, nested, or prototype-mutating target data key.",
      "E",
      unsafeStateInteractions.flatMap(interaction => interaction.sourceRefs),
      "critical",
      true,
    ));
  }
  const runtimeKeySafe = componentSafe.filter(interaction => miniappRuntimeStateKey(interaction.draftState) !== null
    && miniappRuntimeStateKey(interaction.collectionState) !== null);
  const stateIdsByRuntimeKey = new Map<string, Set<string>>();
  for (const interaction of runtimeKeySafe) {
    for (const [rawKey, stateId] of [
      [interaction.draftState, interaction.draftStateId],
      [interaction.collectionState, interaction.collectionStateId],
    ] as const) {
      const key = miniappRuntimeStateKey(rawKey)!;
      const ids = stateIdsByRuntimeKey.get(key) ?? new Set<string>();
      ids.add(stateId);
      stateIdsByRuntimeKey.set(key, ids);
    }
  }
  const collidingKeys = new Set([...stateIdsByRuntimeKey.entries()]
    .filter(([, stateIds]) => stateIds.size > 1)
    .map(([key]) => key));
  if (collidingKeys.size > 0) {
    state.findings.push(finding(
      "MINIAPP_INTERACTION_STATE_KEY_COLLISION",
      `Reconstructed interactions contain colliding target data keys: ${[...collidingKeys].sort().join(", ")}.`,
      "C",
      state.states.filter(candidate => collidingKeys.has(semanticPathTail(candidate.name))).flatMap(candidate => candidate.sourceRefs),
      "error",
      true,
    ));
  }
  return runtimeKeySafe.filter(interaction => !collidingKeys.has(miniappRuntimeStateKey(interaction.draftState)!)
    && !collidingKeys.has(miniappRuntimeStateKey(interaction.collectionState)!));
}

function newMutableAnalysis(): MutableAnalysis {
  return {
    components: [], routes: [], states: [], effects: [], forms: [], styles: [], capabilities: [], actionFacts: [], stateInitialValues: new Map(),
    dependencies: new Set(), dependencyUsage: new Map(), findings: [], parsedFiles: new Set(), failedFiles: new Set(), parserEvidence: new Set(),
    nativeConfigFiles: new Map(), nativeConfigInvalid: new Set(), frameworkExports: new Map(),
  };
}

export function analyzeMiniappSource(
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
  files: SourceFiles,
): MiniappSourceAnalysis {
  const state = newMutableAnalysis();
  const applicableFiles = new Set<string>();
  for (const dependency of readDependencies(files)) state.dependencies.add(dependency);
  collectFrameworkExports(files, state);
  const sourceLabel = request.source.sourceLabel;
  for (const [path, source] of Object.entries(files).sort(([a], [b]) => a.localeCompare(b, "en-US"))) {
    if (path.endsWith(".vue") && ["vue2", "vue3", "uni-app"].includes(sourceLabel)) {
      applicableFiles.add(path);
      analyzeVue(path, source, state, sourceLabel);
    } else if (/\.(?:ts|tsx|js|jsx)$/.test(path) && !sourceBuildConfigPaths.has(path)) {
      applicableFiles.add(path);
      analyzeTypeScript(path, source, state);
    } else if (sourceBuildConfigPaths.has(path)) {
      applicableFiles.add(path);
      state.parsedFiles.add(path);
      state.parserEvidence.add("source-build-config-inventory-only");
    } else if (path.endsWith(".dart") && sourceLabel === "flutter") {
      applicableFiles.add(path);
      analyzeDart(path, source, state);
    } else if (/\.(?:html|wxml|axml|ttml|xhsml)$/.test(path)) {
      applicableFiles.add(path);
      const isSourceBuildEntry = path === "index.html"
        && /<script\b[^>]*\btype\s*=\s*["']module["'][^>]*\bsrc\s*=\s*["'][^"']+["']/iu.test(source)
        && /<div\b[^>]*\bid\s*=\s*["']app["']/iu.test(source);
      if (!isSourceBuildEntry) analyzeMarkup(path, source, path.endsWith(".html") ? "template-ast" : "native-template", state);
      if (path.endsWith(".html")) {
        if (isSourceBuildEntry) {
          state.parsedFiles.add(path);
          state.parserEvidence.add("source-build-entrypoint");
        }
        analyzeHtmlScripts(path, source, state, files);
      }
    } else if (/\.(?:css|scss|less|sass|styl|wxss|acss|ttss)$/.test(path)) {
      applicableFiles.add(path);
      if (/\.(?:scss|less|sass|styl)$/u.test(path)) {
        state.failedFiles.add(path);
        state.findings.push(finding(
          "MINIAPP_STYLE_PREPROCESSOR_NOT_RUN",
          `${path} requires its exact source preprocessor; the bounded CSS parser does not consume preprocessor semantics.`,
          "D",
          [lineRef(path, source, 1)],
          "error",
          true,
        ));
      } else {
        analyzeCss(path, source, state);
      }
    } else if (path === "app.json" || path === "pages.json") {
      applicableFiles.add(path);
      analyzeNativeConfig(path, source, state, sourceLabel);
    }
  }
  const requiredNativeConfig = sourceLabel === "native-miniapp"
    ? "app.json"
    : sourceLabel === "uni-app"
      ? "pages.json"
      : undefined;
  if (requiredNativeConfig && !state.nativeConfigFiles.has(requiredNativeConfig)) {
    state.findings.push(finding(
      "MINIAPP_NATIVE_CONFIG_MISSING",
      `${requiredNativeConfig} is required for ${sourceLabel}; no fallback page manifest is synthesized.`,
      "D",
      [],
      "error",
      true,
    ));
  }
  if (state.routes.length === 0 && state.components.length > 0
    && state.nativeConfigFiles.size === 0
    && state.nativeConfigInvalid.size === 0) {
    const renderable = state.components.filter(component => component.semanticRole !== "non-render-metadata");
    const childIds = new Set(renderable.flatMap(component => component.children));
    const roots = renderable.filter(component => !childIds.has(component.id));
    if (roots.length === 1) {
      const root = roots[0]!;
      state.routes.push({
        id: stableId("route", root.sourceRefs[0]?.path ?? "<source>", "/"), path: "/", component: root.name,
        componentModule: root.sourceRefs[0]?.path ?? null,
        parameters: [], guards: [], sourceRefs: root.sourceRefs,
      });
    } else {
      const refs = roots.flatMap(component => component.sourceRefs).slice(0, 8);
      state.findings.push(finding(
        "MINIAPP_APPLICATION_ROOT_AMBIGUOUS",
        `No explicit router was recovered and ${roots.length} independent render roots remain; a single application root cannot be inferred.`,
        "D",
        refs.length > 0 ? refs : state.components[0]!.sourceRefs,
        "error",
        true,
      ));
    }
  }
  const parsedFiles = [...state.parsedFiles].sort((a, b) => a.localeCompare(b, "en-US"));
  const failedFiles = [...state.failedFiles].sort((a, b) => a.localeCompare(b, "en-US"));
  const interactions = reconstructInteractions(state);
  const consumedActionIds = new Set(interactions.flatMap(interaction => [interaction.submitActionId, interaction.delegatedActionId]));
  for (const action of state.actionFacts) {
    const hasBehavior = action.calls.length > 0 || action.assignments.length > 0 || action.trims.length > 0 || action.appends.length > 0;
    if (hasBehavior && !consumedActionIds.has(action.id)) {
      state.findings.push(finding(
        "MINIAPP_ACTION_BEHAVIOR_UNRESOLVED",
        `${action.name} contains calls or state transitions that are not consumed by an exact interaction/effect lowering.`,
        "C",
        action.sourceRefs,
      ));
    }
  }
  const base = {
    schemaVersion: "1.0" as const,
    analysisId: stableId("analysis", request.source.revision, sourceLabel),
    sourceLabel,
    frameworkVersion: request.source.frameworkVersion,
    parser: [...state.parserEvidence].sort().join("+") || "NO_APPLICABLE_PARSER",
    parserEvidence: [...state.parserEvidence].sort(),
    components: deduplicate(state.components),
    routes: deduplicate(state.routes),
    states: deduplicate(state.states),
    effects: deduplicate(state.effects),
    forms: deduplicate(state.forms),
    styles: deduplicate(state.styles),
    capabilities: deduplicate(state.capabilities),
    interactions,
    dependencies: [...state.dependencies].sort(),
    dependencyUsage: Object.fromEntries([...state.dependencyUsage.entries()]
      .sort(([left], [right]) => left.localeCompare(right, "en-US"))
      .map(([name, refs]) => [name, refs.filter((ref, index) => refs.findIndex(candidate =>
        `${candidate.path}:${candidate.startLine}:${candidate.startColumn}` === `${ref.path}:${ref.startLine}:${ref.startColumn}`) === index)])),
    findings: state.findings.sort((a, b) => `${a.code}:${a.sourceRefs[0]?.path ?? ""}`.localeCompare(`${b.code}:${b.sourceRefs[0]?.path ?? ""}`, "en-US")),
    parsedFiles,
    failedFiles,
    coverage: applicableFiles.size === 0
      ? 0
      : parsedFiles.filter(path => applicableFiles.has(path)).length / applicableFiles.size,
  };
  return { ...base, deterministicDigest: digest(base) };
}

function nodeObligations(kind: MiniappUiIrNode["kind"], value: unknown): readonly string[] {
  const base = ["PRESERVE_SOURCE_TRACE", "NO_SILENT_DROP"];
  if (kind === "route") return [...base, "PRESERVE_DEEP_LINK_AND_PAGE_STACK"];
  if (kind === "state") return [...base, "PRESERVE_STATE_OWNERSHIP_AND_TYPE"];
  if (kind === "effect") return [...base, "PRESERVE_ORDER_CANCELLATION_AND_CLEANUP"];
  if (kind === "form") return [...base, "PRESERVE_BINDING_VALIDATION_AND_ERROR_TIMING"];
  if (kind === "style") return [...base, "PRESERVE_LAYOUT_THEME_RESPONSIVE_AND_SAFE_AREA"];
  if (kind === "capability") return [...base, "RESOLVE_PERMISSION_PRIVACY_BACKEND_AND_REVIEW_RISK"];
  if (kind === "interaction") return [...base, "PRESERVE_EVENT_GUARD_TRANSITIONS_AND_COLLECTION_BINDING"];
  return value ? [...base, "PRESERVE_INTERACTION_AND_ACCESSIBILITY"] : base;
}

type MiniappSemanticNodeCollections = Pick<
  MiniappSourceAnalysis,
  | "components"
  | "routes"
  | "states"
  | "effects"
  | "forms"
  | "styles"
  | "capabilities"
  | "interactions"
>;

function reconstructMiniappSemanticNodes(
  value: MiniappSemanticNodeCollections,
): readonly MiniappUiIrNode[] {
  const nodes: MiniappUiIrNode[] = [];
  const push = (
    kind: MiniappUiIrNode["kind"],
    item: { id: string; name?: string; sourceRefs: readonly MiniappSourceRef[] },
    semanticRole: string,
    references: readonly string[] = [],
  ): void => {
    nodes.push({
      id: item.id,
      kind,
      name: item.name ?? item.id,
      semanticRole,
      references: [...new Set(references)].sort(),
      sourceRefs: item.sourceRefs,
      obligations: nodeObligations(kind, item),
    });
  };

  for (const item of value.components) push("component", item, item.semanticRole);
  for (const item of value.routes) {
    const components = resolveMiniappRouteComponentRoots(value.components, item);
    push("route", item, "route", components.map((component) => component.id));
  }
  for (const item of value.states) push("state", item, item.scope);
  for (const item of value.effects) push("effect", item, item.trigger);
  for (const item of value.forms) push("form", item, "form-binding");
  for (const item of value.styles) {
    push("style", { ...item, name: item.selector }, "style-rule");
  }
  for (const item of value.capabilities) push("capability", item, item.category);
  for (const item of value.interactions) {
    push("interaction", item, item.kind, [
      item.inputComponentId,
      item.submitComponentId,
      item.listComponentId,
      item.draftStateId,
      item.collectionStateId,
    ]);
  }

  return deduplicate(nodes);
}

export function buildMiniappSemanticIr(
  request: MiniappConversionRequest,
  inventory: MiniappSourceInventory,
  analysis: MiniappSourceAnalysis,
): MiniappSemanticIr {
  if (analysis.deterministicDigest !== digest({ ...analysis, deterministicDigest: undefined })) {
    throw new Error("source analysis deterministic digest does not match its content");
  }
  const sortedNodes = reconstructMiniappSemanticNodes(analysis);
  const traceIndex = Object.fromEntries(sortedNodes.map(node => [node.id, node.sourceRefs]));
  const title = analysis.components.find(item => /^h1$/iu.test(item.sourceTag) && item.textContent)?.textContent
    ?? analysis.components.find(item => /app|home|index/i.test(item.name))?.name
    ?? analysis.components[0]?.name
    ?? request.requestId;
  const base = {
    schemaVersion: "2.0" as const,
    profile: "miniapp-ui-interaction-v1" as const,
    source: {
      label: request.source.sourceLabel,
      frameworkVersion: request.source.frameworkVersion,
      snapshotDigest: request.source.snapshotDigest,
      revision: request.source.revision,
      parser: analysis.parser,
    },
    application: {
      id: stableId("application", request.tenantId, request.requestId),
      title,
      routeIds: analysis.routes.map(item => item.id).sort(),
      componentIds: analysis.components.map(item => item.id).sort(),
      defaultLocale: "zh-CN",
      theme: "platform-adaptive",
    },
    nodes: sortedNodes,
    routes: analysis.routes,
    components: analysis.components,
    states: analysis.states,
    effects: analysis.effects,
    forms: analysis.forms,
    styles: analysis.styles,
    capabilities: analysis.capabilities,
    interactions: analysis.interactions,
    dependencies: analysis.dependencies,
    dependencyUsage: analysis.dependencyUsage,
    unknowns: analysis.findings.filter(item => item.classification === "C" || item.classification === "D" || item.classification === "E"),
    traceIndex,
    coverage: {
      parsedSource: analysis.coverage,
      tracedNodes: sortedNodes.length === 0 ? 0 : sortedNodes.filter(node => node.sourceRefs.length > 0).length / sortedNodes.length,
      unresolvedCritical: analysis.findings.filter(item => item.blocking && (item.severity === "critical" || item.severity === "error")).length,
    },
  };
  validateMiniappSemanticIr(base, inventory);
  return { ...base, deterministicDigest: digest(base) };
}

export function validateMiniappSemanticIr(
  value: Omit<MiniappSemanticIr, "deterministicDigest"> | MiniappSemanticIr,
  inventory?: MiniappSourceInventory,
): void {
  if (value.schemaVersion !== "2.0" || value.profile !== "miniapp-ui-interaction-v1") throw new Error("unsupported miniapp IR profile");
  const ids = new Set<string>();
  const inventoryFiles = inventory ? new Map(inventory.files.map(file => [file.path, file.digest])) : undefined;
  for (const node of value.nodes) {
    if (!/^[-a-z0-9.]+$/.test(node.id) || ids.has(node.id)) throw new Error(`invalid or duplicate IR node id: ${node.id}`);
    if (node.sourceRefs.length === 0) throw new Error(`IR node has no source trace: ${node.id}`);
    for (const ref of node.sourceRefs) {
      if (!/^sha256:[a-f0-9]{64}$/.test(ref.sha256)
        || ref.startLine < 1
        || ref.startColumn < 1
        || ref.endColumn < 1
        || ref.endLine < ref.startLine
        || (ref.endLine === ref.startLine && ref.endColumn < ref.startColumn)) {
        throw new Error(`invalid source trace: ${node.id}`);
      }
      if (inventoryFiles && inventoryFiles.get(ref.path) !== ref.sha256) {
        throw new Error(`source trace is not bound to the inventory: ${node.id} -> ${ref.path}`);
      }
    }
    ids.add(node.id);
  }
  for (const node of value.nodes) {
    for (const reference of node.references) if (!ids.has(reference)) throw new Error(`IR reference is not closed: ${node.id} -> ${reference}`);
    if (!Object.hasOwn(value.traceIndex, node.id)) throw new Error(`trace index is missing ${node.id}`);
    if (canonical(value.traceIndex[node.id]) !== canonical(node.sourceRefs)) {
      throw new Error(`trace index does not match node source trace: ${node.id}`);
    }
  }
  const traceIds = Object.keys(value.traceIndex).sort();
  const nodeIds = value.nodes.map(node => node.id).sort();
  if (canonical(traceIds) !== canonical(nodeIds)) throw new Error("trace index is not an exact IR node index");
  const collections = [
    ["component", value.components],
    ["route", value.routes],
    ["state", value.states],
    ["effect", value.effects],
    ["form", value.forms],
    ["style", value.styles],
    ["capability", value.capabilities],
    ["interaction", value.interactions],
  ] as const;
  for (const [kind, collection] of collections) {
    const collectionIds = collection.map(item => item.id).sort();
    const indexedIds = value.nodes.filter(node => node.kind === kind).map(node => node.id).sort();
    if (collectionIds.length !== new Set(collectionIds).size || canonical(collectionIds) !== canonical(indexedIds)) {
      throw new Error(`IR ${kind} collection is not exactly indexed by nodes`);
    }
  }
  if (canonical(value.nodes) !== canonical(reconstructMiniappSemanticNodes(value))) {
    throw new Error("IR nodes do not exactly reconstruct the typed semantic collections");
  }
  if (canonical([...value.application.routeIds].sort()) !== canonical(value.routes.map(route => route.id).sort())) {
    throw new Error("application route index is not closed");
  }
  if (canonical([...value.application.componentIds].sort()) !== canonical(value.components.map(component => component.id).sort())) {
    throw new Error("application component index is not closed");
  }
  if (value.coverage.parsedSource < 0 || value.coverage.parsedSource > 1
      || value.coverage.tracedNodes < 0 || value.coverage.tracedNodes > 1) {
    throw new Error("IR coverage is outside 0..1");
  }
  if ("deterministicDigest" in value
    && value.deterministicDigest !== digest({ ...value, deterministicDigest: undefined })) {
    throw new Error("miniapp IR deterministic digest does not match its content");
  }
}

export function canonicalizeMiniappSourceAnalysis(value: MiniappSourceAnalysis): string {
  return canonical(value);
}

export function canonicalizeMiniappSemanticIr(value: MiniappSemanticIr): string {
  return canonical(value);
}

export function miniappIrDigest(value: unknown): string {
  return digest(value);
}

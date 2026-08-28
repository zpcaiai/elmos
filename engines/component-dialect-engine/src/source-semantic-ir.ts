/**
 * Loss-aware semantic capture for React-family components that do not fit
 * the automatic ComponentDef subset.
 *
 * This is deliberately not another emitter.  It gives blocked components a
 * typed, source-ranged migration contract so external Hooks, effects,
 * structured data, collections, slots and document/platform semantics can be
 * adapted or hand-ported without being rediscovered from an error string.
 * Capturing a construct never promotes it into the automatic subset.
 */
import * as crypto from "crypto";
import * as ts from "typescript";

import { ALL_FRAMEWORKS, type Framework } from "./models";
import {
  type SourceSemanticFeature,
  type SourceSemanticFeatureKind,
  type SourceSemanticRange,
  type TargetSemanticDecision,
  type TargetSemanticMode,
} from "./semantic-capabilities";
import { targetAdapter } from "./target-adapters";

export const SOURCE_SEMANTIC_IR_SCHEMA_VERSION = "1.0" as const;

export interface SourceImportContract {
  module: string;
  bindings: string[];
  typeOnly: boolean;
  sourceRange: SourceSemanticRange;
}

export interface SourceHookContract {
  name: string;
  ownerModule: string | null;
  role: "STATE" | "EFFECT" | "DERIVED" | "CALLBACK" | "CONTEXT" | "REDUCER" | "EXTERNAL";
  asyncCallback: boolean;
  dependencyCount: number | null;
  sourceRange: SourceSemanticRange;
}

export interface SourceEffectContract {
  id: string;
  owner: string;
  trigger: "MOUNT" | "DEPENDENCY_CHANGE" | "CALL" | "ASYNC_COMPONENT";
  resources: ("NETWORK" | "TIMER" | "SUBSCRIPTION" | "STORAGE" | "NATIVE" | "WORKER" | "UNKNOWN")[];
  cleanup: "PRESENT" | "ABSENT" | "NOT_APPLICABLE";
  cancellation: "PRESENT" | "ABSENT" | "UNKNOWN";
  status: "REPRESENTED" | "REPRESENTED_WITH_GAP";
  sourceRange: SourceSemanticRange;
}

export interface SourceDataContract {
  name: string;
  ownership: "PROP" | "STATE" | "REDUCER";
  typeText: string;
  shape: "PRIMITIVE" | "LITERAL_UNION" | "OBJECT" | "ARRAY" | "MAP" | "SET" | "PROMISE" | "UNKNOWN";
  nullable: boolean;
  initializerKind: string | null;
  sourceRange: SourceSemanticRange;
}

export interface SourceCollectionContract {
  id: string;
  collection: "MAP" | "SET" | "ARRAY_DERIVATION";
  operation: string;
  mutation: "READ" | "WRITE" | "CONSTRUCT" | "UNKNOWN";
  sourceRange: SourceSemanticRange;
}

export interface SourceSlotContract {
  name: string;
  sourceForm: "CHILDREN_PROP" | "JSX_PROJECTION" | "PROVIDER" | "COMPONENT_CHILDREN";
  evaluationOwner: "PARENT" | "CHILD" | "UNKNOWN";
  sourceRange: SourceSemanticRange;
}

export interface SourceSemanticObligation {
  id: string;
  featureId: string;
  targetFramework: Framework;
  mode: Exclude<TargetSemanticMode, "NATIVE">;
  reason: string;
  requiredEvidence: string[];
}

export interface SourceTargetSemanticPlan {
  targetFramework: Framework;
  adapterId: string;
  disposition: "ADAPTER_REQUIRED" | "HAND_PORTED" | "BLOCKED";
  decisions: TargetSemanticDecision[];
  requiredEvidence: string[];
}

export interface SourceComponentSemanticIR {
  schemaVersion: typeof SOURCE_SEMANTIC_IR_SCHEMA_VERSION;
  kind: "elmos.source-component-semantic-ir";
  componentId: string;
  source: {
    framework: Framework;
    file: string;
    componentName: string;
    componentDigest: string;
    sourceRange: SourceSemanticRange;
  };
  blocker: { reasonCode: string; reason: string };
  captureStatus: "REPRESENTED" | "PARTIAL";
  imports: SourceImportContract[];
  hooks: SourceHookContract[];
  effects: SourceEffectContract[];
  dataContracts: SourceDataContract[];
  collections: SourceCollectionContract[];
  slots: SourceSlotContract[];
  features: SourceSemanticFeature[];
  targetPlans: Record<Framework, SourceTargetSemanticPlan>;
  obligations: SourceSemanticObligation[];
  /** No executable source or AST nodes are retained. */
  irDigest: string;
}

export interface CaptureSourceSemanticOptions {
  sourceFile: ts.SourceFile;
  sourceFramework: Framework;
  sourcePath: string;
  componentName: string;
  reasonCode: string;
  reason: string;
}

type ComponentFunction = ts.FunctionDeclaration | ts.FunctionExpression | ts.ArrowFunction;

const COLLECTION_METHODS = new Set(["map", "filter", "reduce", "flatMap", "sort", "toSorted", "groupBy", "join"]);
const BUILTIN_HOOK_ROLES: Readonly<Record<string, SourceHookContract["role"]>> = {
  useState: "STATE",
  useEffect: "EFFECT",
  useLayoutEffect: "EFFECT",
  useInsertionEffect: "EFFECT",
  useMemo: "DERIVED",
  useCallback: "CALLBACK",
  useContext: "CONTEXT",
  useReducer: "REDUCER",
};

function hash(value: string): string {
  return `sha256:${crypto.createHash("sha256").update(value, "utf8").digest("hex")}`;
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => compareText(left, right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function sourceRange(node: ts.Node, sourceFile: ts.SourceFile): SourceSemanticRange {
  const start = node.getStart(sourceFile);
  const end = node.getEnd();
  const startPoint = sourceFile.getLineAndCharacterOfPosition(start);
  const endPoint = sourceFile.getLineAndCharacterOfPosition(end);
  return {
    start,
    end,
    startLine: startPoint.line + 1,
    startColumn: startPoint.character + 1,
    endLine: endPoint.line + 1,
    endColumn: endPoint.character + 1,
  };
}

function excerpt(node: ts.Node, sourceFile: ts.SourceFile): string {
  const compact = node.getText(sourceFile).replace(/\s+/g, " ").trim();
  return compact.length <= 240 ? compact : `${compact.slice(0, 237)}...`;
}

function hasAsyncModifier(node: ts.Node): boolean {
  return Boolean(ts.canHaveModifiers(node)
    && ts.getModifiers(node)?.some((modifier) => modifier.kind === ts.SyntaxKind.AsyncKeyword));
}

function componentFunction(sourceFile: ts.SourceFile, componentName: string): ComponentFunction | null {
  let found: ComponentFunction | null = null;
  const visit = (node: ts.Node): void => {
    if (found !== null) return;
    if (ts.isFunctionDeclaration(node) && node.name?.text === componentName) {
      found = node;
      return;
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === componentName
      && node.initializer !== undefined
      && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
      found = node.initializer;
      return;
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return found;
}

function importedBindings(sourceFile: ts.SourceFile): {
  imports: SourceImportContract[];
  ownerByBinding: Map<string, string>;
  cssModuleBindings: Map<string, ts.ImportDeclaration>;
} {
  const imports: SourceImportContract[] = [];
  const ownerByBinding = new Map<string, string>();
  const cssModuleBindings = new Map<string, ts.ImportDeclaration>();
  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) continue;
    const module = statement.moduleSpecifier.text;
    const bindings: string[] = [];
    const clause = statement.importClause;
    if (clause?.name) bindings.push(clause.name.text);
    if (clause?.namedBindings && ts.isNamespaceImport(clause.namedBindings)) bindings.push(clause.namedBindings.name.text);
    if (clause?.namedBindings && ts.isNamedImports(clause.namedBindings)) {
      bindings.push(...clause.namedBindings.elements.map((element) => element.name.text));
    }
    for (const binding of bindings) ownerByBinding.set(binding, module);
    if (/\.module\.(css|scss|sass|less)$/.test(module) && clause?.name) cssModuleBindings.set(clause.name.text, statement);
    imports.push({
      module,
      bindings: [...new Set(bindings)].sort(),
      typeOnly: clause?.isTypeOnly === true,
      sourceRange: sourceRange(statement, sourceFile),
    });
  }
  return { imports: imports.sort((a, b) => a.sourceRange.start - b.sourceRange.start), ownerByBinding, cssModuleBindings };
}

function callName(expression: ts.LeftHandSideExpression, sourceFile: ts.SourceFile): string {
  if (ts.isIdentifier(expression)) return expression.text;
  if (ts.isPropertyAccessExpression(expression)) return expression.name.text;
  return expression.getText(sourceFile);
}

function callOwner(expression: ts.LeftHandSideExpression, ownerByBinding: ReadonlyMap<string, string>): string | null {
  if (ts.isIdentifier(expression)) return ownerByBinding.get(expression.text) ?? null;
  if (ts.isPropertyAccessExpression(expression) && ts.isIdentifier(expression.expression)) {
    return ownerByBinding.get(expression.expression.text) ?? null;
  }
  return null;
}

function callbackArgument(call: ts.CallExpression): ts.ArrowFunction | ts.FunctionExpression | null {
  const first = call.arguments[0];
  return first !== undefined && (ts.isArrowFunction(first) || ts.isFunctionExpression(first)) ? first : null;
}

function dependencyCount(call: ts.CallExpression): number | null {
  const last = call.arguments[call.arguments.length - 1];
  return last !== undefined && ts.isArrayLiteralExpression(last) ? last.elements.length : null;
}

function typeShape(node: ts.TypeNode | undefined): SourceDataContract["shape"] {
  if (node === undefined) return "UNKNOWN";
  if (node.kind === ts.SyntaxKind.StringKeyword || node.kind === ts.SyntaxKind.NumberKeyword
    || node.kind === ts.SyntaxKind.BooleanKeyword || node.kind === ts.SyntaxKind.BigIntKeyword) return "PRIMITIVE";
  if (ts.isUnionTypeNode(node)) {
    const meaningful = node.types.filter((member) => member.kind !== ts.SyntaxKind.NullKeyword
      && member.kind !== ts.SyntaxKind.UndefinedKeyword);
    if (meaningful.length > 0 && meaningful.every((member) => ts.isLiteralTypeNode(member))) return "LITERAL_UNION";
    return "UNKNOWN";
  }
  if (ts.isArrayTypeNode(node) || ts.isTupleTypeNode(node)) return "ARRAY";
  if (ts.isTypeLiteralNode(node) || ts.isMappedTypeNode(node) || ts.isIntersectionTypeNode(node)) return "OBJECT";
  if (ts.isTypeReferenceNode(node)) {
    const name = node.typeName.getText();
    if (name === "Array" || name === "ReadonlyArray") return "ARRAY";
    if (name === "Map" || name === "ReadonlyMap") return "MAP";
    if (name === "Set" || name === "ReadonlySet") return "SET";
    if (name === "Promise") return "PROMISE";
  }
  return "UNKNOWN";
}

function nullableType(node: ts.TypeNode | undefined): boolean {
  return node !== undefined && ts.isUnionTypeNode(node)
    && node.types.some((member) => member.kind === ts.SyntaxKind.NullKeyword
      || member.kind === ts.SyntaxKind.UndefinedKeyword
      || ts.isLiteralTypeNode(member) && member.literal.kind === ts.SyntaxKind.NullKeyword);
}

function resourceForNode(node: ts.Node, sourceFile: ts.SourceFile): SourceEffectContract["resources"][number] | null {
  if (ts.isCallExpression(node)) {
    const text = node.expression.getText(sourceFile);
    if (text === "fetch" || /\.(get|post|put|patch|delete|request)$/.test(text)) return "NETWORK";
    if (/^(setTimeout|setInterval)$/.test(text) || /\.(setTimeout|setInterval)$/.test(text)) return "TIMER";
    if (/\.(addEventListener|subscribe|on)$/.test(text)) return "SUBSCRIPTION";
    if (/^(localStorage|sessionStorage|indexedDB)\./.test(text)) return "STORAGE";
    if (/\.(postMessage|requestAnimationFrame)$/.test(text)) return "NATIVE";
  }
  if (ts.isNewExpression(node)) {
    const text = node.expression.getText(sourceFile);
    if (text === "Worker" || text === "SharedWorker") return "WORKER";
    if (text === "BroadcastChannel" || text === "WebSocket" || text === "EventSource") return "SUBSCRIPTION";
  }
  return null;
}

function containsText(node: ts.Node, sourceFile: ts.SourceFile, pattern: RegExp): boolean {
  return pattern.test(node.getText(sourceFile));
}

function targetDisposition(decisions: readonly TargetSemanticDecision[]): SourceTargetSemanticPlan["disposition"] {
  if (decisions.some((item) => item.mode === "BLOCKED")) return "BLOCKED";
  if (decisions.some((item) => item.mode === "HAND_PORTED")) return "HAND_PORTED";
  // Source semantic IR is a handoff contract, not a canonical ComponentDef;
  // even all-native features still need a target adapter before emission.
  return "ADAPTER_REQUIRED";
}

export function captureReactSourceSemanticIR(options: CaptureSourceSemanticOptions): SourceComponentSemanticIR | null {
  const { sourceFile, sourceFramework, sourcePath, componentName, reasonCode, reason } = options;
  const component = componentFunction(sourceFile, componentName);
  if (component === null) return null;

  const componentRange = sourceRange(component, sourceFile);
  const componentText = component.getText(sourceFile);
  const { imports, ownerByBinding, cssModuleBindings } = importedBindings(sourceFile);
  const hooks: SourceHookContract[] = [];
  const effects: SourceEffectContract[] = [];
  const dataContracts: SourceDataContract[] = [];
  const collections: SourceCollectionContract[] = [];
  const slots: SourceSlotContract[] = [];
  const featureMap = new Map<string, SourceSemanticFeature>();

  const addFeature = (kind: SourceSemanticFeatureKind, node: ts.Node, detail: string): void => {
    const range = sourceRange(node, sourceFile);
    const key = `${kind}:${range.start}:${range.end}:${detail}`;
    if (featureMap.has(key)) return;
    featureMap.set(key, {
      id: `feature:${kind.toLowerCase()}:${range.start}-${range.end}`,
      kind,
      detail,
      sourceRange: range,
      sourceExcerpt: excerpt(node, sourceFile),
    });
  };

  for (const [binding, declaration] of cssModuleBindings) {
    addFeature("CSS_MODULE", declaration, `CSS Module binding ${binding}`);
  }

  if (hasAsyncModifier(component)) {
    addFeature("ASYNC_EFFECT", component, "async component body");
    effects.push({
      id: `effect:async-component:${componentRange.start}`,
      owner: componentName,
      trigger: "ASYNC_COMPONENT",
      resources: ["UNKNOWN"],
      cleanup: "NOT_APPLICABLE",
      cancellation: "UNKNOWN",
      status: "REPRESENTED_WITH_GAP",
      sourceRange: componentRange,
    });
  }

  for (const parameter of component.parameters) {
    const parameterType = parameter.type;
    const shape = typeShape(parameterType);
    dataContracts.push({
      name: parameter.name.getText(sourceFile),
      ownership: "PROP",
      typeText: parameterType?.getText(sourceFile) ?? "UNKNOWN",
      shape,
      nullable: nullableType(parameterType),
      initializerKind: parameter.initializer ? ts.SyntaxKind[parameter.initializer.kind] : null,
      sourceRange: sourceRange(parameter, sourceFile),
    });
    if (shape === "OBJECT" || shape === "ARRAY") addFeature("OBJECT_STATE", parameter, "structured props contract");
    if (shape === "LITERAL_UNION") addFeature("LITERAL_UNION_TYPE", parameter, "closed literal-union props contract");
    if (/\bchildren\b/.test(parameter.name.getText(sourceFile)) || /React(Node|Element|Portal)/.test(parameterType?.getText(sourceFile) ?? "")) {
      slots.push({ name: "children", sourceForm: "CHILDREN_PROP", evaluationOwner: "PARENT", sourceRange: sourceRange(parameter, sourceFile) });
      addFeature("SLOT_PROJECTION", parameter, "React children projection");
    }
  }

  const visit = (node: ts.Node): void => {
    if ((ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node))
      && node !== component && hasAsyncModifier(node)) {
      addFeature("ASYNC_EFFECT", node, "nested async callback or helper");
    }

    if (ts.isVariableDeclaration(node) && ts.isArrayBindingPattern(node.name)
      && node.initializer !== undefined && ts.isCallExpression(node.initializer)) {
      const hookName = callName(node.initializer.expression, sourceFile);
      if (hookName === "useState" || hookName === "useReducer") {
        const first = node.name.elements[0];
        const name = first && ts.isBindingElement(first) ? first.name.getText(sourceFile) : node.name.getText(sourceFile);
        const typeNode = node.initializer.typeArguments?.[0];
        const shape = typeShape(typeNode);
        dataContracts.push({
          name,
          ownership: hookName === "useState" ? "STATE" : "REDUCER",
          typeText: typeNode?.getText(sourceFile) ?? "INFERRED",
          shape,
          nullable: nullableType(typeNode),
          initializerKind: node.initializer.arguments[0] ? ts.SyntaxKind[node.initializer.arguments[0].kind] : null,
          sourceRange: sourceRange(node, sourceFile),
        });
        if (shape === "OBJECT" || shape === "ARRAY") addFeature("OBJECT_STATE", node, `${hookName} structured state`);
        if (shape === "LITERAL_UNION") addFeature("LITERAL_UNION_TYPE", node, `${hookName} literal-union state`);
        if (shape === "MAP") addFeature("MAP_COLLECTION", node, `${hookName} Map state`);
        if (shape === "SET") addFeature("SET_COLLECTION", node, `${hookName} Set state`);
      }
    }

    if (ts.isCallExpression(node)) {
      const name = callName(node.expression, sourceFile);
      const ownerModule = callOwner(node.expression, ownerByBinding);
      if (/^use[A-Z0-9_]/.test(name)) {
        const role = BUILTIN_HOOK_ROLES[name] ?? "EXTERNAL";
        const callback = callbackArgument(node);
        hooks.push({
          name,
          ownerModule,
          role,
          asyncCallback: callback !== null && hasAsyncModifier(callback),
          dependencyCount: dependencyCount(node),
          sourceRange: sourceRange(node, sourceFile),
        });
        if (role === "EXTERNAL") addFeature("EXTERNAL_HOOK", node, `${name} from ${ownerModule ?? "application scope"}`);
        if (role === "EFFECT") {
          addFeature("ASYNC_EFFECT", node, `${name} lifecycle effect`);
          const body = callback ?? node;
          const resources = new Set<SourceEffectContract["resources"][number]>();
          const findResources = (child: ts.Node): void => {
            const resource = resourceForNode(child, sourceFile);
            if (resource !== null) resources.add(resource);
            ts.forEachChild(child, findResources);
          };
          findResources(body);
          if (resources.size === 0) resources.add("UNKNOWN");
          const cleanupPresent = callback !== null && ts.isBlock(callback.body)
            && callback.body.statements.some((statement) => ts.isReturnStatement(statement)
              && statement.expression !== undefined
              && (ts.isArrowFunction(statement.expression) || ts.isFunctionExpression(statement.expression)));
          const requiresCleanup = [...resources].some((resource) => resource === "TIMER" || resource === "SUBSCRIPTION" || resource === "WORKER" || resource === "NATIVE");
          const cancellationPresent = containsText(body, sourceFile, /\b(AbortController|abort|clearTimeout|clearInterval|removeEventListener|unsubscribe|close|terminate)\b/);
          effects.push({
            id: `effect:${name}:${node.getStart(sourceFile)}`,
            owner: name,
            trigger: dependencyCount(node) === 0 ? "MOUNT" : "DEPENDENCY_CHANGE",
            resources: [...resources].sort(),
            cleanup: cleanupPresent ? "PRESENT" : requiresCleanup ? "ABSENT" : "NOT_APPLICABLE",
            cancellation: cancellationPresent ? "PRESENT" : resources.has("NETWORK") ? "ABSENT" : "UNKNOWN",
            status: (!requiresCleanup || cleanupPresent) && (!resources.has("NETWORK") || cancellationPresent)
              ? "REPRESENTED" : "REPRESENTED_WITH_GAP",
            sourceRange: sourceRange(node, sourceFile),
          });
        }
      }

      const resource = resourceForNode(node, sourceFile);
      if (resource === "NETWORK") addFeature("NETWORK_RESOURCE", node, `network call ${node.expression.getText(sourceFile)}`);
      if (resource === "TIMER") addFeature("TIMER_RESOURCE", node, `timer call ${node.expression.getText(sourceFile)}`);
      if (resource === "SUBSCRIPTION") addFeature("SUBSCRIPTION_RESOURCE", node, `subscription call ${node.expression.getText(sourceFile)}`);
      if (resource === "STORAGE") addFeature("STORAGE_RESOURCE", node, `storage call ${node.expression.getText(sourceFile)}`);
      if (resource === "NATIVE") addFeature("NATIVE_RESOURCE", node, `platform call ${node.expression.getText(sourceFile)}`);
      if (ts.isPropertyAccessExpression(node.expression) && COLLECTION_METHODS.has(node.expression.name.text)) {
        collections.push({
          id: `collection:${node.expression.name.text}:${node.getStart(sourceFile)}`,
          collection: "ARRAY_DERIVATION",
          operation: node.expression.name.text,
          mutation: node.expression.name.text === "sort" ? "WRITE" : "READ",
          sourceRange: sourceRange(node, sourceFile),
        });
        addFeature("DERIVED_COLLECTION", node, `collection operation ${node.expression.name.text}`);
      }
    }

    if (ts.isNewExpression(node)) {
      const constructor = node.expression.getText(sourceFile);
      if (constructor === "Map") {
        collections.push({ id: `collection:Map:${node.getStart(sourceFile)}`, collection: "MAP", operation: "construct", mutation: "CONSTRUCT", sourceRange: sourceRange(node, sourceFile) });
        addFeature("MAP_COLLECTION", node, "Map construction");
      } else if (constructor === "Set") {
        collections.push({ id: `collection:Set:${node.getStart(sourceFile)}`, collection: "SET", operation: "construct", mutation: "CONSTRUCT", sourceRange: sourceRange(node, sourceFile) });
        addFeature("SET_COLLECTION", node, "Set construction");
      } else if (constructor === "Worker" || constructor === "SharedWorker") {
        addFeature("WORKER_RESOURCE", node, `${constructor} construction`);
      } else if (constructor === "BroadcastChannel" || constructor === "WebSocket" || constructor === "EventSource") {
        addFeature("SUBSCRIPTION_RESOURCE", node, `${constructor} construction`);
      }
    }

    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node;
      const tag = opening.tagName.getText(sourceFile);
      const lower = tag.toLowerCase();
      if (/^[A-Z]/.test(tag) || tag.includes(".")) {
        addFeature("COMPONENT_COMPOSITION", opening.tagName, `child component ${tag}`);
        if (ts.isJsxElement(node) && node.children.length > 0) {
          slots.push({ name: tag, sourceForm: tag.endsWith(".Provider") ? "PROVIDER" : "COMPONENT_CHILDREN", evaluationOwner: "PARENT", sourceRange: sourceRange(node, sourceFile) });
          addFeature("SLOT_PROJECTION", node, `children projected into ${tag}`);
        }
      }
      if (["table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col"].includes(lower)) addFeature("TABLE_SEMANTIC", opening.tagName, `HTML table element ${tag}`);
      else if (lower === "details" || lower === "summary") addFeature("DISCLOSURE_SEMANTIC", opening.tagName, `HTML disclosure element ${tag}`);
      else if (lower === "svg" || lower === "path" || lower === "circle" || lower === "rect" || lower === "line" || lower === "polyline" || lower === "polygon" || lower === "g") addFeature("SVG_SEMANTIC", opening.tagName, `SVG element ${tag}`);
      else if (lower === "html" || lower === "body" || lower === "head") addFeature("DOCUMENT_ROOT_SEMANTIC", opening.tagName, `document-root element ${tag}`);
      else if (["article", "aside", "footer", "header", "main", "nav", "section", "form", "ol", "dl", "dt", "dd", "figure", "figcaption", "code", "pre"].includes(lower)) addFeature("HTML_SEMANTIC", opening.tagName, `document semantic element ${tag}`);
    }

    if (ts.isJsxExpression(node) && node.expression !== undefined
      && ts.isIdentifier(node.expression) && node.expression.text === "children") {
      slots.push({ name: "children", sourceForm: "JSX_PROJECTION", evaluationOwner: "PARENT", sourceRange: sourceRange(node, sourceFile) });
      addFeature("SLOT_PROJECTION", node, "children expression projected into render tree");
    }

    ts.forEachChild(node, visit);
  };
  visit(component);

  if (reasonCode.includes("TYPE") && ![...featureMap.values()].some((feature) =>
    feature.kind === "LITERAL_UNION_TYPE" || feature.kind === "OBJECT_STATE"
      || feature.kind === "UNKNOWN_OR_INCOMPATIBLE_TYPE")) {
    addFeature("UNKNOWN_OR_INCOMPATIBLE_TYPE", component, reason);
  }
  if (featureMap.size === 0 || reasonCode.includes("EXPRESSION") && ![...featureMap.values()].some((feature) =>
    feature.kind === "EXTERNAL_HOOK" || feature.kind === "ASYNC_EFFECT" || feature.kind.endsWith("_RESOURCE")
      || feature.kind.endsWith("_COLLECTION"))) {
    addFeature("UNMODELED_SOURCE_SEMANTIC", component, `${reasonCode}: ${reason}`);
  }

  const features = [...featureMap.values()].sort((left, right) =>
    left.sourceRange.start - right.sourceRange.start || compareText(left.kind, right.kind) || compareText(left.id, right.id));
  const targetPlans = Object.fromEntries(ALL_FRAMEWORKS.map((target) => {
    const adapter = targetAdapter(target);
    const decisions = features.map((feature) => adapter.decideSemanticFeature(feature));
    const requiredEvidence = [...new Set(decisions.flatMap((item) => item.requiredEvidence))].sort(compareText);
    return [target, {
      targetFramework: target,
      adapterId: adapter.id,
      disposition: targetDisposition(decisions),
      decisions,
      requiredEvidence,
    } satisfies SourceTargetSemanticPlan];
  })) as Record<Framework, SourceTargetSemanticPlan>;
  const obligations = ALL_FRAMEWORKS.flatMap((target) => targetPlans[target].decisions
    .filter((item): item is TargetSemanticDecision & { mode: Exclude<TargetSemanticMode, "NATIVE"> } => item.mode !== "NATIVE")
    .map((item) => ({
      id: `obligation:${target}:${item.featureId}`,
      featureId: item.featureId,
      targetFramework: target,
      mode: item.mode,
      reason: item.reason,
      requiredEvidence: item.requiredEvidence,
    })));

  const base: Omit<SourceComponentSemanticIR, "irDigest"> = {
    schemaVersion: SOURCE_SEMANTIC_IR_SCHEMA_VERSION,
    kind: "elmos.source-component-semantic-ir",
    componentId: `${sourceFramework}:${sourcePath}:${componentName}`,
    source: {
      framework: sourceFramework,
      file: sourcePath,
      componentName,
      componentDigest: hash(componentText),
      sourceRange: componentRange,
    },
    blocker: { reasonCode, reason },
    captureStatus: features.some((feature) => feature.kind === "UNMODELED_SOURCE_SEMANTIC") ? "PARTIAL" : "REPRESENTED",
    imports,
    hooks: hooks.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    effects: effects.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    dataContracts: dataContracts.sort((a, b) => a.sourceRange.start - b.sourceRange.start || compareText(a.name, b.name)),
    collections: collections.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    slots: slots.sort((a, b) => a.sourceRange.start - b.sourceRange.start || compareText(a.name, b.name)),
    features,
    targetPlans,
    obligations,
  };
  return { ...base, irDigest: hash(canonicalJson(base)) };
}

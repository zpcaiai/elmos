/**
 * Lossless-enough semantic inventory for components outside the automatic
 * certified subset.
 *
 * This is intentionally not a second permissive parser. It never turns a
 * blocked component into an automatic success. Instead, the TypeScript AST
 * records the exact declaration range, hooks, resources, collections,
 * platform-only nodes, slots, CSS Modules and API references a hand-port
 * must account for. The resulting IR is digest-bound and feeds an explicit
 * target adapter; unsupported facts remain obligations.
 */
import * as crypto from "crypto";
import * as ts from "typescript";
import type { SemanticCategory } from "./cross-platform-ir";

export type ManualResourceKind = "NETWORK" | "TIMER" | "SUBSCRIPTION" | "STORAGE" | "NAVIGATION" | "WORKER" | "UNKNOWN";
export type ManualPlatformDomain = "TABLE" | "DISCLOSURE" | "SVG" | "DOCUMENT_ROOT" | "SLOT" | "CSS_MODULE";

export interface ManualComponentIR {
  schemaVersion: "1.0";
  kind: "elmos.manual-component-ir";
  source: {
    file: string;
    componentName: string;
    sha256: string;
    range: { start: number; end: number };
  };
  blocker: { reasonCode: string; reason: string; category: SemanticCategory };
  props: { name: string; type: string; optional: boolean }[];
  state: { name: string; setter: string; type: string; initializer: string; sourceRange: { start: number; end: number } }[];
  hooks: { callee: string; sourceRange: { start: number; end: number } }[];
  effects: {
    hook: string;
    resources: ManualResourceKind[];
    cleanup: "PRESENT" | "ABSENT" | "NOT_APPLICABLE";
    cancellationRequired: boolean;
    sourceRange: { start: number; end: number };
  }[];
  collections: { operation: "map" | "filter" | "reduce" | "Map" | "Set"; sourceRange: { start: number; end: number } }[];
  platformSemantics: { domain: ManualPlatformDomain; sourceName: string; targetAdapter: string }[];
  cssModuleTokens: string[];
  apiPaths: string[];
  textLabels: string[];
  obligations: { id: string; category: SemanticCategory; evidence: string[]; detail: string }[];
  targetPlan: {
    platform: "wechat";
    disposition: "HAND_PORTED";
    adapters: string[];
    runtimeEvidence: "NOT_RUN";
    certification: "NOT_CERTIFIED";
  };
  irDigest: string;
}

export interface ManualComponentIRInput {
  source: string;
  sourceFile: string;
  componentName: string;
  reasonCode: string;
  reason: string;
  category: SemanticCategory;
}

type ComponentNode = ts.FunctionDeclaration | ts.FunctionExpression | ts.ArrowFunction;

function sha256(value: string): string {
  return `sha256:${crypto.createHash("sha256").update(value, "utf8").digest("hex")}`;
}

function calleeName(expression: ts.Expression): string {
  if (ts.isIdentifier(expression)) return expression.text;
  if (ts.isPropertyAccessExpression(expression)) return `${calleeName(expression.expression)}.${expression.name.text}`;
  return expression.getText();
}

function componentNode(sourceFile: ts.SourceFile, name: string): ComponentNode {
  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.name?.text === name) return statement;
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || declaration.name.text !== name || declaration.initializer === undefined) continue;
      if (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer)) return declaration.initializer;
    }
  }
  throw new Error(`MANUAL_IR_COMPONENT_NOT_FOUND: ${name} in ${sourceFile.fileName}`);
}

function propsFor(node: ComponentNode, sourceFile: ts.SourceFile): ManualComponentIR["props"] {
  const parameter = node.parameters[0];
  if (parameter === undefined) return [];
  const type = parameter.type;
  const names = ts.isObjectBindingPattern(parameter.name)
    ? parameter.name.elements.map((element) => element.name.getText(sourceFile))
    : [parameter.name.getText(sourceFile)];
  if (type !== undefined && ts.isTypeLiteralNode(type)) {
    return type.members.flatMap((member) => {
      if (!ts.isPropertySignature(member) || member.name === undefined) return [];
      return [{
        name: member.name.getText(sourceFile).replace(/^['"]|['"]$/g, ""),
        type: member.type?.getText(sourceFile) ?? "unknown",
        optional: member.questionToken !== undefined,
      }];
    }).sort((a, b) => a.name.localeCompare(b.name));
  }
  return names.map((propName) => ({
    name: propName,
    type: type?.getText(sourceFile) ?? "unknown",
    optional: parameter.questionToken !== undefined || parameter.initializer !== undefined,
  })).sort((a, b) => a.name.localeCompare(b.name));
}

function resourcesFor(text: string): ManualResourceKind[] {
  const resources = new Set<ManualResourceKind>();
  if (/\bfetch\s*\(|\bwx\.request\s*\(/.test(text)) resources.add("NETWORK");
  if (/\bset(?:Timeout|Interval)\s*\(/.test(text)) resources.add("TIMER");
  if (/addEventListener|subscribe\s*\(|WebSocket|EventSource/.test(text)) resources.add("SUBSCRIPTION");
  if (/localStorage|sessionStorage|indexedDB|wx\.(?:get|set|remove)Storage/.test(text)) resources.add("STORAGE");
  if (/useRouter|router\.|navigate|location\./.test(text)) resources.add("NAVIGATION");
  if (/\bWorker\s*\(|worker\./.test(text)) resources.add("WORKER");
  if (resources.size === 0) resources.add("UNKNOWN");
  return [...resources].sort();
}

function hasCleanup(call: ts.CallExpression): boolean {
  const callback = call.arguments[0];
  if (callback === undefined || (!ts.isArrowFunction(callback) && !ts.isFunctionExpression(callback))) return false;
  if (!ts.isBlock(callback.body)) return ts.isArrowFunction(callback.body) || ts.isFunctionExpression(callback.body);
  return callback.body.statements.some((statement) =>
    ts.isReturnStatement(statement)
    && statement.expression !== undefined
    && (ts.isArrowFunction(statement.expression) || ts.isFunctionExpression(statement.expression)),
  );
}

function targetAdapter(domain: ManualPlatformDomain): string {
  switch (domain) {
    case "TABLE": return "wechat-scroll-row-table-v1";
    case "DISCLOSURE": return "wechat-controlled-disclosure-v1";
    case "SVG": return "wechat-icon-glyph-registry-v1";
    case "DOCUMENT_ROOT": return "wechat-app-page-lifecycle-v1";
    case "SLOT": return "wechat-named-slot-projection-v1";
    case "CSS_MODULE": return "wechat-css-module-token-map-v1";
  }
}

export function buildManualComponentIR(input: ManualComponentIRInput): ManualComponentIR {
  const sourceFile = ts.createSourceFile(input.sourceFile, input.source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const component = componentNode(sourceFile, input.componentName);
  const state: ManualComponentIR["state"] = [];
  const hooks: ManualComponentIR["hooks"] = [];
  const effects: ManualComponentIR["effects"] = [];
  const collections: ManualComponentIR["collections"] = [];
  const semantics = new Map<string, ManualComponentIR["platformSemantics"][number]>();
  const cssTokens = new Set<string>();
  const apiPaths = new Set<string>();
  const labels = new Set<string>();

  const addSemantic = (domain: ManualPlatformDomain, sourceName: string): void => {
    semantics.set(`${domain}:${sourceName}`, { domain, sourceName, targetAdapter: targetAdapter(domain) });
  };

  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) continue;
    if (!statement.moduleSpecifier.text.endsWith(".module.css")) continue;
    addSemantic("CSS_MODULE", statement.moduleSpecifier.text);
  }

  const visit = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node) && ts.isArrayBindingPattern(node.name) && node.initializer !== undefined && ts.isCallExpression(node.initializer)) {
      const call = calleeName(node.initializer.expression);
      if (call === "useState" && node.name.elements.length >= 2) {
        const stateBinding = node.name.elements[0];
        const setterBinding = node.name.elements[1];
        state.push({
          name: stateBinding && ts.isBindingElement(stateBinding) ? stateBinding.name.getText(sourceFile) : "state",
          setter: setterBinding && ts.isBindingElement(setterBinding) ? setterBinding.name.getText(sourceFile) : "setState",
          type: node.initializer.typeArguments?.[0]?.getText(sourceFile) ?? "inferred",
          initializer: node.initializer.arguments[0]?.getText(sourceFile) ?? "undefined",
          sourceRange: { start: node.getStart(sourceFile), end: node.getEnd() },
        });
      }
    }
    if (ts.isCallExpression(node)) {
      const call = calleeName(node.expression);
      if (/^use[A-Z]/.test(call)) {
        hooks.push({ callee: call, sourceRange: { start: node.getStart(sourceFile), end: node.getEnd() } });
      }
      if (call === "useEffect" || call === "useLayoutEffect") {
        const text = node.getText(sourceFile);
        const resources = resourcesFor(text);
        effects.push({
          hook: call,
          resources,
          cleanup: hasCleanup(node) ? "PRESENT" : "ABSENT",
          cancellationRequired: resources.some((resource) => resource !== "UNKNOWN"),
          sourceRange: { start: node.getStart(sourceFile), end: node.getEnd() },
        });
      }
      if (ts.isPropertyAccessExpression(node.expression) && ["map", "filter", "reduce"].includes(node.expression.name.text)) {
        collections.push({ operation: node.expression.name.text as "map" | "filter" | "reduce", sourceRange: { start: node.getStart(sourceFile), end: node.getEnd() } });
      }
    }
    if (ts.isNewExpression(node) && ts.isIdentifier(node.expression) && (node.expression.text === "Map" || node.expression.text === "Set")) {
      collections.push({ operation: node.expression.text, sourceRange: { start: node.getStart(sourceFile), end: node.getEnd() } });
    }
    if (ts.isStringLiteralLike(node)) {
      if (node.text.startsWith("/api/")) apiPaths.add(node.text);
      if (node.text.trim().length > 1 && node.text.trim().length <= 120) labels.add(node.text.trim());
    }
    if (ts.isJsxText(node)) {
      const text = node.getText(sourceFile).replace(/\s+/g, " ").trim();
      if (text.length > 1 && text.length <= 120) labels.add(text);
    }
    if (ts.isJsxAttribute(node) && ts.isIdentifier(node.name) && node.name.text === "className" && node.initializer && ts.isJsxExpression(node.initializer)) {
      const expression = node.initializer.expression;
      if (expression && ts.isPropertyAccessExpression(expression) && ts.isIdentifier(expression.expression)) cssTokens.add(expression.name.text);
    }
    const tag = ts.isJsxElement(node)
      ? node.openingElement.tagName.getText(sourceFile)
      : ts.isJsxSelfClosingElement(node) ? node.tagName.getText(sourceFile) : null;
    if (tag !== null) {
      if (["table", "thead", "tbody", "tr", "th", "td"].includes(tag)) addSemantic("TABLE", tag);
      if (tag === "details" || tag === "summary") addSemantic("DISCLOSURE", tag);
      if (tag === "svg" || tag === "path") addSemantic("SVG", tag);
      if (tag === "html" || tag === "body" || tag === "head") addSemantic("DOCUMENT_ROOT", tag);
      if (/^[A-Z]/.test(tag)) {
        const childCount = ts.isJsxElement(node) ? node.children.filter((child) => !ts.isJsxText(child) || child.getText(sourceFile).trim()).length : 0;
        if (childCount > 0) addSemantic("SLOT", tag);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(component);

  if (propsFor(component, sourceFile).some((prop) => prop.name === "children" || prop.type.includes("ReactNode"))) addSemantic("SLOT", "children");
  const semanticValues = [...semantics.values()].sort((a, b) => `${a.domain}:${a.sourceName}`.localeCompare(`${b.domain}:${b.sourceName}`));
  const adapters = new Set(semanticValues.map((item) => item.targetAdapter));
  if (effects.length > 0 || hooks.some((hook) => hook.callee !== "useState")) adapters.add("wechat-effect-resource-lifecycle-v1");
  if (state.length > 0) adapters.add("wechat-typed-state-decoder-v1");
  if (collections.length > 0) adapters.add("wechat-plain-collection-projection-v1");
  if (apiPaths.size > 0) adapters.add("wechat-cancellable-request-v1");
  const obligations: ManualComponentIR["obligations"] = [{
    id: `${input.componentName}:source-blocker`,
    category: input.category,
    evidence: ["official-target-build", "emulator-or-device-journey", "differential-behavior", "independent-review"],
    detail: `${input.reasonCode}: ${input.reason}`,
  }];
  for (const effect of effects.filter((item) => item.cancellationRequired && item.cleanup === "ABSENT")) {
    obligations.push({
      id: `${input.componentName}:effect-cleanup:${effect.sourceRange.start}`,
      category: "effects-and-resources",
      evidence: ["cancellation-test", "detached-lifecycle-test"],
      detail: "source effect has an external resource without an explicit cleanup; target adapter supplies cancellation and requires differential validation",
    });
  }

  const withoutDigest: Omit<ManualComponentIR, "irDigest"> = {
    schemaVersion: "1.0",
    kind: "elmos.manual-component-ir",
    source: {
      file: input.sourceFile,
      componentName: input.componentName,
      sha256: sha256(input.source),
      range: { start: component.getStart(sourceFile), end: component.getEnd() },
    },
    blocker: { reasonCode: input.reasonCode, reason: input.reason, category: input.category },
    props: propsFor(component, sourceFile),
    state: state.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    hooks: hooks.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    effects: effects.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    collections: collections.sort((a, b) => a.sourceRange.start - b.sourceRange.start),
    platformSemantics: semanticValues,
    cssModuleTokens: [...cssTokens].sort(),
    apiPaths: [...apiPaths].sort(),
    textLabels: [...labels].sort().slice(0, 24),
    obligations,
    targetPlan: {
      platform: "wechat",
      disposition: "HAND_PORTED",
      adapters: [...adapters].sort(),
      runtimeEvidence: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    },
  };
  return { ...withoutDigest, irDigest: sha256(JSON.stringify(withoutDigest)) };
}

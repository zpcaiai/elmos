/**
 * Source extractors for the four non-web FRT source stacks.
 *
 * Each extractor accepts one deliberately bounded counter-route grammar.  The
 * grammar is parsed from source bytes (Vue/JavaScript with compiler ASTs,
 * WXML with a structural parser, and ArkTS/Dart with balanced lexical tokens).
 * Unsupported syntax blocks with a registered typed gap; no IR field is
 * defaulted from a caller declaration.
 */

import { parse as parseVueSfc } from "@vue/compiler-sfc";
import ts from "typescript";

import {
  canonical,
  contentAddressedSourceRefs,
  gap,
  sha256,
  type FrtRouteStack,
  type FrtRouteTypedGap,
  type PortableUiIr,
} from "./frt-route-ir.js";

const exactVersion = /^(?:[0-9]+\.)+[0-9]+$/;
const vue2Version = /^2\./;
const accentRule = /^button\s*\{\s*color\s*:\s*(#[0-9A-Fa-f]{6})\s*;?\s*\}$/;
const identifier = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

function buildIr(
  stack: FrtRouteStack,
  version: string,
  files: Readonly<Record<string, string>>,
  values: {
    readonly title: string;
    readonly initialCount: number;
    readonly incrementBy: number;
    readonly buttonLabel: string;
    readonly accentColor: string;
    readonly mainLabel: string;
    readonly accessibleButtonLabel: string;
  },
): PortableUiIr {
  const sourceRefs = contentAddressedSourceRefs(files, new Set(["frt-ui-ir.json"]));
  return {
    schemaVersion: "1.0",
    source: { stack, version },
    sourceSnapshotDigest: sha256(canonical(sourceRefs)),
    sourceRefs,
    route: { path: "/", requiresAuth: false, deepLink: true },
    view: {
      title: values.title,
      initialCount: values.initialCount,
      incrementBy: values.incrementBy,
      buttonLabel: values.buttonLabel,
    },
    style: { accentColor: values.accentColor },
    accessibility: {
      mainLabel: values.mainLabel,
      buttonLabel: values.accessibleButtonLabel,
      liveRegion: "polite",
    },
    capabilities: { permissions: [], native: [], network: [] },
  };
}

function integerLiteral(node: ts.Expression): number | undefined {
  if (ts.isNumericLiteral(node)) {
    const value = Number(node.text);
    return Number.isInteger(value) ? value : undefined;
  }
  if (ts.isPrefixUnaryExpression(node) && ts.isNumericLiteral(node.operand)
      && (node.operator === ts.SyntaxKind.MinusToken || node.operator === ts.SyntaxKind.PlusToken)) {
    const value = Number(node.operand.text);
    if (!Number.isInteger(value)) return undefined;
    return node.operator === ts.SyntaxKind.MinusToken ? -value : value;
  }
  return undefined;
}

function propertyName(node: ts.ObjectLiteralElementLike): string | undefined {
  const name = node.name;
  if (!name) return undefined;
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) return name.text;
  return undefined;
}

function objectProperty(object: ts.ObjectLiteralExpression, name: string): ts.ObjectLiteralElementLike | undefined {
  return object.properties.find(property => propertyName(property) === name);
}

function propertyInitializer(property: ts.ObjectLiteralElementLike | undefined): ts.Expression | undefined {
  return property && ts.isPropertyAssignment(property) ? property.initializer : undefined;
}

function returnedObject(expression: ts.Expression): ts.ObjectLiteralExpression | undefined {
  const value = ts.isParenthesizedExpression(expression) ? expression.expression : expression;
  if (ts.isObjectLiteralExpression(value)) return value;
  if ((ts.isArrowFunction(value) || ts.isFunctionExpression(value)) && !ts.isBlock(value.body)) {
    return returnedObject(value.body);
  }
  if ((ts.isArrowFunction(value) || ts.isFunctionExpression(value)) && ts.isBlock(value.body)) {
    const returns = value.body.statements.filter(ts.isReturnStatement);
    const returned = returns.length === 1 ? returns[0]!.expression : undefined;
    if (returned) return returnedObject(returned);
  }
  return undefined;
}

interface VueTemplateNode {
  readonly type: number;
  readonly tag?: string;
  readonly tagType?: number;
  readonly content?: string | { readonly content?: string };
  readonly children?: readonly VueTemplateNode[];
  readonly props?: readonly VueTemplateProp[];
}

interface VueTemplateProp {
  readonly type: number;
  readonly name?: string;
  readonly value?: { readonly content?: string };
  readonly arg?: { readonly content?: string };
  readonly exp?: { readonly content?: string };
  readonly modifiers?: readonly unknown[];
}

const VUE_ROOT = 0;
const VUE_ELEMENT = 1;
const VUE_TEXT = 2;
const VUE_INTERPOLATION = 5;
const VUE_ATTRIBUTE = 6;
const VUE_DIRECTIVE = 7;

function significantVueChildren(node: VueTemplateNode): readonly VueTemplateNode[] {
  return (node.children ?? []).filter(child => {
    if (child.type !== VUE_TEXT || typeof child.content !== "string") return true;
    return child.content.trim().length > 0;
  });
}

function vueStaticAttribute(node: VueTemplateNode, name: string): string | undefined {
  const prop = (node.props ?? []).find(item => item.type === VUE_ATTRIBUTE && item.name === name);
  return prop?.value?.content;
}

function vueInterpolation(node: VueTemplateNode): string | undefined {
  if (node.type !== VUE_INTERPOLATION || typeof node.content !== "object") return undefined;
  const value = node.content.content?.trim();
  return value && identifier.test(value) ? value : undefined;
}

function vueText(
  node: VueTemplateNode,
  strings: ReadonlyMap<string, string>,
): string | undefined {
  const children = significantVueChildren(node);
  if (children.length !== 1) return undefined;
  const child = children[0]!;
  if (child.type === VUE_TEXT && typeof child.content === "string") return child.content.trim();
  const name = vueInterpolation(child);
  return name === undefined ? undefined : strings.get(name);
}

function checkVueProps(
  node: VueTemplateNode,
  allowedAttributes: readonly string[],
  allowClick: boolean,
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): void {
  for (const prop of node.props ?? []) {
    const allowedAttribute = prop.type === VUE_ATTRIBUTE && allowedAttributes.includes(prop.name ?? "");
    const allowedClick = allowClick && prop.type === VUE_DIRECTIVE && prop.name === "on"
      && prop.arg?.content === "click" && (prop.modifiers?.length ?? 0) === 0;
    if (!allowedAttribute && !allowedClick) {
      gap(gaps, "FRT_VUE2_TEMPLATE_SEMANTIC_UNSUPPORTED", sourcePath,
        `Property ${prop.name ?? "<unknown>"} on <${node.tag ?? "?"}> is outside the bounded route grammar.`);
    }
  }
}

function vue2MethodDelta(method: ts.ObjectLiteralElementLike, stateName: string): number | undefined {
  if (!ts.isMethodDeclaration(method) || method.parameters.length !== 0 || !method.body
      || method.body.statements.length !== 1) return undefined;
  const statement = method.body.statements[0]!;
  if (!ts.isExpressionStatement(statement)) return undefined;
  const expression = statement.expression;
  const isState = (node: ts.Expression): boolean => ts.isPropertyAccessExpression(node)
    && node.expression.kind === ts.SyntaxKind.ThisKeyword && node.name.text === stateName;
  if (ts.isPostfixUnaryExpression(expression) && isState(expression.operand)) {
    if (expression.operator === ts.SyntaxKind.PlusPlusToken) return 1;
    if (expression.operator === ts.SyntaxKind.MinusMinusToken) return -1;
  }
  if (ts.isBinaryExpression(expression) && isState(expression.left)) {
    const value = integerLiteral(expression.right);
    if (value === undefined) return undefined;
    if (expression.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken) return value;
    if (expression.operatorToken.kind === ts.SyntaxKind.MinusEqualsToken) return -value;
  }
  return undefined;
}

/** Derive Vue 2 Options API source into the portable interaction IR. */
export function deriveVue2PortableUiIr(
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  const before = gaps.length;
  let version: string | undefined;
  try {
    const manifest = JSON.parse(files["package.json"] ?? "") as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const declared = manifest.dependencies?.vue ?? manifest.devDependencies?.vue;
    if (!declared || !exactVersion.test(declared) || !vue2Version.test(declared)) {
      gap(gaps, "FRT_VUE2_SOURCE_VERSION_NOT_EXACT", "package.json",
        `The Vue dependency ${declared ?? "<missing>"} is not an exact Vue 2 version.`);
    } else version = declared;
  } catch {
    gap(gaps, "FRT_VUE2_PACKAGE_MANIFEST_INVALID", "package.json",
      "package.json is required and must be valid JSON.");
  }

  const components = Object.keys(files).filter(path => path.endsWith(".vue")).sort();
  const sourcePath = components[0] ?? "<missing-vue2-sfc>";
  if (components.length !== 1) {
    gap(gaps, "FRT_VUE2_SFC_CARDINALITY_UNSUPPORTED", sourcePath,
      `${components.length} Vue SFCs were found; exactly one is supported.`);
    return undefined;
  }
  const parsed = parseVueSfc(files[sourcePath]!, { filename: sourcePath, sourceMap: false });
  if (parsed.errors.length > 0) {
    gap(gaps, "FRT_VUE2_SFC_PARSE_ERROR", sourcePath, String(parsed.errors[0]));
    return undefined;
  }
  const descriptor = parsed.descriptor;
  if (!descriptor.script || descriptor.scriptSetup || !descriptor.template?.ast) {
    gap(gaps, "FRT_VUE2_COMPONENT_MODE_UNSUPPORTED", sourcePath,
      "Exactly one classic Options API script and one template are required.");
    return undefined;
  }

  const script = ts.createSourceFile(sourcePath, descriptor.script.content, ts.ScriptTarget.ESNext, true, ts.ScriptKind.JS);
  const diagnostics = (script as ts.SourceFile & { readonly parseDiagnostics?: readonly unknown[] }).parseDiagnostics ?? [];
  const exports = script.statements.filter(ts.isExportAssignment);
  if (diagnostics.length > 0 || script.statements.length !== 1 || exports.length !== 1
      || !ts.isObjectLiteralExpression(exports[0]!.expression)) {
    gap(gaps, "FRT_VUE2_OPTIONS_API_UNSUPPORTED", sourcePath,
      "The script must be one `export default` object with data and methods.");
    return undefined;
  }
  const component = exports[0]!.expression;
  const componentKeys = component.properties.map(propertyName);
  if (componentKeys.length !== 2 || !componentKeys.includes("data") || !componentKeys.includes("methods")) {
    gap(gaps, "FRT_VUE2_OPTIONS_API_UNSUPPORTED", sourcePath,
      "Only exact data and methods options are modeled; lifecycle, props, computed, and mixins require mappings.");
  }
  const data = returnedObject(propertyInitializer(objectProperty(component, "data")) ?? ts.factory.createNull());
  const methods = propertyInitializer(objectProperty(component, "methods"));
  if (!data || !methods || !ts.isObjectLiteralExpression(methods)) {
    gap(gaps, "FRT_VUE2_STATE_ACTION_NOT_DERIVABLE", sourcePath,
      "data must return an object and methods must be an object literal.");
    return undefined;
  }
  const dataKeys = data.properties.map(propertyName);
  const methodKeys = methods.properties.map(propertyName);
  if (dataKeys.length !== 3 || !["title", "buttonLabel", "count"].every(name => dataKeys.includes(name))
      || methodKeys.length !== 1 || methodKeys[0] !== "increment") {
    gap(gaps, "FRT_VUE2_STATE_ACTION_NOT_DERIVABLE", sourcePath,
      "The bounded route requires title, buttonLabel, count, and one increment method, with no hidden state or actions.");
  }
  const titleNode = propertyInitializer(objectProperty(data, "title"));
  const buttonNode = propertyInitializer(objectProperty(data, "buttonLabel"));
  const countNode = propertyInitializer(objectProperty(data, "count"));
  const title = titleNode && ts.isStringLiteral(titleNode) ? titleNode.text : undefined;
  const buttonLabel = buttonNode && ts.isStringLiteral(buttonNode) ? buttonNode.text : undefined;
  const initialCount = countNode ? integerLiteral(countNode) : undefined;
  const incrementMethod = objectProperty(methods, "increment");
  const incrementBy = incrementMethod ? vue2MethodDelta(incrementMethod, "count") : undefined;
  if (title === undefined || buttonLabel === undefined || initialCount === undefined || incrementBy === undefined) {
    gap(gaps, "FRT_VUE2_STATE_ACTION_NOT_DERIVABLE", sourcePath,
      "Literal text/integer state or the deterministic integer increment action could not be read.");
  }

  const root = descriptor.template.ast as unknown as VueTemplateNode;
  const roots = root.type === VUE_ROOT ? significantVueChildren(root) : [];
  const main = roots.length === 1 ? roots[0] : undefined;
  if (!main || main.type !== VUE_ELEMENT || main.tag !== "main" || main.tagType !== 0) {
    gap(gaps, "FRT_VUE2_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "The route must have one plain <main> root.");
    return undefined;
  }
  checkVueProps(main, ["aria-label"], false, sourcePath, gaps);
  const parts = significantVueChildren(main);
  const heading = parts[0];
  const button = parts[1];
  const live = parts[2];
  if (parts.length !== 3 || heading?.tag !== "h1" || button?.tag !== "button" || live?.tag !== "p") {
    gap(gaps, "FRT_VUE2_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "The route must contain exactly h1, button, and p in that order.");
    return undefined;
  }
  checkVueProps(heading, [], false, sourcePath, gaps);
  checkVueProps(button, ["aria-label"], true, sourcePath, gaps);
  checkVueProps(live, ["aria-live"], false, sourcePath, gaps);
  const strings = new Map<string, string>();
  if (title !== undefined) strings.set("title", title);
  if (buttonLabel !== undefined) strings.set("buttonLabel", buttonLabel);
  if (vueText(heading, strings) !== title || vueText(button, strings) !== buttonLabel
      || vueInterpolation(significantVueChildren(live)[0] ?? { type: -1 }) !== "count") {
    gap(gaps, "FRT_VUE2_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "Template bindings do not resolve exactly to title, buttonLabel, and count.");
  }
  const click = (button.props ?? []).find(prop => prop.type === VUE_DIRECTIVE && prop.name === "on"
    && prop.arg?.content === "click")?.exp?.content?.trim();
  if (click !== "increment") {
    gap(gaps, "FRT_VUE2_STATE_ACTION_NOT_DERIVABLE", sourcePath,
      "The button must bind directly to the increment method.");
  }
  const mainLabel = vueStaticAttribute(main, "aria-label");
  const accessibleButtonLabel = vueStaticAttribute(button, "aria-label");
  const liveMode = vueStaticAttribute(live, "aria-live");
  if (!mainLabel || !accessibleButtonLabel || !liveMode) {
    gap(gaps, "FRT_VUE2_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "main aria-label, button aria-label, and the live-region declaration are all required in source.");
  } else if (liveMode !== "polite") {
    gap(gaps, "FRT_VUE2_LIVE_REGION_UNSUPPORTED", sourcePath,
      `aria-live=${JSON.stringify(liveMode)} cannot be represented by this IR slice.`);
  }

  let accentColor: string | undefined;
  if (descriptor.styles.length !== 1) {
    gap(gaps, "FRT_VUE2_STYLE_UNSUPPORTED", sourcePath,
      `${descriptor.styles.length} style blocks were found; exactly one is supported.`);
  } else {
    accentColor = accentRule.exec(descriptor.styles[0]!.content.trim())?.[1];
    if (!accentColor) gap(gaps, "FRT_VUE2_STYLE_UNSUPPORTED", sourcePath,
      "The style must be exactly one button color token.");
  }
  if (gaps.length !== before || version === undefined || title === undefined || buttonLabel === undefined
      || initialCount === undefined || incrementBy === undefined || accentColor === undefined
      || mainLabel === undefined || accessibleButtonLabel === undefined) return undefined;
  return buildIr("Vue 2", version, files, {
    title, buttonLabel, initialCount, incrementBy, accentColor, mainLabel, accessibleButtonLabel,
  });
}

interface XmlElement {
  readonly name: string;
  readonly attributes: ReadonlyMap<string, string>;
  readonly children: readonly (XmlElement | string)[];
}

function xmlDecode(value: string): string {
  return value.replaceAll("&quot;", '"').replaceAll("&apos;", "'")
    .replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&");
}

/** A strict, non-executing WXML structural parser for the bounded fixture. */
function parseWxml(source: string): XmlElement {
  let cursor = 0;
  const whitespace = (): void => { while (/\s/.test(source[cursor] ?? "")) cursor += 1; };
  const name = (): string => {
    const start = cursor;
    while (/[A-Za-z0-9_:@-]/.test(source[cursor] ?? "")) cursor += 1;
    const value = source.slice(start, cursor);
    if (!value) throw new Error("expected WXML name");
    return value;
  };
  const element = (): XmlElement => {
    if (source[cursor] !== "<" || source[cursor + 1] === "/") throw new Error("expected opening tag");
    cursor += 1;
    const tag = name();
    const attributes = new Map<string, string>();
    whitespace();
    while (source[cursor] !== ">") {
      const attribute = name();
      whitespace();
      if (source[cursor] !== "=") throw new Error("WXML attributes require explicit values");
      cursor += 1;
      whitespace();
      const quote = source[cursor];
      if (quote !== '"' && quote !== "'") throw new Error("WXML attribute value must be quoted");
      cursor += 1;
      const start = cursor;
      while (cursor < source.length && source[cursor] !== quote) cursor += 1;
      if (cursor >= source.length) throw new Error("unterminated WXML attribute");
      if (attributes.has(attribute)) throw new Error("duplicate WXML attribute");
      attributes.set(attribute, xmlDecode(source.slice(start, cursor)));
      cursor += 1;
      whitespace();
    }
    cursor += 1;
    const children: (XmlElement | string)[] = [];
    while (true) {
      if (source.startsWith(`</${tag}`, cursor)) {
        cursor += tag.length + 2;
        whitespace();
        if (source[cursor] !== ">") throw new Error("invalid closing tag");
        cursor += 1;
        return { name: tag, attributes, children };
      }
      if (source[cursor] === "<") children.push(element());
      else {
        const start = cursor;
        while (cursor < source.length && source[cursor] !== "<") cursor += 1;
        const text = xmlDecode(source.slice(start, cursor)).trim();
        if (text) children.push(text);
      }
      if (cursor >= source.length) throw new Error(`unclosed <${tag}>`);
    }
  };
  whitespace();
  const root = element();
  whitespace();
  if (cursor !== source.length) throw new Error("multiple WXML roots are unsupported");
  return root;
}

function exactAttributes(element: XmlElement, names: readonly string[]): boolean {
  return element.attributes.size === names.length && names.every(name => element.attributes.has(name));
}

function miniProgramModel(source: string): {
  readonly count?: number | undefined;
  readonly buttonLabel?: string | undefined;
  readonly incrementBy?: number | undefined;
} {
  const file = ts.createSourceFile("index.js", source, ts.ScriptTarget.ESNext, true, ts.ScriptKind.JS);
  const diagnostics = (file as ts.SourceFile & { readonly parseDiagnostics?: readonly unknown[] }).parseDiagnostics ?? [];
  if (diagnostics.length !== 0 || file.statements.length !== 1) return {};
  const statement = file.statements[0]!;
  if (!ts.isExpressionStatement(statement) || !ts.isCallExpression(statement.expression)
      || !ts.isIdentifier(statement.expression.expression) || statement.expression.expression.text !== "Page"
      || statement.expression.arguments.length !== 1 || !ts.isObjectLiteralExpression(statement.expression.arguments[0]!)) return {};
  const page = statement.expression.arguments[0]!;
  const keys = page.properties.map(propertyName);
  if (keys.length !== 2 || !keys.includes("data") || !keys.includes("increment")) return {};
  const data = propertyInitializer(objectProperty(page, "data"));
  const increment = objectProperty(page, "increment");
  if (!data || !ts.isObjectLiteralExpression(data) || !increment || !ts.isMethodDeclaration(increment)
      || !increment.body || increment.parameters.length !== 0 || increment.body.statements.length !== 1) return {};
  const dataKeys = data.properties.map(propertyName);
  if (dataKeys.length !== 2 || !dataKeys.includes("count") || !dataKeys.includes("buttonLabel")) return {};
  const countNode = propertyInitializer(objectProperty(data, "count"));
  const labelNode = propertyInitializer(objectProperty(data, "buttonLabel"));
  const count = countNode ? integerLiteral(countNode) : undefined;
  const buttonLabel = labelNode && ts.isStringLiteral(labelNode) ? labelNode.text : undefined;
  const action = increment.body.statements[0]!;
  if (!ts.isExpressionStatement(action) || !ts.isCallExpression(action.expression)
      || !ts.isPropertyAccessExpression(action.expression.expression)
      || action.expression.expression.name.text !== "setData"
      || action.expression.expression.expression.kind !== ts.SyntaxKind.ThisKeyword
      || action.expression.arguments.length !== 1 || !ts.isObjectLiteralExpression(action.expression.arguments[0]!)) {
    return { count, buttonLabel };
  }
  const update = action.expression.arguments[0]!;
  if (update.properties.length !== 1 || propertyName(update.properties[0]!) !== "count") return { count, buttonLabel };
  const value = propertyInitializer(update.properties[0]!);
  if (!value || !ts.isBinaryExpression(value) || value.operatorToken.kind !== ts.SyntaxKind.PlusToken
      || !ts.isPropertyAccessExpression(value.left) || value.left.name.text !== "count"
      || !ts.isPropertyAccessExpression(value.left.expression) || value.left.expression.name.text !== "data"
      || value.left.expression.expression.kind !== ts.SyntaxKind.ThisKeyword) return { count, buttonLabel };
  return { count, buttonLabel, incrementBy: integerLiteral(value.right) };
}

/** Derive a native WeChat Mini Program Page/WXML route. */
export function deriveMiniProgramPortableUiIr(
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  const before = gaps.length;
  let version: string | undefined;
  try {
    const project = JSON.parse(files["project.config.json"] ?? "") as { libVersion?: unknown; compileType?: unknown };
    if (typeof project.libVersion !== "string" || !exactVersion.test(project.libVersion)
        || project.compileType !== "miniprogram") {
      gap(gaps, "FRT_MINIPROGRAM_PROJECT_PROFILE_INVALID", "project.config.json",
        "The project must pin an exact base-library version and compileType=miniprogram.");
    } else version = project.libVersion;
  } catch {
    gap(gaps, "FRT_MINIPROGRAM_PROJECT_PROFILE_INVALID", "project.config.json",
      "project.config.json is required and must be valid JSON.");
  }
  const wxmls = Object.keys(files).filter(path => path.endsWith(".wxml")).sort();
  const scripts = Object.keys(files).filter(path => path.endsWith(".js")).sort();
  const styles = Object.keys(files).filter(path => path.endsWith(".wxss")).sort();
  const sourcePath = wxmls[0] ?? "<missing-wxml>";
  if (wxmls.length !== 1 || scripts.length !== 1 || styles.length !== 1) {
    gap(gaps, "FRT_MINIPROGRAM_PAGE_CARDINALITY_UNSUPPORTED", sourcePath,
      `Expected one WXML, one Page script, and one WXSS; found ${wxmls.length}/${scripts.length}/${styles.length}.`);
    return undefined;
  }
  let root: XmlElement;
  try {
    root = parseWxml(files[wxmls[0]!]!);
  } catch (error) {
    gap(gaps, "FRT_MINIPROGRAM_WXML_PARSE_ERROR", sourcePath,
      error instanceof Error ? error.message : "WXML parse failed.");
    return undefined;
  }
  const children = root.children.filter((child): child is XmlElement => typeof child !== "string");
  if (root.name !== "view" || children.length !== 3 || root.children.length !== 3
      || children[0]!.name !== "text" || children[1]!.name !== "button" || children[2]!.name !== "text"
      || !exactAttributes(root, ["role", "aria-label"])
      || !exactAttributes(children[0]!, [])
      || !exactAttributes(children[1]!, ["aria-label", "bindtap"])
      || !exactAttributes(children[2]!, ["aria-live"])) {
    gap(gaps, "FRT_MINIPROGRAM_WXML_SEMANTIC_UNSUPPORTED", sourcePath,
      "The WXML must be one accessible view containing exact title, button, and live counter nodes.");
    return undefined;
  }
  const title = typeof children[0]!.children[0] === "string" && children[0]!.children.length === 1
    ? children[0]!.children[0] : undefined;
  const buttonBinding = children[1]!.children.length === 1 ? children[1]!.children[0] : undefined;
  const countBinding = children[2]!.children.length === 1 ? children[2]!.children[0] : undefined;
  if (!title || buttonBinding !== "{{buttonLabel}}" || countBinding !== "{{count}}"
      || root.attributes.get("role") !== "main" || children[1]!.attributes.get("bindtap") !== "increment") {
    gap(gaps, "FRT_MINIPROGRAM_WXML_SEMANTIC_UNSUPPORTED", sourcePath,
      "WXML bindings must resolve directly to buttonLabel, count, and increment.");
  }
  const mainLabel = root.attributes.get("aria-label");
  const accessibleButtonLabel = children[1]!.attributes.get("aria-label");
  const liveMode = children[2]!.attributes.get("aria-live");
  if (!mainLabel || !accessibleButtonLabel || !liveMode) {
    gap(gaps, "FRT_MINIPROGRAM_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "role=main, both labels, and a live-region declaration are required.");
  } else if (liveMode !== "polite") {
    gap(gaps, "FRT_MINIPROGRAM_LIVE_REGION_UNSUPPORTED", sourcePath,
      `aria-live=${JSON.stringify(liveMode)} cannot be represented by this IR slice.`);
  }
  const model = miniProgramModel(files[scripts[0]!]!);
  if (model.count === undefined || model.buttonLabel === undefined || model.incrementBy === undefined) {
    gap(gaps, "FRT_MINIPROGRAM_STATE_ACTION_NOT_DERIVABLE", scripts[0]!,
      "Page data and setData must express one literal count/buttonLabel and one deterministic count delta.");
  }
  const accentColor = accentRule.exec(files[styles[0]!]!.trim())?.[1];
  if (!accentColor) gap(gaps, "FRT_MINIPROGRAM_STYLE_UNSUPPORTED", styles[0]!,
    "WXSS must be exactly one button color token.");
  if (gaps.length !== before || version === undefined || title === undefined
      || model.count === undefined || model.buttonLabel === undefined || model.incrementBy === undefined
      || accentColor === undefined || mainLabel === undefined || accessibleButtonLabel === undefined) return undefined;
  return buildIr("WeChat Mini Program", version, files, {
    title, initialCount: model.count, incrementBy: model.incrementBy, buttonLabel: model.buttonLabel,
    accentColor, mainLabel, accessibleButtonLabel,
  });
}

interface LexToken {
  readonly kind: "word" | "string" | "number" | "punct";
  readonly value: string;
}

/** Balanced tokenizer shared by the strict ArkTS and Dart source grammars. */
function lexicalTokens(source: string): readonly LexToken[] {
  const result: LexToken[] = [];
  const closers: Record<string, string> = { "(": ")", "[": "]", "{": "}" };
  const stack: string[] = [];
  let cursor = 0;
  while (cursor < source.length) {
    const char = source[cursor]!;
    if (/\s/.test(char)) { cursor += 1; continue; }
    if (char === "/" && source[cursor + 1] === "/") {
      cursor += 2;
      while (cursor < source.length && source[cursor] !== "\n") cursor += 1;
      continue;
    }
    if (char === "/" && source[cursor + 1] === "*") {
      const end = source.indexOf("*/", cursor + 2);
      if (end < 0) throw new Error("unterminated block comment");
      cursor = end + 2;
      continue;
    }
    if (char === '"' || char === "'") {
      const quote = char;
      cursor += 1;
      let value = "";
      let closed = false;
      while (cursor < source.length) {
        const item = source[cursor++]!;
        if (item === quote) { closed = true; break; }
        if (item === "\\") {
          if (cursor >= source.length) throw new Error("unterminated escape");
          const escaped = source[cursor++]!;
          const mappings: Record<string, string> = { n: "\n", r: "\r", t: "\t", "\\": "\\", '"': '"', "'": "'", "$": "$" };
          value += mappings[escaped] ?? escaped;
        } else value += item;
      }
      if (!closed) throw new Error("unterminated string");
      result.push({ kind: "string", value });
      continue;
    }
    if (/[A-Za-z_$]/.test(char)) {
      const start = cursor++;
      while (/[A-Za-z0-9_$]/.test(source[cursor] ?? "")) cursor += 1;
      result.push({ kind: "word", value: source.slice(start, cursor) });
      continue;
    }
    if (/[0-9]/.test(char)) {
      const start = cursor++;
      while (/[0-9A-Fa-f_xX]/.test(source[cursor] ?? "")) cursor += 1;
      result.push({ kind: "number", value: source.slice(start, cursor) });
      continue;
    }
    const two = source.slice(cursor, cursor + 2);
    if (["=>", "+=", "-=", "++", "--", ">=", "<="].includes(two)) {
      result.push({ kind: "punct", value: two });
      cursor += 2;
      continue;
    }
    if (Object.hasOwn(closers, char)) stack.push(closers[char]!);
    else if ([")", "]", "}"].includes(char) && stack.pop() !== char) throw new Error("unbalanced delimiters");
    result.push({ kind: "punct", value: char });
    cursor += 1;
  }
  if (stack.length !== 0) throw new Error("unbalanced delimiters");
  return result;
}

function tokenIndex(tokens: readonly LexToken[], pattern: readonly string[], start = 0): number {
  outer: for (let index = start; index <= tokens.length - pattern.length; index += 1) {
    for (let offset = 0; offset < pattern.length; offset += 1) {
      if (tokens[index + offset]!.value !== pattern[offset]) continue outer;
    }
    return index;
  }
  return -1;
}

function following(tokens: readonly LexToken[], pattern: readonly string[], kind: LexToken["kind"]): LexToken | undefined {
  const index = tokenIndex(tokens, pattern);
  const value = index < 0 ? undefined : tokens[index + pattern.length];
  return value?.kind === kind ? value : undefined;
}

function tokenIdentity(tokens: readonly LexToken[]): string {
  return tokens.map(token => `${token.kind}:${token.value}`).join("\u0000");
}

function arkSource(values: {
  readonly title: string; readonly mainLabel: string; readonly buttonLabel: string;
  readonly accessibleButtonLabel: string; readonly initialCount: number;
  readonly incrementBy: number; readonly accentColor: string;
}): string {
  return [
    "@Entry",
    "@Component",
    "struct Index {",
    `  @State count: number = ${values.initialCount};`,
    "  build() {",
    "    Column() {",
    `      Text(${JSON.stringify(values.title)}).accessibilityText(${JSON.stringify(values.mainLabel)})`,
    `      Button(${JSON.stringify(values.buttonLabel)}).accessibilityText(${JSON.stringify(values.accessibleButtonLabel)}).onClick(() => { this.count += ${values.incrementBy}; })`,
    "      Text(this.count.toString()).accessibilityLevel('yes')",
    `    }.fontColor('${values.accentColor}')`,
    "  }",
    "}",
    "",
  ].join("\n");
}

/** Derive the exact ArkUI/ArkTS counter component grammar. */
export function deriveArkUiPortableUiIr(
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  const before = gaps.length;
  let version: string | undefined;
  try {
    const profile = JSON.parse(files["build-profile.json5"] ?? "") as { apiVersion?: unknown };
    if (!Number.isInteger(profile.apiVersion) || (profile.apiVersion as number) < 1) {
      gap(gaps, "FRT_ARKUI_PROFILE_INVALID", "build-profile.json5",
        "build-profile.json5 must pin one numeric apiVersion.");
    } else version = `6.0.0(${String(profile.apiVersion)})`;
  } catch {
    gap(gaps, "FRT_ARKUI_PROFILE_INVALID", "build-profile.json5",
      "build-profile.json5 is required and must be parseable JSON5-compatible JSON.");
  }
  const modules = Object.keys(files).filter(path => path.endsWith(".ets")).sort();
  const sourcePath = modules[0] ?? "<missing-arkts-module>";
  if (modules.length !== 1) {
    gap(gaps, "FRT_ARKUI_MODULE_CARDINALITY_UNSUPPORTED", sourcePath,
      `${modules.length} ArkTS modules were found; exactly one is supported.`);
    return undefined;
  }
  let tokens: readonly LexToken[];
  try { tokens = lexicalTokens(files[sourcePath]!); }
  catch (error) {
    gap(gaps, "FRT_ARKUI_PARSE_ERROR", sourcePath, error instanceof Error ? error.message : "ArkTS parse failed.");
    return undefined;
  }
  const count = following(tokens, ["@", "State", "count", ":", "number", "="], "number");
  const title = following(tokens, ["Text", "("], "string");
  const titleIndex = title ? tokenIndex(tokens, ["Text", "(", title.value, ")", ".", "accessibilityText", "("]) : -1;
  const mainLabel = titleIndex < 0 ? undefined : tokens[titleIndex + 7];
  const button = following(tokens, ["Button", "("], "string");
  const buttonIndex = button ? tokenIndex(tokens, ["Button", "(", button.value, ")", ".", "accessibilityText", "("]) : -1;
  const accessibleButtonLabel = buttonIndex < 0 ? undefined : tokens[buttonIndex + 7];
  const increment = following(tokens, ["this", ".", "count", "+="], "number");
  const color = following(tokens, [".", "fontColor", "("], "string");
  const live = tokenIndex(tokens, ["Text", "(", "this", ".", "count", ".", "toString", "(", ")", ")", ".", "accessibilityLevel", "(", "yes", ")"]);
  const initialCount = count ? Number(count.value) : undefined;
  const incrementBy = increment ? Number(increment.value) : undefined;
  if (!title || mainLabel?.kind !== "string" || !button || accessibleButtonLabel?.kind !== "string"
      || !Number.isInteger(initialCount) || !Number.isInteger(incrementBy) || !color || live < 0) {
    gap(gaps, "FRT_ARKUI_CONTRACT_NOT_DERIVABLE", sourcePath,
      "State, action, component text, accessibility declarations, or color could not be read from ArkTS.");
    return undefined;
  }
  const values = {
    title: title.value,
    mainLabel: mainLabel.value,
    buttonLabel: button.value,
    accessibleButtonLabel: accessibleButtonLabel.value,
    initialCount: initialCount!,
    incrementBy: incrementBy!,
    accentColor: color.value,
  };
  if (!/^#[0-9A-Fa-f]{6}$/.test(values.accentColor)
      || tokenIdentity(tokens) !== tokenIdentity(lexicalTokens(arkSource(values)))) {
    gap(gaps, "FRT_ARKUI_SEMANTIC_UNSUPPORTED", sourcePath,
      "The ArkTS component contains syntax or semantics outside the exact bounded counter component grammar.");
  }
  if (gaps.length !== before || version === undefined) return undefined;
  return buildIr("ArkUI", version, files, values);
}

function flutterSource(values: {
  readonly title: string; readonly mainLabel: string; readonly buttonLabel: string;
  readonly accessibleButtonLabel: string; readonly initialCount: number;
  readonly incrementBy: number; readonly accentColor: string;
}): string {
  const flutterString = (value: string): string => JSON.stringify(value.replaceAll("$", "\\$"));
  const color = `0xFF${values.accentColor.slice(1).toUpperCase()}`;
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
    `  int count = ${values.initialCount};`,
    `  void increment() => setState(() => count += ${values.incrementBy});`,
    "  @override Widget build(BuildContext context) => Scaffold(body: SafeArea(child: Semantics(",
    `    label: ${flutterString(values.mainLabel)}, container: true, child: Column(children: [`,
    `      Text(${flutterString(values.title)}),`,
    `      Semantics(button: true, label: ${flutterString(values.accessibleButtonLabel)}, child: ExcludeSemantics(child: ElevatedButton(`,
    `        style: ElevatedButton.styleFrom(foregroundColor: const Color(${color})),`,
    `        onPressed: increment, child: Text(${flutterString(values.buttonLabel)}),`,
    "      ))),",
    "      Semantics(liveRegion: true, child: Text('$count', key: const Key('count'))),",
    "    ]),",
    "  )));",
    "}",
    "",
  ].join("\n");
}

/** Derive the exact Flutter/Dart counter widget grammar. */
export function deriveFlutterPortableUiIr(
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  const before = gaps.length;
  let version: string | undefined;
  try {
    const fvm = JSON.parse(files[".fvmrc"] ?? "") as { flutter?: unknown };
    if (typeof fvm.flutter !== "string" || !exactVersion.test(fvm.flutter)) {
      gap(gaps, "FRT_FLUTTER_VERSION_PROFILE_INVALID", ".fvmrc",
        ".fvmrc must pin one exact Flutter SDK version.");
    } else version = fvm.flutter;
  } catch {
    gap(gaps, "FRT_FLUTTER_VERSION_PROFILE_INVALID", ".fvmrc",
      ".fvmrc is required and must be valid JSON.");
  }
  if (!/(?:^|\n)\s*flutter:\s*(?:\n\s+sdk:\s*flutter\s*(?:\n|$)|[^\n]+(?:\n|$))/.test(files["pubspec.yaml"] ?? "")) {
    gap(gaps, "FRT_FLUTTER_PUBSPEC_INVALID", "pubspec.yaml",
      "pubspec.yaml must declare the Flutter SDK dependency.");
  }
  const modules = Object.keys(files).filter(path => path.endsWith(".dart") && !path.startsWith("test/")).sort();
  const sourcePath = modules[0] ?? "<missing-dart-module>";
  if (modules.length !== 1) {
    gap(gaps, "FRT_FLUTTER_MODULE_CARDINALITY_UNSUPPORTED", sourcePath,
      `${modules.length} application Dart modules were found; exactly one is supported.`);
    return undefined;
  }
  let tokens: readonly LexToken[];
  try { tokens = lexicalTokens(files[sourcePath]!); }
  catch (error) {
    gap(gaps, "FRT_FLUTTER_PARSE_ERROR", sourcePath, error instanceof Error ? error.message : "Dart parse failed.");
    return undefined;
  }
  const count = following(tokens, ["int", "count", "="], "number");
  const increment = following(tokens, ["count", "+="], "number");
  const rootLabel = following(tokens, ["SafeArea", "(", "child", ":", "Semantics", "(", "label", ":"], "string");
  const title = following(tokens, ["Column", "(", "children", ":", "[", "Text", "("], "string");
  const accessibleButtonLabel = following(tokens, ["Semantics", "(", "button", ":", "true", ",", "label", ":"], "string");
  const buttonLabel = following(tokens, ["onPressed", ":", "increment", ",", "child", ":", "Text", "("], "string");
  const color = following(tokens, ["foregroundColor", ":", "const", "Color", "("], "number");
  const live = tokenIndex(tokens, ["Semantics", "(", "liveRegion", ":", "true", ",", "child", ":", "Text", "(", "$count"]);
  const initialCount = count ? Number(count.value) : undefined;
  const incrementBy = increment ? Number(increment.value) : undefined;
  const colorMatch = color?.value.match(/^0xFF([0-9A-Fa-f]{6})$/);
  if (!Number.isInteger(initialCount) || !Number.isInteger(incrementBy) || !rootLabel || !title
      || !accessibleButtonLabel || !buttonLabel || !colorMatch || live < 0) {
    gap(gaps, "FRT_FLUTTER_CONTRACT_NOT_DERIVABLE", sourcePath,
      "State, action, widgets, semantics, or design token could not be read from Dart source.");
    return undefined;
  }
  const values = {
    title: title.value,
    mainLabel: rootLabel.value,
    buttonLabel: buttonLabel.value,
    accessibleButtonLabel: accessibleButtonLabel.value,
    initialCount: initialCount!,
    incrementBy: incrementBy!,
    accentColor: `#${colorMatch[1]!.toUpperCase()}`,
  };
  if (tokenIdentity(tokens) !== tokenIdentity(lexicalTokens(flutterSource(values)))) {
    gap(gaps, "FRT_FLUTTER_SEMANTIC_UNSUPPORTED", sourcePath,
      "The Dart module contains syntax or semantics outside the exact bounded counter-widget grammar.");
  }
  if (gaps.length !== before || version === undefined) return undefined;
  return buildIr("Flutter", version, files, values);
}

/**
 * Parses a WeChat Mini Program custom component (the `.wxml` + `.js` pair)
 * into the certified-component-v1 canonical model, using the real
 * `@wxml/parser` for the template and the real TypeScript Compiler API for
 * the `Component({...})` definition.
 *
 * This is the inverse of `emitters/miniprogram.ts` and has to undo three
 * things that emitter deliberately does:
 *
 *  1. **Tag mapping.** There are no HTML tags in a mini program, so
 *     `<div>` was emitted as `<view>` and every text-level tag as
 *     `<text>`. The reverse map cannot be a plain inverse (several HTML
 *     tags collapse onto `<text>`), so the generated semantic class
 *     (`cc-h2`, `cc-strong`, ...) is what recovers the original tag.
 *  2. **Named handlers.** WXML cannot host a statement body, so handlers
 *     were lifted into `methods: {}`. They are matched back by name.
 *  3. **Closure snapshots.** The emitter inserts
 *     `const count$0 = this.data.count;` at handler entry to reproduce
 *     React's closure semantics across WeChat's synchronous `setData`.
 *     Those synthetic locals are resolved back to their source names here,
 *     otherwise the round trip would produce an undeclared `count$0`
 *     identifier.
 */
import * as ts from "typescript";
import {
  at, AttrBinding, AttrName, ATTR_NAMES, CallbackPropDef, ComponentDef, DataPropDef, EventName,
  Expr, fail, HtmlTag, Literal, Node as CNode, PrimitiveType, PropDef, requireDefined, require_,
  StateDef, Stmt, validateComponent,
} from "../models";
import { callbackNameForEvent, literalFromNode, parseExprNode, parseTemplateExpression } from "./expressions";

/** Reverse of the emitter's SEMANTIC_CLASS map. */
const CLASS_TO_TAG: Record<string, HtmlTag> = {
  "cc-h1": "h1", "cc-h2": "h2", "cc-h3": "h3", "cc-h4": "h4", "cc-h5": "h5", "cc-h6": "h6",
  "cc-strong": "strong", "cc-em": "em", "cc-p": "p", "cc-ul": "ul", "cc-li": "li",
};

/** Default HTML tag for each mini program component when no semantic class
 * is present. */
const COMPONENT_TO_TAG: Record<string, HtmlTag> = {
  view: "div", text: "span", button: "button", input: "input", label: "label", navigator: "a",
};

const BIND_TO_EVENT: Record<string, EventName> = {
  bindtap: "onClick", bindchange: "onChange", bindinput: "onInput", bindsubmit: "onSubmit",
};

const ATTR_RENAME: Record<string, AttrName> = { url: "href" };

/* eslint-disable @typescript-eslint/no-explicit-any */
type WxNode = any;

interface JsInfo {
  props: DataPropDef[];
  state: StateDef[];
  /** methodName -> parsed statements */
  methods: Map<string, Stmt[]>;
  callbackNames: Set<string>;
}

function primitiveFromConstructor(node: ts.Expression, what: string): PrimitiveType {
  require_(ts.isIdentifier(node), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `${what} must declare a String/Number/Boolean type`);
  const name = node.text;
  if (name === "String") return "string";
  if (name === "Number") return "number";
  if (name === "Boolean") return "boolean";
  // `{ type: Array, value: [] }` records no element shape, so a WeChat
  // component cannot be a list SOURCE. It remains a supported list target.
  require_(name !== "Array", "CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT", `${what} is declared \`type: Array\`, which does not record its element shape; the WeChat mini program cannot be used as a source for list props (it remains supported as a target)`);
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${name}`);
}

/**
 * Resolves the emitter's `x$0` closure-snapshot locals back to the source
 * name, so the canonical model does not gain a phantom identifier.
 */
function stripSnapshotSuffix(name: string): string {
  return name.endsWith("$0") ? name.slice(0, -2) : name;
}

function normalizeSnapshots(expr: Expr): Expr {
  switch (expr.kind) {
    case "ident": return { kind: "ident", name: stripSnapshotSuffix(expr.name) };
    case "member": return expr;
    case "path": return expr;
    case "literal": return expr;
    case "eventValue": return expr;
    case "unaryNot": return { kind: "unaryNot", operand: normalizeSnapshots(expr.operand) };
    case "stringMethod": return { kind: "stringMethod", method: expr.method, receiver: normalizeSnapshots(expr.receiver), args: expr.args.map(normalizeSnapshots) };
    case "numericFunction": return { kind: "numericFunction", function: expr.function, args: expr.args.map(normalizeSnapshots) };
    case "numericPredicate": return { kind: "numericPredicate", predicate: expr.predicate, operand: normalizeSnapshots(expr.operand) };
    case "cssModuleClass": return expr;
    case "regexTest": return { kind: "regexTest", pattern: expr.pattern, flags: expr.flags, operand: normalizeSnapshots(expr.operand) };
    case "arrayLength": return { kind: "arrayLength", operand: normalizeSnapshots(expr.operand) };
    case "binary": return { kind: "binary", operator: expr.operator, left: normalizeSnapshots(expr.left), right: normalizeSnapshots(expr.right) };
    case "ternary": return { kind: "ternary", condition: normalizeSnapshots(expr.condition), then: normalizeSnapshots(expr.then), else: normalizeSnapshots(expr.else) };
  }
}

function parseMethodBody(body: ts.Block, stateNames: ReadonlySet<string>, callbackNames: Set<string>, what: string): Stmt[] {
  const result: Stmt[] = [];
  for (const stmt of body.statements) {
    // `const count$0 = this.data.count;` -- a synthetic closure snapshot.
    if (ts.isVariableStatement(stmt)) {
      const decl = at(stmt.declarationList.declarations, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "missing declarator");
      require_(ts.isIdentifier(decl.name) && decl.name.text.endsWith("$0"), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: only generated \`x$0\` closure snapshots may be declared in a handler`);
      continue;
    }
    require_(ts.isExpressionStatement(stmt), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: handler may only contain expression statements`);
    const expr = stmt.expression;
    require_(ts.isCallExpression(expr) && ts.isPropertyAccessExpression(expr.expression), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: handler statement must be this.setData(...) or this.triggerEvent(...)`);
    const call = expr as ts.CallExpression;
    const callee = (call.expression as ts.PropertyAccessExpression).name.text;

    if (callee === "setData") {
      const arg = at(call.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "setData needs an object argument");
      require_(ts.isObjectLiteralExpression(arg), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: setData argument must be an object literal`);
      for (const field of (arg as ts.ObjectLiteralExpression).properties) {
        require_(ts.isPropertyAssignment(field) && ts.isIdentifier(field.name), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: setData entries must be plain property assignments`);
        const target = (field.name as ts.Identifier).text;
        require_(stateNames.has(target), "CERTIFIED_COMPONENT_UNKNOWN_STATE_TARGET", `${what}: ${JSON.stringify(target)} is not declared component data`);
        result.push({ kind: "setState", target, value: normalizeSnapshots(parseExprNode(field.initializer)) });
      }
      continue;
    }

    if (callee === "triggerEvent") {
      const nameArg = at(call.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "triggerEvent needs an event name");
      require_(ts.isStringLiteral(nameArg), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: triggerEvent name must be a string literal`);
      const eventName = (nameArg as ts.StringLiteral).text;
      const callbackName = callbackNameForEvent(eventName);
      callbackNames.add(callbackName);

      const args: Expr[] = [];
      if (call.arguments.length > 1) {
        const detail = at(call.arguments, 1, "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "missing detail");
        require_(ts.isObjectLiteralExpression(detail), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: triggerEvent detail must be an object literal`);
        const fields = (detail as ts.ObjectLiteralExpression).properties;
        require_(fields.length === 1, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `${what}: triggerEvent detail must carry exactly one value`);
        const only = at(fields, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "missing detail field");
        require_(ts.isPropertyAssignment(only) && ts.isIdentifier(only.name) && only.name.text === "value", "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: triggerEvent detail must be { value: ... }`);
        args.push(normalizeSnapshots(parseExprNode(only.initializer)));
      }
      result.push({ kind: "callProp", target: callbackName, args });
      continue;
    }

    fail("CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: this.${callee}(...) is outside certified-component-v1`);
  }
  return result;
}

function parseComponentJs(code: string): JsInfo {
  const file = ts.createSourceFile("component.js", code, ts.ScriptTarget.ES2022, true, ts.ScriptKind.JS);
  const call = file.statements
    .filter(ts.isExpressionStatement)
    .map((s) => s.expression)
    .find((e): e is ts.CallExpression => ts.isCallExpression(e) && ts.isIdentifier(e.expression) && e.expression.text === "Component");
  const componentCall = requireDefined(call, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "the .js file must contain a top-level Component({...}) call");
  const options = at(componentCall.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "Component() needs an options object");
  require_(ts.isObjectLiteralExpression(options), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "Component() argument must be an object literal");

  const props: DataPropDef[] = [];
  const state: StateDef[] = [];
  const methodNodes: { name: string; body: ts.Block }[] = [];

  for (const member of (options as ts.ObjectLiteralExpression).properties) {
    require_(ts.isPropertyAssignment(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "Component options must be plain property assignments");
    const key = (member.name as ts.Identifier).text;
    const value = member.initializer;

    if (key === "properties") {
      require_(ts.isObjectLiteralExpression(value), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "`properties` must be an object literal");
      for (const prop of (value as ts.ObjectLiteralExpression).properties) {
        require_(ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "each property must be a plain assignment");
        const name = (prop.name as ts.Identifier).text;
        require_(ts.isObjectLiteralExpression(prop.initializer), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `property ${JSON.stringify(name)} must use the { type, value } form`);
        let propType: PrimitiveType | undefined;
        let defaultValue: Literal | undefined;
        for (const field of (prop.initializer as ts.ObjectLiteralExpression).properties) {
          require_(ts.isPropertyAssignment(field) && ts.isIdentifier(field.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "property spec fields must be plain assignments");
          const fieldName = (field.name as ts.Identifier).text;
          if (fieldName === "type") propType = primitiveFromConstructor(field.initializer, `property ${name}`);
          else if (fieldName === "value") defaultValue = literalFromNode(field.initializer);
          else fail("CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `property spec field ${JSON.stringify(fieldName)} is outside certified-component-v1`);
        }
        const resolved = requireDefined(propType, "CERTIFIED_COMPONENT_MISSING_TYPE", `property ${JSON.stringify(name)} has no type`);
        props.push({ kind: "data", name, propType: resolved, required: false, defaultValue });
      }
      continue;
    }

    if (key === "data") {
      require_(ts.isObjectLiteralExpression(value), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "`data` must be an object literal");
      for (const field of (value as ts.ObjectLiteralExpression).properties) {
        require_(ts.isPropertyAssignment(field) && ts.isIdentifier(field.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "data fields must be plain assignments");
        const initial = literalFromNode(field.initializer);
        state.push({ name: (field.name as ts.Identifier).text, stateType: initial.type === "null" ? "string" : initial.type, ...(initial.type === "null" ? { nullable: true } : {}), initial });
      }
      continue;
    }

    if (key === "methods") {
      require_(ts.isObjectLiteralExpression(value), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "`methods` must be an object literal");
      for (const method of (value as ts.ObjectLiteralExpression).properties) {
        require_(ts.isMethodDeclaration(method) && ts.isIdentifier(method.name), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "methods must be plain method declarations");
        const body = requireDefined((method as ts.MethodDeclaration).body, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "method must have a body");
        methodNodes.push({ name: (method.name as ts.Identifier).text, body });
      }
      continue;
    }

    fail("CERTIFIED_COMPONENT_UNSUPPORTED_SFC", `Component option ${JSON.stringify(key)} is outside certified-component-v1 (no lifetimes, observers, behaviors, or relations)`);
  }

  const stateNames = new Set(state.map((s) => s.name));
  const callbackNames = new Set<string>();
  const methods = new Map<string, Stmt[]>();
  for (const { name, body } of methodNodes) {
    methods.set(name, parseMethodBody(body, stateNames, callbackNames, `method ${name}`));
  }
  return { props, state, methods, callbackNames };
}

/** `{{ expr }}` -> the inner expression source. */
function interpolationSource(raw: string): string {
  const trimmed = raw.trim();
  const match = /^\{\{([\s\S]*)\}\}$/.exec(trimmed);
  return match && match[1] !== undefined ? match[1].trim() : trimmed;
}

function attrEntries(node: WxNode): { key: string; value: string | undefined }[] {
  return (node.startTag?.attributes ?? []).map((a: WxNode) => ({ key: String(a.key), value: a.value === undefined || a.value === null ? undefined : String(a.value) }));
}

function meaningful(children: WxNode[]): WxNode[] {
  return (children ?? []).filter((c) => !(c.type === "WXText" && String(c.value ?? "").trim() === ""));
}

function parseNode(node: WxNode, info: JsInfo, siblings: WxNode[], index: number): CNode | null {
  if (node.type === "WXText") {
    const text = String(node.value ?? "").trim();
    if (text.length === 0) return null;
    return { kind: "text", value: { kind: "literal", literal: { type: "string", value: text } } };
  }
  if (node.type === "WXInterpolation") {
    return { kind: "text", value: parseTemplateExpression(String(node.value ?? "").trim(), "interpolation") };
  }
  require_(node.type === "WXElement", "CERTIFIED_COMPONENT_UNSUPPORTED_TEMPLATE_NODE", `WXML node type ${node.type} is outside certified-component-v1`);

  const componentName = String(node.name);
  const attributes = attrEntries(node);

  // Recover the original HTML tag: a generated semantic class wins,
  // otherwise fall back to the default mapping for this component.
  const classAttr = attributes.find((a) => a.key === "class");
  const classNames = (classAttr?.value ?? "").split(/\s+/).filter(Boolean);
  const semanticClass = classNames.find((c) => CLASS_TO_TAG[c] !== undefined);
  const tag = semanticClass !== undefined
    ? (CLASS_TO_TAG[semanticClass] as HtmlTag)
    : requireDefined(COMPONENT_TO_TAG[componentName], "CERTIFIED_COMPONENT_UNSUPPORTED_TAG", `mini program component <${componentName}> is outside certified-component-v1`);

  const attrs: AttrBinding[] = [];
  const events: { name: EventName; body: Stmt[] }[] = [];
  let condition: Expr | null = null;
  let isElse = false;

  for (const attr of attributes) {
    const key = attr.key;
    if (key === "wx:if") {
      condition = parseTemplateExpression(interpolationSource(attr.value ?? ""), `<${componentName}> wx:if`);
      continue;
    }
    if (key === "wx:else") { isElse = true; continue; }
    if (key === "wx:elif") fail("CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "wx:elif chains are outside certified-component-v1");
    if (key === "wx:for" || key === "wx:for-item" || key === "wx:key") {
      fail("CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT", `<${componentName}>: wx:for cannot be read back, because a WeChat \`type: Array\` property records no element shape; the mini program remains supported as a list TARGET`);
    }

    const boundEvent = BIND_TO_EVENT[key];
    if (boundEvent !== undefined) {
      const methodName = String(attr.value ?? "");
      const body = requireDefined(info.methods.get(methodName), "CERTIFIED_COMPONENT_UNKNOWN_HANDLER", `<${componentName}>: ${key} references method ${JSON.stringify(methodName)}, which is not declared in methods`);
      events.push({ name: boundEvent, body });
      continue;
    }

    if (key === "class") {
      // Strip the generated semantic class; keep whatever the source had.
      const remaining = classNames.filter((c) => CLASS_TO_TAG[c] === undefined);
      if (remaining.length > 0) attrs.push({ kind: "static", name: "class", value: remaining.join(" ") });
      continue;
    }

    const canonical = ATTR_RENAME[key] ?? key;
    require_((ATTR_NAMES as readonly string[]).includes(canonical), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${componentName}>: attribute ${JSON.stringify(key)} is outside certified-component-v1`);
    const raw = attr.value ?? "";
    if (/^\s*\{\{[\s\S]*\}\}\s*$/.test(raw)) {
      attrs.push({ kind: "dynamic", name: canonical as AttrName, value: parseTemplateExpression(interpolationSource(raw), `<${componentName}> ${key}`) });
    } else {
      attrs.push({ kind: "static", name: canonical as AttrName, value: raw });
    }
  }

  if (isElse) return null; // consumed by the preceding wx:if

  const children = meaningful(node.children ?? [])
    .map((c: WxNode, i: number, arr: WxNode[]) => parseNode(c, info, arr, i))
    .filter((c: CNode | null): c is CNode => c !== null);

  const element: CNode = { kind: "element", tag, attrs, events, children };

  if (condition !== null) {
    const next = siblings[index + 1];
    let elseNode: CNode | null = null;
    if (next && next.type === "WXElement" && attrEntries(next).some((a) => a.key === "wx:else")) {
      const stripped: WxNode = {
        ...next,
        startTag: { ...next.startTag, attributes: (next.startTag?.attributes ?? []).filter((a: WxNode) => String(a.key) !== "wx:else") },
      };
      elseNode = parseNode(stripped, info, [stripped], 0);
    }
    return { kind: "conditional", condition, then: element, else: elseNode };
  }
  return element;
}

/** Re-exported from the emitter so the two halves cannot drift apart. */
export type { MiniProgramBundle } from "../emitters/miniprogram";

export interface MiniProgramSource {
  wxml: string;
  js: string;
}

export function parseMiniProgramComponent(source: string | MiniProgramSource, fileName = "index"): ComponentDef {
  require_(typeof source !== "string", "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "a mini program component is a multi-file bundle; pass { wxml, js }");
  const bundle = source as MiniProgramSource;

  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const wxml = require("@wxml/parser");
  let ast: WxNode;
  try {
    ast = wxml.parse(bundle.wxml);
  } catch (error) {
    fail("CERTIFIED_COMPONENT_PARSE_FAILED", `@wxml/parser rejected the template: ${(error as Error).message}`);
  }

  const info = parseComponentJs(bundle.js);

  const roots = meaningful(ast.body ?? []).filter((n: WxNode) => n.type === "WXElement");
  require_(roots.length === 1, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", `certified-component-v1 requires exactly one root element, found ${roots.length}`);
  const root = requireDefined(parseNode(at<WxNode>(roots, 0, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", "missing root"), info, roots, 0), "CERTIFIED_COMPONENT_PARSE_FAILED", "root element produced no node");

  const callbacks: CallbackPropDef[] = [...info.callbackNames].map((name) => ({ kind: "callback", name, paramType: undefined }));
  const props: PropDef[] = [...info.props, ...callbacks];

  const base = fileName.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9]/g, "");
  const component: ComponentDef = {
    name: base.charAt(0).toUpperCase() + base.slice(1) || "Component",
    props,
    state: info.state,
    root,
  };
  validateComponent(component);
  return component;
}

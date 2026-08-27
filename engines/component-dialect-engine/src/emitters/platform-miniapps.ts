/**
 * Native mini-app emitters for the certified-component-v1 canonical model.
 *
 * This module deliberately walks ComponentDef for every target.  It never
 * emits one platform and rewrites the generated text into another dialect:
 * template directives, events, property models and callback delivery are
 * selected while rendering each canonical node.
 *
 * Platform IDE/CLI execution is outside this package.  The worker reports
 * those evidence legs as NOT_RUN and never promotes these locally generated
 * bundles to certified output.
 */
import {
  AttrName,
  ComponentDef,
  EventName,
  Expr,
  HtmlTag,
  ListPropDef,
  Literal,
  Node as CNode,
  PropDef,
  Stmt,
  fail,
  validateComponent,
} from "../models";
import { listPropIndex, referencedComponents } from "./react";

export const MINI_APP_PLATFORMS = ["wechat", "alipay", "douyin", "xiaohongshu"] as const;
export type MiniAppPlatform = (typeof MINI_APP_PLATFORMS)[number];

export interface PlatformMiniAppEmission {
  platform: MiniAppPlatform;
  templateExtension: "wxml" | "axml" | "ttml" | "xhsml";
  styleExtension: "wxss" | "acss" | "ttss" | "css";
  /** Exactly template + JavaScript + JSON configuration + style. */
  files: Readonly<Record<string, string>>;
}

type CallbackStrategy = "trigger-event" | "props-callback";
type PropertyContainer = "properties" | "props";

interface PlatformProfile {
  platform: MiniAppPlatform;
  templateExtension: PlatformMiniAppEmission["templateExtension"];
  styleExtension: PlatformMiniAppEmission["styleExtension"];
  directivePrefix: "wx" | "a" | "tt" | "xhs";
  eventNames: Readonly<Record<EventName, string>>;
  propertyContainer: PropertyContainer;
  callbackStrategy: CallbackStrategy;
}

const BIND_EVENTS: Readonly<Record<EventName, string>> = {
  onClick: "bindtap",
  onChange: "bindchange",
  onInput: "bindinput",
  onSubmit: "bindsubmit",
};

const PROFILES: Readonly<Record<MiniAppPlatform, PlatformProfile>> = {
  wechat: {
    platform: "wechat",
    templateExtension: "wxml",
    styleExtension: "wxss",
    directivePrefix: "wx",
    eventNames: BIND_EVENTS,
    propertyContainer: "properties",
    callbackStrategy: "trigger-event",
  },
  alipay: {
    platform: "alipay",
    templateExtension: "axml",
    styleExtension: "acss",
    directivePrefix: "a",
    eventNames: {
      onClick: "onTap",
      onChange: "onChange",
      onInput: "onInput",
      onSubmit: "onSubmit",
    },
    propertyContainer: "props",
    callbackStrategy: "props-callback",
  },
  douyin: {
    platform: "douyin",
    templateExtension: "ttml",
    styleExtension: "ttss",
    directivePrefix: "tt",
    eventNames: BIND_EVENTS,
    propertyContainer: "properties",
    callbackStrategy: "trigger-event",
  },
  xiaohongshu: {
    platform: "xiaohongshu",
    templateExtension: "xhsml",
    styleExtension: "css",
    directivePrefix: "xhs",
    eventNames: BIND_EVENTS,
    propertyContainer: "properties",
    callbackStrategy: "trigger-event",
  },
};

const TAG_MAP: Readonly<Record<HtmlTag, string>> = {
  div: "view",
  span: "text",
  p: "view",
  button: "button",
  input: "input",
  label: "label",
  a: "navigator",
  h1: "view",
  h2: "view",
  h3: "view",
  h4: "view",
  h5: "view",
  h6: "view",
  ul: "view",
  ol: "view",
  li: "view",
  strong: "text",
  em: "text",
  i: "text",
  section: "view",
  article: "view",
  header: "view",
  footer: "view",
  nav: "view",
  main: "view",
  aside: "view",
  dl: "view",
  dt: "text",
  dd: "text",
  small: "text",
  code: "text",
};

const SEMANTIC_CLASS: Readonly<Partial<Record<HtmlTag, string>>> = {
  h1: "cc-h1",
  h2: "cc-h2",
  h3: "cc-h3",
  h4: "cc-h4",
  h5: "cc-h5",
  h6: "cc-h6",
  strong: "cc-strong",
  em: "cc-em",
  ul: "cc-ul",
  ol: "cc-ol",
  li: "cc-li",
  p: "cc-p",
  small: "cc-small",
  code: "cc-code",
};

const ATTR_MAP: Readonly<Partial<Record<AttrName, string>>> = {
  href: "url",
  maxLength: "maxlength",
};

const SEMANTIC_STYLE = `.cc-h1 { font-size: 48rpx; font-weight: bold; display: block; }
.cc-h2 { font-size: 40rpx; font-weight: bold; display: block; }
.cc-h3 { font-size: 36rpx; font-weight: bold; display: block; }
.cc-h4 { font-size: 32rpx; font-weight: bold; display: block; }
.cc-h5 { font-size: 30rpx; font-weight: bold; display: block; }
.cc-h6 { font-size: 28rpx; font-weight: bold; display: block; }
.cc-strong { font-weight: bold; }
.cc-em { font-style: italic; }
.cc-p { display: block; margin: 8rpx 0; }
.cc-ul { display: block; }
.cc-ol { display: block; }
.cc-li { display: block; }
.cc-small { font-size: 24rpx; }
.cc-code { font-family: monospace; }
`;

function kebab(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

function escapeText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttribute(value: string): string {
  return escapeText(value).replace(/"/g, "&quot;");
}

function assertStaticTemplateLiteralSafe(value: string, location: string): void {
  if (value.includes("{{") || value.includes("}}")) {
    fail(
      "MINIAPP_UNSAFE_STATIC_TEMPLATE_DELIMITER",
      `${location} contains a MiniApp template delimiter; target-specific literal escaping is not proven`,
    );
  }
}

function assertUniqueTargetNames(names: readonly string[], location: string): void {
  const exactByTargetName = new Map<string, string>();
  for (const name of [...names].sort()) {
    const targetName = kebab(name);
    const previous = exactByTargetName.get(targetName);
    if (previous !== undefined && previous !== name) {
      fail(
        "MINIAPP_TARGET_NAME_COLLISION",
        `${location} names ${JSON.stringify(previous)} and ${JSON.stringify(name)} both normalize to ${JSON.stringify(targetName)}`,
      );
    }
    exactByTargetName.set(targetName, name);
  }
}

function assertTargetNameClosure(component: ComponentDef): void {
  assertUniqueTargetNames(
    component.props.map((prop) => prop.name),
    `component ${component.name} property`,
  );
  assertUniqueTargetNames(
    [component.name, ...referencedComponents(component)],
    `component ${component.name} render graph`,
  );

  const visit = (node: CNode): void => {
    switch (node.kind) {
      case "fragment":
        node.children.forEach(visit);
        return;
      case "component":
        assertUniqueTargetNames(
          node.props.map((prop) => prop.name),
          `invocation of ${node.name} property`,
        );
        return;
      case "element":
        node.children.forEach(visit);
        return;
      case "conditional":
        visit(node.then);
        if (node.else !== null) visit(node.else);
        return;
      case "list":
        visit(node.body);
        return;
      case "text":
        return;
    }
  };
  visit(component.root);
}

function literalSource(literal: Literal): string {
  if (literal.type === "string") return JSON.stringify(literal.value);
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

interface RenderScope {
  readonly itemName: string;
}

interface JsExpressionContext {
  readonly profile: PlatformProfile;
  readonly stateNames: ReadonlySet<string>;
  readonly snapshots: ReadonlySet<string>;
  readonly localReads: ReadonlyMap<string, string>;
}

function localKey(expr: Expr, scope: RenderScope | null): string | null {
  if (scope === null) return null;
  if (expr.kind === "ident" && expr.name === scope.itemName) return `ident:${expr.name}`;
  if (expr.kind === "member" && expr.object === scope.itemName) return `member:${expr.object}.${expr.field}`;
  return null;
}

function templateExprSource(expr: Expr): string {
  const wrap = (child: Expr): string => {
    const source = templateExprSource(child);
    return child.kind === "binary" || child.kind === "ternary" ? `(${source})` : source;
  };
  switch (expr.kind) {
    case "ident":
      return expr.name;
    case "member":
      return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal":
      return literalSource(expr.literal);
    case "eventValue": return "event.detail.value";
    case "unaryNot":
      return `!${wrap(expr.operand)}`;
    case "binary": {
      const operator = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${operator} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map(templateExprSource).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map(templateExprSource).join(", ")})`;
    case "numericPredicate": return `Number.${expr.predicate}(${templateExprSource(expr.operand)})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${templateExprSource(expr.operand)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary":
      return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function jsExprSource(expr: Expr, context: JsExpressionContext): string {
  const local = context.localReads.get(
    expr.kind === "ident" ? `ident:${expr.name}` : expr.kind === "member" ? `member:${expr.object}.${expr.field}` : "",
  );
  if (local !== undefined) return local;

  const wrap = (child: Expr): string => {
    const source = jsExprSource(child, context);
    return child.kind === "binary" || child.kind === "ternary" ? `(${source})` : source;
  };
  switch (expr.kind) {
    case "ident":
      if (context.snapshots.has(expr.name)) return `${expr.name}$0`;
      if (context.profile.propertyContainer === "props" && !context.stateNames.has(expr.name)) {
        return `this.props.${expr.name}`;
      }
      return `this.data.${expr.name}`;
    case "member":
      fail("MINIAPP_UNBOUND_LOOP_VALUE", `loop-local value ${expr.object}.${expr.field} was not bound into the event dataset`);
    case "path":
      fail("MINIAPP_UNBOUND_LOOP_VALUE", `loop-local value ${expr.object}.${expr.fields.join(".")} was not bound into the event dataset`);
    case "literal":
      return literalSource(expr.literal);
    case "eventValue": return "event.detail.value";
    case "unaryNot":
      return `!${wrap(expr.operand)}`;
    case "binary": {
      const operator = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${operator} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map((arg) => jsExprSource(arg, context)).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map((arg) => jsExprSource(arg, context)).join(", ")})`;
    case "numericPredicate": return `Number.${expr.predicate}(${jsExprSource(expr.operand, context)})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${jsExprSource(expr.operand, context)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary":
      return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function walkExpr(expr: Expr, visit: (candidate: Expr) => void): void {
  visit(expr);
  switch (expr.kind) {
    case "binary":
      walkExpr(expr.left, visit);
      walkExpr(expr.right, visit);
      return;
    case "unaryNot":
      walkExpr(expr.operand, visit);
      return;
    case "ternary":
      walkExpr(expr.condition, visit);
      walkExpr(expr.then, visit);
      walkExpr(expr.else, visit);
      return;
    case "stringMethod":
      walkExpr(expr.receiver, visit);
      expr.args.forEach((arg) => walkExpr(arg, visit));
      return;
    case "regexTest":
      walkExpr(expr.operand, visit);
      return;
    case "numericFunction":
      expr.args.forEach((arg) => walkExpr(arg, visit));
      return;
    case "numericPredicate":
      walkExpr(expr.operand, visit);
      return;
    case "arrayLength":
      walkExpr(expr.operand, visit);
      return;
    default:
      return;
  }
}

function statementExpressions(statement: Stmt): readonly Expr[] {
  return statement.kind === "setState" ? [statement.value] : statement.args;
}

interface EventLocalBindings {
  readonly attributes: readonly string[];
  readonly declarations: readonly string[];
  readonly reads: ReadonlyMap<string, string>;
}

/**
 * Template loop variables do not exist in component-method scope.  When an
 * event body reads the current item, bind the exact primitive/field through
 * data-ccN and recover it from currentTarget.dataset.  Silently emitting
 * `item.id` in JavaScript would compile but be undefined at runtime.
 */
function eventLocalBindings(body: readonly Stmt[], scope: RenderScope | null): EventLocalBindings {
  const ordered = new Map<string, Expr>();
  for (const statement of body) {
    for (const expression of statementExpressions(statement)) {
      walkExpr(expression, (candidate) => {
        const key = localKey(candidate, scope);
        if (key !== null && !ordered.has(key)) ordered.set(key, candidate);
      });
    }
  }

  const attributes: string[] = [];
  const declarations: string[] = [];
  const reads = new Map<string, string>();
  let index = 0;
  for (const [key, expression] of ordered) {
    const dataName = `cc${index}`;
    const localName = `ccLocal${index}`;
    attributes.push(`data-${dataName}="{{ ${escapeAttribute(templateExprSource(expression))} }}"`);
    declarations.push(`const ${localName} = event.currentTarget.dataset.${dataName};`);
    reads.set(key, localName);
    index += 1;
  }
  return { attributes, declarations, reads };
}

function collectIdentReads(expr: Expr, into: Set<string>): void {
  walkExpr(expr, (candidate) => {
    if (candidate.kind === "ident") into.add(candidate.name);
  });
}

function statementSource(statement: Stmt, context: JsExpressionContext): string {
  if (statement.kind === "setState") {
    return `this.setData({ ${statement.target}: ${jsExprSource(statement.value, context)} });`;
  }

  const argument = statement.args.length === 1 ? jsExprSource(statement.args[0] as Expr, context) : null;
  if (context.profile.callbackStrategy === "props-callback") {
    const callback = `this.props.${statement.target}`;
    return `if (typeof ${callback} === "function") { ${callback}(${argument ?? ""}); }`;
  }

  const rawName = statement.target.slice(2);
  const eventName = rawName.charAt(0).toLowerCase() + rawName.slice(1);
  const detail = argument === null ? "" : `, { value: ${argument} }`;
  return `this.triggerEvent(${JSON.stringify(eventName)}${detail});`;
}

interface EmittedHandler {
  readonly methodName: string;
  readonly body: readonly string[];
}

function handlerBody(
  body: readonly Stmt[],
  profile: PlatformProfile,
  stateNames: ReadonlySet<string>,
  locals: EventLocalBindings,
): string[] {
  const reads = new Set<string>();
  const writes = new Set<string>();
  for (const statement of body) {
    if (statement.kind === "setState") writes.add(statement.target);
    for (const expression of statementExpressions(statement)) collectIdentReads(expression, reads);
  }
  const snapshots = new Set([...reads].filter((name) => writes.has(name) && stateNames.has(name)));
  const context: JsExpressionContext = { profile, stateNames, snapshots, localReads: locals.reads };
  return [
    ...locals.declarations,
    ...[...snapshots].map((name) => `const ${name}$0 = this.data.${name};`),
    ...body.map((statement) => statementSource(statement, context)),
  ];
}

function handlerName(tag: HtmlTag, index: number, event: EventName): string {
  return `handle${event.slice(2)}${tag.charAt(0).toUpperCase()}${tag.slice(1)}${index}`;
}

interface RenderContext {
  readonly profile: PlatformProfile;
  readonly handlers: EmittedHandler[];
  readonly counter: { value: number };
  readonly lists: ReadonlyMap<string, ListPropDef>;
  readonly stateNames: ReadonlySet<string>;
}

function classAttribute(node: Extract<CNode, { kind: "element" }>): { value: string | null; remaining: typeof node.attrs } {
  const semantic = SEMANTIC_CLASS[node.tag];
  const staticClasses: string[] = semantic === undefined ? [] : [semantic];
  let dynamic: Expr | null = null;
  const remaining: typeof node.attrs = [];

  for (const attr of node.attrs) {
    if (attr.name !== "class") {
      remaining.push(attr);
      continue;
    }
    if (attr.kind === "static") {
      assertStaticTemplateLiteralSafe(attr.value, `static class on ${node.tag}`);
      staticClasses.unshift(attr.value);
    } else {
      if (dynamic !== null) fail("MINIAPP_DUPLICATE_DYNAMIC_CLASS", "an element cannot contain multiple dynamic class bindings");
      dynamic = attr.value;
    }
  }

  if (staticClasses.length === 0 && dynamic === null) return { value: null, remaining };
  const staticPart = staticClasses.join(" ");
  // Escape the complete class attribute exactly once in elementSource.
  // Escaping the expression here as well would turn &quot; into &amp;quot;.
  const dynamicPart = dynamic === null ? "" : `{{ ${templateExprSource(dynamic)} }}`;
  return { value: [staticPart, dynamicPart].filter((part) => part.length > 0).join(" "), remaining };
}

function nodeSource(node: CNode, indent: string, context: RenderContext, scope: RenderScope | null): string {
  if (node.kind === "fragment") {
    const childSrc = node.children.map((child) => nodeSource(child, indent + "  ", context, scope)).join("\n");
    return `${indent}<block>\n${childSrc}\n${indent}</block>`;
  }
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") {
      assertStaticTemplateLiteralSafe(node.value.literal.value, "static text");
      return `${indent}${escapeText(node.value.literal.value)}`;
    }
    return `${indent}{{ ${escapeText(templateExprSource(node.value))} }}`;
  }

  if (node.kind === "conditional") {
    const prefix = context.profile.directivePrefix;
    const condition = escapeAttribute(templateExprSource(node.condition));
    const thenSource = branchSource(node.then, `${prefix}:if="{{ ${condition} }}"`, indent, context, scope);
    if (node.else === null) return thenSource;
    return `${thenSource}\n${branchSource(node.else, `${prefix}:else`, indent, context, scope)}`;
  }

  if (node.kind === "component") {
    const tag = kebab(node.name);
    const props = node.props.map(
      (prop) => `${kebab(prop.name)}="{{ ${escapeAttribute(templateExprSource(prop.value))} }}"`,
    );
    return `${indent}<${tag}${props.length > 0 ? " " + props.join(" ") : ""} />`;
  }

  if (node.kind === "list") {
    const prefix = context.profile.directivePrefix;
    const list = context.lists.get(node.source);
    if (list === undefined) fail("MINIAPP_UNKNOWN_LIST", `list ${JSON.stringify(node.source)} is not declared`);
    const key = node.keyField ?? list.keyField ?? "*this";
    const source = node.sourceExpression === undefined ? node.source : templateExprSource(node.sourceExpression);
    const directive = `${prefix}:for="{{ ${source} }}" ${prefix}:for-item="${node.itemName}" ${prefix}:key="${key}"`;
    return branchSource(node.body, directive, indent, context, { itemName: node.itemName });
  }

  return elementSource(node, [], indent, context, scope);
}

function branchSource(
  node: CNode,
  directive: string,
  indent: string,
  context: RenderContext,
  scope: RenderScope | null,
): string {
  if (node.kind === "element") return elementSource(node, [directive], indent, context, scope);
  const inner = nodeSource(node, indent + "  ", context, scope);
  return `${indent}<block ${directive}>\n${inner}\n${indent}</block>`;
}

function elementSource(
  node: Extract<CNode, { kind: "element" }>,
  directives: readonly string[],
  indent: string,
  context: RenderContext,
  scope: RenderScope | null,
): string {
  const tag = TAG_MAP[node.tag];
  const classInfo = classAttribute(node);
  const attributes: string[] = [];
  if (classInfo.value !== null) attributes.push(`class="${escapeAttribute(classInfo.value)}"`);

  for (const attr of classInfo.remaining) {
    const name = ATTR_MAP[attr.name] ?? attr.name;
    if (attr.kind === "static") {
      assertStaticTemplateLiteralSafe(attr.value, `static ${attr.name} attribute on ${node.tag}`);
      attributes.push(`${name}="${escapeAttribute(attr.value)}"`);
    } else {
      attributes.push(`${name}="{{ ${escapeAttribute(templateExprSource(attr.value))} }}"`);
    }
  }

  const eventAttributes: string[] = [];
  for (const event of node.events) {
    const methodName = handlerName(node.tag, context.counter.value, event.name);
    context.counter.value += 1;
    const locals = eventLocalBindings(event.body, scope);
    attributes.push(...locals.attributes);
    context.handlers.push({
      methodName,
      body: handlerBody(event.body, context.profile, context.stateNames, locals),
    });
    eventAttributes.push(`${context.profile.eventNames[event.name]}="${methodName}"`);
  }

  const allAttributes = [...directives, ...attributes, ...eventAttributes];
  const suffix = allAttributes.length === 0 ? "" : " " + allAttributes.join(" ");
  if (node.children.length === 0) return `${indent}<${tag}${suffix} />`;
  const children = node.children.map((child) => nodeSource(child, indent + "  ", context, scope)).join("\n");
  return `${indent}<${tag}${suffix}>\n${children}\n${indent}</${tag}>`;
}

function propertyType(type: "string" | "number" | "boolean"): string {
  return type === "string" ? "String" : type === "number" ? "Number" : "Boolean";
}

function defaultDataValue(prop: Extract<PropDef, { kind: "data" }>): string {
  if (prop.defaultValue !== undefined) return literalSource(prop.defaultValue);
  return prop.propType === "string" ? `""` : prop.propType === "number" ? "0" : "false";
}

function propertiesBlock(props: readonly PropDef[], profile: PlatformProfile): string {
  if (profile.propertyContainer === "props") {
    const entries = props.map((prop) => {
      if (prop.kind === "callback") return `    ${prop.name}: null,`;
      if (prop.kind === "list") return `    ${prop.name}: [],`;
      return `    ${prop.name}: ${defaultDataValue(prop)},`;
    });
    return entries.length === 0 ? "  props: {}," : `  props: {\n${entries.join("\n")}\n  },`;
  }

  const entries = props.flatMap((prop) => {
    if (prop.kind === "callback") return [];
    if (prop.kind === "list") return [`    ${prop.name}: { type: Array, value: [] },`];
    return [`    ${prop.name}: { type: ${propertyType(prop.propType)}, value: ${defaultDataValue(prop)} },`];
  });
  return entries.length === 0 ? "  properties: {}," : `  properties: {\n${entries.join("\n")}\n  },`;
}

function dataBlock(component: ComponentDef): string {
  if (component.state.length === 0) return "  data: {},";
  const entries = component.state.map((state) => `    ${state.name}: ${literalSource(state.initial)},`);
  return `  data: {\n${entries.join("\n")}\n  },`;
}

function methodsBlock(handlers: readonly EmittedHandler[]): string {
  if (handlers.length === 0) return "  methods: {},";
  const entries = handlers.map(
    (handler) => `    ${handler.methodName}(event) {\n${handler.body.map((line) => "      " + line).join("\n")}\n    },`,
  );
  return `  methods: {\n${entries.join("\n")}\n  },`;
}

/** Emit a platform-native four-file component bundle from canonical IR. */
export function emitPlatformMiniApp(component: ComponentDef, platform: MiniAppPlatform): PlatformMiniAppEmission {
  validateComponent(component);
  assertTargetNameClosure(component);
  const profile = (PROFILES as Readonly<Partial<Record<string, PlatformProfile>>>)[platform];
  if (profile === undefined) {
    fail("MINIAPP_UNSUPPORTED_PLATFORM", `platform ${JSON.stringify(platform)} has no native mini-app emitter profile`);
  }
  const handlers: EmittedHandler[] = [];
  const context: RenderContext = {
    profile,
    handlers,
    counter: { value: 0 },
    lists: listPropIndex(component),
    stateNames: new Set(component.state.map((state) => state.name)),
  };
  const template = nodeSource(component.root, "", context, null) + "\n";
  const js = [
    `// Generated by ELMOS component-dialect-engine for ${platform} (certified-component-v1 IR).`,
    "Component({",
    propertiesBlock(component.props, profile),
    dataBlock(component),
    methodsBlock(handlers),
    "});",
    "",
  ].join("\n");
  const usingComponents = Object.fromEntries(
    referencedComponents(component).map((name) => [kebab(name), `/components/${name}/index`]),
  );
  const json = JSON.stringify({ component: true, usingComponents }, null, 2) + "\n";

  const files: Record<string, string> = {
    [profile.templateExtension]: template,
    js,
    json,
    [profile.styleExtension]: SEMANTIC_STYLE,
  };
  return {
    platform,
    templateExtension: profile.templateExtension,
    styleExtension: profile.styleExtension,
    files,
  };
}

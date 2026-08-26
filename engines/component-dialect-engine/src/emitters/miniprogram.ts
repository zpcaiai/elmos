/**
 * Emits certified-component-v1 canonical model as a WeChat Mini Program
 * custom component bundle: the real four-file layout the platform requires
 * (`.wxml` / `.js` / `.json` / `.wxss`).
 *
 * The mini program is structurally the most different target in
 * certified-component-v1 and gets its own hand-written emitter for
 * concrete, verified reasons -- none of these are stylistic:
 *
 *  - There are no HTML tags. Every element must map to a mini program
 *    built-in component (`view`, `text`, `button`, `input`, ...); a `<div>`
 *    passed through verbatim renders as nothing.
 *  - There is no `class` attribute binding syntax shared with the web:
 *    static is `class="x"`, dynamic is `class="{{ expr }}"`.
 *  - State is NOT assignable. `this.data.count = 1` silently fails to
 *    re-render; the only correct write is `this.setData({ count: ... })`.
 *    This is the mini program's exact analogue of the Vue
 *    `count.value = ...`-in-template defect this engine already catches.
 *  - Events are `bindtap` / `bindinput` / etc. and handlers must be named
 *    methods in `methods: {}`, not inline expressions -- WXML cannot host
 *    a statement body at all.
 *  - Callback props do not exist. The parent is notified with
 *    `this.triggerEvent("name", detail)`.
 */
import {
  AttrBinding, AttrName, ComponentDef, EventName, Expr, HtmlTag, ListPropDef, Literal, Node as CNode, PropDef, Stmt,
} from "../models";
import { listPropIndex, referencedComponents } from "./react";

/** HTML tag -> mini program built-in component. Verified against the
 * official component list; anything not mappable must fail closed rather
 * than be emitted as an unknown tag that renders blank. */
/** Mini program custom components are registered and addressed by a
 * kebab-case tag name. */
function kebab(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

const TAG_MAP: Record<HtmlTag, string> = {
  div: "view", span: "text", p: "view", button: "button", input: "input",
  label: "label", a: "navigator", h1: "view", h2: "view", h3: "view",
  h4: "view", h5: "view", h6: "view", ul: "view", ol: "view", li: "view",
  strong: "text", em: "text", i: "text",
  // The mini program component set has no landmark elements; every
  // semantic container is a `view`, which is what `div` already maps to.
  section: "view", article: "view", header: "view", footer: "view",
  nav: "view", main: "view", aside: "view", dl: "view", dt: "text", dd: "text",
  small: "text", code: "text",
};

/** Headings and emphasis have no styling semantics in the mini program's
 * component set, so their visual role is preserved with a generated class
 * instead of being silently dropped. The matching WXSS is emitted below. */
const SEMANTIC_CLASS: Partial<Record<HtmlTag, string>> = {
  h1: "cc-h1", h2: "cc-h2", h3: "cc-h3", h4: "cc-h4", h5: "cc-h5", h6: "cc-h6",
  strong: "cc-strong", em: "cc-em", ul: "cc-ul", ol: "cc-ol", li: "cc-li", p: "cc-p",
  small: "cc-small", code: "cc-code", dt: "cc-dt", dd: "cc-dd",
};

const EVENT_MAP: Record<EventName, string> = {
  onClick: "bindtap", onChange: "bindchange", onInput: "bindinput", onSubmit: "bindsubmit",
};

const ATTR_MAP: Partial<Record<AttrName, string>> = {
  href: "url", // <a href> -> <navigator url>
  maxLength: "maxlength",
};

function literalSource(literal: Literal): string {
  if (literal.type === "string") return JSON.stringify(literal.value);
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

/** Inside WXML `{{ }}` and inside the component's JS, identifiers resolve
 * differently: WXML reads `data` fields bare, JS must read
 * `this.data.<name>`. */
function exprSource(expr: Expr, inJs: boolean, snapshot: ReadonlySet<string> = new Set()): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e, inJs, snapshot);
    return e.kind === "binary" || e.kind === "ternary" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident":
      if (!inJs) return expr.name;
      return snapshot.has(expr.name) ? `${expr.name}$0` : `this.data.${expr.name}`;
    // A wx:for-item binding is a template-local; `this.data.` would not
    // resolve it, and WXML has no JS scope to fall back on.
    case "member": return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal": return literalSource(expr.literal);
    case "eventValue": return inJs ? "event.detail.value" : "event.detail.value";
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map((arg) => exprSource(arg, inJs, snapshot)).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map((arg) => exprSource(arg, inJs, snapshot)).join(", ")})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${exprSource(expr.operand, inJs, snapshot)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function handlerMethodName(tag: string, index: number, event: EventName): string {
  return `handle${event.slice(2)}${tag.charAt(0).toUpperCase()}${tag.slice(1)}${index}`;
}

interface EmittedHandler {
  methodName: string;
  body: string[];
}

/**
 * Collects every identifier an expression reads, so the handler can
 * snapshot them before any setData call -- see `handlerBody`.
 */
function collectReads(expr: Expr, into: Set<string>): void {
  switch (expr.kind) {
    case "ident": into.add(expr.name); return;
    // A loop variable is scoped to the template, never to component data,
    // so it must NOT be snapshotted as if it were state.
    case "member": return;
    case "literal": return;
    case "unaryNot": collectReads(expr.operand, into); return;
    case "stringMethod": collectReads(expr.receiver, into); expr.args.forEach((arg) => collectReads(arg, into)); return;
    case "regexTest": collectReads(expr.operand, into); return;
    case "numericFunction": expr.args.forEach((arg) => collectReads(arg, into)); return;
    case "binary": collectReads(expr.left, into); collectReads(expr.right, into); return;
    case "ternary": collectReads(expr.condition, into); collectReads(expr.then, into); collectReads(expr.else, into); return;
  }
}

function stmtSource(stmt: Stmt, snapshot: ReadonlySet<string>): string {
  const read = (e: Expr): string => exprSource(e, true, snapshot);
  if (stmt.kind === "setState") {
    // Mini program state is only writable through setData; a direct
    // `this.data.x = ...` assignment compiles and silently does not
    // re-render, which is exactly the defect class this engine refuses to
    // emit.
    return `this.setData({ ${stmt.target}: ${read(stmt.value)} });`;
  }
  const detail = stmt.args.length > 0 ? `, { value: ${read(stmt.args[0] as Expr)} }` : "";
  const eventName = stmt.target.slice(2);
  return `this.triggerEvent(${JSON.stringify(eventName.charAt(0).toLowerCase() + eventName.slice(1))}${detail});`;
}

/**
 * Emits a handler body with React's closure semantics preserved.
 *
 * This is a real semantic divergence, not a formatting choice. In React,
 * `() => { setCount(count + step); onDone(count); }` passes the *old*
 * `count` to `onDone`, because `count` is a value captured by the closure
 * and `setCount` does not mutate it. In a WeChat mini program,
 * `this.setData({...})` updates `this.data` synchronously, so a naive
 * transliteration would read the *new* value on the next line and pass a
 * different number to `triggerEvent` -- silently, with no compiler
 * complaint from either side.
 *
 * Snapshotting every identifier the body reads into local `const`s at
 * handler entry reproduces the closure semantics exactly.
 */
function handlerBody(body: Stmt[]): string[] {
  const reads = new Set<string>();
  for (const stmt of body) {
    if (stmt.kind === "setState") collectReads(stmt.value, reads);
    else stmt.args.forEach((a) => collectReads(a, reads));
  }
  const writes = new Set(body.filter((s) => s.kind === "setState").map((s) => (s as Extract<Stmt, { kind: "setState" }>).target));
  // Only names that are both read and (possibly) written need snapshotting;
  // read-only names cannot change mid-handler, so snapshotting them would
  // add noise without changing behavior.
  const snapshot = new Set([...reads].filter((name) => writes.has(name)));
  const lines = [...snapshot].map((name) => `const ${name}$0 = this.data.${name};`);
  return [...lines, ...body.map((s) => stmtSource(s, snapshot))];
}

function attrSource(attr: AttrBinding, tag: HtmlTag, extraClasses: string[]): string | null {
  const mapped = ATTR_MAP[attr.name] ?? attr.name;
  if (attr.name === "class") {
    if (attr.kind === "static") {
      extraClasses.unshift(attr.value);
      return null; // folded into the single class attribute below
    }
    return `class="{{ ${exprSource(attr.value, false)} }}"`;
  }
  void tag;
  if (attr.kind === "static") return `${mapped}="${attr.value.replace(/"/g, "&quot;")}"`;
  return `${mapped}="{{ ${exprSource(attr.value, false).replace(/"/g, "&quot;")} }}"`;
}

function nodeSource(node: CNode, indent: string, handlers: EmittedHandler[], counter: { n: number }, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") {
      return `${indent}${node.value.literal.value}`;
    }
    return `${indent}{{ ${exprSource(node.value, false)} }}`;
  }
  if (node.kind === "conditional") {
    const cond = exprSource(node.condition, false).replace(/"/g, "&quot;");
    const thenSrc = branchSource(node.then, `wx:if="{{ ${cond} }}"`, indent, handlers, counter, lists);
    if (node.else === null) return thenSrc;
    return `${thenSrc}\n${branchSource(node.else, "wx:else", indent, handlers, counter, lists)}`;
  }
  if (node.kind === "component") {
    // A mini program custom component is addressed by the kebab-case name
    // registered in the .json `usingComponents` map -- NOT by class name,
    // and an unregistered tag renders blank with no error at all.
    const tag = kebab(node.name);
    const args = node.props.map((a) => `${kebab(a.name)}="{{ ${exprSource(a.value, false).replace(/"/g, "&quot;")} }}"`);
    return `${indent}<${tag}${args.length ? " " + args.join(" ") : ""} />`;
  }
  if (node.kind === "list") {
    // `wx:key` takes a FIELD NAME for object items (not an expression) and
    // the sentinel `*this` for primitives -- getting this wrong silently
    // disables list diffing rather than erroring.
    const list = lists.get(node.source);
    const key = node.keyField ?? (list && list.keyField !== undefined ? list.keyField : "*this");
    const source = node.sourceExpression === undefined ? node.source : exprSource(node.sourceExpression, false);
    const directive = `wx:for="{{ ${source} }}" wx:for-item="${node.itemName}" wx:key="${key}"`;
    return branchSource(node.body, directive, indent, handlers, counter, lists);
  }
  return elementSource(node, [], indent, handlers, counter, lists);
}

function branchSource(node: CNode, directive: string, indent: string, handlers: EmittedHandler[], counter: { n: number }, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "element") return elementSource(node, [directive], indent, handlers, counter, lists);
  const inner = nodeSource(node, indent + "  ", handlers, counter, lists);
  return `${indent}<block ${directive}>\n${inner}\n${indent}</block>`;
}

function elementSource(
  node: Extract<CNode, { kind: "element" }>,
  extraDirectives: string[],
  indent: string,
  handlers: EmittedHandler[],
  counter: { n: number },
  lists: ReadonlyMap<string, ListPropDef>,
): string {
  const tag = TAG_MAP[node.tag];
  const extraClasses: string[] = [];
  const semantic = SEMANTIC_CLASS[node.tag];
  if (semantic) extraClasses.push(semantic);

  const attrParts: string[] = [];
  for (const attr of node.attrs) {
    const rendered = attrSource(attr, node.tag, extraClasses);
    if (rendered !== null) attrParts.push(rendered);
  }
  if (extraClasses.length > 0 && !attrParts.some((p) => p.startsWith("class="))) {
    attrParts.unshift(`class="${extraClasses.join(" ")}"`);
  }

  const eventParts: string[] = [];
  for (const event of node.events) {
    const methodName = handlerMethodName(node.tag, counter.n++, event.name);
    handlers.push({ methodName, body: handlerBody(event.body) });
    eventParts.push(`${EVENT_MAP[event.name]}="${methodName}"`);
  }

  const parts = [...extraDirectives, ...attrParts, ...eventParts];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";
  if (node.children.length === 0) return `${indent}<${tag}${attrText} />`;
  const childSrc = node.children.map((c) => nodeSource(c, indent + "  ", handlers, counter, lists)).join("\n");
  return `${indent}<${tag}${attrText}>\n${childSrc}\n${indent}</${tag}>`;
}

function propertyType(t: "string" | "number" | "boolean"): string {
  return t === "string" ? "String" : t === "number" ? "Number" : "Boolean";
}

function propertiesBlock(props: PropDef[]): string {
  const dataProps = props.filter((p): p is Extract<PropDef, { kind: "data" }> => p.kind === "data");
  const listProps = props.filter((p): p is ListPropDef => p.kind === "list");
  if (dataProps.length === 0 && listProps.length === 0) return "  properties: {},";
  const listEntries = listProps.map((p) => `    ${p.name}: { type: Array, value: [] },`);
  const entries = dataProps.map((p) => {
    const value = p.defaultValue !== undefined
      ? literalSource(p.defaultValue)
      : p.valueShape?.kind === "object" || p.valueShape?.kind === "slot" ? "{}"
        : p.valueShape?.kind === "array" ? "[]"
          : p.propType === "string" ? `""` : p.propType === "number" ? "0" : "false";
    const type = p.valueShape?.kind === "object" || p.valueShape?.kind === "slot" ? "Object"
      : p.valueShape?.kind === "array" ? "Array" : propertyType(p.propType);
    return `    ${p.name}: { type: ${type}, value: ${value} },`;
  });
  return `  properties: {\n${[...entries, ...listEntries].join("\n")}\n  },`;
}

function dataBlock(component: ComponentDef): string {
  if (component.state.length === 0) return "  data: {},";
  const entries = component.state.map((s) => `    ${s.name}: ${literalSource(s.initial)},`);
  return `  data: {\n${entries.join("\n")}\n  },`;
}

function methodsBlock(handlers: EmittedHandler[]): string {
  if (handlers.length === 0) return "  methods: {},";
  const entries = handlers.map((h) => `    ${h.methodName}(event) {\n${h.body.map((b) => "      " + b).join("\n")}\n    },`);
  return `  methods: {\n${entries.join("\n")}\n  },`;
}

const SEMANTIC_WXSS = `.cc-h1 { font-size: 48rpx; font-weight: bold; display: block; }
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
.cc-dt { font-weight: bold; display: block; }
.cc-dd { display: block; margin-left: 24rpx; }
`;

/**
 * The real four-file mini program component bundle, keyed by extension.
 * Typed rather than a bare `Record<string, string>` so the parser's
 * requirement for `wxml` + `js` is enforced by the compiler instead of
 * discovered at runtime.
 */
export interface MiniProgramBundle {
  wxml: string;
  js: string;
  json: string;
  wxss: string;
  [extension: string]: string;
}

/** The validator re-parses `wxml` with the real `@wxml/parser` and `js`
 * with the real TypeScript parser. */
export function emitMiniProgram(component: ComponentDef): MiniProgramBundle {
  const handlers: EmittedHandler[] = [];
  const counter = { n: 0 };
  const wxml = nodeSource(component.root, "", handlers, counter, listPropIndex(component));

  const js = [
    `// Generated by ELMOS component-dialect-engine (certified-component-v1).`,
    `Component({`,
    propertiesBlock(component.props),
    dataBlock(component),
    methodsBlock(handlers),
    `});`,
    ``,
  ].join("\n");

  // A custom component tag that is NOT in `usingComponents` renders as
  // absolutely nothing -- no error, no warning, no placeholder. This map is
  // the whole reason a WeChat component reference works, and the emitted
  // paths follow runRepository's `components/<Name>/index` layout.
  const usingComponents = Object.fromEntries(
    referencedComponents(component).map((c) => [kebab(c), `/components/${c}/index`]),
  );
  const json = JSON.stringify({ component: true, usingComponents }, null, 2) + "\n";

  return { wxml: wxml + "\n", js, json, wxss: SEMANTIC_WXSS };
}

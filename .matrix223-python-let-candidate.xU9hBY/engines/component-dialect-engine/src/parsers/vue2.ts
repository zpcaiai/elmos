/**
 * Parses one Vue 2 SFC (Options API) into the certified-component-v1
 * canonical model using the real `vue-template-compiler` 2.7.16.
 *
 * `vue-template-compiler`'s `index.js` refuses to load when `vue@3` is
 * also installed (a hard version-mismatch guard). The compiler itself is
 * in `build.js` without that guard, so it is required directly -- this is
 * the officially published build artifact, not a private internal.
 *
 * Recognized shape:
 *
 *   <template> ...single root element... </template>
 *   <script>
 *   export default {
 *     props: { label: { type: String, required: true },
 *              step:  { type: Number, default: 1 } },
 *     data() { return { count: 0 }; },
 *   };
 *   </script>
 */
import * as ts from "typescript";
import {
  at, AttrBinding, AttrName, ATTR_NAMES, CallbackPropDef, ComponentDef, DataPropDef, EventName,
  Expr, fail, HtmlTag, HTML_TAGS, Node as CNode, PrimitiveType, PropDef, requireDefined,
  require_, StateDef, validateComponent,
} from "../models";
import { callbackNameForEvent, literalFromNode, parseHandlerStatements, parseTemplateExpression } from "./expressions";

const NODE_ELEMENT = 1;
const NODE_INTERPOLATION = 2;
const NODE_TEXT = 3;

const VUE_EVENT_NAME: Record<string, EventName> = {
  click: "onClick", change: "onChange", input: "onInput", submit: "onSubmit",
};

const VUE_PROP_TYPE: Record<string, PrimitiveType> = {
  String: "string", Number: "number", Boolean: "boolean",
};

interface V2Node {
  type: number;
  tag?: string;
  text?: string;
  expression?: string;
  /** vue-template-compiler lifts v-for out of attrsList into these. */
  for?: string;
  alias?: string;
  iterator1?: string;
  key?: string;
  attrsList?: { name: string; value: string }[];
  /** `vue-template-compiler` hoists `class`/`:class` out of `attrsList`
   * into these dedicated fields, so reading only `attrsList` silently
   * loses every class attribute. */
  staticClass?: string;
  classBinding?: string;
  staticStyle?: string;
  styleBinding?: string;
  events?: Record<string, { value: string } | { value: string }[]>;
  if?: string;
  else?: boolean;
  elseif?: string;
  ifConditions?: { exp: string | undefined; block: V2Node }[];
  children?: V2Node[];
}

interface ScriptInfo {
  props: PropDef[];
  state: StateDef[];
  emittedEvents: Set<string>;
}

/**
 * Vue 2 has no `defineEmits`, so the set of events a component emits is
 * only discoverable from the `$emit(...)` calls in the template. They are
 * collected up front so handler parsing can validate against them.
 */
function collectEmittedEvents(node: V2Node, into: Set<string>): void {
  for (const handler of Object.values(node.events ?? {})) {
    const handlers = Array.isArray(handler) ? handler : [handler];
    for (const h of handlers) {
      for (const match of h.value.matchAll(/\$emit\(\s*['"]([^'"]+)['"]/g)) {
        const name = match[1];
        if (name !== undefined) into.add(name);
      }
    }
  }
  for (const child of node.children ?? []) collectEmittedEvents(child, into);
  for (const condition of node.ifConditions ?? []) {
    if (condition.block !== node) collectEmittedEvents(condition.block, into);
  }
}

function parseScript(code: string, emittedEvents: Set<string>): ScriptInfo {
  const file = ts.createSourceFile("options.ts", code, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
  const exportAssignment = file.statements.find(ts.isExportAssignment);
  const exported = requireDefined(exportAssignment, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "Vue 2 <script> must have `export default { ... }`").expression;
  require_(ts.isObjectLiteralExpression(exported), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "`export default` must be an object literal");

  const props: PropDef[] = [];
  const state: StateDef[] = [];

  for (const member of exported.properties) {
    require_(ts.isPropertyAssignment(member) || ts.isMethodDeclaration(member), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "component options must be plain properties or methods");
    require_(ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "component option names must be plain identifiers");
    const key = (member.name as ts.Identifier).text;

    if (key === "props") {
      require_(ts.isPropertyAssignment(member) && ts.isObjectLiteralExpression(member.initializer), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "`props` must be an object literal (array shorthand carries no type information)");
      for (const propMember of (member.initializer as ts.ObjectLiteralExpression).properties) {
        require_(ts.isPropertyAssignment(propMember) && ts.isIdentifier(propMember.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "each prop must be a plain property assignment");
        const name = (propMember.name as ts.Identifier).text;
        const spec = propMember.initializer;
        require_(ts.isObjectLiteralExpression(spec), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `prop ${JSON.stringify(name)} must use the { type, required, default } object form`);

        let propType: PrimitiveType | undefined;
        let required = false;
        let defaultValue: DataPropDef["defaultValue"];
        for (const field of (spec as ts.ObjectLiteralExpression).properties) {
          require_(ts.isPropertyAssignment(field) && ts.isIdentifier(field.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "prop spec fields must be plain property assignments");
          const fieldName = (field.name as ts.Identifier).text;
          if (fieldName === "type") {
            require_(ts.isIdentifier(field.initializer), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `prop ${JSON.stringify(name)} type must be String, Number or Boolean`);
            const ctor = (field.initializer as ts.Identifier).text;
            // A Vue 2 runtime prop declaration says only `Array` -- it cannot
            // express the element shape (`{ id: number; label: string }[]`).
            // Reconstructing that shape from template usage would be
            // guessing at field TYPES, so Vue 2 fails closed as a list
            // SOURCE while remaining a perfectly good list target.
            require_(ctor !== "Array", "CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT", `prop ${JSON.stringify(name)} is declared \`type: Array\`, which does not record its element shape; Vue 2 cannot be used as a source for list props (it remains supported as a target)`);
            propType = requireDefined(VUE_PROP_TYPE[ctor], "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `prop ${JSON.stringify(name)} has unsupported type ${ctor}`);
          } else if (fieldName === "required") {
            required = field.initializer.kind === ts.SyntaxKind.TrueKeyword;
          } else if (fieldName === "default") {
            defaultValue = literalFromNode(field.initializer);
          } else {
            fail("CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `prop spec field ${JSON.stringify(fieldName)} is outside certified-component-v1`);
          }
        }
        const resolved = requireDefined(propType, "CERTIFIED_COMPONENT_MISSING_TYPE", `prop ${JSON.stringify(name)} has no declared type`);
        props.push({ kind: "data", name, propType: resolved, required: required && defaultValue === undefined, defaultValue });
      }
      continue;
    }

    if (key === "data") {
      const body = ts.isMethodDeclaration(member) ? member.body : (ts.isPropertyAssignment(member) && ts.isFunctionExpression(member.initializer) ? member.initializer.body : undefined);
      const dataBody = requireDefined(body, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "`data` must be a function returning an object literal");
      const ret = dataBody.statements.find(ts.isReturnStatement);
      const returned = requireDefined(ret?.expression, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "`data()` must return an object literal");
      require_(ts.isObjectLiteralExpression(returned), "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "`data()` must return an object literal");
      for (const field of (returned as ts.ObjectLiteralExpression).properties) {
        require_(ts.isPropertyAssignment(field) && ts.isIdentifier(field.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "data fields must be plain property assignments");
        const initial = literalFromNode(field.initializer);
        state.push({ name: (field.name as ts.Identifier).text, stateType: initial.type, initial });
      }
      continue;
    }

    if (key === "name") continue;
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_SFC", `component option ${JSON.stringify(key)} is outside certified-component-v1 (no computed, watch, methods, lifecycle hooks, or mixins)`);
  }

  // Vue 2's Options API has no typed emit declaration (that arrived with
  // Vue 3's `defineEmits<...>()`), so a callback's payload TYPE is simply
  // not present in the source and cannot be recovered. `paramType` is
  // therefore left undefined rather than guessed from the call site --
  // guessing would produce a `number` annotation that a later
  // Vue2 -> React translation would emit as fact.
  //
  // Consequence: a React -> Vue 2 -> React round trip preserves structure
  // and behavior but widens `onDone: (value: number) => void` to
  // `onDone: () => void`. This is real information loss in the Vue 2
  // format, and it is reported as a translation note rather than hidden.
  for (const eventName of emittedEvents) {
    const def: CallbackPropDef = { kind: "callback", name: callbackNameForEvent(eventName), paramType: undefined };
    props.push(def);
  }
  return { props, state, emittedEvents };
}

function attrName(raw: string, what: string): AttrName {
  require_((ATTR_NAMES as readonly string[]).includes(raw), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `${what}: attribute ${JSON.stringify(raw)} is outside certified-component-v1`);
  return raw as AttrName;
}

function parseNode(node: V2Node, script: ScriptInfo, stateNames: ReadonlySet<string>): CNode | null {
  if (node.type === NODE_TEXT) {
    const text = (node.text ?? "").trim();
    if (text.length === 0) return null;
    return { kind: "text", value: { kind: "literal", literal: { type: "string", value: text } } };
  }
  if (node.type === NODE_INTERPOLATION) {
    // Vue 2 stores `{{ label }}` raw in `text` and its compiled form in
    // `expression`; the raw text is the certified surface.
    const raw = (node.text ?? "").replace(/^\s*\{\{/, "").replace(/\}\}\s*$/, "").trim();
    return { kind: "text", value: parseTemplateExpression(raw, "interpolation") };
  }
  require_(node.type === NODE_ELEMENT, "CERTIFIED_COMPONENT_UNSUPPORTED_TEMPLATE_NODE", `template node type ${node.type} is outside certified-component-v1`);

  const tag = String(node.tag ?? "");
  require_((HTML_TAGS as readonly string[]).includes(tag), "CERTIFIED_COMPONENT_UNSUPPORTED_TAG", `tag ${JSON.stringify(tag)} is outside certified-component-v1`);

  const attrs: AttrBinding[] = [];
  const events: { name: EventName; body: ReturnType<typeof parseHandlerStatements> }[] = [];

  // `class` never appears in attrsList -- vue-template-compiler moves it to
  // staticClass / classBinding. Reading only attrsList drops it silently,
  // which a React -> Vue2 -> React round trip catches immediately.
  if (node.staticClass !== undefined) {
    // staticClass arrives already JSON-quoted (e.g. `"counter"`).
    const raw = node.staticClass.replace(/^"(.*)"$/s, "$1");
    attrs.push({ kind: "static", name: "class", value: raw });
  }
  if (node.classBinding !== undefined) {
    attrs.push({ kind: "dynamic", name: "class", value: parseTemplateExpression(node.classBinding, `<${tag}> :class`) });
  }
  require_(node.staticStyle === undefined && node.styleBinding === undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: style bindings are outside certified-component-v1`);

  for (const attr of node.attrsList ?? []) {
    const name = attr.name;
    if (name.startsWith("@") || name.startsWith("v-on:")) continue; // handled from node.events
    if (name === "v-if" || name === "v-else" || name === "v-else-if") continue;
    if (name.startsWith(":") || name.startsWith("v-bind:")) {
      const bound = name.startsWith(":") ? name.slice(1) : name.slice("v-bind:".length);
      attrs.push({ kind: "dynamic", name: attrName(bound, `<${tag}>`), value: parseTemplateExpression(attr.value, `<${tag}> :${bound}`) });
      continue;
    }
    require_(!name.startsWith("v-"), "CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", `<${tag}>: directive ${JSON.stringify(name)} is outside certified-component-v1`);
    attrs.push({ kind: "static", name: attrName(name, `<${tag}>`), value: attr.value });
  }

  for (const [rawEvent, handler] of Object.entries(node.events ?? {})) {
    const eventName = requireDefined(VUE_EVENT_NAME[rawEvent], "CERTIFIED_COMPONENT_UNSUPPORTED_EVENT", `<${tag}>: event ${JSON.stringify(rawEvent)} is outside certified-component-v1`);
    const handlers = Array.isArray(handler) ? handler : [handler];
    require_(handlers.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_EVENT", `<${tag}>: multiple handlers for ${rawEvent} are outside certified-component-v1`);
    const body = parseHandlerStatements(at(handlers, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_EVENT", "missing handler").value, {
      stateNames,
      eventToCallback: (name) => (script.emittedEvents.has(name) ? callbackNameForEvent(name) : null),
      matchEmitCall: (call) => {
        // Vue 2 emits with `$emit('name', payload)`.
        if (ts.isIdentifier(call.expression) && call.expression.text === "$emit") {
          const first = call.arguments[0];
          if (first && ts.isStringLiteral(first)) return { eventName: first.text, args: call.arguments.slice(1) };
        }
        if (ts.isPropertyAccessExpression(call.expression) && call.expression.name.text === "$emit") {
          const first = call.arguments[0];
          if (first && ts.isStringLiteral(first)) return { eventName: first.text, args: call.arguments.slice(1) };
        }
        return null;
      },
    }, `<${tag}> @${rawEvent}`);
    events.push({ name: eventName, body });
  }

  const children = (node.children ?? [])
    .map((c) => parseNode(c, script, stateNames))
    .filter((c): c is CNode => c !== null);

  const element: CNode = { kind: "element", tag: tag as HtmlTag, attrs, events, children };

  require_(node.for === undefined, "CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT", `<${tag}>: v-for cannot be read back from Vue 2, whose \`type: Array\` prop declaration does not record the element shape; Vue 2 remains supported as a list TARGET`);

  // Vue 2 attaches the whole if/else chain to the `v-if` node via
  // `ifConditions`, where entry 0 is the node itself.
  if (node.if && node.ifConditions && node.ifConditions.length > 0) {
    const branches = node.ifConditions;
    require_(branches.length <= 2, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "certified-component-v1 supports a single v-if/v-else pair, not v-else-if chains");
    const elseBranch = branches[1];
    const elseNode = elseBranch ? parseNode(elseBranch.block, script, stateNames) : null;
    return { kind: "conditional", condition: parseTemplateExpression(node.if, `<${tag}> v-if`), then: element, else: elseNode };
  }
  return element;
}

export function parseVue2Component(source: string, fileName = "Component.vue"): ComponentDef {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const compiler = require("vue-template-compiler/build");
  const descriptor = compiler.parseComponent(source);
  const template = requireDefined(descriptor.template, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "SFC must have a <template> block");
  const script = requireDefined(descriptor.script, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "SFC must have a <script> block");

  const compiled = compiler.compile(template.content);
  require_((compiled.errors ?? []).length === 0, "CERTIFIED_COMPONENT_PARSE_FAILED", `vue-template-compiler rejected the template: ${(compiled.errors ?? []).join("; ")}`);
  const ast = requireDefined(compiled.ast, "CERTIFIED_COMPONENT_PARSE_FAILED", "template produced no AST") as V2Node;

  const emittedEvents = new Set<string>();
  collectEmittedEvents(ast, emittedEvents);
  const scriptInfo = parseScript(script.content, emittedEvents);
  const stateNames = new Set(scriptInfo.state.map((s) => s.name));

  const root = requireDefined(parseNode(ast, scriptInfo, stateNames), "CERTIFIED_COMPONENT_PARSE_FAILED", "template produced no root node");

  const base = fileName.replace(/\.vue$/i, "").replace(/[^A-Za-z0-9]/g, "");
  const component: ComponentDef = {
    name: base.charAt(0).toUpperCase() + base.slice(1),
    props: scriptInfo.props,
    state: scriptInfo.state,
    root,
  };
  validateComponent(component);
  return component;
}

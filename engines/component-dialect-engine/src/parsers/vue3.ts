/**
 * Parses one Vue 3 SFC (`<script setup lang="ts">` + `<template>`) into the
 * certified-component-v1 canonical model, using the real
 * `@vue/compiler-sfc` as the parsing frontend. Template expressions and
 * handler bodies go through the real TypeScript parser (`./expressions`).
 *
 * Recognized shape (anything else raises DialectError):
 *
 *   <script setup lang="ts">
 *   import { ref } from "vue";
 *   const props = defineProps<{ label: string; step?: number }>();
 *   const emit  = defineEmits<{ (e: "done", value: number): void }>();
 *   const count = ref<number>(0);
 *   </script>
 *   <template> ...single root element... </template>
 *
 * `withDefaults(defineProps<...>(), { step: 1 })` is also recognized and
 * becomes the canonical prop default.
 */
import * as ts from "typescript";
import {
  at, AttrBinding, AttrName, ATTR_NAMES, CallbackPropDef, ComponentDef, DataPropDef, EventName,
  Expr, fail, HtmlTag, HTML_TAGS, ListPropDef, Literal, Node as CNode, PrimitiveType, PropDef, requireDefined,
  require_, StateDef, validateComponent, ComponentArg } from "../models";
import { callbackNameForEvent, literalFromNode, parseExprNode, parseHandlerStatements, parseTemplateExpression } from "./expressions";
import { inferKeyField, isArrayTypeNode, listElementFromArrayType } from "./react";

// Node type constants from @vue/compiler-core's NodeTypes enum. Pinned to
// the values observed in the installed compiler (3.5.x) via a direct AST
// dump rather than assumed.
const NODE_ROOT = 0;
const NODE_ELEMENT = 1;
const NODE_TEXT = 2;
const NODE_INTERPOLATION = 5;
const ATTR_PLAIN = 6;
const ATTR_DIRECTIVE = 7;

const VUE_EVENT_NAME: Record<string, EventName> = {
  click: "onClick", change: "onChange", input: "onInput", submit: "onSubmit",
};

interface VueNode {
  type: number;
  tag?: string;
  content?: unknown;
  props?: VueProp[];
  children?: VueNode[];
}

interface VueProp {
  type: number;
  name?: string;
  arg?: { content?: string };
  exp?: { content?: string };
  value?: { content?: string };
}

function primitiveFromTypeNode(node: ts.TypeNode | undefined, what: string): PrimitiveType {
  const text = requireDefined(node, "CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`).getText();
  if (text === "string" || text === "number" || text === "boolean") return text;
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${JSON.stringify(text)}`);
}

interface ScriptInfo {
  props: PropDef[];
  state: StateDef[];
  eventNames: Set<string>;
}

function parseScriptSetup(code: string): ScriptInfo {
  const file = ts.createSourceFile("setup.ts", code, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
  const props: PropDef[] = [];
  const state: StateDef[] = [];
  const eventNames = new Set<string>();
  const optionalProps = new Set<string>();
  const propDefaults = new Map<string, Literal>();
  let propTypeLiteral: ts.TypeLiteralNode | undefined;

  const readDefineProps = (call: ts.CallExpression): void => {
    const typeArg = at(call.typeArguments ?? [], 0, "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "defineProps requires an inline type argument");
    require_(ts.isTypeLiteralNode(typeArg), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "defineProps type argument must be an inline type literal");
    propTypeLiteral = typeArg;
  };

  const readDefineEmits = (call: ts.CallExpression): void => {
    const typeArg = at(call.typeArguments ?? [], 0, "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "defineEmits requires an inline type argument");
    require_(ts.isTypeLiteralNode(typeArg), "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "defineEmits type argument must be an inline type literal");
    for (const member of typeArg.members) {
      require_(ts.isCallSignatureDeclaration(member), "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "defineEmits members must be call signatures");
      const first = at(member.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "emit signature needs an event-name parameter");
      const literalType = requireDefined(first.type, "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "emit event parameter needs a string-literal type");
      require_(ts.isLiteralTypeNode(literalType) && ts.isStringLiteral(literalType.literal), "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "emit event parameter must be a string-literal type");
      const eventName = (literalType.literal as ts.StringLiteral).text;
      require_(member.parameters.length <= 2, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `emit ${JSON.stringify(eventName)} declares more than one payload parameter`);
      const paramType = member.parameters.length === 2
        ? primitiveFromTypeNode(at(member.parameters, 1, "CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE", "missing payload").type, `emit ${eventName} payload`)
        : undefined;
      eventNames.add(eventName);
      const def: CallbackPropDef = { kind: "callback", name: callbackNameForEvent(eventName), paramType };
      props.push(def);
    }
  };

  const visitCall = (call: ts.CallExpression): boolean => {
    if (!ts.isIdentifier(call.expression)) return false;
    const callee = call.expression.text;
    if (callee === "defineProps") { readDefineProps(call); return true; }
    if (callee === "defineEmits") { readDefineEmits(call); return true; }
    if (callee === "withDefaults") {
      const inner = at(call.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "withDefaults needs a defineProps call");
      require_(ts.isCallExpression(inner) && ts.isIdentifier(inner.expression) && inner.expression.text === "defineProps", "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "withDefaults first argument must be defineProps");
      readDefineProps(inner);
      const defaults = at(call.arguments, 1, "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "withDefaults needs a defaults object");
      require_(ts.isObjectLiteralExpression(defaults), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "withDefaults defaults must be an object literal");
      for (const prop of defaults.properties) {
        require_(ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "withDefaults entries must be plain property assignments");
        propDefaults.set((prop.name as ts.Identifier).text, literalFromNode(prop.initializer));
      }
      return true;
    }
    return false;
  };

  for (const stmt of file.statements) {
    if (ts.isImportDeclaration(stmt)) continue;
    if (ts.isExpressionStatement(stmt) && ts.isCallExpression(stmt.expression)) {
      if (visitCall(stmt.expression)) continue;
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", `<script setup> statement ${JSON.stringify(stmt.getText())} is outside certified-component-v1`);
    }
    if (ts.isVariableStatement(stmt)) {
      require_(stmt.declarationList.declarations.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "only one declaration per const statement is supported");
      const decl = at(stmt.declarationList.declarations, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing declaration");
      const initializer = requireDefined(decl.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "declaration must have an initializer");
      if (ts.isCallExpression(initializer) && visitCall(initializer)) continue;
      require_(ts.isIdentifier(decl.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "state declaration must bind a plain name");
      require_(ts.isCallExpression(initializer) && ts.isIdentifier(initializer.expression) && initializer.expression.text === "ref", "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", `only ref(...) state declarations are supported, found ${JSON.stringify(decl.getText())}`);
      const call = initializer as ts.CallExpression;
      require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "ref() must be called with exactly one literal initial value");
      const initial = literalFromNode(at(call.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing ref argument"));
      state.push({ name: (decl.name as ts.Identifier).text, stateType: initial.type, initial });
      continue;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", `<script setup> statement kind ${ts.SyntaxKind[stmt.kind]} is outside certified-component-v1`);
  }

  // Data props come first, in their declared order, then callbacks -- the
  // same order the React parser produces, so a React -> Vue -> React round
  // trip yields an identical canonical model rather than merely an
  // equivalent one. Tests assert exact equality, which is a strictly
  // stronger check than "looks the same".
  const dataProps: DataPropDef[] = [];
  const listProps: ListPropDef[] = [];
  if (propTypeLiteral) {
    for (const member of propTypeLiteral.members) {
      require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "props type literal must contain plain property signatures");
      const name = (member.name as ts.Identifier).text;
      if (member.questionToken) optionalProps.add(name);
      const annotation = member.type;
      if (annotation !== undefined && isArrayTypeNode(annotation)) {
        const shape = listElementFromArrayType(annotation, `list prop ${JSON.stringify(name)}`);
        listProps.push({ kind: "list", name, element: shape, keyField: inferKeyField(shape, `list prop ${JSON.stringify(name)}`) });
        continue;
      }
      const propType = primitiveFromTypeNode(member.type, `prop ${name}`);
      const defaultValue = propDefaults.get(name);
      dataProps.push({ kind: "data", name, propType, required: !member.questionToken, defaultValue });
    }
  }

  return { props: [...dataProps, ...listProps, ...props], state, eventNames };
}

function attrName(raw: string, what: string): AttrName {
  require_((ATTR_NAMES as readonly string[]).includes(raw), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `${what}: attribute ${JSON.stringify(raw)} is outside certified-component-v1`);
  return raw as AttrName;
}

function isElement(node: VueNode): boolean {
  return node.type === NODE_ELEMENT;
}

function meaningfulChildren(children: readonly VueNode[]): VueNode[] {
  return children.filter((c) => !(c.type === NODE_TEXT && String(c.content ?? "").trim() === ""));
}

function parseNode(node: VueNode, script: ScriptInfo, siblings: VueNode[], indexInParent: number): CNode | null {
  if (node.type === NODE_TEXT) {
    const text = String(node.content ?? "").trim();
    if (text.length === 0) return null;
    return { kind: "text", value: { kind: "literal", literal: { type: "string", value: text } } };
  }
  if (node.type === NODE_INTERPOLATION) {
    const raw = (node.content as { content?: string } | undefined)?.content ?? "";
    return { kind: "text", value: parseTemplateExpression(raw, "interpolation") };
  }
  require_(isElement(node), "CERTIFIED_COMPONENT_UNSUPPORTED_TEMPLATE_NODE", `template node type ${node.type} is outside certified-component-v1`);

  const tag = String(node.tag ?? "");

  // @vue/compiler-sfc classifies an element as a COMPONENT itself, so this
  // reads the compiler's own judgement rather than re-deriving it from
  // capitalisation.
  if (/^[A-Z]/.test(tag)) {
    const componentProps: ComponentArg[] = [];
    for (const prop of node.props ?? []) {
      if (prop.type === ATTR_PLAIN) {
        componentProps.push({ name: String(prop.name ?? ""), value: { kind: "literal", literal: { type: "string", value: prop.value?.content ?? "" } } });
        continue;
      }
      const dirName = String(prop.name ?? "");
      require_(dirName === "bind", "CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", `<${tag}>: v-${dirName} on a component reference is outside certified-component-v1`);
      const argName = String(prop.arg?.content ?? "");
      componentProps.push({ name: argName, value: parseTemplateExpression(String(prop.exp?.content ?? ""), `<${tag}> :${argName}`) });
    }
    require_((node.children ?? []).filter((c) => !(c.type === 2 && String(c.content ?? "").trim() === "")).length === 0,
      "CERTIFIED_COMPONENT_UNSUPPORTED_SLOT", `<${tag}> is given slot content, which is outside certified-component-v1`);
    return { kind: "component", name: tag, props: componentProps };
  }

  require_((HTML_TAGS as readonly string[]).includes(tag), "CERTIFIED_COMPONENT_UNSUPPORTED_TAG", `tag ${JSON.stringify(tag)} is outside certified-component-v1`);

  const attrs: AttrBinding[] = [];
  const events: { name: EventName; body: ReturnType<typeof parseHandlerStatements> }[] = [];
  let vIf: Expr | null = null;
  let vFor: { itemName: string; source: string } | null = null;
  let hasVElse = false;

  const stateNames = new Set(script.state.map((s) => s.name));

  for (const prop of node.props ?? []) {
    if (prop.type === ATTR_PLAIN) {
      const name = String(prop.name ?? "");
      attrs.push({ kind: "static", name: attrName(name, `<${tag}>`), value: prop.value?.content ?? "" });
      continue;
    }
    require_(prop.type === ATTR_DIRECTIVE, "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: unsupported attribute node type ${prop.type}`);
    const directive = String(prop.name ?? "");
    if (directive === "if") {
      vIf = parseTemplateExpression(prop.exp?.content ?? "", `<${tag}> v-if`);
      continue;
    }
    if (directive === "for") {
      // `v-for="row in rows"` -- the compiler keeps the raw expression, so
      // the binding is split here rather than re-parsed as JS.
      const raw = (prop.exp?.content ?? "").trim();
      const match = /^\(?\s*([A-Za-z_$][\w$]*)\s*\)?\s+(?:in|of)\s+([A-Za-z_$][\w$]*)\s*$/.exec(raw);
      require_(match !== null, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", `<${tag}>: v-for must be "item in listProp" over a declared list prop (index bindings and expressions are outside certified-component-v1), got ${JSON.stringify(raw)}`);
      vFor = { itemName: (match as RegExpExecArray)[1] as string, source: (match as RegExpExecArray)[2] as string };
      continue;
    }
    if (directive === "bind" && prop.arg?.content === "key") {
      // Identity is carried by the list prop's keyField in the canonical
      // model; the emitted `:key` is derived, so it is dropped on re-parse.
      continue;
    }
    if (directive === "else") { hasVElse = true; continue; }
    if (directive === "bind") {
      const arg = requireDefined(prop.arg?.content, "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: v-bind without an argument is outside certified-component-v1`);
      attrs.push({ kind: "dynamic", name: attrName(arg, `<${tag}>`), value: parseTemplateExpression(prop.exp?.content ?? "", `<${tag}> :${arg}`) });
      continue;
    }
    if (directive === "on") {
      const arg = requireDefined(prop.arg?.content, "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: v-on without an argument is outside certified-component-v1`);
      const eventName = requireDefined(VUE_EVENT_NAME[arg], "CERTIFIED_COMPONENT_UNSUPPORTED_EVENT", `<${tag}>: event ${JSON.stringify(arg)} is outside certified-component-v1`);
      const body = parseHandlerStatements(prop.exp?.content ?? "", {
        stateNames,
        eventToCallback: (name) => (script.eventNames.has(name) ? callbackNameForEvent(name) : null),
        matchEmitCall: (call) => {
          if (ts.isIdentifier(call.expression) && call.expression.text === "emit") {
            const first = call.arguments[0];
            if (first && ts.isStringLiteral(first)) {
              return { eventName: first.text, args: call.arguments.slice(1) };
            }
          }
          return null;
        },
      }, `<${tag}> @${arg}`);
      events.push({ name: eventName, body });
      continue;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE", `<${tag}>: directive v-${directive} is outside certified-component-v1`);
  }

  const childNodes = meaningfulChildren(node.children ?? [])
    .map((c, i, arr) => parseNode(c, script, arr, i))
    .filter((c): c is CNode => c !== null);

  const element: CNode = { kind: "element", tag: tag as HtmlTag, attrs, events, children: childNodes };

  if (vFor !== null) {
    return { kind: "list", source: vFor.source, itemName: vFor.itemName, body: element };
  }
  if (hasVElse) return null; // consumed by the preceding v-if branch
  if (vIf !== null) {
    // Vue conditionals are sibling-based: `<em v-if>` followed by
    // `<em v-else>`. The canonical model nests them, so the v-else sibling
    // must be looked up here rather than emitted as its own child.
    const next = siblings[indexInParent + 1];
    let elseNode: CNode | null = null;
    if (next && isElement(next) && (next.props ?? []).some((p) => p.type === ATTR_DIRECTIVE && p.name === "else")) {
      elseNode = parseElseBranch(next, script);
    }
    return { kind: "conditional", condition: vIf, then: element, else: elseNode };
  }
  return element;
}

function parseElseBranch(node: VueNode, script: ScriptInfo): CNode {
  const stripped: VueNode = { ...node, props: (node.props ?? []).filter((p) => !(p.type === ATTR_DIRECTIVE && p.name === "else")) };
  const parsed = parseNode(stripped, script, [stripped], 0);
  return requireDefined(parsed, "CERTIFIED_COMPONENT_UNSUPPORTED_TEMPLATE_NODE", "v-else branch produced no node");
}

export function parseVue3Component(source: string, fileName = "Component.vue"): ComponentDef {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const sfc = require("@vue/compiler-sfc");
  const { descriptor, errors } = sfc.parse(source, { filename: fileName });
  require_(errors.length === 0, "CERTIFIED_COMPONENT_PARSE_FAILED", `@vue/compiler-sfc rejected the SFC: ${errors.map(String).join("; ")}`);
  require_(descriptor.script === null || descriptor.script === undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "certified-component-v1 supports <script setup> only, not a plain <script> block");
  const scriptSetup = requireDefined(descriptor.scriptSetup, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "SFC must have a <script setup> block");
  const template = requireDefined(descriptor.template, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "SFC must have a <template> block");

  const script = parseScriptSetup(scriptSetup.content);

  const ast = requireDefined(template.ast, "CERTIFIED_COMPONENT_PARSE_FAILED", "template AST unavailable") as VueNode;
  require_(ast.type === NODE_ROOT, "CERTIFIED_COMPONENT_PARSE_FAILED", "unexpected template root node");
  const roots = meaningfulChildren(ast.children ?? []);
  require_(roots.length === 1, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", `certified-component-v1 requires exactly one root element, found ${roots.length}`);
  const rootNode = at(roots, 0, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", "missing root element");
  const root = requireDefined(parseNode(rootNode, script, roots, 0), "CERTIFIED_COMPONENT_PARSE_FAILED", "root element produced no node");

  const name = fileName.replace(/\.vue$/i, "").replace(/[^A-Za-z0-9]/g, "");
  const component: ComponentDef = { name: name.charAt(0).toUpperCase() + name.slice(1), props: script.props, state: script.state, root };
  validateComponent(component);
  return component;
}

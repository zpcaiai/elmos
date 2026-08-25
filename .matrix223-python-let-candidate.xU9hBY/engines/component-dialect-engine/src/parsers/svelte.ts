/**
 * Parses one Svelte 5 component into the certified-component-v1 canonical
 * model using the real `svelte/compiler`.
 *
 * Svelte's AST embeds ESTree nodes for every expression, which is a
 * *different* node vocabulary from the TypeScript AST the other parsers
 * share (`estree` uses `Identifier`/`BinaryExpression`/`Literal` with
 * string `type` tags rather than TypeScript's numeric `SyntaxKind`). The
 * ESTree subset certified-component-v1 accepts is therefore translated
 * here explicitly; anything else raises DialectError instead of being
 * approximated.
 *
 * Recognized shape:
 *
 *   <script lang="ts">
 *     let { label, step = 1, onDone }: { ... } = $props();
 *     let count = $state<number>(0);
 *   </script>
 *   <div>...single root element...</div>
 */
import {
  at, AttrBinding, AttrName, ATTR_NAMES, BinaryOperator, CallbackPropDef, ComponentDef, DataPropDef,
  EventName, Expr, fail, HtmlTag, HTML_TAGS, ListElementShape, ListPropDef, Literal, Node as CNode, PrimitiveType, PropDef,
  requireDefined, require_, StateDef, Stmt, validateComponent, ComponentArg } from "../models";

const SVELTE_EVENT_ATTR: Record<string, EventName> = {
  onclick: "onClick", onchange: "onChange", oninput: "onInput", onsubmit: "onSubmit",
};

const ESTREE_BINARY: Record<string, BinaryOperator> = {
  "+": "+", "-": "-", "*": "*", "/": "/", "%": "%",
  "<": "<", "<=": "<=", ">": ">", ">=": ">=",
  "==": "==", "===": "==", "!=": "!=", "!==": "!=",
  "&&": "&&", "||": "||",
};

/* eslint-disable @typescript-eslint/no-explicit-any */
type EsNode = any;
type SvelteNode = any;

function esLiteral(node: EsNode): Literal {
  if (node.type === "Literal") {
    if (typeof node.value === "string") return { type: "string", value: node.value };
    if (typeof node.value === "number") return { type: "number", value: node.value };
    if (typeof node.value === "boolean") return { type: "boolean", value: node.value };
  }
  if (node.type === "UnaryExpression" && node.operator === "-" && node.argument?.type === "Literal" && typeof node.argument.value === "number") {
    return { type: "number", value: -node.argument.value };
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `expression of type ${node.type} is not a plain literal`);
}

function esExpr(node: EsNode): Expr {
  switch (node.type) {
    case "Identifier":
      return { kind: "ident", name: node.name };
    case "MemberExpression":
      // `row.label` off an {#each} item. Computed access (`row[k]`) has no
      // certified counterpart on other targets, so it stays rejected.
      require_(!node.computed, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", "computed member access is outside certified-component-v1");
      require_(node.object?.type === "Identifier" && node.property?.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", "only single-level field access on a list item is supported");
      return { kind: "member", object: node.object.name, field: node.property.name };
    case "Literal":
      return { kind: "literal", literal: esLiteral(node) };
    case "UnaryExpression":
      if (node.operator === "!") return { kind: "unaryNot", operand: esExpr(node.argument) };
      if (node.operator === "-" && node.argument?.type === "Literal") return { kind: "literal", literal: esLiteral(node) };
      break;
    case "LogicalExpression":
    case "BinaryExpression": {
      const op = requireDefined(ESTREE_BINARY[node.operator], "CERTIFIED_COMPONENT_UNSUPPORTED_OPERATOR", `operator ${node.operator} is outside certified-component-v1`);
      return { kind: "binary", operator: op, left: esExpr(node.left), right: esExpr(node.right) };
    }
    case "ConditionalExpression":
      return { kind: "ternary", condition: esExpr(node.test), then: esExpr(node.consequent), else: esExpr(node.alternate) };
    default:
      break;
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `expression type ${node.type} is outside certified-component-v1`);
}

/** Maps a TypeScript type annotation carried in the Svelte script (parsed
 * by svelte/compiler with `lang="ts"`) to a canonical primitive. */
/** Svelte's TS AST (acorn-typescript) names the element type
 * `elementType` on TSArrayType, matching TypeScript's own naming. */
function esListElement(elementType: EsNode, what: string): ListElementShape {
  if (elementType.type === "TSTypeLiteral") {
    const fields: Record<string, PrimitiveType> = {};
    for (const member of elementType.members) {
      require_(member.type === "TSPropertySignature" && member.key?.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}: list element type must contain plain property signatures`);
      require_(!member.optional, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}: optional list element fields are outside certified-component-v1`);
      fields[member.key.name] = esPrimitiveType(member.typeAnnotation, `${what} field`);
    }
    return { kind: "object", fields };
  }
  return { kind: "primitive", primitive: esPrimitiveType(elementType, `${what} element`) };
}

/** Same identity rule the React parser uses, kept in sync deliberately. */
function esInferKey(element: ListElementShape, what: string): string | undefined {
  if (element.kind === "primitive") return undefined;
  const names = Object.keys(element.fields);
  if (names.includes("id")) return "id";
  const candidates = names.filter((n) => /(Id|Key)$/.test(n));
  require_(candidates.length === 1, "CERTIFIED_COMPONENT_MISSING_LIST_KEY", `${what}: list elements need an identity field named "id" (or exactly one field ending in "Id"/"Key"); found ${JSON.stringify(names)}`);
  return at(candidates, 0, "CERTIFIED_COMPONENT_MISSING_LIST_KEY", `${what}: missing key candidate`);
}

function esPrimitiveType(annotation: EsNode | undefined, what: string): PrimitiveType {
  const node = requireDefined(annotation, "CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`);
  const inner = node.typeAnnotation ?? node;
  if (inner.type === "TSStringKeyword") return "string";
  if (inner.type === "TSNumberKeyword") return "number";
  if (inner.type === "TSBooleanKeyword") return "boolean";
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${inner.type}`);
}

interface ScriptInfo {
  props: PropDef[];
  state: StateDef[];
}

function parseInstanceScript(body: EsNode[]): ScriptInfo {
  const props: PropDef[] = [];
  const state: StateDef[] = [];

  for (const stmt of body) {
    if (stmt.type === "ImportDeclaration") continue;
    require_(stmt.type === "VariableDeclaration", "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", `<script> statement ${stmt.type} is outside certified-component-v1`);
    require_(stmt.declarations.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "only one declarator per statement is supported");
    const decl: EsNode = at<EsNode>(stmt.declarations, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing declarator");
    const init = requireDefined(decl.init, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "declaration must have an initializer");

    // `let { a, b = 1 }: {...} = $props();`
    if (init.type === "CallExpression" && init.callee?.type === "Identifier" && init.callee.name === "$props") {
      require_(decl.id.type === "ObjectPattern", "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "$props() must be destructured into an object pattern");
      const annotation = requireDefined(decl.id.typeAnnotation, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "the $props() destructuring needs an inline type literal annotation");
      const literalType = annotation.typeAnnotation;
      require_(literalType?.type === "TSTypeLiteral", "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "the $props() type annotation must be an inline type literal");

      const fieldTypes = new Map<string, EsNode>();
      const optional = new Set<string>();
      for (const member of literalType.members) {
        require_(member.type === "TSPropertySignature" && member.key?.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "props type literal must contain plain property signatures");
        fieldTypes.set(member.key.name, member.typeAnnotation);
        if (member.optional) optional.add(member.key.name);
      }

      const dataProps: DataPropDef[] = [];
      const listProps: ListPropDef[] = [];
      const callbacks: CallbackPropDef[] = [];
      for (const prop of decl.id.properties) {
        require_(prop.type === "Property" && prop.key?.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props destructuring must bind plain names (no rest patterns)");
        const name = prop.key.name;
        const annotationNode = requireDefined(fieldTypes.get(name), "CERTIFIED_COMPONENT_UNKNOWN_PROP", `destructured prop ${JSON.stringify(name)} is not declared in the props type`);
        const typeNode = annotationNode.typeAnnotation ?? annotationNode;

        if (/^on[A-Z]/.test(name)) {
          require_(typeNode.type === "TSFunctionType", "CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE", `callback prop ${JSON.stringify(name)} must have a function type`);
          // Svelte parses TypeScript with acorn-typescript, whose
          // TSFunctionType node names its parameter list `parameters` --
          // NOT `params` as the TypeScript compiler's own AST does.
          // Reading `params` silently yields an empty list, which would
          // drop the payload type without any error.
          const params: EsNode[] = typeNode.parameters ?? typeNode.params ?? [];
          require_(params.length <= 1, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", `callback prop ${JSON.stringify(name)} may take at most one parameter`);
          const paramType = params.length === 1
            ? esPrimitiveType(at<EsNode>(params, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", "missing callback parameter").typeAnnotation, `${name} parameter`)
            : undefined;
          callbacks.push({ kind: "callback", name, paramType });
          continue;
        }

        const inner = annotationNode.typeAnnotation ?? annotationNode;
        if (inner.type === "TSArrayType") {
          const shape = esListElement(inner.elementType, `list prop ${JSON.stringify(name)}`);
          listProps.push({ kind: "list", name, element: shape, keyField: esInferKey(shape, `list prop ${JSON.stringify(name)}`) });
          continue;
        }
        const propType = esPrimitiveType(annotationNode, `prop ${name}`);
        // `{ step = 1 }` shows up as an AssignmentPattern value.
        const defaultValue = prop.value?.type === "AssignmentPattern" ? esLiteral(prop.value.right) : undefined;
        dataProps.push({ kind: "data", name, propType, required: !optional.has(name) && defaultValue === undefined, defaultValue });
      }
      props.push(...dataProps, ...listProps, ...callbacks);
      continue;
    }

    // `let count = $state<number>(0);`
    if (init.type === "CallExpression" && init.callee?.type === "Identifier" && init.callee.name === "$state") {
      require_(decl.id.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "$state must be assigned to a plain name");
      require_((init.arguments ?? []).length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "$state() must be called with exactly one literal initial value");
      const initial = esLiteral(at<EsNode>(init.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing $state argument"));
      state.push({ name: decl.id.name, stateType: initial.type, initial });
      continue;
    }

    fail("CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "only `$props()` destructuring and `$state(...)` declarations are supported in <script>");
  }
  return { props, state };
}

function parseHandler(fn: EsNode, stateNames: ReadonlySet<string>, callbackNames: ReadonlySet<string>, what: string): Stmt[] {
  require_(fn.type === "ArrowFunctionExpression", "CERTIFIED_COMPONENT_BAD_EVENT_BINDING", `${what} must bind to an inline arrow function`);
  const statements: EsNode[] = fn.body.type === "BlockStatement" ? fn.body.body : [{ type: "ExpressionStatement", expression: fn.body }];
  const result: Stmt[] = [];
  for (const stmt of statements) {
    require_(stmt.type === "ExpressionStatement", "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: handler may only contain expression statements`);
    const expr = stmt.expression;
    if (expr.type === "AssignmentExpression" && expr.operator === "=") {
      require_(expr.left.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: assignment target must be a plain state name`);
      require_(stateNames.has(expr.left.name), "CERTIFIED_COMPONENT_UNKNOWN_STATE_TARGET", `${what}: ${JSON.stringify(expr.left.name)} is not declared state`);
      result.push({ kind: "setState", target: expr.left.name, value: esExpr(expr.right) });
      continue;
    }
    if (expr.type === "CallExpression" && expr.callee?.type === "Identifier") {
      const name = expr.callee.name;
      require_(callbackNames.has(name), "CERTIFIED_COMPONENT_UNKNOWN_CALLBACK_TARGET", `${what}: ${JSON.stringify(name)} is not a declared callback prop`);
      require_((expr.arguments ?? []).length <= 1, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `${what}: ${name} is called with more than one argument`);
      result.push({ kind: "callProp", target: name, args: (expr.arguments ?? []).map(esExpr) });
      continue;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: statement of type ${expr.type} is neither a state assignment nor a callback call`);
  }
  return result;
}

function attrName(raw: string, what: string): AttrName {
  require_((ATTR_NAMES as readonly string[]).includes(raw), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `${what}: attribute ${JSON.stringify(raw)} is outside certified-component-v1`);
  return raw as AttrName;
}

/** Whitespace-only text between markup lines is layout, not content. */
function meaningful(nodes: SvelteNode[]): SvelteNode[] {
  return nodes.filter((n) => !(n.type === "Text" && String(n.data ?? "").trim() === ""));
}

function parseFragmentNodes(nodes: SvelteNode[], ctx: ParseContext): CNode[] {
  return meaningful(nodes).map((n) => parseNode(n, ctx));
}

interface ParseContext {
  stateNames: ReadonlySet<string>;
  callbackNames: ReadonlySet<string>;
}

function parseNode(node: SvelteNode, ctx: ParseContext): CNode {
  if (node.type === "Text") {
    return { kind: "text", value: { kind: "literal", literal: { type: "string", value: String(node.data).trim() } } };
  }
  if (node.type === "ExpressionTag") {
    return { kind: "text", value: esExpr(node.expression) };
  }
  if (node.type === "EachBlock") {
    require_(node.expression?.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", "{#each} must iterate a declared list prop directly");
    require_(node.context?.type === "Identifier", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "{#each} item binding must be a plain identifier (no destructuring)");
    require_(node.index === undefined || node.index === null, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "an index binding in {#each} is outside certified-component-v1");
    const bodyNodes = parseFragmentNodes(node.body?.nodes ?? [], ctx);
    require_(bodyNodes.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY", "an {#each} body must contain exactly one element");
    return { kind: "list", source: node.expression.name, itemName: node.context.name, body: at(bodyNodes, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY", "empty each body") };
  }
  if (node.type === "IfBlock") {
    const thenNodes = parseFragmentNodes(node.consequent?.nodes ?? [], ctx);
    require_(thenNodes.length === 1, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "an {#if} branch must contain exactly one element");
    const alternateNodes = node.alternate ? parseFragmentNodes(node.alternate.nodes ?? [], ctx) : [];
    require_(alternateNodes.length <= 1, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "an {:else} branch must contain at most one element");
    return {
      kind: "conditional",
      condition: esExpr(node.test),
      then: at(thenNodes, 0, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "empty {#if} branch"),
      else: alternateNodes.length === 1 ? at(alternateNodes, 0, "CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL", "empty {:else} branch") : null,
    };
  }
  // svelte/compiler emits a distinct "Component" node type, so this is the
  // compiler's own classification rather than a naming heuristic.
  if (node.type === "Component") {
    const name = String(node.name);
    const componentProps: ComponentArg[] = [];
    for (const attr of node.attributes ?? []) {
      require_(attr.type === "Attribute", "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${name}>: ${attr.type} is outside certified-component-v1`);
      const value = attr.value;
      const tag_ = Array.isArray(value) ? value[0] : value;
      if (tag_ && tag_.type === "ExpressionTag") {
        componentProps.push({ name: String(attr.name), value: esExpr(tag_.expression) });
      } else if (tag_ && tag_.type === "Text") {
        componentProps.push({ name: String(attr.name), value: { kind: "literal", literal: { type: "string", value: String(tag_.data ?? "") } } });
      } else {
        fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${name}> prop ${String(attr.name)} has an unsupported value shape`);
      }
    }
    require_((node.fragment?.nodes ?? []).filter((n: { type: string; data?: string }) => !(n.type === "Text" && String(n.data ?? "").trim() === "")).length === 0,
      "CERTIFIED_COMPONENT_UNSUPPORTED_SLOT", `<${name}> is given slot content, which is outside certified-component-v1`);
    return { kind: "component", name, props: componentProps };
  }
  require_(node.type === "RegularElement", "CERTIFIED_COMPONENT_UNSUPPORTED_TEMPLATE_NODE", `template node type ${node.type} is outside certified-component-v1`);

  const tag = String(node.name);
  require_((HTML_TAGS as readonly string[]).includes(tag), "CERTIFIED_COMPONENT_UNSUPPORTED_TAG", `tag ${JSON.stringify(tag)} is outside certified-component-v1`);

  const attrs: AttrBinding[] = [];
  const events: { name: EventName; body: Stmt[] }[] = [];

  for (const attr of node.attributes ?? []) {
    require_(attr.type === "Attribute", "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: ${attr.type} is outside certified-component-v1 (no spreads, directives, or bindings)`);
    const name = String(attr.name);
    const mappedEvent = SVELTE_EVENT_ATTR[name];
    if (mappedEvent !== undefined) {
      // `onclick={() => ...}` -- value is an ExpressionTag holding the arrow.
      const value = attr.value;
      const expressionTag: EsNode = Array.isArray(value) ? at<EsNode>(value, 0, "CERTIFIED_COMPONENT_BAD_EVENT_BINDING", "empty event binding") : value;
      const fn = expressionTag?.expression ?? expressionTag;
      events.push({ name: mappedEvent, body: parseHandler(fn, ctx.stateNames, ctx.callbackNames, `<${tag}> ${name}`) });
      continue;
    }
    const canonical = attrName(name, `<${tag}>`);
    // A static attribute's value is an array with a single Text node;
    // `attr={expr}` gives an ExpressionTag; `attr` alone gives `true`.
    if (attr.value === true) {
      attrs.push({ kind: "static", name: canonical, value: "true" });
      continue;
    }
    const parts = Array.isArray(attr.value) ? attr.value : [attr.value];
    require_(parts.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: concatenated attribute values are outside certified-component-v1`);
    const part: EsNode = at<EsNode>(parts, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", "empty attribute value");
    if (part.type === "Text") {
      attrs.push({ kind: "static", name: canonical, value: String(part.data) });
    } else if (part.type === "ExpressionTag") {
      attrs.push({ kind: "dynamic", name: canonical, value: esExpr(part.expression) });
    } else {
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `<${tag}>: attribute value of type ${part.type} is outside certified-component-v1`);
    }
  }

  return { kind: "element", tag: tag as HtmlTag, attrs, events, children: parseFragmentNodes(node.fragment?.nodes ?? [], ctx) };
}

export function parseSvelteComponent(source: string, fileName = "Component.svelte"): ComponentDef {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const compiler = require("svelte/compiler");
  let ast: SvelteNode;
  try {
    ast = compiler.parse(source, { filename: fileName, modern: true });
  } catch (error) {
    fail("CERTIFIED_COMPONENT_PARSE_FAILED", `svelte/compiler rejected the component: ${(error as Error).message}`);
  }

  require_(!ast.module, "CERTIFIED_COMPONENT_UNSUPPORTED_SFC", "a <script module> block is outside certified-component-v1");
  const script = ast.instance ? parseInstanceScript(ast.instance.content.body) : { props: [], state: [] };

  const ctx: ParseContext = {
    stateNames: new Set(script.state.map((s) => s.name)),
    callbackNames: new Set(script.props.filter((p) => p.kind === "callback").map((p) => p.name)),
  };

  const roots: CNode[] = parseFragmentNodes(ast.fragment?.nodes ?? [], ctx);
  require_(roots.length === 1, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", `certified-component-v1 requires exactly one root element, found ${roots.length}`);

  const base = fileName.replace(/\.svelte$/i, "").replace(/[^A-Za-z0-9]/g, "");
  const component: ComponentDef = {
    name: base.charAt(0).toUpperCase() + base.slice(1),
    props: script.props,
    state: script.state,
    root: at(roots, 0, "CERTIFIED_COMPONENT_MULTIPLE_ROOTS", "missing root element"),
  };
  validateComponent(component);
  return component;
}

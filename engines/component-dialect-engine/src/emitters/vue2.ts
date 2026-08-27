/**
 * Emits certified-component-v1 canonical model as a Vue 2 SFC using the
 * Options API.
 *
 * Deliberately separate from the Vue 3 emitter despite the shared template
 * syntax, because the script half is entirely different and the
 * differences are behavioral:
 *  - State is `data()` returning an object, read as bare names in the
 *    template but `this.x` in script; there is no `ref`/`.value`.
 *  - Props are a `props: { name: { type, required, default } }` object,
 *    not a type-level `defineProps`; the type must survive as a runtime
 *    constructor (String/Number/Boolean).
 *  - Events are `$emit`, not a `defineEmits`-returned function.
 */
import { AttrBinding, ComponentDef, EventName, Expr, ListPropDef, Literal, Node as CNode, PropDef, StateDef, Stmt } from "../models";
import { listKeyExpression, listPropIndex, listSourceExpression, referencedComponents, stateInitialSource, staticListSource } from "./react";

const VUE_EVENT_DIRECTIVE: Record<EventName, string> = {
  onClick: "@click", onChange: "@change", onInput: "@input", onSubmit: "@submit",
};

const RUNTIME_TYPE: Record<string, string> = { string: "String", number: "Number", boolean: "Boolean" };

function runtimeType(prop: Extract<PropDef, { kind: "data" }>): string {
  if (prop.valueShape?.kind === "object" || prop.valueShape?.kind === "slot") return "Object";
  if (prop.valueShape?.kind === "array") return "Array";
  return RUNTIME_TYPE[prop.propType] ?? "String";
}

function literalSource(literal: Literal): string {
  if (literal.type === "string") return JSON.stringify(literal.value);
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

/** Template expressions read data/props bare; script expressions need
 * `this.`. Vue 2 has no `.value` unwrapping to worry about. */
function exprSource(expr: Expr, inScript: boolean): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e, inScript);
    return e.kind === "binary" || e.kind === "ternary" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident": return inScript ? `this.${expr.name}` : expr.name;
    // Loop variables are template-locals; `this.` would not resolve them.
    case "member": return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal": return literalSource(expr.literal);
    case "eventValue": return "$event.target.value";
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map((arg) => exprSource(arg, inScript)).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map((arg) => exprSource(arg, inScript)).join(", ")})`;
    case "numericPredicate": return `Number.${expr.predicate}(${exprSource(expr.operand, inScript)})`;
    case "numberMethod": return `${wrap(expr.receiver)}.toFixed(${expr.fractionDigits})`;
    case "numberFormat": return `${wrap(expr.operand)}.toLocaleString(${JSON.stringify(expr.locale ?? "zh-CN")})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${exprSource(expr.operand, inScript)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "percentageWidth": return `${exprSource(expr.value, inScript)} + "%"`;
    case "styleObject": return `{ ${expr.fields.map((field) => `${field.name}: ${exprSource(field.value, inScript)}`).join(", ")} }`;
    case "collectionFilter": return `${exprSource(expr.source, inScript)}.filter((${expr.itemName}) => ${exprSource(expr.predicate, inScript)})`;
    case "collectionMap": return `${exprSource(expr.source, inScript)}.map((${expr.itemName}) => (${exprSource(expr.projection, inScript)}))`;
    case "collectionReduce": return `${exprSource(expr.source, inScript)}.reduce((${expr.accumulatorName}, ${expr.itemName}) => (${exprSource(expr.reducer, inScript)}), ${exprSource(expr.initial, inScript)})`;
    case "collectionMax": return `Math.max(...${exprSource(expr.source, inScript)}.map((${expr.itemName}) => (${exprSource(expr.operand, inScript)})))`;
    case "collectionJoin": return `${exprSource(expr.source, inScript)}.join(${exprSource(expr.separator, inScript)})`;
    case "objectLookup": return `${exprSource(expr.object, inScript)}[${exprSource(expr.key, inScript)}]`;
    case "objectLiteral": return `{ ${[...expr.fields.map((field) => `${field.name}: ${exprSource(field.value, inScript)}`), ...(expr.computedFields ?? []).map((field) => `[${exprSource(field.key, inScript)}]: ${exprSource(field.value, inScript)}`)].join(", ")} }`;
    case "arrayLiteral": return `[${expr.items.map((item) => exprSource(item, inScript)).join(", ")}]`;
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

export function eventNameForCallback(callbackName: string): string {
  const rest = callbackName.slice(2);
  return rest.charAt(0).toLowerCase() + rest.slice(1);
}

function stmtSource(stmt: Stmt): string {
  // Rendered into a template attribute, so bare (template-scoped) names.
  if (stmt.kind === "setState") return `${stmt.target} = ${exprSource(stmt.value, false)}`;
  const args = stmt.args.map((a) => exprSource(a, false)).join(", ");
  return `$emit('${eventNameForCallback(stmt.target)}'${args ? ", " + args : ""})`;
}

function handlerSource(body: Stmt[]): string {
  return body.map(stmtSource).join("; ").replace(/"/g, "&quot;");
}

function attrSource(attr: AttrBinding): string {
  if (attr.kind === "static") return `${attr.name}=${JSON.stringify(attr.value)}`;
  return `:${attr.name}="${exprSource(attr.value, false).replace(/"/g, "&quot;")}"`;
}

function nodeSource(node: CNode, indent: string, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "fragment") {
    const childSrc = node.children.map((child) => nodeSource(child, indent + "  ", lists)).join("\n");
    return `${indent}<template>\n${childSrc}\n${indent}</template>`;
  }
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") return `${indent}${node.value.literal.value}`;
    return `${indent}{{ ${exprSource(node.value, false)} }}`;
  }
  if (node.kind === "conditional") {
    const cond = exprSource(node.condition, false).replace(/"/g, "&quot;");
    const thenSrc = withDirective(node.then, `v-if="${cond}"`, indent, lists);
    if (node.else === null) return thenSrc;
    return `${thenSrc}\n${withDirective(node.else, "v-else", indent, lists)}`;
  }
  if (node.kind === "component") {
    const args = node.props.map((a) => `:${a.name}="${exprSource(a.value, false).replace(/"/g, "&quot;")}"`);
    return `${indent}<${node.name}${args.length ? " " + args.join(" ") : ""} />`;
  }
  if (node.kind === "list") {
    // Same structural-directive shape as Vue 3.
    const list = lists.get(node.source);
    const key = node.keyField !== undefined ? `${node.itemName}.${node.keyField}` : list ? listKeyExpression(list, node.itemName) : node.itemName;
    const source = node.sourceExpression === undefined ? listSourceExpression(list, node.source) : exprSource(node.sourceExpression, false);
    return withDirective(node.body, `v-for="${node.itemName} in ${source}" :key="${key}"`, indent, lists);
  }
  return elementSource(node, [], indent, lists);
}

function withDirective(node: CNode, directive: string, indent: string, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "element") return elementSource(node, [directive], indent, lists);
  const inner = nodeSource(node, indent + "  ", lists);
  return `${indent}<template ${directive}>\n${inner}\n${indent}</template>`;
}

function elementSource(node: Extract<CNode, { kind: "element" }>, extraDirectives: string[], indent: string, lists: ReadonlyMap<string, ListPropDef>): string {
  const parts = [
    ...extraDirectives,
    ...node.attrs.map(attrSource),
    ...node.events.map((e) => `${VUE_EVENT_DIRECTIVE[e.name]}="${handlerSource(e.body)}"`),
  ];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";
  if (node.children.length === 0) return `${indent}<${node.tag}${attrText} />`;
  // Text-only children inline: Vue preserves surrounding whitespace, React
  // does not. See the Vue 3 emitter for the full explanation.
  if (node.children.every((c) => c.kind === "text")) {
    const inline = node.children.map((c) => nodeSource(c, "", lists).trim()).join("");
    return `${indent}<${node.tag}${attrText}>${inline}</${node.tag}>`;
  }
  const childSrc = node.children.map((c) => nodeSource(c, indent + "  ", lists)).join("\n");
  return `${indent}<${node.tag}${attrText}>\n${childSrc}\n${indent}</${node.tag}>`;
}

function propsBlock(props: PropDef[]): string {
  const dataProps = props.filter((p): p is Extract<PropDef, { kind: "data" }> => p.kind === "data");
  const listProps = props.filter((p): p is ListPropDef => p.kind === "list");
  if (dataProps.length === 0 && listProps.length === 0) return "";
  const listEntries = listProps.map((p) => `    ${p.name}: { type: Array, default: () => [] },`);
  const entries = dataProps.map((p) => {
    const bits = [`type: ${runtimeType(p)}`];
    if (p.defaultValue !== undefined) bits.push(`default: ${literalSource(p.defaultValue)}`);
    else if (p.required) bits.push("required: true");
    return `    ${p.name}: { ${bits.join(", ")} },`;
  });
  return `  props: {\n${[...entries, ...listEntries].join("\n")}\n  },`;
}

function dataBlock(state: StateDef[], lists: ReadonlyMap<string, ListPropDef>): string {
  const entries = [
    ...state.map((s) => `      ${s.name}: ${stateInitialSource(s)},`),
    ...[...lists.values()].filter((list) => list.staticItems !== undefined || list.staticValues !== undefined).map((list) => `      ${list.name}: ${staticListSource(list)},`),
  ];
  if (entries.length === 0) return "";
  return `  data() {\n    return {\n${entries.join("\n")}\n    };\n  },`;
}

export function emitVue2(component: ComponentDef): string {
  const template = nodeSource(component.root, "  ", listPropIndex(component));
  const scriptParts = [
    `  name: ${JSON.stringify(component.name)},`,
    propsBlock(component.props),
    dataBlock(component.state, listPropIndex(component)),
  ].filter((p) => p.length > 0);
  // Vue 2 has no auto-registration: a child must appear in `components`
  // or the tag renders as an unknown element with a runtime warning.
  const children = referencedComponents(component);
  const childImports = children.map((c) => `import ${c} from "./${c}.vue";`);
  if (children.length > 0) {
    scriptParts.unshift(`  components: { ${children.join(", ")} },`);
  }
  const script = [...childImports, childImports.length ? "" : null, `export default {`, ...scriptParts, `};`]
    .filter((l): l is string => l !== null).join("\n");
  return `<template>\n${template}\n</template>\n\n<script>\n${script}\n</script>\n`;
}

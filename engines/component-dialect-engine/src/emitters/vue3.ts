/**
 * Emits certified-component-v1 canonical model as a Vue 3 SFC using
 * `<script setup lang="ts">` + `<template>`.
 *
 * Hand-written, not derived from the React emitter: Vue spells state as
 * `ref()` (and reads it as `.value` in script but bare in template),
 * conditionals as `v-if`/`v-else` structural directives rather than a
 * ternary expression in the tree, dynamic attributes as `:attr`, and
 * events as `@click`. Sharing one emitter across these would be exactly
 * the "looks right, behaves wrong" failure mode this engine exists to
 * avoid.
 */
import { AttrBinding, ComponentDef, EventName, Expr, ListPropDef, Literal, Node as CNode, PropDef, StateDef, Stmt } from "../models";
import { dataPropTypeSource, listElementTypeSource, listKeyExpression, listPropIndex, listSourceExpression, referencedComponents, stateInitialSource, stateTypeSource, staticListSource } from "./react";

const VUE_EVENT_DIRECTIVE: Record<EventName, string> = {
  onClick: "@click", onChange: "@change", onInput: "@input", onSubmit: "@submit",
};

function literalSource(literal: Literal, inScript: boolean): string {
  if (literal.type === "string") {
    if (inScript) return JSON.stringify(literal.value);
    return `'${literal.value.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
  }
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

/** In `<template>`, `ref` state is auto-unwrapped, so identifiers are bare.
 * In `<script setup>`, the same state must be read/written as `x.value`.
 * `stateNames` selects which spelling this call site needs. */
function exprSource(expr: Expr, stateNames: ReadonlySet<string>, inScript: boolean): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e, stateNames, inScript);
    return e.kind === "binary" || e.kind === "ternary" || e.kind === "objectLiteral" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident":
      return inScript && stateNames.has(expr.name) ? `${expr.name}.value` : expr.name;
    // A loop variable is a template-local binding in both scopes, so it is
    // never `.value`-unwrapped and never prefixed.
    case "member":
      return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal":
      return literalSource(expr.literal, inScript);
    case "eventValue": return "$event.target.value";
    case "unaryNot":
      return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod":
      return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map((arg) => exprSource(arg, stateNames, inScript)).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map((arg) => exprSource(arg, stateNames, inScript)).join(", ")})`;
    case "numericPredicate": return `Number.${expr.predicate}(${exprSource(expr.operand, stateNames, inScript)})`;
    case "numberMethod": return `${wrap(expr.receiver)}.toFixed(${expr.fractionDigits})`;
    case "numberFormat": return `${wrap(expr.operand)}.toLocaleString(${JSON.stringify(expr.locale ?? "zh-CN")})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${exprSource(expr.operand, stateNames, inScript)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "percentageWidth": return `${exprSource(expr.value, stateNames, inScript)} + "%"`;
    case "styleObject": return `{ ${expr.fields.map((field) => `${field.name}: ${exprSource(field.value, stateNames, inScript)}`).join(", ")} }`;
    case "collectionFilter": return `${exprSource(expr.source, stateNames, inScript)}.filter((${expr.itemName}) => ${exprSource(expr.predicate, stateNames, inScript)})`;
    case "collectionMap": return `${exprSource(expr.source, stateNames, inScript)}.map((${expr.itemName}) => (${exprSource(expr.projection, stateNames, inScript)}))`;
    case "collectionReduce": return `${exprSource(expr.source, stateNames, inScript)}.reduce((${expr.accumulatorName}, ${expr.itemName}) => (${exprSource(expr.reducer, stateNames, inScript)}), ${exprSource(expr.initial, stateNames, inScript)})`;
    case "collectionMax": return `Math.max(...${exprSource(expr.source, stateNames, inScript)}.map((${expr.itemName}) => (${exprSource(expr.operand, stateNames, inScript)})))`;
    case "collectionJoin": return `${exprSource(expr.source, stateNames, inScript)}.join(${exprSource(expr.separator, stateNames, inScript)})`;
    case "objectLookup": return `${wrap(expr.object)}[${exprSource(expr.key, stateNames, inScript)}]`;
    case "objectLiteral": return `{ ${[...expr.fields.map((field) => `${field.name}: ${exprSource(field.value, stateNames, inScript)}`), ...(expr.computedFields ?? []).map((field) => `[${exprSource(field.key, stateNames, inScript)}]: ${exprSource(field.value, stateNames, inScript)}`)].join(", ")} }`;
    case "arrayLiteral": return `[${expr.items.map((item) => exprSource(item, stateNames, inScript)).join(", ")}]`;
    case "ternary":
      return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function tsType(t: "string" | "number" | "boolean"): string {
  return t;
}

/**
 * `inScript` matters for correctness, not style. Inside `<script setup>` a
 * ref must be read/written as `count.value`; inside `<template>` (including
 * inline `@click` handler expressions) Vue auto-unwraps it, so the same
 * write must be spelled `count = ...`.
 *
 * Emitting `count.value = ...` in a template is NOT a compile error --
 * `@vue/compiler-sfc` accepts it silently -- but at runtime it assigns
 * `.value` on an already-unwrapped primitive and the state never changes.
 * This is precisely the "compiles clean, behaves wrong" class of defect
 * that certified-component-v1's SSR execution-comparison leg exists to
 * catch, and it is why event handler bodies are rendered with
 * `inScript = false` here.
 */
function stmtSource(stmt: Stmt, stateNames: ReadonlySet<string>, inScript: boolean): string {
  if (stmt.kind === "setState") {
    const lhs = inScript ? `${stmt.target}.value` : stmt.target;
    return `${lhs} = ${exprSource(stmt.value, stateNames, inScript)}`;
  }
  const args = stmt.args.map((a) => exprSource(a, stateNames, inScript)).join(", ");
  return `emit(${JSON.stringify(eventNameForCallback(stmt.target))}${args ? ", " + args : ""})`;
}

/** Vue components receive callbacks as emitted events, not as function
 * props: React's `onDone` becomes `emit("done")` declared via
 * `defineEmits`. The name mapping must be reversible, so it is a pure
 * lowercase-first-letter transform of the part after `on`. */
export function eventNameForCallback(callbackName: string): string {
  const rest = callbackName.slice(2);
  return rest.charAt(0).toLowerCase() + rest.slice(1);
}

function attrSource(attr: AttrBinding, stateNames: ReadonlySet<string>): string {
  if (attr.kind === "static") return `${attr.name}=${JSON.stringify(attr.value)}`;
  return `:${attr.name}="${exprSource(attr.value, stateNames, false).replace(/"/g, "&quot;")}"`;
}

/** Rendered into a `@click="..."` template attribute, so template scoping
 * (auto-unwrapped refs) applies -- see stmtSource's note. */
function handlerSource(body: Stmt[], stateNames: ReadonlySet<string>): string {
  return body.map((s) => stmtSource(s, stateNames, false)).join("; ").replace(/"/g, "&quot;");
}

function nodeSource(node: CNode, stateNames: ReadonlySet<string>, indent: string, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "fragment") {
    const childSrc = node.children.map((child) => nodeSource(child, stateNames, indent + "  ", lists)).join("\n");
    return `${indent}<template>\n${childSrc}\n${indent}</template>`;
  }
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") {
      return `${indent}${node.value.literal.value}`;
    }
    return `${indent}{{ ${exprSource(node.value, stateNames, false)} }}`;
  }
  if (node.kind === "conditional") {
    const cond = exprSource(node.condition, stateNames, false).replace(/"/g, "&quot;");
    const thenSrc = withDirective(node.then, `v-if="${cond}"`, stateNames, indent, lists);
    if (node.else === null) return thenSrc;
    return `${thenSrc}\n${withDirective(node.else, "v-else", stateNames, indent, lists)}`;
  }
  if (node.kind === "component") {
    // Vue binds a child's props with `:name`, which is the same dynamic
    // binding syntax used for element attributes.
    const args = node.props.map((a) => `:${a.name}="${exprSource(a.value, stateNames, false).replace(/"/g, "&quot;")}"`);
    return `${indent}<${node.name}${args.length ? " " + args.join(" ") : ""} />`;
  }
  if (node.kind === "list") {
    // `v-for` is a structural directive placed ON the repeated element, so
    // it reuses the same plumbing as v-if rather than wrapping the body.
    const list = lists.get(node.source);
    const key = node.keyField !== undefined ? `${node.itemName}.${node.keyField}` : list ? listKeyExpression(list, node.itemName) : node.itemName;
    const source = node.sourceExpression === undefined ? listSourceExpression(list, node.source) : exprSource(node.sourceExpression, stateNames, false);
    return withDirective(node.body, `v-for="${node.itemName} in ${source}" :key="${key}"`, stateNames, indent, lists);
  }
  return elementSource(node, [], stateNames, indent, lists);
}

/** Vue conditionals are structural directives placed *on* an element, so a
 * conditional branch must be merged into its child element's tag rather
 * than wrapped -- if the branch is bare text it needs a `<template>`
 * carrier, which is what Vue itself uses for exactly this case. */
function withDirective(node: CNode, directive: string, stateNames: ReadonlySet<string>, indent: string, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "element") return elementSource(node, [directive], stateNames, indent, lists);
  const inner = nodeSource(node, stateNames, indent + "  ", lists);
  return `${indent}<template ${directive}>\n${inner}\n${indent}</template>`;
}

function elementSource(
  node: Extract<CNode, { kind: "element" }>,
  extraDirectives: string[],
  stateNames: ReadonlySet<string>,
  indent: string,
  lists: ReadonlyMap<string, ListPropDef>,
): string {
  const parts = [
    ...extraDirectives,
    ...node.attrs.map((a) => attrSource(a, stateNames)),
    ...node.events.map((e) => `${VUE_EVENT_DIRECTIVE[e.name]}="${handlerSource(e.body, stateNames)}"`),
  ];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";
  if (node.children.length === 0) return `${indent}<${node.tag}${attrText} />`;

  // Text-only children are rendered INLINE, with no surrounding newline or
  // indentation. This is a correctness requirement, not formatting taste:
  // Vue's template compiler preserves the whitespace between a tag and its
  // text content, so a pretty-printed `<strong>\n  small\n</strong>`
  // renders as `<strong> small </strong>` while the equivalent React JSX
  // renders `<strong>small</strong>`. The engine's SSR execution
  // comparison catches that divergence, and this is the fix.
  const textOnly = node.children.every((c) => c.kind === "text");
  if (textOnly) {
    const inline = node.children.map((c) => nodeSource(c, stateNames, "", lists).trim()).join("");
    return `${indent}<${node.tag}${attrText}>${inline}</${node.tag}>`;
  }

  const childSrc = node.children.map((c) => nodeSource(c, stateNames, indent + "  ", lists)).join("\n");
  return `${indent}<${node.tag}${attrText}>\n${childSrc}\n${indent}</${node.tag}>`;
}

function propsBlock(props: PropDef[]): string[] {
  const dataProps = props.filter((p): p is Extract<PropDef, { kind: "data" }> => p.kind === "data");
  const callbacks = props.filter((p): p is Extract<PropDef, { kind: "callback" }> => p.kind === "callback");
  const listProps = props.filter((p): p is ListPropDef => p.kind === "list");
  const lines: string[] = [];
  if (dataProps.length > 0 || listProps.length > 0) {
    const fields = [
      ...dataProps.map((p) => `  ${p.name}${p.required ? "" : "?"}: ${dataPropTypeSource(p, "unknown")};`),
      ...listProps.map((p) => `  ${p.name}: ${listElementTypeSource(p)}[];`),
    ];
    const withDefaults = dataProps.filter((p) => p.defaultValue !== undefined);
    const definition = `defineProps<{\n${fields.join("\n")}\n}>()`;
    if (withDefaults.length > 0) {
      const defaults = withDefaults.map((p) => `  ${p.name}: ${literalSource(p.defaultValue as Literal, true)},`);
      lines.push(`const props = withDefaults(${definition}, {\n${defaults.join("\n")}\n});`);
    } else {
      lines.push(`const props = ${definition};`);
    }
  }
  if (callbacks.length > 0) {
    const sigs = callbacks.map((c) => `  (e: ${JSON.stringify(eventNameForCallback(c.name))}${c.paramType ? `, value: ${tsType(c.paramType)}` : ""}): void;`);
    lines.push(`const emit = defineEmits<{\n${sigs.join("\n")}\n}>();`);
  }
  return lines;
}

function stateBlock(state: StateDef[]): string[] {
  return state.map((s) => `const ${s.name} = ref<${stateTypeSource(s)}${s.nullable && s.stateShape === undefined ? " | null" : ""}>(${stateInitialSource(s)});`);
}

export function emitVue3(component: ComponentDef): string {
  const stateNames = new Set(component.state.map((s) => s.name));
  const dataPropNames = component.props.filter((p) => p.kind === "data").map((p) => p.name);
  const scriptLines: string[] = [];
  if (component.state.length > 0) scriptLines.push(`import { ref } from "vue";`, "");
  for (const list of component.lists ?? []) {
    if (list.staticItems !== undefined || list.staticValues !== undefined) scriptLines.push(`const ${list.name} = ${staticListSource(list)};`);
  }
  scriptLines.push(...propsBlock(component.props));
  scriptLines.push(...stateBlock(component.state));
  // `defineProps` returns a reactive object; template auto-exposes prop names,
  // so nothing further is needed for the template side. Script-side reads of
  // props would need `props.x`, but certified-component-v1 handler bodies only
  // read state and pass values through, so no rewrite is required here --
  // any handler that reads a prop is rewritten below.
  const propRewrite = new Set(dataPropNames);

  const template = nodeSource(component.root, stateNames, "  ", listPropIndex(component));

  // `<script setup>` auto-registers anything in scope, so importing the
  // child is both the import AND the registration.
  const childImports = referencedComponents(component).map((c) => `import ${c} from "./${c}.vue";`);
  const script = [...childImports, ...scriptLines].join("\n");
  return `<script setup lang="ts">\n${script}\n</script>\n\n<template>\n${rewritePropReads(template, propRewrite)}\n</template>\n`;
}

/** Template expressions reference props by bare name (Vue exposes them
 * directly), so no rewriting is needed there; this is a no-op kept as an
 * explicit seam so the reason is documented rather than implicit. */
function rewritePropReads(template: string, _propNames: ReadonlySet<string>): string {
  return template;
}

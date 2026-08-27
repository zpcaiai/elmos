/**
 * Emits certified-component-v1 canonical model as a Svelte 5 component
 * using runes (`$props()`, `$state()`).
 *
 * Svelte's shape is genuinely different again:
 *  - There is no props type declaration; props are destructured from
 *    `$props()`, and defaults are plain destructuring defaults.
 *  - State is a `let` bound to `$state(...)` and assigned directly --
 *    Svelte's compiler makes the assignment reactive, so there is no
 *    setter and no `.value`.
 *  - Interpolation is `{expr}` (single braces), not `{{ }}`.
 *  - Conditionals are block syntax `{#if}...{:else}...{/if}`, not an
 *    attribute directive.
 *  - Callback props are just function props called directly.
 */
import { AttrBinding, ComponentDef, EventName, Expr, ListPropDef, Literal, Node as CNode, PropDef, Stmt, usesEventValueInStatements } from "../models";
import { dataPropTypeSource, listElementTypeSource, listKeyExpression, listPropIndex, listSourceExpression, referencedComponents, stateInitialSource, stateTypeSource, staticListSource } from "./react";

const SVELTE_EVENT: Record<EventName, string> = {
  onClick: "onclick", onChange: "onchange", onInput: "oninput", onSubmit: "onsubmit",
};

function tsType(t: "string" | "number" | "boolean"): string { return t; }

function literalSource(literal: Literal): string {
  if (literal.type === "string") return JSON.stringify(literal.value);
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

function exprSource(expr: Expr): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e);
    return e.kind === "binary" || e.kind === "ternary" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident": return expr.name;
    case "member": return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal": return literalSource(expr.literal);
    case "eventValue": return "event.target.value";
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map(exprSource).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map(exprSource).join(", ")})`;
    case "numericPredicate": return `Number.${expr.predicate}(${exprSource(expr.operand)})`;
    case "numberMethod": return `${wrap(expr.receiver)}.toFixed(${expr.fractionDigits})`;
    case "numberFormat": return `${wrap(expr.operand)}.toLocaleString(${JSON.stringify(expr.locale ?? "zh-CN")})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${exprSource(expr.operand)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "percentageWidth": return `${exprSource(expr.value)} + "%"`;
    case "styleObject": return `{ ${expr.fields.map((field) => `${field.name}: ${exprSource(field.value)}`).join(", ")} }`;
    case "collectionFilter": return `${exprSource(expr.source)}.filter((${expr.itemName}) => ${exprSource(expr.predicate)})`;
    case "collectionMap": return `${exprSource(expr.source)}.map((${expr.itemName}) => (${exprSource(expr.projection)}))`;
    case "collectionReduce": return `${exprSource(expr.source)}.reduce((${expr.accumulatorName}, ${expr.itemName}) => (${exprSource(expr.reducer)}), ${exprSource(expr.initial)})`;
    case "collectionMax": return `Math.max(...${exprSource(expr.source)}.map((${expr.itemName}) => (${exprSource(expr.operand)})))`;
    case "collectionJoin": return `${exprSource(expr.source)}.join(${exprSource(expr.separator)})`;
    case "objectLookup": return `${exprSource(expr.object)}[${exprSource(expr.key)}]`;
    case "objectLiteral": return `{ ${[...expr.fields.map((field) => `${field.name}: ${exprSource(field.value)}`), ...(expr.computedFields ?? []).map((field) => `[${exprSource(field.key)}]: ${exprSource(field.value)}`)].join(", ")} }`;
    case "arrayLiteral": return `[${expr.items.map(exprSource).join(", ")}]`;
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function stmtSource(stmt: Stmt): string {
  // Svelte state is assigned directly; the compiler makes it reactive.
  if (stmt.kind === "setState") return `${stmt.target} = ${exprSource(stmt.value)}`;
  return `${stmt.target}(${stmt.args.map(exprSource).join(", ")})`;
}

function handlerSource(body: Stmt[]): string {
  const parameter = usesEventValueInStatements(body) ? "event" : "";
  if (body.length === 1) return `${parameter ? `${parameter} =>` : "() =>"} ${stmtSource(body[0] as Stmt)}`;
  return `${parameter ? `${parameter} =>` : "() =>"} { ${body.map((s) => stmtSource(s) + ";").join(" ")} }`;
}

function attrSource(attr: AttrBinding): string {
  if (attr.kind === "static") return `${attr.name}=${JSON.stringify(attr.value)}`;
  return `${attr.name}={${exprSource(attr.value)}}`;
}

function nodeSource(node: CNode, indent: string, lists: ReadonlyMap<string, ListPropDef>): string {
  if (node.kind === "fragment") {
    return node.children.map((child) => nodeSource(child, indent, lists)).join("\n");
  }
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") return `${indent}${node.value.literal.value}`;
    return `${indent}{${exprSource(node.value)}}`;
  }
  if (node.kind === "conditional") {
    const lines = [`${indent}{#if ${exprSource(node.condition)}}`, nodeSource(node.then, indent + "  ", lists)];
    if (node.else !== null) {
      lines.push(`${indent}{:else}`);
      lines.push(nodeSource(node.else, indent + "  ", lists));
    }
    lines.push(`${indent}{/if}`);
    return lines.join("\n");
  }
  if (node.kind === "component") {
    const args = node.props.map((a) => `${a.name}={${exprSource(a.value)}}`);
    return `${indent}<${node.name}${args.length ? " " + args.join(" ") : ""} />`;
  }
  if (node.kind === "list") {
    // Svelte's keyed-each syntax puts the identity in parentheses after the
    // binding, which is why the key is not an attribute on the body here.
    const list = lists.get(node.source);
    const key = node.keyField !== undefined ? `${node.itemName}.${node.keyField}` : list ? listKeyExpression(list, node.itemName) : node.itemName;
    const source = node.sourceExpression === undefined ? listSourceExpression(list, node.source) : exprSource(node.sourceExpression);
    return [
      `${indent}{#each ${source} as ${node.itemName} (${key})}`,
      nodeSource(node.body, indent + "  ", lists),
      `${indent}{/each}`,
    ].join("\n");
  }
  const parts = [
    ...node.attrs.map(attrSource),
    ...node.events.map((e) => `${SVELTE_EVENT[e.name]}={${handlerSource(e.body)}}`),
  ];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";
  if (node.children.length === 0) return `${indent}<${node.tag}${attrText} />`;
  if (node.children.every((c) => c.kind === "text")) {
    const inline = node.children.map((c) => nodeSource(c, "", lists).trim()).join("");
    return `${indent}<${node.tag}${attrText}>${inline}</${node.tag}>`;
  }
  const childSrc = node.children.map((c) => nodeSource(c, indent + "  ", lists)).join("\n");
  return `${indent}<${node.tag}${attrText}>\n${childSrc}\n${indent}</${node.tag}>`;
}

function propsSource(props: PropDef[]): string[] {
  if (props.length === 0) return [];
  const names = props.map((p) => {
    if (p.kind === "data" && p.defaultValue !== undefined) return `${p.name} = ${literalSource(p.defaultValue)}`;
    return p.name;
  });
  const fields = props.map((p) => {
    if (p.kind === "callback") return `    ${p.name}: (${p.paramType ? `value: ${tsType(p.paramType)}` : ""}) => void;`;
    if (p.kind === "list") return `    ${p.name}: ${listElementTypeSource(p)}[];`;
    return `    ${p.name}${p.required ? "" : "?"}: ${dataPropTypeSource(p, "unknown")};`;
  });
  return [`  let { ${names.join(", ")} }: {`, ...fields, `  } = $props();`];
}

export function emitSvelte(component: ComponentDef): string {
  const lines: string[] = [`<script lang="ts">`];
  for (const child of referencedComponents(component)) {
    lines.push(`  import ${child} from "./${child}.svelte";`);
  }
  for (const list of component.lists ?? []) {
    if (list.staticItems !== undefined || list.staticValues !== undefined) lines.push(`  const ${list.name} = ${staticListSource(list)};`);
  }
  lines.push(...propsSource(component.props));
  for (const s of component.state) {
    lines.push(`  let ${s.name} = $state<${stateTypeSource(s)}${s.nullable && s.stateShape === undefined ? " | null" : ""}>(${stateInitialSource(s)});`);
  }
  lines.push(`</script>`);
  lines.push("");
  lines.push(nodeSource(component.root, "", listPropIndex(component)));
  return lines.join("\n") + "\n";
}

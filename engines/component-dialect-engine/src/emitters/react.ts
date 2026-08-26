/**
 * Emits certified-component-v1 canonical model as React (TSX) source.
 *
 * Hand-written per-framework renderer, deliberately NOT a generic
 * pretty-printer over some shared template: each framework spells state,
 * events, conditionals and attribute binding differently, and those
 * differences are exactly where a naive shared emitter produces code that
 * looks right and behaves wrong. Same reasoning as
 * `engines/sql-dialect-engine/src/elmos_sql_dialect/dialects.py`.
 */
import {
  AttrBinding, ComponentDef, DataPropDef, EventName, Expr, ListPropDef, Literal, Node as CNode, PropDef, Stmt, ValueShape, usesEventValueInStatements,
} from "../models";

/** The key expression for a list item: an object element uses its declared
 * key field, a primitive element is its own key. React, Vue, Svelte and the
 * WeChat mini program all need this; only the syntax differs. */
export function listKeyExpression(list: ListPropDef, itemName: string): string {
  return list.keyField !== undefined ? `${itemName}.${list.keyField}` : itemName;
}

/** Renders a list prop's TypeScript element type, e.g. `{ id: number;
 * name: string }` or `string`. */
export function listElementTypeSource(list: ListPropDef): string {
  if (list.element.kind === "primitive") return list.element.primitive;
  const fields = Object.entries(list.element.fields).map(([name, field]) => `${name}${field.optional ? "?" : ""}: ${valueShapeTypeSource(field.shape)}`);
  return `{ ${fields.join("; ")} }`;
}

/** Render a canonical structural prop for TypeScript-family targets. */
export function valueShapeTypeSource(shape: ValueShape | undefined, fallback: "string" | "number" | "boolean" = "string", slotType = "React.ReactNode"): string {
  if (shape === undefined) return fallback;
  let source: string;
  switch (shape.kind) {
    case "primitive": source = shape.primitive; break;
    case "slot": source = slotType; break;
    case "array": source = `Array<${valueShapeTypeSource(shape.element, "string", slotType)}>`; break;
    case "object": {
      const fields = Object.entries(shape.fields).map(([name, field]) => `${name}${field.optional ? "?" : ""}: ${valueShapeTypeSource(field.shape, "string", slotType)};`);
      source = `{ ${fields.join(" ")} }`;
      break;
    }
  }
  return shape.nullable ? `${source} | null` : source;
}

export function dataPropTypeSource(prop: DataPropDef, slotType = "React.ReactNode"): string {
  return valueShapeTypeSource(prop.valueShape, prop.propType, slotType);
}

const REACT_EVENT_ATTR: Record<EventName, string> = {
  onClick: "onClick", onChange: "onChange", onInput: "onInput", onSubmit: "onSubmit",
};

const REACT_ATTR_NAME: Record<string, string> = { class: "className", for: "htmlFor" };

export function literalSource(literal: Literal): string {
  if (literal.type === "string") return JSON.stringify(literal.value);
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

/** Renders an expression in plain JS/TS syntax. React, Vue, Svelte and the
 * WeChat mini program all accept this exact syntax inside their binding
 * delimiters, so it is shared; Flutter/ArkUI override where Dart/ArkTS
 * differ (see their emitters). */
export function exprSource(expr: Expr): string {
  switch (expr.kind) {
    case "ident": return expr.name;
    case "member": return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal": return literalSource(expr.literal);
    case "eventValue": return "event.target.value";
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": return `${wrap(expr.left)} ${expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator} ${wrap(expr.right)}`;
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map(exprSource).join(", ")})`;
    case "numericFunction": return `Math.${expr.function}(${expr.args.map(exprSource).join(", ")})`;
    case "numericPredicate": return `Number.${expr.predicate}(${exprSource(expr.operand)})`;
    case "cssModuleClass": return JSON.stringify(expr.className);
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${exprSource(expr.operand)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function wrap(expr: Expr): string {
  const src = exprSource(expr);
  return expr.kind === "binary" || expr.kind === "ternary" ? `(${src})` : src;
}

function tsType(t: "string" | "number" | "boolean"): string {
  return t;
}

function propsTypeSource(props: PropDef[]): string {
  if (props.length === 0) return "";
  const fields = props.map((p) => {
    if (p.kind === "callback") {
      const params = p.paramType ? `value: ${tsType(p.paramType)}` : "";
      return `  ${p.name}: (${params}) => void;`;
    }
    if (p.kind === "list") return `  ${p.name}: ${listElementTypeSource(p)}[];`;
    return `  ${p.name}${p.required ? "" : "?"}: ${dataPropTypeSource(p)};`;
  });
  return `{\n${fields.join("\n")}\n}`;
}

function destructureSource(props: PropDef[]): string {
  if (props.length === 0) return "";
  const names = props.map((p) => {
    if (p.kind === "data" && !p.required && p.defaultValue !== undefined) {
      return `${p.name} = ${literalSource(p.defaultValue)}`;
    }
    return p.name;
  });
  return `{ ${names.join(", ")} }: ${propsTypeSource(props)}`;
}

function setterName(state: string): string {
  return "set" + state[0]!.toUpperCase() + state.slice(1);
}

function stmtSource(stmt: Stmt): string {
  if (stmt.kind === "setState") return `${setterName(stmt.target)}(${exprSource(stmt.value)})`;
  return `${stmt.target}(${stmt.args.map(exprSource).join(", ")})`;
}

function handlerSource(body: Stmt[]): string {
  const parameter = usesEventValueInStatements(body) ? "event" : "";
  if (body.length === 1) return `${parameter ? `${parameter} =>` : "() =>"} ${stmtSource(body[0]!)}`;
  return `${parameter ? `${parameter} =>` : "() =>"} { ${body.map((s) => stmtSource(s) + ";").join(" ")} }`;
}

function attrSource(attr: AttrBinding): string {
  const name = REACT_ATTR_NAME[attr.name] ?? attr.name;
  if (attr.kind === "static") return `${name}=${JSON.stringify(attr.value)}`;
  return `${name}={${exprSource(attr.value)}}`;
}

function nodeSource(node: CNode, indent: string, lists: ReadonlyMap<string, ListPropDef>, keyAttr?: string): string {
  if (node.kind === "fragment") {
    const childSrc = node.children.map((child) => nodeSource(child, indent + "  ", lists)).join("\n");
    return `${indent}<>\n${childSrc}\n${indent}</>`;
  }
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") {
      return `${indent}${node.value.literal.value}`;
    }
    return `${indent}{${exprSource(node.value)}}`;
  }
  if (node.kind === "conditional") {
    const thenSrc = nodeSource(node.then, indent + "  ", lists);
    if (node.else === null) {
      return `${indent}{${wrap(node.condition)} ? (\n${thenSrc}\n${indent}) : null}`;
    }
    const elseSrc = nodeSource(node.else, indent + "  ", lists);
    return `${indent}{${wrap(node.condition)} ? (\n${thenSrc}\n${indent}) : (\n${elseSrc}\n${indent})}`;
  }
  if (node.kind === "component") {
    // JSX renders a child component with the very same syntax as an
    // element, distinguished only by the capital letter.
    const args = node.props.map((a) => `${a.name}={${exprSource(a.value)}}`);
    return `${indent}<${node.name}${args.length ? " " + args.join(" ") : ""} />`;
  }
  if (node.kind === "list") {
    // React's list identity is a `key` prop on the mapped element itself,
    // not a separate construct, so the key is threaded into the body's
    // attribute list rather than emitted as a wrapper.
    const list = lists.get(node.source);
    const key = node.keyField !== undefined ? `${node.itemName}.${node.keyField}` : list ? listKeyExpression(list, node.itemName) : node.itemName;
    const source = node.sourceExpression === undefined ? node.source : exprSource(node.sourceExpression);
    const bodySrc = nodeSource(node.body, indent + "  ", lists, key);
    return `${indent}{${source}.map((${node.itemName}) => (\n${bodySrc}\n${indent}))}`;
  }
  const parts = [
    ...(keyAttr !== undefined ? [`key={${keyAttr}}`] : []),
    ...node.attrs.map(attrSource),
    ...node.events.map((e) => `${REACT_EVENT_ATTR[e.name]}={${handlerSource(e.body)}}`),
  ];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";
  if (node.children.length === 0) return `${indent}<${node.tag}${attrText} />`;
  const childSrc = node.children.map((c) => nodeSource(c, indent + "  ", lists)).join("\n");
  return `${indent}<${node.tag}${attrText}>\n${childSrc}\n${indent}</${node.tag}>`;
}

/** Index the component's list props so a `list` node can look up its key
 * field while rendering. */
/**
 * Every child component referenced anywhere in the tree, deduplicated and
 * sorted.
 *
 * Shared by all emitters because the SET is target-independent even though
 * what each target does with it is not: an ES import for React/Vue/Svelte,
 * an `imports:` entry for standalone Angular, a `usingComponents` map entry
 * for WeChat, a Dart import for Flutter.
 *
 * The convention is that children are siblings in the same components
 * directory -- which is exactly the layout `runRepository` produces.
 */
export function referencedComponents(component: ComponentDef): string[] {
  const found = new Set<string>();
  const walk = (node: CNode): void => {
    if (node.kind === "component") { found.add(node.name); return; }
    if (node.kind === "fragment") { node.children.forEach(walk); return; }
    if (node.kind === "conditional") { walk(node.then); if (node.else) walk(node.else); return; }
    if (node.kind === "list") { walk(node.body); return; }
    if (node.kind === "element") node.children.forEach(walk);
  };
  walk(component.root);
  return [...found].sort();
}

export function listPropIndex(component: ComponentDef): Map<string, ListPropDef> {
  const index = new Map<string, ListPropDef>();
  for (const prop of component.props) if (prop.kind === "list") index.set(prop.name, prop);
  for (const list of component.lists ?? []) index.set(list.name, list);
  return index;
}

export function emitReact(component: ComponentDef): string {
  const lines: string[] = [];
  const usesState = component.state.length > 0;
  lines.push(usesState ? `import { useState } from "react";` : `import * as React from "react";`);
  // Children are siblings in the same components directory, which is the
  // layout runRepository produces. Without these imports the emitted file
  // parses fine and then fails to resolve at build time.
  for (const child of referencedComponents(component)) {
    lines.push(`import ${child} from "./${child}";`);
  }
  lines.push("");
  lines.push(`export default function ${component.name}(${destructureSource(component.props)}) {`);
  for (const s of component.state) {
    lines.push(`  const [${s.name}, ${setterName(s.name)}] = useState<${tsType(s.stateType)}${s.nullable ? " | null" : ""}>(${literalSource(s.initial)});`);
  }
  if (usesState) lines.push("");
  lines.push("  return (");
  if (component.root.kind === "conditional") {
    const lists = listPropIndex(component);
    const thenSrc = nodeSource(component.root.then, "      ", lists);
    const elseSrc = component.root.else === null
      ? "null"
      : ["(", nodeSource(component.root.else, "      ", lists), "    )"].join("\n");
    lines.push(`    ${wrap(component.root.condition)} ? (\n${thenSrc}\n    ) : ${elseSrc}`);
  } else {
    lines.push(nodeSource(component.root, "    ", listPropIndex(component)));
  }
  lines.push("  );");
  lines.push("}");
  return lines.join("\n") + "\n";
}

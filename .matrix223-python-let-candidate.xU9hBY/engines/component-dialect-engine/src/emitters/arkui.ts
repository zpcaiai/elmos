/**
 * Emits certified-component-v1 canonical model as HarmonyOS ArkUI (ArkTS).
 *
 * TARGET-ONLY. ArkTS's `struct` declaration form is not valid TypeScript
 * and has no published standalone parser, so this engine cannot read ArkUI
 * source back in, and there is no ArkTS compiler installed here to confirm
 * the emitted file. `validator.ts` reports that honestly rather than
 * implying a real toolchain accepted it -- the same call
 * `engines/sql-dialect-engine` makes for Oracle/SQL Server execution
 * validation.
 *
 * Structural notes that make this a real emitter rather than a rename:
 *  - ArkUI has no HTML elements; the built-in set is Column/Row/Text/
 *    Button/TextInput, and layout containers take a trailing builder block.
 *  - State is declared with the `@State` decorator; props with `@Prop`.
 *  - Text content is an argument to `Text(...)`, not a child node.
 *  - Conditionals are real `if/else` statements inside `build()`.
 *  - There are no callback props in the web sense; a parent passes a
 *    function-typed field, which is what is emitted here.
 */
import { ComponentDef, Expr, HtmlTag, ListPropDef, Literal, Node as CNode, PropDef, Stmt } from "../models";
import { listKeyExpression, listPropIndex, referencedComponents } from "./react";

/** HTML tag -> ArkUI built-in component. Block-level tags become layout
 * containers, text-level tags become Text. */
// Block containers become a Column. The semantic HTML5 landmarks carry no
// ArkUI equivalent, so they lay out like a div -- which is honest, and is
// why they were admitted to the subset while `table` and `form` were not.
const CONTAINER_TAGS: ReadonlySet<HtmlTag> = new Set<HtmlTag>([
  "div", "ul", "ol", "p",
  "section", "article", "header", "footer", "nav", "main", "aside",
]);

const TEXT_STYLE: Partial<Record<HtmlTag, string>> = {
  h1: ".fontSize(32).fontWeight(FontWeight.Bold)",
  h2: ".fontSize(28).fontWeight(FontWeight.Bold)",
  h3: ".fontSize(24).fontWeight(FontWeight.Bold)",
  h4: ".fontSize(20).fontWeight(FontWeight.Bold)",
  h5: ".fontSize(18).fontWeight(FontWeight.Bold)",
  h6: ".fontSize(16).fontWeight(FontWeight.Bold)",
  strong: ".fontWeight(FontWeight.Bold)",
  small: ".fontSize(12)",
  code: ".fontFamily('monospace')",
  em: ".fontStyle(FontStyle.Italic)",
};

function literalSource(literal: Literal): string {
  if (literal.type === "string") return `'${literal.value.replace(/'/g, "\\'")}'`;
  if (literal.type === "number") return String(literal.value);
  return literal.value ? "true" : "false";
}

function exprSource(expr: Expr): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e);
    return e.kind === "binary" || e.kind === "ternary" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident": return `this.${expr.name}`;
    // ForEach binds the item as a lambda parameter, not a struct field.
    case "member": return `${expr.object}.${expr.field}`;
    case "literal": return literalSource(expr.literal);
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

/** ArkUI's `@State` is assigned directly (the framework tracks it), so
 * there is no async-setter hazard here and React's closure semantics are
 * preserved by snapshotting reads exactly as the mini program emitter does
 * -- assignment is synchronous, so a later read would otherwise see the
 * new value where React would see the old one. */
function handlerBody(body: Stmt[], indent: string): string[] {
  const writes = new Set(body.filter((s) => s.kind === "setState").map((s) => (s as Extract<Stmt, { kind: "setState" }>).target));
  const reads = new Set<string>();
  const collect = (e: Expr): void => {
    if (e.kind === "ident") reads.add(e.name);
    else if (e.kind === "binary") { collect(e.left); collect(e.right); }
    else if (e.kind === "unaryNot") collect(e.operand);
    else if (e.kind === "ternary") { collect(e.condition); collect(e.then); collect(e.else); }
  };
  for (const stmt of body) {
    if (stmt.kind === "setState") collect(stmt.value);
    else stmt.args.forEach(collect);
  }
  const snapshot = new Set([...reads].filter((n) => writes.has(n)));
  const rewrite = (e: Expr): string => {
    if (e.kind === "ident" && snapshot.has(e.name)) return `${e.name}$0`;
    if (e.kind === "binary") return `(${rewrite(e.left)} ${e.operator === "==" ? "===" : e.operator === "!=" ? "!==" : e.operator} ${rewrite(e.right)})`;
    if (e.kind === "unaryNot") return `!${rewrite(e.operand)}`;
    if (e.kind === "ternary") return `(${rewrite(e.condition)} ? ${rewrite(e.then)} : ${rewrite(e.else)})`;
    return exprSource(e);
  };
  const lines = [...snapshot].map((n) => `${indent}const ${n}$0 = this.${n};`);
  for (const stmt of body) {
    if (stmt.kind === "setState") lines.push(`${indent}this.${stmt.target} = ${rewrite(stmt.value)};`);
    else lines.push(`${indent}this.${stmt.target}(${stmt.args.map(rewrite).join(", ")});`);
  }
  return lines;
}

function textArgument(children: CNode[]): string {
  const parts = children.map((c) => {
    if (c.kind !== "text") return null;
    if (c.value.kind === "literal" && c.value.literal.type === "string") return `'${c.value.literal.value.replace(/'/g, "\\'")}'`;
    return `\${${exprSource(c.value)}}`;
  });
  if (parts.some((p) => p === null)) return "''";
  if (parts.length === 1 && !parts[0]!.startsWith("${")) return parts[0]!;
  const template = parts.map((p) => (p!.startsWith("${") ? p : p!.slice(1, -1))).join("");
  return `\`${template}\``;
}

function nodeSource(node: CNode, indent: string, lists: ReadonlyMap<string, ListPropDef>): string[] {
  if (node.kind === "text") {
    return [`${indent}Text(${textArgument([node])})`];
  }
  if (node.kind === "conditional") {
    const lines = [`${indent}if (${exprSource(node.condition)}) {`];
    lines.push(...nodeSource(node.then, indent + "  ", lists));
    if (node.else) {
      lines.push(`${indent}} else {`);
      lines.push(...nodeSource(node.else, indent + "  ", lists));
    }
    lines.push(`${indent}}`);
    return lines;
  }
  if (node.kind === "component") {
    // ArkUI instantiates a child @Component as a CALL with a named
    // initializer object -- there is no JSX-like element syntax.
    const args = node.props.map((a) => `${a.name}: ${exprSource(a.value)}`);
    return [`${indent}${node.name}({ ${args.join(", ")} })`];
  }
  if (node.kind === "list") {
    // ArkUI takes an explicit key generator as ForEach's third argument;
    // it must return a string, so a numeric id is stringified.
    const list = lists.get(node.source);
    const elementType = list && list.element.kind === "object" ? "Object" : "string | number | boolean";
    const key = list ? listKeyExpression(list, node.itemName) : node.itemName;
    const lines = [`${indent}ForEach(this.${node.source}, (${node.itemName}: ${elementType}) => {`];
    lines.push(...nodeSource(node.body, indent + "  ", lists));
    lines.push(`${indent}}, (${node.itemName}: ${elementType}) => String(${key}))`);
    return lines;
  }

  const events = node.events;
  const onClick = events.find((e) => e.name === "onClick");
  const onChange = events.find((e) => e.name === "onChange" || e.name === "onInput");

  if (node.tag === "button") {
    const lines = [`${indent}Button(${textArgument(node.children)})`];
    if (onClick) {
      lines.push(`${indent}  .onClick(() => {`);
      lines.push(...handlerBody(onClick.body, indent + "    "));
      lines.push(`${indent}  })`);
    }
    return lines;
  }
  if (node.tag === "input") {
    const placeholder = node.attrs.find((a) => a.name === "placeholder");
    const arg = placeholder && placeholder.kind === "static" ? `{ placeholder: '${placeholder.value}' }` : "";
    const lines = [`${indent}TextInput(${arg})`];
    if (onChange) {
      lines.push(`${indent}  .onChange((value: string) => {`);
      lines.push(...handlerBody(onChange.body, indent + "    "));
      lines.push(`${indent}  })`);
    }
    return lines;
  }

  const textOnly = node.children.length > 0 && node.children.every((c) => c.kind === "text");
  if (!CONTAINER_TAGS.has(node.tag) && textOnly) {
    const style = TEXT_STYLE[node.tag] ?? "";
    return [`${indent}Text(${textArgument(node.children)})${style}`];
  }

  const container = node.tag === "ul" || node.tag === "div" || node.tag === "p" ? "Column" : "Column";
  const lines = [`${indent}${container}() {`];
  for (const child of node.children) lines.push(...nodeSource(child, indent + "  ", lists));
  lines.push(`${indent}}`);
  return lines;
}

function arkType(t: "string" | "number" | "boolean"): string {
  return t;
}

export function emitArkUI(component: ComponentDef): string {
  const lines: string[] = [];
  lines.push(`// Generated by ELMOS component-dialect-engine (certified-component-v1).`);
  lines.push(`// NOTE: no ArkTS compiler was available to verify this file; see README.`);
  lines.push(`@Component`);
  lines.push(`export struct ${component.name} {`);

  for (const prop of component.props) {
    if (prop.kind === "callback") {
      const param = prop.paramType ? `value: ${arkType(prop.paramType)}` : "";
      lines.push(`  ${prop.name}: (${param}) => void = () => {};`);
    } else if (prop.kind === "list") {
      const elementType = prop.element.kind === "object" ? "Object" : arkType(prop.element.primitive);
      lines.push(`  @Prop ${prop.name}: Array<${elementType}> = [];`);
    } else if (prop.defaultValue !== undefined) {
      lines.push(`  @Prop ${prop.name}: ${arkType(prop.propType)} = ${literalSource(prop.defaultValue)};`);
    } else {
      const fallback: Record<string, string> = { string: "''", number: "0", boolean: "false" };
      lines.push(`  @Prop ${prop.name}: ${arkType(prop.propType)} = ${fallback[prop.propType]};`);
    }
  }
  for (const s of component.state) {
    lines.push(`  @State ${s.name}: ${arkType(s.stateType)} = ${literalSource(s.initial)};`);
  }

  lines.push("");
  lines.push(`  build() {`);
  lines.push(...nodeSource(component.root, "    ", listPropIndex(component)));
  lines.push(`  }`);
  lines.push(`}`);
  return lines.join("\n") + "\n";
}

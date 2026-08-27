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
import { listPropIndex, listSourceExpression, referencedComponents, staticListSource } from "./react";

/** HTML tag -> ArkUI built-in component. Block-level tags become layout
 * containers, text-level tags become Text. */
// Block containers become a Column. The semantic HTML5 landmarks carry no
// ArkUI equivalent, so they lay out like a div -- which is honest, and is
// why they were admitted to the subset while `table` and `form` were not.
const CONTAINER_TAGS: ReadonlySet<HtmlTag> = new Set<HtmlTag>([
  "div", "ul", "ol", "p",
  "section", "article", "header", "footer", "nav", "main", "aside", "dl",
]);

const TEXT_STYLE: Partial<Record<HtmlTag, string>> = {
  h1: ".fontSize(32).fontWeight(FontWeight.Bold)",
  h2: ".fontSize(28).fontWeight(FontWeight.Bold)",
  h3: ".fontSize(24).fontWeight(FontWeight.Bold)",
  h4: ".fontSize(20).fontWeight(FontWeight.Bold)",
  h5: ".fontSize(18).fontWeight(FontWeight.Bold)",
  h6: ".fontSize(16).fontWeight(FontWeight.Bold)",
  strong: ".fontWeight(FontWeight.Bold)",
  b: ".fontWeight(FontWeight.Bold)",
  small: ".fontSize(12)",
  code: ".fontFamily('monospace')",
  em: ".fontStyle(FontStyle.Italic)",
  dt: ".fontWeight(FontWeight.Bold)",
};

function literalSource(literal: Literal): string {
  if (literal.type === "string") return `'${literal.value.replace(/'/g, "\\'")}'`;
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
    case "ident": return `this.${expr.name}`;
    // ForEach binds the item as a lambda parameter, not a struct field.
    case "member": return `${expr.object}.${expr.field}`;
    // Object-valued list fields are emitted as bounded Record values. ArkTS
    // does not guarantee a dot-property on a Record, so nested accesses use
    // explicit key indexing rather than producing a visually plausible but
    // type-invalid `item.build_analysis.total` expression.
    case "path": return expr.fields.reduce((source, field) => `${source}[${JSON.stringify(field)}]`, expr.object);
    case "literal": return literalSource(expr.literal);
    case "eventValue": return "value";
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
    case "objectLiteral": return `{ ${[...expr.fields.map((field) => `${JSON.stringify(field.name)}: ${exprSource(field.value)}`), ...(expr.computedFields ?? []).map((field) => `[${exprSource(field.key)}]: ${exprSource(field.value)}`)].join(", ")} }`;
    case "arrayLiteral": return `[${expr.items.map(exprSource).join(", ")}]`;
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
    else if (e.kind === "stringMethod") { collect(e.receiver); e.args.forEach(collect); }
    else if (e.kind === "numericFunction") e.args.forEach(collect);
    else if (e.kind === "numericPredicate") collect(e.operand);
    else if (e.kind === "numberMethod") collect(e.receiver);
    else if (e.kind === "numberFormat") collect(e.operand);
    else if (e.kind === "regexTest") collect(e.operand);
    else if (e.kind === "arrayLength") collect(e.operand);
    else if (e.kind === "percentageWidth") collect(e.value);
    else if (e.kind === "styleObject") e.fields.forEach((field) => collect(field.value));
   else if (e.kind === "collectionFilter") { collect(e.source); collect(e.predicate); }
    else if (e.kind === "collectionMap") { collect(e.source); collect(e.projection); }
    else if (e.kind === "collectionReduce") { collect(e.source); collect(e.reducer); collect(e.initial); }
    else if (e.kind === "collectionMax") { collect(e.source); collect(e.operand); }
    else if (e.kind === "collectionJoin") { collect(e.source); collect(e.separator); }
    else if (e.kind === "objectLookup") { collect(e.object); collect(e.key); }
   else if (e.kind === "objectLiteral") { e.fields.forEach((field) => collect(field.value)); (e.computedFields ?? []).forEach((field) => { collect(field.key); collect(field.value); }); }
    else if (e.kind === "arrayLiteral") e.items.forEach(collect);
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
    if (e.kind === "stringMethod") return `${rewrite(e.receiver)}.${e.method}(${e.args.map(rewrite).join(", ")})`;
    if (e.kind === "numericFunction") return `Math.${e.function}(${e.args.map(rewrite).join(", ")})`;
    if (e.kind === "numericPredicate") return `Number.${e.predicate}(${rewrite(e.operand)})`;
    if (e.kind === "numberMethod") return `${rewrite(e.receiver)}.toFixed(${e.fractionDigits})`;
    if (e.kind === "numberFormat") return `${rewrite(e.operand)}.toLocaleString(${JSON.stringify(e.locale ?? "zh-CN")})`;
    if (e.kind === "cssModuleClass") return JSON.stringify(e.className);
    if (e.kind === "regexTest") return `/${e.pattern}/${e.flags}.test(${rewrite(e.operand)})`;
    if (e.kind === "arrayLength") return `${rewrite(e.operand)}.length`;
    if (e.kind === "percentageWidth") return `${rewrite(e.value)} + "%"`;
    if (e.kind === "styleObject") return `{ ${e.fields.map((field) => `${field.name}: ${rewrite(field.value)}`).join(", ")} }`;
   if (e.kind === "collectionFilter") return `${rewrite(e.source)}.filter((${e.itemName}) => ${rewrite(e.predicate)})`;
    if (e.kind === "collectionMap") return `${rewrite(e.source)}.map((${e.itemName}) => (${rewrite(e.projection)}))`;
    if (e.kind === "collectionReduce") return `${rewrite(e.source)}.reduce((${e.accumulatorName}, ${e.itemName}) => (${rewrite(e.reducer)}), ${rewrite(e.initial)})`;
    if (e.kind === "collectionMax") return `Math.max(...${rewrite(e.source)}.map((${e.itemName}) => (${rewrite(e.operand)})))`;
   if (e.kind === "objectLiteral") return `{ ${e.fields.map((field) => `${JSON.stringify(field.name)}: ${rewrite(field.value)}`).join(", ")} }`;
    if (e.kind === "arrayLiteral") return `[${e.items.map(rewrite).join(", ")}]`;
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
  if (node.kind === "fragment") {
    return node.children.flatMap((child) => nodeSource(child, indent, lists));
  }
  if (node.kind === "text") {
    return [`${indent}Text(${textArgument([node])})`];
  }
  if (node.kind === "element" && node.tag === "br") return [`${indent}Text('\\n')`];
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
    const elementType = list && list.element.kind === "object" ? "Record<string, Object>" : "string | number | boolean";
    const key = node.keyField !== undefined
      ? `${node.itemName}[${JSON.stringify(node.keyField)}]`
      : list?.keyField !== undefined
        ? `${node.itemName}[${JSON.stringify(list.keyField)}]`
        : node.itemName;
    const source = node.sourceExpression === undefined ? (lists.get(node.source)?.staticItems === undefined && lists.get(node.source)?.staticValues === undefined ? `this.${node.source}` : staticListSource(lists.get(node.source)!)) : exprSource(node.sourceExpression);
    const lines = [`${indent}ForEach(${source}, (${node.itemName}: ${elementType}) => {`];
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
      const elementType = prop.element.kind === "object" ? "Record<string, Object>" : arkType(prop.element.primitive);
      lines.push(`  @Prop ${prop.name}: Array<${elementType}> = [];`);
    } else if (prop.defaultValue !== undefined) {
      lines.push(`  @Prop ${prop.name}: ${arkType(prop.propType)} = ${literalSource(prop.defaultValue)};`);
    } else {
      const fallback: Record<string, string> = { string: "''", number: "0", boolean: "false" };
      lines.push(`  @Prop ${prop.name}: ${arkType(prop.propType)} = ${fallback[prop.propType]};`);
    }
  }
  for (const s of component.state) {
    const stateType = s.stateShape === undefined
      ? arkType(s.stateType)
      : s.stateShape.kind === "array"
        ? `Array<${s.stateShape.element.kind === "primitive" ? arkType(s.stateShape.element.primitive) : "Record<string, Object>"}>`
        : "Record<string, Object>";
    const initial = "kind" in s.initial ? exprSource(s.initial) : literalSource(s.initial);
    lines.push(`  @State ${s.name}: ${stateType}${s.nullable && s.stateShape === undefined ? " | null" : ""} = ${initial};`);
  }

  lines.push("");
  lines.push(`  build() {`);
  lines.push(...nodeSource(component.root, "    ", listPropIndex(component)));
  lines.push(`  }`);
  lines.push(`}`);
  return lines.join("\n") + "\n";
}

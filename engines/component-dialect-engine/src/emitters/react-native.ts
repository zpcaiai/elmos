/**
 * Emits certified-component-v1 canonical model as a React Native component.
 *
 * Shares the JSX shape with the web React emitter but NOT the element or
 * attribute vocabulary, which is the whole point of having a separate
 * emitter: React Native has no DOM. `<div>` does not exist, text may only
 * appear inside `<Text>`, `className` is meaningless (styles are objects),
 * and press handling is `onPress`, not `onClick`. Passing web JSX to a
 * React Native runtime throws "Unimplemented component" at runtime rather
 * than failing at build time, so a shared emitter would produce code that
 * type-checks and then crashes on device.
 */
import { AttrBinding, ComponentDef, EventName, Expr, HtmlTag, ListPropDef, Literal, Node as CNode, PropDef, Stmt, usesEventValueInStatements } from "../models";
import { dataPropTypeSource, listElementTypeSource, listKeyExpression, listPropIndex, referencedComponents } from "./react";

/** HTML tag -> React Native core component. Text-bearing tags all become
 * `<Text>` because React Native throws if a raw string is rendered outside
 * one. */
const TAG_MAP: Record<HtmlTag, string> = {
  div: "View", p: "Text", span: "Text", strong: "Text", em: "Text", i: "Text",
  h1: "Text", h2: "Text", h3: "Text", h4: "Text", h5: "Text", h6: "Text",
  ul: "View", ol: "View", li: "Text", label: "Text", a: "Text",
  button: "Pressable", input: "TextInput",
  // Semantic containers are block-level boxes, exactly like `div`. React
  // Native has no landmark roles, so the semantic meaning is genuinely
  // lost -- the layout is not.
  section: "View", article: "View", header: "View", footer: "View",
  nav: "View", main: "View", aside: "View", dl: "View", dt: "Text", dd: "Text",
  small: "Text", code: "Text",
};

/** RN has no CSS cascade, so the semantic weight of these tags is carried
 * by a generated StyleSheet entry instead of being silently dropped. */
const SEMANTIC_STYLE: Partial<Record<HtmlTag, string>> = {
  h1: "h1", h2: "h2", h3: "h3", h4: "h4", h5: "h5", h6: "h6",
  strong: "strong", em: "em", p: "p", li: "li", a: "a",
  small: "small", code: "code", dt: "strong", dd: "dd",
};

const EVENT_PROP: Record<EventName, string> = {
  onClick: "onPress", onChange: "onChangeText", onInput: "onChangeText", onSubmit: "onSubmitEditing",
};

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
    case "eventValue": return "event";
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map(exprSource).join(", ")})`;
    case "regexTest": return `/${expr.pattern}/${expr.flags}.test(${exprSource(expr.operand)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
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

/** Web attributes that have a real React Native equivalent. Everything
 * else is dropped only when it provably has no on-device meaning, and is
 * recorded in the returned notes so the caller can see it happened. */
function attrSource(attr: AttrBinding, tag: HtmlTag, styles: string[], notes: string[]): string | null {
  if (attr.name === "class") {
    if (attr.kind === "static") { styles.push(...attr.value.split(/\s+/).filter(Boolean)); return null; }
    notes.push(`dynamic class on <${tag}> has no React Native equivalent and was dropped`);
    return null;
  }
  if (attr.name === "disabled") {
    const value = attr.kind === "static" ? "{true}" : `{${exprSource(attr.value)}}`;
    return tag === "button" ? `disabled=${value}` : `editable={!(${attr.kind === "static" ? "true" : exprSource(attr.value)})}`;
  }
  if (attr.name === "placeholder" || attr.name === "value" || attr.name === "maxLength") {
    return attr.kind === "static" ? `${attr.name}=${JSON.stringify(attr.value)}` : `${attr.name}={${exprSource(attr.value)}}`;
  }
  if (attr.name === "id") {
    return attr.kind === "static" ? `testID=${JSON.stringify(attr.value)}` : `testID={${exprSource(attr.value)}}`;
  }
  notes.push(`attribute ${attr.name} on <${tag}> has no React Native equivalent and was dropped`);
  return null;
}

function nodeSource(node: CNode, indent: string, usedStyles: Set<string>, notes: string[], lists: ReadonlyMap<string, ListPropDef>, keyAttr?: string): string {
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") return `${indent}${node.value.literal.value}`;
    return `${indent}{${exprSource(node.value)}}`;
  }
  if (node.kind === "conditional") {
    const thenSrc = nodeSource(node.then, indent + "  ", usedStyles, notes, lists);
    if (node.else === null) return `${indent}{(${exprSource(node.condition)}) ? (\n${thenSrc}\n${indent}) : null}`;
    const elseSrc = nodeSource(node.else, indent + "  ", usedStyles, notes, lists);
    return `${indent}{(${exprSource(node.condition)}) ? (\n${thenSrc}\n${indent}) : (\n${elseSrc}\n${indent})}`;
  }
  if (node.kind === "component") {
    // Identical to web React -- the divergence between RN and React is in
    // the ELEMENT vocabulary, not in how a child component is rendered.
    const args = node.props.map((a) => `${a.name}={${exprSource(a.value)}}`);
    return `${indent}<${node.name}${args.length ? " " + args.join(" ") : ""} />`;
  }
  if (node.kind === "list") {
    const list = lists.get(node.source);
    const key = node.keyField !== undefined ? `${node.itemName}.${node.keyField}` : list ? listKeyExpression(list, node.itemName) : node.itemName;
    const source = node.sourceExpression === undefined ? node.source : exprSource(node.sourceExpression);
    const bodySrc = nodeSource(node.body, indent + "  ", usedStyles, notes, lists, key);
    return `${indent}{${source}.map((${node.itemName}) => (\n${bodySrc}\n${indent}))}`;
  }

  const tag = TAG_MAP[node.tag];
  const styleClasses: string[] = [];
  const semantic = SEMANTIC_STYLE[node.tag];
  if (semantic) styleClasses.push(semantic);

  const attrParts: string[] = [];
  for (const attr of node.attrs) {
    const rendered = attrSource(attr, node.tag, styleClasses, notes);
    if (rendered !== null) attrParts.push(rendered);
  }
  for (const cls of styleClasses) usedStyles.add(cls);
  if (styleClasses.length > 0) {
    const refs = styleClasses.map((c) => /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(c) ? `styles.${c}` : `styles[${JSON.stringify(c)}]`).join(", ");
    attrParts.unshift(styleClasses.length === 1 ? `style={${refs}}` : `style={[${refs}]}`);
  }

  const eventParts = node.events.map((e) => `${EVENT_PROP[e.name]}={${handlerSource(e.body)}}`);
  const parts = [...(keyAttr !== undefined ? [`key={${keyAttr}}`] : []), ...attrParts, ...eventParts];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";

  if (node.children.length === 0) return `${indent}<${tag}${attrText} />`;
  const textOnly = node.children.every((c) => c.kind === "text");
  if (textOnly) {
    const inline = node.children.map((c) => nodeSource(c, "", usedStyles, notes, lists).trim()).join("");
    // React Native throws "Text strings must be rendered within a <Text>
    // component" at runtime -- not at build time -- when a raw string sits
    // inside any non-Text component. `<Pressable>add</Pressable>` compiles
    // and type-checks perfectly and then crashes on device, so text under a
    // non-Text container is wrapped here.
    if (tag !== "Text") {
      return `${indent}<${tag}${attrText}><Text>${inline}</Text></${tag}>`;
    }
    return `${indent}<${tag}${attrText}>${inline}</${tag}>`;
  }
  const childSrc = node.children.map((c) => nodeSource(c, indent + "  ", usedStyles, notes, lists)).join("\n");
  return `${indent}<${tag}${attrText}>\n${childSrc}\n${indent}</${tag}>`;
}

const STYLE_RULES: Record<string, string> = {
  h1: "{ fontSize: 32, fontWeight: \"bold\" }",
  h2: "{ fontSize: 28, fontWeight: \"bold\" }",
  h3: "{ fontSize: 24, fontWeight: \"bold\" }",
  h4: "{ fontSize: 20, fontWeight: \"bold\" }",
  h5: "{ fontSize: 18, fontWeight: \"bold\" }",
  h6: "{ fontSize: 16, fontWeight: \"bold\" }",
  strong: "{ fontWeight: \"bold\" }",
  em: "{ fontStyle: \"italic\" }",
  p: "{ marginVertical: 4 }",
  li: "{ marginVertical: 2 }",
  a: "{ color: \"#0645AD\", textDecorationLine: \"underline\" }",
};

function tsType(t: "string" | "number" | "boolean"): string { return t; }

function destructureSource(props: PropDef[]): string {
  if (props.length === 0) return "";
  const names = props.map((p) => (p.kind === "data" && !p.required && p.defaultValue !== undefined ? `${p.name} = ${literalSource(p.defaultValue)}` : p.name));
  const fields = props.map((p) => {
    if (p.kind === "callback") return `  ${p.name}: (${p.paramType ? `value: ${tsType(p.paramType)}` : ""}) => void;`;
    if (p.kind === "list") return `  ${p.name}: ${listElementTypeSource(p)}[];`;
    return `  ${p.name}${p.required ? "" : "?"}: ${dataPropTypeSource(p)};`;
  });
  return `{ ${names.join(", ")} }: {\n${fields.join("\n")}\n}`;
}

export interface ReactNativeEmission {
  source: string;
  /** Web-only constructs with no on-device equivalent that were dropped.
   * Surfaced rather than silently discarded. */
  notes: string[];
}

export function emitReactNative(component: ComponentDef): ReactNativeEmission {
  const usedStyles = new Set<string>();
  const notes: string[] = [];
  const tree = nodeSource(component.root, "    ", usedStyles, notes, listPropIndex(component));

  const components = new Set<string>();
  const walk = (n: CNode): void => {
    if (n.kind === "element") {
      components.add(TAG_MAP[n.tag]);
      // Text-only children of a non-Text container get a <Text> wrapper
      // (see nodeSource), so Text must be imported for those too.
      if (n.children.length > 0 && n.children.every((c) => c.kind === "text")) components.add("Text");
      n.children.forEach(walk);
    } else if (n.kind === "conditional") { walk(n.then); if (n.else) walk(n.else); }
  };
  walk(component.root);
  components.add("StyleSheet");

  const lines: string[] = [];
  lines.push(component.state.length > 0 ? `import { useState } from "react";` : `import * as React from "react";`);
  lines.push(`import { ${[...components].sort().join(", ")} } from "react-native";`);
  for (const child of referencedComponents(component)) {
    lines.push(`import ${child} from "./${child}";`);
  }
  lines.push("");
  lines.push(`export default function ${component.name}(${destructureSource(component.props)}) {`);
  for (const s of component.state) {
    lines.push(`  const [${s.name}, ${setterName(s.name)}] = useState<${tsType(s.stateType)}${s.nullable ? " | null" : ""}>(${literalSource(s.initial)});`);
  }
  if (component.state.length > 0) lines.push("");
  lines.push("  return (");
  lines.push(tree);
  lines.push("  );");
  lines.push("}");
  lines.push("");

  const styleEntries = [...usedStyles].filter((s) => STYLE_RULES[s] !== undefined).map((s) => `  ${JSON.stringify(s)}: ${STYLE_RULES[s]},`);
  const unknownStyles = [...usedStyles].filter((s) => STYLE_RULES[s] === undefined);
  for (const cls of unknownStyles) {
    // A class name coming from the source's `class="..."` has no CSS here.
    // It is emitted as an empty style entry so the reference resolves, and
    // recorded so nobody assumes the styling survived.
    styleEntries.push(`  ${JSON.stringify(cls)}: {}, // originally a CSS class; no stylesheet was translated`);
    notes.push(`CSS class ${JSON.stringify(cls)} became an empty React Native style; styling was NOT translated`);
  }
  lines.push(`const styles = StyleSheet.create({\n${styleEntries.join("\n")}\n});`);

  return { source: lines.join("\n") + "\n", notes };
}

/**
 * Emits certified-component-v1 canonical model as a Flutter (Dart)
 * StatefulWidget / StatelessWidget.
 *
 * TARGET-ONLY. The Dart SDK is not installed here, so this engine cannot
 * parse Flutter source back in and cannot compile what it emits.
 * `validator.ts` reports that honestly instead of implying a real Dart
 * analyzer accepted the output.
 *
 * Dart is a different language, not a JavaScript dialect, so several
 * canonical constructs need genuine translation rather than a rename:
 *  - `&&`/`||`/`!` exist, but `==`/`!=` on Dart objects are value
 *    comparisons and there is no `===`; the JS strict operators must NOT
 *    be emitted.
 *  - String interpolation is `$name` / `${expr}`, not backtick templates.
 *  - State lives in a separate `State<T>` class and is only mutated inside
 *    `setState(() { ... })`; a bare field assignment compiles fine and
 *    silently fails to rebuild the widget -- the same defect class this
 *    engine already guards against in Vue and the WeChat mini program.
 *  - Props are `final` constructor fields on the widget, read as
 *    `widget.<name>` from inside the State class.
 *  - There is no null-coalescing default in a const constructor for a
 *    required field; optional props become named parameters with defaults.
 */
import { ComponentDef, Expr, HtmlTag, ListPropDef, Literal, Node as CNode, PropDef, Stmt } from "../models";
import { listPropIndex, referencedComponents } from "./react";

// Same rule as ArkUI: block containers become a Column, and the HTML5
// landmark semantics are genuinely absent rather than approximated.
/** Dart file names are snake_case by convention and by lint. */
function snake(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

const CONTAINER_TAGS: ReadonlySet<HtmlTag> = new Set<HtmlTag>([
  "div", "ul", "ol", "p",
  "section", "article", "header", "footer", "nav", "main", "aside", "dl",
]);

const TEXT_STYLE: Partial<Record<HtmlTag, string>> = {
  h1: "const TextStyle(fontSize: 32, fontWeight: FontWeight.bold)",
  h2: "const TextStyle(fontSize: 28, fontWeight: FontWeight.bold)",
  h3: "const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)",
  h4: "const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)",
  h5: "const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)",
  h6: "const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)",
  strong: "const TextStyle(fontWeight: FontWeight.bold)",
  em: "const TextStyle(fontStyle: FontStyle.italic)",
  small: "const TextStyle(fontSize: 12)",
  code: "const TextStyle(fontFamily: 'monospace')",
  dt: "const TextStyle(fontWeight: FontWeight.bold)",
};

function dartType(t: "string" | "number" | "boolean"): string {
  return t === "string" ? "String" : t === "number" ? "num" : "bool";
}

function literalSource(literal: Literal): string {
  if (literal.type === "string") return `'${literal.value.replace(/'/g, "\\'")}'`;
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

function dartString(value: string): string {
  return `'${value.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
}

interface Scope {
  /** Names that are component state, read as bare fields in the State class. */
  stateNames: ReadonlySet<string>;
  /** Names snapshotted at handler entry to preserve React closure semantics. */
  snapshot: ReadonlySet<string>;
  /** Loop variables in scope; locals, so never `widget.`-prefixed. */
  loopVars: ReadonlySet<string>;
  /** Object-valued loop variables are represented by Dart maps. */
  objectLoopVars: ReadonlySet<string>;
}

function exprSource(expr: Expr, scope: Scope): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e, scope);
    return e.kind === "binary" || e.kind === "ternary" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident":
      if (scope.snapshot.has(expr.name)) return `${expr.name}\$0`;
      // A loop variable is a local closure parameter, so it must not take
      // the `widget.` prefix that props require.
      if (scope.loopVars.has(expr.name)) return expr.name;
      // State lives on the State class; props live on the widget.
      return scope.stateNames.has(expr.name) ? expr.name : `widget.${expr.name}`;
    case "member":
      return scope.objectLoopVars.has(expr.object) ? `${expr.object}[${JSON.stringify(expr.field)}]` : `${expr.object}.${expr.field}`;
    case "path":
      return scope.objectLoopVars.has(expr.object)
        ? expr.fields.reduce((source, field) => `${source}[${JSON.stringify(field)}]`, expr.object)
        : `${expr.object}.${expr.fields.join(".")}`;
    case "literal":
      return literalSource(expr.literal);
    case "eventValue": return "value";
    case "unaryNot":
      return `!${wrap(expr.operand)}`;
    case "binary": {
      // Dart has no `===`; `==` is the value comparison. Emitting the JS
      // strict operators here would be a syntax error, so the canonical
      // `==`/`!=` map straight through.
      const op = expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method === "includes" ? "contains" : expr.method === "slice" ? "substring" : expr.method}(${expr.args.map((arg) => exprSource(arg, scope)).join(", ")})`;
    case "numericFunction": {
      const args = expr.args.map((arg) => exprSource(arg, scope)).join(", ");
      if (expr.function === "abs") return `${wrap(expr.args[0]!)}.abs()`;
      if (expr.function === "floor" || expr.function === "ceil") return `${wrap(expr.args[0]!)}.${expr.function}()`;
      return `math.${expr.function}(${args})`;
    }
    case "cssModuleClass": return dartString(expr.className);
    case "regexTest": return `RegExp(${dartString(expr.pattern)}, caseSensitive: ${!expr.flags.includes("i")}, multiLine: ${expr.flags.includes("m")}, dotAll: ${expr.flags.includes("s")}).hasMatch(${exprSource(expr.operand, scope)})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary":
      return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

function collectReads(expr: Expr, into: Set<string>): void {
  if (expr.kind === "member") return;
  if (expr.kind === "ident") into.add(expr.name);
  else if (expr.kind === "binary") { collectReads(expr.left, into); collectReads(expr.right, into); }
  else if (expr.kind === "unaryNot") collectReads(expr.operand, into);
  else if (expr.kind === "stringMethod") { collectReads(expr.receiver, into); expr.args.forEach((arg) => collectReads(arg, into)); }
  else if (expr.kind === "numericFunction") expr.args.forEach((arg) => collectReads(arg, into));
  else if (expr.kind === "regexTest") collectReads(expr.operand, into);
  else if (expr.kind === "arrayLength") collectReads(expr.operand, into);
  else if (expr.kind === "ternary") { collectReads(expr.condition, into); collectReads(expr.then, into); collectReads(expr.else, into); }
}

function handlerBody(body: Stmt[], stateNames: ReadonlySet<string>, indent: string): string[] {
  const writes = new Set(body.filter((s) => s.kind === "setState").map((s) => (s as Extract<Stmt, { kind: "setState" }>).target));
  const reads = new Set<string>();
  for (const stmt of body) {
    if (stmt.kind === "setState") collectReads(stmt.value, reads);
    else stmt.args.forEach((a) => collectReads(a, reads));
  }
  const snapshot = new Set([...reads].filter((n) => writes.has(n)));
  const scope: Scope = { stateNames, snapshot, loopVars: new Set(), objectLoopVars: new Set() };
  const bare: Scope = { stateNames, snapshot: new Set(), loopVars: new Set(), objectLoopVars: new Set() };

  const lines = [...snapshot].map((n) => `${indent}final ${n}\$0 = ${stateNames.has(n) ? n : `widget.${n}`};`);
  const setStateStmts = body.filter((s): s is Extract<Stmt, { kind: "setState" }> => s.kind === "setState");
  const callStmts = body.filter((s): s is Extract<Stmt, { kind: "callProp" }> => s.kind === "callProp");

  if (setStateStmts.length > 0) {
    // A bare field assignment compiles but never rebuilds the widget, so
    // every state write goes inside setState.
    lines.push(`${indent}setState(() {`);
    for (const stmt of setStateStmts) lines.push(`${indent}  ${stmt.target} = ${exprSource(stmt.value, scope)};`);
    lines.push(`${indent}});`);
  }
  for (const stmt of callStmts) {
    lines.push(`${indent}widget.${stmt.target}(${stmt.args.map((a) => exprSource(a, scope)).join(", ")});`);
  }
  void bare;
  return lines;
}

/** Dart string interpolation for a text run. */
function textArgument(children: CNode[], scope: Scope): string {
  const parts: string[] = [];
  for (const child of children) {
    if (child.kind !== "text") return `''`;
    if (child.value.kind === "literal" && child.value.literal.type === "string") {
      parts.push(child.value.literal.value.replace(/'/g, "\\'").replace(/\$/g, "\\$"));
    } else {
      parts.push(`\${${exprSource(child.value, scope)}}`);
    }
  }
  return `'${parts.join("")}'`;
}

function nodeSource(node: CNode, scope: Scope, indent: string, lists: ReadonlyMap<string, ListPropDef>): string[] {
  if (node.kind === "text") return [`${indent}Text(${textArgument([node], scope)}),`];

  if (node.kind === "component") {
    // A Flutter child widget is a constructor call with named arguments.
    const args = node.props.map((a) => `${a.name}: ${exprSource(a.value, scope)}`);
    return [`${indent}${node.name}(${args.join(", ")}),`];
  }
  if (node.kind === "list") {
    // Dart has no list-diff key concept in a plain Column, so identity is
    // positional here; the canonical keyField is preserved in the model but
    // has no Flutter counterpart without a keyed widget strategy.
    const inner: Scope = {
      ...scope,
      loopVars: new Set([...scope.loopVars, node.itemName]),
      objectLoopVars: new Set([
        ...scope.objectLoopVars,
        ...(lists.get(node.source)?.element.kind === "object" ? [node.itemName] : []),
      ]),
    };
    const body = nodeSource(node.body, inner, indent + "    ", lists).join("\n");
    return [
      `${indent}...${node.sourceExpression === undefined ? `widget.${node.source}` : exprSource(node.sourceExpression, scope)}.map((${node.itemName}) =>`,
      body.replace(/,$/, ""),
      `${indent}),`,
    ];
  }
  if (node.kind === "conditional") {
    const thenLines = nodeSource(node.then, scope, indent + "  ", lists);
    const elseLines = node.else ? nodeSource(node.else, scope, indent + "  ", lists) : [`${indent}  const SizedBox.shrink(),`];
    return [
      `${indent}if (${exprSource(node.condition, scope)})`,
      ...thenLines,
      `${indent}else`,
      ...elseLines,
    ];
  }

  const onClick = node.events.find((e) => e.name === "onClick");
  const onChange = node.events.find((e) => e.name === "onChange" || e.name === "onInput");

  if (node.tag === "button") {
    const lines = [`${indent}ElevatedButton(`];
    if (onClick) {
      lines.push(`${indent}  onPressed: () {`);
      lines.push(...handlerBody(onClick.body, scope.stateNames, indent + "    "));
      lines.push(`${indent}  },`);
    } else {
      lines.push(`${indent}  onPressed: null,`);
    }
    lines.push(`${indent}  child: Text(${textArgument(node.children, scope)}),`);
    lines.push(`${indent}),`);
    return lines;
  }

  if (node.tag === "input") {
    const placeholder = node.attrs.find((a) => a.name === "placeholder");
    const lines = [`${indent}TextField(`];
    if (placeholder && placeholder.kind === "static") {
      lines.push(`${indent}  decoration: InputDecoration(hintText: '${placeholder.value.replace(/'/g, "\\'")}'),`);
    }
    if (onChange) {
      lines.push(`${indent}  onChanged: (String value) {`);
      lines.push(...handlerBody(onChange.body, scope.stateNames, indent + "    "));
      lines.push(`${indent}  },`);
    }
    lines.push(`${indent}),`);
    return lines;
  }

  const textOnly = node.children.length > 0 && node.children.every((c) => c.kind === "text");
  if (!CONTAINER_TAGS.has(node.tag) && textOnly) {
    const style = TEXT_STYLE[node.tag];
    const styleArg = style ? `, style: ${style}` : "";
    return [`${indent}Text(${textArgument(node.children, scope)}${styleArg}),`];
  }

  const lines = [`${indent}Column(`, `${indent}  mainAxisSize: MainAxisSize.min,`, `${indent}  children: <Widget>[`];
  for (const child of node.children) lines.push(...nodeSource(child, scope, indent + "    ", lists));
  lines.push(`${indent}  ],`);
  lines.push(`${indent}),`);
  return lines;
}

function constructorParams(props: PropDef[]): string[] {
  return props.map((p) => {
    if (p.kind === "list") return `    required this.${p.name},`;
    if (p.kind === "callback") return `    required this.${p.name},`;
    if (p.defaultValue !== undefined) return `    this.${p.name} = ${literalSource(p.defaultValue)},`;
    return p.required ? `    required this.${p.name},` : `    this.${p.name},`;
  });
}

/** `{ id: number; name: string }` has no Dart equivalent without generating
 * a companion class, so a list of objects is typed as
 * `List<Map<String, dynamic>>` and the loss is reported by the engine. */
function dartListType(list: ListPropDef): string {
  if (list.element.kind === "primitive") return `List<${dartType(list.element.primitive)}>`;
  return "List<Map<String, dynamic>>";
}

function fieldDeclarations(props: PropDef[]): string[] {
  return props.map((p) => {
    if (p.kind === "list") return `  final ${dartListType(p)} ${p.name};`;
    if (p.kind === "callback") {
      const param = p.paramType ? `${dartType(p.paramType)} value` : "";
      return `  final void Function(${param}) ${p.name};`;
    }
    const nullable = !p.required && p.defaultValue === undefined ? "?" : "";
    return `  final ${dartType(p.propType)}${nullable} ${p.name};`;
  });
}

export function emitFlutter(component: ComponentDef): string {
  const stateNames = new Set(component.state.map((s) => s.name));
  const lists = listPropIndex(component);
  const scope: Scope = { stateNames, snapshot: new Set(), loopVars: new Set(), objectLoopVars: new Set() };
  const name = component.name;
  const lines: string[] = [];

  lines.push(`// Generated by ELMOS component-dialect-engine (certified-component-v1).`);
  lines.push(`// NOTE: no Dart SDK was available to verify this file; see README.`);
  lines.push(`import 'package:flutter/material.dart';`);
  lines.push(`import 'dart:math' as math;`);
  // Dart resolves siblings by file path; snake_case is the enforced
  // convention for Dart file names.
  for (const child of referencedComponents(component)) {
    lines.push(`import '${snake(child)}.dart';`);
  }
  lines.push("");

  const stateful = component.state.length > 0;

  if (!stateful) {
    lines.push(`class ${name} extends StatelessWidget {`);
    lines.push(...fieldDeclarations(component.props));
    lines.push("");
    lines.push(`  const ${name}({`);
    lines.push(`    super.key,`);
    lines.push(...constructorParams(component.props));
    lines.push(`  });`);
    lines.push("");
    lines.push(`  @override`);
    lines.push(`  Widget build(BuildContext context) {`);
    lines.push(`    return `.concat(nodeSource(component.root, { stateNames, snapshot: new Set(), loopVars: new Set(), objectLoopVars: new Set() }, "      ", lists).join("\n").trimStart().replace(/,$/, ";")));
    lines.push(`  }`);
    lines.push(`}`);
    return lines.join("\n") + "\n";
  }

  lines.push(`class ${name} extends StatefulWidget {`);
  lines.push(...fieldDeclarations(component.props));
  lines.push("");
  lines.push(`  const ${name}({`);
  lines.push(`    super.key,`);
  lines.push(...constructorParams(component.props));
  lines.push(`  });`);
  lines.push("");
  lines.push(`  @override`);
  lines.push(`  State<${name}> createState() => _${name}State();`);
  lines.push(`}`);
  lines.push("");
  lines.push(`class _${name}State extends State<${name}> {`);
  for (const s of component.state) {
    lines.push(`  ${dartType(s.stateType)}${s.nullable ? "?" : ""} ${s.name} = ${literalSource(s.initial)};`);
  }
  lines.push("");
  lines.push(`  @override`);
  lines.push(`  Widget build(BuildContext context) {`);
  const body = nodeSource(component.root, scope, "      ", lists).join("\n");
  lines.push(`    return ${body.trimStart().replace(/,$/, ";")}`);
  lines.push(`  }`);
  lines.push(`}`);
  return lines.join("\n") + "\n";
}

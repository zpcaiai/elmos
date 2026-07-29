/**
 * Parses one React function component into the certified-component-v1
 * canonical model, using the real TypeScript Compiler API (with JSX) as the
 * parsing frontend -- the same real-compiler-frontend choice already made
 * elsewhere in this repository (`engines/polyglot-route-engine`,
 * `engines/frontend-client-engine/src/polyglot.ts`).
 *
 * Recognized shape (anything else raises DialectError):
 *
 *   function ComponentName({ propA, propB, onSomething }: Props) {
 *     const [count, setCount] = useState(0);
 *     return ( <div>...</div> );
 *   }
 *
 * `Props` must be an inline type literal (`{ name: string; onClick: () =>
 * void }`) with only primitive-typed fields and `on*`-named zero/one-arg
 * callback fields. `useState` calls must destructure `[x, setX]` with a
 * literal initializer. The JSX return must be a single root element from
 * the certified-component-v1 tag/attribute/event allowlist.
 */
import * as ts from "typescript";
import {
  at, AttrBinding, AttrName, ATTR_NAMES, BinaryOperator, CallbackPropDef, ComponentDef, DataPropDef, DialectError,
  EventBinding, EventName, Expr, fail, HtmlTag, HTML_TAGS, ListElementShape, ListPropDef, Literal, Node as CNode,
  PrimitiveType, PropDef, requireDefined, StateDef, Stmt, checkIdentifier, require_, validateComponent, ComponentArg } from "../models";

function primitiveTypeFromNode(node: ts.TypeNode | undefined, what: string): PrimitiveType {
  if (!node) fail("CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`);
  const text = node.getText();
  if (text === "string" || text === "number" || text === "boolean") return text;
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${JSON.stringify(text)}`);
}

/**
 * Reads an array-typed prop annotation into a canonical list element shape.
 * Accepts `T[]` and `Array<T>` where `T` is a primitive or a flat object
 * type literal whose fields are all primitives.
 */
export function listElementFromArrayType(node: ts.TypeNode, what: string): ListElementShape {
  let element: ts.TypeNode | undefined;
  if (ts.isArrayTypeNode(node)) element = node.elementType;
  else if (ts.isTypeReferenceNode(node) && node.typeName.getText() === "Array") element = node.typeArguments?.[0];
  if (element === undefined) fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} is not an array type`);

  if (ts.isTypeLiteralNode(element)) {
    const fields: Record<string, PrimitiveType> = {};
    for (const member of element.members) {
      require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}: list element type must contain plain property signatures`);
      require_(!member.questionToken, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}: optional list element fields are outside certified-component-v1`);
      fields[(member.name as ts.Identifier).text] = primitiveTypeFromNode(member.type, `${what} field`);
    }
    return { kind: "object", fields };
  }
  return { kind: "primitive", primitive: primitiveTypeFromNode(element, `${what} element`) };
}

export function isArrayTypeNode(node: ts.TypeNode): boolean {
  return ts.isArrayTypeNode(node) || (ts.isTypeReferenceNode(node) && node.typeName.getText() === "Array");
}

/**
 * Picks the key field for an object list element.
 *
 * Every target framework needs a stable list identity. Rather than invent
 * one, the conventional identity field is required to be present: `id`, or
 * else a single field whose name ends in `Id`/`Key`. Anything else fails
 * closed, because guessing a key silently changes list-diffing behavior on
 * every target.
 */
export function inferKeyField(element: ListElementShape, what: string): string | undefined {
  if (element.kind === "primitive") return undefined;
  const names = Object.keys(element.fields);
  if (names.includes("id")) return "id";
  const candidates = names.filter((n) => /(Id|Key)$/.test(n));
  require_(candidates.length === 1, "CERTIFIED_COMPONENT_MISSING_LIST_KEY", `${what}: list elements need an identity field named "id" (or exactly one field ending in "Id"/"Key"); found ${JSON.stringify(names)}`);
  return at(candidates, 0, "CERTIFIED_COMPONENT_MISSING_LIST_KEY", `${what}: missing key candidate`);
}

function literalFromNode(node: ts.Expression, type: PrimitiveType): Literal {
  if (type === "string") {
    require_(ts.isStringLiteral(node), "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "expected a string literal");
    return { type: "string", value: (node as ts.StringLiteral).text };
  }
  if (type === "number") {
    require_(ts.isNumericLiteral(node), "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "expected a numeric literal");
    return { type: "number", value: Number((node as ts.NumericLiteral).text) };
  }
  require_(node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword, "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "expected true/false");
  return { type: "boolean", value: node.kind === ts.SyntaxKind.TrueKeyword };
}

function anyLiteralFromNode(node: ts.Expression): Literal {
  if (ts.isStringLiteral(node)) return { type: "string", value: node.text };
  if (ts.isNumericLiteral(node)) return { type: "number", value: Number(node.text) };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { type: "boolean", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { type: "boolean", value: false };
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `expression of kind ${ts.SyntaxKind[node.kind]} is not a plain literal`);
}

const BINARY_TOKEN_MAP: Record<number, BinaryOperator> = {
  [ts.SyntaxKind.PlusToken]: "+",
  [ts.SyntaxKind.MinusToken]: "-",
  [ts.SyntaxKind.AsteriskToken]: "*",
  [ts.SyntaxKind.SlashToken]: "/",
  [ts.SyntaxKind.PercentToken]: "%",
  [ts.SyntaxKind.LessThanToken]: "<",
  [ts.SyntaxKind.LessThanEqualsToken]: "<=",
  [ts.SyntaxKind.GreaterThanToken]: ">",
  [ts.SyntaxKind.GreaterThanEqualsToken]: ">=",
  [ts.SyntaxKind.EqualsEqualsToken]: "==",
  [ts.SyntaxKind.EqualsEqualsEqualsToken]: "==",
  [ts.SyntaxKind.ExclamationEqualsToken]: "!=",
  [ts.SyntaxKind.ExclamationEqualsEqualsToken]: "!=",
  [ts.SyntaxKind.AmpersandAmpersandToken]: "&&",
  [ts.SyntaxKind.BarBarToken]: "||",
};

function parseExpr(node: ts.Expression): Expr {
  if (ts.isParenthesizedExpression(node)) return parseExpr(node.expression);
  if (ts.isIdentifier(node)) return { kind: "ident", name: node.text };
  if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression)) {
    // `item.name` -- validateComponent later proves `item` really is a loop
    // variable and `name` a declared field of its element shape.
    return { kind: "member", object: node.expression.text, field: node.name.text };
  }
  if (ts.isStringLiteral(node) || ts.isNumericLiteral(node) || node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) {
    return { kind: "literal", literal: anyLiteralFromNode(node) };
  }
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.ExclamationToken) {
    return { kind: "unaryNot", operand: parseExpr(node.operand) };
  }
  if (ts.isBinaryExpression(node)) {
    const op = requireDefined(BINARY_TOKEN_MAP[node.operatorToken.kind], "CERTIFIED_COMPONENT_UNSUPPORTED_OPERATOR", `operator ${ts.SyntaxKind[node.operatorToken.kind]} is outside certified-component-v1`);
    return { kind: "binary", operator: op, left: parseExpr(node.left), right: parseExpr(node.right) };
  }
  if (ts.isConditionalExpression(node)) {
    return { kind: "ternary", condition: parseExpr(node.condition), then: parseExpr(node.whenTrue), else: parseExpr(node.whenFalse) };
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `expression kind ${ts.SyntaxKind[node.kind]} is outside certified-component-v1`);
}

/** Parses a certified-component-v1 event handler arrow function body:
 * `() => setCount(count + 1)`, `() => setCount(!on)`,
 * `(v) => onChange(v)` -- a single expression statement, or a block of
 * such statements, each either a setState call or a callback-prop call. */
function parseHandlerBody(fn: ts.ArrowFunction): Stmt[] {
  const exprToStmt = (expr: ts.Expression): Stmt => {
    require_(ts.isCallExpression(expr) && ts.isIdentifier(expr.expression), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "handler statement must be a single call expression");
    const call = expr as ts.CallExpression;
    const callee = (call.expression as ts.Identifier).text;
    const fourth = callee[3];
    if (callee.startsWith("set") && fourth !== undefined && fourth === fourth.toUpperCase() && fourth !== fourth.toLowerCase()) {
      require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} must be called with exactly one argument`);
      const stateName = fourth.toLowerCase() + callee.slice(4);
      return { kind: "setState", target: stateName, value: parseExpr(at(call.arguments, 0, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} is missing its argument`)) };
    }
    require_(/^on[A-Z]/.test(callee), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_CALL", `handler call target ${JSON.stringify(callee)} is neither a setState-style call nor an on*-named callback prop`);
    require_(call.arguments.length <= 1, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `${callee} is called with more than one argument`);
    return { kind: "callProp", target: callee, args: call.arguments.map(parseExpr) };
  };
  if (ts.isBlock(fn.body)) {
    return fn.body.statements.map((s) => {
      require_(ts.isExpressionStatement(s), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "handler block may only contain expression statements");
      return exprToStmt((s as ts.ExpressionStatement).expression);
    });
  }
  return [exprToStmt(fn.body)];
}

function jsxAttrName(name: string): AttrName {
  const mapped = name === "className" ? "class" : name === "htmlFor" ? "for" : name;
  require_((ATTR_NAMES as readonly string[]).includes(mapped), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `attribute ${JSON.stringify(name)} is outside certified-component-v1`);
  return mapped as AttrName;
}

const JSX_EVENT_PROP_TO_EVENT_NAME: Record<string, EventName> = {
  onClick: "onClick", onChange: "onChange", onInput: "onInput", onSubmit: "onSubmit",
};

function parseJsxChildren(children: ts.NodeArray<ts.JsxChild>): CNode[] {
  const result: CNode[] = [];
  for (const child of children) {
    if (ts.isJsxText(child)) {
      const text = child.text.trim();
      if (text.length > 0) result.push({ kind: "text", value: { kind: "literal", literal: { type: "string", value: text } } });
      continue;
    }
    if (ts.isJsxExpression(child)) {
      require_(child.expression !== undefined, "CERTIFIED_COMPONENT_EMPTY_JSX_EXPRESSION", "empty {} JSX expression is not supported");
      const expr = child.expression as ts.Expression;
      if (ts.isConditionalExpression(expr) && (isJsxLike(expr.whenTrue) || isJsxLike(expr.whenFalse))) {
        result.push({
          kind: "conditional",
          condition: parseExpr(expr.condition),
          then: parseJsxNode(expr.whenTrue),
          else: expr.whenFalse.kind === ts.SyntaxKind.NullKeyword ? null : parseJsxNode(expr.whenFalse),
        });
        continue;
      }
      if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && isJsxLike(expr.right)) {
        result.push({ kind: "conditional", condition: parseExpr(expr.left), then: parseJsxNode(expr.right), else: null });
        continue;
      }
      const listNode = tryParseListExpression(expr);
      if (listNode !== null) {
        result.push(listNode);
        continue;
      }
      if (isJsxLike(expr)) {
        result.push(parseJsxNode(expr));
        continue;
      }
      result.push({ kind: "text", value: parseExpr(expr) });
      continue;
    }
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child)) {
      result.push(parseJsxNode(child));
      continue;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_JSX_CHILD", `JSX child kind ${ts.SyntaxKind[child.kind]} is outside certified-component-v1`);
  }
  return result;
}

/** JSX branches of a ternary are commonly written parenthesized
 * (`cond ? (<em>a</em>) : (<em>b</em>)`), so parentheses must be seen
 * through before deciding whether a node is JSX. */
function unwrapParens(node: ts.Expression): ts.Expression {
  let current = node;
  while (ts.isParenthesizedExpression(current)) current = current.expression;
  return current;
}

function isJsxLike(node: ts.Expression): boolean {
  const inner = unwrapParens(node);
  return ts.isJsxElement(inner) || ts.isJsxSelfClosingElement(inner);
}

/**
 * Recognizes `items.map((item) => (<li>...</li>))` as a list render node.
 *
 * Returns null (rather than failing) when the expression is not a `.map`
 * call at all, so the caller can fall through to its other JSX-child
 * cases. A `.map` call that IS present but malformed fails closed.
 */
function tryParseListExpression(expr: ts.Expression): CNode | null {
  const call = unwrapParens(expr);
  if (!ts.isCallExpression(call)) return null;
  if (!ts.isPropertyAccessExpression(call.expression) || call.expression.name.text !== "map") return null;

  require_(ts.isIdentifier(call.expression.expression), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", "list rendering must map directly over a declared list prop");
  const source = (call.expression.expression as ts.Identifier).text;

  require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map must take exactly one callback`);
  const fn = at(call.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "missing map callback");
  require_(ts.isArrowFunction(fn), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map callback must be an inline arrow function`);
  const arrow = fn as ts.ArrowFunction;
  // An index parameter would let the body use array position as identity,
  // which reorders differently on every framework's list diffing.
  require_(arrow.parameters.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map callback must take exactly one parameter (an index parameter is outside certified-component-v1)`);
  const param = at(arrow.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "missing map parameter");
  require_(ts.isIdentifier(param.name), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map parameter must be a plain identifier (no destructuring)`);
  const itemName = (param.name as ts.Identifier).text;

  require_(!ts.isBlock(arrow.body), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map callback must return JSX directly, not through a block body`);
  return { kind: "list", source, itemName, body: parseJsxNode(arrow.body as ts.Expression) };
}

function parseJsxNode(rawNode: ts.Expression): CNode {
  const node = unwrapParens(rawNode);
  require_(ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node), "CERTIFIED_COMPONENT_UNSUPPORTED_JSX_NODE", `expected a JSX element, got ${ts.SyntaxKind[node.kind]}`);
  const opening = ts.isJsxElement(node) ? node.openingElement : node;
  const tagName = opening.tagName.getText();

  // A capitalised tag is a component reference, not an unknown element.
  // JSX makes this distinction lexically, and so does every framework's
  // own compiler.
  if (/^[A-Z]/.test(tagName)) {
    require_(!ts.isJsxElement(node) || node.children.filter((c) => !(ts.isJsxText(c) && c.text.trim() === "")).length === 0,
      "CERTIFIED_COMPONENT_UNSUPPORTED_SLOT",
      `<${tagName}> is given children; slot projection is outside certified-component-v1 because each target evaluates it differently`);
    const props: ComponentArg[] = [];
    for (const attr of opening.attributes.properties) {
      require_(ts.isJsxAttribute(attr), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", "spread attributes are outside certified-component-v1");
      const jsxAttr = attr as ts.JsxAttribute;
      const name = jsxAttr.name.getText();
      if (name === "key") continue;
      if (jsxAttr.initializer === undefined) {
        props.push({ name, value: { kind: "literal", literal: { type: "boolean", value: true } } });
      } else if (ts.isStringLiteral(jsxAttr.initializer)) {
        props.push({ name, value: { kind: "literal", literal: { type: "string", value: jsxAttr.initializer.text } } });
      } else if (ts.isJsxExpression(jsxAttr.initializer) && jsxAttr.initializer.expression) {
        props.push({ name, value: parseExpr(jsxAttr.initializer.expression) });
      } else {
        fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `prop ${JSON.stringify(name)} on <${tagName}> has an unsupported value shape`);
      }
    }
    return { kind: "component", name: tagName, props };
  }

  require_((HTML_TAGS as readonly string[]).includes(tagName), "CERTIFIED_COMPONENT_UNSUPPORTED_TAG", `tag ${JSON.stringify(tagName)} is outside certified-component-v1`);
  const tag = tagName as HtmlTag;

  const attrs: AttrBinding[] = [];
  const events: EventBinding[] = [];
  for (const attr of opening.attributes.properties) {
    require_(ts.isJsxAttribute(attr), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", "spread attributes are outside certified-component-v1");
    const jsxAttr = attr as ts.JsxAttribute;
    const rawName = jsxAttr.name.getText();
    if (rawName === "key") {
      // `key` is React's own list-identity prop, not part of the rendered
      // DOM. The canonical model derives it from the list's keyField, so
      // re-parsing emitted output must drop it rather than treat it as an
      // unsupported attribute.
      continue;
    }
    const mappedEvent = JSX_EVENT_PROP_TO_EVENT_NAME[rawName];
    if (mappedEvent !== undefined) {
      require_(jsxAttr.initializer !== undefined && ts.isJsxExpression(jsxAttr.initializer) && jsxAttr.initializer.expression !== undefined, "CERTIFIED_COMPONENT_BAD_EVENT_BINDING", `${rawName} must bind to an arrow function`);
      const init = (jsxAttr.initializer as ts.JsxExpression).expression as ts.Expression;
      require_(ts.isArrowFunction(init), "CERTIFIED_COMPONENT_BAD_EVENT_BINDING", `${rawName} must bind to an inline arrow function`);
      events.push({ name: mappedEvent, body: parseHandlerBody(init) });
      continue;
    }
    const attrName = jsxAttrName(rawName);
    if (jsxAttr.initializer === undefined) {
      attrs.push({ kind: "static", name: attrName, value: "true" });
    } else if (ts.isStringLiteral(jsxAttr.initializer)) {
      attrs.push({ kind: "static", name: attrName, value: jsxAttr.initializer.text });
    } else if (ts.isJsxExpression(jsxAttr.initializer) && jsxAttr.initializer.expression) {
      attrs.push({ kind: "dynamic", name: attrName, value: parseExpr(jsxAttr.initializer.expression) });
    } else {
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `attribute ${JSON.stringify(rawName)} has an unsupported value shape`);
    }
  }

  const children = ts.isJsxElement(node) ? parseJsxChildren(node.children) : [];
  return { kind: "element", tag, attrs, events, children };
}

/**
 * Every component declared in one file.
 *
 * Real React files routinely declare several components together -- a
 * coverage scan of production code found 11 of 28 files blocked purely on
 * this, with up to 9 components in a single file. Refusing them was never
 * a semantic limit; the canonical model was simply built one component at
 * a time.
 *
 * Order is preserved, so emitted output keeps the author's reading order.
 * Non-component functions in the same file still fail closed: a helper
 * cannot be silently skipped, because skipping it would drop behavior the
 * components depend on.
 */
/**
 * Per-component results, isolating failures.
 *
 * `parseReactComponents` is all-or-nothing, which is wrong for a repository
 * run: one component using an effect hook would blank out the four good
 * components declared beside it. Here each declaration is parsed on its own
 * so a blocked component costs exactly itself.
 */
export function parseReactComponentResults(
  source: string,
  fileName = "Component.tsx",
): { name: string | null; component: ComponentDef | null; error: DialectError | null }[] {
  const sourceFile = ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const functions = sourceFile.statements.filter(ts.isFunctionDeclaration);
  require_(functions.length >= 1, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", "expected at least one top-level function component declaration, found 0");
  const localTypes = collectLocalTypes(sourceFile);
  return functions.map((fn) => {
    const declaredName = fn.name?.text ?? null;
    try {
      return { name: declaredName, component: parseFunctionComponent(fn, localTypes), error: null };
    } catch (error) {
      if (error instanceof DialectError) return { name: declaredName, component: null, error };
      throw error;
    }
  });
}

export function parseReactComponents(source: string, fileName = "Component.tsx"): ComponentDef[] {
  const sourceFile = ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const functions = sourceFile.statements.filter(ts.isFunctionDeclaration);
  require_(functions.length >= 1, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", "expected at least one top-level function component declaration, found 0");
  const localTypes = collectLocalTypes(sourceFile);
  const components = functions.map((fn) => parseFunctionComponent(fn, localTypes));
  const names = new Set<string>();
  for (const c of components) {
    require_(!names.has(c.name), "CERTIFIED_COMPONENT_DUPLICATE_COMPONENT", `component ${JSON.stringify(c.name)} is declared twice in ${fileName}`);
    names.add(c.name);
  }
  return components;
}

/**
 * The single-component entry point, kept because most callers translate one
 * component and because a file with several components is ambiguous about
 * which one "the" component is.
 */
export function parseReactComponent(source: string, fileName = "Component.tsx"): ComponentDef {
  const components = parseReactComponents(source, fileName);
  require_(components.length === 1, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", `expected exactly one top-level function component declaration, found ${components.length}`);
  return at(components, 0, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", "no function component found");
}

/** Type aliases and interfaces declared in this file, by name. */
type LocalTypes = ReadonlyMap<string, ts.TypeLiteralNode>;

function collectLocalTypes(sourceFile: ts.SourceFile): LocalTypes {
  const map = new Map<string, ts.TypeLiteralNode>();
  for (const statement of sourceFile.statements) {
    if (ts.isInterfaceDeclaration(statement)) {
      // An interface body IS a type literal for our purposes; re-parsing
      // its members through the same path keeps one code path for both.
      const synthetic = ts.factory.createTypeLiteralNode(statement.members);
      // The synthesized node has no parent/positions, so re-read members
      // from the original declaration instead.
      void synthetic;
      map.set(statement.name.text, ts.factory.createTypeLiteralNode(statement.members));
    } else if (ts.isTypeAliasDeclaration(statement) && ts.isTypeLiteralNode(statement.type)) {
      map.set(statement.name.text, statement.type);
    }
  }
  return map;
}

function resolveLocalPropsType(annotation: ts.TypeNode, localTypes: LocalTypes): ts.TypeNode {
  if (!ts.isTypeReferenceNode(annotation) || !ts.isIdentifier(annotation.typeName)) return annotation;
  require_(annotation.typeArguments === undefined || annotation.typeArguments.length === 0,
    "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", `generic props type ${annotation.typeName.text}<...> is outside certified-component-v1`);
  const resolved = localTypes.get(annotation.typeName.text);
  require_(resolved !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS",
    `props type ${JSON.stringify(annotation.typeName.text)} is not declared in this file; an imported props type cannot be resolved by a single-file parser`);
  return resolved as ts.TypeNode;
}

/**
 * Whether this function is a component at all.
 *
 * A `.tsx` file routinely holds helper functions beside its components.
 * Counting a helper as "a component outside the subset" is wrong in both
 * directions: it makes coverage look worse than it is, and it pollutes the
 * blocker ranking with reasons no subset widening could ever fix. A React
 * function component is one that returns JSX.
 */
function returnsJsx(fn: ts.FunctionDeclaration): boolean {
  let found = false;
  const visit = (node: ts.Node): void => {
    if (found) return;
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node) || ts.isJsxFragment(node)) { found = true; return; }
    ts.forEachChild(node, visit);
  };
  if (fn.body) ts.forEachChild(fn.body, visit);
  return found;
}

function parseFunctionComponent(fn: ts.FunctionDeclaration, localTypes: LocalTypes = new Map()): ComponentDef {
  require_(returnsJsx(fn), "CERTIFIED_COMPONENT_NOT_A_COMPONENT",
    `${fn.name?.text ?? "an anonymous function"} returns no JSX, so it is a helper rather than a component`);
  const fnName = requireDefined(fn.name, "CERTIFIED_COMPONENT_MISSING_NAME", "component function must be named");
  const name = fnName.text;
  checkIdentifier(name, "component name");

  require_(fn.parameters.length <= 1, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "component must take zero or one (props) parameter");
  const props: PropDef[] = [];
  if (fn.parameters.length === 1) {
    const param = at(fn.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "missing props parameter");
    const bindingPattern = param.name;
    require_(ts.isObjectBindingPattern(bindingPattern), "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props parameter must be an inline destructured object pattern");
    const annotation = requireDefined(param.type, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props parameter must have a type annotation");
    // `function C({ a }: Props)` with `interface Props { ... }` in the same
    // file is the dominant React idiom -- a scan of real code found it
    // blocking 37 components. The declaration is right there, so resolving
    // it is exact rather than inferred. A type imported from elsewhere is
    // still refused: this parser reads ONE file and must not pretend to
    // know what a name means somewhere else.
    const typeLiteral = ts.isTypeLiteralNode(annotation) ? annotation : resolveLocalPropsType(annotation, localTypes);
    require_(ts.isTypeLiteralNode(typeLiteral), "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props parameter must have an inline type literal annotation, or name a type/interface declared in the same file");
    const fieldTypes = new Map<string, ts.TypeNode | undefined>();
    const optionalFields = new Set<string>();
    for (const member of typeLiteral.members) {
      require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "props type literal must contain plain property signatures");
      const fieldName = (member.name as ts.Identifier).text;
      fieldTypes.set(fieldName, member.type);
      if (member.questionToken) optionalFields.add(fieldName);
    }
    for (const element of bindingPattern.elements) {
      require_(ts.isIdentifier(element.name) && !element.dotDotDotToken, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props destructuring must bind plain names (no rest/nested patterns)");
      const propName = (element.name as ts.Identifier).text;
      const typeNode = requireDefined(fieldTypes.get(propName), "CERTIFIED_COMPONENT_UNKNOWN_PROP", `destructured prop ${JSON.stringify(propName)} is not declared in the props type`);
      if (/^on[A-Z]/.test(propName)) {
        require_(ts.isFunctionTypeNode(typeNode), "CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE", `callback prop ${JSON.stringify(propName)} must have a function type`);
        require_(typeNode.parameters.length <= 1, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", `callback prop ${JSON.stringify(propName)} may take at most one parameter`);
        const paramType = typeNode.parameters.length === 1
          ? primitiveTypeFromNode(at(typeNode.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", "missing callback parameter").type, `${propName} parameter`)
          : undefined;
        const def: CallbackPropDef = { kind: "callback", name: propName, paramType };
        props.push(def);
      } else if (isArrayTypeNode(typeNode)) {
        const shape = listElementFromArrayType(typeNode, `list prop ${JSON.stringify(propName)}`);
        require_(!element.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_DEFAULT", `list prop ${JSON.stringify(propName)} may not have a default value`);
        const def: ListPropDef = { kind: "list", name: propName, element: shape, keyField: inferKeyField(shape, `list prop ${JSON.stringify(propName)}`) };
        props.push(def);
      } else {
        const propType = primitiveTypeFromNode(typeNode, `prop ${propName}`);
        const required = !optionalFields.has(propName) && !element.initializer;
        const defaultValue: Literal | undefined = element.initializer ? literalFromNode(element.initializer, propType) : undefined;
        const def: DataPropDef = { kind: "data", name: propName, propType, required, defaultValue };
        props.push(def);
      }
    }
  }

  const body = requireDefined(fn.body, "CERTIFIED_COMPONENT_MISSING_BODY", "component must have a body");
  const state: StateDef[] = [];
  let returnStatement: ts.ReturnStatement | undefined;
  for (const stmt of body.statements) {
    if (ts.isVariableStatement(stmt)) {
      require_(stmt.declarationList.declarations.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "only one declaration per const statement is supported");
      const decl = at(stmt.declarationList.declarations, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing declaration");
      const declName = decl.name;
      require_(ts.isArrayBindingPattern(declName) && declName.elements.length === 2, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "expected a `const [x, setX] = useState(...)` declaration");
      const getterEl = at(declName.elements, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing useState getter");
      const setterEl = at(declName.elements, 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing useState setter");
      require_(ts.isBindingElement(getterEl) && ts.isIdentifier(getterEl.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "useState getter must be a plain identifier");
      require_(ts.isBindingElement(setterEl) && ts.isIdentifier(setterEl.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "useState setter must be a plain identifier");
      const getterName = (getterEl.name as ts.Identifier).text;
      const setterNameText = (setterEl.name as ts.Identifier).text;
      const firstChar = at([...getterName], 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "empty state name");
      const expectedSetter = "set" + firstChar.toUpperCase() + getterName.slice(1);
      require_(setterNameText === expectedSetter, "CERTIFIED_COMPONENT_NONSTANDARD_SETTER_NAME", `useState setter must be named ${expectedSetter}`);
      const initializer = requireDefined(decl.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "expected a useState(...) call");
      require_(ts.isCallExpression(initializer) && ts.isIdentifier(initializer.expression) && initializer.expression.text === "useState", "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "expected a useState(...) call");
      require_(initializer.arguments.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "useState must be called with exactly one literal initial value");
      const initial = anyLiteralFromNode(at(initializer.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing useState argument"));
      state.push({ name: getterName, stateType: initial.type, initial });
      continue;
    }
    if (ts.isReturnStatement(stmt)) {
      returnStatement = stmt;
      continue;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", `component body statement kind ${ts.SyntaxKind[stmt.kind]} is outside certified-component-v1`);
  }
  const ret = requireDefined(returnStatement, "CERTIFIED_COMPONENT_MISSING_RETURN", "component must end with a `return <Jsx/>` statement");
  let returned = requireDefined(ret.expression, "CERTIFIED_COMPONENT_MISSING_RETURN", "component must return JSX");
  if (ts.isParenthesizedExpression(returned)) returned = returned.expression;
  const root = parseJsxNode(returned);

  const component: ComponentDef = { name, props, state, root };
  validateComponent(component);
  return component;
}

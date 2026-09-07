/**
 * Shared expression/statement parsing for every template-based framework
 * (Vue 2, Vue 3, Angular, WeChat mini program).
 *
 * All of these embed *JavaScript expressions* inside their template
 * delimiters (`{{ }}`, `:attr="..."`, `@click="..."`, `bindtap` handler
 * bodies). Rather than hand-roll a fragile mini expression parser per
 * framework -- exactly the "string matching instead of a real frontend"
 * mistake this repository avoids elsewhere -- every one of them re-uses
 * the real TypeScript parser here, and every AST shape not on the
 * certified-component-v1 allowlist raises DialectError.
 */
import * as ts from "typescript";
import { at, BinaryOperator, Expr, fail, Literal, NumericFunction, NumericPredicate, requireDefined, require_, Stmt, StringMethod } from "../models";

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
  [ts.SyntaxKind.QuestionQuestionToken]: "??",
};

export function literalFromNode(node: ts.Expression): Literal {
  if (ts.isStringLiteral(node)) return { type: "string", value: node.text };
  if (ts.isNumericLiteral(node)) return { type: "number", value: Number(node.text) };
  if (node.kind === ts.SyntaxKind.NullKeyword) return { type: "null" };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { type: "boolean", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { type: "boolean", value: false };
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken && ts.isNumericLiteral(node.operand)) {
    return { type: "number", value: -Number(node.operand.text) };
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `expression of kind ${ts.SyntaxKind[node.kind]} is not a plain literal`);
}

function regexParts(node: ts.Expression): { pattern: string; flags: string } | null {
  if (!ts.isRegularExpressionLiteral(node)) return null;
  const source = node.getText();
  let escaped = false;
  let inClass = false;
  let closingSlash = -1;
  for (let index = 1; index < source.length; index += 1) {
    const char = source[index];
    if (escaped) { escaped = false; continue; }
    if (char === "\\") { escaped = true; continue; }
    if (char === "[") { inClass = true; continue; }
    if (char === "]") { inClass = false; continue; }
    if (char === "/" && !inClass) { closingSlash = index; break; }
  }
  require_(closingSlash > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `regular expression ${source} has no closing delimiter`);
  const pattern = source.slice(1, closingSlash);
  const flags = source.slice(closingSlash + 1);
  require_(/^[imsu]*$/.test(flags) && new Set(flags).size === flags.length, "CERTIFIED_COMPONENT_REGEX_TEST_FLAGS", "regex literal flags must be unique and limited to i/m/s/u");
  require_(pattern.length <= 256, "CERTIFIED_COMPONENT_REGEX_TEST_TOO_LONG", "regex pattern exceeds the 256-character certified bound");
  return { pattern, flags };
}

/**
 * `unwrapMemberAccess` collapses the framework-specific "how do I read a
 * value" prefixes into the bare canonical identifier:
 *   Vue `<script setup>` : `count.value`, `props.label`
 *   Vue 2 / Angular      : `this.count`
 *   Mini program         : `this.data.count`
 * The canonical model stores only `count` / `label`; each emitter re-adds
 * whatever spelling its own framework requires.
 */
function unwrapMemberAccess(node: ts.PropertyAccessExpression): string | null {
  const name = node.name.text;
  const target = node.expression;
  if (ts.isIdentifier(target)) {
    if (target.text === "props" || target.text === "data") return name;
    if (target.text === "this") return name;
    if (name === "value") return target.text; // `count.value` -> `count`
  }
  if (ts.isPropertyAccessExpression(target)) {
    // `this.data.count` -- note that `this` parses as a ThisExpression
    // (SyntaxKind.ThisKeyword), NOT an Identifier, so an `isIdentifier`
    // check here silently fails to match and the whole read is rejected.
    const isThisData =
      (target.expression.kind === ts.SyntaxKind.ThisKeyword ||
        (ts.isIdentifier(target.expression) && target.expression.text === "this")) &&
      target.name.text === "data";
    if (isThisData) return name;
    // `props.x.value` and deeper chains are not certified.
  }
  if (target.kind === ts.SyntaxKind.ThisKeyword) return name;
  return null;
}

function isTemplateEventValue(node: ts.Expression): boolean {
  return ts.isPropertyAccessExpression(node)
    && node.name.text === "value"
    && ts.isPropertyAccessExpression(node.expression)
    && node.expression.name.text === "target"
    && ts.isIdentifier(node.expression.expression)
    && node.expression.expression.text === "$event";
}

export function parseExprNode(node: ts.Expression): Expr {
  if (ts.isParenthesizedExpression(node)) return parseExprNode(node.expression);
  if (ts.isIdentifier(node)) return { kind: "ident", name: node.text };
  if (isTemplateEventValue(node)) return { kind: "eventValue" };
  if (ts.isNonNullExpression(node)) return parseExprNode(node.expression);
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
    const methodName = node.expression.name.text;
    if (ts.isIdentifier(node.expression.expression) && node.expression.expression.text === "Math" && ["min", "max", "floor", "ceil", "abs"].includes(methodName)) {
      const variadic = methodName === "min" || methodName === "max";
      require_(variadic ? node.arguments.length >= 1 && node.arguments.length <= 8 : node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMERIC_FUNCTION_ARITY", `${methodName} expects ${variadic ? "between 1 and 8" : "exactly 1"} argument(s)`);
      return { kind: "numericFunction", function: methodName as NumericFunction, args: node.arguments.map(parseExprNode) };
    }
    if (ts.isIdentifier(node.expression.expression) && node.expression.expression.text === "Number" && methodName === "isFinite") {
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMERIC_PREDICATE_ARITY", "isFinite expects exactly one argument");
      return { kind: "numericPredicate", predicate: "isFinite" as NumericPredicate, operand: parseExprNode(at(node.arguments, 0, "CERTIFIED_COMPONENT_NUMERIC_PREDICATE_ARITY", "isFinite is missing its argument")) };
    }
    if (methodName === "test") {
      const regex = regexParts(node.expression.expression);
      require_(regex !== null, "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "regex test receiver must be a literal regular expression");
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_REGEX_TEST_ARITY", "regex test expects one argument");
      return { kind: "regexTest", pattern: regex.pattern, flags: regex.flags, operand: parseExprNode(at(node.arguments, 0, "CERTIFIED_COMPONENT_REGEX_TEST_ARITY", "regex test is missing its argument")) };
    }
    const method = methodName as StringMethod;
    require_(["toUpperCase", "toLowerCase", "trim", "replaceAll", "includes", "startsWith", "endsWith", "slice"].includes(method), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `string method ${method} is outside certified-component-v1`);
    const args = node.arguments.map(parseExprNode);
    const expectedArgs = method === "replaceAll" ? 2 : method === "includes" || method === "startsWith" || method === "endsWith" ? 1 : method === "slice" ? 1 : 0;
    require_(method === "slice" ? args.length <= 2 && args.length >= 1 : args.length === expectedArgs, "CERTIFIED_COMPONENT_STRING_METHOD_ARITY", `${method} expects ${method === "slice" ? "one or two" : expectedArgs} argument(s)`);
    const argumentType = method === "slice" ? "number" : "string";
    require_((method !== "replaceAll" && method !== "includes" && method !== "startsWith" && method !== "endsWith" && method !== "slice") || args.every((arg) => arg.kind === "literal" && arg.literal.type === argumentType), "CERTIFIED_COMPONENT_STRING_METHOD_ARGUMENT", `${method} arguments must be ${argumentType} literals`);
    return { kind: "stringMethod", method, receiver: parseExprNode(node.expression.expression), args };
  }
  if (ts.isPropertyAccessExpression(node) && node.name.text === "length") {
    return { kind: "arrayLength", operand: parseExprNode(node.expression) };
  }
  if (ts.isPropertyAccessExpression(node)) {
    const unwrapped = unwrapMemberAccess(node);
    if (unwrapped !== null) return { kind: "ident", name: unwrapped };
    // Not a framework access prefix, so this is a plain single-level field
    // read -- `row.label` off a list's loop variable. `validateComponent`
    // proves the object really is a loop variable in scope and the field is
    // declared on its element shape; anything deeper stays rejected.
    const base = parseExprNode(node.expression);
    if (base.kind === "ident") return { kind: "member", object: base.name, field: node.name.text };
    if (base.kind === "member") return { kind: "path", object: base.object, fields: [base.field, node.name.text] };
    if (base.kind === "path") return { kind: "path", object: base.object, fields: [...base.fields, node.name.text] };
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `property access ${node.getText()} is outside certified-component-v1 (only plain props/state reads and single-level list-item fields are supported)`);
  }
  if (ts.isStringLiteral(node) || ts.isNumericLiteral(node) || node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword || node.kind === ts.SyntaxKind.NullKeyword) {
    return { kind: "literal", literal: literalFromNode(node) };
  }
  if (ts.isPrefixUnaryExpression(node)) {
    if (node.operator === ts.SyntaxKind.ExclamationToken) return { kind: "unaryNot", operand: parseExprNode(node.operand) };
    if (node.operator === ts.SyntaxKind.MinusToken && ts.isNumericLiteral(node.operand)) {
      return { kind: "literal", literal: literalFromNode(node) };
    }
  }
  if (ts.isBinaryExpression(node)) {
    const op = requireDefined(BINARY_TOKEN_MAP[node.operatorToken.kind], "CERTIFIED_COMPONENT_UNSUPPORTED_OPERATOR", `operator ${ts.SyntaxKind[node.operatorToken.kind]} is outside certified-component-v1`);
    return { kind: "binary", operator: op, left: parseExprNode(node.left), right: parseExprNode(node.right) };
  }
  if (ts.isConditionalExpression(node)) {
    return { kind: "ternary", condition: parseExprNode(node.condition), then: parseExprNode(node.whenTrue), else: parseExprNode(node.whenFalse) };
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `expression kind ${ts.SyntaxKind[node.kind]} is outside certified-component-v1`);
}

/** Parses one embedded template expression (the contents of `{{ }}`,
 * `:attr="..."`, `[attr]="..."`, etc.) using the real TypeScript parser. */
export function parseTemplateExpression(source: string, what: string): Expr {
  const wrapped = `(${source});`;
  const file = ts.createSourceFile("expr.ts", wrapped, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS) as ts.SourceFile & {
    parseDiagnostics?: readonly ts.DiagnosticWithLocation[];
  };
  require_((file.parseDiagnostics ?? []).length === 0, "CERTIFIED_COMPONENT_EXPRESSION_PARSE_FAILED", `${what}: could not parse ${JSON.stringify(source)}`);
  require_(file.statements.length === 1, "CERTIFIED_COMPONENT_EXPRESSION_PARSE_FAILED", `${what}: expected a single expression`);
  const stmt = at(file.statements, 0, "CERTIFIED_COMPONENT_EXPRESSION_PARSE_FAILED", `${what}: empty expression`);
  require_(ts.isExpressionStatement(stmt), "CERTIFIED_COMPONENT_EXPRESSION_PARSE_FAILED", `${what}: expected an expression`);
  return parseExprNode(stmt.expression);
}

/**
 * Parses a template event-handler body such as
 *   Vue      `count = count + step; emit('done', count)`
 *   Angular  `count = count + 1; done.emit(count)`
 * into certified-component-v1 statements.
 *
 * `emitToCallback` maps a framework's event-emission spelling back to the
 * canonical `on*` callback prop name, so the round trip is reversible.
 */
export interface HandlerParseOptions {
  /** Names that are component state (assignable). */
  stateNames: ReadonlySet<string>;
  /** Maps an emitted event name (e.g. "done") to the canonical callback
   * prop name (e.g. "onDone"). Returns null if it is not a known event. */
  eventToCallback: (eventName: string) => string | null;
  /** Recognizes the framework's emit call shape and returns the event name
   * plus argument list, or null if this call is not an emit. */
  matchEmitCall: (call: ts.CallExpression) => { eventName: string; args: readonly ts.Expression[] } | null;
}

export function parseHandlerStatements(source: string, options: HandlerParseOptions, what: string): Stmt[] {
  const wrapped = `function __h() { ${source} }`;
  const file = ts.createSourceFile("handler.ts", wrapped, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS) as ts.SourceFile & {
    parseDiagnostics?: readonly ts.DiagnosticWithLocation[];
  };
  require_((file.parseDiagnostics ?? []).length === 0, "CERTIFIED_COMPONENT_HANDLER_PARSE_FAILED", `${what}: could not parse handler ${JSON.stringify(source)}`);
  const fn = file.statements.find(ts.isFunctionDeclaration);
  const body = requireDefined(fn?.body, "CERTIFIED_COMPONENT_HANDLER_PARSE_FAILED", `${what}: empty handler`);

  const result: Stmt[] = [];
  for (const stmt of body.statements) {
    require_(ts.isExpressionStatement(stmt), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: handler may only contain expression statements, found ${ts.SyntaxKind[stmt.kind]}`);
    const expr = stmt.expression;

    // Assignment to state: `count = count + step`
    if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      const targetExpr = parseExprNode(expr.left);
      require_(targetExpr.kind === "ident", "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: assignment target must be a plain state name`);
      const target = (targetExpr as Extract<Expr, { kind: "ident" }>).name;
      require_(options.stateNames.has(target), "CERTIFIED_COMPONENT_UNKNOWN_STATE_TARGET", `${what}: ${JSON.stringify(target)} is not declared component state`);
      result.push({ kind: "setState", target, value: parseExprNode(expr.right) });
      continue;
    }

    // Emit / callback invocation
    if (ts.isCallExpression(expr)) {
      const matched = options.matchEmitCall(expr);
      if (matched !== null) {
        const callbackName = options.eventToCallback(matched.eventName);
        require_(callbackName !== null, "CERTIFIED_COMPONENT_UNKNOWN_EMITTED_EVENT", `${what}: emitted event ${JSON.stringify(matched.eventName)} is not a declared event`);
        require_(matched.args.length <= 1, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `${what}: emitted event ${JSON.stringify(matched.eventName)} carries more than one argument`);
        result.push({ kind: "callProp", target: callbackName as string, args: matched.args.map(parseExprNode) });
        continue;
      }
    }

    fail("CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", `${what}: statement ${JSON.stringify(expr.getText())} is neither a state assignment nor a declared event emission`);
  }
  return result;
}

/** Recovers the canonical `onFoo` callback prop name from an emitted event
 * name `foo`. Inverse of `eventNameForCallback` in the Vue emitters. */
export function callbackNameForEvent(eventName: string): string {
  return "on" + eventName.charAt(0).toUpperCase() + eventName.slice(1);
}

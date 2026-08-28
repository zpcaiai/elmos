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
import * as path from "path";
import {
  at, AttrBinding, AttrName, ATTR_NAMES, BinaryOperator, CallbackPropDef, ComponentDef, DataPropDef, DialectError,
  EventBinding, EventName, Expr, fail, HtmlTag, HTML_TAGS, ListElementShape, ListPropDef, Literal, Node as CNode,
  NumericFunction, NumericPredicate, PrimitiveType, PropDef, requireDefined, StateDef, Stmt, StringMethod, checkIdentifier, require_, validateComponent, ComponentArg,
  StaticListItem, literalType, ValueShape } from "../models";

function primitiveTypeFromNode(node: ts.TypeNode | undefined, what: string): PrimitiveType {
  if (!node) fail("CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`);
  const text = node.getText();
  if (text === "string" || text === "number" || text === "boolean") return text;
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${JSON.stringify(text)}`);
}

export interface ReactProjectContext {
  program: ts.Program;
  checker: ts.TypeChecker;
}

export interface ReactParserOptions {
  project?: ReactProjectContext;
  sourceFile?: ts.SourceFile;
}

type StaticStringMapValue = string | ReadonlyMap<string, string>;
interface StaticRegexDefinition {
  readonly kind: "regex";
  readonly pattern: string;
  readonly flags: string;
}
interface StaticCssModuleDefinition {
  readonly kind: "css-module";
}
interface StaticNumberFormatDefinition {
  readonly kind: "number-format";
  readonly format: "grouped";
}
interface StaticNavigationDefinition {
  readonly kind: "navigation-component";
}
interface StaticListDefinition {
  readonly kind: "static-list";
  readonly element: Extract<ListElementShape, { kind: "object" }>;
  readonly items: readonly StaticListItem[];
}
interface StaticPrimitiveListDefinition {
  readonly kind: "static-primitive-list";
  readonly element: Extract<ListElementShape, { kind: "primitive" }>;
  readonly values: readonly Literal[];
}
interface StaticPureFunctionDefinition {
  readonly kind: "pure-function";
  readonly parameters: readonly string[];
  readonly body: ts.Expression;
}
interface StaticClosedValueDefinition {
  readonly kind: "closed-value";
  readonly initializer: ts.Expression;
  readonly value?: Expr;
  readonly stringMap?: ReadonlyMap<string, StaticStringMapValue>;
}
type StaticDefinition = ReadonlyMap<string, StaticStringMapValue> | StaticRegexDefinition | StaticCssModuleDefinition | StaticNumberFormatDefinition | StaticNavigationDefinition | StaticListDefinition | StaticPrimitiveListDefinition | StaticPureFunctionDefinition | StaticClosedValueDefinition;
type StaticStringMaps = ReadonlyMap<string, StaticDefinition>;
type ExpressionBindings = ReadonlyMap<string, Expr>;

function isStaticRegexDefinition(value: StaticDefinition): value is StaticRegexDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "regex";
}

function isStaticCssModuleDefinition(value: StaticDefinition): value is StaticCssModuleDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "css-module";
}

function isStaticNumberFormatDefinition(value: StaticDefinition): value is StaticNumberFormatDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "number-format";
}

function isStaticNavigationDefinition(value: StaticDefinition): value is StaticNavigationDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "navigation-component";
}

function isStaticListDefinition(value: StaticDefinition): value is StaticListDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "static-list";
}

function isStaticPrimitiveListDefinition(value: StaticDefinition): value is StaticPrimitiveListDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "static-primitive-list";
}

function isStaticPureFunctionDefinition(value: StaticDefinition): value is StaticPureFunctionDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "pure-function";
}

function isStaticClosedValueDefinition(value: StaticDefinition): value is StaticClosedValueDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "closed-value";
}

function isStaticStringMapDefinition(value: StaticDefinition): value is ReadonlyMap<string, StaticStringMapValue> {
  return !isStaticRegexDefinition(value) && !isStaticCssModuleDefinition(value) && !isStaticNumberFormatDefinition(value) && !isStaticNavigationDefinition(value) && !isStaticListDefinition(value) && !isStaticPrimitiveListDefinition(value) && !isStaticPureFunctionDefinition(value) && !isStaticClosedValueDefinition(value);
}

function staticStringMapEntries(value: StaticDefinition | undefined): ReadonlyMap<string, StaticStringMapValue> | undefined {
  if (value === undefined) return undefined;
  if (isStaticStringMapDefinition(value)) return value;
  return isStaticClosedValueDefinition(value) ? value.stringMap : undefined;
}

function pureFunctionDefinitionFromNode(fn: ts.FunctionDeclaration): StaticPureFunctionDefinition | null {
  if (fn.name === undefined || fn.body === undefined || fn.asteriskToken !== undefined || fn.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.AsyncKeyword)) return null;
  if (fn.type !== undefined && !["string", "number", "boolean"].includes(fn.type.getText())) return null;
  const parameters: string[] = [];
  for (const parameter of fn.parameters) {
    if (!ts.isIdentifier(parameter.name) || parameter.type === undefined || parameter.initializer !== undefined || parameter.dotDotDotToken !== undefined) return null;
    if (!["string", "number", "boolean"].includes(parameter.type.getText())) return null;
    parameters.push(parameter.name.text);
  }
  const statement = fn.body.statements.length === 1 ? fn.body.statements[0] : undefined;
  if (statement === undefined || !ts.isReturnStatement(statement) || statement.expression === undefined) return null;
  return { kind: "pure-function", parameters, body: statement.expression };
}

function unwrapStaticValue(node: ts.Expression): ts.Expression {
  let current = node;
  while (ts.isParenthesizedExpression(current) || ts.isAsExpression(current) || ts.isTypeAssertionExpression(current)) {
    current = ts.isParenthesizedExpression(current) ? current.expression : current.expression;
  }
  return current;
}

function tryStaticLiteral(node: ts.Expression): Literal | null {
  try {
    return anyLiteralFromNode(unwrapStaticValue(node));
  } catch (error) {
    if (error instanceof DialectError) return null;
    throw error;
  }
}

/** Recognize immutable module-level object/tuple arrays as list sources.
 * Values stay as literals in the canonical list contract; an array containing
 * a call, spread, computed field, or nested object is left for the normal
 * fail-closed expression path instead of being partially folded. */
function staticListDefinitionFromInitializer(initializer: ts.Expression, staticMaps: StaticStringMaps = new Map()): StaticListDefinition | null {
  const array = unwrapStaticValue(initializer);
  const mapped = staticMappedObjectListDefinitionFromInitializer(array, staticMaps);
  if (mapped !== null) return mapped;
  if (!ts.isArrayLiteralExpression(array) || array.elements.length === 0) return null;
  const items: StaticListItem[] = [];
  for (const element of array.elements) {
    const value = unwrapStaticValue(element as ts.Expression);
    const fields: Record<string, Literal> = {};
    if (ts.isObjectLiteralExpression(value)) {
      for (const property of value.properties) {
        if (!ts.isPropertyAssignment(property) || property.name === undefined || property.name.getText().startsWith("[") ) return null;
        const fieldName = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) ? property.name.text : null;
        if (fieldName === null || fields[fieldName] !== undefined) return null;
        const literal = tryStaticLiteral(property.initializer);
        if (literal === null || literal.type === "null") return null;
        fields[fieldName] = literal;
      }
    } else if (ts.isArrayLiteralExpression(value)) {
      for (const [index, tupleValue] of value.elements.entries()) {
        const literal = tryStaticLiteral(tupleValue as ts.Expression);
        if (literal === null || literal.type === "null") return null;
        fields[`item${index}`] = literal;
      }
    } else {
      return null;
    }
    if (Object.keys(fields).length === 0) return null;
    items.push({ fields });
  }
  const first = items[0];
  if (first === undefined) return null;
  const fieldNames = Object.keys(first.fields).sort();
  const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
  for (const fieldName of fieldNames) {
    const literal = first.fields[fieldName];
    if (literal === undefined) return null;
    fields[fieldName] = { shape: { kind: "primitive", primitive: literalType(literal) }, optional: false };
  }
  for (const item of items) {
    const names = Object.keys(item.fields).sort();
    if (JSON.stringify(names) !== JSON.stringify(fieldNames)) return null;
    for (const fieldName of fieldNames) {
      const literal = item.fields[fieldName];
      const field = fields[fieldName];
      if (literal === undefined || field === undefined || field.shape.kind !== "primitive" || literalType(literal) !== field.shape.primitive) return null;
    }
  }
  return { kind: "static-list", element: { kind: "object", fields }, items };
}

function staticPrimitiveListDefinitionFromInitializer(initializer: ts.Expression): StaticPrimitiveListDefinition | null {
  const array = unwrapStaticValue(initializer);
  if (!ts.isArrayLiteralExpression(array) || array.elements.length === 0) return null;
  const values: Literal[] = [];
  for (const element of array.elements) {
    const literal = tryStaticLiteral(element as ts.Expression);
    if (literal === null || literal.type === "null") return null;
    values.push(literal);
  }
  const first = values[0];
  if (first === undefined || !values.every((value) => value.type === first.type)) return null;
  return { kind: "static-primitive-list", element: { kind: "primitive", primitive: literalType(first) }, values };
}

function regexDefinitionFromNode(node: ts.Expression): StaticRegexDefinition | null {
  if (!ts.isRegularExpressionLiteral(node)) return null;
  const source = node.getText();
  let escaped = false;
  let inClass = false;
  let closingSlash = -1;
  for (let index = 1; index < source.length; index += 1) {
    const char = source[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === "[") {
      inClass = true;
      continue;
    }
    if (char === "]") {
      inClass = false;
      continue;
    }
    if (char === "/" && !inClass) {
      closingSlash = index;
      break;
    }
  }
  require_(closingSlash > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `regular expression ${source} has no closing delimiter`);
  const pattern = source.slice(1, closingSlash);
  const flags = source.slice(closingSlash + 1);
  require_(/^[imsu]*$/.test(flags) && new Set(flags).size === flags.length, "CERTIFIED_COMPONENT_REGEX_TEST_FLAGS", "regex literal flags must be unique and limited to i/m/s/u");
  require_(pattern.length <= 256, "CERTIFIED_COMPONENT_REGEX_TEST_TOO_LONG", "regex pattern exceeds the 256-character certified bound");
  return { kind: "regex", pattern, flags };
}

type StaticConstant =
  | { kind: "undefined" }
  | { kind: "literal"; literal: Literal }
  | { kind: "array"; items: StaticConstant[] }
  | { kind: "object"; fields: ReadonlyMap<string, StaticConstant> };

function staticConstantLiteral(value: StaticConstant): Literal | null {
  return value.kind === "literal" ? value.literal : null;
}

function staticConstantKey(value: StaticConstant): string | number | null {
  const literal = staticConstantLiteral(value);
  if (literal?.type === "string" || literal?.type === "number") return literal.value;
  return null;
}

function staticConstantFromDefinition(
  definition: StaticDefinition | undefined,
  staticMaps: StaticStringMaps,
  stack: readonly string[],
): StaticConstant | null {
  if (definition === undefined) return null;
  if (isStaticListDefinition(definition)) {
    return { kind: "array", items: definition.items.map((item) => ({ kind: "object", fields: new Map(Object.entries(item.fields).map(([name, literal]) => [name, { kind: "literal", literal }])) })) };
  }
  if (isStaticPrimitiveListDefinition(definition)) return { kind: "array", items: definition.values.map((literal) => ({ kind: "literal", literal })) };
  if (isStaticClosedValueDefinition(definition)) {
    return staticConstantFromExpression(definition.initializer, new Map(), staticMaps, stack);
  }
  return null;
}

function staticConstantFromExpression(
  node: ts.Expression,
  bindings: ReadonlyMap<string, StaticConstant>,
  staticMaps: StaticStringMaps,
  stack: readonly string[] = [],
): StaticConstant | null {
  const value = unwrapStaticValue(node);
  const literal = tryStaticLiteral(value);
  if (literal !== null) return { kind: "literal", literal };
  if (ts.isIdentifier(value)) {
    const bound = bindings.get(value.text);
    if (bound !== undefined) return bound;
    if (stack.includes(value.text)) return null;
    return staticConstantFromDefinition(staticMaps.get(value.text), staticMaps, [...stack, value.text]);
  }
  if (ts.isArrayLiteralExpression(value)) {
    const items: StaticConstant[] = [];
    for (const element of value.elements) {
      if (ts.isSpreadElement(element)) return null;
      const item = staticConstantFromExpression(element as ts.Expression, bindings, staticMaps, stack);
      if (item === null) return null;
      items.push(item);
    }
    return { kind: "array", items };
  }
  if (ts.isObjectLiteralExpression(value)) {
    const fields = new Map<string, StaticConstant>();
    for (const property of value.properties) {
      if (!ts.isPropertyAssignment(property) || ts.isComputedPropertyName(property.name)) return null;
      const name = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) ? property.name.text : null;
      if (name === null || fields.has(name)) return null;
      const field = staticConstantFromExpression(property.initializer, bindings, staticMaps, stack);
      if (field === null) return null;
      fields.set(name, field);
    }
    return { kind: "object", fields };
  }
  if (ts.isTemplateExpression(value)) {
    let result = value.head.text;
    for (const span of value.templateSpans) {
      const part = staticConstantFromExpression(span.expression, bindings, staticMaps, stack);
      const partLiteral = part === null ? null : staticConstantLiteral(part);
      if (partLiteral === null || (partLiteral.type !== "string" && partLiteral.type !== "number" && partLiteral.type !== "boolean")) return null;
      result += String(partLiteral.value) + span.literal.text;
    }
    return { kind: "literal", literal: { type: "string", value: result } };
  }
  if (ts.isPropertyAccessExpression(value)) {
    if (value.name.text === "length") {
      const receiver = staticConstantFromExpression(value.expression, bindings, staticMaps, stack);
      return receiver?.kind === "array" ? { kind: "literal", literal: { type: "number", value: receiver.items.length } } : null;
    }
    const receiver = staticConstantFromExpression(value.expression, bindings, staticMaps, stack);
    return receiver?.kind === "object" ? receiver.fields.get(value.name.text) ?? { kind: "undefined" } : null;
  }
  if (ts.isElementAccessExpression(value) && value.argumentExpression !== undefined) {
    const receiver = staticConstantFromExpression(value.expression, bindings, staticMaps, stack);
    const key = staticConstantFromExpression(value.argumentExpression, bindings, staticMaps, stack);
    const keyValue = key === null ? null : staticConstantKey(key);
    if (receiver?.kind === "object" && typeof keyValue === "string") return receiver.fields.get(keyValue) ?? { kind: "undefined" };
    if (receiver?.kind === "array" && typeof keyValue === "number" && Number.isInteger(keyValue) && keyValue >= 0) return receiver.items[keyValue] ?? { kind: "undefined" };
    return null;
  }
  if (ts.isPrefixUnaryExpression(value)) {
    const operand = staticConstantFromExpression(value.operand, bindings, staticMaps, stack);
    const operandLiteral = operand === null ? null : staticConstantLiteral(operand);
    if (operandLiteral === null) return null;
    if (value.operator === ts.SyntaxKind.ExclamationToken) return { kind: "literal", literal: { type: "boolean", value: !Boolean(operandLiteral.type === "null" ? null : operandLiteral.value) } };
    if (value.operator === ts.SyntaxKind.MinusToken && operandLiteral.type === "number") return { kind: "literal", literal: { type: "number", value: -operandLiteral.value } };
    if (value.operator === ts.SyntaxKind.PlusToken && operandLiteral.type === "number") return operand;
    return null;
  }
  if (ts.isBinaryExpression(value)) {
    const left = staticConstantFromExpression(value.left, bindings, staticMaps, stack);
    const right = staticConstantFromExpression(value.right, bindings, staticMaps, stack);
    const leftLiteral = left === null ? null : staticConstantLiteral(left);
    const rightLiteral = right === null ? null : staticConstantLiteral(right);
    if (value.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken) return left === null || left.kind === "undefined" || leftLiteral?.type === "null" ? right : left;
    if (leftLiteral === null || rightLiteral === null) return null;
    if (leftLiteral.type === "null" || rightLiteral.type === "null") return null;
    const leftValue = leftLiteral.value;
    const rightValue = rightLiteral.value;
    switch (value.operatorToken.kind) {
      case ts.SyntaxKind.PlusToken: {
        if (typeof leftValue === "string" || typeof rightValue === "string") return { kind: "literal", literal: { type: "string", value: String(leftValue) + String(rightValue) } };
        if (typeof leftValue === "number" && typeof rightValue === "number") return { kind: "literal", literal: { type: "number", value: leftValue + rightValue } };
        return null;
      }
      case ts.SyntaxKind.MinusToken: return { kind: "literal", literal: { type: "number", value: Number(leftValue) - Number(rightValue) } };
      case ts.SyntaxKind.AsteriskToken: return { kind: "literal", literal: { type: "number", value: Number(leftValue) * Number(rightValue) } };
      case ts.SyntaxKind.SlashToken: return { kind: "literal", literal: { type: "number", value: Number(leftValue) / Number(rightValue) } };
      case ts.SyntaxKind.PercentToken: return { kind: "literal", literal: { type: "number", value: Number(leftValue) % Number(rightValue) } };
      case ts.SyntaxKind.LessThanToken: return { kind: "literal", literal: { type: "boolean", value: leftValue < rightValue } };
      case ts.SyntaxKind.LessThanEqualsToken: return { kind: "literal", literal: { type: "boolean", value: leftValue <= rightValue } };
      case ts.SyntaxKind.GreaterThanToken: return { kind: "literal", literal: { type: "boolean", value: leftValue > rightValue } };
      case ts.SyntaxKind.GreaterThanEqualsToken: return { kind: "literal", literal: { type: "boolean", value: leftValue >= rightValue } };
      case ts.SyntaxKind.EqualsEqualsToken:
      case ts.SyntaxKind.EqualsEqualsEqualsToken: return { kind: "literal", literal: { type: "boolean", value: leftValue === rightValue } };
      case ts.SyntaxKind.ExclamationEqualsToken:
      case ts.SyntaxKind.ExclamationEqualsEqualsToken: return { kind: "literal", literal: { type: "boolean", value: leftValue !== rightValue } };
      case ts.SyntaxKind.AmpersandAmpersandToken: return { kind: "literal", literal: { type: "boolean", value: Boolean(leftValue && rightValue) } };
      case ts.SyntaxKind.BarBarToken: return { kind: "literal", literal: { type: "boolean", value: Boolean(leftValue || rightValue) } };
      default: return null;
    }
  }
  if (ts.isConditionalExpression(value)) {
    const condition = staticConstantFromExpression(value.condition, bindings, staticMaps, stack);
    const conditionLiteral = condition === null ? null : staticConstantLiteral(condition);
    if (conditionLiteral?.type !== "boolean") return null;
    return staticConstantFromExpression(conditionLiteral.value ? value.whenTrue : value.whenFalse, bindings, staticMaps, stack);
  }
  if (ts.isCallExpression(value)) {
    if (ts.isIdentifier(value.expression) && value.expression.text === "Number" && value.arguments.length === 1) {
      const argument = staticConstantFromExpression(at(value.arguments, 0, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "Number is missing its argument"), bindings, staticMaps, stack);
      const argumentLiteral = argument === null ? null : staticConstantLiteral(argument);
      if (argumentLiteral !== null && (argumentLiteral.type === "string" || argumentLiteral.type === "number" || argumentLiteral.type === "boolean")) {
        const number = Number(argumentLiteral.value);
        return Number.isFinite(number) ? { kind: "literal", literal: { type: "number", value: number } } : null;
      }
      return null;
    }
    if (!ts.isPropertyAccessExpression(value.expression)) return null;
    const method = value.expression.name.text;
    const receiver = staticConstantFromExpression(value.expression.expression, bindings, staticMaps, stack);
    if (receiver?.kind === "array" && method === "map" && value.arguments.length === 1) {
      const callback = at(value.arguments, 0, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "map is missing its callback");
      require_(ts.isArrowFunction(callback) && callback.parameters.length >= 1 && callback.parameters.length <= 2 && !ts.isBlock(callback.body), "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static map must use a synchronous expression callback with one or two parameters");
      const arrow = callback as ts.ArrowFunction;
      const first = at(arrow.parameters, 0, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static map is missing its item parameter");
      const firstName = first.name;
      require_(ts.isIdentifier(firstName), "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static map item parameter must be a plain identifier");
      const result: StaticConstant[] = [];
      receiver.items.forEach((item, index) => {
        const nextBindings = new Map(bindings);
        nextBindings.set((firstName as ts.Identifier).text, item);
        const second = arrow.parameters[1];
        if (second !== undefined) {
          require_(ts.isIdentifier(second.name), "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static map index parameter must be a plain identifier");
          nextBindings.set(second.name.text, { kind: "literal", literal: { type: "number", value: index } });
        }
        const mapped = staticConstantFromExpression(arrow.body as ts.Expression, nextBindings, staticMaps, stack);
        if (mapped === null) return null;
        result.push(mapped);
      });
      return { kind: "array", items: result };
    }
    if (receiver?.kind === "array" && method === "reduce" && value.arguments.length === 2) {
      const callback = at(value.arguments, 0, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "reduce is missing its callback");
      require_(ts.isArrowFunction(callback) && callback.parameters.length === 2 && !ts.isBlock(callback.body), "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static reduce must use a synchronous expression callback with two parameters");
      const arrow = callback as ts.ArrowFunction;
      const accumulatorParameter = at(arrow.parameters, 0, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static reduce is missing its accumulator parameter");
      const itemParameter = at(arrow.parameters, 1, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static reduce is missing its item parameter");
      require_(ts.isIdentifier(accumulatorParameter.name) && ts.isIdentifier(itemParameter.name), "CERTIFIED_COMPONENT_STATIC_EVALUATION", "static reduce parameters must be plain identifiers");
      let accumulator = staticConstantFromExpression(at(value.arguments, 1, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "reduce is missing its initial value"), bindings, staticMaps, stack);
      if (accumulator === null) return null;
      for (const item of receiver.items) {
        const nextBindings = new Map(bindings);
        nextBindings.set(accumulatorParameter.name.text, accumulator);
        nextBindings.set(itemParameter.name.text, item);
        accumulator = staticConstantFromExpression(arrow.body as ts.Expression, nextBindings, staticMaps, stack);
        if (accumulator === null) return null;
      }
      return accumulator;
    }
    if (receiver?.kind === "literal" && receiver.literal.type === "string" && (method === "replace" || method === "replaceAll" || method === "toUpperCase" || method === "toLowerCase" || method === "trim")) {
      const args = value.arguments.map((argument) => staticConstantFromExpression(argument, bindings, staticMaps, stack));
      const literals = args.map((argument) => argument === null ? null : staticConstantLiteral(argument));
      if (!literals.some((argument) => argument === null)) {
        if (method === "toUpperCase" && literals.length === 0) return { kind: "literal", literal: { type: "string", value: receiver.literal.value.toUpperCase() } };
        if (method === "toLowerCase" && literals.length === 0) return { kind: "literal", literal: { type: "string", value: receiver.literal.value.toLowerCase() } };
        if (method === "trim" && literals.length === 0) return { kind: "literal", literal: { type: "string", value: receiver.literal.value.trim() } };
        if ((method === "replace" || method === "replaceAll") && literals.length === 2 && literals[1]?.type === "string") {
          const pattern = literals[0];
          if (pattern?.type === "string") return { kind: "literal", literal: { type: "string", value: method === "replaceAll" ? receiver.literal.value.split(pattern.value).join(literals[1].value) : receiver.literal.value.replace(pattern.value, literals[1].value) } };
        }
      }
    }
    const patternNode = value.arguments[0];
    if (method === "replace" && value.arguments.length === 2 && patternNode !== undefined && ts.isRegularExpressionLiteral(patternNode)) {
      const receiverValue = staticConstantFromExpression(value.expression.expression, bindings, staticMaps, stack);
      const replacement = staticConstantFromExpression(at(value.arguments, 1, "CERTIFIED_COMPONENT_STATIC_EVALUATION", "replace is missing its replacement"), bindings, staticMaps, stack);
      const replacementLiteral = replacement === null ? null : staticConstantLiteral(replacement);
      const regex = regexDefinitionFromNode(patternNode);
      if (receiverValue?.kind === "literal" && receiverValue.literal.type === "string" && replacementLiteral?.type === "string" && regex !== null) {
        const flags = regex.flags.includes("g") ? regex.flags : `${regex.flags}g`;
        return { kind: "literal", literal: { type: "string", value: receiverValue.literal.value.replace(new RegExp(regex.pattern, flags), replacementLiteral.value) } };
      }
    }
    return null;
  }
  return null;
}

function staticConstantToExpr(value: StaticConstant): Expr {
  if (value.kind === "undefined") return { kind: "literal", literal: { type: "null" } };
  if (value.kind === "literal") return { kind: "literal", literal: value.literal };
  if (value.kind === "array") return { kind: "arrayLiteral", items: value.items.map(staticConstantToExpr) };
  return { kind: "objectLiteral", fields: [...value.fields.entries()].map(([name, field]) => ({ name, value: staticConstantToExpr(field) })) };
}

function staticConstantFromExpr(expr: Expr): StaticConstant | null {
  if (expr.kind === "literal") return { kind: "literal", literal: expr.literal };
  if (expr.kind === "arrayLiteral") {
    const items = expr.items.map(staticConstantFromExpr);
    return items.every((item) => item !== null) ? { kind: "array", items: items as StaticConstant[] } : null;
  }
  if (expr.kind === "objectLiteral") {
    const fields = new Map<string, StaticConstant>();
    for (const field of expr.fields) {
      const value = staticConstantFromExpr(field.value);
      if (value === null) return null;
      fields.set(field.name, value);
    }
    return { kind: "object", fields };
  }
  return null;
}

function staticListDefinitionFromStaticConstant(value: StaticConstant): StaticListDefinition | null {
  if (value.kind !== "array" || value.items.length === 0 || !value.items.every((item) => item.kind === "object")) return null;
  const first = value.items[0];
  if (first === undefined || first.kind !== "object") return null;
  const fieldNames = [...first.fields.keys()];
  if (fieldNames.length === 0) return null;
  const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
  const items: StaticListItem[] = [];
  for (const item of value.items) {
    if (item.kind !== "object" || item.fields.size !== fieldNames.length) return null;
    const literals: Record<string, Literal> = {};
    for (const fieldName of fieldNames) {
      const field = item.fields.get(fieldName);
      const fieldLiteral = field === undefined ? null : staticConstantLiteral(field);
      if (fieldLiteral === null || fieldLiteral.type === "null") return null;
      literals[fieldName] = fieldLiteral;
    }
    items.push({ fields: literals });
  }
  for (const fieldName of fieldNames) {
    const literal = items[0]?.fields[fieldName];
    if (literal === undefined) return null;
    fields[fieldName] = { shape: { kind: "primitive", primitive: literalType(literal) }, optional: false };
  }
  return { kind: "static-list", element: { kind: "object", fields }, items };
}

/** Return the common element contract of an immutable object-of-arrays
 * lookup. The selected array can vary with a typed key at runtime, so this
 * helper intentionally records only its shared shape; the emitted list keeps
 * the exact lookup expression instead of pretending one branch is always
 * selected. */
function staticListDefinitionFromExpression(expression: Expr, name: string): ListPropDef | null {
  const candidates: StaticListDefinition[] = [];
  if (expression.kind === "arrayLiteral") {
    const constant = staticConstantFromExpr(expression);
    const definition = constant === null ? null : staticListDefinitionFromStaticConstant(constant);
    if (definition !== null) candidates.push(definition);
  } else if (expression.kind === "objectLookup" && expression.object.kind === "objectLiteral") {
    for (const field of expression.object.fields) {
      const constant = staticConstantFromExpr(field.value);
      const definition = constant === null ? null : staticListDefinitionFromStaticConstant(constant);
      if (definition === null) return null;
      candidates.push(definition);
    }
  }
  const first = candidates[0];
  if (first === undefined || candidates.some((candidate) => JSON.stringify(candidate.element) !== JSON.stringify(first.element))) return null;
  const keyField = inferredKeyFieldOrUndefined(first.element, `static list ${JSON.stringify(name)}`);
  return { kind: "list", name, sourceExpression: expression, element: first.element, ...(keyField === undefined ? {} : { keyField }) };
}

function staticMappedObjectListDefinitionFromInitializer(initializer: ts.Expression, staticMaps: StaticStringMaps): StaticListDefinition | null {
  const value = unwrapStaticValue(initializer);
  if (!ts.isCallExpression(value) || !ts.isPropertyAccessExpression(value.expression) || value.expression.name.text !== "map") return null;
  try {
    const result = staticConstantFromExpression(value, new Map(), staticMaps);
    return result === null ? null : staticListDefinitionFromStaticConstant(result);
  } catch (error) {
    // A map that is only partly static must continue through the ordinary
    // parser and remain blocked; static folding is an optimization, not a
    // second permissive parser or a new diagnostic boundary.
    if (error instanceof DialectError && error.code === "CERTIFIED_COMPONENT_STATIC_EVALUATION") return null;
    throw error;
  }
}

function isClosedStaticValueWithReferences(node: ts.Expression, staticMaps: StaticStringMaps, stack: readonly string[] = []): boolean {
  const value = unwrapStaticValue(node);
  if (isClosedStaticValue(value)) return true;
  if (ts.isIdentifier(value)) {
    if (stack.includes(value.text)) return false;
    const definition = staticMaps.get(value.text);
    return definition !== undefined && (isStaticListDefinition(definition) || isStaticPrimitiveListDefinition(definition) || isStaticClosedValueDefinition(definition) && isClosedStaticValueWithReferences(definition.initializer, staticMaps, [...stack, value.text]));
  }
  if (!ts.isObjectLiteralExpression(value)) return false;
  return value.properties.every((property) => ts.isPropertyAssignment(property)
    && (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name))
    && isClosedStaticValueWithReferences(property.initializer, staticMaps, stack));
}

function collectStaticStringMaps(sourceFile: ts.SourceFile, project?: ReactProjectContext): StaticStringMaps {
  const maps = new Map<string, StaticDefinition>();
  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) continue;
    if (/\.module\.css$/u.test(statement.moduleSpecifier.text)) {
      const defaultImport = statement.importClause?.name;
      if (defaultImport !== undefined) maps.set(defaultImport.text, { kind: "css-module" });
      continue;
    }
    if (statement.moduleSpecifier.text === "next/link") {
      const defaultImport = statement.importClause?.name;
      if (defaultImport !== undefined) maps.set(defaultImport.text, { kind: "navigation-component" });
      continue;
    }
    const namedImports = statement.importClause?.namedBindings && ts.isNamedImports(statement.importClause.namedBindings)
      ? statement.importClause.namedBindings.elements
      : [];
    // This is a semantic, not a name-only, allowlist. `formatQuota` is the
    // repository helper whose contract is integer, non-negative, grouped
    // zh-CN output; arbitrary imported calls remain outside the subset.
    if (/pricingCatalog$/u.test(statement.moduleSpecifier.text)) {
      for (const specifier of namedImports) {
        if ((specifier.propertyName?.text ?? specifier.name.text) === "formatQuota") maps.set(specifier.name.text, { kind: "number-format", format: "grouped" });
      }
    }
    if (project !== undefined) {
      for (const specifier of namedImports) {
        const declaration = importedValueDeclaration(specifier, project);
        const initializer = declaration?.initializer;
        if (initializer === undefined) continue;
        const definition = staticDefinitionFromInitializer(initializer, maps);
        if (definition !== null && !maps.has(specifier.name.text)) maps.set(specifier.name.text, definition);
      }
    }
  }
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      let initializer = declaration.initializer;
      while (initializer !== undefined && (ts.isAsExpression(initializer) || ts.isTypeAssertionExpression(initializer))) initializer = initializer.expression;
      if (!ts.isIdentifier(declaration.name) || initializer === undefined) continue;
      const staticList = staticListDefinitionFromInitializer(initializer, maps);
      if (staticList !== null) {
        maps.set(declaration.name.text, staticList);
        continue;
      }
      const staticPrimitiveList = staticPrimitiveListDefinitionFromInitializer(initializer);
      if (staticPrimitiveList !== null) {
        maps.set(declaration.name.text, staticPrimitiveList);
        continue;
      }
      const regex = regexDefinitionFromNode(initializer);
      if (regex !== null) {
        maps.set(declaration.name.text, regex);
        continue;
      }
      const definition = staticDefinitionFromInitializer(initializer, maps);
      if (definition !== null) maps.set(declaration.name.text, definition);
    }
  }
  for (const statement of sourceFile.statements) {
    if (!ts.isFunctionDeclaration(statement)) continue;
    const definition = pureFunctionDefinitionFromNode(statement);
    if (definition !== null && statement.name !== undefined) maps.set(statement.name.text, definition);
  }
  return maps;
}

/**
 * Build a real TypeScript program for repository-scale parsing.  A single
 * file parser cannot resolve `import type { Foo } from ...`; using the
 * checker here resolves that exact symbol graph while keeping the source
 * parser and the generated IR deterministic.
 */
export function createReactProjectContext(repository: string): ReactProjectContext {
  const root = path.resolve(repository);
  const configPath = ts.findConfigFile(root, ts.sys.fileExists, "tsconfig.json");
  if (configPath !== undefined) {
    const read = ts.readConfigFile(configPath, ts.sys.readFile);
    require_(!read.error, "CERTIFIED_COMPONENT_PROJECT_CONFIG_INVALID", `could not read ${configPath}`);
    const parsed = ts.parseJsonConfigFileContent(read.config, ts.sys, path.dirname(configPath), undefined, configPath);
    return createProjectFromConfig(parsed);
  }
  const files = ts.sys.readDirectory(root, [".ts", ".tsx"], ["node_modules", ".next", "dist", "build"], undefined);
  return createProjectFromConfig({
    fileNames: files,
    options: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, jsx: ts.JsxEmit.ReactJSX, strict: true },
    errors: [],
  });
}

function createProjectFromConfig(config: ts.ParsedCommandLine): ReactProjectContext {
  const program = ts.createProgram({ rootNames: config.fileNames, options: config.options });
  return { program, checker: program.getTypeChecker() };
}

function isNullishType(type: ts.Type): boolean {
  return (type.flags & (ts.TypeFlags.Null | ts.TypeFlags.Undefined)) !== 0;
}

function primitiveShape(primitive: PrimitiveType, nullable = false): ValueShape {
  return nullable ? { kind: "primitive", primitive, nullable: true } : { kind: "primitive", primitive };
}

/** Convert a checker type to the closed structural shape understood by all
 * emitters.  Literal unions intentionally collapse to their primitive domain
 * ("READY" | "BLOCKED" is still a string at the component boundary); unions
 * with incompatible object layouts remain blocked rather than becoming any.
 */
function valueShapeFromChecker(
  type: ts.Type,
  checker: ts.TypeChecker,
  location: ts.Node,
  what: string,
  seen = new Set<ts.Type>(),
): ValueShape {
  const union = type.isUnion() ? type.types : [type];
  const nullable = union.some(isNullishType);
  const members = union.filter((member) => !isNullishType(member));
  require_(members.length > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} is null/undefined only`);
  const first = at(members, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has no usable type`);

  const primitive = (flag: ts.TypeFlags, value: PrimitiveType): boolean => members.every((member) => (member.flags & flag) !== 0 ||
    (value === "string" && (member.flags & ts.TypeFlags.StringLiteral) !== 0) ||
    (value === "number" && (member.flags & ts.TypeFlags.NumberLiteral) !== 0) ||
    (value === "boolean" && (member.flags & ts.TypeFlags.BooleanLiteral) !== 0));
  if (primitive(ts.TypeFlags.StringLike, "string")) return primitiveShape("string", nullable);
  if (primitive(ts.TypeFlags.NumberLike, "number")) return primitiveShape("number", nullable);
  if (primitive(ts.TypeFlags.BooleanLike, "boolean")) return primitiveShape("boolean", nullable);

  require_(!seen.has(first), "CERTIFIED_COMPONENT_RECURSIVE_TYPE", `${what} is recursively defined`);
  const nextSeen = new Set(seen);
  nextSeen.add(first);

  if (members.every((member) => checker.isArrayType(member) || checker.isTupleType(member))) {
    const elementTypes = members.flatMap((member) => checker.getTypeArguments(member as ts.TypeReference));
    const element = valueShapeFromChecker(at(elementTypes, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} array has no element type`), checker, location, `${what} element`, nextSeen);
    return { kind: "array", element, ...(nullable ? { nullable: true } : {}) };
  }

  require_(members.every((member) => (member.flags & (ts.TypeFlags.Object | ts.TypeFlags.Intersection)) !== 0),
    "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${JSON.stringify(checker.typeToString(type, location, ts.TypeFormatFlags.NoTruncation))}`);
  const layouts = members.map((member) => checker.getPropertiesOfType(member));
  const firstLayout = at(layouts, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has no object fields`);
  const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
  for (const symbol of firstLayout) {
    const fieldName = symbol.getName();
    require_(IDENTIFIER_RE.test(fieldName), "CERTIFIED_COMPONENT_UNSUPPORTED_IDENTIFIER", `${what} field ${JSON.stringify(fieldName)} is not a plain identifier`);
    const fieldType = checker.getTypeOfSymbolAtLocation(symbol, location);
    fields[fieldName] = {
      shape: valueShapeFromChecker(fieldType, checker, location, `${what}.${fieldName}`, nextSeen),
      optional: (symbol.flags & ts.SymbolFlags.Optional) !== 0 || fieldType.isUnion() && fieldType.types.some(isNullishType),
    };
  }
  for (const layout of layouts.slice(1)) {
    require_(layout.length === firstLayout.length && layout.every((symbol) => fields[symbol.getName()] !== undefined),
      "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has incompatible union object shapes`);
  }
  require_(Object.keys(fields).length > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has no object fields`);
  return { kind: "object", fields, ...(nullable ? { nullable: true } : {}) };
}

const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

function shapeFromTypeNode(
  node: ts.TypeNode | undefined,
  what: string,
  localTypes: LocalTypes,
  resolving: ReadonlySet<string> = new Set(),
): ValueShape {
  if (!node) fail("CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`);
  const text = node.getText();
  if (text === "string" || text === "number" || text === "boolean") return { kind: "primitive", primitive: text };
  if (ts.isLiteralTypeNode(node)) {
    if (ts.isStringLiteral(node.literal)) return { kind: "primitive", primitive: "string" };
    if (ts.isNumericLiteral(node.literal)) return { kind: "primitive", primitive: "number" };
    if (node.literal.kind === ts.SyntaxKind.TrueKeyword || node.literal.kind === ts.SyntaxKind.FalseKeyword) return { kind: "primitive", primitive: "boolean" };
  }
  if (ts.isParenthesizedTypeNode(node)) return shapeFromTypeNode(node.type, what, localTypes, resolving);
  if (ts.isTypeOperatorNode(node) && node.operator === ts.SyntaxKind.ReadonlyKeyword) return shapeFromTypeNode(node.type, what, localTypes, resolving);
  if (ts.isArrayTypeNode(node)) return { kind: "array", element: shapeFromTypeNode(node.elementType, `${what} element`, localTypes, resolving) };
  if (ts.isTypeReferenceNode(node) && ts.isIdentifier(node.typeName)) {
    const name = node.typeName.text;
    if ((name === "Array" || name === "ReadonlyArray") && node.typeArguments?.length === 1) {
      return { kind: "array", element: shapeFromTypeNode(node.typeArguments[0], `${what} element`, localTypes, resolving) };
    }
    const resolved = localTypes.get(name);
    if (resolved !== undefined) {
      require_(!resolving.has(name), "CERTIFIED_COMPONENT_RECURSIVE_TYPE", `${what} resolves recursively through ${name}`);
      return shapeFromTypeNode(resolved, what, localTypes, new Set([...resolving, name]));
    }
  }
  if (ts.isIndexedAccessTypeNode(node) && ts.isTypeReferenceNode(node.objectType)
    && ts.isIdentifier(node.objectType.typeName) && ts.isLiteralTypeNode(node.indexType)
    && ts.isStringLiteral(node.indexType.literal)) {
    const owner = node.objectType.typeName.text;
    const resolved = localTypes.get(owner);
    require_(resolved !== undefined && ts.isTypeLiteralNode(resolved), "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} cannot resolve indexed owner ${owner}`);
    const fieldName = node.indexType.literal.text;
    const member = resolved.members.find((candidate): candidate is ts.PropertySignature =>
      ts.isPropertySignature(candidate) && candidate.name !== undefined
        && (ts.isIdentifier(candidate.name) || ts.isStringLiteral(candidate.name))
        && candidate.name.text === fieldName);
    require_(member !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} cannot resolve ${owner}[${JSON.stringify(fieldName)}]`);
    const shape = shapeFromTypeNode(member.type, what, localTypes, new Set([...resolving, owner]));
    return member.questionToken === undefined ? shape : { ...shape, nullable: true };
  }
  if (ts.isUnionTypeNode(node)) {
    const isNullish = (member: ts.TypeNode): boolean => member.kind === ts.SyntaxKind.NullKeyword
      || member.kind === ts.SyntaxKind.UndefinedKeyword
      || ts.isLiteralTypeNode(member) && member.literal.kind === ts.SyntaxKind.NullKeyword;
    const nonNull = node.types.filter((member) => !isNullish(member));
    const nullable = nonNull.length !== node.types.length;
    const first = at(nonNull, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} is null/undefined only`);
    const shape = shapeFromTypeNode(first, what, localTypes, resolving);
    for (const member of nonNull.slice(1)) {
      const candidate = shapeFromTypeNode(member, what, localTypes, resolving);
      require_(JSON.stringify(candidate) === JSON.stringify(shape), "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has incompatible union member shapes`);
    }
    return nullable ? { ...shape, nullable: true } : shape;
  }
  if (ts.isTypeLiteralNode(node)) {
    const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
    for (const member of node.members) {
      require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `${what} must contain plain property signatures`);
      fields[member.name.text] = { shape: shapeFromTypeNode(member.type, `${what}.${member.name.text}`, localTypes, resolving), optional: member.questionToken !== undefined };
    }
    require_(Object.keys(fields).length > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has no object fields`);
    return { kind: "object", fields };
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} has unsupported type ${JSON.stringify(text)}`);
}

function primitiveFromShape(shape: ValueShape, what: string): PrimitiveType {
  require_(shape.kind === "primitive", "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} must be a primitive type`);
  return shape.primitive;
}

/**
 * Reads an array-typed prop annotation into a canonical list element shape.
 * Accepts `T[]` and `Array<T>` where `T` is a primitive or an object whose
 * fields retain their bounded structural shapes.
 */
export function listElementFromArrayType(node: ts.TypeNode, what: string): ListElementShape {
  let element: ts.TypeNode | undefined;
  if (ts.isArrayTypeNode(node)) element = node.elementType;
  else if (ts.isTypeReferenceNode(node) && node.typeName.getText() === "Array") element = node.typeArguments?.[0];
  if (element === undefined) fail("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} is not an array type`);

  if (ts.isTypeLiteralNode(element)) {
    const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
    for (const member of element.members) {
      require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}: list element type must contain plain property signatures`);
      const fieldName = (member.name as ts.Identifier).text;
      const fieldType = requireDefined(member.type, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}.${fieldName} is missing a type`);
      const shape = shapeFromTypeNode(fieldType, `${what}.${fieldName}`, new Map());
      fields[fieldName] = { shape, optional: member.questionToken !== undefined || shape.nullable === true };
    }
    return { kind: "object", fields };
  }
  return { kind: "primitive", primitive: primitiveTypeFromNode(element, `${what} element`) };
}

export function isArrayTypeNode(node: ts.TypeNode): boolean {
  return ts.isArrayTypeNode(node) || (ts.isTypeReferenceNode(node) && node.typeName.getText() === "Array");
}

function listElementFromShape(shape: ValueShape, what: string): ListElementShape {
  require_(shape.kind === "array", "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} is not an array type`);
  const element = shape.element;
  if (element.kind === "primitive") return { kind: "primitive", primitive: element.primitive };
  require_(element.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}: list elements must be a primitive or a bounded object shape`);
  const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
  for (const [name, field] of Object.entries(element.fields)) {
    fields[name] = { shape: field.shape, optional: field.optional || field.shape.nullable === true };
  }
  return { kind: "object", fields };
}

function listElementFromChecker(
  type: ts.Type,
  checker: ts.TypeChecker,
  location: ts.Node,
  what: string,
): ListElementShape {
  return listElementFromShape(valueShapeFromChecker(type, checker, location, what), what);
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

function inferredKeyFieldOrUndefined(element: ListElementShape, what: string): string | undefined {
  try {
    return inferKeyField(element, what);
  } catch (error) {
    if (error instanceof DialectError && error.code === "CERTIFIED_COMPONENT_MISSING_LIST_KEY") return undefined;
    throw error;
  }
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
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return { type: "string", value: node.text };
  if (ts.isNumericLiteral(node)) return { type: "number", value: Number(node.text) };
  if (node.kind === ts.SyntaxKind.NullKeyword) return { type: "null" };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { type: "boolean", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { type: "boolean", value: false };
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `expression of kind ${ts.SyntaxKind[node.kind]} is not a plain literal`);
}

/** Fold exactly one deterministic date expression used by immutable fallback
 * state.  `new Date(0).toISOString()` has a fixed result independent of the
 * host timezone; other Date constructors and methods remain outside the
 * portable expression subset. */
function fixedDateIsoLiteral(node: ts.Expression): Literal | null {
  const call = unwrapStaticValue(node);
  if (!ts.isCallExpression(call) || call.arguments.length !== 0 || !ts.isPropertyAccessExpression(call.expression) || call.expression.name.text !== "toISOString") return null;
  const receiver = unwrapStaticValue(call.expression.expression);
  if (!ts.isNewExpression(receiver) || !ts.isIdentifier(receiver.expression) || receiver.expression.text !== "Date" || receiver.arguments?.length !== 1) return null;
  const epoch = receiver.arguments[0];
  if (epoch === undefined || !ts.isNumericLiteral(epoch) || Number(epoch.text) !== 0) return null;
  return { type: "string", value: "1970-01-01T00:00:00.000Z" };
}

/** A module-level value may be reused as state only when its complete tree is
 * made of literals.  This deliberately rejects spreads, calls, identifiers,
 * getters and computed properties: resolving a name must never turn a
 * dynamic module initializer into portable state by accident. */
function isClosedStaticValue(node: ts.Expression): boolean {
  const value = unwrapStaticValue(node);
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value) || ts.isNumericLiteral(value)
    || value.kind === ts.SyntaxKind.TrueKeyword || value.kind === ts.SyntaxKind.FalseKeyword || value.kind === ts.SyntaxKind.NullKeyword) return true;
  if (ts.isArrayLiteralExpression(value)) return value.elements.every((item) => isClosedStaticValue(item as ts.Expression));
  if (!ts.isObjectLiteralExpression(value)) return false;
  return value.properties.every((property) => ts.isPropertyAssignment(property)
    && (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name))
    && isClosedStaticValue(property.initializer));
}

function staticStringMapFromInitializer(initializer: ts.Expression): ReadonlyMap<string, StaticStringMapValue> | null {
  const value = unwrapStaticValue(initializer);
  if (!ts.isObjectLiteralExpression(value)) return null;
  const entries = new Map<string, StaticStringMapValue>();
  for (const property of value.properties) {
    if (!ts.isPropertyAssignment(property)) return null;
    const key = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) ? property.name.text : null;
    if (key === null || entries.has(key)) return null;
    if (ts.isStringLiteral(property.initializer)) {
      entries.set(key, property.initializer.text);
      continue;
    }
    if (!ts.isObjectLiteralExpression(property.initializer)) return null;
    const fields = new Map<string, string>();
    for (const field of property.initializer.properties) {
      if (!ts.isPropertyAssignment(field) || !(ts.isIdentifier(field.name) || ts.isStringLiteral(field.name)) || !ts.isStringLiteral(field.initializer)) return null;
      fields.set(field.name.text, field.initializer.text);
    }
    if (fields.size === 0) return null;
    entries.set(key, fields);
  }
  return entries.size === 0 ? null : entries;
}

function staticDefinitionFromInitializer(initializer: ts.Expression, staticMaps: StaticStringMaps = new Map()): StaticDefinition | null {
  const staticList = staticListDefinitionFromInitializer(initializer, staticMaps);
  if (staticList !== null) return staticList;
  const staticPrimitiveList = staticPrimitiveListDefinitionFromInitializer(initializer);
  if (staticPrimitiveList !== null) return staticPrimitiveList;
  const regex = regexDefinitionFromNode(initializer);
  if (regex !== null) return regex;
  const stringMap = staticStringMapFromInitializer(initializer);
  if (stringMap !== null) {
    const evaluatedMap = staticConstantFromExpression(initializer, new Map(), staticMaps);
    return evaluatedMap === null
      ? { kind: "closed-value", initializer, stringMap }
      : { kind: "closed-value", initializer, stringMap, value: staticConstantToExpr(evaluatedMap) };
  }
  const evaluated = staticConstantFromExpression(initializer, new Map(), staticMaps);
  if (evaluated !== null) return { kind: "closed-value", initializer, value: staticConstantToExpr(evaluated) };
  if (!isClosedStaticValueWithReferences(initializer, staticMaps)) return null;
  return { kind: "closed-value", initializer };
}

function importedValueDeclaration(
  specifier: ts.ImportSpecifier,
  project: ReactProjectContext | undefined,
): ts.VariableDeclaration | undefined {
  if (project === undefined) return undefined;
  const localSymbol = project.checker.getSymbolAtLocation(specifier.name);
  if (localSymbol === undefined) return undefined;
  const symbol = localSymbol.flags & ts.SymbolFlags.Alias
    ? project.checker.getAliasedSymbol(localSymbol)
    : localSymbol;
  return symbol.valueDeclaration && ts.isVariableDeclaration(symbol.valueDeclaration)
    ? symbol.valueDeclaration
    : symbol.declarations?.find((declaration): declaration is ts.VariableDeclaration => ts.isVariableDeclaration(declaration));
}

/** Parse only immutable object/array literals for a state initializer.  A
 * state initializer is allowed to be structured, but it may not execute an
 * import, call a helper, read a prop, or contain a spread.  That boundary is
 * what makes the new state shape portable rather than a disguised `any`. */
function closedStateValue(node: ts.Expression, staticMaps: StaticStringMaps): Literal | Expr {
  const value = unwrapStaticValue(node);
  const fixedDate = fixedDateIsoLiteral(value);
  if (fixedDate !== null) return fixedDate;
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value) || ts.isNumericLiteral(value)
    || value.kind === ts.SyntaxKind.TrueKeyword || value.kind === ts.SyntaxKind.FalseKeyword || value.kind === ts.SyntaxKind.NullKeyword) {
    return anyLiteralFromNode(value);
  }
  if (ts.isArrayLiteralExpression(value)) {
    return {
      kind: "arrayLiteral",
      items: value.elements.map((item) => {
        const itemValue = closedStateValue(item as ts.Expression, staticMaps);
        return "kind" in itemValue ? itemValue : { kind: "literal", literal: itemValue };
      }),
    };
  }
  if (ts.isObjectLiteralExpression(value)) {
    const fields: { name: string; value: Expr }[] = [];
    for (const property of value.properties) {
      require_(ts.isPropertyAssignment(property), "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "state object initializers may only contain explicit property assignments");
      const name = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) ? property.name.text : null;
      require_(name !== null, "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "state object initializer fields must have plain names");
      require_(!fields.some((field) => field.name === name), "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `state object initializer repeats field ${JSON.stringify(name)}`);
      const fieldValue = closedStateValue(property.initializer, staticMaps);
      fields.push({ name, value: "kind" in fieldValue ? fieldValue : { kind: "literal", literal: fieldValue } });
    }
    require_(fields.length > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", "state object initializer must contain at least one field");
    return { kind: "objectLiteral", fields };
  }
  if (ts.isIdentifier(value)) {
    const definition = staticMaps.get(value.text);
    if (definition !== undefined && isStaticClosedValueDefinition(definition)) {
      if (definition.value !== undefined) return definition.value;
      return closedStateValue(definition.initializer, staticMaps);
    }
    if (definition !== undefined && isStaticListDefinition(definition)) {
      return {
        kind: "arrayLiteral",
        items: definition.items.map((item) => ({
          kind: "objectLiteral",
          fields: Object.entries(item.fields).map(([name, literal]) => ({ name, value: { kind: "literal", literal } })),
        })),
      };
    }
    if (definition !== undefined && isStaticPrimitiveListDefinition(definition)) {
      return { kind: "arrayLiteral", items: definition.values.map((literal) => ({ kind: "literal", literal })) };
    }
  }
  // Keep the argument in the diagnostic path rather than allowing parseExpr
  // to admit a readable identifier or call by accident.
  void staticMaps;
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `state initializer expression kind ${ts.SyntaxKind[value.kind]} is not a closed literal`);
}

function staticLookupExpression(table: ReadonlyMap<string, string>, key: Expr): Expr {
  let result: Expr = { kind: "literal", literal: { type: "null" } };
  for (const [name, value] of [...table.entries()].reverse()) {
    result = {
      kind: "ternary",
      condition: { kind: "binary", operator: "==", left: key, right: { kind: "literal", literal: { type: "string", value: name } } },
      then: { kind: "literal", literal: { type: "string", value } },
      else: result,
    };
  }
  return result;
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
  [ts.SyntaxKind.QuestionQuestionToken]: "??",
};

function isEventTargetValue(node: ts.Expression, eventParameter: string | undefined): boolean {
  return eventParameter !== undefined
    && ts.isPropertyAccessExpression(node)
    && node.name.text === "value"
    && ts.isPropertyAccessExpression(node.expression)
    && node.expression.name.text === "target"
    && ts.isIdentifier(node.expression.expression)
    && node.expression.expression.text === eventParameter;
}

function substitutePureFunctionParameters(expr: Expr, substitutions: ReadonlyMap<string, Expr>): Expr {
  if (expr.kind === "ident") return substitutions.get(expr.name) ?? expr;
  if (expr.kind === "binary") return { kind: "binary", operator: expr.operator, left: substitutePureFunctionParameters(expr.left, substitutions), right: substitutePureFunctionParameters(expr.right, substitutions) };
  if (expr.kind === "unaryNot") return { kind: "unaryNot", operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "stringMethod") return { kind: "stringMethod", method: expr.method, receiver: substitutePureFunctionParameters(expr.receiver, substitutions), args: expr.args.map((arg) => substitutePureFunctionParameters(arg, substitutions)) };
  if (expr.kind === "numericFunction") return { kind: "numericFunction", function: expr.function, args: expr.args.map((arg) => substitutePureFunctionParameters(arg, substitutions)) };
  if (expr.kind === "numericPredicate") return { kind: "numericPredicate", predicate: expr.predicate, operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "numberMethod") return { kind: "numberMethod", method: expr.method, receiver: substitutePureFunctionParameters(expr.receiver, substitutions), fractionDigits: expr.fractionDigits };
  if (expr.kind === "numberFormat") return { kind: "numberFormat", format: expr.format, ...(expr.locale === undefined ? {} : { locale: expr.locale }), operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "regexTest") return { kind: "regexTest", pattern: expr.pattern, flags: expr.flags, operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "arrayLength") return { kind: "arrayLength", operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "percentageWidth") return { kind: "percentageWidth", value: substitutePureFunctionParameters(expr.value, substitutions) };
  if (expr.kind === "styleObject") return { kind: "styleObject", fields: expr.fields.map((field) => ({ ...field, value: substitutePureFunctionParameters(field.value, substitutions) })) };
  if (expr.kind === "collectionFilter") return { kind: "collectionFilter", source: substitutePureFunctionParameters(expr.source, substitutions), itemName: expr.itemName, predicate: substitutePureFunctionParameters(expr.predicate, substitutions) };
  if (expr.kind === "collectionMap") return { kind: "collectionMap", source: substitutePureFunctionParameters(expr.source, substitutions), itemName: expr.itemName, projection: substitutePureFunctionParameters(expr.projection, substitutions) };
  if (expr.kind === "collectionReduce") return { kind: "collectionReduce", source: substitutePureFunctionParameters(expr.source, substitutions), accumulatorName: expr.accumulatorName, itemName: expr.itemName, reducer: substitutePureFunctionParameters(expr.reducer, substitutions), initial: substitutePureFunctionParameters(expr.initial, substitutions) };
  if (expr.kind === "collectionMax") return { kind: "collectionMax", source: substitutePureFunctionParameters(expr.source, substitutions), itemName: expr.itemName, operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "collectionJoin") return { kind: "collectionJoin", source: substitutePureFunctionParameters(expr.source, substitutions), separator: substitutePureFunctionParameters(expr.separator, substitutions) };
  if (expr.kind === "objectLookup") return { kind: "objectLookup", object: substitutePureFunctionParameters(expr.object, substitutions), key: substitutePureFunctionParameters(expr.key, substitutions) };
  if (expr.kind === "objectLiteral") return { kind: "objectLiteral", fields: expr.fields.map((field) => ({ name: field.name, value: substitutePureFunctionParameters(field.value, substitutions) })), ...(expr.computedFields === undefined ? {} : { computedFields: expr.computedFields.map((field) => ({ key: substitutePureFunctionParameters(field.key, substitutions), value: substitutePureFunctionParameters(field.value, substitutions) })) }) };
  if (expr.kind === "arrayLiteral") return { kind: "arrayLiteral", items: expr.items.map((item) => substitutePureFunctionParameters(item, substitutions)) };
  if (expr.kind === "ternary") return { kind: "ternary", condition: substitutePureFunctionParameters(expr.condition, substitutions), then: substitutePureFunctionParameters(expr.then, substitutions), else: substitutePureFunctionParameters(expr.else, substitutions) };
  return expr;
}

function directCollectionSource(node: ts.Expression, what: string): ts.Expression {
  require_(ts.isIdentifier(node) || (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression)), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", `${what} source must be a declared list identifier or a field of a structured prop`);
  return node;
}

function collectionMapExpression(node: ts.CallExpression, staticMaps: StaticStringMaps, eventParameter: string | undefined, pureFunctionStack: readonly string[], bindings: ExpressionBindings = new Map()): Expr | null {
  if (!ts.isPropertyAccessExpression(node.expression) || node.expression.name.text !== "map") return null;
  const sourceNode = directCollectionSource(node.expression.expression, "map");
  require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_MAP_ARITY", "map expects exactly one callback");
  const callback = at(node.arguments, 0, "CERTIFIED_COMPONENT_MAP_CALLBACK", "map is missing its callback");
  require_(ts.isArrowFunction(callback) && callback.parameters.length === 1, "CERTIFIED_COMPONENT_MAP_CALLBACK", "map callback must be an inline arrow with exactly one item parameter");
  const parameter = at((callback as ts.ArrowFunction).parameters, 0, "CERTIFIED_COMPONENT_MAP_CALLBACK", "map callback is missing its item parameter");
  require_(ts.isIdentifier(parameter.name), "CERTIFIED_COMPONENT_MAP_CALLBACK", "map callback parameter must be a plain identifier");
  const arrow = callback as ts.ArrowFunction;
  require_(!ts.isBlock(arrow.body), "CERTIFIED_COMPONENT_MAP_CALLBACK", "map callback must return a projection expression directly");
  return {
    kind: "collectionMap",
    source: parseExpr(sourceNode, staticMaps, eventParameter, pureFunctionStack, bindings),
    itemName: parameter.name.text,
    projection: parseExpr(arrow.body as ts.Expression, staticMaps, eventParameter, pureFunctionStack, bindings),
  };
}

function collectionReduceExpression(node: ts.CallExpression, staticMaps: StaticStringMaps, eventParameter: string | undefined, pureFunctionStack: readonly string[], bindings: ExpressionBindings = new Map()): Expr | null {
  if (!ts.isPropertyAccessExpression(node.expression) || node.expression.name.text !== "reduce") return null;
  const sourceNode = directCollectionSource(node.expression.expression, "reduce");
  require_(node.arguments.length === 2, "CERTIFIED_COMPONENT_REDUCE_ARITY", "reduce requires a callback and an initial value");
  const callback = at(node.arguments, 0, "CERTIFIED_COMPONENT_REDUCE_CALLBACK", "reduce is missing its callback");
  require_(ts.isArrowFunction(callback) && callback.parameters.length === 2, "CERTIFIED_COMPONENT_REDUCE_CALLBACK", "reduce callback must have accumulator and item parameters");
  const arrow = callback as ts.ArrowFunction;
  const accumulator = at(arrow.parameters, 0, "CERTIFIED_COMPONENT_REDUCE_CALLBACK", "reduce is missing its accumulator parameter");
  const item = at(arrow.parameters, 1, "CERTIFIED_COMPONENT_REDUCE_CALLBACK", "reduce is missing its item parameter");
  require_(ts.isIdentifier(accumulator.name) && ts.isIdentifier(item.name), "CERTIFIED_COMPONENT_REDUCE_CALLBACK", "reduce parameters must be plain identifiers");
  require_(!ts.isBlock(arrow.body), "CERTIFIED_COMPONENT_REDUCE_CALLBACK", "reduce callback must return a reducer expression directly");
  return {
    kind: "collectionReduce",
    source: parseExpr(sourceNode, staticMaps, eventParameter, pureFunctionStack, bindings),
    accumulatorName: accumulator.name.text,
    itemName: item.name.text,
    reducer: parseExpr(arrow.body as ts.Expression, staticMaps, eventParameter, pureFunctionStack, bindings),
    initial: parseExpr(at(node.arguments, 1, "CERTIFIED_COMPONENT_REDUCE_INITIAL", "reduce is missing its initial value"), staticMaps, eventParameter, pureFunctionStack, bindings),
  };
}

function collectionMaxExpression(node: ts.CallExpression, staticMaps: StaticStringMaps, eventParameter: string | undefined, pureFunctionStack: readonly string[], bindings: ExpressionBindings = new Map()): Expr | null {
  if (!ts.isPropertyAccessExpression(node.expression) || !ts.isIdentifier(node.expression.expression) || node.expression.expression.text !== "Math" || node.expression.name.text !== "max") return null;
  if (node.arguments.length !== 1) return null;
  const spread = node.arguments[0];
  if (spread === undefined || !ts.isSpreadElement(spread)) return null;
  if (!ts.isCallExpression(spread.expression)) fail("CERTIFIED_COMPONENT_MAX_ARGUMENT", "Math.max collection form must spread exactly one list.map expression");
  const mapped = collectionMapExpression(spread.expression, staticMaps, eventParameter, pureFunctionStack, bindings);
  require_(mapped !== null && mapped.kind === "collectionMap", "CERTIFIED_COMPONENT_MAX_ARGUMENT", "Math.max collection form must spread exactly one list.map expression");
  return { kind: "collectionMax", source: mapped.source, itemName: mapped.itemName, operand: mapped.projection };
}

function collectionJoinExpression(node: ts.CallExpression, staticMaps: StaticStringMaps, eventParameter: string | undefined, pureFunctionStack: readonly string[], bindings: ExpressionBindings = new Map()): Expr | null {
  if (!ts.isPropertyAccessExpression(node.expression) || node.expression.name.text !== "join") return null;
  const sourceNode = node.expression.expression;
  require_(ts.isIdentifier(sourceNode)
    || (ts.isPropertyAccessExpression(sourceNode) && ts.isIdentifier(sourceNode.expression))
    || (ts.isCallExpression(sourceNode) && ts.isPropertyAccessExpression(sourceNode.expression) && ["map", "filter"].includes(sourceNode.expression.name.text)),
  "CERTIFIED_COMPONENT_JOIN_SOURCE", "join source must be a declared list or another certified derivation");
  require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_JOIN_ARITY", "join requires exactly one explicit separator");
  const separator = at(node.arguments, 0, "CERTIFIED_COMPONENT_JOIN_ARITY", "join is missing its separator");
  require_(ts.isStringLiteral(separator) || ts.isNoSubstitutionTemplateLiteral(separator), "CERTIFIED_COMPONENT_JOIN_SEPARATOR", "join separator must be a string literal");
  return {
    kind: "collectionJoin",
    source: parseExpr(sourceNode, staticMaps, eventParameter, pureFunctionStack, bindings),
    separator: { kind: "literal", literal: { type: "string", value: separator.text } },
  };
}

function parseExpr(node: ts.Expression, staticMaps: StaticStringMaps = new Map(), eventParameter?: string, pureFunctionStack: readonly string[] = [], bindings: ExpressionBindings = new Map()): Expr {
  if (ts.isParenthesizedExpression(node)) return parseExpr(node.expression, staticMaps, eventParameter, pureFunctionStack, bindings);
  if (ts.isAsExpression(node) || ts.isTypeAssertionExpression(node)) return parseExpr(node.expression, staticMaps, eventParameter, pureFunctionStack, bindings);
  const fixedDate = fixedDateIsoLiteral(node);
  if (fixedDate !== null) return { kind: "literal", literal: fixedDate };
  if (isEventTargetValue(node, eventParameter)) return { kind: "eventValue" };
  if (ts.isIdentifier(node)) {
    const bound = bindings.get(node.text);
    if (bound !== undefined) return bound;
    const definition = staticMaps.get(node.text);
    if (definition !== undefined && isStaticClosedValueDefinition(definition) && definition.value !== undefined) return definition.value;
    return { kind: "ident", name: node.text };
  }
  if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
    const functionName = node.expression.text;
    if (functionName === "useMemo") {
      require_(node.arguments.length === 2, "CERTIFIED_COMPONENT_USEMEMO_ARITY", "useMemo requires a pure callback and an explicit dependency array");
      const callback = at(node.arguments, 0, "CERTIFIED_COMPONENT_USEMEMO_CALLBACK", "useMemo is missing its callback");
      require_(ts.isArrowFunction(callback) && !callback.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.AsyncKeyword), "CERTIFIED_COMPONENT_USEMEMO_CALLBACK", "useMemo callback must be a synchronous inline arrow");
      const arrow = callback as ts.ArrowFunction;
      require_(!ts.isBlock(arrow.body), "CERTIFIED_COMPONENT_USEMEMO_CALLBACK", "useMemo callback must return one pure expression directly");
      const dependencies = at(node.arguments, 1, "CERTIFIED_COMPONENT_USEMEMO_DEPENDENCIES", "useMemo is missing its dependency array");
      require_(ts.isArrayLiteralExpression(dependencies), "CERTIFIED_COMPONENT_USEMEMO_DEPENDENCIES", "useMemo dependencies must be an explicit array literal");
      // Dependencies are parsed for the same reason the callback is parsed:
      // an effectful or otherwise unknown dependency must not disappear when
      // the memo wrapper is erased. The pure body is evaluated directly in
      // the target, so memoization itself has no observable semantics left.
      dependencies.elements.forEach((dependency) => parseExpr(dependency as ts.Expression, staticMaps, eventParameter, pureFunctionStack, bindings));
      return parseExpr(arrow.body as ts.Expression, staticMaps, eventParameter, pureFunctionStack, bindings);
    }
    const definition = staticMaps.get(functionName);
    if (definition !== undefined && isStaticNumberFormatDefinition(definition)) {
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMBER_FORMAT_ARITY", `${functionName} expects exactly one argument`);
      return { kind: "numberFormat", format: definition.format, operand: parseExpr(at(node.arguments, 0, "CERTIFIED_COMPONENT_NUMBER_FORMAT_ARITY", `${functionName} is missing its argument`), staticMaps, eventParameter, pureFunctionStack) };
    }
    if (definition !== undefined && isStaticPureFunctionDefinition(definition)) {
      require_(!pureFunctionStack.includes(functionName), "CERTIFIED_COMPONENT_RECURSIVE_PURE_FUNCTION", `pure helper ${JSON.stringify(functionName)} is recursively defined`);
      require_(node.arguments.length === definition.parameters.length, "CERTIFIED_COMPONENT_PURE_FUNCTION_ARITY", `${functionName} expects ${definition.parameters.length} argument(s)`);
      const args = node.arguments.map((argument) => parseExpr(argument, staticMaps, eventParameter, pureFunctionStack));
      const body = parseExpr(definition.body, staticMaps, eventParameter, [...pureFunctionStack, functionName]);
      const substitutions = new Map(definition.parameters.map((parameter, index) => [parameter, at(args, index, "CERTIFIED_COMPONENT_PURE_FUNCTION_ARITY", `missing argument for ${functionName}`)]));
      return substitutePureFunctionParameters(body, substitutions);
    }
  }
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
    const joined = collectionJoinExpression(node, staticMaps, eventParameter, pureFunctionStack, bindings);
    if (joined !== null) return joined;
    const mapped = collectionMapExpression(node, staticMaps, eventParameter, pureFunctionStack, bindings);
    if (mapped !== null) return mapped;
    const reduced = collectionReduceExpression(node, staticMaps, eventParameter, pureFunctionStack, bindings);
    if (reduced !== null) return reduced;
    const maximum = collectionMaxExpression(node, staticMaps, eventParameter, pureFunctionStack, bindings);
    if (maximum !== null) return maximum;
    const collection = collectionFilterExpression(node, staticMaps, eventParameter, pureFunctionStack);
    if (collection !== null) return collection;
    const methodName = node.expression.name.text;
    if (methodName === "toLocaleString") {
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMBER_FORMAT_ARITY", "toLocaleString expects one explicit locale argument");
      const locale = at(node.arguments, 0, "CERTIFIED_COMPONENT_NUMBER_FORMAT_ARITY", "toLocaleString is missing its locale argument");
      require_(ts.isStringLiteral(locale) || ts.isNoSubstitutionTemplateLiteral(locale), "CERTIFIED_COMPONENT_NUMBER_FORMAT_LOCALE", "toLocaleString locale must be a string literal");
      require_(locale.text === "zh-CN" || locale.text === "en-US", "CERTIFIED_COMPONENT_NUMBER_FORMAT_LOCALE", "toLocaleString is limited to the canonical zh-CN or en-US locales");
      return { kind: "numberFormat", format: "grouped", locale: locale.text, operand: parseExpr(node.expression.expression, staticMaps, eventParameter, pureFunctionStack, bindings) };
    }
    if (methodName === "toFixed") {
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMBER_METHOD_ARITY", "toFixed expects one numeric literal argument");
      const fractionArgument = at(node.arguments, 0, "CERTIFIED_COMPONENT_NUMBER_METHOD_ARITY", "toFixed is missing its fraction digit argument");
      require_(ts.isNumericLiteral(fractionArgument), "CERTIFIED_COMPONENT_NUMBER_METHOD_ARITY", "toFixed expects one numeric literal argument");
      const fractionDigits = Number(fractionArgument.text);
      require_(Number.isInteger(fractionDigits) && fractionDigits >= 0 && fractionDigits <= 20, "CERTIFIED_COMPONENT_NUMBER_METHOD_ARGUMENT", "toFixed fraction digits must be an integer from 0 through 20");
      return { kind: "numberMethod", method: "toFixed", receiver: parseExpr(node.expression.expression, staticMaps, eventParameter, pureFunctionStack), fractionDigits };
    }
    if (ts.isIdentifier(node.expression.expression) && node.expression.expression.text === "Math" && ["min", "max", "floor", "ceil", "abs", "round"].includes(methodName)) {
      const variadic = methodName === "min" || methodName === "max";
      require_(variadic ? node.arguments.length >= 1 && node.arguments.length <= 8 : node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMERIC_FUNCTION_ARITY", `${methodName} expects ${variadic ? "between 1 and 8" : "exactly 1"} argument(s)`);
      return {
        kind: "numericFunction",
        function: methodName as NumericFunction,
        args: node.arguments.map((argument) => parseExpr(argument, staticMaps, eventParameter, pureFunctionStack)),
      };
    }
    if (ts.isIdentifier(node.expression.expression) && node.expression.expression.text === "Number" && methodName === "isFinite") {
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_NUMERIC_PREDICATE_ARITY", "isFinite expects exactly one argument");
      return { kind: "numericPredicate", predicate: "isFinite", operand: parseExpr(at(node.arguments, 0, "CERTIFIED_COMPONENT_NUMERIC_PREDICATE_ARITY", "isFinite is missing its argument"), staticMaps, eventParameter, pureFunctionStack) };
    }
    if (methodName === "test" && ts.isIdentifier(node.expression.expression)) {
      const definition = staticMaps.get(node.expression.expression.text);
      require_(definition !== undefined && isStaticRegexDefinition(definition), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `regex test receiver ${node.expression.expression.text} is not a declared certified static regular expression`);
      const regex = definition;
      require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_REGEX_TEST_ARITY", "regex test expects one argument");
      return { kind: "regexTest", pattern: regex.pattern, flags: regex.flags, operand: parseExpr(at(node.arguments, 0, "CERTIFIED_COMPONENT_REGEX_TEST_ARITY", "regex test is missing its argument"), staticMaps, eventParameter, pureFunctionStack) };
    }
    const method = methodName as StringMethod;
    require_(["toUpperCase", "toLowerCase", "toLocaleLowerCase", "trim", "replaceAll", "includes", "startsWith", "endsWith", "slice"].includes(method), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `string method ${method} is outside certified-component-v1 in ${boundedExpression(node)}`);
    const args = node.arguments.map((argument) => parseExpr(argument, staticMaps, eventParameter, pureFunctionStack, bindings));
    const expectedArgs = method === "replaceAll" ? 2 : method === "includes" || method === "startsWith" || method === "endsWith" || method === "toLocaleLowerCase" ? 1 : method === "slice" ? 1 : 0;
    require_(method === "slice" ? args.length <= 2 && args.length >= 1 : args.length === expectedArgs, "CERTIFIED_COMPONENT_STRING_METHOD_ARITY", `${method} expects ${method === "slice" ? "one or two" : expectedArgs} argument(s)`);
    const argumentType = method === "slice" ? "number" : "string";
    require_((method !== "replaceAll" && method !== "includes" && method !== "startsWith" && method !== "endsWith" && method !== "slice" && method !== "toLocaleLowerCase") || args.every((arg) => arg.kind === "literal" && arg.literal.type === argumentType || (argumentType === "string" && arg.kind !== "literal")), "CERTIFIED_COMPONENT_STRING_METHOD_ARGUMENT", `${method} arguments must be ${argumentType} expressions`);
    return { kind: "stringMethod", method, receiver: parseExpr(node.expression.expression, staticMaps, eventParameter, pureFunctionStack), args };
  }
  if (ts.isPropertyAccessExpression(node) && ts.isElementAccessExpression(node.expression) && ts.isIdentifier(node.expression.expression)) {
    const table = staticMaps.get(node.expression.expression.text);
    const entries = staticStringMapEntries(table);
    require_(entries !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `computed access ${node.expression.getText()} is not a declared certified static string map`);
    require_(node.expression.argumentExpression !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `computed access ${node.expression.getText()} is missing its key`);
    const fieldTables = new Map<string, string>();
    for (const [key, entry] of entries.entries()) {
      require_(typeof entry !== "string", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `static map ${node.expression.expression.text} has no object field ${node.name.text}`);
      const field = entry.get(node.name.text);
      require_(field !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_PROP_FIELD", `static map ${node.expression.expression.text} has no field ${node.name.text} on ${key}`);
      fieldTables.set(key, field);
    }
    return staticLookupExpression(fieldTables, parseExpr(node.expression.argumentExpression, staticMaps));
  }
  if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression)) {
    const definition = staticMaps.get(node.expression.text);
    if (definition !== undefined && isStaticCssModuleDefinition(definition)) {
      return { kind: "cssModuleClass", className: node.name.text };
    }
    if (definition !== undefined && isStaticClosedValueDefinition(definition)) {
      const value = definition.value;
      if (value?.kind === "objectLiteral") {
        const field = value.fields.find((candidate) => candidate.name === node.name.text);
        if (field !== undefined) return field.value;
      }
    }
  }
  if (ts.isObjectLiteralExpression(node)) {
    const fields: { name: string; value: Expr }[] = [];
    const computedFields: { key: Expr; value: Expr }[] = [];
    for (const property of node.properties) {
      if (ts.isShorthandPropertyAssignment(property)) {
        require_(!fields.some((field) => field.name === property.name.text), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "object expression repeats a field");
        fields.push({ name: property.name.text, value: parseExpr(property.name, staticMaps, eventParameter, pureFunctionStack, bindings) });
        continue;
      }
      require_(ts.isPropertyAssignment(property), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "object expressions may only contain explicit property assignments");
      if (ts.isComputedPropertyName(property.name)) {
        computedFields.push({
          key: parseExpr(property.name.expression, staticMaps, eventParameter, pureFunctionStack, bindings),
          value: parseExpr(property.initializer, staticMaps, eventParameter, pureFunctionStack, bindings),
        });
        continue;
      }
      const name = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name) ? property.name.text : null;
      require_(name !== null, "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "object expression fields must have plain names or a certified computed key");
      require_(!fields.some((field) => field.name === name), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "object expression repeats a field");
      fields.push({ name, value: parseExpr(property.initializer, staticMaps, eventParameter, pureFunctionStack, bindings) });
    }
    require_(fields.length > 0 || computedFields.length > 0, "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "object expressions must contain at least one field");
    return { kind: "objectLiteral", fields, ...(computedFields.length === 0 ? {} : { computedFields }) };
  }
  if (ts.isArrayLiteralExpression(node)) {
    for (const element of node.elements) require_(!ts.isSpreadElement(element), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", "array expressions may not contain spreads");
    return { kind: "arrayLiteral", items: node.elements.map((element) => parseExpr(element as ts.Expression, staticMaps, eventParameter, pureFunctionStack, bindings)) };
  }
  if (ts.isPropertyAccessExpression(node) && node.name.text === "length") {
    return { kind: "arrayLength", operand: parseExpr(node.expression, staticMaps, eventParameter) };
  }
  if (ts.isPropertyAccessExpression(node)) {
    const fields: string[] = [];
    let current: ts.Expression = node;
    while (ts.isPropertyAccessExpression(current)) {
      fields.unshift(current.name.text);
      current = current.expression;
    }
    if (ts.isIdentifier(current) && fields.length > 1) return { kind: "path", object: current.text, fields };
  }
  if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression)) {
    // `item.name` -- validateComponent later proves `item` really is a loop
    // variable and `name` a declared field of its element shape.
    return { kind: "member", object: node.expression.text, field: node.name.text };
  }
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isNumericLiteral(node) || node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword || node.kind === ts.SyntaxKind.NullKeyword) {
    return { kind: "literal", literal: anyLiteralFromNode(node) };
  }
  if (ts.isTemplateExpression(node)) {
    let result: Expr = { kind: "literal", literal: { type: "string", value: node.head.text } };
    for (const span of node.templateSpans) {
      result = { kind: "binary", operator: "+", left: result, right: parseExpr(span.expression, staticMaps, eventParameter) };
      if (span.literal.text.length > 0) result = { kind: "binary", operator: "+", left: result, right: { kind: "literal", literal: { type: "string", value: span.literal.text } } };
    }
    return result;
  }
  if (ts.isElementAccessExpression(node) && ts.isIdentifier(node.expression) && node.argumentExpression !== undefined) {
    const table = staticMaps.get(node.expression.text);
    const entries = staticStringMapEntries(table);
    if (entries !== undefined) {
      const values = new Map<string, string>();
      for (const [key, entry] of entries.entries()) {
        require_(typeof entry === "string", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `static map ${node.expression.text} entry ${key} is an object and must select a field`);
        values.set(key, entry);
      }
      return staticLookupExpression(values, parseExpr(node.argumentExpression, staticMaps, eventParameter, pureFunctionStack, bindings));
    }
    if (table !== undefined && isStaticClosedValueDefinition(table)) {
      // A closed module object may contain immutable arrays or other closed
      // objects referenced by name. Inline that fully resolved value before
      // lowering the lookup so generated targets do not depend on a source
      // module import that the canonical component does not carry.
      const object = closedStateValue(table.initializer, staticMaps);
      require_("kind" in object, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `static value ${node.expression.text} could not be lowered to a closed object`);
      const objectExpression: Expr = "type" in object
        ? { kind: "literal", literal: object as Literal }
        : object as Expr;
      return { kind: "objectLookup", object: objectExpression, key: parseExpr(node.argumentExpression, staticMaps, eventParameter, pureFunctionStack, bindings) };
    }
    return {
      kind: "objectLookup",
      object: parseExpr(node.expression, staticMaps, eventParameter, pureFunctionStack, bindings),
      key: parseExpr(node.argumentExpression, staticMaps, eventParameter, pureFunctionStack, bindings),
    };
  }
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.ExclamationToken) {
    return { kind: "unaryNot", operand: parseExpr(node.operand, staticMaps, eventParameter) };
  }
  if (ts.isBinaryExpression(node)) {
    const op = requireDefined(BINARY_TOKEN_MAP[node.operatorToken.kind], "CERTIFIED_COMPONENT_UNSUPPORTED_OPERATOR", `operator ${ts.SyntaxKind[node.operatorToken.kind]} is outside certified-component-v1`);
    return { kind: "binary", operator: op, left: parseExpr(node.left, staticMaps, eventParameter), right: parseExpr(node.right, staticMaps, eventParameter) };
  }
  if (ts.isConditionalExpression(node)) {
    return { kind: "ternary", condition: parseExpr(node.condition, staticMaps, eventParameter), then: parseExpr(node.whenTrue, staticMaps, eventParameter), else: parseExpr(node.whenFalse, staticMaps, eventParameter) };
  }
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `expression kind ${ts.SyntaxKind[node.kind]} is outside certified-component-v1: ${boundedExpression(node)}`);
}

/** Keep failure reports actionable without copying an arbitrarily large or
 * multiline source expression into reports and logs. */
function boundedExpression(node: ts.Node): string {
  const text = node.getText().replace(/\s+/g, " ").trim();
  return JSON.stringify(text.length <= 180 ? text : `${text.slice(0, 177)}...`);
}

function collectionFilterExpression(
  node: ts.CallExpression,
  staticMaps: StaticStringMaps,
  eventParameter: string | undefined,
  pureFunctionStack: readonly string[],
): Expr | null {
  if (!ts.isPropertyAccessExpression(node.expression) || node.expression.name.text !== "filter") return null;
  require_(node.arguments.length === 1, "CERTIFIED_COMPONENT_FILTER_ARITY", "filter expects exactly one callback");
  const sourceNode = node.expression.expression;
  require_(ts.isIdentifier(sourceNode)
    || (ts.isPropertyAccessExpression(sourceNode) && ts.isIdentifier(sourceNode.expression))
    || (ts.isCallExpression(sourceNode) && ts.isPropertyAccessExpression(sourceNode.expression) && ["map", "filter"].includes(sourceNode.expression.name.text)),
  "CERTIFIED_COMPONENT_FILTER_SOURCE", "filter source must be a declared list identifier, a field of a structured prop, or another certified derivation");
  const callback = at(node.arguments, 0, "CERTIFIED_COMPONENT_FILTER_CALLBACK", "filter is missing its callback");
  require_(ts.isArrowFunction(callback), "CERTIFIED_COMPONENT_FILTER_CALLBACK", "filter callback must be an inline arrow function");
  const arrow = callback as ts.ArrowFunction;
  require_(arrow.parameters.length === 1, "CERTIFIED_COMPONENT_FILTER_CALLBACK", "filter callback must take exactly one item parameter");
  const parameter = at(arrow.parameters, 0, "CERTIFIED_COMPONENT_FILTER_CALLBACK", "filter callback is missing its item parameter");
  require_(ts.isIdentifier(parameter.name), "CERTIFIED_COMPONENT_FILTER_CALLBACK", "filter parameter must be a plain identifier");
  require_(!ts.isBlock(arrow.body), "CERTIFIED_COMPONENT_FILTER_CALLBACK", "filter callback must return a predicate expression directly");
  return {
    kind: "collectionFilter",
    source: parseExpr(sourceNode, staticMaps, eventParameter, pureFunctionStack),
    itemName: parameter.name.text,
    predicate: parseExpr(arrow.body as ts.Expression, staticMaps, eventParameter, pureFunctionStack),
  };
}

/** Parses a certified-component-v1 event handler arrow function body:
 * `() => setCount(count + 1)`, `() => setCount(!on)`,
 * `(v) => onChange(v)` -- a single expression statement, or a block of
 * such statements, each either a setState call or a callback-prop call. */
function parseHandlerBody(fn: ts.ArrowFunction, staticMaps: StaticStringMaps = new Map(), callbackNames: ReadonlySet<string> = new Set(), stateSetterNames: ReadonlyMap<string, string> = new Map()): Stmt[] {
  const parameterName = fn.parameters[0]?.name;
  const eventParameter = fn.parameters.length === 1 && parameterName !== undefined && ts.isIdentifier(parameterName)
    ? parameterName.text
    : undefined;
  const exprToStmt = (expr: ts.Expression): Stmt => {
    require_(ts.isCallExpression(expr) && ts.isIdentifier(expr.expression), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "handler statement must be a single call expression");
    const call = expr as ts.CallExpression;
    const callee = (call.expression as ts.Identifier).text;
    const boundState = stateSetterNames.get(callee);
    if (boundState !== undefined) {
      require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} must be called with exactly one argument`);
      return { kind: "setState", target: boundState, value: parseExpr(at(call.arguments, 0, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} is missing its argument`), staticMaps, eventParameter) };
    }
    const fourth = callee[3];
    if (!callbackNames.has(callee) && callee.startsWith("set") && fourth !== undefined && fourth === fourth.toUpperCase() && fourth !== fourth.toLowerCase()) {
      require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} must be called with exactly one argument`);
      const stateName = fourth.toLowerCase() + callee.slice(4);
      return { kind: "setState", target: stateName, value: parseExpr(at(call.arguments, 0, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} is missing its argument`), staticMaps, eventParameter) };
    }
    require_(/^on[A-Z]/.test(callee) || callbackNames.has(callee), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_CALL", `handler call target ${JSON.stringify(callee)} is neither a setState-style call nor a declared callback prop`);
    require_(call.arguments.length <= 1, "CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS", `${callee} is called with more than one argument`);
    return { kind: "callProp", target: callee, args: call.arguments.map((argument) => parseExpr(argument, staticMaps, eventParameter)) };
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

/** A deliberately narrow style IR.  CSS objects are otherwise a target-
 * specific styling system, but a percentage width has identical meaning in
 * every current emitter and can be represented without accepting arbitrary
 * CSS properties or platform-specific values. */
function percentageWidthExpression(node: ts.Expression, staticMaps: StaticStringMaps): Expr {
  if (ts.isStringLiteral(node)) {
    const match = /^(\d+(?:\.\d+)?)%$/u.exec(node.text);
    require_(match !== null, "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "static width must be a finite percentage such as \"45%\"");
    const value = Number(match[1]);
    require_(Number.isFinite(value) && value >= 0 && value <= 100, "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "static width percentage must be between 0 and 100");
    return { kind: "percentageWidth", value: { kind: "literal", literal: { type: "number", value } } };
  }
  require_(ts.isTemplateExpression(node), "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "certified width must be a template percentage such as `${value}%`");
  require_(node.head.text === "" && node.templateSpans.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "certified width must contain exactly one expression followed by `%`");
  const span = at(node.templateSpans, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "certified width is missing its expression");
  require_(span.literal.text === "%", "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "certified width must end with a literal `%`");
  return { kind: "percentageWidth", value: parseExpr(span.expression, staticMaps) };
}

function styleObjectExpression(node: ts.Expression, staticMaps: StaticStringMaps): Expr {
  require_(ts.isObjectLiteralExpression(node), "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "style must be a single-object percentage width binding");
  require_(node.properties.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "style must contain only the certified width property");
  const property = at(node.properties, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "style is missing its width property");
  require_(ts.isPropertyAssignment(property) && property.name.getText() === "width", "CERTIFIED_COMPONENT_UNSUPPORTED_STYLE", "style must contain a width property");
  return { kind: "styleObject", fields: [{ name: "width", value: percentageWidthExpression(property.initializer, staticMaps) }] };
}

const JSX_EVENT_PROP_TO_EVENT_NAME: Record<string, EventName> = {
  onClick: "onClick", onChange: "onChange", onInput: "onInput", onSubmit: "onSubmit",
};

function parseJsxChildren(children: ts.NodeArray<ts.JsxChild>, staticMaps: StaticStringMaps = new Map(), callbackNames: ReadonlySet<string> = new Set(), bindings: ExpressionBindings = new Map(), stateSetterNames: ReadonlyMap<string, string> = new Map()): CNode[] {
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
          condition: parseExpr(expr.condition, staticMaps, undefined, [], bindings),
          then: parseJsxNode(expr.whenTrue, staticMaps, callbackNames, bindings, stateSetterNames),
          else: expr.whenFalse.kind === ts.SyntaxKind.NullKeyword ? null : parseJsxNode(expr.whenFalse, staticMaps, callbackNames, bindings, stateSetterNames),
        });
        continue;
      }
      if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && isJsxLike(expr.right)) {
        result.push({ kind: "conditional", condition: parseExpr(expr.left, staticMaps, undefined, [], bindings), then: parseJsxNode(expr.right, staticMaps, callbackNames, bindings, stateSetterNames), else: null });
        continue;
      }
      const listNode = tryParseListExpression(expr, staticMaps, callbackNames, bindings, stateSetterNames);
      if (listNode !== null) {
        result.push(listNode);
        continue;
      }
      if (isJsxLike(expr)) {
        result.push(parseJsxNode(expr, staticMaps, callbackNames, bindings, stateSetterNames));
        continue;
      }
      result.push({ kind: "text", value: parseExpr(expr, staticMaps, undefined, [], bindings) });
      continue;
    }
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child) || ts.isJsxFragment(child)) {
      result.push(parseJsxNode(child, staticMaps, callbackNames, bindings, stateSetterNames));
      continue;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_JSX_CHILD", `JSX child kind ${ts.SyntaxKind[(child as ts.Node).kind]} is outside certified-component-v1`);
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
  return ts.isJsxElement(inner) || ts.isJsxSelfClosingElement(inner) || ts.isJsxFragment(inner);
}

/**
 * Recognizes `items.map((item) => (<li>...</li>))` as a list render node.
 *
 * Returns null (rather than failing) when the expression is not a `.map`
 * call at all, so the caller can fall through to its other JSX-child
 * cases. A `.map` call that IS present but malformed fails closed.
 */
function tryParseListExpression(expr: ts.Expression, staticMaps: StaticStringMaps = new Map(), callbackNames: ReadonlySet<string> = new Set(), bindings: ExpressionBindings = new Map(), stateSetterNames: ReadonlyMap<string, string> = new Map()): CNode | null {
  const call = unwrapParens(expr);
  if (!ts.isCallExpression(call)) return null;
  if (!ts.isPropertyAccessExpression(call.expression) || call.expression.name.text !== "map") return null;

  require_(ts.isIdentifier(call.expression.expression) || (ts.isPropertyAccessExpression(call.expression.expression) && ts.isIdentifier(call.expression.expression.expression)),
    "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", "list rendering must map directly over a declared list prop or a field of a structured prop");
  const sourceExpression = parseExpr(call.expression.expression, staticMaps);
  require_(sourceExpression.kind === "ident" || sourceExpression.kind === "member", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", "list source must be a direct identifier or object field");
  const source = sourceExpression.kind === "ident" ? sourceExpression.name : `${sourceExpression.object}.${sourceExpression.field}`;

  require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map must take exactly one callback`);
  const fn = at(call.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "missing map callback");
  require_(ts.isArrowFunction(fn), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map callback must be an inline arrow function`);
  const arrow = fn as ts.ArrowFunction;
  // An index parameter would let the body use array position as identity,
  // which reorders differently on every framework's list diffing.
  require_(arrow.parameters.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map callback must take exactly one parameter (an index parameter is outside certified-component-v1)`);
  const param = at(arrow.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", "missing map parameter");
  const staticList = sourceExpression.kind === "ident" ? staticMaps.get(sourceExpression.name) : undefined;
  let itemName: string;
  let bodyBindings = bindings;
  if (ts.isIdentifier(param.name)) {
    itemName = param.name.text;
  } else {
    require_(staticList !== undefined && isStaticListDefinition(staticList), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map destructuring is certified only for an immutable literal collection`);
    itemName = `${source}Item`;
    const nextBindings = new Map(bindings);
    if (ts.isArrayBindingPattern(param.name)) {
      for (const [index, element] of param.name.elements.entries()) {
        require_(ts.isBindingElement(element) && ts.isIdentifier(element.name) && element.propertyName === undefined && element.initializer === undefined,
          "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map tuple destructuring must bind plain names without defaults or rest elements`);
        nextBindings.set(element.name.text, { kind: "member", object: itemName, field: `item${index}` });
      }
    } else if (ts.isObjectBindingPattern(param.name)) {
      for (const element of param.name.elements) {
        require_(ts.isBindingElement(element) && ts.isIdentifier(element.name) && (element.propertyName === undefined || ts.isIdentifier(element.propertyName)) && element.initializer === undefined,
          "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map object destructuring must bind plain fields without defaults or rest elements`);
        const field = element.propertyName === undefined ? element.name.text : element.propertyName.text;
        require_(staticList.element.fields[field] !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_LIST_FIELD", `${source}.map destructuring field ${JSON.stringify(field)} is not declared on the static item`);
        nextBindings.set(element.name.text, { kind: "member", object: itemName, field });
      }
    } else {
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map parameter must be a plain identifier, tuple, or object binding pattern`);
    }
    bodyBindings = nextBindings;
  }

  require_(!ts.isBlock(arrow.body), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map callback must return JSX directly, not through a block body`);
  const body = unwrapParens(arrow.body as ts.Expression);
  let keyField: string | undefined;
  if (ts.isJsxElement(body) || ts.isJsxSelfClosingElement(body)) {
    const opening = ts.isJsxElement(body) ? body.openingElement : body;
    for (const attr of opening.attributes.properties) {
      if (!ts.isJsxAttribute(attr) || attr.name.getText() !== "key") continue;
      require_(attr.initializer !== undefined && ts.isJsxExpression(attr.initializer) && attr.initializer.expression !== undefined,
        "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must be an expression over the current item`);
      const keyExpression = (attr.initializer as ts.JsxExpression).expression as ts.Expression;
      const parsedKey = parseExpr(keyExpression, staticMaps, undefined, [], bodyBindings);
      if (parsedKey.kind === "ident") {
        require_(parsedKey.name === itemName, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must use the current item, not an unrelated identifier`);
      } else if (parsedKey.kind === "member") {
        require_(parsedKey.object === itemName, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must read a direct field from the current item`);
        keyField = parsedKey.field;
      } else {
        fail("CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must be the item itself or a direct item field; composite and index keys are not certified`);
      }
    }
  }
  return { kind: "list", source, sourceExpression: sourceExpression.kind === "ident" ? undefined : sourceExpression, itemName, ...(keyField === undefined ? {} : { keyField }), body: parseJsxNode(body, staticMaps, callbackNames, bodyBindings, stateSetterNames) };
}

function applyExplicitListKeys(root: CNode, props: PropDef[]): void {
  const lists = new Map(props.filter((prop): prop is ListPropDef => prop.kind === "list").map((prop) => [prop.name, prop]));
  const visit = (node: CNode): void => {
    if (node.kind === "fragment") {
      node.children.forEach(visit);
      return;
    }
    if (node.kind === "list") {
      if (node.keyField !== undefined) {
        const list = lists.get(node.source);
        if (list !== undefined) {
          if (list.keyField === undefined) list.keyField = node.keyField;
          else require_(list.keyField === node.keyField, "CERTIFIED_COMPONENT_CONFLICTING_LIST_KEY", `list node ${JSON.stringify(node.source)} key conflicts with the declared list key`);
          if (node.sourceExpression?.kind === "collectionFilter" && node.sourceExpression.source.kind === "ident") {
            const sourceList = lists.get(node.sourceExpression.source.name);
            if (sourceList !== undefined) {
              if (sourceList.keyField === undefined) sourceList.keyField = node.keyField;
              else require_(sourceList.keyField === node.keyField, "CERTIFIED_COMPONENT_CONFLICTING_LIST_KEY", `filtered list ${JSON.stringify(node.source)} key conflicts with its source list key`);
            }
          }
        } else {
          require_(node.sourceExpression !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_LIST_SOURCE", `list node iterates ${JSON.stringify(node.source)}, which is not a declared list prop`);
        }
      }
      visit(node.body);
      return;
    }
    if (node.kind === "conditional") {
      visit(node.then);
      if (node.else !== null) visit(node.else);
      return;
    }
    if (node.kind === "element") node.children.forEach(visit);
  };
  visit(root);
}

function materializeNestedLists(root: CNode, props: PropDef[]): ListPropDef[] {
  const derived = new Map<string, ListPropDef>();
  const visit = (node: CNode): void => {
    if (node.kind === "fragment") {
      node.children.forEach(visit);
      return;
    }
    if (node.kind === "list") {
      const sourceExpression = node.sourceExpression;
      if (sourceExpression?.kind === "member") {
        const owner = props.find((prop): prop is Extract<PropDef, { kind: "data" }> => prop.kind === "data" && prop.name === sourceExpression.object);
        const shape = owner?.valueShape;
        require_(shape?.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", `list source ${JSON.stringify(node.source)} must be a field of a structured prop`);
        const field = shape.fields[sourceExpression.field];
        require_(field?.shape.kind === "array", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE", `list source ${JSON.stringify(node.source)} must be an array field`);
        const element = listElementFromShape(field.shape, `list source ${JSON.stringify(node.source)}`);
        const existing = derived.get(node.source);
        const keyField = node.keyField ?? inferredKeyFieldOrUndefined(element, `list source ${JSON.stringify(node.source)}`);
        if (existing !== undefined) {
          require_(existing.keyField === keyField && JSON.stringify(existing.element) === JSON.stringify(element), "CERTIFIED_COMPONENT_CONFLICTING_LIST_SOURCE", `derived list source ${JSON.stringify(node.source)} is used with conflicting shapes`);
        } else {
          derived.set(node.source, { kind: "list", name: node.source, sourceExpression: node.sourceExpression, element, ...(keyField === undefined ? {} : { keyField }) });
        }
      }
      visit(node.body);
      return;
    }
    if (node.kind === "conditional") {
      visit(node.then);
      if (node.else !== null) visit(node.else);
      return;
    }
    if (node.kind === "element") node.children.forEach(visit);
  };
  visit(root);
  return [...derived.values()];
}

function materializeStaticLists(root: CNode, staticMaps: StaticStringMaps): ListPropDef[] {
  const lists = new Map<string, ListPropDef>();
  const visit = (node: CNode): void => {
    if (node.kind === "fragment") {
      node.children.forEach(visit);
      return;
    }
    if (node.kind === "list") {
      if (node.sourceExpression === undefined) {
        const definition = staticMaps.get(node.source);
        if (definition !== undefined && isStaticListDefinition(definition)) {
          const existing = lists.get(node.source);
          const keyField = node.keyField;
          if (existing !== undefined) {
            require_(JSON.stringify(existing.element) === JSON.stringify(definition.element), "CERTIFIED_COMPONENT_CONFLICTING_LIST_SOURCE", `static list source ${JSON.stringify(node.source)} is used with conflicting element shapes`);
            require_(existing.keyField === undefined || keyField === undefined || existing.keyField === keyField, "CERTIFIED_COMPONENT_CONFLICTING_LIST_KEY", `static list source ${JSON.stringify(node.source)} is used with conflicting keys`);
          } else {
            lists.set(node.source, { kind: "list", name: node.source, element: definition.element, staticItems: definition.items, ...(keyField === undefined ? {} : { keyField }) });
          }
        }
      }
      visit(node.body);
      return;
    }
    if (node.kind === "conditional") {
      visit(node.then);
      if (node.else !== null) visit(node.else);
      return;
    }
    if (node.kind === "element") node.children.forEach(visit);
  };
  visit(root);
  return [...lists.values()];
}

/** Promote immutable module-level collections used only as pure derivation
 * sources. A `.map`/`.filter` expression is still validated as a list
 * operation, so the generated target must receive the exact source values even
 * when the source is not itself rendered by a list node. */
function materializeStaticExpressionLists(root: CNode, staticMaps: StaticStringMaps): ListPropDef[] {
  const lists = new Map<string, ListPropDef>();
  const addSource = (source: Expr): void => {
    if (source.kind === "ident") {
      const definition = staticMaps.get(source.name);
      if (definition !== undefined && isStaticListDefinition(definition)) {
        lists.set(source.name, { kind: "list", name: source.name, element: definition.element, staticItems: definition.items });
      } else if (definition !== undefined && isStaticPrimitiveListDefinition(definition)) {
        lists.set(source.name, { kind: "list", name: source.name, element: definition.element, staticValues: definition.values });
      }
      return;
    }
    if (source.kind === "collectionFilter" || source.kind === "collectionMap" || source.kind === "collectionReduce" || source.kind === "collectionMax") addSource(source.source);
  };
  const visitExpr = (expr: Expr): void => {
    if (expr.kind === "collectionFilter") { addSource(expr.source); visitExpr(expr.source); visitExpr(expr.predicate); return; }
    if (expr.kind === "collectionMap") { addSource(expr.source); visitExpr(expr.source); visitExpr(expr.projection); return; }
    if (expr.kind === "collectionReduce") { addSource(expr.source); visitExpr(expr.source); visitExpr(expr.reducer); visitExpr(expr.initial); return; }
    if (expr.kind === "collectionMax") { addSource(expr.source); visitExpr(expr.source); visitExpr(expr.operand); return; }
    if (expr.kind === "objectLookup") { visitExpr(expr.object); visitExpr(expr.key); return; }
    if (expr.kind === "objectLiteral") {
      expr.fields.forEach((field) => visitExpr(field.value));
      (expr.computedFields ?? []).forEach((field) => { visitExpr(field.key); visitExpr(field.value); });
      return;
    }
    if (expr.kind === "arrayLiteral") { expr.items.forEach(visitExpr); return; }
    if (expr.kind === "binary") { visitExpr(expr.left); visitExpr(expr.right); return; }
    if (expr.kind === "unaryNot" || expr.kind === "arrayLength" || expr.kind === "numericPredicate" || expr.kind === "numberFormat" || expr.kind === "percentageWidth") {
      visitExpr(expr.kind === "unaryNot" || expr.kind === "arrayLength" || expr.kind === "numericPredicate" ? expr.operand : expr.kind === "numberFormat" ? expr.operand : expr.value);
      return;
    }
    if (expr.kind === "stringMethod") { visitExpr(expr.receiver); expr.args.forEach(visitExpr); return; }
    if (expr.kind === "numericFunction") { expr.args.forEach(visitExpr); return; }
    if (expr.kind === "numberMethod") { visitExpr(expr.receiver); return; }
    if (expr.kind === "regexTest") { visitExpr(expr.operand); return; }
    if (expr.kind === "styleObject") { expr.fields.forEach((field) => visitExpr(field.value)); return; }
    if (expr.kind === "ternary") { visitExpr(expr.condition); visitExpr(expr.then); visitExpr(expr.else); }
  };
  const visit = (node: CNode): void => {
    if (node.kind === "fragment") { node.children.forEach(visit); return; }
    if (node.kind === "text") { visitExpr(node.value); return; }
    if (node.kind === "conditional") { visitExpr(node.condition); visit(node.then); if (node.else !== null) visit(node.else); return; }
    if (node.kind === "list") { if (node.sourceExpression !== undefined) visitExpr(node.sourceExpression); visit(node.body); return; }
    if (node.kind === "component") { node.props.forEach((prop) => visitExpr(prop.value)); return; }
    node.attrs.forEach((attr) => { if (attr.kind === "dynamic") visitExpr(attr.value); });
    node.events.forEach((event) => event.body.forEach((statement) => statement.kind === "setState" ? visitExpr(statement.value) : statement.args.forEach(visitExpr)));
    node.children.forEach(visit);
  };
  visit(root);
  return [...lists.values()];
}

/** Promote only state arrays that are actually rendered through `.map` to
 * list contracts.  This keeps arrays useful as state without making every
 * object/array state implicitly iterable or silently inventing keys. */
function materializeStateLists(root: CNode, state: readonly StateDef[]): ListPropDef[] {
  const byName = new Map(state.map((item) => [item.name, item]));
  const lists = new Map<string, ListPropDef>();
  const visit = (node: CNode): void => {
    if (node.kind === "fragment") { node.children.forEach(visit); return; }
    if (node.kind === "list") {
      if (node.sourceExpression === undefined) {
        const stateDef = byName.get(node.source);
        const shape = stateDef?.stateShape;
        if (shape?.kind === "array") {
          const element = listElementFromShape(shape, `state list source ${JSON.stringify(node.source)}`);
          const keyField = node.keyField ?? inferredKeyFieldOrUndefined(element, `state list source ${JSON.stringify(node.source)}`);
          const existing = lists.get(node.source);
          if (existing !== undefined) {
            require_(JSON.stringify(existing.element) === JSON.stringify(element) && (existing.keyField === undefined || keyField === undefined || existing.keyField === keyField), "CERTIFIED_COMPONENT_CONFLICTING_LIST_SOURCE", `state list source ${JSON.stringify(node.source)} is used with conflicting shapes or keys`);
          } else {
            lists.set(node.source, { kind: "list", name: node.source, element, ...(keyField === undefined ? {} : { keyField }) });
          }
        }
      }
      visit(node.body);
      return;
    }
    if (node.kind === "conditional") { visit(node.then); if (node.else !== null) visit(node.else); return; }
    if (node.kind === "element") node.children.forEach(visit);
  };
  visit(root);
  return [...lists.values()];
}

function parseJsxNode(rawNode: ts.Expression, staticMaps: StaticStringMaps = new Map(), callbackNames: ReadonlySet<string> = new Set(), bindings: ExpressionBindings = new Map(), stateSetterNames: ReadonlyMap<string, string> = new Map()): CNode {
  const node = unwrapParens(rawNode);
  if (ts.isJsxFragment(node)) return { kind: "fragment", children: parseJsxChildren(node.children, staticMaps, callbackNames, bindings, stateSetterNames) };
  require_(ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node), "CERTIFIED_COMPONENT_UNSUPPORTED_JSX_NODE", `expected a JSX element, got ${ts.SyntaxKind[node.kind]}`);
  const opening = ts.isJsxElement(node) ? node.openingElement : node;
  const tagName = opening.tagName.getText();

  // Next.js Link is a navigation primitive, not a data-bearing child
  // component.  Lower only the exact `next/link` import to the canonical
  // anchor node so all targets retain the destination and visible children;
  // arbitrary slot projection remains blocked below.
  const navigation = staticMaps.get(tagName);
  if (navigation !== undefined && isStaticNavigationDefinition(navigation)) {
    const attrs: AttrBinding[] = [];
    for (const attr of opening.attributes.properties) {
      require_(ts.isJsxAttribute(attr), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", "spread attributes are outside certified-component-v1");
      const jsxAttr = attr as ts.JsxAttribute;
      const rawName = jsxAttr.name.getText();
      if (rawName === "key") continue;
      const attrName = jsxAttrName(rawName);
      require_(attrName === "href" || attrName === "class" || attrName === "id" || attrName.startsWith("aria-") || attrName.startsWith("data-"), "CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `navigation Link attribute ${JSON.stringify(rawName)} is outside the canonical anchor contract`);
      if (jsxAttr.initializer === undefined) attrs.push({ kind: "static", name: attrName, value: "true" });
      else if (ts.isStringLiteral(jsxAttr.initializer)) attrs.push({ kind: "static", name: attrName, value: jsxAttr.initializer.text });
      else if (ts.isJsxExpression(jsxAttr.initializer) && jsxAttr.initializer.expression) attrs.push({ kind: "dynamic", name: attrName, value: parseExpr(jsxAttr.initializer.expression, staticMaps, undefined, [], bindings) });
      else fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `navigation Link attribute ${JSON.stringify(rawName)} has an unsupported value shape`);
    }
    return { kind: "element", tag: "a", attrs, events: [], children: ts.isJsxElement(node) ? parseJsxChildren(node.children, staticMaps, callbackNames, bindings, stateSetterNames) : [] };
  }

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
        props.push({ name, value: parseExpr(jsxAttr.initializer.expression, staticMaps, undefined, [], bindings) });
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
      events.push({ name: mappedEvent, body: parseHandlerBody(init, staticMaps, callbackNames, stateSetterNames) });
      continue;
    }
    const attrName = jsxAttrName(rawName);
    if (jsxAttr.initializer === undefined) {
      attrs.push({ kind: "static", name: attrName, value: "true" });
    } else if (ts.isStringLiteral(jsxAttr.initializer)) {
      attrs.push({ kind: "static", name: attrName, value: jsxAttr.initializer.text });
    } else if (ts.isJsxExpression(jsxAttr.initializer) && jsxAttr.initializer.expression) {
      const value = rawName === "style"
        ? styleObjectExpression(jsxAttr.initializer.expression, staticMaps)
        : parseExpr(jsxAttr.initializer.expression, staticMaps, undefined, [], bindings);
      attrs.push({ kind: "dynamic", name: attrName, value });
    } else {
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `attribute ${JSON.stringify(rawName)} has an unsupported value shape`);
    }
  }

  const children = ts.isJsxElement(node) ? parseJsxChildren(node.children, staticMaps, callbackNames, bindings, stateSetterNames) : [];
  return { kind: "element", tag, attrs, events, children };
}

/**
 * A render return may be a JSX conditional expression.  It has the same
 * target-independent meaning as the JSX child form, so normalize it into the
 * canonical conditional node instead of treating the expression itself as a
 * tag.  A non-JSX branch remains fail-closed in parseJsxNode.
 */
function parseRenderExpression(raw: ts.Expression, staticMaps: StaticStringMaps, callbackNames: ReadonlySet<string> = new Set(), bindings: ExpressionBindings = new Map(), stateSetterNames: ReadonlyMap<string, string> = new Map()): CNode {
  const node = unwrapParens(raw);
  if (ts.isConditionalExpression(node) && (isJsxLike(node.whenTrue) || isJsxLike(node.whenFalse))) {
    return {
      kind: "conditional",
      condition: parseExpr(node.condition, staticMaps, undefined, [], bindings),
      then: parseJsxNode(node.whenTrue, staticMaps, callbackNames, bindings, stateSetterNames),
      else: node.whenFalse.kind === ts.SyntaxKind.NullKeyword ? null : parseJsxNode(node.whenFalse, staticMaps, callbackNames, bindings, stateSetterNames),
    };
  }
  return parseJsxNode(node, staticMaps, callbackNames, bindings, stateSetterNames);
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
  options: ReactParserOptions = {},
): { name: string | null; component: ComponentDef | null; error: DialectError | null }[] {
  const sourceFile = options.sourceFile
    ?? options.project?.program.getSourceFile(path.resolve(fileName))
    ?? ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const functions = sourceFile.statements.filter(ts.isFunctionDeclaration);
  require_(functions.length >= 1, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", "expected at least one top-level function component declaration, found 0");
  const localTypes = collectLocalTypes(sourceFile);
  return functions.map((fn) => {
    const declaredName = fn.name?.text ?? null;
    try {
      return { name: declaredName, component: parseFunctionComponent(fn, localTypes, options), error: null };
    } catch (error) {
      if (error instanceof DialectError) return { name: declaredName, component: null, error };
      throw error;
    }
  });
}

export function parseReactComponents(source: string, fileName = "Component.tsx", options: ReactParserOptions = {}): ComponentDef[] {
  const sourceFile = options.sourceFile
    ?? options.project?.program.getSourceFile(path.resolve(fileName))
    ?? ts.createSourceFile(fileName, source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
  const functions = sourceFile.statements.filter(ts.isFunctionDeclaration);
  require_(functions.length >= 1, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", "expected at least one top-level function component declaration, found 0");
  const localTypes = collectLocalTypes(sourceFile);
  const components = functions.map((fn) => parseFunctionComponent(fn, localTypes, options));
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
export function parseReactComponent(source: string, fileName = "Component.tsx", options: ReactParserOptions = {}): ComponentDef {
  const components = parseReactComponents(source, fileName, options);
  require_(components.length === 1, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", `expected exactly one top-level function component declaration, found ${components.length}`);
  return at(components, 0, "CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION", "no function component found");
}

/** Type aliases and interfaces declared in this file, by name. Keeping the
 * complete TypeNode lets state aliases such as string literal unions and
 * indexed access types resolve without a working external type checker. */
type LocalTypes = ReadonlyMap<string, ts.TypeNode>;

function collectLocalTypes(sourceFile: ts.SourceFile): LocalTypes {
  const map = new Map<string, ts.TypeNode>();
  for (const statement of sourceFile.statements) {
    if (ts.isInterfaceDeclaration(statement)) {
      // An interface body IS a type literal for our purposes; re-parsing
      // its members through the same path keeps one code path for both.
      const synthetic = ts.factory.createTypeLiteralNode(statement.members);
      // The synthesized node has no parent/positions, so re-read members
      // from the original declaration instead.
      void synthetic;
      map.set(statement.name.text, ts.factory.createTypeLiteralNode(statement.members));
    } else if (ts.isTypeAliasDeclaration(statement)) {
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

interface LocalExpressionDefinition {
  expression?: Expr;
  fields?: ReadonlyMap<string, Expr>;
  list?: ListPropDef;
  order: number;
}

function expandLocalExpression(expr: Expr, definitions: ReadonlyMap<string, LocalExpressionDefinition>, ownerOrder = Number.POSITIVE_INFINITY, stack: readonly string[] = []): Expr {
  if (expr.kind === "ident") {
    const definition = definitions.get(expr.name);
    if (definition === undefined) return expr;
    require_(definition.order < ownerOrder, "CERTIFIED_COMPONENT_FORWARD_LOCAL_READ", `local expression ${JSON.stringify(expr.name)} is read before its declaration`);
    require_(!stack.includes(expr.name), "CERTIFIED_COMPONENT_CYCLIC_LOCAL_READ", `local expressions contain a cycle through ${JSON.stringify(expr.name)}`);
    require_(definition.expression !== undefined, "CERTIFIED_COMPONENT_OBJECT_LOCAL_READ", `object local ${JSON.stringify(expr.name)} must be read through a declared field`);
    return expandLocalExpression(definition.expression, definitions, definition.order, [...stack, expr.name]);
  }
  switch (expr.kind) {
    case "member": {
      const definition = definitions.get(expr.object);
      const field = definition?.fields?.get(expr.field);
      if (field !== undefined) {
        require_(definition !== undefined && definition.order < ownerOrder, "CERTIFIED_COMPONENT_FORWARD_LOCAL_READ", `local expression ${JSON.stringify(expr.object)} is read before its declaration`);
        require_(!stack.includes(expr.object), "CERTIFIED_COMPONENT_CYCLIC_LOCAL_READ", `local expressions contain a cycle through ${JSON.stringify(expr.object)}`);
        return expandLocalExpression(field, definitions, definition.order, [...stack, expr.object]);
      }
      return expr;
    }
    case "path": return expr;
    case "literal": return expr;
    case "unaryNot": return { kind: "unaryNot", operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack) };
    case "binary": return {
      kind: "binary",
      operator: expr.operator,
      left: expandLocalExpression(expr.left, definitions, ownerOrder, stack),
      right: expandLocalExpression(expr.right, definitions, ownerOrder, stack),
    };
    case "stringMethod": return {
      kind: "stringMethod",
      method: expr.method,
      receiver: expandLocalExpression(expr.receiver, definitions, ownerOrder, stack),
      args: expr.args.map((arg) => expandLocalExpression(arg, definitions, ownerOrder, stack)),
    };
    case "numericFunction": return {
      kind: "numericFunction",
      function: expr.function,
      args: expr.args.map((arg) => expandLocalExpression(arg, definitions, ownerOrder, stack)),
    };
    case "numericPredicate": return {
      kind: "numericPredicate",
      predicate: expr.predicate,
      operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack),
    };
    case "numberMethod": return {
      kind: "numberMethod",
      method: expr.method,
      receiver: expandLocalExpression(expr.receiver, definitions, ownerOrder, stack),
      fractionDigits: expr.fractionDigits,
    };
    case "numberFormat": return {
      kind: "numberFormat",
      format: expr.format,
      ...(expr.locale === undefined ? {} : { locale: expr.locale }),
      operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack),
    };
    case "cssModuleClass": return expr;
    case "eventValue": return expr;
    case "regexTest": return {
      kind: "regexTest",
      pattern: expr.pattern,
      flags: expr.flags,
      operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack),
    };
    case "arrayLength": return { kind: "arrayLength", operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack) };
    case "percentageWidth": return { kind: "percentageWidth", value: expandLocalExpression(expr.value, definitions, ownerOrder, stack) };
    case "styleObject": return {
      kind: "styleObject",
      fields: expr.fields.map((field) => ({ name: field.name, value: expandLocalExpression(field.value, definitions, ownerOrder, stack) })),
    };
   case "collectionFilter": return {
     kind: "collectionFilter",
     source: expandLocalExpression(expr.source, definitions, ownerOrder, stack),
     itemName: expr.itemName,
     predicate: expandLocalExpression(expr.predicate, definitions, ownerOrder, stack),
   };
    case "collectionMap": return {
      kind: "collectionMap",
      source: expandLocalExpression(expr.source, definitions, ownerOrder, stack),
      itemName: expr.itemName,
      projection: expandLocalExpression(expr.projection, definitions, ownerOrder, stack),
    };
    case "collectionReduce": return {
      kind: "collectionReduce",
      source: expandLocalExpression(expr.source, definitions, ownerOrder, stack),
      accumulatorName: expr.accumulatorName,
      itemName: expr.itemName,
      reducer: expandLocalExpression(expr.reducer, definitions, ownerOrder, stack),
      initial: expandLocalExpression(expr.initial, definitions, ownerOrder, stack),
    };
    case "collectionMax": return {
      kind: "collectionMax",
      source: expandLocalExpression(expr.source, definitions, ownerOrder, stack),
      itemName: expr.itemName,
      operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack),
    };
    case "collectionJoin": return {
      kind: "collectionJoin",
      source: expandLocalExpression(expr.source, definitions, ownerOrder, stack),
      separator: expandLocalExpression(expr.separator, definitions, ownerOrder, stack),
    };
    case "objectLookup": return {
      kind: "objectLookup",
      object: expandLocalExpression(expr.object, definitions, ownerOrder, stack),
      key: expandLocalExpression(expr.key, definitions, ownerOrder, stack),
    };
   case "objectLiteral": return {
      kind: "objectLiteral",
      fields: expr.fields.map((field) => ({ name: field.name, value: expandLocalExpression(field.value, definitions, ownerOrder, stack) })),
      ...(expr.computedFields === undefined ? {} : { computedFields: expr.computedFields.map((field) => ({ key: expandLocalExpression(field.key, definitions, ownerOrder, stack), value: expandLocalExpression(field.value, definitions, ownerOrder, stack) })) }),
    };
    case "arrayLiteral": return { kind: "arrayLiteral", items: expr.items.map((item) => expandLocalExpression(item, definitions, ownerOrder, stack)) };
    case "ternary": return {
      kind: "ternary",
      condition: expandLocalExpression(expr.condition, definitions, ownerOrder, stack),
      then: expandLocalExpression(expr.then, definitions, ownerOrder, stack),
      else: expandLocalExpression(expr.else, definitions, ownerOrder, stack),
    };
  }
}

function staticObjectAliasFields(initializer: ts.Expression, staticMaps: StaticStringMaps): ReadonlyMap<string, Expr> | null {
  if (!ts.isElementAccessExpression(initializer) || !ts.isIdentifier(initializer.expression) || initializer.argumentExpression === undefined) return null;
  const table = staticMaps.get(initializer.expression.text);
  const entries = staticStringMapEntries(table);
  if (entries === undefined) return null;
  const key = parseExpr(initializer.argumentExpression, staticMaps);
  const fieldNames = new Set<string>();
  for (const entry of entries.values()) {
    if (typeof entry === "string") return null;
    for (const fieldName of entry.keys()) fieldNames.add(fieldName);
  }
  const fields = new Map<string, Expr>();
  for (const fieldName of fieldNames) {
    const values = new Map<string, string>();
    for (const [entryName, entry] of entries.entries()) {
      if (typeof entry === "string") return null;
      const value = entry.get(fieldName);
      if (value === undefined) return null;
      values.set(entryName, value);
    }
    fields.set(fieldName, staticLookupExpression(values, key));
  }
  return fields.size > 0 ? fields : null;
}

function listElementFromProjection(expr: Expr, itemName: string, source: ListElementShape, what: string): ListElementShape {
  const shapeOf = (value: Expr): ValueShape => {
    if (value.kind === "literal") {
      require_(value.literal.type !== "null", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " may not project null items");
      return { kind: "primitive", primitive: value.literal.type };
    }
    if (value.kind === "ident" && value.name === itemName) {
      return source.kind === "primitive" ? { kind: "primitive", primitive: source.primitive } : { kind: "object", fields: source.fields };
    }
    if (value.kind === "member" && value.object === itemName) {
      require_(source.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " projects a field from a primitive item");
      const projectedField: { shape: ValueShape; optional: boolean } | undefined = source.fields[value.field];
      require_(projectedField !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_LIST_FIELD", what + " projects an undeclared item field");
      return projectedField.shape;
    }
    if (value.kind === "path" && value.object === itemName) {
      let shape: ValueShape = source.kind === "primitive" ? { kind: "primitive", primitive: source.primitive } : { kind: "object", fields: source.fields };
      for (const fieldName of value.fields) {
        require_(shape.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " traverses a non-object item field");
        const pathField: { shape: ValueShape; optional: boolean } | undefined = shape.fields[fieldName];
        require_(pathField !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_LIST_FIELD", what + " projects an undeclared item path");
        shape = pathField.shape;
      }
      return shape;
    }
    if (value.kind === "stringMethod") return { kind: "primitive", primitive: value.method === "includes" ? "boolean" : "string" };
    if (value.kind === "numberMethod" || value.kind === "numberFormat" || value.kind === "percentageWidth") return { kind: "primitive", primitive: "string" };
    if (value.kind === "numericFunction" || value.kind === "numericPredicate" || value.kind === "arrayLength" || value.kind === "collectionMax" || value.kind === "collectionReduce") return { kind: "primitive", primitive: value.kind === "numericPredicate" ? "boolean" : "number" };
    if (value.kind === "collectionJoin") return { kind: "primitive", primitive: "string" };
    if (value.kind === "objectLookup") return { kind: "primitive", primitive: "number" };
    if (value.kind === "regexTest") return { kind: "primitive", primitive: "boolean" };
    if (value.kind === "binary") {
      if (value.operator === "+") return { kind: "primitive", primitive: "string" };
      if (value.operator === "??") return shapeOf(value.left);
      if (["-", "*", "/", "%"].includes(value.operator)) return { kind: "primitive", primitive: "number" };
      if (["<", "<=", ">", ">=", "==", "!=", "&&", "||"].includes(value.operator)) return { kind: "primitive", primitive: "boolean" };
    }
    if (value.kind === "objectLiteral") {
      const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
      for (const field of value.fields) fields[field.name] = { shape: shapeOf(field.value), optional: false };
      return { kind: "object", fields };
    }
    if (value.kind === "arrayLiteral") {
      const first = value.items[0];
      require_(first !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " projects an empty array");
      return { kind: "array", element: shapeOf(first) };
    }
    if (value.kind === "ternary") {
      const thenShape = shapeOf(value.then);
      const elseShape = shapeOf(value.else);
      require_(JSON.stringify(thenShape) === JSON.stringify(elseShape), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " has branches with different projected shapes");
      return thenShape;
    }
    fail("CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " has an unsupported projection");
  };
  const projected = shapeOf(expr);
  if (projected.kind === "primitive") return { kind: "primitive", primitive: projected.primitive };
  require_(projected.kind === "object", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", what + " must project primitive or object items");
  return { kind: "object", fields: projected.fields };
}

function derivedListDefinition(
  name: string,
  initializer: ts.Expression,
  staticMaps: StaticStringMaps,
  props: PropDef[],
  definitions: ReadonlyMap<string, LocalExpressionDefinition>,
): ListPropDef | null {
  if (!ts.isCallExpression(initializer) || !ts.isPropertyAccessExpression(initializer.expression) || !["filter", "map"].includes(initializer.expression.name.text)) return null;
  const parsed = initializer.expression.name.text === "filter"
    ? collectionFilterExpression(initializer, staticMaps, undefined, [])
    : collectionMapExpression(initializer, staticMaps, undefined, [], new Map());
  if (parsed === null || (parsed.kind !== "collectionFilter" && parsed.kind !== "collectionMap")) fail("CERTIFIED_COMPONENT_FILTER_SOURCE", `derived list ${JSON.stringify(name)} must use a certified filter or map expression`);
  const sourceExpression = parsed.source;
  const resolveSourceList = (expression: Expr): ListPropDef | undefined => {
    if (expression.kind === "ident") {
      const declared = props.find((prop): prop is ListPropDef => prop.kind === "list" && prop.name === expression.name)
        ?? definitions.get(expression.name)?.list;
      if (declared !== undefined) return declared;
      const definition = staticMaps.get(expression.name);
      if (definition !== undefined && isStaticListDefinition(definition)) return { kind: "list", name: expression.name, element: definition.element, staticItems: definition.items };
      if (definition !== undefined && isStaticPrimitiveListDefinition(definition)) return { kind: "list", name: expression.name, element: definition.element, staticValues: definition.values };
      return undefined;
    }
    if (expression.kind === "member") {
      const owner = props.find((prop): prop is Extract<PropDef, { kind: "data" }> => prop.kind === "data" && prop.name === expression.object);
      const shape = owner?.valueShape;
      const field = shape?.kind === "object" ? shape.fields[expression.field]?.shape : undefined;
      if (field?.kind === "array") return {
        kind: "list",
        name: expression.object + "." + expression.field,
        element: listElementFromShape(field, "derived list source"),
      };
    }
    if (expression.kind === "collectionMap") {
      const base = resolveSourceList(expression.source);
      if (base === undefined) return undefined;
      const element = listElementFromProjection(expression.projection, expression.itemName, base.element, "derived map source");
      return { kind: "list", name: name + ".source", element, ...(element.kind === "object" && element.fields.id !== undefined ? { keyField: "id" } : {}) };
    }
    if (expression.kind === "collectionFilter") {
      const base = resolveSourceList(expression.source);
      return base === undefined ? undefined : { ...base, name: name + ".source" };
    }
    return undefined;
  };
  const sourceList = resolveSourceList(sourceExpression);
  if (sourceList === undefined) fail("CERTIFIED_COMPONENT_FILTER_SOURCE", `derived list ${JSON.stringify(name)} has no declared list source`);
  const sourceElement = sourceList.element;
  const element = parsed.kind === "collectionFilter"
    ? sourceElement
    : listElementFromProjection(parsed.projection, parsed.itemName, sourceElement, "derived list projection");
  return {
    kind: "list",
    name,
    sourceExpression: parsed,
    element,
    ...(element.kind === "object" && element.fields.id !== undefined ? { keyField: "id" } : {}),
  };
}

function expandLocalNode(node: CNode, definitions: ReadonlyMap<string, LocalExpressionDefinition>): CNode {
  if (node.kind === "fragment") return { kind: "fragment", children: node.children.map((child) => expandLocalNode(child, definitions)) };
  if (node.kind === "text") return { kind: "text", value: expandLocalExpression(node.value, definitions) };
  if (node.kind === "conditional") return {
    kind: "conditional",
    condition: expandLocalExpression(node.condition, definitions),
    then: expandLocalNode(node.then, definitions),
    else: node.else === null ? null : expandLocalNode(node.else, definitions),
  };
  if (node.kind === "list") {
    const definition = definitions.get(node.source);
    const sourceExpression = definition?.list !== undefined
      ? expandLocalExpression({ kind: "ident", name: node.source }, definitions)
      : node.sourceExpression === undefined ? undefined : expandLocalExpression(node.sourceExpression, definitions);
    return { ...node, ...(sourceExpression === undefined ? {} : { sourceExpression }), body: expandLocalNode(node.body, definitions) };
  }
  if (node.kind === "component") return {
    ...node,
    props: node.props.map((prop) => ({ ...prop, value: expandLocalExpression(prop.value, definitions) })),
  };
  return {
    ...node,
    attrs: node.attrs.map((attr) => attr.kind === "static" ? attr : { ...attr, value: expandLocalExpression(attr.value, definitions) }),
    events: node.events.map((event) => ({
      ...event,
      body: event.body.map((statement) => statement.kind === "setState"
        ? { ...statement, value: expandLocalExpression(statement.value, definitions) }
        : { ...statement, args: statement.args.map((arg) => expandLocalExpression(arg, definitions)) }),
    })),
    children: node.children.map((child) => expandLocalNode(child, definitions)),
  };
}

function parseFunctionComponent(
  fn: ts.FunctionDeclaration,
  localTypes: LocalTypes = new Map(),
  options: ReactParserOptions = {},
): ComponentDef {
  require_(returnsJsx(fn), "CERTIFIED_COMPONENT_NOT_A_COMPONENT",
    `${fn.name?.text ?? "an anonymous function"} returns no JSX, so it is a helper rather than a component`);
  const fnName = requireDefined(fn.name, "CERTIFIED_COMPONENT_MISSING_NAME", "component function must be named");
  const name = fnName.text;
  checkIdentifier(name, "component name");
  const staticMaps = collectStaticStringMaps(options.sourceFile ?? fn.getSourceFile(), options.project);

  require_(fn.parameters.length <= 1, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "component must take zero or one (props) parameter");
  const props: PropDef[] = [];
  if (fn.parameters.length === 1) {
    const param = at(fn.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "missing props parameter");
    const bindingPattern = param.name;
    require_(ts.isObjectBindingPattern(bindingPattern), "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props parameter must be an inline destructured object pattern");
    const annotation = param.type;
    // `function C({ a }: Props)` with `interface Props { ... }` in the same
    // file is the dominant React idiom -- a scan of real code found it
    // blocking 37 components. The declaration is right there, so resolving
    // it is exact rather than inferred. A type imported from elsewhere is
    // still refused: this parser reads ONE file and must not pretend to
    // know what a name means somewhere else.
    const typeLiteral = annotation === undefined || options.project !== undefined
      ? undefined
      : (ts.isTypeLiteralNode(annotation) ? annotation : resolveLocalPropsType(annotation, localTypes));
    const fieldTypes = new Map<string, ts.TypeNode | undefined>();
    const optionalFields = new Set<string>();
    if (typeLiteral !== undefined) {
      require_(ts.isTypeLiteralNode(typeLiteral), "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props parameter must have an inline type literal annotation, or name a type/interface declared in the same file");
      for (const member of typeLiteral.members) {
        require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", "props type literal must contain plain property signatures");
        const fieldName = (member.name as ts.Identifier).text;
        fieldTypes.set(fieldName, member.type);
        if (member.questionToken) optionalFields.add(fieldName);
      }
    }
    for (const element of bindingPattern.elements) {
      require_(ts.isIdentifier(element.name) && !element.dotDotDotToken, "CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS", "props destructuring must bind plain names (no rest/nested patterns)");
      const propName = (element.name as ts.Identifier).text;
      const typeNode = fieldTypes.get(propName);
      const checkerType = options.project === undefined ? undefined : options.project.checker.getTypeAtLocation(element.name);
      require_(typeNode !== undefined || checkerType !== undefined, "CERTIFIED_COMPONENT_UNKNOWN_PROP", `destructured prop ${JSON.stringify(propName)} is not declared in the props type`);
      const checkerSignatures = checkerType !== undefined
        ? options.project?.checker.getSignaturesOfType(checkerType, ts.SignatureKind.Call) ?? []
        : [];
      const typeText = checkerType !== undefined
        ? options.project?.checker.typeToString(checkerType, element.name, ts.TypeFormatFlags.NoTruncation) ?? ""
        : typeNode?.getText() ?? "";
      if (propName === "children" && /ReactNode|ReactElement|ReactPortal/.test(typeText)) {
        props.push({ kind: "data", name: propName, propType: "string", valueShape: { kind: "slot", slotName: "children", nullable: true }, required: false });
        continue;
      }
      // The canonical IR deliberately has a closed callback vocabulary.  A
      // function-typed prop with an arbitrary name is not automatically an
      // event: it may be a mutation object, render prop, hook result, or
      // another framework-specific API.  Requiring the explicit on*/set*
      // contract keeps those cases blocked instead of misclassifying them.
      if (/^on[A-Z]/.test(propName) || /^set[A-Z]/.test(propName)) {
        const callbackTypeNode = typeNode;
        let paramType: PrimitiveType | undefined;
        if (checkerType !== undefined) {
          const signatures = checkerSignatures;
          const signature = at(signatures, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE", `callback prop ${JSON.stringify(propName)} must have a function type`);
          require_(signature.parameters.length <= 1, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", `callback prop ${JSON.stringify(propName)} may take at most one parameter`);
          if (signature.parameters.length === 1) {
            const callbackParam = at(signature.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", "missing callback parameter");
            const project = requireDefined(options.project, "CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE", "missing project type checker");
            paramType = primitiveFromShape(valueShapeFromChecker(project.checker.getTypeOfSymbolAtLocation(callbackParam, element.name), project.checker, element.name, `${propName} parameter`), `${propName} parameter`);
          }
        } else {
          const callbackNode = requireDefined(callbackTypeNode, "CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE", `callback prop ${JSON.stringify(propName)} must have a function type`);
          require_(ts.isFunctionTypeNode(callbackNode), "CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE", `callback prop ${JSON.stringify(propName)} must have a function type`);
          require_(callbackNode.parameters.length <= 1, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", `callback prop ${JSON.stringify(propName)} may take at most one parameter`);
          paramType = callbackNode.parameters.length === 1
            ? primitiveTypeFromNode(at(callbackNode.parameters, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY", "missing callback parameter").type, `${propName} parameter`)
            : undefined;
        }
        const def: CallbackPropDef = { kind: "callback", name: propName, paramType };
        props.push(def);
      } else {
        const shape = checkerType !== undefined
          ? valueShapeFromChecker(checkerType, options.project?.checker as ts.TypeChecker, element.name, `prop ${propName}`)
          : shapeFromTypeNode(typeNode, `prop ${propName}`, localTypes);
        if ((checkerType !== undefined && shape.kind === "array") || (checkerType === undefined && typeNode !== undefined && isArrayTypeNode(typeNode))) {
        const listShape = checkerType !== undefined
          ? listElementFromChecker(checkerType, options.project?.checker as ts.TypeChecker, element.name, `list prop ${JSON.stringify(propName)}`)
          : listElementFromArrayType(typeNode as ts.TypeNode, `list prop ${JSON.stringify(propName)}`);
        require_(!element.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_DEFAULT", `list prop ${JSON.stringify(propName)} may not have a default value`);
        const def: ListPropDef = { kind: "list", name: propName, element: listShape, keyField: inferredKeyFieldOrUndefined(listShape, `list prop ${JSON.stringify(propName)}`) };
        props.push(def);
        } else {
        const propType = shape.kind === "primitive" ? shape.primitive : "string";
        const required = !optionalFields.has(propName) && !element.initializer && !shape.nullable;
        const defaultValue: Literal | undefined = element.initializer
          ? (shape.kind === "primitive" ? literalFromNode(element.initializer, propType) : undefined)
          : undefined;
        require_(!element.initializer || shape.kind === "primitive", "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `default value for structured prop ${JSON.stringify(propName)} is outside certified-component-v1`);
        const valueShape = shape.kind === "primitive" && shape.nullable !== true ? undefined : shape;
        const def: DataPropDef = { kind: "data", name: propName, propType, ...(valueShape === undefined ? {} : { valueShape }), required, defaultValue };
        props.push(def);
        }
      }
    }
  }

  const body = requireDefined(fn.body, "CERTIFIED_COMPONENT_MISSING_BODY", "component must have a body");
  const state: StateDef[] = [];
  const stateSetterNames = new Map<string, string>();
  const localDefinitions = new Map<string, LocalExpressionDefinition>();
  let returnStatement: ts.ReturnStatement | undefined;
  const earlyReturns: { condition: ts.Expression; statement: ts.ReturnStatement }[] = [];
  for (const [statementOrder, stmt] of body.statements.entries()) {
    if (ts.isVariableStatement(stmt)) {
      require_(stmt.declarationList.declarations.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "only one declaration per const statement is supported");
      const decl = at(stmt.declarationList.declarations, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing declaration");
      const declName = decl.name;
      if (ts.isIdentifier(declName) && decl.initializer !== undefined) {
        const derived = derivedListDefinition(declName.text, decl.initializer, staticMaps, props, localDefinitions);
        if (derived !== null) {
          localDefinitions.set(declName.text, { expression: derived.sourceExpression, list: derived, order: statementOrder });
          continue;
        }
        const fields = staticObjectAliasFields(decl.initializer, staticMaps);
        if (fields !== null) {
          localDefinitions.set(declName.text, { fields, order: statementOrder });
        } else {
          const expression = parseExpr(decl.initializer, staticMaps);
          const staticList = staticListDefinitionFromExpression(expression, declName.text);
          localDefinitions.set(declName.text, { expression, ...(staticList === null ? {} : { list: staticList }), order: statementOrder });
        }
        continue;
      }
      require_(ts.isArrayBindingPattern(declName) && declName.elements.length === 2, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "expected a `const [x, setX] = useState(...)` declaration");
      const getterEl = at(declName.elements, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing useState getter");
      const setterEl = at(declName.elements, 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing useState setter");
      require_(ts.isBindingElement(getterEl) && ts.isIdentifier(getterEl.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "useState getter must be a plain identifier");
      require_(ts.isBindingElement(setterEl) && ts.isIdentifier(setterEl.name), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "useState setter must be a plain identifier");
      const getterName = (getterEl.name as ts.Identifier).text;
      const setterNameText = (setterEl.name as ts.Identifier).text;
      const initializer = requireDefined(decl.initializer, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "expected a useState(...) call");
      require_(ts.isCallExpression(initializer) && ts.isIdentifier(initializer.expression) && initializer.expression.text === "useState", "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "expected a useState(...) call");
      require_(initializer.arguments.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "useState must be called with exactly one closed literal initial value");
      const initial = closedStateValue(at(initializer.arguments, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing useState argument"), staticMaps);
      const checker = options.project?.checker;
      const checkerType = checker?.getTypeAtLocation(getterEl.name);
      const explicitTypeNode = initializer.typeArguments?.[0];
      const explicitCheckerType = checker !== undefined && explicitTypeNode !== undefined
        ? checker.getTypeFromTypeNode(explicitTypeNode)
        : undefined;
      // A synthetic single-file project has no React declaration for
      // `useState`, so TypeScript can report `any` even when the source has an
      // explicit type argument. Never let that tooling absence erase a
      // stronger source annotation; real incompatible checker types still
      // take precedence and fail closed below.
      const declared = checker !== undefined && checkerType !== undefined
        && (checkerType.flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) === 0
        ? valueShapeFromChecker(checkerType, checker, getterEl.name, `state ${getterName}`)
        : checker !== undefined && explicitCheckerType !== undefined
          && (explicitCheckerType.flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) === 0
          ? valueShapeFromChecker(explicitCheckerType, checker, explicitTypeNode as ts.TypeNode, `state ${getterName}`)
        : explicitTypeNode !== undefined
          ? shapeFromTypeNode(explicitTypeNode, `state ${getterName}`, localTypes)
          : undefined;
      const initialLiteral = "type" in initial ? initial : undefined;
      const structured = declared !== undefined && declared.kind !== "primitive";
      const stateType: PrimitiveType = declared?.kind === "primitive"
        ? declared.primitive
        : initialLiteral !== undefined && initialLiteral.type !== "null"
          ? initialLiteral.type
          : "string";
      const nullable = initialLiteral?.type === "null" || declared?.nullable === true;
      if (initialLiteral?.type === "null") {
        require_(declared !== undefined && declared.nullable === true, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `nullable state ${JSON.stringify(getterName)} must declare a nullable structural type`);
      }
      if (structured) {
        require_(declared !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `structured state ${JSON.stringify(getterName)} must declare a structural type`);
        state.push({ name: getterName, stateType, stateShape: declared, ...(nullable ? { nullable: true } : {}), initial });
      } else {
        require_(initialLiteral !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL", `state ${JSON.stringify(getterName)} requires a primitive literal initializer`);
        state.push({ name: getterName, stateType, ...(nullable ? { nullable: true } : {}), initial: initialLiteral });
      }
      // The destructuring declaration is the source of truth for the setter
      // binding. React does not require the conventional `set${Name}` spelling;
      // recording the exact local name lets the canonical IR keep the state
      // target while each emitter chooses its own setter syntax.
      require_(!stateSetterNames.has(setterNameText), "CERTIFIED_COMPONENT_DUPLICATE_SETTER", `state setter ${JSON.stringify(setterNameText)} is bound more than once`);
      stateSetterNames.set(setterNameText, getterName);
      continue;
    }
    if (ts.isIfStatement(stmt)) {
      require_(stmt.elseStatement === undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "an early JSX return may not have an else statement");
      const branch = ts.isBlock(stmt.thenStatement)
        ? (() => {
          require_(stmt.thenStatement.statements.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "an early-return block may contain only one return statement");
          return stmt.thenStatement.statements[0]!;
        })()
        : stmt.thenStatement;
      require_(ts.isReturnStatement(branch), "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "an if statement must return JSX directly to be represented as a conditional node");
      const earlyReturn = branch as ts.ReturnStatement;
      require_(earlyReturn.expression !== undefined, "CERTIFIED_COMPONENT_MISSING_RETURN", "an early return must return JSX");
      earlyReturns.push({ condition: stmt.expression, statement: earlyReturn });
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
  const callbackNames = new Set(props.filter((prop): prop is CallbackPropDef => prop.kind === "callback").map((prop) => prop.name));
  let root = parseRenderExpression(returned, staticMaps, callbackNames, new Map(), stateSetterNames);
  for (let index = earlyReturns.length - 1; index >= 0; index -= 1) {
    const early = earlyReturns[index]!;
    root = {
      kind: "conditional",
      condition: parseExpr(early.condition, staticMaps),
      then: parseRenderExpression(requireDefined(early.statement.expression, "CERTIFIED_COMPONENT_MISSING_RETURN", "an early return must return JSX"), staticMaps, callbackNames, new Map(), stateSetterNames),
      else: root,
    };
  }
  root = expandLocalNode(root, localDefinitions);

  const nestedLists = materializeNestedLists(root, props);
  const staticLists = materializeStaticLists(root, staticMaps);
  const staticExpressionLists = materializeStaticExpressionLists(root, staticMaps);
  const stateLists = materializeStateLists(root, state);
  const localLists = [...localDefinitions.values()].flatMap((definition) => definition.list === undefined ? [] : [definition.list]);
  const allLists = [...nestedLists, ...localLists, ...staticLists, ...staticExpressionLists, ...stateLists];
  const component: ComponentDef = { name, props, state, root, ...(allLists.length === 0 ? {} : { lists: allLists }) };
  applyExplicitListKeys(root, [...props, ...localLists, ...staticLists, ...stateLists]);
  validateComponent(component);
  return component;
}

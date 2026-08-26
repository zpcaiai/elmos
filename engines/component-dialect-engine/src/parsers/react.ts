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
  ValueShape } from "../models";

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
interface StaticPureFunctionDefinition {
  readonly kind: "pure-function";
  readonly parameters: readonly string[];
  readonly body: ts.Expression;
}
type StaticDefinition = ReadonlyMap<string, StaticStringMapValue> | StaticRegexDefinition | StaticCssModuleDefinition | StaticPureFunctionDefinition;
type StaticStringMaps = ReadonlyMap<string, StaticDefinition>;

function isStaticRegexDefinition(value: StaticDefinition): value is StaticRegexDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "regex";
}

function isStaticCssModuleDefinition(value: StaticDefinition): value is StaticCssModuleDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "css-module";
}

function isStaticPureFunctionDefinition(value: StaticDefinition): value is StaticPureFunctionDefinition {
  return typeof value === "object" && value !== null && "kind" in value && value.kind === "pure-function";
}

function isStaticStringMapDefinition(value: StaticDefinition): value is ReadonlyMap<string, StaticStringMapValue> {
  return !isStaticRegexDefinition(value) && !isStaticCssModuleDefinition(value) && !isStaticPureFunctionDefinition(value);
}

function pureFunctionDefinitionFromNode(fn: ts.FunctionDeclaration): StaticPureFunctionDefinition | null {
  if (fn.name === undefined || fn.body === undefined || fn.asteriskToken !== undefined || fn.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.AsyncKeyword)) return null;
  if (fn.type === undefined || !["string", "number", "boolean"].includes(fn.type.getText())) return null;
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

function collectStaticStringMaps(sourceFile: ts.SourceFile): StaticStringMaps {
  const maps = new Map<string, StaticDefinition>();
  for (const statement of sourceFile.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) continue;
    if (!/\.module\.css$/u.test(statement.moduleSpecifier.text)) continue;
    const defaultImport = statement.importClause?.name;
    if (defaultImport !== undefined) maps.set(defaultImport.text, { kind: "css-module" });
  }
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      let initializer = declaration.initializer;
      while (initializer !== undefined && (ts.isAsExpression(initializer) || ts.isTypeAssertionExpression(initializer))) initializer = initializer.expression;
      if (!ts.isIdentifier(declaration.name) || initializer === undefined) continue;
      const regex = regexDefinitionFromNode(initializer);
      if (regex !== null) {
        maps.set(declaration.name.text, regex);
        continue;
      }
      if (!ts.isObjectLiteralExpression(initializer)) continue;
      const entries = new Map<string, StaticStringMapValue>();
      let complete = true;
      for (const property of initializer.properties) {
        if (!ts.isPropertyAssignment(property)) { complete = false; break; }
        if (ts.isStringLiteral(property.initializer)) {
          entries.set(property.name.getText().replace(/^['"]|['"]$/g, ""), property.initializer.text);
          continue;
        }
        if (ts.isObjectLiteralExpression(property.initializer)) {
          const fields = new Map<string, string>();
          for (const field of property.initializer.properties) {
            if (!ts.isPropertyAssignment(field) || !ts.isStringLiteral(field.initializer)) { complete = false; break; }
            fields.set(field.name.getText().replace(/^['"]|['"]$/g, ""), field.initializer.text);
          }
          if (!complete || fields.size === 0) break;
          entries.set(property.name.getText().replace(/^['"]|['"]$/g, ""), fields);
          continue;
        }
        complete = false;
        break;
      }
      if (complete && entries.size > 0) maps.set(declaration.name.text, entries);
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

function shapeFromTypeNode(node: ts.TypeNode | undefined, what: string, localTypes: LocalTypes): ValueShape {
  if (!node) fail("CERTIFIED_COMPONENT_MISSING_TYPE", `${what} is missing an explicit type`);
  const text = node.getText();
  if (text === "string" || text === "number" || text === "boolean") return { kind: "primitive", primitive: text };
  if (ts.isArrayTypeNode(node)) return { kind: "array", element: shapeFromTypeNode(node.elementType, `${what} element`, localTypes) };
  if (ts.isTypeReferenceNode(node) && ts.isIdentifier(node.typeName)) {
    const resolved = localTypes.get(node.typeName.text);
    if (resolved !== undefined) return shapeFromTypeNode(resolved, what, localTypes);
  }
  if (ts.isUnionTypeNode(node)) {
    const nonNull = node.types.filter((member) => member.kind !== ts.SyntaxKind.NullKeyword && member.kind !== ts.SyntaxKind.UndefinedKeyword);
    const nullable = nonNull.length !== node.types.length;
    const first = at(nonNull, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `${what} is null/undefined only`);
    const shape = shapeFromTypeNode(first, what, localTypes);
    return nullable ? { ...shape, nullable: true } : shape;
  }
  if (ts.isTypeLiteralNode(node)) {
    const fields: Record<string, { shape: ValueShape; optional: boolean }> = {};
    for (const member of node.members) {
      require_(ts.isPropertySignature(member) && ts.isIdentifier(member.name), "CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE", `${what} must contain plain property signatures`);
      fields[member.name.text] = { shape: shapeFromTypeNode(member.type, `${what}.${member.name.text}`, localTypes), optional: member.questionToken !== undefined };
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
      require_(shape.kind !== "array", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}.${fieldName} cannot be an array field inside a rendered list element`);
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
    require_(field.shape.kind !== "array", "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT", `${what}.${name} cannot be an array field inside a rendered list element`);
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
  if (expr.kind === "regexTest") return { kind: "regexTest", pattern: expr.pattern, flags: expr.flags, operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "arrayLength") return { kind: "arrayLength", operand: substitutePureFunctionParameters(expr.operand, substitutions) };
  if (expr.kind === "ternary") return { kind: "ternary", condition: substitutePureFunctionParameters(expr.condition, substitutions), then: substitutePureFunctionParameters(expr.then, substitutions), else: substitutePureFunctionParameters(expr.else, substitutions) };
  return expr;
}

function parseExpr(node: ts.Expression, staticMaps: StaticStringMaps = new Map(), eventParameter?: string, pureFunctionStack: readonly string[] = []): Expr {
  if (ts.isParenthesizedExpression(node)) return parseExpr(node.expression, staticMaps, eventParameter, pureFunctionStack);
  if (isEventTargetValue(node, eventParameter)) return { kind: "eventValue" };
  if (ts.isIdentifier(node)) return { kind: "ident", name: node.text };
  if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
    const functionName = node.expression.text;
    const definition = staticMaps.get(functionName);
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
    const methodName = node.expression.name.text;
    if (ts.isIdentifier(node.expression.expression) && node.expression.expression.text === "Math" && ["min", "max", "floor", "ceil", "abs"].includes(methodName)) {
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
    require_(["toUpperCase", "toLowerCase", "trim", "replaceAll", "includes", "startsWith", "endsWith", "slice"].includes(method), "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `string method ${method} is outside certified-component-v1`);
      const args = node.arguments.map((argument) => parseExpr(argument, staticMaps, eventParameter, pureFunctionStack));
    const expectedArgs = method === "replaceAll" ? 2 : method === "includes" || method === "startsWith" || method === "endsWith" ? 1 : method === "slice" ? 1 : 0;
    require_(method === "slice" ? args.length <= 2 && args.length >= 1 : args.length === expectedArgs, "CERTIFIED_COMPONENT_STRING_METHOD_ARITY", `${method} expects ${method === "slice" ? "one or two" : expectedArgs} argument(s)`);
    const argumentType = method === "slice" ? "number" : "string";
    require_((method !== "replaceAll" && method !== "includes" && method !== "startsWith" && method !== "endsWith" && method !== "slice") || args.every((arg) => arg.kind === "literal" && arg.literal.type === argumentType), "CERTIFIED_COMPONENT_STRING_METHOD_ARGUMENT", `${method} arguments must be ${argumentType} literals`);
    return { kind: "stringMethod", method, receiver: parseExpr(node.expression.expression, staticMaps, eventParameter, pureFunctionStack), args };
  }
  if (ts.isPropertyAccessExpression(node) && ts.isElementAccessExpression(node.expression) && ts.isIdentifier(node.expression.expression)) {
    const table = staticMaps.get(node.expression.expression.text);
    require_(table !== undefined && isStaticStringMapDefinition(table), "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `computed access ${node.expression.getText()} is not a declared certified static string map`);
    require_(node.expression.argumentExpression !== undefined, "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `computed access ${node.expression.getText()} is missing its key`);
    const fieldTables = new Map<string, string>();
    for (const [key, entry] of table.entries()) {
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
    require_(table !== undefined && isStaticStringMapDefinition(table), "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `computed access ${node.expression.text}[...] is not a declared certified static string map`);
    const values = new Map<string, string>();
    for (const [key, entry] of table.entries()) {
      require_(typeof entry === "string", "CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS", `static map ${node.expression.text} entry ${key} is an object and must select a field`);
      values.set(key, entry);
    }
    return staticLookupExpression(values, parseExpr(node.argumentExpression, staticMaps, eventParameter));
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
  fail("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION", `expression kind ${ts.SyntaxKind[node.kind]} is outside certified-component-v1`);
}

/** Parses a certified-component-v1 event handler arrow function body:
 * `() => setCount(count + 1)`, `() => setCount(!on)`,
 * `(v) => onChange(v)` -- a single expression statement, or a block of
 * such statements, each either a setState call or a callback-prop call. */
function parseHandlerBody(fn: ts.ArrowFunction, staticMaps: StaticStringMaps = new Map()): Stmt[] {
  const parameterName = fn.parameters[0]?.name;
  const eventParameter = fn.parameters.length === 1 && parameterName !== undefined && ts.isIdentifier(parameterName)
    ? parameterName.text
    : undefined;
  const exprToStmt = (expr: ts.Expression): Stmt => {
    require_(ts.isCallExpression(expr) && ts.isIdentifier(expr.expression), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT", "handler statement must be a single call expression");
    const call = expr as ts.CallExpression;
    const callee = (call.expression as ts.Identifier).text;
    const fourth = callee[3];
    if (callee.startsWith("set") && fourth !== undefined && fourth === fourth.toUpperCase() && fourth !== fourth.toLowerCase()) {
      require_(call.arguments.length === 1, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} must be called with exactly one argument`);
      const stateName = fourth.toLowerCase() + callee.slice(4);
      return { kind: "setState", target: stateName, value: parseExpr(at(call.arguments, 0, "CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY", `${callee} is missing its argument`), staticMaps, eventParameter) };
    }
    require_(/^on[A-Z]/.test(callee), "CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_CALL", `handler call target ${JSON.stringify(callee)} is neither a setState-style call nor an on*-named callback prop`);
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

const JSX_EVENT_PROP_TO_EVENT_NAME: Record<string, EventName> = {
  onClick: "onClick", onChange: "onChange", onInput: "onInput", onSubmit: "onSubmit",
};

function parseJsxChildren(children: ts.NodeArray<ts.JsxChild>, staticMaps: StaticStringMaps = new Map()): CNode[] {
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
          condition: parseExpr(expr.condition, staticMaps),
          then: parseJsxNode(expr.whenTrue, staticMaps),
          else: expr.whenFalse.kind === ts.SyntaxKind.NullKeyword ? null : parseJsxNode(expr.whenFalse, staticMaps),
        });
        continue;
      }
      if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && isJsxLike(expr.right)) {
        result.push({ kind: "conditional", condition: parseExpr(expr.left, staticMaps), then: parseJsxNode(expr.right, staticMaps), else: null });
        continue;
      }
      const listNode = tryParseListExpression(expr, staticMaps);
      if (listNode !== null) {
        result.push(listNode);
        continue;
      }
      if (isJsxLike(expr)) {
        result.push(parseJsxNode(expr, staticMaps));
        continue;
      }
      result.push({ kind: "text", value: parseExpr(expr, staticMaps) });
      continue;
    }
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child)) {
      result.push(parseJsxNode(child, staticMaps));
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
function tryParseListExpression(expr: ts.Expression, staticMaps: StaticStringMaps = new Map()): CNode | null {
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
  require_(ts.isIdentifier(param.name), "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK", `${source}.map parameter must be a plain identifier (no destructuring)`);
  const itemName = (param.name as ts.Identifier).text;

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
      if (ts.isIdentifier(keyExpression)) {
        require_(keyExpression.text === itemName, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must use the current item, not an unrelated identifier`);
      } else if (ts.isPropertyAccessExpression(keyExpression) && ts.isIdentifier(keyExpression.expression)) {
        require_(keyExpression.expression.text === itemName, "CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must read a direct field from the current item`);
        keyField = keyExpression.name.text;
      } else {
        fail("CERTIFIED_COMPONENT_UNSUPPORTED_LIST_KEY", `${source}.map key must be the item itself or a direct item field; composite and index keys are not certified`);
      }
    }
  }
  return { kind: "list", source, sourceExpression: sourceExpression.kind === "ident" ? undefined : sourceExpression, itemName, ...(keyField === undefined ? {} : { keyField }), body: parseJsxNode(body, staticMaps) };
}

function applyExplicitListKeys(root: CNode, props: PropDef[]): void {
  const lists = new Map(props.filter((prop): prop is ListPropDef => prop.kind === "list").map((prop) => [prop.name, prop]));
  const visit = (node: CNode): void => {
    if (node.kind === "list") {
      if (node.keyField !== undefined) {
        const list = lists.get(node.source);
        if (list !== undefined) {
          if (list.keyField === undefined) list.keyField = node.keyField;
          else require_(list.keyField === node.keyField, "CERTIFIED_COMPONENT_CONFLICTING_LIST_KEY", `list node ${JSON.stringify(node.source)} key conflicts with the declared list key`);
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

function parseJsxNode(rawNode: ts.Expression, staticMaps: StaticStringMaps = new Map()): CNode {
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
        props.push({ name, value: parseExpr(jsxAttr.initializer.expression, staticMaps) });
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
      events.push({ name: mappedEvent, body: parseHandlerBody(init, staticMaps) });
      continue;
    }
    const attrName = jsxAttrName(rawName);
    if (jsxAttr.initializer === undefined) {
      attrs.push({ kind: "static", name: attrName, value: "true" });
    } else if (ts.isStringLiteral(jsxAttr.initializer)) {
      attrs.push({ kind: "static", name: attrName, value: jsxAttr.initializer.text });
    } else if (ts.isJsxExpression(jsxAttr.initializer) && jsxAttr.initializer.expression) {
      attrs.push({ kind: "dynamic", name: attrName, value: parseExpr(jsxAttr.initializer.expression, staticMaps) });
    } else {
      fail("CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE", `attribute ${JSON.stringify(rawName)} has an unsupported value shape`);
    }
  }

  const children = ts.isJsxElement(node) ? parseJsxChildren(node.children, staticMaps) : [];
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

interface LocalExpressionDefinition {
  expression?: Expr;
  fields?: ReadonlyMap<string, Expr>;
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
    case "cssModuleClass": return expr;
    case "eventValue": return expr;
    case "regexTest": return {
      kind: "regexTest",
      pattern: expr.pattern,
      flags: expr.flags,
      operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack),
    };
    case "arrayLength": return { kind: "arrayLength", operand: expandLocalExpression(expr.operand, definitions, ownerOrder, stack) };
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
  if (table === undefined || !isStaticStringMapDefinition(table)) return null;
  const key = parseExpr(initializer.argumentExpression, staticMaps);
  const fieldNames = new Set<string>();
  for (const entry of table.values()) {
    if (typeof entry === "string") return null;
    for (const fieldName of entry.keys()) fieldNames.add(fieldName);
  }
  const fields = new Map<string, Expr>();
  for (const fieldName of fieldNames) {
    const values = new Map<string, string>();
    for (const [entryName, entry] of table.entries()) {
      if (typeof entry === "string") return null;
      const value = entry.get(fieldName);
      if (value === undefined) return null;
      values.set(entryName, value);
    }
    fields.set(fieldName, staticLookupExpression(values, key));
  }
  return fields.size > 0 ? fields : null;
}

function expandLocalNode(node: CNode, definitions: ReadonlyMap<string, LocalExpressionDefinition>): CNode {
  if (node.kind === "text") return { kind: "text", value: expandLocalExpression(node.value, definitions) };
  if (node.kind === "conditional") return {
    kind: "conditional",
    condition: expandLocalExpression(node.condition, definitions),
    then: expandLocalNode(node.then, definitions),
    else: node.else === null ? null : expandLocalNode(node.else, definitions),
  };
  if (node.kind === "list") return { ...node, body: expandLocalNode(node.body, definitions) };
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
  const staticMaps = collectStaticStringMaps(options.sourceFile ?? fn.getSourceFile());

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
      const typeText = checkerType !== undefined
        ? options.project?.checker.typeToString(checkerType, element.name, ts.TypeFormatFlags.NoTruncation) ?? ""
        : typeNode?.getText() ?? "";
      if (propName === "children" && /ReactNode|ReactElement|ReactPortal/.test(typeText)) {
        props.push({ kind: "data", name: propName, propType: "string", valueShape: { kind: "slot", slotName: "children", nullable: true }, required: false });
        continue;
      }
      if (/^on[A-Z]/.test(propName)) {
        const callbackTypeNode = typeNode;
        let paramType: PrimitiveType | undefined;
        if (checkerType !== undefined) {
          const signatures = options.project?.checker.getSignaturesOfType(checkerType, ts.SignatureKind.Call) ?? [];
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
  const localDefinitions = new Map<string, LocalExpressionDefinition>();
  let returnStatement: ts.ReturnStatement | undefined;
  for (const [statementOrder, stmt] of body.statements.entries()) {
    if (ts.isVariableStatement(stmt)) {
      require_(stmt.declarationList.declarations.length === 1, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "only one declaration per const statement is supported");
      const decl = at(stmt.declarationList.declarations, 0, "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT", "missing declaration");
      const declName = decl.name;
      if (ts.isIdentifier(declName) && decl.initializer !== undefined) {
        const fields = staticObjectAliasFields(decl.initializer, staticMaps);
        localDefinitions.set(declName.text, fields === null
          ? { expression: parseExpr(decl.initializer, staticMaps), order: statementOrder }
          : { fields, order: statementOrder });
        continue;
      }
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
      let stateType: PrimitiveType = initial.type === "null" ? "string" : initial.type;
      let nullable = initial.type === "null";
      if (initial.type === "null") {
        const checker = options.project?.checker;
        const declared = checker !== undefined
          ? valueShapeFromChecker(checker.getTypeAtLocation(getterEl.name), checker, getterEl.name, `state ${getterName}`)
          : initializer.typeArguments?.[0] !== undefined
            ? shapeFromTypeNode(initializer.typeArguments[0], `state ${getterName}`, localTypes)
            : undefined;
        require_(declared?.kind === "primitive", "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE", `nullable state ${JSON.stringify(getterName)} must declare a primitive base type`);
        stateType = declared.primitive;
        nullable = true;
      }
      state.push({ name: getterName, stateType, ...(nullable ? { nullable: true } : {}), initial });
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
  const root = expandLocalNode(parseJsxNode(returned, staticMaps), localDefinitions);

  const nestedLists = materializeNestedLists(root, props);
  const component: ComponentDef = { name, props, state, root, ...(nestedLists.length === 0 ? {} : { lists: nestedLists }) };
  applyExplicitListKeys(root, props);
  validateComponent(component);
  return component;
}

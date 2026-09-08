import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [typescriptPath, sourcePath, selector, mode] = process.argv.slice(2);
if (!typescriptPath || !sourcePath || !selector || (mode && mode !== "--emitted-target")) {
  throw new Error(
    "usage: analyzer.mjs <typescript-module> <source> <function|--inventory> [--emitted-target]",
  );
}

const imported = await import(pathToFileURL(typescriptPath).href);
const ts = imported.default ?? imported;
const source = fs.readFileSync(sourcePath, "utf8");
const sourceFileName = path.basename(sourcePath);
const tree = ts.createSourceFile(
  sourceFileName,
  source,
  ts.ScriptTarget.ES2022,
  true,
  ts.ScriptKind.JS,
);
const emittedTarget = mode === "--emitted-target";

function byteOffset(characterOffset) {
  return Buffer.byteLength(source.slice(0, characterOffset), "utf8");
}

function span(node) {
  return {
    file: sourceFileName,
    start_byte: byteOffset(node.getStart(tree)),
    end_byte: byteOffset(node.end),
  };
}

function parseDiagnostics() {
  return (tree.parseDiagnostics ?? []).map((item) => {
    const line = tree.getLineAndCharacterOfPosition(item.start ?? 0).line + 1;
    return `JS${item.code}:${line}`;
  });
}

const CANONICAL_TYPES = new Set(["integer", "number", "boolean", "string"]);

function exactType(node, label) {
  const value = node?.getText(tree) ?? "";
  if (!CANONICAL_TYPES.has(value)) {
    throw new Error(`JAVASCRIPT_EXACT_JSDOC_TYPE_REQUIRED:${label}:${value || "<missing>"}`);
  }
  return value;
}

function functionContract(node) {
  if (!node.name || !node.body) throw new Error("JAVASCRIPT_FUNCTION_BODY_REQUIRED");
  if (node.asteriskToken || node.typeParameters || node.questionToken) {
    throw new Error(`JAVASCRIPT_FUNCTION_SHAPE_UNSUPPORTED:${node.name.text}`);
  }
  const modifiers = [...(node.modifiers ?? [])].map((item) => item.kind);
  if (modifiers.includes(ts.SyntaxKind.AsyncKeyword)) {
    throw new Error(`JAVASCRIPT_ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET:${node.name.text}`);
  }
  if (modifiers.length !== 1 || modifiers[0] !== ts.SyntaxKind.ExportKeyword) {
    throw new Error(`JAVASCRIPT_NAMED_EXPORT_REQUIRED:${node.name.text}`);
  }
  const tags = [...ts.getJSDocTags(node)];
  if (tags.length !== node.parameters.length + 1) {
    throw new Error(`JAVASCRIPT_EXACT_JSDOC_TAG_SET_REQUIRED:${node.name.text}`);
  }
  const parameters = node.parameters.map((parameter, index) => {
    if (
      !ts.isIdentifier(parameter.name)
      || parameter.dotDotDotToken
      || parameter.questionToken
      || parameter.initializer
    ) {
      throw new Error(`JAVASCRIPT_PARAMETER_SHAPE_UNSUPPORTED:${node.name.text}:${index}`);
    }
    const tag = tags[index];
    const tagName = tag?.tagName?.text;
    const declaredName = tag?.name?.getText?.(tree) ?? "";
    if (tagName !== "param" || declaredName !== parameter.name.text) {
      throw new Error(`JAVASCRIPT_JSDOC_PARAMETER_ORDER_INVALID:${node.name.text}:${parameter.name.text}`);
    }
    return {
      name: parameter.name.text,
      type: exactType(tag.typeExpression?.type, `${node.name.text}:${parameter.name.text}`),
      source_span: span(parameter.name),
    };
  });
  const returnTag = tags.at(-1);
  if (returnTag?.tagName?.text !== "returns" || returnTag.name !== undefined) {
    throw new Error(`JAVASCRIPT_JSDOC_RETURN_INVALID:${node.name.text}`);
  }
  return {
    parameters,
    returnType: exactType(returnTag.typeExpression?.type, `${node.name.text}:return`),
  };
}

function calleeName(node) {
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression)) {
    return `${node.expression.text}.${node.name.text}`;
  }
  return "";
}

function exactCall(node, name, arity) {
  return ts.isCallExpression(node)
    && node.typeArguments === undefined
    && calleeName(node.expression) === name
    && node.arguments.length === arity;
}

function operator(kind) {
  const values = new Map([
    [ts.SyntaxKind.PlusToken, "+"],
    [ts.SyntaxKind.MinusToken, "-"],
    [ts.SyntaxKind.AsteriskToken, "*"],
    [ts.SyntaxKind.SlashToken, "/"],
    [ts.SyntaxKind.PercentToken, "%"],
    [ts.SyntaxKind.LessThanToken, "<"],
    [ts.SyntaxKind.LessThanEqualsToken, "<="],
    [ts.SyntaxKind.GreaterThanToken, ">"],
    [ts.SyntaxKind.GreaterThanEqualsToken, ">="],
    [ts.SyntaxKind.EqualsEqualsEqualsToken, "=="],
    [ts.SyntaxKind.ExclamationEqualsEqualsToken, "!="],
    [ts.SyntaxKind.AmpersandAmpersandToken, "&&"],
    [ts.SyntaxKind.BarBarToken, "||"],
  ]);
  const value = values.get(kind);
  if (!value) throw new Error(`JAVASCRIPT_OPERATOR_UNSUPPORTED:${ts.SyntaxKind[kind]}`);
  return value;
}

function operatorDiagnosticSubject(value) {
  if (value === "/") return "division";
  if (value === "%") return "remainder";
  return value;
}

const TRANSPARENT_GUARDS = new Set([
  "_elmosRequireSafeInteger",
  "_elmosRequireFiniteNumber",
  "_elmosRequireBoolean",
  "_elmosRequireString",
]);

function expression(node, options = {}) {
  const { allowNonZero = false, allowMathTrunc = false } = options;
  if (ts.isParenthesizedExpression(node)) {
    return expression(node.expression, options);
  }
  if (ts.isIdentifier(node)) {
    return { kind: "name", value: node.text, source_span: span(node) };
  }
  if (ts.isNumericLiteral(node)) {
    const value = Number(node.text);
    if (!Number.isFinite(value)) throw new Error("JAVASCRIPT_NON_FINITE_LITERAL_UNSUPPORTED");
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw new Error("JAVASCRIPT_INTEGER_LITERAL_OUTSIDE_SAFE_SUBSET");
    }
    return { kind: "literal", value, source_span: span(node) };
  }
  if (
    ts.isPrefixUnaryExpression(node)
    && node.operator === ts.SyntaxKind.MinusToken
    && ts.isNumericLiteral(node.operand)
  ) {
    const value = -Number(node.operand.text);
    if (!Number.isFinite(value)) throw new Error("JAVASCRIPT_NON_FINITE_LITERAL_UNSUPPORTED");
    if (Object.is(value, -0)) throw new Error("JAVASCRIPT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED");
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw new Error("JAVASCRIPT_INTEGER_LITERAL_OUTSIDE_SAFE_SUBSET");
    }
    return { kind: "literal", value, source_span: span(node) };
  }
  if (ts.isStringLiteral(node)) {
    return { kind: "literal", value: node.text, source_span: span(node) };
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) {
    return {
      kind: "literal",
      value: node.kind === ts.SyntaxKind.TrueKeyword,
      source_span: span(node),
    };
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = operator(node.operatorToken.kind);
    const guarded = liftedOperator === "/" || liftedOperator === "%";
    if (emittedTarget && guarded && !exactCall(node.right, "_elmosRequireNonZero", 1)) {
      throw new Error(
        `JAVASCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:${operatorDiagnosticSubject(liftedOperator)}`,
      );
    }
    return {
      kind: "binary",
      operator: liftedOperator,
      left: expression(node.left),
      right: expression(node.right, { allowNonZero: emittedTarget && guarded }),
      source_span: span(node),
    };
  }
  if (ts.isCallExpression(node) && emittedTarget) {
    const name = calleeName(node.expression);
    if (TRANSPARENT_GUARDS.has(name)) {
      if (!exactCall(node, name, 1)) {
        throw new Error(`JAVASCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name}`);
      }
      const argument = node.arguments[0];
      if (name === "_elmosRequireSafeInteger" && exactCall(argument, "Math.trunc", 1)) {
        return expression(argument, { allowMathTrunc: true });
      }
      return expression(argument);
    }
    if (name === "_elmosRequireNonZero") {
      if (!allowNonZero || !exactCall(node, name, 1)) {
        throw new Error("JAVASCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
      }
      return expression(node.arguments[0]);
    }
    if (name === "Math.trunc") {
      if (!allowMathTrunc || !exactCall(node, name, 1)) {
        throw new Error("JAVASCRIPT_EMITTED_TRUNCATION_INVALID");
      }
      const argument = node.arguments[0];
      if (!ts.isBinaryExpression(argument) || argument.operatorToken.kind !== ts.SyntaxKind.SlashToken) {
        throw new Error("JAVASCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      return expression(argument);
    }
  }
  throw new Error(`JAVASCRIPT_EXPRESSION_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
}

function statementNodes(node) {
  return ts.isBlock(node) ? [...node.statements] : [node];
}

function returnExpressions(nodes) {
  const values = [];
  for (const node of nodes) {
    if (ts.isReturnStatement(node) && node.expression) values.push(node.expression);
    if (ts.isIfStatement(node)) {
      values.push(...returnExpressions(statementNodes(node.thenStatement)));
      if (node.elseStatement) values.push(...returnExpressions(statementNodes(node.elseStatement)));
    }
  }
  return values;
}

function statements(nodes) {
  return nodes.map((node) => {
    if (ts.isReturnStatement(node) && node.expression) {
      return {
        kind: "return",
        expression: expression(node.expression),
        source_span: span(node),
      };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: expression(node.expression),
        then: statements(statementNodes(node.thenStatement)),
        else: node.elseStatement ? statements(statementNodes(node.elseStatement)) : [],
        source_span: span(node),
      };
    }
    throw new Error(`JAVASCRIPT_STATEMENT_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
  });
}

const PARAMETER_GUARDS = {
  integer: "_elmosRequireSafeInteger",
  number: "_elmosRequireFiniteNumber",
  boolean: "_elmosRequireBoolean",
  string: "_elmosRequireString",
};

const ARITHMETIC_OPERATORS = new Set(["+", "-", "*", "/", "%"]);
const ORDERING_OPERATORS = new Set(["<", "<=", ">", ">="]);
const EQUALITY_OPERATORS = new Set(["==", "!="]);
const LOGICAL_OPERATORS = new Set(["&&", "||"]);
const NUMERIC_TYPES = new Set(["integer", "number"]);

function emittedExpressionType(node, environment) {
  if (ts.isParenthesizedExpression(node)) {
    return emittedExpressionType(node.expression, environment);
  }
  if (ts.isIdentifier(node)) {
    const value = environment.get(node.text);
    if (value === undefined) throw new Error(`JAVASCRIPT_EMITTED_NAME_UNDECLARED:${node.text}`);
    return value;
  }
  if (ts.isNumericLiteral(node)) {
    return /[.eE]/.test(node.getText(tree)) ? "number" : "integer";
  }
  if (
    ts.isPrefixUnaryExpression(node)
    && node.operator === ts.SyntaxKind.MinusToken
    && ts.isNumericLiteral(node.operand)
  ) {
    return emittedExpressionType(node.operand, environment);
  }
  if (ts.isStringLiteral(node)) return "string";
  if (node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) {
    return "boolean";
  }
  if (ts.isCallExpression(node)) {
    const name = calleeName(node.expression);
    if (!exactCall(node, name, 1)) {
      throw new Error(`JAVASCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
    }
    if (name === "_elmosRequireSafeInteger" || name === "Math.trunc") return "integer";
    if (name === "_elmosRequireFiniteNumber") return "number";
    if (name === "_elmosRequireBoolean") return "boolean";
    if (name === "_elmosRequireString") return "string";
    if (name === "_elmosRequireNonZero") {
      return emittedExpressionType(node.arguments[0], environment);
    }
    throw new Error(`JAVASCRIPT_EMITTED_CALL_UNSUPPORTED:${name || "unknown"}`);
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = operator(node.operatorToken.kind);
    const left = emittedExpressionType(node.left, environment);
    const right = emittedExpressionType(node.right, environment);
    if (ARITHMETIC_OPERATORS.has(liftedOperator)) {
      if (liftedOperator === "+" && left === "string" && right === "string") return "string";
      if (!NUMERIC_TYPES.has(left) || !NUMERIC_TYPES.has(right)) {
        throw new Error(`JAVASCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return left === "number" || right === "number" ? "number" : "integer";
    }
    if (ORDERING_OPERATORS.has(liftedOperator)) {
      if (!NUMERIC_TYPES.has(left) || !NUMERIC_TYPES.has(right)) {
        throw new Error(`JAVASCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return "boolean";
    }
    if (EQUALITY_OPERATORS.has(liftedOperator)) {
      if (left !== right && !(NUMERIC_TYPES.has(left) && NUMERIC_TYPES.has(right))) {
        throw new Error(`JAVASCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return "boolean";
    }
    if (LOGICAL_OPERATORS.has(liftedOperator)) {
      if (left !== "boolean" || right !== "boolean") {
        throw new Error(`JAVASCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return "boolean";
    }
  }
  throw new Error(`JAVASCRIPT_EMITTED_EXPRESSION_TYPE_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
}

function validateEmittedArithmeticExpression(
  node,
  environment,
  requiredGuard = null,
  allowNonZero = false,
) {
  if (ts.isParenthesizedExpression(node)) {
    validateEmittedArithmeticExpression(node.expression, environment, requiredGuard, allowNonZero);
    return;
  }
  if (ts.isIdentifier(node) || ts.isNumericLiteral(node) || ts.isStringLiteral(node)) return;
  if (node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) return;
  if (
    ts.isPrefixUnaryExpression(node)
    && node.operator === ts.SyntaxKind.MinusToken
    && ts.isNumericLiteral(node.operand)
  ) {
    return;
  }
  if (ts.isCallExpression(node)) {
    const name = calleeName(node.expression);
    if (!exactCall(node, name, 1)) {
      throw new Error(`JAVASCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
    }
    if (name === "_elmosRequireSafeInteger" || name === "_elmosRequireFiniteNumber") {
      validateEmittedArithmeticExpression(
        node.arguments[0],
        environment,
        name === "_elmosRequireSafeInteger" ? "integer" : "number",
      );
      return;
    }
    if (name === "_elmosRequireBoolean" || name === "_elmosRequireString") {
      validateEmittedArithmeticExpression(node.arguments[0], environment);
      return;
    }
    if (name === "_elmosRequireNonZero") {
      if (!allowNonZero) throw new Error("JAVASCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
      validateEmittedArithmeticExpression(node.arguments[0], environment);
      return;
    }
    if (name === "Math.trunc") {
      const argument = node.arguments[0];
      if (
        requiredGuard !== "integer"
        || !ts.isBinaryExpression(argument)
        || argument.operatorToken.kind !== ts.SyntaxKind.SlashToken
      ) {
        throw new Error("JAVASCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      validateEmittedArithmeticExpression(argument, environment, "integer");
      return;
    }
    throw new Error(`JAVASCRIPT_EMITTED_CALL_UNSUPPORTED:${name || "unknown"}`);
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = operator(node.operatorToken.kind);
    const resultType = emittedExpressionType(node, environment);
    if (
      ARITHMETIC_OPERATORS.has(liftedOperator)
      && (resultType === "integer" || resultType === "number")
      && requiredGuard !== resultType
    ) {
      throw new Error(
        `JAVASCRIPT_EMITTED_ARITHMETIC_GUARD_MISSING:${liftedOperator}:${resultType}`,
      );
    }
    const requiresNonZero = liftedOperator === "/" || liftedOperator === "%";
    if (requiresNonZero && !exactCall(node.right, "_elmosRequireNonZero", 1)) {
      throw new Error(
        `JAVASCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:${operatorDiagnosticSubject(liftedOperator)}`,
      );
    }
    validateEmittedArithmeticExpression(node.left, environment);
    validateEmittedArithmeticExpression(node.right, environment, null, requiresNonZero);
    return;
  }
  throw new Error(`JAVASCRIPT_EMITTED_EXPRESSION_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
}

function validateEmittedArithmeticStatements(nodes, contract) {
  const environment = new Map(contract.parameters.map((parameter) => [parameter.name, parameter.type]));
  const expectedReturnGuard = PARAMETER_GUARDS[contract.returnType];
  for (const node of nodes) {
    if (ts.isReturnStatement(node) && node.expression) {
      if (!exactCall(node.expression, expectedReturnGuard, 1)) {
        throw new Error(`JAVASCRIPT_EMITTED_RETURN_GUARD_INVALID:${expectedReturnGuard}`);
      }
      // The outer call is the return contract.  It cannot double as the
      // independently required guard on an arithmetic BinaryExpression.
      validateEmittedArithmeticExpression(node.expression.arguments[0], environment);
      continue;
    }
    if (ts.isIfStatement(node)) {
      validateEmittedArithmeticExpression(node.expression, environment);
      validateEmittedArithmeticStatements(statementNodes(node.thenStatement), contract);
      if (node.elseStatement) {
        validateEmittedArithmeticStatements(statementNodes(node.elseStatement), contract);
      }
      continue;
    }
    throw new Error(`JAVASCRIPT_EMITTED_STATEMENT_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
  }
}

const CANONICAL_EMITTED_HELPERS = new Map([
  [
    "_elmosRequireSafeInteger",
    `function _elmosRequireSafeInteger(value) {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError("ELMOS_INTEGER_OVERFLOW");
  }
  return Object.is(value, -0) ? 0 : value;
}`,
  ],
  [
    "_elmosRequireFiniteNumber",
    `function _elmosRequireFiniteNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError("ELMOS_NUMBER_NOT_FINITE");
  }
  return value;
}`,
  ],
  [
    "_elmosRequireBoolean",
    `function _elmosRequireBoolean(value) {
  if (typeof value !== "boolean") {
    throw new TypeError("ELMOS_BOOLEAN_REQUIRED");
  }
  return value;
}`,
  ],
  [
    "_elmosRequireString",
    `function _elmosRequireString(value) {
  if (typeof value !== "string") {
    throw new TypeError("ELMOS_STRING_REQUIRED");
  }
  return value;
}`,
  ],
  [
    "_elmosRequireNonZero",
    `function _elmosRequireNonZero(value) {
  if (value === 0) {
    throw new RangeError("ELMOS_DIVIDE_BY_ZERO");
  }
  return value;
}`,
  ],
  [
    "_elmosRequireRecord",
    `function _elmosRequireRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TypeError("ELMOS_RECORD_REQUIRED");
  }
  return value;
}`,
  ],
]);

const CANONICAL_EMITTED_HELPER_SIGNATURES = new Map([
  ["_elmosRequireSafeInteger", ["integer", "integer"]],
  ["_elmosRequireFiniteNumber", ["number", "number"]],
  ["_elmosRequireBoolean", ["boolean", "boolean"]],
  ["_elmosRequireString", ["string", "string"]],
  ["_elmosRequireNonZero", ["number", "number"]],
  ["_elmosRequireRecord", ["record", "record"]],
]);

function canonicalEmittedHelperSignature(node, declarationCounts) {
  const name = node.name?.text ?? "";
  const expectedSource = CANONICAL_EMITTED_HELPERS.get(name);
  const canonicalTypes = CANONICAL_EMITTED_HELPER_SIGNATURES.get(name);
  if (
    expectedSource === undefined
    || canonicalTypes === undefined
    || declarationCounts.get(name) !== 1
    || node.getText(tree) !== expectedSource
  ) {
    return null;
  }
  const [parameterType, returnType] = canonicalTypes;
  return {
    parameters: [{ name: "value", source_type: parameterType }],
    source_return_type: returnType,
    visibility: "internal",
    storage: "file-scope",
  };
}

function validateEmittedHelperDeclarations(userFunctions) {
  const used = new Set();
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const name = calleeName(node.expression);
      if (name.startsWith("_elmos")) used.add(name);
    }
    ts.forEachChild(node, visit);
  }
  for (const userFunction of userFunctions) visit(userFunction);

  const declarations = new Map();
  for (const statement of tree.statements) {
    if (!ts.isFunctionDeclaration(statement) || !statement.name?.text.startsWith("_elmos")) continue;
    const name = statement.name.text;
    const values = declarations.get(name) ?? [];
    values.push(statement);
    declarations.set(name, values);
  }
  for (const name of new Set([...used, ...declarations.keys()])) {
    const expected = CANONICAL_EMITTED_HELPERS.get(name);
    const values = declarations.get(name) ?? [];
    if (
      expected === undefined
      || !used.has(name)
      || values.length !== 1
      || values[0].getText(tree) !== expected
    ) {
      throw new Error(`JAVASCRIPT_EMITTED_HELPER_SOURCE_MISMATCH:${name}`);
    }
  }
}

function emittedBody(body, contract) {
  const nodes = [...body.statements];
  if (nodes.length < contract.parameters.length) {
    throw new Error("JAVASCRIPT_EMITTED_PARAMETER_GUARD_MISSING");
  }
  contract.parameters.forEach((parameter, index) => {
    const node = nodes[index];
    const expected = PARAMETER_GUARDS[parameter.type];
    const expression = ts.isExpressionStatement(node) ? node.expression : undefined;
    const guardedExpression = parameter.type === "integer"
      && expression !== undefined
      && ts.isBinaryExpression(expression)
      && expression.operatorToken.kind === ts.SyntaxKind.EqualsToken
      && ts.isIdentifier(expression.left)
      && expression.left.text === parameter.name
      ? expression.right
      : expression;
    if (
      guardedExpression === undefined
      || !exactCall(guardedExpression, expected, 1)
      || !ts.isIdentifier(guardedExpression.arguments[0])
      || guardedExpression.arguments[0].text !== parameter.name
      || (parameter.type === "integer" && guardedExpression === expression)
    ) {
      throw new Error(`JAVASCRIPT_EMITTED_PARAMETER_GUARD_INVALID:${parameter.name}`);
    }
  });
  const result = nodes.slice(contract.parameters.length);
  const expectedReturn = PARAMETER_GUARDS[contract.returnType];
  const returns = returnExpressions(result);
  if (returns.length === 0 || !returns.every((item) => exactCall(item, expectedReturn, 1))) {
    throw new Error(`JAVASCRIPT_EMITTED_RETURN_GUARD_INVALID:${expectedReturn}`);
  }
  validateEmittedArithmeticStatements(result, contract);
  return result;
}

function analyzeFunction(node) {
  const contract = functionContract(node);
  const body = emittedTarget ? emittedBody(node.body, contract) : [...node.body.statements];
  return {
    name: node.name.text,
    parameters: contract.parameters,
    return_type: contract.returnType,
    body: statements(body),
    source_span: span(node),
  };
}

function inventory() {
  const diagnostics = parseDiagnostics();
  const subjects = [];
  const helperDeclarationCounts = new Map();
  for (const statement of tree.statements) {
    const name = ts.isFunctionDeclaration(statement) ? statement.name?.text ?? "" : "";
    if (name.startsWith("_elmos")) {
      helperDeclarationCounts.set(name, (helperDeclarationCounts.get(name) ?? 0) + 1);
    }
  }
  for (const statement of tree.statements) {
    if (ts.isFunctionDeclaration(statement)) {
      const name = statement.name?.text ?? `<anonymous-function@${statement.pos}>`;
      let contract = null;
      let signature = {};
      if (name.startsWith("_elmos")) {
        signature = canonicalEmittedHelperSignature(statement, helperDeclarationCounts) ?? {
          visibility: "not-applicable",
          storage: "not-applicable",
        };
      } else {
        try {
          contract = functionContract(statement);
        } catch {
          contract = null;
        }
        const isExported = statement.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword) ?? false;
        signature = {
          parameters: contract?.parameters.map((item) => ({
            name: item.name,
            source_type: item.type,
          })) ?? [],
          source_return_type: contract?.returnType ?? "",
          visibility: isExported ? "public" : "internal",
          storage: "file-scope",
        };
      }
      subjects.push({
        name,
        qualified_name: name,
        declaration_kind: "FunctionDeclaration",
        analyzable: name.startsWith("_elmos") ? Object.keys(signature).length !== 0 : contract !== null,
        source_span: span(statement),
        signature,
      });
      continue;
    }
    if (ts.isEmptyStatement(statement)) continue;
    const name = `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
    subjects.push({
      name,
      qualified_name: name,
      declaration_kind: ts.SyntaxKind[statement.kind],
      analyzable: false,
      source_span: span(statement),
      signature: {
        visibility: "not-applicable",
        storage: "not-applicable",
      },
    });
  }
  return {
    schema_version: "1.0.0",
    kind: "elmos.typed-pure-module-inventory",
    profile: "typed-pure-module-v1",
    source_language: "javascript",
    source_file: sourceFileName,
    analyzer: "TypeScript 5.9.2 JavaScript AST/JSDoc frontend",
    analyzer_version: `${ts.version} / Node ${process.versions.node}`,
    enumeration_status: diagnostics.length === 0 ? "PASSED" : "FAILED",
    subjects,
    diagnostics,
  };
}

function validateProgramClosure() {
  for (const statement of tree.statements) {
    if (ts.isFunctionDeclaration(statement) || ts.isEmptyStatement(statement)) continue;
    if (
      ts.isImportDeclaration(statement)
      || ts.isImportEqualsDeclaration(statement)
      || ts.isExportDeclaration(statement)
    ) {
      throw new Error("JAVASCRIPT_MODULE_IMPORT_EXPORT_OUTSIDE_CERTIFIED_SUBSET");
    }
    throw new Error(
      `JAVASCRIPT_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET:${ts.SyntaxKind[statement.kind]}`,
    );
  }
}

try {
  if (selector === "--inventory") {
    if (mode !== undefined) throw new Error("JAVASCRIPT_INVENTORY_MODE_INVALID");
    process.stdout.write(`${JSON.stringify(inventory())}\n`);
  } else {
    const diagnostics = parseDiagnostics();
    if (diagnostics.length !== 0) {
      throw new Error(`JAVASCRIPT_PARSE_DIAGNOSTICS:${diagnostics.join(",")}`);
    }
    validateProgramClosure();
    const candidates = tree.statements
      .filter(ts.isFunctionDeclaration)
      .filter((item) => item.name?.text === selector);
    if (candidates.length !== 1) {
      throw new Error(
        candidates.length === 0
          ? `FUNCTION_NOT_FOUND:${selector}`
          : `JAVASCRIPT_DUPLICATE_FUNCTION:${selector}`,
      );
    }
    if (emittedTarget) {
      const userFunctions = tree.statements
        .filter(ts.isFunctionDeclaration)
        .filter((item) => !item.name?.text.startsWith("_elmos"));
      validateEmittedHelperDeclarations(userFunctions);
    }
    const value = {
      schema_version: "1.0.0",
      source_language: "javascript",
      source_file: sourceFileName,
      analyzer: "TypeScript 5.9.2 JavaScript AST/JSDoc frontend",
      analyzer_version: `${ts.version} / Node ${process.versions.node}`,
      functions: [analyzeFunction(candidates[0])],
      diagnostics,
    };
    process.stdout.write(`${JSON.stringify(value)}\n`);
  }
} catch (error) {
  const message = error instanceof Error ? error.message : "JAVASCRIPT_ANALYZER_FAILED";
  const safe = /^[A-Za-z0-9_.:<>=/+,\-]+$/.test(message)
    ? message
    : "JAVASCRIPT_ANALYZER_FAILED";
  process.stderr.write(`${safe}\n`);
  process.exitCode = 2;
}

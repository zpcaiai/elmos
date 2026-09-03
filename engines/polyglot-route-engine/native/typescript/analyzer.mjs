import fs from "node:fs";
import { pathToFileURL } from "node:url";

const arguments_ = process.argv.slice(2);
if (arguments_.length < 3 || arguments_.length > 4) {
  throw new Error(
    "usage: analyzer.mjs <typescript-module> <source> <function|--inventory> [--emitted-target]",
  );
}
const [typescriptPath, sourcePath, selector, mode] = arguments_;
const emittedTarget = mode === "--emitted-target";
if (
  !typescriptPath
  || !sourcePath
  || !selector
  || (mode !== undefined && !emittedTarget)
  || (selector === "--inventory" && emittedTarget)
) {
  throw new Error("TYPESCRIPT_ANALYZER_COMMAND_SHAPE_INVALID");
}

const imported = await import(pathToFileURL(typescriptPath).href);
const ts = imported.default ?? imported;
const source = fs.readFileSync(sourcePath, "utf8");
const sourceName = sourcePath.split(/[\\/]/).at(-1);
const sourceFile = ts.createSourceFile(
  sourceName,
  source,
  ts.ScriptTarget.ES2022,
  true,
  ts.ScriptKind.TS,
);

function typeName(node) {
  if (!node) throw new Error("TYPESCRIPT_EXPLICIT_TYPE_REQUIRED");
  const value = node.getText(sourceFile);
  if (value === "number") return "number";
  if (value === "boolean") return "boolean";
  if (value === "string") return "string";
  throw new Error(`TYPESCRIPT_UNSUPPORTED_TYPE:${value}`);
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

const ARITHMETIC_OPERATORS = new Set(["+", "-", "*", "/", "%"]);
const ORDERING_OPERATORS = new Set(["<", "<=", ">", ">="]);
const EQUALITY_OPERATORS = new Set(["==", "!="]);
const LOGICAL_OPERATORS = new Set(["&&", "||"]);
const NUMERIC_TYPES = new Set(["integer", "number"]);

const CANONICAL_EMITTED_HELPERS = new Map([
  [
    "_elmosRequireSafeInteger",
    `function _elmosRequireSafeInteger(value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(\`ELMOS_INTEGER_NOT_SAFE:\${value}\`);
  }
  return Object.is(value, -0) ? 0 : value;
}`,
  ],
  [
    "_elmosRequireFiniteNumber",
    `function _elmosRequireFiniteNumber(value: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError("ELMOS_NUMBER_NOT_FINITE");
  }
  return value;
}`,
  ],
  [
    "_elmosRequireNonZero",
    `function _elmosRequireNonZero(value: number): number {
  if (value === 0) {
    throw new RangeError("ELMOS_DIVIDE_BY_ZERO");
  }
  return value;
}`,
  ],
]);

const CANONICAL_EMITTED_HELPER_SIGNATURES = new Map([
  ["_elmosRequireSafeInteger", ["integer", "integer"]],
  ["_elmosRequireFiniteNumber", ["number", "number"]],
  ["_elmosRequireNonZero", ["number", "number"]],
]);

function canonicalEmittedHelperSignature(node, declarationCounts) {
  const name = node.name?.text ?? "";
  const expectedSource = CANONICAL_EMITTED_HELPERS.get(name);
  const canonicalTypes = CANONICAL_EMITTED_HELPER_SIGNATURES.get(name);
  if (
    expectedSource === undefined
    || canonicalTypes === undefined
    || declarationCounts.get(name) !== 1
    || node.getText(sourceFile) !== expectedSource
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

function validateEmittedHelperDeclarations() {
  const used = new Set();
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const name = calleeName(node.expression);
      if (name.startsWith("_elmos")) used.add(name);
    }
    ts.forEachChild(node, visit);
  }
  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement) && !statement.name?.text.startsWith("_elmos")) {
      visit(statement);
    }
  }

  const declarations = new Map();
  for (const statement of sourceFile.statements) {
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
      || values[0].getText(sourceFile) !== expected
    ) {
      throw new Error(`TYPESCRIPT_EMITTED_HELPER_SOURCE_MISMATCH:${name}`);
    }
  }
}

function sourceOperator(kind) {
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
    [ts.SyntaxKind.EqualsEqualsToken, "=="],
    [ts.SyntaxKind.EqualsEqualsEqualsToken, "=="],
    [ts.SyntaxKind.ExclamationEqualsToken, "!="],
    [ts.SyntaxKind.ExclamationEqualsEqualsToken, "!="],
    [ts.SyntaxKind.AmpersandAmpersandToken, "&&"],
    [ts.SyntaxKind.BarBarToken, "||"],
  ]);
  const value = values.get(kind);
  if (!value) throw new Error(`TYPESCRIPT_UNSUPPORTED_OPERATOR:${ts.SyntaxKind[kind]}`);
  return value;
}

function emittedOperator(kind) {
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
  if (!value) {
    throw new Error(`TYPESCRIPT_EMITTED_OPERATOR_UNSUPPORTED:${ts.SyntaxKind[kind]}`);
  }
  return value;
}

function numericLiteralDetails(node) {
  const value = Number(node.text);
  if (!Number.isFinite(value)) {
    throw new Error("TYPESCRIPT_NON_FINITE_LITERAL_UNSUPPORTED");
  }
  return {
    value,
    type: /[.eE]/.test(node.getText(sourceFile)) ? "number" : "integer",
  };
}

function negativeNumericLiteralDetails(node) {
  if (!ts.isPrefixUnaryExpression(node)) return null;
  if (
    node.operator !== ts.SyntaxKind.MinusToken
    || !ts.isNumericLiteral(node.operand)
  ) {
    throw new Error("TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED");
  }
  const literal = numericLiteralDetails(node.operand);
  if (literal.value === 0) {
    throw new Error("TYPESCRIPT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED");
  }
  return { value: -literal.value, type: literal.type };
}

function sourceExpression(node) {
  if (ts.isParenthesizedExpression(node)) return sourceExpression(node.expression);
  if (ts.isIdentifier(node)) return { kind: "name", value: node.text };
  if (ts.isNumericLiteral(node)) {
    return { kind: "literal", value: numericLiteralDetails(node).value };
  }
  const negativeLiteral = negativeNumericLiteralDetails(node);
  if (negativeLiteral !== null) return { kind: "literal", value: negativeLiteral.value };
  if (ts.isStringLiteral(node)) return { kind: "literal", value: node.text };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { kind: "literal", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { kind: "literal", value: false };
  if (ts.isBinaryExpression(node)) {
    return {
      kind: "binary",
      operator: sourceOperator(node.operatorToken.kind),
      left: sourceExpression(node.left),
      right: sourceExpression(node.right),
    };
  }
  throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
}

function emittedExpression(node, { allowNonZero = false, allowMathTrunc = false } = {}) {
  if (ts.isParenthesizedExpression(node)) {
    return emittedExpression(node.expression, { allowNonZero, allowMathTrunc });
  }
  if (ts.isIdentifier(node)) return { kind: "name", value: node.text };
  if (ts.isNumericLiteral(node)) {
    return { kind: "literal", value: numericLiteralDetails(node).value };
  }
  const negativeLiteral = negativeNumericLiteralDetails(node);
  if (negativeLiteral !== null) return { kind: "literal", value: negativeLiteral.value };
  if (ts.isStringLiteral(node)) return { kind: "literal", value: node.text };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { kind: "literal", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { kind: "literal", value: false };
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = emittedOperator(node.operatorToken.kind);
    const guarded = liftedOperator === "/" || liftedOperator === "%";
    if (guarded && !exactCall(node.right, "_elmosRequireNonZero", 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:${liftedOperator}`);
    }
    return {
      kind: "binary",
      operator: liftedOperator,
      left: emittedExpression(node.left),
      right: emittedExpression(node.right, { allowNonZero: guarded }),
    };
  }
  if (ts.isCallExpression(node)) {
    const name = calleeName(node.expression);
    if (name === "_elmosRequireSafeInteger") {
      if (!exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_SAFE_INTEGER_SHAPE_INVALID");
      }
      const argument = node.arguments[0];
      if (exactCall(argument, "Math.trunc", 1)) {
        return emittedExpression(argument, { allowMathTrunc: true });
      }
      return emittedExpression(argument);
    }
    if (name === "_elmosRequireFiniteNumber") {
      if (!exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_FINITE_NUMBER_SHAPE_INVALID");
      }
      return emittedExpression(node.arguments[0]);
    }
    if (name === "_elmosRequireNonZero") {
      if (!allowNonZero || !exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
      }
      return emittedExpression(node.arguments[0]);
    }
    if (name === "Math.trunc") {
      if (!allowMathTrunc || !exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_INVALID");
      }
      const argument = node.arguments[0];
      if (!ts.isBinaryExpression(argument) || argument.operatorToken.kind !== ts.SyntaxKind.SlashToken) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      return emittedExpression(argument);
    }
    throw new Error(`TYPESCRIPT_EMITTED_HELPER_UNRECOGNIZED:${name || "<complex>"}`);
  }
  throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
}

function emittedExpressionType(node, environment) {
  if (ts.isParenthesizedExpression(node)) {
    return emittedExpressionType(node.expression, environment);
  }
  if (ts.isIdentifier(node)) {
    const value = environment.get(node.text);
    if (value === undefined) {
      throw new Error(`TYPESCRIPT_EMITTED_NAME_UNDECLARED:${node.text}`);
    }
    return value;
  }
  if (ts.isNumericLiteral(node)) {
    return numericLiteralDetails(node).type;
  }
  const negativeLiteral = negativeNumericLiteralDetails(node);
  if (negativeLiteral !== null) return negativeLiteral.type;
  if (ts.isStringLiteral(node)) return "string";
  if (node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) {
    return "boolean";
  }
  if (ts.isCallExpression(node)) {
    const name = calleeName(node.expression);
    if (!exactCall(node, name, 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
    }
    if (name === "_elmosRequireSafeInteger") {
      const argumentType = emittedExpressionType(node.arguments[0], environment);
      if (argumentType !== "integer") {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      return "integer";
    }
    if (name === "_elmosRequireFiniteNumber") {
      const argumentType = emittedExpressionType(node.arguments[0], environment);
      if (!NUMERIC_TYPES.has(argumentType)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      return "number";
    }
    if (name === "Math.trunc") return "integer";
    if (name === "_elmosRequireNonZero") {
      const argumentType = emittedExpressionType(node.arguments[0], environment);
      if (!NUMERIC_TYPES.has(argumentType)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      return argumentType;
    }
    throw new Error(`TYPESCRIPT_EMITTED_CALL_UNSUPPORTED:${name || "unknown"}`);
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = emittedOperator(node.operatorToken.kind);
    const left = emittedExpressionType(node.left, environment);
    const right = emittedExpressionType(node.right, environment);
    if (ARITHMETIC_OPERATORS.has(liftedOperator)) {
      if (liftedOperator === "+" && left === "string" && right === "string") return "string";
      if (!NUMERIC_TYPES.has(left) || !NUMERIC_TYPES.has(right)) {
        throw new Error(`TYPESCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return left === "number" || right === "number" ? "number" : "integer";
    }
    if (ORDERING_OPERATORS.has(liftedOperator)) {
      if (!NUMERIC_TYPES.has(left) || !NUMERIC_TYPES.has(right)) {
        throw new Error(`TYPESCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return "boolean";
    }
    if (EQUALITY_OPERATORS.has(liftedOperator)) {
      if (left !== right && !(NUMERIC_TYPES.has(left) && NUMERIC_TYPES.has(right))) {
        throw new Error(`TYPESCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return "boolean";
    }
    if (LOGICAL_OPERATORS.has(liftedOperator)) {
      if (left !== "boolean" || right !== "boolean") {
        throw new Error(`TYPESCRIPT_EMITTED_OPERAND_TYPE_MISMATCH:${liftedOperator}:${left}:${right}`);
      }
      return "boolean";
    }
  }
  throw new Error(`TYPESCRIPT_EMITTED_EXPRESSION_TYPE_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
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
  if (ts.isIdentifier(node) || ts.isNumericLiteral(node) || ts.isStringLiteral(node)) {
    if (ts.isNumericLiteral(node)) numericLiteralDetails(node);
    return;
  }
  if (negativeNumericLiteralDetails(node) !== null) return;
  if (node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) return;
  if (ts.isCallExpression(node)) {
    const name = calleeName(node.expression);
    if (!exactCall(node, name, 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
    }
    if (name === "_elmosRequireSafeInteger" || name === "_elmosRequireFiniteNumber") {
      const guardType = name === "_elmosRequireSafeInteger" ? "integer" : "number";
      const argumentType = emittedExpressionType(node.arguments[0], environment);
      if (
        (guardType === "integer" && argumentType !== "integer")
        || (guardType === "number" && !NUMERIC_TYPES.has(argumentType))
      ) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      validateEmittedArithmeticExpression(node.arguments[0], environment, guardType);
      return;
    }
    if (name === "_elmosRequireNonZero") {
      if (!allowNonZero) throw new Error("TYPESCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
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
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      validateEmittedArithmeticExpression(argument, environment, "integer");
      return;
    }
    throw new Error(`TYPESCRIPT_EMITTED_CALL_UNSUPPORTED:${name || "unknown"}`);
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = emittedOperator(node.operatorToken.kind);
    const resultType = emittedExpressionType(node, environment);
    if (
      ARITHMETIC_OPERATORS.has(liftedOperator)
      && NUMERIC_TYPES.has(resultType)
      && requiredGuard !== resultType
    ) {
      throw new Error(`TYPESCRIPT_EMITTED_ARITHMETIC_GUARD_MISSING:${liftedOperator}:${resultType}`);
    }
    const requiresNonZero = liftedOperator === "/" || liftedOperator === "%";
    if (requiresNonZero && !exactCall(node.right, "_elmosRequireNonZero", 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:${liftedOperator}`);
    }
    validateEmittedArithmeticExpression(node.left, environment);
    validateEmittedArithmeticExpression(node.right, environment, null, requiresNonZero);
    return;
  }
  throw new Error(`TYPESCRIPT_EMITTED_EXPRESSION_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
}

function validateEmittedArithmeticStatements(nodes, environment, numericReturnContract, liftedReturn) {
  for (const node of nodes) {
    if (ts.isReturnStatement(node) && node.expression) {
      const expression = numericReturnContract === null
        ? node.expression
        : node.expression.arguments[0];
      validateEmittedArithmeticExpression(expression, environment);
      if (liftedReturn !== undefined) {
        const actualType = emittedExpressionType(node.expression, environment);
        if (actualType !== liftedReturn) {
          throw new Error(`TYPESCRIPT_EMITTED_RETURN_TYPE_MISMATCH:${liftedReturn}:${actualType}`);
        }
      }
      continue;
    }
    if (ts.isIfStatement(node)) {
      validateEmittedArithmeticExpression(node.expression, environment);
      validateEmittedArithmeticStatements(
        statementNodes(node.thenStatement),
        new Map(environment),
        numericReturnContract,
        liftedReturn,
      );
      if (node.elseStatement) {
        validateEmittedArithmeticStatements(
          statementNodes(node.elseStatement),
          new Map(environment),
          numericReturnContract,
          liftedReturn,
        );
      }
      continue;
    }
    if (ts.isVariableStatement(node)) {
      const declList = node.declarationList;
      if (!(declList.flags & ts.NodeFlags.Const)) {
        throw new Error("TYPESCRIPT_MUTABLE_VARIABLE_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (declList.declarations.length !== 1) {
        throw new Error("TYPESCRIPT_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET");
      }
      const decl = declList.declarations[0];
      if (!ts.isIdentifier(decl.name)) {
        throw new Error("TYPESCRIPT_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (!decl.type) {
        throw new Error("TYPESCRIPT_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (!decl.initializer) {
        throw new Error("TYPESCRIPT_ANNOTATED_DECLARATION_WITHOUT_VALUE");
      }
      const canonicalType = typeName(decl.type);
      validateEmittedArithmeticExpression(decl.initializer, environment);
      environment.set(decl.name.text, canonicalType);
      continue;
    }
    throw new Error(`TYPESCRIPT_EMITTED_STATEMENT_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
  }
}

function numericReturnContract(node) {
  if (exactCall(node, "_elmosRequireSafeInteger", 1)) return "integer";
  if (exactCall(node, "_elmosRequireFiniteNumber", 1)) return "number";
  return null;
}

function statementNodes(node) {
  return ts.isBlock(node) ? [...node.statements] : [node];
}

function sourceStatements(nodes) {
  return nodes.map((node) => {
    if (ts.isReturnStatement(node) && node.expression) {
      return { kind: "return", expression: sourceExpression(node.expression) };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: sourceExpression(node.expression),
        then: sourceStatements(statementNodes(node.thenStatement)),
        else: node.elseStatement ? sourceStatements(statementNodes(node.elseStatement)) : [],
      };
    }
    if (ts.isVariableStatement(node)) {
      const declList = node.declarationList;
      if (!(declList.flags & ts.NodeFlags.Const)) {
        throw new Error("TYPESCRIPT_MUTABLE_VARIABLE_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (declList.declarations.length !== 1) {
        throw new Error("TYPESCRIPT_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET");
      }
      const decl = declList.declarations[0];
      if (!ts.isIdentifier(decl.name)) {
        throw new Error("TYPESCRIPT_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (!decl.type) {
        throw new Error("TYPESCRIPT_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (!decl.initializer) {
        throw new Error("TYPESCRIPT_ANNOTATED_DECLARATION_WITHOUT_VALUE");
      }
      const canonicalType = typeName(decl.type);
      return {
        kind: "let",
        name: decl.name.text,
        type: canonicalType,
        expression: sourceExpression(decl.initializer),
      };
    }
    throw new Error(`TYPESCRIPT_UNSUPPORTED_STATEMENT:${ts.SyntaxKind[node.kind]}`);
  });
}

function emittedStatements(nodes) {
  return nodes.map((node) => {
    if (ts.isReturnStatement(node) && node.expression) {
      return { kind: "return", expression: emittedExpression(node.expression) };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: emittedExpression(node.expression),
        then: emittedStatements(statementNodes(node.thenStatement)),
        else: node.elseStatement ? emittedStatements(statementNodes(node.elseStatement)) : [],
      };
    }
    if (ts.isVariableStatement(node)) {
      const declList = node.declarationList;
      if (!(declList.flags & ts.NodeFlags.Const)) {
        throw new Error("TYPESCRIPT_MUTABLE_VARIABLE_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (declList.declarations.length !== 1) {
        throw new Error("TYPESCRIPT_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET");
      }
      const decl = declList.declarations[0];
      if (!ts.isIdentifier(decl.name)) {
        throw new Error("TYPESCRIPT_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (!decl.type) {
        throw new Error("TYPESCRIPT_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET");
      }
      if (!decl.initializer) {
        throw new Error("TYPESCRIPT_ANNOTATED_DECLARATION_WITHOUT_VALUE");
      }
      const canonicalType = typeName(decl.type);
      return {
        kind: "let",
        name: decl.name.text,
        type: canonicalType,
        expression: emittedExpression(decl.initializer),
      };
    }
    throw new Error(`TYPESCRIPT_UNSUPPORTED_STATEMENT:${ts.SyntaxKind[node.kind]}`);
  });
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

function splitParameterGuards(body, parameters) {
  const parameterIndex = new Map(parameters.map((item, index) => [item.name, index]));
  const guarded = new Set();
  let lastIndex = -1;
  let offset = 0;

  const guardAssignmentName = (node) => {
    if (!ts.isExpressionStatement(node)) return null;
    const candidate = node.expression;
    if (exactCall(candidate, "_elmosRequireSafeInteger", 1)) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_ASSIGNMENT_REQUIRED");
    }
    if (
      !ts.isBinaryExpression(candidate)
      || candidate.operatorToken.kind !== ts.SyntaxKind.EqualsToken
    ) {
      return null;
    }
    const rightIsGuard = ts.isCallExpression(candidate.right)
      && calleeName(candidate.right.expression) === "_elmosRequireSafeInteger";
    if (!rightIsGuard) return null;
    if (
      !ts.isIdentifier(candidate.left)
      || !exactCall(candidate.right, "_elmosRequireSafeInteger", 1)
      || !ts.isIdentifier(candidate.right.arguments[0])
      || candidate.right.arguments[0].text !== candidate.left.text
    ) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_ASSIGNMENT_INVALID");
    }
    return candidate.left.text;
  };

  while (offset < body.length) {
    const node = body[offset];
    const name = guardAssignmentName(node);
    if (name === null) break;
    if (!parameterIndex.has(name)) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_INVALID");
    }
    const index = parameterIndex.get(name);
    if (guarded.has(name) || index <= lastIndex) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_ORDER_INVALID");
    }
    guarded.add(name);
    lastIndex = index;
    offset += 1;
  }
  for (const node of body.slice(offset)) {
    const name = guardAssignmentName(node);
    if (name !== null) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_UNEXPECTED");
    }
  }
  return { guarded, body: body.slice(offset) };
}

function diagnostics() {
  const parseDiagnostics = sourceFile.parseDiagnostics ?? [];
  return parseDiagnostics.map((item) => {
    const line = sourceFile.getLineAndCharacterOfPosition(item.start ?? 0).line + 1;
    return `TS${item.code}:${line}`;
  });
}

function analyzeNamedFunction(functionName) {
  const analysisDiagnostics = diagnostics();
  if (emittedTarget) validateEmittedHelperDeclarations();
  const functions = sourceFile.statements
    .filter(ts.isFunctionDeclaration)
    .filter((item) => item.name?.text === functionName)
    .map((item) => {
      if (!item.name || !item.body) throw new Error("TYPESCRIPT_FUNCTION_BODY_REQUIRED");
      const parameters = item.parameters.map((parameter) => {
        if (!ts.isIdentifier(parameter.name)) {
          throw new Error("TYPESCRIPT_DESTRUCTURED_PARAMETER_UNSUPPORTED");
        }
        return { name: parameter.name.text, declaredType: typeName(parameter.type) };
      });
      if (!emittedTarget) {
        return {
          name: item.name.text,
          parameters: parameters.map((parameter) => ({
            name: parameter.name,
            type: parameter.declaredType,
          })),
          return_type: typeName(item.type),
          body: sourceStatements([...item.body.statements]),
        };
      }
      const split = splitParameterGuards([...item.body.statements], parameters);
      const liftedParameters = parameters.map((parameter) => ({
        name: parameter.name,
        type: parameter.declaredType === "number" && split.guarded.has(parameter.name)
          ? "integer"
          : parameter.declaredType,
      }));
      const environment = new Map(liftedParameters.map((parameter) => [parameter.name, parameter.type]));
      const declaredReturn = typeName(item.type);
      const returns = returnExpressions(split.body);
      if (returns.length === 0) throw new Error("TYPESCRIPT_RETURN_EXPRESSION_REQUIRED");
      const returnContracts = returns.map(numericReturnContract);
      const numericContract = returnContracts[0];
      if (declaredReturn === "number" && numericContract === null) {
        throw new Error("TYPESCRIPT_EMITTED_RETURN_GUARD_MISSING");
      }
      if (returnContracts.some((value) => value !== numericContract)) {
        throw new Error("TYPESCRIPT_EMITTED_RETURN_GUARD_INCONSISTENT");
      }
      if (declaredReturn !== "number" && numericContract !== null) {
        throw new Error("TYPESCRIPT_EMITTED_RETURN_GUARD_TYPE_MISMATCH");
      }
      const liftedReturn = numericContract ?? declaredReturn;
      validateEmittedArithmeticStatements(split.body, environment, numericContract, liftedReturn);
      return {
        name: item.name.text,
        parameters: liftedParameters,
        return_type: liftedReturn,
        body: emittedStatements(split.body),
      };
    });
  if (functions.length === 0) analysisDiagnostics.push(`FUNCTION_NOT_FOUND:${functionName}`);
  return {
    schema_version: "1.0.0",
    source_language: "typescript",
    source_file: sourceName,
    analyzer: emittedTarget
      ? "TypeScript Compiler API emitted-target"
      : "TypeScript Compiler API",
    analyzer_version: ts.version,
    functions,
    diagnostics: analysisDiagnostics,
  };
}

function byteOffset(characterOffset) {
  return Buffer.byteLength(source.slice(0, characterOffset), "utf8");
}

function inventoryModule() {
  const inventoryDiagnostics = diagnostics();
  const subjects = [];
  const helperDeclarationCounts = new Map();
  for (const statement of sourceFile.statements) {
    const name = ts.isFunctionDeclaration(statement) ? statement.name?.text ?? "" : "";
    if (name.startsWith("_elmos")) {
      helperDeclarationCounts.set(name, (helperDeclarationCounts.get(name) ?? 0) + 1);
    }
  }
  const span = (node) => ({
    file: sourceName,
    start_byte: byteOffset(node.getStart(sourceFile)),
    end_byte: byteOffset(node.end),
  });
  const add = (node, name, qualifiedName, declarationKind, analyzable, signature) => {
    subjects.push({
      name,
      qualified_name: qualifiedName,
      declaration_kind: declarationKind,
      analyzable,
      source_span: span(node),
      signature,
    });
  };

  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement)) {
      const name = statement.name?.text ?? `<anonymous-function@${statement.pos}>`;
      const helperSignature = name.startsWith("_elmos")
        ? canonicalEmittedHelperSignature(statement, helperDeclarationCounts)
        : null;
      const permittedModifiers = statement.modifiers?.every(
        (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword,
      ) ?? true;
      const supportedParameters = statement.parameters.every(
        (parameter) => ts.isIdentifier(parameter.name)
          && parameter.dotDotDotToken === undefined
          && parameter.questionToken === undefined
          && parameter.initializer === undefined,
      );
      add(
        statement,
        name,
        name,
        "FunctionDeclaration",
        name.startsWith("_elmos")
          ? helperSignature !== null
          : Boolean(
            statement.name
            && statement.body
            && statement.asteriskToken === undefined
            && statement.typeParameters === undefined
            && permittedModifiers
            && supportedParameters,
          ),
        name.startsWith("_elmos")
          ? helperSignature ?? {}
          : {
            parameters: statement.parameters.map((parameter) => ({
              name: ts.isIdentifier(parameter.name) ? parameter.name.text : parameter.name.getText(sourceFile),
              source_type: parameter.type?.getText(sourceFile) ?? "",
            })),
            source_return_type: statement.type?.getText(sourceFile) ?? "",
          },
      );
      continue;
    }
    if (ts.isClassDeclaration(statement)) {
      const className = statement.name?.text ?? `<anonymous-class@${statement.pos}>`;
      add(statement, className, className, "ClassDeclaration", false, {});
      for (const member of statement.members) {
        const memberName = "name" in member && member.name
          ? member.name.getText(sourceFile)
          : `<${ts.SyntaxKind[member.kind]}@${member.pos}>`;
        add(
          member,
          memberName,
          `${className}.${memberName}`,
          ts.SyntaxKind[member.kind],
          false,
          {},
        );
      }
      continue;
    }
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        const name = declaration.name.getText(sourceFile);
        const callable = declaration.initializer !== undefined
          && (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer));
        add(
          declaration,
          name,
          name,
          callable ? "FunctionValueDeclaration" : "VariableDeclaration",
          false,
          { source_type: declaration.type?.getText(sourceFile) ?? "" },
        );
      }
      continue;
    }
    if (ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement)) {
      const moduleName = statement.moduleSpecifier && ts.isStringLiteral(statement.moduleSpecifier)
        ? statement.moduleSpecifier.text
        : `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
      add(statement, moduleName, moduleName, ts.SyntaxKind[statement.kind], false, {});
      continue;
    }
    if (ts.isEmptyStatement(statement)) continue;
    const name = `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
    add(statement, name, name, ts.SyntaxKind[statement.kind], false, {});
  }

  return {
    schema_version: "1.0.0",
    kind: "elmos.typed-pure-module-inventory",
    profile: "typed-pure-module-v1",
    source_language: "typescript",
    source_file: sourceName,
    analyzer: "TypeScript Compiler API",
    analyzer_version: ts.version,
    enumeration_status: inventoryDiagnostics.length === 0 ? "PASSED" : "FAILED",
    subjects,
    diagnostics: inventoryDiagnostics,
  };
}

try {
  const result = selector === "--inventory"
    ? inventoryModule()
    : analyzeNamedFunction(selector);
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : "TYPESCRIPT_ANALYZER_FAILED";
  const safe = /^[A-Z][A-Z0-9_]*(?::[A-Za-z0-9_.:<>=/+,\-]+)*$/.test(message)
    ? message
    : "TYPESCRIPT_ANALYZER_FAILED";
  process.stderr.write(`${safe}\n`);
  process.exitCode = 2;
}

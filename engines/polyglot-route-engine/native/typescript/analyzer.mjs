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

function byteOffset(characterOffset) {
  return Buffer.byteLength(source.slice(0, characterOffset), "utf8");
}

function span(node) {
  return {
    file: sourceName,
    start_byte: byteOffset(node.getStart(sourceFile)),
    end_byte: byteOffset(node.end),
  };
}

function typeName(node, records = new Map()) {
  if (!node) throw new Error("TYPESCRIPT_EXPLICIT_TYPE_REQUIRED");
  const value = node.getText(sourceFile).trim();
  if (value === "number") return "number";
  if (value === "integer") return "integer";
  if (value === "boolean") return "boolean";
  if (value === "string") return "string";
  if (records.has(value)) return value;
  throw new Error(`TYPESCRIPT_UNSUPPORTED_TYPE:${value}`);
}

function parseRecords(sourceFile) {
  const records = new Map();
  const rawList = [];

  for (const statement of sourceFile.statements) {
    if (ts.isInterfaceDeclaration(statement)) {
      const name = statement.name.text;
      if (records.has(name)) {
        throw new Error(`TYPESCRIPT_DUPLICATE_RECORD:${name}`);
      }
      records.set(name, { name, fields: [] });
      rawList.push({ name, members: statement.members });
    } else if (ts.isTypeAliasDeclaration(statement)) {
      if (ts.isTypeLiteralNode(statement.type)) {
        const name = statement.name.text;
        if (records.has(name)) {
          throw new Error(`TYPESCRIPT_DUPLICATE_RECORD:${name}`);
        }
        records.set(name, { name, fields: [] });
        rawList.push({ name, members: statement.type.members });
      }
    }
  }

  const recordDefs = [];
  for (const item of rawList) {
    const fields = [];
    const seenNames = new Set();
    for (const member of item.members) {
      if (!ts.isPropertySignature(member) || !member.name) {
        throw new Error(`TYPESCRIPT_UNSUPPORTED_RECORD_MEMBER:${item.name}`);
      }
      const fieldName = member.name.getText(sourceFile).trim();
      if (seenNames.has(fieldName)) {
        throw new Error(`TYPESCRIPT_DUPLICATE_RECORD_FIELD:${item.name}.${fieldName}`);
      }
      seenNames.add(fieldName);
      const fieldType = typeName(member.type, records);
      fields.push({ name: fieldName, type: fieldType });
    }
    const def = { name: item.name, fields };
    records.set(item.name, def);
    recordDefs.push(def);
  }

  return { recordDefs, records };
}

function findRecordForKeys(keys, records, expectedType = null) {
  if (expectedType && records.has(expectedType)) {
    const rec = records.get(expectedType);
    const recFieldNames = new Set(rec.fields.map((f) => f.name));
    if (keys.length === recFieldNames.size && keys.every((k) => recFieldNames.has(k))) {
      return rec.name;
    }
  }
  const matches = [];
  for (const [name, rec] of records.entries()) {
    const recFieldNames = new Set(rec.fields.map((f) => f.name));
    if (keys.length === recFieldNames.size && keys.every((k) => recFieldNames.has(k))) {
      matches.push(name);
    }
  }
  if (matches.length === 1) return matches[0];
  if (matches.length > 1) {
    if (expectedType && matches.includes(expectedType)) return expectedType;
    throw new Error(`TYPESCRIPT_AMBIGUOUS_RECORD_TYPE:${matches.join(",")}`);
  }
  throw new Error(`TYPESCRIPT_UNKNOWN_RECORD_SHAPE:${keys.join(",")}`);
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

function sourceExpression(node, records = new Map(), expectedType = null, functionNames = new Set()) {
  if (ts.isParenthesizedExpression(node)) return sourceExpression(node.expression, records, expectedType, functionNames);
  if (ts.isAsExpression(node) || ts.isTypeAssertionExpression(node)) {
    const targetType = typeName(node.type, records);
    return sourceExpression(node.expression, records, targetType, functionNames);
  }
  if (ts.isPropertyAccessExpression(node)) {
    return {
      kind: "member_access",
      target: sourceExpression(node.expression, records, null, functionNames),
      member: node.name.text,
      source_span: span(node),
    };
  }
  if (ts.isObjectLiteralExpression(node)) {
    const keys = [];
    for (const prop of node.properties) {
      if (!ts.isPropertyAssignment(prop) || !ts.isIdentifier(prop.name)) {
        throw new Error("TYPESCRIPT_UNSUPPORTED_OBJECT_PROPERTY");
      }
      keys.push(prop.name.text);
    }
    const recName = findRecordForKeys(keys, records, expectedType);
    const rec = records.get(recName);
    const argsMap = {};
    for (const prop of node.properties) {
      const k = prop.name.text;
      const field = rec.fields.find((f) => f.name === k);
      argsMap[k] = sourceExpression(prop.initializer, records, field?.type, functionNames);
    }
    return {
      kind: "record_construct",
      record_name: recName,
      arguments: argsMap,
      source_span: span(node),
    };
  }
  if (ts.isIdentifier(node)) return { kind: "name", value: node.text, source_span: span(node) };
  if (ts.isNumericLiteral(node)) {
    return { kind: "literal", value: numericLiteralDetails(node).value, source_span: span(node) };
  }
  const negativeLiteral = negativeNumericLiteralDetails(node);
  if (negativeLiteral !== null) return { kind: "literal", value: negativeLiteral.value, source_span: span(node) };
  if (ts.isStringLiteral(node)) return { kind: "literal", value: node.text, source_span: span(node) };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { kind: "literal", value: true, source_span: span(node) };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { kind: "literal", value: false, source_span: span(node) };
  if (ts.isBinaryExpression(node)) {
    return {
      kind: "binary",
      operator: sourceOperator(node.operatorToken.kind),
      left: sourceExpression(node.left, records, null, functionNames),
      right: sourceExpression(node.right, records, null, functionNames),
      source_span: span(node),
    };
  }
  if (ts.isCallExpression(node)) {
    const name = calleeName(node.expression);
    if (functionNames && functionNames.has(name)) {
      return {
        kind: "call",
        function_name: name,
        arguments: node.arguments.map((arg) => sourceExpression(arg, records, null, functionNames)),
        source_span: span(node),
      };
    }
    throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
  }
  throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
}

function emittedExpression(node, { allowNonZero = false, allowMathTrunc = false, expectedType = null, records = new Map(), functionNames = new Set() } = {}) {
  if (ts.isParenthesizedExpression(node)) {
    return emittedExpression(node.expression, { allowNonZero, allowMathTrunc, expectedType, records, functionNames });
  }
  if (ts.isAsExpression(node) || ts.isTypeAssertionExpression(node)) {
    const targetType = typeName(node.type, records);
    return emittedExpression(node.expression, { allowNonZero, allowMathTrunc, expectedType: targetType, records, functionNames });
  }
  if (ts.isPropertyAccessExpression(node)) {
    return {
      kind: "member_access",
      target: emittedExpression(node.expression, { records, functionNames }),
      member: node.name.text,
      source_span: span(node),
    };
  }
  if (ts.isObjectLiteralExpression(node)) {
    const keys = [];
    for (const prop of node.properties) {
      if (!ts.isPropertyAssignment(prop) || !ts.isIdentifier(prop.name)) {
        throw new Error("TYPESCRIPT_UNSUPPORTED_OBJECT_PROPERTY");
      }
      keys.push(prop.name.text);
    }
    const recName = findRecordForKeys(keys, records, expectedType);
    const rec = records.get(recName);
    const argsMap = {};
    for (const prop of node.properties) {
      const k = prop.name.text;
      const field = rec.fields.find((f) => f.name === k);
      argsMap[k] = emittedExpression(prop.initializer, {
        expectedType: field?.type,
        records,
        functionNames,
      });
    }
    return {
      kind: "record_construct",
      record_name: recName,
      arguments: argsMap,
      source_span: span(node),
    };
  }
  if (ts.isIdentifier(node)) return { kind: "name", value: node.text, source_span: span(node) };
  if (ts.isNumericLiteral(node)) {
    return { kind: "literal", value: numericLiteralDetails(node).value, source_span: span(node) };
  }
  const negativeLiteral = negativeNumericLiteralDetails(node);
  if (negativeLiteral !== null) return { kind: "literal", value: negativeLiteral.value, source_span: span(node) };
  if (ts.isStringLiteral(node)) return { kind: "literal", value: node.text, source_span: span(node) };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { kind: "literal", value: true, source_span: span(node) };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { kind: "literal", value: false, source_span: span(node) };
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = emittedOperator(node.operatorToken.kind);
    const guarded = liftedOperator === "/" || liftedOperator === "%";
    if (guarded && !exactCall(node.right, "_elmosRequireNonZero", 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:${liftedOperator}`);
    }
    return {
      kind: "binary",
      operator: liftedOperator,
      left: emittedExpression(node.left, { records, functionNames }),
      right: emittedExpression(node.right, { allowNonZero: guarded, records, functionNames }),
      source_span: span(node),
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
        return emittedExpression(argument, { allowMathTrunc: true, records, functionNames });
      }
      return emittedExpression(argument, { records, functionNames });
    }
    if (name === "_elmosRequireFiniteNumber") {
      if (!exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_FINITE_NUMBER_SHAPE_INVALID");
      }
      return emittedExpression(node.arguments[0], { records, functionNames });
    }
    if (name === "_elmosRequireNonZero") {
      if (!allowNonZero || !exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
      }
      return emittedExpression(node.arguments[0], { records, functionNames });
    }
    if (name === "Math.trunc") {
      if (!allowMathTrunc || !exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_INVALID");
      }
      const argument = node.arguments[0];
      if (!ts.isBinaryExpression(argument) || argument.operatorToken.kind !== ts.SyntaxKind.SlashToken) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      return emittedExpression(argument, { records, functionNames });
    }
    if (functionNames && functionNames.has(name)) {
      return {
        kind: "call",
        function_name: name,
        arguments: node.arguments.map((arg) =>
          emittedExpression(arg, { records, functionNames })
        ),
        source_span: span(node),
      };
    }
    throw new Error(`TYPESCRIPT_EMITTED_HELPER_UNRECOGNIZED:${name || "<complex>"}`);
  }
  throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
}

function emittedExpressionType(node, environment, records = new Map(), expectedType = null, functionsEnv = new Map()) {
  if (ts.isParenthesizedExpression(node)) {
    return emittedExpressionType(node.expression, environment, records, expectedType, functionsEnv);
  }
  if (ts.isAsExpression(node) || ts.isTypeAssertionExpression(node)) {
    return typeName(node.type, records);
  }
  if (ts.isPropertyAccessExpression(node)) {
    const targetType = emittedExpressionType(node.expression, environment, records, null, functionsEnv);
    if (!records.has(targetType)) {
      throw new Error(`TYPESCRIPT_MEMBER_ACCESS_ON_NON_RECORD:${targetType}`);
    }
    const rec = records.get(targetType);
    const field = rec.fields.find((f) => f.name === node.name.text);
    if (!field) {
      throw new Error(`TYPESCRIPT_UNKNOWN_RECORD_MEMBER:${targetType}.${node.name.text}`);
    }
    return field.type;
  }
  if (ts.isObjectLiteralExpression(node)) {
    const keys = [];
    for (const prop of node.properties) {
      if (!ts.isPropertyAssignment(prop) || !ts.isIdentifier(prop.name)) {
        throw new Error("TYPESCRIPT_UNSUPPORTED_OBJECT_PROPERTY");
      }
      keys.push(prop.name.text);
    }
    return findRecordForKeys(keys, records, expectedType);
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
    if (name === "_elmosRequireSafeInteger") {
      if (!exactCall(node, name, 1)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name}`);
      }
      const argumentType = emittedExpressionType(node.arguments[0], environment, records, null, functionsEnv);
      if (argumentType !== "integer") {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      return "integer";
    }
    if (name === "_elmosRequireFiniteNumber") {
      if (!exactCall(node, name, 1)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name}`);
      }
      const argumentType = emittedExpressionType(node.arguments[0], environment, records, null, functionsEnv);
      if (!NUMERIC_TYPES.has(argumentType)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      return "number";
    }
    if (name === "Math.trunc") return "integer";
    if (name === "_elmosRequireNonZero") {
      if (!exactCall(node, name, 1)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name}`);
      }
      const argumentType = emittedExpressionType(node.arguments[0], environment, records, null, functionsEnv);
      if (!NUMERIC_TYPES.has(argumentType)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      return argumentType;
    }
    if (functionsEnv && functionsEnv.has(name)) {
      return functionsEnv.get(name).return_type;
    }
    if (!exactCall(node, name, 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
    }
    throw new Error(`TYPESCRIPT_EMITTED_CALL_UNSUPPORTED:${name || "unknown"}`);
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = emittedOperator(node.operatorToken.kind);
    const left = emittedExpressionType(node.left, environment, records, null, functionsEnv);
    const right = emittedExpressionType(node.right, environment, records, null, functionsEnv);
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
  records = new Map(),
  functionsEnv = new Map(),
) {
  if (ts.isParenthesizedExpression(node)) {
    validateEmittedArithmeticExpression(node.expression, environment, requiredGuard, allowNonZero, records, functionsEnv);
    return;
  }
  if (ts.isAsExpression(node) || ts.isTypeAssertionExpression(node)) {
    validateEmittedArithmeticExpression(node.expression, environment, requiredGuard, allowNonZero, records, functionsEnv);
    return;
  }
  if (ts.isPropertyAccessExpression(node)) {
    const targetType = emittedExpressionType(node.expression, environment, records, null, functionsEnv);
    if (!records.has(targetType)) {
      throw new Error(`TYPESCRIPT_MEMBER_ACCESS_ON_NON_RECORD:${targetType}`);
    }
    const rec = records.get(targetType);
    const field = rec.fields.find((f) => f.name === node.name.text);
    if (!field) {
      throw new Error(`TYPESCRIPT_UNKNOWN_RECORD_MEMBER:${targetType}.${node.name.text}`);
    }
    validateEmittedArithmeticExpression(node.expression, environment, null, false, records, functionsEnv);
    return;
  }
  if (ts.isObjectLiteralExpression(node)) {
    const keys = [];
    for (const prop of node.properties) {
      if (!ts.isPropertyAssignment(prop) || !ts.isIdentifier(prop.name)) {
        throw new Error("TYPESCRIPT_UNSUPPORTED_OBJECT_PROPERTY");
      }
      keys.push(prop.name.text);
    }
    const recName = findRecordForKeys(keys, records);
    const rec = records.get(recName);
    for (const prop of node.properties) {
      const k = prop.name.text;
      const field = rec.fields.find((f) => f.name === k);
      validateEmittedArithmeticExpression(prop.initializer, environment, null, false, records, functionsEnv);
    }
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
    if (name === "_elmosRequireSafeInteger" || name === "_elmosRequireFiniteNumber") {
      if (!exactCall(node, name, 1)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
      }
      const guardType = name === "_elmosRequireSafeInteger" ? "integer" : "number";
      const argumentType = emittedExpressionType(node.arguments[0], environment, records, null, functionsEnv);
      if (
        (guardType === "integer" && argumentType !== "integer")
        || (guardType === "number" && !NUMERIC_TYPES.has(argumentType))
      ) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:${name}:${argumentType}`);
      }
      validateEmittedArithmeticExpression(node.arguments[0], environment, guardType, false, records, functionsEnv);
      return;
    }
    if (name === "_elmosRequireNonZero") {
      if (!exactCall(node, name, 1)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
      }
      if (!allowNonZero) throw new Error("TYPESCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
      validateEmittedArithmeticExpression(node.arguments[0], environment, null, false, records, functionsEnv);
      return;
    }
    if (name === "Math.trunc") {
      if (!exactCall(node, name, 1)) {
        throw new Error(`TYPESCRIPT_EMITTED_GUARD_SHAPE_INVALID:${name || "unknown"}`);
      }
      const argument = node.arguments[0];
      if (
        requiredGuard !== "integer"
        || !ts.isBinaryExpression(argument)
        || argument.operatorToken.kind !== ts.SyntaxKind.SlashToken
      ) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      validateEmittedArithmeticExpression(argument, environment, "integer", false, records, functionsEnv);
      return;
    }
    if (functionsEnv && functionsEnv.has(name)) {
      const callee = functionsEnv.get(name);
      if (node.arguments.length !== callee.parameters.length) {
        throw new Error(`TYPESCRIPT_CALL_ARITY_MISMATCH:${name}:${callee.parameters.length}:${node.arguments.length}`);
      }
      for (let i = 0; i < node.arguments.length; i++) {
        validateEmittedArithmeticExpression(node.arguments[i], environment, null, false, records, functionsEnv);
      }
      return;
    }
    throw new Error(`TYPESCRIPT_EMITTED_CALL_UNSUPPORTED:${name || "unknown"}`);
  }
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = emittedOperator(node.operatorToken.kind);
    const resultType = emittedExpressionType(node, environment, records, null, functionsEnv);
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
    validateEmittedArithmeticExpression(node.left, environment, null, false, records, functionsEnv);
    validateEmittedArithmeticExpression(node.right, environment, null, requiresNonZero, records, functionsEnv);
    return;
  }
  throw new Error(`TYPESCRIPT_EMITTED_EXPRESSION_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
}

function validateEmittedArithmeticStatements(nodes, environment, numericReturnContract, liftedReturn, records = new Map(), functionsEnv = new Map()) {
  for (const node of nodes) {
    if (ts.isReturnStatement(node) && node.expression) {
      const expression = numericReturnContract === null
        ? node.expression
        : node.expression.arguments[0];
      validateEmittedArithmeticExpression(expression, environment, null, false, records, functionsEnv);
      if (liftedReturn !== undefined) {
        const actualType = emittedExpressionType(node.expression, environment, records, liftedReturn, functionsEnv);
        if (actualType !== liftedReturn) {
          throw new Error(`TYPESCRIPT_EMITTED_RETURN_TYPE_MISMATCH:${liftedReturn}:${actualType}`);
        }
      }
      continue;
    }
    if (ts.isIfStatement(node)) {
      validateEmittedArithmeticExpression(node.expression, environment, null, false, records, functionsEnv);
      validateEmittedArithmeticStatements(
        statementNodes(node.thenStatement),
        new Map(environment),
        numericReturnContract,
        liftedReturn,
        records,
        functionsEnv,
      );
      if (node.elseStatement) {
        validateEmittedArithmeticStatements(
          statementNodes(node.elseStatement),
          new Map(environment),
          numericReturnContract,
          liftedReturn,
          records,
          functionsEnv,
        );
      }
      continue;
    }
    if (ts.isBreakStatement(node) || ts.isContinueStatement(node)) {
      continue;
    }
    if (ts.isWhileStatement(node)) {
      validateEmittedArithmeticExpression(node.expression, environment, null, false, records, functionsEnv);
      validateEmittedArithmeticStatements(
        statementNodes(node.statement),
        new Map(environment),
        numericReturnContract,
        liftedReturn,
        records,
        functionsEnv,
      );
      continue;
    }
    if (ts.isForStatement(node)) {
      const loopEnv = new Map(environment);
      if (node.initializer && ts.isVariableDeclarationList(node.initializer)) {
        const decl = node.initializer.declarations[0];
        if (decl && ts.isIdentifier(decl.name)) {
          if (decl.initializer) {
            validateEmittedArithmeticExpression(decl.initializer, environment, null, false, records, functionsEnv);
          }
          loopEnv.set(decl.name.text, "integer");
        }
      }
      if (node.condition) {
        validateEmittedArithmeticExpression(node.condition, loopEnv, null, false, records, functionsEnv);
      }
      if (node.incrementor && ts.isBinaryExpression(node.incrementor)) {
        validateEmittedArithmeticExpression(node.incrementor.right, loopEnv, null, false, records, functionsEnv);
      }
      validateEmittedArithmeticStatements(
        statementNodes(node.statement),
        loopEnv,
        numericReturnContract,
        liftedReturn,
        records,
        functionsEnv,
      );
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
      let canonicalType = typeName(decl.type, records);
      validateEmittedArithmeticExpression(decl.initializer, environment, null, false, records, functionsEnv);
      if (canonicalType === "number" && emittedExpressionType(decl.initializer, environment, records, null, functionsEnv) === "integer") {
        canonicalType = "integer";
      }
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

function parseForStatement(node, parseExpr, parseStmts, records = new Map()) {
  if (!node.initializer || !ts.isVariableDeclarationList(node.initializer)) {
    throw new Error("TYPESCRIPT_FOR_INITIALIZER_OUTSIDE_CERTIFIED_SUBSET");
  }
  const initList = node.initializer;
  if ((initList.flags & ts.NodeFlags.Const) || !(initList.flags & ts.NodeFlags.Let)) {
    throw new Error("TYPESCRIPT_FOR_VARIABLE_MUST_BE_LET");
  }
  if (initList.declarations.length !== 1) {
    throw new Error("TYPESCRIPT_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET");
  }
  const decl = initList.declarations[0];
  if (!ts.isIdentifier(decl.name)) {
    throw new Error("TYPESCRIPT_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
  }
  const varName = decl.name.text;
  if (!decl.type) {
    throw new Error("TYPESCRIPT_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET");
  }
  const declaredType = typeName(decl.type, records);
  if (declaredType !== "number" && declaredType !== "integer") {
    throw new Error(`TYPESCRIPT_FOR_VARIABLE_TYPE_INVALID:${declaredType}`);
  }
  if (!decl.initializer) {
    throw new Error("TYPESCRIPT_ANNOTATED_DECLARATION_WITHOUT_VALUE");
  }
  const startExpr = parseExpr(decl.initializer);

  if (!node.condition || !ts.isBinaryExpression(node.condition)) {
    throw new Error("TYPESCRIPT_FOR_CONDITION_NON_MONOTONIC");
  }
  if (node.condition.operatorToken.kind !== ts.SyntaxKind.LessThanToken) {
    throw new Error("TYPESCRIPT_FOR_CONDITION_NON_MONOTONIC");
  }
  if (!ts.isIdentifier(node.condition.left) || node.condition.left.text !== varName) {
    throw new Error("TYPESCRIPT_FOR_CONDITION_NON_MONOTONIC");
  }
  const endExpr = parseExpr(node.condition.right);

  if (!node.incrementor) {
    throw new Error("TYPESCRIPT_FOR_UPDATE_NON_MONOTONIC");
  }
  let stepExpr = null;
  if (
    (ts.isPostfixUnaryExpression(node.incrementor) || ts.isPrefixUnaryExpression(node.incrementor))
    && node.incrementor.operator === ts.SyntaxKind.PlusPlusToken
  ) {
    if (!ts.isIdentifier(node.incrementor.operand) || node.incrementor.operand.text !== varName) {
      throw new Error("TYPESCRIPT_FOR_UPDATE_NON_MONOTONIC");
    }
  } else if (
    ts.isBinaryExpression(node.incrementor)
    && node.incrementor.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken
  ) {
    if (!ts.isIdentifier(node.incrementor.left) || node.incrementor.left.text !== varName) {
      throw new Error("TYPESCRIPT_FOR_UPDATE_NON_MONOTONIC");
    }
    stepExpr = parseExpr(node.incrementor.right);
  } else {
    throw new Error("TYPESCRIPT_FOR_UPDATE_NON_MONOTONIC");
  }

  const bodyStmts = parseStmts(statementNodes(node.statement));
  const res = {
    kind: "for",
    name: varName,
    type: "integer",
    start: startExpr,
    end: endExpr,
    body: bodyStmts,
    source_span: span(node),
  };
  if (stepExpr !== null) {
    res.step = stepExpr;
  }
  return res;
}

function sourceStatements(nodes, records = new Map(), functionNames = new Set()) {
  return nodes.map((node) => {
    if (ts.isReturnStatement(node) && node.expression) {
      return {
        kind: "return",
        expression: sourceExpression(node.expression, records, null, functionNames),
        source_span: span(node),
      };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: sourceExpression(node.expression, records, null, functionNames),
        then: sourceStatements(statementNodes(node.thenStatement), records, functionNames),
        else: node.elseStatement ? sourceStatements(statementNodes(node.elseStatement), records, functionNames) : [],
        source_span: span(node),
      };
    }
    if (ts.isWhileStatement(node)) {
      return {
        kind: "while",
        condition: sourceExpression(node.expression, records, null, functionNames),
        body: sourceStatements(statementNodes(node.statement), records, functionNames),
        source_span: span(node),
      };
    }
    if (ts.isForStatement(node)) {
      return parseForStatement(
        node,
        (expr) => sourceExpression(expr, records, null, functionNames),
        (stmts) => sourceStatements(stmts, records, functionNames),
        records,
      );
    }
    if (ts.isBreakStatement(node)) {
      if (node.label) throw new Error("TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
      return { kind: "break", source_span: span(node) };
    }
    if (ts.isContinueStatement(node)) {
      if (node.label) throw new Error("TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
      return { kind: "continue", source_span: span(node) };
    }
    if (ts.isDoStatement(node)) {
      throw new Error("TYPESCRIPT_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET");
    }
    if (ts.isForOfStatement(node)) {
      throw new Error("TYPESCRIPT_FOR_OF_OUTSIDE_CERTIFIED_SUBSET");
    }
    if (ts.isForInStatement(node)) {
      throw new Error("TYPESCRIPT_FOR_IN_OUTSIDE_CERTIFIED_SUBSET");
    }
    if (ts.isLabeledStatement(node)) {
      throw new Error("TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
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
      let canonicalType = typeName(decl.type, records);
      if (canonicalType === "number" && ts.isNumericLiteral(decl.initializer)) {
        const text = decl.initializer.text;
        if (!/[.eE]/.test(text)) {
          canonicalType = "integer";
        }
      }
      return {
        kind: "let",
        name: decl.name.text,
        type: canonicalType,
        expression: sourceExpression(decl.initializer, records, canonicalType, functionNames),
        source_span: span(node),
      };
    }
    throw new Error(`TYPESCRIPT_UNSUPPORTED_STATEMENT:${ts.SyntaxKind[node.kind]}`);
  });
}

function emittedStatements(nodes, records = new Map(), expectedReturn = null, functionNames = new Set()) {
  return nodes.map((node) => {
    if (ts.isReturnStatement(node) && node.expression) {
      return {
        kind: "return",
        expression: emittedExpression(node.expression, { records, expectedType: expectedReturn, functionNames }),
        source_span: span(node),
      };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: emittedExpression(node.expression, { records, functionNames }),
        then: emittedStatements(statementNodes(node.thenStatement), records, expectedReturn, functionNames),
        else: node.elseStatement ? emittedStatements(statementNodes(node.elseStatement), records, expectedReturn, functionNames) : [],
        source_span: span(node),
      };
    }
    if (ts.isWhileStatement(node)) {
      return {
        kind: "while",
        condition: emittedExpression(node.expression, { records, functionNames }),
        body: emittedStatements(statementNodes(node.statement), records, expectedReturn, functionNames),
        source_span: span(node),
      };
    }
    if (ts.isForStatement(node)) {
      return parseForStatement(
        node,
        (expr) => emittedExpression(expr, { records, functionNames }),
        (stmts) => emittedStatements(stmts, records, expectedReturn, functionNames),
        records,
      );
    }
    if (ts.isBreakStatement(node)) {
      if (node.label) throw new Error("TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
      return { kind: "break", source_span: span(node) };
    }
    if (ts.isContinueStatement(node)) {
      if (node.label) throw new Error("TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
      return { kind: "continue", source_span: span(node) };
    }
    if (ts.isDoStatement(node)) {
      throw new Error("TYPESCRIPT_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET");
    }
    if (ts.isForOfStatement(node)) {
      throw new Error("TYPESCRIPT_FOR_OF_OUTSIDE_CERTIFIED_SUBSET");
    }
    if (ts.isForInStatement(node)) {
      throw new Error("TYPESCRIPT_FOR_IN_OUTSIDE_CERTIFIED_SUBSET");
    }
    if (ts.isLabeledStatement(node)) {
      throw new Error("TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
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
      let canonicalType = typeName(decl.type, records);
      if (canonicalType === "number" && ts.isNumericLiteral(decl.initializer)) {
        const text = decl.initializer.text;
        if (!/[.eE]/.test(text)) {
          canonicalType = "integer";
        }
      }
      return {
        kind: "let",
        name: decl.name.text,
        type: canonicalType,
        expression: emittedExpression(decl.initializer, { records, expectedType: canonicalType, functionNames }),
        source_span: span(node),
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
    if (ts.isWhileStatement(node)) {
      values.push(...returnExpressions(statementNodes(node.statement)));
    }
    if (ts.isForStatement(node)) {
      values.push(...returnExpressions(statementNodes(node.statement)));
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

function extractExpressionCallees(expr, callees) {
  if (!expr) return;
  if (expr.kind === "call") {
    if (expr.function_name) callees.add(expr.function_name);
    for (const arg of (expr.arguments || [])) {
      extractExpressionCallees(arg, callees);
    }
  } else if (expr.kind === "binary") {
    extractExpressionCallees(expr.left, callees);
    extractExpressionCallees(expr.right, callees);
  } else if (expr.kind === "member_access") {
    extractExpressionCallees(expr.target, callees);
  } else if (expr.kind === "record_construct") {
    for (const val of Object.values(expr.arguments || {})) {
      extractExpressionCallees(val, callees);
    }
  }
}

function extractStatementCallees(stmts, callees) {
  for (const stmt of stmts) {
    if (stmt.kind === "return" || stmt.kind === "let") {
      extractExpressionCallees(stmt.expression, callees);
    } else if (stmt.kind === "if") {
      extractExpressionCallees(stmt.condition, callees);
      extractStatementCallees(stmt.then || [], callees);
      extractStatementCallees(stmt.else || [], callees);
    } else if (stmt.kind === "while") {
      extractExpressionCallees(stmt.condition, callees);
      extractStatementCallees(stmt.body || [], callees);
    } else if (stmt.kind === "for") {
      extractExpressionCallees(stmt.start, callees);
      extractExpressionCallees(stmt.end, callees);
      if (stmt.step) extractExpressionCallees(stmt.step, callees);
      extractStatementCallees(stmt.body || [], callees);
    }
  }
}

function extractFunctionCallees(fn) {
  const callees = new Set();
  extractStatementCallees(fn.body || [], callees);
  return callees;
}

function topologicalSortFunctions(functions) {
  const fnMap = new Map(functions.map((fn) => [fn.name, fn]));
  const calleesMap = new Map();
  for (const fn of functions) {
    const called = extractFunctionCallees(fn);
    if (called.has(fn.name)) {
      throw new Error(`RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET:${fn.name}->${fn.name}`);
    }
    const filtered = new Set();
    for (const c of called) {
      if (fnMap.has(c)) filtered.add(c);
    }
    calleesMap.set(fn.name, filtered);
  }

  // 3-color DFS cycle detection: 0=unvisited, 1=visiting, 2=visited
  const state = new Map(functions.map((fn) => [fn.name, 0]));
  const callPath = [];

  function dfs(name) {
    state.set(name, 1);
    callPath.push(name);
    const callees = Array.from(calleesMap.get(name)).sort();
    for (const callee of callees) {
      if (state.get(callee) === 1) {
        const cycleStartIndex = callPath.indexOf(callee);
        const cycleSlice = callPath.slice(cycleStartIndex).concat([callee]);
        throw new Error(`RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET:${cycleSlice.join("->")}`);
      }
      if (state.get(callee) === 0) {
        dfs(callee);
      }
    }
    callPath.pop();
    state.set(name, 2);
  }

  for (const fn of functions) {
    if (state.get(fn.name) === 0) {
      dfs(fn.name);
    }
  }

  // Topological sort: Kahn's algorithm
  const inDegree = new Map();
  const dependents = new Map();
  for (const fn of functions) {
    inDegree.set(fn.name, calleesMap.get(fn.name).size);
    dependents.set(fn.name, []);
  }
  for (const [caller, callees] of calleesMap.entries()) {
    for (const callee of callees) {
      dependents.get(callee).push(caller);
    }
  }

  const originalOrder = new Map(functions.map((fn, idx) => [fn.name, idx]));
  const ready = functions
    .filter((fn) => inDegree.get(fn.name) === 0)
    .map((fn) => fn.name)
    .sort((a, b) => originalOrder.get(a) - originalOrder.get(b));

  const sortedNames = [];
  while (ready.length > 0) {
    const current = ready.shift();
    sortedNames.push(current);
    const currentDependents = dependents.get(current) || [];
    currentDependents.sort((a, b) => originalOrder.get(a) - originalOrder.get(b));
    for (const dep of currentDependents) {
      inDegree.set(dep, inDegree.get(dep) - 1);
      if (inDegree.get(dep) === 0) {
        ready.push(dep);
        ready.sort((a, b) => originalOrder.get(a) - originalOrder.get(b));
      }
    }
  }

  return sortedNames.map((name) => fnMap.get(name));
}

function extractFunctionSignature(item, emittedTarget, records) {
  if (!item.name || !item.body) throw new Error("TYPESCRIPT_FUNCTION_BODY_REQUIRED");
  const parameters = item.parameters.map((parameter) => {
    if (!ts.isIdentifier(parameter.name)) {
      throw new Error("TYPESCRIPT_DESTRUCTURED_PARAMETER_UNSUPPORTED");
    }
    return {
      name: parameter.name.text,
      declaredType: typeName(parameter.type, records),
      source_span: span(parameter.name),
    };
  });
  if (!emittedTarget) {
    return {
      name: item.name.text,
      parameters: parameters.map((parameter) => ({
        name: parameter.name,
        type: parameter.declaredType,
        source_span: parameter.source_span,
      })),
      return_type: typeName(item.type, records),
      source_span: span(item),
    };
  }
  const split = splitParameterGuards([...item.body.statements], parameters);
  const liftedParameters = parameters.map((parameter) => ({
    name: parameter.name,
    type: parameter.declaredType === "number" && split.guarded.has(parameter.name)
      ? "integer"
      : parameter.declaredType,
    source_span: parameter.source_span,
  }));
  const declaredReturn = typeName(item.type, records);
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
  return {
    name: item.name.text,
    parameters: liftedParameters,
    return_type: liftedReturn,
    source_span: span(item),
  };
}

function parseSingleFunction(item, emittedTarget, records, allFunctionNames, functionsEnv) {
  const sig = functionsEnv.get(item.name.text) ?? extractFunctionSignature(item, emittedTarget, records);
  if (!emittedTarget) {
    return {
      name: sig.name,
      parameters: sig.parameters,
      return_type: sig.return_type,
      body: sourceStatements([...item.body.statements], records, allFunctionNames),
      source_span: span(item),
    };
  }
  const parameters = item.parameters.map((parameter) => ({
    name: parameter.name.text,
    declaredType: typeName(parameter.type, records),
    source_span: span(parameter.name),
  }));
  const split = splitParameterGuards([...item.body.statements], parameters);
  const environment = new Map(sig.parameters.map((parameter) => [parameter.name, parameter.type]));
  const returns = returnExpressions(split.body);
  const returnContracts = returns.map(numericReturnContract);
  const numericContract = returnContracts[0];
  validateEmittedArithmeticStatements(split.body, environment, numericContract, sig.return_type, records, functionsEnv);
  return {
    name: sig.name,
    parameters: sig.parameters,
    return_type: sig.return_type,
    body: emittedStatements(split.body, records, sig.return_type, allFunctionNames),
    source_span: span(item),
  };
}

function analyzeNamedFunction(functionName) {
  const analysisDiagnostics = diagnostics();
  if (emittedTarget) validateEmittedHelperDeclarations();
  const { recordDefs, records } = parseRecords(sourceFile);

  const allFunctionDecls = new Map();
  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.name) {
      const name = statement.name.text;
      if (name.startsWith("_elmos") || CANONICAL_EMITTED_HELPERS.has(name)) {
        continue;
      }
      if (allFunctionDecls.has(name)) {
        throw new Error(`TYPESCRIPT_DUPLICATE_FUNCTION_NAME:${name}`);
      }
      allFunctionDecls.set(name, statement);
    }
  }

  if (!allFunctionDecls.has(functionName)) {
    analysisDiagnostics.push(`FUNCTION_NOT_FOUND:${functionName}`);
    return {
      schema_version: "1.0.0",
      source_language: "typescript",
      source_file: sourceName,
      analyzer: emittedTarget
        ? "TypeScript Compiler API emitted-target"
        : "TypeScript Compiler API",
      analyzer_version: ts.version,
      records: recordDefs,
      functions: [],
      diagnostics: analysisDiagnostics,
    };
  }

  const allFunctionNames = new Set(allFunctionDecls.keys());
  const functionsEnv = new Map();
  for (const [name, decl] of allFunctionDecls.entries()) {
    functionsEnv.set(name, extractFunctionSignature(decl, emittedTarget, records));
  }

  const parsedFunctions = new Map();
  const queue = [functionName];
  const visited = new Set([functionName]);

  while (queue.length > 0) {
    const currName = queue.shift();
    const decl = allFunctionDecls.get(currName);
    const parsed = parseSingleFunction(decl, emittedTarget, records, allFunctionNames, functionsEnv);
    parsedFunctions.set(currName, parsed);
    const callees = extractFunctionCallees(parsed);
    for (const callee of callees) {
      if (allFunctionDecls.has(callee)) {
        if (!visited.has(callee)) {
          visited.add(callee);
          queue.push(callee);
        }
      } else {
        throw new Error(`UNKNOWN_FUNCTION:${callee}`);
      }
    }
  }

  const sortedFunctions = topologicalSortFunctions(Array.from(parsedFunctions.values()));

  return {
    schema_version: "1.0.0",
    source_language: "typescript",
    source_file: sourceName,
    analyzer: emittedTarget
      ? "TypeScript Compiler API emitted-target"
      : "TypeScript Compiler API",
    analyzer_version: ts.version,
    records: recordDefs,
    functions: sortedFunctions,
    diagnostics: analysisDiagnostics,
  };
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
          ? helperSignature ?? { visibility: "not-applicable", storage: "not-applicable" }
          : {
            parameters: statement.parameters.map((parameter) => ({
              name: ts.isIdentifier(parameter.name) ? parameter.name.text : parameter.name.getText(sourceFile),
              source_type: parameter.type?.getText(sourceFile) ?? "",
            })),
            source_return_type: statement.type?.getText(sourceFile) ?? "",
            visibility: statement.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword) ? "public" : "internal",
            storage: "file-scope",
          },
      );
      continue;
    }
    if (ts.isClassDeclaration(statement)) {
      const className = statement.name?.text ?? `<anonymous-class@${statement.pos}>`;
      add(statement, className, className, "ClassDeclaration", false, {
        visibility: "not-applicable",
        storage: "not-applicable",
      });
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
          {
            visibility: "not-applicable",
            storage: "not-applicable",
          },
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
          {
            source_type: declaration.type?.getText(sourceFile) ?? "",
            visibility: "not-applicable",
            storage: "not-applicable",
          },
        );
      }
      continue;
    }
    if (ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement)) {
      const moduleName = statement.moduleSpecifier && ts.isStringLiteral(statement.moduleSpecifier)
        ? statement.moduleSpecifier.text
        : `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
      add(statement, moduleName, moduleName, ts.SyntaxKind[statement.kind], false, {
        visibility: "not-applicable",
        storage: "not-applicable",
      });
      continue;
    }
    if (ts.isInterfaceDeclaration(statement)) {
      const name = statement.name.text;
      add(statement, name, name, "InterfaceDeclaration", false, {
        visibility: "not-applicable",
        storage: "not-applicable",
      });
      continue;
    }
    if (ts.isTypeAliasDeclaration(statement)) {
      const name = statement.name.text;
      add(statement, name, name, "TypeAliasDeclaration", false, {
        visibility: "not-applicable",
        storage: "not-applicable",
      });
      continue;
    }
    if (ts.isEmptyStatement(statement)) continue;
    const name = `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
    add(statement, name, name, ts.SyntaxKind[statement.kind], false, {
      visibility: "not-applicable",
      storage: "not-applicable",
    });
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

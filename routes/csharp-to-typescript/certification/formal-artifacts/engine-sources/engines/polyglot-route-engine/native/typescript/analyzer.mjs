import fs from "node:fs";
import { pathToFileURL } from "node:url";

const [typescriptPath, sourcePath, functionName, mode] = process.argv.slice(2);
if (!typescriptPath || !sourcePath || !functionName || mode !== "--emitted-target") {
  throw new Error(
    "usage: analyzer.mjs <typescript-module> <source> <function> --emitted-target",
  );
}

const imported = await import(pathToFileURL(typescriptPath).href);
const ts = imported.default ?? imported;
const source = fs.readFileSync(sourcePath, "utf8");
const sourceFile = ts.createSourceFile(
  sourcePath.split(/[\\/]/).at(-1),
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
  if (!value) {
    throw new Error(`TYPESCRIPT_EMITTED_OPERATOR_UNSUPPORTED:${ts.SyntaxKind[kind]}`);
  }
  return value;
}

function expression(node, { allowNonZero = false, allowMathTrunc = false } = {}) {
  if (ts.isParenthesizedExpression(node)) {
    return expression(node.expression, { allowNonZero, allowMathTrunc });
  }
  if (ts.isIdentifier(node)) return { kind: "name", value: node.text };
  if (ts.isNumericLiteral(node)) return { kind: "literal", value: Number(node.text) };
  if (ts.isStringLiteral(node)) return { kind: "literal", value: node.text };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { kind: "literal", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { kind: "literal", value: false };
  if (ts.isBinaryExpression(node)) {
    const liftedOperator = operator(node.operatorToken.kind);
    const guarded = liftedOperator === "/" || liftedOperator === "%";
    if (guarded && !exactCall(node.right, "_elmosRequireNonZero", 1)) {
      throw new Error(`TYPESCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:${liftedOperator}`);
    }
    return {
      kind: "binary",
      operator: liftedOperator,
      left: expression(node.left),
      right: expression(node.right, { allowNonZero: guarded }),
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
        return expression(argument, { allowMathTrunc: true });
      }
      return expression(argument);
    }
    if (name === "_elmosRequireNonZero") {
      if (!allowNonZero || !exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_NON_ZERO_GUARD_INVALID");
      }
      return expression(node.arguments[0]);
    }
    if (name === "Math.trunc") {
      if (!allowMathTrunc || !exactCall(node, name, 1)) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_INVALID");
      }
      const argument = node.arguments[0];
      if (!ts.isBinaryExpression(argument) || argument.operatorToken.kind !== ts.SyntaxKind.SlashToken) {
        throw new Error("TYPESCRIPT_EMITTED_TRUNCATION_SHAPE_INVALID");
      }
      return expression(argument);
    }
    throw new Error(`TYPESCRIPT_EMITTED_HELPER_UNRECOGNIZED:${name || "<complex>"}`);
  }
  throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
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

function statementNodes(node) {
  return ts.isBlock(node) ? [...node.statements] : [node];
}

function statements(nodes) {
  return nodes.map((node) => {
    if (ts.isReturnStatement(node) && node.expression) {
      return { kind: "return", expression: expression(node.expression) };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: expression(node.expression),
        then: statements(statementNodes(node.thenStatement)),
        else: node.elseStatement ? statements(statementNodes(node.elseStatement)) : [],
      };
    }
    throw new Error(`TYPESCRIPT_UNSUPPORTED_STATEMENT:${ts.SyntaxKind[node.kind]}`);
  });
}

function splitParameterGuards(body, parameters) {
  const parameterIndex = new Map(parameters.map((item, index) => [item.name, index]));
  const guarded = new Set();
  let lastIndex = -1;
  let offset = 0;
  while (offset < body.length) {
    const node = body[offset];
    if (!ts.isExpressionStatement(node) || !exactCall(node.expression, "_elmosRequireSafeInteger", 1)) {
      break;
    }
    const argument = node.expression.arguments[0];
    if (!ts.isIdentifier(argument) || !parameterIndex.has(argument.text)) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_INVALID");
    }
    const index = parameterIndex.get(argument.text);
    if (guarded.has(argument.text) || index <= lastIndex) {
      throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_ORDER_INVALID");
    }
    guarded.add(argument.text);
    lastIndex = index;
    offset += 1;
  }
  if (body.slice(offset).some((node) =>
    ts.isExpressionStatement(node)
      && exactCall(node.expression, "_elmosRequireSafeInteger", 1))) {
    throw new Error("TYPESCRIPT_EMITTED_PARAMETER_GUARD_UNEXPECTED");
  }
  return { guarded, body: body.slice(offset) };
}

const parseDiagnostics = sourceFile.parseDiagnostics ?? [];
const diagnostics = parseDiagnostics.map((item) => {
  const line = sourceFile.getLineAndCharacterOfPosition(item.start ?? 0).line + 1;
  return `TS${item.code}:${line}`;
});
const functions = sourceFile.statements
  .filter(ts.isFunctionDeclaration)
  .filter((item) => item.name?.text === functionName)
  .map((item) => {
    if (!item.name || !item.body) throw new Error("TYPESCRIPT_FUNCTION_BODY_REQUIRED");
    const parameters = item.parameters.map((parameter) => {
      if (!ts.isIdentifier(parameter.name)) {
        throw new Error("TYPESCRIPT_DESTRUCTURED_PARAMETER_UNSUPPORTED");
      }
      return {
        name: parameter.name.text,
        declaredType: typeName(parameter.type),
      };
    });
    const split = splitParameterGuards([...item.body.statements], parameters);
    const liftedParameters = parameters.map((parameter) => ({
      name: parameter.name,
      type: parameter.declaredType === "number" && split.guarded.has(parameter.name)
        ? "integer"
        : parameter.declaredType,
    }));
    const declaredReturn = typeName(item.type);
    const returns = returnExpressions(split.body);
    if (returns.length === 0) throw new Error("TYPESCRIPT_RETURN_EXPRESSION_REQUIRED");
    const guardedReturn = returns.every((value) => exactCall(value, "_elmosRequireSafeInteger", 1));
    const partiallyGuardedReturn = returns.some((value) => exactCall(value, "_elmosRequireSafeInteger", 1));
    if (partiallyGuardedReturn && !guardedReturn) {
      throw new Error("TYPESCRIPT_EMITTED_RETURN_GUARD_INCONSISTENT");
    }
    return {
      name: item.name.text,
      parameters: liftedParameters,
      return_type: declaredReturn === "number" && guardedReturn ? "integer" : declaredReturn,
      body: statements(split.body),
    };
  });
if (functions.length === 0) diagnostics.push(`FUNCTION_NOT_FOUND:${functionName}`);

process.stdout.write(`${JSON.stringify({
  schema_version: "1.0.0",
  source_language: "typescript",
  source_file: sourceFile.fileName,
  analyzer: "TypeScript Compiler API emitted-target",
  analyzer_version: ts.version,
  functions,
  diagnostics,
})}\n`);

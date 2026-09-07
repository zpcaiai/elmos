import fs from "node:fs";
import { pathToFileURL } from "node:url";

const EXPECTED_TYPESCRIPT_VERSION = "5.9.2";
const EXPECTED_REACT_VERSION = "19.2.7";
const EXPECTED_REACT_DOM_VERSION = "19.2.7";

const arguments_ = process.argv.slice(2);
if (arguments_.length !== 5) {
  throw new Error(
    "usage: analyzer.mjs <typescript-module> <react-entry> <react-dom-entry> <source.tsx> <function>",
  );
}

const [typescriptPath, reactPath, reactDomPath, sourcePath, functionName] = arguments_;
if (!typescriptPath || !reactPath || !reactDomPath || !sourcePath || !functionName) {
  throw new Error("REACT_ANALYZER_COMMAND_SHAPE_INVALID");
}
if (!sourcePath.endsWith(".tsx") && !sourcePath.endsWith(".ts")) {
  throw new Error("REACT_SOURCE_EXTENSION_UNSUPPORTED");
}

const importedTypeScript = await import(pathToFileURL(typescriptPath).href);
const ts = importedTypeScript.default ?? importedTypeScript;
const importedReact = await import(pathToFileURL(reactPath).href);
const importedReactDom = await import(pathToFileURL(reactDomPath).href);
const reactVersion = importedReact.version ?? importedReact.default?.version;
const reactDomVersion = importedReactDom.version ?? importedReactDom.default?.version;

const source = fs.readFileSync(sourcePath, "utf8");
const sourceName = sourcePath.split(/[\\/]/).at(-1);
const sourceFile = ts.createSourceFile(
  sourceName,
  source,
  ts.ScriptTarget.ES2022,
  true,
  sourcePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
);

function isHookName(name) {
  const marker = name.at(3);
  return name.startsWith("use")
    && marker !== undefined
    && (marker === "_" || marker.toUpperCase() === marker);
}

function isJsxNode(node) {
  return ts.isJsxElement(node)
    || ts.isJsxSelfClosingElement(node)
    || ts.isJsxFragment(node)
    || ts.isJsxOpeningElement(node)
    || ts.isJsxClosingElement(node)
    || ts.isJsxExpression(node)
    || ts.isJsxText(node);
}

function rejectUiSemantics(node) {
  if (isJsxNode(node)) {
    throw new Error(`REACT_UI_SEMANTICS_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
  }
  if (
    ts.isImportDeclaration(node)
    || ts.isImportEqualsDeclaration(node)
    || ts.isExportDeclaration(node)
  ) {
    throw new Error(`REACT_IMPORT_BOUND_SEMANTICS_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
  }
  if (ts.isClassDeclaration(node)) {
    throw new Error("REACT_COMPONENT_SEMANTICS_UNSUPPORTED:ClassDeclaration");
  }
  if (ts.isFunctionDeclaration(node) && node.name) {
    if (/^[A-Z]/.test(node.name.text)) {
      throw new Error(`REACT_COMPONENT_SEMANTICS_UNSUPPORTED:${node.name.text}`);
    }
    if (isHookName(node.name.text)) {
      throw new Error(`REACT_HOOK_SEMANTICS_UNSUPPORTED:${node.name.text}`);
    }
  }
  if (ts.isCallExpression(node)) {
    const callee = node.expression.getText(sourceFile);
    const hookName = callee.startsWith("React.") ? callee.slice("React.".length) : callee;
    if (isHookName(hookName)) {
      throw new Error(`REACT_HOOK_SEMANTICS_UNSUPPORTED:${callee}`);
    }
  }
  ts.forEachChild(node, rejectUiSemantics);
}

function rejectUnrepresentedModuleStatements() {
  for (const statement of sourceFile.statements) {
    if (ts.isFunctionDeclaration(statement) || ts.isEmptyStatement(statement)) continue;
    if (
      ts.isImportDeclaration(statement)
      || ts.isImportEqualsDeclaration(statement)
      || ts.isExportDeclaration(statement)
    ) {
      throw new Error(`REACT_IMPORT_BOUND_SEMANTICS_UNSUPPORTED:${ts.SyntaxKind[statement.kind]}`);
    }
    if (ts.isClassDeclaration(statement)) {
      throw new Error("REACT_COMPONENT_SEMANTICS_UNSUPPORTED:ClassDeclaration");
    }
    throw new Error(`REACT_MODULE_STATEMENT_UNSUPPORTED:${ts.SyntaxKind[statement.kind]}`);
  }
}

function explicitType(node) {
  if (!node) throw new Error("REACT_EXPLICIT_TYPE_REQUIRED");
  if (node.kind === ts.SyntaxKind.NumberKeyword) return "number";
  if (node.kind === ts.SyntaxKind.BooleanKeyword) return "boolean";
  if (node.kind === ts.SyntaxKind.StringKeyword) return "string";
  const rendered = node.getText(sourceFile);
  if (rendered.startsWith("JSX.") || rendered === "ReactNode" || rendered === "ReactElement") {
    throw new Error(`REACT_UI_SEMANTICS_UNSUPPORTED:${rendered}`);
  }
  throw new Error(`REACT_UNSUPPORTED_TYPE:${rendered}`);
}

function numericLiteral(node) {
  const value = Number(node.text);
  if (!Number.isFinite(value)) throw new Error("REACT_NON_FINITE_LITERAL_UNSUPPORTED");
  const sourceText = node.getText(sourceFile);
  return {
    ir: { kind: "literal", value },
    type: sourceText.includes(".") || sourceText.includes("e") || sourceText.includes("E")
      ? "number"
      : "integer",
  };
}

function negativeNumericLiteral(node) {
  if (!ts.isPrefixUnaryExpression(node)) return null;
  if (node.operator !== ts.SyntaxKind.MinusToken || !ts.isNumericLiteral(node.operand)) {
    throw new Error("REACT_UNARY_MINUS_LITERAL_REQUIRED");
  }
  const literal = numericLiteral(node.operand);
  if (literal.ir.value === 0) throw new Error("REACT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED");
  return {
    ir: { kind: "literal", value: -literal.ir.value },
    type: literal.type,
  };
}

const operatorByKind = new Map([
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
const arithmeticOperators = new Set(["+", "-", "*", "/", "%"]);
const orderingOperators = new Set(["<", "<=", ">", ">="]);
const equalityOperators = new Set(["==", "!="]);
const logicalOperators = new Set(["&&", "||"]);
const numericTypes = new Set(["integer", "number"]);

function lowerExpression(node, environment) {
  if (ts.isParenthesizedExpression(node)) return lowerExpression(node.expression, environment);
  if (isJsxNode(node)) {
    throw new Error(`REACT_UI_SEMANTICS_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
  }
  if (ts.isIdentifier(node)) {
    const type = environment.get(node.text);
    if (type === undefined) throw new Error(`REACT_FREE_NAME_UNSUPPORTED:${node.text}`);
    return { ir: { kind: "name", value: node.text }, type };
  }
  if (ts.isNumericLiteral(node)) return numericLiteral(node);
  const negative = negativeNumericLiteral(node);
  if (negative !== null) return negative;
  if (ts.isStringLiteral(node)) {
    return { ir: { kind: "literal", value: node.text }, type: "string" };
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword) {
    return { ir: { kind: "literal", value: node.kind === ts.SyntaxKind.TrueKeyword }, type: "boolean" };
  }
  if (ts.isBinaryExpression(node)) {
    if (
      node.operatorToken.kind === ts.SyntaxKind.EqualsEqualsToken
      || node.operatorToken.kind === ts.SyntaxKind.ExclamationEqualsToken
    ) {
      throw new Error("REACT_COERCIVE_EQUALITY_UNSUPPORTED");
    }
    const operator = operatorByKind.get(node.operatorToken.kind);
    if (operator === undefined) {
      throw new Error(`REACT_UNSUPPORTED_OPERATOR:${ts.SyntaxKind[node.operatorToken.kind]}`);
    }
    const left = lowerExpression(node.left, environment);
    const right = lowerExpression(node.right, environment);
    let type;
    if (arithmeticOperators.has(operator)) {
      if (operator === "+" && left.type === "string" && right.type === "string") {
        type = "string";
      } else {
        if (!numericTypes.has(left.type) || !numericTypes.has(right.type)) {
          throw new Error(`REACT_OPERAND_TYPE_MISMATCH:${operator}:${left.type}:${right.type}`);
        }
        type = left.type === "number" || right.type === "number" ? "number" : "integer";
      }
    } else if (orderingOperators.has(operator)) {
      if (!numericTypes.has(left.type) || !numericTypes.has(right.type)) {
        throw new Error(`REACT_OPERAND_TYPE_MISMATCH:${operator}:${left.type}:${right.type}`);
      }
      type = "boolean";
    } else if (equalityOperators.has(operator)) {
      if (left.type !== right.type && !(numericTypes.has(left.type) && numericTypes.has(right.type))) {
        throw new Error(`REACT_OPERAND_TYPE_MISMATCH:${operator}:${left.type}:${right.type}`);
      }
      type = "boolean";
    } else if (logicalOperators.has(operator)) {
      if (left.type !== "boolean" || right.type !== "boolean") {
        throw new Error(`REACT_OPERAND_TYPE_MISMATCH:${operator}:${left.type}:${right.type}`);
      }
      type = "boolean";
    } else {
      throw new Error(`REACT_UNSUPPORTED_OPERATOR:${operator}`);
    }
    return {
      ir: { kind: "binary", operator, left: left.ir, right: right.ir },
      type,
    };
  }
  throw new Error(`REACT_ROUTE_PROFILE_UNSUPPORTED:${ts.SyntaxKind[node.kind]}`);
}

function compatibleType(actual, declared) {
  return actual === declared || (actual === "integer" && declared === "number");
}

function statementNodes(node) {
  return ts.isBlock(node) ? [...node.statements] : [node];
}

function alwaysReturns(statements) {
  if (statements.length === 0) return false;
  const last = statements.at(-1);
  if (ts.isReturnStatement(last)) return true;
  return ts.isIfStatement(last)
    && last.elseStatement !== undefined
    && alwaysReturns(statementNodes(last.thenStatement))
    && alwaysReturns(statementNodes(last.elseStatement));
}

function lowerStatements(statements, environment, returnType) {
  return statements.map((statement) => {
    if (ts.isReturnStatement(statement) && statement.expression) {
      const value = lowerExpression(statement.expression, environment);
      if (!compatibleType(value.type, returnType)) {
        throw new Error(`REACT_RETURN_TYPE_MISMATCH:${returnType}:${value.type}`);
      }
      return { kind: "return", expression: value.ir };
    }
    if (ts.isIfStatement(statement)) {
      const condition = lowerExpression(statement.expression, environment);
      if (condition.type !== "boolean") {
        throw new Error(`REACT_IF_CONDITION_TYPE_MISMATCH:${condition.type}`);
      }
      return {
        kind: "if",
        condition: condition.ir,
        then: lowerStatements(statementNodes(statement.thenStatement), environment, returnType),
        else: statement.elseStatement
          ? lowerStatements(statementNodes(statement.elseStatement), environment, returnType)
          : [],
      };
    }
    throw new Error(`REACT_ROUTE_PROFILE_UNSUPPORTED:${ts.SyntaxKind[statement.kind]}`);
  });
}

function byteOffset(characterOffset) {
  return Buffer.byteLength(source.slice(0, characterOffset), "utf8");
}

function analyzeNamedFunction() {
  if (ts.version !== EXPECTED_TYPESCRIPT_VERSION) {
    throw new Error(`REACT_TYPESCRIPT_VERSION_MISMATCH:${ts.version}`);
  }
  if (reactVersion !== EXPECTED_REACT_VERSION) {
    throw new Error(`REACT_RUNTIME_VERSION_MISMATCH:${reactVersion ?? "missing"}`);
  }
  if (reactDomVersion !== EXPECTED_REACT_DOM_VERSION) {
    throw new Error(`REACT_DOM_RUNTIME_VERSION_MISMATCH:${reactDomVersion ?? "missing"}`);
  }
  const parseDiagnostics = sourceFile.parseDiagnostics ?? [];
  if (parseDiagnostics.length !== 0) {
    const first = parseDiagnostics[0];
    throw new Error(`REACT_PARSE_ERROR:TS${first.code}`);
  }
  // The route IR has no UI node. Refuse JSX or hooks anywhere in the module so
  // a selected pure helper cannot make an adjacent component look supported.
  rejectUiSemantics(sourceFile);
  rejectUnrepresentedModuleStatements();
  const matches = sourceFile.statements.filter(
    (statement) => ts.isFunctionDeclaration(statement) && statement.name?.text === functionName,
  );
  if (matches.length === 0) throw new Error(`FUNCTION_NOT_FOUND:${functionName}`);
  if (matches.length !== 1) throw new Error(`REACT_FUNCTION_AMBIGUOUS:${functionName}`);
  const node = matches[0];
  if (!node.name || !node.body) throw new Error("REACT_FUNCTION_BODY_REQUIRED");
  if (node.asteriskToken || node.typeParameters || node.questionToken) {
    throw new Error("REACT_FUNCTION_SHAPE_UNSUPPORTED");
  }
  const modifiers = node.modifiers ?? [];
  if (modifiers.some((modifier) => modifier.kind !== ts.SyntaxKind.ExportKeyword)) {
    throw new Error("REACT_FUNCTION_MODIFIER_UNSUPPORTED");
  }
  const parameters = node.parameters.map((parameter) => {
    if (
      !ts.isIdentifier(parameter.name)
      || parameter.dotDotDotToken
      || parameter.questionToken
      || parameter.initializer
      || parameter.modifiers?.length
    ) {
      throw new Error("REACT_PARAMETER_SHAPE_UNSUPPORTED");
    }
    return { name: parameter.name.text, type: explicitType(parameter.type) };
  });
  if (new Set(parameters.map((parameter) => parameter.name)).size !== parameters.length) {
    throw new Error("REACT_PARAMETER_NAME_DUPLICATE");
  }
  const returnType = explicitType(node.type);
  const environment = new Map(parameters.map((parameter) => [parameter.name, parameter.type]));
  const statements = [...node.body.statements];
  if (!alwaysReturns(statements)) throw new Error("REACT_FUNCTION_RETURN_NOT_TOTAL");
  return {
    schema_version: "1.0.0",
    source_language: "react",
    source_file: sourceName,
    analyzer: "TypeScript Compiler API TS/TSX / React dependency probe",
    analyzer_version: `TypeScript ${ts.version} / React ${reactVersion} / React DOM ${reactDomVersion}`,
    functions: [
      {
        name: node.name.text,
        parameters,
        return_type: returnType,
        body: lowerStatements(statements, environment, returnType),
        source_span: {
          file: sourceName,
          start_byte: byteOffset(node.getStart(sourceFile)),
          end_byte: byteOffset(node.end),
        },
      },
    ],
    diagnostics: [],
  };
}

function inventoryModule() {
  if (ts.version !== EXPECTED_TYPESCRIPT_VERSION) {
    throw new Error(`REACT_TYPESCRIPT_VERSION_MISMATCH:${ts.version}`);
  }
  if (reactVersion !== EXPECTED_REACT_VERSION) {
    throw new Error(`REACT_RUNTIME_VERSION_MISMATCH:${reactVersion ?? "missing"}`);
  }
  if (reactDomVersion !== EXPECTED_REACT_DOM_VERSION) {
    throw new Error(`REACT_DOM_RUNTIME_VERSION_MISMATCH:${reactDomVersion ?? "missing"}`);
  }
  const parseDiagnostics = sourceFile.parseDiagnostics ?? [];
  const diagnostics = parseDiagnostics.map((item) => `REACT_PARSE_ERROR:TS${item.code}`);
  const subjects = [];
  const span = (node) => ({
    file: sourceName,
    start_byte: byteOffset(node.getStart(sourceFile)),
    end_byte: byteOffset(node.end),
  });
  const add = (node, name, declarationKind, analyzable, signature = {}) => {
    subjects.push({
      name,
      qualified_name: name,
      declaration_kind: declarationKind,
      analyzable,
      source_span: span(node),
      signature,
    });
  };

  for (const statement of sourceFile.statements) {
    if (ts.isEmptyStatement(statement)) continue;
    if (ts.isFunctionDeclaration(statement)) {
      const name = statement.name?.text ?? `<anonymous-function@${statement.pos}>`;
      const permittedModifiers = statement.modifiers?.every(
        (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword,
      ) ?? true;
      const supportedParameters = statement.parameters.every(
        (parameter) => ts.isIdentifier(parameter.name)
          && parameter.dotDotDotToken === undefined
          && parameter.questionToken === undefined
          && parameter.initializer === undefined
          && (parameter.modifiers?.length ?? 0) === 0,
      );
      const hook = isHookName(name);
      const component = /^[A-Z]/.test(name);
      add(
        statement,
        name,
        "FunctionDeclaration",
        Boolean(
          statement.name
          && statement.body
          && statement.asteriskToken === undefined
          && statement.typeParameters === undefined
          && permittedModifiers
          && supportedParameters
          && !hook
          && !component
        ),
        {
          parameters: statement.parameters.map((parameter) => ({
            name: ts.isIdentifier(parameter.name) ? parameter.name.text : parameter.name.getText(sourceFile),
            source_type: parameter.type?.getText(sourceFile) ?? "",
          })),
          source_return_type: statement.type?.getText(sourceFile) ?? "",
          visibility: statement.modifiers?.some(
            (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword,
          ) ? "exported" : "internal",
          storage: "file-scope",
        },
      );
      continue;
    }
    if (
      ts.isImportDeclaration(statement)
      || ts.isImportEqualsDeclaration(statement)
      || ts.isExportDeclaration(statement)
    ) {
      const moduleName = statement.moduleSpecifier && ts.isStringLiteral(statement.moduleSpecifier)
        ? statement.moduleSpecifier.text
        : `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
      add(statement, moduleName, ts.SyntaxKind[statement.kind], false);
      continue;
    }
    if (ts.isClassDeclaration(statement)) {
      add(
        statement,
        statement.name?.text ?? `<anonymous-class@${statement.pos}>`,
        "ClassDeclaration",
        false,
      );
      continue;
    }
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        add(
          declaration,
          declaration.name.getText(sourceFile),
          "VariableDeclaration",
          false,
          { source_type: declaration.type?.getText(sourceFile) ?? "" },
        );
      }
      continue;
    }
    const name = `<${ts.SyntaxKind[statement.kind]}@${statement.pos}>`;
    add(statement, name, ts.SyntaxKind[statement.kind], false);
  }

  return {
    schema_version: "1.0.0",
    kind: "elmos.typed-pure-module-inventory",
    profile: "typed-pure-module-v1",
    source_language: "react",
    source_file: sourceName,
    analyzer: "TypeScript Compiler API TS/TSX / React dependency probe",
    analyzer_version: `TypeScript ${ts.version} / React ${reactVersion} / React DOM ${reactDomVersion}`,
    enumeration_status: diagnostics.length === 0 ? "PASSED" : "FAILED",
    subjects,
    diagnostics,
  };
}

try {
  process.stdout.write(`${JSON.stringify(
    functionName === "--inventory" ? inventoryModule() : analyzeNamedFunction(),
  )}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : "REACT_ANALYZER_FAILED";
  const safe = /^[A-Z][A-Z0-9_]*(?::[A-Za-z0-9_.:<>=/+,$!&*%\-]+)*$/.test(message)
    ? message
    : "REACT_ANALYZER_FAILED";
  process.stderr.write(`${safe}\n`);
  process.exitCode = 2;
}

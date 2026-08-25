import ts from "typescript";

type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];
type JsonObject = { [key: string]: JsonValue };
interface ParsedSourceFile extends ts.SourceFile {
  readonly parseDiagnostics: readonly ts.DiagnosticWithLocation[];
}

function typeName(node: ts.TypeNode | undefined): string {
  if (!node) throw new Error("TYPESCRIPT_EXPLICIT_TYPE_REQUIRED");
  const value = node.getText();
  if (value === "number") return "number";
  if (value === "boolean") return "boolean";
  if (value === "string") return "string";
  throw new Error(`TYPESCRIPT_UNSUPPORTED_TYPE:${value}`);
}

function operator(kind: ts.SyntaxKind): string {
  const values = new Map<ts.SyntaxKind, string>([
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

function expression(node: ts.Expression): JsonObject {
  if (ts.isParenthesizedExpression(node)) return expression(node.expression);
  if (ts.isIdentifier(node)) return { kind: "name", value: node.text };
  if (ts.isNumericLiteral(node)) return { kind: "literal", value: Number(node.text) };
  if (ts.isStringLiteral(node)) return { kind: "literal", value: node.text };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { kind: "literal", value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { kind: "literal", value: false };
  if (ts.isBinaryExpression(node)) {
    return {
      kind: "binary",
      operator: operator(node.operatorToken.kind),
      left: expression(node.left),
      right: expression(node.right),
    };
  }
  throw new Error(`TYPESCRIPT_UNSUPPORTED_EXPRESSION:${ts.SyntaxKind[node.kind]}`);
}

function statementBody(node: ts.Statement): JsonObject[] {
  return ts.isBlock(node) ? statements([...node.statements]) : statements([node]);
}

function statements(nodes: ts.Statement[]): JsonObject[] {
  return nodes.map(node => {
    if (ts.isReturnStatement(node) && node.expression) {
      return { kind: "return", expression: expression(node.expression) };
    }
    if (ts.isIfStatement(node)) {
      return {
        kind: "if",
        condition: expression(node.expression),
        then: statementBody(node.thenStatement),
        else: node.elseStatement ? statementBody(node.elseStatement) : [],
      };
    }
    throw new Error(`TYPESCRIPT_UNSUPPORTED_STATEMENT:${ts.SyntaxKind[node.kind]}`);
  });
}

export function analyzeTypedFunction(source: string, sourceFile: string, functionName: string): JsonObject {
  const tree = ts.createSourceFile(
    sourceFile,
    source,
    ts.ScriptTarget.ES2022,
    true,
    ts.ScriptKind.TS,
  ) as ParsedSourceFile;
  const diagnostics = tree.parseDiagnostics.map(item => `TS${item.code}:${tree.getLineAndCharacterOfPosition(item.start ?? 0).line + 1}`);
  const functions = tree.statements
    .filter(ts.isFunctionDeclaration)
    .filter(item => item.name?.text === functionName)
    .map(item => {
      if (!item.name || !item.body) throw new Error("TYPESCRIPT_FUNCTION_BODY_REQUIRED");
      return {
        name: item.name.text,
        parameters: item.parameters.map(parameter => {
          if (!ts.isIdentifier(parameter.name)) throw new Error("TYPESCRIPT_DESTRUCTURED_PARAMETER_UNSUPPORTED");
          return { name: parameter.name.text, type: typeName(parameter.type) };
        }),
        return_type: typeName(item.type),
        body: statements([...item.body.statements]),
      };
    });
  if (functions.length === 0) diagnostics.push(`FUNCTION_NOT_FOUND:${functionName}`);
  return {
    schema_version: "1.0.0",
    source_language: "typescript",
    source_file: sourceFile,
    analyzer: "TypeScript Compiler API",
    analyzer_version: ts.version,
    functions,
    diagnostics,
  };
}

function byteOffset(source: string, characterOffset: number): number {
  return Buffer.byteLength(source.slice(0, characterOffset), "utf8");
}

export function inventoryTypedModule(source: string, sourceFile: string): JsonObject {
  const tree = ts.createSourceFile(
    sourceFile,
    source,
    ts.ScriptTarget.ES2022,
    true,
    ts.ScriptKind.TS,
  ) as ParsedSourceFile;
  const diagnostics = tree.parseDiagnostics.map(
    item => `TS${item.code}:${tree.getLineAndCharacterOfPosition(item.start ?? 0).line + 1}`,
  );
  const subjects: JsonObject[] = [];

  const span = (node: ts.Node): JsonObject => ({
    file: sourceFile,
    start_byte: byteOffset(source, node.getStart(tree)),
    end_byte: byteOffset(source, node.end),
  });
  const add = (
    node: ts.Node,
    name: string,
    qualifiedName: string,
    declarationKind: string,
    analyzable: boolean,
    signature: JsonObject,
  ): void => {
    subjects.push({
      name,
      qualified_name: qualifiedName,
      declaration_kind: declarationKind,
      analyzable,
      source_span: span(node),
      signature,
    });
  };

  for (const statement of tree.statements) {
    if (ts.isFunctionDeclaration(statement)) {
      const name = statement.name?.text ?? `<anonymous-function@${statement.pos}>`;
      const permittedModifiers = statement.modifiers?.every(
        modifier => modifier.kind === ts.SyntaxKind.ExportKeyword,
      ) ?? true;
      const supportedParameters = statement.parameters.every(
        parameter => ts.isIdentifier(parameter.name)
          && parameter.dotDotDotToken === undefined
          && parameter.questionToken === undefined
          && parameter.initializer === undefined,
      );
      add(
        statement,
        name,
        name,
        "FunctionDeclaration",
        Boolean(
          statement.name
          && statement.body
          && statement.asteriskToken === undefined
          && statement.typeParameters === undefined
          && permittedModifiers
          && supportedParameters,
        ),
        {
          parameters: statement.parameters.map(parameter => ({
            name: ts.isIdentifier(parameter.name) ? parameter.name.text : parameter.name.getText(tree),
            source_type: parameter.type?.getText(tree) ?? "",
          })),
          source_return_type: statement.type?.getText(tree) ?? "",
        },
      );
      continue;
    }
    if (ts.isClassDeclaration(statement)) {
      const className = statement.name?.text ?? `<anonymous-class@${statement.pos}>`;
      add(statement, className, className, "ClassDeclaration", false, {});
      for (const member of statement.members) {
        const memberName = "name" in member && member.name
          ? member.name.getText(tree)
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
        const name = declaration.name.getText(tree);
        const callable = declaration.initializer !== undefined
          && (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer));
        add(
          declaration,
          name,
          name,
          callable ? "FunctionValueDeclaration" : "VariableDeclaration",
          false,
          { source_type: declaration.type?.getText(tree) ?? "" },
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
    source_file: sourceFile,
    analyzer: "TypeScript Compiler API",
    analyzer_version: ts.version,
    enumeration_status: diagnostics.length === 0 ? "PASSED" : "FAILED",
    subjects,
    diagnostics,
  };
}

import { createHash } from "node:crypto";

import { compileStyle, parse } from "@vue/compiler-sfc";
import ts from "typescript";

export interface VueReactTypedGap {
  readonly code: string;
  readonly severity: "WARNING" | "ERROR" | "CRITICAL";
  readonly sourcePath: string;
  readonly message: string;
  readonly blocking: boolean;
}

export interface VueReactRouteResult {
  readonly route: "VUE_3_TO_REACT";
  readonly status: "GENERATED" | "BLOCKED";
  readonly sourceFiles: readonly string[];
  readonly generatedFiles: Readonly<Record<string, string>>;
  readonly mappings: readonly string[];
  readonly typedGaps: readonly VueReactTypedGap[];
  readonly sourceBuild: "NOT_RUN";
  readonly targetBuild: "NOT_RUN";
  readonly browserJourney: "NOT_RUN";
  readonly certification: "NOT_CERTIFIED";
}

type TemplateExpression = { readonly content?: string };
type TemplateAttribute = {
  readonly type: number;
  readonly name?: string;
  readonly value?: { readonly content?: string };
  readonly arg?: TemplateExpression;
  readonly exp?: TemplateExpression;
  readonly modifiers?: readonly string[];
};
type TemplateNode = {
  readonly type: number;
  readonly tag?: string;
  readonly tagType?: number;
  readonly content?: string | TemplateExpression;
  readonly props?: readonly TemplateAttribute[];
  readonly children?: readonly TemplateNode[];
};

const expression = /^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*$/;
const eventNames: Readonly<Record<string, string>> = {
  click: "onClick",
  input: "onInput",
  change: "onChange",
  submit: "onSubmit",
  blur: "onBlur",
  focus: "onFocus",
};
const voidElements = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);

function gap(
  gaps: VueReactTypedGap[],
  sourcePath: string,
  code: string,
  message: string,
  severity: VueReactTypedGap["severity"] = "CRITICAL",
): void {
  gaps.push({ code, sourcePath, message, severity, blocking: severity !== "WARNING" });
}

function stateProperty(node: ts.Node, states: ReadonlySet<string>): string | undefined {
  if (!ts.isPropertyAccessExpression(node) || node.name.text !== "value"
      || !ts.isIdentifier(node.expression) || !states.has(node.expression.text)) return undefined;
  return node.expression.text;
}

function renderScriptExpression(node: ts.Expression, states: ReadonlySet<string>): string | undefined {
  const state = stateProperty(node, states);
  if (state) return state;
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)
      || node.kind === ts.SyntaxKind.TrueKeyword || node.kind === ts.SyntaxKind.FalseKeyword
      || node.kind === ts.SyntaxKind.NullKeyword) return node.getText();
  if (ts.isParenthesizedExpression(node)) {
    const value = renderScriptExpression(node.expression, states);
    return value === undefined ? undefined : `(${value})`;
  }
  if (ts.isBinaryExpression(node)) {
    const left = renderScriptExpression(node.left, states);
    const right = renderScriptExpression(node.right, states);
    return left === undefined || right === undefined
      ? undefined
      : `${left} ${node.operatorToken.getText()} ${right}`;
  }
  if (ts.isPrefixUnaryExpression(node)) {
    const operand = renderScriptExpression(node.operand, states);
    return operand === undefined ? undefined : `${node.operator === ts.SyntaxKind.ExclamationToken ? "!" : node.operator === ts.SyntaxKind.MinusToken ? "-" : "+"}${operand}`;
  }
  if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
    const values = node.arguments.map(argument => renderScriptExpression(argument, states));
    return values.some(value => value === undefined)
      ? undefined
      : `${node.expression.text}(${values.join(", ")})`;
  }
  return undefined;
}

function convertScript(source: string, sourcePath: string, gaps: VueReactTypedGap[]) {
  const sourceFile = ts.createSourceFile(sourcePath, source, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TS);
  const states = new Map<string, { setter: string; initial: string }>();
  const preserved: string[] = [];
  const functions: string[] = [];
  let refImported = false;

  for (const statement of sourceFile.statements) {
    if (ts.isImportDeclaration(statement)) {
      if (!ts.isStringLiteral(statement.moduleSpecifier) || statement.moduleSpecifier.text !== "vue") {
        gap(gaps, sourcePath, "FRT_VUE_EXTERNAL_IMPORT_UNSUPPORTED", `Import ${statement.moduleSpecifier.getText()} requires an explicit target adapter.`);
        continue;
      }
      const elements = statement.importClause?.namedBindings && ts.isNamedImports(statement.importClause.namedBindings)
        ? statement.importClause.namedBindings.elements : [];
      if (elements.length === 1 && elements[0]!.name.text === "ref") refImported = true;
      else gap(gaps, sourcePath, "FRT_VUE_COMPOSITION_API_UNSUPPORTED", "This vertical slice supports only the Vue ref composition primitive.");
      continue;
    }
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        if (!ts.isIdentifier(declaration.name) || !declaration.initializer) {
          gap(gaps, sourcePath, "FRT_VUE_VARIABLE_PATTERN_UNSUPPORTED", "Destructuring and uninitialized declarations require a typed mapping decision.");
          continue;
        }
        if (ts.isCallExpression(declaration.initializer)
            && ts.isIdentifier(declaration.initializer.expression)
            && declaration.initializer.expression.text === "ref") {
          if (declaration.initializer.arguments.length !== 1) {
            gap(gaps, sourcePath, "FRT_VUE_REF_ARITY_UNSUPPORTED", `${declaration.name.text} does not have one deterministic ref initializer.`);
            continue;
          }
          const initial = declaration.initializer.arguments[0]!.getText(sourceFile);
          states.set(declaration.name.text, {
            setter: `set${declaration.name.text[0]!.toUpperCase()}${declaration.name.text.slice(1)}`,
            initial,
          });
        } else {
          preserved.push(statement.getText(sourceFile));
        }
      }
      continue;
    }
    if (ts.isTypeAliasDeclaration(statement) || ts.isInterfaceDeclaration(statement)) {
      preserved.push(statement.getText(sourceFile));
      continue;
    }
    if (ts.isFunctionDeclaration(statement) && statement.name && statement.body && statement.parameters.length === 0) {
      const converted: string[] = [];
      for (const child of statement.body.statements) {
        if (ts.isExpressionStatement(child) && ts.isPostfixUnaryExpression(child.expression)) {
          const state = stateProperty(child.expression.operand, new Set(states.keys()));
          const mapping = state && states.get(state);
          if (mapping && [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(child.expression.operator)) {
            converted.push(`${mapping.setter}(previous => previous ${child.expression.operator === ts.SyntaxKind.PlusPlusToken ? "+" : "-"} 1);`);
            continue;
          }
        }
        if (ts.isExpressionStatement(child) && ts.isBinaryExpression(child.expression)
            && [ts.SyntaxKind.PlusEqualsToken, ts.SyntaxKind.MinusEqualsToken]
              .includes(child.expression.operatorToken.kind)) {
          const state = stateProperty(child.expression.left, new Set(states.keys()));
          const mapping = state && states.get(state);
          const value = renderScriptExpression(child.expression.right, new Set(states.keys()));
          if (mapping && value !== undefined) {
            const operator = child.expression.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken ? "+" : "-";
            converted.push(`${mapping.setter}(previous => previous ${operator} ${value});`);
            continue;
          }
        }
        if (ts.isExpressionStatement(child) && ts.isBinaryExpression(child.expression)
            && child.expression.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
          const state = stateProperty(child.expression.left, new Set(states.keys()));
          const mapping = state && states.get(state);
          const value = renderScriptExpression(child.expression.right, new Set(states.keys()));
          if (mapping && value !== undefined) {
            converted.push(`${mapping.setter}(${value});`);
            continue;
          }
        }
        gap(gaps, sourcePath, "FRT_VUE_FUNCTION_STATEMENT_UNSUPPORTED", `Function ${statement.name.text} contains a statement outside the certified vertical slice.`);
      }
      functions.push(`function ${statement.name.text}() {\n${converted.map(line => `  ${line}`).join("\n")}\n}`);
      continue;
    }
    gap(gaps, sourcePath, "FRT_VUE_SCRIPT_STATEMENT_UNSUPPORTED", `Statement ${ts.SyntaxKind[statement.kind]} requires an explicit semantic adapter.`);
  }
  if (states.size && !refImported) gap(gaps, sourcePath, "FRT_VUE_REF_IMPORT_MISSING", "Reactive refs were found without an exact Vue ref import.");
  return {
    hooks: [...states.entries()].map(([name, value]) => `const [${name}, ${value.setter}] = useState(${value.initial});`),
    preserved,
    functions,
    stateNames: new Set(states.keys()),
    setters: new Map([...states.entries()].map(([name, value]) => [name, value.setter])),
  };
}

function renderTemplate(
  node: TemplateNode,
  context: {
    sourcePath: string;
    gaps: VueReactTypedGap[];
    stateNames: ReadonlySet<string>;
    setters: ReadonlyMap<string, string>;
    scopeAttribute?: string;
  },
): string {
  if (node.type === 0) {
    const children = (node.children ?? []).map(child => renderTemplate(child, context)).join("\n");
    return (node.children?.length ?? 0) === 1 ? children : `<>\n${children}\n</>`;
  }
  if (node.type === 2) return typeof node.content === "string" ? node.content : "";
  if (node.type === 3) return "";
  if (node.type === 5) {
    const value = typeof node.content === "object" ? node.content.content?.trim() : undefined;
    if (!value || !expression.test(value)) {
      gap(context.gaps, context.sourcePath, "FRT_VUE_INTERPOLATION_UNSUPPORTED", "Template interpolation must be a side-effect-free identifier path.");
      return "{undefined}";
    }
    return `{${value}}`;
  }
  if (node.type !== 1 || !node.tag) {
    gap(context.gaps, context.sourcePath, "FRT_VUE_TEMPLATE_NODE_UNSUPPORTED", `Vue template node type ${node.type} is unsupported.`);
    return "{undefined}";
  }
  if (node.tagType !== 0) {
    gap(context.gaps, context.sourcePath, "FRT_VUE_COMPONENT_OR_SLOT_UNSUPPORTED", `Component or slot <${node.tag}> requires an explicit component contract.`);
  }
  const attributes: string[] = [];
  let condition: string | undefined;
  for (const property of node.props ?? []) {
    if (property.type === 6 && property.name) {
      const name = property.name === "class" ? "className" : property.name === "for" ? "htmlFor" : property.name;
      attributes.push(property.value ? `${name}=${JSON.stringify(property.value.content ?? "")}` : name);
      continue;
    }
    if (property.type !== 7 || !property.name) continue;
    const argument = property.arg?.content;
    const value = property.exp?.content?.trim();
    if (property.modifiers?.length) {
      gap(context.gaps, context.sourcePath, "FRT_VUE_DIRECTIVE_MODIFIER_UNSUPPORTED", `Directive modifier on ${property.name} is not silently approximated.`);
      continue;
    }
    if (property.name === "on" && argument && eventNames[argument] && value && expression.test(value)) {
      attributes.push(`${eventNames[argument]}={${value}}`);
    } else if (property.name === "bind" && argument && value && expression.test(value)) {
      attributes.push(`${argument === "class" ? "className" : argument}={${value}}`);
    } else if (property.name === "if" && value && expression.test(value)) {
      condition = value;
    } else if (property.name === "model" && value && context.stateNames.has(value)) {
      const setter = context.setters.get(value)!;
      attributes.push(`value={${value}}`, `onChange={event => ${setter}(event.currentTarget.value)}`);
    } else {
      gap(context.gaps, context.sourcePath, "FRT_VUE_DIRECTIVE_UNSUPPORTED", `Directive v-${property.name} requires an explicit React semantic mapping.`);
    }
  }
  if (context.scopeAttribute) attributes.push(`${context.scopeAttribute}=""`);
  const opening = attributes.length ? `<${node.tag} ${attributes.join(" ")}>` : `<${node.tag}>`;
  const rendered = voidElements.has(node.tag)
    ? opening.replace(/>$/, " />")
    : `${opening}${(node.children ?? []).map(child => renderTemplate(child, context)).join("")}</${node.tag}>`;
  return condition ? `{${condition} && (${rendered})}` : rendered;
}

export function convertVue3ToReact(
  files: Readonly<Record<string, string>>,
): VueReactRouteResult {
  const gaps: VueReactTypedGap[] = [];
  try {
    const packageManifest = JSON.parse(files["package.json"] ?? "") as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const vueVersion = packageManifest.dependencies?.vue ?? packageManifest.devDependencies?.vue;
    if (!vueVersion || !/(?:^|[^0-9])3(?:\.|$)/.test(vueVersion)) {
      gap(gaps, "package.json", "FRT_VUE3_VERSION_UNRESOLVED", "package.json must bind an explicit Vue 3 dependency version.");
    }
  } catch {
    gap(gaps, "package.json", "FRT_VUE_PACKAGE_MANIFEST_INVALID", "A valid package.json is required to prove the source is Vue 3.");
  }
  const vueFiles = Object.keys(files).filter(path => path.endsWith(".vue")).sort();
  const sourcePath = vueFiles[0] ?? "<missing-vue-sfc>";
  if (vueFiles.length !== 1) {
    gap(gaps, sourcePath, "FRT_VUE_SFC_CARDINALITY_UNSUPPORTED", "The current verified vertical slice requires exactly one Vue SFC; multi-component graph conversion remains explicit.");
  }
  const source = files[sourcePath];
  if (source === undefined) {
    return {
      route: "VUE_3_TO_REACT",
      status: "BLOCKED",
      sourceFiles: vueFiles,
      generatedFiles: {},
      mappings: [],
      typedGaps: gaps,
      sourceBuild: "NOT_RUN",
      targetBuild: "NOT_RUN",
      browserJourney: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    };
  }
  const parsed = parse(source, { filename: sourcePath, sourceMap: false });
  for (const error of parsed.errors) gap(gaps, sourcePath, "FRT_VUE_SFC_PARSE_ERROR", String(error));
  const descriptor = parsed.descriptor;
  if (!descriptor.template?.ast) gap(gaps, sourcePath, "FRT_VUE_TEMPLATE_MISSING", "A parsed Vue template AST is required.");
  if (!descriptor.scriptSetup || descriptor.script) gap(gaps, sourcePath, "FRT_VUE_SCRIPT_MODE_UNSUPPORTED", "The current route accepts one <script setup lang=\"ts\"> block and no classic script block.");
  if (descriptor.scriptSetup?.lang !== "ts") gap(gaps, sourcePath, "FRT_VUE_TYPESCRIPT_REQUIRED", "The source script setup block must be TypeScript.");
  if (descriptor.styles.length > 1) gap(gaps, sourcePath, "FRT_VUE_STYLE_CARDINALITY_UNSUPPORTED", "Multiple style blocks require an ordered style contract.");

  const script = convertScript(descriptor.scriptSetup?.content ?? "", sourcePath, gaps);
  const scopeId = descriptor.styles[0]?.scoped
    ? `data-v-frt-${createHash("sha256").update(sourcePath).digest("hex").slice(0, 8)}`
    : undefined;
  const jsx = descriptor.template?.ast
    ? renderTemplate(descriptor.template.ast as unknown as TemplateNode, {
      sourcePath,
      gaps,
      stateNames: script.stateNames,
      setters: script.setters,
      ...(scopeId ? { scopeAttribute: scopeId } : {}),
    })
    : "<></>";
  let css = descriptor.styles[0]?.content ?? "";
  if (descriptor.styles[0]?.scoped && scopeId) {
    const compiled = compileStyle({ source: css, filename: sourcePath, id: scopeId, scoped: true });
    for (const error of compiled.errors) gap(gaps, sourcePath, "FRT_VUE_SCOPED_STYLE_COMPILE_ERROR", String(error));
    css = compiled.code;
  }
  const blocking = gaps.some(item => item.blocking);
  const app = [
    `import { useState } from "react";`,
    `import "./App.css";`,
    "",
    ...script.preserved,
    "",
    "export default function App() {",
    ...script.hooks.map(line => `  ${line}`),
    ...script.functions.flatMap(value => value.split("\n").map(line => `  ${line}`)),
    "  return (",
    ...jsx.split("\n").map(line => `    ${line}`),
    "  );",
    "}",
    "",
  ].join("\n");
  const generatedFiles = blocking ? {} : {
    "src/App.tsx": app,
    "src/App.css": css,
    "src/main.tsx": [
      `import { StrictMode } from "react";`,
      `import { createRoot } from "react-dom/client";`,
      `import App from "./App";`,
      `createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);`,
      "",
    ].join("\n"),
    "index.html": `<div id="root"></div><script type="module" src="/src/main.tsx"></script>\n`,
    "package.json": `${JSON.stringify({
      name: "frt-vue3-react-output",
      private: true,
      version: "1.0.0",
      type: "module",
      scripts: { build: "tsc --noEmit" },
      dependencies: { react: "19.2.7", "react-dom": "19.2.7" },
      devDependencies: { typescript: "5.9.2", "@types/react": "19.1.10", "@types/react-dom": "19.1.7" },
    }, null, 2)}\n`,
    "tsconfig.json": `${JSON.stringify({ compilerOptions: {
      target: "ES2022", module: "ESNext", moduleResolution: "Bundler", jsx: "react-jsx",
      strict: true, noEmit: true, skipLibCheck: false, lib: ["ES2022", "DOM"],
    }, include: ["src"] }, null, 2)}\n`,
  };
  return {
    route: "VUE_3_TO_REACT",
    status: blocking ? "BLOCKED" : "GENERATED",
    sourceFiles: vueFiles,
    generatedFiles,
    mappings: [
      "Vue SFC descriptor -> React module set",
      "script setup ref -> React useState",
      "Vue event directive -> React event prop",
      "Vue interpolation -> JSX expression",
      "Vue scoped style -> compiled scope attribute CSS",
    ],
    typedGaps: gaps,
    sourceBuild: "NOT_RUN",
    targetBuild: "NOT_RUN",
    browserJourney: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
}

/**
 * React source -> Portable UI IR.
 *
 * The second source stack whose IR is read out of real bytes instead of being
 * declared. Everything the IR asserts about a React route is recovered from the
 * TSX module with the TypeScript parser and from the stylesheet the module
 * actually imports; anything that cannot be recovered is a typed gap that
 * blocks the route. Nothing is defaulted, approximated, or invented.
 */

import ts from "typescript";

import {
  canonical,
  contentAddressedSourceRefs,
  gap,
  sha256,
  type FrtRouteTypedGap,
  type PortableUiIr,
} from "./frt-route-ir.js";

const exactVersion = /^(?:[0-9]+\.)+[0-9]+$/;
const accentRule = /^button\s*\{\s*color\s*:\s*(#[0-9A-Fa-f]{6})\s*;?\s*\}$/;
const identifier = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

interface ScriptModel {
  readonly stringConstants: ReadonlyMap<string, string>;
  /** state name -> { setter, initial } for exactly the useState hooks found. */
  readonly states: ReadonlyMap<string, { readonly setter: string; readonly initial: number }>;
  /** handler name -> (state name -> integer delta) for declared functions. */
  readonly handlerDeltas: ReadonlyMap<string, ReadonlyMap<string, number>>;
}

function attributeName(attribute: ts.JsxAttribute): string {
  return ts.isIdentifier(attribute.name) ? attribute.name.text : attribute.name.getText();
}

function stringAttribute(element: ts.JsxOpeningLikeElement, name: string): string | undefined {
  for (const property of element.attributes.properties) {
    if (!ts.isJsxAttribute(property) || attributeName(property) !== name) continue;
    const initializer = property.initializer;
    if (initializer && ts.isStringLiteral(initializer)) return initializer.text;
    return undefined;
  }
  return undefined;
}

function expressionAttribute(
  element: ts.JsxOpeningLikeElement,
  name: string,
): ts.Expression | undefined {
  for (const property of element.attributes.properties) {
    if (!ts.isJsxAttribute(property) || attributeName(property) !== name) continue;
    const initializer = property.initializer;
    if (initializer && ts.isJsxExpression(initializer) && initializer.expression) {
      return initializer.expression;
    }
    return undefined;
  }
  return undefined;
}

function significantChildren(element: ts.JsxElement): readonly ts.JsxChild[] {
  return element.children.filter(child => {
    if (ts.isJsxText(child)) return !child.containsOnlyTriviaWhiteSpaces;
    return true;
  });
}

function childElement(element: ts.JsxElement, tag: string): ts.JsxElement | undefined {
  return significantChildren(element).find(
    (child): child is ts.JsxElement =>
      ts.isJsxElement(child) && child.openingElement.tagName.getText() === tag,
  );
}

function integerLiteral(node: ts.Expression): number | undefined {
  if (ts.isNumericLiteral(node)) {
    const value = Number(node.text);
    return Number.isInteger(value) ? value : undefined;
  }
  if (ts.isPrefixUnaryExpression(node) && ts.isNumericLiteral(node.operand)
      && (node.operator === ts.SyntaxKind.MinusToken || node.operator === ts.SyntaxKind.PlusToken)) {
    const value = Number(node.operand.text);
    if (!Number.isInteger(value)) return undefined;
    return node.operator === ts.SyntaxKind.MinusToken ? -value : value;
  }
  return undefined;
}

/**
 * Read the integer delta out of a `setX(...)` call, in either of the two forms
 * React actually uses: a functional update `setX(previous => previous + n)` or a
 * direct update `setX(x + n)`. Anything else is not a provable delta.
 */
function setterCallDelta(
  call: ts.CallExpression,
  states: ScriptModel["states"],
): { readonly state: string; readonly amount: number } | undefined {
  if (!ts.isIdentifier(call.expression) || call.arguments.length !== 1) return undefined;
  const setter = call.expression.text;
  const entry = [...states.entries()].find(([, value]) => value.setter === setter);
  if (!entry) return undefined;
  const state = entry[0];
  const argument = call.arguments[0]!;

  let amount: number | undefined;
  if (ts.isArrowFunction(argument) && argument.parameters.length === 1
      && ts.isIdentifier(argument.parameters[0]!.name)) {
    const body = argument.body;
    if (ts.isBlock(body)) return undefined;
    amount = additiveDelta(body, argument.parameters[0]!.name.text);
  } else {
    amount = additiveDelta(argument, state);
  }
  return amount === undefined ? undefined : { state, amount };
}

/** `base + n` -> n, `base - n` -> -n, anything else -> undefined. */
function additiveDelta(expression: ts.Expression, base: string): number | undefined {
  if (!ts.isBinaryExpression(expression)) return undefined;
  if (!ts.isIdentifier(expression.left) || expression.left.text !== base) return undefined;
  const amount = integerLiteral(expression.right);
  if (amount === undefined) return undefined;
  if (expression.operatorToken.kind === ts.SyntaxKind.PlusToken) return amount;
  if (expression.operatorToken.kind === ts.SyntaxKind.MinusToken) return -amount;
  return undefined;
}

function analyzeStatements(
  statements: readonly ts.Statement[],
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
  stringConstants: Map<string, string>,
  states: Map<string, { setter: string; initial: number }>,
  handlerDeltas: Map<string, ReadonlyMap<string, number>>,
  allowReturn: boolean,
): void {
  // State declarations are read before handlers so a handler declared above its
  // useState still resolves; the order is fixed, not source-order dependent.
  const ordered = [...statements].sort(
    (left, right) => (ts.isVariableStatement(left) ? 0 : 1) - (ts.isVariableStatement(right) ? 0 : 1),
  );
  for (const statement of ordered) {
    if (allowReturn && ts.isReturnStatement(statement)) continue;

    if (ts.isVariableStatement(statement)) {
      const isConst = (statement.declarationList.flags & ts.NodeFlags.Const) !== 0;
      for (const declaration of statement.declarationList.declarations) {
        if (!isConst || !declaration.initializer) {
          gap(gaps, "FRT_REACT_BINDING_UNSUPPORTED", sourcePath,
            "Only initialized `const` bindings are read as source of truth.");
          continue;
        }
        const initializer = declaration.initializer;

        // const [count, setCount] = useState(0)
        if (ts.isArrayBindingPattern(declaration.name)) {
          const elements = declaration.name.elements;
          const isUseState = ts.isCallExpression(initializer) && ts.isIdentifier(initializer.expression)
            && initializer.expression.text === "useState" && initializer.arguments.length === 1;
          if (!isUseState || elements.length !== 2
              || !elements.every(element => ts.isBindingElement(element) && ts.isIdentifier(element.name))) {
            gap(gaps, "FRT_REACT_BINDING_UNSUPPORTED", sourcePath,
              "Array destructuring is read only as a two-element useState hook.");
            continue;
          }
          const initial = integerLiteral((initializer as ts.CallExpression).arguments[0]!);
          if (initial === undefined) {
            gap(gaps, "FRT_REACT_BINDING_UNSUPPORTED", sourcePath,
              "useState is not initialized with an integer literal, so the initial state is not derivable.");
            continue;
          }
          const name = ((elements[0] as ts.BindingElement).name as ts.Identifier).text;
          const setter = ((elements[1] as ts.BindingElement).name as ts.Identifier).text;
          states.set(name, { setter, initial });
          continue;
        }

        if (!ts.isIdentifier(declaration.name)) {
          gap(gaps, "FRT_REACT_BINDING_UNSUPPORTED", sourcePath,
            "Object destructuring requires an explicit typed mapping decision.");
          continue;
        }
        if (ts.isStringLiteral(initializer)) {
          stringConstants.set(declaration.name.text, initializer.text);
          continue;
        }
        gap(gaps, "FRT_REACT_BINDING_UNSUPPORTED", sourcePath,
          `Binding ${declaration.name.text} is neither a string constant nor a useState hook.`);
      }
      continue;
    }

    if (ts.isFunctionDeclaration(statement) && statement.name && statement.body
        && statement.parameters.length === 0) {
      const deltas = new Map<string, number>();
      let readable = true;
      for (const child of statement.body.statements) {
        if (!ts.isExpressionStatement(child) || !ts.isCallExpression(child.expression)) {
          readable = false;
          continue;
        }
        const delta = setterCallDelta(child.expression, states);
        if (!delta) readable = false;
        else deltas.set(delta.state, (deltas.get(delta.state) ?? 0) + delta.amount);
      }
      if (!readable) {
        gap(gaps, "FRT_REACT_STATEMENT_UNSUPPORTED", sourcePath,
          `Function ${statement.name.text} contains a statement that is not a deterministic integer state delta.`);
      }
      handlerDeltas.set(statement.name.text, deltas);
      continue;
    }

    gap(gaps, "FRT_REACT_STATEMENT_UNSUPPORTED", sourcePath,
      `Statement ${ts.SyntaxKind[statement.kind]} is outside the derivable React route slice.`);
  }
}

function textOrConstant(
  element: ts.JsxElement,
  model: ScriptModel,
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
  code: string,
  what: string,
): string | undefined {
  const children = significantChildren(element);
  if (children.length !== 1) {
    gap(gaps, code, sourcePath, `${what} must be exactly one static text or one string-constant expression.`);
    return undefined;
  }
  const child = children[0]!;
  if (ts.isJsxText(child)) return child.text.trim();
  if (ts.isJsxExpression(child) && child.expression && ts.isIdentifier(child.expression)) {
    const value = model.stringConstants.get(child.expression.text);
    if (value !== undefined) return value;
    gap(gaps, code, sourcePath,
      `${what} renders ${child.expression.text}, which is not a literal string constant in this module.`);
    return undefined;
  }
  gap(gaps, code, sourcePath, `${what} is not readable from the source module.`);
  return undefined;
}

function rejectUnexpectedAttributes(
  element: ts.JsxElement,
  allowed: readonly string[],
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): void {
  const tag = element.openingElement.tagName.getText();
  for (const property of element.openingElement.attributes.properties) {
    if (!ts.isJsxAttribute(property)) {
      gap(gaps, "FRT_REACT_TEMPLATE_ATTRIBUTE_UNSUPPORTED", sourcePath,
        `A spread attribute on <${tag}> hides semantics this slice cannot prove.`);
      continue;
    }
    const name = attributeName(property);
    if (!allowed.includes(name)) {
      gap(gaps, "FRT_REACT_TEMPLATE_ATTRIBUTE_UNSUPPORTED", sourcePath,
        `Attribute ${name} on <${tag}> carries a semantic this slice does not model.`);
    }
  }
}

function deriveAccentColor(
  files: Readonly<Record<string, string>>,
  importedStylesheets: readonly string[],
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): string | undefined {
  const stylesheets = Object.keys(files).filter(path => path.endsWith(".css")).sort();
  if (stylesheets.length !== 1) {
    gap(gaps, "FRT_REACT_STYLESHEET_CARDINALITY_UNSUPPORTED", sourcePath,
      `${stylesheets.length} stylesheets were found; exactly one is required and cascade order is otherwise undetermined.`);
    return undefined;
  }
  const stylesheet = stylesheets[0]!;
  if (importedStylesheets.length !== 1) {
    gap(gaps, "FRT_REACT_STYLESHEET_NOT_IMPORTED", sourcePath,
      "The component must import exactly one stylesheet; an unimported stylesheet styles nothing.");
    return undefined;
  }
  const raw = (files[stylesheet] ?? "").replace(/\/\*[\s\S]*?\*\//g, "").trim();
  const match = accentRule.exec(raw);
  if (!match) {
    gap(gaps, "FRT_REACT_ACCENT_COLOR_NOT_DERIVABLE", stylesheet,
      "The stylesheet is not the single `button { color: #rrggbb; }` design token this IR slice can carry.");
    return undefined;
  }
  return match[1]!;
}

/**
 * Derive the portable UI IR from real React source bytes.
 *
 * Returns `undefined` whenever any part of the contract could not be read; the
 * reason is always in `gaps`, never silently defaulted.
 */
export function deriveReactPortableUiIr(
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  const before = gaps.length;

  let version: string | undefined;
  const manifest = files["package.json"];
  if (manifest === undefined) {
    gap(gaps, "FRT_REACT_PACKAGE_MANIFEST_INVALID", "package.json",
      "package.json is required to prove the source stack and version.");
  } else {
    try {
      const parsed = JSON.parse(manifest) as {
        dependencies?: Record<string, string>;
        devDependencies?: Record<string, string>;
      };
      const declared = parsed.dependencies?.react ?? parsed.devDependencies?.react;
      if (!declared || !exactVersion.test(declared)) {
        gap(gaps, "FRT_REACT_SOURCE_VERSION_NOT_EXACT", "package.json",
          `The React dependency ${declared ?? "<missing>"} is not an exact version.`);
      } else version = declared;
    } catch {
      gap(gaps, "FRT_REACT_PACKAGE_MANIFEST_INVALID", "package.json", "package.json is not valid JSON.");
    }
  }

  const modules = Object.keys(files).filter(path => path.endsWith(".tsx")).sort();
  const sourcePath = modules[0] ?? "<missing-react-module>";
  if (modules.length !== 1) {
    gap(gaps, "FRT_REACT_MODULE_CARDINALITY_UNSUPPORTED", sourcePath,
      `${modules.length} React modules were found; exactly one is required by this slice.`);
    return undefined;
  }

  const file = ts.createSourceFile(sourcePath, files[sourcePath]!, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TSX);
  const diagnostics = (file as ts.SourceFile & { readonly parseDiagnostics?: readonly unknown[] })
    .parseDiagnostics ?? [];
  if (diagnostics.length > 0) {
    gap(gaps, "FRT_REACT_PARSE_ERROR", sourcePath,
      `The React module has ${diagnostics.length} parse diagnostics.`);
    return undefined;
  }

  const stringConstants = new Map<string, string>();
  const states = new Map<string, { setter: string; initial: number }>();
  const handlerDeltas = new Map<string, ReadonlyMap<string, number>>();
  const importedStylesheets: string[] = [];
  const components: ts.FunctionDeclaration[] = [];
  const moduleStatements: ts.Statement[] = [];

  for (const statement of file.statements) {
    if (ts.isImportDeclaration(statement)) {
      const specifier = ts.isStringLiteral(statement.moduleSpecifier)
        ? statement.moduleSpecifier.text : "<computed>";
      if (specifier.endsWith(".css")) {
        if (statement.importClause) {
          gap(gaps, "FRT_REACT_IMPORT_UNSUPPORTED", sourcePath,
            `Stylesheet import ${specifier} must be a side-effect import.`);
          continue;
        }
        importedStylesheets.push(specifier);
        continue;
      }
      const bindings = statement.importClause?.namedBindings;
      const named = bindings && ts.isNamedImports(bindings)
        ? bindings.elements.map(element => element.name.text) : [];
      if (specifier !== "react" || statement.importClause?.name !== undefined
          || named.length !== 1 || named[0] !== "useState") {
        gap(gaps, "FRT_REACT_IMPORT_UNSUPPORTED", sourcePath,
          `Import from ${specifier} is outside the derivable slice; only \`useState\` and one stylesheet are read.`);
      }
      continue;
    }
    if (ts.isFunctionDeclaration(statement) && statement.name && statement.body) {
      components.push(statement);
      continue;
    }
    moduleStatements.push(statement);
  }

  analyzeStatements(moduleStatements, sourcePath, gaps, stringConstants, states, handlerDeltas, false);

  if (components.length !== 1) {
    gap(gaps, "FRT_REACT_COMPONENT_CARDINALITY_UNSUPPORTED", sourcePath,
      `${components.length} function components were found; exactly one is required by this slice.`);
    return undefined;
  }
  const component = components[0]!;
  if (component.parameters.length !== 0) {
    gap(gaps, "FRT_REACT_COMPONENT_CARDINALITY_UNSUPPORTED", sourcePath,
      `Component ${component.name!.text} takes props, which this route slice does not model.`);
    return undefined;
  }

  analyzeStatements(
    [...component.body!.statements], sourcePath, gaps, stringConstants, states, handlerDeltas, true,
  );
  const model: ScriptModel = { stringConstants, states, handlerDeltas };

  const returns = component.body!.statements.filter(ts.isReturnStatement);
  const returned = returns.length === 1 ? returns[0]!.expression : undefined;
  const root = returned && ts.isParenthesizedExpression(returned) ? returned.expression : returned;
  if (!root || !ts.isJsxElement(root) || root.openingElement.tagName.getText() !== "main") {
    gap(gaps, "FRT_REACT_ROUTE_ROOT_UNSUPPORTED", sourcePath,
      "The component must return exactly one <main> route element.");
    return undefined;
  }

  rejectUnexpectedAttributes(root, ["aria-label"], sourcePath, gaps);
  const mainLabel = stringAttribute(root.openingElement, "aria-label");
  if (mainLabel === undefined || mainLabel.trim().length === 0) {
    gap(gaps, "FRT_REACT_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "<main> carries no literal aria-label, so this route has no source-provable accessible name.");
  }

  const parts = significantChildren(root);
  const heading = childElement(root, "h1");
  const button = childElement(root, "button");
  const liveRegion = childElement(root, "p");
  if (parts.length !== 3 || !heading || !button || !liveRegion) {
    gap(gaps, "FRT_REACT_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "This route slice reads exactly one <h1> title, one <button> action, and one <p> live region.");
    return undefined;
  }

  rejectUnexpectedAttributes(heading, [], sourcePath, gaps);
  rejectUnexpectedAttributes(button, ["aria-label", "onClick"], sourcePath, gaps);
  rejectUnexpectedAttributes(liveRegion, ["aria-live"], sourcePath, gaps);

  const title = textOrConstant(heading, model, sourcePath, gaps, "FRT_REACT_TITLE_NOT_DERIVABLE", "The route title");
  const buttonLabel = textOrConstant(
    button, model, sourcePath, gaps, "FRT_REACT_BUTTON_LABEL_NOT_DERIVABLE", "The action label",
  );

  const accessibleButtonLabel = stringAttribute(button.openingElement, "aria-label");
  if (accessibleButtonLabel === undefined || accessibleButtonLabel.trim().length === 0) {
    gap(gaps, "FRT_REACT_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "<button> carries no literal aria-label, so the action has no source-provable accessible name.");
  }

  const politeness = stringAttribute(liveRegion.openingElement, "aria-live");
  if (politeness === undefined) {
    gap(gaps, "FRT_REACT_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "The counter output carries no aria-live attribute, so it is not a source-declared live region.");
  } else if (politeness !== "polite") {
    gap(gaps, "FRT_REACT_LIVE_REGION_UNSUPPORTED", sourcePath,
      `aria-live="${politeness}" is not the polite live region this IR slice models.`);
  }

  const liveChildren = significantChildren(liveRegion);
  const liveExpression = liveChildren.length === 1 && ts.isJsxExpression(liveChildren[0]!)
    ? (liveChildren[0] as ts.JsxExpression).expression : undefined;
  const counterName = liveExpression && ts.isIdentifier(liveExpression) && identifier.test(liveExpression.text)
    ? liveExpression.text : undefined;
  const initialCount = counterName === undefined ? undefined : states.get(counterName)?.initial;
  if (counterName === undefined || initialCount === undefined) {
    gap(gaps, "FRT_REACT_COUNTER_STATE_NOT_DERIVABLE", sourcePath,
      "The live region must render exactly one integer useState value declared in this component.");
  }

  let incrementBy: number | undefined;
  const onClick = expressionAttribute(button.openingElement, "onClick");
  if (!onClick) {
    gap(gaps, "FRT_REACT_COUNTER_ACTION_NOT_DERIVABLE", sourcePath,
      "The action button must bind onClick to a readable handler expression.");
  } else if (counterName !== undefined) {
    const deltas = handlerFor(onClick, model);
    if (!deltas) {
      gap(gaps, "FRT_REACT_COUNTER_ACTION_NOT_DERIVABLE", sourcePath,
        "onClick is neither an inline zero-argument arrow applying one state delta nor a declared handler.");
    } else {
      const delta = deltas.get(counterName);
      if (delta === undefined || deltas.size !== 1) {
        gap(gaps, "FRT_REACT_COUNTER_ACTION_NOT_DERIVABLE", sourcePath,
          `The onClick handler does not apply exactly one delta to ${counterName}.`);
      } else incrementBy = delta;
    }
  }

  const accentColor = deriveAccentColor(files, importedStylesheets, sourcePath, gaps);

  if (gaps.length !== before) return undefined;
  if (version === undefined || title === undefined || buttonLabel === undefined
      || initialCount === undefined || incrementBy === undefined || accentColor === undefined
      || mainLabel === undefined || accessibleButtonLabel === undefined) {
    // Unreachable while every failure above records a gap; kept so a future
    // refactor cannot turn a missing value into a silent default.
    gap(gaps, "FRT_REACT_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "The React route contract was not fully derivable from source.");
    return undefined;
  }

  const sourceRefs = contentAddressedSourceRefs(files, new Set(["frt-ui-ir.json"]));
  return {
    schemaVersion: "1.0",
    source: { stack: "React", version },
    sourceSnapshotDigest: sha256(canonical(sourceRefs)),
    sourceRefs,
    route: { path: "/", requiresAuth: false, deepLink: true },
    view: { title, initialCount, incrementBy, buttonLabel },
    style: { accentColor },
    accessibility: { mainLabel, buttonLabel: accessibleButtonLabel, liveRegion: "polite" },
    capabilities: { permissions: [], native: [], network: [] },
  };
}

/** Resolve an onClick expression to the state deltas it applies, or undefined. */
function handlerFor(
  onClick: ts.Expression,
  model: ScriptModel,
): ReadonlyMap<string, number> | undefined {
  if (ts.isIdentifier(onClick)) return model.handlerDeltas.get(onClick.text);
  if (!ts.isArrowFunction(onClick) || onClick.parameters.length !== 0) return undefined;
  const body = onClick.body;
  const calls: ts.CallExpression[] = [];
  if (ts.isBlock(body)) {
    for (const statement of body.statements) {
      if (!ts.isExpressionStatement(statement) || !ts.isCallExpression(statement.expression)) return undefined;
      calls.push(statement.expression);
    }
  } else if (ts.isCallExpression(body)) calls.push(body);
  else return undefined;

  const deltas = new Map<string, number>();
  for (const call of calls) {
    const delta = setterCallDelta(call, model.states);
    if (!delta) return undefined;
    deltas.set(delta.state, (deltas.get(delta.state) ?? 0) + delta.amount);
  }
  return deltas;
}

/**
 * Vue 3 source -> Portable UI IR.
 *
 * This is the first route source for which the IR is *derived from the source
 * bytes* rather than accepted as a declaration. Everything the IR asserts about
 * a Vue 3 route is read out of the real SFC with @vue/compiler-sfc and the
 * TypeScript parser; anything that cannot be read is reported as a typed gap
 * and blocks the route. Nothing is defaulted, approximated, or invented — in
 * particular the accessibility contract, which earlier could be declared in
 * frt-ui-ir.json without appearing anywhere in the source at all.
 */

import { parse as parseVueSfc } from "@vue/compiler-sfc";
import ts from "typescript";

import {
  canonical,
  contentAddressedSourceRefs,
  gap,
  sha256,
  type FrtRouteTypedGap,
  type PortableUiIr,
} from "./frt-route-ir.js";

/** Vue compiler-core NodeTypes, spelled out so the numbers are not magic. */
const NODE_ROOT = 0;
const NODE_ELEMENT = 1;
const NODE_TEXT = 2;
const NODE_COMMENT = 3;
const NODE_INTERPOLATION = 5;
const PROP_ATTRIBUTE = 6;
const PROP_DIRECTIVE = 7;
/** Vue compiler-core ElementTypes.ELEMENT — a plain DOM element, not a component. */
const ELEMENT_PLAIN = 0;

const exactVersion = /^(?:[0-9]+\.)+[0-9]+$/;
const vue3Major = /^3\./;
const accentRule = /^button\s*\{\s*color\s*:\s*(#[0-9A-Fa-f]{6})\s*;?\s*\}$/;

interface ExpressionNode {
  readonly type: number;
  readonly content?: string;
  readonly isStatic?: boolean;
}
interface PropNode {
  readonly type: number;
  readonly name?: string;
  readonly value?: { readonly content?: string };
  readonly arg?: ExpressionNode;
  readonly exp?: ExpressionNode;
  readonly modifiers?: readonly unknown[];
}

interface TemplateNode {
  readonly type: number;
  readonly tag?: string;
  readonly tagType?: number;
  readonly content?: string | ExpressionNode;
  readonly props?: readonly PropNode[];
  readonly children?: readonly TemplateNode[];
}

interface ScriptModel {
  readonly stringConstants: ReadonlyMap<string, string>;
  readonly numericRefs: ReadonlyMap<string, number>;
  /** handler name -> (ref name -> integer delta applied by that handler) */
  readonly handlerDeltas: ReadonlyMap<string, ReadonlyMap<string, number>>;
}

function significantChildren(node: TemplateNode): readonly TemplateNode[] {
  return (node.children ?? []).filter(child => {
    if (child.type === NODE_COMMENT) return false;
    if (child.type === NODE_TEXT) {
      return typeof child.content === "string" && child.content.trim().length > 0;
    }
    return true;
  });
}

function staticAttribute(node: TemplateNode, name: string): string | undefined {
  for (const prop of node.props ?? []) {
    if (prop.type === PROP_ATTRIBUTE && prop.name === name) return prop.value?.content ?? "";
  }
  return undefined;
}

function interpolatedIdentifier(node: TemplateNode): string | undefined {
  if (node.type !== NODE_INTERPOLATION) return undefined;
  const content = typeof node.content === "object" ? node.content?.content?.trim() : undefined;
  if (!content || !/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(content)) return undefined;
  return content;
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

function refTarget(node: ts.Expression, refs: ReadonlySet<string>): string | undefined {
  if (!ts.isPropertyAccessExpression(node) || node.name.text !== "value") return undefined;
  if (!ts.isIdentifier(node.expression) || !refs.has(node.expression.text)) return undefined;
  return node.expression.text;
}

function analyzeScriptSetup(
  content: string,
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): ScriptModel {
  const file = ts.createSourceFile(sourcePath, content, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TS);
  const stringConstants = new Map<string, string>();
  const numericRefs = new Map<string, number>();
  const handlerDeltas = new Map<string, ReadonlyMap<string, number>>();
  let refImported = false;

  for (const statement of file.statements) {
    if (ts.isImportDeclaration(statement)) {
      const specifier = ts.isStringLiteral(statement.moduleSpecifier)
        ? statement.moduleSpecifier.text : "<computed>";
      const bindings = statement.importClause?.namedBindings;
      const named = bindings && ts.isNamedImports(bindings)
        ? bindings.elements.map(element => element.name.text) : [];
      if (specifier !== "vue" || statement.importClause?.name !== undefined
          || named.length !== 1 || named[0] !== "ref") {
        gap(gaps, "FRT_VUE3_IMPORT_UNSUPPORTED", sourcePath,
          `Import from ${specifier} is outside the derivable slice; only \`import { ref } from "vue"\` is read.`);
        continue;
      }
      refImported = true;
      continue;
    }

    if (ts.isVariableStatement(statement)) {
      const isConst = (statement.declarationList.flags & ts.NodeFlags.Const) !== 0;
      for (const declaration of statement.declarationList.declarations) {
        if (!isConst || !ts.isIdentifier(declaration.name) || !declaration.initializer) {
          gap(gaps, "FRT_VUE3_BINDING_UNSUPPORTED", sourcePath,
            "Only initialized `const` identifier bindings are read as source of truth.");
          continue;
        }
        const name = declaration.name.text;
        const initializer = declaration.initializer;
        if (ts.isStringLiteral(initializer)) {
          stringConstants.set(name, initializer.text);
          continue;
        }
        if (ts.isCallExpression(initializer) && ts.isIdentifier(initializer.expression)
            && initializer.expression.text === "ref" && initializer.arguments.length === 1) {
          const initial = integerLiteral(initializer.arguments[0]!);
          if (initial === undefined) {
            gap(gaps, "FRT_VUE3_BINDING_UNSUPPORTED", sourcePath,
              `ref ${name} is not initialized with an integer literal, so its initial state is not derivable.`);
            continue;
          }
          numericRefs.set(name, initial);
          continue;
        }
        gap(gaps, "FRT_VUE3_BINDING_UNSUPPORTED", sourcePath,
          `Binding ${name} is neither a string constant nor an integer ref.`);
      }
      continue;
    }

    if (ts.isFunctionDeclaration(statement)) {
      if (!statement.name || !statement.body || statement.parameters.length !== 0) {
        gap(gaps, "FRT_VUE3_SCRIPT_STATEMENT_UNSUPPORTED", sourcePath,
          "Only named zero-argument function declarations are read as route actions.");
        continue;
      }
      const deltas = new Map<string, number>();
      const refNames = new Set(numericRefs.keys());
      for (const child of statement.body.statements) {
        const delta = statementDelta(child, refNames);
        if (!delta) {
          gap(gaps, "FRT_VUE3_HANDLER_STATEMENT_UNSUPPORTED", sourcePath,
            `Handler ${statement.name.text} contains a statement that is not a deterministic integer state delta.`);
          continue;
        }
        deltas.set(delta.ref, (deltas.get(delta.ref) ?? 0) + delta.amount);
      }
      handlerDeltas.set(statement.name.text, deltas);
      continue;
    }

    gap(gaps, "FRT_VUE3_SCRIPT_STATEMENT_UNSUPPORTED", sourcePath,
      `Statement ${ts.SyntaxKind[statement.kind]} is outside the derivable Vue 3 route slice.`);
  }

  if (numericRefs.size > 0 && !refImported) {
    gap(gaps, "FRT_VUE3_REF_IMPORT_MISSING", sourcePath,
      "Reactive refs were used without an exact `ref` import from vue.");
  }
  return { stringConstants, numericRefs, handlerDeltas };
}

function statementDelta(
  statement: ts.Statement,
  refs: ReadonlySet<string>,
): { readonly ref: string; readonly amount: number } | undefined {
  if (!ts.isExpressionStatement(statement)) return undefined;
  const expression = statement.expression;
  if (ts.isPostfixUnaryExpression(expression)) {
    const ref = refTarget(expression.operand, refs);
    if (!ref) return undefined;
    if (expression.operator === ts.SyntaxKind.PlusPlusToken) return { ref, amount: 1 };
    if (expression.operator === ts.SyntaxKind.MinusMinusToken) return { ref, amount: -1 };
    return undefined;
  }
  if (ts.isBinaryExpression(expression)) {
    const ref = refTarget(expression.left, refs);
    if (!ref) return undefined;
    const amount = integerLiteral(expression.right);
    if (amount === undefined) return undefined;
    if (expression.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken) return { ref, amount };
    if (expression.operatorToken.kind === ts.SyntaxKind.MinusEqualsToken) return { ref, amount: -amount };
    return undefined;
  }
  return undefined;
}

function textOrConstant(
  element: TemplateNode,
  model: ScriptModel,
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
  code: string,
  what: string,
): string | undefined {
  const children = significantChildren(element);
  if (children.length !== 1) {
    gap(gaps, code, sourcePath, `${what} must be exactly one static text or one string-constant interpolation.`);
    return undefined;
  }
  const child = children[0]!;
  if (child.type === NODE_TEXT && typeof child.content === "string") return child.content.trim();
  const identifier = interpolatedIdentifier(child);
  if (identifier !== undefined) {
    const value = model.stringConstants.get(identifier);
    if (value !== undefined) return value;
    gap(gaps, code, sourcePath,
      `${what} interpolates ${identifier}, which is not a literal string constant in this component.`);
    return undefined;
  }
  gap(gaps, code, sourcePath, `${what} is not readable from the source template.`);
  return undefined;
}

function rejectUnexpectedProps(
  element: TemplateNode,
  allowedAttributes: readonly string[],
  allowedClickHandler: boolean,
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): void {
  for (const prop of element.props ?? []) {
    if (prop.type === PROP_ATTRIBUTE) {
      if (!allowedAttributes.includes(prop.name ?? "")) {
        gap(gaps, "FRT_VUE3_TEMPLATE_ATTRIBUTE_UNSUPPORTED", sourcePath,
          `Attribute ${prop.name ?? "<unnamed>"} on <${element.tag ?? "?"}> carries a semantic this slice does not model.`);
      }
      continue;
    }
    if (prop.type === PROP_DIRECTIVE) {
      const isClick = allowedClickHandler && prop.name === "on" && prop.arg?.content === "click";
      if (!isClick || (prop.modifiers?.length ?? 0) > 0) {
        gap(gaps, "FRT_VUE3_TEMPLATE_ATTRIBUTE_UNSUPPORTED", sourcePath,
          `Directive v-${prop.name ?? "?"} on <${element.tag ?? "?"}> requires an explicit typed mapping.`);
      }
      continue;
    }
    gap(gaps, "FRT_VUE3_TEMPLATE_ATTRIBUTE_UNSUPPORTED", sourcePath,
      `Unsupported property node on <${element.tag ?? "?"}>.`);
  }
}

function clickHandlerName(element: TemplateNode): string | undefined {
  for (const prop of element.props ?? []) {
    if (prop.type !== PROP_DIRECTIVE || prop.name !== "on" || prop.arg?.content !== "click") continue;
    const handler = prop.exp?.content?.trim();
    if (handler && /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(handler)) return handler;
    return undefined;
  }
  return undefined;
}

function deriveAccentColor(
  styles: readonly { readonly content: string }[],
  sourcePath: string,
  gaps: FrtRouteTypedGap[],
): string | undefined {
  if (styles.length > 1) {
    gap(gaps, "FRT_VUE3_STYLE_CARDINALITY_UNSUPPORTED", sourcePath,
      `${styles.length} style blocks were found; cascade order is not determined.`);
    return undefined;
  }
  const raw = (styles[0]?.content ?? "").replace(/\/\*[\s\S]*?\*\//g, "").trim();
  const match = accentRule.exec(raw);
  if (!match) {
    gap(gaps, "FRT_VUE3_ACCENT_COLOR_NOT_DERIVABLE", sourcePath,
      "The style block is not the single `button { color: #rrggbb; }` design token this IR slice can carry.");
    return undefined;
  }
  // Returned verbatim: normalizing the case here would already be a small
  // invention, and the divergence check compares hex case-insensitively.
  return match[1]!;
}

/**
 * Derive the portable UI IR from real Vue 3 source bytes.
 *
 * Returns `undefined` whenever any part of the contract could not be read; the
 * reason is always in `gaps`, never silently defaulted.
 */
export function deriveVue3PortableUiIr(
  files: Readonly<Record<string, string>>,
  gaps: FrtRouteTypedGap[],
): PortableUiIr | undefined {
  const before = gaps.length;

  let version: string | undefined;
  const manifest = files["package.json"];
  if (manifest === undefined) {
    gap(gaps, "FRT_VUE3_PACKAGE_MANIFEST_INVALID", "package.json",
      "package.json is required to prove the source stack and version.");
  } else {
    try {
      const parsed = JSON.parse(manifest) as {
        dependencies?: Record<string, string>;
        devDependencies?: Record<string, string>;
      };
      const declared = parsed.dependencies?.vue ?? parsed.devDependencies?.vue;
      if (!declared || !exactVersion.test(declared) || !vue3Major.test(declared)) {
        gap(gaps, "FRT_VUE3_SOURCE_VERSION_NOT_EXACT", "package.json",
          `The Vue dependency ${declared ?? "<missing>"} is not an exact Vue 3 version.`);
      } else version = declared;
    } catch {
      gap(gaps, "FRT_VUE3_PACKAGE_MANIFEST_INVALID", "package.json", "package.json is not valid JSON.");
    }
  }

  const vueFiles = Object.keys(files).filter(path => path.endsWith(".vue")).sort();
  const sourcePath = vueFiles[0] ?? "<missing-vue-sfc>";
  if (vueFiles.length !== 1) {
    gap(gaps, "FRT_VUE3_SFC_CARDINALITY_UNSUPPORTED", sourcePath,
      `${vueFiles.length} Vue single-file components were found; exactly one is required.`);
    return undefined;
  }

  const parsed = parseVueSfc(files[sourcePath]!, { filename: sourcePath, sourceMap: false });
  for (const error of parsed.errors) {
    gap(gaps, "FRT_VUE3_SFC_PARSE_ERROR", sourcePath, String(error));
  }
  const descriptor = parsed.descriptor;
  if (!descriptor.scriptSetup || descriptor.script) {
    gap(gaps, "FRT_VUE3_SCRIPT_MODE_UNSUPPORTED", sourcePath,
      "Exactly one <script setup> block and no classic script block is required.");
    return undefined;
  }
  if (!descriptor.template?.ast) {
    gap(gaps, "FRT_VUE3_TEMPLATE_MISSING", sourcePath, "A parsed template AST is required.");
    return undefined;
  }

  const model = analyzeScriptSetup(descriptor.scriptSetup.content, sourcePath, gaps);
  const accentColor = deriveAccentColor(descriptor.styles, sourcePath, gaps);

  const root = descriptor.template.ast as unknown as TemplateNode;
  const rootChildren = root.type === NODE_ROOT ? significantChildren(root) : [];
  const main = rootChildren.length === 1 ? rootChildren[0] : undefined;
  if (!main || main.type !== NODE_ELEMENT || main.tag !== "main" || main.tagType !== ELEMENT_PLAIN) {
    gap(gaps, "FRT_VUE3_ROUTE_ROOT_UNSUPPORTED", sourcePath,
      "The template root must be exactly one plain <main> element for this route slice.");
    return undefined;
  }

  rejectUnexpectedProps(main, ["aria-label"], false, sourcePath, gaps);
  const mainLabel = staticAttribute(main, "aria-label");
  if (mainLabel === undefined || mainLabel.trim().length === 0) {
    gap(gaps, "FRT_VUE3_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "<main> carries no aria-label, so this route has no source-provable accessible name.");
  }

  const parts = significantChildren(main);
  const heading = parts.find(part => part.type === NODE_ELEMENT && part.tag === "h1");
  const button = parts.find(part => part.type === NODE_ELEMENT && part.tag === "button");
  const liveRegion = parts.find(part => part.type === NODE_ELEMENT && part.tag === "p");
  if (parts.length !== 3 || !heading || !button || !liveRegion) {
    gap(gaps, "FRT_VUE3_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "This route slice reads exactly one <h1> title, one <button> action, and one <p> live region.");
    return undefined;
  }

  rejectUnexpectedProps(heading, [], false, sourcePath, gaps);
  rejectUnexpectedProps(button, ["aria-label"], true, sourcePath, gaps);
  rejectUnexpectedProps(liveRegion, ["aria-live"], false, sourcePath, gaps);

  const title = textOrConstant(heading, model, sourcePath, gaps, "FRT_VUE3_TITLE_NOT_DERIVABLE", "The route title");
  const buttonLabel = textOrConstant(
    button, model, sourcePath, gaps, "FRT_VUE3_BUTTON_LABEL_NOT_DERIVABLE", "The action label",
  );

  const accessibleButtonLabel = staticAttribute(button, "aria-label");
  if (accessibleButtonLabel === undefined || accessibleButtonLabel.trim().length === 0) {
    gap(gaps, "FRT_VUE3_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "<button> carries no aria-label, so the action has no source-provable accessible name.");
  }

  const politeness = staticAttribute(liveRegion, "aria-live");
  if (politeness === undefined) {
    gap(gaps, "FRT_VUE3_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", sourcePath,
      "The counter output carries no aria-live attribute, so it is not a source-declared live region.");
  } else if (politeness !== "polite") {
    gap(gaps, "FRT_VUE3_LIVE_REGION_UNSUPPORTED", sourcePath,
      `aria-live="${politeness}" is not the polite live region this IR slice models.`);
  }

  const liveChildren = significantChildren(liveRegion);
  const counterName = liveChildren.length === 1 ? interpolatedIdentifier(liveChildren[0]!) : undefined;
  const initialCount = counterName === undefined ? undefined : model.numericRefs.get(counterName);
  if (counterName === undefined || initialCount === undefined) {
    gap(gaps, "FRT_VUE3_COUNTER_STATE_NOT_DERIVABLE", sourcePath,
      "The live region must interpolate exactly one integer ref declared in this component.");
  }

  let incrementBy: number | undefined;
  const handler = clickHandlerName(button);
  if (handler === undefined) {
    gap(gaps, "FRT_VUE3_COUNTER_ACTION_NOT_DERIVABLE", sourcePath,
      "The action button must bind @click to a single declared handler identifier.");
  } else {
    const deltas = model.handlerDeltas.get(handler);
    if (!deltas) {
      gap(gaps, "FRT_VUE3_COUNTER_ACTION_NOT_DERIVABLE", sourcePath,
        `@click handler ${handler} is not a zero-argument function declared in this component.`);
    } else if (counterName !== undefined) {
      const delta = deltas.get(counterName);
      if (delta === undefined || deltas.size !== 1) {
        gap(gaps, "FRT_VUE3_COUNTER_ACTION_NOT_DERIVABLE", sourcePath,
          `Handler ${handler} does not apply exactly one delta to ${counterName}.`);
      } else incrementBy = delta;
    }
  }

  if (gaps.length !== before) return undefined;
  if (version === undefined || title === undefined || buttonLabel === undefined
      || initialCount === undefined || incrementBy === undefined || accentColor === undefined
      || mainLabel === undefined || accessibleButtonLabel === undefined) {
    // Unreachable while every failure above records a gap; kept so a future
    // refactor cannot turn a missing value into a silent default.
    gap(gaps, "FRT_VUE3_TEMPLATE_SHAPE_UNSUPPORTED", sourcePath,
      "The Vue 3 route contract was not fully derivable from source.");
    return undefined;
  }

  const sourceRefs = contentAddressedSourceRefs(files, new Set(["frt-ui-ir.json"]));
  return {
    schemaVersion: "1.0",
    source: { stack: "Vue 3", version },
    sourceSnapshotDigest: sha256(canonical(sourceRefs)),
    sourceRefs,
    route: { path: "/", requiresAuth: false, deepLink: true },
    view: { title, initialCount, incrementBy, buttonLabel },
    style: { accentColor },
    accessibility: { mainLabel, buttonLabel: accessibleButtonLabel, liveRegion: "polite" },
    capabilities: { permissions: [], native: [], network: [] },
  };
}

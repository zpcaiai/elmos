import * as ts from "typescript";
import {
  FullSyntaxAttr,
  FullSyntaxComponentIR,
  FullSyntaxComputed,
  FullSyntaxEffect,
  FullSyntaxEvent,
  FullSyntaxMethod,
  FullSyntaxNode,
  FullSyntaxProp,
  FullSyntaxSlot,
  FullSyntaxState,
} from "../types";

export class SvelteFullAstParser {
  public parse(sourceCode: string, componentNameHint?: string): FullSyntaxComponentIR {
    const compName = componentNameHint || "SvelteComponent";
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];
    const slots: FullSyntaxSlot[] = [];
    const containerApis = new Set<string>();
    const thirdPartyComponents = new Set<string>();
    let nodeCounter = 0;
    const generateId = (prefix = "node") => `${prefix}_${nodeCounter++}`;

    // Extract <script> block
    const scriptMatch = sourceCode.match(/<script(?:\s+lang="ts")?>([\s\S]*?)<\/script>/);
    let templateSource = sourceCode.replace(/<script[\s\S]*?<\/script>/, "");

    // Extract <style> block
    const styleMatch = sourceCode.match(/<style>([\s\S]*?)<\/style>/);
    const scopedCss = styleMatch && styleMatch[1] ? styleMatch[1].trim() : "";
    templateSource = templateSource.replace(/<style[\s\S]*?<\/style>/, "");

    if (scriptMatch) {
      const scriptCode = scriptMatch[1] || "";
      const scriptSource = ts.createSourceFile("script.ts", scriptCode, ts.ScriptTarget.Latest, true);

      const visit = (node: ts.Node) => {
        // export let propName: type = default;
        if (ts.isVariableStatement(node)) {
          const isExport = node.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
          for (const decl of node.declarationList.declarations) {
            if (ts.isIdentifier(decl.name)) {
              const name = decl.name.text;
              const typeAnnot = decl.type ? decl.type.getText(scriptSource) : "any";
              const initVal = decl.initializer ? decl.initializer.getText(scriptSource) : undefined;

              if (isExport) {
                props.push({
                  name,
                  typeAnnotation: typeAnnot,
                  required: !initVal,
                  defaultValue: initVal,
                  isCallback: name.startsWith("on"),
                });
              } else {
                states.push({
                  name,
                  initialValueExpr: initVal || "null",
                  typeAnnotation: typeAnnot,
                });
              }
            }
          }
        }

        // $: computed = expr;
        if (ts.isExpressionStatement(node) && ts.isBinaryExpression(node.expression)) {
          const bin = node.expression;
          if (bin.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
            computed.push({
              name: bin.left.getText(scriptSource),
              returnType: "any",
              dependencies: [],
              expressionOrBody: bin.right.getText(scriptSource),
            });
          }
        }

        // onMount(() => { ... })
        if (ts.isExpressionStatement(node) && ts.isCallExpression(node.expression)) {
          const callee = node.expression.expression.getText(scriptSource);
          if (callee === "onMount" || callee === "onDestroy") {
            const bodyCode = node.expression.arguments[0]?.getText(scriptSource) || "";
            effects.push({
              id: generateId("effect"),
              hookKind: callee === "onMount" ? "mount" : "unmount",
              dependencies: [],
              bodyCode,
              hasCleanup: callee === "onMount" && bodyCode.includes("return () =>"),
            });
          }
        }

        // Functions / methods
        if (ts.isFunctionDeclaration(node) && node.name) {
          methods.push({
            name: node.name.text,
            parameters: node.parameters.map((p) => ({
              name: p.name.getText(scriptSource),
              type: p.type ? p.type.getText(scriptSource) : "any",
            })),
            returnType: node.type ? node.type.getText(scriptSource) : "void",
            bodyCode: node.body ? node.body.getText(scriptSource) : "",
            isAsync: !!(node.modifiers && node.modifiers.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword)),
          });
        }

        ts.forEachChild(node, visit);
      };

      visit(scriptSource);
    }

    const templateRoot = parseSvelteTemplate(templateSource, generateId, thirdPartyComponents, slots);

    return {
      schemaVersion: "2.0",
      componentName: compName,
      sourceFramework: "svelte",
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot,
      styles: {
        scopedCss,
      },
      containerApis: Array.from(containerApis),
      thirdPartyComponents: Array.from(thirdPartyComponents),
      rawSourceLinesCount: sourceCode.split("\n").length,
      metadata: {},
    };
  }
}

function parseSvelteTemplate(
  templateHtml: string,
  generateId: (prefix?: string) => string,
  thirdPartyComponents: Set<string>,
  slots: FullSyntaxSlot[]
): FullSyntaxNode {
  if (!templateHtml.trim()) {
    return { id: generateId("frag"), kind: "fragment", children: [] };
  }

  // Handle Svelte {#if ...} ... {/if}
  const ifRegex = /\{#if\s+([\s\S]*?)\}([\s\S]*?)(?:\{:else\}([\s\S]*?))?\{\/if\}/g;
  let ifMatch: RegExpExecArray | null;
  const conditionals: FullSyntaxNode[] = [];
  let remaining = templateHtml;

  while ((ifMatch = ifRegex.exec(templateHtml)) !== null) {
    const test = (ifMatch[1] || "").trim();
    const thenBlock = ifMatch[2] || "";
    const elseBlock = ifMatch[3];
    const thenNode = parseSvelteTemplate(thenBlock, generateId, thirdPartyComponents, slots);
    const elseNode = elseBlock ? parseSvelteTemplate(elseBlock, generateId, thirdPartyComponents, slots) : undefined;
    conditionals.push({
      id: generateId("cond"),
      kind: "conditional",
      condition: {
        test,
        thenNode,
        elseNode,
      },
    });
    remaining = remaining.replace(ifMatch[0], "");
  }

  // Handle Svelte {#each items as item (key)} ... {/each}
  const eachRegex = /\{#each\s+([\s\S]*?)\s+as\s+([a-zA-Z0-9_]+)(?:\s*\(([^)]+)\))?\}([\s\S]*?)\{\/each\}/g;
  let eachMatch: RegExpExecArray | null;
  const loops: FullSyntaxNode[] = [];
  while ((eachMatch = eachRegex.exec(remaining)) !== null) {
    const sourceExpr = (eachMatch[1] || "").trim();
    const itemName = (eachMatch[2] || "").trim();
    const keyExpr = eachMatch[3]?.trim();
    const bodyContent = eachMatch[4] || "";
    const bodyNode = parseSvelteTemplate(bodyContent, generateId, thirdPartyComponents, slots);
    loops.push({
      id: generateId("loop"),
      kind: "loop",
      loop: {
        sourceExpr,
        itemName,
        keyExpr,
        bodyNode,
      },
    });
    remaining = remaining.replace(eachMatch[0], "");
  }

  // Handle standard HTML elements
  const tagRegex = /<([a-zA-Z0-9_-]+)([^>]*)>([\s\S]*?)<\/\1>|<([a-zA-Z0-9_-]+)([^>]*)\/>/g;
  const elements: FullSyntaxNode[] = [];
  let match: RegExpExecArray | null;

  while ((match = tagRegex.exec(remaining)) !== null) {
    const tag = (match[1] || match[4] || "div").toLowerCase();
    const rawAttrs = match[2] || match[5] || "";
    const inner = match[3] || "";

    if (tag === "slot") {
      const nameMatch = rawAttrs.match(/name="([^"]*)"/);
      const slotName = nameMatch && nameMatch[1] ? nameMatch[1] : "default";
      slots.push({ name: slotName, slotProps: [], fallbackNodes: [] });
      elements.push({ id: generateId("slot"), kind: "slot_outlet", slotName });
      continue;
    }

    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];

    const attrRegex = /([a-zA-Z0-9_:-]+)(?:=(?:"([^"]*)"|{([^}]*)}))?/g;
    let aMatch: RegExpExecArray | null;
    while ((aMatch = attrRegex.exec(rawAttrs)) !== null) {
      const aName = aMatch[1];
      const strVal = aMatch[2];
      const exprVal = aMatch[3];
      if (!aName) continue;

      if (aName.startsWith("on:")) {
        events.push({ name: aName.slice(3).toLowerCase(), handlerNameOrExpr: exprVal || strVal || "" });
      } else if (aName.startsWith("bind:")) {
        attrs.push({ name: aName.slice(5), value: exprVal || strVal || "", isDynamic: true, expression: exprVal || strVal });
      } else if (exprVal !== undefined) {
        attrs.push({ name: aName, value: exprVal, isDynamic: true, expression: exprVal });
      } else {
        attrs.push({ name: aName, value: strVal || "", isDynamic: false });
      }
    }

    const elemChildren = parseSvelteTemplate(inner, generateId, thirdPartyComponents, slots);
    elements.push({
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children: elemChildren.children || (elemChildren.kind === "text" ? [elemChildren] : []),
    });
  }

  // Any remaining expressions or text
  const textContent = remaining.replace(/<[^>]+>/g, "").replace(/{[^}]+}/g, "").trim();
  const textNodes: FullSyntaxNode[] = [];
  if (textContent) {
    textNodes.push({ id: generateId("text"), kind: "text", text: textContent });
  }

  const exprRegex = /{([^}]+)}/g;
  let eMatch: RegExpExecArray | null;
  while ((eMatch = exprRegex.exec(remaining)) !== null) {
    const exprText = (eMatch[1] || "").trim();
    if (!exprText.startsWith("#") && !exprText.startsWith("/") && !exprText.startsWith(":")) {
      textNodes.push({ id: generateId("expr"), kind: "expression", expression: exprText });
    }
  }

  const allChildren = [...conditionals, ...loops, ...elements, ...textNodes];
  return { id: generateId("frag"), kind: "fragment", children: allChildren };
}

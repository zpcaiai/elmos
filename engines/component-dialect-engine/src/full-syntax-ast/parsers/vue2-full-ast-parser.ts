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

export class Vue2FullAstParser {
  public parse(sourceCode: string, componentNameHint?: string): FullSyntaxComponentIR {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const sfc = require("@vue/compiler-sfc");
    const { descriptor } = sfc.parse(sourceCode, { filename: (componentNameHint || "Component") + ".vue" });

    const compName = componentNameHint || "Vue2Component";
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

    if (descriptor.script) {
      const scriptCode = descriptor.script.content;
      const scriptSource = ts.createSourceFile("script.ts", scriptCode, ts.ScriptTarget.Latest, true);

      // Inspect export default { ... }
      const visitOptionsObject = (objLiteral: ts.ObjectLiteralExpression) => {
        for (const prop of objLiteral.properties) {
          if (!ts.isPropertyAssignment(prop) && !ts.isMethodDeclaration(prop)) continue;
          const propName = prop.name.getText(scriptSource);

          // props: { ... } or props: [...]
          if (propName === "props" && ts.isPropertyAssignment(prop)) {
            if (ts.isObjectLiteralExpression(prop.initializer)) {
              for (const p of prop.initializer.properties) {
                const name = p.name?.getText(scriptSource) || "";
                props.push({
                  name,
                  typeAnnotation: "any",
                  required: true,
                  isCallback: name.startsWith("on"),
                });
              }
            } else if (ts.isArrayLiteralExpression(prop.initializer)) {
              for (const elem of prop.initializer.elements) {
                if (ts.isStringLiteral(elem)) {
                  props.push({
                    name: elem.text,
                    typeAnnotation: "any",
                    required: true,
                    isCallback: elem.text.startsWith("on"),
                  });
                }
              }
            }
          }

          // data() { return { ... } }
          if (propName === "data") {
            let dataBlock: ts.Block | undefined;
            if (ts.isMethodDeclaration(prop) && prop.body) {
              dataBlock = prop.body;
            } else if (ts.isPropertyAssignment(prop) && ts.isFunctionExpression(prop.initializer) && prop.initializer.body) {
              dataBlock = prop.initializer.body;
            }

            if (dataBlock) {
              for (const stmt of dataBlock.statements) {
                if (ts.isReturnStatement(stmt) && stmt.expression && ts.isObjectLiteralExpression(stmt.expression)) {
                  for (const field of stmt.expression.properties) {
                    if (ts.isPropertyAssignment(field)) {
                      states.push({
                        name: field.name.getText(scriptSource),
                        initialValueExpr: field.initializer.getText(scriptSource),
                        typeAnnotation: "any",
                      });
                    }
                  }
                }
              }
            }
          }

          // computed: { ... }
          if (propName === "computed" && ts.isPropertyAssignment(prop) && ts.isObjectLiteralExpression(prop.initializer)) {
            for (const c of prop.initializer.properties) {
              if (ts.isMethodDeclaration(c) || ts.isPropertyAssignment(c)) {
                computed.push({
                  name: c.name?.getText(scriptSource) || "",
                  returnType: "any",
                  dependencies: [],
                  expressionOrBody: c.getText(scriptSource),
                });
              }
            }
          }

          // methods: { ... }
          if (propName === "methods" && ts.isPropertyAssignment(prop) && ts.isObjectLiteralExpression(prop.initializer)) {
            for (const m of prop.initializer.properties) {
              if (ts.isMethodDeclaration(m) && m.name) {
                methods.push({
                  name: m.name.getText(scriptSource),
                  parameters: m.parameters.map((p) => ({ name: p.name.getText(scriptSource), type: "any" })),
                  returnType: "any",
                  bodyCode: m.body ? m.body.getText(scriptSource) : "",
                  isAsync: !!(m.modifiers && m.modifiers.some((mod) => mod.kind === ts.SyntaxKind.AsyncKeyword)),
                });
              }
            }
          }

          // Lifecycle hooks: mounted, created, beforeDestroy
          if (["mounted", "created", "beforeDestroy", "destroyed"].includes(propName)) {
            const bodyCode = prop.getText(scriptSource);
            effects.push({
              id: generateId("lifecycle"),
              hookKind: propName === "mounted" ? "mount" : propName.includes("destroy") ? "unmount" : "effect",
              dependencies: [],
              bodyCode,
              hasCleanup: false,
            });
          }
        }
      };

      ts.forEachChild(scriptSource, (node) => {
        if (ts.isExportAssignment(node) && ts.isObjectLiteralExpression(node.expression)) {
          visitOptionsObject(node.expression);
        }
      });
    }

    // Parse template
    let templateRoot: FullSyntaxNode = { id: generateId("root"), kind: "fragment", children: [] };
    if (descriptor.template && descriptor.template.ast) {
      templateRoot = parseVue2TemplateNode(descriptor.template.ast, generateId, containerApis, thirdPartyComponents, slots);
    }

    return {
      schemaVersion: "2.0",
      componentName: compName,
      sourceFramework: "vue2",
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot,
      styles: {
        scopedCss: descriptor.styles?.[0]?.content || "",
      },
      containerApis: Array.from(containerApis),
      thirdPartyComponents: Array.from(thirdPartyComponents),
      rawSourceLinesCount: sourceCode.split("\n").length,
      metadata: {},
    };
  }
}

function parseVue2TemplateNode(
  node: any,
  generateId: (prefix?: string) => string,
  containerApis: Set<string>,
  thirdPartyComponents: Set<string>,
  slots: FullSyntaxSlot[]
): FullSyntaxNode {
  if (node.type === 0) {
    const children = (node.children || []).map((c: any) =>
      parseVue2TemplateNode(c, generateId, containerApis, thirdPartyComponents, slots)
    );
    return { id: generateId("root"), kind: "fragment", children };
  }

  if (node.type === 2) {
    return { id: generateId("text"), kind: "text", text: node.content || "" };
  }

  if (node.type === 5) {
    return { id: generateId("expr"), kind: "expression", expression: String(node.content?.content || node.content || "") };
  }

  if (node.type === 1) {
    const tag = node.tag || "div";
    if (/^[A-Z]/.test(tag)) thirdPartyComponents.add(tag);

    if (tag === "slot") {
      const nameProp = (node.props || []).find((p: any) => p.name === "name");
      const slotName = nameProp?.value?.content || "default";
      slots.push({ name: slotName, slotProps: [], fallbackNodes: [] });
      return { id: generateId("slot"), kind: "slot_outlet", slotName };
    }

    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];
    let vIfTest: string | undefined;

    for (const prop of node.props || []) {
      if (prop.type === 7) {
        if (prop.name === "if") vIfTest = prop.exp?.content || "";
        else if (prop.name === "on") events.push({ name: prop.arg?.content?.toLowerCase() || "click", handlerNameOrExpr: prop.exp?.content || "" });
        else if (prop.name === "bind") attrs.push({ name: prop.arg?.content || "", value: prop.exp?.content || "", isDynamic: true, expression: prop.exp?.content || "" });
      } else if (prop.type === 6) {
        attrs.push({ name: prop.name, value: prop.value?.content || "", isDynamic: false });
      }
    }

    const children = (node.children || []).map((c: any) =>
      parseVue2TemplateNode(c, generateId, containerApis, thirdPartyComponents, slots)
    );

    const elemNode: FullSyntaxNode = {
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children,
    };

    if (vIfTest) {
      return { id: generateId("cond"), kind: "conditional", condition: { test: vIfTest, thenNode: elemNode } };
    }
    return elemNode;
  }

  return { id: generateId("frag"), kind: "fragment", children: [] };
}

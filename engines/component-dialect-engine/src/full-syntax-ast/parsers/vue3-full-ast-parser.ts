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

export class Vue3FullAstParser {
  public parse(sourceCode: string, componentNameHint?: string): FullSyntaxComponentIR {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const sfc = require("@vue/compiler-sfc");
    const { descriptor, errors } = sfc.parse(sourceCode, { filename: (componentNameHint || "Component") + ".vue" });

    const compName = componentNameHint || "Vue3Component";
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

    const scriptBlock = descriptor.scriptSetup || descriptor.script;
    if (scriptBlock) {
      const scriptCode = scriptBlock.content;
      const scriptSource = ts.createSourceFile("script.ts", scriptCode, ts.ScriptTarget.Latest, true);

      const visitScript = (node: ts.Node) => {
        // defineProps<{ ... }>()
        if (ts.isCallExpression(node)) {
          const callText = node.expression.getText(scriptSource);
          if (callText === "defineProps") {
            const typeArg = node.typeArguments?.[0];
            if (typeArg && ts.isTypeLiteralNode(typeArg)) {
              for (const member of typeArg.members) {
                if (ts.isPropertySignature(member) && ts.isIdentifier(member.name)) {
                  const pName = member.name.text;
                  const pType = member.type ? member.type.getText(scriptSource) : "any";
                  const isOptional = !!member.questionToken;
                  const isCb = pName.startsWith("on") || pType.includes("=>");
                  props.push({
                    name: pName,
                    typeAnnotation: pType,
                    required: !isOptional,
                    isCallback: isCb,
                  });
                }
              }
            }
          }
        }

        // const x = ref(init) or const y = reactive(init)
        if (ts.isVariableStatement(node)) {
          for (const decl of node.declarationList.declarations) {
            if (ts.isIdentifier(decl.name) && decl.initializer && ts.isCallExpression(decl.initializer)) {
              const call = decl.initializer;
              const callee = call.expression.getText(scriptSource);
              const ident = decl.name.text;

              if (callee === "ref") {
                const initExpr = call.arguments[0] ? call.arguments[0].getText(scriptSource) : "null";
                const typeAnnotation = call.typeArguments?.[0] ? call.typeArguments[0].getText(scriptSource) : "any";
                states.push({
                  name: ident,
                  initialValueExpr: initExpr,
                  typeAnnotation,
                  isRef: true,
                });
              } else if (callee === "reactive") {
                const initExpr = call.arguments[0] ? call.arguments[0].getText(scriptSource) : "{}";
                states.push({
                  name: ident,
                  initialValueExpr: initExpr,
                  typeAnnotation: "Record<string, any>",
                  isRef: false,
                });
              } else if (callee === "computed") {
                const factory = call.arguments[0];
                computed.push({
                  name: ident,
                  returnType: "any",
                  dependencies: [],
                  expressionOrBody: factory ? factory.getText(scriptSource) : "",
                });
              }
            }
          }
        }

        // onMounted, onUnmounted, watch, watchEffect
        if (ts.isExpressionStatement(node) && ts.isCallExpression(node.expression)) {
          const call = node.expression;
          const callee = call.expression.getText(scriptSource);

          if (callee === "onMounted" || callee === "onUnmounted" || callee === "watch" || callee === "watchEffect") {
            const hookKind = callee === "onMounted" ? "mount" : callee === "onUnmounted" ? "unmount" : "watch";
            const fnArg = callee === "watch" ? call.arguments[1] : call.arguments[0];
            const deps = callee === "watch" && call.arguments[0] ? [call.arguments[0].getText(scriptSource)] : [];
            const bodyCode = fnArg ? fnArg.getText(scriptSource) : "";
            effects.push({
              id: generateId("effect"),
              hookKind,
              dependencies: deps,
              bodyCode,
              hasCleanup: callee === "onMounted" && (bodyCode.includes("return () =>") || bodyCode.includes("onUnmounted")),
            });
          }
        }

        // Regular functions / methods
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

        ts.forEachChild(node, visitScript);
      };

      visitScript(scriptSource);
    }

    // Parse template AST
    let templateRoot: FullSyntaxNode = { id: generateId("root"), kind: "fragment", children: [] };
    if (descriptor.template && descriptor.template.ast) {
      const vueAst = descriptor.template.ast;
      templateRoot = parseVueTemplateNode(vueAst, generateId, containerApis, thirdPartyComponents, slots);
    }

    // Extract scoped CSS
    let scopedCss = "";
    if (descriptor.styles && descriptor.styles.length > 0) {
      scopedCss = descriptor.styles.map((s: { content: string }) => s.content).join("\n");
    }

    return {
      schemaVersion: "2.0",
      componentName: compName,
      sourceFramework: "vue3",
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

function parseVueTemplateNode(
  node: any,
  generateId: (prefix?: string) => string,
  containerApis: Set<string>,
  thirdPartyComponents: Set<string>,
  slots: FullSyntaxSlot[]
): FullSyntaxNode {
  // Root node (type 0)
  if (node.type === 0) {
    const children = (node.children || []).map((c: any) =>
      parseVueTemplateNode(c, generateId, containerApis, thirdPartyComponents, slots)
    );
    return {
      id: generateId("root"),
      kind: "fragment",
      children,
    };
  }

  // Text node (type 2)
  if (node.type === 2) {
    return {
      id: generateId("text"),
      kind: "text",
      text: node.content || "",
    };
  }

  // Interpolation node (type 5) {{ msg }}
  if (node.type === 5) {
    const expr = node.content?.content || node.content || "";
    return {
      id: generateId("expr"),
      kind: "expression",
      expression: String(expr),
    };
  }

  // Element node (type 1)
  if (node.type === 1) {
    const tag = node.tag || "div";
    if (/^[A-Z]/.test(tag)) {
      thirdPartyComponents.add(tag);
    }

    // Slot tag: <slot name="...">
    if (tag === "slot") {
      const nameProp = (node.props || []).find((p: any) => p.name === "name");
      const slotName = nameProp?.value?.content || "default";
      slots.push({
        name: slotName,
        slotProps: [],
        fallbackNodes: [],
      });
      return {
        id: generateId("slot"),
        kind: "slot_outlet",
        slotName,
      };
    }

    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];
    let vIfTest: string | undefined;
    let vForExpr: { source: string; item: string; index?: string; key?: string } | undefined;

    for (const prop of node.props || []) {
      // Directives
      if (prop.type === 7) {
        const dirName = prop.name; // 'if', 'else', 'for', 'on', 'bind', 'model'
        const arg = prop.arg?.content || "";
        const exp = prop.exp?.content || "";

        if (dirName === "if") {
          vIfTest = exp;
        } else if (dirName === "for") {
          // v-for="(item, idx) in list"
          const parsedFor = parseVForExpression(exp);
          vForExpr = parsedFor;
        } else if (dirName === "on") {
          events.push({
            name: arg.toLowerCase(),
            handlerNameOrExpr: exp,
          });
        } else if (dirName === "bind") {
          attrs.push({
            name: arg,
            value: exp,
            isDynamic: true,
            expression: exp,
          });
          if (arg === "key" && vForExpr) {
            vForExpr.key = exp;
          }
        } else if (dirName === "model") {
          attrs.push({
            name: "value",
            value: exp,
            isDynamic: true,
            expression: exp,
          });
          events.push({
            name: "input",
            handlerNameOrExpr: `${exp} = $event.target.value`,
          });
        }
      } else if (prop.type === 6) {
        // Static attribute
        attrs.push({
          name: prop.name,
          value: prop.value?.content || "",
          isDynamic: false,
        });
      }
    }

    const children = (node.children || []).map((c: any) =>
      parseVueTemplateNode(c, generateId, containerApis, thirdPartyComponents, slots)
    );

    const elemNode: FullSyntaxNode = {
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children,
    };

    if (vForExpr) {
      return {
        id: generateId("loop"),
        kind: "loop",
        loop: {
          sourceExpr: vForExpr.source,
          itemName: vForExpr.item,
          indexName: vForExpr.index,
          keyExpr: vForExpr.key,
          bodyNode: elemNode,
        },
      };
    }

    if (vIfTest) {
      return {
        id: generateId("cond"),
        kind: "conditional",
        condition: {
          test: vIfTest,
          thenNode: elemNode,
        },
      };
    }

    return elemNode;
  }

  return {
    id: generateId("frag"),
    kind: "fragment",
    children: [],
  };
}

function parseVForExpression(exp: string): { source: string; item: string; index?: string; key?: string } {
  // Examples: "item in items", "(item, index) in items", "(item, index) of items"
  const match = exp.match(/^\s*(?:\(([^,]+),\s*([^)]+)\)|([^\s]+))\s+(?:in|of)\s+([\s\S]+)$/);
  if (match) {
    const item = (match[1] || match[3] || "item").trim();
    const index = match[2] ? match[2].trim() : undefined;
    const source = (match[4] || exp).trim();
    return { source, item, index };
  }
  return { source: exp, item: "item" };
}

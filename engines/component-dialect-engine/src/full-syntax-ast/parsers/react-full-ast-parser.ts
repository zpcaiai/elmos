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

export class ReactFullAstParser {
  public parse(sourceCode: string, componentNameHint?: string): FullSyntaxComponentIR {
    const sourceFile = ts.createSourceFile(
      "component.tsx",
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX
    );

    let compName = componentNameHint || "";
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];
    const slots: FullSyntaxSlot[] = [];
    const containerApis = new Set<string>();
    const thirdPartyComponents = new Set<string>();
    let templateRoot: FullSyntaxNode | null = null;
    let nodeCounter = 0;

    const generateId = (prefix = "node") => `${prefix}_${nodeCounter++}`;

    // Extract interfaces & types for props
    ts.forEachChild(sourceFile, (node) => {
      if (ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node)) {
        const name = node.name.text;
        if (/Props$/i.test(name) || name === compName + "Props" || (!props.length && /Props/i.test(name))) {
          if (ts.isInterfaceDeclaration(node)) {
            for (const member of node.members) {
              if (ts.isPropertySignature(member) && ts.isIdentifier(member.name)) {
                const pName = member.name.text;
                const pType = member.type ? member.type.getText(sourceFile) : "any";
                const isOptional = !!member.questionToken;
                const isCallback = pName.startsWith("on") || pType.includes("=>") || pType.includes("Function");
                if (pName === "children" || pType.includes("ReactNode") || pType.includes("JSX.Element")) {
                  slots.push({
                    name: "default",
                    slotProps: [],
                    fallbackNodes: [],
                  });
                }
                props.push({
                  name: pName,
                  typeAnnotation: pType,
                  required: !isOptional,
                  isCallback,
                });
              }
            }
          }
        }
      }
    });

    // Find the main component function/arrow declaration
    let compDecl: ts.FunctionDeclaration | ts.ArrowFunction | ts.FunctionExpression | null = null;

    if (componentNameHint) {
      ts.forEachChild(sourceFile, (node) => {
        if (ts.isFunctionDeclaration(node) && node.name?.text === componentNameHint) {
          compDecl = node;
          compName = node.name.text;
        } else if (ts.isVariableStatement(node)) {
          for (const decl of node.declarationList.declarations) {
            if (ts.isIdentifier(decl.name) && decl.name.text === componentNameHint && decl.initializer) {
              if (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer)) {
                compDecl = decl.initializer;
                compName = decl.name.text;
              }
            }
          }
        }
      });
    }

    if (!compDecl) {
      ts.forEachChild(sourceFile, (node) => {
        if (ts.isFunctionDeclaration(node) && node.name) {
          if (!compName || node.name.text === compName || /^[A-Z]/.test(node.name.text)) {
            compDecl = node;
            compName = node.name.text;
          }
        } else if (ts.isVariableStatement(node)) {
          for (const decl of node.declarationList.declarations) {
            if (ts.isIdentifier(decl.name) && decl.initializer) {
              if (
                (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer)) &&
                (!compName || decl.name.text === compName || /^[A-Z]/.test(decl.name.text))
              ) {
                compDecl = decl.initializer;
                compName = decl.name.text;
              }
            }
          }
        }
      });
    }

    if (!compName) {
      compName = "ReactComponent";
    }

    // Inspect function parameters for destructuring props
    if (compDecl) {
      const firstParam = (compDecl as ts.FunctionDeclaration).parameters?.[0];
      if (firstParam && ts.isObjectBindingPattern(firstParam.name)) {
        for (const element of firstParam.name.elements) {
          if (ts.isIdentifier(element.name)) {
            const pName = element.name.text;
            if (!props.some((p) => p.name === pName)) {
              const hasDef = !!element.initializer;
              const isCb = pName.startsWith("on");
              if (pName === "children") {
                slots.push({ name: "default", slotProps: [], fallbackNodes: [] });
              }
              props.push({
                name: pName,
                typeAnnotation: "any",
                required: !hasDef,
                defaultValue: element.initializer ? element.initializer.getText(sourceFile) : undefined,
                isCallback: isCb,
              });
            }
          }
        }
      }

      // Traverse component function body
      const body = (compDecl as ts.FunctionDeclaration).body;
      if (body) {
        const visitComponentBody = (node: ts.Node) => {
          // Hooks inspection: useState, useEffect, useCallback, etc.
          if (ts.isVariableStatement(node)) {
            for (const decl of node.declarationList.declarations) {
              if (decl.initializer && ts.isCallExpression(decl.initializer)) {
                const call = decl.initializer;
                const callText = call.expression.getText(sourceFile);

                if (callText === "useState") {
                  if (ts.isArrayBindingPattern(decl.name)) {
                    const elements = decl.name.elements;
                    const stateIdent = elements[0] && ts.isBindingElement(elements[0]) ? elements[0].name.getText(sourceFile) : "";
                    const setterIdent = elements[1] && ts.isBindingElement(elements[1]) ? elements[1].name.getText(sourceFile) : "";
                    const initExpr = call.arguments[0] ? call.arguments[0].getText(sourceFile) : "null";
                    const typeAnnotation = call.typeArguments?.[0] ? call.typeArguments[0].getText(sourceFile) : "any";

                    states.push({
                      name: stateIdent,
                      setterName: setterIdent,
                      initialValueExpr: initExpr,
                      typeAnnotation,
                    });
                  }
                } else if (callText === "useRef") {
                  const refName = decl.name.getText(sourceFile);
                  const initExpr = call.arguments[0] ? call.arguments[0].getText(sourceFile) : "null";
                  states.push({
                    name: refName,
                    initialValueExpr: initExpr,
                    typeAnnotation: "any",
                    isRef: true,
                  });
                } else if (callText === "useMemo") {
                  const compName = decl.name.getText(sourceFile);
                  const factoryArg = call.arguments[0];
                  const deps = call.arguments[1] ? extractDeps(call.arguments[1], sourceFile) : [];
                  computed.push({
                    name: compName,
                    returnType: "any",
                    dependencies: deps,
                    expressionOrBody: factoryArg ? factoryArg.getText(sourceFile) : "",
                  });
                }
              }
            }
          } else if (ts.isExpressionStatement(node)) {
            if (ts.isCallExpression(node.expression)) {
              const call = node.expression;
              const callText = call.expression.getText(sourceFile);
              if (callText === "useEffect" || callText === "useLayoutEffect") {
                const effectFn = call.arguments[0];
                const depsArg = call.arguments[1];
                const deps = depsArg ? extractDeps(depsArg, sourceFile) : [];
                const bodyCode = effectFn ? effectFn.getText(sourceFile) : "";
                effects.push({
                  id: generateId("effect"),
                  hookKind: callText === "useEffect" ? "effect" : "layoutEffect",
                  dependencies: deps,
                  bodyCode,
                  hasCleanup: bodyCode.includes("return () =>") || bodyCode.includes("return function"),
                });
              }
            }
          } else if (ts.isFunctionDeclaration(node) && node.name) {
            methods.push({
              name: node.name.text,
              parameters: node.parameters.map((p) => ({
                name: p.name.getText(sourceFile),
                type: p.type ? p.type.getText(sourceFile) : "any",
              })),
              returnType: node.type ? node.type.getText(sourceFile) : "void",
              bodyCode: node.body ? node.body.getText(sourceFile) : "",
              isAsync: !!(node.modifiers && node.modifiers.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword)),
            });
            return;
          } else if (ts.isArrowFunction(node) || ts.isFunctionExpression(node)) {
            return;
          } else if (ts.isReturnStatement(node) && node.expression) {
            const parsed = parseJsxNode(node.expression, sourceFile, generateId, containerApis, thirdPartyComponents);
            if (parsed) {
              templateRoot = parsed;
            }
          }

          ts.forEachChild(node, visitComponentBody);
        };

        visitComponentBody(body);
      }
    }

    // Detect browser / container APIs in source code
    const raw = sourceCode;
    const apiPatterns = [
      "window.location",
      "window.alert",
      "localStorage",
      "sessionStorage",
      "navigator.clipboard",
      "document.title",
      "document.body",
      "document.getElementById",
    ];
    for (const api of apiPatterns) {
      if (raw.includes(api)) {
        containerApis.add(api);
      }
    }

    const topLevelHelpers: string[] = [];
    for (const stmt of sourceFile.statements) {
      if (stmt === compDecl) continue;
      if (ts.isExportAssignment(stmt)) continue;
      if (ts.isImportDeclaration(stmt)) continue;
      if (ts.isInterfaceDeclaration(stmt) || ts.isTypeAliasDeclaration(stmt)) continue;

      if (ts.isVariableStatement(stmt)) {
        const isComp = stmt.declarationList.declarations.some(
          (d) => ts.isIdentifier(d.name) && (d.name.text === compName || /^[A-Z]/.test(d.name.text))
        );
        if (!isComp) {
          const rawText = stmt.getText(sourceFile);
          if (rawText.includes('<') && (rawText.includes('/>') || rawText.includes('</'))) continue;
          try {
            const transpiled = ts.transpileModule(rawText, {
              compilerOptions: { target: ts.ScriptTarget.ES2022, removeComments: false },
            }).outputText.trim();
            if (transpiled) topLevelHelpers.push(transpiled);
          } catch {
            topLevelHelpers.push(rawText);
          }
        }
      } else if (ts.isFunctionDeclaration(stmt)) {
        if (!stmt.name || stmt.name.text === compName || /^[A-Z]/.test(stmt.name.text)) continue;
        const rawText = stmt.getText(sourceFile);
        if (rawText.includes('<') && (rawText.includes('/>') || rawText.includes('</'))) continue;
        try {
          const transpiled = ts.transpileModule(rawText, {
            compilerOptions: { target: ts.ScriptTarget.ES2022, removeComments: false },
          }).outputText.trim();
          if (transpiled) topLevelHelpers.push(transpiled);
        } catch {
          topLevelHelpers.push(rawText);
        }
      } else if (ts.isEnumDeclaration(stmt)) {
        const rawText = stmt.getText(sourceFile);
        try {
          const transpiled = ts.transpileModule(rawText, {
            compilerOptions: { target: ts.ScriptTarget.ES2022, removeComments: false },
          }).outputText.trim();
          if (transpiled) topLevelHelpers.push(transpiled);
        } catch {
          topLevelHelpers.push(rawText);
        }
      }
    }

    const refs = states.filter((s) => s.isRef).map((s) => ({ name: s.name, type: s.typeAnnotation }));

    return {
      schemaVersion: "2.0",
      componentName: compName,
      sourceFramework: "react",
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs,
      templateRoot: templateRoot || { id: generateId("root"), kind: "fragment", children: [] },
      styles: {
        cssModules: {},
        tailwindClasses: [],
      },
      containerApis: Array.from(containerApis),
      thirdPartyComponents: Array.from(thirdPartyComponents),
      rawSourceLinesCount: sourceCode.split("\n").length,
      metadata: { topLevelHelpers },
    };
  }
}

function extractDeps(depsNode: ts.Node, sourceFile: ts.SourceFile): string[] {
  if (ts.isArrayLiteralExpression(depsNode)) {
    return depsNode.elements.map((e) => e.getText(sourceFile).trim());
  }
  return [];
}

function isJsxBranch(node: ts.Node | undefined): boolean {
  if (!node) return false;
  let current = node;
  while (ts.isParenthesizedExpression(current)) {
    current = current.expression;
  }
  if (ts.isJsxElement(current) || ts.isJsxSelfClosingElement(current) || ts.isJsxFragment(current)) {
    return true;
  }
  if (ts.isConditionalExpression(current)) {
    return isJsxBranch(current.whenTrue) || isJsxBranch(current.whenFalse);
  }
  if (ts.isBinaryExpression(current) && current.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
    return isJsxBranch(current.right);
  }
  return false;
}

function parseJsxNode(
  node: ts.Node,
  sourceFile: ts.SourceFile,
  generateId: (prefix?: string) => string,
  containerApis: Set<string>,
  thirdPartyComponents: Set<string>
): FullSyntaxNode | null {
  if (ts.isParenthesizedExpression(node)) {
    return parseJsxNode(node.expression, sourceFile, generateId, containerApis, thirdPartyComponents);
  }

  if (ts.isJsxExpression(node)) {
    const expr = node.expression;
    if (!expr) {
      return null;
    }

    const exprText = expr.getText(sourceFile).trim();
    if (exprText === 'children' || exprText === 'props.children') {
      return {
        id: generateId("slot"),
        kind: "slot_outlet",
        slotName: "default",
      };
    }

    return parseJsxNode(expr, sourceFile, generateId, containerApis, thirdPartyComponents);
  }

  if (ts.isConditionalExpression(node)) {
    if (isJsxBranch(node.whenTrue) || isJsxBranch(node.whenFalse)) {
      const isNullish = (n: ts.Node) => {
        const t = n.getText(sourceFile).trim();
        return t === "null" || t === "undefined" || t === "false" || t === '""';
      };

      if (isNullish(node.whenTrue) && !isNullish(node.whenFalse)) {
        const conditionStr = `!(${node.condition.getText(sourceFile)})`;
        const thenNode = parseJsxNode(node.whenFalse, sourceFile, generateId, containerApis, thirdPartyComponents) || {
          id: generateId("empty"),
          kind: "fragment",
          children: [],
        };
        return {
          id: generateId("cond"),
          kind: "conditional",
          condition: {
            test: conditionStr,
            thenNode,
          },
        };
      }

      const conditionStr = node.condition.getText(sourceFile);
      const thenNode = parseJsxNode(node.whenTrue, sourceFile, generateId, containerApis, thirdPartyComponents) || {
        id: generateId("empty"),
        kind: "fragment",
        children: [],
      };
      const elseNode = isNullish(node.whenFalse)
        ? undefined
        : parseJsxNode(node.whenFalse, sourceFile, generateId, containerApis, thirdPartyComponents) || undefined;

      return {
        id: generateId("cond"),
        kind: "conditional",
        condition: {
          test: conditionStr,
          thenNode,
          elseNode,
        },
      };
    }
  }

  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
    if (isJsxBranch(node.right)) {
      const conditionStr = node.left.getText(sourceFile);
      const thenNode = parseJsxNode(node.right, sourceFile, generateId, containerApis, thirdPartyComponents) || {
        id: generateId("empty"),
        kind: "fragment",
        children: [],
      };
      return {
        id: generateId("cond"),
        kind: "conditional",
        condition: {
          test: conditionStr,
          thenNode,
        },
      };
    }
  }

  if (ts.isCallExpression(node)) {
    const callExpr = node.expression;
    if (ts.isPropertyAccessExpression(callExpr) && callExpr.name.text === "map") {
      const sourceListExpr = callExpr.expression.getText(sourceFile);
      const mapCallback = node.arguments[0];
      if (mapCallback && (ts.isArrowFunction(mapCallback) || ts.isFunctionExpression(mapCallback))) {
        const itemParam = mapCallback.parameters[0]?.name.getText(sourceFile) || "item";
        const indexParam = mapCallback.parameters[1]?.name.getText(sourceFile);
        let bodyNode: FullSyntaxNode;
        if (ts.isBlock(mapCallback.body)) {
          const retStmt = mapCallback.body.statements.find((s) => ts.isReturnStatement(s)) as
            | ts.ReturnStatement
            | undefined;
          bodyNode = (retStmt?.expression
            ? parseJsxNode(retStmt.expression, sourceFile, generateId, containerApis, thirdPartyComponents)
            : null) || { id: generateId("empty"), kind: "fragment", children: [] };
        } else {
          bodyNode =
            parseJsxNode(mapCallback.body, sourceFile, generateId, containerApis, thirdPartyComponents) || {
              id: generateId("empty"),
              kind: "fragment",
              children: [],
            };
        }

        return {
          id: generateId("loop"),
          kind: "loop",
          loop: {
            sourceExpr: sourceListExpr,
            itemName: itemParam,
            indexName: indexParam,
            keyExpr: itemParam + ".id",
            bodyNode,
          },
        };
      }
    }
  }

  if (ts.isJsxElement(node)) {
    const opening = node.openingElement;
    const tag = opening.tagName.getText(sourceFile);
    if (tag.endsWith('.Provider') || tag.endsWith('.Consumer')) {
      const children = node.children
        .map((c) => parseJsxNode(c, sourceFile, generateId, containerApis, thirdPartyComponents))
        .filter((c): c is FullSyntaxNode => c !== null);
      return {
        id: generateId("frag"),
        kind: "fragment",
        children,
      };
    }
    if (/^[A-Z]/.test(tag)) {
      thirdPartyComponents.add(tag);
    }
    const attrs = parseJsxAttributes(opening.attributes, sourceFile);
    const events = extractJsxEvents(opening.attributes, sourceFile);
    const children = node.children
      .map((c) => parseJsxNode(c, sourceFile, generateId, containerApis, thirdPartyComponents))
      .filter((c): c is FullSyntaxNode => c !== null);

    return {
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children,
    };
  }

  if (ts.isJsxSelfClosingElement(node)) {
    const tag = node.tagName.getText(sourceFile);
    if (tag.endsWith('.Provider') || tag.endsWith('.Consumer')) {
      return {
        id: generateId("frag"),
        kind: "fragment",
        children: [],
      };
    }
    if (/^[A-Z]/.test(tag)) {
      thirdPartyComponents.add(tag);
    }
    const attrs = parseJsxAttributes(node.attributes, sourceFile);
    const events = extractJsxEvents(node.attributes, sourceFile);

    return {
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children: [],
    };
  }

  if (ts.isJsxFragment(node)) {
    const children = node.children
      .map((c) => parseJsxNode(c, sourceFile, generateId, containerApis, thirdPartyComponents))
      .filter((c): c is FullSyntaxNode => c !== null);
    return {
      id: generateId("frag"),
      kind: "fragment",
      children,
    };
  }

  if (ts.isJsxText(node)) {
    const raw = (node as any).text !== undefined ? (node as any).text : node.getText(sourceFile);
    if (/^\s*[\r\n]+\s*$/.test(raw)) {
      return null;
    }
    const text = raw.replace(/[\r\n]+/g, " ").replace(/[ \t]+/g, " ");
    if (!text.trim()) {
      return null;
    }
    return {
      id: generateId("text"),
      kind: "text",
      text,
    };
  }

  return {
    id: generateId("expr"),
    kind: "expression",
    expression: node.getText(sourceFile),
  };
}

function parseJsxAttributes(attrs: ts.JsxAttributes, sourceFile: ts.SourceFile): FullSyntaxAttr[] {
  const result: FullSyntaxAttr[] = [];
  for (const prop of attrs.properties) {
    if (ts.isJsxAttribute(prop) && prop.name) {
      const attrName = ts.isIdentifier(prop.name) ? prop.name.text : prop.name.name.text;
      if (attrName.startsWith("on")) continue; // Handled separately as events

      let attrVal = "";
      let isDynamic = false;
      let expression: string | undefined;

      if (!prop.initializer) {
        attrVal = "true";
      } else if (ts.isStringLiteral(prop.initializer)) {
        attrVal = prop.initializer.text;
      } else if (ts.isJsxExpression(prop.initializer) && prop.initializer.expression) {
        isDynamic = true;
        expression = prop.initializer.expression.getText(sourceFile);
        attrVal = expression;
      }

      result.push({
        name: attrName === "className" ? "class" : attrName,
        value: attrVal,
        isDynamic,
        expression,
      });
    }
  }
  return result;
}

function extractJsxEvents(attrs: ts.JsxAttributes, sourceFile: ts.SourceFile): FullSyntaxEvent[] {
  const events: FullSyntaxEvent[] = [];
  for (const prop of attrs.properties) {
    if (ts.isJsxAttribute(prop) && prop.name) {
      const rawName = ts.isIdentifier(prop.name) ? prop.name.text : prop.name.name.text;
      if (rawName.startsWith("on")) {
        const eventName = rawName.slice(2).toLowerCase(); // 'onClick' -> 'click'
        let handler = "";
        if (prop.initializer && ts.isJsxExpression(prop.initializer) && prop.initializer.expression) {
          handler = prop.initializer.expression.getText(sourceFile);
        }
        events.push({
          name: eventName,
          handlerNameOrExpr: handler,
        });
      }
    }
  }
  return events;
}

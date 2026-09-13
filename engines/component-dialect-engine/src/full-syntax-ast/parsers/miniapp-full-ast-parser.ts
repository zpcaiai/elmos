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

export interface MiniAppFiles {
  wxml: string;
  js: string;
  wxss?: string;
  json?: string;
}

export class MiniAppFullAstParser {
  public parse(filesOrJs: MiniAppFiles | string, componentNameHint?: string): FullSyntaxComponentIR {
    const files: MiniAppFiles = typeof filesOrJs === "string" ? { wxml: "", js: filesOrJs } : filesOrJs;
    const compName = componentNameHint || "MiniProgramComponent";

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

    // Parse JS/TS Component definition
    if (files.js) {
      const scriptSource = ts.createSourceFile("component.js", files.js, ts.ScriptTarget.Latest, true);

      const visit = (node: ts.Node) => {
        // Component({ ... }) or Page({ ... })
        if (ts.isCallExpression(node)) {
          const callee = node.expression.getText(scriptSource);
          if ((callee === "Component" || callee === "Page") && node.arguments[0] && ts.isObjectLiteralExpression(node.arguments[0])) {
            const configObj = node.arguments[0];

            for (const prop of configObj.properties) {
              if (!ts.isPropertyAssignment(prop) && !ts.isMethodDeclaration(prop)) continue;
              const pName = prop.name.getText(scriptSource);

              // properties: { title: { type: String, value: '' } }
              if (pName === "properties" && ts.isPropertyAssignment(prop) && ts.isObjectLiteralExpression(prop.initializer)) {
                for (const p of prop.initializer.properties) {
                  if (ts.isPropertyAssignment(p)) {
                    const name = p.name.getText(scriptSource);
                    let typeAnnotation = "any";
                    let defVal: string | undefined;

                    if (ts.isObjectLiteralExpression(p.initializer)) {
                      for (const field of p.initializer.properties) {
                        if (ts.isPropertyAssignment(field)) {
                          const fName = field.name.getText(scriptSource);
                          if (fName === "type") typeAnnotation = field.initializer.getText(scriptSource);
                          if (fName === "value") defVal = field.initializer.getText(scriptSource);
                        }
                      }
                    } else {
                      typeAnnotation = p.initializer.getText(scriptSource);
                    }

                    props.push({
                      name,
                      typeAnnotation: mapWxType(typeAnnotation),
                      required: false,
                      defaultValue: defVal,
                      isCallback: name.startsWith("on") || name.startsWith("bind"),
                    });
                  }
                }
              }

              // data: { ... }
              if (pName === "data" && ts.isPropertyAssignment(prop) && ts.isObjectLiteralExpression(prop.initializer)) {
                for (const d of prop.initializer.properties) {
                  if (ts.isPropertyAssignment(d)) {
                    states.push({
                      name: d.name.getText(scriptSource),
                      initialValueExpr: d.initializer.getText(scriptSource),
                      typeAnnotation: "any",
                    });
                  }
                }
              }

              // methods: { ... }
              if (pName === "methods" && ts.isPropertyAssignment(prop) && ts.isObjectLiteralExpression(prop.initializer)) {
                for (const m of prop.initializer.properties) {
                  if (ts.isMethodDeclaration(m) || (ts.isPropertyAssignment(m) && ts.isFunctionExpression(m.initializer))) {
                    const mName = m.name?.getText(scriptSource) || "";
                    const fn = ts.isMethodDeclaration(m) ? m : (m.initializer as ts.FunctionExpression);
                    methods.push({
                      name: mName,
                      parameters: fn.parameters.map((p) => ({ name: p.name.getText(scriptSource), type: "any" })),
                      returnType: "any",
                      bodyCode: fn.body ? fn.body.getText(scriptSource) : "",
                      isAsync: false,
                    });
                  }
                }
              }

              // lifetimes: { attached, detached }
              if (pName === "lifetimes" && ts.isPropertyAssignment(prop) && ts.isObjectLiteralExpression(prop.initializer)) {
                for (const lf of prop.initializer.properties) {
                  const lfName = lf.name?.getText(scriptSource) || "";
                  if (lfName === "attached") {
                    effects.push({
                      id: generateId("attached"),
                      hookKind: "mount",
                      dependencies: [],
                      bodyCode: lf.getText(scriptSource),
                      hasCleanup: false,
                    });
                  } else if (lfName === "detached") {
                    effects.push({
                      id: generateId("detached"),
                      hookKind: "unmount",
                      dependencies: [],
                      bodyCode: lf.getText(scriptSource),
                      hasCleanup: false,
                    });
                  }
                }
              }
            }
          }
        }

        ts.forEachChild(node, visit);
      };

      visit(scriptSource);
    }

    // Parse WXML
    let templateRoot: FullSyntaxNode = { id: generateId("root"), kind: "fragment", children: [] };
    if (files.wxml) {
      templateRoot = parseWxml(files.wxml, generateId, thirdPartyComponents, slots);
    }

    return {
      schemaVersion: "2.0",
      componentName: compName,
      sourceFramework: "miniprogram",
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot,
      styles: {
        scopedCss: files.wxss || "",
      },
      containerApis: Array.from(containerApis),
      thirdPartyComponents: Array.from(thirdPartyComponents),
      rawSourceLinesCount: (files.js + "\n" + files.wxml).split("\n").length,
      metadata: {},
    };
  }
}

function mapWxType(wxType: string): string {
  if (wxType === "String") return "string";
  if (wxType === "Number") return "number";
  if (wxType === "Boolean") return "boolean";
  if (wxType === "Array") return "any[]";
  if (wxType === "Object") return "Record<string, any>";
  return "any";
}

function parseWxml(
  wxml: string,
  generateId: (prefix?: string) => string,
  thirdPartyComponents: Set<string>,
  slots: FullSyntaxSlot[]
): FullSyntaxNode {
  if (!wxml.trim()) return { id: generateId("frag"), kind: "fragment", children: [] };

  const tagRegex = /<([a-zA-Z0-9_-]+)([^>]*)>([\s\S]*?)<\/\1>|<([a-zA-Z0-9_-]+)([^>]*)\/>/g;
  const children: FullSyntaxNode[] = [];
  let match: RegExpExecArray | null;

  while ((match = tagRegex.exec(wxml)) !== null) {
    const tag = (match[1] || match[4] || "view").toLowerCase();
    const rawAttrs = match[2] || match[5] || "";
    const inner = match[3] || "";

    if (tag === "slot") {
      const nameMatch = rawAttrs.match(/name="([^"]*)"/);
      const slotName = nameMatch && nameMatch[1] ? nameMatch[1] : "default";
      slots.push({ name: slotName, slotProps: [], fallbackNodes: [] });
      children.push({ id: generateId("slot"), kind: "slot_outlet", slotName });
      continue;
    }

    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];
    let wxIf: string | undefined;
    let wxFor: string | undefined;
    let wxKey: string | undefined;

    const attrRegex = /([a-zA-Z0-9_:-]+)(?:="([^"]*)")?/g;
    let aMatch: RegExpExecArray | null;
    while ((aMatch = attrRegex.exec(rawAttrs)) !== null) {
      const aName = aMatch[1];
      if (!aName) continue;
      const aVal = aMatch[2] || "";

      if (aName === "wx:if") {
        wxIf = aVal.replace(/^\{\{|\}\}$/g, "").trim();
      } else if (aName === "wx:for") {
        wxFor = aVal.replace(/^\{\{|\}\}$/g, "").trim();
      } else if (aName === "wx:key") {
        wxKey = aVal;
      } else if (aName.startsWith("bind") || aName.startsWith("catch")) {
        const ev = aName.replace(/^(bind|catch):?/, "");
        events.push({ name: ev.toLowerCase(), handlerNameOrExpr: aVal });
      } else {
        const isDynamic = aVal.includes("{{");
        attrs.push({
          name: aName,
          value: aVal,
          isDynamic,
          expression: isDynamic ? aVal.replace(/^\{\{|\}\}$/g, "").trim() : undefined,
        });
      }
    }

    const elemChildren = parseWxml(inner, generateId, thirdPartyComponents, slots);
    const elemNode: FullSyntaxNode = {
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children: elemChildren.children || (elemChildren.kind === "text" ? [elemChildren] : []),
    };

    if (wxFor) {
      children.push({
        id: generateId("loop"),
        kind: "loop",
        loop: {
          sourceExpr: wxFor,
          itemName: "item",
          keyExpr: wxKey,
          bodyNode: elemNode,
        },
      });
    } else if (wxIf) {
      children.push({
        id: generateId("cond"),
        kind: "conditional",
        condition: {
          test: wxIf,
          thenNode: elemNode,
        },
      });
    } else {
      children.push(elemNode);
    }
  }

  if (children.length === 0 && wxml.trim()) {
    const textContent = wxml.replace(/<[^>]+>/g, "").replace(/\{\{[\s\S]*?\}\}/g, "").trim();
    if (textContent) children.push({ id: generateId("text"), kind: "text", text: textContent });

    const exprRegex = /\{\{([\s\S]*?)\}\}/g;
    let eMatch: RegExpExecArray | null;
    while ((eMatch = exprRegex.exec(wxml)) !== null) {
      const expr = (eMatch[1] || "").trim();
      children.push({ id: generateId("expr"), kind: "expression", expression: expr });
    }
  }

  return { id: generateId("frag"), kind: "fragment", children };
}

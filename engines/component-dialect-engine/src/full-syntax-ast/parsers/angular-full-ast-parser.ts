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

export class AngularFullAstParser {
  public parse(sourceCode: string, componentNameHint?: string): FullSyntaxComponentIR {
    const sourceFile = ts.createSourceFile("component.ts", sourceCode, ts.ScriptTarget.Latest, true);

    let compName = componentNameHint || "AngularComponent";
    let templateSource = "";
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

    const visit = (node: ts.Node) => {
      // Look for @Component decorator
      if (ts.isClassDeclaration(node)) {
        if (node.name) compName = node.name.text;

        const decorators = ts.getDecorators ? ts.getDecorators(node) : [];
        for (const dec of decorators || []) {
          if (ts.isCallExpression(dec.expression)) {
            const decName = dec.expression.expression.getText(sourceFile);
            if (decName === "Component") {
              const arg = dec.expression.arguments[0];
              if (arg && ts.isObjectLiteralExpression(arg)) {
                for (const p of arg.properties) {
                  if (ts.isPropertyAssignment(p) && p.name.getText(sourceFile) === "template") {
                    if (ts.isStringLiteral(p.initializer) || ts.isNoSubstitutionTemplateLiteral(p.initializer)) {
                      templateSource = p.initializer.text;
                    }
                  }
                }
              }
            }
          }
        }

        // Walk class members
        for (const member of node.members) {
          if (ts.isPropertyDeclaration(member) && member.name) {
            const propName = member.name.getText(sourceFile);
            const propType = member.type ? member.type.getText(sourceFile) : "any";
            const memberDecorators = ts.getDecorators ? ts.getDecorators(member) : [];
            const isInput = memberDecorators?.some((d) => d.getText(sourceFile).includes("@Input"));
            const isOutput = memberDecorators?.some((d) => d.getText(sourceFile).includes("@Output"));

            if (isInput) {
              props.push({
                name: propName,
                typeAnnotation: propType,
                required: !member.questionToken,
                isCallback: false,
              });
            } else if (isOutput) {
              props.push({
                name: propName,
                typeAnnotation: propType,
                required: true,
                isCallback: true,
              });
            } else {
              states.push({
                name: propName,
                initialValueExpr: member.initializer ? member.initializer.getText(sourceFile) : "null",
                typeAnnotation: propType,
              });
            }
          } else if (ts.isMethodDeclaration(member) && member.name) {
            const mName = member.name.getText(sourceFile);
            if (mName === "ngOnInit") {
              effects.push({
                id: generateId("effect"),
                hookKind: "mount",
                dependencies: [],
                bodyCode: member.body ? member.body.getText(sourceFile) : "",
                hasCleanup: false,
              });
            } else if (mName === "ngOnDestroy") {
              effects.push({
                id: generateId("effect"),
                hookKind: "unmount",
                dependencies: [],
                bodyCode: member.body ? member.body.getText(sourceFile) : "",
                hasCleanup: false,
              });
            } else {
              methods.push({
                name: mName,
                parameters: member.parameters.map((p) => ({
                  name: p.name.getText(sourceFile),
                  type: p.type ? p.type.getText(sourceFile) : "any",
                })),
                returnType: member.type ? member.type.getText(sourceFile) : "void",
                bodyCode: member.body ? member.body.getText(sourceFile) : "",
                isAsync: !!(member.modifiers && member.modifiers.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword)),
              });
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    // Parse template markup
    const templateRoot = parseAngularTemplate(templateSource, generateId, thirdPartyComponents, slots);

    return {
      schemaVersion: "2.0",
      componentName: compName,
      sourceFramework: "angular",
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot,
      styles: {},
      containerApis: Array.from(containerApis),
      thirdPartyComponents: Array.from(thirdPartyComponents),
      rawSourceLinesCount: sourceCode.split("\n").length,
      metadata: {},
    };
  }
}

function parseAngularTemplate(
  templateHtml: string,
  generateId: (prefix?: string) => string,
  thirdPartyComponents: Set<string>,
  slots: FullSyntaxSlot[]
): FullSyntaxNode {
  if (!templateHtml.trim()) {
    return { id: generateId("frag"), kind: "fragment", children: [] };
  }

  // Regex-based recursive or linear tokenization of Angular HTML
  const tagRegex = /<([a-zA-Z0-9_-]+)([^>]*)>([\s\S]*?)<\/\1>|<([a-zA-Z0-9_-]+)([^>]*)\/>/g;
  const children: FullSyntaxNode[] = [];
  let match: RegExpExecArray | null;

  while ((match = tagRegex.exec(templateHtml)) !== null) {
    const tag = (match[1] || match[4] || "div").toLowerCase();
    const rawAttrs = match[2] || match[5] || "";
    const inner = match[3] || "";

    if (tag === "ng-content") {
      slots.push({ name: "default", slotProps: [], fallbackNodes: [] });
      children.push({ id: generateId("slot"), kind: "slot_outlet", slotName: "default" });
      continue;
    }

    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];
    let ngIfCondition: string | undefined;
    let ngForExpr: string | undefined;

    // Parse attributes: *ngIf, *ngFor, [prop], (event), static
    const attrRegex = /([*\[\(]?[a-zA-Z0-9_-]+[\)\]]?)(?:="([^"]*)")?/g;
    let aMatch: RegExpExecArray | null;
    while ((aMatch = attrRegex.exec(rawAttrs)) !== null) {
      const aName = aMatch[1];
      if (!aName) continue;
      const aVal = aMatch[2] || "";

      if (aName === "*ngIf") {
        ngIfCondition = aVal;
      } else if (aName === "*ngFor") {
        ngForExpr = aVal;
      } else if (aName.startsWith("(") && aName.endsWith(")")) {
        const ev = aName.slice(1, -1);
        events.push({ name: ev.toLowerCase(), handlerNameOrExpr: aVal });
      } else if (aName.startsWith("[") && aName.endsWith("]")) {
        const prop = aName.slice(1, -1);
        attrs.push({ name: prop, value: aVal, isDynamic: true, expression: aVal });
      } else {
        attrs.push({ name: aName, value: aVal, isDynamic: false });
      }
    }

    const elemChildren = parseAngularTemplate(inner, generateId, thirdPartyComponents, slots);
    const elemNode: FullSyntaxNode = {
      id: generateId("elem"),
      kind: /^[A-Z]/.test(tag) ? "component" : "element",
      tag,
      attrs,
      events,
      children: elemChildren.children || (elemChildren.kind === "text" ? [elemChildren] : []),
    };

    if (ngForExpr) {
      // *ngFor="let item of items"
      const forMatch = ngForExpr.match(/let\s+([a-zA-Z0-9_]+)\s+of\s+([a-zA-Z0-9_.]+)/);
      const itemName = (forMatch && forMatch[1]) ? forMatch[1] : "item";
      const sourceExpr = (forMatch && forMatch[2]) ? forMatch[2] : "items";
      children.push({
        id: generateId("loop"),
        kind: "loop",
        loop: {
          sourceExpr,
          itemName,
          bodyNode: elemNode,
        },
      });
    } else if (ngIfCondition) {
      children.push({
        id: generateId("cond"),
        kind: "conditional",
        condition: {
          test: ngIfCondition,
          thenNode: elemNode,
        },
      });
    } else {
      children.push(elemNode);
    }
  }

  // Handle plain text if no tags matched
  if (children.length === 0 && templateHtml.trim()) {
    const textContent = templateHtml.replace(/{{([\s\S]*?)}}/g, "").trim();
    if (textContent) {
      children.push({ id: generateId("text"), kind: "text", text: textContent });
    }
    const exprRegex = /{{([\s\S]*?)}}/g;
    let eMatch: RegExpExecArray | null;
    while ((eMatch = exprRegex.exec(templateHtml)) !== null) {
      const expr = (eMatch[1] || "").trim();
      children.push({ id: generateId("expr"), kind: "expression", expression: expr });
    }
  }

  return { id: generateId("frag"), kind: "fragment", children };
}

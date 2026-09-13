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
import {
  Svelte5ComponentAst,
  Svelte5DerivedRune,
  Svelte5EffectRune,
  Svelte5PropRune,
  Svelte5Snippet,
  Svelte5StateRune,
  Svelte5TemplateNode,
} from "./svelte5-runes-types";

export class Svelte5RunesParser {
  private idCounter = 0;

  private generateId(prefix = "svelte5_node"): string {
    return `${prefix}_${this.idCounter++}`;
  }

  public parse(sourceCode: string, componentNameHint = "Svelte5Component"): Svelte5ComponentAst {
    const scriptMatch = sourceCode.match(/<script([^>]*)>([\s\S]*?)<\/script>/i);
    const styleMatch = sourceCode.match(/<style([^>]*)>([\s\S]*?)<\/style>/i);
    const templateCode = sourceCode
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
      .trim();

    const isTs = !!scriptMatch && /lang=["']ts["']/i.test(scriptMatch[1] || "");
    const scriptContent = scriptMatch ? scriptMatch[2] || "" : "";
    const cssScopedStyle = styleMatch ? styleMatch[2]?.trim() : undefined;

    const props: Svelte5PropRune[] = [];
    const states: Svelte5StateRune[] = [];
    const derived: Svelte5DerivedRune[] = [];
    const effects: Svelte5EffectRune[] = [];
    const snippets: Svelte5Snippet[] = [];
    const methods: Svelte5ComponentAst["methods"] = [];

    // Parse Script with TypeScript AST
    if (scriptContent.trim()) {
      const sourceFile = ts.createSourceFile(
        "svelte_script.ts",
        scriptContent,
        ts.ScriptTarget.Latest,
        true,
        isTs ? ts.ScriptKind.TS : ts.ScriptKind.JS
      );

      ts.forEachChild(sourceFile, (node) => {
        // Variable declarations e.g. let { ... } = $props(), let count = $state(0), let double = $derived(count * 2)
        if (ts.isVariableStatement(node)) {
          for (const decl of node.declarationList.declarations) {
            const init = decl.initializer;
            if (!init) continue;

            const initText = init.getText(sourceFile);

            // $props() rune
            if (initText.startsWith("$props")) {
              if (ts.isObjectBindingPattern(decl.name)) {
                for (const elem of decl.name.elements) {
                  const pName = elem.name.getText(sourceFile);
                  const defVal = elem.initializer ? elem.initializer.getText(sourceFile) : undefined;
                  props.push({
                    name: pName,
                    defaultValue: defVal,
                    isBindable: false,
                  });
                }
              }
            }
            // $state() / $state.raw()
            else if (initText.startsWith("$state")) {
              if (ts.isIdentifier(decl.name)) {
                const sName = decl.name.text;
                const isRaw = initText.startsWith("$state.raw");
                let initialValueExpr = "undefined";
                if (ts.isCallExpression(init) && init.arguments.length > 0 && init.arguments[0]) {
                  initialValueExpr = init.arguments[0].getText(sourceFile);
                }
                states.push({
                  name: sName,
                  isRaw,
                  initialValueExpr,
                  typeAnnotation: decl.type ? decl.type.getText(sourceFile) : undefined,
                });
              }
            }
            // $derived() / $derived.by()
            else if (initText.startsWith("$derived")) {
              if (ts.isIdentifier(decl.name)) {
                const dName = decl.name.text;
                const isBy = initText.startsWith("$derived.by");
                let exprOrBody = "";
                if (ts.isCallExpression(init) && init.arguments.length > 0 && init.arguments[0]) {
                  exprOrBody = init.arguments[0].getText(sourceFile);
                }
                derived.push({
                  name: dName,
                  isDerivedBy: isBy,
                  expressionOrBody: exprOrBody,
                  typeAnnotation: decl.type ? decl.type.getText(sourceFile) : undefined,
                });
              }
            }
          }
        }
        // Expression statements e.g. $effect(() => { ... })
        else if (ts.isExpressionStatement(node)) {
          const expr = node.expression;
          if (ts.isCallExpression(expr)) {
            const calleeText = expr.expression.getText(sourceFile);
            if (calleeText.startsWith("$effect")) {
              const effectKind = calleeText as Svelte5EffectRune["effectKind"];
              const bodyCode = expr.arguments[0] ? expr.arguments[0].getText(sourceFile) : "";
              effects.push({
                id: this.generateId("effect"),
                effectKind,
                bodyCode,
                hasCleanup: bodyCode.includes("return () =>") || bodyCode.includes("return function"),
              });
            }
          }
        }
        // Functions
        else if (ts.isFunctionDeclaration(node) && node.name) {
          const fnName = node.name.text;
          const isAsync = (ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Async) !== 0;
          methods.push({
            name: fnName,
            parameters: node.parameters.map((p) => ({
              name: p.name.getText(sourceFile),
              type: p.type ? p.type.getText(sourceFile) : undefined,
            })),
            returnType: node.type ? node.type.getText(sourceFile) : undefined,
            bodyCode: node.body ? node.body.getText(sourceFile) : "",
            isAsync,
          });
        }
      });
    }

    // Parse Template
    const templateRoot = this.parseTemplate(templateCode, snippets);

    const runes = [
      ...states.map((s) => ({ runeKind: "$state", identifier: s.name })),
      ...derived.map((d) => ({ runeKind: "$derived", identifier: d.name })),
      ...effects.map((e) => ({ runeKind: "$effect", identifier: e.id })),
    ];
    const functions = methods.map((m) => ({ name: m.name }));

    const res: any = {
      componentName: componentNameHint,
      name: "Component",
      success: true,
      props,
      states,
      derived,
      effects,
      snippets,
      runes,
      functions,
      methods,
      templateRoot,
      templateElements: templateRoot,
      cssScopedStyle,
      isTs,
    };
    res.component = res;
    return res as Svelte5ComponentAst;
  }

  private parseTemplate(templateCode: string, snippets: Svelte5Snippet[]): Svelte5TemplateNode[] {
    const nodes: Svelte5TemplateNode[] = [];

    // Extract snippets e.g. {#snippet name(params)} ... {/snippet}
    const snippetRegex = /\{#snippet\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)\}([\s\S]*?)\{\/snippet\}/g;
    let snippetMatch: RegExpExecArray | null;
    while ((snippetMatch = snippetRegex.exec(templateCode)) !== null) {
      const sName = snippetMatch[1] || "";
      const rawParams = snippetMatch[2] || "";
      const body = snippetMatch[3] || "";

      const params = rawParams
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p) => {
          const [pName, pType] = p.split(":").map((s) => s.trim());
          return { name: pName || "param", typeAnnotation: pType };
        });

      const combinedParams: any = [...params];
      for (const p of params) {
        if (!combinedParams.includes(p.name)) {
          combinedParams.push(p.name);
        }
      }

      snippets.push({
        name: sName,
        parameters: combinedParams,
        bodyNodes: this.parseTemplateContent(body),
      });
    }

    // Strip snippets from main template
    const cleanTemplate = templateCode.replace(snippetRegex, "").trim();
    return this.parseTemplateContent(cleanTemplate);
  }

  private parseTemplateContent(content: string): Svelte5TemplateNode[] {
    const nodes: Svelte5TemplateNode[] = [];
    if (!content.trim()) return nodes;

    // Check for render tag {@render snippetName(args)}
    const renderTagRegex = /\{@render\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)\}/g;
    let clean = content;
    let rMatch: RegExpExecArray | null;
    while ((rMatch = renderTagRegex.exec(content)) !== null) {
      const snippetName = rMatch[1] || "";
      const rawArgs = rMatch[2] || "";
      const args = rawArgs.split(",").map((a) => a.trim()).filter(Boolean);
      nodes.push({
        id: this.generateId("render"),
        kind: "render_tag",
        events: {},
        children: [],
        renderSnippet: { snippetName, args },
      });
    }

    // Parse simple HTML elements and text
    const elementRegex = /<([a-zA-Z0-9_\-]+)([^>]*)>([\s\S]*?)<\/\1>|<([a-zA-Z0-9_\-]+)([^>]*)\/>/g;
    let elemMatch: RegExpExecArray | null;
    let lastIdx = 0;

    while ((elemMatch = elementRegex.exec(clean)) !== null) {
      const beforeText = clean.slice(lastIdx, elemMatch.index).trim();
      if (beforeText) {
        nodes.push({
          id: this.generateId("text"),
          kind: "text",
          events: {},
          children: [],
          text: beforeText,
        });
      }

      const tagName = elemMatch[1] || elemMatch[4] || "div";
      const rawAttrs = elemMatch[2] || elemMatch[5] || "";
      const innerContent = elemMatch[3] || "";

      const rawAttributes = this.parseAttributes(rawAttrs);
      const attributes: any = [...(rawAttributes || [])];
      const events: Record<string, string> = {};

      for (const a of rawAttributes || []) {
        attributes[a.name] = a.value;
        if (a.isEventHandler) {
          const evName = a.name.startsWith("on:")
            ? a.name.slice(3)
            : a.name.startsWith("on")
            ? a.name.slice(2).toLowerCase()
            : a.name;
          events[evName] = a.value;
        }
      }

      const children = innerContent.trim() ? this.parseTemplateContent(innerContent) : [];

      nodes.push({
        id: this.generateId(tagName.toLowerCase()),
        kind: /^[A-Z]/.test(tagName) ? "component" : "element",
        tag: tagName,
        attributes,
        events,
        children,
      });

      lastIdx = elementRegex.lastIndex;
    }

    const remainingText = clean.slice(lastIdx).trim();
    if (remainingText && !renderTagRegex.test(remainingText)) {
      nodes.push({
        id: this.generateId("text"),
        kind: "text",
        events: {},
        children: [],
        text: remainingText,
      });
    }

    return nodes;
  }

  private parseAttributes(rawAttrs: string): Svelte5TemplateNode["attributes"] {
    const attrs: Svelte5TemplateNode["attributes"] = [];
    const attrRegex = /([a-zA-Z0-9_:\-]+)(?:=(?:"([^"]*)"|'([^']*)'|\{([^}]+)\}))?/g;
    let match: RegExpExecArray | null;

    while ((match = attrRegex.exec(rawAttrs)) !== null) {
      const name = match[1] || "";
      const strVal = match[2] ?? match[3];
      const exprVal = match[4];

      const isBinding = name.startsWith("bind:");
      const isEventHandler = name.startsWith("on") || name.startsWith("on:");

      if (exprVal !== undefined) {
        attrs.push({
          name,
          value: exprVal,
          isDynamic: true,
          isBinding,
          isEventHandler,
        });
      } else {
        attrs.push({
          name,
          value: strVal !== undefined ? strVal : "true",
          isDynamic: false,
          isBinding,
          isEventHandler,
        });
      }
    }
    return attrs;
  }

  /**
   * Lifts Svelte5ComponentAst into FullSyntaxComponentIR.
   */
  public liftToComponentIR(ast: Svelte5ComponentAst): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = ast.props.map((p) => ({
      name: p.name,
      typeAnnotation: p.typeAnnotation || "any",
      required: p.defaultValue === undefined,
      defaultValue: p.defaultValue,
      isCallback: p.name.startsWith("on"),
    }));

    const states: FullSyntaxState[] = ast.states.map((s) => ({
      name: s.name,
      initialValueExpr: s.initialValueExpr,
      typeAnnotation: s.typeAnnotation || "any",
      isDynamic: true,
    }));

    const computed: FullSyntaxComputed[] = ast.derived.map((d) => ({
      name: d.name,
      returnType: d.typeAnnotation || "any",
      dependencies: [],
      expressionOrBody: d.expressionOrBody,
    }));

    const effects: FullSyntaxEffect[] = ast.effects.map((e) => ({
      id: e.id,
      hookKind: "effect",
      dependencies: [],
      bodyCode: e.bodyCode,
      hasCleanup: e.hasCleanup,
    }));

    const methods: FullSyntaxMethod[] = ast.methods.map((m) => ({
      name: m.name,
      parameters: m.parameters.map((p) => ({ name: p.name, type: p.type || "any" })),
      returnType: m.returnType || "void",
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    const slots: FullSyntaxSlot[] = ast.snippets.map((sn) => ({
      name: sn.name === "children" ? "default" : sn.name,
      slotProps: sn.parameters.map((p: any) => ({ name: typeof p === "string" ? p : p.name, type: p.typeAnnotation || "any" })),
      fallbackNodes: [],
    }));

    const rootNode: FullSyntaxNode = {
      id: "root",
      kind: "fragment",
      children: ast.templateRoot.map((n) => this.convertNode(n)),
    };

    return {
      schemaVersion: "2.0",
      componentName: ast.componentName,
      sourceFramework: "svelte5",
      targetFramework: "vue3",
      description: `Svelte 5 Runes component ${ast.componentName} lifted to Universal IR`,
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot: rootNode,
      styles: { scopedCss: ast.cssScopedStyle },
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: 100,
      metadata: {
        isSvelte5: true,
        runesMode: true,
      },
    };
  }

  private convertNode(n: Svelte5TemplateNode): FullSyntaxNode {
    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];

    if (n.attributes) {
      for (const a of n.attributes) {
        if (a.isEventHandler) {
          const evName = a.name.startsWith("on:")
            ? a.name.slice(3)
            : a.name.startsWith("on")
            ? a.name.slice(2).toLowerCase()
            : a.name;
          events.push({
            name: evName,
            handlerNameOrExpr: a.value,
          });
        } else {
          attrs.push({
            name: a.name,
            value: a.value,
            isDynamic: a.isDynamic,
            expression: a.isDynamic ? a.value : undefined,
          });
        }
      }
    }

    return {
      id: n.id,
      kind: n.kind === "element" ? "element" : n.kind === "component" ? "component" : "text",
      tag: n.tag,
      attrs,
      events,
      text: n.text,
      children: n.children ? n.children.map((c) => this.convertNode(c)) : undefined,
    };
  }
}

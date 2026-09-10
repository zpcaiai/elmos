import {
  FullSyntaxComponentIR,
  FullSyntaxComputed,
  FullSyntaxEffect,
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

export class Svelte5SemanticLowering {
  private idCounter = 0;

  private generateId(prefix = "svelte_lower"): string {
    return `${prefix}_${this.idCounter++}`;
  }

  public lowerToSvelte5(ir: FullSyntaxComponentIR): Svelte5ComponentAst {
    const props: Svelte5PropRune[] = ir.props.map((p) => ({
      name: p.name,
      typeAnnotation: p.typeAnnotation,
      defaultValue: p.defaultValue !== undefined ? JSON.stringify(p.defaultValue) : undefined,
      isBindable: p.name.startsWith("model") || p.name.endsWith("Value"),
    }));

    const states: Svelte5StateRune[] = ir.states.map((s) => ({
      name: s.name,
      isRaw: false,
      initialValueExpr: s.initialValueExpr || "undefined",
      typeAnnotation: s.typeAnnotation,
    }));

    const derived: Svelte5DerivedRune[] = ir.computed.map((c) => ({
      name: c.name,
      isDerivedBy: c.expressionOrBody.includes("return "),
      expressionOrBody: c.expressionOrBody,
      typeAnnotation: c.returnType,
    }));

    const effects: Svelte5EffectRune[] = ir.effects.map((e) => ({
      id: e.id,
      effectKind: "$effect",
      bodyCode: e.bodyCode,
      hasCleanup: e.hasCleanup,
      cleanupCode: e.cleanupCode,
    }));

    const snippets: Svelte5Snippet[] = ir.slots.map((s) => ({
      name: s.name === "default" ? "children" : s.name,
      parameters: s.slotProps.map((sp) => ({ name: sp.name, typeAnnotation: sp.type })),
      bodyNodes: s.fallbackNodes.map((fn) => this.convertFullSyntaxNodeToSvelte(fn)),
    }));

    const methods = ir.methods.map((m) => ({
      name: m.name,
      parameters: m.parameters,
      returnType: m.returnType,
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    const templateRoot: Svelte5TemplateNode[] = ir.templateRoot
      ? [this.convertFullSyntaxNodeToSvelte(ir.templateRoot)]
      : [];

    const runes = [
      ...states.map((s) => ({ runeKind: "$state", identifier: s.name })),
      ...derived.map((d) => ({ runeKind: "$derived", identifier: d.name })),
      ...effects.map((e) => ({ runeKind: "$effect", identifier: e.id })),
    ];
    const functions = methods.map((m) => ({ name: m.name }));

    const res: any = {
      componentName: ir.componentName,
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
      cssScopedStyle: ir.styles?.scopedCss,
      isTs: true,
    };
    res.component = res;
    return res as Svelte5ComponentAst;
  }

  private convertFullSyntaxNodeToSvelte(node: FullSyntaxNode): Svelte5TemplateNode {
    const rawAttrs = (node.attrs || []).map((a) => ({
      name: a.name,
      value: a.expression || a.value,
      isDynamic: a.isDynamic,
    }));

    const attributes: any = [...rawAttrs];
    const events: Record<string, string> = {};

    if (node.events) {
      for (const ev of node.events) {
        attributes.push({
          name: `on${ev.name}`,
          value: ev.handlerNameOrExpr,
          isDynamic: true,
          isEventHandler: true,
        });
        events[ev.name] = ev.handlerNameOrExpr;
      }
    }

    let ifBlock: Svelte5TemplateNode["ifBlock"];
    if (node.condition) {
      ifBlock = {
        testExpr: node.condition.test,
        consequent: [this.convertFullSyntaxNodeToSvelte(node.condition.thenNode)],
        alternate: node.condition.elseNode
          ? [this.convertFullSyntaxNodeToSvelte(node.condition.elseNode)]
          : undefined,
        elseIfBranches: node.condition.elifBranches
          ? node.condition.elifBranches.map((b) => ({
              testExpr: b.test,
              consequent: [this.convertFullSyntaxNodeToSvelte(b.node)],
            }))
          : undefined,
      };
    }

    let eachBlock: Svelte5TemplateNode["eachBlock"];
    if (node.loop) {
      eachBlock = {
        sourceExpr: node.loop.sourceExpr,
        itemName: node.loop.itemName,
        indexName: node.loop.indexName,
        keyExpr: node.loop.keyExpr,
        body: [this.convertFullSyntaxNodeToSvelte(node.loop.bodyNode)],
      };
    }

    const children = (node.children || []).map((c) => this.convertFullSyntaxNodeToSvelte(c));

    return {
      id: node.id || this.generateId("node"),
      kind: node.kind === "text" ? "text" : node.tag && /^[A-Z]/.test(node.tag) ? "component" : "element",
      tag: node.tag,
      attributes,
      events,
      text: node.text,
      expression: node.expression,
      ifBlock,
      eachBlock,
      children,
    };
  }

  public liftToUniversal(ast: Svelte5ComponentAst): FullSyntaxComponentIR & { stateVariables: FullSyntaxState[] } {
    const props: FullSyntaxProp[] = ast.props.map((p) => ({
      name: p.name,
      typeAnnotation: p.typeAnnotation || "any",
      required: !p.defaultValue,
      defaultValue: p.defaultValue,
      isCallback: false,
    }));

    const states: FullSyntaxState[] = ast.states.map((s) => ({
      name: s.name,
      initialValueExpr: s.initialValueExpr,
      typeAnnotation: s.typeAnnotation || "any",
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
      cleanupCode: e.cleanupCode,
    }));

    const methods: FullSyntaxMethod[] = ast.methods.map((m) => ({
      name: m.name,
      parameters: m.parameters.map((p) => ({ name: p.name, type: p.type || "any" })),
      returnType: m.returnType || "void",
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    const slots: FullSyntaxSlot[] = ast.snippets.map((s) => ({
      name: s.name === "children" ? "default" : s.name,
      slotProps: Array.isArray(s.parameters)
        ? s.parameters.map((p: any) =>
            typeof p === "string" ? { name: p, type: "any" } : { name: p.name || "param", type: p.typeAnnotation || "any" }
          )
        : [],
      fallbackNodes: [],
    }));

    const templateRoot: FullSyntaxNode =
      ast.templateRoot && ast.templateRoot.length > 0 && ast.templateRoot[0]
        ? this.convertSvelteNodeToFullSyntax(ast.templateRoot[0])
        : { id: "root", kind: "element", tag: "div", children: [] };

    const ir: FullSyntaxComponentIR & { stateVariables: FullSyntaxState[] } = {
      schemaVersion: "2.0" as const,
      componentName: ast.componentName || "Component",
      sourceFramework: "svelte5" as const,
      props,
      states,
      get stateVariables(): FullSyntaxState[] {
        return this.states;
      },
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot,
      styles: {
        scopedCss: ast.cssScopedStyle,
      },
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: 0,
      metadata: {},
    };

    return ir;
  }

  public lowerToUniversal(ast: Svelte5ComponentAst): FullSyntaxComponentIR & { stateVariables: FullSyntaxState[] } {
    return this.liftToUniversal(ast);
  }

  public liftFromUniversal(ir: FullSyntaxComponentIR): Svelte5ComponentAst {
    return this.lowerToSvelte5(ir);
  }

  private convertSvelteNodeToFullSyntax(node: Svelte5TemplateNode): FullSyntaxNode {
    const rawAttrs = Array.isArray(node.attributes) ? node.attributes : [];
    const attrs = rawAttrs
      .filter((a: any) => !a.isEventHandler)
      .map((a: any) => ({
        name: a.name,
        value: a.value,
        isDynamic: !!a.isDynamic,
      }));

    const events = rawAttrs
      .filter((a: any) => a.isEventHandler)
      .map((a: any) => ({
        name: a.name.replace(/^on/, ""),
        handlerNameOrExpr: a.value,
      }));

    return {
      id: node.id || this.generateId("node"),
      kind: node.kind === "text" ? "text" : "element",
      tag: node.tag,
      attrs,
      events,
      text: node.text,
      expression: node.expression,
      children: (node.children || []).map((c) => this.convertSvelteNodeToFullSyntax(c)),
    };
  }
}

export { Svelte5SemanticLowering as Svelte5SemanticLowerer };

import {
  FullSyntaxComponentIR,
  FullSyntaxNode,
  FullSyntaxProp,
  FullSyntaxState,
} from "../types";
import {
  Angular18Attribute,
  Angular18ComponentAst,
  Angular18ComponentDecl,
  Angular18SignalComputed,
  Angular18SignalEffect,
  Angular18SignalInput,
  Angular18SignalItem,
  Angular18SignalOutput,
  Angular18SignalState,
  Angular18TemplateNode,
} from "./angular18-signals-types";

export class Angular18SemanticLowering {
  private idCounter = 0;

  private generateId(prefix = "ng_lower"): string {
    return `${prefix}_${this.idCounter++}`;
  }

  public lowerToUniversal(comp: Angular18ComponentDecl | Angular18ComponentAst): FullSyntaxComponentIR & { name: string; stateVariables: any[] } {
    const props: FullSyntaxProp[] = [
      ...comp.inputs.map((i) => ({
        name: i.name,
        typeAnnotation: i.typeAnnotation,
        required: i.required,
        isCallback: false,
        defaultValue: i.defaultValue,
      })),
      ...comp.outputs.map((o) => ({
        name: o.name,
        typeAnnotation: `(payload: ${o.payloadType}) => void`,
        required: false,
        isCallback: true,
      })),
    ];

    const states: FullSyntaxState[] = comp.states.map((s) => ({
      name: s.name,
      typeAnnotation: s.typeAnnotation,
      initialValueExpr: s.initialValueExpr,
      isRef: false,
    }));

    const computed = comp.computed.map((c) => ({
      name: c.name,
      returnType: c.returnType,
      expressionOrBody: c.expressionOrBody,
      dependencies: [],
    }));

    const effects = comp.effects.map((e) => ({
      id: e.id,
      hookKind: 'effect' as const,
      dependencies: [] as string[],
      bodyCode: e.bodyCode,
      hasCleanup: e.hasCleanup,
      cleanupCode: e.cleanupCode,
    }));

    const methods = comp.methods.map((m) => ({
      name: m.name,
      parameters: m.parameters,
      returnType: m.returnType,
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    const stateVariables = [
      ...states,
      ...computed.map((c) => ({ name: c.name, typeAnnotation: c.returnType, initialValueExpr: c.expressionOrBody, isRef: false })),
    ];

    const universalIR: FullSyntaxComponentIR & { name: string; stateVariables: any[] } = {
      componentName: comp.className,
      name: comp.className,
      sourceFramework: 'angular18',
      schemaVersion: '2.0',
      props,
      states,
      stateVariables,
      computed,
      effects,
      methods,
      slots: [],
      refs: [],
      templateRoot: { id: "root", kind: "element", tag: "div", children: [] },
      styles: { scopedCss: comp.styles.join('\n') },
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: 0,
      metadata: {},
    };

    return universalIR;
  }

  public liftFromUniversal(ir: FullSyntaxComponentIR): Angular18ComponentDecl {
    const compAst = this.lowerToAngular18(ir);
    const signals: Angular18SignalItem[] = [
      ...compAst.states.map((s) => ({
        name: s.name,
        kind: 'writable' as const,
        typeAnnotation: s.typeAnnotation,
        initialValueExpr: s.initialValueExpr,
      })),
      ...compAst.computed.map((c) => ({
        name: c.name,
        kind: 'computed' as const,
        returnType: c.returnType,
        expressionOrBody: c.expressionOrBody,
      })),
    ];

    const decl: Angular18ComponentDecl = {
      ...compAst,
      name: compAst.className,
      success: true,
      component: null as any,
      signals,
      controlFlowBlocks: [],
    };
    decl.component = decl;
    return decl;
  }

  public lowerToAngular18(ir: FullSyntaxComponentIR): Angular18ComponentAst {
    const inputs: Angular18SignalInput[] = [];
    const outputs: Angular18SignalOutput[] = [];

    for (const pr of ir.props) {
      if (!pr.isCallback) {
        inputs.push({
          name: pr.name,
          typeAnnotation: pr.typeAnnotation,
          required: pr.required,
          defaultValue: pr.defaultValue !== undefined ? JSON.stringify(pr.defaultValue) : undefined,
        });
      } else {
        const payloadType = pr.callbackSignature?.params[0]?.type || "void";
        outputs.push({
          name: pr.name,
          payloadType,
        });
      }
    }

    const states: Angular18SignalState[] = ir.states.map((s) => ({
      name: s.name,
      typeAnnotation: s.typeAnnotation || "any",
      initialValueExpr: s.initialValueExpr || "undefined",
    }));

    const computed: Angular18SignalComputed[] = ir.computed.map((c) => ({
      name: c.name,
      returnType: c.returnType || "any",
      expressionOrBody: c.expressionOrBody,
    }));

    const effects: Angular18SignalEffect[] = ir.effects.map((e) => ({
      id: e.id,
      bodyCode: e.bodyCode,
      hasCleanup: e.hasCleanup,
      cleanupCode: e.cleanupCode,
    }));

    const methods = ir.methods.map((m) => ({
      name: m.name,
      parameters: m.parameters,
      returnType: m.returnType,
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    const templateNodes: Angular18TemplateNode[] = ir.templateRoot
      ? [this.convertFullSyntaxNodeToAngular(ir.templateRoot)]
      : [];

    return {
      className: ir.componentName.endsWith('Component') ? ir.componentName : `${ir.componentName}Component`,
      selector: `app-${ir.componentName.toLowerCase()}`,
      standalone: true,
      imports: ["CommonModule"],
      inputs,
      outputs,
      models: [],
      states,
      computed,
      effects,
      methods,
      templateNodes,
      styles: ir.styles?.scopedCss ? [ir.styles.scopedCss] : [],
    };
  }

  private convertFullSyntaxNodeToAngular(node: FullSyntaxNode): Angular18TemplateNode {
    const attributes: Angular18Attribute[] = (node.attrs || []).map((a) => ({
      name: a.name,
      value: a.expression || a.value,
      kind: (a.isDynamic ? "property_binding" : "literal") as Angular18Attribute["kind"],
    }));

    if (node.events) {
      for (const ev of node.events) {
        attributes.push({
          name: ev.name,
          value: ev.handlerNameOrExpr,
          kind: "event_binding" as const,
        });
      }
    }

    let ifControl: Angular18TemplateNode["ifControl"];
    if (node.condition) {
      ifControl = {
        testExpr: node.condition.test,
        consequent: [this.convertFullSyntaxNodeToAngular(node.condition.thenNode)],
        alternate: node.condition.elseNode
          ? [this.convertFullSyntaxNodeToAngular(node.condition.elseNode)]
          : undefined,
        elseIfBranches: node.condition.elifBranches
          ? node.condition.elifBranches.map((b) => ({
              testExpr: b.test,
              consequent: [this.convertFullSyntaxNodeToAngular(b.node)],
            }))
          : undefined,
      };
    }

    let forControl: Angular18TemplateNode["forControl"];
    if (node.loop) {
      forControl = {
        itemName: node.loop.itemName,
        sourceExpr: node.loop.sourceExpr,
        trackExpr: node.loop.keyExpr || `${node.loop.itemName}.id || $index`,
        indexAlias: node.loop.indexName,
        body: [this.convertFullSyntaxNodeToAngular(node.loop.bodyNode)],
      };
    }

    const children = (node.children || []).map((c) => this.convertFullSyntaxNodeToAngular(c));

    return {
      id: node.id || this.generateId("node"),
      kind: node.kind === "text" ? "text" : "element",
      tag: node.tag,
      attributes,
      text: node.text,
      expression: node.expression,
      ifControl,
      forControl,
      children,
    };
  }
}

export { Angular18SemanticLowering as Angular18SemanticLowerer };

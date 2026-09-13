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
  Angular18ComponentAst,
  Angular18ComponentDecl,
  Angular18ControlFlowBlock,
  Angular18SignalComputed,
  Angular18SignalEffect,
  Angular18SignalInput,
  Angular18SignalItem,
  Angular18SignalModel,
  Angular18SignalOutput,
  Angular18SignalState,
  Angular18TemplateNode,
} from "./angular18-signals-types";

export class Angular18SignalsParser {
  private idCounter = 0;

  private generateId(prefix = "ng18_node"): string {
    return `${prefix}_${this.idCounter++}`;
  }

  public parse(sourceCode: string, classNameHint?: string): Angular18ComponentDecl {
    const sourceFile = ts.createSourceFile(
      "component.ts",
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    let className = classNameHint || "AppComponent";
    let selector = "app-root";
    let standalone = true;
    const imports: string[] = [];
    let inlineTemplate = "";
    const styles: string[] = [];

    const inputs: Angular18SignalInput[] = [];
    const outputs: Angular18SignalOutput[] = [];
    const models: Angular18SignalModel[] = [];
    const states: Angular18SignalState[] = [];
    const computed: Angular18SignalComputed[] = [];
    const effects: Angular18SignalEffect[] = [];
    const methods: Angular18ComponentAst["methods"] = [];

    // Parse AST
    ts.forEachChild(sourceFile, (node) => {
      if (ts.isClassDeclaration(node)) {
        if (node.name) {
          className = node.name.text;
        }

        // Decorator @Component({ ... })
        const decorators: ts.Decorator[] = [];
        if (ts.canHaveDecorators && ts.canHaveDecorators(node)) {
          const decs = ts.getDecorators(node);
          if (decs) decorators.push(...decs);
        }
        if (decorators.length === 0 && (node as any).decorators) {
          decorators.push(...(node as any).decorators);
        }
        if (decorators.length === 0 && ts.canHaveModifiers(node)) {
          const mods = ts.getModifiers(node);
          if (mods) {
            for (const m of mods) {
              if (ts.isDecorator(m)) decorators.push(m);
            }
          }
        }

        for (const dec of decorators) {
          if (ts.isCallExpression(dec.expression)) {
            const decName = dec.expression.expression.getText(sourceFile);
            if (decName === "Component" && dec.expression.arguments.length > 0) {
              const arg = dec.expression.arguments[0];
              if (arg && ts.isObjectLiteralExpression(arg)) {
                for (const prop of arg.properties) {
                  if (ts.isPropertyAssignment(prop) && ts.isIdentifier(prop.name)) {
                    const pName = prop.name.text;
                    if (pName === "selector" && ts.isStringLiteral(prop.initializer)) {
                      selector = prop.initializer.text;
                    } else if (pName === "standalone") {
                      standalone = prop.initializer.kind === ts.SyntaxKind.TrueKeyword;
                    } else if (pName === "template" && (ts.isStringLiteral(prop.initializer) || ts.isNoSubstitutionTemplateLiteral(prop.initializer))) {
                      inlineTemplate = prop.initializer.text;
                    } else if (pName === "imports" && ts.isArrayLiteralExpression(prop.initializer)) {
                      for (const el of prop.initializer.elements) {
                        imports.push(el.getText(sourceFile));
                      }
                    }
                  }
                }
              }
            }
          }
        }

        // Class members
        for (const member of node.members) {
          if (ts.isPropertyDeclaration(member) && member.name && ts.isIdentifier(member.name)) {
            const pName = member.name.text;
            const init = member.initializer;
            if (!init) continue;

            const initText = init.getText(sourceFile);

            // Signal input: input<T>() or input.required<T>()
            if (initText.startsWith("input")) {
              const isRequired = initText.startsWith("input.required");
              let typeAnn = "any";
              if (ts.isCallExpression(init) && init.typeArguments && init.typeArguments[0]) {
                typeAnn = init.typeArguments[0].getText(sourceFile);
              }
              let defVal: string | undefined;
              if (ts.isCallExpression(init) && init.arguments.length > 0 && init.arguments[0]) {
                defVal = init.arguments[0].getText(sourceFile);
              }
              inputs.push({
                name: pName,
                typeAnnotation: typeAnn,
                required: isRequired,
                defaultValue: defVal,
              });
            }
            // Signal output: output<T>()
            else if (initText.startsWith("output")) {
              let payloadType = "void";
              if (ts.isCallExpression(init) && init.typeArguments && init.typeArguments[0]) {
                payloadType = init.typeArguments[0].getText(sourceFile);
              }
              outputs.push({
                name: pName,
                payloadType,
              });
            }
            // Signal model: model<T>()
            else if (initText.startsWith("model")) {
              let typeAnn = "any";
              if (ts.isCallExpression(init) && init.typeArguments && init.typeArguments[0]) {
                typeAnn = init.typeArguments[0].getText(sourceFile);
              }
              let defVal: string | undefined;
              if (ts.isCallExpression(init) && init.arguments.length > 0 && init.arguments[0]) {
                defVal = init.arguments[0].getText(sourceFile);
              }
              models.push({
                name: pName,
                typeAnnotation: typeAnn,
                defaultValue: defVal,
              });
            }
            // Signal state: signal<T>(initial)
            else if (initText.startsWith("signal")) {
              let typeAnn = "any";
              if (ts.isCallExpression(init) && init.typeArguments && init.typeArguments[0]) {
                typeAnn = init.typeArguments[0].getText(sourceFile);
              }
              let initialVal = "undefined";
              if (ts.isCallExpression(init) && init.arguments.length > 0 && init.arguments[0]) {
                initialVal = init.arguments[0].getText(sourceFile);
              }
              states.push({
                name: pName,
                typeAnnotation: typeAnn,
                initialValueExpr: initialVal,
              });
            }
            // Signal computed: computed(() => ...)
            else if (initText.startsWith("computed")) {
              let exprOrBody = "";
              if (ts.isCallExpression(init) && init.arguments.length > 0 && init.arguments[0]) {
                exprOrBody = init.arguments[0].getText(sourceFile);
              }
              computed.push({
                name: pName,
                returnType: "any",
                expressionOrBody: exprOrBody,
              });
            }
          }
          // Constructor effects: constructor() { effect(() => { ... }) }
          else if (ts.isConstructorDeclaration(member) && member.body) {
            for (const stmt of member.body.statements) {
              if (ts.isExpressionStatement(stmt) && ts.isCallExpression(stmt.expression)) {
                if (stmt.expression.expression.getText(sourceFile) === "effect") {
                  const bodyCode = stmt.expression.arguments[0]
                    ? stmt.expression.arguments[0].getText(sourceFile)
                    : "";
                  effects.push({
                    id: this.generateId("effect"),
                    bodyCode,
                    hasCleanup: bodyCode.includes("onCleanup"),
                  });
                }
              }
            }
          }
          // Methods
          else if (ts.isMethodDeclaration(member) && member.name && ts.isIdentifier(member.name)) {
            const mName = member.name.text;
            const isAsync = (ts.getCombinedModifierFlags(member) & ts.ModifierFlags.Async) !== 0;
            methods.push({
              name: mName,
              parameters: member.parameters.map((p) => ({
                name: p.name.getText(sourceFile),
                type: p.type ? p.type.getText(sourceFile) : "any",
                defaultValue: p.initializer ? p.initializer.getText(sourceFile) : undefined,
              })),
              returnType: member.type ? member.type.getText(sourceFile) : "void",
              bodyCode: member.body ? member.body.getText(sourceFile) : "",
              isAsync,
            });
          }
        }
      }
    });

    const templateNodes = this.parseControlFlowTemplate(inlineTemplate);

    const signals: Angular18SignalItem[] = [
      ...states.map((s) => ({
        name: s.name,
        kind: 'writable' as const,
        typeAnnotation: s.typeAnnotation,
        initialValueExpr: s.initialValueExpr,
      })),
      ...computed.map((c) => ({
        name: c.name,
        kind: 'computed' as const,
        returnType: c.returnType,
        expressionOrBody: c.expressionOrBody,
      })),
    ];

    const controlFlowBlocks: Angular18ControlFlowBlock[] = [];
    // 1. @if (condition) { ... }
    const ifGlobalRegex = /@if\s*\(((?:[^)(]|\([^)(]*\))*)\)\s*\{/g;
    let ifMatch: RegExpExecArray | null;
    while ((ifMatch = ifGlobalRegex.exec(inlineTemplate)) !== null) {
      controlFlowBlocks.push({
        type: 'if',
        conditionCode: ifMatch[1] ? ifMatch[1].trim() : 'true',
      });
    }

    // 2. @for (item of items; track item.id) { ... }
    const forGlobalRegex = /@for\s*\(([a-zA-Z0-9_$]+)\s+of\s+((?:[^);]|\([^)(]*\))*);\s*track\s+((?:[^);)]|\([^)(]*\))*)\)\s*\{/g;
    let forMatch: RegExpExecArray | null;
    while ((forMatch = forGlobalRegex.exec(inlineTemplate)) !== null) {
      controlFlowBlocks.push({
        type: 'for',
        itemName: forMatch[1],
        sourceExpr: forMatch[2] ? forMatch[2].trim() : '',
        trackExpression: forMatch[3] ? forMatch[3].trim() : '',
      });
    }

    // 3. @switch (expr) { ... }
    const switchGlobalRegex = /@switch\s*\(((?:[^)(]|\([^)(]*\))*)\)\s*\{/g;
    let switchMatch: RegExpExecArray | null;
    while ((switchMatch = switchGlobalRegex.exec(inlineTemplate)) !== null) {
      controlFlowBlocks.push({
        type: 'switch',
        conditionCode: switchMatch[1] ? switchMatch[1].trim() : '',
      });
    }

    const extractBlocks = (tNodes: Angular18TemplateNode[]) => {
      for (const node of tNodes) {
        if (node.kind === 'at_if' && node.ifControl) {
          if (!controlFlowBlocks.some((b) => b.type === 'if' && b.conditionCode === node.ifControl?.testExpr)) {
            controlFlowBlocks.push({
              type: 'if',
              conditionCode: node.ifControl.testExpr,
            });
          }
          if (node.ifControl.consequent) extractBlocks(node.ifControl.consequent);
          if (node.ifControl.alternate) extractBlocks(node.ifControl.alternate);
        } else if (node.kind === 'at_for' && node.forControl) {
          if (!controlFlowBlocks.some((b) => b.type === 'for' && b.trackExpression === node.forControl?.trackExpr)) {
            controlFlowBlocks.push({
              type: 'for',
              trackExpression: node.forControl.trackExpr,
              itemName: node.forControl.itemName,
              sourceExpr: node.forControl.sourceExpr,
            });
          }
          if (node.forControl.body) extractBlocks(node.forControl.body);
        }
        if (node.children) extractBlocks(node.children);
      }
    };
    extractBlocks(templateNodes);

    const result: Angular18ComponentDecl = {
      className,
      name: className,
      selector,
      standalone,
      imports,
      inputs,
      outputs,
      models,
      states,
      computed,
      effects,
      methods,
      templateNodes,
      styles,
      signals,
      controlFlowBlocks,
      success: true,
      component: null as any,
    };
    result.component = result;
    return result;
  }

  private parseControlFlowTemplate(template: string): Angular18TemplateNode[] {
    const nodes: Angular18TemplateNode[] = [];
    let rem = template.trim();
    if (!rem) return nodes;

    while (rem.length > 0) {
      rem = rem.trim();
      if (!rem) break;

      // Check for @if
      if (rem.startsWith("@if")) {
        const ifMatch = /^@if\s*\(([\s\S]*?)\)\s*\{([\s\S]*?)\}(?:\s*@else\s*\{([\s\S]*?)\})?/.exec(rem);
        if (ifMatch) {
          const testExpr = (ifMatch[1] ?? "").trim();
          const cons = ifMatch[2] ? this.parseControlFlowTemplate(ifMatch[2]) : [];
          const alt = ifMatch[3] ? this.parseControlFlowTemplate(ifMatch[3]) : undefined;
          nodes.push({
            id: this.generateId("if"),
            kind: "at_if",
            ifControl: {
              testExpr,
              consequent: cons,
              alternate: alt,
            },
          });
          rem = rem.slice(ifMatch[0].length);
          continue;
        }
      }

      // Check for @for
      if (rem.startsWith("@for")) {
        const forMatch = /^@for\s*\(([a-zA-Z0-9_$]+)\s+of\s+([\s\S]*?);\s*track\s+([\s\S]*?)\)\s*\{([\s\S]*?)\}(?:\s*@empty\s*\{([\s\S]*?)\})?/.exec(rem);
        if (forMatch) {
          const itemName = forMatch[1] ?? "item";
          const sourceExpr = (forMatch[2] ?? "").trim();
          const trackExpr = (forMatch[3] ?? "").trim();
          const body = forMatch[4] ? this.parseControlFlowTemplate(forMatch[4]) : [];
          nodes.push({
            id: this.generateId("for"),
            kind: "at_for",
            forControl: {
              itemName,
              sourceExpr,
              trackExpr,
              body,
            },
          });
          rem = rem.slice(forMatch[0].length);
          continue;
        }
      }

      // Check for HTML element
      if (rem.startsWith("<")) {
        // Self-closing
        const scMatch = /^<([a-zA-Z0-9_\-]+)([^>]*)\/>/.exec(rem);
        if (scMatch) {
          const tag = scMatch[1] ?? "div";
          nodes.push({
            id: this.generateId(tag.toLowerCase()),
            kind: /^[A-Z]/.test(tag) ? "component" : "element",
            tag,
            children: [],
          });
          rem = rem.slice(scMatch[0].length);
          continue;
        }

        // Open tag ... close tag
        const openMatch = /^<([a-zA-Z0-9_\-]+)([^>]*)>/.exec(rem);
        if (openMatch) {
          const tag = openMatch[1] ?? "div";
          const closeTag = "</" + tag + ">";
          let depth = 1;
          let pos = openMatch[0].length;
          let closeIdx = -1;

          while (depth > 0 && pos < rem.length) {
            const nextClose = rem.indexOf(closeTag, pos);
            if (nextClose === -1) break;
            const segment = rem.slice(pos, nextClose);
            const openCount = (segment.match(new RegExp("<" + tag + "(\\s+[^>]*)?>", "g")) || []).length;
            depth += openCount - 1;
            if (depth === 0) {
              closeIdx = nextClose;
              break;
            }
            pos = nextClose + closeTag.length;
          }

          if (closeIdx !== -1) {
            const inner = rem.slice(openMatch[0].length, closeIdx);
            const children = this.parseControlFlowTemplate(inner);
            nodes.push({
              id: this.generateId(tag.toLowerCase()),
              kind: /^[A-Z]/.test(tag) ? "component" : "element",
              tag,
              children,
            });
            rem = rem.slice(closeIdx + closeTag.length);
            continue;
          }
        }
      }

      // Otherwise, consume text until next '<' or '@'
      const nextTag = rem.search(/[<@]/);
      if (nextTag > 0) {
        const text = rem.slice(0, nextTag).trim();
        if (text) {
          nodes.push({ id: this.generateId("text"), kind: "text", text });
        }
        rem = rem.slice(nextTag);
      } else {
        const text = rem.trim();
        if (text) {
          nodes.push({ id: this.generateId("text"), kind: "text", text });
        }
        break;
      }
    }

    return nodes;
  }

  /**
   * Lifts Angular18ComponentAst into FullSyntaxComponentIR.
   */
  public liftToComponentIR(ast: Angular18ComponentAst): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = [];

    for (const inp of ast.inputs) {
      props.push({
        name: inp.name,
        typeAnnotation: inp.typeAnnotation,
        required: inp.required,
        defaultValue: inp.defaultValue,
        isCallback: false,
      });
    }

    for (const out of ast.outputs) {
      props.push({
        name: out.name,
        typeAnnotation: `(payload: ${out.payloadType}) => void`,
        required: false,
        isCallback: true,
      });
    }

    const states: FullSyntaxState[] = ast.states.map((s) => ({
      name: s.name,
      initialValueExpr: s.initialValueExpr,
      typeAnnotation: s.typeAnnotation,
      isDynamic: true,
    }));

    for (const m of ast.models) {
      states.push({
        name: m.name,
        initialValueExpr: m.defaultValue || "''",
        typeAnnotation: m.typeAnnotation,
        isDynamic: true,
      });
    }

    const computed: FullSyntaxComputed[] = ast.computed.map((c) => ({
      name: c.name,
      returnType: c.returnType,
      dependencies: [],
      expressionOrBody: c.expressionOrBody,
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
      parameters: m.parameters,
      returnType: m.returnType,
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    const templateRoot: FullSyntaxNode = {
      id: "root",
      kind: "fragment",
      children: ast.templateNodes.map((n) => this.convertNode(n)),
    };

    return {
      schemaVersion: "2.0",
      componentName: ast.className,
      sourceFramework: "angular18",
      targetFramework: "vue3",
      description: `Angular 18 Signals component ${ast.className} lifted to Universal IR`,
      props,
      states,
      computed,
      effects,
      methods,
      slots: [],
      refs: [],
      templateRoot,
      styles: {},
      containerApis: [],
      thirdPartyComponents: ast.imports,
      rawSourceLinesCount: 100,
      metadata: {
        isAngular18: true,
        selector: ast.selector,
        standalone: ast.standalone,
      },
    };
  }

  private convertNode(n: Angular18TemplateNode): FullSyntaxNode {
    let condition: FullSyntaxNode["condition"];
    if (n.ifControl) {
      condition = {
        test: n.ifControl.testExpr,
        thenNode: {
          id: this.generateId("then"),
          kind: "fragment",
          children: n.ifControl.consequent.map((c) => this.convertNode(c)),
        },
        elseNode: n.ifControl.alternate
          ? {
              id: this.generateId("else"),
              kind: "fragment",
              children: n.ifControl.alternate.map((c) => this.convertNode(c)),
            }
          : undefined,
      };
    }

    let loop: FullSyntaxNode["loop"];
    if (n.forControl) {
      loop = {
        sourceExpr: n.forControl.sourceExpr,
        itemName: n.forControl.itemName,
        keyExpr: n.forControl.trackExpr,
        bodyNode: {
          id: this.generateId("body"),
          kind: "fragment",
          children: n.forControl.body.map((c) => this.convertNode(c)),
        },
      };
    }

    return {
      id: n.id,
      kind: n.kind === "text" ? "text" : "element",
      tag: n.tag,
      text: n.text,
      condition,
      loop,
      children: n.children ? n.children.map((c) => this.convertNode(c)) : undefined,
    };
  }
}

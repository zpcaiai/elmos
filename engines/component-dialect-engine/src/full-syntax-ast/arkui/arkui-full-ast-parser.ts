import * as ts from "typescript";
import {
  ArkUIBuilderMethod,
  ArkUIBuilderParam,
  ArkUIComponentAst,
  ArkUIDecorator,
  ArkUILifecycleMethod,
  ArkUIModifier,
  ArkUINode,
  ArkUIStateProperty,
  ArkUIStylesMethod,
} from "./arkui-full-ast-types";
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

export class ArkUIFullAstParser {
  private idCounter = 0;

  private generateId(prefix = "ark_node"): string {
    return `${prefix}_${this.idCounter++}`;
  }

  public parse(sourceCode: string, structNameHint?: string): ArkUIComponentAst {
    const normalizedCode = sourceCode.replace(/\bstruct\s+([A-Za-z0-9_$]+)/g, "class $1");
    const sourceFile = ts.createSourceFile(
      "component.ets",
      normalizedCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    );

    let structName = structNameHint || "";
    let isEntry = false;
    let isPreview = false;
    const stateProperties: ArkUIStateProperty[] = [];
    const builderParams: ArkUIBuilderParam[] = [];
    const builderMethods: ArkUIBuilderMethod[] = [];
    const stylesMethods: ArkUIStylesMethod[] = [];
    const lifecycleMethods: ArkUILifecycleMethod[] = [];
    const customMethods: ArkUIComponentAst["customMethods"] = [];
    const importedModules: ArkUIComponentAst["importedModules"] = [];
    let buildRoot: ArkUINode = {
      id: "root",
      kind: "container",
      componentName: "Column",
      modifiers: [],
      children: [],
    };

    // Extract imports
    ts.forEachChild(sourceFile, (node) => {
      if (ts.isImportDeclaration(node)) {
        const moduleSpecifier = (node.moduleSpecifier as ts.StringLiteral).text;
        const namedImports: string[] = [];
        let defaultImport: string | undefined;

        if (node.importClause) {
          if (node.importClause.name) {
            defaultImport = node.importClause.name.text;
          }
          if (node.importClause.namedBindings && ts.isNamedImports(node.importClause.namedBindings)) {
            for (const el of node.importClause.namedBindings.elements) {
              namedImports.push(el.name.text);
            }
          }
        }
        importedModules.push({ namedImports, defaultImport, moduleSpecifier });
      }
    });

    // Find struct / class declaration
    ts.forEachChild(sourceFile, (node) => {
      if (ts.isClassDeclaration(node) || (node as any).members) {
        const classDecl = node as ts.ClassDeclaration;
        const name = classDecl.name?.text || "UnknownStruct";
        if (structNameHint && name !== structNameHint) {
          return;
        }
        structName = name;

        // Check decorators
        const modifiers = ts.canHaveModifiers(node) ? ts.getModifiers(node) : undefined;
        if (modifiers) {
          for (const m of modifiers) {
            const dec = m as any;
            if (ts.isDecorator(dec)) {
              const decText = dec.expression.getText(sourceFile);
              if (decText.includes("Entry")) isEntry = true;
              if (decText.includes("Preview")) isPreview = true;
            }
          }
        }

        // Process members
        for (const member of classDecl.members) {
          if (ts.isPropertyDeclaration(member) && member.name && ts.isIdentifier(member.name)) {
            const propName = member.name.text;
            const propType = member.type ? member.type.getText(sourceFile) : "any";
            const initExpr = member.initializer ? member.initializer.getText(sourceFile) : undefined;

            const rawDecorators = (ts.canHaveDecorators && ts.canHaveDecorators(member) ? ts.getDecorators(member) : undefined) || (member as any).decorators || [];
            const memberModifiers = (ts.canHaveModifiers(member) ? ts.getModifiers(member) : undefined) || [];
            const allDecs = [...(rawDecorators as any[]), ...(memberModifiers as any[])];

            let decorator: ArkUIDecorator | undefined;
            let watchCallback: string | undefined;

            for (const dec of allDecs) {
              if (ts.isDecorator(dec)) {
                const exprText = dec.expression.getText(sourceFile);
                if (exprText.startsWith("@State")) {
                  decorator = { kind: "@State" };
                } else if (exprText.startsWith("@Prop")) {
                  decorator = { kind: "@Prop" };
                } else if (exprText.startsWith("@Link")) {
                  decorator = { kind: "@Link" };
                } else if (exprText.startsWith("@Provide")) {
                  decorator = { kind: "@Provide" };
                } else if (exprText.startsWith("@Consume")) {
                  decorator = { kind: "@Consume" };
                } else if (exprText.startsWith("@ObjectLink")) {
                  decorator = { kind: "@ObjectLink" };
                } else if (exprText.startsWith("@BuilderParam")) {
                  builderParams.push({
                    name: propName,
                    typeAnnotation: propType,
                    required: !member.questionToken,
                    defaultBuilderName: initExpr,
                  });
                } else if (exprText.startsWith("@Watch")) {
                  const match = exprText.match(/@Watch\(['"](\w+)['"]\)/);
                  if (match && match[1]) {
                    watchCallback = match[1];
                  }
                }
              }
            }

            if (decorator) {
              stateProperties.push({
                name: propName,
                decorator,
                typeAnnotation: propType,
                initialValueExpr: initExpr,
                watchCallbackName: watchCallback,
              });
            }
          } else if (ts.isMethodDeclaration(member) && member.name && ts.isIdentifier(member.name)) {
            const methodName = member.name.text;
            const methodModifiers = ts.canHaveModifiers(member) ? ts.getModifiers(member) : undefined;
            let isBuilder = false;
            let isStyles = false;

            if (methodModifiers) {
              for (const mod of methodModifiers) {
                const dec = mod as any;
                if (ts.isDecorator(dec)) {
                  const exprText = dec.expression.getText(sourceFile);
                  if (exprText.startsWith("@Builder")) isBuilder = true;
                  if (exprText.startsWith("@Styles")) isStyles = true;
                }
              }
            }

            if (methodName === "build" && member.body) {
              buildRoot = this.parseBuildBody(member.body, sourceFile);
            } else if (
              methodName === "aboutToAppear" ||
              methodName === "aboutToDisappear" ||
              methodName === "onPageShow" ||
              methodName === "onPageHide" ||
              methodName === "onBackPress"
            ) {
              lifecycleMethods.push({
                name: methodName,
                bodyCode: member.body ? member.body.getText(sourceFile) : "",
              });
            } else if (isBuilder && member.body) {
              builderMethods.push({
                name: methodName,
                parameters: member.parameters.map((p) => ({
                  name: p.name.getText(sourceFile),
                  type: p.type ? p.type.getText(sourceFile) : "any",
                })),
                body: this.parseBuilderBody(member.body, sourceFile),
              });
            } else if (isStyles && member.body) {
              stylesMethods.push({
                name: methodName,
                modifiers: this.parseStylesModifiers(member.body, sourceFile),
              });
            } else {
              const isAsync = (ts.getCombinedModifierFlags(member) & ts.ModifierFlags.Async) !== 0;
              customMethods.push({
                name: methodName,
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
      }
    });

    // In ArkUI, declarative syntax inside build() features trailing closures and chained modifiers
    // that standard TypeScript syntax treats as invalid grammar. Extract build() and parse with specialized ArkUI grammar parser.
    const buildIndex = sourceCode.search(/build\s*\(\)\s*\{/);
    if (buildIndex !== -1) {
      const openBrace = sourceCode.indexOf("{", buildIndex);
      let depth = 1;
      let pos = openBrace + 1;
      let inString: string | null = null;
      while (pos < sourceCode.length && depth > 0) {
        const ch = sourceCode[pos];
        if (inString) {
          if (ch === "\\") {
            pos += 2;
            continue;
          }
          if (ch === inString) inString = null;
        } else {
          if (ch === '"' || ch === "'" || ch === "`") inString = ch;
          else if (ch === "{") depth++;
          else if (ch === "}") depth--;
        }
        pos++;
      }
      const buildBodyStr = sourceCode.substring(openBrace + 1, pos - 1);
      const declarativeNodes = this.parseDeclarativeString(buildBodyStr);
      if (declarativeNodes.length > 0 && declarativeNodes[0]) {
        buildRoot = declarativeNodes[0];
      }
    }

    // Fallback extraction for ArkTS state properties if TS AST member decorators were suppressed
    if (stateProperties.length === 0) {
      const propRegex = /@(State|Prop|Link|Provide|Consume|ObjectLink|StorageLink|StorageProp)\s+([A-Za-z0-9_$]+)(?:\s*:\s*([^=;]+))?(?:\s*=\s*([^;]+))?;/g;
      let match: RegExpExecArray | null;
      while ((match = propRegex.exec(sourceCode)) !== null) {
        const kind = `@${match[1]}` as any;
        const name = match[2] || "prop";
        const typeAnnotation = match[3]?.trim() || "any";
        const initialValueExpr = match[4]?.trim();
        stateProperties.push({
          name,
          decorator: { kind },
          typeAnnotation,
          initialValueExpr,
        });
      }
    }

    if (builderParams.length === 0) {
      const bpRegex = /@BuilderParam\s+([A-Za-z0-9_$]+)(?:\?|!)?(?:\s*:\s*([^=;]+))?(?:\s*=\s*([^;]+))?;/g;
      let match: RegExpExecArray | null;
      while ((match = bpRegex.exec(sourceCode)) !== null) {
        if (match[1]) {
          builderParams.push({
            name: match[1],
            typeAnnotation: match[2]?.trim() || "() => void",
            required: false,
            defaultBuilderName: match[3]?.trim(),
          });
        }
      }
    }

    return {
      structName,
      isEntry,
      isPreview,
      stateProperties,
      builderParams,
      builderMethods,
      stylesMethods,
      extendMethods: [],
      lifecycleMethods,
      customMethods,
      buildRoot,
      importedModules,
    };
  }

  private parseDeclarativeString(input: string): ArkUINode[] {
    const nodes: ArkUINode[] = [];
    let pos = 0;
    const len = input.length;

    const skipWhitespaceAndComments = () => {
      while (pos < len) {
        const ch = input[pos];
        if (ch && /\s/.test(ch)) {
          pos++;
          continue;
        }
        if (input[pos] === '/' && input[pos + 1] === '/') {
          pos += 2;
          while (pos < len && input[pos] !== '\n') pos++;
          continue;
        }
        if (input[pos] === '/' && input[pos + 1] === '*') {
          pos += 2;
          while (pos < len - 1 && !(input[pos] === '*' && input[pos + 1] === '/')) pos++;
          pos += 2;
          continue;
        }
        break;
      }
    };

    const extractBalanced = (openChar: string, closeChar: string): string => {
      if (input[pos] !== openChar) return "";
      let depth = 0;
      const start = pos + 1;
      let inString: string | null = null;

      while (pos < len) {
        const ch = input[pos];
        if (inString) {
          if (ch === '\\') {
            pos += 2;
            continue;
          }
          if (ch === inString) {
            inString = null;
          }
        } else {
          if (ch === '"' || ch === "'" || ch === '`') {
            inString = ch;
          } else if (ch === openChar) {
            depth++;
          } else if (ch === closeChar) {
            depth--;
            if (depth === 0) {
              const res = input.substring(start, pos);
              pos++;
              return res;
            }
          }
        }
        pos++;
      }
      return input.substring(start, pos);
    };

    while (pos < len) {
      skipWhitespaceAndComments();
      if (pos >= len) break;

      const identMatch = input.slice(pos).match(/^([A-Za-z0-9_$]+)/);
      if (!identMatch || !identMatch[1]) {
        pos++;
        continue;
      }

      const compName: string = identMatch[1];
      pos += compName.length;
      skipWhitespaceAndComments();

      let constructorArgs: string[] = [];
      if (pos < len && input[pos] === '(') {
        const rawArgs = extractBalanced('(', ')');
        if (rawArgs.trim()) {
          constructorArgs = [rawArgs.trim()];
        }
      }
      skipWhitespaceAndComments();

      let children: ArkUINode[] = [];
      if (pos < len && input[pos] === '{') {
        const blockContent = extractBalanced('{', '}');
        children = this.parseDeclarativeString(blockContent);
      }
      skipWhitespaceAndComments();

      const modifiers: ArkUIModifier[] = [];
      while (pos < len && input[pos] === '.') {
        pos++;
        skipWhitespaceAndComments();
        const modNameMatch = input.slice(pos).match(/^([A-Za-z0-9_$]+)/);
        if (!modNameMatch || !modNameMatch[1]) break;
        const modName: string = modNameMatch[1];
        pos += modName.length;
        skipWhitespaceAndComments();

        let modArgs: string[] = [];
        if (pos < len && input[pos] === '(') {
          const rawModArgs = extractBalanced('(', ')');
          if (rawModArgs.trim()) {
            modArgs = [rawModArgs.trim()];
          }
        }
        const isEvent = modName.startsWith('on') || modName === 'onClick';
        modifiers.push({ name: modName, args: modArgs, isEvent });
        skipWhitespaceAndComments();
      }

      const isContainer = [
        "Column",
        "Row",
        "Stack",
        "Flex",
        "Grid",
        "GridItem",
        "List",
        "ListItem",
        "Scroll",
        "Swiper",
        "Tabs",
        "TabContent",
      ].includes(compName) || children.length > 0;

      nodes.push({
        id: this.generateId(compName.toLowerCase()),
        kind: isContainer ? "container" : "atomic",
        componentName: compName,
        constructorArgs: constructorArgs.length > 0 ? constructorArgs : undefined,
        children: children.length > 0 ? children : undefined,
        modifiers,
      });

      skipWhitespaceAndComments();
      const endChar = input[pos];
      if (pos < len && (endChar === ';' || endChar === ',')) {
        pos++;
      }
    }

    return nodes;
  }

  private parseBuildBody(body: ts.Block, sourceFile: ts.SourceFile): ArkUINode {
    for (const stmt of body.statements) {
      if (ts.isExpressionStatement(stmt)) {
        return this.parseArkUIExpression(stmt.expression, sourceFile);
      }
    }
    return {
      id: this.generateId(),
      kind: "container",
      componentName: "Column",
      modifiers: [],
      children: [],
    };
  }

  private parseBuilderBody(body: ts.Block, sourceFile: ts.SourceFile): ArkUINode[] {
    const nodes: ArkUINode[] = [];
    for (const stmt of body.statements) {
      if (ts.isExpressionStatement(stmt)) {
        nodes.push(this.parseArkUIExpression(stmt.expression, sourceFile));
      }
    }
    return nodes;
  }

  private parseStylesModifiers(body: ts.Block, sourceFile: ts.SourceFile): ArkUIModifier[] {
    const modifiers: ArkUIModifier[] = [];
    // Style block in ArkUI e.g. .width(100).height(50)
    for (const stmt of body.statements) {
      if (ts.isExpressionStatement(stmt)) {
        let curr: ts.Expression = stmt.expression;
        while (ts.isCallExpression(curr) && ts.isPropertyAccessExpression(curr.expression)) {
          modifiers.unshift({
            name: curr.expression.name.text,
            args: curr.arguments.map((a) => a.getText(sourceFile)),
          });
          curr = curr.expression.expression;
        }
      }
    }
    return modifiers;
  }

  private parseArkUIExpression(expr: ts.Expression, sourceFile: ts.SourceFile): ArkUINode {
    const modifiers: ArkUIModifier[] = [];
    let baseExpr: ts.Expression = expr;

    // Unwind call modifiers: Component().width('100%').onClick(() => ...)
    while (ts.isCallExpression(baseExpr) && ts.isPropertyAccessExpression(baseExpr.expression)) {
      const modifierName = baseExpr.expression.name.text;
      const args = baseExpr.arguments.map((a) => a.getText(sourceFile));
      const isEvent = modifierName.startsWith("on") || modifierName === "onClick";
      modifiers.unshift({ name: modifierName, args, isEvent });
      baseExpr = baseExpr.expression.expression;
    }

    // Now baseExpr should be the component invocation or block e.g. Column() { ... } or Text('hello')
    if (ts.isCallExpression(baseExpr)) {
      const callee = baseExpr.expression;
      const componentName = callee.getText(sourceFile);
      const constructorArgs = baseExpr.arguments.map((a) => a.getText(sourceFile));
      const children: ArkUINode[] = [];

      // Check for trailing block or trailing closure
      // In ArkTS, container components take trailing closures: Column() { Text('...') }
      // In TypeScript AST, this is sometimes represented as a call with function argument or special expression
      const isContainer = [
        "Column",
        "Row",
        "Stack",
        "Flex",
        "Grid",
        "GridItem",
        "List",
        "ListItem",
        "Scroll",
        "Swiper",
        "Tabs",
        "TabContent",
      ].includes(componentName);

      return {
        id: this.generateId(componentName.toLowerCase()),
        kind: isContainer ? "container" : "atomic",
        componentName,
        constructorArgs,
        modifiers,
        children,
      };
    }

    // Builder invocation e.g. this.myCustomBuilder()
    if (ts.isPropertyAccessExpression(baseExpr) && baseExpr.expression.kind === ts.SyntaxKind.ThisKeyword) {
      return {
        id: this.generateId("builder_call"),
        kind: "builder_invocation",
        componentName: baseExpr.name.text,
        modifiers,
      };
    }

    return {
      id: this.generateId("unknown"),
      kind: "atomic",
      componentName: "Text",
      constructorArgs: [baseExpr.getText(sourceFile)],
      modifiers,
    };
  }

  /**
   * Lifts an ArkUIComponentAst into the canonical FullSyntaxComponentIR.
   */
  public liftToComponentIR(ast: ArkUIComponentAst): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];
    const slots: FullSyntaxSlot[] = [];

    // Map state properties
    for (const prop of ast.stateProperties) {
      if (prop.decorator.kind === "@Prop" || prop.decorator.kind === "@Link") {
        props.push({
          name: prop.name,
          typeAnnotation: prop.typeAnnotation,
          required: prop.decorator.kind === "@Link" || !prop.initialValueExpr,
          defaultValue: prop.initialValueExpr,
          isCallback: false,
        });
      } else {
        states.push({
          name: prop.name,
          initialValueExpr: prop.initialValueExpr || "undefined",
          typeAnnotation: prop.typeAnnotation,
          isDynamic: true,
        });
      }

      // If watch callback exists, map to an effect
      if (prop.watchCallbackName) {
        effects.push({
          id: `watch_${prop.name}`,
          hookKind: "watch",
          dependencies: [prop.name],
          bodyCode: `this.${prop.watchCallbackName}()`,
          hasCleanup: false,
        });
      }
    }

    // Map builderParams to slots
    for (const bp of ast.builderParams) {
      slots.push({
        name: bp.name === "defaultBuilder" ? "default" : bp.name,
        slotProps: [],
        fallbackNodes: [],
      });
    }

    // Map lifecycle hooks to effects
    for (const life of ast.lifecycleMethods) {
      if (life.name === "aboutToAppear") {
        effects.push({
          id: "mount_effect",
          hookKind: "mount",
          dependencies: [],
          bodyCode: life.bodyCode,
          hasCleanup: false,
        });
      } else if (life.name === "aboutToDisappear") {
        effects.push({
          id: "unmount_effect",
          hookKind: "unmount",
          dependencies: [],
          bodyCode: life.bodyCode,
          hasCleanup: false,
        });
      }
    }

    // Map custom methods
    for (const cm of ast.customMethods) {
      methods.push({
        name: cm.name,
        parameters: cm.parameters,
        returnType: cm.returnType,
        bodyCode: cm.bodyCode,
        isAsync: cm.isAsync,
      });
    }

    // Convert ArkUINode tree to FullSyntaxNode tree
    const templateRoot = this.convertArkUINodeToFullSyntaxNode(ast.buildRoot);

    return {
      schemaVersion: "2.0",
      componentName: ast.structName,
      sourceFramework: "arkui",
      targetFramework: "arkui",
      description: `ArkTS component ${ast.structName} lifted to Universal IR`,
      props,
      states,
      computed: [],
      effects,
      methods,
      slots,
      refs: [],
      templateRoot,
      styles: {},
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: 100,
      metadata: {
        isEntry: ast.isEntry,
        isPreview: ast.isPreview,
        arkuiVersion: "3.0",
      },
    };
  }

  private convertArkUINodeToFullSyntaxNode(node: ArkUINode): FullSyntaxNode {
    const attrs: FullSyntaxAttr[] = [];
    const events: FullSyntaxEvent[] = [];

    // Map modifiers to attributes or events
    for (const mod of node.modifiers) {
      if (mod.isEvent || mod.name === "onClick" || mod.name.startsWith("on")) {
        const eventName = mod.name.startsWith("on") ? mod.name.slice(2).toLowerCase() : mod.name;
        events.push({
          name: eventName,
          handlerNameOrExpr: mod.args[0] || "() => {}",
        });
      } else {
        attrs.push({
          name: mod.name,
          value: mod.args[0] || "",
          isDynamic: !mod.args[0]?.startsWith("'") && !mod.args[0]?.startsWith('"'),
          expression: mod.args[0],
        });
      }
    }

    // Handle constructor arguments e.g. Text('hello') or Button('Click Me')
    let textContent: string | undefined;
    if (node.componentName === "Text" && node.constructorArgs?.[0]) {
      const rawArg = node.constructorArgs[0];
      if (rawArg.startsWith("'") || rawArg.startsWith('"')) {
        textContent = rawArg.slice(1, -1);
      } else {
        textContent = rawArg;
      }
    }

    const children: FullSyntaxNode[] = (node.children || []).map((c) =>
      this.convertArkUINodeToFullSyntaxNode(c)
    );

    return {
      id: node.id,
      kind: node.kind === "container" ? "element" : "component",
      tag: node.componentName,
      attrs,
      events,
      text: textContent,
      children,
    };
  }
}

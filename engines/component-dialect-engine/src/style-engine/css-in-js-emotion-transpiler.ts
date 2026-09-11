/**
 * @file css-in-js-emotion-transpiler.ts
 * @description Emotion and styled-components CSS-in-JS AST transpiler for MiniApp & ArkUI.
 * Parses tagged template literals and object styles, separates static rules from dynamic
 * prop-dependent functions, generates scoped WXSS classes and inline dynamic bindings,
 * and handles theme context injection (ThemeProvider).
 */

import * as ts from 'typescript';

export interface DynamicStyleBinding {
  property: string;
  expression: string; // e.g. "props.primary ? '#1677ff' : '#000000'"
  defaultVal?: string;
}

export interface TranspiledCssInJsComponent {
  componentName: string;
  baseTag: string;
  staticCss: string;
  staticClassName: string;
  dynamicBindings: DynamicStyleBinding[];
  arkUiAttributeModifiers: string[];
}

export class CssInJsEmotionTranspiler {
  private componentCounter = 0;

  /**
   * Transpiles a CSS-in-JS source file containing styled components or css tags
   */
  public transpile(sourceCode: string): {
    components: TranspiledCssInJsComponent[];
    combinedWxss: string;
    themeVariables: Record<string, string>;
  } {
    const components: TranspiledCssInJsComponent[] = [];
    const themeVariables: Record<string, string> = {};

    const sourceFile = ts.createSourceFile(
      'styled.tsx',
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX
    );

    const extracted: TranspiledCssInJsComponent[] = [];

    const visit = (node: ts.Node) => {
      // 1. styled.button`...` or styled('div')`...`
      if (ts.isVariableDeclaration(node) && node.initializer) {
        const compName = node.name.getText(sourceFile);

        // Tagged template literal: styled.div`...`
        if (ts.isTaggedTemplateExpression(node.initializer)) {
          const tagExpr = node.initializer.tag.getText(sourceFile);
          if (tagExpr.startsWith('styled')) {
            const baseTag = this.extractBaseTag(tagExpr);
            const template = node.initializer.template;

            const res = this.processTemplateLiteral(compName, baseTag, template, sourceFile);
            extracted.push(res);
          }
        }
        // Call expression: styled('div')({ ... })
        else if (ts.isCallExpression(node.initializer)) {
          const fnText = node.initializer.expression.getText(sourceFile);
          if (fnText.startsWith('styled') && node.initializer.arguments.length > 0) {
            const baseTag = this.extractBaseTag(fnText);
            const res = this.processObjectStyles(compName, baseTag, node.initializer.arguments[0]!, sourceFile);
            extracted.push(res);
          }
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    // Combine all static WXSS
    const combinedWxss = extracted.map((c) => c.staticCss).join('\n\n');

    return {
      components: extracted,
      combinedWxss,
      themeVariables,
    };
  }

  private extractBaseTag(tagExpr: string): string {
    const dotMatch = tagExpr.match(/styled\.([a-zA-Z0-9_-]+)/);
    if (dotMatch && dotMatch[1]) return dotMatch[1];
    const callMatch = tagExpr.match(/styled\(['"]([a-zA-Z0-9_-]+)['"]\)/);
    if (callMatch && callMatch[1]) return callMatch[1];
    return 'view'; // default MiniApp tag
  }

  private processTemplateLiteral(
    compName: string,
    baseTag: string,
    template: ts.TemplateLiteral,
    sourceFile: ts.SourceFile
  ): TranspiledCssInJsComponent {
    this.componentCounter++;
    const className = `styled-${compName.toLowerCase()}-${this.componentCounter}`;
    const dynamicBindings: DynamicStyleBinding[] = [];
    const staticDecls: string[] = [];
    const arkUiAttrs: string[] = [];

    if (ts.isNoSubstitutionTemplateLiteral(template)) {
      // Entirely static
      const rawText = template.rawText || template.text;
      staticDecls.push(rawText);
    } else if (ts.isTemplateExpression(template)) {
      // Has head and spans with dynamic expressions
      let combined = template.head.text;

      for (const span of template.templateSpans) {
        const exprText = span.expression.getText(sourceFile);
        const tailText = span.literal.text;

        // Check if exprText is an interpolation function e.g. `props => props.primary ? 'red' : 'blue'`
        const propMatch = exprText.match(/props\s*=>\s*(.+)/);
        if (propMatch && propMatch[1]) {
          // Identify previous CSS property name from combined
          const lastProp = this.extractLastCssProperty(combined);
          if (lastProp) {
            dynamicBindings.push({
              property: lastProp,
              expression: propMatch[1].trim(),
            });
            arkUiAttrs.push(`.${this.toArkUiMethod(lastProp)}(${propMatch[1].trim()})`);
          }
        } else {
          // Constant or theme value interpolation
          combined += exprText;
        }

        combined += tailText;
      }

      // Filter out dynamic properties from static CSS
      const lines = combined.split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.length > 0 && !dynamicBindings.some((b) => trimmed.startsWith(b.property))) {
          staticDecls.push(trimmed);
        }
      }
    }

    const staticCss = `.${className} {\n  ${staticDecls.join('\n  ')}\n}`;

    return {
      componentName: compName,
      baseTag,
      staticCss,
      staticClassName: className,
      dynamicBindings,
      arkUiAttributeModifiers: arkUiAttrs,
    };
  }

  private processObjectStyles(
    compName: string,
    baseTag: string,
    arg: ts.Node,
    sourceFile: ts.SourceFile
  ): TranspiledCssInJsComponent {
    this.componentCounter++;
    const className = `styled-${compName.toLowerCase()}-${this.componentCounter}`;
    const dynamicBindings: DynamicStyleBinding[] = [];
    const staticDecls: string[] = [];

    if (ts.isObjectLiteralExpression(arg)) {
      for (const prop of arg.properties) {
        if (ts.isPropertyAssignment(prop)) {
          const propName = prop.name.getText(sourceFile);
          const cssProp = this.camelToKebab(propName);
          const initText = prop.initializer.getText(sourceFile);

          if (initText.includes('=>') || initText.includes('props.')) {
            dynamicBindings.push({
              property: cssProp,
              expression: initText,
            });
          } else {
            const cleanVal = initText.replace(/['"]/g, '');
            staticDecls.push(`${cssProp}: ${cleanVal};`);
          }
        }
      }
    }

    const staticCss = `.${className} {\n  ${staticDecls.join('\n  ')}\n}`;

    return {
      componentName: compName,
      baseTag,
      staticCss,
      staticClassName: className,
      dynamicBindings,
      arkUiAttributeModifiers: [],
    };
  }

  private extractLastCssProperty(str: string): string | null {
    const match = str.match(/([a-zA-Z-]+)\s*:\s*$/);
    return match && match[1] ? match[1].toLowerCase() : null;
  }

  private camelToKebab(str: string): string {
    return str.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
  }

  private toArkUiMethod(cssProp: string): string {
    switch (cssProp) {
      case 'color':
        return 'fontColor';
      case 'background-color':
      case 'background':
        return 'backgroundColor';
      case 'font-size':
        return 'fontSize';
      case 'width':
        return 'width';
      case 'height':
        return 'height';
      case 'border-radius':
        return 'borderRadius';
      default:
        return 'attributeModifier';
    }
  }
}

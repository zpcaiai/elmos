/**
 * WeChat MiniApp SSR Evaluator
 *
 * Parses WXML templates, evaluates MiniApp component logic, simulates reactive data binding,
 * and renders a canonical HeadlessDOMNode tree for cross-platform differential analysis.
 */

import { HeadlessDOMNode, ComponentRenderContext } from './types';
import { DOMNode, HTMLParser, HeadlessBoxLayoutEngine } from './headless-browser-dom';

export interface MiniAppSourceFiles {
  wxml: string;
  js?: string;
  json?: string;
  wxss?: string;
}

export class MiniAppSSREvaluator {
  /**
   * Evaluate a MiniApp component with given props and state to produce a Virtual DOM tree.
   */
  public static evaluate(
    source: MiniAppSourceFiles | string,
    context: ComponentRenderContext = {}
  ): DOMNode {
    const wxmlContent = typeof source === 'string' ? source : source.wxml;
    const jsContent = typeof source === 'object' ? source.js : undefined;

    // 1. Extract default component data and properties from JS if available
    const componentData: Record<string, any> = {
      ...(typeof context.props === 'object' ? context.props : {}),
      ...(typeof context.state === 'object' ? context.state : {})
    };

    if (jsContent) {
      const extractedDefaults = this.extractComponentDefaults(jsContent);
      Object.assign(componentData, extractedDefaults.data, componentData);
    }

    // 2. Parse WXML into raw DOM nodes
    const rawNodes = HTMLParser.parse(wxmlContent);

    // 3. Create root container
    const root = new DOMNode('element', 'view');
    root.setAttribute('class', 'miniapp-root');

    // 4. Evaluate directives and expressions
    for (const node of rawNodes) {
      const evaluated = this.evaluateNode(node, componentData);
      if (evaluated) {
        if (Array.isArray(evaluated)) {
          for (const child of evaluated) {
            root.appendChild(child);
          }
        } else {
          root.appendChild(evaluated);
        }
      }
    }

    // 5. Compute layout
    HeadlessBoxLayoutEngine.computeLayout(root);

    return root;
  }

  private static extractComponentDefaults(jsCode: string): { data: Record<string, any>; properties: Record<string, any> } {
    const data: Record<string, any> = {};
    const properties: Record<string, any> = {};

    try {
      // Extract data: { ... }
      const dataMatch = jsCode.match(/data\s*:\s*\{([^}]+)\}/);
      if (dataMatch && dataMatch[1]) {
        const lines = dataMatch[1].split(',');
        for (const line of lines) {
          const parts = line.split(':');
          if (parts.length === 2 && parts[0] && parts[1]) {
            const key = parts[0].trim();
            const rawVal = parts[1].trim();
            data[key] = this.parseLiteral(rawVal);
          }
        }
      }

      // Extract properties: { ... }
      const propMatch = jsCode.match(/properties\s*:\s*\{([^}]+)\}/);
      if (propMatch && propMatch[1]) {
        const lines = propMatch[1].split(',');
        for (const line of lines) {
          const parts = line.split(':');
          if (parts.length >= 2 && parts[0]) {
            const key = parts[0].trim();
            properties[key] = null;
          }
        }
      }
    } catch {
      // Fallback on empty defaults
    }

    return { data, properties };
  }

  private static parseLiteral(rawVal: string): any {
    if (rawVal === 'true') return true;
    if (rawVal === 'false') return false;
    if (rawVal === 'null') return null;
    if (rawVal === 'undefined') return undefined;
    if (/^-?\d+(\.\d+)?$/.test(rawVal)) return Number(rawVal);
    if ((rawVal.startsWith('"') && rawVal.endsWith('"')) || (rawVal.startsWith("'") && rawVal.endsWith("'"))) {
      return rawVal.slice(1, -1);
    }
    return rawVal;
  }

  private static evaluateNode(node: DOMNode, scope: Record<string, any>): DOMNode | DOMNode[] | null {
    if (node.nodeType === 'comment') {
      return null;
    }

    if (node.nodeType === 'text') {
      const interpolated = this.interpolate(node.nodeValue || '', scope);
      if (!interpolated) return null;
      return new DOMNode('text', undefined, interpolated);
    }

    // Handle wx:if, wx:elif, wx:else
    if (node.hasAttribute('wx:if')) {
      const conditionExpr = node.getAttribute('wx:if') || '';
      const passes = this.evaluateExpression(conditionExpr, scope);
      if (!passes) {
        return null;
      }
    }

    // Handle wx:for
    if (node.hasAttribute('wx:for')) {
      const listExpr = node.getAttribute('wx:for') || '';
      const itemVar = node.getAttribute('wx:for-item') || 'item';
      const indexVar = node.getAttribute('wx:for-index') || 'index';
      const listData = this.evaluateExpression(listExpr, scope);

      if (!Array.isArray(listData) || listData.length === 0) {
        return null;
      }

      const results: DOMNode[] = [];
      listData.forEach((item, index) => {
        const childScope = {
          ...scope,
          [itemVar]: item,
          [indexVar]: index
        };

        const cloned = node.clone(true);
        cloned.removeAttribute('wx:for');
        cloned.removeAttribute('wx:for-item');
        cloned.removeAttribute('wx:for-index');
        cloned.removeAttribute('wx:key');
        cloned.removeAttribute('wx:if');

        const evaluatedItem = this.evaluateElement(cloned, childScope);
        if (evaluatedItem) {
          if (Array.isArray(evaluatedItem)) {
            results.push(...evaluatedItem);
          } else {
            results.push(evaluatedItem);
          }
        }
      });

      return results;
    }

    return this.evaluateElement(node, scope);
  }

  private static evaluateElement(node: DOMNode, scope: Record<string, any>): DOMNode | DOMNode[] | null {
    // If it's a virtual block element <block>, unwrap its children
    if (node.tagName === 'block') {
      const unwrapped: DOMNode[] = [];
      for (const child of node.children) {
        const evaluatedChild = this.evaluateNode(child, scope);
        if (evaluatedChild) {
          if (Array.isArray(evaluatedChild)) {
            unwrapped.push(...evaluatedChild);
          } else {
            unwrapped.push(evaluatedChild);
          }
        }
      }
      return unwrapped;
    }

    const element = new DOMNode('element', node.tagName);

    // Copy and interpolate attributes
    for (const [key, val] of Object.entries(node.attributes)) {
      if (key.startsWith('wx:')) continue;
      const interpolatedVal = this.interpolate(val, scope);
      element.setAttribute(key, interpolatedVal);
    }

    // Evaluate children
    for (const child of node.children) {
      const evaluatedChild = this.evaluateNode(child, scope);
      if (evaluatedChild) {
        if (Array.isArray(evaluatedChild)) {
          for (const c of evaluatedChild) {
            element.appendChild(c);
          }
        } else {
          element.appendChild(evaluatedChild);
        }
      }
    }

    return element;
  }

  public static interpolate(text: string, scope: Record<string, any>): string {
    return text.replace(/\{\{\s*([\s\S]*?)\s*\}\}/g, (_, expr) => {
      const val = this.evaluateExpression(expr, scope);
      if (val === undefined || val === null) return '';
      if (typeof val === 'object') return JSON.stringify(val);
      return String(val);
    });
  }

  public static evaluateExpression(expression: string, scope: Record<string, any>): any {
    const trimmed = expression.trim();
    if (!trimmed) return '';

    // Simple literals
    if (trimmed === 'true') return true;
    if (trimmed === 'false') return false;
    if (trimmed === 'null') return null;
    if (trimmed === 'undefined') return undefined;
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
    if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
      return trimmed.slice(1, -1);
    }

    // Negation !expr
    if (trimmed.startsWith('!') && !trimmed.startsWith('!=')) {
      return !this.evaluateExpression(trimmed.slice(1), scope);
    }

    // Simple ternary: condition ? exprA : exprB
    const ternaryMatch = trimmed.match(/^([^?]+)\?([^:]+):(.*)$/);
    if (ternaryMatch && ternaryMatch[1] && ternaryMatch[2] && ternaryMatch[3] !== undefined) {
      const cond = this.evaluateExpression(ternaryMatch[1], scope);
      return cond
        ? this.evaluateExpression(ternaryMatch[2], scope)
        : this.evaluateExpression(ternaryMatch[3], scope);
    }

    // Logical OR: exprA || exprB
    if (trimmed.includes('||')) {
      const parts = trimmed.split('||');
      for (const part of parts) {
        const val = this.evaluateExpression(part, scope);
        if (val) return val;
      }
      return false;
    }

    // Logical AND: exprA && exprB
    if (trimmed.includes('&&')) {
      const parts = trimmed.split('&&');
      let result: any = true;
      for (const part of parts) {
        result = this.evaluateExpression(part, scope);
        if (!result) return result;
      }
      return result;
    }

    // Equality: a == b or a === b
    const eqMatch = trimmed.match(/^([^=!]+)==(=)?(.*)$/);
    if (eqMatch && eqMatch[1] && eqMatch[3] !== undefined) {
      const left = this.evaluateExpression(eqMatch[1], scope);
      const right = this.evaluateExpression(eqMatch[3], scope);
      return left == right;
    }

    // Inequality: a != b or a !== b
    const neqMatch = trimmed.match(/^([^=!]+)!=(=)?(.*)$/);
    if (neqMatch && neqMatch[1] && neqMatch[3] !== undefined) {
      const left = this.evaluateExpression(neqMatch[1], scope);
      const right = this.evaluateExpression(neqMatch[3], scope);
      return left != right;
    }

    // Property path lookup: item.sub.prop or prop
    return this.resolvePath(trimmed, scope);
  }

  private static resolvePath(path: string, scope: Record<string, any>): any {
    const parts = path.split('.').map(p => p.trim());
    let current: any = scope;

    for (const part of parts) {
      if (current === undefined || current === null) return undefined;
      // Handle array indexing: item[0]
      const arrayIdxMatch = part.match(/^([a-zA-Z0-9_$]+)\[(\d+)\]$/);
      if (arrayIdxMatch && arrayIdxMatch[1] && arrayIdxMatch[2] !== undefined) {
        const prop = arrayIdxMatch[1];
        const idx = Number(arrayIdxMatch[2]);
        current = current[prop] ? current[prop][idx] : undefined;
      } else {
        current = current[part];
      }
    }

    return current;
  }
}

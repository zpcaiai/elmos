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
    const componentData: Record<string, any> = {};

    if (jsContent) {
      const extractedDefaults = this.extractComponentDefaults(jsContent);
      Object.assign(componentData, extractedDefaults.data);
    }

    if (context.props && typeof context.props === 'object') {
      Object.assign(componentData, context.props);
    }
    if (context.state && typeof context.state === 'object') {
      Object.assign(componentData, context.state);
    }

    // 2. Parse WXML into raw DOM nodes
    const rawNodes = HTMLParser.parse(wxmlContent);

    // 3. Create root container
    const root = new DOMNode('element', 'view');
    root.setAttribute('class', 'miniapp-root');

    // 4. Evaluate directives and expressions
    const evaluatedNodes = this.evaluateNodeList(rawNodes, componentData, context);
    for (const evaluated of evaluatedNodes) {
      root.appendChild(evaluated);
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
        const entryRegex = /([a-zA-Z0-9_$]+)\s*:\s*('(?:\\'|[^'])*'|"(?:\\"|[^"])*"|[^,}]+)/g;
        let m: RegExpExecArray | null;
        while ((m = entryRegex.exec(dataMatch[1])) !== null) {
          const key = m[1];
          const rawVal = m[2];
          if (key && rawVal) {
            data[key.trim()] = this.parseLiteral(rawVal.trim());
          }
        }
      }

      // Extract properties: { ... }
      const propMatch = jsCode.match(/properties\s*:\s*\{([^}]+)\}/);
      if (propMatch && propMatch[1]) {
        const propEntryRegex = /([a-zA-Z0-9_$]+)\s*:\s*(?:\{|[^,}]+)/g;
        let m: RegExpExecArray | null;
        while ((m = propEntryRegex.exec(propMatch[1])) !== null) {
          const key = m[1];
          if (key) {
            properties[key.trim()] = null;
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

  private static evaluateNodeList(
    nodes: DOMNode[],
    scope: Record<string, any>,
    context: ComponentRenderContext = {}
  ): DOMNode[] {
    const results: DOMNode[] = [];
    let ifMatched = false;
    let inIfChain = false;

    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      if (!node || node.nodeType === 'comment') continue;

      if (node.nodeType === 'element' && node.hasAttribute('wx:if')) {
        inIfChain = true;
        const conditionExpr = (node.getAttribute('wx:if') || '').replace(/^\{\{|\}\}$/g, '').trim();
        const condVal = this.evaluateExpression(conditionExpr, scope);
        ifMatched = Boolean(condVal);
        if (ifMatched) {
          const evaluated = this.evaluateNode(node, scope, context, true);
          if (evaluated) {
            if (Array.isArray(evaluated)) results.push(...evaluated);
            else results.push(evaluated);
          }
        }
        continue;
      }

      if (node.nodeType === 'element' && node.hasAttribute('wx:elif')) {
        if (!inIfChain) {
          const conditionExpr = (node.getAttribute('wx:elif') || '').replace(/^\{\{|\}\}$/g, '').trim();
          const condVal = this.evaluateExpression(conditionExpr, scope);
          if (condVal) {
            const evaluated = this.evaluateNode(node, scope, context, true);
            if (evaluated) {
              if (Array.isArray(evaluated)) results.push(...evaluated);
              else results.push(evaluated);
            }
          }
          continue;
        }
        if (!ifMatched) {
          const conditionExpr = (node.getAttribute('wx:elif') || '').replace(/^\{\{|\}\}$/g, '').trim();
          const condVal = this.evaluateExpression(conditionExpr, scope);
          if (condVal) {
            ifMatched = true;
            const evaluated = this.evaluateNode(node, scope, context, true);
            if (evaluated) {
              if (Array.isArray(evaluated)) results.push(...evaluated);
              else results.push(evaluated);
            }
          }
        }
        continue;
      }

      if (node.nodeType === 'element' && node.hasAttribute('wx:else')) {
        if (inIfChain && !ifMatched) {
          ifMatched = true;
          const evaluated = this.evaluateNode(node, scope, context, true);
          if (evaluated) {
            if (Array.isArray(evaluated)) results.push(...evaluated);
            else results.push(evaluated);
          }
        }
        inIfChain = false;
        continue;
      }

      if (node.nodeType === 'text' && !(node.nodeValue || '').trim()) {
        continue;
      }

      inIfChain = false;
      const evaluated = this.evaluateNode(node, scope, context, false);
      if (evaluated) {
        if (Array.isArray(evaluated)) results.push(...evaluated);
        else results.push(evaluated);
      }
    }

    return results;
  }

  private static evaluateNode(
    node: DOMNode,
    scope: Record<string, any>,
    context: ComponentRenderContext = {},
    conditionAlreadyChecked = false
  ): DOMNode | DOMNode[] | null {
    if (node.nodeType === 'comment') {
      return null;
    }

    if (node.nodeType === 'text') {
      const interpolated = this.interpolate(node.nodeValue || '', scope).trim();
      if (!interpolated) return null;
      return new DOMNode('text', undefined, interpolated);
    }

    if (!conditionAlreadyChecked) {
      if (node.hasAttribute('wx:if')) {
        const conditionExpr = (node.getAttribute('wx:if') || '').replace(/^\{\{|\}\}$/g, '').trim();
        const passes = this.evaluateExpression(conditionExpr, scope);
        if (!passes) return null;
      } else if (node.hasAttribute('wx:elif') || node.hasAttribute('wx:else')) {
        return null;
      }
    }

    // Handle wx:for
    if (node.hasAttribute('wx:for')) {
      const listExpr = (node.getAttribute('wx:for') || '').replace(/^\{\{|\}\}$/g, '').trim();
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
        cloned.removeAttribute('wx:elif');
        cloned.removeAttribute('wx:else');

        const evaluatedItem = this.evaluateElement(cloned, childScope, context);
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

    return this.evaluateElement(node, scope, context);
  }

  private static evaluateElement(
    node: DOMNode,
    scope: Record<string, any>,
    context: ComponentRenderContext = {}
  ): DOMNode | DOMNode[] | null {
    // If it's a virtual block element <block>, unwrap its children
    if (node.tagName === 'block') {
      return this.evaluateNodeList(node.children, scope, context);
    }

    // If it's a slot, handle slot replacement or fallback
    if (node.tagName === 'slot') {
      const slotName = node.getAttribute('name') || 'default';
      if (context.slots && context.slots[slotName]) {
        const slotContent = context.slots[slotName];
        if (typeof slotContent === 'string') {
          return HTMLParser.parse(slotContent);
        }
        return (slotContent as DOMNode).clone(true);
      }
      return this.evaluateNodeList(node.children, scope, context);
    }

    const element = new DOMNode('element', node.tagName);

    // Copy and interpolate attributes
    for (const [key, val] of Object.entries(node.attributes)) {
      if (key.startsWith('wx:')) continue;
      const interpolatedVal = this.interpolate(val, scope);
      element.setAttribute(key, interpolatedVal);
    }

    // Evaluate children
    const childNodes = this.evaluateNodeList(node.children, scope, context);
    for (const child of childNodes) {
      element.appendChild(child);
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
    const trimmed = expression.replace(/^\{\{|\}\}$/g, "").trim();
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

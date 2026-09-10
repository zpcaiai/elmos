/**
 * Web SSR Evaluator
 *
 * Evaluates Web components (HTML output or FullSyntaxComponentIR) into a HeadlessDOMNode tree,
 * computing standard DOM layouts and styles for cross-platform differential analysis.
 */

import { HeadlessDOMNode, ComponentRenderContext } from './types';
import { DOMNode, HTMLParser, HeadlessBoxLayoutEngine } from './headless-browser-dom';
import { FullSyntaxComponentIR, FullSyntaxNode } from '../full-syntax-ast/types';
import { MiniAppSSREvaluator } from './miniapp-ssr-evaluator';

export class WebSSREvaluator {
  /**
   * Evaluate raw HTML string into a DOMNode tree.
   */
  public static evaluateHTML(html: string): DOMNode {
    const parsed = HTMLParser.parse(html);
    const root = new DOMNode('element', 'div');
    root.setAttribute('class', 'web-ssr-root');

    for (const child of parsed) {
      root.appendChild(child);
    }

    HeadlessBoxLayoutEngine.computeLayout(root);
    return root;
  }

  /**
   * Evaluate a FullSyntaxComponentIR directly with given props and state.
   */
  public static evaluateIR(
    ir: FullSyntaxComponentIR,
    context: ComponentRenderContext = {}
  ): DOMNode {
    const scope: Record<string, any> = {
      ...(ir.props.reduce((acc: Record<string, any>, p) => ({ ...acc, [p.name]: this.parseLiteral(p.defaultValue) }), {})),
      ...(ir.states.reduce((acc: Record<string, any>, s) => ({ ...acc, [s.name]: this.parseLiteral(s.initialValueExpr) }), {})),
      ...(typeof context.props === 'object' ? context.props : {}),
      ...(typeof context.state === 'object' ? context.state : {})
    };

    if (ir.computed) {
      for (const c of ir.computed) {
        if (!(c.name in scope)) {
          let fallbackVal: any = null;
          if (c.name.endsWith("List") || c.name.endsWith("Items") || c.name.endsWith("Commands") || c.name.endsWith("Navigation")) {
            fallbackVal = [];
          } else if (c.name.startsWith("is") || c.name.startsWith("has") || c.name === "english") {
            fallbackVal = false;
          }
          scope[c.name] = fallbackVal;
        }
      }
    }

    const root = new DOMNode('element', 'div');
    root.setAttribute('class', `component-${ir.componentName.toLowerCase()}`);

    if (ir.templateRoot) {
      const renderedChild = this.renderASTNode(ir.templateRoot, scope, context);
      if (renderedChild) {
        if (Array.isArray(renderedChild)) {
          for (const c of renderedChild) {
            root.appendChild(c);
          }
        } else {
          root.appendChild(renderedChild);
        }
      }
    }

    HeadlessBoxLayoutEngine.computeLayout(root);
    return root;
  }

  private static renderASTNode(
    astNode: FullSyntaxNode,
    scope: Record<string, any>,
    context: ComponentRenderContext
  ): DOMNode | DOMNode[] | null {
    switch (astNode.kind) {
      case 'text': {
        const textVal = (astNode.text || '').replace(/\s+/g, ' ');
        if (!textVal || !textVal.trim()) return null;
        return new DOMNode('text', undefined, textVal);
      }

      case 'expression': {
        const val = this.evalExpression(astNode.expression || '', scope);
        const textVal = val !== undefined && val !== null ? String(val).trim() : '';
        if (!textVal) return null;
        return new DOMNode('text', undefined, textVal);
      }

      case 'conditional':
      case 'condition': {
        if (!astNode.condition) return null;
        const passed = this.evalExpression(astNode.condition.test, scope);
        if (passed) {
          return this.renderASTNode(astNode.condition.thenNode, scope, context);
        } else if (astNode.condition.elifBranches) {
          for (const branch of astNode.condition.elifBranches) {
            if (this.evalExpression(branch.test, scope)) {
              return this.renderASTNode(branch.node, scope, context);
            }
          }
        }
        if (astNode.condition.elseNode) {
          return this.renderASTNode(astNode.condition.elseNode, scope, context);
        }
        return null;
      }

      case 'loop': {
        if (!astNode.loop) return null;
        const list = this.evalExpression(astNode.loop.sourceExpr, scope);
        if (!Array.isArray(list)) return null;

        const results: DOMNode[] = [];
        list.forEach((item, index) => {
          const loopScope = {
            ...scope,
            [astNode.loop!.itemName]: item,
            [astNode.loop!.indexName || 'index']: index
          };
          const rendered = this.renderASTNode(astNode.loop!.bodyNode, loopScope, context);
          if (rendered) {
            if (Array.isArray(rendered)) {
              results.push(...rendered);
            } else {
              results.push(rendered);
            }
          }
        });
        return results;
      }

      case 'slot_outlet': {
        const slotName = astNode.slotName || 'default';
        if (context.slots && context.slots[slotName]) {
          const slotContent = context.slots[slotName];
          if (typeof slotContent === 'string') {
            return HTMLParser.parse(slotContent);
          }
          return (slotContent as DOMNode).clone(true);
        }
        // Render fallback slot children if any
        if (astNode.children && astNode.children.length > 0) {
          const fallbackNodes: DOMNode[] = [];
          for (const child of astNode.children) {
            const r = this.renderASTNode(child, scope, context);
            if (r) {
              if (Array.isArray(r)) fallbackNodes.push(...r);
              else fallbackNodes.push(r);
            }
          }
          return fallbackNodes;
        }
        return null;
      }

      case 'fragment': {
        const fragmentChildren: DOMNode[] = [];
        if (astNode.children) {
          for (const child of astNode.children) {
            const r = this.renderASTNode(child, scope, context);
            if (r) {
              if (Array.isArray(r)) fragmentChildren.push(...r);
              else fragmentChildren.push(r);
            }
          }
        }
        return fragmentChildren;
      }

      case 'element':
      case 'component':
      default: {
        const elem = new DOMNode('element', astNode.tag || 'div');

        // Attributes
        if (astNode.attrs) {
          for (const attr of astNode.attrs) {
            if (attr.isDynamic && attr.expression) {
              const dynVal = this.evalExpression(attr.expression, scope);
              if (attr.name.startsWith('aria-')) {
                if (dynVal !== undefined && dynVal !== null) {
                  elem.setAttribute(attr.name, String(dynVal));
                }
              } else if (dynVal !== undefined && dynVal !== null && dynVal !== false) {
                elem.setAttribute(attr.name, dynVal === true ? '' : String(dynVal));
              }
            } else {
              elem.setAttribute(attr.name, attr.value);
            }
          }
        }

        // Children
        if (astNode.children) {
          for (const child of astNode.children) {
            const r = this.renderASTNode(child, scope, context);
            if (r) {
              if (Array.isArray(r)) {
                for (const c of r) elem.appendChild(c);
              } else {
                elem.appendChild(r);
              }
            }
          }
        }

        return elem;
      }
    }
  }

  private static parseLiteral(rawVal?: any): any {
    if (rawVal === undefined || rawVal === null) return undefined;
    if (typeof rawVal !== 'string') return rawVal;
    const trimmed = rawVal.trim();
    if (trimmed === 'true') return true;
    if (trimmed === 'false') return false;
    if (trimmed === 'null') return null;
    if (trimmed === 'undefined') return undefined;
    if (trimmed === '[]') return [];
    if (trimmed === '{}') return {};
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
    if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
      return trimmed.slice(1, -1);
    }
    return trimmed;
  }

  private static evalExpression(expr: string, scope: Record<string, any>): any {
    return MiniAppSSREvaluator.evaluateExpression(expr, scope);
  }
}

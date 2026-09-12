/**
 * Headless Browser Virtual DOM Engine
 *
 * Lightweight, high-performance, hermetic Virtual DOM and Box Layout engine.
 * Capable of parsing HTML/XML strings, manipulating node hierarchies, executing CSS selectors,
 * calculating 2D layout bounding boxes, and serializing trees.
 */

import {
  DOMNodeType,
  HeadlessDOMNode,
  BoxRect,
  ComputedLayout
} from './types';

let idCounter = 1;
function generateNodeId(prefix = 'node'): string {
  return `${prefix}_${Date.now().toString(36)}_${(idCounter++).toString(36)}`;
}

export class DOMNode implements HeadlessDOMNode {
  public id: string;
  public nodeType: DOMNodeType;
  public tagName?: string;
  public nodeValue?: string;
  public attributes: Record<string, string> = {};
  public classList: string[] = [];
  public style: Record<string, string> = {};
  public children: DOMNode[] = [];
  public parent?: DOMNode;
  public computedLayout?: ComputedLayout;
  public sourceLocation?: { line: number; column: number };

  constructor(nodeType: DOMNodeType, tagName?: string, nodeValue?: string) {
    this.id = generateNodeId(tagName ? tagName.toLowerCase() : nodeType);
    this.nodeType = nodeType;
    if (tagName) {
      this.tagName = tagName.toLowerCase();
    }
    if (nodeValue !== undefined) {
      this.nodeValue = nodeValue;
    }
  }

  public appendChild(child: DOMNode): DOMNode {
    if (child.parent) {
      child.parent.removeChild(child);
    }
    child.parent = this;
    this.children.push(child);
    return child;
  }

  public insertBefore(newChild: DOMNode, referenceChild: DOMNode | null): DOMNode {
    if (!referenceChild) {
      return this.appendChild(newChild);
    }
    const idx = this.children.indexOf(referenceChild);
    if (idx === -1) {
      return this.appendChild(newChild);
    }
    if (newChild.parent) {
      newChild.parent.removeChild(newChild);
    }
    newChild.parent = this;
    this.children.splice(idx, 0, newChild);
    return newChild;
  }

  public removeChild(child: DOMNode): DOMNode {
    const idx = this.children.indexOf(child);
    if (idx !== -1) {
      this.children.splice(idx, 1);
      child.parent = undefined;
    }
    return child;
  }

  public setAttribute(name: string, value: string): void {
    const lower = name.toLowerCase();
    this.attributes[lower] = value;
    if (lower === 'class' || lower === 'classname') {
      this.classList = value.trim().split(/\s+/).filter(Boolean);
    } else if (lower === 'style') {
      this.parseStyleAttribute(value);
    }
  }

  public getAttribute(name: string): string | undefined {
    return this.attributes[name.toLowerCase()];
  }

  public hasAttribute(name: string): boolean {
    return this.attributes[name.toLowerCase()] !== undefined;
  }

  public removeAttribute(name: string): void {
    const lower = name.toLowerCase();
    delete this.attributes[lower];
    if (lower === 'class' || lower === 'classname') {
      this.classList = [];
    } else if (lower === 'style') {
      this.style = {};
    }
  }

  public addClass(cls: string): void {
    const trimmed = cls.trim();
    if (trimmed && !this.classList.includes(trimmed)) {
      this.classList.push(trimmed);
      this.attributes['class'] = this.classList.join(' ');
    }
  }

  public removeClass(cls: string): void {
    const idx = this.classList.indexOf(cls.trim());
    if (idx !== -1) {
      this.classList.splice(idx, 1);
      this.attributes['class'] = this.classList.join(' ');
    }
  }

  public hasClass(cls: string): boolean {
    return this.classList.includes(cls.trim());
  }

  private parseStyleAttribute(styleStr: string): void {
    this.style = {};
    const declarations = styleStr.split(';');
    for (const decl of declarations) {
      const parts = decl.split(':');
      if (parts.length === 2 && parts[0] && parts[1]) {
        const key = parts[0].trim().toLowerCase();
        const val = parts[1].trim();
        if (key && val) {
          this.style[key] = val;
        }
      }
    }
  }

  public get textContent(): string {
    if (this.nodeType === 'text') {
      return this.nodeValue || '';
    }
    return this.children
      .map(c => c.textContent.trim())
      .filter(Boolean)
      .join(' ');
  }

  public set textContent(val: string) {
    this.children = [];
    if (val) {
      const textNode = new DOMNode('text', undefined, val);
      this.appendChild(textNode);
    }
  }

  public get innerHTML(): string {
    return this.children.map(c => c.outerHTML).join('');
  }

  public set innerHTML(html: string) {
    this.children = [];
    const parsed = HTMLParser.parse(html);
    for (const child of parsed) {
      this.appendChild(child);
    }
  }

  public get outerHTML(): string {
    if (this.nodeType === 'text') {
      return escapeHTML(this.nodeValue || '');
    }
    if (this.nodeType === 'comment') {
      return `<!--${this.nodeValue || ''}-->`;
    }
    const tag = this.tagName || 'div';
    const attrs = Object.entries(this.attributes)
      .map(([k, v]) => ` ${k}="${escapeAttr(v)}"`)
      .join('');

    const selfClosing = ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'meta', 'param', 'source', 'track', 'wbr'];
    if (selfClosing.includes(tag) && this.children.length === 0) {
      return `<${tag}${attrs} />`;
    }
    return `<${tag}${attrs}>${this.innerHTML}</${tag}>`;
  }

  public querySelector(selector: string): DOMNode | null {
    const results = this.querySelectorAll(selector);
    return results.length > 0 ? (results[0] ?? null) : null;
  }

  public querySelectorAll(selector: string): DOMNode[] {
    const tokens = selector.trim().split(/\s+/);
    let currentNodes: DOMNode[] = [this];

    for (const token of tokens) {
      const nextNodes: DOMNode[] = [];
      for (const node of currentNodes) {
        nextNodes.push(...this.matchDirectDescendants(node, token));
      }
      currentNodes = nextNodes;
    }
    return currentNodes;
  }

  private matchDirectDescendants(root: DOMNode, singleSelector: string): DOMNode[] {
    const matches: DOMNode[] = [];
    const traverse = (node: DOMNode) => {
      for (const child of node.children) {
        if (child.nodeType === 'element' && this.matchesSimple(child, singleSelector)) {
          matches.push(child);
        }
        traverse(child);
      }
    };
    traverse(root);
    return matches;
  }

  private matchesSimple(node: DOMNode, selector: string): boolean {
    if (!selector || selector === '*') return true;
    if (selector.startsWith('.')) {
      return node.hasClass(selector.slice(1));
    }
    if (selector.startsWith('#')) {
      return node.getAttribute('id') === selector.slice(1);
    }
    if (selector.includes('.')) {
      const [tag, ...classes] = selector.split('.');
      if (tag && node.tagName !== tag.toLowerCase()) return false;
      return classes.every(c => node.hasClass(c));
    }
    if (selector.includes('#')) {
      const [tag, id] = selector.split('#');
      if (tag && node.tagName !== tag.toLowerCase()) return false;
      return node.getAttribute('id') === id;
    }
    return node.tagName === selector.toLowerCase();
  }

  public clone(deep = true): DOMNode {
    const cloneNode = new DOMNode(this.nodeType, this.tagName, this.nodeValue);
    cloneNode.attributes = { ...this.attributes };
    cloneNode.classList = [...this.classList];
    cloneNode.style = { ...this.style };
    if (this.sourceLocation) {
      cloneNode.sourceLocation = { ...this.sourceLocation };
    }
    if (this.computedLayout) {
      cloneNode.computedLayout = JSON.parse(JSON.stringify(this.computedLayout));
    }
    if (deep) {
      for (const child of this.children) {
        cloneNode.appendChild(child.clone(true));
      }
    }
    return cloneNode;
  }
}

function escapeHTML(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeAttr(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * Robust HTML / WXML string tokenizer and parser
 */
export class HTMLParser {
  public static parse(html: string): DOMNode[] {
    const roots: DOMNode[] = [];
    const stack: DOMNode[] = [];

    // Regex matching tags, comments, and plain text chunks
    // Quoted strings inside tag attributes can contain '>' e.g. wx:if="{{ a > b }}" or value="a > b"
    const tagRegex = /<!--[\s\S]*?-->|<\/?[a-zA-Z0-9_-]+(?:\s+(?:[^>"']|"[^"]*"|'[^']*')*)*\s*\/?>|[^<]+/g;
    let match: RegExpExecArray | null;

    while ((match = tagRegex.exec(html)) !== null) {
      const text = match[0];
      if (!text) continue;

      if (text.startsWith('<!--')) {
        // Comment
        const content = text.slice(4, -3);
        const commentNode = new DOMNode('comment', undefined, content);
        const top = stack[stack.length - 1];
        if (top) {
          top.appendChild(commentNode);
        } else {
          roots.push(commentNode);
        }
      } else if (text.startsWith('</')) {
        // End tag
        const closingTagMatch = text.match(/<\/([a-zA-Z0-9_-]+)/);
        if (closingTagMatch && closingTagMatch[1]) {
          const closingTag = closingTagMatch[1].toLowerCase();
          for (let i = stack.length - 1; i >= 0; i--) {
            const item = stack[i];
            if (item && item.tagName === closingTag) {
              stack.splice(i);
              break;
            }
          }
        }
      } else if (text.startsWith('<')) {
        // Start tag or self-closing tag
        const tagMatch = text.match(/<([a-zA-Z0-9_-]+)([\s\S]*?)(\/?)>/);
        if (tagMatch && tagMatch[1]) {
          const tagName = tagMatch[1].toLowerCase();
          const rawAttrs = tagMatch[2] || '';
          const isSelfClosing = tagMatch[3] === '/' || ['input', 'img', 'br', 'hr', 'meta'].includes(tagName);

          const elementNode = new DOMNode('element', tagName);
          parseAttributes(rawAttrs, elementNode);

          const top = stack[stack.length - 1];
          if (top) {
            top.appendChild(elementNode);
          } else {
            roots.push(elementNode);
          }

          if (!isSelfClosing) {
            stack.push(elementNode);
          }
        }
      } else {
        // Plain text
        const content = decodeHTMLEntities(text).trim();
        if (content.length > 0) {
          const textNode = new DOMNode('text', undefined, content);
          const top = stack[stack.length - 1];
          if (top) {
            top.appendChild(textNode);
          } else {
            roots.push(textNode);
          }
        }
      }
    }

    return roots;
  }
}

function parseAttributes(attrString: string, node: DOMNode): void {
  const attrRegex = /([a-zA-Z0-9_:@.-]+)(?:=(?:"((?:\{\{[\s\S]*?\}\}|[^"])*)"|'((?:\{\{[\s\S]*?\}\}|[^'])*)'|([^\s>]+)))?/g;
  let match: RegExpExecArray | null;
  while ((match = attrRegex.exec(attrString)) !== null) {
    const key = match[1];
    if (!key) continue;
    const val = match[2] ?? match[3] ?? match[4] ?? '';
    node.setAttribute(key, decodeHTMLEntities(val));
  }
}

function decodeHTMLEntities(text: string): string {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ');
}

/**
 * 2D Box Layout Calculation Engine
 * Estimates bounding boxes (x, y, width, height) based on standard CSS box model.
 */
export class HeadlessBoxLayoutEngine {
  public static computeLayout(
    root: DOMNode,
    viewportWidth = 375, // Default mobile / miniapp viewport width
    viewportHeight = 667
  ): void {
    const initialRect: BoxRect = {
      x: 0,
      y: 0,
      width: viewportWidth,
      height: viewportHeight
    };

    root.computedLayout = {
      rect: initialRect,
      display: 'block',
      visibility: 'visible'
    };

    this.layoutNode(root, 0, 0, viewportWidth);
  }

  private static layoutNode(
    node: DOMNode,
    currentX: number,
    currentY: number,
    availableWidth: number
  ): { width: number; height: number } {
    const style = node.style;
    const isHidden = style['display'] === 'none' || node.getAttribute('hidden') !== undefined;
    if (isHidden) {
      node.computedLayout = {
        rect: { x: currentX, y: currentY, width: 0, height: 0 },
        display: 'none',
        visibility: 'hidden'
      };
      return { width: 0, height: 0 };
    }

    const display = style['display'] || (this.isInlineTag(node.tagName) ? 'inline' : 'block');
    const isFlex = display.includes('flex');
    const flexDirection = (style['flex-direction'] as any) || 'row';

    // Parse dimensions if specified
    const explicitWidth = this.parseDimension(style['width'], availableWidth);
    const explicitHeight = this.parseDimension(style['height'], 0);

    const padding = this.parsePadding(style);
    const margin = this.parseMargin(style);

    const innerX = currentX + margin.left + padding.left;
    let innerY = currentY + margin.top + padding.top;
    const innerWidth = (explicitWidth !== null ? explicitWidth : availableWidth) - margin.left - margin.right - padding.left - padding.right;

    let contentWidth = 0;
    let contentHeight = 0;

    if (node.nodeType === 'text') {
      const textLen = (node.nodeValue || '').trim().replace(/\s+/g, ' ').length;
      contentWidth = Math.min(textLen * 14, Math.max(0, innerWidth));
      const lines = Math.max(1, Math.ceil((textLen * 14) / Math.max(1, innerWidth)));
      contentHeight = lines * 20; // 20px line height
    } else if (isFlex && flexDirection === 'row') {
      let flexCursorX = innerX;
      let maxChildHeight = 0;
      for (const child of node.children) {
        const childDim = this.layoutNode(child, flexCursorX, innerY, innerWidth);
        flexCursorX += childDim.width;
        if (childDim.height > maxChildHeight) {
          maxChildHeight = childDim.height;
        }
      }
      contentWidth = flexCursorX - innerX;
      contentHeight = maxChildHeight;
    } else {
      // Normal block flow
      let blockCursorY = innerY;
      let maxChildWidth = 0;
      for (const child of node.children) {
        const childDim = this.layoutNode(child, innerX, blockCursorY, innerWidth);
        blockCursorY += childDim.height;
        if (childDim.width > maxChildWidth) {
          maxChildWidth = childDim.width;
        }
      }
      contentWidth = maxChildWidth;
      contentHeight = blockCursorY - innerY;
    }

    if (contentHeight === 0) {
      const lowerTag = (node.tagName || '').toLowerCase();
      if (lowerTag === 'textarea') {
        const rawRows = (node.getAttribute('rows') || '3').replace(/[^0-9]/g, '');
        const rows = parseInt(rawRows || '3', 10);
        contentHeight = (isNaN(rows) || rows <= 0 ? 3 : rows) * 20;
      } else if (lowerTag === 'input') {
        contentHeight = 28;
      }
    }

    const totalWidth = explicitWidth !== null ? explicitWidth : Math.max(contentWidth, innerWidth > 0 && display === 'block' ? innerWidth : 0) + padding.left + padding.right + margin.left + margin.right;
    const totalHeight = explicitHeight !== null ? explicitHeight : contentHeight + padding.top + padding.bottom + margin.top + margin.bottom;

    node.computedLayout = {
      rect: {
        x: currentX,
        y: currentY,
        width: Math.round(totalWidth),
        height: Math.round(totalHeight)
      },
      display,
      visibility: 'visible',
      flexDirection: isFlex ? flexDirection : undefined
    };

    return { width: totalWidth, height: totalHeight };
  }

  public static isInlineTag(tag?: string): boolean {
    if (!tag) return true;
    return ['span', 'a', 'link', 'navigator', 'text', 'strong', 'em', 'b', 'i', 'label', 'icon', 'small', 'code', 'sub', 'sup', 'cite', 'time'].includes(tag.toLowerCase());
  }

  private static parseDimension(val?: string, ref = 0): number | null {
    if (!val) return null;
    const trimmed = val.trim();
    if (trimmed.endsWith('px')) {
      return parseFloat(trimmed);
    }
    if (trimmed.endsWith('rpx')) {
      // 750rpx = 375px -> 2rpx = 1px
      return parseFloat(trimmed) / 2;
    }
    if (trimmed.endsWith('%')) {
      return (parseFloat(trimmed) / 100) * ref;
    }
    if (trimmed.endsWith('rem')) {
      return parseFloat(trimmed) * 16;
    }
    const num = parseFloat(trimmed);
    return isNaN(num) ? null : num;
  }

  private static parsePadding(style: Record<string, string>): { top: number; right: number; bottom: number; left: number } {
    return {
      top: this.parseDimension(style['padding-top']) || 0,
      right: this.parseDimension(style['padding-right']) || 0,
      bottom: this.parseDimension(style['padding-bottom']) || 0,
      left: this.parseDimension(style['padding-left']) || 0
    };
  }

  private static parseMargin(style: Record<string, string>): { top: number; right: number; bottom: number; left: number } {
    return {
      top: this.parseDimension(style['margin-top']) || 0,
      right: this.parseDimension(style['margin-right']) || 0,
      bottom: this.parseDimension(style['margin-bottom']) || 0,
      left: this.parseDimension(style['margin-left']) || 0
    };
  }
}

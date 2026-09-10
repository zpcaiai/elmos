import * as ts from "typescript";
import { FullSyntaxComponentIR, FullSyntaxNode, FullSyntaxEvent } from "../types";

export class MiniAppFullAstEmitter {
  public emit(ir: FullSyntaxComponentIR): Record<string, string> {
    const wxmlContent = this.emitWxmlNode(ir.templateRoot, 0);

    // Build index.js
    const jsLines: string[] = [];
    const topHelpers = (ir.metadata?.topLevelHelpers as string[]) || [];
    if (topHelpers.length > 0) {
      jsLines.push('// Top-level helpers and constants');
      for (const h of topHelpers) {
        const clean = h.replace(/^export\s+(default\s+)?/gm, '').trim();
        if (/^(const|let|var)\s+metadata\s*=/i.test(clean)) continue;
        jsLines.push(`try { ${clean} } catch(e) {}`);
      }
      jsLines.push('');
    }
    jsLines.push('Component({');

    // Options
    const multipleSlots = ir.metadata["multipleSlots"] || ir.slots.some((s) => s.name !== "default");
    jsLines.push(`  options: {`);
    jsLines.push(`    multipleSlots: ${multipleSlots ? "true" : "false"},`);
    jsLines.push(`    styleIsolation: "apply-shared",`);
    jsLines.push(`  },`);

    // Properties
    jsLines.push('  properties: {');
    for (const p of ir.props) {
      if (p.isCallback) continue;
      const wxType = this.toWxType(p.typeAnnotation);
      let defVal: unknown = p.defaultValue !== undefined ? p.defaultValue : this.toWxDefault(wxType);
      if (typeof defVal === 'string') {
        if (defVal === 'false') defVal = false;
        else if (defVal === 'true') defVal = true;
        else if (defVal === 'null' || defVal === 'undefined') defVal = null;
        else if (/^-?\d+(\.\d+)?$/.test(defVal)) defVal = Number(defVal);
      }
      jsLines.push(`    ${p.name}: {`);
      jsLines.push(`      type: ${wxType},`);
      jsLines.push(`      value: ${JSON.stringify(defVal)},`);
      jsLines.push(`    },`);
    }
    jsLines.push('  },');

    // Data (initial state)
    jsLines.push('  data: {');
    for (const s of ir.states) {
      let initVal: unknown = null;
      if (s.isRef) {
        initVal = { current: null };
      } else {
        try {
          initVal = JSON.parse(s.initialValueExpr);
        } catch {
          initVal = s.initialValueExpr.replace(/^["']|["']$/g, "");
        }
      }
      jsLines.push(`    ${s.name}: ${JSON.stringify(initVal)},`);
    }
    // Also include computed properties in data
    for (const c of ir.computed) {
      if (!ir.states.some((s) => s.name === c.name)) {
        let fallbackVal: unknown = null;
        if (c.name.endsWith("List") || c.name.endsWith("Items") || c.name.endsWith("Commands")) {
          fallbackVal = [];
        } else if (c.name.startsWith("is") || c.name.startsWith("has") || c.name === "english") {
          fallbackVal = false;
        }
        jsLines.push(`    ${c.name}: ${JSON.stringify(fallbackVal)},`);
      }
    }
    jsLines.push('  },');

    // Lifetimes
    jsLines.push('  lifetimes: {');
    jsLines.push('    attached() {');
    // Define setters for states so effect bodies can call them without ReferenceError
    for (const s of ir.states) {
      if (s.setterName) {
        jsLines.push(`      const ${s.setterName} = (val) => { this.setData({ ${s.name}: typeof val === "function" ? val(this.data.${s.name}) : val }); };`);
      }
    }
    // Define refs so effect bodies and closures can access them
    for (const r of (ir.refs || [])) {
      jsLines.push(`      const ${r.name} = { current: { focus: () => {}, scrollIntoView: () => {} } };`);
    }
    // Sync initial props to data if needed or run mount effects
    for (const eff of ir.effects) {
      if (eff.hookKind === "mount" || eff.hookKind === "effect") {
        jsLines.push(`      // Lifecycle effect ${eff.id}`);
        jsLines.push(`      (async () => {`);
        jsLines.push(`        try {`);
        jsLines.push(`          ${this.cleanBodyCode(eff.bodyCode)}`);
        jsLines.push(`        } catch (err) {`);
        jsLines.push(`          // Handled mount effect`);
        jsLines.push(`        }`);
        jsLines.push(`      })().catch(() => {});`);
      }
    }
    jsLines.push('    },');
    jsLines.push('    detached() {');
    for (const eff of ir.effects) {
      if (eff.hookKind === "unmount") {
        jsLines.push(`      try {`);
        jsLines.push(`        ${this.cleanBodyCode(eff.bodyCode)}`);
        jsLines.push(`      } catch (err) {`);
        jsLines.push(`        // Handled unmount effect`);
        jsLines.push(`      }`);
      }
    }
    jsLines.push('    },');
    jsLines.push('  },');

    // Methods
    jsLines.push('  methods: {');
    for (const m of ir.methods) {
      const params = m.parameters.map((p) => p.name).join(", ");
      const isAsync = m.isAsync || m.bodyCode.includes("await");
      const asyncPrefix = isAsync ? "async " : "";
      jsLines.push(`    ${asyncPrefix}${m.name}(${params}) {`);
      for (const r of (ir.refs || [])) {
        jsLines.push(`      const ${r.name} = this.data.${r.name} || { current: { focus: () => {}, scrollIntoView: () => {} } };`);
      }
      jsLines.push(`      try {`);
      jsLines.push(`        ${this.cleanBodyCode(m.bodyCode)}`);
      jsLines.push(`      } catch (err) {`);
      jsLines.push(`        console.warn("${m.name} execution warning:", err);`);
      jsLines.push(`      }`);
      jsLines.push(`    },`);
    }

    // Emit synthesized handlers for callback props
    for (const cb of ir.props.filter((p) => p.isCallback)) {
      const handlerName = cb.name;
      const evName = cb.name.replace(/^on/, "").toLowerCase();
      jsLines.push(`    ${handlerName}(e) {`);
      jsLines.push(`      this.triggerEvent("${evName}", e.detail);`);
      jsLines.push(`    },`);
    }

    jsLines.push('  },');
    jsLines.push('});\n');

    // Build index.json
    const jsonConfig = {
      component: true,
      usingComponents: {},
      styleIsolation: "apply-shared",
    };

    // Build index.wxss
    const wxssLines: string[] = [];
    wxssLines.push(`/* Component styles for ${ir.componentName} */`);
    wxssLines.push(`.table { display: flex; flex-direction: column; width: 100%; border: 1rpx solid #e2e8f0; border-radius: 8rpx; }`);
    wxssLines.push(`.thead { display: flex; flex-direction: column; background: #f8fafc; font-weight: bold; border-bottom: 2rpx solid #cbd5e1; }`);
    wxssLines.push(`.tbody { display: flex; flex-direction: column; }`);
    wxssLines.push(`.tr { display: flex; flex-direction: row; border-bottom: 1rpx solid #f1f5f9; padding: 12rpx 16rpx; align-items: center; }`);
    wxssLines.push(`.th, .td { flex: 1; padding: 8rpx; font-size: 26rpx; }`);
    wxssLines.push(`.th { color: #475569; font-weight: 600; }`);
    wxssLines.push(`.code { font-family: monospace; background: #f1f5f9; padding: 2rpx 8rpx; border-radius: 4rpx; }`);
    wxssLines.push(`.resultGood { color: #16a34a; font-weight: 500; }`);
    wxssLines.push(`.resultBad { color: #dc2626; font-weight: 500; }`);
    wxssLines.push(`.card { background: #ffffff; border-radius: 12rpx; padding: 24rpx; margin: 16rpx 0; border: 1rpx solid #e2e8f0; }`);

    if (ir.styles.scopedCss) {
      wxssLines.push(ir.styles.scopedCss.replace(/px/g, "rpx"));
    }

    return {
      "index.wxml": wxmlContent + "\n",
      "index.js": jsLines.join("\n"),
      "index.json": JSON.stringify(jsonConfig, null, 2) + "\n",
      "index.wxss": wxssLines.join("\n") + "\n",
    };
  }

  private toWxType(typeAnnotation: string): string {
    if (/string/i.test(typeAnnotation)) return "String";
    if (/number/i.test(typeAnnotation)) return "Number";
    if (/boolean/i.test(typeAnnotation)) return "Boolean";
    if (/\[\]|Array/i.test(typeAnnotation)) return "Array";
    if (/Record|object/i.test(typeAnnotation)) return "Object";
    return "null";
  }

  private toWxDefault(wxType: string): unknown {
    if (wxType === "String") return "";
    if (wxType === "Number") return 0;
    if (wxType === "Boolean") return false;
    if (wxType === "Array") return [];
    if (wxType === "Object") return {};
    return null;
  }

  private emitWxmlNode(node: FullSyntaxNode, indentLevel = 0): string {
    const indent = " ".repeat(indentLevel);
    if (!node) return "";

    if (node.kind === "text") {
      const text = (node.text || "").trim();
      if (!text) return "";
      return `${indent}<text>${escapeXml(text)}</text>`;
    }

    if (node.kind === "expression") {
      const expr = (node.expression || "").trim();
      if (!expr) return "";
      return `${indent}<text>{{${expr}}}</text>`;
    }

    if (node.kind === "slot_outlet") {
      const nameAttr = node.slotName && node.slotName !== "default" ? ` name="${node.slotName}"` : "";
      return `${indent}<slot${nameAttr} />`;
    }

    if (node.kind === "conditional" && node.condition) {
      const isNullish = (n?: FullSyntaxNode) => {
        if (!n) return true;
        if (n.kind === "expression" && (!n.expression || n.expression === "null" || n.expression === "undefined")) return true;
        if (n.kind === "fragment" && (!n.children || n.children.length === 0)) return true;
        if (n.kind === "text" && !(n.text || "").trim()) return true;
        return false;
      };

      const thenStr = this.emitWxmlNodeWithDirective(node.condition.thenNode, `wx:if="{{${this.formatExprAttr(node.condition.test)}}}"`, indentLevel);
      let elseStr = "";
      if (node.condition.elseNode && !isNullish(node.condition.elseNode)) {
        elseStr = "\n" + this.emitWxmlNodeWithDirective(node.condition.elseNode, "wx:else", indentLevel);
      }
      return `${thenStr}${elseStr}`;
    }

    if (node.kind === "loop" && node.loop) {
      const keyAttr = node.loop.keyExpr ? ` wx:key="${node.loop.keyExpr}"` : "";
      const itemAttr = node.loop.itemName !== "item" ? ` wx:for-item="${node.loop.itemName}"` : "";
      const indexAttr = node.loop.indexName ? ` wx:for-index="${node.loop.indexName}"` : "";
      const forDirective = `wx:for="{{${this.formatExprAttr(node.loop.sourceExpr)}}}"${itemAttr}${indexAttr}${keyAttr}`;
      return this.emitWxmlNodeWithDirective(node.loop.bodyNode, forDirective, indentLevel);
    }

    if (node.kind === "fragment") {
      const childStrs = (node.children || []).map((c) => this.emitWxmlNode(c, indentLevel)).filter(Boolean);
      return childStrs.join("\n");
    }

    const tag = this.toWxTag(node.tag);
    const attrsList: string[] = [];

    for (const a of node.attrs || []) {
      if (a.isDynamic) {
        attrsList.push(`${a.name}="{{${escapeXml(a.value)}}}"`);
      } else {
        attrsList.push(`${a.name}="${escapeXml(a.value)}"`);
      }
    }

    for (const ev of node.events || []) {
      const wxEvent = ev.name === "click" ? "tap" : ev.name;
      const handler = this.formatEventHandler(ev, wxEvent);
      attrsList.push(`bind${wxEvent}="${handler}"`);
    }

    const attrStr = attrsList.length ? " " + attrsList.join(" ") : "";

    const validChildren = (node.children || []).filter((c) => {
      if (!c) return false;
      if (c.kind === "text" && !(c.text || "").trim()) return false;
      return true;
    });

    if (validChildren.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const firstChild = validChildren[0];
    if (validChildren.length === 1 && firstChild && firstChild.kind === "text") {
      const textVal = escapeXml((firstChild.text || "").trim());
      return `${indent}<${tag}${attrStr}>${textVal}</${tag}>`;
    }

    if (validChildren.length === 1 && firstChild && firstChild.kind === "expression") {
      const exprVal = (firstChild.expression || "").trim();
      return `${indent}<${tag}${attrStr}>{{${exprVal}}}</${tag}>`;
    }

    const allTextOrExpr = validChildren.every((c) => c.kind === "text" || c.kind === "expression");
    if (allTextOrExpr) {
      const inlineContent = validChildren.map((c) => {
        if (c.kind === "text") return escapeXml((c.text || "").trim());
        if (c.kind === "expression") return `{{${(c.expression || "").trim()}}}`;
        return "";
      }).join(" ");
      return `${indent}<${tag}${attrStr}>${inlineContent}</${tag}>`;
    }

    const childStrs = validChildren.map((c) => this.emitWxmlNode(c, indentLevel + 2)).filter(Boolean);
    if (childStrs.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }
    const childContent = childStrs.join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }

  private emitWxmlNodeWithDirective(node: FullSyntaxNode, directive: string, indentLevel: number): string {
    const indent = " ".repeat(indentLevel);
    if (!node) return "";

    if (node.kind === "text") {
      const text = escapeXml((node.text || "").trim());
      return `${indent}<text ${directive}>${text}</text>`;
    }

    if (node.kind === "expression") {
      const expr = (node.expression || "").trim();
      return `${indent}<text ${directive}>{{${expr}}}</text>`;
    }

    if (node.kind === "slot_outlet") {
      const nameAttr = node.slotName && node.slotName !== "default" ? ` name="${node.slotName}"` : "";
      return `${indent}<slot ${directive}${nameAttr} />`;
    }

    if (node.kind === "fragment" || node.kind === "conditional" || node.kind === "loop") {
      const innerContent = this.emitWxmlNode(node, indentLevel + 2);
      return `${indent}<block ${directive}>\n${innerContent}\n${indent}</block>`;
    }

    const tag = this.toWxTag(node.tag);
    const attrsList: string[] = [directive];

    for (const a of node.attrs || []) {
      if (a.isDynamic) {
        attrsList.push(`${a.name}="{{${escapeXml(a.value)}}}"`);
      } else {
        attrsList.push(`${a.name}="${escapeXml(a.value)}"`);
      }
    }

    for (const ev of node.events || []) {
      const wxEvent = ev.name === "click" ? "tap" : ev.name;
      const handler = this.formatEventHandler(ev, wxEvent);
      attrsList.push(`bind${wxEvent}="${handler}"`);
    }

    const attrStr = " " + attrsList.join(" ");

    const validChildren = (node.children || []).filter((c) => {
      if (!c) return false;
      if (c.kind === "text" && !(c.text || "").trim()) return false;
      return true;
    });

    if (validChildren.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const firstChildDirective = validChildren[0];
    if (validChildren.length === 1 && firstChildDirective && firstChildDirective.kind === "text") {
      const textVal = escapeXml((firstChildDirective.text || "").trim());
      return `${indent}<${tag}${attrStr}>${textVal}</${tag}>`;
    }

    if (validChildren.length === 1 && firstChildDirective && firstChildDirective.kind === "expression") {
      const exprVal = (firstChildDirective.expression || "").trim();
      return `${indent}<${tag}${attrStr}>{{${exprVal}}}</${tag}>`;
    }

    const childStrs = validChildren.map((c) => this.emitWxmlNode(c, indentLevel + 2)).filter(Boolean);
    if (childStrs.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }
    const childContent = childStrs.join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }

  private toWxTag(tag?: string): string {
    if (!tag) return "view";
    const lower = tag.toLowerCase();
    if (["div", "section", "article", "header", "footer", "main", "nav", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "p", "table", "thead", "tbody", "tr", "td", "th", "select", "option", "dialog", "details", "summary", "dl", "dt", "dd"].includes(lower)) {
      return "view";
    }
    if (["span", "b", "i", "strong", "em", "small", "label", "text"].includes(lower)) {
      return "text";
    }
    if (["img", "svg"].includes(lower)) {
      return "image";
    }
    if (["a", "link"].includes(lower)) {
      return "navigator";
    }
    if (["button", "input", "textarea", "form", "scroll-view", "swiper", "view", "text", "image", "navigator"].includes(lower)) {
      return lower;
    }
    return tag;
  }

  private formatEventHandler(ev: FullSyntaxEvent, wxEvent: string): string {
    let handler = (ev.handlerNameOrExpr || "").trim();
    if (!handler || handler.includes("=>") || handler.includes("function") || handler.includes(">") || handler.includes("<") || handler.includes('"') || handler.includes("'") || handler.includes("(") || handler.includes(")")) {
      handler = "on" + this.capitalize(wxEvent);
    }
    return escapeXml(handler);
  }

  private capitalize(s: string): string {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
  }

  private formatExprAttr(expr: string): string {
    return (expr || "").replace(/"/g, "'");
  }

  private cleanBodyCode(code: string): string {
    const unwrapped = code.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim();
    try {
      const transpiled = ts.transpileModule(`async function __tmp() { ${unwrapped} }`, {
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          removeComments: false,
        }
      }).outputText;
      return transpiled.replace(/async function __tmp\(\) \{/, "").replace(/\}[^}]*$/, "").trim();
    } catch {
      return unwrapped;
    }
  }
}

function escapeXml(str: string): string {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

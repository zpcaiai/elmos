import { FullSyntaxComponentIR, FullSyntaxNode } from "../types";

export class MiniAppFullAstEmitter {
  public emit(ir: FullSyntaxComponentIR): Record<string, string> {
    const wxmlContent = this.emitWxmlNode(ir.templateRoot, 0);

    // Build index.js
    const jsLines: string[] = [];
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
      const defVal = p.defaultValue !== undefined ? p.defaultValue : this.toWxDefault(wxType);
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
      try {
        initVal = JSON.parse(s.initialValueExpr);
      } catch {
        initVal = s.initialValueExpr.replace(/^["']|["']$/g, "");
      }
      jsLines.push(`    ${s.name}: ${JSON.stringify(initVal)},`);
    }
    jsLines.push('  },');

    // Lifetimes
    jsLines.push('  lifetimes: {');
    jsLines.push('    attached() {');
    // Sync initial props to data if needed or run mount effects
    for (const eff of ir.effects) {
      if (eff.hookKind === "mount" || eff.hookKind === "effect") {
        jsLines.push(`      // Lifecycle effect ${eff.id}`);
        jsLines.push(`      try {`);
        jsLines.push(`        ${eff.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
        jsLines.push(`      } catch (err) {`);
        jsLines.push(`        console.error("Effect execution error:", err);`);
        jsLines.push(`      }`);
      }
    }
    jsLines.push('    },');
    jsLines.push('    detached() {');
    for (const eff of ir.effects) {
      if (eff.hookKind === "unmount") {
        jsLines.push(`      ${eff.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
      }
    }
    jsLines.push('    },');
    jsLines.push('  },');

    // Methods
    jsLines.push('  methods: {');
    for (const m of ir.methods) {
      const params = m.parameters.map((p) => p.name).join(", ");
      jsLines.push(`    ${m.name}(${params}) {`);
      jsLines.push(`      ${m.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
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
      return `${indent}<text>${escapeXml(node.text || "")}</text>`;
    }

    if (node.kind === "expression") {
      return `${indent}<text>{{${node.expression || ""}}}</text>`;
    }

    if (node.kind === "slot_outlet") {
      const nameAttr = node.slotName && node.slotName !== "default" ? ` name="${node.slotName}"` : "";
      return `${indent}<slot${nameAttr} />`;
    }

    if (node.kind === "conditional" && node.condition) {
      const thenStr = this.emitWxmlNodeWithDirective(node.condition.thenNode, `wx:if="{{${node.condition.test}}}"`, indentLevel);
      let elseStr = "";
      if (node.condition.elseNode) {
        elseStr = "\n" + this.emitWxmlNodeWithDirective(node.condition.elseNode, "wx:else", indentLevel);
      }
      return `${thenStr}${elseStr}`;
    }

    if (node.kind === "loop" && node.loop) {
      const keyAttr = node.loop.keyExpr ? ` wx:key="${node.loop.keyExpr}"` : "";
      const itemAttr = node.loop.itemName !== "item" ? ` wx:for-item="${node.loop.itemName}"` : "";
      const indexAttr = node.loop.indexName ? ` wx:for-index="${node.loop.indexName}"` : "";
      const forDirective = `wx:for="{{${node.loop.sourceExpr}}}"${itemAttr}${indexAttr}${keyAttr}`;
      return this.emitWxmlNodeWithDirective(node.loop.bodyNode, forDirective, indentLevel);
    }

    if (node.kind === "fragment") {
      const childStrs = (node.children || []).map((c) => this.emitWxmlNode(c, indentLevel)).filter(Boolean);
      return childStrs.join("\n");
    }

    const tag = node.tag || "view";
    const attrsList: string[] = [];

    for (const a of node.attrs || []) {
      if (a.isDynamic) {
        attrsList.push(`${a.name}="{{${a.value}}}"`);
      } else {
        attrsList.push(`${a.name}="${a.value}"`);
      }
    }

    for (const ev of node.events || []) {
      const wxEvent = ev.name === "click" ? "tap" : ev.name;
      attrsList.push(`bind${wxEvent}="${ev.handlerNameOrExpr}"`);
    }

    const attrStr = attrsList.length ? " " + attrsList.join(" ") : "";

    if (!node.children || node.children.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const childContent = node.children.map((c) => this.emitWxmlNode(c, indentLevel + 2)).join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }

  private emitWxmlNodeWithDirective(node: FullSyntaxNode, directive: string, indentLevel: number): string {
    const indent = " ".repeat(indentLevel);
    const tag = node.tag || "view";
    const attrsList: string[] = [directive];

    for (const a of node.attrs || []) {
      if (a.isDynamic) {
        attrsList.push(`${a.name}="{{${a.value}}}"`);
      } else {
        attrsList.push(`${a.name}="${a.value}"`);
      }
    }

    for (const ev of node.events || []) {
      const wxEvent = ev.name === "click" ? "tap" : ev.name;
      attrsList.push(`bind${wxEvent}="${ev.handlerNameOrExpr}"`);
    }

    const attrStr = " " + attrsList.join(" ");

    if (!node.children || node.children.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const childContent = node.children.map((c) => this.emitWxmlNode(c, indentLevel + 2)).join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }
}

function escapeXml(str: string): string {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

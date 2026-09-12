import { FullSyntaxComponentIR, FullSyntaxNode } from "../types";

export class ReactFullAstEmitter {
  public emit(ir: FullSyntaxComponentIR): Record<string, string> {
    const jsxContent = this.emitNode(ir.templateRoot, 4);

    const lines: string[] = [];
    lines.push('import React, { useState, useEffect, useMemo, useCallback } from "react";');
    if (ir.styles.scopedCss || ir.styles.cssModules) {
      lines.push(`import styles from "./${ir.componentName}.module.css";`);
    }

    // Props interface
    lines.push('');
    lines.push(`export interface ${ir.componentName}Props {`);
    for (const p of ir.props) {
      const opt = p.required ? "" : "?";
      lines.push(`  ${p.name}${opt}: ${p.typeAnnotation};`);
    }
    lines.push('}');

    // Component declaration
    lines.push('');
    const propDestructuring = ir.props.map((p) => p.name).join(", ");
    const paramStr = ir.props.length > 0 ? `{ ${propDestructuring} }: ${ir.componentName}Props` : "";
    lines.push(`export function ${ir.componentName}(${paramStr}) {`);

    // State declarations
    for (const s of ir.states) {
      const setter = s.setterName || `set${s.name.charAt(0).toUpperCase() + s.name.slice(1)}`;
      lines.push(`  const [${s.name}, ${setter}] = useState<${s.typeAnnotation}>(${s.initialValueExpr});`);
    }

    // Computed / useMemo
    for (const c of ir.computed) {
      const deps = c.dependencies.join(", ");
      lines.push(`  const ${c.name} = useMemo(() => ${c.expressionOrBody}, [${deps}]);`);
    }

    // Effects
    for (const eff of ir.effects) {
      const deps = eff.dependencies.join(", ");
      lines.push(`  useEffect(() => {`);
      lines.push(`    ${eff.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
      lines.push(`  }, [${deps}]);`);
    }

    // Methods
    for (const m of ir.methods) {
      const asyncPrefix = m.isAsync ? "async " : "";
      const params = m.parameters.map((p) => `${p.name}: ${p.type}`).join(", ");
      lines.push(`  const ${m.name} = useCallback(${asyncPrefix}(${params}) => {`);
      lines.push(`    ${m.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
      lines.push(`  }, []);`);
    }

    // Return JSX
    lines.push('');
    lines.push('  return (');
    lines.push(jsxContent);
    lines.push('  );');
    lines.push('}');

    const code = lines.join("\n") + "\n";
    return {
      [`${ir.componentName}.tsx`]: code,
    };
  }

  private emitNode(node: FullSyntaxNode, indentLevel = 0): string {
    const indent = " ".repeat(indentLevel);
    if (!node) return "";

    if (node.kind === "text") {
      return `${indent}${node.text || ""}`;
    }

    if (node.kind === "expression") {
      return `${indent}{${node.expression || ""}}`;
    }

    if (node.kind === "slot_outlet") {
      return `${indent}{children}`;
    }

    if (node.kind === "conditional" && node.condition) {
      if (node.condition.elseNode) {
        const thenStr = this.emitNode(node.condition.thenNode, indentLevel + 2);
        const elseStr = this.emitNode(node.condition.elseNode, indentLevel + 2);
        return `${indent}{${node.condition.test} ? (\n${thenStr}\n${indent}) : (\n${elseStr}\n${indent})}`;
      }
      const thenStr = this.emitNode(node.condition.thenNode, indentLevel + 2);
      return `${indent}{${node.condition.test} && (\n${thenStr}\n${indent})}`;
    }

    if (node.kind === "loop" && node.loop) {
      const idx = node.loop.indexName ? `, ${node.loop.indexName}` : "";
      const bodyStr = this.emitNode(node.loop.bodyNode, indentLevel + 4);
      return `${indent}{(${node.loop.sourceExpr} || []).map((${node.loop.itemName}${idx}) => (\n${bodyStr}\n${indent}))}`;
    }

    if (node.kind === "fragment") {
      const childStrs = (node.children || []).map((c) => this.emitNode(c, indentLevel + 2)).filter(Boolean);
      return `${indent}<>\n${childStrs.join("\n")}\n${indent}</>`;
    }

    const tag = node.tag || "div";
    const attrsList: string[] = [];

    for (const a of node.attrs || []) {
      const aName = a.name === "class" ? "className" : a.name;
      if (a.isDynamic) {
        attrsList.push(`${aName}={${a.value}}`);
      } else {
        attrsList.push(`${aName}="${a.value}"`);
      }
    }

    for (const ev of node.events || []) {
      const capitalized = ev.name.charAt(0).toUpperCase() + ev.name.slice(1);
      attrsList.push(`on${capitalized}={${ev.handlerNameOrExpr}}`);
    }

    const attrStr = attrsList.length ? " " + attrsList.join(" ") : "";

    if (!node.children || node.children.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const childContent = node.children.map((c) => this.emitNode(c, indentLevel + 2)).join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }
}

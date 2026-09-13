import {
  FullSyntaxComponentIR,
  FullSyntaxNode,
  FullSyntaxProp,
  FullSyntaxState,
} from "../types";
import { Angular18ComponentAst } from "./angular18-signals-types";

export interface Angular18EmitOptions {
  selector?: string;
  standalone?: boolean;
}

export class Angular18SignalsEmitter {
  public emit(ir: FullSyntaxComponentIR | Angular18ComponentAst, options: Angular18EmitOptions = {}): string {
    const rawName = ("className" in ir) ? ir.className : ir.componentName;
    const className = rawName.endsWith("Component") ? rawName : `${rawName}Component`;
    const selector = options.selector || (("selector" in ir) ? ir.selector : `app-${rawName.toLowerCase()}`);
    const standalone = options.standalone ?? (("standalone" in ir) ? ir.standalone : true);

    const classLines: string[] = [];

    if ("className" in ir) {
      // Inputs: input() / input.required()
      for (const p of ir.inputs) {
        const reqStr = p.required ? ".required" : "";
        const typeArg = p.typeAnnotation ? `<${p.typeAnnotation}>` : "";
        const defArg = p.defaultValue !== undefined ? `(${p.defaultValue})` : "()";
        classLines.push(`  readonly ${p.name} = input${reqStr}${typeArg}${defArg};`);
      }
      for (const o of ir.outputs) {
        classLines.push(`  readonly ${o.name} = output<${o.payloadType}>();`);
      }
      if (ir.inputs.length > 0 || ir.outputs.length > 0) classLines.push(``);

      // State: signal<T>(initial)
      for (const st of ir.states) {
        const initVal = st.initialValueExpr || "undefined";
        classLines.push(`  readonly ${st.name} = signal(${initVal});`);
      }
      if (ir.states.length > 0) classLines.push(``);

      // Computed: computed(() => ...)
      for (const comp of ir.computed) {
        classLines.push(`  readonly ${comp.name} = computed(() => ${comp.expressionOrBody});`);
      }
      if (ir.computed.length > 0) classLines.push(``);

      // Effects: effect(() => { ... })
      if (ir.effects.length > 0) {
        classLines.push(`  constructor() {`);
        for (const eff of ir.effects) {
          classLines.push(`    effect(() => {`);
          classLines.push(`      ${eff.bodyCode.trim()}`);
          classLines.push(`    });`);
        }
        classLines.push(`  }`);
        classLines.push(``);
      }

      // Methods
      for (const m of ir.methods) {
        const params = m.parameters.map((p) => `${p.name}: ${p.type}`).join(", ");
        const ret = m.returnType ? `: ${m.returnType}` : "";
        const asyncPrefix = m.isAsync ? "async " : "";
        classLines.push(`  ${asyncPrefix}${m.name}(${params})${ret} {`);
        classLines.push(`    ${m.bodyCode.trim()}`);
        classLines.push(`  }`);
      }
    } else {
      // Inputs: input() / input.required()
      for (const p of ir.props) {
        if (!p.isCallback) {
          const reqStr = p.required ? ".required" : "";
          const typeArg = p.typeAnnotation ? `<${p.typeAnnotation}>` : "";
          const defArg = p.defaultValue !== undefined ? `(${JSON.stringify(p.defaultValue)})` : "()";
          classLines.push(`  readonly ${p.name} = input${reqStr}${typeArg}${defArg};`);
        } else {
          const payloadType = p.callbackSignature?.params[0]?.type || "void";
          classLines.push(`  readonly ${p.name} = output<${payloadType}>();`);
        }
      }

      if (ir.props.length > 0) classLines.push(``);

      // State: signal<T>(initial)
      for (const st of ir.states) {
        const initVal = st.initialValueExpr || "undefined";
        classLines.push(`  readonly ${st.name} = signal(${initVal});`);
      }

      if (ir.states.length > 0) classLines.push(``);

      // Computed: computed(() => ...)
      for (const comp of ir.computed) {
        classLines.push(`  readonly ${comp.name} = computed(() => ${comp.expressionOrBody});`);
      }

      if (ir.computed.length > 0) classLines.push(``);

      // Effects: effect(() => { ... })
      if (ir.effects.length > 0) {
        classLines.push(`  constructor() {`);
        for (const eff of ir.effects) {
          classLines.push(`    effect(() => {`);
          classLines.push(`      ${eff.bodyCode.trim()}`);
          classLines.push(`    });`);
        }
        classLines.push(`  }`);
        classLines.push(``);
      }

      // Methods
      for (const m of ir.methods) {
        const params = m.parameters.map((p) => `${p.name}: ${p.type}`).join(", ");
        const ret = m.returnType ? `: ${m.returnType}` : "";
        const asyncPrefix = m.isAsync ? "async " : "";
        classLines.push(`  ${asyncPrefix}${m.name}(${params})${ret} {`);
        classLines.push(`    ${m.bodyCode.trim()}`);
        classLines.push(`  }`);
      }
    }

    // Template with built-in control flow
    const templateStr = ("templateRoot" in ir && ir.templateRoot) ? this.emitTemplateNode(ir.templateRoot, "    ") : "";

    const lines: string[] = [];
    lines.push(`import { Component, ChangeDetectionStrategy, signal, computed, effect, input, output } from '@angular/core';`);
    lines.push(`import { CommonModule } from '@angular/common';`);
    lines.push(``);
    lines.push(`@Component({`);
    lines.push(`  selector: '${selector}',`);
    lines.push(`  standalone: ${standalone},`);
    lines.push(`  imports: [CommonModule],`);
    lines.push(`  changeDetection: ChangeDetectionStrategy.OnPush,`);
    lines.push(`  template: \`\n${templateStr}\n  \`,`);
    lines.push(`})`);
    lines.push(`export class ${className} {`);
    lines.push(classLines.join("\n"));
    lines.push(`}`);
    lines.push(``);

    return lines.join("\n");
  }

  private emitTemplateNode(node: FullSyntaxNode, indent: string): string {
    const lines: string[] = [];

    // Condition using Angular 17/18 @if
    if (node.condition) {
      lines.push(`${indent}@if (${node.condition.test}) {`);
      lines.push(this.emitTemplateNode(node.condition.thenNode, indent + "  "));
      if (node.condition.elifBranches) {
        for (const b of node.condition.elifBranches) {
          lines.push(`${indent}} @else if (${b.test}) {`);
          lines.push(this.emitTemplateNode(b.node, indent + "  "));
        }
      }
      if (node.condition.elseNode) {
        lines.push(`${indent}} @else {`);
        lines.push(this.emitTemplateNode(node.condition.elseNode, indent + "  "));
      }
      lines.push(`${indent}}`);
      return lines.join("\n");
    }

    // Loop using Angular 17/18 @for
    if (node.loop) {
      const { sourceExpr, itemName, indexName, keyExpr, bodyNode } = node.loop;
      const trackStr = keyExpr || `${itemName}.id || $index`;
      const idxStr = indexName ? `; let ${indexName} = $index` : "";
      lines.push(`${indent}@for (${itemName} of ${sourceExpr}; track ${trackStr}${idxStr}) {`);
      lines.push(this.emitTemplateNode(bodyNode, indent + "  "));
      lines.push(`${indent}}`);
      return lines.join("\n");
    }

    if (node.kind === "text") {
      return `${indent}${node.text || ""}`;
    }

    const tag = node.tag || "div";
    const attrs: string[] = [];

    if (node.attrs) {
      for (const a of node.attrs) {
        if (a.isDynamic) {
          attrs.push(`[${a.name}]="${a.expression || a.value}"`);
        } else {
          attrs.push(`${a.name}="${a.value}"`);
        }
      }
    }

    if (node.events) {
      for (const ev of node.events) {
        attrs.push(`(${ev.name})="${ev.handlerNameOrExpr}"`);
      }
    }

    const attrStr = attrs.length > 0 ? " " + attrs.join(" ") : "";

    if (!node.children || node.children.length === 0) {
      if (node.text) {
        return `${indent}<${tag}${attrStr}>{{ ${node.text} }}</${tag}>`;
      }
      return `${indent}<${tag}${attrStr}></${tag}>`;
    }

    lines.push(`${indent}<${tag}${attrStr}>`);
    for (const child of node.children) {
      lines.push(this.emitTemplateNode(child, indent + "  "));
    }
    lines.push(`${indent}</${tag}>`);

    return lines.join("\n");
  }
}

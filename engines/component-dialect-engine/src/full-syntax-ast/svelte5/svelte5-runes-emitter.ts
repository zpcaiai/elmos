import {
  FullSyntaxAttr,
  FullSyntaxComponentIR,
  FullSyntaxNode,
  FullSyntaxProp,
  FullSyntaxState,
} from "../types";
import { Svelte5ComponentAst } from "./svelte5-runes-types";
import { Svelte5SemanticLowering } from "./svelte5-semantic-lowering";

export interface Svelte5EmitOptions {
  useTypeScript?: boolean;
}

export class Svelte5RunesEmitter {
  public emit(input: FullSyntaxComponentIR | Svelte5ComponentAst, options: Svelte5EmitOptions = {}): string {
    const ir: FullSyntaxComponentIR = "derived" in input && !("schemaVersion" in input)
      ? new Svelte5SemanticLowering().liftToUniversal(input)
      : (input as FullSyntaxComponentIR);
    const isTs = options.useTypeScript ?? true;
    const scriptLines: string[] = [];

    // Props with $props()
    if (ir.props.length > 0) {
      const propTypes: string[] = [];
      const propDestructure: string[] = [];

      for (const p of ir.props) {
        const opt = p.required ? "" : "?";
        const def = p.defaultValue !== undefined ? ` = ${JSON.stringify(p.defaultValue)}` : "";
        propTypes.push(`    ${p.name}${opt}: ${p.typeAnnotation || "any"};`);
        propDestructure.push(`${p.name}${def}`);
      }

      if (isTs) {
        scriptLines.push(`  interface Props {`);
        scriptLines.push(propTypes.join("\n"));
        scriptLines.push(`  }`);
        scriptLines.push(``);
        scriptLines.push(`  let { ${propDestructure.join(", ")} }: Props = $props();`);
      } else {
        scriptLines.push(`  let { ${propDestructure.join(", ")} } = $props();`);
      }
      scriptLines.push(``);
    }

    // State with $state()
    for (const st of ir.states) {
      const typeStr = isTs && st.typeAnnotation ? `: ${st.typeAnnotation}` : "";
      const initStr = st.initialValueExpr ? st.initialValueExpr : "undefined";
      scriptLines.push(`  let ${st.name}${typeStr} = $state(${initStr});`);
    }

    if (ir.states.length > 0) scriptLines.push(``);

    // Derived with $derived()
    for (const comp of ir.computed) {
      scriptLines.push(`  let ${comp.name} = $derived(${comp.expressionOrBody});`);
    }

    if (ir.computed.length > 0) scriptLines.push(``);

    // Effects with $effect()
    for (const eff of ir.effects) {
      scriptLines.push(`  $effect(() => {`);
      scriptLines.push(`    ${eff.bodyCode.trim()}`);
      if (eff.hasCleanup && eff.cleanupCode) {
        scriptLines.push(`    return () => {`);
        scriptLines.push(`      ${eff.cleanupCode.trim()}`);
        scriptLines.push(`    };`);
      }
      scriptLines.push(`  });`);
    }

    if (ir.effects.length > 0) scriptLines.push(``);

    // Methods
    for (const m of ir.methods) {
      const params = m.parameters
        .map((p) => (isTs && p.type ? `${p.name}: ${p.type}` : p.name))
        .join(", ");
      const ret = isTs && m.returnType ? `: ${m.returnType}` : "";
      const asyncPrefix = m.isAsync ? "async " : "";
      scriptLines.push(`  ${asyncPrefix}function ${m.name}(${params})${ret} {`);
      scriptLines.push(`    ${m.bodyCode.trim()}`);
      scriptLines.push(`  }`);
    }

    // Assemble SFC
    const langAttr = isTs ? ' lang="ts"' : "";
    const lines: string[] = [];

    lines.push(`<script${langAttr}>`);
    lines.push(scriptLines.join("\n"));
    lines.push(`</script>`);
    lines.push(``);

    // Snippet declarations for slots
    for (const slot of ir.slots) {
      if (slot.name !== "default") {
        const params = slot.slotProps.map((p) => p.name).join(", ");
        lines.push(`{#snippet ${slot.name}(${params})}`);
        if (slot.fallbackNodes && slot.fallbackNodes.length > 0) {
          for (const fn of slot.fallbackNodes) {
            lines.push(this.emitNode(fn, "  "));
          }
        }
        lines.push(`{/snippet}`);
        lines.push(``);
      }
    }

    // Template
    if (ir.templateRoot) {
      lines.push(this.emitNode(ir.templateRoot, ""));
    }

    // Style block
    if (ir.styles?.scopedCss) {
      lines.push(``);
      lines.push(`<style>`);
      lines.push(ir.styles.scopedCss.trim());
      lines.push(`</style>`);
    }

    return lines.join("\n");
  }

  private emitNode(node: FullSyntaxNode, indent: string): string {
    const lines: string[] = [];

    // Condition
    if (node.condition) {
      lines.push(`${indent}{#if ${node.condition.test}}`);
      lines.push(this.emitNode(node.condition.thenNode, indent + "  "));
      if (node.condition.elifBranches) {
        for (const b of node.condition.elifBranches) {
          lines.push(`${indent}{:else if ${b.test}}`);
          lines.push(this.emitNode(b.node, indent + "  "));
        }
      }
      if (node.condition.elseNode) {
        lines.push(`${indent}{:else}`);
        lines.push(this.emitNode(node.condition.elseNode, indent + "  "));
      }
      lines.push(`${indent}{/if}`);
      return lines.join("\n");
    }

    // Loop
    if (node.loop) {
      const { sourceExpr, itemName, indexName, keyExpr, bodyNode } = node.loop;
      const idxStr = indexName ? `, ${indexName}` : "";
      const keyStr = keyExpr ? ` (${keyExpr})` : "";
      lines.push(`${indent}{#each ${sourceExpr} as ${itemName}${idxStr}${keyStr}}`);
      lines.push(this.emitNode(bodyNode, indent + "  "));
      lines.push(`${indent}{/each}`);
      return lines.join("\n");
    }

    // Slot projection
    if (node.slotName) {
      lines.push(`${indent}{@render ${node.slotName}()}`);
      return lines.join("\n");
    }

    // Text node
    if (node.kind === "text") {
      return `${indent}${node.text || ""}`;
    }

    const tag = node.tag || "div";
    const attrs: string[] = [];

    // Dynamic and static attributes
    if (node.attrs) {
      for (const a of node.attrs) {
        if (a.isDynamic) {
          attrs.push(`${a.name}={${a.expression || a.value}}`);
        } else {
          attrs.push(`${a.name}="${a.value}"`);
        }
      }
    }

    // Modern Svelte 5 event handlers: onclick={handler}
    if (node.events) {
      for (const ev of node.events) {
        const evAttr = `on${ev.name}`;
        attrs.push(`${evAttr}={${ev.handlerNameOrExpr}}`);
      }
    }

    const attrStr = attrs.length > 0 ? " " + attrs.join(" ") : "";

    if (!node.children || node.children.length === 0) {
      if (node.text) {
        return `${indent}<${tag}${attrStr}>${node.text}</${tag}>`;
      }
      return `${indent}<${tag}${attrStr} />`;
    }

    lines.push(`${indent}<${tag}${attrStr}>`);
    for (const child of node.children) {
      lines.push(this.emitNode(child, indent + "  "));
    }
    lines.push(`${indent}</${tag}>`);

    return lines.join("\n");
  }
}

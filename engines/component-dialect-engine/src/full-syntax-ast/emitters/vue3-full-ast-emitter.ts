import { FullSyntaxComponentIR, FullSyntaxNode } from "../types";

export class Vue3FullAstEmitter {
  public emit(ir: FullSyntaxComponentIR): Record<string, string> {
    const templateContent = this.emitNode(ir.templateRoot, 2);

    // Build <script setup lang="ts">
    const scriptLines: string[] = [];
    scriptLines.push('<script setup lang="ts">');
    scriptLines.push('import { ref, computed, onMounted, onUnmounted, watch } from "vue";');

    // Props interface
    if (ir.props.length > 0) {
      scriptLines.push('');
      scriptLines.push('const props = defineProps<{');
      for (const p of ir.props) {
        const opt = p.required ? "" : "?";
        scriptLines.push(`  ${p.name}${opt}: ${p.typeAnnotation};`);
      }
      scriptLines.push('}>();');
    }

    // Emits
    const callbackProps = ir.props.filter((p) => p.isCallback);
    if (callbackProps.length > 0) {
      scriptLines.push('');
      scriptLines.push('const emit = defineEmits<{');
      for (const cb of callbackProps) {
        const evName = cb.name.replace(/^on/, "").toLowerCase();
        scriptLines.push(`  (e: "${evName}", ...args: any[]): void;`);
      }
      scriptLines.push('}>();');
    }

    // State refs
    if (ir.states.length > 0) {
      scriptLines.push('');
      for (const s of ir.states) {
        scriptLines.push(`const ${s.name} = ref<${s.typeAnnotation}>(${s.initialValueExpr});`);
      }
    }

    // Computed properties
    if (ir.computed.length > 0) {
      scriptLines.push('');
      for (const c of ir.computed) {
        scriptLines.push(`const ${c.name} = computed(() => ${c.expressionOrBody});`);
      }
    }

    // Effects & Lifecycle
    if (ir.effects.length > 0) {
      scriptLines.push('');
      for (const eff of ir.effects) {
        if (eff.hookKind === "mount") {
          scriptLines.push(`onMounted(() => {`);
          scriptLines.push(`  ${eff.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
          scriptLines.push(`});`);
        } else if (eff.hookKind === "unmount") {
          scriptLines.push(`onUnmounted(() => {`);
          scriptLines.push(`  ${eff.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
          scriptLines.push(`});`);
        } else if (eff.hookKind === "watch") {
          const deps = eff.dependencies.join(", ") || "() => props";
          scriptLines.push(`watch(${deps}, () => {`);
          scriptLines.push(`  ${eff.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
          scriptLines.push(`});`);
        }
      }
    }

    // Methods
    if (ir.methods.length > 0) {
      scriptLines.push('');
      for (const m of ir.methods) {
        const asyncPrefix = m.isAsync ? "async " : "";
        const params = m.parameters.map((p) => `${p.name}: ${p.type}`).join(", ");
        scriptLines.push(`${asyncPrefix}function ${m.name}(${params}) {`);
        scriptLines.push(`  ${m.bodyCode.replace(/^[^{]*{/, "").replace(/}[^}]*$/, "").trim()}`);
        scriptLines.push(`}`);
      }
    }

    scriptLines.push('</script>');

    // Build <template>
    const templateLines: string[] = [];
    templateLines.push('<template>');
    templateLines.push(templateContent);
    templateLines.push('</template>');

    // Build <style scoped>
    const styleLines: string[] = [];
    if (ir.styles.scopedCss) {
      styleLines.push('');
      styleLines.push('<style scoped>');
      styleLines.push(ir.styles.scopedCss);
      styleLines.push('</style>');
    }

    const fullSfc = `${scriptLines.join("\n")}\n\n${templateLines.join("\n")}${styleLines.length ? "\n" + styleLines.join("\n") : ""}\n`;
    return {
      [`${ir.componentName}.vue`]: fullSfc,
    };
  }

  private emitNode(node: FullSyntaxNode, indentLevel = 0): string {
    const indent = " ".repeat(indentLevel);
    if (!node) return "";

    if (node.kind === "text") {
      return `${indent}${node.text || ""}`;
    }

    if (node.kind === "expression") {
      return `${indent}{{ ${node.expression || ""} }}`;
    }

    if (node.kind === "slot_outlet") {
      const slotNameAttr = node.slotName && node.slotName !== "default" ? ` name="${node.slotName}"` : "";
      return `${indent}<slot${slotNameAttr} />`;
    }

    if (node.kind === "conditional" && node.condition) {
      const thenStr = this.emitNodeWithDirective(node.condition.thenNode, `v-if="${node.condition.test}"`, indentLevel);
      let elseStr = "";
      if (node.condition.elseNode) {
        elseStr = "\n" + this.emitNodeWithDirective(node.condition.elseNode, "v-else", indentLevel);
      }
      return `${thenStr}${elseStr}`;
    }

    if (node.kind === "loop" && node.loop) {
      const idx = node.loop.indexName ? `, ${node.loop.indexName}` : "";
      const forDirective = `v-for="(${node.loop.itemName}${idx}) in ${node.loop.sourceExpr}"`;
      const keyAttr = node.loop.keyExpr ? ` :key="${node.loop.keyExpr}"` : "";
      return this.emitNodeWithDirective(node.loop.bodyNode, `${forDirective}${keyAttr}`, indentLevel);
    }

    if (node.kind === "fragment") {
      const childStrs = (node.children || []).map((c) => this.emitNode(c, indentLevel)).filter(Boolean);
      return childStrs.join("\n");
    }

    const tag = node.tag || "div";
    const attrsList: string[] = [];

    for (const a of node.attrs || []) {
      if (a.isDynamic) {
        attrsList.push(`:${a.name}="${a.value}"`);
      } else {
        attrsList.push(`${a.name}="${a.value}"`);
      }
    }

    for (const ev of node.events || []) {
      attrsList.push(`@${ev.name}="${ev.handlerNameOrExpr}"`);
    }

    const attrStr = attrsList.length ? " " + attrsList.join(" ") : "";

    if (!node.children || node.children.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const childContent = node.children.map((c) => this.emitNode(c, indentLevel + 2)).join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }

  private emitNodeWithDirective(node: FullSyntaxNode, directive: string, indentLevel: number): string {
    const indent = " ".repeat(indentLevel);
    const tag = node.tag || "div";
    const attrsList: string[] = [directive];

    for (const a of node.attrs || []) {
      if (a.isDynamic) {
        attrsList.push(`:${a.name}="${a.value}"`);
      } else {
        attrsList.push(`${a.name}="${a.value}"`);
      }
    }

    for (const ev of node.events || []) {
      attrsList.push(`@${ev.name}="${ev.handlerNameOrExpr}"`);
    }

    const attrStr = " " + attrsList.join(" ");

    if (!node.children || node.children.length === 0) {
      return `${indent}<${tag}${attrStr} />`;
    }

    const childContent = node.children.map((c) => this.emitNode(c, indentLevel + 2)).join("\n");
    return `${indent}<${tag}${attrStr}>\n${childContent}\n${indent}</${tag}>`;
  }
}

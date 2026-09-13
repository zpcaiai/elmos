import { FullSyntaxComponentIR, FullSyntaxNode, TargetFramework } from "../types";

export class SlotProjectionTransformer {
  public transform(ir: FullSyntaxComponentIR, target: TargetFramework): void {
    const hasDefaultSlot = ir.slots.some((s) => s.name === "default") || ir.props.some((p) => p.name === "children");
    const hasNamedSlots = ir.slots.some((s) => s.name !== "default");

    if (hasNamedSlots && target === "miniapp") {
      ir.metadata["multipleSlots"] = true;
    }

    // Traverse template tree and transform slot nodes
    this.transformNodeSlots(ir.templateRoot, target);
  }

  private transformNodeSlots(node: FullSyntaxNode, target: TargetFramework): void {
    if (!node) return;

    if (node.kind === "expression" && node.expression) {
      if (node.expression === "children" || node.expression === "props.children") {
        node.kind = "slot_outlet";
        node.slotName = "default";
        node.tag = "slot";
      }
    }

    if (node.children) {
      for (const child of node.children) {
        this.transformNodeSlots(child, target);
      }
    }

    if (node.condition) {
      this.transformNodeSlots(node.condition.thenNode, target);
      if (node.condition.elseNode) {
        this.transformNodeSlots(node.condition.elseNode, target);
      }
    }

    if (node.loop) {
      this.transformNodeSlots(node.loop.bodyNode, target);
    }
  }
}

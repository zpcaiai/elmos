import { FullSyntaxComponentIR, FullSyntaxNode, TargetFramework } from "../types";

export class StyleTransformer {
  public transform(ir: FullSyntaxComponentIR, target: TargetFramework): void {
    if (target === "miniapp") {
      this.sanitizeMiniAppNodeStyles(ir.templateRoot);
    }
  }

  private sanitizeMiniAppNodeStyles(node: FullSyntaxNode): void {
    if (!node) return;

    if (node.attrs) {
      for (const attr of node.attrs) {
        if (attr.name === "class" || attr.name === "className") {
          attr.name = "class";
          if (attr.isDynamic && attr.expression) {
            // styles.cardWrap -> 'cardWrap'
            attr.expression = attr.expression.replace(/styles\.([a-zA-Z0-9_-]+)/g, "'$1'");
            attr.value = attr.expression;
          } else if (attr.value) {
            attr.value = this.sanitizeTailwindForWxss(attr.value);
          }
        }
      }
    }

    if (node.children) {
      for (const child of node.children) {
        this.sanitizeMiniAppNodeStyles(child);
      }
    }

    if (node.condition) {
      this.sanitizeMiniAppNodeStyles(node.condition.thenNode);
      if (node.condition.elseNode) {
        this.sanitizeMiniAppNodeStyles(node.condition.elseNode);
      }
    }

    if (node.loop) {
      this.sanitizeMiniAppNodeStyles(node.loop.bodyNode);
    }
  }

  private sanitizeTailwindForWxss(className: string): string {
    return className
      .split(/\s+/)
      .map((c) =>
        c
          .replace(/:/g, "_")
          .replace(/\//g, "_")
          .replace(/\[/g, "-")
          .replace(/\]/g, "")
          .replace(/#/g, "-")
          .replace(/\./g, "d_")
          .replace(/%/g, "pct_")
      )
      .join(" ");
  }
}

import { FullSyntaxComponentIR, FullSyntaxNode, TargetFramework } from "../types";
import { TailwindJitCompiler } from "../../style-engine/tailwind-jit-compiler";
import { ScssLessPreprocessor } from "../../style-engine/scss-less-preprocessor";
import { WxssLayoutLowerer } from "../../style-engine/wxss-layout-lowerer";

export class StyleTransformer {
  private tailwindJit = new TailwindJitCompiler();
  private preprocessor = new ScssLessPreprocessor();
  private wxssLowerer = new WxssLayoutLowerer();

  public transform(ir: FullSyntaxComponentIR, target: TargetFramework): void {
    // 1. Extract Tailwind classes from template
    const tailwindClasses = this.tailwindJit.extractClassesFromTemplate(ir.templateRoot);
    if (tailwindClasses.length > 0) {
      const generatedTailwindCss = this.tailwindJit.generateCss(tailwindClasses);
      if (generatedTailwindCss) {
        ir.styles.scopedCss = ir.styles.scopedCss
          ? `${ir.styles.scopedCss}\n\n/* Tailwind JIT Generated */\n${generatedTailwindCss}`
          : generatedTailwindCss;
      }
      ir.styles.tailwindClasses = tailwindClasses;
    }

    // 2. Preprocess SCSS/LESS if present in scopedCss
    if (ir.styles.scopedCss && (ir.styles.scopedCss.includes("$") || ir.styles.scopedCss.includes("@mixin") || ir.styles.scopedCss.includes("&"))) {
      try {
        ir.styles.scopedCss = this.preprocessor.processToCssString(ir.styles.scopedCss);
      } catch (e) {
        // Fallback gracefully to existing CSS
      }
    }

    // 3. Lowering for MiniApp (unit conversion, selector sanitization, grid fallback)
    if (target === "miniapp" || target === "miniprogram") {
      if (ir.styles.scopedCss) {
        ir.styles.scopedCss = this.wxssLowerer.lowerToWxss(ir.styles.scopedCss, {
          designWidthPx: 375,
          gridToFlexFallback: true,
        });
      }
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
      if (node.condition.elifBranches) {
        for (const b of node.condition.elifBranches) {
          this.sanitizeMiniAppNodeStyles(b.node);
        }
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
          .replace(/\[/g, "--")
          .replace(/\]/g, "-")
          .replace(/#/g, "hex_")
          .replace(/\./g, "d_")
          .replace(/%/g, "pct_")
      )
      .join(" ");
  }
}

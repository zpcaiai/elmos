/**
 * WeChat MiniProgram WXSS Layout and Selector Lowerer.
 * 
 * Performs:
 * - Viewport unit conversion: px / rem / vw -> rpx based on 750rpx mobile design standard
 * - CSS Grid to Flexbox fallback layout conversion
 * - Selector sanitization for MiniApp (escaped characters, colon prefixes, brackets)
 * - Deep selector (/deep/, ::v-deep, >>>) translation for shadow DOM / component isolation
 */

import { CssAstParser, CssStylesheet, CssStyleRule } from "./css-ast-parser";

export interface WxssLoweringOptions {
  designWidthPx?: number;       // default: 375 (so 1px = 2rpx)
  remBasePx?: number;           // default: 16 (so 1rem = 32rpx)
  preserveHairlineBorders?: boolean; // keep 1px as 1px or 1rpx
  gridToFlexFallback?: boolean; // convert display:grid to display:flex wrap
  scopeClassPrefix?: string;    // e.g. "wx-comp-root"
}

export class WxssLayoutLowerer {
  private parser = new CssAstParser();

  /**
   * Lowers standard CSS / SCSS AST or string into optimized WeChat WXSS.
   */
  public lowerToWxss(cssOrStylesheet: string | CssStylesheet, options: WxssLoweringOptions = {}): string {
    const stylesheet = typeof cssOrStylesheet === "string" 
      ? this.parser.parse(cssOrStylesheet) 
      : cssOrStylesheet;

    const designWidth = options.designWidthPx || 375;
    const rpxPerPx = 750 / designWidth;
    const remBase = options.remBasePx || 16;

    for (const rule of stylesheet.rules) {
      if (rule.type === "style") {
        this.lowerStyleRule(rule, rpxPerPx, remBase, options);
      } else if (rule.type === "media" || rule.type === "supports") {
        for (const inner of rule.rules) {
          if (inner.type === "style") {
            this.lowerStyleRule(inner, rpxPerPx, remBase, options);
          }
        }
      }
    }

    return this.parser.serialize(stylesheet);
  }

  /**
   * Lowers a single style rule.
   */
  private lowerStyleRule(
    rule: CssStyleRule,
    rpxPerPx: number,
    remBase: number,
    options: WxssLoweringOptions
  ): void {
    // 1. Lower Selectors (deep selector rewriting & sanitization)
    for (const sel of rule.selectors) {
      sel.raw = this.lowerSelector(sel.raw, options.scopeClassPrefix);
    }

    // 2. Lower Declarations (unit conversions)
    let hasGrid = false;
    let gridCols = 1;
    let gridGap = "";

    for (const decl of rule.declarations) {
      // Unit conversion
      decl.value = this.convertUnitsToRpx(decl.value, rpxPerPx, remBase, options.preserveHairlineBorders);

      if (decl.property === "display" && decl.value.trim() === "grid") {
        hasGrid = true;
      }
      if (decl.property === "grid-template-columns") {
        const repeatMatch = decl.value.match(/repeat\((\d+)/);
        if (repeatMatch) {
          gridCols = parseInt(repeatMatch[1]!, 10);
        } else {
          // Count column tokens e.g. "1fr 1fr"
          const tokens = decl.value.split(/\s+/).filter(Boolean);
          if (tokens.length > 1) gridCols = tokens.length;
        }
      }
      if (decl.property === "gap" || decl.property === "grid-gap") {
        gridGap = decl.value;
      }
    }

    // 3. Grid to Flexbox fallback if enabled
    if (hasGrid && options.gridToFlexFallback) {
      // Change display: grid to flex
      const dispDecl = rule.declarations.find((d) => d.property === "display");
      if (dispDecl) dispDecl.value = "flex";

      // Add flex-wrap: wrap
      rule.declarations.push({
        property: "flex-wrap",
        value: "wrap",
        important: false,
      });

      // Add flex layout comment annotation
      rule.declarations.push({
        property: "--elmos-grid-fallback-cols",
        value: `${gridCols}`,
        important: false,
      });
      if (gridGap) {
        rule.declarations.push({
          property: "--elmos-grid-fallback-gap",
          value: gridGap,
          important: false,
        });
      }
    }
  }

  /**
   * Rewrites deep selectors and sanitizes MiniApp class names.
   * e.g. .btn /deep/ .icon -> .btn .icon
   * e.g. .btn::v-deep .icon -> .btn .icon
   * e.g. .w-[240px] -> .w--240px-
   */
  public lowerSelector(rawSelector: string, scopePrefix?: string): string {
    let s = rawSelector;

    // 1. Remove Vue / Angular deep penetrations
    s = s.replace(/::v-deep/g, "");
    s = s.replace(/\/deep\//g, "");
    s = s.replace(/>>>/g, "");
    s = s.replace(/\s+/g, " ");

    // 2. Sanitize Tailwind arbitrary and variant classes in selectors
    // e.g. \: -> _
    s = s.replace(/\\:/g, "_");
    s = s.replace(/\\\[/g, "--");
    s = s.replace(/\\\]/g, "-");
    s = s.replace(/\\#/g, "hex_");
    s = s.replace(/\\\//g, "_");
    s = s.replace(/\\\./g, "d_");
    s = s.replace(/\\%/g, "pct_");

    // Also unescaped colons in class selectors if present
    s = s.replace(/\.([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)/g, ".$1_$2");

    // 3. Add component scope prefix if requested
    if (scopePrefix) {
      const parts = s.split(",").map((p) => p.trim());
      s = parts.map((p) => `.${scopePrefix} ${p}`).join(", ");
    }

    return s.trim();
  }

  /**
   * Converts px, rem, vw units to rpx.
   */
  public convertUnitsToRpx(
    value: string,
    rpxPerPx: number,
    remBase: number,
    preserveHairline = true
  ): string {
    let res = value;

    // 1. Convert px to rpx: e.g. 16px -> 32rpx
    res = res.replace(/(\d*\.?\d+)px\b/g, (_, numStr) => {
      const num = parseFloat(numStr);
      if (preserveHairline && num === 1) {
        return "1px"; // Keep 1px hairline border
      }
      const rpx = Math.round(num * rpxPerPx * 100) / 100;
      return `${rpx}rpx`;
    });

    // 2. Convert rem to rpx: 1rem = remBase * rpxPerPx rpx
    res = res.replace(/(\d*\.?\d+)rem\b/g, (_, numStr) => {
      const num = parseFloat(numStr);
      const rpx = Math.round(num * remBase * rpxPerPx * 100) / 100;
      return `${rpx}rpx`;
    });

    // 3. Convert vw to rpx: 100vw = 750rpx -> 1vw = 7.5rpx
    res = res.replace(/(\d*\.?\d+)vw\b/g, (_, numStr) => {
      const num = parseFloat(numStr);
      const rpx = Math.round(num * 7.5 * 100) / 100;
      return `${rpx}rpx`;
    });

    return res;
  }
}

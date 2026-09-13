/**
 * Test Suite: Full-Syntax Style Engine (Pillar 2)
 * 
 * Tests:
 * 1. CssAstParser: Rules, At-rules, complex selectors, custom properties
 * 2. ScssLessPreprocessor: Variables, mixins, nesting unrolling (& combinators), built-in functions
 * 3. TailwindJitCompiler: Arbitrary values, responsive breakpoints, state variants, CSS emission
 * 4. WxssLayoutLowerer: px/rem/vw -> rpx conversion, CSS Grid -> Flexbox fallback, selector sanitization
 */

import { CssAstParser } from "../src/style-engine/css-ast-parser";
import { ScssLessPreprocessor } from "../src/style-engine/scss-less-preprocessor";
import { TailwindJitCompiler } from "../src/style-engine/tailwind-jit-compiler";
import { WxssLayoutLowerer } from "../src/style-engine/wxss-layout-lowerer";

describe("Full-Syntax Cross-Platform Style Engine", () => {
  describe("1. CssAstParser & Serializer", () => {
    const parser = new CssAstParser();

    it("parses style rules with complex selectors and declarations", () => {
      const css = `
        .card-header > h2.title:hover {
          font-size: 20px;
          color: #1e293b !important;
          --header-bg: #f8fafc;
        }
      `;
      const ast = parser.parse(css);
      expect(ast.rules).toHaveLength(1);
      const rule = ast.rules[0] as any;
      expect(rule.type).toBe("style");
      expect(rule.selectors[0].raw).toBe(".card-header > h2.title:hover");
      expect(rule.declarations).toHaveLength(3);

      const colorDecl = rule.declarations.find((d: any) => d.property === "color");
      expect(colorDecl.value).toBe("#1e293b");
      expect(colorDecl.important).toBe(true);

      const varDecl = rule.declarations.find((d: any) => d.property === "--header-bg");
      expect(varDecl.value).toBe("#f8fafc");
    });

    it("parses @media and @keyframes at-rules", () => {
      const css = `
        @media (max-width: 640px) {
          .container {
            width: 100%;
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `;
      const ast = parser.parse(css);
      expect(ast.rules).toHaveLength(2);
      expect(ast.rules[0]?.type).toBe("media");
      expect(ast.rules[1]?.type).toBe("keyframes");

      const kf = ast.rules[1] as any;
      expect(kf.name).toBe("fadeIn");
      expect(kf.keyframes).toHaveLength(2);
    });

    it("serializes AST back to formatted CSS", () => {
      const css = `.btn { color: #fff; }`;
      const ast = parser.parse(css);
      const serialized = parser.serialize(ast);
      expect(serialized).toContain(".btn {");
      expect(serialized).toContain("color: #fff;");
    });
  });

  describe("2. ScssLessPreprocessor", () => {
    const preprocessor = new ScssLessPreprocessor();

    it("resolves SCSS variables and default values", () => {
      const scss = `
        $primary: #3b82f6;
        $theme: $primary;
        $padding: 16px !default;

        .btn-primary {
          background-color: $theme;
          padding: $padding;
        }
      `;
      const css = preprocessor.processToCssString(scss, { syntax: "scss" });
      expect(css).toContain("background-color: #3b82f6;");
      expect(css).toContain("padding: 16px;");
      expect(css).not.toContain("$primary");
    });

    it("unrolls nested selectors with BEM '&' parent combinators", () => {
      const scss = `
        .block {
          color: black;
          &__element {
            font-weight: bold;
            &:hover {
              color: red;
            }
          }
          > span {
            font-size: 14px;
          }
        }
      `;
      const css = preprocessor.processToCssString(scss, { syntax: "scss" });
      expect(css).toContain(".block {");
      expect(css).toContain(".block__element {");
      expect(css).toContain(".block__element:hover {");
      expect(css).toContain(".block > span {");
    });

    it("extracts and expands mixins with arguments", () => {
      const scss = `
        @mixin flex-layout($dir: row, $align: center) {
          display: flex;
          flex-direction: $dir;
          align-items: $align;
        }

        .nav-bar {
          @include flex-layout(column, flex-start);
        }
      `;
      const css = preprocessor.processToCssString(scss, { syntax: "scss" });
      expect(css).toContain("display: flex;");
      expect(css).toContain("flex-direction: column;");
      expect(css).toContain("align-items: flex-start;");
    });
  });

  describe("3. TailwindJitCompiler", () => {
    const jit = new TailwindJitCompiler();

    it("compiles standard utility classes into exact CSS declarations", () => {
      const classes = ["flex", "flex-col", "items-center", "justify-between", "p-4", "m-2", "text-sm", "font-bold", "rounded-lg", "shadow-md"];
      const css = jit.generateCss(classes);
      expect(css).toContain("display: flex;");
      expect(css).toContain("flex-direction: column;");
      expect(css).toContain("align-items: center;");
      expect(css).toContain("justify-content: space-between;");
      expect(css).toContain("padding: 1rem;");
      expect(css).toContain("font-size: 0.875rem;");
      expect(css).toContain("font-weight: 700;");
      expect(css).toContain("border-radius: 0.5rem;");
    });

    it("compiles arbitrary values and arbitrary properties", () => {
      const classes = ["w-[240px]", "bg-[#1e293b]", "p-[12px_16px]", "[mask-type:alpha]"];
      const css = jit.generateCss(classes);
      expect(css).toContain("width: 240px;");
      expect(css).toContain("background-color: #1e293b;");
      expect(css).toContain("padding: 12px 16px;");
      expect(css).toContain("mask-type: alpha;");
    });

    it("compiles responsive and state variant prefixes", () => {
      const classes = ["md:w-full", "hover:bg-blue-600", "dark:text-white"];
      const css = jit.generateCss(classes);
      expect(css).toContain("@media (min-width: 768px)");
      expect(css).toContain("@media (prefers-color-scheme: dark)");
      expect(css).toContain(":hover");
    });
  });

  describe("4. WxssLayoutLowerer", () => {
    const lowerer = new WxssLayoutLowerer();

    it("converts px, rem, and vw units to rpx based on 750rpx mobile standard", () => {
      const inputCss = `
        .container {
          width: 375px;
          height: 100px;
          margin: 1rem;
          padding: 10vw;
          border: 1px solid #ccc;
        }
      `;
      const wxss = lowerer.lowerToWxss(inputCss, {
        designWidthPx: 375, // 1px = 2rpx
        preserveHairlineBorders: true,
      });

      expect(wxss).toContain("width: 750rpx;");
      expect(wxss).toContain("height: 200rpx;");
      expect(wxss).toContain("margin: 32rpx;"); // 1rem = 16px = 32rpx
      expect(wxss).toContain("padding: 75rpx;"); // 10vw = 75rpx
      expect(wxss).toContain("border: 1px solid #ccc;"); // 1px hairline preserved
    });

    it("converts CSS Grid to Flexbox fallback layout", () => {
      const gridCss = `
        .data-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
        }
      `;
      const wxss = lowerer.lowerToWxss(gridCss, {
        gridToFlexFallback: true,
      });

      expect(wxss).toContain("display: flex;");
      expect(wxss).toContain("flex-wrap: wrap;");
      expect(wxss).toContain("--elmos-grid-fallback-cols: 3;");
    });

    it("rewrites deep selectors and sanitizes MiniApp class names", () => {
      const deepCss = `
        .parent /deep/ .child {
          color: red;
        }
        .wrapper::v-deep .inner {
          color: blue;
        }
        .w--240px- {
          width: 240px;
        }
      `;
      const wxss = lowerer.lowerToWxss(deepCss);
      expect(wxss).not.toContain("/deep/");
      expect(wxss).not.toContain("::v-deep");
      expect(wxss).toContain(".parent .child {");
      expect(wxss).toContain(".wrapper .inner {");
    });
  });
});

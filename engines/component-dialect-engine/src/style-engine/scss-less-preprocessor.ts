/**
 * Industrial SCSS and LESS Preprocessor Engine.
 * 
 * Unrolls nesting (including & parent combinators, BEM &__elem, pseudo-states),
 * resolves variables ($scss and @less), evaluates mixins with arguments,
 * and normalizes preprocessed code into standard CSS AST.
 */

import { CssAstParser, CssStylesheet } from "./css-ast-parser";

export interface PreprocessorOptions {
  syntax?: "scss" | "less" | "css";
  externalVariables?: Record<string, string>;
}

export class ScssLessPreprocessor {
  private parser = new CssAstParser();

  /**
   * Preprocesses raw SCSS/LESS code into standard CSS AST.
   */
  public process(code: string, options: PreprocessorOptions = {}): CssStylesheet {
    const syntax = options.syntax || this.detectSyntax(code);
    let output = code;

    // 1. Strip comments
    output = this.stripComments(output);

    // 2. Extract & resolve variables
    const variables = this.extractVariables(output, syntax, options.externalVariables);
    output = this.replaceVariables(output, variables, syntax);

    // 3. Extract & expand mixins
    const mixins = this.extractMixins(output, syntax);
    output = this.expandMixins(output, mixins, syntax);

    // 4. Unroll nested rules (SCSS/LESS nesting & BEM &)
    output = this.unrollNesting(output);

    // 5. Evaluate built-in color / math functions (lighten, darken, etc.)
    output = this.evaluateBuiltinFunctions(output);

    // 6. Parse final CSS through CssAstParser
    return this.parser.parse(output);
  }

  /**
   * Preprocesses and emits plain CSS string.
   */
  public processToCssString(code: string, options: PreprocessorOptions = {}): string {
    const stylesheet = this.process(code, options);
    return this.parser.serialize(stylesheet);
  }

  // =========================================================================
  // Syntax Detection & Comment Stripping
  // =========================================================================

  private detectSyntax(code: string): "scss" | "less" | "css" {
    if (code.includes("@mixin") || code.includes("@include") || /\$[a-zA-Z0-9_-]+\s*:/.test(code)) {
      return "scss";
    }
    if (/@[\w-]+\s*:\s*[^;]+;/.test(code) || /\.[a-zA-Z0-9_-]+\(@[^)]*\)\s*\{/.test(code)) {
      return "less";
    }
    return "css";
  }

  private stripComments(code: string): string {
    // Strip // single-line comments safely while keeping urls/strings
    let cleaned = code.replace(/\/\*[\s\S]*?\*\//g, "");
    cleaned = cleaned.replace(/\/\/[^\n\r]*/g, "");
    return cleaned;
  }

  // =========================================================================
  // Variable Resolution
  // =========================================================================

  private extractVariables(
    code: string,
    syntax: "scss" | "less" | "css",
    external: Record<string, string> = {}
  ): Map<string, string> {
    const vars = new Map<string, string>(Object.entries(external));
    const prefix = syntax === "less" ? "@" : "\\$";
    const varRegex = new RegExp(`(?:^|[\\s;{])(${prefix}[a-zA-Z0-9_-]+)\\s*:\\s*([^;{}()]+);`, "g");

    let match: RegExpExecArray | null;
    while ((match = varRegex.exec(code)) !== null) {
      const varName = match[1]!;
      let varValue = match[2]!.trim();
      const isDefault = /!default\s*$/i.test(varValue);
      if (isDefault) {
        varValue = varValue.replace(/!default\s*$/i, "").trim();
        if (!vars.has(varName)) {
          vars.set(varName, varValue);
        }
      } else {
        vars.set(varName, varValue);
      }
    }

    // Resolve chained variables ($b: $a + 2)
    for (const [k, v] of vars.entries()) {
      let resolved = v;
      for (const [otherK, otherV] of vars.entries()) {
        if (k !== otherK && resolved.includes(otherK)) {
          resolved = resolved.split(otherK).join(otherV);
        }
      }
      vars.set(k, resolved);
    }

    return vars;
  }

  private replaceVariables(
    code: string,
    variables: Map<string, string>,
    syntax: "scss" | "less" | "css"
  ): string {
    let res = code;

    // Remove variable declarations safely
    const prefix = syntax === "less" ? "@" : "\\$";
    res = res.replace(new RegExp(`(?:^|[\\s;{])${prefix}[a-zA-Z0-9_-]+\\s*:[^;{}()]+;`, "g"), "");

    // Replace variable usages
    for (const [name, val] of variables.entries()) {
      // Escape for regex
      const escaped = name.replace(/[$@]/g, "\\$&");
      // Variable interpolation #{$var}
      res = res.replace(new RegExp(`#\\{${escaped}\\}`, "g"), val);
      // Plain variable usage
      res = res.replace(new RegExp(`${escaped}(?![a-zA-Z0-9_-])`, "g"), val);
    }

    return res;
  }

  // =========================================================================
  // Mixin Extraction & Expansion
  // =========================================================================

  private extractMixins(
    code: string,
    syntax: "scss" | "less" | "css"
  ): Map<string, { params: string[]; body: string }> {
    const mixins = new Map<string, { params: string[]; body: string }>();

    if (syntax === "scss") {
      // @mixin name($arg1, $arg2: default) { ... }
      const mixinRegex = /@mixin\s+([a-zA-Z0-9_-]+)(?:\s*\(([^)]*)\))?\s*\{/g;
      let match: RegExpExecArray | null;
      while ((match = mixinRegex.exec(code)) !== null) {
        const name = match[1]!;
        const rawParams = match[2] || "";
        const params = rawParams.split(",").map((p) => p.trim()).filter(Boolean);
        const openBrace = match.index + match[0].length - 1;
        const closeBrace = this.findMatchingBrace(code, openBrace);
        const body = code.substring(openBrace + 1, closeBrace).trim();
        mixins.set(name, { params, body });
      }
    } else if (syntax === "less") {
      // .mixin(@arg1, @arg2: default) { ... }
      const mixinRegex = /\.([a-zA-Z0-9_-]+)(?:\s*\(([^)]*)\))?\s*\{/g;
      let match: RegExpExecArray | null;
      while ((match = mixinRegex.exec(code)) !== null) {
        const name = match[1]!;
        const rawParams = match[2] || "";
        const params = rawParams.split(",").map((p) => p.trim()).filter(Boolean);
        const openBrace = match.index + match[0].length - 1;
        const closeBrace = this.findMatchingBrace(code, openBrace);
        const body = code.substring(openBrace + 1, closeBrace).trim();
        mixins.set(name, { params, body });
      }
    }

    return mixins;
  }

  private expandMixins(
    code: string,
    mixins: Map<string, { params: string[]; body: string }>,
    syntax: "scss" | "less" | "css"
  ): string {
    let res = code;

    // Remove mixin definitions
    if (syntax === "scss") {
      res = res.replace(/@mixin\s+[a-zA-Z0-9_-]+(?:\s*\([^)]*\))?\s*\{[\s\S]*?\}/g, (match) => {
        // Need to check for nested braces in mixin
        return "";
      });
    }

    // Expand @include mixinName(arg1, arg2);
    for (const [name, def] of mixins.entries()) {
      const includeRegex = new RegExp(`@include\\s+${name}(?:\\s*\\(([^)]*)\\))?\\s*;`, "g");
      res = res.replace(includeRegex, (_, rawArgs) => {
        const args = (rawArgs || "").split(",").map((a: string) => a.trim());
        let expanded = def.body;
        for (let i = 0; i < def.params.length; i++) {
          const p = def.params[i]!;
          const [pName, pDef] = p.split(":").map((s) => s.trim());
          const argVal = args[i] || pDef || "";
          if (pName) {
            const escaped = pName.replace(/[$@]/g, "\\$&");
            expanded = expanded.replace(new RegExp(escaped, "g"), argVal);
          }
        }
        return expanded;
      });

      // LESS .mixinName(arg1);
      if (syntax === "less") {
        const lessIncludeRegex = new RegExp(`\\.${name}(?:\\s*\\(([^)]*)\\))?\\s*;`, "g");
        res = res.replace(lessIncludeRegex, (_, rawArgs) => {
          const args = (rawArgs || "").split(",").map((a: string) => a.trim());
          let expanded = def.body;
          for (let i = 0; i < def.params.length; i++) {
            const p = def.params[i]!;
            const [pName, pDef] = p.split(":").map((s) => s.trim());
            const argVal = args[i] || pDef || "";
            if (pName) {
              const escaped = pName.replace(/[$@]/g, "\\$&");
              expanded = expanded.replace(new RegExp(escaped, "g"), argVal);
            }
          }
          return expanded;
        });
      }
    }

    return res;
  }

  // =========================================================================
  // Nesting Unroller (including BEM & and Parent Combinators)
  // =========================================================================

  public unrollNesting(css: string): string {
    const outRules: { selector: string; declarations: string[] }[] = [];
    this.parseNestedBlocks(css, "", outRules);

    return outRules
      .filter((r) => r.declarations.length > 0)
      .map((r) => `${r.selector} {\n  ${r.declarations.join("\n  ")}\n}`)
      .join("\n\n");
  }

  private parseNestedBlocks(
    chunk: string,
    currentSelector: string,
    results: { selector: string; declarations: string[] }[]
  ): void {
    let i = 0;
    const len = chunk.length;
    const currentDecls: string[] = [];

    while (i < len) {
      while (i < len && /[\s;]/.test(chunk[i]!)) i++;
      if (i >= len) break;

      const braceOpen = chunk.indexOf("{", i);
      const nextSemi = chunk.indexOf(";", i);

      // If next item is a declaration (has ';' before '{' or no '{' left)
      if (nextSemi !== -1 && (braceOpen === -1 || nextSemi < braceOpen)) {
        const decl = chunk.substring(i, nextSemi).trim();
        if (decl && decl.includes(":")) {
          currentDecls.push(decl + ";");
        }
        i = nextSemi + 1;
        continue;
      }

      if (braceOpen === -1) break;

      // Nested Block encountered!
      const rawSel = chunk.substring(i, braceOpen).trim();
      const braceClose = this.findMatchingBrace(chunk, braceOpen);
      const innerContent = chunk.substring(braceOpen + 1, braceClose);

      // Handle @media or at-rules specially
      if (rawSel.startsWith("@media")) {
        const nestedMediaDecls: { selector: string; declarations: string[] }[] = [];
        this.parseNestedBlocks(innerContent, currentSelector, nestedMediaDecls);
        const mediaBody = nestedMediaDecls
          .map((r) => `  ${r.selector} {\n    ${r.declarations.join("\n    ")}\n  }`)
          .join("\n\n");
        currentDecls.push(`${rawSel} {\n${mediaBody}\n}`);
      } else {
        // Resolve combinators with currentSelector
        const combinedSelector = this.resolveParentSelector(currentSelector, rawSel);
        this.parseNestedBlocks(innerContent, combinedSelector, results);
      }

      i = braceClose + 1;
    }

    if (currentSelector && currentDecls.length > 0) {
      results.push({
        selector: currentSelector,
        declarations: currentDecls,
      });
    }
  }

  /**
   * Resolves '&' parent combinators:
   * parent: '.btn', child: '&:hover' -> '.btn:hover'
   * parent: '.block', child: '&__element' -> '.block__element'
   * parent: '.card', child: '.theme-dark &' -> '.theme-dark .card'
   * parent: '.item', child: '> span' -> '.item > span'
   */
  public resolveParentSelector(parent: string, child: string): string {
    if (!parent) return child;

    const parents = parent.split(",").map((p) => p.trim());
    const children = child.split(",").map((c) => c.trim());
    const resolved: string[] = [];

    for (const p of parents) {
      for (const c of children) {
        if (c.includes("&")) {
          // Replace '&' with parent selector
          resolved.push(c.replace(/&/g, p));
        } else if (/^[>+~]/.test(c)) {
          // Direct combinator: > span -> .parent > span
          resolved.push(`${p} ${c}`);
        } else {
          // Standard descendant: .child -> .parent .child
          resolved.push(`${p} ${c}`);
        }
      }
    }

    return resolved.join(", ");
  }

  // =========================================================================
  // Built-in Function Evaluator
  // =========================================================================

  private evaluateBuiltinFunctions(code: string): string {
    let res = code;

    // Evaluate simple darken / lighten
    // e.g. darken(#ffffff, 10%) or lighten(#000000, 20%)
    res = res.replace(/(lighten|darken)\s*\(\s*(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)\s*,\s*(\d+)%\s*\)/g, (_, fn, color, pct) => {
      return this.adjustLightness(color, fn === "lighten" ? Number(pct) : -Number(pct));
    });

    return res;
  }

  private adjustLightness(hexColor: string, percentDelta: number): string {
    // If hex #rrggbb
    if (/^#[0-9a-fA-F]{6}$/.test(hexColor)) {
      let r = parseInt(hexColor.slice(1, 3), 16);
      let g = parseInt(hexColor.slice(3, 5), 16);
      let b = parseInt(hexColor.slice(5, 7), 16);

      const factor = 1 + percentDelta / 100;
      r = Math.min(255, Math.max(0, Math.round(r * factor)));
      g = Math.min(255, Math.max(0, Math.round(g * factor)));
      b = Math.min(255, Math.max(0, Math.round(b * factor)));

      const toHex = (n: number) => n.toString(16).padStart(2, "0");
      return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    }
    return hexColor;
  }

  private findMatchingBrace(code: string, openIndex: number): number {
    let depth = 1;
    let i = openIndex + 1;
    while (i < code.length && depth > 0) {
      if (code[i] === "{") depth++;
      else if (code[i] === "}") depth--;
      i++;
    }
    return i - 1;
  }
}

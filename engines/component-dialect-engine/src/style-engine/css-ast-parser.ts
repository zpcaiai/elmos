/**
 * Industrial CSS AST Parser and Serializer.
 * 
 * Supports CSS Rules (Style, @media, @keyframes, @supports, @font-face, @container),
 * complex selector parsing (attributes, pseudo-classes, pseudo-elements, combinators),
 * custom properties (CSS variables), and formatted AST serialization.
 */

export interface CssDeclaration {
  property: string;
  value: string;
  important: boolean;
  raw?: string;
}

export interface CssSelector {
  raw: string;
  parts: CssSelectorPart[];
}

export interface CssSelectorPart {
  type: "type" | "class" | "id" | "attribute" | "pseudo-class" | "pseudo-element" | "combinator";
  value: string;
  combinator?: " " | ">" | "+" | "~";
  attributeDetails?: {
    name: string;
    operator?: "=" | "~=" | "|=" | "^=" | "$=" | "*=";
    value?: string;
    caseSensitive?: boolean;
  };
  pseudoArg?: string;
}

export interface CssStyleRule {
  type: "style";
  selectors: CssSelector[];
  declarations: CssDeclaration[];
}

export interface CssMediaRule {
  type: "media";
  params: string; // e.g. "(min-width: 768px)"
  rules: CssRule[];
}

export interface CssKeyframesRule {
  type: "keyframes";
  name: string;
  vendorPrefix?: string;
  keyframes: {
    keyframeSelector: string; // "0%", "from", "100%", "to"
    declarations: CssDeclaration[];
  }[];
}

export interface CssFontFaceRule {
  type: "font-face";
  declarations: CssDeclaration[];
}

export interface CssSupportsRule {
  type: "supports";
  condition: string;
  rules: CssRule[];
}

export interface CssContainerRule {
  type: "container";
  nameAndCondition: string;
  rules: CssRule[];
}

export type CssRule =
  | CssStyleRule
  | CssMediaRule
  | CssKeyframesRule
  | CssFontFaceRule
  | CssSupportsRule
  | CssContainerRule;

export interface CssStylesheet {
  rules: CssRule[];
  sourcePath?: string;
}

export class CssAstParser {
  /**
   * Parses raw CSS code into a structured CssStylesheet AST.
   */
  public parse(css: string, sourcePath?: string): CssStylesheet {
    const cleaned = this.stripComments(css).trim();
    const rules = this.parseRuleList(cleaned);
    return { rules, sourcePath };
  }

  /**
   * Serializes a CssStylesheet or rule list back into formatted CSS.
   */
  public serialize(stylesheetOrRules: CssStylesheet | CssRule[], indent = 0): string {
    const rules = Array.isArray(stylesheetOrRules) ? stylesheetOrRules : stylesheetOrRules.rules;
    const pad = "  ".repeat(indent);
    const out: string[] = [];

    for (const rule of rules) {
      switch (rule.type) {
        case "style": {
          const selectorStr = rule.selectors.map((s) => s.raw).join(", ");
          if (rule.declarations.length === 0) {
            out.push(`${pad}${selectorStr} {}`);
          } else {
            out.push(`${pad}${selectorStr} {`);
            for (const decl of rule.declarations) {
              const imp = decl.important ? " !important" : "";
              out.push(`${pad}  ${decl.property}: ${decl.value}${imp};`);
            }
            out.push(`${pad}}`);
          }
          break;
        }
        case "media": {
          out.push(`${pad}@media ${rule.params} {`);
          out.push(this.serialize(rule.rules, indent + 1));
          out.push(`${pad}}`);
          break;
        }
        case "keyframes": {
          const prefix = rule.vendorPrefix ? `-${rule.vendorPrefix}-` : "";
          out.push(`${pad}@${prefix}keyframes ${rule.name} {`);
          for (const kf of rule.keyframes) {
            out.push(`${pad}  ${kf.keyframeSelector} {`);
            for (const decl of kf.declarations) {
              const imp = decl.important ? " !important" : "";
              out.push(`${pad}    ${decl.property}: ${decl.value}${imp};`);
            }
            out.push(`${pad}  }`);
          }
          out.push(`${pad}}`);
          break;
        }
        case "supports": {
          out.push(`${pad}@supports ${rule.condition} {`);
          out.push(this.serialize(rule.rules, indent + 1));
          out.push(`${pad}}`);
          break;
        }
        case "container": {
          out.push(`${pad}@container ${rule.nameAndCondition} {`);
          out.push(this.serialize(rule.rules, indent + 1));
          out.push(`${pad}}`);
          break;
        }
        case "font-face": {
          out.push(`${pad}@font-face {`);
          for (const decl of rule.declarations) {
            const imp = decl.important ? " !important" : "";
            out.push(`${pad}  ${decl.property}: ${decl.value}${imp};`);
          }
          out.push(`${pad}}`);
          break;
        }
      }
    }

    return out.join("\n");
  }

  // =========================================================================
  // Internal Recursive Descent Parser
  // =========================================================================

  private stripComments(css: string): string {
    return css.replace(/\/\*[\s\S]*?\*\//g, "");
  }

  private parseRuleList(css: string): CssRule[] {
    const rules: CssRule[] = [];
    let i = 0;
    const len = css.length;

    while (i < len) {
      // skip whitespace and semicolons
      while (i < len && /[\s;]/.test(css[i]!)) i++;
      if (i >= len) break;

      if (css[i] === "@") {
        // At-Rule
        const atRuleEnd = this.findAtRuleEnd(css, i);
        const atChunk = css.substring(i, atRuleEnd);
        const parsedAt = this.parseAtRule(atChunk);
        if (parsedAt) rules.push(parsedAt);
        i = atRuleEnd;
      } else {
        // Style Rule
        const blockStart = css.indexOf("{", i);
        if (blockStart === -1) break;
        const selectorRaw = css.substring(i, blockStart).trim();
        const blockEnd = this.findMatchingBrace(css, blockStart);
        const declsRaw = css.substring(blockStart + 1, blockEnd);

        if (selectorRaw.length > 0) {
          rules.push({
            type: "style",
            selectors: this.parseSelectorList(selectorRaw),
            declarations: this.parseDeclarations(declsRaw),
          });
        }
        i = blockEnd + 1;
      }
    }

    return rules;
  }

  private findMatchingBrace(css: string, openIndex: number): number {
    let depth = 1;
    let i = openIndex + 1;
    while (i < css.length && depth > 0) {
      if (css[i] === "{") depth++;
      else if (css[i] === "}") depth--;
      i++;
    }
    return i - 1;
  }

  private findAtRuleEnd(css: string, atIndex: number): number {
    let i = atIndex;
    let inParen = 0;
    while (i < css.length) {
      const char = css[i];
      if (char === "(") inParen++;
      else if (char === ")") inParen--;
      else if (char === "{" && inParen === 0) {
        return this.findMatchingBrace(css, i) + 1;
      } else if (char === ";" && inParen === 0) {
        return i + 1;
      }
      i++;
    }
    return css.length;
  }

  private parseAtRule(chunk: string): CssRule | null {
    const trimmed = chunk.trim();
    if (trimmed.startsWith("@media")) {
      const braceIdx = trimmed.indexOf("{");
      if (braceIdx === -1) return null;
      const params = trimmed.substring(6, braceIdx).trim();
      const body = trimmed.substring(braceIdx + 1, trimmed.lastIndexOf("}")).trim();
      return {
        type: "media",
        params,
        rules: this.parseRuleList(body),
      };
    }

    if (trimmed.startsWith("@keyframes") || /@-[\w]+-keyframes/.test(trimmed)) {
      const prefixMatch = trimmed.match(/^@-([a-zA-Z]+)-keyframes/);
      const vendorPrefix = prefixMatch ? prefixMatch[1] : undefined;
      const headerEnd = trimmed.indexOf("{");
      if (headerEnd === -1) return null;
      const atKw = vendorPrefix ? `@-${vendorPrefix}-keyframes` : "@keyframes";
      const name = trimmed.substring(atKw.length, headerEnd).trim();
      const body = trimmed.substring(headerEnd + 1, trimmed.lastIndexOf("}")).trim();

      const keyframes: CssKeyframesRule["keyframes"] = [];
      let i = 0;
      while (i < body.length) {
        while (i < body.length && /\s/.test(body[i]!)) i++;
        if (i >= body.length) break;
        const bStart = body.indexOf("{", i);
        if (bStart === -1) break;
        const sel = body.substring(i, bStart).trim();
        const bEnd = this.findMatchingBrace(body, bStart);
        const innerDecls = body.substring(bStart + 1, bEnd);
        keyframes.push({
          keyframeSelector: sel,
          declarations: this.parseDeclarations(innerDecls),
        });
        i = bEnd + 1;
      }

      return {
        type: "keyframes",
        name,
        vendorPrefix,
        keyframes,
      };
    }

    if (trimmed.startsWith("@font-face")) {
      const braceIdx = trimmed.indexOf("{");
      if (braceIdx === -1) return null;
      const body = trimmed.substring(braceIdx + 1, trimmed.lastIndexOf("}")).trim();
      return {
        type: "font-face",
        declarations: this.parseDeclarations(body),
      };
    }

    if (trimmed.startsWith("@supports")) {
      const braceIdx = trimmed.indexOf("{");
      if (braceIdx === -1) return null;
      const cond = trimmed.substring(9, braceIdx).trim();
      const body = trimmed.substring(braceIdx + 1, trimmed.lastIndexOf("}")).trim();
      return {
        type: "supports",
        condition: cond,
        rules: this.parseRuleList(body),
      };
    }

    if (trimmed.startsWith("@container")) {
      const braceIdx = trimmed.indexOf("{");
      if (braceIdx === -1) return null;
      const cond = trimmed.substring(10, braceIdx).trim();
      const body = trimmed.substring(braceIdx + 1, trimmed.lastIndexOf("}")).trim();
      return {
        type: "container",
        nameAndCondition: cond,
        rules: this.parseRuleList(body),
      };
    }

    return null;
  }

  /**
   * Parses declaration block into an array of CssDeclarations.
   */
  public parseDeclarations(declsStr: string): CssDeclaration[] {
    const list: CssDeclaration[] = [];
    const tokens = declsStr.split(";");

    for (const rawToken of tokens) {
      const token = rawToken.trim();
      if (!token) continue;

      const colonIdx = token.indexOf(":");
      if (colonIdx === -1) continue;

      const property = token.substring(0, colonIdx).trim();
      let value = token.substring(colonIdx + 1).trim();
      let important = false;

      if (/!important\s*$/i.test(value)) {
        important = true;
        value = value.replace(/!important\s*$/i, "").trim();
      }

      list.push({
        property,
        value,
        important,
        raw: token,
      });
    }

    return list;
  }

  /**
   * Parses comma-separated selector string into CssSelector objects.
   */
  public parseSelectorList(selectorsStr: string): CssSelector[] {
    const rawList = this.splitSelectorsSafely(selectorsStr);
    return rawList.map((raw) => ({
      raw: raw.trim(),
      parts: this.parseSelectorParts(raw.trim()),
    }));
  }

  private splitSelectorsSafely(str: string): string[] {
    const parts: string[] = [];
    let current = "";
    let parenDepth = 0;
    let bracketDepth = 0;

    for (let i = 0; i < str.length; i++) {
      const ch = str[i];
      if (ch === "(") parenDepth++;
      else if (ch === ")") parenDepth--;
      else if (ch === "[") bracketDepth++;
      else if (ch === "]") bracketDepth--;

      if (ch === "," && parenDepth === 0 && bracketDepth === 0) {
        parts.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
    if (current.trim()) parts.push(current.trim());
    return parts;
  }

  /**
   * Parses a single selector into structured parts with type, pseudo, and combinators.
   */
  public parseSelectorParts(selector: string): CssSelectorPart[] {
    const parts: CssSelectorPart[] = [];
    // Tokenize selector regex:
    // class (.cls), id (#id), attribute ([attr=val]), pseudo (::before or :hover or :nth-child(n)), type (div), combinator (>, +, ~)
    const regex = /([>+~]|\s+)|(\.[a-zA-Z0-9_-]+)|(#[a-zA-Z0-9_-]+)|(\[[^\]]+\])|(::[a-zA-Z0-9_-]+|:[a-zA-Z0-9_-]+(?:\([^)]*\))?)|([a-zA-Z0-9_-]+|\*)/g;

    let match: RegExpExecArray | null;
    while ((match = regex.exec(selector)) !== null) {
      const [full, comb, cls, id, attr, pseudo, type] = match;

      if (comb !== undefined) {
        const c = comb.trim() as ">" | "+" | "~" | "";
        parts.push({
          type: "combinator",
          value: comb,
          combinator: c === "" ? " " : (c as ">" | "+" | "~"),
        });
      } else if (cls !== undefined) {
        parts.push({ type: "class", value: cls });
      } else if (id !== undefined) {
        parts.push({ type: "id", value: id });
      } else if (attr !== undefined) {
        parts.push({
          type: "attribute",
          value: attr,
          attributeDetails: this.parseAttributeSelector(attr),
        });
      } else if (pseudo !== undefined) {
        const isElement = pseudo.startsWith("::");
        const parenIdx = pseudo.indexOf("(");
        let pseudoName = pseudo;
        let pseudoArg: string | undefined;

        if (parenIdx !== -1) {
          pseudoName = pseudo.substring(0, parenIdx);
          pseudoArg = pseudo.substring(parenIdx + 1, pseudo.lastIndexOf(")"));
        }

        parts.push({
          type: isElement ? "pseudo-element" : "pseudo-class",
          value: pseudoName,
          pseudoArg,
        });
      } else if (type !== undefined) {
        parts.push({ type: "type", value: type });
      }
    }

    return parts;
  }

  private parseAttributeSelector(attrStr: string): CssSelectorPart["attributeDetails"] {
    const inner = attrStr.slice(1, -1).trim();
    const opMatch = inner.match(/^([a-zA-Z0-9_-]+)\s*([~|^$*]?=)\s*["']?([^"']*)["']?\s*([iI]?)$/);
    if (!opMatch) {
      return { name: inner };
    }
    return {
      name: opMatch[1]!,
      operator: opMatch[2]! as any,
      value: opMatch[3]!,
      caseSensitive: opMatch[4] !== "i" && opMatch[4] !== "I",
    };
  }
}

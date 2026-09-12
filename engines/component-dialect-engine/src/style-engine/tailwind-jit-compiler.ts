/**
 * Industrial Tailwind CSS JIT Compiler.
 * 
 * Generates exact CSS declarations from Tailwind utility classes, supporting:
 * - Arbitrary values: w-[240px], bg-[#1e293b], p-[12px_16px], text-[1.25rem]
 * - Arbitrary properties: [mask-type:alpha]
 * - Responsive prefixes: sm:, md:, lg:, xl:, 2xl:
 * - State variants: hover:, focus:, active:, disabled:, dark:, group-hover:
 * - Full utility library: Layout, Flex, Grid, Spacing, Sizing, Colors, Borders, Typography, Shadows
 */

import { FullSyntaxNode } from "../full-syntax-ast/types";

export interface TailwindCompiledRule {
  className: string;
  cssSelector: string;
  declarations: Record<string, string>;
  mediaQuery?: string;
  pseudoClass?: string;
}

export class TailwindJitCompiler {
  // Breakpoints map
  private breakpoints: Record<string, string> = {
    sm: "min-width: 640px",
    md: "min-width: 768px",
    lg: "min-width: 1024px",
    xl: "min-width: 1280px",
    "2xl": "min-width: 1536px",
  };

  // Standard color palette (slate, gray, red, green, blue, etc.)
  private colors: Record<string, string> = {
    transparent: "transparent",
    current: "currentColor",
    black: "#000000",
    white: "#ffffff",
    "slate-50": "#f8fafc",
    "slate-100": "#f1f5f9",
    "slate-200": "#e2e8f0",
    "slate-300": "#cbd5e1",
    "slate-400": "#94a3b8",
    "slate-500": "#64748b",
    "slate-600": "#475569",
    "slate-700": "#334155",
    "slate-800": "#1e293b",
    "slate-900": "#0f172a",
    "gray-50": "#f9fafb",
    "gray-100": "#f3f4f6",
    "gray-200": "#e5e7eb",
    "gray-300": "#d1d5db",
    "gray-400": "#9ca3af",
    "gray-500": "#6b7280",
    "gray-600": "#4b5563",
    "gray-700": "#374151",
    "gray-800": "#1f2937",
    "gray-900": "#111827",
    "red-500": "#ef4444",
    "red-600": "#dc2626",
    "green-500": "#22c55e",
    "green-600": "#16a34a",
    "blue-500": "#3b82f6",
    "blue-600": "#2563eb",
    "indigo-500": "#6366f1",
    "indigo-600": "#4f46e5",
    "purple-500": "#a855f7",
    "amber-500": "#f59e0b",
  };

  // Spacing scale: 1 = 0.25rem (4px)
  private spacingScale: Record<string, string> = {
    "0": "0px",
    "0.5": "0.125rem",
    "1": "0.25rem",
    "1.5": "0.375rem",
    "2": "0.5rem",
    "2.5": "0.625rem",
    "3": "0.75rem",
    "3.5": "0.875rem",
    "4": "1rem",
    "5": "1.25rem",
    "6": "1.5rem",
    "7": "1.75rem",
    "8": "2rem",
    "9": "2.25rem",
    "10": "2.5rem",
    "12": "3rem",
    "14": "3.5rem",
    "16": "4rem",
    "20": "5rem",
    "24": "6rem",
    "32": "8rem",
    "40": "10rem",
    "48": "12rem",
    "64": "16rem",
    "auto": "auto",
    "px": "1px",
    "full": "100%",
    "screen": "100vw",
  };

  /**
   * Scans a FullSyntaxNode template tree for all class / className attributes.
   */
  public extractClassesFromTemplate(node: FullSyntaxNode): string[] {
    const classSet = new Set<string>();

    const traverse = (n: FullSyntaxNode) => {
      if (!n) return;
      if (n.attrs) {
        for (const a of n.attrs) {
          if (a.name === "class" || a.name === "className") {
            if (a.value) {
              for (const cls of a.value.split(/\s+/)) {
                if (cls.trim()) classSet.add(cls.trim());
              }
            }
          }
        }
      }
      if (n.children) n.children.forEach(traverse);
      if (n.condition) {
        traverse(n.condition.thenNode);
        if (n.condition.elseNode) traverse(n.condition.elseNode);
        if (n.condition.elifBranches) n.condition.elifBranches.forEach((b) => traverse(b.node));
      }
      if (n.loop) traverse(n.loop.bodyNode);
    };

    traverse(node);
    return Array.from(classSet);
  }

  /**
   * Compiles an array of Tailwind class names into structured CSS rules.
   */
  public compileClasses(classNames: string[]): TailwindCompiledRule[] {
    const rules: TailwindCompiledRule[] = [];
    const seenSelectors = new Set<string>();

    for (const rawName of classNames) {
      const parsed = this.parseUtilityClass(rawName);
      if (parsed) {
        const key = `${parsed.mediaQuery || ""}_${parsed.cssSelector}`;
        if (!seenSelectors.has(key)) {
          seenSelectors.add(key);
          rules.push(parsed);
        }
      }
    }

    return rules;
  }

  /**
   * Compiles class names into standard CSS string.
   */
  public generateCss(classNames: string[]): string {
    const rules = this.compileClasses(classNames);
    const standardRules: string[] = [];
    const mediaRulesMap: Map<string, string[]> = new Map();

    for (const r of rules) {
      const decls = Object.entries(r.declarations)
        .map(([prop, val]) => `  ${prop}: ${val};`)
        .join("\n");
      const ruleBlock = `${r.cssSelector} {\n${decls}\n}`;

      if (r.mediaQuery) {
        if (!mediaRulesMap.has(r.mediaQuery)) {
          mediaRulesMap.set(r.mediaQuery, []);
        }
        mediaRulesMap.get(r.mediaQuery)!.push(ruleBlock);
      } else {
        standardRules.push(ruleBlock);
      }
    }

    const output: string[] = [...standardRules];
    for (const [query, blocks] of mediaRulesMap.entries()) {
      output.push(`@media (${query}) {\n${blocks.map((b) => "  " + b.split("\n").join("\n  ")).join("\n\n")}\n}`);
    }

    return output.join("\n\n");
  }

  /**
   * Parses a single utility class (e.g. `md:hover:bg-[#1e293b]`, `w-full`, `[mask-type:alpha]`).
   */
  public parseUtilityClass(className: string): TailwindCompiledRule | null {
    // Escape class selector for CSS
    const escapedSelector = "." + this.escapeCssSelector(className);

    // Check for prefixes (sm:, md:, hover:, focus:, dark:)
    let remaining = className;
    let mediaQuery: string | undefined;
    let pseudoClass: string | undefined;
    let isGroupHover = false;

    // Peel off variants
    let hasMorePrefixes = true;
    while (hasMorePrefixes) {
      const colonIdx = remaining.indexOf(":");
      if (colonIdx === -1) break;

      const prefix = remaining.substring(0, colonIdx);
      if (this.breakpoints[prefix]) {
        mediaQuery = this.breakpoints[prefix];
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "hover" || prefix === "focus" || prefix === "active" || prefix === "disabled") {
        pseudoClass = `:${prefix}`;
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "first") {
        pseudoClass = ":first-child";
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "last") {
        pseudoClass = ":last-child";
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "odd") {
        pseudoClass = ":nth-child(odd)";
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "even") {
        pseudoClass = ":nth-child(even)";
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "dark") {
        mediaQuery = "prefers-color-scheme: dark";
        remaining = remaining.substring(colonIdx + 1);
      } else if (prefix === "group-hover") {
        isGroupHover = true;
        remaining = remaining.substring(colonIdx + 1);
      } else {
        hasMorePrefixes = false;
      }
    }

    // Determine target selector
    let finalSelector = escapedSelector;
    if (pseudoClass) finalSelector += pseudoClass;
    if (isGroupHover) finalSelector = `.group:hover ${finalSelector}`;

    // 1. Check Arbitrary Property: `[mask-type:alpha]`
    if (remaining.startsWith("[") && remaining.endsWith("]") && remaining.includes(":")) {
      const inner = remaining.slice(1, -1);
      const colon = inner.indexOf(":");
      const prop = inner.substring(0, colon).trim();
      const val = inner.substring(colon + 1).trim();
      return {
        className,
        cssSelector: finalSelector,
        declarations: { [prop]: val },
        mediaQuery,
        pseudoClass,
      };
    }

    // 2. Check Arbitrary Value: `w-[240px]`, `bg-[#1e293b]`, `p-[10px_20px]`
    const arbMatch = remaining.match(/^([a-zA-Z0-9_-]+)-\[(.+)\]$/);
    if (arbMatch) {
      const prefix = arbMatch[1]!;
      const rawVal = arbMatch[2]!.replace(/_/g, " ");
      const decls = this.mapArbitraryValue(prefix, rawVal);
      if (decls) {
        return {
          className,
          cssSelector: finalSelector,
          declarations: decls,
          mediaQuery,
          pseudoClass,
        };
      }
    }

    // 3. Check Standard Utilities
    const standardDecls = this.mapStandardUtility(remaining);
    if (standardDecls) {
      return {
        className,
        cssSelector: finalSelector,
        declarations: standardDecls,
        mediaQuery,
        pseudoClass,
      };
    }

    return null;
  }

  private mapArbitraryValue(prefix: string, val: string): Record<string, string> | null {
    switch (prefix) {
      case "w": return { width: val };
      case "h": return { height: val };
      case "min-w": return { "min-width": val };
      case "max-w": return { "max-width": val };
      case "min-h": return { "min-height": val };
      case "max-h": return { "max-height": val };
      case "p": return { padding: val };
      case "px": return { "padding-left": val, "padding-right": val };
      case "py": return { "padding-top": val, "padding-bottom": val };
      case "pt": return { "padding-top": val };
      case "pb": return { "padding-bottom": val };
      case "pl": return { "padding-left": val };
      case "pr": return { "padding-right": val };
      case "m": return { margin: val };
      case "mx": return { "margin-left": val, "margin-right": val };
      case "my": return { "margin-top": val, "margin-bottom": val };
      case "mt": return { "margin-top": val };
      case "mb": return { "margin-bottom": val };
      case "ml": return { "margin-left": val };
      case "mr": return { "margin-right": val };
      case "bg": return { "background-color": val };
      case "text":
        if (val.startsWith("#") || val.startsWith("rgb") || val.startsWith("hsl")) {
          return { color: val };
        }
        return { "font-size": val };
      case "border": return { "border-color": val };
      case "rounded": return { "border-radius": val };
      case "gap": return { gap: val };
      case "z": return { "z-index": val };
      case "opacity": return { opacity: val };
      case "leading": return { "line-height": val };
      case "tracking": return { "letter-spacing": val };
      case "top": return { top: val };
      case "bottom": return { bottom: val };
      case "left": return { left: val };
      case "right": return { right: val };
    }
    return null;
  }

  private mapStandardUtility(name: string): Record<string, string> | null {
    // Display & Layout
    if (name === "flex") return { display: "flex" };
    if (name === "inline-flex") return { display: "inline-flex" };
    if (name === "grid") return { display: "grid" };
    if (name === "block") return { display: "block" };
    if (name === "inline-block") return { display: "inline-block" };
    if (name === "hidden") return { display: "none" };

    // Flex attributes
    if (name === "flex-row") return { "flex-direction": "row" };
    if (name === "flex-col") return { "flex-direction": "column" };
    if (name === "flex-wrap") return { "flex-wrap": "wrap" };
    if (name === "flex-nowrap") return { "flex-wrap": "nowrap" };
    if (name === "flex-1") return { flex: "1 1 0%" };
    if (name === "flex-auto") return { flex: "1 1 auto" };
    if (name === "flex-none") return { flex: "none" };
    if (name === "items-center") return { "align-items": "center" };
    if (name === "items-start") return { "align-items": "flex-start" };
    if (name === "items-end") return { "align-items": "flex-end" };
    if (name === "justify-center") return { "justify-content": "center" };
    if (name === "justify-between") return { "justify-content": "space-between" };
    if (name === "justify-start") return { "justify-content": "flex-start" };
    if (name === "justify-end") return { "justify-content": "flex-end" };

    // Grid cols & gap
    const gridColsMatch = name.match(/^grid-cols-(\d+)$/);
    if (gridColsMatch) return { "grid-template-columns": `repeat(${gridColsMatch[1]}, minmax(0, 1fr))` };
    const colSpanMatch = name.match(/^col-span-(\d+)$/);
    if (colSpanMatch) return { "grid-column": `span ${colSpanMatch[1]} / span ${colSpanMatch[1]}` };
    const gapMatch = name.match(/^gap-(\d+|\d+\.\d+)$/);
    if (gapMatch && this.spacingScale[gapMatch[1]!]) return { gap: this.spacingScale[gapMatch[1]!]! };

    // Width & Height
    if (name.startsWith("w-")) {
      const sub = name.slice(2);
      if (this.spacingScale[sub]) return { width: this.spacingScale[sub]! };
      if (sub === "1/2") return { width: "50%" };
      if (sub === "1/3") return { width: "33.333333%" };
      if (sub === "2/3") return { width: "66.666667%" };
      if (sub === "1/4") return { width: "25%" };
      if (sub === "3/4") return { width: "75%" };
    }
    if (name.startsWith("h-")) {
      const sub = name.slice(2);
      if (this.spacingScale[sub]) return { height: this.spacingScale[sub]! };
      if (sub === "1/2") return { height: "50%" };
    }

    // Padding & Margin
    const pMatch = name.match(/^p([xytrbl])?-(\d+|\d+\.\d+|auto|px)$/);
    if (pMatch) {
      const dir = pMatch[1];
      const val = this.spacingScale[pMatch[2]!];
      if (val) {
        if (!dir) return { padding: val };
        if (dir === "x") return { "padding-left": val, "padding-right": val };
        if (dir === "y") return { "padding-top": val, "padding-bottom": val };
        if (dir === "t") return { "padding-top": val };
        if (dir === "b") return { "padding-bottom": val };
        if (dir === "l") return { "padding-left": val };
        if (dir === "r") return { "padding-right": val };
      }
    }

    const mMatch = name.match(/^m([xytrbl])?-(\d+|\d+\.\d+|auto|px)$/);
    if (mMatch) {
      const dir = mMatch[1];
      const val = this.spacingScale[mMatch[2]!];
      if (val) {
        if (!dir) return { margin: val };
        if (dir === "x") return { "margin-left": val, "margin-right": val };
        if (dir === "y") return { "margin-top": val, "margin-bottom": val };
        if (dir === "t") return { "margin-top": val };
        if (dir === "b") return { "margin-bottom": val };
        if (dir === "l") return { "margin-left": val };
        if (dir === "r") return { "margin-right": val };
      }
    }

    // Background color
    if (name.startsWith("bg-")) {
      const c = name.slice(3);
      if (this.colors[c]) return { "background-color": this.colors[c]! };
    }

    // Text color & Font size
    if (name.startsWith("text-")) {
      const c = name.slice(5);
      if (this.colors[c]) return { color: this.colors[c]! };
      if (c === "xs") return { "font-size": "0.75rem", "line-height": "1rem" };
      if (c === "sm") return { "font-size": "0.875rem", "line-height": "1.25rem" };
      if (c === "base") return { "font-size": "1rem", "line-height": "1.5rem" };
      if (c === "lg") return { "font-size": "1.125rem", "line-height": "1.75rem" };
      if (c === "xl") return { "font-size": "1.25rem", "line-height": "1.75rem" };
      if (c === "2xl") return { "font-size": "1.5rem", "line-height": "2rem" };
      if (c === "3xl") return { "font-size": "1.875rem", "line-height": "2.25rem" };
      if (c === "left") return { "text-align": "left" };
      if (c === "center") return { "text-align": "center" };
      if (c === "right") return { "text-align": "right" };
    }

    // Font weight
    if (name === "font-normal") return { "font-weight": "400" };
    if (name === "font-medium") return { "font-weight": "500" };
    if (name === "font-semibold") return { "font-weight": "600" };
    if (name === "font-bold") return { "font-weight": "700" };

    // Border & Radius
    if (name === "border") return { "border-width": "1px", "border-style": "solid" };
    if (name === "border-0") return { "border-width": "0px" };
    if (name === "border-2") return { "border-width": "2px", "border-style": "solid" };
    if (name === "border-4") return { "border-width": "4px", "border-style": "solid" };
    if (name.startsWith("border-")) {
      const c = name.slice(7);
      if (this.colors[c]) return { "border-color": this.colors[c]! };
    }
    if (name === "rounded") return { "border-radius": "0.25rem" };
    if (name === "rounded-sm") return { "border-radius": "0.125rem" };
    if (name === "rounded-md") return { "border-radius": "0.375rem" };
    if (name === "rounded-lg") return { "border-radius": "0.5rem" };
    if (name === "rounded-xl") return { "border-radius": "0.75rem" };
    if (name === "rounded-2xl") return { "border-radius": "1rem" };
    if (name === "rounded-full") return { "border-radius": "9999px" };

    // Shadow
    if (name === "shadow-sm") return { "box-shadow": "0 1px 2px 0 rgb(0 0 0 / 0.05)" };
    if (name === "shadow") return { "box-shadow": "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)" };
    if (name === "shadow-md") return { "box-shadow": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)" };
    if (name === "shadow-lg") return { "box-shadow": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)" };

    // Position
    if (name === "relative") return { position: "relative" };
    if (name === "absolute") return { position: "absolute" };
    if (name === "fixed") return { position: "fixed" };
    if (name === "sticky") return { position: "sticky" };
    if (name === "inset-0") return { top: "0px", right: "0px", bottom: "0px", left: "0px" };

    return null;
  }

  private escapeCssSelector(className: string): string {
    return className
      .replace(/:/g, "\\:")
      .replace(/\[/g, "\\[")
      .replace(/\]/g, "\\]")
      .replace(/#/g, "\\#")
      .replace(/\//g, "\\/")
      .replace(/\./g, "\\.")
      .replace(/%/g, "\\%");
  }
}

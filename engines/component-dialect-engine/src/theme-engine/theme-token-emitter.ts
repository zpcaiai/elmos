/**
 * @file theme-token-emitter.ts
 * @description Design Token Emitter for CSS Custom Properties, Tailwind configs, and MiniApp WXSS.
 * Emits platform-idiomatic design tokens from UniversalThemeIR.
 * Conforms to Batch 32 Skill 1204 (b32-design-token-theme-extraction).
 */

import {
  UniversalThemeIR,
  TargetTokenFormat,
  TokenEmitResult,
} from './theme-ir-types';

export class ThemeTokenEmitter {
  /**
   * Emit design tokens in specified target format
   */
  public emit(themeIR: UniversalThemeIR, format: TargetTokenFormat): TokenEmitResult {
    switch (format) {
      case 'css-variables':
        return this.emitCSSVariables(themeIR);
      case 'tailwind-theme':
        return this.emitTailwindConfig(themeIR);
      case 'miniapp-wxss':
        return this.emitMiniAppWXSS(themeIR);
      case 'dtcg-json':
        return this.emitDTCGJson(themeIR);
      default:
        throw new Error(`Unsupported token target format: ${format}`);
    }
  }

  private emitCSSVariables(themeIR: UniversalThemeIR): TokenEmitResult {
    const lines: string[] = [];
    lines.push(`/**`);
    lines.push(` * Design Tokens - CSS Custom Properties`);
    lines.push(` * Theme: ${themeIR.themeName} (v${themeIR.version})`);
    lines.push(` */\n`);

    lines.push(`:root {`);
    for (const token of themeIR.tokens) {
      const varName = token.name.startsWith('--') ? token.name : `--${token.name}`;
      const desc = token.description ? ` /* ${token.description} */` : '';
      lines.push(`  ${varName}: ${String(token.value)};${desc}`);
    }
    lines.push(`}\n`);

    for (const variant of themeIR.variants) {
      if (Object.keys(variant.tokenOverrides).length > 0) {
        lines.push(`[data-theme="${variant.variantId}"] {`);
        for (const [k, v] of Object.entries(variant.tokenOverrides)) {
          const varName = k.startsWith('--') ? k : `--${k}`;
          lines.push(`  ${varName}: ${String(v)};`);
        }
        lines.push(`}\n`);
      }
    }

    return {
      code: lines.join('\n'),
      fileName: `${themeIR.themeId}-variables.css`,
      format: 'css-variables',
      notes: [`Emitted ${themeIR.tokens.length} CSS variables`],
    };
  }

  private emitTailwindConfig(themeIR: UniversalThemeIR): TokenEmitResult {
    const lines: string[] = [];
    lines.push(`/** @type {import('tailwindcss').Config} */`);
    lines.push(`module.exports = {`);
    lines.push(`  theme: {`);
    lines.push(`    extend: {`);

    const colorTokens = themeIR.tokens.filter((t) => t.type === 'color');
    if (colorTokens.length > 0) {
      lines.push(`      colors: {`);
      for (const t of colorTokens) {
        lines.push(`        '${t.name.replace(/^color-/, '')}': '${String(t.value)}',`);
      }
      lines.push(`      },`);
    }

    lines.push(`    },`);
    lines.push(`  },`);
    lines.push(`};\n`);

    return {
      code: lines.join('\n'),
      fileName: 'tailwind.theme.js',
      format: 'tailwind-theme',
      notes: [`Emitted Tailwind theme config from ${themeIR.themeId}`],
    };
  }

  private emitMiniAppWXSS(themeIR: UniversalThemeIR): TokenEmitResult {
    const lines: string[] = [];
    lines.push(`/**`);
    lines.push(` * WeChat MiniApp Global Theme Variables (WXSS)`);
    lines.push(` */`);
    lines.push(`page {`);
    for (const token of themeIR.tokens) {
      const varName = token.name.startsWith('--') ? token.name : `--${token.name}`;
      lines.push(`  ${varName}: ${String(token.value)};`);
    }
    lines.push(`}\n`);

    return {
      code: lines.join('\n'),
      fileName: `${themeIR.themeId}.wxss`,
      format: 'miniapp-wxss',
      notes: [`Emitted MiniApp WXSS variables from ${themeIR.themeId}`],
    };
  }

  private emitDTCGJson(themeIR: UniversalThemeIR): TokenEmitResult {
    const dtcgTree: Record<string, any> = {};

    for (const token of themeIR.tokens) {
      let current = dtcgTree;
      for (let i = 0; i < token.path.length; i++) {
        const seg = token.path[i]!;
        if (i === token.path.length - 1) {
          current[seg] = {
            $value: token.value,
            $type: token.type,
            $description: token.description,
          };
        } else {
          if (!current[seg]) current[seg] = {};
          current = current[seg];
        }
      }
    }

    return {
      code: JSON.stringify(dtcgTree, null, 2),
      fileName: `${themeIR.themeId}.tokens.json`,
      format: 'dtcg-json',
      notes: [`Emitted W3C DTCG Design Tokens JSON for ${themeIR.themeId}`],
    };
  }
}

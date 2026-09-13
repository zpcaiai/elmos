/**
 * @file media-query-pseudo-bridge.ts
 * @description Bridges desktop/web pseudo-classes and responsive media queries to MiniApp & ArkUI.
 * MiniApp WXSS does not support standard hover/active/focus-visible pseudo-classes or desktop media queries:
 * 1. Pseudo-class Lowering: :hover/:active -> hover-class attributes, :focus -> focus property/state
 * 2. Media Query Compilation: @media (min-width) -> dynamic viewport listener (wx.onWindowResize)
 *    and responsive class emitters (screen-sm, screen-md, screen-lg) or 750rpx auto-scaling.
 */

export interface PseudoClassMapping {
  originalSelector: string;
  pseudoKind: 'hover' | 'active' | 'focus' | 'nth-child';
  hoverClassName: string;
  hoverStayTimeMs?: number;
  hoverStartTimeMs?: number;
}

export interface MediaQueryBreakpoint {
  name: string; // sm, md, lg, xl
  minWidthPx: number;
  maxWidthPx?: number;
}

export const DEFAULT_BREAKPOINTS: MediaQueryBreakpoint[] = [
  { name: 'sm', minWidthPx: 640 },
  { name: 'md', minWidthPx: 768 },
  { name: 'lg', minWidthPx: 1024 },
  { name: 'xl', minWidthPx: 1280 },
];

export class MediaQueryPseudoBridge {
  private breakpoints: MediaQueryBreakpoint[];

  constructor(breakpoints: MediaQueryBreakpoint[] = DEFAULT_BREAKPOINTS) {
    this.breakpoints = breakpoints;
  }

  /**
   * Lowers CSS content with pseudo-classes into MiniApp WXSS and extracted hover-class mappings
   */
  public lowerPseudoClasses(cssContent: string): {
    wxss: string;
    mappings: PseudoClassMapping[];
  } {
    const mappings: PseudoClassMapping[] = [];
    const lines = cssContent.split('\n');
    const outLines: string[] = [];

    let i = 0;
    while (i < lines.length) {
      const line = lines[i]!;

      // Check for :hover
      if (line.includes(':hover')) {
        const sel = line.replace(/\{.*/, '').trim();
        const cleanBase = sel.replace(':hover', '').replace(/^[.#]/, '').trim();
        const hoverCls = `${cleanBase}-hover`;

        mappings.push({
          originalSelector: sel,
          pseudoKind: 'hover',
          hoverClassName: hoverCls,
          hoverStayTimeMs: 70,
          hoverStartTimeMs: 20,
        });

        // Rewrite selector in WXSS to .className-hover
        outLines.push(line.replace(':hover', `-hover`));
      }
      // Check for :active
      else if (line.includes(':active')) {
        const sel = line.replace(/\{.*/, '').trim();
        const cleanBase = sel.replace(':active', '').replace(/^[.#]/, '').trim();
        const activeCls = `${cleanBase}-active`;

        mappings.push({
          originalSelector: sel,
          pseudoKind: 'active',
          hoverClassName: activeCls,
        });

        outLines.push(line.replace(':active', `-active`));
      }
      // Check for :focus or :focus-visible
      else if (line.includes(':focus')) {
        const sel = line.replace(/\{.*/, '').trim();
        const cleanBase = sel.replace(/:focus(-visible)?/, '').replace(/^[.#]/, '').trim();
        const focusCls = `${cleanBase}-focused`;

        mappings.push({
          originalSelector: sel,
          pseudoKind: 'focus',
          hoverClassName: focusCls,
        });

        outLines.push(line.replace(/:focus(-visible)?/, `-focused`));
      } else {
        outLines.push(line);
      }
      i++;
    }

    return {
      wxss: outLines.join('\n'),
      mappings,
    };
  }

  /**
   * Generates MiniApp Window Resize / MatchMedia Dynamic Responsive Breakpoint Manager
   */
  public generateResponsiveObserverCode(): string {
    const lines: string[] = [];

    lines.push(`/**`);
    lines.push(` * WeChat MiniApp Responsive Viewport Breakpoint Observer`);
    lines.push(` * Bridges desktop @media queries to dynamic Page data class names`);
    lines.push(` */\n`);

    lines.push(`export interface ViewportBreakpoints {`);
    lines.push(`  screenWidth: number;`);
    lines.push(`  screenHeight: number;`);
    lines.push(`  isLandscape: boolean;`);
    for (const bp of this.breakpoints) {
      lines.push(`  is${bp.name.toUpperCase()}: boolean;`);
    }
    lines.push(`}\n`);

    lines.push(`export class MiniAppViewportObserver {`);
    lines.push(`  private static listeners: Set<(bp: ViewportBreakpoints) => void> = new Set();`);
    lines.push(`  private static current: ViewportBreakpoints | null = null;\n`);

    lines.push(`  public static init(): void {`);
    lines.push(`    if (typeof wx === 'undefined') return;\n`);
    lines.push(`    const update = (width: number, height: number) => {`);
    lines.push(`      const bp: ViewportBreakpoints = {`);
    lines.push(`        screenWidth: width,`);
    lines.push(`        screenHeight: height,`);
    lines.push(`        isLandscape: width > height,`);
    for (const bp of this.breakpoints) {
      lines.push(`        is${bp.name.toUpperCase()}: width >= ${bp.minWidthPx},`);
    }
    lines.push(`      };`);
    lines.push(`      this.current = bp;`);
    lines.push(`      for (const cb of this.listeners) { cb(bp); }`);
    lines.push(`    };\n`);

    lines.push(`    try {`);
    lines.push(`      const info = wx.getSystemInfoSync();`);
    lines.push(`      update(info.windowWidth, info.windowHeight);`);
    lines.push(`      if (wx.onWindowResize) {`);
    lines.push(`        wx.onWindowResize((res) => update(res.size.windowWidth, res.size.windowHeight));`);
    lines.push(`      }`);
    lines.push(`    } catch (e) {`);
    lines.push(`      console.warn('[ViewportObserver] Failed to bind resize listener:', e);`);
    lines.push(`    }`);
    lines.push(`  }\n`);

    lines.push(`  public static subscribe(cb: (bp: ViewportBreakpoints) => void): () => void {`);
    lines.push(`    this.listeners.add(cb);`);
    lines.push(`    if (this.current) cb(this.current);`);
    lines.push(`    return () => this.listeners.delete(cb);`);
    lines.push(`  }\n`);

    lines.push(`  public static bindToPage(pageInstance: any): () => void {`);
    lines.push(`    return this.subscribe((bp) => {`);
    lines.push(`      if (typeof pageInstance.setData === 'function') {`);
    lines.push(`        pageInstance.setData({ $viewport: bp });`);
    lines.push(`      }`);
    lines.push(`    });`);
    lines.push(`  }`);
    lines.push(`}\n`);

    return lines.join('\n');
  }
}

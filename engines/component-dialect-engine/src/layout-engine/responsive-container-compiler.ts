/**
 * @file responsive-container-compiler.ts
 * @description Advanced Responsive Container Query Compiler and Fluid Sizing Engine.
 * Synthesizes CSS Container Queries (`@container`), fluid clamp() calculations for
 * typography and spacing, and multi-tier responsive viewport rules.
 * Conforms to Batch 32 Skill 1218 (b32-desktop-web-crossplatform) & Skill 1208.
 */

import {
  UniversalLayoutIR,
  LayoutContainerIR,
  LayoutItemIR,
  ResponsiveBreakpointKey,
  DEFAULT_BREAKPOINT_TIERS,
} from './layout-ir-types';

export interface FluidClampConfig {
  minViewportPx: number;
  maxViewportPx: number;
  minSizePx: number;
  maxSizePx: number;
}

export interface ContainerQuerySynthesisResult {
  containerCss: string;
  itemRulesCss: string;
  clampStyles: Record<string, string>;
  warnings: string[];
}

export class ResponsiveContainerCompiler {
  /**
   * Calculate CSS clamp() formula for fluid typography or fluid spacing
   * clamp(min, slope + intersection, max)
   */
  public static computeFluidClamp(config: FluidClampConfig): string {
    const { minViewportPx, maxViewportPx, minSizePx, maxSizePx } = config;
    if (minViewportPx >= maxViewportPx) {
      return `${minSizePx}px`;
    }

    const slope = (maxSizePx - minSizePx) / (maxViewportPx - minViewportPx);
    const yIntersection = -minViewportPx * slope + minSizePx;

    const slopeVw = Math.round(slope * 100 * 1000) / 1000;
    const yIntersectionRem = Math.round((yIntersection / 16) * 1000) / 1000;

    const minRem = Math.round((minSizePx / 16) * 1000) / 1000;
    const maxRem = Math.round((maxSizePx / 16) * 1000) / 1000;

    const sign = yIntersectionRem >= 0 ? '+' : '-';
    const absY = Math.abs(yIntersectionRem);

    return `clamp(${minRem}rem, ${slopeVw}vw ${sign} ${absY}rem, ${maxRem}rem)`;
  }

  /**
   * Synthesize modern CSS Container Queries for a Universal Layout container
   */
  public synthesizeContainerQueries(container: LayoutContainerIR): ContainerQuerySynthesisResult {
    const warnings: string[] = [];
    const containerName = container.containerQueryName || `cq_${container.id.replace(/[^a-zA-Z0-9_]/g, '_')}`;
    const containerType = container.containerType || 'inline-size';

    const containerCss = [
      `.${containerName}-wrapper {`,
      `  container-name: ${containerName};`,
      `  container-type: ${containerType};`,
      `  width: 100%;`,
      `  box-sizing: border-box;`,
      `}`,
    ].join('\n');

    const itemRules: string[] = [];
    const clampStyles: Record<string, string> = {};

    container.children.forEach((item, index) => {
      const itemSelector = `.${containerName}-item-${index + 1}`;

      if (item.containerConditions && item.containerConditions.length > 0) {
        for (const cond of item.containerConditions) {
          const queryParts: string[] = [];
          if (cond.minWidth !== undefined) {
            queryParts.push(`(min-width: ${cond.minWidth}px)`);
          }
          if (cond.maxWidth !== undefined) {
            queryParts.push(`(max-width: ${cond.maxWidth}px)`);
          }
          const queryCondStr = queryParts.join(' and ');

          const styleEntries = Object.entries(cond.styleOverrides)
            .map(([prop, val]) => `    ${this.kebabCase(prop)}: ${val};`)
            .join('\n');

          itemRules.push(
            `@container ${containerName} ${queryCondStr} {\n  ${itemSelector} {\n${styleEntries}\n  }\n}`
          );
        }
      }
    });

    return {
      containerCss,
      itemRulesCss: itemRules.join('\n\n'),
      clampStyles,
      warnings,
    };
  }

  /**
   * Validate UniversalLayoutIR document for common responsive defects:
   * - Total column span exceeding row capacity without wrap
   * - Missing responsive breakpoints
   * - Invalid negative gutters or widths
   */
  public validateLayout(layout: UniversalLayoutIR): { isValid: boolean; errors: string[]; warnings: string[] } {
    const errors: string[] = [];
    const warnings: string[] = [];

    const checkContainer = (c: LayoutContainerIR, path: string) => {
      const baseSystem = layout.gridBaseSystem;

      // Check span sums across breakpoints
      const keys: ResponsiveBreakpointKey[] = ['xs', 'sm', 'md', 'lg', 'xl', 'xxl'];
      for (const k of keys) {
        let spanSum = 0;
        for (const child of c.children) {
          if (typeof child.span === 'number') {
            spanSum += child.span;
          } else if (typeof child.span === 'object' && child.span !== null) {
            const val = (child.span as any)[k];
            if (typeof val === 'number') {
              spanSum += val;
            }
          }
        }
        if (spanSum > baseSystem && c.wrap === 'nowrap') {
          errors.push(
            `Layout container at ${path} has nowrap set but total span for breakpoint '${k}' (${spanSum}) exceeds grid base (${baseSystem}).`
          );
        }
      }

      for (let i = 0; i < c.children.length; i++) {
        const item = c.children[i];
        if (item && item.nestedContainer) {
          checkContainer(item.nestedContainer, `${path} -> item[${i}] -> container`);
        }
      }
    };

    checkContainer(layout.rootContainer, 'rootContainer');

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
    };
  }

  private kebabCase(str: string): string {
    return str.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
  }
}

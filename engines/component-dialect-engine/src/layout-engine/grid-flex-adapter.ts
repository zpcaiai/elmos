/**
 * @file grid-flex-adapter.ts
 * @description Bidirectional layout compilation and transformation between
 * 12/24-column grid systems (Ant Design, Element Plus), pure CSS Grid,
 * Flexbox, WeChat MiniApp WXML layouts, and ArkUI native components.
 * Conforms to Batch 32 Skill 1218 (b32-desktop-web-crossplatform) & Skill 1208.
 */

import {
  UniversalLayoutIR,
  LayoutContainerIR,
  LayoutItemIR,
  LayoutCompileResult,
  LayoutFrameworkId,
  ResponsiveBreakpointKey,
  ResponsiveValue,
  DEFAULT_BREAKPOINT_TIERS,
  FlexDirection,
  JustifyContent,
  AlignItems,
} from './layout-ir-types';

export class GridFlexAdapter {
  private idCounter = 0;

  private generateId(prefix = 'layout'): string {
    return `${prefix}_${this.idCounter++}`;
  }

  /**
   * Helper to normalize a responsive value into an object keyed by breakpoints
   */
  public static normalizeResponsive<T>(val: ResponsiveValue<T> | undefined, fallback: T): Record<ResponsiveBreakpointKey, T> {
    if (val === undefined || val === null) {
      return { xs: fallback, sm: fallback, md: fallback, lg: fallback, xl: fallback, xxl: fallback };
    }
    if (typeof val !== 'object' || Array.isArray(val)) {
      return { xs: val as T, sm: val as T, md: val as T, lg: val as T, xl: val as T, xxl: val as T };
    }
    const obj = val as Record<string, T>;
    const xs = obj.xs !== undefined ? obj.xs : fallback;
    const sm = obj.sm !== undefined ? obj.sm : xs;
    const md = obj.md !== undefined ? obj.md : sm;
    const lg = obj.lg !== undefined ? obj.lg : md;
    const xl = obj.xl !== undefined ? obj.xl : lg;
    const xxl = obj.xxl !== undefined ? obj.xxl : xl;
    return { xs, sm, md, lg, xl, xxl };
  }

  /**
   * Compile UniversalLayoutIR to Ant Design React Grid JSX
   */
  public emitAntDesignGrid(layout: UniversalLayoutIR): LayoutCompileResult {
    const warnings: string[] = [];
    let itemsCount = 0;
    let containersCount = 0;
    let breakpointsApplied = 0;

    const emitContainer = (container: LayoutContainerIR, indent: string = '  '): string => {
      containersCount++;
      const lines: string[] = [];
      const gapVal = container.gap || container.colGap || 16;
      const gutterProp = typeof gapVal === 'number' ? `gutter={${gapVal}}` : `gutter={[16, 16]}`;

      const justifyProp = container.justify ? ` justify="${this.mapFlexJustifyToAntd(container.justify)}"` : '';
      const alignProp = container.align ? ` align="${this.mapFlexAlignToAntd(container.align)}"` : '';
      const wrapProp = container.wrap === 'nowrap' ? ` wrap={false}` : '';

      lines.push(`${indent}<Row ${gutterProp}${justifyProp}${alignProp}${wrapProp}>`);

      for (const item of container.children) {
        itemsCount++;
        const colProps = this.buildAntDColProps(item, layout.gridBaseSystem);
        if (colProps.hasBreakpoints) breakpointsApplied++;

        lines.push(`${indent}  <Col ${colProps.propsString}>`);
        if (item.nestedContainer) {
          lines.push(emitContainer(item.nestedContainer, `${indent}    `));
        } else if (item.contentCode) {
          lines.push(`${indent}    ${item.contentCode}`);
        } else if (item.componentTag) {
          lines.push(`${indent}    <${item.componentTag} />`);
        } else {
          lines.push(`${indent}    <div className="grid-cell-content">Cell Content</div>`);
        }
        lines.push(`${indent}  </Col>`);
      }

      lines.push(`${indent}</Row>`);
      return lines.join('\n');
    };

    const renderedTree = emitContainer(layout.rootContainer);
    const code = [
      `import React from 'react';`,
      `import { Row, Col } from 'antd';`,
      ``,
      `export const ${layout.documentName}Layout: React.FC = () => {`,
      `  return (`,
      `    <div className="layout-root">`,
      renderedTree,
      `    </div>`,
      `  );`,
      `};`,
    ].join('\n');

    return {
      targetFramework: 'ant-design-grid',
      code,
      warnings,
      metrics: {
        containersCount,
        itemsCount,
        responsiveBreakpointsApplied: breakpointsApplied,
      },
    };
  }

  /**
   * Compile UniversalLayoutIR to Element Plus Vue 3 SFC
   */
  public emitElementPlusGrid(layout: UniversalLayoutIR): LayoutCompileResult {
    const warnings: string[] = [];
    let itemsCount = 0;
    let containersCount = 0;
    let breakpointsApplied = 0;

    const emitContainer = (container: LayoutContainerIR, indent: string = '    '): string => {
      containersCount++;
      const lines: string[] = [];
      const gapVal = container.gap || container.colGap || 20;
      const gutterProp = typeof gapVal === 'number' ? `:gutter="${gapVal}"` : `:gutter="20"`;

      const justifyProp = container.justify ? ` justify="${this.mapFlexJustifyToElPlus(container.justify)}"` : '';
      const alignProp = container.align ? ` align="${this.mapFlexAlignToElPlus(container.align)}"` : '';

      lines.push(`${indent}<el-row ${gutterProp}${justifyProp}${alignProp}>`);

      for (const item of container.children) {
        itemsCount++;
        const colProps = this.buildElPlusColProps(item, layout.gridBaseSystem);
        if (colProps.hasBreakpoints) breakpointsApplied++;

        lines.push(`${indent}  <el-col ${colProps.propsString}>`);
        if (item.nestedContainer) {
          lines.push(emitContainer(item.nestedContainer, `${indent}    `));
        } else if (item.contentCode) {
          lines.push(`${indent}    ${item.contentCode}`);
        } else if (item.componentTag) {
          lines.push(`${indent}    <${item.componentTag} />`);
        } else {
          lines.push(`${indent}    <div class="grid-cell-content">Cell Content</div>`);
        }
        lines.push(`${indent}  </el-col>`);
      }

      lines.push(`${indent}</el-row>`);
      return lines.join('\n');
    };

    const renderedTree = emitContainer(layout.rootContainer);
    const code = [
      `<template>`,
      `  <div class="layout-root">`,
      renderedTree,
      `  </div>`,
      `</template>`,
      ``,
      `<script setup lang="ts">`,
      `import { ElRow, ElCol } from 'element-plus';`,
      `</script>`,
      ``,
      `<style scoped>`,
      `.layout-root {`,
      `  width: 100%;`,
      `  box-sizing: border-box;`,
      `}`,
      `</style>`,
    ].join('\n');

    return {
      targetFramework: 'element-plus-grid',
      code,
      warnings,
      metrics: {
        containersCount,
        itemsCount,
        responsiveBreakpointsApplied: breakpointsApplied,
      },
    };
  }

  /**
   * Compile UniversalLayoutIR to pure CSS Grid with responsive media queries
   */
  public emitPureCSSGrid(layout: UniversalLayoutIR): LayoutCompileResult {
    const warnings: string[] = [];
    let itemsCount = 0;
    let containersCount = 0;
    let breakpointsApplied = 0;

    const cssRules: string[] = [];
    const mediaQueries: string[] = [];

    const rootClass = `cssgrid-${layout.documentName.toLowerCase()}`;
    const baseCols = layout.gridBaseSystem;

    cssRules.push(`.${rootClass} {`);
    cssRules.push(`  display: grid;`);
    cssRules.push(`  grid-template-columns: repeat(${baseCols}, 1fr);`);
    cssRules.push(`  gap: 16px;`);
    cssRules.push(`  width: 100%;`);
    cssRules.push(`  box-sizing: border-box;`);
    cssRules.push(`}`);

    const htmlElements: string[] = [];

    layout.rootContainer.children.forEach((item, index) => {
      itemsCount++;
      const itemClass = `${rootClass}-item-${index + 1}`;
      const spanObj = GridFlexAdapter.normalizeResponsive(item.span, baseCols);

      cssRules.push(`.${itemClass} {`);
      cssRules.push(`  grid-column: span ${spanObj.xs};`);
      cssRules.push(`}`);

      // Media queries for sm, md, lg, xl, xxl
      const keys: ResponsiveBreakpointKey[] = ['sm', 'md', 'lg', 'xl', 'xxl'];
      for (const k of keys) {
        if (spanObj[k] !== spanObj.xs) {
          breakpointsApplied++;
          const minW = DEFAULT_BREAKPOINT_TIERS[k].minWidth;
          mediaQueries.push(`@media (min-width: ${minW}px) {\n  .${itemClass} {\n    grid-column: span ${spanObj[k]};\n  }\n}`);
        }
      }

      htmlElements.push(`  <div class="${itemClass}">`);
      if (item.contentCode) {
        htmlElements.push(`    ${item.contentCode}`);
      } else {
        htmlElements.push(`    <span>Item ${index + 1}</span>`);
      }
      htmlElements.push(`  </div>`);
    });

    containersCount++;

    const htmlCode = [
      `<div class="${rootClass}">`,
      ...htmlElements,
      `</div>`,
    ].join('\n');

    const styleCode = [
      ...cssRules,
      '',
      ...mediaQueries,
    ].join('\n');

    return {
      targetFramework: 'css-grid',
      code: htmlCode,
      styleCode,
      mediaQueriesCss: mediaQueries.join('\n\n'),
      warnings,
      metrics: {
        containersCount,
        itemsCount,
        responsiveBreakpointsApplied: breakpointsApplied,
      },
    };
  }

  /**
   * Compile UniversalLayoutIR to WeChat MiniApp WXML + WXSS Flexbox Layout
   */
  public emitMiniAppFlex(layout: UniversalLayoutIR): LayoutCompileResult {
    const warnings: string[] = [];
    let itemsCount = 0;
    let containersCount = 0;
    let breakpointsApplied = 0;

    const baseCols = layout.gridBaseSystem;
    const wxmlLines: string[] = [];
    const wxssLines: string[] = [];

    const rootClass = `miniapp-layout-${layout.documentName.toLowerCase()}`;

    wxssLines.push(`.${rootClass} {`);
    wxssLines.push(`  display: flex;`);
    wxssLines.push(`  flex-wrap: wrap;`);
    wxssLines.push(`  box-sizing: border-box;`);
    wxssLines.push(`  width: 750rpx;`);
    wxssLines.push(`  padding: 16rpx;`);
    wxssLines.push(`}`);

    wxmlLines.push(`<view class="${rootClass}">`);

    layout.rootContainer.children.forEach((item, index) => {
      itemsCount++;
      const cellClass = `${rootClass}-cell-${index + 1}`;
      const spanObj = GridFlexAdapter.normalizeResponsive(item.span, baseCols);

      // In MiniApp default viewport (phone screen / xs tier)
      const xsSpan = spanObj.xs || baseCols;
      const widthPct = Math.min(100, Math.round((xsSpan / baseCols) * 10000) / 100);

      wxssLines.push(`.${cellClass} {`);
      wxssLines.push(`  width: ${widthPct}%;`);
      wxssLines.push(`  box-sizing: border-box;`);
      wxssLines.push(`  padding: 8rpx;`);
      wxssLines.push(`}`);

      wxmlLines.push(`  <view class="${cellClass}">`);
      if (item.contentCode) {
        wxmlLines.push(`    ${item.contentCode}`);
      } else {
        wxmlLines.push(`    <text>Cell ${index + 1}</text>`);
      }
      wxmlLines.push(`  </view>`);
    });

    wxmlLines.push(`</view>`);
    containersCount++;

    return {
      targetFramework: 'miniapp-flex',
      code: wxmlLines.join('\n'),
      styleCode: wxssLines.join('\n'),
      warnings,
      metrics: {
        containersCount,
        itemsCount,
        responsiveBreakpointsApplied: breakpointsApplied,
      },
    };
  }

  /**
   * Compile UniversalLayoutIR to HarmonyOS ArkUI Flex / Column / Row
   */
  public emitArkUILayout(layout: UniversalLayoutIR): LayoutCompileResult {
    const warnings: string[] = [];
    let itemsCount = 0;
    let containersCount = 0;
    let breakpointsApplied = 0;

    const arkLines: string[] = [];
    arkLines.push(`@Component`);
    arkLines.push(`export struct ${layout.documentName}LayoutView {`);
    arkLines.push(`  build() {`);
    arkLines.push(`    Flex({ wrap: FlexWrap.Wrap, justifyContent: FlexAlign.SpaceBetween }) {`);

    containersCount++;

    const baseCols = layout.gridBaseSystem;

    layout.rootContainer.children.forEach((item, index) => {
      itemsCount++;
      const spanObj = GridFlexAdapter.normalizeResponsive(item.span, baseCols);
      const pct = Math.min(100, Math.round(((spanObj.xs || baseCols) / baseCols) * 100));

      arkLines.push(`      Column() {`);
      if (item.contentCode) {
        arkLines.push(`        ${item.contentCode}`);
      } else {
        arkLines.push(`        Text('Item ${index + 1}')`);
        arkLines.push(`          .fontSize(14)`);
        arkLines.push(`          .fontColor(Color.Black)`);
      }
      arkLines.push(`      }`);
      arkLines.push(`      .width('${pct}%')`);
      arkLines.push(`      .padding(8)`);
    });

    arkLines.push(`    }`);
    arkLines.push(`    .width('100%')`);
    arkLines.push(`  }`);
    arkLines.push(`}`);

    return {
      targetFramework: 'arkui-layout',
      code: arkLines.join('\n'),
      warnings,
      metrics: {
        containersCount,
        itemsCount,
        responsiveBreakpointsApplied: breakpointsApplied,
      },
    };
  }

  /**
   * Helper: Build Ant Design Col props string from LayoutItemIR
   */
  private buildAntDColProps(item: LayoutItemIR, baseSystem: number): { propsString: string; hasBreakpoints: boolean } {
    if (typeof item.span === 'number') {
      const scaled = this.scaleSpan(item.span, baseSystem, 24);
      return { propsString: `span={${scaled}}`, hasBreakpoints: false };
    }
    if (typeof item.span === 'object' && item.span !== null) {
      const parts: string[] = [];
      const keys: ResponsiveBreakpointKey[] = ['xs', 'sm', 'md', 'lg', 'xl', 'xxl'];
      for (const k of keys) {
        const val = (item.span as any)[k];
        if (val !== undefined) {
          const scaled = this.scaleSpan(val, baseSystem, 24);
          parts.push(`${k}={${scaled}}`);
        }
      }
      return { propsString: parts.join(' '), hasBreakpoints: parts.length > 1 };
    }
    return { propsString: `span={24}`, hasBreakpoints: false };
  }

  /**
   * Helper: Build Element Plus Col props string from LayoutItemIR
   */
  private buildElPlusColProps(item: LayoutItemIR, baseSystem: number): { propsString: string; hasBreakpoints: boolean } {
    if (typeof item.span === 'number') {
      const scaled = this.scaleSpan(item.span, baseSystem, 24);
      return { propsString: `:span="${scaled}"`, hasBreakpoints: false };
    }
    if (typeof item.span === 'object' && item.span !== null) {
      const parts: string[] = [];
      const keys: ResponsiveBreakpointKey[] = ['xs', 'sm', 'md', 'lg', 'xl', 'xxl'];
      for (const k of keys) {
        const val = (item.span as any)[k];
        if (val !== undefined) {
          const scaled = this.scaleSpan(val, baseSystem, 24);
          parts.push(`:${k}="${scaled}"`);
        }
      }
      return { propsString: parts.join(' '), hasBreakpoints: parts.length > 1 };
    }
    return { propsString: `:span="24"`, hasBreakpoints: false };
  }

  private scaleSpan(span: number, fromBase: number, toBase: number): number {
    if (fromBase === toBase) return span;
    return Math.max(1, Math.min(toBase, Math.round((span / fromBase) * toBase)));
  }

  private mapFlexJustifyToAntd(val: ResponsiveValue<JustifyContent>): string {
    const raw = typeof val === 'object' ? (val as any).xs || 'start' : val;
    switch (raw) {
      case 'flex-start': return 'start';
      case 'flex-end': return 'end';
      case 'center': return 'center';
      case 'space-between': return 'space-between';
      case 'space-around': return 'space-around';
      case 'space-evenly': return 'space-evenly';
      default: return 'start';
    }
  }

  private mapFlexAlignToAntd(val: ResponsiveValue<AlignItems>): string {
    const raw = typeof val === 'object' ? (val as any).xs || 'top' : val;
    switch (raw) {
      case 'flex-start': return 'top';
      case 'flex-end': return 'bottom';
      case 'center': return 'middle';
      case 'stretch': return 'stretch';
      default: return 'top';
    }
  }

  private mapFlexJustifyToElPlus(val: ResponsiveValue<JustifyContent>): string {
    const raw = typeof val === 'object' ? (val as any).xs || 'start' : val;
    switch (raw) {
      case 'flex-start': return 'start';
      case 'flex-end': return 'end';
      case 'center': return 'center';
      case 'space-between': return 'space-between';
      case 'space-around': return 'space-around';
      case 'space-evenly': return 'space-evenly';
      default: return 'start';
    }
  }

  private mapFlexAlignToElPlus(val: ResponsiveValue<AlignItems>): string {
    const raw = typeof val === 'object' ? (val as any).xs || 'top' : val;
    switch (raw) {
      case 'flex-start': return 'top';
      case 'flex-end': return 'bottom';
      case 'center': return 'middle';
      default: return 'top';
    }
  }
}

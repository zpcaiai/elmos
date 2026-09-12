/**
 * @file layout-ir-types.ts
 * @description Universal Layout IR (Intermediate Representation) types for cross-platform
 * responsive layout systems, grid-to-flex compilation, container query synthesis,
 * fluid typography/spacing, and multi-screen viewport adaptation.
 * Conforms to Batch 32 Skill 1218 (b32-desktop-web-crossplatform) & Skill 1208.
 */

/**
 * Supported responsive breakpoint tiers conforming to enterprise design systems
 * (Ant Design, Element Plus, Bootstrap, Tailwind, Material Design).
 */
export type ResponsiveBreakpointKey = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl';

export interface BreakpointRange {
  key: ResponsiveBreakpointKey;
  minWidth: number; // in px
  maxWidth?: number; // in px
  columnCount: number; // default column count for this breakpoint tier
  gutter: number; // in px
  containerPadding: number; // in px
}

export const DEFAULT_BREAKPOINT_TIERS: Record<ResponsiveBreakpointKey, BreakpointRange> = {
  xs: { key: 'xs', minWidth: 0, maxWidth: 575, columnCount: 4, gutter: 8, containerPadding: 16 },
  sm: { key: 'sm', minWidth: 576, maxWidth: 767, columnCount: 8, gutter: 12, containerPadding: 24 },
  md: { key: 'md', minWidth: 768, maxWidth: 991, columnCount: 12, gutter: 16, containerPadding: 32 },
  lg: { key: 'lg', minWidth: 992, maxWidth: 1199, columnCount: 12, gutter: 20, containerPadding: 32 },
  xl: { key: 'xl', minWidth: 1200, maxWidth: 1599, columnCount: 12, gutter: 24, containerPadding: 40 },
  xxl: { key: 'xxl', minWidth: 1600, columnCount: 12, gutter: 32, containerPadding: 48 },
};

/**
 * Target layout paradigms
 */
export type LayoutFrameworkId =
  | 'css-grid'
  | 'css-flexbox'
  | 'tailwind'
  | 'ant-design-grid'
  | 'element-plus-grid'
  | 'miniapp-flex'
  | 'arkui-layout'
  | 'flutter-layout';

/**
 * Alignment properties
 */
export type FlexDirection = 'row' | 'row-reverse' | 'column' | 'column-reverse';
export type FlexWrap = 'nowrap' | 'wrap' | 'wrap-reverse';
export type JustifyContent =
  | 'flex-start'
  | 'flex-end'
  | 'center'
  | 'space-between'
  | 'space-around'
  | 'space-evenly'
  | 'stretch';
export type AlignItems = 'flex-start' | 'flex-end' | 'center' | 'baseline' | 'stretch';
export type AlignContent =
  | 'flex-start'
  | 'flex-end'
  | 'center'
  | 'space-between'
  | 'space-around'
  | 'stretch';

/**
 * Grid track sizing
 */
export interface GridTrackSize {
  unit: 'fr' | 'px' | '%' | 'em' | 'rem' | 'auto' | 'min-content' | 'max-content' | 'fit-content' | 'minmax';
  value?: number;
  minVal?: { unit: string; value: number };
  maxVal?: { unit: string; value: number | 'auto' };
  raw?: string;
}

/**
 * Responsive value mapping across breakpoints
 */
export type ResponsiveValue<T> = T | {
  xs?: T;
  sm?: T;
  md?: T;
  lg?: T;
  xl?: T;
  xxl?: T;
};

/**
 * Universal layout container specifications
 */
export interface LayoutContainerIR {
  id: string;
  kind: 'container' | 'row' | 'grid' | 'stack' | 'flow' | 'split-pane';
  display: 'flex' | 'grid' | 'block' | 'inline-flex' | 'inline-grid';
  // Flexbox configurations
  direction?: ResponsiveValue<FlexDirection>;
  wrap?: ResponsiveValue<FlexWrap>;
  justify?: ResponsiveValue<JustifyContent>;
  align?: ResponsiveValue<AlignItems>;
  alignContent?: ResponsiveValue<AlignContent>;
  // Grid configurations
  columns?: ResponsiveValue<number | string | GridTrackSize[]>;
  rows?: ResponsiveValue<number | string | GridTrackSize[]>;
  autoFlow?: ResponsiveValue<'row' | 'column' | 'dense' | 'row dense' | 'column dense'>;
  // Spacing & Gutter
  gap?: ResponsiveValue<number | string>;
  rowGap?: ResponsiveValue<number | string>;
  colGap?: ResponsiveValue<number | string>;
  padding?: ResponsiveValue<string | number>;
  margin?: ResponsiveValue<string | number>;
  // Container Query rules
  containerQueryName?: string;
  containerType?: 'inline-size' | 'size' | 'normal';
  // Dimensions & Limits
  maxWidth?: ResponsiveValue<number | string>;
  minWidth?: ResponsiveValue<number | string>;
  width?: ResponsiveValue<number | string>;
  height?: ResponsiveValue<number | string>;
  // Nested Children
  children: LayoutItemIR[];
  // CSS class or style pass-through
  className?: string;
  customStyle?: Record<string, string | number>;
}

/**
 * Individual layout child / column specification
 */
export interface LayoutItemIR {
  id: string;
  kind: 'col' | 'grid-cell' | 'flex-item' | 'nested-container';
  // Column grid span (e.g. out of 12 or 24 columns)
  span?: ResponsiveValue<number>;
  offset?: ResponsiveValue<number>;
  order?: ResponsiveValue<number>;
  push?: ResponsiveValue<number>;
  pull?: ResponsiveValue<number>;
  // Flex child properties
  flexGrow?: ResponsiveValue<number>;
  flexShrink?: ResponsiveValue<number>;
  flexBasis?: ResponsiveValue<string | number>;
  alignSelf?: ResponsiveValue<AlignItems | 'auto'>;
  // Grid item placement
  gridColumn?: ResponsiveValue<string>;
  gridRow?: ResponsiveValue<string>;
  gridArea?: string;
  // Container Query conditional modifiers
  containerConditions?: Array<{
    minWidth?: number;
    maxWidth?: number;
    styleOverrides: Record<string, string | number>;
  }>;
  // Inner nested container or component placeholder
  nestedContainer?: LayoutContainerIR;
  componentTag?: string;
  contentCode?: string;
}

/**
 * Overall page/view responsive layout document IR
 */
export interface UniversalLayoutIR {
  version: '1.0';
  documentName: string;
  gridBaseSystem: 12 | 24;
  breakpointConfig: Record<ResponsiveBreakpointKey, BreakpointRange>;
  rootContainer: LayoutContainerIR;
  fluidTypography?: {
    minViewport: number;
    maxViewport: number;
    minFontSize: number;
    maxFontSize: number;
  };
  globalCssTokens?: Record<string, string>;
}

/**
 * Conversion results
 */
export interface LayoutCompileResult {
  targetFramework: LayoutFrameworkId;
  code: string;
  styleCode?: string;
  mediaQueriesCss?: string;
  warnings: string[];
  metrics: {
    containersCount: number;
    itemsCount: number;
    responsiveBreakpointsApplied: number;
  };
}

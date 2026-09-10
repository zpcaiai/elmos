/**
 * @file theme-ir-types.ts
 * @description Universal Design Token & Theme IR Contracts based on W3C DTCG Specification.
 * Models hierarchical design tokens (colors, typography, spacing, elevations, animations),
 * multi-theme sets (light, dark, high-contrast), and cross-platform token emitters.
 * Conforms to Batch 32 Skill 1204 (b32-design-token-theme-extraction).
 */

export type DesignTokenType =
  | 'color'
  | 'dimension'
  | 'fontFamily'
  | 'fontWeight'
  | 'duration'
  | 'cubicBezier'
  | 'number'
  | 'shadow'
  | 'border'
  | 'typography';

export type TargetTokenFormat =
  | 'css-variables'
  | 'tailwind-theme'
  | 'miniapp-wxss'
  | 'arkui-resources'
  | 'dtcg-json';

export interface ShadowValue {
  color: string;
  offsetX: string;
  offsetY: string;
  blur: string;
  spread: string;
}

export interface BorderValue {
  color: string;
  width: string;
  style: 'solid' | 'dashed' | 'dotted' | 'none';
}

export interface TypographyValue {
  fontFamily: string;
  fontSize: string;
  fontWeight: string | number;
  lineHeight: string;
  letterSpacing?: string;
}

export interface DesignTokenIR {
  name: string;
  path: string[];             // e.g. ['color', 'brand', 'primary']
  value: string | number | ShadowValue | BorderValue | TypographyValue;
  type: DesignTokenType;
  description?: string;
  isAlias?: boolean;
  aliasTarget?: string;       // e.g. "{color.palette.blue.600}"
}

export interface ResponsiveBreakpointIR {
  name: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | string;
  minWidth: number;           // in pixels
}

export interface ThemeVariantIR {
  variantId: 'light' | 'dark' | 'high-contrast' | string;
  tokenOverrides: Record<string, string | number>;
}

export interface UniversalThemeIR {
  themeId: string;
  themeName: string;
  tokens: DesignTokenIR[];
  variants: ThemeVariantIR[];
  breakpoints: ResponsiveBreakpointIR[];
  version: string;
  metadata?: Record<string, unknown>;
}

export interface TokenExtractionResult {
  themeIR: UniversalThemeIR;
  tokenCount: number;
  unresolvedAliases: string[];
  warnings: string[];
}

export interface TokenEmitResult {
  code: string;
  fileName: string;
  format: TargetTokenFormat;
  notes: string[];
}

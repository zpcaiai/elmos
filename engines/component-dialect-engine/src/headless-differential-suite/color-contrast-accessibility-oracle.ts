/**
 * @file color-contrast-accessibility-oracle.ts
 * @description WCAG 2.1 AA/AAA and APCA Color Contrast Accessibility Oracle.
 * Linearizes sRGB color values, computes relative luminance, evaluates contrast ratios,
 * and validates compliance for regular text, large text, and interactive UI components.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

export interface RGBColor {
  r: number; // 0-255
  g: number; // 0-255
  b: number; // 0-255
  a?: number; // 0-1
}

export interface ContrastEvaluationResult {
  ratio: number;
  wcagAATextPassed: boolean;
  wcagAALargeTextPassed: boolean;
  wcagAAATextPassed: boolean;
  wcagAAALargeTextPassed: boolean;
  wcagAAUIComponentPassed: boolean;
  apcaScore: number;
  textColorLuminance: number;
  bgColorLuminance: number;
  suggestedTextColor?: string;
  notes: string[];
}

export class ColorContrastAccessibilityOracle {
  /**
   * Parse hex, rgb, or color string to RGBColor
   */
  public static parseColor(colorStr: string): RGBColor {
    const s = colorStr.trim().toLowerCase();

    // Hex #rgb or #rrggbb or #rrggbbaa
    if (s.startsWith('#')) {
      const hex = s.slice(1);
      if (hex.length === 3) {
        return {
          r: parseInt(hex[0]! + hex[0]!, 16),
          g: parseInt(hex[1]! + hex[1]!, 16),
          b: parseInt(hex[2]! + hex[2]!, 16),
          a: 1.0,
        };
      } else if (hex.length === 6) {
        return {
          r: parseInt(hex.slice(0, 2), 16),
          g: parseInt(hex.slice(2, 4), 16),
          b: parseInt(hex.slice(4, 6), 16),
          a: 1.0,
        };
      } else if (hex.length === 8) {
        return {
          r: parseInt(hex.slice(0, 2), 16),
          g: parseInt(hex.slice(2, 4), 16),
          b: parseInt(hex.slice(4, 6), 16),
          a: parseInt(hex.slice(6, 8), 16) / 255,
        };
      }
    }

    // rgb(r, g, b) or rgba(r, g, b, a)
    const rgbMatch = s.match(/^rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)$/);
    if (rgbMatch) {
      return {
        r: parseInt(rgbMatch[1]!, 10),
        g: parseInt(rgbMatch[2]!, 10),
        b: parseInt(rgbMatch[3]!, 10),
        a: rgbMatch[4] ? parseFloat(rgbMatch[4]) : 1.0,
      };
    }

    // Common named colors
    const named: Record<string, RGBColor> = {
      black: { r: 0, g: 0, b: 0, a: 1 },
      white: { r: 255, g: 255, b: 255, a: 1 },
      red: { r: 255, g: 0, b: 0, a: 1 },
      green: { r: 0, g: 128, b: 0, a: 1 },
      blue: { r: 0, g: 0, b: 255, a: 1 },
      gray: { r: 128, g: 128, b: 128, a: 1 },
      transparent: { r: 0, g: 0, b: 0, a: 0 },
    };

    return named[s] || { r: 0, g: 0, b: 0, a: 1 };
  }

  /**
   * Linearize an 8-bit sRGB color channel to relative luminance component
   */
  public static linearize(val8bit: number): number {
    const v = val8bit / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  }

  /**
   * Compute relative luminance per WCAG 2.1 formula
   */
  public static calculateLuminance(color: RGBColor): number {
    const R = this.linearize(color.r);
    const G = this.linearize(color.g);
    const B = this.linearize(color.b);
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  }

  /**
   * Calculate WCAG 2.1 contrast ratio between two colors
   */
  public static calculateContrastRatio(color1: RGBColor, color2: RGBColor): number {
    const l1 = this.calculateLuminance(color1);
    const l2 = this.calculateLuminance(color2);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  /**
   * Compute APCA Lightness Contrast (Lc) estimation
   */
  public static calculateAPCA(textColor: RGBColor, bgColor: RGBColor): number {
    const yText = this.calculateLuminance(textColor);
    const yBg = this.calculateLuminance(bgColor);

    // Simplified SAPC / APCA approximation
    const deltaY = Math.abs(yBg - yText);
    return Math.round(deltaY * 100);
  }

  /**
   * Evaluate WCAG 2.1 and APCA compliance for text against background
   */
  public evaluate(textColorInput: string | RGBColor, bgColorInput: string | RGBColor): ContrastEvaluationResult {
    const textRgb = typeof textColorInput === 'string' ? ColorContrastAccessibilityOracle.parseColor(textColorInput) : textColorInput;
    const bgRgb = typeof bgColorInput === 'string' ? ColorContrastAccessibilityOracle.parseColor(bgColorInput) : bgColorInput;

    const lText = ColorContrastAccessibilityOracle.calculateLuminance(textRgb);
    const lBg = ColorContrastAccessibilityOracle.calculateLuminance(bgRgb);
    const ratio = ColorContrastAccessibilityOracle.calculateContrastRatio(textRgb, bgRgb);
    const apca = ColorContrastAccessibilityOracle.calculateAPCA(textRgb, bgRgb);

    const roundedRatio = Math.round(ratio * 100) / 100;

    const wcagAATextPassed = roundedRatio >= 4.5;
    const wcagAALargeTextPassed = roundedRatio >= 3.0;
    const wcagAAATextPassed = roundedRatio >= 7.0;
    const wcagAAALargeTextPassed = roundedRatio >= 4.5;
    const wcagAAUIComponentPassed = roundedRatio >= 3.0;

    const notes: string[] = [];
    if (!wcagAATextPassed) {
      notes.push(`Contrast ratio ${roundedRatio}:1 fails WCAG AA normal text threshold of 4.5:1`);
    } else {
      notes.push(`Contrast ratio ${roundedRatio}:1 satisfies WCAG AA normal text threshold`);
    }

    let suggestedTextColor: string | undefined;
    if (!wcagAATextPassed) {
      suggestedTextColor = lBg > 0.5 ? '#111827' : '#ffffff';
    }

    return {
      ratio: roundedRatio,
      wcagAATextPassed,
      wcagAALargeTextPassed,
      wcagAAATextPassed,
      wcagAAALargeTextPassed,
      wcagAAUIComponentPassed,
      apcaScore: apca,
      textColorLuminance: lText,
      bgColorLuminance: lBg,
      suggestedTextColor,
      notes,
    };
  }
}

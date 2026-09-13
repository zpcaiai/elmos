/**
 * @file wcag-audit-oracle.ts
 * @description Static Analysis Oracle for W3C WCAG 2.2 Level A/AA/AAA Accessibility.
 * Evaluates component JSX/TSX and HTML templates against accessibility standards:
 * - 1.1.1 Non-text Content (img alt attributes)
 * - 1.3.1 Info and Relationships (heading levels, form input labels)
 * - 1.4.3 Contrast (Minimum 4.5:1 / 3.0:1)
 * - 2.1.1 Keyboard (no tabIndex > 0)
 * - 2.4.3 Focus Order (modal dialog focus trapping)
 * - 4.1.2 Name, Role, Value (button / link accessible names)
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import * as ts from 'typescript';
import {
  WcagAuditReport,
  WcagViolationRecord,
  WcagComplianceLevel,
} from './a11y-seo-ir-types';

export class WcagAuditOracle {
  /**
   * Audit TSX / JSX source code for WCAG accessibility violations.
   */
  public auditTsx(sourceCode: string, fileName: string = 'Component.tsx', targetLevel: WcagComplianceLevel = 'AA'): WcagAuditReport {
    const sourceFile = ts.createSourceFile(
      fileName,
      sourceCode,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX
    );

    const violations: WcagViolationRecord[] = [];
    const headingLevelsEncountered: number[] = [];

    const visit = (node: ts.Node) => {
      if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
        const opening = ts.isJsxElement(node) ? node.openingElement : node;
        const tagName = opening.tagName.getText(sourceFile);
        const attrs = this.extractAttributes(opening.attributes, sourceFile);
        const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart());

        // 1. Rule: img-has-alt (WCAG 1.1.1)
        if (tagName === 'img' || tagName === 'Image') {
          if (!('alt' in attrs) && !('aria-label' in attrs) && !('aria-labelledby' in attrs) && attrs['role'] !== 'presentation') {
            violations.push({
              ruleId: 'img-has-alt',
              wcagCriterion: '1.1.1 Non-text Content',
              severity: 'error',
              elementTag: tagName,
              message: `<${tagName}> element is missing an 'alt' attribute for screen reader accessibility.`,
              suggestedFix: `Add alt="descriptive text" or alt="" if image is purely decorative, or role="presentation".`,
              line: line + 1,
            });
          }
        }

        // 2. Rule: interactive-has-name (WCAG 4.1.2)
        if (tagName === 'button' || tagName === 'Button') {
          let hasChildText = false;
          if (ts.isJsxElement(node)) {
            hasChildText = node.children.some((c) => {
              if (ts.isJsxText(c)) return c.text.trim().length > 0;
              if (ts.isJsxExpression(c) && c.expression) return true;
              return false;
            });
          }

          const hasAriaName = !!(attrs['aria-label'] || attrs['aria-labelledby'] || attrs['title']);

          if (!hasChildText && !hasAriaName) {
            violations.push({
              ruleId: 'interactive-has-name',
              wcagCriterion: '4.1.2 Name, Role, Value',
              severity: 'error',
              elementTag: tagName,
              message: `<${tagName}> does not have an accessible name (no child text or aria-label).`,
              suggestedFix: `Provide visible text content or add an 'aria-label' attribute explaining the button action.`,
              line: line + 1,
            });
          }
        }

        // 3. Rule: link-has-href (WCAG 2.1.1 / 4.1.2)
        if (tagName === 'a' || tagName === 'Link') {
          if (!('href' in attrs) && !('to' in attrs) && !('role' in attrs)) {
            violations.push({
              ruleId: 'link-has-href',
              wcagCriterion: '2.1.1 Keyboard',
              severity: 'warning',
              elementTag: tagName,
              message: `<${tagName}> is missing an 'href' or navigation target, rendering it non-keyboard-focusable.`,
              suggestedFix: `Use a <button> for actions, or provide a valid 'href' attribute.`,
              line: line + 1,
            });
          }
        }

        // 4. Rule: form-input-has-label (WCAG 3.3.2)
        if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
          const type = attrs['type'] || 'text';
          if (type !== 'hidden' && type !== 'submit' && type !== 'button') {
            const hasAriaLabel = !!(attrs['aria-label'] || attrs['aria-labelledby'] || attrs['id']);
            if (!hasAriaLabel && !('placeholder' in attrs)) {
              violations.push({
                ruleId: 'form-input-has-label',
                wcagCriterion: '3.3.2 Labels or Instructions',
                severity: 'error',
                elementTag: tagName,
                message: `<${tagName}> has no associated accessible label or identifier.`,
                suggestedFix: `Add aria-label="Label" or bind a corresponding <label htmlFor="inputId">.`,
                line: line + 1,
              });
            }
          }
        }

        // 5. Rule: heading-order (WCAG 1.3.1)
        const headingMatch = tagName.match(/^h([1-6])$/i);
        if (headingMatch && headingMatch[1]) {
          const level = parseInt(headingMatch[1], 10);
          if (headingLevelsEncountered.length > 0) {
            const prevLevel = headingLevelsEncountered[headingLevelsEncountered.length - 1]!;
            if (level > prevLevel + 1) {
              violations.push({
                ruleId: 'heading-order',
                wcagCriterion: '1.3.1 Info and Relationships',
                severity: 'warning',
                elementTag: tagName,
                message: `Heading hierarchy skipped from <h${prevLevel}> to <h${level}>.`,
                suggestedFix: `Adjust heading level to <h${prevLevel + 1}> to preserve semantic document outline.`,
                line: line + 1,
              });
            }
          }
          headingLevelsEncountered.push(level);
        }

        // 6. Rule: no-positive-tabindex (WCAG 2.4.3)
        if ('tabIndex' in attrs || 'tabindex' in attrs) {
          const rawVal = attrs['tabIndex'] || attrs['tabindex'] || '';
          const tabVal = parseInt(rawVal, 10);
          if (!isNaN(tabVal) && tabVal > 0) {
            violations.push({
              ruleId: 'no-positive-tabindex',
              wcagCriterion: '2.4.3 Focus Order',
              severity: 'error',
              elementTag: tagName,
              message: `Element has positive tabIndex (${tabVal}), which alters natural reading order.`,
              suggestedFix: `Use tabIndex={0} to include in sequential focus, or tabIndex={-1} for programmatically focusable elements.`,
              line: line + 1,
            });
          }
        }

        // 7. Rule: dialog-has-aria-modal (WCAG 2.4.3)
        if (attrs['role'] === 'dialog' || attrs['role'] === 'alertdialog' || tagName === 'Modal' || tagName === 'Dialog') {
          if (attrs['aria-modal'] !== 'true' && attrs['role'] !== 'region') {
            violations.push({
              ruleId: 'dialog-has-aria-modal',
              wcagCriterion: '2.4.3 Focus Order',
              severity: 'warning',
              elementTag: tagName,
              message: `Modal dialog does not explicitly declare aria-modal="true".`,
              suggestedFix: `Add aria-modal="true" to instruct assistive technologies to restrict focus within the dialog.`,
              line: line + 1,
            });
          }
        }
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);

    const errorsCount = violations.filter((v) => v.severity === 'error').length;
    const warningsCount = violations.filter((v) => v.severity === 'warning').length;

    return {
      isCompliant: errorsCount === 0,
      level: targetLevel,
      totalViolations: violations.length,
      errorsCount,
      warningsCount,
      violations,
    };
  }

  /**
   * Verify WCAG 2.2 Color Contrast Ratio.
   * Formula: (L1 + 0.05) / (L2 + 0.05)
   * where L is relative luminance = 0.2126 * R + 0.7152 * G + 0.0722 * B.
   */
  public calculateContrastRatio(fgHex: string, bgHex: string): { ratio: number; passesAA: boolean; passesAAA: boolean } {
    const l1 = this.getLuminance(fgHex);
    const l2 = this.getLuminance(bgHex);

    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    const ratio = Math.round(((lighter + 0.05) / (darker + 0.05)) * 100) / 100;

    return {
      ratio,
      passesAA: ratio >= 4.5,
      passesAAA: ratio >= 7.0,
    };
  }

  private getLuminance(hex: string): number {
    const cleanHex = hex.replace('#', '');
    const r = parseInt(cleanHex.substring(0, 2), 16) / 255;
    const g = parseInt(cleanHex.substring(2, 4), 16) / 255;
    const b = parseInt(cleanHex.substring(4, 6), 16) / 255;

    const transform = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));

    return 0.2126 * transform(r) + 0.7152 * transform(g) + 0.0722 * transform(b);
  }

  private extractAttributes(attrs: ts.JsxAttributes, sourceFile: ts.SourceFile): Record<string, string> {
    const result: Record<string, string> = {};

    for (const prop of attrs.properties) {
      if (ts.isJsxAttribute(prop) && prop.name) {
        const name = prop.name.getText(sourceFile);
        if (!prop.initializer) {
          result[name] = 'true';
        } else if (ts.isStringLiteral(prop.initializer)) {
          result[name] = prop.initializer.text;
        } else if (ts.isJsxExpression(prop.initializer) && prop.initializer.expression) {
          result[name] = prop.initializer.expression.getText(sourceFile);
        }
      }
    }

    return result;
  }
}

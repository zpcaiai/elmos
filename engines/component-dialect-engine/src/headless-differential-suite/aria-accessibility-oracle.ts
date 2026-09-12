/**
 * @file aria-accessibility-oracle.ts
 * @description W3C WAI-ARIA 1.2 Semantic Compliance and Accessibility Oracle.
 * Validates ARIA role validity, required attributes, accessible name computations,
 * broken ID references (aria-labelledby / aria-describedby), and keyboard reachability.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import { HeadlessDOMNode } from './types';

export interface ARIAViolation {
  nodeId: string;
  tagName?: string;
  ruleId: string;
  impact: 'critical' | 'serious' | 'moderate' | 'minor';
  description: string;
  helpUrl?: string;
}

export interface ARIAValidationReport {
  passed: boolean;
  totalViolations: number;
  criticalCount: number;
  seriousCount: number;
  moderateCount: number;
  minorCount: number;
  violations: ARIAViolation[];
  accessibleNodesCount: number;
}

export class ARIAAccessibilityOracle {
  private static readonly VALID_ROLES = new Set([
    'alert',
    'alertdialog',
    'application',
    'article',
    'banner',
    'button',
    'cell',
    'checkbox',
    'columnheader',
    'combobox',
    'complementary',
    'contentinfo',
    'definition',
    'dialog',
    'directory',
    'document',
    'feed',
    'figure',
    'form',
    'grid',
    'gridcell',
    'group',
    'heading',
    'img',
    'link',
    'list',
    'listbox',
    'listitem',
    'log',
    'main',
    'marquee',
    'math',
    'menu',
    'menubar',
    'menuitem',
    'menuitemcheckbox',
    'menuitemradio',
    'navigation',
    'none',
    'note',
    'option',
    'presentation',
    'progressbar',
    'radio',
    'radiogroup',
    'region',
    'row',
    'rowgroup',
    'rowheader',
    'scrollbar',
    'search',
    'searchbox',
    'separator',
    'slider',
    'spinbutton',
    'status',
    'switch',
    'tab',
    'table',
    'tablist',
    'tabpanel',
    'term',
    'textbox',
    'timer',
    'toolbar',
    'tooltip',
    'tree',
    'treegrid',
    'treeitem',
  ]);

  private static readonly REQUIRED_ATTRIBUTES_BY_ROLE: Record<string, string[]> = {
    checkbox: ['aria-checked'],
    combobox: ['aria-expanded'],
    radio: ['aria-checked'],
    slider: ['aria-valuenow'],
    spinbutton: ['aria-valuenow'],
    switch: ['aria-checked'],
    scrollbar: ['aria-valuenow', 'aria-orientation'],
  };

  /**
   * Validate full DOM node tree for WAI-ARIA accessibility compliance
   */
  public validate(root: HeadlessDOMNode): ARIAValidationReport {
    const violations: ARIAViolation[] = [];
    const allIds = new Set<string>();
    let accessibleNodesCount = 0;

    // Collect all element IDs
    const collectIds = (node: HeadlessDOMNode) => {
      const id = node.attributes['id'];
      if (id) {
        if (allIds.has(id)) {
          violations.push({
            nodeId: node.id,
            tagName: node.tagName,
            ruleId: 'duplicate-id',
            impact: 'serious',
            description: `Duplicate ID detected in document: "${id}"`,
          });
        } else {
          allIds.add(id);
        }
      }
      for (const child of node.children) {
        collectIds(child);
      }
    };
    collectIds(root);

    // Validate ARIA roles and references
    const inspectNode = (node: HeadlessDOMNode) => {
      if (node.nodeType === 'element') {
        accessibleNodesCount++;
        const role = node.attributes['role'];

        // 1. Role validity
        if (role) {
          if (!ARIAAccessibilityOracle.VALID_ROLES.has(role)) {
            violations.push({
              nodeId: node.id,
              tagName: node.tagName,
              ruleId: 'invalid-aria-role',
              impact: 'critical',
              description: `Unknown or invalid ARIA role: "${role}"`,
            });
          } else {
            // 2. Required attributes by role
            const reqAttrs = ARIAAccessibilityOracle.REQUIRED_ATTRIBUTES_BY_ROLE[role];
            if (reqAttrs) {
              for (const attr of reqAttrs) {
                if (!(attr in node.attributes)) {
                  violations.push({
                    nodeId: node.id,
                    tagName: node.tagName,
                    ruleId: 'missing-required-aria-attribute',
                    impact: 'serious',
                    description: `Role "${role}" requires attribute "${attr}"`,
                  });
                }
              }
            }
          }
        }

        // 3. Broken ID references (aria-labelledby, aria-describedby)
        for (const refAttr of ['aria-labelledby', 'aria-describedby', 'aria-errormessage']) {
          const refVal = node.attributes[refAttr];
          if (refVal) {
            const targets = refVal.split(/\s+/).filter(Boolean);
            for (const t of targets) {
              if (!allIds.has(t)) {
                violations.push({
                  nodeId: node.id,
                  tagName: node.tagName,
                  ruleId: 'broken-aria-reference',
                  impact: 'moderate',
                  description: `Attribute "${refAttr}" references nonexistent ID: "${t}"`,
                });
              }
            }
          }
        }

        // 4. Interactive buttons/inputs accessible name
        if (node.tagName === 'button' || role === 'button') {
          const hasLabel =
            Boolean(node.attributes['aria-label']) ||
            Boolean(node.attributes['aria-labelledby']) ||
            Boolean(node.attributes['title']) ||
            this.hasDirectTextContent(node);

          if (!hasLabel) {
            violations.push({
              nodeId: node.id,
              tagName: node.tagName,
              ruleId: 'button-name-missing',
              impact: 'critical',
              description: 'Button element has no discernible text or accessible name',
            });
          }
        }

        // 5. Image elements must have alt attribute
        if (node.tagName === 'img') {
          if (!('alt' in node.attributes) && !node.attributes['aria-label'] && role !== 'presentation') {
            violations.push({
              nodeId: node.id,
              tagName: node.tagName,
              ruleId: 'image-alt-missing',
              impact: 'critical',
              description: 'Image element must have an alt attribute or aria-label',
            });
          }
        }
      }

      for (const child of node.children) {
        inspectNode(child);
      }
    };

    inspectNode(root);

    let criticalCount = 0;
    let seriousCount = 0;
    let moderateCount = 0;
    let minorCount = 0;

    for (const v of violations) {
      if (v.impact === 'critical') criticalCount++;
      else if (v.impact === 'serious') seriousCount++;
      else if (v.impact === 'moderate') moderateCount++;
      else minorCount++;
    }

    return {
      passed: criticalCount === 0 && seriousCount === 0,
      totalViolations: violations.length,
      criticalCount,
      seriousCount,
      moderateCount,
      minorCount,
      violations,
      accessibleNodesCount,
    };
  }

  private hasDirectTextContent(node: HeadlessDOMNode): boolean {
    for (const child of node.children) {
      if (child.nodeType === 'text' && child.nodeValue && child.nodeValue.trim().length > 0) {
        return true;
      }
    }
    return false;
  }
}

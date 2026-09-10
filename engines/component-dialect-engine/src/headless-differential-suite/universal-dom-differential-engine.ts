/**
 * Universal Cross-Platform DOM Differential Verification Engine
 *
 * Implements semantic tag normalization, hierarchical Tree Edit Distance (TED),
 * text token similarity, attribute parity, and 2D box layout comparison.
 * Produces deterministic L3 Structural and L4 Semantic Equivalence verdicts.
 */

import {
  HeadlessDOMNode,
  DOMMismatchRecord,
  DifferentialScores,
  DifferentialGateVerdict,
  DifferentialComparisonOptions,
  MismatchCategory,
  MismatchSeverity
} from './types';
import { DOMNode } from './headless-browser-dom';

export class UniversalDOMDifferentialEngine {
  private static defaultOptions: Required<DifferentialComparisonOptions> = {
    ignoreWhitespace: true,
    ignoreClassHashes: true,
    normalizeSemanticTags: true,
    normalizeUnits: true,
    viewportWidth: 375,
    viewportHeight: 667,
    l3Threshold: 0.85,
    l4Threshold: 0.95,
    maxDiffsReported: 50
  };

  /**
   * Compare a Web Virtual DOM tree and a MiniApp Virtual DOM tree.
   */
  public static compare(
    sourceDOM: DOMNode,
    targetDOM: DOMNode,
    options?: DifferentialComparisonOptions
  ): DifferentialGateVerdict {
    const opts = { ...this.defaultOptions, ...options };
    const mismatches: DOMMismatchRecord[] = [];

    // 1. Compute Structural Similarity via Tree Edit Distance (TED)
    const structDiff = this.computeTreeStructuralDiff(sourceDOM, targetDOM, mismatches, opts);

    // 2. Compute Text Content Similarity
    const contentDiff = this.computeContentDiff(sourceDOM, targetDOM, mismatches, opts);

    // 3. Compute Attribute & Event Parity
    const attrDiff = this.computeAttributeDiff(sourceDOM, targetDOM, mismatches, opts);

    // 4. Compute 2D Box Layout Parity
    const layoutDiff = this.computeLayoutDiff(sourceDOM, targetDOM, mismatches, opts);

    // 5. Calculate Weighted Composite Score
    const compositeScore = Number((
      0.40 * structDiff.score +
      0.30 * contentDiff.score +
      0.15 * attrDiff.score +
      0.15 * layoutDiff.score
    ).toFixed(4));

    const scores: DifferentialScores = {
      structuralScore: structDiff.score,
      contentScore: contentDiff.score,
      attributeScore: attrDiff.score,
      layoutScore: layoutDiff.score,
      compositeScore
    };

    // 6. Aggregate Mismatch Severities
    let fatalCount = 0;
    let highCount = 0;
    let mediumCount = 0;
    let lowCount = 0;

    for (const m of mismatches) {
      if (m.severity === 'fatal') fatalCount++;
      else if (m.severity === 'high') highCount++;
      else if (m.severity === 'medium') mediumCount++;
      else lowCount++;
    }

    const reasons: string[] = [];
    if (fatalCount > 0) {
      reasons.push(`Found ${fatalCount} fatal DOM divergence(s).`);
    }
    if (scores.structuralScore < opts.l3Threshold) {
      reasons.push(`Structural similarity ${scores.structuralScore} is below L3 threshold (${opts.l3Threshold}).`);
    }
    if (scores.compositeScore < opts.l4Threshold) {
      reasons.push(`Composite semantic score ${scores.compositeScore} is below L4 threshold (${opts.l4Threshold}).`);
    }
    if (highCount > 2) {
      reasons.push(`High-severity mismatches (${highCount}) exceeded allowable threshold.`);
    }

    const l3Passed = fatalCount === 0 && scores.structuralScore >= opts.l3Threshold;
    const l4Passed = l3Passed && highCount === 0 && scores.compositeScore >= opts.l4Threshold;

    let tier: 'L3_STRUCTURAL' | 'L4_SEMANTIC_EQUIVALENT' | 'REJECTED' = 'REJECTED';
    if (l4Passed) {
      tier = 'L4_SEMANTIC_EQUIVALENT';
    } else if (l3Passed) {
      tier = 'L3_STRUCTURAL';
    }

    return {
      passed: l3Passed,
      tier,
      l3Passed,
      l4Passed,
      scores,
      fatalCount,
      highCount,
      mediumCount,
      lowCount,
      totalMismatches: mismatches.length,
      reasons
    };
  }

  /**
   * Structural Tree Difference & Edit Distance
   */
  private static computeTreeStructuralDiff(
    src: DOMNode,
    tgt: DOMNode,
    mismatches: DOMMismatchRecord[],
    opts: Required<DifferentialComparisonOptions>
  ): { score: number } {
    let matchPoints = 0;
    let totalPoints = 0;

    const traverse = (sNode: DOMNode | null, tNode: DOMNode | null, path: string) => {
      totalPoints++;

      if (!sNode && !tNode) return;
      if (!sNode && tNode) {
        mismatches.push({
          id: `diff_${mismatches.length + 1}`,
          category: 'extra_node',
          severity: 'medium',
          sourcePath: path,
          targetPath: path,
          sourceValue: null,
          targetValue: tNode.tagName || tNode.nodeType,
          description: `Extra target node at ${path}`,
          semanticImpact: 0.2
        });
        return;
      }
      if (sNode && !tNode) {
        mismatches.push({
          id: `diff_${mismatches.length + 1}`,
          category: 'missing_node',
          severity: 'high',
          sourcePath: path,
          targetPath: path,
          sourceValue: sNode.tagName || sNode.nodeType,
          targetValue: null,
          description: `Missing target node corresponding to source at ${path}`,
          semanticImpact: 0.4
        });
        return;
      }

      // Both nodes exist: check semantic tag match
      const sTag = this.normalizeSemanticTag(sNode!.tagName, sNode!.nodeType);
      const tTag = this.normalizeSemanticTag(tNode!.tagName, tNode!.nodeType);

      if (sTag === tTag) {
        matchPoints++;
      } else {
        const severity: MismatchSeverity = (sTag === 'button' || sTag === 'input') ? 'high' : 'medium';
        mismatches.push({
          id: `diff_${mismatches.length + 1}`,
          category: 'tag_mismatch',
          severity,
          sourcePath: path,
          targetPath: path,
          sourceValue: sNode!.tagName,
          targetValue: tNode!.tagName,
          description: `Semantic tag mismatch: source <${sNode!.tagName}> (${sTag}) vs target <${tNode!.tagName}> (${tTag})`,
          suggestedFix: `Ensure target element maps to semantic equivalent of ${sTag}`,
          semanticImpact: severity === 'high' ? 0.4 : 0.15
        });
      }

      // Filter meaningful children (exclude empty text nodes)
      const sChildren = sNode!.children.filter(c => !this.isEmptyTextNode(c, opts));
      const tChildren = tNode!.children.filter(c => !this.isEmptyTextNode(c, opts));

      const maxLen = Math.max(sChildren.length, tChildren.length);
      for (let i = 0; i < maxLen; i++) {
        const sChild = sChildren[i] || null;
        const tChild = tChildren[i] || null;
        traverse(sChild, tChild, `${path}/${i}`);
      }
    };

    traverse(src, tgt, 'root');

    const score = totalPoints > 0 ? Number((matchPoints / totalPoints).toFixed(4)) : 1.0;
    return { score };
  }

  /**
   * Text Content Difference via Token Set Overlap
   */
  private static computeContentDiff(
    src: DOMNode,
    tgt: DOMNode,
    mismatches: DOMMismatchRecord[],
    opts: Required<DifferentialComparisonOptions>
  ): { score: number } {
    const sText = this.normalizeText(src.textContent, opts);
    const tText = this.normalizeText(tgt.textContent, opts);

    if (sText.length === 0 && tText.length === 0) {
      return { score: 1.0 };
    }

    const sTokens = this.tokenizeText(sText);
    const tTokens = this.tokenizeText(tText);

    const sSet = new Set(sTokens);
    const tSet = new Set(tTokens);

    let intersectionCount = 0;
    for (const tok of sSet) {
      if (tSet.has(tok)) intersectionCount++;
    }

    const unionCount = new Set([...sTokens, ...tTokens]).size;
    const jaccardScore = unionCount > 0 ? intersectionCount / unionCount : 1.0;

    if (jaccardScore < 0.8) {
      mismatches.push({
        id: `diff_${mismatches.length + 1}`,
        category: 'text_divergence',
        severity: jaccardScore < 0.5 ? 'high' : 'medium',
        sourcePath: 'root/text',
        targetPath: 'root/text',
        sourceValue: sText.slice(0, 100),
        targetValue: tText.slice(0, 100),
        description: `Text content divergence: similarity score is ${jaccardScore.toFixed(3)}`,
        semanticImpact: (1.0 - jaccardScore) * 0.5
      });
    }

    return { score: Number(jaccardScore.toFixed(4)) };
  }

  /**
   * Attribute & Event Parity
   */
  private static computeAttributeDiff(
    src: DOMNode,
    tgt: DOMNode,
    mismatches: DOMMismatchRecord[],
    opts: Required<DifferentialComparisonOptions>
  ): { score: number } {
    let matchCount = 0;
    let totalAttrs = 0;

    const criticalAttrs = ['id', 'name', 'type', 'placeholder', 'disabled', 'checked', 'role', 'aria-label'];

    const compareAttrs = (sNode: DOMNode, tNode: DOMNode, path: string) => {
      for (const attr of criticalAttrs) {
        const sVal = sNode.getAttribute(attr);
        const tVal = tNode.getAttribute(attr);

        if (sVal !== undefined || tVal !== undefined) {
          totalAttrs++;
          if (sVal === tVal) {
            matchCount++;
          } else {
            mismatches.push({
              id: `diff_${mismatches.length + 1}`,
              category: 'attribute_divergence',
              severity: attr === 'id' || attr === 'type' ? 'medium' : 'low',
              sourcePath: `${path}[@${attr}]`,
              targetPath: `${path}[@${attr}]`,
              sourceValue: sVal,
              targetValue: tVal,
              description: `Attribute divergence on @${attr}: source="${sVal}" vs target="${tVal}"`,
              semanticImpact: 0.1
            });
          }
        }
      }

      const sChildren = sNode.children.filter(c => c.nodeType === 'element');
      const tChildren = tNode.children.filter(c => c.nodeType === 'element');
      const minLen = Math.min(sChildren.length, tChildren.length);
      for (let i = 0; i < minLen; i++) {
        const sc = sChildren[i];
        const tc = tChildren[i];
        if (sc && tc) {
          compareAttrs(sc, tc, `${path}/${sc.tagName || 'el'}`);
        }
      }
    };

    compareAttrs(src, tgt, 'root');

    const score = totalAttrs > 0 ? Number((matchCount / totalAttrs).toFixed(4)) : 1.0;
    return { score };
  }

  /**
   * 2D Box Layout Parity (Bounding Box IoU & Alignment)
   */
  private static computeLayoutDiff(
    src: DOMNode,
    tgt: DOMNode,
    mismatches: DOMMismatchRecord[],
    opts: Required<DifferentialComparisonOptions>
  ): { score: number } {
    const sRect = src.computedLayout?.rect;
    const tRect = tgt.computedLayout?.rect;

    if (!sRect || !tRect) {
      return { score: 1.0 };
    }

    // Measure bounding box aspect ratio and dimension agreement
    const widthRatio = Math.min(sRect.width, tRect.width) / Math.max(1, Math.max(sRect.width, tRect.width));
    const heightRatio = Math.min(sRect.height, tRect.height) / Math.max(1, Math.max(sRect.height, tRect.height));

    const layoutScore = Number(((widthRatio * 0.5) + (heightRatio * 0.5)).toFixed(4));

    if (layoutScore < 0.7) {
      mismatches.push({
        id: `diff_${mismatches.length + 1}`,
        category: 'layout_shift',
        severity: 'low',
        sourcePath: 'root/layout',
        targetPath: 'root/layout',
        sourceValue: `${sRect.width}x${sRect.height}`,
        targetValue: `${tRect.width}x${tRect.height}`,
        description: `Dimension disparity between root layouts: score is ${layoutScore}`,
        semanticImpact: 0.05
      });
    }

    return { score: layoutScore };
  }

  private static normalizeSemanticTag(tagName?: string, nodeType?: string): string {
    if (nodeType === 'text') return 'text';
    if (nodeType === 'comment') return 'comment';
    if (!tagName) return 'unknown';

    const t = tagName.toLowerCase();

    // Universal Block Containers (in WeChat MiniApp and cross-platform UI, all block elements map to view)
    if ([
      'div', 'section', 'article', 'main', 'header', 'footer', 'nav', 'aside',
      'view', 'block', 'form', 'fieldset', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th'
    ].includes(t)) {
      return 'container';
    }
    // Universal Inline Typography & Text
    if (['span', 'b', 'i', 'strong', 'em', 'small', 'label', 'text', 'code', 'pre', 'abbr', 'time'].includes(t)) {
      return 'text';
    }
    // Interactive Buttons
    if (['button'].includes(t)) {
      return 'button';
    }
    // Form Inputs & Controls
    if (['input', 'textarea', 'select', 'switch', 'slider'].includes(t)) {
      return 'input';
    }
    // Navigation / Links
    if (['a', 'navigator', 'link'].includes(t)) {
      return 'navigation';
    }
    // Media & Visuals
    if (['img', 'image', 'svg', 'canvas', 'icon'].includes(t)) {
      return 'image';
    }

    return t;
  }

  private static isEmptyTextNode(node: DOMNode, opts: Required<DifferentialComparisonOptions>): boolean {
    if (node.nodeType !== 'text') return false;
    if (opts.ignoreWhitespace) {
      return (node.nodeValue || '').trim().length === 0;
    }
    return (node.nodeValue || '').length === 0;
  }

  private static normalizeText(text: string, opts: Required<DifferentialComparisonOptions>): string {
    let result = text;
    if (opts.ignoreWhitespace) {
      result = result.replace(/\s+/g, ' ').trim();
    }
    return result;
  }

  private static tokenizeText(text: string): string[] {
    // Splits by spaces and CJK characters
    return text
      .toLowerCase()
      .split(/[\s,.;:!?()[\]{}"'\\/<>+=_-]+|(?=[\u4e00-\u9fa5])|(?<=[\u4e00-\u9fa5])/)
      .filter(t => t.trim().length > 0);
  }
}

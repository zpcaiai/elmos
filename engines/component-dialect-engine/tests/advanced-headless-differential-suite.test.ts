/**
 * @file advanced-headless-differential-suite.test.ts
 * @description Comprehensive Jest test suite for Advanced Headless Differential Suite (Skill 1221).
 * Tests Zhang-Shasha Tree Edit Distance, WCAG Color Contrast Oracle, ARIA Accessibility Oracle,
 * and Visual Layout Geometry Matcher.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import {
  TreeEditDistanceEngine,
  TreeNode,
  ColorContrastAccessibilityOracle,
  ARIAAccessibilityOracle,
  VisualLayoutGeometryMatcher,
  HeadlessDOMNode,
} from '../src/headless-differential-suite';

describe('Advanced Headless Differential Suite (Skill 1221)', () => {
  describe('Zhang-Shasha Tree Edit Distance Engine', () => {
    const tedEngine = new TreeEditDistanceEngine();

    it('should report distance 0 and similarity 1.0 for identical trees', () => {
      const tree: TreeNode = {
        id: '1',
        label: 'div',
        children: [
          { id: '2', label: 'header', children: [{ id: '3', label: 'h1', children: [] }] },
          { id: '4', label: 'main', children: [{ id: '5', label: 'p', children: [] }] },
        ],
      };

      const result = tedEngine.compute(tree, tree);
      expect(result.distance).toBe(0);
      expect(result.similarity).toBe(1.0);
      expect(result.matchedNodeCount).toBe(5);
      expect(result.insertedNodeCount).toBe(0);
      expect(result.deletedNodeCount).toBe(0);
    });

    it('should compute correct edit distance when nodes are deleted or inserted', () => {
      const treeA: TreeNode = {
        id: '1',
        label: 'div',
        children: [
          { id: '2', label: 'p', children: [] },
          { id: '3', label: 'span', children: [] },
        ],
      };

      const treeB: TreeNode = {
        id: '1',
        label: 'div',
        children: [{ id: '2', label: 'p', children: [] }],
      };

      const result = tedEngine.compute(treeA, treeB);
      expect(result.distance).toBe(1.0); // Deletion of span
      expect(result.similarity).toBeLessThan(1.0);
      expect(result.deletedNodeCount).toBe(1);
    });
  });

  describe('Color Contrast Accessibility Oracle', () => {
    const oracle = new ColorContrastAccessibilityOracle();

    it('should correctly linearize and compute relative luminance', () => {
      const white = { r: 255, g: 255, b: 255, a: 1 };
      const black = { r: 0, g: 0, b: 0, a: 1 };

      expect(ColorContrastAccessibilityOracle.calculateLuminance(white)).toBeCloseTo(1.0, 2);
      expect(ColorContrastAccessibilityOracle.calculateLuminance(black)).toBeCloseTo(0.0, 2);
    });

    it('should compute exact contrast ratio for black on white (21:1)', () => {
      const ratio = ColorContrastAccessibilityOracle.calculateContrastRatio(
        { r: 0, g: 0, b: 0 },
        { r: 255, g: 255, b: 255 }
      );
      expect(ratio).toBeCloseTo(21.0, 1);
    });

    it('should evaluate WCAG AA/AAA compliance and suggest repairs for low contrast', () => {
      // Light gray on white (#aaaaaa on #ffffff) - fails WCAG AA
      const res = oracle.evaluate('#aaaaaa', '#ffffff');
      expect(res.wcagAATextPassed).toBe(false);
      expect(res.suggestedTextColor).toBeDefined();

      // Deep blue on white (#1e3a8a on #ffffff) - passes WCAG AAA
      const goodRes = oracle.evaluate('#1e3a8a', '#ffffff');
      expect(goodRes.wcagAATextPassed).toBe(true);
      expect(goodRes.wcagAAATextPassed).toBe(true);
    });
  });

  describe('ARIA Accessibility Oracle', () => {
    const oracle = new ARIAAccessibilityOracle();

    it('should pass on valid, fully accessible DOM tree', () => {
      const validDom: HeadlessDOMNode = {
        id: 'root',
        nodeType: 'element',
        tagName: 'div',
        attributes: {},
        classList: [],
        style: {},
        children: [
          {
            id: 'btn1',
            nodeType: 'element',
            tagName: 'button',
            attributes: { 'aria-label': 'Close dialog' },
            classList: [],
            style: {},
            children: [],
          },
          {
            id: 'chk1',
            nodeType: 'element',
            tagName: 'div',
            attributes: { role: 'checkbox', 'aria-checked': 'true', 'aria-label': 'Accept Terms' },
            classList: [],
            style: {},
            children: [],
          },
        ],
      };

      const report = oracle.validate(validDom);
      expect(report.passed).toBe(true);
      expect(report.criticalCount).toBe(0);
      expect(report.seriousCount).toBe(0);
    });

    it('should detect invalid role and missing required role attributes', () => {
      const invalidDom: HeadlessDOMNode = {
        id: 'root',
        nodeType: 'element',
        tagName: 'div',
        attributes: {},
        classList: [],
        style: {},
        children: [
          {
            id: 'bad-role',
            nodeType: 'element',
            tagName: 'div',
            attributes: { role: 'super-button' }, // Invalid role
            classList: [],
            style: {},
            children: [],
          },
          {
            id: 'missing-attr',
            nodeType: 'element',
            tagName: 'div',
            attributes: { role: 'checkbox' }, // Missing aria-checked
            classList: [],
            style: {},
            children: [],
          },
        ],
      };

      const report = oracle.validate(invalidDom);
      expect(report.passed).toBe(false);
      expect(report.violations.some((v) => v.ruleId === 'invalid-aria-role')).toBe(true);
      expect(report.violations.some((v) => v.ruleId === 'missing-required-aria-attribute')).toBe(true);
    });

    it('should detect duplicate IDs and broken references', () => {
      const brokenRefDom: HeadlessDOMNode = {
        id: 'root',
        nodeType: 'element',
        tagName: 'div',
        attributes: { id: 'dup1' },
        classList: [],
        style: {},
        children: [
          {
            id: 'child1',
            nodeType: 'element',
            tagName: 'p',
            attributes: { id: 'dup1' }, // Duplicate ID
            classList: [],
            style: {},
            children: [],
          },
          {
            id: 'child2',
            nodeType: 'element',
            tagName: 'input',
            attributes: { 'aria-describedby': 'nonexistent-helper' }, // Broken ref
            classList: [],
            style: {},
            children: [],
          },
        ],
      };

      const report = oracle.validate(brokenRefDom);
      expect(report.violations.some((v) => v.ruleId === 'duplicate-id')).toBe(true);
      expect(report.violations.some((v) => v.ruleId === 'broken-aria-reference')).toBe(true);
    });
  });

  describe('Visual Layout Geometry Matcher', () => {
    const matcher = new VisualLayoutGeometryMatcher();

    it('should compute 1.0 IoU for identical bounding boxes', () => {
      const box = { x: 10, y: 20, width: 100, height: 50 };
      const iou = VisualLayoutGeometryMatcher.computeIoU(box, box);
      expect(iou).toBe(1.0);
    });

    it('should compute 0.0 IoU for non-overlapping boxes', () => {
      const boxA = { x: 0, y: 0, width: 50, height: 50 };
      const boxB = { x: 100, y: 100, width: 50, height: 50 };
      const iou = VisualLayoutGeometryMatcher.computeIoU(boxA, boxB);
      expect(iou).toBe(0.0);
    });

    it('should calculate geometry metrics and visual alignment within tolerance', () => {
      const boxA = { x: 100, y: 100, width: 200, height: 80 };
      const boxB = { x: 102, y: 101, width: 200, height: 80 }; // 2px delta

      const metrics = matcher.compareBoxes(boxA, boxB, 4.0);
      expect(metrics.isVisuallyAligned).toBe(true);
      expect(metrics.iou).toBeGreaterThan(0.95);
      expect(metrics.hausdorffDistance).toBeLessThan(4.0);
    });
  });
});

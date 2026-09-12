/**
 * Headless Browser & MiniApp SSR DOM Differential Verification Suite - Types
 *
 * Defines the core models for virtual DOM representation, tree diffing,
 * cross-platform semantic normalization, and L3/L4 quality gate metrics.
 */

export type DOMNodeType = 'element' | 'text' | 'comment' | 'document' | 'fragment';

export interface BoxRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ComputedLayout {
  rect: BoxRect;
  display: string;
  visibility: 'visible' | 'hidden' | 'collapse';
  flexDirection?: 'row' | 'column' | 'row-reverse' | 'column-reverse';
  justifyContent?: string;
  alignItems?: string;
}

export interface HeadlessDOMNode {
  id: string;
  nodeType: DOMNodeType;
  tagName?: string;
  nodeValue?: string;
  attributes: Record<string, string>;
  classList: string[];
  style: Record<string, string>;
  children: HeadlessDOMNode[];
  parent?: HeadlessDOMNode;
  computedLayout?: ComputedLayout;
  sourceLocation?: {
    line: number;
    column: number;
  };
}

export interface NormalizedDOMNode {
  path: string;
  semanticTag: string; // e.g. 'container', 'text', 'button', 'input', 'list', 'list-item', 'image'
  originalTag: string;
  text: string;
  normalizedAttributes: Record<string, string>;
  classes: string[];
  layout?: BoxRect;
  children: NormalizedDOMNode[];
}

export type MismatchSeverity = 'fatal' | 'high' | 'medium' | 'low' | 'info';

export type MismatchCategory =
  | 'tag_mismatch'
  | 'missing_node'
  | 'extra_node'
  | 'text_divergence'
  | 'attribute_divergence'
  | 'class_divergence'
  | 'style_divergence'
  | 'layout_shift'
  | 'hierarchy_divergence';

export interface DOMMismatchRecord {
  id: string;
  category: MismatchCategory;
  severity: MismatchSeverity;
  sourcePath: string;
  targetPath: string;
  sourceValue: any;
  targetValue: any;
  description: string;
  suggestedFix?: string;
  semanticImpact: number; // 0.0 to 1.0
}

export interface DifferentialScores {
  structuralScore: number;       // 0.0 to 1.0 (Tree Edit Distance similarity)
  contentScore: number;          // 0.0 to 1.0 (Text token overlap & similarity)
  attributeScore: number;        // 0.0 to 1.0 (Key attributes & role match)
  layoutScore: number;           // 0.0 to 1.0 (2D box overlap & flow agreement)
  compositeScore: number;        // Weighted composite score (0.0 to 1.0)
}

export interface DifferentialGateVerdict {
  passed: boolean;
  tier: 'L3_STRUCTURAL' | 'L4_SEMANTIC_EQUIVALENT' | 'REJECTED';
  l3Passed: boolean;
  l4Passed: boolean;
  scores: DifferentialScores;
  fatalCount: number;
  highCount: number;
  mediumCount: number;
  lowCount: number;
  totalMismatches: number;
  reasons: string[];
  mismatches?: DOMMismatchRecord[];
}

export interface DifferentialComparisonOptions {
  ignoreWhitespace?: boolean;
  ignoreClassHashes?: boolean;
  normalizeSemanticTags?: boolean;
  normalizeUnits?: boolean; // convert rpx <-> px
  viewportWidth?: number;
  viewportHeight?: number;
  l3Threshold?: number; // default 0.85
  l4Threshold?: number; // default 0.95
  maxDiffsReported?: number;
}

export interface ComponentRenderContext {
  props?: Record<string, any>;
  state?: Record<string, any>;
  slots?: Record<string, string | HeadlessDOMNode>;
  env?: {
    platform?: 'web' | 'wechat-miniapp' | 'alipay-miniapp';
    locale?: string;
  };
}

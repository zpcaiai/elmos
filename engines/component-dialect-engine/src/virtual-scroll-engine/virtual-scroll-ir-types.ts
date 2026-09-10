/**
 * @file virtual-scroll-ir-types.ts
 * @description Universal Virtual Windowing and Infinite Scroll IR Types.
 * Models virtual scroll window calculation, dynamic height measurement cache,
 * binary search prefix-sum offsets, overscan buffers, and cross-framework emitters.
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform).
 */

export type ScrollDirection = 'vertical' | 'horizontal';

export interface VirtualScrollItemSize {
  index: number;
  size: number;
  offset: number;
}

export interface VirtualScrollConfigIR {
  totalItems: number;
  itemHeight: number | 'dynamic';
  estimatedItemHeight?: number;
  viewportHeight: number;
  overscan: number; // Number of extra items rendered before and after visible window
  direction: ScrollDirection;
  stickyIndices?: number[];
  scrollThrottleMs?: number;
}

export interface VirtualWindowSliceIR {
  startIndex: number;
  endIndex: number;
  totalSize: number;
  startOffset: number;
  endOffset: number;
  visibleItems: VirtualScrollItemSize[];
  isAtTop: boolean;
  isAtBottom: boolean;
}

export type VirtualListFrameworkId =
  | 'react-virtual'
  | 'vue-virtual'
  | 'miniapp-virtual'
  | 'arkui-virtual';

export interface VirtualListEmitResult {
  targetFramework: VirtualListFrameworkId;
  componentCode: string;
  styleCode?: string;
  helperCode?: string;
  templateCode?: string; // For MiniApp / Vue
  warnings: string[];
}

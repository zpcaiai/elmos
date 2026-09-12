/**
 * @file virtual-window-calculator.ts
 * @description High-Performance Virtual Window Slice and Offset Calculator.
 * Supports:
 * 1. O(1) Fixed Height slicing
 * 2. O(log N) Dynamic Height Binary Search with Prefix-Sum offsets
 * 3. Dynamic size cache updates with incremental prefix re-indexing
 * 4. Velocity-aware asymmetric overscan extension to prevent blank flickers during fast fling gestures
 * Conforms to Batch 32 Skill 1205 (b32-desktop-web-crossplatform).
 */

import {
  VirtualScrollConfigIR,
  VirtualWindowSliceIR,
  VirtualScrollItemSize,
} from './virtual-scroll-ir-types';

export class VirtualWindowCalculator {
  private config: VirtualScrollConfigIR;
  private measuredSizes: number[] = [];
  private prefixOffsets: number[] = [];
  private lastScrollTop: number = 0;
  private lastScrollTimestamp: number = 0;
  private scrollVelocity: number = 0; // px / ms

  constructor(config: VirtualScrollConfigIR) {
    this.config = config;
    this.initializeMeasurements();
  }

  private initializeMeasurements(): void {
    const total = this.config.totalItems;
    const defaultSize =
      typeof this.config.itemHeight === 'number'
        ? this.config.itemHeight
        : this.config.estimatedItemHeight || 50;

    this.measuredSizes = new Array(total).fill(defaultSize);
    this.recomputePrefixOffsets();
  }

  public setTotalItems(total: number): void {
    const prevLength = this.measuredSizes.length;
    this.config.totalItems = total;
    const defaultSize =
      typeof this.config.itemHeight === 'number'
        ? this.config.itemHeight
        : this.config.estimatedItemHeight || 50;

    if (total > prevLength) {
      for (let i = prevLength; i < total; i++) {
        this.measuredSizes.push(defaultSize);
      }
    } else {
      this.measuredSizes.length = total;
    }
    this.recomputePrefixOffsets();
  }

  /**
   * Update dynamic measured size for an item after DOM render.
   */
  public setItemSize(index: number, size: number): void {
    if (index < 0 || index >= this.measuredSizes.length) return;
    if (this.measuredSizes[index] === size) return;

    this.measuredSizes[index] = size;
    this.recomputePrefixOffsets(index);
  }

  /**
   * Recompute prefix sum offsets from a starting index.
   */
  private recomputePrefixOffsets(startIndex: number = 0): void {
    if (startIndex === 0 || this.prefixOffsets.length === 0) {
      this.prefixOffsets = new Array(this.measuredSizes.length);
      let acc = 0;
      for (let i = 0; i < this.measuredSizes.length; i++) {
        this.prefixOffsets[i] = acc;
        acc += this.measuredSizes[i] || 0;
      }
    } else {
      let acc = (this.prefixOffsets[startIndex] || 0) + (this.measuredSizes[startIndex] || 0);
      for (let i = startIndex + 1; i < this.measuredSizes.length; i++) {
        this.prefixOffsets[i] = acc;
        acc += this.measuredSizes[i] || 0;
      }
    }
  }

  /**
   * Total scrollable size in pixels.
   */
  public getTotalSize(): number {
    if (this.measuredSizes.length === 0) return 0;
    const lastIdx = this.measuredSizes.length - 1;
    const lastOffset = this.prefixOffsets[lastIdx] || 0;
    const lastSize = this.measuredSizes[lastIdx] || 0;
    return lastOffset + lastSize;
  }

  /**
   * Compute virtual window slice for given scroll position and optional timestamp.
   */
  public computeWindow(scrollTop: number, currentTimestamp: number = Date.now()): VirtualWindowSliceIR {
    return this.calculateSlice(scrollTop, currentTimestamp);
  }

  /**
   * Slice calculation alias for virtual window.
   */
  public calculateSlice(scrollTop: number, currentTimestamp: number = Date.now()): VirtualWindowSliceIR {
    const totalItems = this.config.totalItems;
    if (totalItems === 0) {
      return {
        startIndex: 0,
        endIndex: 0,
        totalSize: 0,
        startOffset: 0,
        endOffset: 0,
        visibleItems: [],
        isAtTop: true,
        isAtBottom: true,
      };
    }

    // Velocity update
    if (this.lastScrollTimestamp > 0 && currentTimestamp > this.lastScrollTimestamp) {
      const dt = currentTimestamp - this.lastScrollTimestamp;
      const dy = scrollTop - this.lastScrollTop;
      this.scrollVelocity = dy / dt;
    }
    this.lastScrollTop = scrollTop;
    this.lastScrollTimestamp = currentTimestamp;

    // Expand overscan in direction of fast scroll velocity
    let leadingOverscan = this.config.overscan;
    let trailingOverscan = this.config.overscan;

    if (this.scrollVelocity > 1.0) {
      // Fast scroll down: expand trailing overscan
      trailingOverscan = Math.min(this.config.overscan * 2, 20);
    } else if (this.scrollVelocity < -1.0) {
      // Fast scroll up: expand leading overscan
      leadingOverscan = Math.min(this.config.overscan * 2, 20);
    }

    let firstVisibleIndex = 0;
    let lastVisibleIndex = 0;

    if (typeof this.config.itemHeight === 'number') {
      // O(1) Fixed Height math
      const h = this.config.itemHeight;
      firstVisibleIndex = Math.floor(scrollTop / h);
      lastVisibleIndex = Math.floor((scrollTop + this.config.viewportHeight) / h);
    } else {
      // O(log N) Binary Search for dynamic height
      firstVisibleIndex = this.findNearestItemIndex(scrollTop);
      lastVisibleIndex = this.findNearestItemIndex(scrollTop + this.config.viewportHeight);
    }

    // Apply overscan
    const startIndex = Math.max(0, firstVisibleIndex - leadingOverscan);
    const endIndex = Math.min(totalItems - 1, lastVisibleIndex + trailingOverscan);

    const visibleItems: VirtualScrollItemSize[] = [];
    for (let i = startIndex; i <= endIndex; i++) {
      visibleItems.push({
        index: i,
        offset: this.prefixOffsets[i] || 0,
        size: this.measuredSizes[i] || 0,
      });
    }

    const startOffset = this.prefixOffsets[startIndex] || 0;
    const endOffset = (this.prefixOffsets[endIndex] || 0) + (this.measuredSizes[endIndex] || 0);
    const totalSize = this.getTotalSize();

    return {
      startIndex,
      endIndex,
      totalSize,
      startOffset,
      endOffset,
      visibleItems,
      isAtTop: scrollTop <= 0,
      isAtBottom: scrollTop + this.config.viewportHeight >= totalSize - 5,
    };
  }

  /**
   * Binary search for nearest item index at given target pixel offset.
   */
  public findNearestItemIndex(targetOffset: number): number {
    let low = 0;
    let high = this.prefixOffsets.length - 1;

    if (targetOffset <= 0) return 0;
    if (targetOffset >= this.getTotalSize()) return high;

    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const currentOffset = this.prefixOffsets[mid] || 0;
      const nextOffset = (this.prefixOffsets[mid + 1] !== undefined)
        ? this.prefixOffsets[mid + 1]!
        : currentOffset + (this.measuredSizes[mid] || 0);

      if (currentOffset <= targetOffset && targetOffset < nextOffset) {
        return mid;
      }

      if (targetOffset < currentOffset) {
        high = mid - 1;
      } else {
        low = mid + 1;
      }
    }

    return Math.max(0, Math.min(low, this.prefixOffsets.length - 1));
  }

  public getItemOffset(index: number): number {
    return this.prefixOffsets[index] || 0;
  }

  public getItemSize(index: number): number {
    return this.measuredSizes[index] || 0;
  }
}

/**
 * @file visual-layout-geometry-matcher.ts
 * @description Sub-pixel bounding box, flexbox/grid layout geometry matcher with IoU and Hausdorff distance.
 * Quantifies visual layout fidelity and detects unintended layout shifts between source and target renderings.
 * Conforms to Batch 32 Skill 1221 (b32-accessibility-i18n-seo-visual-e2e).
 */

import { BoxRect } from './types';

export interface LayoutComparisonMetrics {
  iou: number; // Intersection over Union (0.0 to 1.0)
  overlapArea: number;
  unionArea: number;
  dx: number; // Horizontal offset
  dy: number; // Vertical offset
  dw: number; // Width divergence
  dh: number; // Height divergence
  aspectRatioDifference: number;
  hausdorffDistance: number;
  layoutShiftScore: number;
  isVisuallyAligned: boolean;
}

export class VisualLayoutGeometryMatcher {
  /**
   * Compute Intersection over Union (IoU) of two 2D bounding boxes
   */
  public static computeIoU(boxA: BoxRect, boxB: BoxRect): number {
    const xLeft = Math.max(boxA.x, boxB.x);
    const yTop = Math.max(boxA.y, boxB.y);
    const xRight = Math.min(boxA.x + boxA.width, boxB.x + boxB.width);
    const yBottom = Math.min(boxA.y + boxA.height, boxB.y + boxB.height);

    if (xRight < xLeft || yBottom < yTop) {
      return 0.0;
    }

    const intersectionArea = (xRight - xLeft) * (yBottom - yTop);
    const areaA = boxA.width * boxA.height;
    const areaB = boxB.width * boxB.height;
    const unionArea = areaA + areaB - intersectionArea;

    return unionArea > 0 ? intersectionArea / unionArea : 1.0;
  }

  /**
   * Compute Hausdorff distance between two rectangles (corner point sets)
   */
  public static computeHausdorffDistance(boxA: BoxRect, boxB: BoxRect): number {
    const cornersA = [
      { x: boxA.x, y: boxA.y },
      { x: boxA.x + boxA.width, y: boxA.y },
      { x: boxA.x, y: boxA.y + boxA.height },
      { x: boxA.x + boxA.width, y: boxA.y + boxA.height },
    ];

    const cornersB = [
      { x: boxB.x, y: boxB.y },
      { x: boxB.x + boxB.width, y: boxB.y },
      { x: boxB.x, y: boxB.y + boxB.height },
      { x: boxB.x + boxB.width, y: boxB.y + boxB.height },
    ];

    // Directed Hausdorff from A to B
    let maxDistAtoB = 0;
    for (const ptA of cornersA) {
      let minDist = Infinity;
      for (const ptB of cornersB) {
        const d = Math.hypot(ptA.x - ptB.x, ptA.y - ptB.y);
        if (d < minDist) minDist = d;
      }
      if (minDist > maxDistAtoB) maxDistAtoB = minDist;
    }

    // Directed Hausdorff from B to A
    let maxDistBtoA = 0;
    for (const ptB of cornersB) {
      let minDist = Infinity;
      for (const ptA of cornersA) {
        const d = Math.hypot(ptB.x - ptA.x, ptB.y - ptA.y);
        if (d < minDist) minDist = d;
      }
      if (minDist > maxDistBtoA) maxDistBtoA = minDist;
    }

    return Math.max(maxDistAtoB, maxDistBtoA);
  }

  /**
   * Compare two layout boxes with detailed geometry metrics
   */
  public compareBoxes(boxA: BoxRect, boxB: BoxRect, tolerancePx: number = 4.0): LayoutComparisonMetrics {
    const iou = VisualLayoutGeometryMatcher.computeIoU(boxA, boxB);
    const hausdorff = VisualLayoutGeometryMatcher.computeHausdorffDistance(boxA, boxB);

    const dx = Math.abs(boxA.x - boxB.x);
    const dy = Math.abs(boxA.y - boxB.y);
    const dw = Math.abs(boxA.width - boxB.width);
    const dh = Math.abs(boxA.height - boxB.height);

    const arA = boxA.height > 0 ? boxA.width / boxA.height : 1.0;
    const arB = boxB.height > 0 ? boxB.width / boxB.height : 1.0;
    const aspectRatioDiff = Math.abs(arA - arB);

    const areaA = boxA.width * boxA.height;
    const areaB = boxB.width * boxB.height;
    const intersectionArea = iou * (areaA + areaB) / (1 + iou);
    const unionArea = areaA + areaB - intersectionArea;

    // Cumulative layout shift estimate
    const viewportArea = 1920 * 1080;
    const impactFraction = unionArea / viewportArea;
    const distanceFraction = Math.hypot(dx, dy) / 1080;
    const layoutShiftScore = Math.round(impactFraction * distanceFraction * 1000) / 1000;

    const isVisuallyAligned = dx <= tolerancePx && dy <= tolerancePx && dw <= tolerancePx && dh <= tolerancePx;

    return {
      iou,
      overlapArea: intersectionArea,
      unionArea,
      dx,
      dy,
      dw,
      dh,
      aspectRatioDifference: aspectRatioDiff,
      hausdorffDistance: hausdorff,
      layoutShiftScore,
      isVisuallyAligned,
    };
  }
}
